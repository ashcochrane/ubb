import hashlib
import hmac
import json
import logging
import time

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend

from apps.platform.events.webhook_models import TenantWebhookConfig, WebhookDeliveryAttempt
from core.url_validation import validate_webhook_url

logger = logging.getLogger("ubb.webhooks")

WEBHOOK_TIMEOUT = 10  # seconds


class _PinnedIPBackend(SyncBackend):
    """httpcore network backend that pins TCP connections to a pre-validated IP.

    DNS resolution is bypassed: connect_tcp replaces the hostname with the IP
    address that was already validated by validate_webhook_url.  TLS SNI and
    certificate verification are unaffected because httpcore resolves the SNI
    hostname independently from origin.host, not from the host passed to
    connect_tcp — see httpcore/_sync/connection.py::HTTPConnection._connect
    where start_tls(server_hostname=self._origin.host.decode("ascii")) is
    called on the stream returned by connect_tcp, using the original hostname.
    """

    def __init__(self, validated_ip: str) -> None:
        self._validated_ip = validated_ip

    def connect_tcp(
        self,
        host: str,
        port: int,
        timeout: float | None = None,
        local_address: str | None = None,
        socket_options=None,
    ):
        # Replace the hostname with the pre-validated IP.  The caller
        # (HTTPConnection._connect) will subsequently call start_tls with
        # the original hostname for SNI + certificate verification.
        return super().connect_tcp(
            host=self._validated_ip,
            port=port,
            timeout=timeout,
            local_address=local_address,
            socket_options=socket_options,
        )


class _PinnedIPTransport(httpx.HTTPTransport):
    """httpx transport that pins TCP connections to a pre-validated IP.

    Constructs a normal HTTPTransport (preserving verify=True, SSL context
    setup, etc.) and then replaces the httpcore connection pool's network
    backend with _PinnedIPBackend so that every TCP connect goes to the
    validated IP rather than re-resolving the hostname.
    """

    def __init__(self, validated_ip: str, **kwargs) -> None:
        super().__init__(**kwargs)
        # self._pool is an httpcore.ConnectionPool created by HTTPTransport.__init__.
        # We swap its _network_backend after construction to avoid duplicating the
        # SSL context / limits setup that HTTPTransport already handles.
        self._pool._network_backend = _PinnedIPBackend(validated_ip)


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

    # SSRF / DNS-rebinding guard: re-validate at delivery time (Fix A) and pin
    # the TCP connection to the validated IP (Fix B) so the hostname cannot
    # re-resolve to a private address between this check and httpx's connect.
    try:
        validated_ip = validate_webhook_url(config.url)
    except ValueError as e:
        attempt.success = False
        attempt.error_message = f"blocked: {e}"[:500]
        attempt.save()
        logger.warning("webhook.delivery_blocked", extra={"data": {
            "config_id": str(config.id), "event_id": str(event.id), "reason": str(e)[:200]}})
        return

    transport = _PinnedIPTransport(validated_ip)
    try:
        with httpx.Client(timeout=WEBHOOK_TIMEOUT, transport=transport) as client:
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
