import logging

from celery import shared_task
from datetime import timedelta
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_topups")
def expire_stale_topup_attempts():
    """Expire stale pending TopUpAttempts that are stuck."""
    from apps.billing.topups.models import TRIGGER_AUTO_TOP_UP, TopUpAttempt

    now = timezone.now()
    auto_cutoff = now - timedelta(minutes=30)
    manual_cutoff = now - timedelta(hours=24)

    # Expire stale auto top-up attempts
    auto_expired = TopUpAttempt.objects.filter(
        status="pending",
        trigger=TRIGGER_AUTO_TOP_UP,
        created_at__lt=auto_cutoff,
    ).update(status="expired")
    if auto_expired:
        logger.info(
            "Expired stale auto top-up attempts",
            extra={"data": {"expired_count": auto_expired}},
        )

    # Expire stale Checkout attempts — the tenant route's (`manual`) and the
    # widget's (`widget`, R10 Stage C1b F-11/O-6: a widget attempt is the
    # same Checkout Session, which Stripe itself expires after 24 hours, so
    # it gets the same window; it never expired before). An expired Checkout
    # that completes late is still credited (handle_checkout_completed's
    # expired-manual recovery).
    for trigger in ("manual", "widget"):
        expired = TopUpAttempt.objects.filter(
            status="pending",
            trigger=trigger,
            created_at__lt=manual_cutoff,
        ).update(status="expired")
        if expired:
            logger.info(
                "Expired stale %s top-up attempts", trigger,
                extra={"data": {"trigger": trigger, "expired_count": expired}},
            )
