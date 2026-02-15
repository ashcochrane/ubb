import logging
from datetime import timedelta

from celery import shared_task
from django.utils import timezone

from apps.platform.events.webhook_models import WebhookDeliveryAttempt

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_webhooks")
def cleanup_webhook_delivery_attempts():
    """Delete old webhook delivery attempts.

    - Successful attempts: delete after 30 days
    - Failed attempts: delete after 90 days
    """
    now = timezone.now()

    success_cutoff = now - timedelta(days=30)
    success_count, _ = WebhookDeliveryAttempt.objects.filter(
        success=True, created_at__lt=success_cutoff
    ).delete()

    fail_cutoff = now - timedelta(days=90)
    fail_count, _ = WebhookDeliveryAttempt.objects.filter(
        success=False, created_at__lt=fail_cutoff
    ).delete()

    if success_count or fail_count:
        logger.info(
            "webhook_delivery_attempts.cleanup",
            extra={"data": {"success_deleted": success_count, "failed_deleted": fail_count}},
        )
