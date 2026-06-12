from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


@dataclass(frozen=True)
class PreCheckResult:
    allowed: bool
    reason: str | None = None
    can_proceed: bool | None = None
    balance_micros: int | None = None
    run_id: str | None = None
    cost_limit_micros: int | None = None
    hard_stop_balance_micros: int | None = None

@dataclass(frozen=True)
class RecordUsageResult:
    event_id: str
    new_balance_micros: int | None = None
    suspended: bool = False
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    units: int | None = None
    balance_after_micros: int | None = None
    run_id: str | None = None
    run_total_cost_micros: int | None = None
    hard_stop: bool = False
    usage_metrics: dict | None = None
    pricing_provenance: dict | None = None
    uncosted_metrics: list | None = None
    service_id: str = ""
    agent_id: str = ""

@dataclass(frozen=True)
class BatchItemResult:
    """One item's outcome from record_batch. ``data`` is the full raw per-item
    body (success: the same fields as RecordUsageResult; error: the same error
    body the single-call endpoint would have returned)."""
    ok: bool
    error: str | None = None
    detail: str | None = None
    event_id: str | None = None
    data: dict | None = None

@dataclass(frozen=True)
class BatchResult:
    results: list[BatchItemResult]
    succeeded: int
    failed: int

@dataclass(frozen=True)
class CloseRunResult:
    run_id: str
    status: str
    total_cost_micros: int
    event_count: int

@dataclass(frozen=True)
class CustomerResult:
    id: str
    external_id: str
    status: str

@dataclass(frozen=True)
class BalanceResult:
    balance_micros: int
    currency: str

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
class CustomerRevenue:
    recurring_amount_micros: int | None = None
    interval: str | None = None
    currency: str | None = None
    effective_from: str | None = None
    effective_to: str | None = None

@dataclass(frozen=True)
class BudgetConfig:
    cap_micros: int | None = None
    enforce_mode: str | None = None
    hard_stop_pct: int | None = None
    alert_levels: list | None = None
    fail_closed: bool | None = None

@dataclass(frozen=True)
class BudgetStatus:
    period: str | None = None
    spend_micros: int | None = None
    cap_micros: int | None = None
    pct: float | None = None
    enforce_mode: str | None = None

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
class TenantMarkup:
    markup_percentage_micros: int | None = None
    fixed_uplift_micros: int | None = None

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
    tiers: list | None = None
    currency: str | None = None
    product_id: str | None = None
    customer_id: str | None = None
    valid_from: str | None = None
    valid_to: str | None = None
