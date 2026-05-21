from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.retry import request_with_retry
from ubb.types import (
    SubscriptionResult, SubscriptionInvoice, CustomerEconomics,
    EconomicsSummary, PaginatedResponse,
)


class SubscriptionsClient:
    """Product-specific client for the UBB Subscriptions API (/api/v1/subscriptions/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, max_retries: int = 3) -> None:
        self._base_url = base_url.rstrip("/")
        self._max_retries = max_retries
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

    def sync(self) -> dict:
        """Trigger a Stripe subscription sync via POST /api/v1/subscriptions/sync."""
        r = self._request("post", "/api/v1/subscriptions/sync")
        return r.json()

    def get_economics(self, period_start: str | None = None,
                      period_end: str | None = None) -> dict:
        """Get unit economics for all customers via GET /api/v1/subscriptions/economics.

        Returns raw dict with 'period', 'customers' list, and 'summary'.
        Use get_customer_economics() or get_economics_summary() for typed results.
        """
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics", params=params)
        return r.json()

    def get_customer_economics(self, customer_id: str,
                               period_start: str | None = None,
                               period_end: str | None = None) -> CustomerEconomics:
        """Get unit economics for a single customer via GET /api/v1/subscriptions/economics/{customer_id}."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", f"/api/v1/subscriptions/economics/{customer_id}", params=params)
        data = r.json()
        return CustomerEconomics(
            customer_id=str(data["customer_id"]),
            external_id=data.get("external_id", ""),
            plan=data.get("plan", ""),
            subscription_revenue_micros=data.get("subscription_revenue_micros", 0),
            usage_cost_micros=data.get("usage_cost_micros", 0),
            gross_margin_micros=data.get("gross_margin_micros", 0),
            margin_percentage=data.get("margin_percentage", 0.0),
            period=data.get("period"),
        )

    def get_economics_summary(self, period_start: str | None = None,
                              period_end: str | None = None) -> EconomicsSummary:
        """Get economics summary via GET /api/v1/subscriptions/economics/summary."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/subscriptions/economics/summary", params=params)
        data = r.json()
        return EconomicsSummary(
            total_revenue_micros=data.get("total_revenue_micros", 0),
            total_cost_micros=data.get("total_cost_micros", 0),
            total_margin_micros=data.get("total_margin_micros", 0),
            avg_margin_percentage=data.get("avg_margin_percentage", 0.0),
            unprofitable_customers=data.get("unprofitable_customers", 0),
            total_customers=data.get("total_customers", 0),
            period=data.get("period"),
        )

    def get_subscription(self, customer_id: str) -> SubscriptionResult:
        """Get a customer's subscription via GET /api/v1/subscriptions/customers/{customer_id}/subscription."""
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/subscription")
        data = r.json()
        return SubscriptionResult(
            id=str(data["id"]),
            stripe_subscription_id=data["stripe_subscription_id"],
            stripe_product_name=data.get("stripe_product_name", ""),
            status=data["status"],
            amount_micros=data.get("amount_micros", 0),
            currency=data.get("currency", "USD"),
            interval=data.get("interval", ""),
            current_period_start=data.get("current_period_start", ""),
            current_period_end=data.get("current_period_end", ""),
            last_synced_at=data.get("last_synced_at"),
        )

    def get_invoices(self, customer_id: str, cursor: str | None = None,
                     limit: int = 20) -> PaginatedResponse[SubscriptionInvoice]:
        """Get a customer's invoices via GET /api/v1/subscriptions/customers/{customer_id}/invoices."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/subscriptions/customers/{customer_id}/invoices", params=params)
        body = r.json()
        invoices = [
            SubscriptionInvoice(
                id=str(inv["id"]),
                stripe_invoice_id=inv.get("stripe_invoice_id", ""),
                amount_micros=inv.get("amount_micros", 0),
                currency=inv.get("currency", "USD"),
                status=inv.get("status", ""),
                period_start=inv.get("period_start", ""),
                period_end=inv.get("period_end", ""),
                paid_at=inv.get("paid_at"),
            )
            for inv in body["data"]
        ]
        return PaginatedResponse(
            data=invoices,
            next_cursor=body.get("next_cursor"),
            has_more=body["has_more"],
        )

    def close(self) -> None:
        self._http.close()
