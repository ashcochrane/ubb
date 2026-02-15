import logging

from django.db import IntegrityError, transaction

logger = logging.getLogger(__name__)


def handle_refund_requested(event_id, payload):
    """Create Refund record in metering when billing approves a refund.

    Registered as outbox handler with requires_product="metering".
    Idempotent: IntegrityError from OneToOneField is silently ignored.
    Uses savepoint so IntegrityError doesn't break the outer transaction.
    """
    from apps.metering.usage.models import UsageEvent, Refund

    try:
        event = UsageEvent.objects.get(
            id=payload["usage_event_id"], tenant_id=payload["tenant_id"],
        )
    except UsageEvent.DoesNotExist:
        logger.warning(
            "Refund requested for missing usage event",
            extra={"data": {"usage_event_id": payload["usage_event_id"]}},
        )
        return

    try:
        with transaction.atomic():
            refund = Refund.objects.create(
                tenant_id=payload["tenant_id"],
                customer_id=payload["customer_id"],
                usage_event=event,
                amount_micros=payload["refund_amount_micros"],
                reason=payload.get("reason", ""),
            )

            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import UsageRefunded

            write_event(UsageRefunded(
                tenant_id=payload["tenant_id"],
                customer_id=payload["customer_id"],
                event_id=str(event.id),
                refund_id=str(refund.id),
                refund_amount_micros=payload["refund_amount_micros"],
            ))
    except IntegrityError as exc:
        if "refund" in str(exc).lower() or "unique" in str(exc).lower():
            pass  # Already refunded — idempotent
        else:
            logger.exception(
                "Unexpected IntegrityError in refund handler",
                extra={"data": {"usage_event_id": payload["usage_event_id"]}},
            )
            raise
