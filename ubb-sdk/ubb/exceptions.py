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

class UBBStoppedError(UBBError):
    """A stop verdict rode a success response (one-rule contract).

    Raised by record_usage(..., raise_on_stop=True) when the ack carries
    ``stop=True`` — a task crossed its provider-cost limit or floor snapshot
    (scope "task"), an event landed on a non-active task, or the customer
    crossed their wallet floor / budget cap (scope "customer"). The event WAS
    recorded and charged either way — a stop is a signal, never a refusal;
    this tells the caller to stop sending work for the named scope. Default
    record_usage behavior is NOT to raise — read result.stop instead (opt
    into raising for an exception-driven loop)."""
    def __init__(self, reason: str | None = None, scope: str | None = None,
                 task_id: str | None = None):
        self.reason = reason
        self.scope = scope
        self.task_id = task_id
        super().__init__(f"Stopped ({scope or 'unknown scope'}): "
                         f"{reason or 'spend limit reached'}")

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
