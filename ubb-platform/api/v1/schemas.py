from uuid import UUID
from typing import Optional

from ninja import Schema, Field
from pydantic import ConfigDict, field_validator


def _to_camel(name: str) -> str:
    """Convert snake_case to camelCase for pydantic alias generation."""
    parts = name.split("_")
    return parts[0] + "".join(p.capitalize() for p in parts[1:] if p)


class CamelSchema(Schema):
    """Base schema that outputs camelCase field names in JSON and OpenAPI spec."""
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
    )


class PreCheckRequest(CamelSchema):
    customer_id: UUID
    start_run: bool = False
    run_metadata: Optional[dict] = None
    external_run_id: str = ""


class PreCheckResponse(CamelSchema):
    allowed: bool
    reason: Optional[str] = None
    balance_micros: Optional[int] = None
    run_id: Optional[str] = None
    cost_limit_micros: Optional[int] = None
    hard_stop_balance_micros: Optional[int] = None


class RecordUsageRequest(CamelSchema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    pricing_card: str = Field(min_length=1, max_length=255)
    usage_metrics: dict[str, int] = Field(default_factory=dict)
    group: Optional[str] = Field(default=None, max_length=255)
    run_id: Optional[UUID] = None

    @field_validator("usage_metrics")
    @classmethod
    def usage_metrics_values_non_negative(cls, v):
        if v is not None:
            if not v:
                raise ValueError("usage_metrics must not be empty")
            for key, val in v.items():
                if not isinstance(val, int) or isinstance(val, bool):
                    raise ValueError(f"Metric '{key}' must be an integer")
                if val < 0:
                    raise ValueError(f"Metric '{key}' must be >= 0")
        return v


class RecordUsageResponse(CamelSchema):
    event_id: str
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    run_id: Optional[str] = None
    run_total_cost_micros: Optional[int] = None
    hard_stop: bool = False


class BalanceResponse(CamelSchema):
    balance_micros: int
    currency: str


class UsageEventOut(CamelSchema):
    id: UUID
    request_id: str
    cost_micros: int
    provider: str
    card_slug: str
    card_name: str
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    effective_at: str


class ConfigureAutoTopUpRequest(CamelSchema):
    is_enabled: bool
    trigger_threshold_micros: int = Field(ge=0)
    top_up_amount_micros: int = Field(gt=0)

    @field_validator("top_up_amount_micros")
    @classmethod
    def top_up_amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class CreateTopUpRequest(CamelSchema):
    amount_micros: int = Field(gt=0)
    success_url: str = Field(min_length=1)
    cancel_url: str = Field(min_length=1)

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class PaginatedUsageResponse(CamelSchema):
    data: list[UsageEventOut]
    next_cursor: Optional[str] = None
    has_more: bool


class WithdrawRequest(CamelSchema):
    amount_micros: int = Field(gt=0)
    idempotency_key: str = Field(min_length=1, max_length=500)
    description: str = ""

    @field_validator("amount_micros")
    @classmethod
    def amount_micros_divisible(cls, v):
        if v % 10_000 != 0:
            raise ValueError("must be divisible by 10_000 (whole cents)")
        return v


class RefundRequest(CamelSchema):
    usage_event_id: UUID
    reason: str = ""
    idempotency_key: str = Field(min_length=1, max_length=500)


class DebitRequest(CamelSchema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)


class CreditRequest(CamelSchema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0, le=999_999_999_999)
    source: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)
    idempotency_key: Optional[str] = Field(default=None, max_length=500)


class DebitCreditResponse(CamelSchema):
    new_balance_micros: int
    transaction_id: str


class CloseRunResponse(CamelSchema):
    run_id: str
    status: str
    total_cost_micros: int
    event_count: int


class UsageAnalyticsResponse(CamelSchema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_card: list[dict]


class RevenueAnalyticsResponse(CamelSchema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


class CreateGroupRequest(CamelSchema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = ""
    margin_pct: Optional[float] = None
    parent_id: Optional[str] = None


class UpdateGroupRequest(CamelSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    margin_pct: Optional[float] = None
    status: Optional[str] = None


class GroupResponse(CamelSchema):
    id: str
    name: str
    slug: str
    description: str
    margin_pct: Optional[float]
    status: str
    parent_id: Optional[str]
    created_at: str
    updated_at: str


class GroupListResponse(CamelSchema):
    data: list[GroupResponse]
    next_cursor: Optional[str] = None
    has_more: bool


# --- Card / Rate schemas ---


class DimensionIn(CamelSchema):
    metric_name: str = Field(min_length=1, max_length=100)
    pricing_type: str = Field(default="per_unit", pattern=r"^(per_unit|flat)$")
    cost_per_unit_micros: int = Field(ge=0)
    provider_cost_per_unit_micros: Optional[int] = Field(default=None, ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)
    label: str = Field(default="", max_length=100)
    unit: str = Field(default="", max_length=50)


class CreateCardRequest(CamelSchema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    provider: str = Field(min_length=1, max_length=100)
    description: str = ""
    pricing_source_url: str = ""
    group_id: Optional[str] = None
    status: str = Field(default="active", pattern=r"^(draft|active)$")
    dimensions: list[DimensionIn] = Field(default_factory=list)


class UpdateCardRequest(CamelSchema):
    name: Optional[str] = None
    description: Optional[str] = None
    pricing_source_url: Optional[str] = None
    group_id: Optional[str] = None
    status: Optional[str] = None


class DimensionOut(CamelSchema):
    id: str
    metric_name: str
    pricing_type: str
    cost_per_unit_micros: int
    provider_cost_per_unit_micros: Optional[int] = None
    unit_quantity: int
    currency: str
    label: str
    unit: str
    valid_from: str
    valid_to: Optional[str] = None


class CardOut(CamelSchema):
    id: str
    slug: str
    name: str
    provider: str
    description: str
    pricing_source_url: str
    group_id: Optional[str] = None
    group_name: Optional[str] = None
    status: str
    dimensions: list[DimensionOut]
    created_at: str
    updated_at: str


class CardListResponse(CamelSchema):
    data: list[CardOut]
    next_cursor: Optional[str] = None
    has_more: bool


# --- Event management schemas ---


class EventsListRequest(CamelSchema):
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    customer_id: Optional[str] = None
    group: Optional[str] = None
    card_slug: Optional[str] = None
    cursor: Optional[str] = None
    limit: int = 50


class StagedEventIn(CamelSchema):
    customer_external_id: str = Field(min_length=1)
    pricing_card: str = Field(min_length=1)
    group: str = ""
    usage_metrics: dict[str, int]
    idempotency_key: Optional[str] = None


class PushEventsRequest(CamelSchema):
    events: list[StagedEventIn]
    reason: str = ""


# --- Dashboard schemas ---


class SparklineSet(CamelSchema):
    revenue: list[int]
    api_costs: list[int]
    gross_margin: list[int]
    margin_pct: list[float]
    cost_per_rev: list[float]


class DashboardStatsResponse(CamelSchema):
    revenue_micros: int
    api_costs_micros: int
    gross_margin_micros: int
    margin_percentage: float
    cost_per_dollar_revenue: float
    revenue_prev_change: float
    costs_prev_change: float
    margin_prev_change: float
    margin_pct_prev_change: float
    cost_per_rev_prev_change: float
    sparklines: SparklineSet


class DailyChartPoint(CamelSchema):
    date: str
    revenue_micros: int
    api_costs_micros: int
    margin_micros: int


class StackedSeries(CamelSchema):
    """Stacked chart data. 'series' lists keys, 'data' has daily rows with dynamic group/card keys."""
    series: list[dict]
    data: list[dict]


class GroupBreakdown(CamelSchema):
    key: str
    label: str
    value_micros: int
    percentage: float


class DashboardChartsResponse(CamelSchema):
    revenue_time_series: list[DailyChartPoint]
    cost_by_group: StackedSeries
    cost_by_card: StackedSeries
    revenue_by_group: list[GroupBreakdown]
    margin_by_group: list[GroupBreakdown]


class DashboardCustomerRow(CamelSchema):
    customer_id: str
    external_id: str
    revenue_micros: int
    api_costs_micros: int
    margin_micros: int
    margin_percentage: float
    event_count: int


class DashboardCustomersResponse(CamelSchema):
    customers: list[DashboardCustomerRow]


# --- Event management response schemas ---


class EventOut(CamelSchema):
    id: str
    effective_at: str
    customer_id: str
    customer_external_id: str
    group: Optional[str] = None
    card_id: Optional[str] = None
    card_slug: Optional[str] = None
    card_name: Optional[str] = None
    provider: str
    usage_metrics: dict
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None


class EventsListResponse(CamelSchema):
    events: list[EventOut]
    total_count: int
    total_cost_micros: int
    next_cursor: Optional[str] = None
    has_more: bool


class FilterOption(CamelSchema):
    key: str
    event_count: int


class EventFilterOptionsResponse(CamelSchema):
    customers: list[FilterOption]
    groups: list[FilterOption]
    cards: list[FilterOption]
    ungrouped_count: int
    card_dimensions: dict  # dynamic keys: card_slug -> [metric_names]
    dimension_prices: dict  # dynamic keys: metric_name -> price info


class PushEventsResponse(CamelSchema):
    pushed_count: int
    batch_id: str
    errors: list[dict] = Field(default_factory=list)


class EventBatchOut(CamelSchema):
    id: str
    action: str
    reason: str
    row_count: int
    author: str
    created_at: str
    reversed_at: Optional[str] = None


class TenantDefaultMarginResponse(CamelSchema):
    default_margin_pct: float


class UpdateTenantDefaultMarginRequest(CamelSchema):
    default_margin_pct: float = Field(ge=0, lt=100)


class MeTenantResponse(CamelSchema):
    id: str
    name: str
    products: list[str]
    pricing_cards_count: int
    usage_events_count: int


class MeTenantUserResponse(CamelSchema):
    id: str
    email: str
    role: str


class MeResponse(CamelSchema):
    tenant_user: Optional[MeTenantUserResponse] = None
    tenant: Optional[MeTenantResponse] = None
    onboarding_completed: bool


class CreateTenantRequest(CamelSchema):
    name: str

    @field_validator("name")
    @classmethod
    def strip_and_validate(cls, v):
        v = (v or "").strip()
        if not v:
            raise ValueError("name must be non-empty")
        if len(v) > 255:
            raise ValueError("name must be <= 255 characters")
        return v


class CreateTenantResponse(CamelSchema):
    tenant: MeTenantResponse
    api_key: Optional[str] = None


class UpdateTenantRequest(CamelSchema):
    name: Optional[str] = None
    complete_onboarding: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def strip_and_validate_name(cls, v):
        if v is None:
            return v
        v = v.strip()
        if not v:
            raise ValueError("name must be non-empty")
        if len(v) > 255:
            raise ValueError("name must be <= 255 characters")
        return v
