"""Announcement bookkeeping — the delivery spec's §B vocabulary (#43).

Every signal-bearing row (a ``StopSignalState`` ledger row, a killed
``Task``) stamps ``announce_outbox_id`` with the OutboxEvent id of its LAST
announcement, inside the same atomic unit as the transition that emitted it.
This module is the ONE definition of what that stamp means, shared by every
consumer (the hourly patrol's re-mint pass, ops surfaces, tests):

- ANNOUNCED   — the stamped event reached terminal success: ``processed``,
                or ``skipped`` (a tenant with no webhook config has chosen no
                push channel — vacuous success, never re-minted). A stamp
                pointing at a row the outbox cleanup has since deleted is
                ALSO announced: cleanup only ever deletes terminal-success
                rows (failed rows are never auto-deleted).
- IN_FLIGHT   — the stamped row is still ``pending``/``processing``; the
                patrol leaves it alone (at most one live announcement per
                signal row).
- UNANNOUNCED — no stamp, or the stamped row terminally ``failed``
                (dead-lettered). The patrol re-mints a fresh current-state
                event (``re_announcement: true``) and re-stamps.

The null-stamp case is only meaningful on a row that HAS signal-bearing
state (a ledger row in a non-initial state, a task whose winning kill flip
emitted). Callers own that precondition — a row with nothing to announce has
no announcement to classify.
"""
from apps.platform.events.models import OutboxEvent

ANNOUNCED = "announced"
IN_FLIGHT = "in_flight"
UNANNOUNCED = "unannounced"

_TERMINAL_SUCCESS = ("processed", "skipped")


def announcement_status(announce_outbox_id):
    """Classify a row's ``announce_outbox_id`` stamp per delivery spec §B.

    Returns ANNOUNCED / IN_FLIGHT / UNANNOUNCED.
    """
    if announce_outbox_id is None:
        return UNANNOUNCED
    status = (OutboxEvent.objects.filter(id=announce_outbox_id)
              .values_list("status", flat=True).first())
    if status is None:
        # The stamped row was deleted by cleanup_outbox, which only touches
        # terminal-success rows — announced, long ago.
        return ANNOUNCED
    if status in _TERMINAL_SUCCESS:
        return ANNOUNCED
    if status == "failed":
        return UNANNOUNCED
    return IN_FLIGHT  # pending / processing
