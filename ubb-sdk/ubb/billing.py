from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.retry import request_with_retry
from ubb.types import (
    BalanceResult, TopUpResult, WithdrawResult, RefundResult,
    RevenueAnalyticsResult, WalletTransaction, PaginatedResponse,
)


class BillingClient:
    """Product-specific client for the UBB Billing API (/api/v1/billing/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> BillingClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internal request helper (same pattern as UBBClient) ----

    def _request_once(self, method: str, path: str, **kwargs) -> httpx.Response:
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
            err = UBBAPIError(response.status_code, detail)
            retry_after = response.headers.get("Retry-After")
            if retry_after:
                try:
                    err.retry_after = float(retry_after)
                except (ValueError, TypeError):
                    pass
            raise err
        return response

    def _request(self, method: str, path: str, **kwargs) -> httpx.Response:
        return request_with_retry(
            self._request_once, max_retries=self._max_retries,
            method=method, path=path, **kwargs,
        )

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

    # ---- public API ----

    def debit(self, customer_id: str, amount_micros: int, reference: str) -> dict:
        """Debit a customer's wallet via POST /api/v1/billing/debit."""
        r = self._request("post", "/api/v1/billing/debit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "reference": reference,
        })
        return r.json()

    def credit(self, customer_id: str, amount_micros: int, source: str,
               reference: str) -> dict:
        """Credit a customer's wallet via POST /api/v1/billing/credit."""
        r = self._request("post", "/api/v1/billing/credit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "source": source,
            "reference": reference,
        })
        return r.json()

    def get_balance(self, customer_id: str) -> BalanceResult:
        """Get customer balance via GET /api/v1/billing/customers/{customer_id}/balance."""
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/balance")
        return BalanceResult(**r.json())

    def pre_check(self, customer_id: str, start_run: bool = False,
                  run_metadata: dict | None = None, external_run_id: str = "") -> dict:
        """Pre-check billing via POST /api/v1/billing/pre-check."""
        body: dict = {"customer_id": customer_id}
        if start_run:
            body["start_run"] = True
        if run_metadata:
            body["run_metadata"] = run_metadata
        if external_run_id:
            body["external_run_id"] = external_run_id
        r = self._request("post", "/api/v1/billing/pre-check", json=body)
        return r.json()

    def create_top_up(self, customer_id: str, amount_micros: int,
                      success_url: str, cancel_url: str) -> TopUpResult:
        """Create a top-up checkout session via POST /api/v1/billing/customers/{customer_id}/top-up."""
        r = self._request("post", f"/api/v1/billing/customers/{customer_id}/top-up", json={
            "amount_micros": amount_micros,
            "success_url": success_url,
            "cancel_url": cancel_url,
        })
        return TopUpResult(**r.json())

    def configure_auto_topup(self, customer_id: str, is_enabled: bool,
                             trigger_threshold_micros: int | None = None,
                             top_up_amount_micros: int | None = None) -> dict:
        """Configure auto top-up via PUT /api/v1/billing/customers/{customer_id}/auto-top-up."""
        body: dict = {"is_enabled": is_enabled}
        if trigger_threshold_micros is not None:
            body["trigger_threshold_micros"] = trigger_threshold_micros
        if top_up_amount_micros is not None:
            body["top_up_amount_micros"] = top_up_amount_micros
        r = self._request("put", f"/api/v1/billing/customers/{customer_id}/auto-top-up", json=body)
        return r.json()

    def withdraw(self, customer_id: str, amount_micros: int,
                 idempotency_key: str, description: str = "") -> WithdrawResult:
        """Withdraw from customer wallet via POST /api/v1/billing/customers/{customer_id}/withdraw."""
        body: dict = {
            "amount_micros": amount_micros,
            "idempotency_key": idempotency_key,
        }
        if description:
            body["description"] = description
        r = self._request("post", f"/api/v1/billing/customers/{customer_id}/withdraw", json=body)
        data = r.json()
        return WithdrawResult(
            transaction_id=data["transaction_id"],
            balance_micros=data["balance_micros"],
        )

    def refund(self, customer_id: str, usage_event_id: str,
               idempotency_key: str, reason: str = "") -> RefundResult:
        """Refund a usage event via POST /api/v1/billing/customers/{customer_id}/refund."""
        body: dict = {
            "usage_event_id": usage_event_id,
            "idempotency_key": idempotency_key,
        }
        if reason:
            body["reason"] = reason
        r = self._request("post", f"/api/v1/billing/customers/{customer_id}/refund", json=body)
        data = r.json()
        return RefundResult(
            refund_id=data["refund_id"],
            balance_micros=data["balance_micros"],
        )

    def get_transactions(self, customer_id: str, cursor: str | None = None,
                         limit: int = 20) -> PaginatedResponse[WalletTransaction]:
        """Get transactions via GET /api/v1/billing/customers/{customer_id}/transactions."""
        params: dict = {"limit": limit}
        if cursor is not None:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/transactions", params=params)
        body = r.json()
        txns = [WalletTransaction(**item) for item in body["data"]]
        return PaginatedResponse(data=txns, next_cursor=body.get("next_cursor"), has_more=body["has_more"])

    def get_revenue_analytics(self, start_date: str | None = None,
                              end_date: str | None = None) -> RevenueAnalyticsResult:
        """Get revenue analytics via GET /api/v1/billing/analytics/revenue."""
        params = {}
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        r = self._request("get", "/api/v1/billing/analytics/revenue", params=params)
        return RevenueAnalyticsResult(**r.json())

    def close(self) -> None:
        self._http.close()
