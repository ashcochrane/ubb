from uuid import UUID
from typing import Optional

from ninja import Schema, Field
from pydantic import field_validator, model_validator


class PreCheckRequest(Schema):
    customer_id: UUID


class PreCheckResponse(Schema):
    allowed: bool
    reason: Optional[str] = None


class RecordUsageRequest(Schema):
    customer_id: UUID
    request_id: str = Field(min_length=1, max_length=500)
    idempotency_key: str = Field(min_length=1, max_length=500)
    metadata: dict = Field(default_factory=dict)

    # Mode 1: Caller-provided cost (legacy)
    cost_micros: Optional[int] = Field(default=None, gt=0, le=999_999_999_999)

    group_keys: Optional[dict[str, str]] = None

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
    amount_micros: int = Field(gt=0)
    reference: str = Field(min_length=1, max_length=500)


class CreditRequest(Schema):
    customer_id: str = Field(min_length=1, max_length=255)
    amount_micros: int = Field(gt=0)
    source: str = Field(min_length=1, max_length=255)
    reference: str = Field(min_length=1, max_length=500)


class DebitCreditResponse(Schema):
    new_balance_micros: int
    transaction_id: str
