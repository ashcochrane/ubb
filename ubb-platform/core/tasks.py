import logging
from datetime import datetime

from celery import shared_task
from django.core.cache import cache

from apps.platform.tenants.models import TenantApiKey

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_billing")
def flush_api_key_last_used():
    """Flush buffered last_used_at timestamps from Redis to DB.

    Runs every 5 minutes. Scans all active API keys and updates
    last_used_at if a Redis entry exists.
    """
    keys = TenantApiKey.objects.filter(is_active=True).values_list("pk", flat=True)
    updated = 0
    for pk in keys:
        cache_key = f"apikey_used:{pk}"
        ts = cache.get(cache_key)
        if ts:
            TenantApiKey.objects.filter(pk=pk).update(
                last_used_at=datetime.fromisoformat(ts)
            )
            cache.delete(cache_key)
            updated += 1
    if updated:
        logger.info("api_key.last_used_flushed", extra={"data": {"count": updated}})
