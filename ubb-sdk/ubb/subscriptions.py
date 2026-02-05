from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)


class SubscriptionsClient:
    """Product-specific client for the UBB Subscriptions API (/api/v1/subscriptions/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> SubscriptionsClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internal request helper (same pattern as BillingClient) ----

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

    # ---- public API ----

    def sync(self) -> dict:
        """Trigger a Stripe subscription sync via POST /api/v1/subscriptions/sync."""
        r = self._request("post", "/api/v1/subscriptions/sync")
        return r.json()

    def get_economics(self, period_start: str | None = None,
                      period_end: str | None = None) -> dict:
        """Get unit economics for all customers via GET /api/v1/subscriptions/economics."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics", params=params)
        return r.json()

    def get_customer_economics(self, customer_id: str,
                               period_start: str | None = None,
                               period_end: str | None = None) -> dict:
        """Get unit economics for a single customer via GET /api/v1/subscriptions/economics/{customer_id}."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", f"/api/v1/subscriptions/economics/{customer_id}", params=params)
        return r.json()

    def get_economics_summary(self, period_start: str | None = None,
                              period_end: str | None = None) -> dict:
        """Get economics summary via GET /api/v1/subscriptions/economics/summary."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics/summary", params=params)
        return r.json()

    def get_subscription(self, customer_id: str) -> dict:
        """Get a customer's subscription via GET /api/v1/subscriptions/customers/{customer_id}/subscription."""
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/subscription")
        return r.json()

    def get_invoices(self, customer_id: str, cursor: str | None = None,
                     limit: int = 20) -> dict:
        """Get a customer's invoices via GET /api/v1/subscriptions/customers/{customer_id}/invoices."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/invoices", params=params)
        return r.json()

    def close(self) -> None:
        self._http.close()
