from __future__ import annotations


class UBBError(Exception):
    pass

class UBBAuthError(UBBError):
    pass

class UBBAPIError(UBBError):
    """An error response from the API (RFC 9457 problem+json, #78).

    ``code`` is the stable snake_case registry code — the machine contract;
    ``detail`` is prose and may change wording without notice."""
    def __init__(self, status_code: int, detail: str = "", code: str | None = None):
        self.status_code = status_code
        self.detail = detail
        self.code = code
        self.retry_after: float | None = None
        super().__init__(f"API error {status_code}"
                         + (f" [{code}]" if code else "") + f": {detail}")

class UBBValidationError(UBBError):
    """Client-side input validation failure (e.g., micros not divisible by 10_000)."""
    pass

class UBBConnectionError(UBBError):
    """Cannot reach the API (network error or timeout)."""
    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)

class UBBStopRequested(BaseException):
    """UBB recorded the event and is asking you to stop spending for a scope.

    Raised by ``record_usage`` BY DEFAULT when the acknowledgement carries a
    stop verdict (``stop=True``): the work crossed its supplier-cost ceiling
    or floor snapshot (scope "task"), the event landed on work that is no
    longer active, or the customer crossed a floor or ceiling of their own
    (scope "customer"). THE EVENT WAS RECORDED AND CHARGED. The write
    committed, the acknowledgement was built, and only then was this raised,
    carrying it — so it is a control signal about the NEXT call and never a
    failed submission. Do not resend the event; stop sending work for
    ``stop_scope``.

    It derives from ``BaseException`` — not ``Exception``, not ``UBBError`` —
    for the reason ``KeyboardInterrupt`` does: a tenant's own
    ``except Exception:`` around a provider loop must not be able to swallow
    the one signal that protects their customer's money and carry on
    spending. Catch it by name, once, at the outermost boundary that can
    honour its scope; a helper that knows about one call has neither the
    authority nor the context to halt everything for a customer. A bare
    ``except:`` or ``except BaseException:`` still catches it, and that is
    accepted: the objective is the common accidental failure, not technical
    impossibility (#179 §1.4). Every ordinary SDK failure stays an
    ``Exception`` under ``UBBError``; this is the one type outside it.

    ``result`` is the whole acknowledgement (a ``RecordUsageResponse``, the
    exact object ``raise_on_stop=False`` would have returned), so nothing is
    lost by catching this; ``event_id``, ``stop_scope``, ``stop_reason`` and
    ``task_id`` are lifted off it and ``idempotency_key`` off the call, so a
    handler can log what happened and reconcile without a second request.
    ``record_batch`` never raises this — it reports the stop per item."""
    def __init__(self, result, *, idempotency_key: str | None = None):
        self.result = result
        self.idempotency_key = idempotency_key
        self.event_id = result.event_id
        self.stop_scope = result.stop_scope
        self.stop_reason = result.stop_reason
        self.task_id = result.task_id
        super().__init__(
            f"UBB requested a stop for {self.stop_scope or 'an unnamed scope'}"
            f" ({self.stop_reason or 'spend ceiling reached'}). Event "
            f"{self.event_id} was recorded and charged; do not resend it")

class UBBWebhookVerificationError(UBBError):
    """Webhook signature verification failed.

    Raised by ubb.webhooks.verify_webhook / verify_webhook_legacy for a bad
    signature, a timestamp outside the tolerance window, or a malformed
    signature header. Treat the delivery as untrusted and respond non-2xx.
    """
    pass


# The per-code API exception hierarchy is GENERATED from openapi/error-codes.json
# (ubb/codegen/generate_exceptions.py) and committed under the ratchet. Importing
# it here re-exports every status-family parent (ConflictError, …) and per-code
# leaf (InsufficientBalanceError, …) from ``ubb.exceptions``. The import sits at
# the bottom so UBBAPIError is already defined when the generated module (which
# subclasses it) imports back — a benign, resolved circular import.
from ubb._exceptions_generated import *  # noqa: E402,F401,F403
from ubb._exceptions_generated import ConflictError  # noqa: E402

# Backwards-compatible alias: 409 Conflict was ``UBBConflictError`` before the
# registry-derived hierarchy landed; it is now exactly ``ConflictError``.
UBBConflictError = ConflictError
