import logging

logger = logging.getLogger("ubb.events")


class EventBus:
    def __init__(self):
        self._handlers = {}

    def subscribe(self, event_name, handler, requires_product=None):
        self._handlers.setdefault(event_name, []).append({
            "handler": handler,
            "requires_product": requires_product,
        })

    def _tenant_has_product(self, tenant_id, product):
        from django.core.cache import cache
        cache_key = f"tenant_products:{tenant_id}"
        products = cache.get(cache_key)
        if products is None:
            from apps.platform.tenants.models import Tenant
            tenant = Tenant.objects.get(id=tenant_id)
            products = tenant.products
            cache.set(cache_key, products, timeout=300)
        return product in products

    def emit(self, event_name, data):
        logger.info("event.emitted", extra={"data": {"event": event_name, **data}})
        for entry in self._handlers.get(event_name, []):
            try:
                if entry["requires_product"] and data.get("tenant_id"):
                    if not self._tenant_has_product(data["tenant_id"], entry["requires_product"]):
                        continue
                entry["handler"](data)
            except Exception:
                handler_name = getattr(entry["handler"], "__name__", repr(entry["handler"]))
                logger.exception(
                    "event.handler_failed",
                    extra={"data": {"event": event_name, "handler": handler_name}},
                )


event_bus = EventBus()
