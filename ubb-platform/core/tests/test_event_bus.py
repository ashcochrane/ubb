import pytest
from unittest.mock import MagicMock

from core.event_bus import EventBus


class TestEventBusSubscribeAndEmit:
    def test_subscribe_and_emit(self):
        """Subscribe handler, emit event, handler called with data."""
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("order.created", handler)
        bus.emit("order.created", {"order_id": "123"})
        handler.assert_called_once_with({"order_id": "123"})

    def test_emit_unknown_event_does_nothing(self):
        """No error on emit with no subscribers."""
        bus = EventBus()
        # Should not raise
        bus.emit("nonexistent.event", {"foo": "bar"})

    def test_multiple_handlers(self):
        """Multiple handlers all called."""
        bus = EventBus()
        handler1 = MagicMock()
        handler2 = MagicMock()
        bus.subscribe("order.created", handler1)
        bus.subscribe("order.created", handler2)
        bus.emit("order.created", {"order_id": "456"})
        handler1.assert_called_once_with({"order_id": "456"})
        handler2.assert_called_once_with({"order_id": "456"})

    def test_handler_error_is_swallowed(self):
        """Bad handler doesn't prevent good handler from running."""
        bus = EventBus()
        bad_handler = MagicMock(side_effect=Exception("boom"))
        good_handler = MagicMock()
        bus.subscribe("order.created", bad_handler)
        bus.subscribe("order.created", good_handler)
        bus.emit("order.created", {"order_id": "789"})
        bad_handler.assert_called_once()
        good_handler.assert_called_once_with({"order_id": "789"})


@pytest.mark.django_db
class TestEventBusProductAccess:
    def test_product_access_skips_handler_when_tenant_lacks_product(self):
        """Handler with requires_product='billing' skipped when tenant has no products."""
        from apps.platform.tenants.models import Tenant
        tenant = Tenant.objects.create(name="No Products Tenant", products=[])
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("usage.recorded", handler, requires_product="billing")
        bus.emit("usage.recorded", {"tenant_id": str(tenant.id), "amount": 100})
        handler.assert_not_called()

    def test_product_access_calls_handler_when_tenant_has_product(self):
        """Handler called when tenant has the required product."""
        from apps.platform.tenants.models import Tenant
        tenant = Tenant.objects.create(name="Billing Tenant", products=["billing"])
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("usage.recorded", handler, requires_product="billing")
        bus.emit("usage.recorded", {"tenant_id": str(tenant.id), "amount": 100})
        handler.assert_called_once_with({"tenant_id": str(tenant.id), "amount": 100})

    def test_handler_without_product_requirement_always_runs(self):
        """Handler without requires_product always runs."""
        from apps.platform.tenants.models import Tenant
        tenant = Tenant.objects.create(name="Any Tenant", products=[])
        bus = EventBus()
        handler = MagicMock()
        bus.subscribe("usage.recorded", handler)  # No requires_product
        bus.emit("usage.recorded", {"tenant_id": str(tenant.id), "amount": 100})
        handler.assert_called_once_with({"tenant_id": str(tenant.id), "amount": 100})
