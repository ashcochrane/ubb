"""
Frozen dataclass contracts for outbox events.

Rules:
- All event schemas are frozen dataclasses inheriting ``EventSchema``.
- New fields MUST have defaults (additive-only evolution).
- Breaking changes (renames, removals, type changes) require a new class.
- Producers: construct dataclass -> asdict() -> write to outbox. Id fields
  accept ``UUID | str``; construction normalizes to str.
- Consumers: ``SchemaClass.from_payload(payload)`` — unknown keys filtered,
  defaults applied from the class, missing required fields loud.

The base class registers every subclass by its ``EVENT_TYPE``, and the
webhook catalog (``catalog.WEBHOOK_EVENT_TYPES``) derives from that registry:
adding a schema class here IS adding the event type. A subclass without an
EVENT_TYPE, or two subclasses claiming one, is an import-time error.
"""
import dataclasses
import uuid as _uuid
from dataclasses import dataclass
from typing import ClassVar


class EventSchema:
    """Base for all payload schemas: the consumer half of the frozen contract
    plus the EVENT_TYPE registry the catalog derives from."""

    _registry: ClassVar[dict[str, type]] = {}

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        event_type = cls.__dict__.get("EVENT_TYPE")
        if not isinstance(event_type, str) or not event_type:
            raise TypeError(
                f"{cls.__name__} must define EVENT_TYPE as a non-empty str"
            )
        if event_type in EventSchema._registry:
            raise TypeError(
                f"{cls.__name__} redefines EVENT_TYPE {event_type!r}, already "
                f"owned by {EventSchema._registry[event_type].__name__}"
            )
        EventSchema._registry[event_type] = cls

    def __post_init__(self):
        # UUID | str for ids: writers pass model ids as-is; the payload (and
        # asdict()) always carries plain, JSON-serializable strings.
        for f in dataclasses.fields(self):
            value = getattr(self, f.name)
            if isinstance(value, _uuid.UUID):
                object.__setattr__(self, f.name, str(value))

    @classmethod
    def from_payload(cls, payload):
        """Construct from a stored outbox payload dict.

        Unknown keys are filtered (additive-only evolution: a newer producer's
        extra fields must not break this consumer), absent defaulted fields
        take the class default (defined once, here), and an absent required
        field raises TypeError — a payload that malformed cannot be produced
        by the typed write side.
        """
        field_names = {f.name for f in dataclasses.fields(cls)}
        return cls(**{k: v for k, v in payload.items() if k in field_names})


def payload_schema_classes():
    """Every registered payload schema class, in definition order.

    The one enumeration of the payload contract surface — the webhook catalog
    and the OpenAPI ``webhooks`` section both derive from it.
    """
    return tuple(EventSchema._registry.values())


@dataclass(frozen=True)
class UsageRecorded(EventSchema):
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
class UsageRefunded(EventSchema):
    EVENT_TYPE = "usage.refunded"

    tenant_id: str
    customer_id: str
    event_id: str
    refund_id: str
    refund_amount_micros: int


@dataclass(frozen=True)
class ReferralRewardEarned(EventSchema):
    EVENT_TYPE = "referral.reward_earned"

    tenant_id: str
    referral_id: str
    referrer_id: str
    referred_customer_id: str
    reward_micros: int


@dataclass(frozen=True)
class ReferralCreated(EventSchema):
    EVENT_TYPE = "referral.created"

    tenant_id: str
    referral_id: str
    referrer_id: str
    referred_customer_id: str


@dataclass(frozen=True)
class ReferralExpired(EventSchema):
    EVENT_TYPE = "referral.expired"

    tenant_id: str
    referral_id: str
    referrer_id: str
    total_earned_micros: int


@dataclass(frozen=True)
class RefundRequested(EventSchema):
    EVENT_TYPE = "refund.requested"

    tenant_id: str
    customer_id: str
    usage_event_id: str
    refund_amount_micros: int
    reason: str = ""
    idempotency_key: str = ""


@dataclass(frozen=True)
class CustomerDeleted(EventSchema):
    EVENT_TYPE = "customer.deleted"
    tenant_id: str
    customer_id: str


@dataclass(frozen=True)
class WithdrawalRequested(EventSchema):
    EVENT_TYPE = "billing.withdrawal_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    transaction_id: str
    idempotency_key: str = ""


@dataclass(frozen=True)
class ReferralPayoutDue(EventSchema):
    EVENT_TYPE = "referral.payout_due"
    tenant_id: str
    referral_id: str
    referrer_customer_id: str
    payout_amount_micros: int
    period_start: str = ""
    period_end: str = ""


@dataclass(frozen=True)
class BalanceLow(EventSchema):
    EVENT_TYPE = "billing.balance_low"
    tenant_id: str
    customer_id: str
    balance_micros: int
    threshold_micros: int
    suggested_topup_micros: int


@dataclass(frozen=True)
class BalanceCritical(EventSchema):
    EVENT_TYPE = "billing.balance_critical"
    tenant_id: str
    customer_id: str
    balance_micros: int
    min_balance_micros: int


@dataclass(frozen=True)
class TopUpRequested(EventSchema):
    EVENT_TYPE = "billing.topup_requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    trigger: str  # "auto", "manual", "widget"
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class CustomerSuspended(EventSchema):
    EVENT_TYPE = "billing.customer_suspended"
    tenant_id: str
    customer_id: str
    reason: str
    balance_micros: int


@dataclass(frozen=True)
class MarginCustomerUnprofitable(EventSchema):
    EVENT_TYPE = "margin.customer_unprofitable"
    tenant_id: str
    customer_id: str
    period_start: str
    gross_margin_micros: int = 0
    margin_pct: float = 0.0
    threshold_pct: float = 0.0


@dataclass(frozen=True)
class MarginProviderCostSpike(EventSchema):
    EVENT_TYPE = "margin.provider_cost_spike"
    tenant_id: str
    customer_id: str
    period_start: str
    prev_provider_cost_micros: int = 0
    current_provider_cost_micros: int = 0
    prev_margin_pct: float = 0.0
    current_margin_pct: float = 0.0


@dataclass(frozen=True)
class BudgetThresholdReached(EventSchema):
    EVENT_TYPE = "budget.threshold_reached"
    tenant_id: str
    customer_id: str
    period: str
    level: int = 0
    spend_micros: int = 0
    cap_micros: int = 0
    enforce_mode: str = "advisory"


@dataclass(frozen=True)
class UsageInvoicePushed(EventSchema):
    EVENT_TYPE = "usage.invoice_pushed"
    tenant_id: str
    customer_id: str
    period_start: str
    total_billed_micros: int = 0
    line_item_count: int = 0
    stripe_invoice_id: str = ""
    residual_micros: int = 0


@dataclass(frozen=True)
class UsageInvoicePushFailedPermanent(EventSchema):
    EVENT_TYPE = "usage.invoice_push_failed_permanent"
    tenant_id: str
    customer_id: str
    period_start: str
    push_attempts: int = 0
    last_error: str = ""
    stripe_invoice_id: str = ""


@dataclass(frozen=True)
class AutoTopupRequiresAction(EventSchema):
    EVENT_TYPE = "auto_topup.requires_action"
    tenant_id: str
    customer_id: str
    attempt_id: str
    amount_micros: int = 0
    code: str = ""


@dataclass(frozen=True)
class BalanceOverage(EventSchema):
    EVENT_TYPE = "billing.balance_overage"
    tenant_id: str
    customer_id: str
    balance_micros: int = 0
    overage_limit_micros: int = 0
    overage_micros: int = 0


@dataclass(frozen=True)
class CreditGrantExpiring(EventSchema):
    EVENT_TYPE = "billing.credit_grant_expiring"
    tenant_id: str
    customer_id: str
    grant_id: str
    kind: str = ""
    remaining_micros: int = 0
    expires_at: str = ""


@dataclass(frozen=True)
class SandboxResetCompleted(EventSchema):
    EVENT_TYPE = "sandbox.reset_completed"
    tenant_id: str
    keep_config: bool = True


@dataclass(frozen=True)
class TenantApiKeyCreated(EventSchema):
    EVENT_TYPE = "tenant.api_key_created"
    tenant_id: str
    api_key_id: str
    key_prefix: str = ""
    label: str = ""


@dataclass(frozen=True)
class TenantApiKeyRotated(EventSchema):
    EVENT_TYPE = "tenant.api_key_rotated"
    tenant_id: str
    old_api_key_id: str
    new_api_key_id: str
    key_prefix: str = ""  # the NEW key's prefix
    label: str = ""


@dataclass(frozen=True)
class TenantApiKeyRevoked(EventSchema):
    EVENT_TYPE = "tenant.api_key_revoked"
    tenant_id: str
    api_key_id: str
    key_prefix: str = ""
    label: str = ""


@dataclass(frozen=True)
class CreditGrantExpired(EventSchema):
    EVENT_TYPE = "billing.credit_grant_expired"
    tenant_id: str
    customer_id: str
    grant_id: str
    kind: str = ""
    expired_micros: int = 0
    balance_micros: int = 0


@dataclass(frozen=True)
class TaskLimitExceeded(EventSchema):
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
    # Delivery spec §B (#43): True only on a patrol re-mint — a repaired
    # delivery of the CURRENT state, never a fresh crossing. Consumers dedup
    # on the episode/unit id as ever.
    re_announcement: bool = False


@dataclass(frozen=True)
class SubtaskLimitExceeded(EventSchema):
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
    # Delivery spec §B (#43): True only on a patrol re-mint (see
    # TaskLimitExceeded.re_announcement).
    re_announcement: bool = False


@dataclass(frozen=True)
class StopFired(EventSchema):
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
    # Delivery spec §B (#43): True only on a patrol re-mint — an ordinary
    # event of this same type carrying the CURRENT state and episode, minted
    # because the last announcement never terminally succeeded. Consumers
    # dedup on episode_seq as ever.
    re_announcement: bool = False


@dataclass(frozen=True)
class StopCleared(EventSchema):
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
    # Delivery spec §B (#43): True only on a patrol re-mint (see
    # StopFired.re_announcement).
    re_announcement: bool = False


@dataclass(frozen=True)
class SoftFloorCrossed(EventSchema):
    """The soft floor's crossing half (#40, spec §F) — the wind-down line.

    Emitted through the ``soft_floor`` family of the ``StopSignalState``
    transition guard when the DURABLE drawdown lane sees the owner's wallet
    cross the resolved soft line — there is no fast Redis lane for the soft
    family (signal latency is outbox latency, accepted by #28). Never a stop:
    acks don't change, events are never tagged, nothing is suspended — the
    tenant's cue to refuse new top-level task starts while running work
    completes (the start-gate enforces the same line server-side with reason
    ``soft_floor_reached``).

    owner_id = the billing owner (the end customer whose wallet crossed),
    matching stop.fired. soft_min_balance_micros = the RESOLVED soft value
    (the line is -value). episode_seq = the soft_floor family's own episode
    sequence, independent of the hard floor's.
    """
    EVENT_TYPE = "soft_floor.crossed"
    tenant_id: str
    owner_id: str
    balance_micros: int = 0
    soft_min_balance_micros: int = 0
    episode_seq: int = 0
    # Delivery spec §B (#43): True only on a patrol re-mint (see
    # StopFired.re_announcement).
    re_announcement: bool = False


@dataclass(frozen=True)
class SoftFloorCleared(EventSchema):
    """The soft floor's clearing half (#40, spec §F).

    Fires when the owner's balance re-crosses the resolved soft line — from
    the credit hook (``balance_recovered``) or the hourly reconcile
    (``reconciled``) — through the same transition guard, so the pair fires
    exactly once per episode. soft_min_balance_micros is None when the soft
    floor was UNCONFIGURED while an episode was open (removing the line
    clears the state: there is no line left to be past).
    """
    EVENT_TYPE = "soft_floor.cleared"
    tenant_id: str
    owner_id: str
    reason: str
    balance_micros: int = 0
    soft_min_balance_micros: int | None = None
    episode_seq: int = 0
    # Delivery spec §B (#43): True only on a patrol re-mint (see
    # StopFired.re_announcement).
    re_announcement: bool = False


# --- Membership / identity (identity build 1, #79) ---


@dataclass(frozen=True)
class InvitationCreated(EventSchema):
    """An Admin invited a teammate. A pending Member is created alongside; the
    invitee activates it on their first Clerk-verified login (member.activated)."""
    EVENT_TYPE = "invitation.created"
    tenant_id: str
    invitation_id: str
    member_id: str
    email: str = ""
    role: str = ""


@dataclass(frozen=True)
class InvitationRevoked(EventSchema):
    """An Admin cancelled a still-pending invitation; its pending Member is
    dropped and can no longer activate."""
    EVENT_TYPE = "invitation.revoked"
    tenant_id: str
    invitation_id: str
    email: str = ""


@dataclass(frozen=True)
class MemberActivated(EventSchema):
    """A pending Member joined — matched by email on first Clerk login and
    bound from then on to the Clerk user id."""
    EVENT_TYPE = "member.activated"
    tenant_id: str
    member_id: str
    email: str = ""
    role: str = ""
    clerk_user_id: str = ""
