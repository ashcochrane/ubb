import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.utils import OperationalError, InterfaceError
from django.utils import timezone

logger = logging.getLogger(__name__)


@shared_task(
    queue="ubb_billing",
    autoretry_for=(OperationalError, InterfaceError),
    max_retries=3,
    retry_backoff=True,
)
def close_abandoned_runs():
    """Close runs that have been active for longer than 1 hour.

    Safety net for runs that were never explicitly closed by the SDK
    (e.g., client crash, network failure, forgotten close call).
    """
    from apps.platform.runs.models import Run

    cutoff = timezone.now() - timedelta(hours=1)
    stale_runs = Run.objects.filter(status="active", created_at__lt=cutoff)
    closed_count = 0

    for run in stale_runs.iterator():
        with transaction.atomic():
            locked = Run.objects.select_for_update().get(id=run.id)
            if locked.status != "active":
                continue
            locked.status = "completed"
            locked.completed_at = timezone.now()
            locked.metadata["auto_closed"] = True
            locked.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
            closed_count += 1

    if closed_count:
        logger.info("Auto-closed %d abandoned runs", closed_count)
    return closed_count
