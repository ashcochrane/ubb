from datetime import datetime
from uuid import UUID
from typing import Annotated, List, Literal, Optional

from ninja import Schema, Field
from pydantic import ConfigDict, field_validator, model_validator

from api.v1.pagination import Paginated
from apps.platform.event_types.models import REPORTED_COST_MAPPING
from apps.platform.grouping_fields.models import (
    SLOT_CHOICES, SLOT_MAX_LENGTH, SLOTS)
from core.exceptions import MisalignedAmount
from core.money import DEFAULT_CURRENCY, assert_aligned, minor_units
from core.vocabulary import RATE_STRUCTURE_PER_UNIT

#: WHAT A PRICING RECEIPT IS, ON THE PUBLISHED DOCUMENT (#349, ADR-0006).
#:
#: The qualification travels with the name wherever the name appears. Without
#: it a metering-only tenant reads "pricing receipt" as "UBB charged my
#: customer" — and files a support ticket about a charge nobody made.
#:
#: One constant on both schemas that publish the record, because two hand-typed
#: copies of a sentence whose whole job is to be the same sentence is two
#: sentences waiting to disagree.
RECEIPT_DESCRIPTION = (
    "The Pricing Receipt: the authoritative record of the ECONOMIC RESOLUTION "
    "behind this event's amounts — what UBB resolved, how, and as of when. It "
    "is not a guarantee that customer revenue exists and it is not evidence a "
    "customer was charged: a metering-only tenant has a receipt for every "
    "event it records. The record carries its own shape version "
    "(receipt_schema_version) and the version of the engine that computed it "
    "(pricing_engine_version), the subject it explains, a costing and a "
    "pricing section holding their method, status and detail BY VALUE, the "
    "totals, and a provenance section of cross-reference ids that nothing "
    "reads to reconstruct an amount."
)

# Envelope + serializer conventions (#115): every list endpoint answers a
# concrete ``Paginated[T]`` subclass — the subclass pins the OpenAPI component
# name (ninja silently overwrites duplicate schema names in the one document,
# #77's hazard, so every name below must stay unique). Each entity's row
# mapping lives in ONE named serializer function declared beside its Out
# schema; endpoints answer ``page(qs, cursor, limit, serialize=<it>)``.


def whole_minor_units(value, message=None):
    """Refuse inbound money that is not a whole minor unit of the currency.

    R3 §5.4 keeps the *inward* boundaries strict: unlike a computed invoice
    line, this is money Stripe will really move, and there is no later line to
    carry a remainder into.

    Request validation runs before any tenant is resolved, so it can only ask
    the platform's default currency. Admitting a second currency means moving
    this check to somewhere a tenant is in scope — the parameter on the
    ``core.money`` helpers is what makes that a move rather than an excavation.

    ``message`` overrides the rejection text: the widget surface (me_endpoints)
    words the same rule differently, and that wording is part of its answer.
    """
    try:
        assert_aligned(value, DEFAULT_CURRENCY)
    except MisalignedAmount:
        raise ValueError(message or (
            f"must be divisible by {minor_units(DEFAULT_CURRENCY):_} (whole cents)"
        )) from None
    return value


class PreCheckRequest(Schema):
    customer_id: UUID
    start_task: bool = False
    task_metadata: Optional[dict] = None
    external_task_id: str = ""
    # Registers a SUBTASK under this active top-level task (#38): a child
    # unit with its own limit whose spend rolls up into the parent's totals.
    # Only meaningful with start_task=True (ignored otherwise).
    parent_task_id: Optional[UUID] = None
    # COGS-denominated unit limit (what the job burns). Omitted/null = the
    # tenant default (RiskConfig.default_task_provider_cost_limit_micros, or
    # default_subtask_provider_cost_limit_micros when parent_task_id is set);
    # absent both, the unit is uncapped and no signal ever fires.
    provider_cost_limit_micros: Optional[int] = Field(default=None, gt=0)
    # The declared KIND of work (design D7). Resolves the server-side COGS
    # ceiling; a caller may request lower via provider_cost_limit_micros but
    # never higher.
    task_type: Optional[str] = Field(default=None, max_length=64)
    # Set instead of task_type when parent_task_id is present.
    subtask_type: Optional[str] = Field(default=None, max_length=64)
    # Declared grouping field values at task/subtask scope, inherited by every
    # event in the tree (design D6). Keys must be declared; values are
    # cardinality-capped on write.
    dimensions: dict = Field(default_factory=dict)


class PreCheckResponse(Schema):
    allowed: bool
    # reason vocabulary: insufficient_funds | account_closed |
    # customer_stopped | soft_floor_reached (#40 — past the wind-down line,
    # NEW top-level starts refuse; subtask starts under an active parent
    # pass) | rate_limit_exceeded | budget-cap reasons |
    # concurrency_limit | parent_task_not_active |
    # subtask_depth_exceeded (subtask registration refusals, #38 — refusing
    # work that hasn't happened, never a usage report).
    # A resolved COGS ceiling used to refuse here unless the tenant promised
    # full cost coverage; #321 deleted that verdict outright rather than
    # renaming it, because #320 made the promise unkeepable — an uncosted
    # event is now recorded with its cost unresolved, so the ceiling races a
    # floor rather than a total (#328 makes the floor say so).
    reason: Optional[str] = None
    balance_micros: Optional[int] = None
    task_id: Optional[str] = None
    # Set when the started unit is a subtask — the parent it registered under.
    parent_task_id: Optional[str] = None
    provider_cost_limit_micros: Optional[int] = None
    task_type: Optional[str] = None
    subtask_type: Optional[str] = None


#: What the caller's own cost figure MEANS, published on the wire rather than
#: kept in a comment here (#323, story 21).
#:
#: ONE WORDING, used by the request that carries the figure and the three
#: responses that publish it back. A generated client's user never reads this
#: module, and "never COGS" is the entire reason the figure has its own name
#: instead of sharing `provider_cost_micros` — #151 §9.1 chose the name
#: "precisely so it cannot be mistaken for canonical COGS", and a name is only
#: half of saying so. Four paraphrases would be four chances to soften it, so
#: the constant is shared and the sentence is stated once. It moved above the
#: request in #324, which is where the figure now enters.
CLAIMED_PROVIDER_COST_MEANING = (
    "What the caller believes this call cost. Diagnostic only, recorded as "
    "stated and never COGS: it is never rated, never summed into a cost "
    "total, and never becomes the supplier cost beside it. "
    "`provider_cost_micros` is the supplier's own reported figure and the "
    "only one UBB treats as cost."
)


#: THE ONE BODY KEY THIS REQUEST REFUSES RATHER THAN DROPS (#365). Spelled once,
#: here, so the validator below and the tests that pin it cannot drift apart.
A_PRICE_A_CALLER_MAY_NOT_STATE = "billed_cost_micros"


# ⚠ WHY THAT ONE KEY IS REFUSED AND EVERY OTHER UNKNOWN ONE IS STILL DROPPED
# (#365) — a COMMENT rather than a docstring, because a `Schema`'s docstring is
# exported verbatim into `openapi/v1.json` and the generated SDK, and this is a
# note to the next author.
#
# The customer price used to arrive on this request, and this commit deletes it:
# a price is a commercial decision UBB resolves and holds, stated once as a rule
# rather than pasted onto every call. Deleting the field alone would not have
# made that true, because Django Ninja DROPS a body key no schema names rather
# than refusing it — so a client still sending its own prices would keep getting
# `200` and would read agreement into a route that discards the number. That is
# the one population this deletion has to reach, so the refusal below is what
# makes *there is no request-side path to a price* a fact rather than a claim
# about this file.
#
# ⚠ AND `extra="forbid"` IS THE WRONG INSTRUMENT FOR IT, WHICH WAS MEASURED
# RATHER THAN REASONED. It is the general form — refuse everything unpublished —
# and it was written here first, on the argument that a list of forbidden
# spellings says nothing about the next spelling somebody picks. The suite
# answered with 64 failures, and three of them name the reason: *a stale client
# still sending the retired field is accepted*, *the retired key is ignored
# rather than refused*, *a stale caller is accepted and its labels are dropped*.
# Dropping an unknown key is RATIFIED POSTURE here, argued in #272 and pinned
# ever since — this re-model renames wire fields in every slice, and a caller
# mid-migration must not be broken by each one in turn. The general rule would
# have reversed that for every retired key at once, which is a slice-wide policy
# change no ticket owns. So the refusal names its one subject.
#
# It is therefore a TOMBSTONE, with the cost tombstones have: it is a list of
# one spelling, and it only answers for the name it holds. That is the trade
# taken deliberately — the alternative was not "a stronger rule" but "a
# different rule about other people's fields". It is also temporary: it exists
# so this deletion is loud while the re-model is in flight, and the cutover
# (slice 8) is where a key nothing has sent for eight slices stops needing a
# headstone.
class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    # THE ONE OPEN BAG (#273). Free-form labelling: filterable and readable,
    # never grouped, never priced, never unit attribution. Anything you want to
    # slice or price on is a declared `dimensions` key. The second bag that
    # used to sit further down this schema folded into this one, and its name
    # went with it — it advertised a grouping capability this bag deliberately
    # does not have. Keys are yours: UBB stores and returns them as authored.
    metadata: dict = Field(default_factory=dict)
    # THE SUPPLIER'S OWN REPORTED COST, and the only figure here UBB treats as
    # COGS. Admissible only where the Event Type declares that it arrives on
    # the call — `metering_endpoints.admit_supplier_cost` owns that rule and
    # refuses everything else with a 422 rather than dropping it (#324).
    provider_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
    # WHAT THE CALLER BELIEVES THE CALL COST, on its own field so it can be
    # accepted anywhere without ever being read as the number above. The
    # meaning is published rather than kept in this comment: the same sentence
    # the three responses carry, so no reader meets two wordings of it.
    #
    # The bound is the one the supplier cost beside it carries. The three
    # `amount_micros` fields further down this module — `DebitRequest`,
    # `CreditRequest`, `CreateGrantRequest` — share the LITERAL and not the
    # rule: a wallet movement of nothing is refused, while a call that
    # genuinely cost nothing is an ordinary resolved amount. So the two are
    # deliberately not folded into one constant.
    claimed_provider_cost_micros: Optional[int] = Field(
        default=None, ge=0, le=999_999_999_999,
        description=CLAIMED_PROVIDER_COST_MEANING)
    # The measured quantities, keyed by the codes declared beneath this event's
    # Event Type (#274). The name is the declarations' own: a quantity is
    # costable exactly when a declaration matches its key, and one that matches
    # nothing is still accepted here and still contributes nothing to the
    # amounts below — slice 3 owns making that visible rather than silent.
    measurements: Optional[dict[str, int]] = None

    @field_validator("measurements")
    @classmethod
    def measurement_values_nonnegative(cls, v):
        """The only validation this bag has ever carried, moved unchanged.

        Not tightened, deliberately: refusing a key no declaration matches is
        slice 3's, which owns every behaviour a declaration selects. Anything
        this refused before it was renamed it still refuses, and nothing more —
        `usage/tests/test_negative_quantity_rejection.py` states both halves.

        The PREDICATE is what moved unchanged. The message had to be rewritten
        because it names the field, and its second noun moved with it rather
        than being left spelling the retired word for the one ticket between
        this rename and the one that clears that word from the backend.
        """
        if v is None:
            return v
        negative = [k for k, val in v.items() if val < 0]
        if negative:
            raise ValueError(
                f"measurements values must be >= 0; negative quantities: {negative}")
        return v
    currency: Optional[str] = Field(default=None, max_length=3)
    task_id: Optional[UUID] = None
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
    # Declared EVENT-scoped grouping field values (design D1/D6). Keys must be in the
    # tenant's GroupingField registry and declared at event scope; task- and
    # subtask-scoped values are set at the start-gate and inherited, not sent
    # here. Values are cardinality-capped on write.
    dimensions: dict = Field(default_factory=dict)
    # When the usage economically happened. Must be timezone-aware; bounded by
    # the tenant's backfill window. Omitted = now (server clock).
    effective_at: Optional[datetime] = None

    @model_validator(mode="before")
    @classmethod
    def refuse_a_caller_supplied_customer_price(cls, body):
        """The one key this request refuses instead of dropping — see the block
        above the class for why it is one key and not every unpublished one.

        The MESSAGE is most of the point. A 422 saying only "no" would leave an
        integrator with a call that used to work, a field that has vanished, and
        nowhere to go; this one names where a price comes from now and which
        cost fields they may still send.

        ⚠ A `mode="before"` VALIDATOR ON A NINJA `Schema` IS NOT HANDED A DICT.
        `Schema` carries its own `mode="wrap"` root validator that replaces the
        incoming value with a `DjangoGetter` — the adapter that lets a response
        schema read attributes off an ORM object — so this runs against that
        wrapper and an `isinstance(body, dict)` guard is DEAD. The first draft
        had exactly that guard, and the refusal never fired once: every body
        carrying the key answered `200`, which is the silence this validator
        exists to end, produced by the code meant to end it. Its own test is
        what found it. Unwrap `_obj`, and keep the plain-dict path for a caller
        that builds the model directly.
        """
        body = getattr(body, "_obj", body)
        if isinstance(body, dict) and A_PRICE_A_CALLER_MAY_NOT_STATE in body:
            raise ValueError(
                f"{A_PRICE_A_CALLER_MAY_NOT_STATE} is no longer accepted on a "
                f"usage event. What you charge a customer is resolved by UBB "
                f"from the pricing rules you configure and is returned on this "
                f"response, rather than stated on the call — configure a price "
                f"rule for the quantity this event measures. The supplier's "
                f"own cost is still yours to report: provider_cost_micros "
                f"where your Event Type declares it arrives on the call, or "
                f"claimed_provider_cost_micros anywhere.")
        return body


class UsageBatchRequest(Schema):
    events: list[RecordUsageRequest] = Field(min_length=1, max_length=100)


class UsageBatchResponse(Schema):
    # Per-item VERDICTS — the field set #78 unified across this route and the
    # async ingest route, which slice 1 deleted; this is the surviving shape.
    # Positionally aligned with the request's events[]. Success items mirror
    # the single-call success body plus {"accepted": true}; rejected items are
    # {"accepted": false, "code", "detail", "stop": false, "stop_reason":
    # null, "stop_scope": null} with `code` from the registry.
    results: list[dict]
    accepted: int
    rejected: int


#: Whether the supplier cost beside it is settled (#317). `closed` — UBB owns
#: all three — so the export writes a real `enum` here, and this file spells
#: none of the values. The same marker mechanism as the block near the foot of
#: this module; declared here because its first user is the next schema down.
#:
#: IT TRAVELS WITH THE AMOUNT, ON EVERY RESPONSE THAT CARRIES ONE. A cost of
#: zero and a cost UBB has not learned yet are now two different facts in the
#: table, and a response that published the number without this would hand a
#: client back the exact ambiguity the column stopped having — read as money,
#: both say "nothing", and only one of them means it.
#:
#: STORED, NOT DERIVED, which is where it differs from `MeasurementsStatus`
#: below: a column holds it, because resolving a cost has to move the status
#: and the amount in one `UPDATE`.
#:
#: The marker lands in the same commit that made the backend consumer serve the
#: concept, and that is forced: the moment `usage/models.py` holds all three
#: values by reference, the known-value document advertises them, and a concept
#: advertised with no field naming it is what
#: `test_every_advertised_concept_reaches_the_contract` refuses.
#:
#: ONE OTHER ROUTE WOULD ALSO HAVE GONE GREEN, and it is named here so nobody
#: has to rediscover it and wonder whether it was missed: WITHDRAWING the
#: registry's `openapi` consumer would drop the representation to none and take
#: the concept out of the owed set entirely. It was rejected on two counts. It
#: would make the registry state that this concept is not in the contract while
#: the whole slice is building it — and the migration ledger only ever shrinks
#: (#155 §3.2), so the entry deleted along with it could not be put back
#: without a seeding authorisation. Withdrawing a declaration to quiet a gate
#: is the shape `gates/README.md` spends four pages refusing.
#:
#: The rest of what these responses owed — the amount admitting its own absent
#: case, the caller's claimed figure, the unresolved reason's own metadata — is
#: paid: #320 widened the last of the three amounts, and #323 published the
#: reason and the claimed figure, both declared immediately below.
CostingStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "costing_status"})]


#: WHICH input did not arrive, when the status above says `unresolved` (#323).
#: `closed` — UBB owns all three — so the export writes a real `enum` here and
#: this file spells none of the values.
#:
#: NULLABLE, WHICH IS WHY ITS MARKER SITS WHERE IT DOES. Every field using this
#: is `Optional`, so django-ninja renders `anyOf: [string, null]` and the marker
#: travels into the string member — `EventTypeUpdateIn.costing_method` is the
#: standing precedent. That placement is load-bearing rather than incidental:
#: `enum` and `anyOf` at ONE node are conjunctive, so a marker on the union
#: itself would publish a document under which `null` is invalid, while the
#: server returns `null` for every settled posting. The wire body would be
#: unchanged and the export clean, so nothing but
#: `test_the_cost_reaches_the_contract.py` would see it.
#:
#: NO HAND-WRITTEN `description`, DELIBERATELY, and this is where it differs
#: from the claim below. The registry owns this concept's summary and generates
#: its values; a sentence restating either here would be a second copy that can
#: drift with nothing to catch it — no gate reads prose. The claimed figure has
#: no registry entry to own it (it is an amount, not a value set), so the
#: schema is the only place its meaning can live, and it says so there.
UnresolvedReason = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "unresolved_reason"})]


#: WHETHER A CUSTOMER PRICE IS SETTLED, AND IF NOT, WHY NOT (#351). `closed` —
#: UBB owns all four — so the export writes a real `enum` here and this file
#: spells none of the values.
#:
#: Never `Optional` on any response, so its marker sits on a plain string. That
#: is not an oversight to be corrected later: `unknown` IS the status for a
#: price UBB does not have, and a nullable status column would be a fifth state
#: meaning "nobody said".
PricingStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "pricing_status"})]


#: WHY A SUBJECT GENERATES NO CUSTOMER REVENUE AT THIS LEVEL (#351). Read only
#: where the status above is `not_applicable`.
#:
#: NULLABLE, WHICH IS WHY ITS MARKER SITS WHERE IT DOES — the argument
#: `UnresolvedReason` above makes in full, and the trap this slice was warned
#: about by name. Every field using this is `Optional`, so django-ninja renders
#: `anyOf: [string, null]` and the marker travels into the STRING MEMBER. A
#: marker on the union node itself would publish a document under which `null`
#: is invalid, while the server returns `null` for every priced posting: `enum`
#: and `anyOf` at ONE node are read conjunctively. The wire body would be
#: unchanged and the export clean, so nothing but
#: `test_openapi_known_values.py`'s placement check would see it.
#:
#: NO HAND-WRITTEN `description`, for the reason `UnresolvedReason` gives: the
#: registry owns this concept's summary and generates its values, and a
#: sentence restating either here would be a second copy no gate reads.
NotApplicableReason = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "not_applicable_reason"})]


#: HOW A CUSTOMER PRICE WAS DERIVED (#355, #147 §2). `closed` — UBB owns both
#: values — so the export writes a real `enum` here and this file spells
#: neither of them.
#:
#: NULLABLE, WHICH IS WHY ITS MARKER SITS WHERE IT DOES — the argument
#: `UnresolvedReason` makes in full, and the second half of the trap this slice
#: was warned about by name. `Optional[PricingMethod]` renders
#: `anyOf: [string, null]` with the marker inside the STRING MEMBER; a marker on
#: the union node would publish a document under which `null` is invalid while
#: the server returns `null` for every price it did not derive, because `enum`
#: and `anyOf` at ONE node are read conjunctively.
#:
#: NULL IS NOT A THIRD METHOD. It says the price was not derived, and
#: `pricing_status` beside it says which of the two reasons applied. The
#: argument for that shape is made once, where the rule's own column is
#: declared (`apps/metering/pricing/models.py`).
#:
#: NO HAND-WRITTEN `description`, for the reason `UnresolvedReason` gives: the
#: registry owns this concept's summary and generates its values, and a sentence
#: restating either here would be a second copy no gate reads.
PricingMethod = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "pricing_method"})]

#: WHICH ARITHMETIC A RULE RUNS (#366, #151 §13.2). `closed` — UBB owns both
#: values — so the export writes a real `enum` here and this file spells
#: neither of them.
#:
#: NOT THE SAME FACT AS `PricingMethod` ABOVE, and the two used to sit one
#: character apart on the model, which is the collision ADR-0006 §3 names as its
#: own worked example. HOW A PRICE IS DERIVED (a margin over what the call cost,
#: or a price of its own) versus HOW THE ARITHMETIC RUNS (so much per unit of
#: quantity, or a component that applies once regardless). A schema carrying one
#: says nothing about the other.
#:
#: **IT IS NON-NULL ON EVERY ROW SCHEMA AND NULLABLE ON EVERY CHANGE BODY**,
#: and that is the difference between opening a rule and repricing one rather
#: than an inconsistency: every rule HAS a shape, so a row always answers with
#: one, while a change states only what moves and null there means *carry the
#: superseded rule's over*. ⚠ The one body that was non-null — the immediate
#: add-a-rule request — left with its route in #367, so the split is now
#: exactly rows-versus-changes with no exception to remember.
#: `Optional[RateStructure]` renders `anyOf: [string,
#: null]` with the marker inside the STRING MEMBER — the rule
#: `UnresolvedReason` argues in full, and the trap this slice was warned about
#: by name.
#:
#: NO HAND-WRITTEN `description`: the registry owns this concept's summary and
#: generates its values, and a sentence restating either here would be a second
#: copy no gate reads.
RateStructure = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "rate_structure"})]


class RecordUsageResponse(Schema):
    event_id: str
    new_balance_micros: Optional[int] = None
    suspended: bool
    provider_cost_micros: Optional[int] = None
    # Whether the number above is settled. See `CostingStatus`: without it a
    # supplier cost of zero and one UBB has not learned yet are the same
    # answer on the wire.
    costing_status: CostingStatus
    # WHICH input did not arrive, when the status says `unresolved`. Null
    # otherwise — a settled cost has no missing input to name. It travels
    # everywhere the status does, because a status that says a cost is missing
    # without saying what would settle it leaves the reader nothing to do.
    unresolved_reason: Optional[UnresolvedReason] = None
    # WHAT THE CALLER SENT, HANDED STRAIGHT BACK. #323 published this field
    # here while nothing could put a value in it; #324 gave the recording
    # request the field that does, so an ack now echoes the caller's own
    # figure beside the supplier's and the two are visibly different numbers.
    claimed_provider_cost_micros: Optional[int] = Field(
        default=None, description=CLAIMED_PROVIDER_COST_MEANING)
    billed_cost_micros: Optional[int] = None
    # Whether the number above is settled (#351). See `PricingStatus`: without
    # it a customer price of zero and one UBB could not resolve are the same
    # answer on the wire — the ack's own version of the defect the supplier
    # half fixed one slice ago.
    pricing_status: PricingStatus
    # WHICH OF TWO MUTUALLY EXCLUSIVE CAUSES produced `not_applicable`. Null
    # otherwise — the other three statuses have no cause to name.
    not_applicable_reason: Optional[NotApplicableReason] = None
    task_id: Optional[str] = None
    # Set when the named unit is a subtask — its parent task (#38).
    parent_task_id: Optional[str] = None
    # The named unit's running totals, denominationally explicit — billed
    # (what you charge) and provider (what the job burns; only this one races
    # the COGS limit). A subtask's spend also rolls up into its parent's
    # totals (containment); the parent's totals ride its own acks/events.
    task_total_billed_cost_micros: Optional[int] = None
    task_total_provider_cost_micros: Optional[int] = None
    # How many of the unit's events that provider total could not include
    # (#328). `costing_status` above says whether THIS event's cost is one of
    # them; this says how many the running total has already left out, which is
    # the number a caller watching its own spend against a limit needs. Null
    # exactly when the totals beside it are — no named unit, nothing to total.
    task_total_unresolved_event_count: Optional[int] = None
    # And how many the BILLED total could not include (#351). Two counts and
    # not one: a caller watching spend against a limit is watching the provider
    # total, while a caller reconciling what it will be charged is watching the
    # billed one, and the same event need not be missing from both.
    task_total_unpriced_event_count: Optional[int] = None
    # One-rule stop verdict on a 200 body — the event was ALWAYS recorded +
    # charged; `stop` means "stop sending work for the named scope". The
    # scalar slot carries one verdict: a unit-scoped crossing wins over a
    # simultaneous customer-wide stop, and among unit verdicts the WIDEST
    # tripped scope wins (a parent trip beats a subtask trip — stop the whole
    # tree); the losers surface on the next ack and via the pushed events.
    # stop_reason ∈ task_limit | subtask_limit |
    # task_not_active | customer_wide_stop; stop_scope ∈ task | subtask |
    # customer. On a subtask's ack, scope `task` names the PARENT
    # (parent_task_id above) — the whole tree is stopped, not just the named
    # unit. `suspended` stays the durable owner status.
    stop: bool = False
    stop_reason: Optional[str] = None
    stop_scope: Optional[str] = None
    # The itemized past-limit story (#41, spec §H): null when the event
    # landed past nothing, else the event's immutable stop-context ARRAY —
    # one entry per limit it landed past (a simultaneous task-limit +
    # customer-wide-stop crossing carries both, nothing lost). Each entry:
    # {limit, stop_scope, tripped_at, episode_seq, task_id, subtask_id,
    # arrived_after} — arrived_after=false marks the tipping event.
    stop_context: Optional[list] = None
    # The quantities as recorded — see `RecordUsageRequest.measurements` (#274).
    measurements: Optional[dict] = None
    pricing_provenance: Optional[dict] = Field(
        None, description=RECEIPT_DESCRIPTION)
    # WHICH declared quantities went uncosted — the status above says THAT the
    # cost is unresolved, and this says which declaration to fix. Both, because
    # neither answers the other's question (#320).
    #
    # It took the canonical word for a declared quantity here rather than in a
    # later break: the response was already breaking in this commit, no ledger
    # entry owned the old spelling (it survived the forbidden-term sweep only
    # because plurals are invisible to token matching), and keeping the old key
    # beside the new status would have been two encodings of "we could not cost
    # this" — which ADR-0007 §3 refuses in a response that is already breaking.
    uncosted_measurement_keys: list[str] = []
    # HOW THE CUSTOMER PRICE ABOVE WAS DERIVED, lifted out of the receipt this
    # response already carries (#355). Null means it was not derived, and
    # `pricing_status` above says which of the two reasons applied.
    #
    # ⚠ ON THIS RESPONSE BECAUSE THE RECORD IS ON THIS RESPONSE, which is the
    # whole rule — see `UsageEventDetailOut.pricing_method`. The value was
    # already crossing here inside `pricing_provenance`, untyped and therefore
    # advertised nowhere; publishing it typed is what puts the agreed value set
    # in front of a consumer that switches on it. An acknowledgement that
    # carried the record but not the vocabulary for what is in it would be the
    # unmarked-closed-concept shape one level out.
    pricing_method: Optional[PricingMethod] = None
    # The posting's grouping values, keyed by the tenant's own declared key
    # (#277) — see `UsageEventDetailOut.grouping_fields`, which is the same
    # object. Inherited values are included: task- and subtask-scoped values are
    # set at the start gate and never travel with the event (D6), so this is
    # where a caller sees what its posting was attributed to without a second
    # call.
    grouping_fields: dict[str, str] = {}


class BalanceResponse(Schema):
    balance_micros: int
    currency: str
    # F4.3 (additive): grant visibility. None when the wallet has no grants
    # context (kept optional for response back-compat).
    promo_micros: Optional[int] = None
    expiring_micros: Optional[int] = None
    next_expiry_at: Optional[str] = None
    # Negative-balance visibility (#41, pin 10): when the balance last
    # crossed ≥0 → <0; null whenever the balance is ≥ 0. Observational only —
    # UBB never acts on it (no reminders, no auto-close; collections stay
    # between the tenant, their customer, and Stripe).
    negative_since: Optional[str] = None
    # Pooled-seat disclosure (Task 3): the resolved billing owner — equals
    # this customer's own id/external_id when not a pooled seat.
    billing_owner_id: UUID
    billing_owner_external_id: str
    is_pooled_seat: bool


class UsageEventOut(Schema):
    id: UUID
    request_id: str
    event_type: str = ""
    provider: str = ""
    provider_cost_micros: Optional[int] = None
    # On the lean list row too, and that is the point rather than symmetry: a
    # list is where a reader totals a column by eye, so this is exactly where
    # an unknown cost reading as zero would be believed.
    costing_status: CostingStatus
    # And so is the reason, for the same argument one step on: a list of rows
    # reading `unresolved` with no cause is a column of shrugs. This is the
    # surface a tenant works THROUGH — the remedy is readable from the value,
    # so the list is where it saves a call rather than prompting one.
    unresolved_reason: Optional[UnresolvedReason] = None
    # The third field this row carries on one argument rather than on
    # leanness, after the status (#317) and the cause above it: this is where
    # a reader totals a column by eye. A claim published only on the detail
    # view would be a number invisible exactly where a supplier cost is
    # missing and a plausible-looking figure would be reached for.
    claimed_provider_cost_micros: Optional[int] = Field(
        default=None, description=CLAIMED_PROVIDER_COST_MEANING)
    billed_cost_micros: Optional[int] = None
    # On the lean list row for the same argument the cost half makes above it:
    # a list is where a reader totals a column by eye, so this is exactly where
    # a price UBB could not resolve reading as zero would be believed (#351).
    pricing_status: PricingStatus
    not_applicable_reason: Optional[NotApplicableReason] = None
    metadata: dict
    effective_at: str
    # #41: the immutable past-limit context array (see RecordUsageResponse).
    stop_context: Optional[list] = None


def usage_event_out(e):
    """UsageEventOut's serializer — the lean list row (the full pricing
    receipt is the detail view's, GET /usage/{event_id})."""
    return {
        "id": e.id,
        "request_id": e.request_id,
        "event_type": e.event_type,
        "provider": e.provider,
        "provider_cost_micros": e.provider_cost_micros,
        "costing_status": e.costing_status,
        "unresolved_reason": e.unresolved_reason,
        "claimed_provider_cost_micros": e.claimed_provider_cost_micros,
        "billed_cost_micros": e.billed_cost_micros,
        "pricing_status": e.pricing_status,
        "not_applicable_reason": e.not_applicable_reason,
        "metadata": e.metadata,
        "effective_at": e.effective_at.isoformat(),
        "stop_context": e.stop_context,
    }


#: Whether a posting's measured quantities can still be read (#271, §E5).
#: `closed` — UBB owns all three — so the export writes a real `enum` here from
#: `openapi/known-values.json`, and this file spells none of the values. The
#: same marker mechanism as the block near the foot of this module; declared
#: beside its one user rather than with them because it is the only one that
#: belongs to a schema this far up the file.
#:
#: DERIVED AND SERVED, NEVER STORED. The serialiser computes it; no column
#: holds it, and G10 is what proves so (ADR-0006 §4).
MeasurementsStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "measurements_status"})]


class UsageEventDetailOut(Schema):
    # Full pricing receipt for one event — the audit lookup. pricing_provenance
    # is the recorded "why this amount", omitted from the lean list view: the
    # two versions, the typed subject, the costing and pricing sections by
    # value, the totals and the cross-reference ids (#349).
    id: UUID
    request_id: str
    idempotency_key: str
    event_type: str = ""
    provider: str = ""
    # The posting's grouping values, keyed by the tenant's OWN declared key,
    # with unset slots omitted (#277, §G4):
    #
    #     {"region": "eu-west-1", "model_variant": "flash-4.0-standard"}
    #
    # Three of the physical slots used to be published individually, under the
    # slot's name. The slot is UBB's identity for the binding and not the
    # tenant's — nobody chose "slot four" — so this object is keyed by the word
    # the tenant declared, which makes the response self-describing and makes
    # how many slots exist a question the contract never answers. #276 widened
    # six slots to ten; under this shape that was not a contract change, and
    # neither is the next one.
    #
    # Same flat `{key: value}` shape the write side takes, so the round trip
    # needs no translation. Typed tighter than the write side on purpose: a
    # declared value is admitted through `str()` and stored in a `CharField`, so
    # a string is the only thing this can ever answer, and saying so is what
    # gives a generated client a real type instead of `any`.
    grouping_fields: dict[str, str] = {}
    currency: str = "usd"
    # `None` means UBB does not know what the supplier charged — never that the
    # call was free. Zero is a resolved amount and reads as zero.
    #
    # ⚠ WIDENED BY #320 RATHER THAN BY #323, WHICH OWNED THE REST OF THIS.
    # #317 recorded the gap here and left it: the amount was required and
    # non-nullable while `costing_status` could already say `unresolved`, which
    # is a response this schema could not serialise. That was safe only while
    # nothing wrote `unresolved`, and #320's compute spine is what started
    # writing it — so the half that would 500 was paid in the commit that made
    # it reachable, exactly as #317 paid its own contract half early when the
    # consumer census forced one.
    #
    # THIS WAS THE ONLY ONE OF THE THREE THAT NEEDED WIDENING, and the reason
    # the other two did not is worth keeping: they have been `Optional` since
    # long before slice 3, while the COLUMN behind them was non-nullable with a
    # default of zero. Their nullability was decorative — no posting could
    # produce a null to put through it. So the absent case became EXPRESSIBLE
    # in #317, which made the column nullable, and REACHABLE in #320, which
    # taught the spine to leave it unset; on those two schemas the contract had
    # been ready for years and was waiting on the table. That is why #323 —
    # nominally the ticket that owns AC 1 — edits no amount at all, and why
    # `test_the_cost_reaches_the_contract.py` asserts the property over all
    # three rather than trusting a claim spread across two earlier commits.
    # What #323 does add is the two fields below.
    provider_cost_micros: Optional[int] = None
    # Whether the number above is settled. Typed required, like the status
    # below it and for the same reason: every posting has an answer.
    costing_status: CostingStatus
    # The audit lookup is where an unresolved cost gets investigated, so the
    # cause belongs on it — see `UnresolvedReason`. Null on a settled posting.
    unresolved_reason: Optional[UnresolvedReason] = None
    # The caller's own figure, on the receipt where a dispute is settled. This
    # is the response the field matters most on: the two numbers are read
    # side by side here, which is exactly the comparison story 20 asks for and
    # exactly the confusion story 21 refuses.
    claimed_provider_cost_micros: Optional[int] = Field(
        default=None, description=CLAIMED_PROVIDER_COST_MEANING)
    # ⚠ WIDENED BY #351, AND IT IS THE PRICE HALF OF THE PARAGRAPH ABOVE. This
    # was the last of the four amounts on this schema still typed non-nullable,
    # on the argument the comment above records: the column behind it could not
    # produce a null. It can now, and the absent case became EXPRESSIBLE and
    # REACHABLE in the same commit rather than two — because unlike #317 this
    # slice lands the column, the status and every reader together, so there is
    # no window in which the schema could not serialise a row the table admits.
    billed_cost_micros: Optional[int] = None
    # Whether the number above is settled. Typed required, like the costing
    # status above it and for the same reason: every posting has an answer.
    pricing_status: PricingStatus
    # The audit lookup is where a price that does not apply gets investigated,
    # so the cause belongs on it. Null on any other status.
    not_applicable_reason: Optional[NotApplicableReason] = None
    # HOW THE PRICE ABOVE WAS DERIVED, read off the receipt and published beside
    # the status that qualifies it (#355). Null means it was NOT derived, and
    # the status says which of the two reasons applied.
    #
    # THE RULE FOR WHERE THIS SITS IS "WHEREVER THE RECEIPT DOES", and it is
    # mechanical rather than a judgement call: this value is INSIDE the record
    # `pricing_provenance` publishes, which is untyped, so on every response
    # carrying that record the method is already on the wire with no schema
    # saying what it may be. Lifting it into a typed field is what lets the
    # contract advertise the agreed value set for it, and leaving one of those
    # responses out would leave the same closed concept unadvertised there.
    # Exactly two responses publish the record — this one and the recording
    # ack — and `test_openapi_known_values.py` pins that pair.
    #
    # The two surfaces that DO publish a price and do NOT get this are ruled out
    # by the same sentence: the list row omits the receipt to stay lean, so it
    # holds no record to read from; and the `usage.recorded` payload carries no
    # receipt either, its readers being accumulators asking whether an amount
    # may be included rather than how it was reached.
    #
    # DERIVED AT THE SERIALISER, LIKE THE STATUS BELOW IT AND UNLIKE THE ONE
    # ABOVE. No column on a posting holds it: what holds it is the receipt, and
    # reading it back through the receipts module is what keeps the answer the
    # one that was recorded rather than one recomputed against today's rules —
    # which is the whole of what the receipt is for.
    pricing_method: Optional[PricingMethod] = None
    # The quantities this posting was measured by, keyed by declared code
    # (#274) — the field the status below has always been about.
    measurements: dict = {}
    # What the bag above MEANS when it is empty — pruned, never applicable, or
    # genuinely there and empty. Without it an expired payload and a synthetic
    # charge are one indistinguishable `{}`, and a reader that defaults on an
    # empty bag shows an end customer "no usage" for detail that was removed on
    # schedule. Required rather than optional: every posting has an answer.
    measurements_status: MeasurementsStatus
    pricing_provenance: dict = Field({}, description=RECEIPT_DESCRIPTION)
    # The one open bag (#273) — see `RecordUsageRequest.metadata`.
    metadata: dict = {}
    task_id: Optional[str] = None
    effective_at: str
    created_at: str
    # #41: the immutable past-limit context array (see RecordUsageResponse).
    stop_context: Optional[list] = None


class PastLimitReportResponse(Schema):
    # #41 (spec §I): "exactly what was spent past the limit and why" in one
    # call. episodes[] entries (kept as dict, the list[dict] precedent):
    # {family: floor_stop|task|soft_floor, limit, stop_scope, episode_seq,
    #  task_id, subtask_id, provider_cost_limit_micros, tripped_at,
    #  resumed_at, events: [{event_id, effective_at, billed_cost_micros,
    #  provider_cost_micros, costing_status, arrived_after}], event_count,
    #  total_billed_cost_micros, total_provider_cost_micros,
    #  unresolved_event_count}.
    # Soft-floor entries are crossed/cleared MARKER rows: events always [].
    # totals_per_limit: {limit: {billed_cost_micros, provider_cost_micros,
    #  unresolved_event_count, event_count}} — both denominations, per tripping
    # limit, covering exactly the itemized events of the episodes shown.
    # #328: an itemized event carries `costing_status` because its supplier
    # cost is null both where UBB has not resolved one and where the Event Type
    # declares none; each total carries `unresolved_event_count`, the number of
    # the first kind it therefore could not include, which makes that total a
    # floor.
    customer_id: str
    billing_owner_id: str
    since: Optional[str] = None
    until: Optional[str] = None
    episodes: list[dict]
    totals_per_limit: dict


class ConfigureAutoTopUpRequest(Schema):
    is_enabled: bool
    trigger_threshold_micros: int = Field(ge=0)
    top_up_amount_micros: int = Field(gt=0)

    @field_validator("top_up_amount_micros")
    @classmethod
    def top_up_amount_micros_divisible(cls, v):
        return whole_minor_units(v)


class CreateTopUpRequest(Schema):
    amount_micros: int = Field(gt=0)
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)
    # #78: top-up creation moves money — replay must never mint a second
    # attempt (backed by uq_topup_attempt_idempotency).
    idempotency_key: str = Field(min_length=1, max_length=400)

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        return whole_minor_units(v)


class TopUpCheckoutResponse(Schema):
    # The 200 answer when the Stripe connector is active (#98). The
    # no-connector twin answers 202 out-of-band (top-up request handed to the
    # tenant) — see the globally-documented out-of-band statuses.
    checkout_url: str


class PaginatedUsageResponse(Paginated[UsageEventOut]):
    pass


class WithdrawRequest(Schema):
    amount_micros: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=500)
    description: str = ""

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        return whole_minor_units(v)


class RefundRequest(Schema):
    usage_event_id: UUID
    reason: str = ""
    idempotency_key: str = Field(min_length=1, max_length=500)


class WithdrawResponse(Schema):
    transaction_id: str
    balance_micros: int


class RefundResponse(Schema):
    # A fresh refund answers the REFUND transaction id; an idempotent replay
    # answers the original's reference_id — always a string (the column is
    # NOT NULL, default ""), possibly empty if the replayed key belongs to a
    # non-refund transaction that carries no reference.
    refund_id: str
    balance_micros: int


class WalletTransactionOut(Schema):
    id: UUID
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    # "" for transaction types that carry no reference (e.g. WITHDRAWAL) —
    # the column is NOT NULL, so the wire never serves null here.
    reference_id: str
    created_at: str


def wallet_transaction_out(t):
    """WalletTransactionOut's serializer (the tenant-facing ledger row; the
    /me widget surface serves its own leaner TransactionOut)."""
    return {
        "id": t.id,
        "transaction_type": t.transaction_type,
        "amount_micros": t.amount_micros,
        "balance_after_micros": t.balance_after_micros,
        "description": t.description,
        "reference_id": t.reference_id,
        "created_at": t.created_at.isoformat(),
    }


class PaginatedWalletTransactions(Paginated[WalletTransactionOut]):
    # Pooled-seat disclosure (Task 3): these transactions are the resolved
    # billing owner's ledger — equals this customer's own id/external_id
    # when not a pooled seat.
    billing_owner_id: UUID
    billing_owner_external_id: str
    is_pooled_seat: bool


class ReadyResponse(Schema):
    # The passing readiness answer (#98): overall status plus the per-
    # dependency word ("ok"). The failing answer is a problem+json 503 with
    # the same map riding as a `checks` extension member (#78).
    status: str
    checks: dict[str, str]


REASON_CODES = ("correction", "goodwill", "chargeback", "write_off", "migration", "other")


class DebitRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    reference: str = Field(min_length=1, max_length=500)
    # Required: every balance-mutating write must be safely replayable. A NULL
    # key is excluded from the (wallet, key) partial unique constraint, so an
    # unkeyed retry would double-debit. Matches withdraw/refund/grant.
    idempotency_key: str = Field(min_length=1, max_length=500)
    # Debit respects the customer's overdraft floor by default (like drawdown);
    # allow_negative=true forces a correction past it (logged as forced_overdraw).
    allow_negative: bool = False
    # Attribution (Phase 1): reason_code categorizes the adjustment; actor is
    # who/what initiated it. Optional today; recommended on every manual move.
    reason_code: str = Field(default="", max_length=32)
    actor: str = Field(default="", max_length=255)

    @field_validator("reason_code")
    @classmethod
    def reason_code_valid(cls, v):
        if v and v not in REASON_CODES:
            raise ValueError(f"reason_code must be one of {sorted(REASON_CODES)} or empty")
        return v


class CreditRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    source: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)
    # Required — see DebitRequest.idempotency_key.
    idempotency_key: str = Field(min_length=1, max_length=500)
    # Attribution (Phase 1) — see DebitRequest.
    reason_code: str = Field(default="", max_length=32)
    actor: str = Field(default="", max_length=255)

    @field_validator("reason_code")
    @classmethod
    def reason_code_valid(cls, v):
        if v and v not in REASON_CODES:
            raise ValueError(f"reason_code must be one of {sorted(REASON_CODES)} or empty")
        return v


class DebitCreditResponse(Schema):
    new_balance_micros: int
    transaction_id: str


class CreateGrantRequest(Schema):
    kind: str  # "paid" | "promo"
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    expires_at: Optional[datetime] = None
    expires_in_days: Optional[int] = Field(default=None, gt=0, le=3650)
    idempotency_key: str = Field(min_length=1, max_length=400)
    description: str = Field(default="", max_length=500)

    @field_validator("kind")
    @classmethod
    def kind_valid(cls, v):
        if v not in ("paid", "promo"):
            raise ValueError("kind must be 'paid' or 'promo'")
        return v

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        return whole_minor_units(v)


class GrantOut(Schema):
    id: str
    kind: str
    granted_micros: int
    remaining_micros: int
    expired_micros: int
    voided_micros: int
    currency: str
    status: str
    source: str
    expires_at: Optional[str] = None
    warning_sent_at: Optional[str] = None
    created_at: str
    balance_micros: Optional[int] = None
    transaction_id: Optional[str] = None


def grant_out(grant, *, balance_micros=None, transaction_id=None):
    """GrantOut's serializer. The keyword pair is set only on the
    money-moving answers (create/void), never on list rows."""
    return {
        "id": str(grant.id),
        "kind": grant.kind,
        "granted_micros": grant.granted_micros,
        "remaining_micros": grant.remaining_micros,
        "expired_micros": grant.expired_micros,
        "voided_micros": grant.voided_micros,
        "currency": grant.currency,
        "status": grant.status,
        "source": grant.source,
        "expires_at": grant.expires_at.isoformat() if grant.expires_at else None,
        "warning_sent_at": grant.warning_sent_at.isoformat() if grant.warning_sent_at else None,
        "created_at": grant.created_at.isoformat(),
        "balance_micros": balance_micros,
        "transaction_id": transaction_id,
    }


class PaginatedGrants(Paginated[GrantOut]):
    pass


class TenantMarkupIn(Schema):
    markup_percentage_micros: int = Field(default=0, ge=0)
    fixed_uplift_micros: int = Field(default=0, ge=0)


class TenantMarkupOut(Schema):
    markup_percentage_micros: int
    fixed_uplift_micros: int


class TenantDefaultMarkupIn(Schema):
    """The tenant's default markup rung, as the tenant declares it (#357).

    ⚠ **REQUIRED, WITH NO DEFAULT, WHICH IS THE WHOLE POINT.** UBB ships no
    catalogue: there is no starter percentage anywhere, and a tenant that has
    declared nothing has no markup rung at all. A default of zero here would let
    a caller declare a rung by accident, and a rung of zero is a decision — it
    says *charge my customer exactly what the call cost* — so it has to be
    stated.

    **ONE TERM, BECAUSE A MARGIN NEVER COMPOSES** (#147 §2). No floor, no cap
    and no flat addend beside the percentage: a resolved price is explicable by
    naming one thing, and a chain whose middle terms are on no record is what
    that rule exists to prevent.
    """

    #: Millionths of a percent — 1_000_000 is 1%. Not under the money suffix:
    #: `_micros` means millionths of a CURRENCY unit everywhere else on this
    #: contract.
    markup_micro_percent: int = Field(ge=0)


class TenantDefaultMarkupOut(Schema):
    """What the tenant has declared, or that they have declared nothing.

    ⚠ **NULL MEANS NO RUNG, AND IT IS NOT A ZERO.** The two are different facts
    and reading one as the other is how a customer gets billed exactly what a
    call cost with nobody having decided that: a declared zero says *charge
    cost* and settles, and an absent declaration resolves to `unknown` with no
    amount at all. One nullable field rather than a percentage beside a
    `declared` flag, because two fields encoding one fact is two fields that can
    disagree.
    """

    markup_micro_percent: Optional[int] = None


class CloseTaskResponse(Schema):
    task_id: str
    # Set when the closed unit is a subtask (#38). Closing a PARENT
    # auto-completes its active subtasks; closing a subtask closes it alone.
    parent_task_id: Optional[str] = None
    status: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    #: See `TaskOut.unresolved_event_count` — a closed unit's total is a floor
    #: on exactly the same terms as a running one's, and closing it settles
    #: nothing that was never learned.
    unresolved_event_count: int
    #: And the price half (#351) — a closed unit's billed total is a floor on
    #: the same terms, and closing it prices nothing that was never resolved.
    unpriced_event_count: int
    event_count: int


class TaskOut(Schema):
    task_id: str
    parent_task_id: Optional[str] = None
    task_type: str = ""
    subtask_type: str = ""
    status: str
    total_provider_cost_micros: int
    #: HOW MANY OF THIS UNIT'S EVENTS THE TOTAL ABOVE COULD NOT INCLUDE (#328).
    #:
    #: Non-zero means the unit cost AT LEAST that much: the accumulate primitive
    #: adds a supplier cost only where UBB has resolved one, and counts the rest
    #: here rather than adding a zero that would read as a settled figure. It is
    #: also what the unit's COGS limit raced, so a limit that has not fired has
    #: not been shown to be safe.
    #:
    #: An event whose Event Type declares no supplier cost is not counted: there
    #: is nothing missing about a cost that does not exist.
    unresolved_event_count: int
    total_billed_cost_micros: int
    #: HOW MANY OF THIS UNIT'S EVENTS THE BILLED TOTAL COULD NOT INCLUDE (#351).
    #:
    #: The mirror of the count above, and it bounds the unit in the other
    #: direction: non-zero means the unit will be charged AT LEAST that much.
    #: The accumulate primitive adds a customer price only where UBB resolved
    #: one and counts the rest here rather than adding a zero.
    #:
    #: A `waived` price and a `not_applicable` one are not counted: neither is
    #: missing information, and a caveat that is always on is one nobody reads.
    unpriced_event_count: int
    event_count: int
    provider_cost_limit_micros: Optional[int] = None
    dimensions: dict = Field(default_factory=dict)
    created_at: str
    completed_at: Optional[str] = None


def task_out(t):
    """TaskOut's serializer — the per-unit cost receipt, read straight off the
    materialized rollups the accumulate primitive maintains."""
    return {
        "task_id": str(t.id),
        "parent_task_id": str(t.parent_id) if t.parent_id else None,
        "task_type": t.task_type, "subtask_type": t.subtask_type,
        "status": t.status,
        "total_provider_cost_micros": t.total_provider_cost_micros,
        "unresolved_event_count": t.unresolved_event_count,
        "total_billed_cost_micros": t.total_billed_cost_micros,
        "unpriced_event_count": t.unpriced_event_count,
        "event_count": t.event_count,
        "provider_cost_limit_micros": t.provider_cost_limit_micros,
        # A FREE-FORM OBJECT, so its keys are data and not contract: the
        # published document types this as an object and names no property, and
        # #276 renaming the columns therefore renames the keys here without
        # touching the schema. That is also why widening it to ten costs the
        # contract nothing. Ticket 20 replaces the physical slot with the
        # tenant's own declared key, which is the shape the read side is being
        # moved to match.
        "dimensions": {slot: getattr(t, slot) for slot, _ in SLOT_CHOICES
                       if getattr(t, slot)},
        "created_at": t.created_at.isoformat(),
        "completed_at": t.completed_at.isoformat() if t.completed_at else None,
    }


class TaskDetailOut(TaskOut):
    subtasks: list[TaskOut] = Field(default_factory=list)


class PaginatedTasks(Paginated[TaskOut]):
    pass


class UsageAnalyticsResponse(Schema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    #: HOW MANY EVENTS THE SUPPLIER-COST TOTAL COULD NOT INCLUDE (#327).
    #:
    #: A supplier cost UBB has not resolved contributes nothing to the total
    #: above, and SQL says nothing about having skipped it — so the total says
    #: it here instead. Non-zero means the figure is a FLOOR: the true cost is
    #: at least that much, and the margin beside it is at most what it says.
    #: Zero means the total is whole.
    #:
    #: An event whose Event Type declares no supplier cost is NOT counted here.
    #: Nothing about it is missing, and a caveat that is always on is a caveat
    #: nobody reads.
    #:
    #: The breakdown blocks below are `list[dict]` and each of their rows
    #: carries the same key for its own group. No schema holds those rows, so
    #: `api/v1/tests/test_a_cost_total_says_what_it_excluded.py` asserts them.
    unresolved_event_count: int
    #: And how many the BILLED total could not include (#351). It bounds the
    #: margin below in the OPPOSITE direction from the count above: an excluded
    #: cost makes the margin a ceiling, an excluded price makes it a floor, and
    #: an answer can be both at once. That is why they are two properties and
    #: not one — a single number could not say which way the figure is wrong.
    unpriced_event_count: int
    usage_markup_margin_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]
    by_customer: list[dict]
    by_task_type: list[dict]
    by_tag: list[dict]
    breakdowns: dict = {}


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    #: The same pair as `UsageAnalyticsResponse` above, for the tenant-wide
    #: total. Each row of `daily` carries its own count for its own day.
    unresolved_event_count: int
    total_billed_cost_micros: int
    #: The price half of the same pair (#351), tenant-wide. Each row of `daily`
    #: carries its own, for its own day.
    unpriced_event_count: int
    total_markup_micros: int
    daily: list[dict]


class UsageTimeseriesResponse(Schema):
    granularity: str
    group_by: str = ""
    series: list[dict]


class TaskAnalyticsRow(Schema):
    task_type: str
    run_count: int
    total_provider_cost_micros: int
    #: How many events this KIND of work could not cost (#328). Non-zero makes
    #: every figure in the row a floor — the total, the mean and the p95 — since
    #: each unit they are built from is one.
    unresolved_event_count: int
    total_billed_cost_micros: int
    #: And how many this KIND of work could not PRICE (#351), bounding the
    #: billed total the same way. Two counts because a kind of job can be fully
    #: costed and partly unpriced, or the reverse.
    unpriced_event_count: int
    avg_provider_cost_micros: int
    p95_provider_cost_micros: int
    limit_hit_count: int


class TaskAnalyticsOut(Schema):
    group_by: str
    rows: list[TaskAnalyticsRow]


class BudgetConfigIn(Schema):
    cap_micros: int = Field(ge=0)
    # Must match apps.billing.gating.models.BUDGET_ENFORCE_MODES — the model
    # field's `choices` alone never gets enforced (Django doesn't validate
    # choices on save()), so an out-of-vocabulary value used to persist
    # silently and could never cross (crossing.py's budget_stop_threshold
    # treats anything != "blocking" as non-blocking).
    enforce_mode: Literal["alert_only", "blocking"] = "alert_only"
    hard_stop_pct: int = Field(default=100, ge=1, le=1000)
    alert_levels: Optional[list[int]] = None
    fail_closed: bool = False


class BudgetConfigOut(Schema):
    cap_micros: int
    enforce_mode: str
    hard_stop_pct: int
    alert_levels: list[int]
    fail_closed: bool


class CustomerBillingProfileIn(Schema):
    # All are null-able overrides (PUT = full replace, so null clears the
    # override): null min_balance_micros = inherit the tenant default; null
    # topup_grant_expiry_days = top-ups never expire; null
    # soft_min_balance_micros = inherit the tenant's soft-floor default.
    min_balance_micros: Optional[int] = None
    topup_grant_expiry_days: Optional[int] = None
    # Soft floor (#40): the wind-down line, same orientation as
    # min_balance_micros (the line is -value) but may be NEGATIVE — that
    # places the line above zero (refuse new starts while money remains).
    # Must keep the soft line at or above the hard floor's (value <= the
    # effective min_balance).
    soft_min_balance_micros: Optional[int] = None


class CustomerBillingProfileOut(Schema):
    min_balance_micros: Optional[int] = None
    topup_grant_expiry_days: Optional[int] = None
    soft_min_balance_micros: Optional[int] = None
    # Pooled-seat disclosure (Task 3): this is the resolved billing owner's
    # effective profile — equals this customer's own id/external_id when not
    # a pooled seat.
    billing_owner_id: UUID
    billing_owner_external_id: str
    is_pooled_seat: bool


class BudgetStatusOut(Schema):
    period: str
    spend_micros: int
    cap_micros: int
    pct: float
    enforce_mode: str


class UsageInvoiceOut(Schema):
    period_start: str
    period_end: str
    total_billed_micros: int
    currency: str
    status: str
    stripe_invoice_id: str = ""
    skip_reason: str = ""
    push_attempts: Optional[int] = None
    last_attempt_error: Optional[str] = None


def usage_invoice_out(r):
    """UsageInvoiceOut's serializer — one customer's usage invoice."""
    return {
        "period_start": r.period_start.isoformat(),
        "period_end": r.period_end.isoformat(),
        "total_billed_micros": r.total_billed_micros,
        "currency": r.currency,
        "status": r.status,
        "stripe_invoice_id": r.stripe_invoice_id,
        "skip_reason": r.skip_reason,
        "push_attempts": r.push_attempts,
        "last_attempt_error": r.last_attempt_error,
    }


class UsageInvoiceListResponse(Paginated[UsageInvoiceOut]):
    # NOT "PaginatedUsageInvoices" — the /me surface already owns that
    # component name (me_endpoints.py) and ninja silently overwrites
    # duplicate schema names in the one document (#77's hazard).
    pass


class TenantUsageInvoiceOut(Schema):
    customer_id: str
    external_id: str
    period_start: str
    total_billed_micros: int
    status: str
    stripe_invoice_id: str = ""
    skip_reason: str = ""
    push_attempts: Optional[int] = None
    last_attempt_error: Optional[str] = None


def tenant_usage_invoice_out(r):
    """TenantUsageInvoiceOut's serializer — the tenant-wide invoice sweep
    row (callers select_related("customer") for external_id)."""
    return {
        "customer_id": str(r.customer_id),
        "external_id": r.customer.external_id,
        "period_start": r.period_start.isoformat(),
        "total_billed_micros": r.total_billed_micros,
        "status": r.status,
        "stripe_invoice_id": r.stripe_invoice_id,
        "skip_reason": r.skip_reason,
        "push_attempts": r.push_attempts,
        "last_attempt_error": r.last_attempt_error,
    }


class TenantUsageInvoiceListResponse(Paginated[TenantUsageInvoiceOut]):
    pass


class PostpaidConfigIn(Schema):
    # None sentinel on BOTH fields: omit means "leave unchanged".  An explicit
    # "" clears group_by; an explicit False turns consolidation off.
    # F5.5 Fix 2: group_by used to default to "" which silently overwrote the
    # current value on every partial PUT that omitted it.
    usage_line_item_group_by: Optional[str] = None
    # F5.5 opt-in; None = leave unchanged (a group_by-only PUT must never
    # silently switch a tenant's consolidation mode off).
    consolidate_with_subscription: Optional[bool] = None


class PostpaidConfigOut(Schema):
    usage_line_item_group_by: str
    consolidate_with_subscription: bool = False


# --- Two-level pricing: a RateCard BOOK groups many Rates ---


class PricingBookIn(Schema):
    """Declare a Pricing Book: a catalogue of what this tenant charges.

    It names neither a supplier nor a currency, and both absences are
    deliberate. A tenant's price for a unit of work does not change because
    they switched supplier, and a tenant has exactly one currency
    (per-tenant single currency; multi-currency and FX are not supported), so
    a book that repeated either would be repeating a decision made elsewhere.
    A rule that should price one supplier's work differently pins `provider`
    as a selector, which is where that belongs.

    `is_default` marks the book a customer is priced from when nothing
    narrower applies. A tenant has at most one; declaring a second answers
    409.
    """
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    is_default: bool = False


class PricingBookOut(Schema):
    id: str
    key: str
    name: str
    version: int
    is_default: bool
    #: Set when this book holds one named customer's own rules — their
    #: negotiated deal, declared and withdrawn through the override routes.
    #: Null on a catalogue the tenant wrote for everybody.
    customer_id: Optional[str]


def pricing_book_out(b):
    """PricingBookOut's serializer."""
    return {
        "id": str(b.id),
        "key": b.key,
        "name": b.name,
        "version": b.version,
        "is_default": b.is_default,
        "customer_id": str(b.customer_id) if b.customer_id else None,
    }


class CostBookIn(Schema):
    """Declare a cost book: a record of what one supplier charges this tenant.

    It names the supplier and the currency that supplier bills in, and both
    are required in the sense that matters: `currency` may not be empty, and
    `provider_key` must be stated — the empty string is a stated value and
    means the book applies whatever the supplier, which is a real choice
    rather than an omission.

    `is_default` marks the book a cost is resolved from for that supplier and
    currency. A tenant has at most one per pair; declaring a second answers
    409.
    """
    provider_key: str = Field(default="", max_length=100)
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    # CUR-1: omitted/None defaults to the tenant's default_currency; an
    # explicit value must MATCH the tenant currency (422 otherwise).
    currency: Optional[str] = Field(default=None, max_length=3)
    is_default: bool = False


class CostBookOut(Schema):
    id: str
    provider_key: str
    currency: str
    key: str
    name: str
    version: int
    is_default: bool


def cost_book_out(b):
    """CostBookOut's serializer."""
    return {
        "id": str(b.id),
        "provider_key": b.provider_key,
        "currency": b.currency,
        "key": b.key,
        "name": b.name,
        "version": b.version,
        "is_default": b.is_default,
    }


class RateOut(Schema):
    id: str
    #: The book this rule is in, whichever kind it is. A caller that needs to
    #: know which kind reads the book: a cost book names a supplier and a
    #: currency, a Pricing Book names neither.
    book_id: Optional[str]
    lineage_id: str
    measurement_key: str
    provider: str
    event_type: str
    task_type: str
    subtask_type: str
    grouping_field_1: str
    grouping_field_2: str
    grouping_field_3: str
    grouping_field_4: str
    grouping_field_5: str
    grouping_field_6: str
    grouping_field_7: str
    grouping_field_8: str
    grouping_field_9: str
    grouping_field_10: str
    rate_structure: RateStructure
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    currency: str
    valid_from: str
    valid_to: Optional[str] = None


#: THE PROPERTY/COLUMN MISMATCH IS GONE, AND THE JOIN THAT HELD IT WENT WITH IT
#: (#366, ruling 15).
#:
#: #276 renamed the rate's slot columns to the canonical noun and deliberately
#: renamed no published property — its acceptance criteria forbid it. So six
#: published `dim<n>` names sat over six differently-named columns, and a
#: dictionary here joined them. **`SLOT_PROPERTY_COLUMNS` is DELETED rather than
#: widened to ten**: widening it would have coined four new published properties
#: under a spelling this slice retires, and the properties take the COLUMN names
#: instead, so there is nothing left for a join to state.
#:
#: **WHO CLOSED IT WAS SETTLED, AND IT WAS SLICE 4.** #276 left the question
#: open here; ticket 20 (#277) answered it and did not take it. Its body is
#: about a posting's grouping values and says nothing about a rate, while its
#: acceptance criteria are worded wider ("no physical slot field is exposed on
#: any public schema") — so the two readings really did differ, and **#193 §L
#: decided between them**: "the rate entity, the rate book, the card-type
#: discriminator, **the rate selector list**, specificity ranking, and the
#: tenant markup" belong to slice 4, listed there expressly "so that no ticket
#: quietly widens". Slice 4 rebuilds all three of these schemas, so converting
#: them in #277 would have been the same work twice and a second breaking change
#: on the same six properties.
#:
#: ⚠ **THE SIX-OF-TEN GAP WAS FUNCTIONAL, NOT COSMETIC.** A rate can pin ten
#: slots; these three schemas named six. A reprice body left the other four at
#: "", which is exactly what matches a rate that leaves them UNPINNED — so a
#: rule pinned on the seventh slot could be written server-side and then matched
#: by no publish body at all. It is not a spelling difference that closes here
#: but that unreachability: all ten are stated, and
#: `api/v1/tests/test_a_rate_on_any_slot_can_be_repriced.py` reprices one
#: end to end.
#:
#: The residue is not left to memory. `api/v1/tests/
#: test_grouping_values_on_the_contract.py` walks every published schema, holds
#: the (schema, property) pairs as an EQUALITY, and fails if the set ever
#: overstates or understates what the contract actually publishes.
#:
#: ⚠ **THE SAME FACT IS REACHABLE TWO WAYS AND THAT IS DELIBERATE (#358).** A
#: publish's change body carries `grouping_fields` keyed by what the TENANT
#: declared, and the registry resolves the key to whichever slot it is bound to;
#: these three name the slot directly. The first is the shape a tenant should
#: reach for — it survives a slot being rebound — and the second is what the
#: three immediate routes have always spoken. They agree on which rule they
#: address because both end at the same columns.


def rate_out(r):
    """RateOut's serializer — one rate version under a book.

    ⚠ **THE KIND WORD IS GONE FROM THE ROW AND FROM THIS RESPONSE (#367).** It
    was a copy of the book's, and a reader who wants it reads it off the book
    the rules were listed under — which is the id already on every row here.
    Publishing a second copy of it let a client compare two answers to one
    question, and the row was the one that could be wrong.
    """
    return {
        "id": str(r.id),
        "book_id": str(r.book.id) if r.book is not None else None,
        "lineage_id": str(r.lineage_id),
        "measurement_key": r.measurement_key,
        "provider": r.provider,
        "event_type": r.event_type,
        "task_type": r.task_type,
        "subtask_type": r.subtask_type,
        # Ten slots under their own column names, walked off the ROW's own
        # selector list rather than off a map: a slot the model gains and this
        # schema does not name would then be a `KeyError` a reader can act on,
        # where a map walk would drop it silently (#361's lesson, one schema
        # over).
        **{slot: getattr(r, slot) for slot in SLOTS},
        "rate_structure": r.rate_structure,
        "rate_per_unit_micros": r.rate_per_unit_micros,
        "unit_quantity": r.unit_quantity,
        "fixed_micros": r.fixed_micros,
        "currency": r.currency,
        "valid_from": r.valid_from.isoformat(),
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
    }


# --- Every change to a Pricing Book is a publish (#358) -----------------------
#
# One act replacing three, so a book has one mutation surface and a tenant has
# one thing to read: *your book changes on 1 August; here is the diff*.
#
# ⚠ **THESE SCHEMAS NAME NO PHYSICAL SLOT, AND THAT IS STILL DELIBERATE — BUT
# NOT FOR THE REASON IT WAS (#366).** #358 kept the slot spelling off this act
# because the three schemas above published the rate's selector list as six
# `dim<n>` properties under a name slice 4 was retiring, and reusing it here
# would have coined six more for the converting ticket to convert. That ticket
# has landed: those three publish all TEN slots now, under the COLUMN names, and
# the join dictionary between the two spellings is gone.
#
# **SO THE TWO SHAPES ARE BOTH LIVE AND THEY ARE NOT REDUNDANT.** A change body
# names its grouping fields the way a recording call does — by the tenant's own
# declared key, in an object — and the three above name the slot directly. The
# key-keyed form is the one to reach for, because a key rebound to another slot
# takes its rules with it while a body naming the slot silently starts
# addressing something else; the slot-named form is what the three immediate
# routes have always spoken, and it is how a rule with no declared key for a
# slot is addressable at all. Both end at the same columns, so they cannot
# disagree about which rule they mean.


class BookChangeIn(Schema):
    """One change in a publish: what to do, and to which rule.

    `kind` is `add`, `reprice` or `retire` — the three surfaces a book used to
    have, arriving as three kinds of one act. It is a plain string and the
    service refuses anything else, which is how the book's own discriminators
    are already handled on this surface: these three name the shape of one
    request body, they are stored on no column and returned in no response, and
    a `Literal` here would publish an enumeration the vocabulary registry does
    not own.

    The rule is identified by the quantity it prices plus its selectors —
    `provider`, `event_type`, `task_type`, `subtask_type` and the tenant's own
    declared grouping fields. An omitted selector means the rule leaves it
    unpinned, which is what an unpinned selector means everywhere on this
    surface, so a change body names only what the rule pins.

    The three terms, the method and the arithmetic shape are nullable because a
    reprice states only what moves: anything unstated is carried over from the
    rule being superseded. An `add` takes the model's own defaults for what it
    leaves out, and a `retire` states none of them at all — it opens no rule.

    `rate_structure` says which arithmetic the rule runs: an amount per unit of
    quantity, or a component that applies once regardless of quantity. It is a
    different fact from `pricing_method`, which says how the price is DERIVED,
    and a change may move either without the other.
    """
    kind: str
    measurement_key: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    task_type: str = Field(default="", max_length=64)
    subtask_type: str = Field(default="", max_length=64)
    grouping_fields: dict[str, str] = {}
    #: HOW THE RULE DERIVES ITS PRICE — a margin over what the call cost, or an
    #: amount attached to the event regardless of cost (#361, #147 §2).
    #:
    #: Nullable, and null is not a third method: it says the rule derives no
    #: price of its own and charges its own terms. An `add` that omits it takes
    #: that null; a `reprice` that omits it keeps the method of the rule it
    #: supersedes, exactly as it keeps every term it does not restate; a
    #: `retire` may not state it at all, because it opens no rule.
    #:
    #: **THIS IS WHAT MAKES A CUSTOMER OVERRIDE A WHOLE RULE** (#151 §6): a
    #: customer moved from cost-plus onto a flat price is a method change, and
    #: without it the tenant's only route to that deal would be to estimate the
    #: customer's typical cost and enter a number that approximates it — a
    #: price computed outside UBB, going stale the moment the supplier moves.
    pricing_method: Optional[PricingMethod] = None
    #: WHICH ARITHMETIC THE RULE RUNS — per unit of quantity, or once
    #: regardless (#366, #151 §13.2).
    #:
    #: ⚠ It arrives one ticket after everything beside it, and the reason was
    #: never a product decision: the column's name was retired until this
    #: commit, and coining either spelling on a new schema would have broken a
    #: ledger ceiling or published a field whose values were still the retired
    #: ones. #358 recorded the deferral by naming the commit that could clear
    #: both at once. Until it landed, the only way to move a rule's arithmetic
    #: shape was the immediate reprice route this act replaces.
    #:
    #: Nullable for the same reason as the terms beside it — a reprice states
    #: what moves — and NOT for the method's reason: null here is not a value
    #: the rule can end up carrying. Every rule has a shape, so an `add` that
    #: omits this takes the column's default rather than a null.
    rate_structure: Optional[RateStructure] = None
    rate_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: Optional[int] = Field(default=None, gt=0)
    fixed_micros: Optional[int] = Field(default=None, ge=0)


class BookPublishIn(Schema):
    """The intended changes, and when they take effect.

    **`effective_at` IS WHAT DATES A CHANGE FORWARD, AND OMITTING IT MEANS
    NOW.** A tenant who has agreed a rise from the first of next month states
    that instant here and stops having to remember: publishing writes the rows
    immediately, carrying the boundary as a value the resolver reads, so
    **nothing runs at the instant itself**. There is no job to be late, which
    matters because a late job would price every event in the gap at the old
    rate and that wrong price would sit permanently on an authoritative record.

    The instant must be timezone-aware (`effective_at_naive`). A change is dated
    forward or not at all, so an instant more than five minutes behind the
    present is refused with `effective_at_in_past` — the allowance is clock
    skew, so that a caller stamping its own "now" is not told its clock is
    wrong. And it must be within the platform's forward horizon of **366 days**;
    beyond it the request is refused with `effective_at_too_far_ahead`.

    Each of the three carries a code of its own so that *"that date is a typo"*
    is distinguishable from *"that date has passed"* and from every other reason
    a body is refused. The horizon is a platform bound and no tenant setting
    moves it.
    """
    changes: list[BookChangeIn] = Field(min_length=1)
    effective_at: Optional[datetime] = None


class RuleTermsOut(Schema):
    """What a rule charges, how it derives it, and which arithmetic it runs.

    Everything a change may move, so a `before` and an `after` side by side are
    a complete account of what a publish does to a rule. `rate_structure`
    decides which of the money terms is actually spent, so a rule going from a
    per-unit charge to a fixed component would read as *"nothing moved"* from
    the terms alone.
    """
    # ⚠ WHY THE LAST TWO FIELDS ARRIVED LATE, in a COMMENT rather than the
    # docstring above: a `Schema`'s docstring is exported verbatim into
    # `openapi/v1.json` and the generated SDK, and this repository's slice
    # history is not something a caller needs. The method joined in #361,
    # because a customer override replaces a whole rule INCLUDING its method
    # and a diff that hid the change would hide the one part of a negotiated
    # deal that changes shape. The arithmetic shape joined in #366 for the same
    # reason one ticket later — it was absent only while a publish could not
    # move it, which was a retired column name rather than a decision.
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    #: Null where the rule derives no price of its own — see `BookChangeIn`.
    pricing_method: Optional[PricingMethod] = None
    #: Never null: every rule has an arithmetic shape, and this row is a rule's
    #: terms rather than a statement of what a body said.
    rate_structure: RateStructure


def rule_terms_out(terms):
    """`RuleTermsOut`'s serializer — one rule's terms, named key by key.

    ⚠ **NAMED RATHER THAN PASSED THROUGH, AND THAT IS THE WHOLE POINT.** A
    `Schema` that does not name a key does not merely omit it — Django Ninja
    DROPS it, silently, which is how a read contract once published a ceiling as
    a margin. The service decides what a rule's terms ARE; this decides what the
    contract publishes; and handing the service's dict straight to the schema
    would let those two disagree with nothing saying so. Spelling each key here
    makes a term the service gains and this does not name a `KeyError` on the
    first request instead, and
    `api/v1/tests/test_a_book_changes_by_publishing.py` asserts the two sets are
    equal, which is the same claim held at rest.
    """
    return {
        "rate_per_unit_micros": terms["rate_per_unit_micros"],
        "unit_quantity": terms["unit_quantity"],
        "fixed_micros": terms["fixed_micros"],
        "pricing_method": terms["pricing_method"],
        "rate_structure": terms["rate_structure"],
    }


class BookChangeDiffOut(Schema):
    """One row of the diff: which rule, and what happens to it.

    `before` is the rule as it will stand at the publish's effective instant and
    is null where the change adds one; `after` is the rule the publish opens and
    is null where the change retires one. Neither is null on a reprice, which is
    what makes the row readable as a change rather than as an outcome.
    """
    kind: str
    measurement_key: str
    provider: str
    event_type: str
    task_type: str
    subtask_type: str
    grouping_fields: dict[str, str] = {}
    before: Optional[RuleTermsOut] = None
    after: Optional[RuleTermsOut] = None


class BookPublishOut(Schema):
    """A change to a book: an intention while it is a draft, a decision once
    published.

    ⚠ `declaration_status` is deliberately UNMARKED, on the same footing as
    `EventTypeOut.declaration_status`: the concept declares no `openapi`
    consumer in the registry, and the applier refuses a marker for a concept
    that contributes nothing. A field is marked by the ticket that declares its
    concept's contract consumer, never by one passing nearby. The FIELD is still
    final under ADR-0007 §3 — gaining an `enum` later is additive, and its
    values are already the registry's.
    """
    id: str
    book_id: str
    declaration_status: str
    effective_at: str
    published_at: Optional[str] = None
    #: An immutable snapshot of the principal whose decision this was, taken at
    #: the moment of the publish (ADR-004 §4). Empty on a draft: whose decision
    #: put a price in force is a question with an answer only once one is in
    #: force, and who declared the draft is the audit ledger's.
    actor_kind: str
    actor_id: str
    actor_display: str
    #: The rule versions this publish opened and closed. Empty on a draft,
    #: because a draft opened and closed none.
    opened_rule_ids: list[str]
    closed_rule_ids: list[str]
    #: WHAT THIS PUBLISH WILL DO, computed against the book as it will stand at
    #: `effective_at`. Present while the record is a draft and NULL once it is
    #: published, because a diff is a statement about a change that has not
    #: happened yet. What a published record DID is the two id lists above, read
    #: back off the rules themselves — which carry their own terms, their own
    #: boundaries and their lineage — rather than out of an echo of the request.
    diff: Optional[list[BookChangeDiffOut]] = None
    #: ⚠ WHY A DRAFT MAY HAVE NO DIFF EITHER, WHICH IS A REACHABLE STATE AND NOT
    #: A DEFENSIVE ONE. Two drafts can name one rule while only one of them
    #: publishes, so a draft can be left stating a change that can no longer be
    #: carried out. The immediate reprice route beside this act reaches the same
    #: rules and can do it too — it is the last of three, the other two having
    #: left with #367 — but it is not what makes this reachable, and a book with
    #: no immediate route at all would still get here through two drafts.
    #: Reading such a draft must say so rather than answer a diff nobody can
    #: compute: `diff` is null and this carries the same sentence declaring the
    #: draft would now be refused with. Null on a draft with a diff, and null on
    #: a published record — where `declaration_status` is what tells a reader
    #: which of the two an absent diff means.
    diff_unavailable_reason: Optional[str] = None


def book_publish_out(record, diff=None, diff_unavailable_reason=None):
    """`BookPublishOut`'s serializer.

    `diff` arrives already translated into the tenant's own vocabulary — see
    `book_change_diff_out` — because the service works in column names and this
    contract publishes none.
    """
    return {
        "id": str(record.id),
        "book_id": str(record.book_id),
        "declaration_status": record.declaration_status,
        "effective_at": record.effective_at.isoformat(),
        "published_at": (record.published_at.isoformat()
                         if record.published_at else None),
        "actor_kind": record.actor_kind,
        "actor_id": record.actor_id,
        "actor_display": record.actor_display,
        "opened_rule_ids": list(record.opened_rule_ids),
        "closed_rule_ids": list(record.closed_rule_ids),
        "diff": diff,
        "diff_unavailable_reason": diff_unavailable_reason,
    }


class UndeclaredGroupingField(ValueError):
    """A change body selects on a grouping field the tenant has not declared.

    Its own type rather than a `KeyError`, so the route can answer 422 for THIS
    and let anything else fail loudly: catching `KeyError` around a translation
    catches every bug inside it too and reports each one as a tenant error.
    """

    def __init__(self, key):
        self.key = key
        super().__init__(key)


def book_change_body(change: dict, slots: dict) -> dict:
    """One change body with its grouping fields resolved to slot columns.

    The service matches a rule on `Rate.SELECTORS`, which are columns. A tenant
    names its own declared key; `slots` is the registry's `{key: slot}` map for
    that tenant, and a key the registry does not carry raises `KeyError` here so
    the route can answer 422 rather than silently matching a rule that leaves
    every slot unpinned — which would reprice the wrong rule, or none.
    """
    body = {name: value for name, value in change.items()
            if name != "grouping_fields"}
    for key, value in (change.get("grouping_fields") or {}).items():
        if key not in slots:
            # Raised on the LOOKUP rather than caught around the whole loop: a
            # `KeyError` from anywhere else in here is a bug in this function,
            # and reporting one to a tenant as "you have not declared that
            # grouping field" would be a wrong answer wearing a right one's
            # clothes.
            raise UndeclaredGroupingField(key)
        body[slots[key]] = value
    return body


def book_change_diff_out(row: dict, keys: dict) -> dict:
    """One diff row, in the tenant's own vocabulary.

    The inverse of `book_change_body`: `keys` is the registry's `{slot: key}`
    map, so a row names the grouping field the tenant declared rather than the
    column it happens to occupy.
    """
    reserved = ("provider", "event_type", "task_type", "subtask_type")
    selectors = row["selectors"]
    return {
        "kind": row["kind"],
        "measurement_key": row["measurement_key"],
        **{name: selectors.get(name, "") for name in reserved},
        # The slots, by exclusion of the four reserved axes, and then `keys[]`
        # rather than a membership test. Dropping a slot the registry cannot
        # name would take a selector OFF a diff row and leave it naming a
        # different rule — the blanket one — which is the misreading the write
        # side above refuses outright. `keys_by_slot` keeps retired definitions
        # for exactly this reason and nothing in the tree removes one, so a
        # missing slot is a corrupt row rather than a state a tenant can reach,
        # and it should be loud.
        "grouping_fields": {keys[slot]: value
                            for slot, value in selectors.items()
                            if slot not in reserved},
        "before": rule_terms_out(row["before"]) if row["before"] else None,
        "after": rule_terms_out(row["after"]) if row["after"] else None,
    }


# --- A customer override replaces a whole rule, method included (#361) -------
#
# A tenant honouring a negotiated deal gives one customer their own pricing
# rule. The override replaces the WHOLE rule — never a number inside one — so a
# customer on cost-plus and a customer on a flat price are both expressible, and
# a rule can be read on its own without tracing a chain (#151 §6).


# ⚠ WHY THIS BODY CARRIES NO `kind` WHILE `BookChangeIn` DOES — a COMMENT, not
# the docstring, because a `Schema`'s docstring is exported verbatim into
# `openapi/v1.json` and the generated SDK, and this is a note to the next author
# rather than something a caller can act on (#359's lesson, one layer out from
# the route it was learned on).
#
# The two bodies name a rule identically on purpose: they are the same rule, and
# a client that can write one can write the other. What differs is the ACT, and
# here the act is the route — declaring an override adds a rule, withdrawing one
# retires it. Reusing `BookChangeIn` would let the declaring route be sent a
# retirement, and the governance ledger would then record the wrong act for it.
class CustomerOverrideIn(Schema):
    """The rule this customer gets, and when it takes effect.

    **A COMPLETE RULE, WHICH IS THE WHOLE RULING.** Every field a rule has is
    stated here: the quantity it prices, the selectors it pins, how it derives
    its price and what it charges. There is no field naming a rule to inherit
    from and no field that takes a value while leaving a method behind —
    **partial override is not expressible on this surface**, because a rule
    whose method comes from one record and whose value comes from another
    cannot be explained by naming one rule, which is the property the receipt
    design rests on (#151 §6.2).

    **THIS BODY NAMES NO ACT.** It carries no `kind`, unlike a change to a
    book: declaring an override adds a rule and withdrawing one retires it, and
    which of the two is happening is the route you called.

    `effective_at` dates the override forward and omitting it means now, under
    exactly the bounds a publish takes, because this IS a publish: it is
    declared as a draft on the customer's own book, published through the
    book's own route, and reversed by a further publish. There is no
    immediate-effect path to an override and no second mutation surface for one.
    """
    measurement_key: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    task_type: str = Field(default="", max_length=64)
    subtask_type: str = Field(default="", max_length=64)
    grouping_fields: dict[str, str] = {}
    pricing_method: Optional[PricingMethod] = None
    #: WHICH ARITHMETIC THE OVERRIDE RUNS (#366). It joins because "every field
    #: a rule has is stated here" is a claim this body makes about itself, and
    #: a whole-rule replacement that could not state the shape would be exactly
    #: the partial override the paragraph above says is inexpressible: the terms
    #: would come from the negotiated deal and the shape from whatever the
    #: model's default happens to be. `BookChangeIn`'s own note records why it
    #: could not arrive until the column was renamed.
    #:
    #: The agreement is not left to a reader —
    #: `api/v1/tests/test_a_customer_override_is_declared_and_withdrawn.py`
    #: asserts this field set EQUALS a change body's, minus the act, plus the
    #: instant. It is the test that found this omission.
    rate_structure: Optional[RateStructure] = None
    rate_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: Optional[int] = Field(default=None, gt=0)
    fixed_micros: Optional[int] = Field(default=None, ge=0)
    effective_at: Optional[datetime] = None


class InheritedPricingRule(Schema):
    """One rule, as a client would start an override from it.

    Everything an override body has to state, in the shape it has to state it —
    so *create from the inherited rule* is a copy rather than a translation. The
    rule's own id and the book it came from ride along so a reader can say where
    the starting point came from.
    """
    rule_id: str
    book_id: str
    measurement_key: str
    provider: str
    event_type: str
    task_type: str
    subtask_type: str
    grouping_fields: dict[str, str] = {}
    pricing_method: Optional[PricingMethod] = None
    #: Never null: this is a rule, and every rule has an arithmetic shape. It
    #: joins with #366 because the override body it seeds now states one, and a
    #: starting point missing a field the destination requires makes "copy
    #: rather than translate" false for exactly the field a client is least
    #: likely to notice — a per-unit rule copied into a body that omits the
    #: shape takes the model's default, which happens to agree, while a fixed
    #: component copied the same way silently becomes a per-unit charge.
    rate_structure: RateStructure
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    currency: str


class InheritedRuleOut(Schema):
    """What this customer is charged for a quantity where they have no override.

    **AN ENVELOPE, BECAUSE "NOTHING IS INHERITED" IS AN ANSWER.** A quantity no
    book in play prices falls to the tenant's markup rung, and a client creating
    an override there is starting from nothing rather than from a rule — a
    perfectly ordinary state, and one a `404` would report as *"no such
    customer"*. So the rule is nullable and the status stays `200`.
    """
    rule: Optional[InheritedPricingRule] = None


def inherited_rule_out(rule, selectors, keys):
    """`InheritedRuleOut`'s serializer.

    `selectors` is the rule's own `{column: value}` map and `keys` is the
    registry's `{slot: declared key}`, exactly as `book_change_diff_out` takes
    them — and this walks them the same way round, which is the part that
    matters.

    ⚠ **THE WALK IS OVER THE RULE'S SLOTS AND THE LOOKUP IS `keys[slot]`,
    LOUD.** Walking the registry's map instead would silently drop a slot the
    registry cannot name, and that is worse here than anywhere: this row is
    what a client copies into an override body, so a dropped selector produces
    an override BROADER than the rule it was supposed to replace — the blanket
    one. `keys_by_slot` keeps retired definitions and nothing removes one, so a
    missing slot is a corrupt row rather than a state a tenant can reach, and
    it should be loud.

    Named key by key for the reason `rule_terms_out` gives: a `Schema` that does
    not name a key does not merely omit it, Django Ninja DROPS it.
    """
    if rule is None:
        return {"rule": None}
    reserved = ("provider", "event_type", "task_type", "subtask_type")
    return {"rule": {
        "rule_id": str(rule.id),
        "book_id": str(rule.book.id),
        "measurement_key": rule.measurement_key,
        **{name: selectors.get(name, "") for name in reserved},
        "grouping_fields": {keys[slot]: value
                            for slot, value in selectors.items()
                            if slot not in reserved and value},
        "pricing_method": rule.pricing_method,
        "rate_structure": rule.rate_structure,
        "rate_per_unit_micros": rule.rate_per_unit_micros,
        "unit_quantity": rule.unit_quantity,
        "fixed_micros": rule.fixed_micros,
        "currency": rule.currency,
    }}


# --- A Resolution Run completes what was never resolved (#363) --------------
#
# ⚠ WHY THE REQUEST BODY REFUSES WHAT IT DOES NOT PUBLISH — a COMMENT rather
# than the docstring, because a `Schema`'s docstring is exported verbatim into
# `openapi/v1.json` and the generated SDK, and this is a note to the next author.
#
# Django Ninja DROPS a body key no schema names rather than refusing it, so a
# caller sending a condition of their own — a filter expression, a status, a
# flag — would get a 200 and a run that quietly ignored it. Ruling 12b settles
# that a run declares its selector on three fixed axes and accepts no arbitrary
# predicate, and a silently-dropped key is exactly that predicate appearing to
# be honoured. `extra="forbid"` is what makes the refusal real; it publishes as
# `additionalProperties: false`, so the contract says so too.
class ResolutionRunIn(Schema):
    """Which postings this run should reach: a date range, a customer, an
    Event Type — in any combination, and any of them may be omitted.

    An omitted axis is unpinned rather than empty: a body naming nothing at all
    reaches every posting of this tenant that was never resolved. The date range
    is over the posting's own effective instant and is half-open — `[from, to)`
    — so running one month and then the next repairs each posting exactly once.

    A run reaches only postings whose status says they were never resolved, and
    that is a property of how the set is built rather than of what you send:
    there is no field here that could widen it to a posting already carrying a
    cost or a price, and none that could reach one whose charge was waived.

    Any other field is refused (`validation_error`). A run takes no condition of
    its own.
    """
    model_config = ConfigDict(extra="forbid")

    selected_from: Optional[datetime] = None
    selected_to: Optional[datetime] = None
    selected_customer_id: Optional[UUID] = None
    selected_event_type: str = Field(default="", max_length=100)


class ResolutionRunSelectorOut(Schema):
    """The three axes, as they were stated — echoed so the record of the act and
    the answer to the request cannot describe the same run differently."""
    selected_from: Optional[str] = None
    selected_to: Optional[str] = None
    selected_customer_id: Optional[str] = None
    selected_event_type: Optional[str] = None


class ResolutionRunOut(Schema):
    """What one run reached, and what it completed.

    `postings_examined` is how many never-resolved postings the run took up, and
    the three numbers under it account for all of them: a cost settled, a price
    resolved, or nothing — because nothing the tenant has since configured
    resolves that posting at the instant it happened. A posting can appear in
    both of the first two, so they do not sum to the total.

    `more_to_do` says the selector matched more postings than one run takes.
    Send the same body again: everything this run completed has left the set it
    selects from, so the next run continues where this one stopped.

    A run moves no money. It completes what was never resolved and records that
    it did; no invoice, credit note, charge or refund follows from one.
    """
    id: str
    #: When the run happened, which is when this record was created — a run
    #: record exists because a run happened, so there is no second instant.
    executed_at: str
    #: An immutable snapshot of the principal who ran it, taken at the moment of
    #: the act (ADR-004 §4), because a run cannot be undone and this is the only
    #: place the answer survives.
    actor_kind: str
    actor_id: str
    actor_display: str
    selector: ResolutionRunSelectorOut
    postings_examined: int
    costs_settled: int
    prices_resolved: int
    postings_left_unresolved: int
    more_to_do: bool


def resolution_run_out(run) -> dict:
    """One run on the wire, from the record that holds it."""
    return {
        "id": str(run.id),
        "executed_at": run.created_at.isoformat(),
        "actor_kind": run.actor_kind,
        "actor_id": run.actor_id,
        "actor_display": run.actor_display,
        "selector": run.selector,
        "postings_examined": run.postings_examined,
        "costs_settled": run.costs_settled,
        "prices_resolved": run.prices_resolved,
        "postings_left_unresolved": run.postings_left_unresolved,
        "more_to_do": run.more_to_do,
    }


# --- The three surfaces a Resolution Run projects onto (#364) ---------------
#
# ⚠ EVERY COUNT BELOW IS NAMED ON A DECLARED ROW, WHICH IS THE POINT OF
# DECLARING THEM. A `Schema` that does not name a key does not merely omit it —
# django-ninja DROPS it — so a completeness count attached in `queries.py`
# survives on an untyped rollup and vanishes from the one row a drift gate can
# see (#327, spec §24). These rows are typed precisely so that the surfaces
# whose subject is *a total that says what it left out* are the surfaces a gate
# can hold to it.
#
# None of the three publishes a mutating verb, and that is checked rather than
# asserted: the #82 audit sweep counts mutating routes on the live API and its
# expected number does not move for this commit.


class UnresolvedQueueRow(Schema):
    """One posting UBB could not resolve, and what says why.

    The amounts are the columns as they stand: `null` where UBB has no figure,
    never a zero and never a word. Which of the two readings a `null` takes is
    the status beside it — that is the whole of what the nullable columns and
    their statuses were built for, and a queue is exactly where a reader would
    otherwise total a column of blanks by eye.
    """
    usage_event_id: str
    effective_at: str
    customer_id: str
    event_type: str = ""
    provider: str = ""
    #: The denomination both amounts below are in. On the row because the
    #: totals are per currency and a reader has to be able to see which row
    #: belongs to which total.
    currency: str
    provider_cost_micros: Optional[int] = None
    #: Whether the supplier cost above is settled — and on this surface it is
    #: the reason the row is in the list at all, half the time.
    costing_status: CostingStatus
    #: WHICH INPUT DID NOT ARRIVE. Null unless the cost is unresolved. This is
    #: the recorded *why* the queue exists to show: a tenant who reads
    #: `cost_rate_missing` knows what to write, and one who reads
    #: `reported_cost_missing` knows they are waiting on a supplier.
    unresolved_reason: Optional[UnresolvedReason] = None
    billed_cost_micros: Optional[int] = None
    #: Whether the customer price above is settled. `unknown` is the other
    #: reason a row is here.
    #:
    #: ⚠ THE PRICE SIDE RECORDS NO REASON OF ITS OWN, AND THIS SURFACE REPORTS
    #: WHAT THE RECORD HOLDS RATHER THAN DERIVING ONE. The engine writes a
    #: reason for an unresolved COST and none for an unresolved price, so a
    #: finer answer here would be a second copy of the engine's branch logic
    #: living in a read surface, going stale silently. Coining a price-side
    #: reason is a value-set decision with a registry entry behind it, and it
    #: belongs to whoever changes what the recording path writes.
    pricing_status: PricingStatus


class UnresolvedQueueTotals(Schema):
    """What the queue has already cost, in one currency, and what it left out."""
    currency: str
    #: WHAT UBB HAS ALREADY PAID THE SUPPLIER for the calls in this queue —
    #: money out with no settled price against it. Over the whole filter, not
    #: over one page.
    provider_cost_micros: int
    #: How many queued postings that total could NOT include, because their own
    #: supplier cost is one UBB has not learned either. The total is a floor and
    #: this is how far short it may fall.
    unresolved_event_count: int
    #: How many postings the filter matched in this currency. Not a caveat —
    #: the size of the working list.
    queued_event_count: int


class PaginatedUnresolvedQueue(Paginated[UnresolvedQueueRow]):
    """Everything that went unresolved, with the reason the record holds."""
    #: What this list is and what its total is taken over, in the response's
    #: own words.
    basis: str
    totals: List[UnresolvedQueueTotals]


class ProjectedAdjustmentRow(Schema):
    """What recovering this filter would be worth for one customer."""
    customer_id: str
    currency: str
    #: The customer prices a Resolution Run over this filter would settle,
    #: summed. Zero where nothing would be recovered — and the count below is
    #: what separates *nothing to recover* from *nothing could be valued*.
    projected_billed_cost_micros: int
    #: How many unpriced postings this figure could NOT put a number on,
    #: because re-resolving them still resolves no price. A posting a recovery
    #: would waive, or one whose Event Type generates no customer revenue, is
    #: not counted here: neither is missing information.
    unpriced_event_count: int
    #: How many postings DID produce a figure.
    recoverable_event_count: int
    #: The postings behind the figure. Each one's Pricing Receipt — the record
    #: explaining what its amount would be and how — is at
    #: GET /metering/usage/{event_id}.
    usage_event_ids: List[str]


class ProjectedAdjustmentOut(Schema):
    """What a recovery would be worth, per customer — and nothing that bills.

    A projection, never an instruction. UBB does not back-bill: it tells you
    what completing these postings would be worth and leaves the decision, and
    the money movement, with you. There is no grand total across currencies,
    because adding two denominations produces a number in neither.
    """
    #: What the figures are, what they are not, and where the receipts are.
    basis: str
    rows: List[ProjectedAdjustmentRow]
    #: How many never-resolved postings this pass examined. One pass takes the
    #: same bounded number of postings a Resolution Run does, so the figures
    #: are what a run over the same filter would complete.
    postings_examined: int
    #: HOW MANY THE FILTER MATCHED BEYOND THAT BOUND — the second reason these
    #: figures are a floor, and a count rather than a flag for the reason every
    #: total on these surfaces carries one: "there is more" does not say how
    #: much more. Zero means the pass reached everything the filter matched.
    #: It cannot be attributed per customer, because working out whose postings
    #: they are is exactly the examination the bound refused. Narrow the date
    #: range to reach them.
    postings_not_examined: int


class WaivedLossRow(Schema):
    """What waiving cost this tenant in one currency."""
    currency: str
    #: THE SUPPLIER COST PAID ON WAIVED CALLS. See `basis` on the envelope for
    #: why this, and not a sum of prices: a waived charge never carried one.
    provider_cost_micros: int
    #: How many waived postings that figure could NOT include, because their
    #: own supplier cost is also one UBB never learned. The figure is a floor
    #: and this says how far short.
    unresolved_event_count: int
    #: How many postings in this currency were waived.
    waived_event_count: int


class WaivedLossOut(Schema):
    """What waiving has cost, as money, for the economic horizon."""
    #: The basis of the figure, stated rather than left to be inferred — a
    #: number a tenant reads as revenue lost is a number they will act on
    #: wrongly, and a waived charge has no revenue to lose.
    basis: str
    rows: List[WaivedLossRow]


class PaginatedBookPublishes(Paginated[BookPublishOut]):
    pass


class PaginatedPricingBooks(Paginated[PricingBookOut]):
    pass


class PaginatedCostBooks(Paginated[CostBookOut]):
    pass


class PaginatedRates(Paginated[RateOut]):
    pass


class DimensionDefIn(Schema):
    key: str = Field(max_length=64)
    # Both bounds are read off the registry's own vocabulary rather than typed,
    # so a future widening cannot ship a contract that refuses the slots it just
    # created. They are also the only two published values #276 moves: the
    # identifiers got longer and there are ten of them, and a bound that still
    # said six-and-eight would reject every one of the new ones. Neither is a
    # property rename and neither narrows anything a caller could already send.
    slot: str = Field(max_length=SLOT_MAX_LENGTH)
    scope: str = "event"
    max_cardinality: int = Field(default=100, ge=1, le=100_000)


class DimensionRegistryIn(Schema):
    dimensions: list[DimensionDefIn] = Field(min_length=1,
                                             max_length=len(SLOT_CHOICES))


class DimensionDefOut(Schema):
    key: str
    slot: str
    scope: str
    max_cardinality: int
    retired: bool


class DimensionRegistryOut(Schema):
    dimensions: list[DimensionDefOut]


class GroupingFieldValuesOut(Schema):
    key: str
    values: list[str]


class TaskTypeIn(Schema):
    key: str = Field(max_length=64)
    kind: str = "task"
    default_provider_cost_limit_micros: Optional[int] = Field(default=None, gt=0)
    required_dimensions: list[str] = Field(default_factory=list, max_length=6)


class TaskTypeRegistryIn(Schema):
    task_types: list[TaskTypeIn] = Field(min_length=1, max_length=100)


class TaskTypeOut(Schema):
    key: str
    kind: str
    default_provider_cost_limit_micros: Optional[int] = None
    required_dimensions: list[str]
    retired: bool


class TaskTypeRegistryOut(Schema):
    task_types: list[TaskTypeOut]


#: One enabled product, as the published contract carries it.
#:
#: The concept names the VALUE, not the array, so the marker sits on the item
#: rather than on the field — `tenant_product` is what a member of the list is,
#: and a marker on the array would be naming the wrong node. The item renders
#: `type: string`, which is what the applier requires; the input's array is
#: nullable and renders as an `anyOf`, but the item inside it is the same plain
#: string node either way.
#:
#: `tenant_product` is a CLOSED concept, so the export writes a real `enum`
#: here from `openapi/known-values.json`. This file spells no value: the set is
#: the registry's, and the agreement is structural rather than a coincidence
#: of spelling (#208, ADR-0006 §4).
TenantProduct = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "tenant_product"})]


class TenantConfigOut(Schema):
    name: str
    billing_mode: str
    products: list[TenantProduct]
    default_currency: str
    stripe_connected_account_id: str
    is_active: bool
    automatic_tax_enabled: bool
    # Tier-2 spend-control mode (read-only here; two positions: off|enforcing).
    enforcement_mode: str = "off"
    # Live-counter-maintenance switch (#46; narrowed by #149 §6.5, renamed by
    # #246): whether real-time counter maintenance (the synchronous
    # live-counter write and its crossing check, the reconciles' counter jobs,
    # the upward repair) is on. OFF = the honest durable-lane-latency posture;
    # the durable lane and the ack schema never change. Meaningful only when
    # enforcing.
    live_counter_maintenance_enabled: bool = True
    # Spend-safety defaults. min_balance_micros is the allowed OVERDRAFT
    # magnitude (balance may go to -min_balance before blocking), not a
    # positive floor. BillingTenantConfig-backed (#52) — the row
    # get_customer_min_balance reads.
    min_balance_micros: int = 0
    # Default COGS limit for new tasks (RiskConfig); null = no default —
    # absent an explicit start-call limit too, the task is uncapped.
    default_task_provider_cost_limit_micros: Optional[int] = None
    # Soft floor tenant default (#40, BillingTenantConfig): the wind-down
    # line (-value; negative places it above zero); null = no soft floor.
    soft_min_balance_micros: Optional[int] = None


class TenantConfigIn(Schema):
    billing_mode: Optional[str] = None
    products: Optional[list[TenantProduct]] = None
    automatic_tax_enabled: Optional[bool] = None
    # Tier-2 spend-control mode: two positions, off | enforcing (#42).
    enforcement_mode: Optional[str] = None
    # Live-counter-maintenance switch (#46, renamed by #246): flipping either
    # way enqueues an immediate per-tenant reconcile (OFF→ON re-seeds honest
    # counters from durable truth within minutes; ON→OFF has nothing to drain,
    # because nothing on the recording path was ever deferred). Omit =
    # unchanged. Never a contract change — only the latency profile.
    live_counter_maintenance_enabled: Optional[bool] = None
    # CUR-1: lowercase ISO code from core.money.SUPPORTED_CURRENCIES
    # (2-decimal only); 409 once any money exists for the tenant.
    default_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    # Spend-safety defaults. Omitting a key leaves it unchanged.
    # min_balance_micros is the allowed overdraft magnitude (>= 0; cannot be
    # null). For the two nullable defaults, sending an explicit null CLEARS
    # the default (distinguished from "omitted" via model_fields_set in the
    # endpoint); a value sets it.
    min_balance_micros: Optional[int] = None
    # Default COGS limit for new tasks (RiskConfig). Omit = unchanged;
    # null = no default.
    default_task_provider_cost_limit_micros: Optional[int] = None
    # Soft floor tenant default (#40, BillingTenantConfig): may be negative
    # (a wind-down line above zero); must keep the soft line at or above the
    # hard floor's. Omit = unchanged; null = no soft floor.
    soft_min_balance_micros: Optional[int] = None


class PlanIn(Schema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    access_fee_micros: int = Field(default=0, ge=0)
    per_seat_micros: int = Field(default=0, ge=0)
    # 1_000_000 == 1%. Capped at 1000% — a higher value is far more likely a
    # unit error (percent passed as micros) than a real commercial term.
    markup_percentage_micros: int = Field(default=0, ge=0, le=1_000_000_000)
    fixed_uplift_micros: int = Field(default=0, ge=0)
    interval: Literal["month", "year"] = "month"


class PlanOut(Schema):
    id: str
    key: str
    name: str
    access_fee_micros: int
    per_seat_micros: int
    markup_percentage_micros: int
    fixed_uplift_micros: int
    interval: str
    pricing_version: int
    archived_at: Optional[str] = None


class PlanListOut(Schema):
    plans: List[PlanOut]


class PlanUpdateIn(Schema):
    # None = leave the axis alone (0 is a meaningful value, not an omission).
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    access_fee_micros: Optional[int] = Field(default=None, ge=0)
    per_seat_micros: Optional[int] = Field(default=None, ge=0)
    markup_percentage_micros: Optional[int] = Field(default=None, ge=0, le=1_000_000_000)
    fixed_uplift_micros: Optional[int] = Field(default=None, ge=0)
    migrate_existing: bool = False


class AssignPlanIn(Schema):
    plan_key: str


# SubscriptionCancelIn / SubscribeIn / SeatsIn moved to
# apps/subscriptions/api/schemas.py with the lifecycle routes they serve
# (ADR-001: a product's api/ module may not import api.v1).


# Tenant billing periods / invoices — shared by the tenant mount and the
# billing mount's duplicate routes (#77): one definition, one component name
# in the merged OpenAPI document. Picking the canonical route home is a
# Stage-5 final-sweep item, not this restructure's.


class TenantBillingPeriodOut(Schema):
    id: str
    period_start: str
    period_end: str
    status: str
    total_usage_cost_micros: int
    event_count: int
    platform_fee_micros: int


def tenant_billing_period_out(p):
    """TenantBillingPeriodOut's serializer — one platform billing period."""
    return {
        "id": str(p.id),
        "period_start": p.period_start.isoformat(),
        "period_end": p.period_end.isoformat(),
        "status": p.status,
        "total_usage_cost_micros": p.total_usage_cost_micros,
        "event_count": p.event_count,
        "platform_fee_micros": p.platform_fee_micros,
    }


class TenantBillingPeriodListResponse(Paginated[TenantBillingPeriodOut]):
    pass


class TenantInvoiceOut(Schema):
    id: str
    billing_period_id: str
    stripe_invoice_id: str
    total_amount_micros: int
    status: str
    created_at: str


def tenant_invoice_out(inv):
    """TenantInvoiceOut's serializer — one platform invoice."""
    return {
        "id": str(inv.id),
        "billing_period_id": str(inv.billing_period_id),
        "stripe_invoice_id": inv.stripe_invoice_id,
        "total_amount_micros": inv.total_amount_micros,
        "status": inv.status,
        "created_at": inv.created_at.isoformat(),
    }


class TenantInvoiceListResponse(Paginated[TenantInvoiceOut]):
    pass


# ---------------------------------------------------------------------------
# The Event Type catalogue (#267) — the tenant's metered vocabulary, on the wire
# ---------------------------------------------------------------------------
#
# ADR-0007 §3 governs everything below: every name here ships under its FINAL
# name and final contract, even where the implementation behind it is only
# partly built. Nothing rated, resolved or measured reads this catalogue yet —
# slice 2 owns the declaration and slice 3 owns every behaviour the declaration
# selects — but a field broken a second time purely to repair the first break's
# placeholder is the cost that rule exists to refuse. Internal scaffolding is
# permitted; public scaffolding is not.
#
# THE MARKERS BELOW ARE THE CONCEPTS THIS CONTRACT ADVERTISES BEYOND THE
# TENANT'S PRODUCT LIST, and they come in BOTH KINDS. The kind is the whole
# difference in what a client sees:
#
#   closed (#267)  a real `enum`. UBB owns the whole value set, so the schema
#                  says so and a client may switch on it exhaustively.
#   open   (#268)  an `x-ubb-known-values` block beside an untouched
#                  `type: string`. The values are what UBB has MET, never what
#                  it will accept — so UBB meeting a new one is not a change to
#                  this document, which is exactly what an `enum` here would
#                  make it (ADR-0003).
#
# Nothing in this file chooses between them: the field names a concept and
# `tools/known_values/document.py::_representation` reads the kind off the
# registry. A field cannot agree with the registry by coincidence, because it
# spells nothing the registry could disagree with.
#
# The order that got them here is not a matter of taste either: the backend
# consumer was converted first — #262 for `costing_method` and
# `source_shape_id`, #263 for `source_kind` and `unit`, #266 for
# `amount_representation` — and marking a field before its consumer serves the
# concept is a RED export naming the field's JSON pointer, never a silent
# no-op.

#: How an Event Type's supplier COGS is derived. `closed` — UBB owns both
#: values — so the export writes a real `enum` here from
#: `openapi/known-values.json`. This file spells neither value: the set is the
#: registry's, and the agreement is structural rather than a coincidence of
#: spelling (#208, ADR-0006 §4).
CostingMethod = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "costing_method"})]

#: Where a declared number comes from, and how the Code Builder is to obtain
#: it. One concept on two schemas below — the declared quantity's and the
#: reported cost's — which is the sharing the registry's own summary describes
#: rather than a duplication: the mapping NARROWS the set, at the model, and a
#: narrowing restated here would be a second copy of a rule that already has an
#: owner. A narrowed value's refusal is the model's, served through the one
#: error dialect.
SourceKind = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "source_kind"})]

#: What an extracted supplier-cost number actually represents, so the
#: conversion to currency micros is generated once and exactly rather than
#: hand-written in a repository UBB never sees.
AmountRepresentation = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "amount_representation"})]

#: What one declared quantity is counted in. `open`, so the export writes an
#: `x-ubb-known-values` block here and NOT an `enum`: the five spellings UBB
#: holds are what it has met, and a tenant declaring a sixth is a normal
#: declaration rather than a refusal. UBB says a spelling looks like a near
#: miss and changes nothing — advice, at the model, never a constraint on the
#: wire (#193 §C5).
Unit = Annotated[str, Field(json_schema_extra={"x-ubb-concept": "unit"})]

#: Which provider response shape a tenant's declared paths are written against.
#: `open` for the reason a closed one would cost: every new supplier SDK, and
#: every materially changed response shape, would need a schema migration and a
#: re-generated client. UBB checks a path against a shape it recognises and
#: warns; a shape it does not recognise is a tenant's own wrapper, named by
#: `source_shape_label` beside it, and is supported rather than blocked.
SourceShapeId = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "source_shape_id"})]


class ProviderIn(Schema):
    """Declare a supplier. The key is the tenant's own handle for it."""
    key: str = Field(max_length=64)


class ProviderUpdateIn(Schema):
    """Rename or retire a supplier.

    There is no delete, here or anywhere: a Provider is retired and never
    removed, because supplier COGS attribution keys on its identity and
    deleting one would silently rewrite what historical postings say they cost.
    `retired` is a two-way switch rather than a timestamp a caller supplies —
    WHEN a supplier was retired is UBB's record of an act, not an input.
    """
    key: Optional[str] = Field(default=None, max_length=64)
    retired: Optional[bool] = None


class ProviderOut(Schema):
    key: str
    #: Null means live. A timestamp rather than a `retired` boolean, because a
    #: reader reconciling last quarter needs to know WHEN the supplier stopped
    #: being offered, and a boolean throws that away.
    retired_at: Optional[str] = None


def provider_out(provider):
    """ProviderOut's serializer — one supplier."""
    return {
        "key": provider.key,
        "retired_at": (provider.retired_at.isoformat()
                       if provider.retired_at else None),
    }


class PaginatedProviders(Paginated[ProviderOut]):
    pass


class EventCategoryIn(Schema):
    key: str = Field(max_length=64)


class EventCategoryOut(Schema):
    key: str


def event_category_out(category):
    """EventCategoryOut's serializer — one grouping."""
    return {"key": category.key}


class PaginatedEventCategories(Paginated[EventCategoryOut]):
    pass


class MeasurementIn(Schema):
    """One measurable quantity an Event Type produces.

    The code is the path segment rather than a body field: it is this
    declaration's identity beneath its Event Type, and a body that could
    disagree with the URL would make "which declaration is this" a question
    with two answers.
    """
    display_name: str = Field(default="", max_length=200)
    value_type: str = Field(max_length=16)
    #: `max_length` bounds how LONG a unit may be, which the column behind it
    #: already does. It says nothing about which spellings UBB knows, and the
    #: block beside it says nothing about which ones it accepts.
    unit: Unit = Field(max_length=64)
    required_for_costing: bool = False
    source_kind: SourceKind
    #: Canonical segments — `["usage_metadata", "prompt_token_count"]` — never
    #: an expression. The builder emits more than one language, and a stored
    #: expression is portable to none of them.
    source_path: List[str] = Field(default_factory=list)


class MeasurementOut(Schema):
    code: str
    display_name: str
    value_type: str
    unit: Unit
    required_for_costing: bool
    source_kind: SourceKind
    source_path: List[str]
    #: What UBB advises about this declaration, and will never act on. A near
    #: miss on the unit, and a path that looks inconsistent with the shape its
    #: Event Type declares. Advice is the entire product: UBB renders access
    #: syntax and never translates a supplier's own field name.
    advisories: List[str]


def measurement_out(measurement):
    """MeasurementOut's serializer — one declared quantity.

    `advisories` is computed rather than stored, and it reaches the wire
    because advice is the entire product of the checking UBB does here: it says
    a unit is a near miss, or a path looks inconsistent with the declared
    response shape, and it never edits either. A tenant who cannot see the
    advice gets the silence instead.
    """
    return {
        "code": measurement.code,
        "display_name": measurement.display_name,
        "value_type": measurement.value_type,
        "unit": measurement.unit,
        "required_for_costing": measurement.required_for_costing,
        "source_kind": measurement.source_kind,
        "source_path": list(measurement.source_path),
        "advisories": list(measurement.declaration_advisories()),
    }


class PaginatedMeasurements(Paginated[MeasurementOut]):
    pass


class ReportedCostMappingIn(Schema):
    """Where a supplier's own cost figure is read from. One per Event Type.

    A sibling of the declared quantities rather than one of them: money with a
    currency does not fit a shape built for a quantity and its unit.
    """
    source_kind: SourceKind
    amount_representation: AmountRepresentation
    source_path: List[str] = Field(default_factory=list)
    #: Where the currency is read from, when it travels beside the amount.
    #: Exclusive with `currency` below — exactly one of the two, because an
    #: amount whose currency is undeclared is an amount that can be
    #: reinterpreted under the wrong one.
    currency_path: List[str] = Field(default_factory=list)
    #: The pinned currency, when the supplier always reports in one.
    currency: str = Field(default="", max_length=3)


class ReportedCostMappingOut(Schema):
    source_kind: SourceKind
    amount_representation: AmountRepresentation
    source_path: List[str]
    currency_path: List[str]
    currency: str
    #: What the caller's own code must pass, because UBB cannot read it off the
    #: supplier's response. Empty for a cost that arrives on the response,
    #: which is the point of serving it at all: a declaration answering the
    #: same for both would tell a generator nothing.
    required_runtime_parameters: List[str]
    advisories: List[str]


def reported_cost_mapping_out(mapping):
    """ReportedCostMappingOut's serializer — where a supplier's cost is read."""
    return {
        "source_kind": mapping.source_kind,
        "amount_representation": mapping.amount_representation,
        "source_path": list(mapping.source_path),
        "currency_path": list(mapping.currency_path),
        "currency": mapping.currency,
        "required_runtime_parameters":
            list(mapping.required_runtime_parameters()),
        "advisories": list(mapping.declaration_advisories()),
    }


class EventTypeIn(Schema):
    key: str = Field(max_length=100)
    costing_method: CostingMethod
    #: The supplier's key, or absent for internal work that has no supplier. A
    #: fictitious Provider is a defect, not a workaround.
    provider_key: Optional[str] = Field(default=None, max_length=64)
    category_key: Optional[str] = Field(default=None, max_length=64)
    source_shape_id: SourceShapeId = Field(default="", max_length=100)
    #: Deliberately UNMARKED, and it is the pair with the field above that
    #: makes the point: this is prose a human typed for a wrapper of their own,
    #: registered `free_text`, and a concept with no values contributes nothing
    #: to the contract. A block here would advertise a set that does not exist.
    source_shape_label: str = Field(default="", max_length=200)


class EventTypeUpdateIn(Schema):
    """Every field optional: an absent field is untouched, not cleared.

    The two satellites detach on an EMPTY STRING rather than on a null, which
    is the one place this shape has to be explicit: "no supplier" is a state a
    tenant reaches deliberately, and a null that meant "leave alone" would
    leave them no way to say it.

    **The key is absent on purpose.** It is the name a tenant's own recorded
    events arrive under, so renaming one would silently re-point every posting
    made against it — the same objection that keeps supplier cost resolution on
    the Provider's identity rather than on its handle, arriving at the opposite
    answer because here the handle IS the identity. Withdraw and re-declare, or
    map the old name through the quarantine that already exists for a name UBB
    does not recognise.
    """
    costing_method: Optional[CostingMethod] = None
    provider_key: Optional[str] = Field(default=None, max_length=64)
    category_key: Optional[str] = Field(default=None, max_length=64)
    source_shape_id: Optional[SourceShapeId] = Field(default=None,
                                                     max_length=100)
    source_shape_label: Optional[str] = Field(default=None, max_length=200)


class EventTypeOut(Schema):
    key: str
    costing_method: CostingMethod
    provider_key: Optional[str] = None
    category_key: Optional[str] = None
    source_shape_id: SourceShapeId
    source_shape_label: str
    #: `draft` or `published`. Deliberately UNMARKED: `declaration_status`
    #: declares no `openapi` consumer in the registry, and the applier refuses
    #: a marker for a concept that contributes nothing rather than emitting an
    #: empty one. A field is marked by the ticket that declares its concept's
    #: contract consumer, never by one passing nearby. The FIELD is still final
    #: under ADR-0007 §3 — gaining an `enum` later is additive, and its values
    #: are already the registry's.
    declaration_status: str
    #: Bumped by each publication that pins something different. A tenant's
    #: generated code was generated against a revision, so the revision is what
    #: tells them their integration has become a reading of a contract that
    #: moved.
    published_revision: int
    published_at: Optional[str] = None
    #: What stands between this declaration and publication. Empty means
    #: publishable. Served rather than stored, so two encodings of one fact
    #: cannot disagree.
    publication_blockers: List[str]
    #: The parts travel with the root because they ARE the declaration, and a
    #: nested list is not the banned "unwrapped list" the envelope rule is
    #: about: this is one entity's own representation, not an entity-list
    #: endpoint. Splitting it would let a tenant read the quantities and the
    #: root either side of a publication and generate against a declaration
    #: that never existed.
    measurements: List[MeasurementOut]
    reported_cost_mapping: Optional[ReportedCostMappingOut] = None


def event_type_out(event_type):
    """EventTypeOut's serializer — one whole declaration.

    `publication_blockers` is served rather than stored, so the two encodings
    of one fact cannot disagree, and the reverse one-to-one is read through
    `getattr` because a missing part raises rather than answering `None`.
    """
    mapping = getattr(event_type, REPORTED_COST_MAPPING, None)
    return {
        "key": event_type.key,
        "costing_method": event_type.costing_method,
        "provider_key": (event_type.provider.key
                         if event_type.provider_id else None),
        "category_key": (event_type.category.key
                         if event_type.category_id else None),
        "source_shape_id": event_type.source_shape_id,
        "source_shape_label": event_type.source_shape_label,
        "declaration_status": event_type.declaration_status,
        "published_revision": event_type.published_revision,
        "published_at": (event_type.published_at.isoformat()
                         if event_type.published_at else None),
        "publication_blockers": list(event_type.publication_blockers()),
        "measurements": [measurement_out(m)
                         for m in event_type.measurements.all()],
        "reported_cost_mapping": (reported_cost_mapping_out(mapping)
                                  if mapping is not None else None),
    }


class PaginatedEventTypes(Paginated[EventTypeOut]):
    pass
