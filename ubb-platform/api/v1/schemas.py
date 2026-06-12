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
    usage_metrics: Optional[dict] = None
    pricing_provenance: Optional[dict] = None
    uncosted_metrics: list[str] = []
    service_id: str = ""
    agent_id: str = ""


class BalanceResponse(Schema):
    balance_micros: int
    currency: str


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


class DebitRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)


class CreditRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    source: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)


class DebitCreditResponse(Schema):
    new_balance_micros: int
    transaction_id: str


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
    usage_line_item_group_by: str = ""


class PostpaidConfigOut(Schema):
    usage_line_item_group_by: str


class RateCardIn(Schema):
    card_type: str
    metric_name: str = Field(min_length=1, max_length=100)
    provider: str = Field(default="", max_length=100)
    event_type: str = Field(default="", max_length=100)
    dimensions: dict = Field(default_factory=dict)
    pricing_model: str = "per_unit"
    rate_per_unit_micros: int = Field(default=0, ge=0)
    unit_quantity: int = Field(default=1_000_000, gt=0)
    fixed_micros: int = Field(default=0, ge=0)
    tiers: list = Field(default_factory=list)
    currency: str = Field(default="usd", max_length=3)
    product_id: str = Field(default="", max_length=100)
    customer_id: Optional[UUID] = None


class RateCardUpdateIn(Schema):
    card_type: Optional[str] = None
    metric_name: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
    event_type: Optional[str] = Field(default=None, max_length=100)
    dimensions: Optional[dict] = None
    pricing_model: Optional[str] = None
    rate_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: Optional[int] = Field(default=None, gt=0)
    fixed_micros: Optional[int] = Field(default=None, ge=0)
    tiers: Optional[list] = None  # None (or omitted) = keep current tiers
    currency: Optional[str] = Field(default=None, max_length=3)
    product_id: Optional[str] = Field(default=None, max_length=100)
    customer_id: Optional[UUID] = None


class RateCardOut(Schema):
    id: str
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
    tiers: list
    currency: str
    product_id: str
    customer_id: Optional[str] = None
    valid_from: str
    valid_to: Optional[str] = None


class RateCardBatchIn(Schema):
    cards: list[RateCardIn]


class TenantConfigOut(Schema):
    name: str
    billing_mode: str
    products: list[str]
    require_cost_card_coverage: bool
    default_currency: str
    stripe_connected_account_id: str
    is_active: bool


class TenantConfigIn(Schema):
    billing_mode: Optional[str] = None
    products: Optional[list[str]] = None
    require_cost_card_coverage: Optional[bool] = None


class PlanIn(Schema):
    key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=255)
    access_fee_micros: int = Field(default=0, ge=0)
    per_seat_micros: int = Field(default=0, ge=0)
    interval: str = "month"
    usage_mode: str = "invoice_item"


class PlanOut(Schema):
    id: str
    key: str
    name: str
    access_fee_micros: int
    per_seat_micros: int
    interval: str
    usage_mode: str


class SubscribeIn(Schema):
    plan_key: str = Field(min_length=1, max_length=64)
    seats: int = Field(default=0, ge=0)


class SeatsIn(Schema):
    seats: int = Field(ge=0)
