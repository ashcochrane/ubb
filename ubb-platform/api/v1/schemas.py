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
    cost_micros: int = Field(gt=0, le=999_999_999_999)
    group_keys: Optional[dict[str, str]] = None
    run_id: Optional[UUID] = None
    # Descriptive dimensions (not pricing inputs)
    event_type: Optional[str] = Field(default=None, max_length=100)
    provider: Optional[str] = Field(default=None, max_length=100)


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
    by_provider: list[dict]
    by_event_type: list[dict]


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]
