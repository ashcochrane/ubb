from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBAuthError, UBBAPIError, UBBConflictError, UBBConnectionError,
)
from ubb.retry import request_with_retry
from ubb.types import (
    BalanceResult, TopUpResult, WalletTransaction, PaginatedResponse,
    BudgetConfig, BudgetStatus, UsageInvoice, CreditGrant,
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

    def debit(self, customer_id: str, amount_micros: int, reference: str,
              idempotency_key: str) -> dict:
        """Debit a customer's wallet via POST /api/v1/billing/debit.

        idempotency_key is required (server-enforced) so a retried debit never
        double-charges. This is the raw, floor-less escape hatch — for a
        guarded withdrawal use ``withdraw``.
        """
        r = self._request("post", "/api/v1/billing/debit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "reference": reference,
            "idempotency_key": idempotency_key,
        })
        return r.json()

    def credit(self, customer_id: str, amount_micros: int, source: str,
               reference: str, idempotency_key: str) -> dict:
        """Credit a customer's wallet via POST /api/v1/billing/credit.

        idempotency_key is required (server-enforced). Adds plain, non-expiring
        adjustment money — for refunding a usage charge use ``refund``.
        """
        r = self._request("post", "/api/v1/billing/credit", json={
            "customer_id": customer_id,
            "amount_micros": amount_micros,
            "source": source,
            "reference": reference,
            "idempotency_key": idempotency_key,
        })
        return r.json()

    def withdraw(self, customer_id: str, amount_micros: int,
                 idempotency_key: str, description: str = "") -> dict:
        """Withdraw from a wallet via the guarded POST
        /customers/{customer_id}/withdraw (floor-checked — a debit is not).
        customer_id is the platform customer UUID."""
        r = self._request(
            "post", f"/api/v1/billing/customers/{customer_id}/withdraw", json={
                "amount_micros": amount_micros,
                "idempotency_key": idempotency_key,
                "description": description,
            })
        return r.json()

    def refund(self, customer_id: str, usage_event_id: str,
               idempotency_key: str, reason: str = "") -> dict:
        """Refund a usage charge via the lot-aware POST
        /customers/{customer_id}/refund (resolves the original charge amount
        server-side). customer_id is the platform customer UUID."""
        r = self._request(
            "post", f"/api/v1/billing/customers/{customer_id}/refund", json={
                "usage_event_id": usage_event_id,
                "reason": reason,
                "idempotency_key": idempotency_key,
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

    def set_budget(self, customer_id, cap_micros, enforce_mode="advisory",
                   hard_stop_pct=100, alert_levels=None, fail_closed=False):
        body = {"cap_micros": cap_micros, "enforce_mode": enforce_mode,
                "hard_stop_pct": hard_stop_pct, "fail_closed": fail_closed}
        if alert_levels is not None:
            body["alert_levels"] = alert_levels
        r = self._request("put", f"/api/v1/billing/customers/{customer_id}/budget", json=body)
        return BudgetConfig(**r.json())

    def get_budget(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/budget")
        return BudgetConfig(**r.json())

    def get_budget_status(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/budget/status")
        return BudgetStatus(**r.json())

    def get_usage_invoices(self, customer_id):
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/usage-invoices")
        return [UsageInvoice(**row) for row in r.json()]

    def create_grant(self, customer_id: str, kind: str, amount_micros: int,
                     idempotency_key: str, expires_at: str | None = None,
                     expires_in_days: int | None = None,
                     description: str = "") -> CreditGrant:
        """Create a credit grant lot via POST /api/v1/billing/customers/{customer_id}/grants.

        kind is "paid" or "promo". Pass expires_at (ISO-8601, tz-aware) OR
        expires_in_days; omit both for a non-expiring lot. idempotency_key is
        required — retries with the same key return the original grant.
        """
        body: dict = {
            "kind": kind,
            "amount_micros": amount_micros,
            "idempotency_key": idempotency_key,
        }
        if expires_at is not None:
            body["expires_at"] = expires_at
        if expires_in_days is not None:
            body["expires_in_days"] = expires_in_days
        if description:
            body["description"] = description
        r = self._request("post", f"/api/v1/billing/customers/{customer_id}/grants", json=body)
        return CreditGrant(**r.json())

    def list_grants(self, customer_id: str, status: str | None = None,
                    cursor: str | None = None, limit: int = 50) -> PaginatedResponse[CreditGrant]:
        """List grant lots via GET /api/v1/billing/customers/{customer_id}/grants."""
        params: dict = {"limit": limit}
        if status is not None:
            params["status"] = status
        if cursor is not None:
            params["cursor"] = cursor
        r = self._request("get", f"/api/v1/billing/customers/{customer_id}/grants", params=params)
        body = r.json()
        grants = [CreditGrant(**item) for item in body["data"]]
        return PaginatedResponse(data=grants, next_cursor=body.get("next_cursor"),
                                 has_more=body["has_more"])

    def void_grant(self, customer_id: str, grant_id: str) -> CreditGrant:
        """Void a grant via POST /api/v1/billing/customers/{customer_id}/grants/{grant_id}/void.

        Debits the lot's remaining (never below a zero balance) and retires it.
        Idempotent — voiding twice returns the already-voided lot.
        """
        r = self._request(
            "post", f"/api/v1/billing/customers/{customer_id}/grants/{grant_id}/void")
        return CreditGrant(**r.json())

    def get_postpaid_config(self):
        """The tenant's postpaid config:
        ``{"usage_line_item_group_by": str, "consolidate_with_subscription": bool}``."""
        r = self._request("get", "/api/v1/billing/postpaid-config")
        return r.json()

    def set_postpaid_config(self, usage_line_item_group_by="",
                            consolidate_with_subscription=None):
        """Update the postpaid config. ``consolidate_with_subscription=None``
        leaves the consolidation opt-in unchanged; True pins each period's
        usage onto the customer's subscription-renewal invoice (one Stripe
        invoice per period) with a standalone fallback."""
        body = {"usage_line_item_group_by": usage_line_item_group_by}
        if consolidate_with_subscription is not None:
            body["consolidate_with_subscription"] = consolidate_with_subscription
        r = self._request("put", "/api/v1/billing/postpaid-config", json=body)
        return r.json()

    def close(self) -> None:
        self._http.close()
