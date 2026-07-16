from __future__ import annotations


class UBBError(Exception):
    pass

class UBBAuthError(UBBError):
    pass

class UBBAPIError(UBBError):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
        self.retry_after: float | None = None
        super().__init__(f"API error {status_code}: {detail}")

class UBBValidationError(UBBError):
    """Client-side input validation failure (e.g., micros not divisible by 10_000)."""
    pass

class UBBConnectionError(UBBError):
    """Cannot reach the API (network error or timeout)."""
    def __init__(self, message: str, original: Exception | None = None):
        self.original = original
        super().__init__(message)

class UBBConflictError(UBBAPIError):
    """409 Conflict (e.g., duplicate external_id on create_customer)."""
    def __init__(self, detail: str = ""):
        super().__init__(409, detail)

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
