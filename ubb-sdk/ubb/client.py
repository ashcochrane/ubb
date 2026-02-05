from __future__ import annotations

import httpx

from ubb.exceptions import (
    UBBError, UBBAuthError, UBBAPIError, UBBConflictError, UBBValidationError, UBBConnectionError,
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
    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, widget_secret: str | None = None,
                 tenant_id: str | None = None,
                 metering: bool = True, billing: bool = False,
                 subscriptions: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._widget_secret = widget_secret
        self._tenant_id = tenant_id
        self._http = httpx.Client(
            base_url=self._base_url,
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=timeout,
        )

        # Product-specific clients (lazy imports to avoid circular deps)
        from ubb.metering import MeteringClient
        from ubb.billing import BillingClient

        self.metering: MeteringClient | None = (
            MeteringClient(api_key, base_url, timeout) if metering else None
        )
        self.billing: BillingClient | None = (
            BillingClient(api_key, base_url, timeout) if billing else None
        )
        # Backward compat alias
        self.billing_client = self.billing

        from ubb.subscriptions import SubscriptionsClient

        self.subscriptions: SubscriptionsClient | None = (
            SubscriptionsClient(api_key, base_url, timeout) if subscriptions else None
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

    def create_widget_token(self, customer_id: str, expires_in: int = 900) -> str:
        """Create a signed JWT for widget authentication."""
        if not self._widget_secret:
            raise ValueError("widget_secret is required to create widget tokens")
        if not self._tenant_id:
            raise ValueError("tenant_id is required to create widget tokens")

        import time
        import jwt

        payload = {
            "sub": customer_id,
            "tid": self._tenant_id,
            "iss": "ubb",
            "exp": int(time.time()) + expires_in,
        }
        return jwt.encode(payload, self._widget_secret, algorithm="HS256")

    def pre_check(self, customer_id: str, event_type: str | None = None,
                  provider: str | None = None,
                  usage_metrics: dict | None = None) -> PreCheckResult:
        """Pre-check whether a request should proceed.

        When metering and billing product clients are configured and event_type
        is provided, orchestrates across both products: estimates cost via
        metering, then checks billing eligibility. Otherwise falls back to the
        legacy flat /api/v1/pre-check endpoint.
        """
        # Orchestrated path: metering estimate + billing pre-check
        if self.metering and event_type:
            cost = self.metering.estimate_cost(
                event_type, provider or "", usage_metrics or {},
            )
            if self.billing:
                check = self.billing.pre_check(customer_id, cost)
                return PreCheckResult(
                    allowed=check.get("allowed", check.get("can_proceed", True)),
                    can_proceed=check.get("can_proceed", check.get("allowed", True)),
                    estimated_cost_micros=cost,
                    balance_micros=check.get("balance_micros"),
                )
            return PreCheckResult(
                allowed=True,
                can_proceed=True,
                estimated_cost_micros=cost,
            )

        # Legacy fallback: flat endpoint
        r = self._request("post", "/api/v1/pre-check", json={"customer_id": customer_id})
        return PreCheckResult(**r.json())

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                     cost_micros: int | None = None, metadata: dict | None = None,
                     event_type: str | None = None, provider: str | None = None,
                     usage_metrics: dict | None = None, properties: dict | None = None,
                     group_keys: dict | None = None) -> RecordUsageResult:
        """Record a usage event, optionally orchestrating metering + billing.

        When the metering product client is configured, delegates to
        metering.record_usage(). If billing is also configured and the event
        has a billed_cost_micros > 0, automatically debits the customer wallet.
        Falls back to the legacy flat /api/v1/usage endpoint when metering is
        not configured.
        """
        # Orchestrated path: metering + optional billing debit
        if self.metering:
            result = self.metering.record_usage(
                customer_id=customer_id,
                request_id=request_id,
                idempotency_key=idempotency_key,
                cost_micros=cost_micros,
                metadata=metadata,
                event_type=event_type,
                provider=provider,
                usage_metrics=usage_metrics,
                properties=properties,
                group_keys=group_keys,
            )
            if self.billing and result.billed_cost_micros:
                debit = self.billing.debit(
                    customer_id, result.billed_cost_micros, str(result.event_id),
                )
                # Return enriched result with balance_after_micros from debit
                result = RecordUsageResult(
                    event_id=result.event_id,
                    new_balance_micros=result.new_balance_micros,
                    suspended=result.suspended,
                    provider_cost_micros=result.provider_cost_micros,
                    billed_cost_micros=result.billed_cost_micros,
                    balance_after_micros=debit.get("new_balance_micros"),
                )
            return result

        # Legacy fallback: flat endpoint (no product clients configured)
        body: dict = {
            "customer_id": customer_id, "request_id": request_id,
            "idempotency_key": idempotency_key, "metadata": metadata or {},
        }
        if cost_micros is not None:
            _check_micros(cost_micros, "cost_micros")
            body["cost_micros"] = cost_micros
        if usage_metrics is not None:
            body["event_type"] = event_type
            body["provider"] = provider
            body["usage_metrics"] = usage_metrics
            if properties:
                body["properties"] = properties
        if group_keys is not None:
            body["group_keys"] = group_keys
        r = self._request("post", "/api/v1/usage", json=body)
        return RecordUsageResult(**r.json())

    def create_customer(self, external_id: str, stripe_customer_id: str,
                        metadata: dict | None = None) -> CustomerResult:
        """Create a new customer. Raises UBBConflictError (409) if external_id already exists."""
        r = self._request("post", "/api/v1/customers", json={
            "external_id": external_id,
            "stripe_customer_id": stripe_customer_id,
            "metadata": metadata or {},
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

    def create_top_up(self, customer_id: str, amount_micros: int, *,
                      success_url: str, cancel_url: str) -> TopUpResult:
        _check_micros(amount_micros, "amount_micros")
        r = self._request("post", f"/api/v1/customers/{customer_id}/top-up", json={
            "amount_micros": amount_micros,
            "success_url": success_url,
            "cancel_url": cancel_url,
        })
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
        if self.metering is not None:
            self.metering.close()
        if self.billing is not None:
            self.billing.close()
        if self.subscriptions is not None:
            self.subscriptions.close()
