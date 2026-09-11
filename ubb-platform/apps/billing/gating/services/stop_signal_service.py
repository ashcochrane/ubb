"""The stop-signal transition guard (#39, spec §D/§E; soft floor #40, §F;
three lines keyed by family, slice 6 §9, #458).

The single emission choke point for the customer-wide stop/resume pair
(``stop.fired`` / ``stop.cleared``) and the soft-floor pair
(``soft_floor.crossed`` / ``soft_floor.cleared`` — its own line, its own
episode sequence, never a suspension). Every lane that detects a crossing —
the real-time counter write (the live counter's ``_set_stop``), the durable
drawdown handler (``apps.billing.handlers``), the hourly reconcile — drives a
transition on the owner's ``StopSignalState`` row for THAT LINE; only the
WINNING transition emits the outbox event, and the emission commits
atomically with the ledger row, so the ledger and the event stream cannot
disagree and a crossing observed by several lanes fires exactly once per
episode.

THE LEDGER KEYS ONE ROW PER OWNER PER LINE, AND A LINE IS (FAMILY, WORD).
Two lines are stops — the wallet policy's hard floor and the customer spend
pool, each named by the `reason_code` its stop carries — and one is the
wind-down signal, the wallet policy's soft floor. The family is derived from
the line's word by the one map in ``core.controls`` (the kernel derives a
unit's stop the same way), the row records the control's identity beside it,
and the customer-wide pair carries all three so a subscriber routes the stop
to the control that fired. A customer stopped by its pool and by its floor at
once holds two open episodes that announce and clear independently; the stop
FLAG lifts only when no stop line is left open (``open_stop_lines`` is the
read the live counter's ``resume`` makes before it lifts anything).

Suspension folds into the stop lines (spec §D): the durable active->suspended
flip and its ``CustomerSuspended`` emission ride the winning STOP transition —
prepaid/meter_only in every enforcement-on mode (the Tier-1 baseline
suspension, unchanged), postpaid only when ``enforcing`` (D13). The
suspension records the stop that opened it, in that stop's own word (§9).
Floor-stop and suspension therefore can never disagree or double-fire. The
paired un-suspend stays with the clearing side (``LiveCounter.resume``'s
durable gate), decided on the DURABLE balance per D15 — a live-view clear
must not un-suspend an owner whose true balance is still past the floor.

Lock order (core/locking.py): Customer before StopSignalState — ``drive_stop``
locks the owner row first (it may flip status), then the ledger row; callers
already holding Wallet -> Customer via ``lock_for_billing`` nest cleanly.

Neither method swallows exceptions: each opens its own ``transaction.atomic``
(a savepoint inside an ambient transaction), and money-path callers wrap the
call in try/except so a signal-bookkeeping failure can never poison a
recorded event — the reconcile bottom line re-drives any missed transition.
"""
import logging

from django.db import transaction
from django.utils import timezone

from apps.platform.tenants.flags import enforcing
from apps.platform.work import reasons
from core import controls
from core.vocabulary import CONTROL_FAMILY_WALLET_POLICY

logger = logging.getLogger("ubb.billing")

#: THE THREE LINES. The two stop lines are the registry's own stop words —
#: the same constant the stop's `reason_code` carries, so the ledger and the
#: wire cannot spell one control two ways — and the wind-down line has the
#: ledger's own name, because it is a signal and no stop carries it.
LINE_HARD_FLOOR = reasons.HARD_FLOOR
LINE_CUSTOMER_SPEND_POOL = reasons.CUSTOMER_SPEND_POOL
LINE_SOFT_FLOOR = "soft_floor"

#: The lines that STOP a customer: each opens the customer-wide stop state,
#: and the flag lifts only when every one of them has cleared.
STOP_LINES = (LINE_HARD_FLOOR, LINE_CUSTOMER_SPEND_POOL)

STATE_STOPPED = "stopped"
STATE_CLEARED = "cleared"

# Clear-cause vocabulary for `StopSignalState.clear_reason` and for
# SoftFloorCleared.reason on a clearing transition. A balance re-cross via
# the credit hook (fast lane or its durable-balance fallback) says
# balance_recovered; the hourly bottom-line catch-up says reconciled.
CLEAR_BALANCE_RECOVERED = "balance_recovered"
CLEAR_RECONCILED = "reconciled"
# The upward live-balance repair (#45): the counter was dishonest — a repair,
# not a credit, lifted it back over the floor (the wedge lifted with no
# balance change; see apps/billing/gating/repair.py).
CLEAR_BALANCE_REPAIRED = "balance_repaired"
# The soft line's start-gate refusal word (the crossed event itself carries
# no reason; the ledger row's line is `LINE_SOFT_FLOOR`).
SOFT_FLOOR_REACHED = "soft_floor_reached"
# Administrative silent close on an enforcement_mode transition (the live
# counter's cleanup → close_all_silently) — never rides a StopCleared event
# (a config flip is not a re-cross).
CLEAR_ENFORCEMENT_MODE_TRANSITION = "enforcement_mode_transition"


def family_of_line(line):
    """The control family a ledger line belongs to. The two stop lines are
    the kernel's own map's answer for their word; the wind-down line is the
    wallet policy's, said here because no stop reason names it."""
    if line == LINE_SOFT_FLOOR:
        return CONTROL_FAMILY_WALLET_POLICY
    return controls.control_family(line)


def control_id_of(line, owner_id, tenant):
    """The row that declares the control whose line this is (#458, §15): the
    resolved CustomerSpendPool row for the pool's line, the billing profile
    or tenant billing configuration that carried the floor for the hard
    floor's — the same resolution the live counter's threshold compares
    against, asked again only on a crossing. None where the pool's line
    crossed with no row to name (it cannot: a missing pool never crosses),
    and None for the wind-down line, which declares no stop."""
    if line == LINE_CUSTOMER_SPEND_POOL:
        from apps.billing.gating.services.customer_spend_pool_service import (
            CustomerSpendPoolService)
        pool = CustomerSpendPoolService.resolve_config_for(tenant.id, owner_id)
        return pool.id if pool is not None else None
    if line == LINE_HARD_FLOOR:
        from apps.billing.queries import get_customer_floor_control_id
        return get_customer_floor_control_id(owner_id, tenant.id)
    return None


def emit_stamped(row, schema_instance):
    """Emit the signal event and stamp the ledger row's announcement in one
    §B unit (#43), inside the caller's savepoint — the stamp, the event, and
    the transition commit or vanish together, so the row can always prove
    what it last told the world."""
    from apps.platform.events.outbox import write_event

    outbox = write_event(schema_instance)
    row.announce_outbox_id = outbox.id
    row.save(update_fields=["announce_outbox_id", "updated_at"])


def _line_row(owner_id, line):
    from apps.billing.gating.models import StopSignalState
    return (StopSignalState.objects.select_for_update()
            .filter(owner_id=owner_id, control_family=family_of_line(line),
                    reason=line))


def _open_line(owner_id, tenant, line, *, control_id, now):
    """Open an episode on ``line`` — the shared stop-side transition. Returns
    the row when THIS call won (created, or flipped from cleared), else None."""
    from apps.billing.gating.models import StopSignalState

    row, created = StopSignalState.objects.select_for_update().get_or_create(
        owner_id=owner_id, control_family=family_of_line(line), reason=line,
        defaults={"tenant_id": tenant.id, "state": STATE_STOPPED,
                  "episode_seq": 1, "clear_reason": "",
                  "control_id": control_id, "transitioned_at": now})
    if not created:
        if row.state == STATE_STOPPED:
            return None
        row.state = STATE_STOPPED
        row.episode_seq += 1
        row.clear_reason = ""
        row.control_id = control_id
        row.transitioned_at = now
        row.save(update_fields=["state", "episode_seq", "clear_reason",
                                "control_id", "transitioned_at", "updated_at"])
    return row


def _close_line(owner_id, line, *, clear_reason):
    """Close ``line``'s open episode — the shared clearing transition.
    Returns the row when THIS call won (it was stopped), else None."""
    row = _line_row(owner_id, line).first()
    if row is None or row.state != STATE_STOPPED:
        return None
    row.state = STATE_CLEARED
    row.clear_reason = clear_reason
    row.transitioned_at = timezone.now()
    row.save(update_fields=["state", "clear_reason", "transitioned_at",
                            "updated_at"])
    return row


class StopSignalService:
    @staticmethod
    def drive_stop(owner_id, tenant, *, line, control_id, balance_micros=0):
        """Drive the stop transition for (owner, ``line``) — one of the two
        STOP_LINES, named by the stop word the lane produces.

        Returns the opened episode_seq when THIS call won the transition
        (state was cleared/absent), else None (already stopped — a sibling
        lane signaled this episode first). The winner, atomically:

        1. flips the ledger row to ``stopped``, increments ``episode_seq``
           and records ``control_id`` — the row that declares the control,
           passed by the caller because only the caller holds it (§1);
        2. emits ``stop.fired`` carrying the episode id, the line's word as
           `reason_code`, the family the word belongs to and the id;
        3. durably suspends the owner (active->suspended winning flip +
           ``CustomerSuspended``) — the suspension fold. Every caller is
           mode-gated (#42: two positions, signals exist only in enforcing);
           the postpaid ``enforcing`` re-check is defense against a mode
           flip racing an in-flight drive. An owner the OTHER stop line
           already suspended keeps that line's word: the suspension records
           the stop that opened it.

        ``balance_micros`` rides CustomerSuspended (the balance at the
        crossing, best available to the detecting lane; postpaid passes 0).
        """
        from apps.platform.customers.models import Customer
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import StopFired, CustomerSuspended

        if line not in STOP_LINES:
            raise ValueError(f"{line!r} is not a stop line: {STOP_LINES}")
        with transaction.atomic():
            owner = Customer.objects.select_for_update().get(id=owner_id)
            row = _open_line(owner_id, tenant, line, control_id=control_id,
                             now=timezone.now())
            if row is None:
                return None
            emit_stamped(row, StopFired(
                tenant_id=str(tenant.id), owner_id=str(owner.id),
                reason_code=line, control_family=row.control_family,
                control_id=str(row.control_id or ""), scope="customer",
                episode_seq=row.episode_seq))
            postpaid = tenant.billing_mode == "postpaid"
            if (not postpaid or enforcing(tenant)) and owner.status == "active":
                owner.status = "suspended"
                # THE THING THAT SUSPENDED THE OWNER IS THE STOP THAT OPENED
                # THE EPISODE, AND IT IS ONE WORD (slice 6 §9): the line's
                # word — the wallet floor's or the pool's — which is also what
                # `LiveCounter._MONEY_SUSPEND_REASONS` clears.
                owner.suspension_reason = line
                owner.save(update_fields=["status", "suspension_reason", "updated_at"])
                write_event(CustomerSuspended(
                    tenant_id=str(tenant.id), customer_id=str(owner.id),
                    reason=owner.suspension_reason, balance_micros=int(balance_micros)))
            return row.episode_seq

    @staticmethod
    def drive_clear(owner_id, tenant, *, line, clear_reason, balance_micros=0):
        """Drive the clearing transition for (owner, ``line``).

        Returns the episode_seq of the stop it closed when THIS call won
        (state was stopped), else None — a clear that didn't win emits
        nothing (spec §E). The winner flips the row to ``cleared``, records
        why (``clear_reason``) and emits ``stop.cleared`` carrying the closed
        episode, the line's word, family and control id, and the balance at
        clearance. Un-suspension is deliberately NOT here: it rides
        ``LiveCounter.resume``'s durable gate (D15), which also asks whether
        the OTHER stop line still holds the owner before lifting anything.
        """
        from apps.platform.events.schemas import StopCleared

        if line not in STOP_LINES:
            raise ValueError(f"{line!r} is not a stop line: {STOP_LINES}")
        with transaction.atomic():
            row = _close_line(owner_id, line, clear_reason=clear_reason)
            if row is None:
                return None
            emit_stamped(row, StopCleared(
                tenant_id=str(tenant.id), owner_id=str(owner_id),
                reason_code=line, control_family=row.control_family,
                control_id=str(row.control_id or ""), scope="customer",
                episode_seq=row.episode_seq,
                balance_micros=int(balance_micros)))
            return row.episode_seq

    @staticmethod
    def open_stop_lines(owner_id):
        """The stop lines currently holding this owner — ``[(line, family,
        control_id), ...]`` in line order, empty when no stop is open. The
        one read every lifting path makes: the customer-wide stop flag and
        the money suspension lift only when this answers empty (§9)."""
        from apps.billing.gating.models import StopSignalState

        rows = dict(
            (r.reason, r) for r in StopSignalState.objects.filter(
                owner_id=owner_id, reason__in=STOP_LINES, state=STATE_STOPPED))
        return [(line, rows[line].control_family, rows[line].control_id)
                for line in STOP_LINES if line in rows]

    @staticmethod
    def close_all_silently(tenant, *, reason):
        """Administratively close every OPEN episode of a tenant — the
        silent bulk close behind an enforcement_mode transition (D5 of #111;
        the ledger must not carry a stale 'stopped' row across the flip, or
        it would swallow the first real crossing's emission after re-enable).

        DELIBERATELY a bulk, NON-EMITTING UPDATE — do NOT rewrite this as a
        loop of ``drive_clear`` calls: per #39 a config flip is not a
        re-cross, so no ``stop.cleared`` may ride out, and ``episode_seq`` is
        preserved so episode ids never restart or collide (test_p7 pins the
        observable behavior). Closes open episodes on ALL THREE lines (a
        stale soft-floor 'crossed' row would equally swallow the first real
        crossing after re-enable); the patrol's re-mint leg skips
        administratively-closed rows, so the close never rides the wire.
        ``reason`` is the clear cause the rows record."""
        from apps.billing.gating.models import StopSignalState

        now = timezone.now()
        StopSignalState.objects.filter(tenant_id=tenant.id, state=STATE_STOPPED).update(
            state=STATE_CLEARED, clear_reason=reason,
            transitioned_at=now, updated_at=now)

    @staticmethod
    def drive_soft_crossed(owner_id, tenant, *, balance_micros=0,
                           soft_min_balance_micros=0):
        """Drive the crossing transition on the soft-floor line (#40, §F).

        Returns the opened episode_seq when THIS call won (state was
        cleared/absent), else None. The winner atomically flips the ledger
        row and emits ``soft_floor.crossed``. Deliberately unlike the hard
        pair: NO suspension fold, NO Redis flag, NO ack change, NO control
        id — the soft floor is a webhook + start-gate line only, it passes
        nothing to a kill, and its only detector is the durable drawdown
        lane (no fast lane; signal latency is outbox latency). The owner
        Customer row is never locked or touched here, so the Customer ->
        StopSignalState lock order holds trivially.
        """
        from apps.platform.events.schemas import SoftFloorCrossed

        with transaction.atomic():
            row = _open_line(owner_id, tenant, LINE_SOFT_FLOOR, control_id=None,
                             now=timezone.now())
            if row is None:
                return None
            emit_stamped(row, SoftFloorCrossed(
                tenant_id=str(tenant.id), owner_id=str(owner_id),
                balance_micros=int(balance_micros),
                soft_min_balance_micros=int(soft_min_balance_micros),
                episode_seq=row.episode_seq))
            return row.episode_seq

    @staticmethod
    def drive_soft_cleared(owner_id, tenant, *, reason, balance_micros=0,
                           soft_min_balance_micros=0):
        """Drive the clearing transition on the soft-floor line (#40, §F).

        Returns the episode_seq it closed when THIS call won (state was
        stopped), else None — a clear that didn't win emits nothing, so the
        pair fires exactly once per episode. Reached from the credit hook
        (``balance_recovered``) and the hourly reconcile (``reconciled``);
        ``reason`` is that clear cause, recorded on the row and carried on
        the event. ``soft_min_balance_micros`` may be None: an owner whose
        soft floor was UNCONFIGURED mid-episode still clears (there is no
        line left to be past), and the event says so honestly.
        """
        from apps.platform.events.schemas import SoftFloorCleared

        with transaction.atomic():
            row = _close_line(owner_id, LINE_SOFT_FLOOR, clear_reason=reason)
            if row is None:
                return None
            emit_stamped(row, SoftFloorCleared(
                tenant_id=str(tenant.id), owner_id=str(owner_id), reason=reason,
                balance_micros=int(balance_micros),
                soft_min_balance_micros=(None if soft_min_balance_micros is None
                                         else int(soft_min_balance_micros)),
                episode_seq=row.episode_seq))
            return row.episode_seq
