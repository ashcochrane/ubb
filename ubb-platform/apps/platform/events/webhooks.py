import hashlib
import hmac
import json
import logging
import time

import httpcore
import httpx
from httpcore._backends.sync import SyncBackend

from apps.platform.events.webhook_models import TenantWebhookConfig, WebhookDeliveryAttempt
from core.exceptions import UBBError
from core.url_validation import validate_webhook_url

logger = logging.getLogger("ubb.webhooks")

WEBHOOK_TIMEOUT = 10  # seconds


class WebhookDeliveryIncomplete(UBBError):
    """One or more endpoints failed retryably during a delivery pass.

    Raised at the END of the pass — never mid-loop — so one endpoint's failure
    can't stop its neighbours receiving the event. Bubbling up to the outbox
    marks the event pending again; on the retry pass the per-endpoint
    checkpoint (an existing successful WebhookDeliveryAttempt) skips endpoints
    that already received the event, so only the still-failing
    (event, endpoint) pairs are re-POSTed.
    """


class _RetryableHTTPStatus(UBBError):
    """A response landed but with a retryable status (5xx / 429) — the
    endpoint did not durably receive the event. Internal to this module:
    raised by _deliver_to_config after recording the attempt, collected by
    deliver_webhook exactly like a network failure."""


# The single definition of "this delivery failure is retryable" — collected by
# deliver_webhook into WebhookDeliveryIncomplete. Everything else (3xx/4xx
# responses, non-network exceptions, blocked URLs) is permanent for the pair.
RETRYABLE_DELIVERY_ERRORS = (httpx.HTTPError, OSError, _RetryableHTTPStatus)


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
    """Compute HMAC-SHA256 signature for webhook payload.

    LEGACY (v1) scheme: body-only — no timestamp binding, so a captured
    delivery verifies forever. Kept (and still sent as ``X-UBB-Signature``)
    during the v2 deprecation window; new receivers should verify
    ``X-UBB-Signature-V2`` instead (see compute_signature_v2 / the SDK's
    ``ubb.webhooks.verify_webhook``).
    """
    return hmac.new(
        secret.encode("utf-8"),
        payload_bytes,
        hashlib.sha256,
    ).hexdigest()


def compute_signature_v2(payload_bytes: bytes, secret: str, timestamp: int) -> str:
    """Compute the v2 (replay-bounded) webhook signature.

    HMAC-SHA256 over ``f"{timestamp}.{body}"`` — the signed string is the
    decimal unix-seconds timestamp, a literal ``.``, then the raw request
    body bytes. Sent as ``X-UBB-Signature-V2: t=<ts>,v1=<hexdigest>``.
    Binding the timestamp lets receivers reject deliveries older than their
    tolerance window (SDK default 300s), closing the indefinite-replay hole
    of the legacy body-only scheme.
    """
    signed_payload = str(timestamp).encode("utf-8") + b"." + payload_bytes
    return hmac.new(
        secret.encode("utf-8"),
        signed_payload,
        hashlib.sha256,
    ).hexdigest()


def deliver_webhook(event):
    """Deliver an outbox event to all matching tenant webhook configs.

    This is called as an outbox handler. It finds all active webhook configs
    for the tenant that match the event type, and POSTs to each.

    Delivery is checkpointed per (event, endpoint): a successful
    WebhookDeliveryAttempt is the checkpoint, so a retry pass skips endpoints
    that already received the event. A failing endpoint never aborts the pass
    for its neighbours — retryable failures are collected and re-raised as
    WebhookDeliveryIncomplete only after every endpoint has been attempted.
    """
    configs = TenantWebhookConfig.objects.filter(
        tenant_id=event.tenant_id,
        is_active=True,
    )
    if not configs:
        return

    # F4.4: every outbound payload carries the tenant's mode so receivers can
    # tell sandbox traffic from live (OutboxEvent.tenant_id is a bare UUID).
    from apps.platform.tenants.models import Tenant
    is_sandbox = (
        Tenant.objects.filter(id=event.tenant_id)
        .values_list("is_sandbox", flat=True).first()
    )
    livemode = not bool(is_sandbox)

    delivered_config_ids = set(
        WebhookDeliveryAttempt.objects.filter(
            outbox_event=event,
            success=True,
        ).values_list("webhook_config_id", flat=True)
    )

    retryable_failures = []
    for config in configs:
        # Event-type filter (explicit opt-in; see catalog.py for the contract):
        #   ["*"]      -> all events
        #   []         -> no events (deliver nothing)
        #   ["a","b"]  -> only those types
        if "*" not in config.event_types and event.event_type not in config.event_types:
            continue

        # Per-endpoint checkpoint: this pair already succeeded on an earlier pass.
        if config.id in delivered_config_ids:
            continue

        try:
            _deliver_to_config(config, event, livemode=livemode)
        except RETRYABLE_DELIVERY_ERRORS as e:
            # The failed attempt is already recorded by _deliver_to_config.
            retryable_failures.append((config, e))

    if retryable_failures:
        summary = "; ".join(
            f"config={config.id}: {type(e).__name__}: {str(e)[:120]}"
            for config, e in retryable_failures
        )
        raise WebhookDeliveryIncomplete(
            f"{len(retryable_failures)} webhook endpoint(s) still failing for "
            f"event {event.id}: {summary}"
        ) from retryable_failures[-1][1]


def _deliver_to_config(config, event, *, livemode=True):
    """POST event payload to a single webhook config URL."""
    ts = int(time.time())
    payload = {
        "event_type": event.event_type,
        "event_id": str(event.id),
        "tenant_id": str(event.tenant_id),
        "timestamp": ts,
        "livemode": livemode,
        "data": event.payload,
    }
    payload_bytes = json.dumps(payload, sort_keys=True).encode("utf-8")
    # Legacy body-only header can't carry candidates, so it signs with the
    # active secret only — a not-yet-migrated receiver follows the cutover.
    signature = compute_signature(payload_bytes, config.secret)
    # Same ts as payload["timestamp"]: signed at send time, parseable from the
    # header alone (the receiver never needs to parse the body to verify). One
    # v1= candidate per active signing secret — during a two-secret overlap
    # rotation (#83) that is the new secret AND the retiring one, so a receiver
    # on either verifies. config.signing_secrets() owns the window logic.
    v2_candidates = ",".join(
        f"v1={compute_signature_v2(payload_bytes, secret, ts)}"
        for secret in config.signing_secrets()
    )

    headers = {
        "Content-Type": "application/json",
        # Legacy body-only signature — kept during the v2 deprecation window
        # so existing receivers keep verifying unchanged. Prefer the v2
        # header: the legacy scheme has no timestamp binding and a captured
        # delivery replays forever.
        "X-UBB-Signature": signature,
        "X-UBB-Signature-V2": f"t={ts},{v2_candidates}",
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
        raise  # Collected by deliver_webhook -> WebhookDeliveryIncomplete -> outbox retry
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
        # Raise network errors so deliver_webhook collects them for the outbox
        # retry; swallow only non-network issues (no retry for this pair).
        if isinstance(e, RETRYABLE_DELIVERY_ERRORS):
            raise
        return

    attempt.save()

    if not attempt.success and (attempt.status_code >= 500 or attempt.status_code == 429):
        # The endpoint answered but didn't durably receive the event — a 5xx
        # (or 429) is as transient as a network failure, so it retries per
        # endpoint. 3xx/4xx stay permanent: a receiver rejecting the request
        # will keep rejecting it.
        raise _RetryableHTTPStatus(
            f"HTTP {attempt.status_code} from config {config.id} for event {event.id}"
        )


def handle_webhook_delivery(event_id, payload):
    """Outbox handler that delivers events to tenant webhooks."""
    from apps.platform.events.models import OutboxEvent

    try:
        event = OutboxEvent.objects.get(id=event_id)
    except OutboxEvent.DoesNotExist:
        return
    deliver_webhook(event)
