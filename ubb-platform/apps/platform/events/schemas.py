"""
Frozen dataclass contracts for outbox events.

Rules:
- All event schemas are frozen dataclasses.
- New fields MUST have defaults (additive-only evolution).
- Breaking changes (renames, removals, type changes) require a new class.
- Producers: construct dataclass -> asdict() -> write to outbox.
- Consumers: filter unknown keys -> construct dataclass from payload.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class UsageRecorded:
    EVENT_TYPE = "usage.recorded"

    tenant_id: str
    customer_id: str
    event_id: str
    cost_micros: int
    provider_cost_micros: int | None = None
    billed_cost_micros: int | None = None
    event_type: str = ""
    provider: str = ""
    auto_topup_attempt_id: str | None = None
    run_id: str | None = None


@dataclass(frozen=True)
class UsageRefunded:
    EVENT_TYPE = "usage.refunded"

    tenant_id: str
    customer_id: str
    event_id: str
    refund_id: str
    refund_amount_micros: int


@dataclass(frozen=True)
class ReferralRewardEarned:
    EVENT_TYPE = "referral.reward_earned"

    tenant_id: str
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    reward_micros: int


@dataclass(frozen=True)
class ReferralCreated:
    EVENT_TYPE = "referral.created"

    tenant_id: str
    referral_id: str
    referrer_id: str
    referred_customer_id: str


@dataclass(frozen=True)
class ReferralExpired:
    EVENT_TYPE = "referral.expired"

    tenant_id: str
    referral_id: str
    referrer_id: str
    total_earned_micros: int


@dataclass(frozen=True)
class RefundRequested:
    EVENT_TYPE = "refund.requested"

    tenant_id: str
    customer_id: str
    usage_event_id: str
    refund_amount_micros: int
    reason: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class CustomerDeleted:
    EVENT_TYPE = "customer.deleted"
    tenant_id: str
    customer_id: str


@dataclass(frozen=True)
class WithdrawalRequested:
    EVENT_TYPE = "billing.withdrawal_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    transaction_id: str
    idempotency_key: str = ""


@dataclass(frozen=True)
class ReferralPayoutDue:
    EVENT_TYPE = "referral.payout_due"
    tenant_id: str
    referral_id: str
    referrer_customer_id: str
    payout_amount_micros: int
    period_start: str = ""
    period_end: str = ""


@dataclass(frozen=True)
class BalanceLow:
    EVENT_TYPE = "billing.balance_low"
    tenant_id: str
    customer_id: str
    balance_micros: int
    threshold_micros: int
    suggested_topup_micros: int


@dataclass(frozen=True)
class BalanceCritical:
    EVENT_TYPE = "billing.balance_critical"
    tenant_id: str
    customer_id: str
    balance_micros: int
    min_balance_micros: int


@dataclass(frozen=True)
class TopUpRequested:
    EVENT_TYPE = "billing.topup_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    trigger: str  # "auto", "manual", "widget"
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class CustomerSuspended:
    EVENT_TYPE = "billing.customer_suspended"
    tenant_id: str
    customer_id: str
    reason: str
    balance_micros: int
