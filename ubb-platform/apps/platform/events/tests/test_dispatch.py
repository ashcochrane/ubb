import pytest
from unittest.mock import MagicMock, patch
import uuid

from apps.platform.events.models import OutboxEvent, HandlerCheckpoint


@pytest.mark.django_db
class TestDispatchToHandlers:
    def test_dispatches_to_registered_handler(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id), "customer_id": "c1", "cost_micros": 5000},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_called_once()

    def test_skips_handler_when_tenant_lacks_product(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_not_called()

    def test_idempotent_handler_skips_on_replay(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        # Pre-create checkpoint — simulates already-processed
        HandlerCheckpoint.objects.create(
            outbox_event=event,
            handler_name="test.handler",
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)
        handler.assert_not_called()

    def test_handler_without_product_gate_always_runs(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=[])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler)

        dispatch_to_handlers(event, registry=registry)
        handler.assert_called_once()

    def test_creates_checkpoint_after_handler_success(self):
        from apps.platform.events.dispatch import dispatch_to_handlers
        from apps.platform.events.registry import HandlerRegistry
        from apps.platform.tenants.models import Tenant

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={"tenant_id": str(tenant.id)},
            tenant_id=tenant.id,
        )

        handler = MagicMock()
        registry = HandlerRegistry()
        registry.register("usage.recorded", "test.handler", handler, requires_product="billing")

        dispatch_to_handlers(event, registry=registry)

        assert HandlerCheckpoint.objects.filter(
            outbox_event=event, handler_name="test.handler"
        ).exists()
