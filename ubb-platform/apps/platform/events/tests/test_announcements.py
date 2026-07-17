"""#43 §B — the one shared definition of announced / in-flight / unannounced.

The patrol (#44) keys its re-mint pass on exactly these verdicts, so the
mapping from OutboxEvent status to announcement status is pinned here:
terminal success (processed, or skipped = vacuous success for a tenant with
no webhook config) is announced and never re-minted; a dead-lettered stamp is
unannounced; pending/processing is in flight and left alone; a stamp whose
row the outbox cleanup deleted is announced (cleanup only ever deletes
terminal-success rows).
"""
import uuid

import pytest

from apps.platform.events.announcements import (
    ANNOUNCED,
    IN_FLIGHT,
    UNANNOUNCED,
    announcement_status,
)
from apps.platform.events.models import OutboxEvent


def _row(status):
    return OutboxEvent.objects.create(
        event_type="stop.fired", payload={}, tenant_id=uuid.uuid4(),
        status=status)


@pytest.mark.django_db
class TestAnnouncementStatus:
    def test_null_stamp_is_unannounced(self):
        assert announcement_status(None) == UNANNOUNCED

    def test_processed_is_announced(self):
        assert announcement_status(_row("processed").id) == ANNOUNCED

    def test_skipped_is_vacuous_success_never_reminted(self):
        assert announcement_status(_row("skipped").id) == ANNOUNCED

    def test_dead_lettered_is_unannounced(self):
        assert announcement_status(_row("failed").id) == UNANNOUNCED

    def test_pending_and_processing_are_in_flight(self):
        assert announcement_status(_row("pending").id) == IN_FLIGHT
        assert announcement_status(_row("processing").id) == IN_FLIGHT

    def test_stamp_outliving_outbox_cleanup_stays_announced(self):
        # cleanup_outbox deletes processed/skipped rows after 30/90 days;
        # failed rows are never auto-deleted — so a dangling stamp can only
        # mean the announcement terminally succeeded long ago.
        assert announcement_status(uuid.uuid4()) == ANNOUNCED
