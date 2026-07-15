from datetime import datetime
from uuid import UUID
from typing import Optional

from ninja import Schema, Field
from pydantic import field_validator


class PreCheckRequest(Schema):
    customer_id: UUID
    start_run: bool = False
    run_metadata: Optional[dict] = None
    external_run_id: str = ""


class PreCheckResponse(Schema):
    allowed: bool
    reason: Optional[str] = None
    balance_micros: Optional[int] = None
    run_id: Optional[str] = None
    cost_limit_micros: Optional[int] = None
    hard_stop_balance_micros: Optional[int] = None


class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)
    provider_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
    billed_cost_micros: Optional[int] = Field(default=None, ge=0, le=999_999_999_999)
    usage_metrics: Optional[dict[str, int]] = None
    units: Optional[int] = Field(default=None, ge=0)

    @field_validator("usage_metrics")
    @classmethod
    def usage_metrics_values_nonnegative(cls, v):
        if v is None:
            return v
        negative = [k for k, val in v.items() if val < 0]
        if negative:
            raise ValueError(
                f"usage_metrics values must be >= 0; negative metrics: {negative}")
        return v
    currency: Optional[str] = Field(default=None, max_length=3)
    tags: Optional[dict[str, str]] = None
    run_id: Optional[UUID] = None
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
    product_id: Optional[str] = Field(default=None, max_length=100)
    # When the usage economically happened. Must be timezone-aware; bounded by
    # the tenant's backfill window. Omitted = now (server clock).
    effective_at: Optional[datetime] = None


class UsageBatchRequest(Schema):
    events: list[RecordUsageRequest] = Field(min_length=1, max_length=100)


class UsageBatchResponse(Schema):
    # Per-item results, positionally aligned with the request's events[].
    # Success items mirror the single-call success body plus {"ok": true};
    # error items mirror the single-call error bodies plus {"ok": false}.
    results: list[dict]
    succeeded: int
    failed: int


class IngestEventIn(RecordUsageRequest):
    """One item in an async ingest batch (POST /usage/ingest). Field-for-field
    identical to RecordUsageRequest (the sync batch item) — a distinct name so
    the ingest request/response schemas are independently versionable."""
    pass


class IngestBatchRequest(Schema):
    events: list[IngestEventIn] = Field(min_length=1, max_length=1000)


class IngestBatchResponse(Schema):
    # Per-item results, positionally aligned with the request's events[]. Each
    # entry: {accepted, estimated_cost_micros, stop, stop_reason, stop_scope,
    # rejected, reason, mode, duplicate_suspect} plus (for accepted
    # sync_fallback items) event_id — kept as `dict` (not a strict sub-schema)
    # to match the UsageBatchResponse precedent above.
    results: list[dict]
    accepted: int
    rejected: int


class RecordUsageResponse(Schema):
    event_id: str
    new_balance_micros: Optional[int] = None
    suspended: bool
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    units: Optional[int] = None
    run_id: Optional[str] = None
    run_total_cost_micros: Optional[int] = None
    hard_stop: bool = False
    # Tier-2 (D14): customer-wide cooperative spend stop on a 200 body. `stop`
    # means "halt this customer's runs at the next safe boundary" (the event
    # was still recorded + charged). Distinct from `hard_stop` (per-run/task
    # 429, run already killed) and `suspended` (durable owner status).
    stop: bool = False
    stop_reason: Optional[str] = None
    stop_scope: Optional[str] = None
    usage_metrics: Optional[dict] = None
    pricing_provenance: Optional[dict] = None
    uncosted_metrics: list[str] = []
    service_id: str = ""
    agent_id: str = ""


class BalanceResponse(Schema):
    balance_micros: int
    currency: str
    # F4.3 (additive): grant visibility. None when the wallet has no grants
    # context (kept optional for response back-compat).
    promo_micros: Optional[int] = None
    expiring_micros: Optional[int] = None
    next_expiry_at: Optional[str] = None


class UsageEventOut(Schema):
    id: UUID
    request_id: str
    event_type: str = ""
    provider: str = ""
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    units: Optional[int] = None
    metadata: dict
    effective_at: str


class UsageEventDetailOut(Schema):
    # Full pricing receipt for one event — the audit lookup. pricing_provenance
    # is the recorded "why this amount" (engine version, price source, per-metric
    # card id, tier-by-tier breakdown) omitted from the lean list view.
    id: UUID
    request_id: str
    idempotency_key: str
    event_type: str = ""
    provider: str = ""
    product_id: str = ""
    service_id: str = ""
    agent_id: str = ""
    units: Optional[int] = None
    currency: str = "usd"
    provider_cost_micros: int
    billed_cost_micros: int
    usage_metrics: dict = {}
    pricing_provenance: dict = {}
    tags: Optional[dict] = None
    metadata: dict = {}
    run_id: Optional[str] = None
    effective_at: str
    created_at: str


class ConfigureAutoTopUpRequest(Schema):
    is_enabled: bool
    trigger_threshold_micros: int = Field(ge=0)
    top_up_amount_micros: int = Field(gt=0)

    @field_validator("top_up_amount_micros")
    @classmethod
    def top_up_amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class CreateTopUpRequest(Schema):
    amount_micros: int = Field(gt=0)
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class PaginatedUsageResponse(Schema):
    data: list[UsageEventOut]
    next_cursor: Optional[str] = None
    has_more: bool


class WithdrawRequest(Schema):
    amount_micros: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=500)
    description: str = ""

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class RefundRequest(Schema):
    usage_event_id: UUID
    reason: str = ""
    idempotency_key: str = Field(min_length=1, max_length=500)


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
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


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


class PaginatedGrants(Schema):
    data: list[GrantOut]
    next_cursor: Optional[str] = None
    has_more: bool


class TenantMarkupIn(Schema):
    markup_percentage_micros: int = Field(default=0, ge=0)
    fixed_uplift_micros: int = Field(default=0, ge=0)


class TenantMarkupOut(Schema):
    markup_percentage_micros: int
    fixed_uplift_micros: int


class CloseRunResponse(Schema):
    run_id: str
    status: str
    total_cost_micros: int
    event_count: int


class UsageAnalyticsResponse(Schema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    usage_markup_margin_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]
    by_customer: list[dict]
    by_product: list[dict]
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


class BudgetConfigIn(Schema):
    cap_micros: int = Field(ge=0)
    enforce_mode: str = "advisory"
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
    # Both are null-able overrides (PUT = full replace, so null clears the
    # override): null min_balance_micros = inherit the tenant default; null
    # topup_grant_expiry_days = top-ups never expire.
    min_balance_micros: Optional[int] = None
    topup_grant_expiry_days: Optional[int] = None


class CustomerBillingProfileOut(Schema):
    min_balance_micros: Optional[int] = None
    topup_grant_expiry_days: Optional[int] = None


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
    metric_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    dimensions: dict = Field(default_factory=dict)
    pricing_model: str = "per_unit"
    rate_per_unit_micros: int = Field(default=0, ge=0)
    unit_quantity: int = Field(default=1_000_000, gt=0)
    fixed_micros: int = Field(default=0, ge=0)
    product_id: str = Field(default="", max_length=100)


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


class RateChangeIn(Schema):
    """One reprice in a publish. Match keys (metric_name/provider/event_type/
    dimensions) locate the active rate; the remaining (nullable) fields, when
    present, override it in the new version."""
    metric_name: str
    provider: str = ""
    event_type: str = ""
    dimensions: dict = Field(default_factory=dict)
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
    metric_name: str
    provider: str
    event_type: str
    dimensions: dict
    pricing_model: str
    rate_per_unit_micros: int
    unit_quantity: int
    fixed_micros: int
    currency: str
    product_id: str
    valid_from: str
    valid_to: Optional[str] = None


class TenantConfigOut(Schema):
    name: str
    billing_mode: str
    products: list[str]
    require_cost_card_coverage: bool
    default_currency: str
    stripe_connected_account_id: str
    is_active: bool
    automatic_tax_enabled: bool
    # Tier-2 spend-control mode (read-only here; off|advisory|enforcing).
    enforcement_mode: str = "off"
    # Spend-safety caps (tenant defaults). min_balance_micros is the allowed
    # OVERDRAFT magnitude (balance may go to -min_balance before blocking), not
    # a positive floor. run_cost_limit/hard_stop_balance are null = no cap.
    min_balance_micros: int = 0
    run_cost_limit_micros: Optional[int] = None
    hard_stop_balance_micros: Optional[int] = None
    # Per-task cost ceiling (lives on RiskConfig); null = no cap.
    max_cost_per_task_micros: Optional[int] = None


class TenantConfigIn(Schema):
    billing_mode: Optional[str] = None
    products: Optional[list[str]] = None
    require_cost_card_coverage: Optional[bool] = None
    automatic_tax_enabled: Optional[bool] = None
    # Tier-2 spend-control mode: off | advisory | enforcing.
    enforcement_mode: Optional[str] = None
    # CUR-1: lowercase ISO code from tenants.models.SUPPORTED_CURRENCIES
    # (2-decimal only); 409 once any money exists for the tenant.
    default_currency: Optional[str] = Field(default=None, min_length=3, max_length=3)
    # Spend-safety caps. Omitting a key leaves it unchanged. min_balance_micros
    # is the allowed overdraft magnitude (>= 0; cannot be null). For the two
    # nullable caps, sending an explicit null CLEARS the cap (distinguished from
    # "omitted" via model_fields_set in the endpoint); a positive value sets it.
    min_balance_micros: Optional[int] = None
    run_cost_limit_micros: Optional[int] = None
    hard_stop_balance_micros: Optional[int] = None
    # Per-task cost ceiling (RiskConfig). Omit = unchanged; null = no cap.
    max_cost_per_task_micros: Optional[int] = None


class PlanIn(Schema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    access_fee_micros: int = Field(default=0, ge=0)
    per_seat_micros: int = Field(default=0, ge=0)
    interval: str = "month"


class PlanOut(Schema):
    id: str
    key: str
    name: str
    access_fee_micros: int
    per_seat_micros: int
    interval: str


class PlanUpdateIn(Schema):
    # None = leave the axis alone (0 is a meaningful value, not an omission).
    access_fee_micros: Optional[int] = Field(default=None, ge=0)
    per_seat_micros: Optional[int] = Field(default=None, ge=0)
    migrate_existing: bool = False


class SubscriptionCancelIn(Schema):
    at_period_end: bool = True


class SubscribeIn(Schema):
    plan_key: str = Field(min_length=1, max_length=64)
    seats: int = Field(default=0, ge=0)


class SeatsIn(Schema):
    seats: int = Field(ge=0)
