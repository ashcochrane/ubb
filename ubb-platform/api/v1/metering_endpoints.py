import logging
from datetime import date, datetime
from uuid import UUID

from django.db import IntegrityError, transaction
from django.db.models import Sum, Count, Q
from django.db.models.fields.json import KeyTextTransform
from django.shortcuts import get_object_or_404
from ninja import Query, Router

from apps.metering.pricing.receipts import (
    pricing_method_of,
    uncosted_quantity_keys,
)
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, WRITE, role_floor
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY, carry_cost_total,
    cost_total_annotations,
)
from core.identifiers import UUIDIdentifier
from core.problems import Problem, ProblemOut
from core.responses import StatusResponse
from core.scheduling import validate_scheduled_instant
from core.time_windows import (
    REPORT_WINDOW_MAX_DAYS, utc_day_start, utc_next_day_start)
from django.utils import timezone

from api.v1.schemas import (
    RecordUsageRequest, RecordUsageResponse,
    UsageBatchRequest, UsageBatchResponse,
    PaginatedUsageResponse,
    UsageEventDetailOut,
    TenantMarkupIn, TenantMarkupOut,
    TenantDefaultMarkupIn, TenantDefaultMarkupOut,
    CloseTaskResponse,
    TaskDetailOut, PaginatedTasks, task_out,
    UsageAnalyticsResponse,
    UsageTimeseriesResponse,
    TaskAnalyticsOut,
    RateIn, RateOut, BookIn, BookOut, RateChangeIn, PublishIn, AssignIn,
    PaginatedBooks, PaginatedRates,
    BookPublishIn, BookPublishOut, PaginatedBookPublishes,
    CustomerOverrideIn, InheritedRuleOut, inherited_rule_out,
    ResolutionRunIn, ResolutionRunOut, resolution_run_out,
    UndeclaredGroupingField,
    book_change_body, book_change_diff_out, book_publish_out,
    book_out, rate_change_body, rate_out, usage_event_out,
    SLOT_PROPERTY_COLUMNS,
    DimensionRegistryIn, DimensionRegistryOut, GroupingFieldValuesOut,
    TaskTypeRegistryIn, TaskTypeRegistryOut,
)
from apps.metering.pricing.models import (
    CHANGE_ADD, CHANGE_RETIRE,
    PricingBookPublish, Rate, RateCard, RateCardAssignment,
    CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES,
)
from api.v1.pagination import page
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.audit.actors import get_current_actor
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.metering.queries import GROUPED_VALUE_KEY
from apps.platform.event_types.costing import (
    admits_a_caller_supplied_cost, cost_declaration)
from apps.platform.event_types.quantities import declaration_named
from core.vocabulary import (
    COSTING_METHOD_REPORTED, DECLARATION_STATUS_DRAFT,
    SOURCE_KIND_CALLER_SUPPLIED)
from apps.metering.usage.services.usage_service import (
    EffectiveAtError, UsageService)
from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.models import SLOT_CHOICES
from apps.platform.grouping_fields.queries import keys_by_slot, slot_map
from apps.platform.grouping_fields.services import DimensionError, DimensionService

logger = logging.getLogger(__name__)

metering_router = Router(auth=ApiKeyAuth())

_product_check = ProductAccess("metering")


# --- The request-item adapters over UsageService.record_usage ---------------
#
# These moved here when the async accept pipeline was deleted. They were
# lifted out of this module by #113 to be SHARED between the endpoints and
# that pipeline; with the pipeline gone the two recording routes below are
# their only callers, so the seam that justified a separate module no longer
# has two sides. Written once, here, rather than twice: the single route and
# the batch route must map fields and classify errors identically or the
# batch stops being "N sequential singles".


class SupplierCostNotAdmissible(ValueError):
    """A caller stated the supplier's own cost where no declaration admits it.

    Raised by :func:`admit_supplier_cost` before anything is written or
    recorded. The single route renders it as a **422**; the batch route renders
    it as a rejected ITEM verdict inside its always-200 body — the same shape
    every other per-item failure takes there, because on that route a non-200
    would mean the whole batch was not recorded (`docs/conventions/
    api-contract.md`, *Usage verdicts: data, not errors*). A ``ValueError`` so
    it takes the same lane as every other pre-recording refusal here.
    """


def admit_supplier_cost(tenant, item):
    """Refuse a supplier cost the Event Type's declaration does not admit (#324).

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

    **IT RUNS BEFORE ANYTHING IS WRITTEN.** Both routes call it above the
    grouping-field admission, which records novel values against a cardinality
    cap: a refusal underneath that would have spent a tenant's keyspace on a
    request that was never recorded. Nothing here writes, so first is free.

    **WHAT IT COSTS, STATED RATHER THAN HIDDEN.** One query, and only on a
    request that carries the figure — which is precisely the branch on which
    the compute spine skips the same lookup, so no event pays for it twice. An
    event that carries no supplier cost reads exactly what it read before. A
    batch pays it per item that carries one; it is deliberately not memoised
    across the batch, because a batch item is a whole independent request here
    and a shared verdict would be the first place they stopped being one.

    The message names both halves of the declaration that would admit the
    figure, and the field that is accepted anywhere, so a caller reading the
    body knows what to do next rather than only what they may not do.
    """
    if item.provider_cost_micros is None:
        return
    if admits_a_caller_supplied_cost(
            cost_declaration(tenant=tenant, key=item.event_type)):
        return
    named = (f"Event Type {item.event_type!r} does not declare it"
             if item.event_type
             else "This event names no Event Type, so nothing declares it")
    raise SupplierCostNotAdmissible(
        f"provider_cost_micros is the supplier's own reported cost for this "
        f"call. {named}: it is admissible only where the "
        f"Event Type declares costing_method '{COSTING_METHOD_REPORTED}' with "
        f"a reported-cost mapping whose source_kind is "
        f"'{SOURCE_KIND_CALLER_SUPPLIED}'. Declare that pair, or send what you "
        f"believe this call cost as claimed_provider_cost_micros, which is "
        f"accepted on any event and is never treated as cost.")


def usage_kwargs(item):
    """The single↔batch pass-through, written ONCE (#112): the field-for-
    field map from a request item (RecordUsageRequest — the single and batch
    items share the schema) onto record_usage's keyword surface."""
    return dict(
        request_id=item.request_id,
        idempotency_key=item.idempotency_key,
        provider_cost_micros=item.provider_cost_micros,
        claimed_provider_cost_micros=item.claimed_provider_cost_micros,
        billed_cost_micros=item.billed_cost_micros,
        currency=item.currency,
        metadata=item.metadata,
        event_type=item.event_type,
        provider=item.provider,
        task_id=item.task_id,
        measurements=item.measurements,
        effective_at=item.effective_at,
    )


def usage_error(e):
    """The ONE record_usage error map (#112): exception → (code, detail).
    The specific-before-general order lives HERE and only here —
    EffectiveAtError (which IS a ValueError, so it must be tested before the
    generic branch), then plain ValueError. The single endpoint raises the code
    as a Problem; the batch wraps the same code in a verdict dict.

    **A COST UBB CANNOT WORK OUT IS NO LONGER AN ERROR (#320)**, so the branch
    that was first here is gone along with the exception it named and the wire
    code it produced. The supplier has already run the call and already charged
    for it; the event is recorded with its cost said to be unresolved, and the
    caller learns that from the 200 body rather than from a 422 that throws the
    charge away."""
    if isinstance(e, EffectiveAtError):
        return e.code, str(e)
    return "validation_error", str(e)


def with_receipt_reads(result):
    """Surface what the receipt says, typed, on a success body — both recording
    surfaces return it.

    Two reads, and they answer two questions.

    The uncosted-quantity list says WHICH declared quantities went uncosted;
    `costing_status` on the same body says THAT the cost is unresolved. Neither
    is the other: a tenant fixing this needs the specific declaration, and a
    reader totalling a column needs the status.

    The pricing method says HOW the customer price was derived; `pricing_status`
    beside it says whether that price is settled. Null means no derivation
    happened, and the status says why (#355).

    **BOTH ARE ALREADY IN THE BODY, UNTYPED, AND THAT IS THE POINT OF LIFTING
    THEM.** These surfaces publish the whole record in `pricing_provenance`,
    which is `additionalProperties: true` — so a value inside it reaches a
    consumer with no schema saying what it may be, and a closed value set
    published that way is advertised nowhere. Lifting each into a typed field
    is what lets the contract carry the agreed vocabulary for it.

    **THE RECEIPT'S SHAPE IS ASKED FOR, NOT ASSUMED (#349).** An idempotent
    replay answers with the receipt the posting was recorded with, so this is a
    live read over rows written in the older shape as well as the current one —
    a read-path obligation rather than a migration, since old receipts are read
    and never rewritten. The tolerance is expressed once, in the receipts
    module, because a second copy of it here is a second thing to repair."""
    receipt = result.get("pricing_provenance")
    result["uncosted_measurement_keys"] = uncosted_quantity_keys(receipt)
    result["pricing_method"] = pricing_method_of(receipt)
    return result


def _rejected(code, detail):
    """A batch-item rejection verdict: the typed code plus the constant stop
    trio — a rejected item was never recorded, so nothing can have stopped."""
    return {"accepted": False, "code": code, "detail": detail,
            "stop": False, "stop_reason": None, "stop_scope": None}


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
    # #324: this item's own refusal, and it runs FIRST for the reason the
    # grouping-field admission below states about itself — that one WRITES.
    # A refusal underneath it would have spent novel grouping values out of
    # the tenant's cardinality cap on an item that was never recorded.
    try:
        admit_supplier_cost(tenant, item)
    except SupplierCostNotAdmissible as exc:
        return _rejected("validation_error", str(exc))
    # Task 9: admission is a WRITE, run BEFORE the recording core — a bad
    # grouping field is THIS item's rejection, same as any other validation
    # failure below, and never reaches record_usage.
    try:
        dimension_slots = DimensionService.admit(tenant, item.dimensions, scope="event")
    except DimensionError as exc:
        return _rejected("validation_error", str(exc))
    try:
        result = UsageService.record_usage(
            tenant=tenant, customer=customer, dimension_slots=dimension_slots,
            **usage_kwargs(item))
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

    customer = get_object_or_404(Customer, id=payload.customer_id, tenant=request.auth.tenant)
    if payload.task_id is not None:
        get_object_or_404(Task, id=payload.task_id, tenant=request.auth.tenant, customer=customer)
    # #324: the supplier's own figure is admissible only where the Event Type
    # declares it arrives on the call. Refused rather than dropped — a 200 here
    # would tell an integrator UBB is using a number it discards.
    #
    # IT RUNS BEFORE THE GROUPING-FIELD ADMISSION, AND THE ORDER IS THE POINT:
    # that one WRITES (see its own note below), so a refusal underneath it
    # would have burned novel values out of the tenant's cardinality cap for a
    # request that was never recorded. This one is a single read and can go
    # first at no cost.
    try:
        admit_supplier_cost(request.auth.tenant, payload)
    except SupplierCostNotAdmissible as exc:
        raise Problem("validation_error", str(exc))
    # Task 9: admission is a WRITE (records GroupingFieldValue rows), so it runs
    # BEFORE the recording core, outside record_usage's own retry/replay
    # machinery — a bad grouping field is a whole-request 422, never a partial
    # record.
    try:
        dimension_slots = DimensionService.admit(
            request.auth.tenant, payload.dimensions, scope="event")
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
    try:
        result = UsageService.record_usage(
            tenant=request.auth.tenant, customer=customer,
            dimension_slots=dimension_slots,
            **usage_kwargs(payload))
    except ValueError as e:
        code, detail = usage_error(e)
        raise Problem(code, detail)
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
              tag_key: str = None, tag_value: str = None,
              task_id: UUIDIdentifier = None, include_subtasks: bool = False,
              past_limit: bool = None, stop_scope: str = None,
              episode_seq: int = None):
    _product_check(request)

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)

    qs = customer.postings.all()
    # FILTERING is what the open bag is for, and it is what survived the fold
    # in #273 — the parameter names are the analytics vocabulary slice 7 owns
    # and are deliberately left spelled as they are published.
    if tag_key and tag_value:
        qs = qs.filter(metadata__contains={tag_key: tag_value})
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
        "request_id": e.request_id,
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
        # Derived here rather than stored, and read out of the record rather
        # than recomputed (#355). The receipt is the authority on how an amount
        # was reached; re-deriving the method from today's configuration is the
        # failure the receipt exists to prevent. The shape is ASKED FOR, not
        # assumed — the tolerance lives once in the receipts module, like the
        # uncosted list on the recording surfaces.
        "pricing_method": pricing_method_of(e.pricing_provenance),
        "measurements": e.measurements or {},
        # Derived, never stored (ADR-0006 §4) — computed here, at the
        # serialiser, which is the only place §E5 permits it to exist.
        "measurements_status": measurements_status_for(e),
        "pricing_provenance": e.pricing_provenance or {},
        "metadata": e.metadata,
        "task_id": str(e.task_id) if e.task_id else None,
        "effective_at": e.effective_at.isoformat(),
        "created_at": e.created_at.isoformat(),
        "stop_context": e.stop_context,
    }


# --- Task lifecycle ---


@metering_router.post("/tasks/{task_id}/close", response=CloseTaskResponse)
@role_floor(WRITE)
def close_task(request, task_id: UUID):
    """Close (complete) a task or subtask. Closing a PARENT auto-completes
    its active subtasks in the same transaction (#38) — cleanup is one call;
    a killed subtask keeps its state. Closing a subtask completes it alone."""
    _product_check(request)
    from django.db import transaction
    from apps.platform.work.services import TaskService

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    with transaction.atomic():
        completed, _ = TaskService.complete_task(task.id)
    return {
        "task_id": str(completed.id),
        "parent_task_id": str(completed.parent_id) if completed.parent_id else None,
        "status": completed.status,
        "total_billed_cost_micros": completed.total_billed_cost_micros,
        "total_provider_cost_micros": completed.total_provider_cost_micros,
        "unresolved_event_count": completed.unresolved_event_count,
        "unpriced_event_count": completed.unpriced_event_count,
        "event_count": completed.event_count,
    }


@metering_router.get("/tasks", response=PaginatedTasks)
@role_floor(READ)
def list_tasks(request, cursor: str = None, limit: int = 50,
               customer_id: UUIDIdentifier = None, task_type: str = None,
               status: str = None):
    """Top-level units of work with their materialized cost rollups.

    Subtasks are omitted — they belong to their parent's detail view, so a
    listing counts JOBS, not steps."""
    _product_check(request)

    qs = Task.objects.filter(tenant=request.auth.tenant, parent__isnull=True)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if task_type:
        qs = qs.filter(task_type=task_type)
    if status:
        qs = qs.filter(status=status)
    return page(qs, cursor, limit, serialize=task_out, time_field="created_at")


@metering_router.get("/tasks/{task_id}", response={200: TaskDetailOut, 404: ProblemOut})
@role_floor(READ)
def get_task(request, task_id: UUID):
    """One unit's cost receipt plus its subtask tree.

    Reads the rollups `TaskService.accumulate_cost` maintains — including
    events that landed after a kill — so this never aggregates
    ubb_posting. One indexed row read plus its children."""
    _product_check(request)

    task = get_object_or_404(Task, id=task_id, tenant=request.auth.tenant)
    body = task_out(task)
    body["subtasks"] = [task_out(s) for s in
                        task.subtasks.all().order_by("created_at")]
    return 200, body


@metering_router.get("/analytics/tasks", response={200: TaskAnalyticsOut,
                                                  422: ProblemOut})
@role_floor(READ)
def task_analytics(request, group_by: str = "task_type", start_date: date = None,
                   end_date: date = None):
    """Cost per KIND of job: run count, mean, p95, and limit hits.

    A p95 approaching the type's ceiling is the signal that the limit is about
    to start biting real customers."""
    _product_check(request)
    from apps.platform.work.queries import task_rollup_by_type

    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error",
                          "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    try:
        rows = task_rollup_by_type(
            request.auth.tenant.id, group_by=group_by,
            start_date=utc_day_start(start_date) if start_date else None,
            end_date=utc_next_day_start(end_date) if end_date else None)
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
@records_audit("tenant_default_markup.declared")
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
            action="tenant_default_markup.declared",
            tenant_id=request.auth.tenant.id,
            resource_type="tenant_default_markup",
            resource_id=rung.id,
            metadata={"markup_micro_percent": rung.markup_micro_percent},
        )
    return {"markup_micro_percent": rung.markup_micro_percent}


@metering_router.delete("/pricing/default-markup", response=StatusResponse)
@role_floor(ADMIN)
@records_audit("tenant_default_markup.withdrawn")
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
            action="tenant_default_markup.withdrawn",
            tenant_id=request.auth.tenant.id,
            resource_type="tenant_default_markup",
            resource_id=rung_id,
        )
    return {"status": "withdrawn"}


# --- Pricing Markup ---
#
# ⚠ THE TENANT-SCOPE PAIR BELOW NO LONGER PRICES ANYTHING (#357). Resolution's
# tenant-default rung reads the declaration above; what these two write and read
# is a row that survives only until the record is deleted, along with these
# routes, their two schemas and their two audit action names. The
# customer-scope routes further down are unaffected: a customer override is
# still a rung, until it becomes a rule in the customer's own Pricing Book.


@metering_router.get("/pricing/markup", response=TenantMarkupOut)
@role_floor(READ)
def get_tenant_markup(request):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.put("/pricing/markup", response=TenantMarkupOut)
@role_floor(ADMIN)
@records_audit("markup.set")
def upsert_tenant_markup(request, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    with transaction.atomic():
        markup, _ = TenantMarkup.objects.update_or_create(
            tenant=request.auth.tenant,
            customer=None,
            defaults={
                "markup_percentage_micros": payload.markup_percentage_micros,
                "fixed_uplift_micros": payload.fixed_uplift_micros,
            },
        )
        audit_record(
            action="markup.set",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=markup.id,
            metadata={
                "scope": "tenant",
                "markup_percentage_micros": markup.markup_percentage_micros,
                "fixed_uplift_micros": markup.fixed_uplift_micros,
            },
        )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.get("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
@role_floor(READ)
def get_customer_markup(request, customer_id: UUID):
    _product_check(request)
    from apps.metering.pricing.services.markup_service import MarkupService

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = MarkupService.resolve(tenant=request.auth.tenant, customer=customer)
    if markup is None:
        return {"markup_percentage_micros": 0, "fixed_uplift_micros": 0}
    # The rung answers in the honest unit spelling and this response publishes
    # the retired one, so the two are joined here rather than either being
    # renamed: this schema is deleted with the record it describes (#369).
    return {"markup_percentage_micros": markup.markup_micro_percent, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.put("/pricing/customers/{customer_id}/markup", response=TenantMarkupOut)
@role_floor(ADMIN)
@records_audit("markup.set")
def upsert_customer_markup(request, customer_id: UUID, payload: TenantMarkupIn):
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    with transaction.atomic():
        markup, _ = TenantMarkup.objects.update_or_create(
            tenant=request.auth.tenant,
            customer=customer,
            defaults={
                "markup_percentage_micros": payload.markup_percentage_micros,
                "fixed_uplift_micros": payload.fixed_uplift_micros,
            },
        )
        audit_record(
            action="markup.set",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=markup.id,
            metadata={
                "scope": "customer",
                "customer_id": str(customer.id),
                "markup_percentage_micros": markup.markup_percentage_micros,
                "fixed_uplift_micros": markup.fixed_uplift_micros,
            },
        )
    return {"markup_percentage_micros": markup.markup_percentage_micros, "fixed_uplift_micros": markup.fixed_uplift_micros}


@metering_router.delete("/pricing/customers/{customer_id}/markup",
                        response=StatusResponse)
@role_floor(ADMIN)
@records_audit("markup.deleted")
def delete_customer_markup(request, customer_id: UUID):
    """Remove a customer's markup override so they revert to inheriting the
    tenant default. This is NOT the same as PUT-ing 0/0 — a 0/0 row still
    resolves as the customer's markup and SHADOWS the tenant default, pinning
    the customer at cost. Idempotent: 'no_override' when none existed; a bad
    customer id is a 404."""
    _product_check(request)
    from apps.metering.pricing.models import TenantMarkup

    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    markup = TenantMarkup.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if markup is None:
        return {"status": "no_override"}
    with transaction.atomic():
        markup.delete()  # instance delete — the model layer bumps MarkupCache's version
        audit_record(
            action="markup.deleted",
            tenant_id=request.auth.tenant.id,
            resource_type="markup",
            resource_id=customer.id,
            metadata={"scope": "customer", "customer_id": str(customer.id)},
        )
    return {"status": "deleted"}


# --- Analytics ---


# The four reserved dimensions (design D1) plus "customer", which is a column
# on the event rather than a slot. Tenant keys come from the registry.
_RESERVED_ANALYTICS_DIMS = ("provider", "event_type", "task_type", "subtask_type",
                            "customer")

#: How many breakdowns one analytics call may ask for. The tenant slot count,
#: read off the registry rather than restated — six was the slot count too, and
#: #276 made a hard-coded six disagree with it.
#:
#: NOT "one per requestable axis": the four reserved axes plus `customer` are
#: also requestable, so fifteen names can be asked for and ten of them can be
#: served in one call. The cap is a bound on work per request, and the slot
#: count is what it has always been pinned to.
_MAX_BREAKDOWNS = len(SLOT_CHOICES)


def _resolve_dimension(tenant, dim):
    """Map a requested grouping axis to the column to GROUP BY.

    Reserved names map to themselves; declared tenant keys map to their slot.
    Anything else — notably a correlation id like task_id (design D9) — is a
    422, so an unbounded key can never become a group-by.
    """
    from apps.platform.grouping_fields.queries import slot_map

    if dim in _RESERVED_ANALYTICS_DIMS:
        return "customer__external_id" if dim == "customer" else dim
    slot = slot_map(tenant.id).get(dim)
    if slot is None:
        raise Problem("validation_error", f"unknown grouping field {dim!r}")
    return slot


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


@metering_router.get("/analytics/usage", response={200: UsageAnalyticsResponse, 422: ProblemOut})
@role_floor(READ)
def usage_analytics(request, start_date: date = None, end_date: date = None,
                    customer_id: UUIDIdentifier = None, tag_key: str = None,
                    dimensions: list[str] = Query(None),
                    task_id: UUIDIdentifier = None, include_subtasks: bool = False,
                    past_limit: bool = None, stop_scope: str = None,
                    episode_seq: int = None):
    """Usage analytics with markup margin and customer/product/tag breakdowns.

    The #41 past-limit filters (past_limit / stop_scope / episode_seq)
    compose with every breakdown — e.g. past_limit=true totals exactly what
    was spent past a stop, in both denominations."""
    _product_check(request)
    tenant = request.auth.tenant
    # #78: computed reports are cursor-exempt but parameter-bounded.
    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error", "end_date must not precede start_date")
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    qs = Posting.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    qs = _apply_stop_context_filters(qs, past_limit, stop_scope, episode_seq)
    qs = _apply_task_filter(qs, tenant, task_id, include_subtasks)

    # EVERY MONEY TOTAL BELOW IS A PAIR, ON BOTH SIDES OF THE MARGIN (#327,
    # #351), and each breakdown row carries its OWN two counts: a provider whose
    # costs are all resolved is not made partial by another provider's that are
    # not, and the same holds of prices.
    totals = qs.aggregate(
        total_events=Count("id"),
        **cost_total_annotations(CUSTOMER_PRICE, key="total_billed_cost_micros"),
        **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
    )
    totals = carry_cost_total(SUPPLIER_COST, totals,
                              key="total_provider_cost_micros")
    totals = carry_cost_total(CUSTOMER_PRICE, totals,
                              key="total_billed_cost_micros")
    total_billed = totals["total_billed_cost_micros"]
    total_provider = totals["total_provider_cost_micros"]

    def _paired(grouped, *, billed_key):
        """Resolve each grouped row's TWO pairs. Every block goes through here,
        including the two below that build their own query.

        ``billed_key`` because the four blocks do not agree on what they call
        the billed total — three say `total_cost_micros` and the dimensional one
        says `total_billed_cost_micros` — and inventing a fifth spelling here to
        avoid the parameter would rename a published response property.
        """
        rows = [carry_cost_total(SUPPLIER_COST, row,
                                 key="total_provider_cost_micros")
                for row in grouped]
        return [carry_cost_total(CUSTOMER_PRICE, row, key=billed_key)
                for row in rows]

    def _rollup(column, *, skip_blank=False):
        """One breakdown block: group by `column`, largest billed first, every
        row carrying the count of what its own group excluded.

        Four blocks differed only in the column they group and whether an
        unattributed value is dropped, and the completeness pair would have been
        a fifth copy of the same four lines in each.
        """
        rows = qs.exclude(**{column: ""}) if skip_blank else qs
        return _paired(rows.values(column).annotate(
            event_count=Count("id"),
            **cost_total_annotations(CUSTOMER_PRICE, key="total_cost_micros"),
            **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
        ).order_by("-total_cost_micros"), billed_key="total_cost_micros")

    by_provider = _rollup("provider", skip_blank=True)
    by_event_type = _rollup("event_type", skip_blank=True)
    by_customer = _rollup("customer__external_id")
    by_task_type = _rollup("task_type", skip_blank=True)

    by_tag = []
    if tag_key:
        # SLICE 7 OWNS THIS SURFACE, and #273 left it exactly where it found
        # it: the keyed parameter, the response block and their spelling are
        # the analytics grouping vocabulary the ledger owns at slice 7, which
        # is what migrates the capability onto the declared grouping contract.
        # All that moved here is the column underneath, because the bag this
        # read folded into the survivor.
        by_tag = _paired(
            qs.filter(metadata__has_key=tag_key)
            .annotate(tag_value=KeyTextTransform(tag_key, "metadata"))
            .values("tag_value")
            .annotate(
                event_count=Count("id"),
                **cost_total_annotations(CUSTOMER_PRICE, key="total_cost_micros"),
                **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
            )
            .order_by("-total_cost_micros"),
            billed_key="total_cost_micros",
        )

    breakdowns: dict = {}
    if dimensions:
        if len(dimensions) > _MAX_BREAKDOWNS:
            raise Problem("validation_error",
                          f"at most {_MAX_BREAKDOWNS} dimensions")
        for dim in dimensions:
            col = _resolve_dimension(tenant, dim)
            # Run over the FULL qs (no exclusion) so every event is counted.
            # customer always has an external_id so no "(unattributed)" needed there.
            rows = _paired(
                qs.values(col)
                .annotate(
                    event_count=Count("id"),
                    **cost_total_annotations(SUPPLIER_COST, key="total_provider_cost_micros"),
                    **cost_total_annotations(CUSTOMER_PRICE,
                                             key="total_billed_cost_micros"),
                )
                .order_by("-total_billed_cost_micros"),
                billed_key="total_billed_cost_micros",
            )
            for r in rows:
                raw_val = r.pop(col)
                # Map empty string or None to the sentinel for non-customer cols
                if dim != "customer" and not raw_val:
                    raw_val = "(unattributed)"
                # The same property the DECLARED margin rollup publishes for the
                # same thing (`GroupingFieldMarginRow.grouping_field_value`),
                # taken from the one constant its sibling timeseries rollup also
                # writes so the two cannot drift. These rows are `list[dict]`,
                # so no schema holds the name and no drift or breaking gate can
                # see it change — `test_analytics_dimensions.py` asserts the
                # whole row instead.
                r[GROUPED_VALUE_KEY] = raw_val
            breakdowns[dim] = rows

    return 200, {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": total_billed,
        "total_provider_cost_micros": total_provider,
        UNRESOLVED_EVENT_COUNT_KEY: totals[UNRESOLVED_EVENT_COUNT_KEY],
        UNPRICED_EVENT_COUNT_KEY: totals[UNPRICED_EVENT_COUNT_KEY],
        # What UBB knows it charged minus what it knows it paid, bounded by BOTH
        # counts. An excluded cost makes this the largest the margin can be; an
        # excluded price makes it the smallest. Two facts, each stated once, and
        # the margin mints neither of them again.
        "usage_markup_margin_micros": total_billed - total_provider,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
        "by_customer": by_customer,
        "by_task_type": by_task_type,
        "by_tag": by_tag,
        "breakdowns": breakdowns,
    }


@metering_router.get("/analytics/usage/timeseries", response={200: UsageTimeseriesResponse, 422: ProblemOut})
@role_floor(READ)
def usage_timeseries(request, granularity: str = "day", start_date: date = None, end_date: date = None,
                     customer_id: UUIDIdentifier = None, group_by: str = None):
    """Time-series spend rollup: daily or hourly COGS per tenant/customer.

    start_date and end_date are both INCLUSIVE calendar dates, matching the
    /analytics/usage rollup so the same inputs cover the same window on both.
    """
    _product_check(request)
    if granularity not in ("hour", "day"):
        raise Problem("validation_error", "granularity must be hour or day")
    resolved_group_by = None
    if group_by is not None:
        resolved_group_by = _resolve_dimension(request.auth.tenant, group_by)
    # #78 bounds: hourly windows capped at ~92 days, daily at 366.
    if start_date and end_date:
        if end_date < start_date:
            raise Problem("validation_error", "end_date must not precede start_date")
        if granularity == "hour" and (end_date - start_date).days > 92:
            raise Problem("validation_error", "hourly window too large (max 92 days)")
        if granularity == "day" and (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem("validation_error", "date window must not exceed 366 days")
    from apps.metering.queries import get_usage_timeseries
    series = get_usage_timeseries(request.auth.tenant.id, granularity=granularity,
        customer_id=customer_id, group_by=resolved_group_by, start_date=start_date, end_date=end_date)
    return 200, {"granularity": granularity, "group_by": group_by or "", "series": series}


# --- Rate Cards ---

_billing_check = ProductAccess("billing")


def _refuse_an_immediate_change_to_an_override(book):
    """The three immediate routes do not reach a customer's own book (#361).

    An override is created, changed and retired through a PUBLISH — the same
    draft, the same diff, the same forward-dating, the same
    reversal-by-further-publish — and this is what makes that true of the whole
    surface rather than only of the two routes that declare one.

    ⚠ **WITHOUT IT THE CLAIM WOULD BE FALSE, AND THE PATH IS SHORT.** A book
    still has three immediate mutation surfaces beside the publish record —
    adding a rule, repricing a set of them, retiring one — every one of which
    takes a bare book id and is filtered by the tenant alone. A customer's own
    book is one of that tenant's books, so a negotiated deal could be written,
    repriced and retired with no record of who decided it or when it took
    effect. That is the one thing an override must never be: it is the record
    of a contract.

    The three leave with the rest of this slice's vocabulary (#369) and this
    refusal leaves with them.
    """
    if book.customer_id is not None:
        raise Problem(
            "validation_error",
            "this book holds one customer's own pricing rules, which are "
            "changed by a publish and never written directly. Declare an "
            "override at POST /pricing/customers/{customer_id}/overrides, "
            "withdraw one at DELETE "
            "/pricing/customers/{customer_id}/overrides/{override_id}, and "
            "reprice one through the book's own publish")


def _gate_card_type(request, card_type):
    _product_check(request)
    if card_type == "price":
        _billing_check(request)


def _resolve_card_currency(tenant, raw_currency):
    """CUR-1 rate-card currency pin: cards live in the tenant's currency.

    Omitted/empty currency defaults to the tenant's default_currency; an
    explicit value must match it case-insensitively. Returns the normalized
    lowercase currency, or raises ValueError (mapped to 422 by callers).
    """
    tenant_currency = (tenant.default_currency or "usd").lower()
    if not raw_currency:
        return tenant_currency
    card_currency = str(raw_currency).strip().lower()
    if card_currency != tenant_currency:
        raise ValueError(
            f"rate-card currency {card_currency!r} does not match tenant "
            f"currency {tenant_currency!r} (per-tenant single currency; "
            "multi-currency/FX is not supported)")
    return card_currency


@metering_router.get("/pricing/rate-cards", response=PaginatedBooks)
@role_floor(READ)
def list_books(request, card_type: str = None, cursor: str = None, limit: int = 50):
    """List the tenant's rate-card BOOKS (containers), newest first. Rates
    live under a book and are read via GET /pricing/rate-cards/{book_id}/rates."""
    _product_check(request)
    qs = RateCard.objects.filter(tenant=request.auth.tenant)
    if card_type:
        qs = qs.filter(card_type=card_type)
    return page(qs, cursor, limit, serialize=book_out)


@metering_router.post("/pricing/rate-cards",
                      response={200: BookOut, 409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.created")
def create_book(request, payload: BookIn):
    """Create a rate-card BOOK. Rates are added under it (so every API-created
    rate is book-scoped and therefore resolvable). Creates dedupe on natural
    identity (#78): a duplicate book answers 409."""
    _gate_card_type(request, payload.card_type)
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    if payload.card_type not in valid_types:
        raise Problem("validation_error",
                      f"card_type must be one of {sorted(valid_types)}")
    try:
        currency = _resolve_card_currency(request.auth.tenant, payload.currency)
    except ValueError as e:
        raise Problem("validation_error", str(e))
    try:
        with transaction.atomic():
            book = RateCard.objects.create(
                tenant=request.auth.tenant, card_type=payload.card_type,
                provider_key=payload.provider_key, key=payload.key, name=payload.name,
                currency=currency, is_default=payload.is_default)
            audit_record(
                action="rate_card.created",
                tenant_id=request.auth.tenant.id,
                resource_type="rate_card",
                resource_id=book.id,
                metadata={
                    "card_type": book.card_type,
                    "provider_key": book.provider_key,
                    "key": book.key,
                    "name": book.name,
                    "currency": book.currency,
                    "is_default": book.is_default,
                },
            )
    except IntegrityError:
        raise Problem("conflict", "a rate-card book with this identity already exists")
    return 200, book_out(book)


@metering_router.get("/pricing/rate-cards/{book_id}/rates",
                     response={200: PaginatedRates, 404: ProblemOut})
@role_floor(READ)
def list_book_rates(request, book_id: UUID, include_history: bool = False,
                    as_of: datetime = None, cursor: str = None, limit: int = 50):
    """List the rates in a book, newest first. Active-only by default;
    ``include_history`` returns every version (superseded rows carry a
    ``valid_to``), and ``as_of`` returns the version active at that instant
    (point-in-time)."""
    _product_check(request)
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    # The declaration is joined, not fetched per row: `rate_out` reads the
    # quantity's name off it since #326, and a page of fifty rates would
    # otherwise be fifty-one queries. A deactivated rate references nothing and
    # answers from its own column, which `select_related` handles without a
    # second path — it is a LEFT JOIN, not a filter.
    qs = Rate.objects.filter(
        tenant=request.auth.tenant, rate_card=book).select_related("measurement")
    if as_of is not None:
        qs = qs.filter(valid_from__lte=as_of).filter(
            Q(valid_to__isnull=True) | Q(valid_to__gt=as_of))
    elif not include_history:
        qs = qs.filter(valid_to__isnull=True)
    return 200, page(qs, cursor, limit, serialize=rate_out)


@metering_router.post("/pricing/rate-cards/{book_id}/rates",
                      response={200: RateOut, 404: ProblemOut,
                                409: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate.added")
def add_rate(request, book_id: UUID, payload: RateIn):
    """Add a rate to a book. card_type and currency are inherited from the book
    (single source of truth); tier/enum validation mirrors the old flat create.
    Creates dedupe on natural identity (#78): a duplicate rate answers 409."""
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    _refuse_an_immediate_change_to_an_override(book)
    if book.is_default and payload.provider != book.provider_key:
        raise Problem("validation_error",
                      f"rate provider {payload.provider!r} must match the "
                      f"default book's provider {book.provider_key!r}")
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.pricing_model not in valid_models:
        raise Problem("validation_error",
                      f"pricing_model must be one of {sorted(valid_models)}")
    # WHICH DECLARED QUANTITY THIS RATE PRICES, RESOLVED BEFORE ANYTHING IS
    # WRITTEN (#326). A name this tenant has not declared has no record to
    # reference, and a priced rule against a name nobody declared is the typo
    # this slice exists to make impossible — it matches nothing, costs nothing
    # and looks configured.
    #
    # The lookup is a pure read and every statement below it writes, which is
    # why it sits here rather than beside the create: a refusal placed under a
    # write spends what it refuses, and this route's writes are a rate and an
    # audit record.
    declaration = declaration_named(tenant=request.auth.tenant,
                                    measurement_key=payload.measurement_key)
    if declaration is None:
        raise Problem(
            "validation_error",
            f"no declared quantity is called {payload.measurement_key!r}. A "
            f"rate prices a quantity this tenant has declared on an Event "
            f"Type; declare it first, then price it.")
    try:
        with transaction.atomic():
            rate = Rate.objects.create(
                tenant=request.auth.tenant, rate_card=book, card_type=book.card_type,
                measurement=declaration, provider=payload.provider,
                event_type=payload.event_type, task_type=payload.task_type,
                subtask_type=payload.subtask_type,
                # Six published properties onto six of the ten columns (#276);
                # `SLOT_PROPERTY_COLUMNS` states why there are only six.
                **{column: getattr(payload, name)
                   for name, column in SLOT_PROPERTY_COLUMNS.items()},
                pricing_model=payload.pricing_model,
                rate_per_unit_micros=payload.rate_per_unit_micros,
                unit_quantity=payload.unit_quantity, fixed_micros=payload.fixed_micros,
                currency=book.currency,
                book_version_from=book.version)
            audit_record(
                action="rate.added",
                tenant_id=request.auth.tenant.id,
                resource_type="rate",
                resource_id=rate.id,
                # This key moved with the column (#275) and audit records
                # already written are NOT rewritten, on the same ground as the
                # pricing receipt: an audit row states what was done on a day,
                # and back-dating it to a vocabulary that did not exist then
                # would make it a worse record. Nothing queries this key — the
                # audit read path filters on `action` and `resource_type`, both
                # unchanged — so the split costs no reader a lookup.
                metadata={
                    "book_id": str(book.id),
                    "measurement_key": rate.measurement_key,
                    "pricing_model": rate.pricing_model,
                    "rate_per_unit_micros": rate.rate_per_unit_micros,
                    "currency": rate.currency,
                },
            )
    except IntegrityError:
        raise Problem("conflict", "a rate with this identity already exists")
    return 200, rate_out(rate)


@metering_router.post("/pricing/rate-cards/{book_id}/publish",
                      response={200: BookOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.published")
def publish_book(request, book_id: UUID, payload: PublishIn):
    """Atomically reprice a set of the book's rates: each change supersedes the
    matching active rate (same lineage, valid_to stamped) and opens a new
    version; the book version bumps once. All-or-nothing."""
    from apps.metering.pricing.services.book_service import BookService

    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
    _refuse_an_immediate_change_to_an_override(book)
    try:
        BookService.publish(book, [rate_change_body(c.dict(exclude_none=True))
                                   for c in payload.changes])
    except ValueError as e:
        raise Problem("validation_error", str(e))
    book.refresh_from_db()
    audit_record(
        action="rate_card.published",
        tenant_id=request.auth.tenant.id,
        resource_type="rate_card",
        resource_id=book.id,
        metadata={"version": book.version,
                  "change_count": len(payload.changes)},
    )
    return 200, book_out(book)


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
# ⚠ THE IMMEDIATE ROUTES ABOVE SURVIVE THIS COMMIT and still write rules with no
# publish record behind them. `POST .../rates`, `DELETE .../rates/{rate_id}` and
# `POST .../publish` are deleted by a later ticket together with the THREE
# retired action names they write, so that nothing here decrements a count. (The
# ticket names two of the three: the pair belonging to the add-rule and
# retire-rule routes. The publish route's own name is retired with them.) Until
# then a book has two ways to change and only one of them leaves a record.


def _book_publish_or_404(request, book_id, publish_id):
    return get_object_or_404(PricingBookPublish, id=publish_id,
                             book_id=book_id, tenant=request.auth.tenant)


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


@metering_router.post("/pricing/rate-cards/{book_id}/publishes",
                      response={200: BookPublishOut, 404: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit("pricing_book_publish.declared")
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

    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    _gate_card_type(request, book.card_type)
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
                action="pricing_book_publish.declared",
                tenant_id=request.auth.tenant.id,
                resource_type="pricing_book_publish",
                resource_id=record.id,
                metadata={"book_id": str(book.id),
                          "effective_at": record.effective_at.isoformat(),
                          "change_count": len(changes)},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.get("/pricing/rate-cards/{book_id}/publishes",
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
    _product_check(request)
    book = get_object_or_404(RateCard, id=book_id, tenant=request.auth.tenant)
    pending = PricingBookPublish.objects.filter(
        tenant=request.auth.tenant, book=book,
        declaration_status=DECLARATION_STATUS_DRAFT)
    return 200, page(pending, cursor, limit,
                     serialize=lambda record: _publish_response(request, record))


@metering_router.get("/pricing/rate-cards/{book_id}/publishes/{publish_id}",
                     response={200: BookPublishOut, 404: ProblemOut})
@role_floor(READ)
def get_book_publish(request, book_id: UUID, publish_id: UUID):
    """One change to a book, with its diff while it is still a draft."""
    _product_check(request)
    return 200, _publish_response(
        request, _book_publish_or_404(request, book_id, publish_id))


@metering_router.post(
    "/pricing/rate-cards/{book_id}/publishes/{publish_id}/publish",
    response={200: BookPublishOut, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("pricing_book_publish.published")
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
    _gate_card_type(request, record.book.card_type)
    try:
        with transaction.atomic():
            BookService.publish_declared(record, actor=get_current_actor())
            audit_record(
                action="pricing_book_publish.published",
                tenant_id=request.auth.tenant.id,
                resource_type="pricing_book_publish",
                resource_id=record.id,
                metadata={"book_id": str(book_id),
                          "effective_at": record.effective_at.isoformat(),
                          "opened": len(record.opened_rule_ids),
                          "closed": len(record.closed_rule_ids)},
            )
    except ValueError as e:
        raise Problem("validation_error", str(e))
    return 200, _publish_response(request, record)


@metering_router.delete(
    "/pricing/rate-cards/{book_id}/publishes/{publish_id}",
    response={200: StatusResponse, 404: ProblemOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("pricing_book_publish.discarded")
def discard_book_publish(request, book_id: UUID, publish_id: UUID):
    """Discard a draft, leaving the book exactly as it stood.

    A draft closed nothing, so this reopens nothing. A published record is
    refused: a publish that has already closed and opened rules is not an
    intention that can be withdrawn, and the act that undoes one is a further
    publish.
    """
    from apps.metering.pricing.services.book_service import BookService

    record = _book_publish_or_404(request, book_id, publish_id)
    _gate_card_type(request, record.book.card_type)
    try:
        with transaction.atomic():
            record_id = record.id
            BookService.discard(record)
            audit_record(
                action="pricing_book_publish.discarded",
                tenant_id=request.auth.tenant.id,
                resource_type="pricing_book_publish",
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
@records_audit("customer_pricing_override.declared")
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
    through `POST /pricing/rate-cards/{book_id}/publishes/{publish_id}/publish`
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

    _gate_card_type(request, "price")
    customer = get_object_or_404(Customer, id=customer_id,
                                 tenant=request.auth.tenant)
    slots = slot_map(request.auth.tenant.id)
    body = {**payload.dict(exclude={"effective_at"}), "kind": CHANGE_ADD}
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
                action="customer_pricing_override.declared",
                tenant_id=request.auth.tenant.id,
                resource_type="pricing_book_publish",
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
@records_audit("customer_pricing_override.withdrawn")
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

    _gate_card_type(request, "price")
    override = get_object_or_404(
        Rate.objects.select_related("rate_card", "measurement"),
        id=override_id, tenant=request.auth.tenant,
        rate_card__customer_id=customer_id)
    # The change is built from the rule's OWN columns rather than from a body,
    # so what is retired is the rule the caller addressed and nothing that
    # merely resembles it. `plan_changes` identifies a rule by the quantity it
    # prices plus its selectors, which is exactly what this reads back.
    change = {"kind": CHANGE_RETIRE,
              "measurement_key": override.measurement_key,
              **{name: getattr(override, name) for name in Rate.SELECTORS}}
    try:
        with transaction.atomic():
            record = BookService.declare(override.rate_card, [change],
                                         effective_at=effective_at)
            audit_record(
                action="customer_pricing_override.withdrawn",
                tenant_id=request.auth.tenant.id,
                resource_type="pricing_book_publish",
                resource_id=record.id,
                metadata={"customer_id": str(customer_id),
                          "book_id": str(override.rate_card_id),
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


@metering_router.post("/pricing/customers/{customer_id}/rate-card", response={200: dict, 404: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate_card.assigned")
def assign_book(request, customer_id: UUID, payload: AssignIn):
    """Assign a PRICE book to a customer (one per customer per currency).
    Resolution consults the assigned book before the per-provider default."""
    _billing_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    book = get_object_or_404(RateCard, id=payload.rate_card_id,
                             tenant=request.auth.tenant, card_type="price")
    with transaction.atomic():
        RateCardAssignment.objects.update_or_create(
            tenant=request.auth.tenant, customer=customer, currency=book.currency,
            defaults={"rate_card": book})
        audit_record(
            action="rate_card.assigned",
            tenant_id=request.auth.tenant.id,
            resource_type="rate_card",
            resource_id=book.id,
            metadata={"customer_id": str(customer.id),
                      "rate_card_id": str(book.id),
                      "currency": book.currency},
        )
    return 200, {"assigned": str(book.id)}


@metering_router.delete("/pricing/rate-cards/{book_id}/rates/{rate_id}",
                        response={200: StatusResponse, 404: ProblemOut,
                                  422: ProblemOut})
@role_floor(ADMIN)
@records_audit("rate.deleted")
def delete_rate(request, book_id: UUID, rate_id: UUID):
    """Retire (soft-expire) a single rate within its book. Addressed under its
    book — matching GET/POST /pricing/rate-cards/{book_id}/rates — so the path
    noun (``rates``) agrees with the identifier it takes (#86 sweep: this route
    previously took a rate id on a bare ``/pricing/rate-cards/{card_id}`` path).

    A rule in a book that holds one customer's own pricing is refused (422): an
    override is withdrawn through DELETE
    /pricing/customers/{customer_id}/overrides/{override_id}, which takes
    effect when its publish lands."""
    _product_check(request)
    rate = get_object_or_404(
        Rate.objects.select_related("rate_card"), id=rate_id,
        rate_card_id=book_id, tenant=request.auth.tenant,
        valid_to__isnull=True)
    _refuse_an_immediate_change_to_an_override(rate.rate_card)
    with transaction.atomic():
        rate.valid_to = timezone.now()
        rate.save(update_fields=["valid_to", "updated_at"])
        audit_record(
            action="rate.deleted",
            tenant_id=request.auth.tenant.id,
            resource_type="rate",
            resource_id=rate.id,
            metadata={"book_id": str(book_id),
                      "rate_id": str(rate.id),
                      "valid_to": rate.valid_to.isoformat()},
        )
    return {"status": "deleted"}


@metering_router.post("/pricing/resolution-runs",
                      response={200: ResolutionRunOut, 404: ProblemOut,
                                422: ProblemOut})
@role_floor(ADMIN)
@records_audit("resolution_run.executed")
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
    run completes is what today's markup rung and today's Event Type
    declarations resolve at that past instant.

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

    # ⚠ THE METERING GATE AND NOT THE BILLING ONE, WHICH IS A DECISION RATHER
    # THAN THE HABIT OF THE ROUTES AROUND THIS. The pricing routes beside it
    # gate on `billing` because writing a price rule is a billing act. A run is
    # not: it completes BOTH pairs, and one of them — a supplier cost UBB never
    # learned — is metering's own, owed to a metering-only tenant who never
    # charges anybody through UBB. Gating on billing would leave exactly that
    # tenant with no way to work through an unresolved-cost backlog at all,
    # which is the queue this mechanism exists to be. A tenant that does not
    # bill resolves no PRICE either way: their postings price to
    # `not_applicable`, which is not a completable status, so the wider gate
    # admits nothing extra rather than admitting something wrong.
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
            action="resolution_run.executed",
            tenant_id=request.auth.tenant.id,
            resource_type="resolution_run",
            resource_id=run.id,
            metadata={"selector": run.selector,
                      "postings_examined": run.postings_examined,
                      "costs_settled": run.costs_settled,
                      "prices_resolved": run.prices_resolved,
                      "more_to_do": run.more_to_do},
        )
    return 200, resolution_run_out(run)


@metering_router.put("/grouping-fields",
                     response={200: DimensionRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("grouping_field.declared")
def declare_grouping_fields(request, payload: DimensionRegistryIn):
    """Declare this tenant's slicing axes — the ONE vocabulary used by both
    analytics grouping and rate selection (design D1). Idempotent: re-PUTting
    an identical declaration is a no-op. `slot` and `scope` are immutable once
    bound and `max_cardinality` may only be raised (D8)."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_dimensions
    from apps.platform.grouping_fields.services import DimensionError, DimensionService

    tenant = request.auth.tenant
    try:
        with transaction.atomic():
            for d in payload.dimensions:
                DimensionService.declare(tenant, key=d.key, slot=d.slot, scope=d.scope,
                                         max_cardinality=d.max_cardinality)
            audit_record(
                action="grouping_field.declared",
                tenant_id=tenant.id,
                resource_type="dimension_registry",
                resource_id=tenant.id,
                metadata={"dimensions": [
                    {"key": d.key, "slot": d.slot, "scope": d.scope,
                     "max_cardinality": d.max_cardinality}
                    for d in payload.dimensions]},
            )
    except DimensionError as exc:
        raise Problem("validation_error", str(exc))
    return 200, {"dimensions": declared_dimensions(tenant.id)}


@metering_router.get("/grouping-fields", response=DimensionRegistryOut)
@role_floor(READ)
def list_grouping_fields(request):
    """This tenant's declared Grouping Field vocabulary."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import declared_dimensions
    return {"dimensions": declared_dimensions(request.auth.tenant.id)}


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


@metering_router.put("/task-types", response={200: TaskTypeRegistryOut, 422: ProblemOut})
@role_floor(ADMIN)
@records_audit("task_type.declared")
def declare_task_types(request, payload: TaskTypeRegistryIn):
    """Declare the tenant's work vocabulary and its per-kind COGS ceilings
    (design D7). Idempotent; the ceiling and required_dimensions may be updated
    on a re-PUT. Admin-floored: a task type's ceiling prices usage the same way
    markup.set/rate_card.* do, so it takes the write-default Admin floor rather
    than a Write carve-out."""
    _product_check(request)
    from apps.platform.grouping_fields.queries import slot_map
    from apps.platform.work.models import TaskType
    from apps.platform.work.queries import declared_task_types

    tenant = request.auth.tenant
    declared = set(slot_map(tenant.id))
    with transaction.atomic():
        for tt in payload.task_types:
            if tt.kind not in ("task", "subtask"):
                raise Problem("validation_error", f"invalid kind {tt.kind!r}")
            missing = [d for d in tt.required_dimensions if d not in declared]
            if missing:
                raise Problem("validation_error",
                              f"required_dimensions not declared: {missing}")
            TaskType.objects.update_or_create(
                tenant=tenant, key=tt.key, kind=tt.kind,
                defaults={
                    "default_provider_cost_limit_micros":
                        tt.default_provider_cost_limit_micros,
                    "required_dimensions": tt.required_dimensions,
                })
        audit_record(
            action="task_type.declared",
            tenant_id=tenant.id,
            resource_type="task_type_registry",
            resource_id=tenant.id,
            metadata={"task_types": [
                {"key": tt.key, "kind": tt.kind,
                 "default_provider_cost_limit_micros":
                     tt.default_provider_cost_limit_micros,
                 "required_dimensions": tt.required_dimensions}
                for tt in payload.task_types]},
        )
    return 200, {"task_types": declared_task_types(tenant.id)}


@metering_router.get("/task-types", response=TaskTypeRegistryOut)
@role_floor(READ)
def list_task_types(request):
    """The tenant's declared work vocabulary."""
    _product_check(request)
    from apps.platform.work.queries import declared_task_types
    return {"task_types": declared_task_types(request.auth.tenant.id)}
