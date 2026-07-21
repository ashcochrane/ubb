from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class PreCheckResult:
    allowed: bool
    reason: str | None = None
    can_proceed: bool | None = None
    balance_micros: int | None = None
    task_id: str | None = None
    # Set when the started unit is a subtask — the parent it registered under.
    parent_task_id: str | None = None
    provider_cost_limit_micros: int | None = None
    floor_snapshot_micros: int | None = None

@dataclass(frozen=True)
class BatchItemResult:
    """One item's VERDICT from record_batch (#78: one verdict field set with
    async ingest). ``data`` is the full raw per-item body (accepted: the same
    fields as RecordUsageResult; rejected: {accepted, code, detail} plus null
    stop fields). ``code`` words come from the platform's error-code
    registry."""
    accepted: bool
    code: str | None = None
    detail: str | None = None
    event_id: str | None = None
    data: dict | None = None

@dataclass(frozen=True)
class BatchResult:
    results: list[BatchItemResult]
    accepted: int
    rejected: int

@dataclass(frozen=True)
class UsageEvent:
    id: str
    request_id: str
    event_type: str | None = None
    provider: str | None = None
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    units: int | None = None
    metadata: dict | None = None
    effective_at: str | None = None
    # #41: the event's immutable past-limit context array (see
    # RecordUsageResult.stop_context); None for the common untagged event.
    stop_context: list | None = None

@dataclass(frozen=True)
class TopUpResult:
    checkout_url: str

@dataclass(frozen=True)
class AutoTopUpResult:
    status: str

@dataclass(frozen=True)
class WithdrawResult:
    transaction_id: str
    balance_micros: int

@dataclass(frozen=True)
class RefundResult:
    refund_id: str
    balance_micros: int

@dataclass(frozen=True)
class WalletTransaction:
    id: str
    transaction_type: str
    amount_micros: int
    balance_after_micros: int
    description: str
    reference_id: str
    created_at: str

@dataclass(frozen=True)
class CustomerMargin:
    customer_id: str
    subscription_revenue_micros: int | None = None
    usage_billed_micros: int | None = None
    provider_cost_micros: int | None = None
    gross_margin_micros: int | None = None
    margin_percentage: float | None = None

@dataclass(frozen=True)
class DimensionMargin:
    dimension: str | None = None
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    margin_micros: int | None = None
    event_count: int | None = None

@dataclass(frozen=True)
class MarginTrendPoint:
    period_start: str
    provider_cost_micros: int | None = None
    usage_billed_micros: int | None = None
    subscription_revenue_micros: int | None = None
    gross_margin_micros: int | None = None
    margin_percentage: float | None = None

@dataclass(frozen=True)
class UsageInvoice:
    period_start: str | None = None
    period_end: str | None = None
    total_billed_micros: int | None = None
    currency: str | None = None
    status: str | None = None
    stripe_invoice_id: str | None = None
    skip_reason: str | None = None

T = TypeVar("T")

@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    data: list[T]
    next_cursor: str | None
    has_more: bool

@dataclass(frozen=True)
class RateCard:
    id: str | None = None
    lineage_id: str | None = None
    card_type: str | None = None
    metric_name: str | None = None
    provider: str | None = None
    event_type: str | None = None
    dimensions: dict | None = None
    pricing_model: str | None = None
    rate_per_unit_micros: int | None = None
    unit_quantity: int | None = None
    fixed_micros: int | None = None
    currency: str | None = None
    product_id: str | None = None
    customer_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
