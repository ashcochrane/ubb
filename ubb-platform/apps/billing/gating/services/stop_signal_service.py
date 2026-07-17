"""The stop-signal transition guard (#39, spec §D/§E; soft floor #40, §F).

The single emission choke point for the customer-wide stop/resume pair
(``stop.fired`` / ``stop.cleared``) and the soft-floor pair
(``soft_floor.crossed`` / ``soft_floor.cleared`` — its own family, its own
episode sequence, never a suspension). Every lane that detects a crossing —
the fast Redis lane at arrival (``LiveLedgerService._set_stop``), the durable
drawdown handler (``apps.billing.handlers``), the hourly reconcile — drives a
transition on the owner's ``StopSignalState`` row; only the WINNING transition
emits the outbox event, and the emission commits atomically with the ledger
row, so the ledger and the event stream cannot disagree and a crossing
observed by several lanes fires exactly once per episode.

Suspension folds into the stop family (spec §D): the durable active->suspended
flip and its ``CustomerSuspended`` emission ride the winning STOP transition —
prepaid/meter_only in every enforcement-on mode (the Tier-1 baseline
suspension, unchanged), postpaid only when ``enforcing`` (D13). Floor-stop and
suspension therefore can never disagree or double-fire. The paired un-suspend
stays with the clearing call sites (``LiveLedgerService._maybe_unsuspend``),
which gate on the DURABLE balance per D15 — a live-view clear must not
un-suspend an owner whose true balance is still past the floor.

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

logger = logging.getLogger("ubb.billing")

FAMILY_FLOOR_STOP = "floor_stop"
FAMILY_SOFT_FLOOR = "soft_floor"

STATE_STOPPED = "stopped"
STATE_CLEARED = "cleared"

# Clear-cause vocabulary for StopCleared.reason / SoftFloorCleared.reason /
# the ledger row's reason on a clearing transition. A balance re-cross via
# the credit hook (fast lane or its durable-balance fallback) says
# balance_recovered; the hourly bottom-line catch-up says reconciled.
CLEAR_BALANCE_RECOVERED = "balance_recovered"
CLEAR_RECONCILED = "reconciled"
# The soft_floor family's stop-side reason (ledger row + the start-gate
# refusal share the string; the crossed event itself carries no reason).
SOFT_FLOOR_REACHED = "soft_floor_reached"
# Administrative silent close on an enforcement_mode transition (cleanup_keys)
# — never rides a StopCleared event (a config flip is not a re-cross).
CLEAR_ENFORCEMENT_MODE_TRANSITION = "enforcement_mode_transition"


class StopSignalService:
    @staticmethod
    def drive_stop(owner_id, tenant, *, reason, balance_micros=0):
        """Drive the stop transition for (owner, floor_stop).

        Returns the opened episode_seq when THIS call won the transition
        (state was cleared/absent), else None (already stopped — a sibling
        lane signaled this episode first). The winner, atomically:

        1. flips the ledger row to ``stopped`` and increments ``episode_seq``;
        2. emits ``stop.fired`` carrying the episode id;
        3. durably suspends the owner (active->suspended winning flip +
           ``CustomerSuspended``) — the suspension fold; postpaid only when
           ``enforcing`` (advisory computes+emits, never suspends).

        ``balance_micros`` rides CustomerSuspended (the balance at the
        crossing, best available to the detecting lane; postpaid passes 0).
        """
        from apps.platform.customers.models import Customer
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import StopFired, CustomerSuspended
        from apps.billing.gating.models import StopSignalState

        with transaction.atomic():
            owner = Customer.objects.select_for_update().get(id=owner_id)
            now = timezone.now()
            row, created = StopSignalState.objects.select_for_update().get_or_create(
                owner_id=owner.id, family=FAMILY_FLOOR_STOP,
                defaults={"tenant_id": tenant.id, "state": STATE_STOPPED,
                          "episode_seq": 1, "reason": reason, "transitioned_at": now})
            if not created:
                if row.state == STATE_STOPPED:
                    return None
                row.state = STATE_STOPPED
                row.episode_seq += 1
                row.reason = reason
                row.transitioned_at = now
                row.save(update_fields=["state", "episode_seq", "reason",
                                        "transitioned_at", "updated_at"])
            write_event(StopFired(tenant_id=str(tenant.id), owner_id=str(owner.id),
                                  reason=reason, scope="customer",
                                  episode_seq=row.episode_seq))
            postpaid = tenant.billing_mode == "postpaid"
            if (not postpaid or enforcing(tenant)) and owner.status == "active":
                owner.status = "suspended"
                owner.suspension_reason = "budget_exceeded" if postpaid else "min_balance_exceeded"
                owner.save(update_fields=["status", "suspension_reason", "updated_at"])
                write_event(CustomerSuspended(
                    tenant_id=str(tenant.id), customer_id=str(owner.id),
                    reason=owner.suspension_reason, balance_micros=int(balance_micros)))
            return row.episode_seq

    @staticmethod
    def drive_clear(owner_id, tenant, *, reason, balance_micros=0):
        """Drive the clearing transition for (owner, floor_stop).

        Returns the episode_seq of the stop it closed when THIS call won
        (state was stopped), else None — a clear that didn't win emits
        nothing (spec §E). The winner flips the row to ``cleared`` and emits
        ``stop.cleared`` carrying the closed episode and the balance at
        clearance. Un-suspension is deliberately NOT here: it stays with the
        call sites' ``_maybe_unsuspend``, gated on the durable balance (D15).
        """
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import StopCleared
        from apps.billing.gating.models import StopSignalState

        with transaction.atomic():
            row = (StopSignalState.objects.select_for_update()
                   .filter(owner_id=owner_id, family=FAMILY_FLOOR_STOP).first())
            if row is None or row.state != STATE_STOPPED:
                return None
            row.state = STATE_CLEARED
            row.reason = reason
            row.transitioned_at = timezone.now()
            row.save(update_fields=["state", "reason", "transitioned_at", "updated_at"])
            write_event(StopCleared(tenant_id=str(tenant.id), owner_id=str(owner_id),
                                    reason=reason, episode_seq=row.episode_seq,
                                    balance_micros=int(balance_micros)))
            return row.episode_seq

    @staticmethod
    def drive_soft_crossed(owner_id, tenant, *, balance_micros=0,
                           soft_min_balance_micros=0):
        """Drive the crossing transition on the soft_floor family (#40, §F).

        Returns the opened episode_seq when THIS call won (state was
        cleared/absent), else None. The winner atomically flips the ledger
        row and emits ``soft_floor.crossed``. Deliberately unlike the hard
        pair: NO suspension fold, NO Redis flag, NO ack change — the soft
        floor is a webhook + start-gate line only, and its only detector is
        the durable drawdown lane (no fast lane; signal latency is outbox
        latency). The owner Customer row is never locked or touched here, so
        the Customer -> StopSignalState lock order holds trivially.
        """
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import SoftFloorCrossed
        from apps.billing.gating.models import StopSignalState

        with transaction.atomic():
            now = timezone.now()
            row, created = StopSignalState.objects.select_for_update().get_or_create(
                owner_id=owner_id, family=FAMILY_SOFT_FLOOR,
                defaults={"tenant_id": tenant.id, "state": STATE_STOPPED,
                          "episode_seq": 1, "reason": SOFT_FLOOR_REACHED,
                          "transitioned_at": now})
            if not created:
                if row.state == STATE_STOPPED:
                    return None
                row.state = STATE_STOPPED
                row.episode_seq += 1
                row.reason = SOFT_FLOOR_REACHED
                row.transitioned_at = now
                row.save(update_fields=["state", "episode_seq", "reason",
                                        "transitioned_at", "updated_at"])
            write_event(SoftFloorCrossed(
                tenant_id=str(tenant.id), owner_id=str(owner_id),
                balance_micros=int(balance_micros),
                soft_min_balance_micros=int(soft_min_balance_micros),
                episode_seq=row.episode_seq))
            return row.episode_seq

    @staticmethod
    def drive_soft_cleared(owner_id, tenant, *, reason, balance_micros=0,
                           soft_min_balance_micros=0):
        """Drive the clearing transition on the soft_floor family (#40, §F).

        Returns the episode_seq it closed when THIS call won (state was
        stopped), else None — a clear that didn't win emits nothing, so the
        pair fires exactly once per episode. Reached from the credit hook
        (``balance_recovered``) and the hourly reconcile (``reconciled``).
        ``soft_min_balance_micros`` may be None: an owner whose soft floor
        was UNCONFIGURED mid-episode still clears (there is no line left to
        be past), and the event says so honestly.
        """
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import SoftFloorCleared
        from apps.billing.gating.models import StopSignalState

        with transaction.atomic():
            row = (StopSignalState.objects.select_for_update()
                   .filter(owner_id=owner_id, family=FAMILY_SOFT_FLOOR).first())
            if row is None or row.state != STATE_STOPPED:
                return None
            row.state = STATE_CLEARED
            row.reason = reason
            row.transitioned_at = timezone.now()
            row.save(update_fields=["state", "reason", "transitioned_at", "updated_at"])
            write_event(SoftFloorCleared(
                tenant_id=str(tenant.id), owner_id=str(owner_id), reason=reason,
                balance_micros=int(balance_micros),
                soft_min_balance_micros=(None if soft_min_balance_micros is None
                                         else int(soft_min_balance_micros)),
                episode_seq=row.episode_seq))
            return row.episode_seq
