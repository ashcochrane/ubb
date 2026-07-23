"""
Outbox event writing.

All event writes happen inside the same @transaction.atomic as the domain change.
If the transaction rolls back, the event disappears.
If it commits, the event is guaranteed to exist and a Celery task is scheduled.

The post-commit dispatch is a doorbell, not the queue (delivery spec §A, #43):
the durable row IS the queue, and the minutely ``sweep_outbox`` re-dispatches
any pending row whose doorbell was lost. A dead Celery broker at dispatch time
is therefore swallowed and logged — it costs at most a minute of delivery
latency and must never surface an error for an event that durably landed
(the 200-always contract).
"""
import logging
from dataclasses import asdict

from django.db import connection, transaction

from apps.platform.events.models import OutboxEvent

logger = logging.getLogger("ubb.events")


def _dispatch(outbox_id):
    """Post-commit doorbell — broker errors are swallowed + logged.

    Runs inside Django's on_commit callback chain, so a raise here would both
    5xx a request whose transaction already committed AND abort every later
    callback in the chain. The sweep is the guaranteed path; this is latency.
    """
    from apps.platform.events.tasks import process_single_event

    try:
        process_single_event.delay(outbox_id)
    except Exception:
        logger.warning(
            "outbox.dispatch_failed",
            extra={"data": {"event_id": outbox_id}},
        )


def write_event(schema_instance):
    """Write an event to the outbox. Must be called inside @transaction.atomic."""
    from core.logging import get_correlation_id

    # Not just documentation: an event written outside the caller's atomic
    # block would survive a rollback of the domain change it announces.
    assert connection.in_atomic_block, (
        "write_event must be called inside transaction.atomic"
    )

    outbox = OutboxEvent.objects.create(
        event_type=schema_instance.EVENT_TYPE,
        payload=asdict(schema_instance),
        tenant_id=schema_instance.tenant_id,
        correlation_id=get_correlation_id(),
    )

    transaction.on_commit(lambda: _dispatch(str(outbox.id)))

    return outbox
