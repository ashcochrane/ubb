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
    # The clean cut (#37) renamed this field in place rather than minting a
    # new class: no consumer read the pre-rename name, and payload
    # construction filters unknown keys, so a legacy queued payload still
    # constructs (task_id defaults to None).
    task_id: str | None = None
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
class TaskLimitExceeded:
    """One-rule task-kill fan-out event (#37). The SINGLE canonical class —
    no other module may redefine it.

    Emitted exactly once per winning active->killed transition — by the
    verdict-driven kill flow (sync record, batch items, async settle) and the
    stale-task reaper — so sibling/idle workers tear the task down. The task
    is a signal point, not a wall: events arriving after this still land,
    bill, and count into both totals.

    customer_id      = the SEAT that owns the task.
    billing_owner_id = resolve_billing_owner(seat) — the KILL SCOPE.
    reason           = one of apps.platform.tasks.reasons (closed set).
    Both running totals are carried, denominationally explicit; only the
    provider (COGS) total races provider_cost_limit_micros.
    """
    EVENT_TYPE = "task.limit_exceeded"
    tenant_id: str
    customer_id: str = ""
    billing_owner_id: str = ""
    task_id: str = ""
    external_task_id: str = ""
    reason: str = ""
    total_billed_cost_micros: int = 0
    total_provider_cost_micros: int = 0
    provider_cost_limit_micros: int = 0


@dataclass(frozen=True)
class SubtaskLimitExceeded:
    """Subtask-kill fan-out event (#38) — the subtask sibling of
    TaskLimitExceeded, emitted exactly once per winning active->killed
    transition of a SUBTASK (its own limit/floor crossing, or the reaper).
    The subtask is killed ALONE: the parent keeps running and counting, so
    consumers tear down only the named child. A parent's own crossing emits
    task.limit_exceeded instead and cascades its kill downward silently —
    cascaded children never emit this event (they crossed nothing).

    Ids are explicit (spec §B — the run-era scope field died with the
    split): subtask_id = the killed child unit, parent_task_id = the parent
    whose totals its spend rolls up into. Totals and limit are the
    SUBTASK's own, denominationally explicit; only the provider (COGS)
    total races the limit.
    """
    EVENT_TYPE = "subtask.limit_exceeded"
    tenant_id: str
    customer_id: str = ""
    billing_owner_id: str = ""
    subtask_id: str = ""
    parent_task_id: str = ""
    external_task_id: str = ""
    reason: str = ""
    total_billed_cost_micros: int = 0
    total_provider_cost_micros: int = 0
    provider_cost_limit_micros: int = 0


@dataclass(frozen=True)
class StopFired:
    """Customer-wide stop signal — the stop half of the stop/resume pair (#39).

    Emitted through the ``StopSignalState`` transition guard
    (apps/billing/gating/services/stop_signal_service.py): every lane that
    detects a floor/cap crossing — the fast Redis lane at arrival, the durable
    drawdown handler, the hourly reconcile — drives a transition on the
    owner's per-family ledger row, and only the WINNING stop transition emits
    this event, so a crossing observed by several lanes fires exactly once per
    episode. The emission commits atomically with the ledger transition (same
    transaction), so the ledger and the event stream cannot disagree — a
    caller's rollback takes both, and the durable lane / reconcile re-drives
    the missed transition (late, never lost).

    owner_id    = the billing owner the stop is keyed on (resolve_billing_owner).
    scope       = "customer" — the whole owner is stopped (consumers fan the
                  stop to every task they hold for the owner).
    episode_seq = the per-owner stop-episode id (StopSignalState.episode_seq);
                  the paired ``stop.cleared`` carries the same id, and the
                  stop-context tagging / past-limit report (#41) key on it.
    """
    EVENT_TYPE = "stop.fired"
    tenant_id: str
    owner_id: str
    reason: str
    scope: str = "customer"
    episode_seq: int = 0


@dataclass(frozen=True)
class StopCleared:
    """The resume half of the stop/resume pair (#39, spec §E).

    Fires the moment the balance re-crosses the floor — no hysteresis margin,
    no ack latch (decision 4) — from any clearing path: the ``credit()`` hook
    (fast lane, with a durable-balance fallback when Redis is blind) or the
    hourly reconcile. All paths route through the same ``StopSignalState``
    transition guard as ``stop.fired``; a clear that didn't win the transition
    emits nothing, so resume fires exactly once per episode.

    episode_seq    = the episode this clear closes (pairs with the stop.fired
                     that opened it).
    balance_micros = the balance at clearance, as seen by the clearing lane
                     (live counter on the fast path, durable balance on the
                     fallback/reconcile paths; postpaid passes 0).
    """
    EVENT_TYPE = "stop.cleared"
    tenant_id: str
    owner_id: str
    reason: str
    scope: str = "customer"
    episode_seq: int = 0
    balance_micros: int = 0
