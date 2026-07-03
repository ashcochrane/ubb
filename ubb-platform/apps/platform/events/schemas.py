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
    billing_owner_id: str = ""
    # ISO-8601 timestamp of when the usage economically happened (caller
    # timestamps / backfill). Default "" keeps legacy queued payloads valid;
    # consumers fall back to the metering read contract when absent.
    effective_at: str = ""


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


@dataclass(frozen=True)
class MarginCustomerUnprofitable:
    EVENT_TYPE = "margin.customer_unprofitable"
    tenant_id: str
    customer_id: str
    period_start: str
    gross_margin_micros: int = 0
    margin_pct: float = 0.0
    threshold_pct: float = 0.0


@dataclass(frozen=True)
class MarginProviderCostSpike:
    EVENT_TYPE = "margin.provider_cost_spike"
    tenant_id: str
    customer_id: str
    period_start: str
    prev_provider_cost_micros: int = 0
    current_provider_cost_micros: int = 0
    prev_margin_pct: float = 0.0
    current_margin_pct: float = 0.0


@dataclass(frozen=True)
class BudgetThresholdReached:
    EVENT_TYPE = "budget.threshold_reached"
    tenant_id: str
    customer_id: str
    period: str
    level: int = 0
    spend_micros: int = 0
    cap_micros: int = 0
    enforce_mode: str = "advisory"


@dataclass(frozen=True)
class UsageInvoicePushed:
    EVENT_TYPE = "usage.invoice_pushed"
    tenant_id: str
    customer_id: str
    period_start: str
    total_billed_micros: int = 0
    line_item_count: int = 0
    stripe_invoice_id: str = ""
    residual_micros: int = 0


@dataclass(frozen=True)
class UsageInvoicePushFailedPermanent:
    EVENT_TYPE = "usage.invoice_push_failed_permanent"
    tenant_id: str
    customer_id: str
    period_start: str
    push_attempts: int = 0
    last_error: str = ""
    stripe_invoice_id: str = ""


@dataclass(frozen=True)
class AutoTopupRequiresAction:
    EVENT_TYPE = "auto_topup.requires_action"
    tenant_id: str
    customer_id: str
    attempt_id: str
    amount_micros: int = 0
    code: str = ""


@dataclass(frozen=True)
class BalanceOverage:
    EVENT_TYPE = "billing.balance_overage"
    tenant_id: str
    customer_id: str
    balance_micros: int = 0
    overage_limit_micros: int = 0
    overage_micros: int = 0


@dataclass(frozen=True)
class CreditGrantExpiring:
    EVENT_TYPE = "billing.credit_grant_expiring"
    tenant_id: str
    customer_id: str
    grant_id: str
    kind: str = ""
    remaining_micros: int = 0
    expires_at: str = ""


@dataclass(frozen=True)
class SandboxResetCompleted:
    EVENT_TYPE = "sandbox.reset_completed"
    tenant_id: str
    keep_config: bool = True


@dataclass(frozen=True)
class TenantApiKeyCreated:
    EVENT_TYPE = "tenant.api_key_created"
    tenant_id: str
    api_key_id: str
    key_prefix: str = ""
    label: str = ""


@dataclass(frozen=True)
class TenantApiKeyRotated:
    EVENT_TYPE = "tenant.api_key_rotated"
    tenant_id: str
    old_api_key_id: str
    new_api_key_id: str
    key_prefix: str = ""  # the NEW key's prefix
    label: str = ""


@dataclass(frozen=True)
class TenantApiKeyRevoked:
    EVENT_TYPE = "tenant.api_key_revoked"
    tenant_id: str
    api_key_id: str
    key_prefix: str = ""
    label: str = ""


@dataclass(frozen=True)
class CreditGrantExpired:
    EVENT_TYPE = "billing.credit_grant_expired"
    tenant_id: str
    customer_id: str
    grant_id: str
    kind: str = ""
    expired_micros: int = 0
    balance_micros: int = 0


@dataclass(frozen=True)
class RunLimitExceeded:
    """Tier-2 spend-control fan-out event (D6). The SINGLE canonical class —
    no other module may redefine it.

    customer_id      = the SEAT that owns the run.
    billing_owner_id = resolve_billing_owner(seat) — the KILL SCOPE.
    scope            = "run"  -> a single run hit its per-run/per-task cap or
                                  was reaped (run_id is set);
                       "customer" -> a customer-wide spend stop; consumers fan
                                  the kill to every run they hold for the owner.
    reason           = one of apps.platform.runs.reasons (closed set).
    """
    EVENT_TYPE = "run.limit_exceeded"
    tenant_id: str
    customer_id: str = ""
    billing_owner_id: str = ""
    run_id: str = ""
    external_run_id: str = ""
    task_id: str = ""
    reason: str = ""
    scope: str = "run"
    total_cost_micros: int = 0
    limit_micros: int = 0


@dataclass(frozen=True)
class StopFired:
    """Customer-wide cooperative stop flag TRANSITION (unset -> set) — Task 7.

    Emitted (best-effort, alongside a ``ubb:stopchan:{owner_id}`` Redis
    pub/sub publish) exactly once per transition by
    ``LiveLedgerService._set_stop`` so the existing outgoing-webhook system
    can deliver ``stop.fired`` to tenant endpoints. A repeat crossing while
    the flag is already set only refreshes its TTL and does NOT re-emit this
    event (see the SET NX transition detector in _set_stop).

    owner_id = the billing owner the stop flag is keyed on (resolve_billing_owner).
    scope    = "customer" — the whole owner is stopped (mirrors
               RunLimitExceeded's scope="customer" fan-out semantics).
    """
    EVENT_TYPE = "stop.fired"
    tenant_id: str
    owner_id: str
    reason: str
    scope: str = "customer"
