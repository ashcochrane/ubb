"""Upward live-balance repair — the honesty repair (#45, delivery spec §D).

"We CANNOT have a wallet balance that does not show reality." An orphaned
hold — acquired on the fast lane, its ``RawIngestEvent`` row rolled back with
a crashed request — leaves the prepaid live counter (``ubb:livebal:{owner}``)
permanently below reality: the stingy direction, false stops when it drifts
far enough. The MIN-merge can only lower; this is its grace-gated upward
sibling, the fifth patrol job (rides ``run_patrol`` on the hourly reconcile
beat; enforcing tenants only).

Per owner, from one snapshot under ``lock_for_billing`` (the lock every
credit/drawdown/settle path takes): **expected** = durable balance −
Σ(genuinely pending holds, via the ``apps.metering.queries`` contract); then
the live counter is read; **deficit** = expected − live, when past the
de-minimis (below it, drift is noise, not dishonesty). Two-pass grace: the
first pass observing a deficit writes a ``LiveBalanceRepair`` candidate and
changes nothing; the immediately-next pass (staleness-guarded) still
measuring one applies **min(first, second)** — the amount proven stable
across a full hour — as a **relative INCRBY**, never an absolute SET, so a
transient in-flight window (holds land in Redis before their rows; settles
flip rows before crediting back) can inflate one measurement but never the
repair. A vanished deficit lapses the candidate.

Resume on repair: a repair that lifts a wedged stop drives the clearing
transition through the same ``StopSignalState`` guard as every other
clearing — ``stop.cleared`` exactly once — and re-aligns the fast flag.

Untouched neighbors: the MIN-merge stays byte-identical (live may transiently
sit ABOVE expected by up to the pending sum — the generous direction,
draining at settle). The postpaid spend counter is out of scope: its drift
lane is the MAX-merge + budget reconcile, and the repair exists only where
holds exist. The repair is part of the fast lane and switches off with it
(the arrival-signals switch, #46).
"""
import logging
from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.platform.tenants.flags import arrival_signals_on

logger = logging.getLogger("ubb.billing")

# Below this, a measured deficit is drift noise, not dishonesty — never a
# candidate, never a repair. $1.
REPAIR_DE_MINIMIS_MICROS = 1_000_000

# A candidate must be confirmed by the IMMEDIATELY-NEXT hourly pass. Older
# than this (a skipped beat, worker downtime) and hour-stability is unproven:
# the candidate lapses unconfirmed and the observation starts over.
CANDIDATE_FRESH_WINDOW = timedelta(hours=2, minutes=30)

# Repair-rate spike alert (§D): repairs per tenant per trailing 24h past
# either threshold log CRITICAL — a repair epidemic reads as the bug it is
# (a broken hold/settle path), never as silent self-healing. The Stage D
# drawdown-repair spike is the prior art.
REPAIR_SPIKE_COUNT_24H = 10
REPAIR_SPIKE_AMOUNT_MICROS_24H = 100_000_000  # $100

STATUS_CANDIDATE = "candidate"
STATUS_REPAIRED = "repaired"
STATUS_LAPSED = "lapsed"


def repair_live_balances(tenant):
    """Run the §D repair across every wallet owner of a prepaid/meter_only
    enforcing tenant, one isolated pass per owner, and return the patrol
    outcome counts ({repaired, repaired_micros, repair_lapsed})."""
    from apps.billing.gating.patrol import (OUTCOME_REPAIR_LAPSED,
                                            OUTCOME_REPAIRED,
                                            OUTCOME_REPAIRED_MICROS)
    from apps.billing.wallets.models import Wallet

    counts = {OUTCOME_REPAIRED: 0, OUTCOME_REPAIRED_MICROS: 0,
              OUTCOME_REPAIR_LAPSED: 0}
    # The repair exists only where holds exist: the prepaid wallet lane.
    # Postpaid spend drift is owned by the MAX-merge + budget reconcile.
    # Part of the fast lane, so it switches off with it (#46, §E): with
    # arrival signals off nothing holds and nothing reads the counter — a
    # deficit is moot, and the repair is inert.
    if not arrival_signals_on(tenant) or tenant.billing_mode == "postpaid":
        return counts
    for owner_id in Wallet.objects.filter(
            customer__tenant=tenant).values_list("customer_id", flat=True):
        try:
            outcome = _repair_owner(owner_id, tenant)
        except Exception:
            logger.exception("live_balance.repair_owner_failed", extra={
                "data": {"tenant_id": str(tenant.id),
                         "owner_id": str(owner_id)}})
            continue
        for key, n in (outcome or {}).items():
            counts[key] += n
    if counts[OUTCOME_REPAIRED]:
        _alert_on_repair_spike(tenant)
    return counts


def _repair_owner(owner_id, tenant):
    """One owner, one pass: measure, then advance the candidate lifecycle.

    Everything runs inside ``lock_for_billing`` — the durable balance and the
    pending-hold sum come from one snapshot serialized against every
    credit/drawdown/settle path, and concurrent passes serialize on the same
    lock so a candidate resolves exactly once. The live counter is read
    AFTER the DB snapshot (spec order); in-flight fast-lane movement can
    only inflate a single measurement, which min(d1, d2) discards. Lock
    order: Wallet -> Customer (lock_for_billing) -> LiveBalanceRepair;
    ``drive_clear`` nests cleanly. Returns an outcome-count fragment.
    """
    from apps.billing.gating.models import LiveBalanceRepair
    from apps.billing.gating.patrol import (OUTCOME_REPAIR_LAPSED,
                                            OUTCOME_REPAIRED,
                                            OUTCOME_REPAIRED_MICROS)
    from apps.billing.locking import lock_for_billing
    from apps.billing.queries import get_customer_balance
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    from apps.metering.queries import get_pending_held_estimate_total

    now = timezone.now()
    counts = {}
    with transaction.atomic():
        lock_for_billing(owner_id)
        durable = int(get_customer_balance(owner_id))
        pending = int(get_pending_held_estimate_total(tenant.id, owner_id))
        try:
            live = LiveLedgerService.read_prepaid(owner_id)
        except Exception:
            # Redis blind: nothing can be measured or applied. An open
            # candidate stays open — the next pass (or the staleness guard)
            # resolves it.
            logger.warning("live_balance.repair_redis_blind", extra={
                "data": {"owner_id": str(owner_id)}})
            return counts
        # No counter, no deficit: an absent key is seeded from durable at
        # first use, so there is nothing to repair.
        deficit = None if live is None else durable - pending - live

        candidate = (LiveBalanceRepair.objects.select_for_update()
                     .filter(owner_id=owner_id, status=STATUS_CANDIDATE)
                     .first())
        if candidate is not None and now - candidate.created_at >= CANDIDATE_FRESH_WINDOW:
            # Too stale to prove the deficit held for one full hour: lapse
            # unconfirmed (second_deficit stays null — the in-window second
            # measurement never happened) and start over below.
            _lapse(candidate, now)
            counts[OUTCOME_REPAIR_LAPSED] = counts.get(OUTCOME_REPAIR_LAPSED, 0) + 1
            candidate = None

        qualifying = deficit is not None and deficit >= REPAIR_DE_MINIMIS_MICROS
        if candidate is None:
            if qualifying:
                LiveBalanceRepair.objects.create(
                    tenant=tenant, owner_id=owner_id,
                    status=STATUS_CANDIDATE, first_deficit_micros=deficit,
                    durable_balance_micros=durable,
                    pending_hold_micros=pending)
                logger.info("live_balance.repair_candidate", extra={"data": {
                    "owner_id": str(owner_id), "deficit_micros": deficit,
                    "durable_micros": durable, "pending_micros": pending}})
            return counts

        if not qualifying:
            # The deficit drained between passes (settle backlog, credit) —
            # or the counter vanished. Lapse with the second bottom line.
            _lapse(candidate, now, second_deficit=deficit,
                   durable=durable, pending=pending)
            counts[OUTCOME_REPAIR_LAPSED] = counts.get(OUTCOME_REPAIR_LAPSED, 0) + 1
            return counts

        applied = _apply_increment(
            owner_id, min(candidate.first_deficit_micros, deficit))
        if applied is None:
            # The key vanished between the read and the apply (or Redis went
            # blind): nothing was moved; the deficit is moot without a
            # counter. Lapse rather than claim a repair that never applied.
            _lapse(candidate, now, second_deficit=deficit,
                   durable=durable, pending=pending)
            counts[OUTCOME_REPAIR_LAPSED] = counts.get(OUTCOME_REPAIR_LAPSED, 0) + 1
            return counts

        amount, live_after = applied
        candidate.status = STATUS_REPAIRED
        candidate.second_deficit_micros = deficit
        candidate.applied_micros = amount
        candidate.live_before_micros = live
        candidate.live_after_micros = live_after
        candidate.durable_balance_micros = durable
        candidate.pending_hold_micros = pending
        candidate.resolved_at = now
        candidate.save(update_fields=[
            "status", "second_deficit_micros", "applied_micros",
            "live_before_micros", "live_after_micros",
            "durable_balance_micros", "pending_hold_micros", "resolved_at",
            "updated_at"])
        logger.warning("live_balance.repaired", extra={"data": {
            "owner_id": str(owner_id), "applied_micros": amount,
            "first_deficit_micros": candidate.first_deficit_micros,
            "second_deficit_micros": deficit,
            "live_before_micros": live, "live_after_micros": live_after,
            "durable_micros": durable, "pending_micros": pending}})
        counts[OUTCOME_REPAIRED] = 1
        counts[OUTCOME_REPAIRED_MICROS] = amount
        _resume_if_wedge_lifted(owner_id, tenant, live_after, durable)
    return counts


def _lapse(candidate, now, second_deficit=None, durable=None, pending=None):
    """Close a candidate without repairing. With a second measurement
    (vanished deficit / nothing to apply) the row gains the resolving bottom
    line and snapshot; a stale lapse passes none — ``second_deficit_micros``
    stays null, marking a confirmation window that never happened."""
    candidate.status = STATUS_LAPSED
    candidate.resolved_at = now
    fields = ["status", "resolved_at", "updated_at"]
    if second_deficit is not None or durable is not None:
        candidate.second_deficit_micros = second_deficit
        candidate.durable_balance_micros = durable
        candidate.pending_hold_micros = pending
        fields += ["second_deficit_micros", "durable_balance_micros",
                   "pending_hold_micros"]
    candidate.save(update_fields=fields)


def _apply_increment(owner_id, amount):
    """Apply the repair as a guarded relative INCRBY on the live counter —
    only if the key still exists (creating one here would plant a stale
    absolute value that first-use seeding owns). Returns (amount, new value)
    or None when nothing was applied. Reuses the credit hook's Lua so the
    upward move rides the exact primitive every credit site uses."""
    from apps.billing.gating.services.live_ledger_service import (
        LEDGER_TTL_SECONDS, _CREDIT_IF_PRESENT, _client, _livebal_key)

    try:
        v = _client().eval(_CREDIT_IF_PRESENT, 1, _livebal_key(owner_id),
                           int(amount), LEDGER_TTL_SECONDS)
    except Exception:
        logger.warning("live_balance.repair_apply_failed",
                       extra={"data": {"owner_id": str(owner_id)}})
        return None
    return None if v is None else (int(amount), int(v))


def _resume_if_wedge_lifted(owner_id, tenant, live_after, durable):
    """Resume on repair (§D): re-check the floor_stop family against the
    repaired balance; a repair that lifted a wedged stop drives the clearing
    transition — ``stop.cleared`` exactly once, through the same guard as
    every other clearing — deletes the fast flag, and un-suspends on the
    DURABLE balance (D15). Best-effort: a failure here degrades to the next
    reconcile bottom line (late, never lost), never rolls back the repair's
    audit row."""
    from apps.billing.queries import get_customer_min_balance
    from apps.billing.gating.services.live_ledger_service import LiveLedgerService
    from apps.billing.gating.services.stop_signal_service import (
        CLEAR_BALANCE_REPAIRED, StopSignalService)

    try:
        floor = get_customer_min_balance(owner_id, tenant.id)
        if live_after < -floor:
            return  # still past the floor: the stop stands
        StopSignalService.drive_clear(owner_id, tenant,
                                      reason=CLEAR_BALANCE_REPAIRED,
                                      balance_micros=live_after)
        LiveLedgerService._clear_stop(owner_id)
        if durable >= -floor:
            LiveLedgerService._maybe_unsuspend(owner_id)
    except Exception:
        logger.warning("live_balance.repair_resume_failed",
                       extra={"data": {"owner_id": str(owner_id)}})


def _alert_on_repair_spike(tenant):
    """CRITICAL when the tenant's trailing-24h repairs cross either threshold
    (count or total amount). Checked on every pass that applied a repair, so
    the alert accompanies the epidemic and stops with it."""
    from django.db.models import Count, Sum
    from apps.billing.gating.models import LiveBalanceRepair

    now = timezone.now()
    agg = LiveBalanceRepair.objects.filter(
        tenant=tenant, status=STATUS_REPAIRED,
        resolved_at__gte=now - timedelta(hours=24),
    ).aggregate(n=Count("id"), total=Sum("applied_micros"))
    n, total = int(agg["n"] or 0), int(agg["total"] or 0)
    if n >= REPAIR_SPIKE_COUNT_24H or total >= REPAIR_SPIKE_AMOUNT_MICROS_24H:
        logger.critical("live_balance.repair_spike", extra={"data": {
            "tenant_id": str(tenant.id), "repairs_24h": n,
            "amount_micros_24h": total}})
