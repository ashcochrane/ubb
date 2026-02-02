from __future__ import annotations


class UBBError(Exception):
    pass

class UBBAuthError(UBBError):
    pass

class UBBAPIError(UBBError):
    def __init__(self, status_code: int, detail: str = ""):
        self.status_code = status_code
        self.detail = detail
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
