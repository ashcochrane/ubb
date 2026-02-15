"""
Dispatch outbox events to registered handlers with idempotency and product gating.
"""
import logging

from django.core.cache import cache
from django.db import IntegrityError

from apps.platform.events.models import HandlerCheckpoint
from apps.platform.events.registry import handler_registry

logger = logging.getLogger("ubb.events")


def _tenant_has_product(tenant_id, product):
    """Check tenant products with 5-minute cache."""
    cache_key = f"tenant_products:{tenant_id}"
    products = cache.get(cache_key)
    if products is None:
        from apps.platform.tenants.models import Tenant

        try:
            tenant = Tenant.objects.get(id=tenant_id)
        except Tenant.DoesNotExist:
            logger.warning(
                "tenant.not_found_in_dispatch",
                extra={"data": {"tenant_id": str(tenant_id)}},
            )
            products = []
            cache.set(cache_key, products, timeout=300)
            return False
        products = tenant.products
        cache.set(cache_key, products, timeout=300)
    return product in products


def dispatch_to_handlers(event, registry=None):
    """Dispatch an outbox event to all registered handlers.

    - Product gating: skips handlers whose required product is missing.
    - Idempotency: skips handlers that already have a checkpoint for this event.
    - Creates checkpoint after successful handler execution.
    """
    if registry is None:
        registry = handler_registry

    handlers = registry.get_handlers(event.event_type)

    for entry in handlers:
        handler_name = entry["name"]
        handler_fn = entry["handler"]
        required_product = entry["requires_product"]

        # Product gating
        if required_product:
            if not _tenant_has_product(event.tenant_id, required_product):
                continue

        # Idempotency check
        if HandlerCheckpoint.objects.filter(
            outbox_event=event, handler_name=handler_name
        ).exists():
            logger.info(
                "handler.skipped_checkpoint",
                extra={"data": {"handler": handler_name, "event_id": str(event.id)}},
            )
            continue

        # Execute handler
        handler_fn(str(event.id), event.payload)

        # Record checkpoint
        try:
            HandlerCheckpoint.objects.create(
                outbox_event=event,
                handler_name=handler_name,
            )
        except IntegrityError:
            logger.info(
                "handler.checkpoint_race",
                extra={"data": {"handler": handler_name, "event_id": str(event.id)}},
            )
