import logging

from celery import shared_task
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_webhooks")
def cleanup_webhook_events():
    """Batch-delete old webhook events to avoid long-running deletes and WAL bloat."""
    from apps.billing.stripe.models import StripeWebhookEvent

    now = timezone.now()
    succeeded_cutoff = now - timedelta(days=90)
    failed_cutoff = now - timedelta(days=180)

    # Delete succeeded/skipped events older than 90 days in batches
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status__in=["succeeded", "skipped"],
            created_at__lt=succeeded_cutoff,
        )
    )

    # Delete failed events older than 180 days in batches
    _batched_delete(
        StripeWebhookEvent.objects.filter(
            status="failed",
            created_at__lt=failed_cutoff,
        )
    )


def _batched_delete(queryset, batch_size=1000):
    """Delete in batches by PK range to avoid long locks."""
    while True:
        batch_ids = list(queryset.values_list("id", flat=True)[:batch_size])
        if not batch_ids:
            break
        deleted, _ = queryset.model.objects.filter(id__in=batch_ids).delete()
        logger.info(
            "Cleaned up webhook events",
            extra={"data": {"deleted_count": deleted}},
        )
