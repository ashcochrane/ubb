"""The prepaid reservation's lifecycle — Wallet policy's write at a start,
its release on every terminal transition, and the backstop that releases what
a failed listener left behind (#461, slice 6 §5, #139 §4.1).

THREE ENTRY POINTS AND ONE READ, and where each is called from:

* ``reserve`` — the one writer of a `WalletReservation` row. Called by the
  money verdict's reservation half (`RiskService.reserve_agreed_price`), which
  is the service the composition layer already calls for the money-shaped
  verdict at a start: the reservation is a wallet WRITE at start and it lands
  there, not in billing's read contract, whose write-shaped holds #141 §6.4
  said must not be widened. Must be called under ``lock_for_billing`` on the
  owner, which is what serializes concurrent starts against one wallet.
* ``release_on_terminal_transition`` — the listener billing registers on the
  kernel's terminal-transition registry (`apps/platform/work/hooks.py`) in
  `WalletsConfig.ready()`. The kernel calls it, synchronously and inside the
  transition's own transaction, for every terminal path — the three closes,
  the kills, both expiries and each cascade — and it releases the unit's open
  reservation if it holds one. It is a notification and never a veto: it
  raises for nothing it can foresee, and the registry catches and logs what
  it cannot, under a savepoint of its own.
* ``release_reservations_left_open_on_terminal_work`` — the backstop sweep,
  an hourly beat (`wallets/tasks.py`): idempotent, releasing and logging. A
  row it releases is a row the listener did not — the registry logged the
  failure at the time — so each release here is logged as a warning naming
  the unit, and a quiet sweep is the ordinary state.
* ``open_reservations_micros`` — the "open reservations" term of the
  affordability read, for the money verdict, the customer's balance read and
  the live-balance repair's audit row.

THE DELIVERED CLOSE releases here and the Charge's drawdown lands shortly after
through the outbox; the brief window in which neither encumbers the balance is
the window every metered event already has between recording and drawdown,
and the ledger-not-wall doctrine tolerates it.
"""
import logging

from django.db.models import Sum
from django.utils import timezone

from apps.billing.wallets.models import (
    RELEASED_BY_BACKSTOP_SWEEP, RELEASED_BY_TERMINAL_TRANSITION,
    WalletReservation)
from apps.platform.work.models import TERMINAL_TASK_STATUSES

logger = logging.getLogger("ubb.billing")


def open_reservations_micros(owner_id):
    """Everything reserved against ``owner_id``'s wallet and not yet released,
    as one integer; zero for an owner nothing has ever reserved against."""
    total = WalletReservation.objects.filter(
        owner_id=owner_id, released_at__isnull=True,
    ).aggregate(total=Sum("amount_micros"))["total"]
    return int(total or 0)


def reserve(*, task, owner_id, tenant, amount_micros):
    """Write the reservation for ``task``: ``amount_micros`` against the
    wallet of the billing owner ``owner_id``. The caller holds that owner's
    billing lock and has already found the amount affordable; this only
    writes what it was told."""
    row = WalletReservation.objects.create(
        tenant=tenant, owner_id=owner_id, task=task, amount_micros=amount_micros)
    logger.info("wallet.reservation_taken", extra={"data": {
        "task_id": str(task.id), "owner_id": str(owner_id),
        "amount_micros": amount_micros}})
    return row


def _release(rows, *, released_by):
    """Release every open row in ``rows`` in one UPDATE; returns how many.
    Idempotent by construction: a released row no longer matches."""
    return rows.filter(released_at__isnull=True).update(
        released_at=timezone.now(), released_by=released_by)


def release_on_terminal_transition(task, transition):
    """The listener: release the reservation the unit holds, if any.

    One UPDATE keyed on the unit — a no-op for a unit that never reserved
    (event-priced work, contained work, a postpaid tenant's priced unit,
    anything a reaper registered) and for a row already released. It asks the
    reservation table and not the unit's price column on purpose: the row is
    the record of what was reserved, and a release keyed on what the unit
    says about itself would leave a row behind the day the two disagree.
    """
    released = _release(WalletReservation.objects.filter(task_id=task.id),
                        released_by=RELEASED_BY_TERMINAL_TRANSITION)
    if released:
        logger.info("wallet.reservation_released", extra={"data": {
            "task_id": str(task.id), "status": transition.status,
            "cascaded": transition.cascaded}})


def release_reservations_left_open_on_terminal_work():
    """The backstop sweep: release every open reservation whose unit of work
    is already terminal, and say so per unit. Returns how many it released;
    a second run over the same rows releases nothing."""
    candidates = list(WalletReservation.objects.filter(
        released_at__isnull=True, task__status__in=TERMINAL_TASK_STATUSES,
    ).values_list("id", flat=True))
    if not candidates:
        return 0
    released = _release(WalletReservation.objects.filter(id__in=candidates),
                        released_by=RELEASED_BY_BACKSTOP_SWEEP)
    # Logged off what the UPDATE stamped, not off the candidate list: a row
    # the listener released between the read and the UPDATE is the
    # listener's, and the warning says only what this sweep did.
    for row in WalletReservation.objects.filter(
            id__in=candidates, released_by=RELEASED_BY_BACKSTOP_SWEEP,
    ).values("task_id", "owner_id", "tenant_id", "amount_micros", "task__status"):
        logger.warning("wallet.reservation_released_by_backstop", extra={"data": {
            "task_id": str(row["task_id"]), "owner_id": str(row["owner_id"]),
            "tenant_id": str(row["tenant_id"]),
            "amount_micros": row["amount_micros"],
            "status": row["task__status"]}})
    return released
