from datetime import datetime
from uuid import UUID
from typing import Annotated, List, Literal, Optional

from ninja import Schema, Field
from pydantic import field_validator

from api.v1.pagination import Paginated
from apps.platform.event_types.models import REPORTED_COST_MAPPING
from apps.platform.grouping_fields.models import SLOT_CHOICES, SLOT_MAX_LENGTH
from core.exceptions import MisalignedAmount
from core.money import DEFAULT_CURRENCY, assert_aligned, minor_units

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
    # Declared dimension values at task/subtask scope, inherited by every event
    # in the tree (design D6). Keys must be declared; values are cardinality-
    # capped on write.
    dimensions: dict = Field(default_factory=dict)


class PreCheckResponse(Schema):
    allowed: bool
    # reason vocabulary: insufficient_funds | account_closed |
    # customer_stopped | soft_floor_reached (#40 — past the wind-down line,
    # NEW top-level starts refuse; subtask starts under an active parent
    # pass) | rate_limit_exceeded | budget-cap reasons |
    # concurrency_limit | cost_coverage_required (a resolved COGS limit
    # requires Tenant.require_cost_card_coverage) | parent_task_not_active |
    # subtask_depth_exceeded (subtask registration refusals, #38 — refusing
    # work that hasn't happened, never a usage report).
    reason: Optional[str] = None
    balance_micros: Optional[int] = None
    task_id: Optional[str] = None
    # Set when the started unit is a subtask — the parent it registered under.
    parent_task_id: Optional[str] = None
    provider_cost_limit_micros: Optional[int] = None
    task_type: Optional[str] = None
    subtask_type: Optional[str] = None


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
    provider_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
    billed_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
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
    # Declared EVENT-scoped dimension values (design D1/D6). Keys must be in the
    # tenant's GroupingField registry and declared at event scope; task- and
    # subtask-scoped values are set at the start-gate and inherited, not sent
    # here. Values are cardinality-capped on write.
    dimensions: dict = Field(default_factory=dict)
    # When the usage economically happened. Must be timezone-aware; bounded by
    # the tenant's backfill window. Omitted = now (server clock).
    effective_at: Optional[datetime] = None


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


class RecordUsageResponse(Schema):
    event_id: str
    new_balance_micros: Optional[int] = None
    suspended: bool
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    task_id: Optional[str] = None
    # Set when the named unit is a subtask — its parent task (#38).
    parent_task_id: Optional[str] = None
    # The named unit's running totals, denominationally explicit — billed
    # (what you charge) and provider (what the job burns; only this one races
    # the COGS limit). A subtask's spend also rolls up into its parent's
    # totals (containment); the parent's totals ride its own acks/events.
    task_total_billed_cost_micros: Optional[int] = None
    task_total_provider_cost_micros: Optional[int] = None
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
    pricing_provenance: Optional[dict] = None
    uncosted_metrics: list[str] = []
    dim2: str = ""
    dim3: str = ""


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
    billed_cost_micros: Optional[int] = None
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
        "billed_cost_micros": e.billed_cost_micros,
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
    # is the recorded "why this amount" (engine version, price source, the card
    # id that priced each named quantity, tier-by-tier breakdown) omitted from
    # the lean list view.
    id: UUID
    request_id: str
    idempotency_key: str
    event_type: str = ""
    provider: str = ""
    dim1: str = ""
    dim2: str = ""
    dim3: str = ""
    currency: str = "usd"
    provider_cost_micros: int
    billed_cost_micros: int
    # The quantities this posting was measured by, keyed by declared code
    # (#274) — the field the status below has always been about.
    measurements: dict = {}
    # What the bag above MEANS when it is empty — pruned, never applicable, or
    # genuinely there and empty. Without it an expired payload and a synthetic
    # charge are one indistinguishable `{}`, and a reader that defaults on an
    # empty bag shows an end customer "no usage" for detail that was removed on
    # schedule. Required rather than optional: every posting has an answer.
    measurements_status: MeasurementsStatus
    pricing_provenance: dict = {}
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
    #  provider_cost_micros, arrived_after}], event_count,
    #  total_billed_cost_micros, total_provider_cost_micros}.
    # Soft-floor entries are crossed/cleared MARKER rows: events always [].
    # totals_per_limit: {limit: {billed_cost_micros, provider_cost_micros,
    #  event_count}} — both denominations, per tripping limit, covering
    # exactly the itemized events of the episodes shown.
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


class CloseTaskResponse(Schema):
    task_id: str
    # Set when the closed unit is a subtask (#38). Closing a PARENT
    # auto-completes its active subtasks; closing a subtask closes it alone.
    parent_task_id: Optional[str] = None
    status: str
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    event_count: int


class TaskOut(Schema):
    task_id: str
    parent_task_id: Optional[str] = None
    task_type: str = ""
    subtask_type: str = ""
    status: str
    total_provider_cost_micros: int
    total_billed_cost_micros: int
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
        "total_billed_cost_micros": t.total_billed_cost_micros,
        "event_count": t.event_count,
        "provider_cost_limit_micros": t.provider_cost_limit_micros,
        # A FREE-FORM OBJECT, so its keys are data and not contract: the
        # published document types this as an object and names no property, and
        # #276 renaming the columns therefore renames the keys here without
        # touching the schema. That is also why widening it to ten costs the
        # contract nothing. Ticket 20 replaces the physical slot with the
        # tenant's own declared key, which is the shape the read side is being
        # moved to match.
        "dimensions": {s: getattr(t, s) for s in
                       (f"grouping_field_{i}" for i in range(1, 11))
                       if getattr(t, s)},
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
    usage_markup_margin_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]
    by_customer: list[dict]
    by_task_type: list[dict]
    by_tag: list[dict]
    breakdowns: dict = {}


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
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
    total_billed_cost_micros: int
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


class RateIn(Schema):
    """A single Rate added under a book. card_type and currency are inherited
    from the book, so they are NOT accepted here (the book owns them)."""
    measurement_key: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    task_type: str = Field(default="", max_length=64)
    subtask_type: str = Field(default="", max_length=64)
    dim1: str = Field(default="", max_length=100)
    dim2: str = Field(default="", max_length=100)
    dim3: str = Field(default="", max_length=100)
    dim4: str = Field(default="", max_length=100)
    dim5: str = Field(default="", max_length=100)
    dim6: str = Field(default="", max_length=100)
    pricing_model: str = "per_unit"
    rate_per_unit_micros: int = Field(default=0, ge=0)
    unit_quantity: int = Field(default=1_000_000, gt=0)
    fixed_micros: int = Field(default=0, ge=0)


class BookIn(Schema):
    card_type: str
    provider_key: str = Field(default="", max_length=100)
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(default="", max_length=255)
    # CUR-1: omitted/None defaults to the tenant's default_currency; an
    # explicit value must MATCH the tenant currency (422 otherwise).
    currency: Optional[str] = Field(default=None, max_length=3)
    is_default: bool = False


class BookOut(Schema):
    id: str
    card_type: str
    provider_key: str
    key: str
    name: str
    currency: str
    version: int
    is_default: bool


def book_out(b):
    """BookOut's serializer — a rate-card book (the container)."""
    return {
        "id": str(b.id),
        "card_type": b.card_type,
        "provider_key": b.provider_key,
        "key": b.key,
        "name": b.name,
        "currency": b.currency,
        "version": b.version,
        "is_default": b.is_default,
    }


class RateChangeIn(Schema):
    """One reprice in a publish. Match keys (measurement_key plus the ten
    selector columns — provider/event_type/task_type/subtask_type/dim1..
    dim6) locate the active rate; the remaining (nullable) fields, when
    present, override it in the new version."""
    measurement_key: str
    provider: str = ""
    event_type: str = ""
    task_type: str = ""
    subtask_type: str = ""
    dim1: str = ""
    dim2: str = ""
    dim3: str = ""
    dim4: str = ""
    dim5: str = ""
    dim6: str = ""
    pricing_model: Optional[str] = None
    rate_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: Optional[int] = Field(default=None, gt=0)
    fixed_micros: Optional[int] = Field(default=None, ge=0)


class PublishIn(Schema):
    changes: list[RateChangeIn]


class AssignIn(Schema):
    rate_card_id: UUID


class RateOut(Schema):
    id: str
    rate_card_id: str
    lineage_id: str
    card_type: str
    measurement_key: str
    provider: str
    event_type: str
    task_type: str
    subtask_type: str
    dim1: str
    dim2: str
    dim3: str
    dim4: str
    dim5: str
    dim6: str
    pricing_model: str
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    currency: str
    valid_from: str
    valid_to: Optional[str] = None


#: THE WHOLE OF THE PROPERTY/COLUMN MISMATCH, IN ONE PLACE.
#:
#: #276 renamed the rate's slot columns to the canonical noun and deliberately
#: renamed no published property — its acceptance criteria forbid it. So six
#: published names now sit over six differently-named columns, and this dict is
#: the join.
#:
#: **NO TICKET IN SLICE 2 CLOSES THIS.** The posting's own slot properties go in
#: ticket 20, which replaces them with one object keyed by the tenant's declared
#: key; the rate's are not in that ticket, not in ticket 21 (which renames the
#: Grouping Field route family), and not in any other. The rate entity, its book
#: and its selector list are all rebuilt in **slice 4** — the same slice that
#: owns the retired words still standing on this model — and that is where the
#: join below is deleted rather than edited. Saying so here is the point: a
#: reader who assumes the next ticket tidies this will not find it there.
#:
#: Six, not ten. A rate can hold ten slots; the contract can name six. The four
#: without an entry here are unreachable from outside — a reprice body leaves
#: them at "", which matches a rate that leaves them unpinned — so a rate pinned
#: on slot seven can be written server-side and never repriced through the API.
#: That gap arrives with this ticket and leaves with slice 4.
SLOT_PROPERTY_COLUMNS = {f"dim{i}": f"grouping_field_{i}" for i in range(1, 7)}


def rate_change_body(change: dict) -> dict:
    """One reprice body with its slot properties renamed to the columns.

    `BookService.publish` matches an active rate on `Rate.SELECTORS`, which are
    column names. Handing it the request body untranslated would match every
    slot against "" and silently reprice the wrong rate — or, more often, fail
    to find one at all and abort the publish.
    """
    return {SLOT_PROPERTY_COLUMNS.get(name, name): value
            for name, value in change.items()}


def rate_out(r):
    """RateOut's serializer — one rate version under a book."""
    return {
        "id": str(r.id),
        "rate_card_id": str(r.rate_card_id) if r.rate_card_id else None,
        "lineage_id": str(r.lineage_id),
        "card_type": r.card_type,
        "measurement_key": r.measurement_key,
        "provider": r.provider,
        "event_type": r.event_type,
        "task_type": r.task_type,
        "subtask_type": r.subtask_type,
        **{name: getattr(r, column)
           for name, column in SLOT_PROPERTY_COLUMNS.items()},
        "pricing_model": r.pricing_model,
        "rate_per_unit_micros": r.rate_per_unit_micros,
        "unit_quantity": r.unit_quantity,
        "fixed_micros": r.fixed_micros,
        "currency": r.currency,
        "valid_from": r.valid_from.isoformat(),
        "valid_to": r.valid_to.isoformat() if r.valid_to else None,
    }


class PaginatedBooks(Paginated[BookOut]):
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


class DimensionValuesOut(Schema):
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
    require_cost_card_coverage: bool
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
    require_cost_card_coverage: Optional[bool] = None
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
