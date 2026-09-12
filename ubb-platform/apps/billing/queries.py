"""Billing Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(and the API layer) to read billing data. Functions return
model instances or scalars, never require callers to import
billing models directly.

If billing becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/gating/services/risk_service.py → get_billing_config(), get_customer_min_balance()
- apps/billing/handlers.py → get_customer_min_balance()
- apps/billing/stripe/services/stripe_service.py → get_billing_config()
- apps/billing/tenant_billing/services.py → get_billing_config()
- apps/metering/usage/services/usage_service.py → is_usage_period_closed()
- api/v1/spend_control_endpoints.py → signal_episodes(),
  customer_spend_pool_utilisation() (the two spend-control reports, #465)
"""


def get_billing_config(tenant_id):
    """Returns billing config for a tenant. Lazily creates with defaults if missing."""
    from apps.billing.tenant_billing.models import BillingTenantConfig

    config, _ = BillingTenantConfig.objects.get_or_create(tenant_id=tenant_id)
    return config


def _hard_floor_source(customer_id, tenant_id):
    """``(min_balance_micros, the row it came from)`` — the customer's
    billing profile where it carries an override, else the tenant's billing
    configuration. ONE resolution for the value and for the control's
    identity (#458): the two readers below cannot disagree about which rung
    answered."""
    from apps.billing.wallets.models import CustomerBillingProfile

    try:
        profile = CustomerBillingProfile.objects.get(customer_id=customer_id)
        if profile.min_balance_micros is not None:
            return profile.min_balance_micros, profile
    except CustomerBillingProfile.DoesNotExist:
        pass

    config = get_billing_config(tenant_id)
    return config.min_balance_micros, config


def get_customer_min_balance(customer_id, tenant_id):
    """Returns the effective min balance: customer override -> tenant default -> 0."""
    return _hard_floor_source(customer_id, tenant_id)[0]


def get_customer_floor_control_id(customer_id, tenant_id):
    """The id of the row that carries the customer's hard floor — the
    Wallet policy control a floor stop names as its `control_id` (slice 6
    §1, §15, #458): the billing profile where an override exists, else the
    tenant's billing configuration. Resolved by the same walk as the value,
    so the stop that fired on a floor names the row that set it."""
    return _hard_floor_source(customer_id, tenant_id)[1].id


def get_customer_soft_min_balance(customer_id, tenant_id):
    """Returns the effective SOFT floor value (#40, spec §F), or None = no
    soft floor. Same orientation as get_customer_min_balance: the wind-down
    line is -value (negative values place it above zero). Resolution mirrors
    the hard floor's — customer override -> tenant default -> None — then
    clamps so the soft line sits AT OR ABOVE the hard floor's line
    (value <= the hard's value): the set-time API validation can go stale
    across levels (a customer override vs a later-changed tenant hard
    default), so the resolver, not the writer, guarantees the invariant.
    """
    from apps.billing.wallets.models import CustomerBillingProfile

    soft = None
    try:
        profile = CustomerBillingProfile.objects.get(customer_id=customer_id)
        soft = profile.soft_min_balance_micros
    except CustomerBillingProfile.DoesNotExist:
        pass
    if soft is None:
        soft = get_billing_config(tenant_id).soft_min_balance_micros
    if soft is None:
        return None
    return min(soft, get_customer_min_balance(customer_id, tenant_id))


def get_customer_balance(customer_id):
    """Returns wallet balance, or 0 if no wallet exists."""
    from apps.billing.wallets.models import Wallet

    try:
        wallet = Wallet.objects.get(customer_id=customer_id)
        return wallet.balance_micros
    except Wallet.DoesNotExist:
        return 0


def record_live_usage_debit(owner_id, tenant, billed_cost_micros, *,
                            effective_at=None, now=None):
    """Tier-2 synchronous live-counter hook — the cross-product PORT for the
    metering choke point.

    Maintains the billing owner's live spend/balance counter synchronously at
    record_usage time so the response can carry a real stop verdict (P3 reads
    it). Exposed here (the sanctioned billing read/port contract) so metering
    need not import a billing internal — mirrors is_usage_period_closed().
    No-op unless the tenant has enforcement enabled. Returns the live verdict
    dict ({mode, balance_micros|spend_micros, stop fields}) or None.
    """
    from apps.billing.gating.services.live_counter import LiveCounter
    return LiveCounter.debit(
        owner_id, tenant, billed_cost_micros, effective_at=effective_at, now=now)


def read_live_stop(owner_id, tenant) -> dict:
    """Read the customer-wide stop verdict for a billing owner — the
    cross-product port for the metering replay paths. Returns
    {stop, stop_reason, stop_scope}; {stop: False, ...} when enforcement is off
    (short-circuits before touching Redis)."""
    from apps.billing.gating.services.live_counter import LiveCounter
    return LiveCounter.read(owner_id, tenant)


def get_negative_balance_stats(tenant_id=None):
    """The aged-negatives operations figure (#41, pin 10) — a cross-product read.
    Counts wallets currently below zero and
    the age of the oldest, from Wallet.negative_since (the ≥0 → <0 transition
    stamp; soft-deleted wallets excluded by the default manager). Visibility
    only: no reminder events, no auto-close — collections stay between the
    tenant, their customer, and Stripe."""
    from django.db.models import Min
    from django.utils import timezone
    from apps.billing.wallets.models import Wallet
    qs = Wallet.objects.filter(negative_since__isnull=False)
    if tenant_id is not None:
        qs = qs.filter(customer__tenant_id=tenant_id)
    oldest = qs.aggregate(oldest=Min("negative_since"))["oldest"]
    return {
        "negative_balance_count": qs.count(),
        "oldest_negative_age_seconds": (
            (timezone.now() - oldest).total_seconds() if oldest else 0.0),
    }


def get_patrol_stats(tenant_id=None):
    """Patrol-outcome counters (#44,
    delivery spec §F) — trailing 7 days of day-bucketed ``PatrolOutcome``
    rows, summed per outcome. Visibility only: a nonzero count means the
    patrol actually healed a crash/blind-window corner (re-minted a lost
    announcement, re-aligned an orphaned stop flag, swept a crashed kill,
    repaired a wedged live balance — count, micros, lapsed candidates; #45);
    a persistent spike means a lane is unhealthy."""
    from datetime import timedelta
    from django.db.models import Sum
    from django.utils import timezone
    from apps.billing.gating import patrol
    from apps.billing.gating.models import PatrolOutcome
    since = timezone.now().date() - timedelta(days=7)
    qs = PatrolOutcome.objects.filter(day__gte=since)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    agg = dict(qs.values_list("outcome").annotate(n=Sum("count")))
    return {f"patrol_{outcome}_7d": int(agg.get(outcome, 0))
            for outcome in (patrol.OUTCOME_REMINTED,
                            patrol.OUTCOME_FLAG_REALIGNED,
                            patrol.OUTCOME_SWEEP_KILLED,
                            patrol.OUTCOME_REPAIRED,
                            patrol.OUTCOME_REPAIRED_MICROS,
                            patrol.OUTCOME_REPAIR_LAPSED)}


def get_stop_signal_state(owner_id, tenant_id, *, line):
    """Plain-data snapshot of the owner's DURABLE stop-signal ledger row for
    one LINE (#41 stop-context tagging; three lines since #458) — the
    cross-product read for the metering record/settle paths and the retired
    report. ``line`` is the ledger's own line name: the two stop words, or
    the wind-down line. Returns {state, episode_seq, reason, control_family,
    control_id, clear_reason, transitioned_at} or None when the line has
    never transitioned for this owner. One indexed point read (unique on
    (owner, family, line)); the caller decides what an open episode means."""
    from apps.billing.gating.models import StopSignalState
    from apps.billing.gating.services.stop_signal_service import family_of_line
    return (StopSignalState.objects
            .filter(owner_id=owner_id, tenant_id=tenant_id,
                    control_family=family_of_line(line), reason=line)
            .values("state", "episode_seq", "reason", "control_family",
                    "control_id", "clear_reason", "transitioned_at")
            .first())


def signal_episodes(tenant_id, *, owner_ids=None, since=None, until=None) -> list[dict]:
    """Every customer-wide episode the signal ledger's three lines ever
    opened for this tenant, as plain data — the Pool and Wallet rows of
    Stops and breaches (#465, slice 6 §14).

    THE HISTORY IS THE OUTBOX PAIR, BY CONSTANT; THE LEDGER ROW IS THE
    BACKSTOP. The two stop lines share one pair (`StopFired` /
    `StopCleared`) and are told apart by the word each carries (#458); the
    wind-down line has a pair of its own. Every event type is the payload
    class's constant, never a spelled name (#464). An open episode outlives
    outbox retention because the row still says `stopped`, so a row with no
    surviving opening is dated by the row's own instant; a cleared episode
    whose clearing aged out is closed the same way. An episode nothing can
    date at all — both announcements gone and the row moved on — is not
    listed, because it cannot be placed in any window.

    WHAT EACH ROW CARRIES BEYOND THE EPISODE. The control (family, id) off
    the announcement, or off the row for the current episode. For a pool's
    line: the pool row's configured amount and its stop line as they stand
    now (null where the row is gone) and the crossing month's label — the
    pool's crossing is month-scoped. For the hard floor: the floor the control row carries now
    (the crossing did not record the figure, and the declaration can have
    moved since) and the balance the suspension announced beside the stop —
    the stop pair carries none, and a customer already suspended by the
    other line announces no second suspension, so it is null where none was
    announced. For the soft floor: both figures off the pair itself, no stop
    word and no control — the wind-down line stops nothing (§F).
    ``owner_ids`` narrows to the customers named — a pooled seat's own pool
    line is declared on the seat while its floor is its billing owner's, so
    a customer filter asks for both (review of #465); the window selects on
    the opening instant. Ordered by opening instant.
    """
    from apps.billing.gating.models import CustomerSpendPool, StopSignalState
    from apps.billing.gating.services.stop_signal_service import (
        LINE_CUSTOMER_SPEND_POOL, LINE_HARD_FLOOR, LINE_SOFT_FLOOR, STATE_STOPPED,
        STOP_LINES, family_of_line)
    from apps.platform.events.models import OutboxEvent
    from apps.platform.events.schemas import (
        CustomerSuspended, SoftFloorCleared, SoftFloorCrossed, StopCleared, StopFired)
    from core.crossing import month_label_bounds, spend_pool_stop_line

    owners = None if owner_ids is None else [str(o) for o in owner_ids]

    def _announcements(*event_types):
        qs = OutboxEvent.objects.filter(tenant_id=tenant_id, event_type__in=event_types)
        if owners is not None:
            qs = qs.filter(payload__owner_id__in=owners)
        return qs.order_by("created_at").values_list("event_type", "payload", "created_at")

    # (owner, line, episode) -> the episode as the announcements tell it.
    episodes = {}

    def _episode(owner, line, seq):
        return episodes.setdefault((owner, line, seq), {
            "owner_id": owner, "line": line, "episode_seq": seq,
            "opened_at": None, "closed_at": None, "control_id": None,
            "balance_at_crossing_micros": None, "floor_micros": None})

    pairs = (
        (StopFired.EVENT_TYPE, StopCleared.EVENT_TYPE, None),
        (SoftFloorCrossed.EVENT_TYPE, SoftFloorCleared.EVENT_TYPE, LINE_SOFT_FLOOR),
    )
    for opened_type, closed_type, fixed_line in pairs:
        for event_type, payload, created_at in _announcements(opened_type, closed_type):
            line = fixed_line or payload.get("reason_code")
            if line not in STOP_LINES and line != LINE_SOFT_FLOOR:
                continue
            ep = _episode(payload["owner_id"], line, payload.get("episode_seq"))
            if event_type == opened_type:
                if ep["opened_at"] is None:
                    ep["opened_at"] = created_at
                    ep["control_id"] = payload.get("control_id") or None
                    if line == LINE_SOFT_FLOOR:
                        ep["balance_at_crossing_micros"] = payload.get("balance_micros")
                        ep["floor_micros"] = payload.get("soft_min_balance_micros")
            else:
                ep["closed_at"] = created_at

    rows_qs = StopSignalState.objects.filter(tenant_id=tenant_id)
    if owners is not None:
        rows_qs = rows_qs.filter(owner_id__in=owners)
    for state in rows_qs.values("owner_id", "reason", "state", "episode_seq",
                                "control_id", "transitioned_at"):
        key = (str(state["owner_id"]), state["reason"], state["episode_seq"])
        if state["state"] == STATE_STOPPED:
            ep = _episode(*key)
            if ep["opened_at"] is None:
                ep["opened_at"] = state["transitioned_at"]
            if ep["control_id"] is None and state["control_id"]:
                ep["control_id"] = str(state["control_id"])
        elif key in episodes and episodes[key]["closed_at"] is None:
            episodes[key]["closed_at"] = state["transitioned_at"]

    dated = sorted((ep for ep in episodes.values() if ep["opened_at"] is not None),
                   key=lambda ep: (ep["opened_at"], ep["owner_id"], ep["line"]))
    if since is not None:
        dated = [ep for ep in dated if ep["opened_at"] >= since]
    if until is not None:
        dated = [ep for ep in dated if ep["opened_at"] < until]

    # The balance the hard floor's stop announced beside itself: the first
    # suspension in the floor's word at or after the episode opened and
    # before it closed (or before the owner's next floor episode).
    floor_eps = [ep for ep in dated if ep["line"] == LINE_HARD_FLOOR]
    if floor_eps:
        suspensions = (OutboxEvent.objects
                       .filter(tenant_id=tenant_id, event_type=CustomerSuspended.EVENT_TYPE,
                               payload__reason=LINE_HARD_FLOOR)
                       .order_by("created_at").values_list("payload", "created_at"))
        by_owner = {}
        for payload, created_at in suspensions:
            by_owner.setdefault(payload["customer_id"], []).append(
                (created_at, payload.get("balance_micros")))
        next_open = {}
        for ep in sorted(floor_eps, key=lambda e: e["opened_at"], reverse=True):
            key = ep["owner_id"]
            ep["_until"] = ep["closed_at"] or next_open.get(key)
            next_open[key] = ep["opened_at"]
        for ep in floor_eps:
            for created_at, balance in by_owner.get(ep["owner_id"], []):
                if created_at >= ep["opened_at"] and (
                        ep["_until"] is None or created_at < ep["_until"]):
                    ep["balance_at_crossing_micros"] = balance
                    break
            del ep["_until"]
            ep["floor_micros"] = get_customer_min_balance(ep["owner_id"], tenant_id)

    pool_ids = {ep["control_id"] for ep in dated
                if ep["line"] == LINE_CUSTOMER_SPEND_POOL and ep["control_id"]}
    pools = {str(pk): (cap, spend_pool_stop_line(cap, pct))
             for pk, cap, pct in CustomerSpendPool.objects
             .filter(tenant_id=tenant_id, id__in=pool_ids)
             .values_list("id", "cap_micros", "hard_stop_pct")}

    out = []
    for ep in dated:
        a_pool = ep["line"] == LINE_CUSTOMER_SPEND_POOL
        soft = ep["line"] == LINE_SOFT_FLOOR
        out.append({
            "control_family": family_of_line(ep["line"]),
            "reason_code": None if soft else ep["line"],
            "soft_floor": soft,
            "owner_id": ep["owner_id"],
            "episode_seq": ep["episode_seq"],
            "control_id": ep["control_id"],
            "opened_at": ep["opened_at"],
            "closed_at": ep["closed_at"],
            "balance_at_crossing_micros": ep["balance_at_crossing_micros"],
            "floor_micros": ep["floor_micros"],
            "cap_micros": pools[ep["control_id"]][0]
                          if a_pool and ep["control_id"] in pools else None,
            # The line the crossing was measured against, off the row as it
            # stands (the crossing recorded no figure); the composition layer
            # replays the drawdown up to it to name the Charge that reached
            # it where the recording route marked none. Never the enforce
            # mode's answer — an open episode proves the pool was blocking.
            "stop_threshold_micros": pools[ep["control_id"]][1]
                                     if a_pool and ep["control_id"] in pools else None,
            "period": month_label_bounds(ep["opened_at"])[0] if a_pool else None,
        })
    return out


def customer_spend_pool_utilisation(tenant_id, customer_id) -> dict:
    """Where one customer's known period charges stand against the pool
    that applies to them — the status pair the pool's status route publishes
    and Utilisation and headroom carries beside its per-unit rows (#456 §13,
    #465 §14), composed ONCE here for both readers.

    The basis is the durable pair (`CustomerSpendPoolService.period_basis` —
    the resolved period charges, a lower bound wherever the count beside
    them is not zero) and the assessment is the kernel's crossing module's,
    over the resolved pool row: the customer's own, else the tenant default
    where that reaches them (a seat, never a business). No pool is
    `cap_micros` 0 with every assessed figure null and `blocking_occurred`
    false — the row's own reading of an absent pool.
    """
    from apps.billing.gating.services.customer_spend_pool_service import (
        CustomerSpendPoolService)
    from core.crossing import spend_pool_assessment
    from core.vocabulary import SPEND_POOL_ENFORCE_MODE_ALERT_ONLY

    cfg = CustomerSpendPoolService.resolve_config_for(tenant_id, customer_id)
    label, known_micros, unresolved_count = CustomerSpendPoolService.period_basis(
        tenant_id, customer_id)
    assessment = spend_pool_assessment(cfg, known_micros)
    return {"period": label,
            "cap_micros": cfg.cap_micros if cfg else 0,
            "enforce_mode": cfg.enforce_mode if cfg else SPEND_POOL_ENFORCE_MODE_ALERT_ONLY,
            "known_period_charges_micros": known_micros,
            "unresolved_posting_count": unresolved_count,
            **assessment._asdict()}


def get_open_customer_stops(owner_id, tenant_id):
    """Every STOP line currently holding the owner, as plain data, in line
    order — ``[{episode_seq, reason, control_family, control_id,
    transitioned_at}, ...]``, empty when no stop is open (#458, slice 6 §9).
    A customer stopped by its pool and by its floor at once answers two
    rows, one per episode; the stop-context tagging marks each. The read is
    the ledger service's own (`open_stop_lines`), the one the lifting paths
    make; an owner's id is unique across tenants, so the tenant is not a
    second filter here."""
    from apps.billing.gating.services.stop_signal_service import StopSignalService
    return StopSignalService.open_stop_lines(owner_id)


def is_usage_period_closed(owner_id, period_start) -> bool:
    """True when the billing owner's postpaid usage invoice for the calendar
    month starting at ``period_start`` (date) is FROZEN — i.e. matches the
    same predicate that destroys billability at push time.

    Frozen = status in (pushing, pushed, skipped, failed_permanent)
    OR push_phase != "" OR stripe_invoice_id != "" OR line_snapshot != [].
    The line_snapshot check is the load-bearing one: under the F0.1 resume
    semantics the lines are frozen at FIRST CLAIM (Phase 1), so a
    ``status="failed"`` row whose Phase 2 died before Invoice.create — and a
    reclaimed ``pending`` row — both carry a frozen snapshot while reading as
    "untouched" on status/phase/pointer alone. Accepting a backfill into such
    a period would commit an event the frozen lines permanently exclude:
    recorded but never billed. A genuinely-fresh ``pending`` row (empty
    snapshot, no phase, no pointer) re-aggregates safely and does NOT close
    the period. No row at all = open.
    """
    from django.db.models import Q
    from apps.billing.invoicing.models import CustomerUsageInvoice

    return CustomerUsageInvoice.objects.filter(
        customer_id=owner_id, period_start=period_start,
    ).filter(
        Q(status__in=("pushing", "pushed", "skipped", "failed_permanent"))
        | ~Q(push_phase="") | ~Q(stripe_invoice_id="") | ~Q(line_snapshot=[])
    ).exists()
