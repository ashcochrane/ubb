import pytest
from unittest.mock import patch, MagicMock
from django.utils import timezone

from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestProcessSingleEvent:
    def test_processes_pending_event(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        with patch("apps.platform.events.dispatch.dispatch_to_handlers") as mock_dispatch:
            process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "processed"
        assert event.processed_at is not None
        mock_dispatch.assert_called_once()

    def test_skips_already_processed_event(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="processed",
        )

        with patch("apps.platform.events.dispatch.dispatch_to_handlers") as mock_dispatch:
            process_single_event(str(event.id))

        mock_dispatch.assert_not_called()

    def test_retries_on_handler_failure(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        with patch("apps.platform.events.dispatch.dispatch_to_handlers", side_effect=Exception("boom")):
            process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "pending"
        assert event.retry_count == 1
        assert "boom" in event.last_error
        assert event.next_retry_at is not None

    def test_marks_failed_after_max_retries(self):
        from apps.platform.events.tasks import process_single_event

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            retry_count=4,  # One more failure = 5 = max_retries
        )

        with patch("apps.platform.events.dispatch.dispatch_to_handlers", side_effect=Exception("boom")):
            with patch("apps.platform.events.tasks.alert_dead_letter") as mock_alert:
                process_single_event(str(event.id))

        event.refresh_from_db()
        assert event.status == "failed"
        assert event.retry_count == 5
        mock_alert.assert_called_once()


@pytest.mark.django_db
class TestSweepOutbox:
    def test_sweep_picks_up_stuck_pending_events(self):
        from apps.platform.events.tasks import sweep_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        # Event with past next_retry_at
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="pending",
            next_retry_at=timezone.now() - timezone.timedelta(minutes=1),
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            sweep_outbox()

        mock_task.delay.assert_called_once_with(str(event.id))

    def test_sweep_picks_up_new_pending_events_without_retry_at(self):
        from apps.platform.events.tasks import sweep_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="pending",
            next_retry_at=None,
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            sweep_outbox()

        mock_task.delay.assert_called()


@pytest.mark.django_db
class TestCleanupOutbox:
    def test_cleanup_deletes_old_processed_events(self):
        from apps.platform.events.tasks import cleanup_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        # Old processed event
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="processed",
        )
        # Backdate created_at
        OutboxEvent.objects.filter(id=event.id).update(
            created_at=timezone.now() - timezone.timedelta(days=31)
        )

        cleanup_outbox()

        assert OutboxEvent.objects.filter(id=event.id).count() == 0

    def test_cleanup_preserves_failed_events(self):
        from apps.platform.events.tasks import cleanup_outbox

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
            status="failed",
        )
        OutboxEvent.objects.filter(id=event.id).update(
            created_at=timezone.now() - timezone.timedelta(days=365)
        )

        cleanup_outbox()

        assert OutboxEvent.objects.filter(id=event.id).count() == 1
