"""Verify signatures on UBB outgoing webhooks.

UBB signs every webhook delivery twice during the v2 deprecation window:

- ``X-UBB-Signature-V2: t=<unix-seconds>,v1=<hexdigest>`` — the v2 scheme.
  ``<hexdigest>`` is HMAC-SHA256 over ``f"{t}.{raw_body}"`` with your endpoint
  secret. The signed timestamp bounds replay: ``verify_webhook`` rejects any
  delivery whose ``t`` is more than ``tolerance`` seconds (default 300) from
  the receiver's clock, so a captured request stops verifying minutes later.

- ``X-UBB-Signature: <hexdigest>`` — the LEGACY scheme: HMAC-SHA256 over the
  raw body only. There is no timestamp binding, so a captured delivery
  verifies FOREVER — anyone who ever sees a valid request (proxy logs, crash
  dumps) can replay it indefinitely. ``verify_webhook_legacy`` exists only so
  receivers can migrate gradually; switch to ``verify_webhook`` as soon as
  you can.

Always verify against the RAW request body bytes, before any JSON parsing or
re-serialization — re-encoded JSON almost never matches byte-for-byte.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from ubb.exceptions import UBBWebhookVerificationError

DEFAULT_TOLERANCE = 300  # seconds of clock skew / delivery delay allowed (v2)


def _as_bytes(payload: bytes | str) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return payload


def verify_webhook(payload: bytes, signature_header: str, secret: str,
                   tolerance: int = DEFAULT_TOLERANCE) -> dict:
    """Verify a v2-signed webhook delivery and return the parsed JSON payload.

    Args:
        payload: the RAW request body bytes, exactly as received.
        signature_header: the ``X-UBB-Signature-V2`` header value,
            ``t=<unix-seconds>,v1=<hexdigest>``.
        secret: the endpoint secret configured on the webhook.
        tolerance: maximum |now - t| in seconds (default 300). Deliveries
            signed further in the past OR future are rejected — this is what
            bounds replay of a captured request.

    Returns:
        The payload parsed as a dict.

    Raises:
        UBBWebhookVerificationError: malformed header, timestamp outside the
            tolerance window, or signature mismatch.
    """
    if not signature_header:
        raise UBBWebhookVerificationError("missing signature header")
    payload = _as_bytes(payload)

    timestamp: int | None = None
    candidate_sigs: list[str] = []  # all v1= values (allows secret rotation)
    for part in signature_header.split(","):
        key, _, value = part.strip().partition("=")
        if not value:
            continue
        if key == "t":
            try:
                timestamp = int(value)
            except ValueError:
                raise UBBWebhookVerificationError(
                    f"malformed signature header: non-integer timestamp {value!r}")
        elif key == "v1":
            candidate_sigs.append(value)
    if timestamp is None or not candidate_sigs:
        raise UBBWebhookVerificationError(
            "malformed signature header: expected 't=<unix-seconds>,v1=<hexdigest>', "
            f"got {signature_header!r}")

    now = int(time.time())
    if abs(now - timestamp) > tolerance:
        raise UBBWebhookVerificationError(
            f"timestamp outside tolerance: signed at {timestamp}, now {now} "
            f"(tolerance {tolerance}s) — possible replay or severe clock skew")

    signed_payload = str(timestamp).encode("utf-8") + b"." + payload
    expected = hmac.new(secret.encode("utf-8"), signed_payload,
                        hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected, sig) for sig in candidate_sigs):
        raise UBBWebhookVerificationError("signature mismatch")

    return json.loads(payload)


def verify_webhook_legacy(payload: bytes, signature: str, secret: str) -> dict:
    """Verify a LEGACY (body-only) webhook signature; returns the parsed dict.

    The legacy scheme (``X-UBB-Signature`` header) is HMAC-SHA256 over the raw
    body with NO timestamp, so there is nothing to bound replay against — a
    captured delivery verifies forever. That is why this is a separate,
    explicitly-named function with no ``tolerance`` parameter rather than a
    fallback inside :func:`verify_webhook`: calling it should be a visible,
    deliberate choice made only while migrating to the v2 header.

    Raises:
        UBBWebhookVerificationError: signature missing or mismatched.
    """
    if not signature:
        raise UBBWebhookVerificationError("missing signature")
    payload = _as_bytes(payload)
    expected = hmac.new(secret.encode("utf-8"), payload,
                        hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, signature):
        raise UBBWebhookVerificationError("signature mismatch")
    return json.loads(payload)
