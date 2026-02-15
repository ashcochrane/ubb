from uuid import UUID
from typing import Optional

from ninja import Schema, Field
from pydantic import field_validator, model_validator


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

    # Mode 1: Caller-provided cost (legacy)
    cost_micros: Optional[int] = Field(default=None, gt=0, le=999_999_999_999)

    group_keys: Optional[dict[str, str]] = None

    run_id: Optional[UUID] = None

    # Mode 2: Raw metrics (platform prices it)
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)
    usage_metrics: Optional[dict[str, int]] = None
    properties: Optional[dict] = None

    @field_validator("cost_micros")
    @classmethod
    def cost_micros_positive(cls, v):
        # Sub-cent micros values are valid for token-level pricing
        return v

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

    @model_validator(mode="after")
    def validate_intake_mode(self):
        has_cost = self.cost_micros is not None
        has_metrics = self.usage_metrics is not None
        if not has_cost and not has_metrics:
            raise ValueError("Must provide either cost_micros or usage_metrics")
        if has_cost and has_metrics:
            raise ValueError("Provide cost_micros OR usage_metrics, not both")
        if has_metrics:
            if not self.event_type:
                raise ValueError("event_type required when using usage_metrics")
            if not self.provider:
                raise ValueError("provider required when using usage_metrics")
        return self


class RecordUsageResponse(Schema):
    event_id: str
    new_balance_micros: Optional[int] = None
    suspended: bool
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
    event_type: str = ""
    provider: str = ""
    provider_cost_micros: Optional[int] = None
    billed_cost_micros: Optional[int] = None
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


class ProviderRateIn(Schema):
    provider: str = Field(min_length=1, max_length=100)
    event_type: str = Field(min_length=1, max_length=100)
    metric_name: str = Field(min_length=1, max_length=100)
    dimensions: dict = Field(default_factory=dict)
    cost_per_unit_micros: int = Field(ge=0)
    unit_quantity: int = Field(gt=0, default=1_000_000)
    currency: str = Field(default="USD", max_length=3)


class ProviderRateOut(Schema):
    id: UUID
    provider: str
    event_type: str
    metric_name: str
    dimensions: dict
    cost_per_unit_micros: int
    unit_quantity: int
    currency: str
    valid_from: str
    valid_to: Optional[str] = None


class TenantMarkupIn(Schema):
    event_type: str = Field(default="", max_length=100)
    provider: str = Field(default="", max_length=100)
    markup_percentage_micros: int = Field(default=0, ge=0)
    fixed_uplift_micros: int = Field(default=0, ge=0)


class TenantMarkupOut(Schema):
    id: UUID
    event_type: str
    provider: str
    markup_percentage_micros: int
    fixed_uplift_micros: int
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
