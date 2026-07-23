import logging

from django.db import IntegrityError, transaction

from apps.platform.events.schemas import RefundRequested

logger = logging.getLogger(__name__)


def handle_refund_requested(event_id, payload):
    """Create Refund record in metering when billing approves a refund.

    Registered as outbox handler with requires_product="metering".
    Idempotent: IntegrityError from OneToOneField is silently ignored.
    Uses savepoint so IntegrityError doesn't break the outer transaction.
    """
    from apps.metering.usage.models import UsageEvent, Refund

    evt = RefundRequested.from_payload(payload)

    try:
        event = UsageEvent.objects.get(
            id=evt.usage_event_id, tenant_id=evt.tenant_id,
        )
    except UsageEvent.DoesNotExist:
        logger.warning(
            "Refund requested for missing usage event",
            extra={"data": {"usage_event_id": evt.usage_event_id}},
        )
        return

    try:
        with transaction.atomic():
            refund = Refund.objects.create(
                tenant_id=evt.tenant_id,
                customer_id=evt.customer_id,
                usage_event=event,
                amount_micros=evt.refund_amount_micros,
                reason=evt.reason,
            )

            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import UsageRefunded

            write_event(UsageRefunded(
                tenant_id=evt.tenant_id,
                customer_id=evt.customer_id,
                event_id=event.id,
                refund_id=refund.id,
                refund_amount_micros=evt.refund_amount_micros,
            ))
    except IntegrityError as exc:
        if "refund" in str(exc).lower() or "unique" in str(exc).lower():
            pass  # Already refunded — idempotent
        else:
            logger.exception(
                "Unexpected IntegrityError in refund handler",
                extra={"data": {"usage_event_id": evt.usage_event_id}},
            )
            raise
