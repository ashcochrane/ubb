from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)


class ReferralsClient:
    """Product-specific client for the UBB Referrals API (/api/v1/referrals/)."""

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0) -> None:
        self._base_url = base_url.rstrip("/")
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

    def __enter__(self) -> ReferralsClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- internal request helper ----

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

    # ---- Program Management ----

    def create_program(self, reward_type: str, reward_value: float,
                       attribution_window_days: int = 30,
                       reward_window_days: int | None = None,
                       max_reward_micros: int | None = None,
                       estimated_cost_percentage: float | None = None) -> dict:
        """Create a referral program via POST /api/v1/referrals/program."""
        body: dict = {
            "reward_type": reward_type,
            "reward_value": reward_value,
            "attribution_window_days": attribution_window_days,
        }
        if reward_window_days is not None:
            body["reward_window_days"] = reward_window_days
        if max_reward_micros is not None:
            body["max_reward_micros"] = max_reward_micros
        if estimated_cost_percentage is not None:
            body["estimated_cost_percentage"] = estimated_cost_percentage
        r = self._request("post", "/api/v1/referrals/program", json=body)
        return r.json()

    def get_program(self) -> dict:
        """Get the active referral program via GET /api/v1/referrals/program."""
        r = self._request("get", "/api/v1/referrals/program")
        return r.json()

    def update_program(self, **kwargs) -> dict:
        """Update the active referral program via PATCH /api/v1/referrals/program."""
        r = self._request("patch", "/api/v1/referrals/program", json=kwargs)
        return r.json()

    def deactivate_program(self) -> dict:
        """Deactivate the referral program via DELETE /api/v1/referrals/program."""
        r = self._request("delete", "/api/v1/referrals/program")
        return r.json()

    def reactivate_program(self) -> dict:
        """Reactivate a deactivated program via POST /api/v1/referrals/program/reactivate."""
        r = self._request("post", "/api/v1/referrals/program/reactivate")
        return r.json()

    # ---- Referrer Management ----

    def register_referrer(self, customer_id: str) -> dict:
        """Register a customer as a referrer via POST /api/v1/referrals/referrers."""
        r = self._request("post", "/api/v1/referrals/referrers", json={
            "customer_id": customer_id,
        })
        return r.json()

    def get_referrer(self, customer_id: str) -> dict:
        """Get referrer details via GET /api/v1/referrals/referrers/{customer_id}."""
        r = self._request("get", f"/api/v1/referrals/referrers/{customer_id}")
        return r.json()

    def list_referrers(self, cursor: str | None = None, limit: int = 50) -> dict:
        """List referrers via GET /api/v1/referrals/referrers."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", "/api/v1/referrals/referrers", params=params)
        return r.json()

    # ---- Attribution ----

    def attribute(self, customer_id: str, *,
                  code: str | None = None,
                  link_token: str | None = None) -> dict:
        """Attribute a customer to a referrer via POST /api/v1/referrals/attribute."""
        body: dict = {"customer_id": customer_id}
        if code:
            body["code"] = code
        if link_token:
            body["link_token"] = link_token
        r = self._request("post", "/api/v1/referrals/attribute", json=body)
        return r.json()

    # ---- Rewards ----

    def get_earnings(self, customer_id: str) -> dict:
        """Get referrer earnings via GET /api/v1/referrals/referrers/{customer_id}/earnings."""
        r = self._request("get", f"/api/v1/referrals/referrers/{customer_id}/earnings")
        return r.json()

    def get_referrals(self, customer_id: str, cursor: str | None = None,
                      limit: int = 50) -> dict:
        """Get referrer's referrals via GET /api/v1/referrals/referrers/{customer_id}/referrals."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/referrals/referrers/{customer_id}/referrals",
                          params=params)
        return r.json()

    def get_ledger(self, referral_id: str, cursor: str | None = None,
                   limit: int = 50) -> dict:
        """Get referral reward ledger via GET /api/v1/referrals/referrals/{referral_id}/ledger."""
        params: dict = {"limit": limit}
        if cursor:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/referrals/referrals/{referral_id}/ledger",
                          params=params)
        return r.json()

    # ---- Revocation ----

    def revoke_referral(self, referral_id: str) -> dict:
        """Revoke a referral via DELETE /api/v1/referrals/referrals/{referral_id}."""
        r = self._request("delete", f"/api/v1/referrals/referrals/{referral_id}")
        return r.json()

    # ---- Analytics ----

    def get_analytics_summary(self) -> dict:
        """Get referral analytics summary via GET /api/v1/referrals/analytics/summary."""
        r = self._request("get", "/api/v1/referrals/analytics/summary")
        return r.json()

    def get_analytics_earnings(self, period_start: str | None = None,
                               period_end: str | None = None) -> dict:
        """Get earnings analytics via GET /api/v1/referrals/analytics/earnings."""
        params = {}
        if period_start:
            params["period_start"] = period_start
        if period_end:
            params["period_end"] = period_end
        r = self._request("get", "/api/v1/referrals/analytics/earnings", params=params)
        return r.json()

    def close(self) -> None:
        self._http.close()
