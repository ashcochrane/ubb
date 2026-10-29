import logging
from datetime import date, datetime
from typing import Optional
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import ProtectedError
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404
from ninja import Query, Router

from apps.metering.pricing.receipts import (
    pricing_method_of,
    subject_type_of,
    uncosted_quantity_keys,
)
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.currency_policy import (
    FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY,
    UnsupportedCurrency,
    admit_currency,
)
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut
from core.responses import StatusResponse
from core.scheduling import validate_scheduled_instant
from api.v1.economic_question import ask_the_economic_query
from core.report_windows import (
    END_DATE_DESCRIPTION, START_DATE_DESCRIPTION, resolve_report_window,
    states_its_report_window)
from core.time_windows import REPORT_WINDOW_MAX_DAYS
from django.utils import timezone

from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    UsageBatchRequest, UsageBatchResponse,
    PaginatedUsageResponse,
    UsageEventDetailOut,
    TenantDefaultMarkupIn, TenantDefaultMarkupOut,
    TaskAnalyticsOut,
    PricingBookIn, PricingBookOut, CostBookIn, CostBookOut,
    PaginatedAgreedPrices, PaginatedPricingBooks, PaginatedCostBooks,
    PaginatedRates,
    BookPublishIn, BookPublishOut, PaginatedBookPublishes,
    CustomerOverrideIn, InheritedRuleOut, inherited_rule_out,
    ResolutionRunIn, ResolutionRunOut, resolution_run_out,
    PaginatedUnresolvedQueue, ProjectedAdjustmentOut, WaivedLossOut,
    UndeclaredGroupingField,
    book_change_body, book_change_diff_out, book_publish_out,
    agreed_price_out, pricing_book_out, cost_book_out, rate_out,
    usage_event_out,
    GroupingFieldRegistryIn, GroupingFieldRegistryOut, GroupingFieldValuesOut,
    GroupingOptionsOut, EconomicsOut,
)
from core.vocabulary import (
    AUDIT_ACTION_COST_BOOK_DECLARED,
    AUDIT_ACTION_COST_BOOK_WITHDRAWN,
    AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_DECLARED,
    AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_WITHDRAWN,
    AUDIT_ACTION_GROUPING_FIELD_DECLARED,
    AUDIT_ACTION_PRICING_BOOK_DECLARED,
    AUDIT_ACTION_PRICING_BOOK_PUBLISH_DECLARED,
    AUDIT_ACTION_PRICING_BOOK_PUBLISH_DISCARDED,
    AUDIT_ACTION_PRICING_BOOK_PUBLISH_PUBLISHED,
    AUDIT_ACTION_PRICING_BOOK_WITHDRAWN,
    AUDIT_ACTION_RESOLUTION_RUN_EXECUTED,
    AUDIT_ACTION_TENANT_DEFAULT_MARKUP_DECLARED,
    AUDIT_ACTION_TENANT_DEFAULT_MARKUP_WITHDRAWN,
    AUDIT_RESOURCE_TYPE_COST_BOOK,
    AUDIT_RESOURCE_TYPE_GROUPING_FIELD_REGISTRY,
    AUDIT_RESOURCE_TYPE_PRICING_BOOK,
    AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
    AUDIT_RESOURCE_TYPE_RESOLUTION_RUN,
    AUDIT_RESOURCE_TYPE_TENANT_DEFAULT_MARKUP,
    REVENUE_BASIS_VALUES,
)
from apps.metering.pricing.models import (
    CHANGE_ADD, CHANGE_RETIRE, LINE_RATE,
    CostBook, PricingBook, PricingBookPublish, Rate,
)
from api.v1.pagination import page
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.audit.actors import get_current_actor
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
# THE MODULE RATHER THAN ITS FUNCTIONS, so that each route handler can carry
# the SAME name as the read-contract call it makes without shadowing it.
# ADR-0006 §2 wants one canonical public term per concept, and a handler's name
# IS public: django-ninja builds the operationId from it, and the generated SDK
# names a module and a constant after that.
from apps.metering import queries as metering_queries
from apps.platform.event_types.costing import (
    admitted_supplier_cost_source, declaration_of)
from apps.platform.event_types.models import ValueTypeMismatch, quantity_under
from apps.platform.event_types.publication import last_published_declaration
from core.vocabulary import (
    COSTING_METHOD_REPORTED, DECLARATION_STATUS_DRAFT,
    GROUPING_FIELD_SCOPE_EVENT, SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_PROVIDER_RESPONSE)
from apps.metering.usage.services.usage_service import (
    EffectiveAtError, UsageService)
from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.queries import keys_by_slot, slot_map
from apps.platform.grouping_fields.services import GroupingFieldService

logger = logging.getLogger(__name__)

metering_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")


# --- The request-item adapters over the recording path ---------------------
#
# These moved here when the async accept pipeline was deleted. They were
# lifted out of this module by #113 to be SHARED between the endpoints and
# that pipeline; with the pipeline gone the two recording routes below are
# their only callers, so the seam that justified a separate module no longer
# has two sides. Written once, here, rather than twice: the single route and
# the batch route must map fields, take the same steps in the same order
# (`replay_or_record`, #605) and classify errors identically, or the batch
# stops being "N sequential singles".


class SupplierCostNotAdmissible(ValueError):
    """A supplier cost arrived on a transport the Event Type's last
    publication does not admit — or on both transports at once.

    Raised by :func:`admit_supplier_cost` before anything is written or
    recorded. The single route renders it as a **422**; the batch route renders
    it as a rejected ITEM verdict inside its always-200 body — the same shape
    every other per-item failure takes there, because on that route a non-200
    would mean the whole batch was not recorded (`docs/conventions/
    api-contract.md`, *Usage verdicts: data, not errors*). A ``ValueError`` so
    it takes the same lane as every other pre-recording refusal here.
    """


#: THE FIELD EACH REPORTED-COST SOURCE'S FIGURE ARRIVES ON (#324, #570) — one
#: transport per source, so the field a figure came in on says where the
#: caller's integration got it. A figure read off the supplier's response is
#: never sent in the field whose published contract means "the caller supplied
#: this" (owner ruling on #570): the two are different statements about one
#: number, and the declaration decides which one a call may make. Both land in
#: the one supplier-cost column, through the one keyword `usage_kwargs` maps
#: them onto, and a response reads either back as `provider_cost_micros`.
SUPPLIER_COST_TRANSPORTS = {
    SOURCE_KIND_CALLER_SUPPLIED: "provider_cost_micros",
    SOURCE_KIND_PROVIDER_RESPONSE: "provider_response_cost_micros",
}

#: What each transport's figure IS, in a refusal's words: every refusal opens
#: with the refused field's, and names the admissible field's — the published
#: meanings (`api/v1/schemas.py`), shortened to a clause.
_A_FIGURE_ON = {
    "provider_cost_micros":
        "a supplier cost supplied directly by the caller",
    "provider_response_cost_micros":
        "a supplier cost the caller obtained from the provider's response",
}


def _transports_carrying_a_figure(item):
    """The supplier-cost fields this request item sets, in a fixed order."""
    return [field for field in SUPPLIER_COST_TRANSPORTS.values()
            if getattr(item, field) is not None]


#: Each transport's source kind — :data:`SUPPLIER_COST_TRANSPORTS` read the
#: other way round.
_SOURCE_OF = {field: source
              for source, field in SUPPLIER_COST_TRANSPORTS.items()}


def _the_supplier_cost(item):
    """The one supplier-cost figure the item carries and the source kind of
    the transport it arrived on — `(None, None)` where it carries none.

    The source is the transport's, and that IS the source the figure was
    admitted under: admission has refused any item whose transport is not the
    one the governing publication admits, and any item carrying two."""
    carried = _transports_carrying_a_figure(item)
    if not carried:
        return None, None
    return getattr(item, carried[0]), _SOURCE_OF[carried[0]]


def _nothing_admissible(subject):
    return (
        f"{subject} admits no supplier cost on the call: neither "
        f"provider_cost_micros nor provider_response_cost_micros is "
        f"admissible. Each is admissible only where the Event Type's last "
        f"publication declares costing_method '{COSTING_METHOD_REPORTED}' "
        f"with a reported-cost mapping whose source_kind is "
        f"'{SOURCE_KIND_CALLER_SUPPLIED}' (for provider_cost_micros) or "
        f"'{SOURCE_KIND_PROVIDER_RESPONSE}' (for "
        f"provider_response_cost_micros). Declare and publish that, or send "
        f"what you believe this call cost as claimed_provider_cost_micros, "
        f"which is accepted on any event and is never treated as cost.")


#: THE NAMED REFUSAL OF A PROVIDER THE EVENT TYPE DOES NOT DECLARE (#572), as
#: the error-code catalogue registers it (`openapi/error-codes.json`): a 422 on
#: the single route, and the same code as a rejected item's verdict on a batch.
PROVIDER_CONFLICTS_WITH_EVENT_TYPE = "provider_conflicts_with_event_type"


class ProviderConflictsWithEventType(ValueError):
    """A provider named on the call that is not the one its Event Type's
    publication names (#572, ruled on #184, item 8 of the batch).

    A ``ValueError``, so both routes take it on the lane every other
    admission does — but it carries a CODE of its own, because the ruling
    asked for a named refusal: a caller has to be able to tell "you named the
    wrong supplier" from every other validation failure without parsing
    prose. :func:`usage_error` reads the code off it.
    """

    code = PROVIDER_CONFLICTS_WITH_EVENT_TYPE


def admit_provider(item, declaration):
    """The provider this item is recorded and costed under — the published
    Event Type's own, where there is one — or the refusal of a different one
    (#572, #193 §B3).

    **For a published Event Type its Provider is authoritative.** Cost
    resolution keys on the supplier the tenant declared, and a free-text
    `provider` on the call is the caller's say-so, which UBB used to select
    rates by while never reading the declaration. So:

    * a provider the declaration names, or none at all, proceeds, and the
      event is recorded and costed under the declared one (its key as the
      catalogue holds it now, `CostDeclaration.provider_key`);
    * any other provider is REFUSED, never silently trusted and never
      silently replaced — including one sent for an Event Type that declares
      no supplier, which is a statement that the work has none.

    An event with no published Event Type keeps the provider it sent:
    naming none is outside this (#567), and one nobody published is held
    whole for the tenant's decision (#568), its replay costed under the
    Provider of whatever the tenant says it was.

    **The message says what each answer means and never tells a caller to
    send the declared value.** The field is a statement about which supplier
    ran the call, and "send that one instead" would ask a caller who knows
    better to say otherwise (#570's lesson). Omitting it is always honest;
    the rest is the declaration's to change.
    """
    if declaration is None:
        return item.provider
    declared = declaration.provider_key
    if item.provider and item.provider != declared:
        if declared:
            raise ProviderConflictsWithEventType(
                f"provider {item.provider!r} is not the supplier the last "
                f"publication of Event Type {item.event_type!r} names, which "
                f"is {declared!r}. The supplier a published Event Type names "
                f"decides whose call it is and what its supplier cost resolves "
                f"under, so a different one is refused rather than trusted or "
                f"replaced. "
                f"Omit provider to record the call under {declared!r}; if "
                f"the call was another supplier's, it belongs to the Event "
                f"Type that names that supplier, or the Event Type's provider "
                f"is what needs correcting.")
        raise ProviderConflictsWithEventType(
            f"provider {item.provider!r} names a supplier, and the last "
            f"publication of Event Type {item.event_type!r} names none — it "
            f"meters work with no supplier. The supplier a published Event "
            f"Type names decides whose call it is and what its supplier cost "
            f"resolves under, so a supplier it does not name is refused rather "
            f"than trusted. Omit "
            f"provider; if the call is a supplier's, declare that provider on "
            f"the Event Type.")
    return declared


def admit_supplier_cost(item, declaration):
    """Refuse a supplier cost the Event Type's publication does not admit
    (#324), on a transport it does not admit, or on both at once (#570).

    **ONE RULE FOR BOTH FIELDS.** The declaration admits at most one source
    (`costing.admitted_supplier_cost_source`), the source names one field
    (`SUPPLIER_COST_TRANSPORTS`), and a request is admitted only when that one
    field is exactly what it set. So the owner's matrix on #570 is this one
    comparison: `caller_supplied` admits `provider_cost_micros` alone,
    `provider_response` admits `provider_response_cost_micros` alone, and
    `calculated`, no publication, or `reported` with no mapping admit neither.
    Both fields on one event are refused whatever is declared: nothing is
    summed, and nothing is chosen between two figures for one call.

    **WHY A REFUSAL AND NOT A QUIET DROP.** The figure is COGS or it is
    nothing: where no declaration admits it, UBB will never read it as cost, so
    an accepted call would tell an integrator their supplier costs are being
    recorded while every one of them is discarded. This repository has already
    paid for the softer version of that — a read route sent two query
    parameters it publishes nowhere, and the framework's habit of DROPPING what
    no schema declares kept it answering `200` on the axis default for years.
    An integrator must never spend months believing UBB is using a number it
    has been throwing away.

    **WHY HERE AND NOT IN THE RECORDING SERVICE.** This is a rule about the
    *request*: what a caller may assert, and how they are told they may not.
    The two routes below are the recording service's only callers, so the edge
    is the whole surface — and it is where the batch route can refuse ONE item
    without throwing away the events beside it.

    **IT RUNS BEFORE ANYTHING IS WRITTEN, AND AFTER THE REPLAY LOOKUP.**
    `replay_or_record` calls it above the grouping-field admission, which
    records novel values against a cardinality cap: a refusal underneath that
    would have spent a tenant's keyspace on a request that was never
    recorded. Nothing here writes, so going ahead of it is free. And the
    publication it is handed may have changed since an event was recorded, so
    a retry of that event is answered with what was recorded before this is
    asked (#605).

    **WHAT IT COSTS, STATED RATHER THAN HIDDEN.** Nothing of its own: it is
    handed the declaration :func:`replay_or_record` reads once per event
    naming an Event Type, which the provider admission needs on every such
    event (#572), and that same read is handed down to the costing, which
    therefore asks it no second time — one read of the cost declaration per
    event, as before #572. (`admit_quantities` reads the publication's value
    types on its own query, as it has since #603.) A batch pays it per item;
    it is deliberately not memoised across the batch, because a batch item is
    a whole independent request here and a shared verdict would be the first
    place they stopped being one.

    **EACH REFUSAL HAS ITS OWN MESSAGE**, and every one names what the caller
    may do next rather than only what they may not: it opens with what the
    refused field means, then names the field that IS admissible for the
    declared source and what THAT field means — or says neither is, which
    declarations would admit each, and the field accepted anywhere.

    **IT NEVER TELLS A CALLER TO MOVE A FIGURE TO THE OTHER FIELD.** The field
    a figure arrives on is the caller's statement of where it came from, so
    "send it there instead" would ask a caller holding a cost read off the
    provider's response to call it one they supplied directly — the relabelling
    the owner's ruling on #570 forbids. The message says which source the
    declaration admits and leaves the caller to say which theirs is: if it is
    the other one, the declaration is what needs to change.
    """
    carried = _transports_carrying_a_figure(item)
    if not carried:
        return
    source = admitted_supplier_cost_source(declaration)
    admitted = SUPPLIER_COST_TRANSPORTS.get(source)
    if carried == [admitted]:
        return
    subject = (f"Event Type {item.event_type!r}" if item.event_type
               else "An event that names no Event Type")
    if len(carried) > 1:
        raise SupplierCostNotAdmissible(
            "provider_cost_micros and provider_response_cost_micros were both "
            "sent. An event carries its supplier cost on one transport at "
            "most — the one its Event Type's last publication admits — and "
            "nothing is summed or chosen between two figures for one call. "
            + (f"{subject} admits only {admitted}, {_A_FIGURE_ON[admitted]}: "
               f"send one figure, and only on the field that says where it "
               f"came from." if admitted is not None
               else _nothing_admissible(subject)))
    (field,) = carried
    opening = f"{field} is {_A_FIGURE_ON[field]}."
    if admitted is None:
        raise SupplierCostNotAdmissible(
            f"{opening} {_nothing_admissible(subject)}")
    raise SupplierCostNotAdmissible(
        f"{opening} The last publication of {subject} declares a reported "
        f"cost whose source_kind is '{source}', so the only supplier cost it "
        f"admits on the call is {admitted}, {_A_FIGURE_ON[admitted]}. Where "
        f"your figure comes from decides the field: if it is not that source, "
        f"it is the declaration that has to change, and a change takes effect "
        f"when it is published.")


def usage_kwargs(item, *, provider, declaration):
    """The single↔batch pass-through, written ONCE (#112): the field-for-
    field map from a request item (RecordUsageRequest — the single and batch
    items share the schema) onto record_new_usage's keyword surface.

    **THE PROVIDER IS THE ADMITTED ONE, NOT THE ONE SENT (#572).** For a
    published Event Type it is the declared supplier — `admit_provider` has
    refused any other — so an omitted provider records and costs under the
    declaration's, and nothing downstream ever reads the caller's string for
    such an event.

    **EITHER SUPPLIER-COST TRANSPORT IS THE ONE SUPPLIER COST (#570).** A
    figure read off the provider's response and one the caller supplied are
    the same economic fact arriving two ways, so both are handed on as the one
    keyword the recording core costs a figure that arrived from — the compute
    spine's "a figure that arrived is a reported cost" branch — and land in the
    one column. Never through the caller's claim, which is never COGS. At most
    one of the two is set: `admit_supplier_cost` has refused both, and it runs
    first on every path that reaches here.

    **AND THE SOURCE IT WAS ADMITTED UNDER GOES WITH IT** (#179 §3.6, the
    owner's review of #570). One amount and no echo means the receipt is the
    only place left that can say which transport carried the figure, so the
    recording core is handed the source kind to keep there by value — never
    a second amount, and never the transport's own field.

    **AND THE DECLARATION THE ADMISSIONS READ GOES DOWN TO THE COSTING (#605).**
    The event pays one read of its Event Type's publication, and the
    admissions and the costing answer from the same one."""
    figure, source = _the_supplier_cost(item)
    return dict(
        idempotency_key=item.idempotency_key,
        provider_cost_micros=figure,
        reported_cost_source_kind=source,
        claimed_provider_cost_micros=item.claimed_provider_cost_micros,
        currency=item.currency,
        metadata=item.metadata,
        event_type=item.event_type,
        provider=provider,
        task_id=item.task_id,
        measurements=item.measurements,
        effective_at=item.effective_at,
        declaration=declaration,
    )


def usage_error(e):
    """The ONE recording error map (#112): exception → (code, detail).
    The specific-before-general order lives HERE and only here — the refusals
    that carry a NAMED code (`EffectiveAtError`, and since #572
    `ProviderConflictsWithEventType`; each IS a ValueError, so they must be
    tested before the generic branch), then plain ValueError — which is also
    what the other admissions raise (`SupplierCostNotAdmissible`,
    `QuantityNotAdmissible`, `GroupingFieldError`), so every refusal
    `replay_or_record` can raise is mapped here. The single endpoint raises
    the code as a Problem; the batch wraps the same code in a verdict dict.

    **A COST UBB CANNOT WORK OUT IS NO LONGER AN ERROR (#320)**, so the branch
    that was first here is gone along with the exception it named and the wire
    code it produced. The supplier has already run the call and already charged
    for it; the event is recorded with its cost said to be unresolved, and the
    caller learns that from the 200 body rather than from a 422 that throws the
    charge away."""
    if isinstance(e, (EffectiveAtError, ProviderConflictsWithEventType,
                      UnsupportedCurrency)):
        return e.code, str(e)
    return "validation_error", str(e)


def with_receipt_reads(result):
    """Surface what the receipt says, typed, on a success body — both recording
    surfaces return it.

    Two reads, and they answer two questions.

    The uncosted-quantity list says WHICH quantities went uncosted — a
    declared one no rate matched, or since #428 a name the Event Type's
    declaration does not carry; `costing_status` on the same body says THAT
    the cost is unresolved. Neither is the other: a tenant fixing this needs
    the specific declaration, and a reader totalling a column needs the
    status.

    The pricing method says HOW the customer price was derived; `pricing_status`
    beside it says whether that price is settled. Null means no derivation
    happened, and the status says why (#355).

    The subject type says WHAT the receipt explains — one usage row, or one
    canonical Charge (#370). It is read out of the record rather than inferred
    from the row the record hangs on, because an inference is a second answer
    able to disagree with the recorded one.

    **ALL THREE ARE ALREADY IN THE BODY, UNTYPED, AND THAT IS THE POINT OF
    LIFTING THEM.** These surfaces publish the whole record, which is
    `additionalProperties: true` — so a value inside it reaches a consumer with
    no schema saying what it may be, and a closed value set published that way
    is advertised nowhere. Lifting each into a typed field is what lets the
    contract carry the agreed vocabulary for it.

    **THE RECEIPT'S SHAPE IS ASKED FOR, NOT ASSUMED (#349).** An idempotent
    replay answers with the receipt the posting was recorded with, and the
    receipts module's readers refuse any record not in the one shape this code
    writes — the empty record included (#190). The question is asked once, in
    that module, because a second copy of it here is a second thing to
    repair."""
    # THE WIRE KEY, NOT THE COLUMN — spelled rather than taken from
    # `Posting.RECEIPT_COLUMN`. The two are the same word since #370 and that is
    # deliberate (ADR-0006 §2: one public name per concept), but they are two
    # facts: this reads the recording service's plain-data result, whose key is
    # what `RecordUsageResponse` publishes. Addressing it through the column's
    # constant would make a future column rename silently answer `None` here on
    # every receipt, with no test able to see it.
    receipt = result.get("pricing_receipt")
    result["uncosted_measurement_keys"] = uncosted_quantity_keys(receipt)
    result["pricing_method"] = pricing_method_of(receipt)
    result["pricing_receipt_subject_type"] = subject_type_of(receipt)
    return result


class QuantityNotAdmissible(ValueError):
    """A recorded quantity its declaration's value type refuses (#603).

    A ``ValueError``, so both routes refuse it as they refuse every other
    admission: a 422 on the single route, that one item in a batch."""


def admit_quantities(item, published):
    """Refuse a quantity its Event Type's last publication declares whole
    and the caller sent with a fraction (#603, ADR-0020).

    The request's own validator has already put every value in its canonical
    text, so a whole number written `12.0` is `12` by now and passes; what is
    asked here is only what a request cannot know until the Event Type is
    looked up — `integer` requires a whole value, `decimal` permits a
    fraction. The reader is the Measurement contract's own
    (`event_types.models.quantity_under`), asked of the published copy, never
    the draft (#605). A key no publication declares has no value type and is
    admitted as written: it is held for the tenant's decision, not refused.

    After the replay lookup and before anything is written, on
    `admit_supplier_cost`'s reasoning: a retry of something already recorded
    is answered first, and a refusal never burns grouping-field keyspace.
    """
    if not item.measurements or published is None:
        return
    value_types = {quantity.code: quantity.value_type
                   for quantity in published.measurements}
    for code, value in item.measurements.items():
        if code not in value_types:
            continue
        try:
            quantity_under(code, value_types[code], value)
        except ValueTypeMismatch as mismatch:
            raise QuantityNotAdmissible(
                f"measurements.{code}: {mismatch} The last publication of "
                f"{item.event_type!r} declares {code} "
                f"{value_types[code]!r}.") from None


def _rejected(code, detail):
    """A batch-item rejection verdict: the typed code plus the constant stop
    facts — a rejected item was never recorded, so nothing can have stopped,
    and nothing applied, bounded or measured a stop (#569: null, never 0) —
    and no price, so no reason for one (#603), and no receipt, so nothing it
    explains (#190). Every required-and-nullable acknowledgement fact is here,
    null."""
    return {"accepted": False, "code": code, "detail": detail,
            "stop": False, "stop_reason": None, "stop_scope": None,
            "trigger_source": None, "stop_bound_micros": None,
            "stop_measured_micros": None, "pricing_status_reason": None,
            "pricing_receipt": None, "pricing_receipt_subject_type": None}


def replay_or_record(tenant, customer, item):
    """One request item's recording, in the one order both routes take: its
    plain-data acknowledgement, or the ``ValueError`` that refuses it.

    The customer (and task) are resolved in the tenant first, by the caller,
    so nothing here is a way round authentication, tenant isolation or the
    lookup scope. Then, and the order is the point:

    1. **REPLAY WINS (#605).** An event already recorded under this key
       answers its original acknowledgement before any admission below is
       asked. Each reads current configuration — the Event Type's last
       publication and its supplier, the Grouping Field registry — and current
       configuration must not make an already-successful write unreplayable: a
       retry carrying a figure the publication has stopped admitting, a
       provider the Event Type has stopped naming, or a grouping value a field
       retired since would refuse, is the same event and gets the same answer.
       Found by `UsageService.replay`, the recording path's own lookup — keyed
       by tenant, customer and key, with no body compared.
    2. **The publication, read once** (`publication.last_published_declaration`)
       for every admission below that asks it and for the costing, which is
       handed its cost declaration (`costing.declaration_of`) rather than
       reading it again (#605) — none for an event naming no Event Type.
    3. **The provider (#572)**: a published Event Type's own supplier is
       authoritative, so another is refused by name
       (`provider_conflicts_with_event_type`) and an omitted one records under
       the declared (`admit_provider`).
    4. **A supplier cost (#324, #570)** is admissible only on the transport
       the Event Type's last publication admits — `provider_cost_micros` for
       a caller-supplied source, `provider_response_cost_micros` for one read
       off the provider's response, never both. Refused rather than dropped: a
       200 would tell an integrator UBB is using a number it discards.
    5. **A quantity's value type (#603)**: `integer` refuses a fraction, by
       the last publication's declaration of the key (`admit_quantities`). A
       read too, so it also goes ahead of the write below.
    6. **The grouping-field admission (Task 9) WRITES** — it records novel
       values against each key's cardinality cap — so it comes after the
       refusals above, which would otherwise have burned keyspace on a request
       that was never recorded, and before the recording core, outside its
       retry machinery. A replay never reaches it, so a retry neither
       re-admits nor records a value.
    7. **The recording core**, for a new event — which refuses one more thing,
       by name: an amount its costing computes past the money columns
       (`pricing_service.AmountPastTheMoneyBound`, #603).

    Written once, for the reason the adapters around it are: the single route
    and the batch item must take the same steps in the same order, or the
    batch stops being "N sequential singles". Every refusal it raises is a
    ``ValueError`` — ``ProviderConflictsWithEventType``,
    ``SupplierCostNotAdmissible``, ``QuantityNotAdmissible``,
    ``GroupingFieldError`` and ``AmountPastTheMoneyBound`` are — so each route
    renders all of them through :func:`usage_error`.
    """
    replayed = UsageService.replay(tenant, customer, item.idempotency_key)
    if replayed is not None:
        return replayed
    published = last_published_declaration(tenant=tenant, key=item.event_type)
    declaration = declaration_of(published)
    provider = admit_provider(item, declaration)
    admit_supplier_cost(item, declaration)
    admit_quantities(item, published)
    grouping_slots = GroupingFieldService.admit(
        tenant, item.grouping_fields, scope=GROUPING_FIELD_SCOPE_EVENT)
    return UsageService.record_new_usage(
        tenant=tenant, customer=customer, grouping_slots=grouping_slots,
        **usage_kwargs(item, provider=provider, declaration=declaration))


def record_sync_item(tenant, item, customers, task_exists):
    """One batch item == one independent POST /usage, error mapping included.

    Mirrors the single endpoint's contract byte-for-byte as per-item VERDICT
    dicts: a success mirrors the single-call success body (stop-verdict
    fields included) plus {"accepted": true}. 404s become per-item
    {"code": "not_found"}; the generic ValueError branch becomes
    {"code": "validation_error"} - every code from the registry. One-rule
    parity: a crossing verdict runs the same kill flow and the batch
    CONTINUES — later items on the killed task still land, bill, and carry
    the task_not_active stop verdict, identical to firing the same items as
    sequential singles.
    """
    cid = str(item.customer_id)
    if cid not in customers:
        customers[cid] = Customer.objects.filter(id=item.customer_id, tenant=tenant).first()
    customer = customers[cid]
    if customer is None:
        return _rejected("not_found", "Customer not found")
    if item.task_id is not None:
        task_key = (cid, str(item.task_id))
        if task_key not in task_exists:
            task_exists[task_key] = Task.objects.filter(
                id=item.task_id, tenant=tenant, customer=customer).exists()
        if not task_exists[task_key]:
            return _rejected("not_found", "Task not found")
    # A bad item is THIS item's rejection, the same as any other validation
    # failure, and the batch carries on.
    try:
        result = replay_or_record(tenant, customer, item)
    except ValueError as e:
        return _rejected(*usage_error(e))
    return {"accepted": True, **with_receipt_reads(result)}


@metering_router.post("/usage", response={200: RecordUsageResponse})
@role_floor(WRITE)
def record_usage(request, payload: RecordUsageRequest):
    """Record one usage event. One-rule contract: every event that reaches
    UBB is priced, recorded, and billed with an HTTP 200 — including the
    tipping event that crosses a limit and everything arriving after a kill.
    The stop instruction rides the response fields (stop / stop_reason /
    stop_scope); a non-200 always means "this was not recorded" (auth,
    malformed payload, unknown customer/task, validation errors).

    A cost UBB cannot work out is NOT one of those (#320): the event is
    recorded, and `costing_status` plus `uncosted_measurement_keys` on this
    body say so at the moment the gap is created."""
    _product_check(request)
    return record(request.auth.tenant, payload)


def record(tenant, payload):
    """One recording, for `tenant`: the body of the route above, as its 200
    answers it — or the refusal it raises.

    A function of its own so that the Code Builder's verification records
    exactly as a tenant's own code does (`api/v1/verification.py`): the
    customer and task lookup, then `replay_or_record` — the one order both
    recording routes take.
    """
    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=tenant)
    if payload.task_id is not None:
        get_object_or_404(Task, id=payload.task_id, tenant=tenant, customer=customer)
    # Every refusal below is a whole-request 422, never a partial record.
    try:
        result = replay_or_record(tenant, customer, payload)
    except ValueError as e:
        raise Problem(*usage_error(e))
    # Kill execution is the recording core's job (#112): a crossing verdict
    # registers kill_and_announce on the recording transaction's on_commit,
    # so the kills have already fired by the time this returns.
    return with_receipt_reads(result)


@metering_router.post("/usage/batch", response={200: UsageBatchResponse})
@role_floor(WRITE)
def record_usage_batch(request, payload: UsageBatchRequest):
    """Batch ingestion: 1..100 INDEPENDENT items (>100 or 0 → 422).

    Each item runs the same per-item record_usage in its own atomic commit —
    deliberately NOT one mega-transaction, which would hold Task/counter locks
    for the whole batch, delay outbox dispatch, and diverge from the semantics
    of N sequential singles. Always HTTP 200 with positionally-aligned
    results[] + accepted/rejected counts; per-item idempotency makes a
    whole-batch replay return the original event ids with zero new rows, and
    a duplicate idempotency_key WITHIN one batch resolves to the first item's
    event id (the first item commits before the second runs).
    """
    _product_check(request)
    tenant = request.auth.tenant
    customers: dict = {}
    task_exists: dict = {}
    results = [record_sync_item(tenant, item, customers, task_exists)
               for item in payload.events]
    accepted = sum(1 for r in results if r.get("accepted"))
    return {"results": results, "accepted": accepted,
            "rejected": len(results) - accepted}


def _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq):
    """The #41 past-limit query filters, shared by the events listing and the
    analytics rollup so both surfaces compose identically:

    - past_limit=true  → only events carrying a stop context (landed past
      something); false → only untagged events.
    - stop_scope=X     → events with at least one context entry of scope X.
    - episode_seq=N    → events tagged into customer-wide episode N.

    The array-containment filters ride the partial GIN index on
    Posting.stop_context (JSONB @>)."""
    if past_limit is not None:
        qs = qs.filter(stop_context__isnull=not past_limit)
    if stop_scope is not None:
        qs = qs.filter(stop_context__contains=[{"stop_scope": stop_scope}])
    if episode_seq is not None:
        qs = qs.filter(stop_context__contains=[{"episode_seq": episode_seq}])
    return qs


@metering_router.get("/customers/{customer_id}/usage", response=PaginatedUsageResponse)
@role_floor(READ)
def get_usage(request, customer_id: UUIDIdentifier, cursor: str = None, limit: int = 50,
              metadata_key: str = None, metadata_value: str = None,
              task_id: UUIDIdentifier = None, include_subtasks: bool = False,
              past_limit: bool = None, stop_scope: str = None,
              episode_seq: int = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)

    qs = customer.postings.all()
    # FILTERING is what the open bag is for, and it is what survived the fold
    # in #273. The pair NAMES THE BAG since #504 (slice 7 phase B1): it used to
    # carry the analytics grouping word, which read as an axis on a bag ADR-0005
    # keeps deliberately ungroupable, and this route is a filter surface rather
    # than a grouping one — which is why slice 7 renamed its request vocabulary
    # and left its route and its response alone (slice 7 §1).
    if metadata_key and metadata_value:
        qs = qs.filter(metadata__contains={metadata_key: metadata_value})
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)
    qs = _apply_task_filter(qs, request.auth.tenant, task_id, include_subtasks)

    return page(qs, cursor, limit, serialize=usage_event_out,
                time_field="effective_at")


@metering_router.get("/usage/{event_id}", response={200: UsageEventDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_usage_event(request, event_id: UUID):
    """Fetch one usage event's full pricing receipt (audit / dispute lookup).

    Returns every priced field plus the Pricing Receipt — the authoritative
    record of the economic resolution behind those amounts, not a guarantee
    that customer revenue exists. It carries its own shape version and the
    version of the engine that computed it, the subject it explains, a costing
    and a pricing section holding their method, status and detail by value, the
    totals, and cross-reference ids nothing reads to reconstruct an amount. The
    usage list omits the receipt to stay lean; this is where it is read back.
    Tenant-scoped; 404 for an unknown or foreign event id."""
    _product_check(request)
    from apps.metering.usage.grouping import grouping_fields_for
    from apps.metering.usage.measurements import measurements_status_for
    from apps.metering.usage.models import Posting

    # select_related on the measurement child (#270): the response reads the
    # measured quantities through it, and the detail route is a single-row
    # lookup where a second query buys nothing. #271's status reads the same
    # cached relation, so serving it costs no query either.
    e = get_object_or_404(
        Posting.objects.select_related("measurement"),
        id=event_id, tenant=request.auth.tenant)
    return 200, {
        "id": e.id,
        # Stored, and read straight off the row (#417): a posting is born one
        # kind or the other and the column is frozen, so there is nothing here
        # a serialiser could usefully re-derive or get wrong.
        "kind": e.kind,
        "idempotency_key": e.idempotency_key,
        "event_type": e.event_type,
        "provider": e.provider,
        # Derived at the serialiser like the status below, and for the same
        # reason (#277): the row carries physical slots, and what a caller reads
        # is the tenant's own vocabulary. One registry read, and none at all for
        # a posting with no grouping values.
        "grouping_fields": grouping_fields_for(e),
        "currency": e.currency,
        "provider_cost_micros": e.provider_cost_micros,
        # Stored, unlike the two derived answers around it: the status is a
        # statement about this posting's economics and a column holds it.
        "costing_status": e.costing_status,
        # Stored beside it, and read rather than re-derived (#323) — for two
        # different reasons, which is why they are not one comment. The cause
        # settles WITH the status and the amount, in the one `UPDATE`
        # RESOLVE_ONCE permits, so a serialiser that recomputed it could
        # contradict the status it arrived with. The claim never moves at all:
        # it is declared FROZEN (`usage/models.py`), so what is published is
        # necessarily what the caller said at the time, which is the only
        # thing that makes it worth publishing.
        "unresolved_reason": e.unresolved_reason,
        "claimed_provider_cost_micros": e.claimed_provider_cost_micros,
        "billed_cost_micros": e.billed_cost_micros,
        # Stored, and read rather than re-derived, on the same two arguments as
        # the cost pair above (#351): the status settles with the amount, and a
        # serialiser that recomputed either could contradict what the row says.
        "pricing_status": e.pricing_status,
        "not_applicable_reason": e.not_applicable_reason,
        # The price status's own reason (#603), stored and read on the same
        # two arguments as the status beside it.
        "pricing_status_reason": e.pricing_status_reason,
        # Derived here rather than stored, and read out of the record rather
        # than recomputed (#355). The receipt is the authority on how an amount
        # was reached; re-deriving the method from today's configuration is the
        # failure the receipt exists to prevent. The shape is ASKED FOR, not
        # assumed — once, in the receipts module, like the uncosted list on the
        # recording surfaces.
        "pricing_method": pricing_method_of(e.pricing_receipt),
        # WHAT THE RECEIPT EXPLAINS, on the same two arguments (#370): read out
        # of the record, never inferred from the row it hangs on.
        "pricing_receipt_subject_type": subject_type_of(e.pricing_receipt),
        "measurements": e.measurements or {},
        # Derived, never stored (ADR-0006 §4) — computed here, at the
        # serialiser, which is the only place §E5 permits it to exist.
        "measurements_status": measurements_status_for(e),
        "pricing_receipt": e.pricing_receipt,
        "metadata": e.metadata,
        "task_id": str(e.task_id) if e.task_id else None,
        "effective_at": e.effective_at.isoformat(),
        "created_at": e.created_at.isoformat(),
        "stop_context": e.stop_context,
    }


# --- Task analytics ---
#
# THE LIFECYCLE ITSELF IS NO LONGER HERE (#409). Reading one unit of work,
# listing them and closing one moved to the root prefix and are ungated — a
# unit of work is a kernel concept neither metering nor billing owns, and
# api/v1/task_endpoints.py carries the argument.
#
# The report below deliberately stayed, and stayed gated on `metering`: it is a
# reporting surface rather than part of the lifecycle, it was left for slice 7's
# analytics collapse, and moving it on the way past would have broken one path
# twice. That collapse then kept it OUTSIDE (slice 7 §12 — one observation per
# unit of work, not per posting), so it never moved at all.


@metering_router.get("/analytics/tasks", response={200: TaskAnalyticsOut,
                                                  422: ProblemOut})
@states_its_report_window()
@role_floor(READ)
def task_analytics(request, group_by: str = "task_type",
                   start_date: Optional[date] = Query(None, description=START_DATE_DESCRIPTION),
                   end_date: Optional[date] = Query(None, description=END_DATE_DESCRIPTION)):
    """Cost per KIND of work: run count, mean and p95, over the work created in
    the window.

    A p95 approaching the kind's ceiling is the signal that the ceiling is
    about to start biting real customers; how much work reached it is
    `GET /spend-controls/utilisation-and-headroom`'s figure."""
    _product_check(request)
    from apps.platform.work.queries import task_rollup_by_type

    # ⚠ THE WINDOW IS RESOLVED BEFORE ANYTHING IS READ, WHATEVER WAS SENT
    # (#542). This route used to bound only a supplied PAIR, so a lone
    # `start_date` was an unbounded rollup and no date at all was the whole of
    # history; it now answers the month to date like every other report.
    window = resolve_report_window(start_date, end_date)
    try:
        rows = task_rollup_by_type(
            request.auth.tenant.id, group_by=group_by,
            start_date=window.opens_at, end_date=window.closes_at)
    except ValueError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"group_by": group_by, "rows": rows}


# --- The tenant's default markup rung ---
#
# THE LAST RUNG OF THE PRICE LADDER, DECLARED (#357). Where the books in play
# hold no rule for a quantity, the customer's price is a percentage over what
# UBB knows the call cost — so this is the rung that produces most of the prices
# in the system, and a tenant has to be able to say what it is, read it back and
# take it away again.
#
# ⚠ IT REPLACES THE TENANT-SCOPE HALF OF THE SECTION BELOW, WHICH SURVIVES THIS
# COMMIT AND PRICES NOTHING. That record's `customer IS NULL` row was the tenant
# default by being the row with no customer on it; resolution now reads this
# declaration instead. The commit that deletes that record deletes its routes,
# its two schemas and its two audit action names with it.


@metering_router.get("/pricing/default-markup", response=TenantDefaultMarkupOut)
@role_floor(READ)
def get_tenant_default_markup(request):
    """What the tenant has declared, or null if they have declared nothing.

    ⚠ **NULL, NOT ZERO.** UBB ships no catalogue, and a tenant with no
    declaration has no markup rung — every event they record with no matching
    rule prices to `unknown`. Answering `0` would say they had decided to charge
    exactly what their calls cost, which is a different decision and one nobody
    made.
    """
    _product_check(request)
    from apps.metering.pricing.models import TenantDefaultMarkup

    declared = TenantDefaultMarkup.objects.filter(
        tenant=request.auth.tenant).first()
    return {"markup_micro_percent":
            declared.markup_micro_percent if declared else None}


@metering_router.put("/pricing/default-markup", response=TenantDefaultMarkupOut)
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_TENANT_DEFAULT_MARKUP_DECLARED)
def declare_tenant_default_markup(request, payload: TenantDefaultMarkupIn):
    """Declare the tenant's default markup rung, or re-declare it.

    Re-declaring is the same act as declaring — a correction to a declared
    percentage is still a declaration — which is why one action name covers
    both and why withdrawal is a different one.

    The ADMIN floor is the write default this surface already runs for
    everything that decides what a customer is charged.
    """
    _product_check(request)
    from apps.metering.pricing.models import TenantDefaultMarkup

    with transaction.atomic():
        rung, _ = TenantDefaultMarkup.objects.update_or_create(
            tenant=request.auth.tenant,
            defaults={"markup_micro_percent": payload.markup_micro_percent},
        )
        audit_record(
            action=AUDIT_ACTION_TENANT_DEFAULT_MARKUP_DECLARED,
            tenant_id=request.auth.tenant.id,
            resource_type=AUDIT_RESOURCE_TYPE_TENANT_DEFAULT_MARKUP,
            resource_id=rung.id,
            metadata={"markup_micro_percent": rung.markup_micro_percent},
        )
    return {"markup_micro_percent": rung.markup_micro_percent}


@metering_router.delete("/pricing/default-markup", response=StatusResponse)
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_TENANT_DEFAULT_MARKUP_WITHDRAWN)
def withdraw_tenant_default_markup(request):
    """Withdraw the rung, leaving the tenant with none.

    ⚠ **THIS IS NOT THE SAME AS DECLARING ZERO**, and the difference is the one
    this rung exists to keep. A declared zero prices an event at exactly what
    the call cost and settles; no rung at all resolves to `unknown` with no
    amount, because nobody has said what to charge.

    Idempotent: withdrawing nothing answers `no_declaration` rather than 404,
    and writes no audit entry — there was no act.
    """
    _product_check(request)
    from apps.metering.pricing.models import TenantDefaultMarkup

    rung = TenantDefaultMarkup.objects.filter(
        tenant=request.auth.tenant).first()
    if rung is None:
        return {"status": "no_declaration"}
    with transaction.atomic():
        rung_id = rung.id
        rung.delete()  # instance delete — the model layer invalidates the cache
        audit_record(
            action=AUDIT_ACTION_TENANT_DEFAULT_MARKUP_WITHDRAWN,
            tenant_id=request.auth.tenant.id,
            resource_type=AUDIT_RESOURCE_TYPE_TENANT_DEFAULT_MARKUP,
            resource_id=rung_id,
        )
    return {"status": "withdrawn"}


# THE FIVE MARKUP ROUTES ARE GONE, AND SO IS THE RECORD THEY WROTE (#369).
#
# A tenant-scope pair read and wrote a percentage and a per-event flat
# addend for the whole tenant; a customer-scope trio did the same for one
# named customer, and a resolve behind the read walked a three-rung ladder to
# answer it. The record is deleted. What replaced each rung is a record that
# can say what it prices: the tenant's default markup rung is declared at
# `/pricing/default-markup` above (#357), a customer's own price is a rule in
# their own Pricing Book (#361), and a plan's is a rule in the book the plan
# names (#362).
#
# Their two schemas went with them, and so did the two audit action names they
# wrote — deleting an action whose act no longer exists is not the rename
# ADR-004 §2 governs, and `record()` refuses an unregistered name, which is
# what forced the routes and the registry into one commit. The names are cited
# rather than spelled: their ledger entries reach zero here, and a file naming
# one would put the count back over its own entry.


# --- Analytics ---


# THE AD-HOC AXIS RESOLVER WAS HERE AND IS GONE WITH THE TWO ROUTES THAT USED
# IT (#501). It mapped a requested word either to itself, for a handful of
# reserved names, or to whichever slot a tenant's key happened to occupy — and
# the cap beside it bounded how many such breakdowns one call could ask for.
# Both are now the discovery contract's job: `grouping_options` publishes the
# axes a tenant may group by, each carrying its own kind, and the one query
# refuses a word that is not on it. The bound is by CONSTRUCTION there — a fixed
# set of axes plus at most one slot apiece — rather than a number this module
# kept in step with the registry by hand.


def _apply_task_filter(qs, tenant, task_id, include_subtasks):
    """Correlation-id filtering (design D9). With include_subtasks the whole
    tree is in scope — one extra indexed query for the child ids, since
    containment is a single level."""
    if task_id is None:
        return qs
    from apps.platform.work.models import Task

    ids = [task_id]
    if include_subtasks:
        ids += list(Task.objects.filter(
            tenant=tenant, parent_id=task_id).values_list("id", flat=True))
    return qs.filter(task_id__in=ids)


# THE USAGE ANALYTICS REPORT AND ITS TIMESERIES SIBLING WERE HERE AND ARE GONE
# (#501, slice 7 §1) — the first two of the nine routes the one economic query
# replaces, and between them the origin of the rest: the grouped margin
# breakdown and the billing revenue report were each a reimplementation of one
# of these two.
#
# What each capability became, because a removal owes that per capability and
# not per route:
#
# * the totals — the three money measures on the one query, with no grouping;
# * the four fixed breakdown blocks — `group_by=field:provider` and its three
#   siblings, which are PRESETS a caller composes rather than four response keys
#   every answer carries whether or not it was asked for;
# * the several ad-hoc breakdowns in one response — multi-axis `group_by`;
# * day and hour bucketing — `bucket=day|hour`;
# * every filter, including the three stop-context ones and the unit-of-work
#   pair — filters on the one query, which compose with every grouping exactly
#   as they did here.
#
# ⚠ TWO THINGS DIED WITH THESE ROUTES RATHER THAN MOVING.
#
# The FREE-TEXT-KEY BREAKDOWN, which grouped by whatever key a caller named out
# of the open bag, has no replacement on purpose: the declared grouping contract
# (#498) publishes what a tenant may group by and an unbounded keyspace is the
# capability it deliberately does not have.
#
# The FUSED FIELD that stated the billed total minus the supplier cost over the
# whole window is neither a markup nor a margin — it is the difference between
# two aggregates, which after this slice is the gross-margin measure, computed
# once at a bucket and carrying its own state. Publishing it under a name that
# suggested a rate is what let a reader take a floor for a figure.
#
# The one query also bounds its window on the RESOLVED span rather than only
# where both dates were sent, so the open-window escape this timeseries kept —
# flagged in its own comment as #501's to take away — goes with it.


# --- Rate Cards ---

def _gate_a_pricing_book(request):
    """A Pricing Book — what a tenant's customers are agreed to pay — takes the
    metering floor, exactly as a cost book does (#553, ADR-0021 §4).

    **BILLING/COLLECTION MODE DOES NOT DECIDE WHETHER UBB MAY KNOW THE AGREED
    CUSTOMER PRICE.** This gate asked for the billing product until #553, on
    the reading that a price is what UBB COLLECTS. A metering-only tenant
    collects elsewhere and still agrees prices with its customers, and its
    margin reporting is exactly what those prices exist for: a fixed-price
    unit's revenue, an event's billed amount, the margin between them. So
    declaring, reading and publishing a Pricing Book — and a customer's own
    override — is metering. What the billing product still gates is MOVING
    money: its outbox handlers draw wallets and accumulate fees only for a
    tenant that has it, and a Plan, whose fee axes are subscriptions and
    Stripe, stays behind it (`plan_endpoints.py`).

    ⚠ TWO NAMED GATES STILL, ALTHOUGH THEY NOW ASK THE SAME THING. The gate
    this pair replaced took the kind word as an argument and branched on it,
    which is how a cost route came to be gated on billing once (#363); a route
    calls the gate for the entity it serves, and the day the two entities'
    floors differ again the call sites are already right.
    """
    _product_check(request)


def _gate_a_cost_book(request):
    """Recording what a SUPPLIER charges is metering, not billing.

    A metering-only tenant tracks its supplier costs whatever it bills, so
    nothing here may ask for the billing product.
    """
    _product_check(request)


def _gate_the_books_product(request, book):
    """The product gate for an act performed on a book already looked up.

    Which gate a book takes is a property of the ENTITY, so the two named
    gates above are reached through the book rather than through a value
    read off it. Both are the metering floor since #553 — see
    `_gate_a_pricing_book` for why a Pricing Book is not a billing surface —
    and they stay two because the entities are two. The routes that know
    which kind they serve call those directly; the SIX that act on either
    kind come here.

    ⚠ **THE THREE READS CAME HERE LATE, AND UNTIL THEY DID A METERING-ONLY
    TENANT COULD READ A PRICING BOOK.** Listing a book's rules, listing its
    pending changes and reading one of them each took the bare metering check
    they had when one container served both halves — correct then, because one
    gate covered one entity. After the split the collection routes gate per
    kind while these three did not, so `/pricing/pricing-books` answered 403
    and `/pricing/books/{id}/rates` answered the same tenant's Pricing Book
    rules. It is the mistake the deleted kind-word gate made in the other
    direction (#363), found by review rather than by a gate: the walkers check
    that a route HAS a floor, never which product it names.
    """
    if isinstance(book, PricingBook):
        _gate_a_pricing_book(request)
    else:
        _gate_a_cost_book(request)


def _refuse_to_withdraw_a_book_with_a_pending_change(book):
    """A book with a change waiting on it is not withdrawn (#368, review).

    ⚠ **`PricingBookPublish` CASCADES FROM ITS BOOK, SO WITHOUT THIS THE
    WITHDRAWAL DELETES THE GOVERNANCE TRAIL SILENTLY.** The cascade is right
    for what it was written for — a publish record EXPLAINS a book and means
    nothing once the book is gone, and a `PROTECT` there would make a wipe fail
    from a record nobody asked about (#354, #358). What it is wrong for is a
    tenant withdrawing a book that still has an intention pending on it: the
    draft vanishes with no record that it ever existed, on a surface whose
    whole argument is that an intention and a publication are separate acts a
    governance reader can tell apart.

    ⚠ **THE EXPOSURE IS DRAFTS AND ONLY DRAFTS, WHICH IS WHY THE FILTER SAYS
    SO RATHER THAN COUNTING EVERY RECORD.** A PUBLISHED record opened or closed
    a rule, and a rule holds its book with `PROTECT` — so a book carrying
    one is already unwithdrawable by the refusal below it, and its history was
    never reachable by this path. Counting published records here would refuse
    nothing new while REPLACING the honest message about rules with a
    misleading one about drafts, on exactly the book whose rules are all
    retired. What can be lost is what a tenant has not committed to yet, and
    discarding a draft is a route they already have. This points at it.
    """
    drafts = PricingBookPublish.objects.filter(
        declaration_status=DECLARATION_STATUS_DRAFT,
        **{book.REFERENCE_COLUMN: book}).count()
    if drafts:
        raise Problem(
            "conflict",
            f"this book has {drafts} change(s) declared against it and not "
            f"yet published. Discard them at DELETE /pricing/books/"
            f"{book.id}/publishes/{{publish_id}} first — withdrawing the "
            f"book would take the record of what was proposed with it")


def _book_or_404(request, book_id):
    """The book with this id, whichever kind it is (#368).

    ⚠ **A LOOKUP, NOT A DISCRIMINATOR.** The two tables hold different
    entities and this asks each in turn for one id; nothing reads a value off
    a row to decide what kind of thing it is, which is the difference between
    this and the column the slice deletes. Ids are UUIDs, so at most one
    answers.

    It exists because the acts BELOW a book — list its rules, list the
    changes declared against it, read one of them, declare a change, publish
    that change, discard it — are genuinely one act each, whichever kind of
    book they are performed on. Splitting those six
    operations per kind would have put the kind back into the surface as a
    path segment, which is the same conflation wearing a different hat, and
    doubled the operation ids the SDK mints for no difference a caller can
    act on.
    """
    for model in (PricingBook, CostBook):
        book = model.objects.filter(
            id=book_id, tenant=request.auth.tenant).first()
        if book is not None:
            return book
    raise Http404("no book with that id")


def _resolve_book_currency(tenant, raw_currency):
    """The currency a cost book is declared in: UBB v1's one (ADR-0023).

    Omitted/empty takes the tenant's, which the policy holds to US dollars;
    an explicit value is admitted by the one policy or refused with
    `UnsupportedCurrency`.

    ⚠ **ONLY THE COST BOOK ASKS THIS NOW.** A Pricing Book has no currency
    column at all, so there is nothing on it to pin — which is the same fact
    this function has always enforced, said by the schema instead of by a
    check.
    """
    if not raw_currency:
        return tenant.default_currency
    return admit_currency(raw_currency)


@metering_router.get("/pricing/pricing-books", response=PaginatedPricingBooks)
@role_floor(READ)
def list_pricing_books(request, cursor: str = None, limit: int = 50):
    """List the tenant's Pricing Books — the catalogues of what this tenant
    charges — newest first. Rules live under a book and are read via
    GET /pricing/books/{book_id}/rates."""
    _gate_a_pricing_book(request)
    return page(PricingBook.objects.filter(tenant=request.auth.tenant),
                cursor, limit, serialize=pricing_book_out)


@metering_router.post("/pricing/pricing-books",
                      response={200: PricingBookOut, 409: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_PRICING_BOOK_DECLARED)
def declare_pricing_book(request, payload: PricingBookIn):
    """Declare a Pricing Book: a catalogue of what this tenant charges.

    It arrives EMPTY. UBB ships no catalogue — no starter rules, no default
    rule set, no seeded markup — so a book prices nothing until rules are
    published into it and every event falls past it to the markup rung.

    A book names neither a supplier nor a currency; see the request schema for
    why. Declarations dedupe on natural identity: a second book under the same
    key, or a second default, answers 409.
    """
    _gate_a_pricing_book(request)
    try:
        with transaction.atomic():
            book = PricingBook.objects.create(
                tenant=request.auth.tenant, key=payload.key,
                name=payload.name, is_default=payload.is_default)
            audit_record(
                action=AUDIT_ACTION_PRICING_BOOK_DECLARED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK,
                resource_id=book.id,
                metadata={
                    "key": book.key,
                    "name": book.name,
                    "is_default": book.is_default,
                },
            )
    except IntegrityError:
        raise Problem("conflict",
                      "a Pricing Book with this identity already exists")
    return 200, pricing_book_out(book)


@metering_router.delete("/pricing/pricing-books/{book_id}",
                        response={200: StatusResponse, 404: ProblemOut,
                                  409: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_PRICING_BOOK_WITHDRAWN)
def withdraw_pricing_book(request, book_id: UUID):
    """Withdraw a Pricing Book the tenant no longer prices from.

    **A book that has EVER held a rule is not withdrawn, it answers 409** —
    and "ever" is the operative word rather than a hedge. Rules are what a
    tenant was charged from and the receipts explaining past charges point at
    them, so retiring a rule stamps its end and KEEPS the row; the book still
    holds it. Withdrawal is therefore for a book that was declared and never
    used, which is the state it exists to clear up.

    A book a Plan prices from answers 409 for the same reason: the plan would
    be left naming nothing, which is the state its required reference exists
    to make unreachable. So does a book with a change recorded against it.
    """
    _gate_a_pricing_book(request)
    book = get_object_or_404(PricingBook, id=book_id,
                             tenant=request.auth.tenant)
    _refuse_to_withdraw_a_book_with_a_pending_change(book)
    try:
        with transaction.atomic():
            book.delete()
            audit_record(
                action=AUDIT_ACTION_PRICING_BOOK_WITHDRAWN,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK,
                resource_id=book.id,
                metadata={"key": book.key, "name": book.name},
            )
    except ProtectedError:
        raise Problem(
            "conflict",
            "this book holds rules, or a plan still prices from it. A "
            "retired rule is kept rather than removed, so a book that has "
            "ever been published into cannot be withdrawn; move any plan onto "
            "another book instead")
    return 200, {"status": "ok"}


@metering_router.get("/pricing/cost-books", response=PaginatedCostBooks)
@role_floor(READ)
def list_cost_books(request, cursor: str = None, limit: int = 50):
    """List the tenant's cost books — what each supplier charges — newest
    first. Rules live under a book and are read via
    GET /pricing/books/{book_id}/rates."""
    _gate_a_cost_book(request)
    return page(CostBook.objects.filter(tenant=request.auth.tenant),
                cursor, limit, serialize=cost_book_out)


@metering_router.post("/pricing/cost-books",
                      response={200: CostBookOut, 409: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_COST_BOOK_DECLARED)
def declare_cost_book(request, payload: CostBookIn):
    """Declare a cost book: a record of what one supplier charges this tenant.

    It arrives EMPTY, for the reason a Pricing Book does: UBB ships no
    catalogue of supplier prices and cannot — they are the supplier's.

    Declarations dedupe on natural identity: a second book under the same key,
    or a second default for one supplier and currency, answers 409.
    """
    _gate_a_cost_book(request)
    try:
        currency = _resolve_book_currency(request.auth.tenant, payload.currency)
    except UnsupportedCurrency as refused:
        raise Problem(refused.code, str(refused))
    try:
        with transaction.atomic():
            book = CostBook.objects.create(
                tenant=request.auth.tenant, provider_key=payload.provider_key,
                key=payload.key, name=payload.name, currency=currency,
                is_default=payload.is_default)
            audit_record(
                action=AUDIT_ACTION_COST_BOOK_DECLARED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_COST_BOOK,
                resource_id=book.id,
                metadata={
                    "provider_key": book.provider_key,
                    "key": book.key,
                    "name": book.name,
                    "currency": book.currency,
                    "is_default": book.is_default,
                },
            )
    except IntegrityError:
        raise Problem("conflict",
                      "a cost book with this identity already exists")
    return 200, cost_book_out(book)


@metering_router.delete("/pricing/cost-books/{book_id}",
                        response={200: StatusResponse, 404: ProblemOut,
                                  409: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_COST_BOOK_WITHDRAWN)
def withdraw_cost_book(request, book_id: UUID):
    """Withdraw a cost book the tenant no longer records costs from.

    **A book that has EVER held a rule is not withdrawn, it answers 409**, for
    the reason `withdraw_pricing_book` gives in full: a retired rule is kept
    rather than removed, and the receipts explaining what past work cost point
    at it. So does a book with a change recorded against it.
    """
    _gate_a_cost_book(request)
    book = get_object_or_404(CostBook, id=book_id, tenant=request.auth.tenant)
    _refuse_to_withdraw_a_book_with_a_pending_change(book)
    try:
        with transaction.atomic():
            book.delete()
            audit_record(
                action=AUDIT_ACTION_COST_BOOK_WITHDRAWN,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_COST_BOOK,
                resource_id=book.id,
                metadata={"key": book.key, "name": book.name,
                          "provider_key": book.provider_key,
                          "currency": book.currency},
            )
    except ProtectedError:
        raise Problem(
            "conflict",
            "this book holds rules. A retired rule is kept rather than "
            "removed, so a book that has ever been published into cannot be "
            "withdrawn")
    return 200, {"status": "ok"}


@metering_router.get("/pricing/books/{book_id}/rates",
                     response={200: PaginatedRates, 404: ProblemOut})
@role_floor(READ)
def list_book_rates(request, book_id: UUID, include_history: bool = False,
                    as_of: datetime = None, cursor: str = None, limit: int = 50):
    """List the rules in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time).

    The book may be a Pricing Book or a cost book: listing what is in one is
    the same act either way, and it is gated on the product that BOOK belongs
    to rather than on metering alone."""
    book = _book_or_404(request, book_id)
    _gate_the_books_product(request, book)
    # The declaration is joined, not fetched per row: `rate_out` reads the
    # quantity's name off it since #326, and a page of fifty rates would
    # otherwise be fifty-one queries. A deactivated rate references nothing and
    # answers from its own column, which `select_related` handles without a
    # second path — it is a LEFT JOIN, not a filter.
    qs = Rate.objects.filter(
        tenant=request.auth.tenant,
        **{book.REFERENCE_COLUMN: book}).select_related("measurement")
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    return 200, page(qs, cursor, limit, serialize=rate_out)


@metering_router.get("/pricing/books/{book_id}/agreed-prices",
                     response={200: PaginatedAgreedPrices, 404: ProblemOut})
@role_floor(READ)
def list_book_agreed_prices(request, book_id: UUID,
                            include_history: bool = False,
                            as_of: datetime = None, cursor: str = None,
                            limit: int = 50):
    """List the agreed prices in a Pricing Book, newest first: what one
    delivered unit of each kind of work sells for.

    Lines still open by default — in force now, or scheduled to open —
    ``include_history`` returns every version (a superseded or retired line
    carries a ``valid_to``), and ``as_of`` returns the line in force at that
    instant, at most one per kind of work. Lines are added, repriced and
    retired through the book's publish act.

    A cost book holds no agreed price: its id answers 404 here."""
    from apps.metering.pricing.services.book_service import agreed_prices_of

    book = get_object_or_404(PricingBook, id=book_id,
                             tenant=request.auth.tenant)
    _gate_a_pricing_book(request)
    return 200, page(
        agreed_prices_of(book, as_of=as_of,
                         include_history=include_history),
        cursor, limit, serialize=agreed_price_out)


# --- Every change to a Pricing Book is a publish, and a draft is not one ------
#
# THREE ACTS AND THEIR THREE ROUTES (#358). Adding a rule, repricing one and
# retiring one become one act, recorded once, with a diff a tenant reads before
# committing to it. Declaring a draft, publishing it and discarding it are three
# answers to three different questions, so each carries its own audit action —
# `#148 §6.3`'s "one path replaces three" is about the book's MUTATION surface,
# not about collapsing governance — and `record()` refuses an unregistered name,
# which is why the registry and these routes are one commit.
#
# ⚠ AND THERE IS NOTHING LEFT BESIDE THEM (#368). `POST .../rates` and
# `DELETE .../rates/{rate_id}` went with #367; the atomic reprice that stood
# here — a route that DID version the book but took effect the instant it was
# called, with no diff a tenant could read first and no way to date the change
# forward — goes with this commit, together with the third and last of the
# retired action names. **A book has exactly one way to change now, and it
# leaves a record.** That is what makes forward-dating, the readable diff and
# reversal-by-further-publish properties of the BOOK rather than of one of its
# two mutation paths.


def _book_publish_or_404(request, book_id, publish_id):
    """The draft on THIS book, whichever kind of book it is (#368).

    The book is resolved first and then names its own column. Filtering on a
    single `book_id` stopped being possible when the container split, and it
    would have been wrong even if it had survived: a publish id alone does not
    say which catalogue it belongs to, and a lookup that ignored the book would
    let a draft be published through another book's path.
    """
    book = _book_or_404(request, book_id)
    return get_object_or_404(PricingBookPublish, id=publish_id,
                             tenant=request.auth.tenant,
                             **{book.REFERENCE_COLUMN: book})


def _publish_response(request, record):
    """One publish record, with its diff where there is one to compute.

    THREE CASES, AND THE THIRD IS THE ONE THAT MATTERS. A published record's
    diff is null rather than recomputed: a diff is a statement about a change
    that has not happened, and re-planning a change already applied would
    describe the book disagreeing with itself.

    ⚠ **AND A DRAFT CAN BE LEFT STATING A CHANGE THAT CAN NO LONGER BE CARRIED
    OUT.** This is reachable through surfaces this commit deliberately keeps
    alive: a book still has three immediate mutation routes, and two drafts can
    name one rule while only one of them publishes. Reading such a draft must
    SAY so — it is exactly what a tenant needs to know, since declaring it again
    would be refused with the same sentence and discarding it is the way out.
    Letting the refusal escape would have answered `internal_error` from a GET,
    and because the list below serializes every pending draft, ONE stale draft
    would have taken the whole book's pending list with it.

    ⚠ **AND THE CODED REFUSAL IS CAUGHT HERE TOO, FOR THE SAME REASON (#360).**
    A draft can fall behind the book's own diary — a later publish schedules a
    boundary past this draft's instant — and the planner refuses that by name
    rather than as a `ValueError`. `Problem` is not a `ValueError`, so catching
    only the latter would have re-opened exactly the hole the paragraph above
    describes, with a 422 escaping a GET instead of an `internal_error`.
    """
    from apps.metering.pricing.services.book_service import BookService

    if record.is_published:
        return book_publish_out(record)
    keys = keys_by_slot(request.auth.tenant.id)
    try:
        rows = BookService.diff(record)
    except Problem as e:
        # `detail` is optional on a `Problem`, and an absent reason here would
        # render as "no problem and no diff" — the two states this field exists
        # to keep apart. The code is never empty, so it is the floor.
        return book_publish_out(record,
                                diff_unavailable_reason=e.detail or e.code)
    except ValueError as e:
        return book_publish_out(record, diff_unavailable_reason=str(e))
    return book_publish_out(
        record, diff=[book_change_diff_out(row, keys) for row in rows])


@metering_router.post("/pricing/books/{book_id}/publishes",
                      response={200: BookPublishOut, 404: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_PRICING_BOOK_PUBLISH_DECLARED)
def declare_book_publish(request, book_id: UUID, payload: BookPublishIn):
    """Declare a change to a book: the intended changes, and nothing written.

    A draft holds the changes and writes no rule, which is what makes it freely
    editable and freely discardable. The response carries the diff — what the
    book will look like afterwards — so a tenant decides against the outcome
    rather than against their own request.

    Every change is resolved before the draft is created, so a name the tenant
    has not declared, or a rule that is not there, is a 422 while they are still
    deciding rather than a surprise when the price was supposed to change.

    **The change can be dated forward, and nothing runs at the instant.**
    `effective_at` names when it takes effect and omitting it means now.
    Publishing writes the rows there and then, carrying the boundary as a value
    resolution reads, so no job has to run when the moment arrives.

    An instant must be timezone-aware (`effective_at_naive`), must not be in the
    past (`effective_at_in_past`), and must be within 366 days
    (`effective_at_too_far_ahead`). It must also be at or after the latest
    boundary already scheduled in this book
    (`effective_at_before_scheduled_boundary`): changes to one book are dated
    forwards, so a change may follow what is scheduled or land exactly on it —
    which is how a scheduled change is reversed — but never slip in behind it.
    There is no limit on how many changes a book may have scheduled at once. A
    refused declaration writes nothing and is recorded nowhere.
    """
    from apps.metering.pricing.services.book_service import BookService

    # ⚠ THE INSTANT IS CHECKED BEFORE ANYTHING ELSE HAPPENS, AND THAT IS THE
    # POINT. *A refusal added to a route can spend what it refuses* — this
    # programme has already paid for a 422 that sat underneath an admission and
    # burned tenant keyspace on requests that recorded nothing. So the check is
    # the first EFFECTFUL statement here, above the book lookup, the product
    # gate and the slot registry read, and therefore far above the two
    # statements that spend anything: `BookService.declare`, which creates the
    # record, and `audit_record`, which writes the governance entry. (The only
    # thing textually above it is the deferred import, which ADR-001's boundary
    # discipline puts in every one of these handlers and which does nothing.)
    # It can be hoisted that far because `validate_scheduled_instant` reads
    # nothing but the payload and the clock.
    #
    # WHAT SITS ABOVE IT, NAMED: the authenticator, which buffers the key's
    # last-used marker on EVERY request whatever the answer — a property of
    # authenticating rather than something this refusal decides — and the role
    # floor, which is a pure read of the principal's role. A refused request
    # records no audit entry and needs no action of its own to say so:
    # `records_audit` is a marker, and `audit_record` is only reached on the
    # path that succeeds. `test_a_book_changes_by_publishing.py`'s
    # `TheRefusalSpendsNothingTest` pins the ORDER, which is invisible in a diff.
    if payload.effective_at is not None:
        validate_scheduled_instant(payload.effective_at, timezone.now())

    book = _book_or_404(request, book_id)
    _gate_the_books_product(request, book)
    slots = slot_map(request.auth.tenant.id)
    try:
        changes = [book_change_body(change.dict(), slots)
                   for change in payload.changes]
    except UndeclaredGroupingField as e:
        raise Problem(
            "validation_error",
            f"no grouping field is declared under the key {e.key!r}. A "
            f"rule selects on a grouping field this tenant has declared; "
            f"declare it first, then price on it")
    try:
        with transaction.atomic():
            record = BookService.declare(book, changes,
                                         effective_at=payload.effective_at)
            audit_record(
                action=AUDIT_ACTION_PRICING_BOOK_PUBLISH_DECLARED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
                resource_id=record.id,
                metadata={"book_id": str(book.id),
                          "effective_at": record.effective_at.isoformat(),
                          "change_count": len(changes)},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.get("/pricing/books/{book_id}/publishes",
                     response={200: PaginatedBookPublishes, 404: ProblemOut})
@role_floor(READ)
def list_book_publishes(request, book_id: UUID, cursor: str = None,
                        limit: int = 50):
    """The changes PENDING on this book — the drafts, newest first, each with
    its diff.

    Drafts only, and that is the question this route answers: *what is about to
    happen to my prices*. A published record is history and the governance
    ledger is where history is read, filtered by action; here it would cost a
    diff computation per row for a record whose diff is null anyway.
    """
    book = _book_or_404(request, book_id)
    _gate_the_books_product(request, book)
    pending = PricingBookPublish.objects.filter(
        tenant=request.auth.tenant,
        declaration_status=DECLARATION_STATUS_DRAFT,
        **{book.REFERENCE_COLUMN: book})
    return 200, page(pending, cursor, limit,
                     serialize=lambda record: _publish_response(request, record))


@metering_router.get("/pricing/books/{book_id}/publishes/{publish_id}",
                     response={200: BookPublishOut, 404: ProblemOut})
@role_floor(READ)
def get_book_publish(request, book_id: UUID, publish_id: UUID):
    """One change to a book, with its diff while it is still a draft."""
    record = _book_publish_or_404(request, book_id, publish_id)
    _gate_the_books_product(request, record.book)
    return 200, _publish_response(request, record)


@metering_router.post(
    "/pricing/books/{book_id}/publishes/{publish_id}/publish",
    response={200: BookPublishOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_PRICING_BOOK_PUBLISH_PUBLISHED)
def publish_book_publish(request, book_id: UUID, publish_id: UUID):
    """Publish a declared change: close each superseded rule, open its
    replacement, from one value.

    All-or-nothing, and nothing runs at the effective instant — the rows are
    written now, carrying the boundary as a value the resolver reads.

    A draft is re-checked against the book as it stands now, so one that has
    fallen behind a boundary scheduled since it was declared is refused with
    `effective_at_before_scheduled_boundary` rather than published. Discard it
    and declare the change again at an instant at or after that boundary.
    """
    from apps.metering.pricing.services.book_service import BookService

    record = _book_publish_or_404(request, book_id, publish_id)
    _gate_the_books_product(request, record.book)
    try:
        with transaction.atomic():
            BookService.publish_declared(record, actor=get_current_actor())
            audit_record(
                action=AUDIT_ACTION_PRICING_BOOK_PUBLISH_PUBLISHED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
                resource_id=record.id,
                metadata={"book_id": str(book_id),
                          "effective_at": record.effective_at.isoformat(),
                          "opened": len(record.opened_rule_ids),
                          "closed": len(record.closed_rule_ids),
                          "opened_agreed_prices":
                              len(record.opened_agreed_price_ids),
                          "closed_agreed_prices":
                              len(record.closed_agreed_price_ids)},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.delete(
    "/pricing/books/{book_id}/publishes/{publish_id}",
    response={200: StatusResponse, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_PRICING_BOOK_PUBLISH_DISCARDED)
def discard_book_publish(request, book_id: UUID, publish_id: UUID):
    """Discard a draft, leaving the book exactly as it stood.

    A draft closed nothing, so this reopens nothing. A published record is
    refused: a publish that has already closed and opened rules is not an
    intention that can be withdrawn, and the act that undoes one is a further
    publish.
    """
    from apps.metering.pricing.services.book_service import BookService

    record = _book_publish_or_404(request, book_id, publish_id)
    _gate_the_books_product(request, record.book)
    try:
        with transaction.atomic():
            record_id = record.id
            BookService.discard(record)
            audit_record(
                action=AUDIT_ACTION_PRICING_BOOK_PUBLISH_DISCARDED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
                resource_id=record_id,
                metadata={"book_id": str(book_id)},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, {"status": "discarded"}


# --- A customer override replaces a whole rule, method included (#361) -------
#
# A tenant honouring a negotiated deal gives one customer their own pricing
# rule. The override replaces the WHOLE rule — its method, its terms and the
# selectors it pins — so it is a rule, written where rules are written and
# published the way rules are published (#151 §6).
#
# ⚠ **THE TWO ACTS BELOW DECLARE A DRAFT AND NOTHING ELSE.** Neither writes a
# rule: an override is created, changed and retired through a publish, on the
# customer's own book, through the book's own routes — the same draft, the same
# diff, the same forward-dating, the same reversal-by-further-publish. There is
# no immediate-effect path to an override and no second mutation surface for
# one. What these two add is the book: a client declaring a customer's first
# override does not have to know that a container exists.


@metering_router.post("/pricing/customers/{customer_id}/overrides",
                      response={200: BookPublishOut, 404: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_DECLARED)
def declare_customer_override(request, customer_id: UUID,
                              payload: CustomerOverrideIn):
    """Declare one customer's own pricing rule, as a draft.

    The override states a WHOLE rule — the quantity it prices, the selectors it
    pins, how it derives its price and what it charges — and replaces whatever
    this customer inherits for that rule. Nothing is inherited into it: a field
    left out takes the rule defaults, never the superseded rule's value, so a
    customer moved from a margin over cost onto a flat price is stated in one
    body. `GET /pricing/customers/{customer_id}/inherited-rule` answers what
    they get today, which is what a client offers as the starting point.

    **This writes no rule.** It declares a draft on the customer's own book,
    exactly as a change to any other book is declared, and publishing it
    through `POST /pricing/books/{book_id}/publishes/{publish_id}/publish`
    is what puts the deal in force. The response carries that book's id and the
    diff.

    `effective_at` dates the override forward and omitting it means now, under
    the bounds every publish takes: timezone-aware (`effective_at_naive`), not
    in the past (`effective_at_in_past`), within 366 days
    (`effective_at_too_far_ahead`), and at or after the latest boundary already
    scheduled on this customer's book
    (`effective_at_before_scheduled_boundary`).
    """
    # The instant is checked before anything else happens, for the reason
    # `declare_book_publish` states in full: a refusal placed under a write
    # spends what it refuses, and this handler's writes are the customer's book
    # (created on first declaration), the draft and the governance entry.
    if payload.effective_at is not None:
        validate_scheduled_instant(payload.effective_at, timezone.now())

    from apps.metering.pricing.services.book_service import BookService

    _gate_a_pricing_book(request)
    customer = get_object_or_404(Customer, id=customer_id,
                                 tenant=request.auth.tenant)
    slots = slot_map(request.auth.tenant.id)
    body = {**payload.dict(exclude={"effective_at"}), "line": LINE_RATE,
            "kind": CHANGE_ADD}
    try:
        change = book_change_body(body, slots)
    except UndeclaredGroupingField as e:
        raise Problem(
            "validation_error",
            f"no grouping field is declared under the key {e.key!r}. A "
            f"rule selects on a grouping field this tenant has declared; "
            f"declare it first, then price on it")
    try:
        with transaction.atomic():
            book = BookService.the_customers_own_book(
                request.auth.tenant, customer)
            record = BookService.declare(book, [change],
                                         effective_at=payload.effective_at)
            audit_record(
                action=AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_DECLARED,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
                resource_id=record.id,
                metadata={"customer_id": str(customer.id),
                          "book_id": str(book.id),
                          "measurement_key": payload.measurement_key,
                          "effective_at": record.effective_at.isoformat()},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.delete("/pricing/customers/{customer_id}/overrides/{override_id}",
                        response={200: BookPublishOut, 404: ProblemOut,
                                  422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_WITHDRAWN)
def withdraw_customer_override(request, customer_id: UUID, override_id: UUID,
                               effective_at: datetime = None):
    """Withdraw one of a customer's own rules: they go back to inheriting.

    **This writes no rule either.** It declares a draft retiring the override
    on the customer's own book, and publishing that draft is what ends the
    deal. Retiring an override reopens nothing and revives nothing — the rule
    the customer inherits was there all along, out-ranked, and starts
    answering again the moment it is not.

    `effective_at` dates the withdrawal forward under the same bounds a publish
    takes, and omitting it means now.
    """
    if effective_at is not None:
        validate_scheduled_instant(effective_at, timezone.now())

    from apps.metering.pricing.services.book_service import BookService

    _gate_a_pricing_book(request)
    override = get_object_or_404(
        Rate.objects.select_related("pricing_book", "measurement"),
        id=override_id, tenant=request.auth.tenant,
        pricing_book__customer_id=customer_id)
    # The change is built from the rule's OWN columns rather than from a body,
    # so what is retired is the rule the caller addressed and nothing that
    # merely resembles it. `plan_changes` identifies a rule by the quantity it
    # prices plus its selectors, which is exactly what this reads back.
    change = {"line": LINE_RATE, "kind": CHANGE_RETIRE,
              "measurement_key": override.measurement_key,
              **{name: getattr(override, name) for name in Rate.SELECTORS}}
    try:
        with transaction.atomic():
            record = BookService.declare(override.pricing_book, [change],
                                         effective_at=effective_at)
            audit_record(
                action=AUDIT_ACTION_CUSTOMER_PRICING_OVERRIDE_WITHDRAWN,
                tenant_id=request.auth.tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_PRICING_BOOK_PUBLISH,
                resource_id=record.id,
                metadata={"customer_id": str(customer_id),
                          "book_id": str(override.pricing_book_id),
                          "override_id": str(override.id),
                          "measurement_key": override.measurement_key,
                          "effective_at": record.effective_at.isoformat()},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.get("/pricing/customers/{customer_id}/inherited-rule",
                     response={200: InheritedRuleOut, 404: ProblemOut,
                               422: ProblemOut})
@role_floor(READ)
def get_inherited_rule(request, customer_id: UUID, measurement_key: str,
                       provider: str = "", event_type: str = "",
                       task_type: str = "", subtask_type: str = "",
                       grouping_field: list[str] = Query([]),
                       as_of: datetime = None):
    """What this customer is charged for a rule where they have no override.

    The starting point for writing one: the rule as it stands for this customer
    with their own book taken out of the ladder, so a client can show the
    method and the current value the override is about to replace, and copy
    them into `POST /pricing/customers/{customer_id}/overrides`.

    It is the same ladder one rung shorter — same specificity-before-source,
    same absence of fallthrough between books — so what is shown cannot drift
    from what is being overridden.

    `rule` is null where nothing is inherited, which is an ordinary state
    rather than an error: a quantity no book in play prices falls to the
    tenant's markup rung, and an override written there starts from nothing.

    Each `grouping_field` is `key=value`, naming a grouping field this tenant
    has declared; repeat the parameter to pin more than one. `as_of` asks the
    question at an instant other than now.
    """
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id,
                                 tenant=request.auth.tenant)
    slots = slot_map(request.auth.tenant.id)
    selectors = {name: "" for name in Rate.SELECTORS}
    selectors.update(provider=provider, event_type=event_type,
                     task_type=task_type, subtask_type=subtask_type)
    for pinned in grouping_field:
        key, separator, value = pinned.partition("=")
        if not separator or key not in slots:
            raise Problem(
                "validation_error",
                f"grouping_field takes `key=value` naming a grouping field "
                f"this tenant has declared; got {pinned!r}")
        selectors[slots[key]] = value
    from apps.metering.pricing.services.pricing_service import PricingService

    rule = PricingService.the_rule_a_customer_inherits(
        tenant=request.auth.tenant, customer=customer, selectors=selectors,
        measurement_key=measurement_key,
        currency=request.auth.tenant.default_currency or "usd",
        as_of=as_of or timezone.now())
    # The rule's OWN selector values, not the ones asked about: a rule that
    # leaves a selector unpinned matches an event that carries one, and a
    # starting point echoing the request would tell a client the rule pins
    # something it does not.
    return 200, inherited_rule_out(
        rule,
        {} if rule is None else {name: getattr(rule, name)
                                 for name in Rate.SELECTORS},
        keys_by_slot(request.auth.tenant.id))


@metering_router.post("/pricing/resolution-runs",
                      response={200: ResolutionRunOut, 404: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_RESOLUTION_RUN_EXECUTED)
def execute_resolution_run(request, payload: ResolutionRunIn):
    """Complete what was never resolved: prices and supplier costs UBB could
    not work out at the time.

    Each posting the run reaches is re-resolved **at its own effective
    instant**, and a field recorded as unresolved is completed where that
    resolution now has an answer. Nothing else is touched: a posting already
    carrying a cost or a price is not in the set the run selects from, and
    neither is one whose charge was waived — a waived charge is a decision
    somebody made, not information UBB is missing.

    **Nothing is repriced.** A rule takes effect from the moment it is published
    forward, so writing one today does not change work recorded in July; what a
    run completes is what today's markup rung and each Event Type's last
    published declaration resolve at that past instant. A draft change to an
    Event Type does not reach a run until it is published.

    **A run moves no money.** No invoice, credit note, charge or refund follows
    from one. It completes the numbers and records that it did, and the response
    says what it completed.

    The selector takes a date range, a customer and an Event Type in any
    combination — the range is half-open, `[from, to)` — and any other field is
    refused (`validation_error`). A customer this tenant does not have is a 404.
    `more_to_do` says the selector matched more postings than one run takes;
    send the same body again and the next run continues where this one stopped.

    A run cannot be undone: completing an unresolved field happens exactly once,
    and the receipt is sealed after it. It requires the `admin` role.
    """
    from apps.metering.pricing.services import resolution_run

    # ⚠ THE METERING GATE, LIKE EVERY PRICING ROUTE BESIDE IT SINCE #553. A run
    # completes BOTH pairs, and one of them — a supplier cost UBB never learned
    # — is metering's own, owed to a metering-only tenant who never charges
    # anybody through UBB; gating on `billing` would leave exactly that tenant
    # with no way through an unresolved-cost backlog. The price pair is no
    # longer a reason to gate differently: a metering-only tenant declares
    # Pricing Books like any other (ADR-0021 §4), its event-priced postings are
    # priced for its own margin reporting, and an `unknown` price of its is
    # completed by a run exactly as a billing tenant's is. What a run never
    # does, for anybody, is move money.
    _product_check(request)
    customer = None
    if payload.selected_customer_id is not None:
        customer = get_object_or_404(Customer, id=payload.selected_customer_id,
                                     tenant=request.auth.tenant)
    selector = resolution_run.RunSelector(
        selected_from=payload.selected_from,
        selected_to=payload.selected_to,
        selected_customer=customer,
        selected_event_type=payload.selected_event_type)

    # ONE TRANSACTION FOR THE WHOLE RUN, which is what makes it all or nothing:
    # a failure part way through leaves no completed postings and no record
    # claiming otherwise. That is the honest shape for an act nothing can undo.
    #
    # ⚠ NOTHING ABOVE THIS REFUSES A SECOND RUN, AND THAT IS DELIBERATE. A run
    # is idempotent by construction — everything it completes leaves the set it
    # selects from — so re-sending the same body reaches whatever the first run
    # could not repair and answers with an outcome. A guard reading "that
    # selector has already been run" or "there is nothing to do" would refuse
    # the second call forever while the criteria still read as satisfied.
    with transaction.atomic():
        run = resolution_run.execute(tenant=request.auth.tenant,
                                     selector=selector)
        audit_record(
            action=AUDIT_ACTION_RESOLUTION_RUN_EXECUTED,
            tenant_id=request.auth.tenant.id,
            resource_type=AUDIT_RESOURCE_TYPE_RESOLUTION_RUN,
            resource_id=run.id,
            metadata={"selector": run.selector,
                      "postings_examined": run.postings_examined,
                      "costs_settled": run.costs_settled,
                      "prices_resolved": run.prices_resolved,
                      "more_to_do": run.more_to_do},
        )
    return 200, resolution_run_out(run)


# --- What a run is aimed at, what it would be worth, and what waiving cost ---
#
# The three READS a Resolution Run projects onto (#364, ruling 11). Every one of
# them is a GET, and that is the ruling rather than the shape that fell out: the
# customer adjustment is the only one of the four recovery mechanisms that moves
# money, two documents forbid it being automatic, and Stripe owns the billing
# engine UBB drives but never reimplements. So there is a figure with its
# receipts and no button that bills.
#
# ⚠ THE METERING GATE, FOR #363'S REASON. Half of what these report is a
# supplier cost UBB never learned, which is owed to a metering-only tenant who
# charges nobody through UBB. Gating on `billing` would leave exactly the tenant
# the unresolved-cost queue exists for unable to read it.
#
# ⚠ AND THE READ FLOOR IS SAFE ONLY BECAUSE BOTH BOUNDS BELOW EXIST. The
# projection runs the same per-posting re-resolution the ADMIN-floored run does,
# so an unbounded one would be expensive work at the lowest role. A stated
# window is capped at `REPORT_WINDOW_MAX_DAYS` here and the work itself is
# capped at `MAXIMUM_POSTINGS_PER_RUN` in the service, which is what keeps a
# read a read. The floor is the carve's default for a GET (#74) because these
# decide nothing; the act they project keeps its Admin floor above.
#
# ⚠ THE DOCSTRINGS BELOW ARE THE TENANT CONTRACT — exported verbatim into
# `openapi/v1.json` and the generated SDK — so they say what a caller needs and
# nothing about why. Each response also carries a `basis` field stating what its
# figures are taken over; these do not repeat it.


def _the_filter_axes_or_404(request, selected_from, selected_to,
                            selected_customer_id, selected_event_type):
    """The three axes as read-contract keyword arguments, or a refusal.

    Two refusals, both before any work: a customer this tenant does not have is
    a 404 rather than an empty answer — a filter that silently matched nothing
    would read as *there is nothing to recover for them*, which is a different
    and much worse statement — and a stated window longer than
    `REPORT_WINDOW_MAX_DAYS` is refused, which
    `docs/conventions/api-contract.md` requires of every computed report and
    which the three rollups above already enforce.

    ⚠ **AN OMITTED BOUND IS STILL UNPINNED, WHICH IS THE HOUSE READING AND NOT
    AN OVERSIGHT.** The rule is about a *stated* window; the sibling reports
    compare two dates and refuse the span, and a surface that demanded a range
    would refuse the commonest question a tenant has — *what have I got
    outstanding altogether*. What bounds the unbounded case is the work cap in
    the service, which is reported as a count rather than left silent.

    The axes travel as plain keyword arguments rather than as the run's own
    `RunSelector` because the read contract returns and takes plain data
    (ADR-001); `queries` builds the selector on the other side, in one place, so
    that the surfaces and the run cannot come to filter differently.
    """
    if selected_customer_id is not None:
        get_object_or_404(Customer, id=selected_customer_id,
                          tenant=request.auth.tenant)
    if selected_from is not None and selected_to is not None:
        if selected_to < selected_from:
            raise Problem("validation_error",
                          "selected_to must not precede selected_from")
        if (selected_to - selected_from).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error",
                          "date window must not exceed 366 days")
    return {"selected_from": selected_from, "selected_to": selected_to,
            "selected_customer_id": selected_customer_id,
            "selected_event_type": selected_event_type}


@metering_router.get("/pricing/unresolved-queue",
                     response={200: PaginatedUnresolvedQueue, 404: ProblemOut,
                               422: ProblemOut})
@role_floor(READ)
def get_unresolved_queue(request, selected_from: datetime = None,
                         selected_to: datetime = None,
                         selected_customer_id: UUID = None,
                         selected_event_type: str = "",
                         cursor: str = None, limit: int = 50):
    """Everything UBB could not resolve: a supplier cost it never learned, a
    customer price it could not work out, or both.

    Each row carries the status that put it in the list and, for a supplier
    cost, the recorded reason the cost is missing. An amount UBB does not have
    is `null`, never a zero.

    These are exactly the postings a Resolution Run over the same filter would
    take up. The filter is the run's: a date range over the posting's own
    effective instant (half-open, `[selected_from, selected_to)`), a customer,
    and an Event Type, in any combination. A customer this tenant does not have
    is a 404; a stated window longer than 366 days is a `validation_error`.

    `totals` is over the whole filter rather than over one page, one row per
    currency, and says how many postings each figure could not include.
    """
    _product_check(request)
    return 200, metering_queries.get_unresolved_queue(
        request.auth.tenant.id, cursor=cursor, limit=limit,
        **_the_filter_axes_or_404(request, selected_from, selected_to,
                                  selected_customer_id, selected_event_type))


@metering_router.get("/pricing/projected-adjustment",
                     response={200: ProjectedAdjustmentOut, 404: ProblemOut,
                               422: ProblemOut})
@role_floor(READ)
def get_projected_adjustment(request, selected_from: datetime = None,
                             selected_to: datetime = None,
                             selected_customer_id: UUID = None,
                             selected_event_type: str = ""):
    """What recovering this filter would be worth, per customer.

    A projection and not an instruction: reading it moves no money, creates no
    invoice, credit note, charge or refund, and UBB will not bill your customer
    for it. Deciding to go back to a customer stays yours, and you act on it
    through the billing path you already use.

    Each posting is re-resolved at its own effective instant, so nothing is
    repriced against today's rules. `usage_event_ids` names the postings behind
    each figure; each one's Pricing Receipt is at
    GET /metering/usage/{event_id}.

    One pass examines a bounded number of postings. `postings_not_examined`
    says how many the filter matched beyond it — narrow the date range to reach
    those — and `unpriced_event_count` says how many examined postings still
    resolve to no price. Each figure is the sum of what a run would settle, and
    is complete when both counts are zero.

    The filter is the Resolution Run's: a half-open date range, a customer and
    an Event Type, in any combination. A customer this tenant does not have is
    a 404; a stated window longer than 366 days is a `validation_error`.
    """
    _product_check(request)
    return 200, metering_queries.get_projected_adjustment(
        request.auth.tenant.id,
        **_the_filter_axes_or_404(request, selected_from, selected_to,
                                  selected_customer_id, selected_event_type))


@metering_router.get("/pricing/waived-loss",
                     response={200: WaivedLossOut, 404: ProblemOut,
                               422: ProblemOut})
@role_floor(READ)
def get_waived_loss(request, selected_from: datetime = None,
                    selected_to: datetime = None,
                    selected_customer_id: UUID = None,
                    selected_event_type: str = ""):
    """What waiving has cost you over a period, as money.

    A charge is waived where the margin rule had no supplier cost to take a
    margin over, so a waived posting never carried a price and this figure
    cannot be revenue forgone. `basis` states what it is instead, in the
    response itself.

    Waived postings whose own supplier cost UBB never learned are not in the
    figure and are counted beside it: the total is the sum of the resolved
    costs, complete when that count is zero (#603). Waived postings
    are never candidates for a Resolution Run: a decision somebody made is not
    information UBB is missing.

    Rows are per currency and there is no total across them. The filter is the
    Resolution Run's: a half-open date range, a customer and an Event Type, in
    any combination. A customer this tenant does not have is a 404; a stated
    window longer than 366 days is a `validation_error`.
    """
    _product_check(request)
    return 200, metering_queries.get_waived_loss(
        request.auth.tenant.id,
        **_the_filter_axes_or_404(request, selected_from, selected_to,
                                  selected_customer_id, selected_event_type))


@metering_router.put("/grouping-fields",
                     response={200: GroupingFieldRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit(AUDIT_ACTION_GROUPING_FIELD_DECLARED)
def declare_grouping_fields(request, payload: GroupingFieldRegistryIn):
    """Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8)."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_grouping_fields
    from apps.platform.grouping_fields.services import GroupingFieldError, GroupingFieldService

    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            for d in payload.grouping_fields:
                GroupingFieldService.declare(tenant, key=d.key, slot=d.slot, scope=d.scope,
                                             max_cardinality=d.max_cardinality)
            audit_record(
                action=AUDIT_ACTION_GROUPING_FIELD_DECLARED,
                tenant_id=tenant.id,
                resource_type=AUDIT_RESOURCE_TYPE_GROUPING_FIELD_REGISTRY,
                resource_id=tenant.id,
                # THE AUDIT RECORD NAMES WHAT THE RESPONSE NAMES. `metadata`
                # is an open object on a tenant-readable feed, so this key
                # is as published as the body below it; records written
                # before #505 keep the word they were written with, which
                # is what an immutable ledger means.
                metadata={"grouping_fields": [
                    {"key": d.key, "slot": d.slot, "scope": d.scope,
                     "max_cardinality": d.max_cardinality}
                    for d in payload.grouping_fields]},
            )
    except GroupingFieldError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"grouping_fields": declared_grouping_fields(tenant.id)}


@metering_router.get("/grouping-fields", response=GroupingFieldRegistryOut)
@role_floor(READ)
def list_grouping_fields(request):
    """This tenant's declared Grouping Field vocabulary."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_grouping_fields
    return {"grouping_fields": declared_grouping_fields(request.auth.tenant.id)}


@metering_router.get("/grouping-fields/{key}/values",
                     response={200: GroupingFieldValuesOut, 404: ProblemOut})
@role_floor(READ)
def list_grouping_field_values(request, key: str):
    """Every value admitted for one Grouping Field — the read model a dashboard
    filter dropdown needs. Bounded by the key's max_cardinality (D4)."""
    _product_check(request)
    from apps.platform.grouping_fields.models import GroupingField, GroupingFieldValue

    if not GroupingField.objects.filter(tenant=request.auth.tenant, key=key).exists():
        raise Problem("not_found", f"{key!r} is not a declared grouping field")
    values = list(GroupingFieldValue.objects.filter(
        tenant=request.auth.tenant, key=key).order_by("value").values_list("value", flat=True))
    return 200, {"key": key, "values": values}


@metering_router.get("/analytics/grouping-options", response=GroupingOptionsOut)
@role_floor(READ)
def list_grouping_options(request):
    """What this tenant may group an economic question by — the discovery
    contract (#498, slice 7 §7).

    `apps/metering/queries.py::grouping_options` computes it and argues what it
    is for; this is the wire, and the two things the wire itself decides.

    Read floor, and deliberately: a finance operator building a chart is exactly
    who asks this, and it publishes no amount. The axes it lists are the
    tenant's own declarations, which the same floor already reads next door.

    UNPAGINATED, on `docs/conventions/api-contract.md`'s *"computed reports are
    not lists"* clause rather than in spite of its cursor rule. It is computed
    per tenant; and where that clause asks a report to be parameter-bounded,
    this one is bounded by CONSTRUCTION — the always-present axes, at most the
    registry's ten slots, and the two rollups — so there is no window a caller
    could leave open. The two registry reads beside it answer the same way.
    """
    _product_check(request)
    from apps.metering.queries import grouping_options
    return {"options": grouping_options(request.auth.tenant.id)}


#: The problem code a well-formed question UBB will not answer earns.
#:
#: ⚠ **A SECOND CODE, AND THE DIVISION IS WHAT A CALLER DOES NEXT.**
#: `validation_error` means the request is malformed — a date that will not
#: parse, a window past the bound, a measure name that is not one — and the
#: remedy is to fix the request. This one means the request is perfectly
#: well-formed and UBB declines to answer it, because answering would be subtly
#: wrong; the remedy is to ask a DIFFERENT question, and the sentence says which.
#: Serving both on one code would give away, on the one surface built to refuse
#: the dishonest comparison, exactly the distinguishability the refusal is for.
UNANSWERABLE_COMBINATION = "unanswerable_combination"


def _equality_filters(wanted):
    """The declared grouping fields a caller pinned to a value.

    Each one is `<axis word>=<value>`, split at the FIRST `=`. ⚠ **A DECLARED
    KEY MAY CONTAIN THAT CHARACTER AND SUCH A KEY CANNOT BE FILTERED THIS WAY**,
    which is a named limit rather than a hatch: UBB never invented a charset for
    a tenant's own key — the registry says so at the column, because a charset
    UBB invented would be UBB second-guessing a tenant's catalogue — so the
    split has to happen somewhere and a value may contain the character too.
    Splitting at the first one makes the failure LOUD: the text before it is not
    an axis this tenant declared, and the refusal names the word.
    """
    filters = []
    for entry in wanted or []:
        axis, separator, value = str(entry).partition("=")
        if not separator or not axis:
            raise Problem(
                "validation_error",
                f"{entry!r} is not a filter; each one is <axis>=<value>, "
                "with the axis spelled as it is on the grouping options")
        filters.append((axis, value))
    return filters


@metering_router.get("/analytics/economics",
                     response={200: EconomicsOut, 422: ProblemOut})
@states_its_report_window()
@role_floor(READ)
def query_economics(request,
                    start_date: Optional[date] = Query(None, description=START_DATE_DESCRIPTION),
                    end_date: Optional[date] = Query(None, description=END_DATE_DESCRIPTION),
                    measures: list[str] = Query(None),
                    group_by: list[str] = Query(None),
                    bucket: str = None,
                    basis: str = None,
                    customer_id: UUIDIdentifier = None,
                    event_type: str = None, task_type: str = None,
                    task_id: UUIDIdentifier = None,
                    include_subtasks: bool = False,
                    where: list[str] = Query(None),
                    past_limit: bool = None, stop_scope: str = None,
                    episode_seq: int = None):
    """What your AI work cost, what it earned, and the difference — one answer
    from one definition.

    Ask for one or more `measures`, group by zero or more axes from
    `/metering/analytics/grouping-options`, and bucket by `hour`, `day` or
    `month`. Every filter composes with every grouping.

    **Requesting no measure is refused rather than defaulted**: a default
    measure set is how a caller ends up aggregating three different things to
    draw one line.

    **A row's grouped values are positional**, in the order the axes were sent,
    and the response echoes `group_by` so the alignment is readable from the
    answer alone. Where a row has no value on an axis, the entry beside it says
    whether the value was never recorded or whether the question does not apply
    to that kind of row.

    **Each measure carries its own state and the state is part of the answer.**
    A margin UBB cannot attribute at the grain you asked for is absent rather
    than small, and the revenue that could not be placed is listed under
    `context` with the axes at which asking again would produce one.

    **A revenue figure you supplied is the whole revenue for the customer and
    period it covers.** Revenue UBB derived from priced usage inside that period
    is not added to it, and usage nobody priced there does not make it
    incomplete — the count of that usage is still published. Everywhere else a
    revenue is derived from priced usage: where some usage is unpriced the
    figure is the sum of what was priced and reads `incomplete`, and where no
    piece of a row's revenue resolved at all, the revenue and the margin read
    `incomplete` with no amount. A deliberate zero price is resolved.

    `basis` picks how revenue a tenant supplied is spread over the span it
    declares: `recorded` places each amount whole on the day its record opens
    and is the default, `recognised` spreads it by the record's own method. It
    moves where a supplied amount lands and never which usage the record
    covers. So because `recorded` attributes the whole supplied figure to the
    day its period opens, windows elsewhere in its covered period may contain
    known zero recorded revenue — and a known negative margin over the usage in
    them. Use `recognised` when analysing revenue attributable across the
    covered period. The answer always states which it served.

    **How far back you may ask, and how much of it per request — the two
    numbers, together, because they do not compose on their own.** UBB keeps the
    economics for six years and detailed measurement on a shorter platform
    clock, and this answer publishes both start dates in
    `economic_data_available_from` and `measurement_data_available_from` —
    always, whether or not anything was truncated. One request, meanwhile, spans
    at most 366 calendar dates, or 92 for an hourly question, because that
    ceiling is about how many buckets one answer may carry. So six years of
    history is read as consecutive windows (below), not in one call, and the
    response states each number rather than leaving you to discover the second
    by being refused.

    A measure whose stretch reaches back past the horizon governing it reads
    `unavailable_outside_retention_horizon` and carries `available_from`: never
    a zero, and never a partial total presented as a total. Only a question
    grouped by the measurement-concept rollup is governed by the shorter clock;
    every money measure is on the six-year one however you filter it. The
    response echoes the period it applied, so a caller who left the window to
    the default can see what it was.

    Codes: `validation_error` for a request that will not parse or a window past
    the bound; `unanswerable_combination` for a well-formed question this
    surface declines to answer subtly wrongly, whose message says what to ask
    instead.
    """
    _product_check(request)
    from apps.metering.queries import (
        ECONOMIC_BUCKETS, ECONOMIC_MEASURES, EconomicFilters,
        EconomicQuestionRefused, economic_refusal, grouping_options)
    from apps.subscriptions.economics.revenue import DEFAULT_REVENUE_BASIS

    measures = list(measures or [])
    axes = list(group_by or [])
    chosen = basis or DEFAULT_REVENUE_BASIS
    if chosen not in REVENUE_BASIS_VALUES:
        raise Problem("validation_error",
                      f"unknown basis {chosen!r}; allowed: "
                      f"{', '.join(sorted(REVENUE_BASIS_VALUES))}")
    # The bucket is settled BEFORE the window, because the window's ceiling
    # depends on it: an hourly question keeps the tighter one.
    if bucket is not None and bucket not in ECONOMIC_BUCKETS:
        raise Problem("validation_error",
                      f"unknown bucket {bucket!r}; allowed: "
                      f"{', '.join(ECONOMIC_BUCKETS)}")
    # ⚠ ONE WINDOW, RESOLVED ONCE, AND EVERYTHING BELOW READS IT: the postings,
    # the revenue windows, the covered periods and the two horizons, which read
    # the clock through `window.today` rather than again — two readings a
    # microsecond apart answer differently across midnight, and the surface
    # would then publish a period its own horizon disagreed with. An hourly
    # question keeps the tighter ceiling, because the measurement fold is
    # Python-side and rests on that bound by name.
    window = resolve_report_window(start_date, end_date,
                                   hourly=bucket == "hour")
    filters = EconomicFilters(
        window=window, customer_id=customer_id,
        event_type=event_type, task_type=task_type, task_id=task_id,
        include_subtasks=include_subtasks, past_limit=past_limit,
        stop_scope=stop_scope, episode_seq=episode_seq,
        field_filters=_equality_filters(where))
    refusal = economic_refusal(request.auth.tenant.id, measures=measures,
                               axes=axes, event_type=event_type)
    if refusal is not None:
        # ⚠ TWO CODES, AND THE LINE BETWEEN THEM IS WHETHER THE REQUEST CAN BE
        # READ AT ALL. A name this vocabulary does not contain — a measure, or
        # an axis the tenant never declared — is a request UBB cannot
        # interpret, and the remedy is to fix it. Everything else here is a
        # request UBB reads perfectly and declines to answer subtly wrongly,
        # and the remedy is to ask a DIFFERENT question. One code for both
        # would give away, on the surface built to refuse the dishonest
        # comparison, exactly the distinguishability the refusal is bought for.
        #
        # ⚠ DECIDED STRUCTURALLY AND NOT BY READING THE SENTENCE. Matching on
        # the refusal's wording would make the published error code depend on
        # prose, so re-wording a message for clarity would silently re-code the
        # response. The extra read runs only on the refusal path.
        offered = {option["key"]
                   for option in grouping_options(request.auth.tenant.id)}
        unreadable = (not measures
                      or set(measures) - set(ECONOMIC_MEASURES)
                      or any(word not in offered for word in axes))
        raise Problem("validation_error" if unreadable else
                      UNANSWERABLE_COMBINATION, refusal)

    try:
        answer, foreign = ask_the_economic_query(
            request.auth.tenant.id, measures=measures, group_by=axes,
            bucket=bucket, basis=chosen, window=window, filters=filters)
    except EconomicQuestionRefused as refused:
        # The read contract answers a refusal as a sentence, because a read
        # contract returns plain data and the caller decides what an
        # unanswerable request looks like on its own surface. This is that
        # decision, and it is the same one the pre-flight above makes — the
        # pre-flight exists so the common refusals never build a queryset.
        #
        # ⚠ THE TYPE IS WHAT MAKES THIS SAFE. Catching `ValueError` would catch
        # every incidental one the query or Django raises underneath it and
        # render its internal message to a tenant as a 422 refusal. Only a
        # refusal of the QUESTION is translated; a `ValueError` about the CALL
        # — the caller forgot the revenue rows — is a bug and reaches the
        # handler as one.
        raise Problem(UNANSWERABLE_COMBINATION, str(refused))
    return 200, {"period_start": window.start_date.isoformat(),
                 "period_end": window.end_date.isoformat(), **answer,
                 FOREIGN_CURRENCY_SUBSCRIPTION_COUNT_KEY: foreign}
