from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.retry import request_with_retry


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
        code, detail = self._extract_error(response)
        if response.status_code == 409:
            raise UBBConflictError(detail, code=code)
        if response.status_code >= 400:
            err = UBBAPIError(response.status_code, detail, code=code)
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
    def _extract_error(response: httpx.Response) -> tuple[str | None, str]:
        """(code, detail) from an RFC 9457 problem+json body (#78); falls
        back to (None, raw text) for anything non-problem."""
        try:
            body = response.json()
            if isinstance(body, dict):
                detail = body.get("detail") or body.get("title") or response.text
                return body.get("code"), detail
        except Exception:
            pass
        return None, response.text

    # ---- public API ----

    def sync(self) -> dict:
        """Trigger a Stripe subscription sync via POST /api/v1/subscriptions/sync."""
        r = self._request("post", "/api/v1/subscriptions/sync")
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
