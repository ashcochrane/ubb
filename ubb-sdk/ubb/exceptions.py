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

class UBBHardStopError(UBBAPIError):
    """429 Hard stop exceeded — run has been killed."""
    def __init__(self, run_id: str, reason: str, total_cost_micros: int, detail: str = ""):
        self.run_id = run_id
        self.reason = reason
        self.total_cost_micros = total_cost_micros
        super().__init__(429, detail or f"Hard stop: {reason}")

class UBBCustomerStoppedError(UBBError):
    """Tier-2 customer-wide cooperative spend stop on a 200 response.

    Raised by record_usage(..., raise_on_stop=True) when the customer crossed
    their wallet floor / budget cap. The event WAS recorded and charged (unlike
    UBBHardStopError's 429); this signals the caller to halt the customer's runs
    at the next safe boundary. Default record_usage behavior is NOT to raise —
    read result.stop instead (opt into raising for an exception-driven loop)."""
    def __init__(self, reason: str | None = None, scope: str | None = None,
                 run_id: str | None = None):
        self.reason = reason
        self.scope = scope
        self.run_id = run_id
        super().__init__(f"Customer stopped: {reason or 'spend limit reached'}")


class UBBRunNotActiveError(UBBAPIError):
    """409 Run is not active (already killed or completed)."""
    def __init__(self, run_id: str, status: str, detail: str = ""):
        self.run_id = run_id
        self.run_status = status
        super().__init__(409, detail or f"Run {run_id} is {status}")

class UBBWebhookVerificationError(UBBError):
    """Webhook signature verification failed.

    Raised by ubb.webhooks.verify_webhook / verify_webhook_legacy for a bad
    signature, a timestamp outside the tolerance window, or a malformed
    signature header. Treat the delivery as untrusted and respond non-2xx.
    """
    pass
