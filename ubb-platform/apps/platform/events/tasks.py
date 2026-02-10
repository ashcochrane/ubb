"""
Celery tasks for outbox event processing.

Two mechanisms (belt and suspenders):
1. Immediate: transaction.on_commit() dispatches process_single_event for each event.
2. Sweep: Celery beat picks up pending/stuck events every minute.
"""
import logging
from datetime import timedelta

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from apps.platform.events.models import OutboxEvent

logger = logging.getLogger("ubb.events")

BACKOFF_SCHEDULE = [30, 120, 600, 1800, 7200]  # seconds: 30s, 2m, 10m, 30m, 2h


def calculate_backoff(retry_count):
    """Calculate next_retry_at based on retry count."""
    idx = min(retry_count - 1, len(BACKOFF_SCHEDULE) - 1)
    return timezone.now() + timedelta(seconds=BACKOFF_SCHEDULE[idx])


def alert_dead_letter(event):
    """Alert on permanently failed event. Extend with Slack/PagerDuty as needed."""
    logger.critical(
        "outbox.dead_letter",
        extra={
            "data": {
                "event_id": str(event.id),
                "event_type": event.event_type,
                "tenant_id": str(event.tenant_id),
                "retry_count": event.retry_count,
                "last_error": event.last_error[:500],
                "correlation_id": event.correlation_id,
            }
        },
    )


@shared_task(queue="ubb_events", bind=True, max_retries=0)
def process_single_event(self, event_id):
    """Process a single outbox event -- dispatches to all registered handlers."""
    from apps.platform.events.dispatch import dispatch_to_handlers

    try:
        event = OutboxEvent.objects.select_for_update(skip_locked=True).get(id=event_id)
    except OutboxEvent.DoesNotExist:
        return

    if event.status not in ("pending",):
        return

    event.status = "processing"
    event.save(update_fields=["status", "updated_at"])

    try:
        dispatch_to_handlers(event)
        event.status = "processed"
        event.processed_at = timezone.now()
    except Exception as e:
        event.retry_count += 1
        event.last_error = str(e)[:2000]
        if event.retry_count >= event.max_retries:
            event.status = "failed"
            alert_dead_letter(event)
        else:
            event.status = "pending"
            event.next_retry_at = calculate_backoff(event.retry_count)
        logger.exception(
            "outbox.handler_failed",
            extra={"data": {"event_id": event_id, "retry_count": event.retry_count}},
        )

    event.save()


@shared_task(queue="ubb_events")
def sweep_outbox():
    """Pick up pending events that need processing.

    Catches:
    - Events whose on_commit Celery dispatch was lost (worker restart, etc.)
    - Events due for retry (next_retry_at in the past)
    - Stuck 'processing' events older than 5 minutes (worker crashed)
    """
    now = timezone.now()

    # Pending events ready for retry or never dispatched
    pending_events = list(
        OutboxEvent.objects.filter(
            status="pending",
        )
        .filter(Q(next_retry_at__isnull=True) | Q(next_retry_at__lte=now))
        .values_list("id", flat=True)[:100]
    )

    for event_id in pending_events:
        process_single_event.delay(str(event_id))

    # Reclaim stuck processing events
    stuck_cutoff = now - timedelta(minutes=5)
    stuck_events = list(
        OutboxEvent.objects.filter(
            status="processing",
            updated_at__lt=stuck_cutoff,
        ).values_list("id", flat=True)[:50]
    )

    for event_id in stuck_events:
        OutboxEvent.objects.filter(id=event_id, status="processing").update(
            status="pending",
            next_retry_at=now,
        )
        process_single_event.delay(str(event_id))

    if pending_events or stuck_events:
        logger.info(
            "outbox.sweep",
            extra={
                "data": {
                    "pending_dispatched": len(pending_events),
                    "stuck_reclaimed": len(stuck_events),
                }
            },
        )


@shared_task(queue="ubb_events")
def cleanup_outbox():
    """Delete old processed/skipped events. Failed events are never auto-deleted."""
    now = timezone.now()

    # Processed events older than 30 days
    cutoff_processed = now - timedelta(days=30)
    deleted_processed, _ = OutboxEvent.objects.filter(
        status="processed",
        created_at__lt=cutoff_processed,
    ).delete()

    # Skipped events older than 90 days
    cutoff_skipped = now - timedelta(days=90)
    deleted_skipped, _ = OutboxEvent.objects.filter(
        status="skipped",
        created_at__lt=cutoff_skipped,
    ).delete()

    if deleted_processed or deleted_skipped:
        logger.info(
            "outbox.cleanup",
            extra={
                "data": {
                    "deleted_processed": deleted_processed,
                    "deleted_skipped": deleted_skipped,
                }
            },
        )
