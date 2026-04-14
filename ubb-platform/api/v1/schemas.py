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
    event_type: str = Field(min_length=1, max_length=100)
    provider: str = Field(min_length=1, max_length=100)
    usage_metrics: dict[str, int]
    group: Optional[str] = Field(default=None, max_length=255)
    run_id: Optional[UUID] = None

    @field_validator("usage_metrics")
    @classmethod
    def usage_metrics_values_non_negative(cls, v):
        if v is not None:
            for key, val in v.items():
                if not isinstance(val, int) or isinstance(val, bool):
                    raise ValueError(f"Metric '{key}' must be an integer")
                if val < 0:
                    raise ValueError(f"Metric '{key}' must be >= 0")
        return v


class RecordUsageResponse(Schema):
    event_id: str
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
    run_id: Optional[str] = None
    run_total_cost_micros: Optional[int] = None
    hard_stop: bool = False


class BalanceResponse(Schema):
    balance_micros: int
    currency: str


class UsageEventOut(Schema):
    id: UUID
    request_id: str
    cost_micros: int
    event_type: str
    provider: str
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
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
    event_type: str = Field(default="", max_length=100)
    provider: str = Field(default="", max_length=100)
    margin_pct: float = Field(ge=0, lt=100, default=0)


class TenantMarkupOut(Schema):
    id: UUID
    event_type: str
    provider: str
    margin_pct: float
    valid_from: str
    valid_to: Optional[str] = None


class CloseRunResponse(Schema):
    run_id: str
    status: str
    total_cost_micros: int
    event_count: int


class UsageAnalyticsResponse(Schema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


class CreateGroupRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z][a-z0-9_]*$")
    description: str = ""
    margin_pct: Optional[float] = None
    parent_id: Optional[str] = None


class UpdateGroupRequest(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    margin_pct: Optional[float] = None
    status: Optional[str] = None


class GroupResponse(Schema):
    id: str
    name: str
    slug: str
    description: str
    margin_pct: Optional[float]
    status: str
    parent_id: Optional[str]
    created_at: str
    updated_at: str


class GroupListResponse(Schema):
    data: list[GroupResponse]
    next_cursor: Optional[str] = None
    has_more: bool


# --- Card / Rate schemas ---


class RateIn(Schema):
    metric_name: str = Field(min_length=1, max_length=100)
    cost_per_unit_micros: int = Field(ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)


class CreateCardRequest(Schema):
    name: str = Field(min_length=1, max_length=255)
    provider: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    dimensions: dict = Field(default_factory=dict)
    description: str = ""
    rates: list[RateIn] = Field(default_factory=list)


class UpdateCardRequest(Schema):
    name: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None


class RateOut(Schema):
    id: str
    metric_name: str
    cost_per_unit_micros: int
    unit_quantity: int
    currency: str
    valid_from: str
    valid_to: Optional[str] = None


class CardOut(Schema):
    id: str
    name: str
    provider: str
    event_type: str
    dimensions: dict
    description: str
    status: str
    rates: list[RateOut]
    created_at: str


class CardListResponse(Schema):
    data: list[CardOut]
    next_cursor: Optional[str] = None
    has_more: bool
