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
from typing import Annotated, ClassVar

from pydantic import Field

from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    PRICING_STATUS_KNOWN,
    TASK_STATUS_EXPIRED,
    TASK_STATUS_KILLED,
)

#: A payload field naming the closed set that says whether a supplier cost is
#: settled (#328).
#:
#: The marker is the same one `api/v1/schemas.py` puts on the three RESPONSES
#: that publish this concept, and it is spelled again here rather than imported
#: because a product may not import the composition layer (ADR-001). What it
#: buys is the same thing: the published document states the three values
#: instead of `type: string`, so a subscriber writing a switch over this field
#: can see the whole set. `tools/known_values/apply.py` walks the WHOLE document
#: — the `webhooks` section included — so a marked payload field is annotated
#: exactly as a marked response field is.
CostingStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "costing_status"})]

#: The same, for the closed set that says whether a customer PRICE is settled
#: (#351). Same marker, same reason, same applier — and the marker sits on a
#: plain `str` rather than on a nullable union because this field is never null:
#: `unknown` is a status, not the absence of one.
PricingStatus = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "pricing_status"})]

#: A payload field naming the MECHANISM that applied a stop (#412), which is a
#: different question from the business cause beside it: *what stopped this*
#: and *why it was stopped* are answered by two fields so that a subscriber
#: classifies an event by reading it rather than by parsing its name
#: (ADR-0006 §5).
#:
#: ⚠ OPEN, NOT CLOSED — and the marker renders `x-ubb-known-values`
#: documentation metadata beside an untouched `type: string` rather than an
#: `enum`. The set grows whenever UBB adds an enforcement path, so a subscriber
#: must accept a mechanism it has not seen instead of rejecting the event
#: carrying it (ADR-0003). That is also what makes shipping a SUBSET honest:
#: an open set is designed for a producer that drives some of it.
#:
#: THE FIELD IS HERE BECAUSE THE BACKEND NOW SERVES THE CONCEPT. Its declared
#: backend consumer is `apps/platform/work/reasons.py`, which holds all five
#: mechanisms by reference — and a concept the backend serves that declares an
#: `openapi` consumer must appear in the published document, or the contract
#: is silent about a value UBB is already sending. The alternative was to hold
#: fewer than five words in that module for no reason but to keep this field
#: away, which is a worse contract bought with a worse module.
TriggerSource = Annotated[
    str, Field(json_schema_extra={"x-ubb-concept": "trigger_source"})]


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
    # ⚠ NULLABLE SINCE #351, AND IT WAS TYPED `int` WHILE THE COLUMN IT IS
    # FILLED FROM WENT NULLABLE — which is the whole of the finding this ticket
    # was sent to make. The recording path assigns this straight from
    # `Posting.billed_cost_micros`, and a frozen dataclass does not enforce its
    # own annotations at runtime, so the payload would have carried `null` under
    # a field the published document declares `integer`: no exception, no failed
    # write, and two products reading it. Both accumulators below it already
    # took the same treatment for the supplier half in #328.
    #
    # `billed_cost_micros` further down is the newer spelling of this same
    # number and has been nullable since it was added; retiring one of the two
    # is not this ticket's.
    cost_micros: int | None
    # A NULL HERE IS DISAMBIGUATED BY THE FIELD BELOW IT (#328). This field has
    # always been nullable, but until #320 a null only ever meant "the recording
    # path supplied nothing"; #320 taught the compute spine to leave the column
    # NULL for a cost UBB could not settle, and this payload is filled straight
    # from that column — so for three commits a subscriber read the same null
    # for "no supplier cost" and "a supplier cost we have not learned yet".
    provider_cost_micros: int | None = None
    # WHICH OF THOSE TWO THE NULL ABOVE MEANS, carried because two products
    # accumulate off this payload and neither can count what it excluded without
    # it. `not_applicable` also arrives as a null amount, and counting it as
    # missing information would mark every metering-only tenant's every period
    # partial forever (#327's ruling, inherited rather than re-made here).
    #
    # THE DEFAULT IS `known`, WHICH IS THE POSTING COLUMN'S OWN DEFAULT AND ITS
    # OWN ARGUMENT (`usage/models.py`): "a writer that says nothing about
    # supplier cost has recorded what UBB actually holds, and inventing an
    # unknown it never observed would make every period partial". A payload
    # queued before this field existed carries no key, so a reader falls to this
    # default and counts no exclusion — which is what those events meant.
    #
    # It is a DECLARED value rather than an empty string for the reason the
    # column is NOT NULL: a fourth state meaning "nobody said" is the ambiguity
    # this slice exists to remove, and putting one on the wire would publish it
    # to every subscriber. That also lets the field carry the concept marker
    # below, so the document states the closed set rather than `type: string`.
    costing_status: CostingStatus = COSTING_STATUS_KNOWN
    #
    # ⚠ THE CAUSE DOES NOT FOLLOW THE STATUS HERE, AND THAT IS A DECISION. The
    # three RESPONSES carry `unresolved_reason` beside this (#323) because a
    # tenant reading one event needs to know which input would settle it. This
    # payload's readers are two accumulators counting HOW MANY costs they could
    # not include; none of them asks why, and a field nothing reads is a field
    # that goes stale. It joins the payload the day a subscriber needs it.
    billed_cost_micros: int | None = None
    # WHICH READING THE TWO PRICE NULLS ABOVE TAKE (#351), carried for exactly
    # the reason `costing_status` is: two products accumulate off this payload
    # and neither can count what it excluded without it. `waived` and
    # `not_applicable` arrive as a null amount too, and counting either as
    # missing information would mark every metering-only tenant's every period
    # partial forever.
    #
    # THE DEFAULT IS `known`, which is the posting column's own default and its
    # own argument: a payload queued before this field existed carries no key,
    # so a reader falls to this default and counts no exclusion — which is what
    # those events meant.
    pricing_status: PricingStatus = PRICING_STATUS_KNOWN
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
    EVENT_TYPE = "withdrawal.requested"
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
    EVENT_TYPE = "wallet.balance_low"
    tenant_id: str
    customer_id: str
    balance_micros: int
    threshold_micros: int
    suggested_topup_micros: int


@dataclass(frozen=True)
class BalanceCritical(EventSchema):
    EVENT_TYPE = "wallet.balance_critical"
    tenant_id: str
    customer_id: str
    balance_micros: int
    min_balance_micros: int


@dataclass(frozen=True)
class TopUpRequested(EventSchema):
    EVENT_TYPE = "top_up.requested"
    tenant_id: str
    customer_id: str
    amount_micros: int
    trigger: str  # "auto", "manual", "widget"
    success_url: str
    cancel_url: str


@dataclass(frozen=True)
class CustomerSuspended(EventSchema):
    EVENT_TYPE = "customer.suspended"
    tenant_id: str
    customer_id: str
    reason: str
    balance_micros: int


@dataclass(frozen=True)
class CustomerUnprofitable(EventSchema):
    EVENT_TYPE = "customer.unprofitable"
    tenant_id: str
    customer_id: str
    period_start: str
    gross_margin_micros: int = 0
    margin_pct: float = 0.0
    threshold_pct: float = 0.0


@dataclass(frozen=True)
class ProviderCostSpike(EventSchema):
    EVENT_TYPE = "provider.cost_spike"
    tenant_id: str
    customer_id: str
    period_start: str
    prev_provider_cost_micros: int = 0
    current_provider_cost_micros: int = 0
    #: How many of THIS period's events its cost total could not include
    #: (#328). Non-zero means the rise announced here was computed from a
    #: floor and is itself a lower bound — the real spike is at least this
    #: steep, which is why the alarm fires anyway.
    #:
    #: The PREVIOUS period never carries one, because a previous cost that
    #: excluded anything is not compared at all: it is the denominator, and too
    #: small a denominator invents a spike rather than understating one.
    unresolved_event_count: int = 0
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
    enforce_mode: str = "alert_only"


@dataclass(frozen=True)
class UsageInvoicePushed(EventSchema):
    EVENT_TYPE = "usage_invoice.pushed"
    tenant_id: str
    customer_id: str
    period_start: str
    total_billed_micros: int = 0
    line_item_count: int = 0
    stripe_invoice_id: str = ""
    residual_micros: int = 0


@dataclass(frozen=True)
class UsageInvoicePushFailedPermanent(EventSchema):
    EVENT_TYPE = "usage_invoice.push_failed_permanent"
    tenant_id: str
    customer_id: str
    period_start: str
    push_attempts: int = 0
    last_error: str = ""
    stripe_invoice_id: str = ""


@dataclass(frozen=True)
class AutoTopUpRequiresAction(EventSchema):
    EVENT_TYPE = "auto_top_up.requires_action"
    tenant_id: str
    customer_id: str
    attempt_id: str
    amount_micros: int = 0
    code: str = ""


@dataclass(frozen=True)
class BalanceOverage(EventSchema):
    EVENT_TYPE = "wallet.balance_overage"
    tenant_id: str
    customer_id: str
    balance_micros: int = 0
    overage_limit_micros: int = 0
    overage_micros: int = 0


@dataclass(frozen=True)
class CreditGrantExpiring(EventSchema):
    EVENT_TYPE = "credit_grant.expiring"
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
    EVENT_TYPE = "credit_grant.expired"
    tenant_id: str
    customer_id: str
    grant_id: str
    kind: str = ""
    expired_micros: int = 0
    balance_micros: int = 0


# --- The four terminal stops (#140 §4.3, ratified in full by #154 §5.3) -----
#
# ⚠ TWO EVENTS BECAME FOUR HERE, AND THE NAME IS THE WHOLE OF THE CHANGE. Every
# field below travelled on the two events these replace. ADR-0006 §5 names an
# event for the STATE ENTERED under the owner whose lifecycle moved, and
# `killed` and `expired` are two different claims about a unit of work: *UBB
# stopped this on a spend signal* against *nobody ever told UBB how it ended*.
# One name could not say which — so an operator subscribed to spend incidents
# was paged because a worker crashed, and *how often did work stop on a
# ceiling?* could not be answered without parsing a cause out of the payload.
#
# WHY TWO AND NOT ONE, SETTLED AND CLOSED (#154 §5.3). A single stopped-event
# was declined on exactly that paging argument; a ceiling-named one was declined
# for putting the cause where the outcome belongs; and a spend-pool crossing and
# the work it stops are separate events, never one overloaded webhook.
#
# THE CAUSE AND THE MECHANISM TRAVEL AS FIELDS, which is the other half of the
# same rule: a subscriber classifies by SUBSCRIBING and then by reading, never
# by parsing a name. A control's FAMILY and identity are deliberately NOT here
# — they are a CLOSED set of four, three of whose families do not exist yet, and
# publishing a closed set only one member of which is producible is precisely
# what `domain-vocabulary/concepts/economics.yaml` forbids a closed set to do.
# Adding an optional field to a payload is additive, so declining them now costs
# a subscriber nothing and shipping them would cost a promise UBB cannot keep.


@dataclass(frozen=True)
class _TerminalStop:
    """Everything a terminal stop announcement carries, whichever it is.

    Deliberately NOT an ``EventSchema``: it declares no ``EVENT_TYPE``, so it is
    nothing a tenant can subscribe to and nothing the catalogue derives. It
    exists because the four events below differ in exactly two things — the
    state entered, which is in the name, and the ids saying which unit — and
    writing everything else out four times is how four payloads carrying one
    fact come to carry it differently. The two they replace already asked a
    reader to keep them identical, in a comment; this asks the language.

    customer_id      = the SEAT that owns the work.
    billing_owner_id = resolve_billing_owner(seat) — the STOP SCOPE.
    Both running totals are carried, denominationally explicit; only the
    provider (COGS) total races provider_cost_limit_micros.
    """
    tenant_id: str
    customer_id: str = ""
    billing_owner_id: str = ""
    external_task_id: str = ""
    #: WHY THE UNIT STOPPED — one of `apps.platform.work.reasons`, beside the
    #: mechanism below it. It was a bare `reason` until the split and carries
    #: the registry's own word for the concept now: two questions with two
    #: value sets are two fields, and a field named for neither answers a
    #: reader nothing. The set is `open` and this producer drives part of it,
    #: which is what an open set is for — a subscriber must accept a cause it
    #: has not seen rather than reject the event carrying it (ADR-0003).
    reason_code: str = ""
    #: THE MECHANISM, beside the cause (#412) — see `TriggerSource` above for
    #: why an open set may ship a subset. Every path that APPLIES a stop names
    #: itself, and a patrol re-mint reads back the mechanism the stopped row
    #: recorded, so `""` means UBB is genuinely not stating one.
    trigger_source: TriggerSource = ""
    total_billed_cost_micros: int = 0
    total_provider_cost_micros: int = 0
    #: How many of this unit's events the provider total could not include
    #: (#328). Non-zero means the crossing was measured against a FLOOR — the
    #: unit spent at least the total above, so the stop is sound and the figure
    #: understates it.
    unresolved_event_count: int = 0
    provider_cost_limit_micros: int = 0
    #: Delivery spec §B (#43): True only on a patrol re-mint — a repaired
    #: delivery of the CURRENT state, never a fresh crossing. The re-mint reads
    #: that state off the row, so a unit that was killed re-announces
    #: `*.killed` and one that expired re-announces `*.expired`. Consumers
    #: dedup on the unit id as ever.
    re_announcement: bool = False


@dataclass(frozen=True)
class TaskKilled(_TerminalStop, EventSchema):
    """UBB STOPPED THIS WHOLE UNIT OF WORK ON A SPEND SIGNAL, and that is all
    this event ever means — a ceiling crossing, the enforcement patrol, or a
    customer-wide stop reaching it.

    Emitted exactly once per winning transition into `killed`, so racing
    callers (the sync endpoint, batch items, async settle workers, the patrol)
    can never double-emit. A stop is a signal point and not a wall: events
    arriving after it still land, bill, and count into both totals.
    """
    EVENT_TYPE = "task.killed"
    task_id: str = ""


@dataclass(frozen=True)
class TaskExpired(_TerminalStop, EventSchema):
    """NOBODY EVER TOLD UBB HOW THIS WHOLE UNIT OF WORK ENDED — it went quiet
    for longer than its silence window, or ran past its absolute deadline, and
    a sweeper wrote the honest answer.

    The same announcement on the same terms as `TaskKilled`, and a SEPARATE
    event for the reason the split exists: a subscriber paging an on-call
    engineer about spend wants the one above and not this one, and a
    subscriber cleaning up after crashed workers wants this one and not that.
    """
    EVENT_TYPE = "task.expired"
    task_id: str = ""


@dataclass(frozen=True)
class SubtaskKilled(_TerminalStop, EventSchema):
    """The same spend stop on CONTAINED work, which is killed ALONE: the
    parent keeps running and counting, so a subscriber tears down only the
    named child (#38).

    A parent's own crossing emits `task.killed` instead and cascades downward
    silently — cascaded children never emit this event, because they crossed
    nothing themselves.

    Ids are explicit: subtask_id is the stopped child, parent_task_id the
    parent whose totals its spend rolls up into. The totals and the limit are
    the child's own.
    """
    EVENT_TYPE = "subtask.killed"
    subtask_id: str = ""
    parent_task_id: str = ""


@dataclass(frozen=True)
class SubtaskExpired(_TerminalStop, EventSchema):
    """Nobody ever told UBB how this contained piece of work ended.

    One model and one status set means one rule (#154 §3.1), so contained work
    splits exactly as the whole unit does — and the ids and the altitude rule
    are `SubtaskKilled`'s.
    """
    EVENT_TYPE = "subtask.expired"
    subtask_id: str = ""
    parent_task_id: str = ""


#: The four, keyed on the two facts that choose between them. Private because
#: the reader below is the door: a bare mapping answers a state it does not
#: know with `KeyError: (False, 'completed')`, which is read exactly when
#: somebody is already confused, and it offers no place to say WHY the states a
#: tenant declares are absent.
_TERMINAL_STOP_EVENTS = {
    (False, TASK_STATUS_KILLED): TaskKilled,
    (False, TASK_STATUS_EXPIRED): TaskExpired,
    (True, TASK_STATUS_KILLED): SubtaskKilled,
    (True, TASK_STATUS_EXPIRED): SubtaskExpired,
}


def terminal_stop_event(status, *, is_contained):
    """The event class that announces a unit of work's terminal stop.

    ⚠ PASS THE STATE THE ROW NOW CARRIES, never the one the caller meant to
    write. The name of these events IS the state entered, so reading it back
    off the record is what makes that a property of the record rather than a
    habit each emitter has to keep — and it is the only thing the patrol's
    re-mint can do, since it announces a stop it did not apply.
    ``is_contained`` chooses the altitude.

    Refuses any other state, and that is the right answer rather than a
    fallback: the three states a TENANT declares announce nothing at all (the
    tenant already knows how the work ended), and a further state arriving here
    is a lane that has not said which of these two claims it makes.
    """
    try:
        return _TERMINAL_STOP_EVENTS[(is_contained, status)]
    except KeyError:
        announced = sorted({state for _, state in _TERMINAL_STOP_EVENTS})
        raise ValueError(
            f"{status!r} is not a state UBB announces a stop for — "
            f"the announced states are {announced}") from None


@dataclass(frozen=True)
class StopFired(EventSchema):
    """Customer-wide stop signal — the stop half of the stop/resume pair (#39).

    Emitted through the ``StopSignalState`` transition guard
    (apps/billing/gating/services/stop_signal_service.py): every lane that
    detects a floor/cap crossing — the real-time counter write, the durable
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
