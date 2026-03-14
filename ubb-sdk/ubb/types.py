from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, TypeVar


# ---- Metering ----

@dataclass(frozen=True)
class RecordUsageResult:
    event_id: str
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    run_id: str | None = None
    run_total_cost_micros: int | None = None
    hard_stop: bool = False

@dataclass(frozen=True)
class CloseRunResult:
    run_id: str
    status: str
    total_cost_micros: int
    event_count: int

@dataclass(frozen=True)
class UsageEvent:
    id: str
    request_id: str
    cost_micros: int
    effective_at: str
    event_type: str = ""
    provider: str = ""
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None

@dataclass(frozen=True)
class UsageAnalyticsResult:
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]


# ---- Billing ----

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
class BalanceResult:
    balance_micros: int
    currency: str

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
class RevenueAnalyticsResult:
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


# ---- Platform ----

@dataclass(frozen=True)
class CustomerResult:
    id: str
    external_id: str
    status: str
    stripe_customer_id: str = ""


# ---- Subscriptions ----

@dataclass(frozen=True)
class SubscriptionResult:
    id: str
    stripe_subscription_id: str
    stripe_product_name: str
    status: str
    amount_micros: int
    currency: str
    interval: str
    current_period_start: str
    current_period_end: str
    last_synced_at: str | None = None

@dataclass(frozen=True)
class SubscriptionInvoice:
    id: str
    stripe_invoice_id: str
    amount_micros: int
    currency: str
    status: str
    period_start: str
    period_end: str
    paid_at: str | None = None

@dataclass(frozen=True)
class CustomerEconomics:
    customer_id: str
    external_id: str
    plan: str
    subscription_revenue_micros: int
    usage_cost_micros: int
    gross_margin_micros: int
    margin_percentage: float
    period: dict | None = None

@dataclass(frozen=True)
class EconomicsSummary:
    total_revenue_micros: int
    total_cost_micros: int
    total_margin_micros: int
    avg_margin_percentage: float
    unprofitable_customers: int
    total_customers: int
    period: dict | None = None


# ---- Referrals ----

@dataclass(frozen=True)
class ReferralProgram:
    id: str
    reward_type: str
    reward_value: float
    attribution_window_days: int
    status: str
    reward_window_days: int | None = None
    max_reward_micros: int | None = None
    estimated_cost_percentage: float | None = None

@dataclass(frozen=True)
class Referrer:
    customer_id: str
    referral_code: str
    referral_link: str
    is_active: bool
    created_at: str

@dataclass(frozen=True)
class ReferralAttribution:
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    status: str

@dataclass(frozen=True)
class ReferrerEarnings:
    referrer_customer_id: str
    total_earned_micros: int
    total_referred_spend_micros: int
    active_referral_count: int
    referral_count: int

@dataclass(frozen=True)
class PayoutExportEntry:
    referrer_customer_id: str
    external_id: str
    referral_code: str
    total_earned_micros: int
    total_referred_spend_micros: int
    referral_count: int
    active_referral_count: int

@dataclass(frozen=True)
class PayoutExportResult:
    data: list[PayoutExportEntry]
    total_payout_micros: int
    referrer_count: int
    exported_at: str


# ---- Pagination ----

T = TypeVar("T")

@dataclass(frozen=True)
class PaginatedResponse(Generic[T]):
    data: list[T]
    next_cursor: str | None
    has_more: bool
