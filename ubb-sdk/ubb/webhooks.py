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

THE CATALOGUE (#464, slice 6 §16–§17). Every event UBB publishes is named in
the registry's closed ``webhook_event_type`` set, and this module holds it by
reference from the generated vocabulary — one constant per name, reached BY
MODULE as ``vocabulary.WEBHOOK_EVENT_TYPE_<OWNER>_<STATE>`` (the spelling
``docs/conventions/sdk-wrap.md`` prescribes; a hand-written re-export here
would be the second copy of every name that convention refuses), and the
whole set as ``vocabulary.WEBHOOK_EVENT_TYPE_VALUES``. A subscription's
``event_types`` may also hold the one selector that is not a name, ``"*"``
(every current and future event), so what a subscription may NAME is
:data:`EVENT_SELECTORS` below, and :func:`unpublished_event_types` says
whether a proposed subscription names only published events before the API
refuses it with a ``validation_error``. An event's name in a delivered body
(``payload["event_type"]``) is always one of the 37, never the selector.
"""
from __future__ import annotations

import hashlib
import hmac
import json
import time

from ubb.exceptions import UBBWebhookVerificationError
# The catalogue, reached by module — see the module docstring.
from ubb import vocabulary

DEFAULT_TOLERANCE = 300  # seconds of clock skew / delivery delay allowed (v2)

#: The selector that subscribes to every event, current and future. Stored
#: verbatim by the API; never the name of a delivered event.
WILDCARD = "*"

#: EVERYTHING A SUBSCRIPTION'S ``event_types`` MAY NAME: the registry's closed
#: catalogue of 37 events plus the wildcard. Not an alias of the generated set
#: — the wildcard is a selector the registry deliberately does not list — and
#: the reason a subscription is checked against this rather than against
#: ``vocabulary.WEBHOOK_EVENT_TYPE_VALUES`` directly.
EVENT_SELECTORS = frozenset(vocabulary.WEBHOOK_EVENT_TYPE_VALUES | {WILDCARD})


def unpublished_event_types(event_types) -> frozenset[str]:
    """The entries of a proposed subscription that UBB does not publish.

    Empty when the subscription names only published events (the wildcard
    counts as published: it selects every event UBB publishes), so
    ``if unpublished_event_types(types):`` is the question *would the API
    refuse this?* — answered before the round trip, with the offending names
    in hand, from the same closed set the server's ``enum`` states. Membership
    only: the server also refuses an EMPTY list (a subscription to nothing),
    which is not a naming question and is left to it.

    >>> unpublished_event_types([vocabulary.WEBHOOK_EVENT_TYPE_USAGE_RECORDED])
    frozenset()
    >>> sorted(unpublished_event_types(["usage.recieved", "*"]))
    ['usage.recieved']
    """
    return frozenset(event_types) - EVENT_SELECTORS


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
