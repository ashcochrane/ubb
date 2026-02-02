from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBValidationError, UBBConnectionError,
)
from ubb.types import (
    PreCheckResult, RecordUsageResult, CustomerResult, BalanceResult,
    UsageEvent, TopUpResult, AutoTopUpResult, WithdrawResult, RefundResult,
    WalletTransaction, PaginatedResponse,
)


def _check_micros(value: int, name: str) -> None:
    """Validate that a micros value is positive."""
    if value <= 0:
        raise UBBValidationError(f"{name} must be positive, got {value}")


def _check_micros_allow_zero(value: int, name: str) -> None:
    """Validate that a micros value is non-negative."""
    if value < 0:
        raise UBBValidationError(f"{name} must be non-negative, got {value}")


class UBBClient:
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001", timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> UBBClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        try:
            response = getattr(self._http, method)(path, **kwargs)
        except httpx.TimeoutException as e:
            raise UBBConnectionError("Request timed out", original=e) from e
        except httpx.ConnectError as e:
            raise UBBConnectionError("Could not connect to UBB API", original=e) from e
        if response.status_code == 401:
            raise UBBAuthError("Invalid or revoked API key")
        detail = self._extract_error_detail(response)
        if response.status_code == 409:
            raise UBBConflictError(detail)
        if response.status_code >= 400:
            raise UBBAPIError(response.status_code, detail)
        return response

    @staticmethod
    def _extract_error_detail(response: httpx.Response) -> str:
        """Parse JSON error body if available, fallback to raw text."""
        try:
            body = response.json()
            if isinstance(body, dict) and "error" in body:
                return body["error"]
            if isinstance(body, dict) and "detail" in body:
                return body["detail"]
        except Exception:
            pass
        return response.text

    def pre_check(self, customer_id: str) -> PreCheckResult:
        r = self._request("post", "/api/v1/pre-check", json={"customer_id": customer_id})
        return PreCheckResult(**r.json())

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                     cost_micros: int, metadata: dict | None = None) -> RecordUsageResult:
        _check_micros(cost_micros, "cost_micros")
        r = self._request("post", "/api/v1/usage", json={
            "customer_id": customer_id, "request_id": request_id,
            "idempotency_key": idempotency_key, "cost_micros": cost_micros,
            "metadata": metadata or {},
        })
        return RecordUsageResult(**r.json())

    def create_customer(self, external_id: str, email: str, metadata: dict | None = None) -> CustomerResult:
        """Create a new customer. Raises UBBConflictError (409) if external_id already exists."""
        r = self._request("post", "/api/v1/customers", json={
            "external_id": external_id, "email": email, "metadata": metadata or {},
        })
        return CustomerResult(**r.json())

    def get_balance(self, customer_id: str) -> BalanceResult:
        r = self._request("get", f"/api/v1/customers/{customer_id}/balance")
        return BalanceResult(**r.json())

    def get_usage(self, customer_id: str, cursor: str | None = None, limit: int = 50) -> PaginatedResponse[UsageEvent]:
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/customers/{customer_id}/usage", params=params)
        body = r.json()
        events = [UsageEvent(**item) for item in body["data"]]
        return PaginatedResponse(data=events, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def create_top_up(self, customer_id: str, amount_micros: int) -> TopUpResult:
        _check_micros(amount_micros, "amount_micros")
        r = self._request("post", f"/api/v1/customers/{customer_id}/top-up", json={"amount_micros": amount_micros})
        return TopUpResult(**r.json())

    def configure_auto_top_up(self, customer_id: str, threshold: int, amount: int, enabled: bool = True) -> AutoTopUpResult:
        _check_micros_allow_zero(threshold, "threshold")
        _check_micros(amount, "amount")
        r = self._request("put", f"/api/v1/customers/{customer_id}/auto-top-up", json={
            "is_enabled": enabled, "trigger_threshold_micros": threshold, "top_up_amount_micros": amount,
        })
        return AutoTopUpResult(**r.json())

    def withdraw(self, customer_id: str, amount_micros: int, idempotency_key: str, description: str = "") -> WithdrawResult:
        _check_micros(amount_micros, "amount_micros")
        r = self._request("post", f"/api/v1/customers/{customer_id}/withdraw", json={
            "amount_micros": amount_micros, "idempotency_key": idempotency_key, "description": description,
        })
        return WithdrawResult(**r.json())

    def refund_usage(self, customer_id: str, usage_event_id: str, idempotency_key: str, reason: str = "") -> RefundResult:
        r = self._request("post", f"/api/v1/customers/{customer_id}/refund", json={
            "usage_event_id": usage_event_id, "idempotency_key": idempotency_key, "reason": reason,
        })
        return RefundResult(**r.json())

    def get_transactions(self, customer_id: str, cursor: str | None = None, limit: int = 50) -> PaginatedResponse[WalletTransaction]:
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/customers/{customer_id}/transactions", params=params)
        body = r.json()
        txns = [WalletTransaction(**item) for item in body["data"]]
        return PaginatedResponse(data=txns, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def close(self) -> None:
        self._http.close()
