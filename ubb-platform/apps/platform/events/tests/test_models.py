import pytest
from django.db import IntegrityError, transaction


@pytest.mark.django_db
class TestOutboxEvent:
    def test_create_outbox_event(self):
        from apps.platform.events.models import OutboxEvent
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"customer_id": "cust_123", "cost_micros": 5000},
            tenant_id=uuid.uuid4(),
        )
        assert event.status == "pending"
        assert event.retry_count == 0
        assert event.max_retries == 5
        assert event.next_retry_at is None
        assert event.processed_at is None
        assert event.last_error == ""
        assert event.correlation_id == ""

    def test_outbox_event_str(self):
        from apps.platform.events.models import OutboxEvent
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        assert "usage.recorded" in str(event)


@pytest.mark.django_db
class TestHandlerCheckpoint:
    def test_create_checkpoint(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        cp = HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        assert cp.handler_name == "billing.wallet_deduction"

    def test_checkpoint_unique_per_event_handler(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                HandlerCheckpoint.objects.create(
                    outbox_event=event,
                    handler_name="billing.wallet_deduction",
                )

    def test_checkpoint_cascade_deletes_with_event(self):
        from apps.platform.events.models import OutboxEvent, HandlerCheckpoint
        import uuid

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={},
            tenant_id=uuid.uuid4(),
        )
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="billing.wallet_deduction",
        )
        event.delete()
        assert HandlerCheckpoint.objects.count() == 0
