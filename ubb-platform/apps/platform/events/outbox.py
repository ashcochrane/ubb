"""
Outbox event writing.

All event writes happen inside the same @transaction.atomic as the domain change.
If the transaction rolls back, the event disappears.
If it commits, the event is guaranteed to exist and a Celery task is scheduled.
"""
from dataclasses import asdict

from django.db import transaction

from apps.platform.events.models import OutboxEvent


def write_event(schema_instance):
    """Write an event to the outbox. Must be called inside @transaction.atomic."""
    # Lazy import to avoid circular dependency at module load time
    from apps.platform.events.tasks import process_single_event

    try:
        from core.logging import correlation_id_var
        correlation_id = correlation_id_var.get("")
    except Exception:
        correlation_id = ""

    outbox = OutboxEvent.objects.create(
        event_type=schema_instance.EVENT_TYPE,
        payload=asdict(schema_instance),
        tenant_id=schema_instance.tenant_id,
        correlation_id=correlation_id,
    )

    transaction.on_commit(
        lambda: process_single_event.delay(str(outbox.id))
    )

    return outbox
