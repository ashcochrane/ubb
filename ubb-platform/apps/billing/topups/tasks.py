import logging

from celery import shared_task
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_topups")
def expire_stale_topup_attempts():
    """Expire stale pending TopUpAttempts that are stuck."""
    from apps.billing.topups.models import TopUpAttempt

    now = timezone.now()
    auto_cutoff = now - timedelta(minutes=30)
    manual_cutoff = now - timedelta(hours=24)

    # Expire stale auto-topup attempts
    auto_expired = TopUpAttempt.objects.filter(
        status="pending",
        trigger="auto_topup",
        created_at__lt=auto_cutoff,
    ).update(status="expired")
    if auto_expired:
        logger.info(
            "Expired stale auto-topup attempts",
            extra={"data": {"expired_count": auto_expired}},
        )

    # Expire stale manual/checkout attempts
    manual_expired = TopUpAttempt.objects.filter(
        status="pending",
        trigger="manual",
        created_at__lt=manual_cutoff,
    ).update(status="expired")
    if manual_expired:
        logger.info(
            "Expired stale manual top-up attempts",
            extra={"data": {"expired_count": manual_expired}},
        )
