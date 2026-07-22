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

# The small hand results that once covered untyped 200s (top-up / withdraw /
# refund / transactions / auto-top-up / the margin surface) are RETIRED (#98):
# those responses are typed in the committed contract now, so their DTOs come
# from the generated core (TopUpCheckoutResponse, WithdrawResponse,
# RefundResponse, WalletTransactionOut, StatusResponse, CustomerMarginOut,
# DimensionMarginRow, MarginTrendPointOut).

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
