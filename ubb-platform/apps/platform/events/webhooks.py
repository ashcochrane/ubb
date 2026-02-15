import hashlib
import hmac
import json
import logging
import time

import httpx

from apps.platform.events.webhook_models import TenantWebhookConfig, WebhookDeliveryAttempt

logger = logging.getLogger("ubb.webhooks")

WEBHOOK_TIMEOUT = 10  # seconds


def compute_signature(payload_bytes: bytes, secret: str) -> str:
    """Compute HMAC-SHA256 signature for webhook payload."""
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def deliver_webhook(event):
    """Deliver an outbox event to all matching tenant webhook configs.

    This is called as an outbox handler. It finds all active webhook configs
    for the tenant that match the event type, and POSTs to each.
    """
    configs = TenantWebhookConfig.objects.filter(
        tenant_id=event.tenant_id,
        is_active=True,
    )

    for config in configs:
        # Check event type filter
        if config.event_types and event.event_type not in config.event_types:
            continue

        _deliver_to_config(config, event)


def _deliver_to_config(config, event):
    """POST event payload to a single webhook config URL."""
    payload = {
        "event_type": event.event_type,
        "event_id": str(event.id),
        "tenant_id": str(event.tenant_id),
        "timestamp": int(time.time()),
        "data": event.payload,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    signature = compute_signature(payload_bytes, config.secret)

    headers = {
        "Content-Type": "application/json",
        "X-UBB-Signature": signature,
        "X-UBB-Event-Type": event.event_type,
    }

    attempt = WebhookDeliveryAttempt(
        webhook_config=config,
        outbox_event=event,
    )

    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT) as client:
            response = client.post(config.url, content=payload_bytes, headers=headers)
        attempt.status_code = response.status_code
        attempt.success = 200 <= response.status_code < 300
        if not attempt.success:
            attempt.error_message = response.text[:500]
    except httpx.TimeoutException as e:
        attempt.success = False
        attempt.error_message = str(e)[:500]
        attempt.save()
        logger.warning(
            "webhook.delivery_timeout",
            extra={
                "data": {
                    "config_id": str(config.id),
                    "event_id": str(event.id),
                    "error": str(e)[:200],
                }
            },
        )
        raise  # Re-raise for Celery retry
    except Exception as e:
        attempt.success = False
        attempt.error_message = str(e)[:500]
        attempt.save()
        logger.warning(
            "webhook.delivery_failed",
            extra={
                "data": {
                    "config_id": str(config.id),
                    "event_id": str(event.id),
                    "error": str(e)[:200],
                }
            },
        )
        # Re-raise network errors for Celery retry; swallow only non-network issues
        if isinstance(e, (httpx.HTTPError, OSError)):
            raise
        return

    attempt.save()


def handle_webhook_delivery(event_id, payload):
    """Outbox handler that delivers events to tenant webhooks."""
    from apps.platform.events.models import OutboxEvent

    try:
        event = OutboxEvent.objects.get(id=event_id)
    except OutboxEvent.DoesNotExist:
        return
    deliver_webhook(event)
