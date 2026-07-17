import uuid

import pytest
from unittest.mock import patch, MagicMock

from apps.platform.events.schemas import UsageRecorded

TENANT_UUID = str(uuid.uuid4())


@pytest.mark.django_db
class TestWriteEvent:
    def test_write_event_creates_outbox_row(self):
        from apps.platform.events.outbox import write_event
        from apps.platform.events.models import OutboxEvent

        schema = UsageRecorded(
            tenant_id=TENANT_UUID,
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            write_event(schema)

        assert OutboxEvent.objects.count() == 1
        event = OutboxEvent.objects.first()
        assert event.event_type == "usage.recorded"
        assert event.payload["customer_id"] == "c1"
        assert event.payload["cost_micros"] == 5000
        assert event.status == "pending"

    @pytest.mark.django_db(transaction=True)
    def test_write_event_schedules_celery_task_on_commit(self):
        from apps.platform.events.outbox import write_event

        schema = UsageRecorded(
            tenant_id=TENANT_UUID,
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            write_event(schema)

        mock_task.delay.assert_called_once()

    @pytest.mark.django_db(transaction=True)
    def test_broker_down_dispatch_is_swallowed_and_row_stays_pending(self):
        """Delivery spec §A (#43): the post-commit dispatch is a doorbell,
        not the queue. A dead broker at dispatch time must never raise out
        of the on_commit chain — the durable pending row is picked up by the
        minutely sweep."""
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.outbox import write_event

        schema = UsageRecorded(
            tenant_id=TENANT_UUID,
            customer_id="c1",
            event_id="e1",
            cost_micros=5000,
        )

        with patch("apps.platform.events.tasks.process_single_event") as mock_task:
            mock_task.delay.side_effect = ConnectionError("broker down")
            write_event(schema)  # must not raise

        event = OutboxEvent.objects.get()
        assert event.status == "pending"


@pytest.mark.django_db
class TestRegistry:
    def test_register_and_get_handlers(self):
        from apps.platform.events.registry import HandlerRegistry

        registry = HandlerRegistry()

        def my_handler(event_id, payload):
            pass

        registry.register(
            "usage.recorded", "test.my_handler", my_handler, requires_product="billing"
        )

        handlers = registry.get_handlers("usage.recorded")
        assert len(handlers) == 1
        assert handlers[0]["name"] == "test.my_handler"
        assert handlers[0]["handler"] is my_handler
        assert handlers[0]["requires_product"] == "billing"

    def test_get_handlers_returns_empty_for_unknown_event(self):
        from apps.platform.events.registry import HandlerRegistry

        registry = HandlerRegistry()
        assert registry.get_handlers("unknown.event") == []
