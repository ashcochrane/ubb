from __future__ import annotations

from ubb.exceptions import (
    UBBError, UBBValidationError,
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
    """Orchestrator that delegates to product-specific clients.

    Does NOT have its own HTTP client. All product-specific operations
    delegate to ``MeteringClient``, ``BillingClient``, ``SubscriptionsClient``,
    or ``ReferralsClient``. Platform-level calls (e.g. ``create_customer``)
    piggyback on ``self.metering._request`` since metering is always present.
    """

    def __init__(self, api_key: str, base_url: str = "http://localhost:8001",
                 timeout: float = 10.0, widget_secret: str | None = None,
                 tenant_id: str | None = None,
                 metering: bool = True, billing: bool = False,
                 subscriptions: bool = False,
                 referrals: bool = False) -> None:
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._widget_secret = widget_secret
        self._tenant_id = tenant_id

        # Product-specific clients (lazy imports to avoid circular deps)
        from ubb.metering import MeteringClient
        from ubb.billing import BillingClient

        self.metering: MeteringClient | None = (
            MeteringClient(api_key, base_url, timeout) if metering else None
        )
        self.billing: BillingClient | None = (
            BillingClient(api_key, base_url, timeout) if billing else None
        )

        from ubb.subscriptions import SubscriptionsClient

        self.subscriptions: SubscriptionsClient | None = (
            SubscriptionsClient(api_key, base_url, timeout) if subscriptions else None
        )

        from ubb.referrals import ReferralsClient

        self.referrals: ReferralsClient | None = (
            ReferralsClient(api_key, base_url, timeout) if referrals else None
        )

    def __enter__(self) -> UBBClient:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- product requirement helpers ----

    def _require_metering(self):
        if self.metering is None:
            raise UBBError("metering product is required for this operation")
        return self.metering

    def _require_billing(self):
        if self.billing is None:
            raise UBBError("billing product is required for this operation")
        return self.billing

    # ---- widget token (local, no HTTP) ----

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

    # ---- orchestrated methods ----

    def pre_check(self, customer_id: str) -> PreCheckResult:
        """Pre-check whether a request should proceed.

        If billing is enabled, delegates to billing pre-check which checks
        customer status, rate limits, and wallet balance vs arrears threshold.
        If billing is not enabled, returns trivially allowed.
        """
        if self.billing:
            check = self.billing.pre_check(customer_id)
            return PreCheckResult(
                allowed=check.get("allowed", check.get("can_proceed", True)),
                can_proceed=check.get("can_proceed", check.get("allowed", True)),
                balance_micros=check.get("balance_micros"),
            )

        return PreCheckResult(allowed=True, can_proceed=True)

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                     cost_micros: int | None = None, metadata: dict | None = None,
                     event_type: str | None = None, provider: str | None = None,
                     usage_metrics: dict | None = None, properties: dict | None = None,
                     group_keys: dict | None = None) -> RecordUsageResult:
        """Record a usage event via metering.

        Delegates to metering.record_usage(). Wallet deduction is handled
        server-side via the billing outbox handler — the SDK does NOT call
        billing.debit() to avoid double-debit.
        """
        metering = self._require_metering()

        return metering.record_usage(
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

    # ---- platform-level methods (use metering's HTTP client) ----

    def create_customer(self, external_id: str, stripe_customer_id: str = "",
                        metadata: dict | None = None) -> CustomerResult:
        """Create a new customer via the platform API.

        Uses metering's HTTP client (metering is always present) to call
        POST /api/v1/platform/customers.
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/platform/customers", json={
            "external_id": external_id,
            "stripe_customer_id": stripe_customer_id,
            "metadata": metadata or {},
        })
        return CustomerResult(**r.json())

    # ---- billing delegates ----

    def get_balance(self, customer_id: str) -> BalanceResult:
        """Get customer wallet balance. Requires billing product."""
        return self._require_billing().get_balance(customer_id)

    def get_usage(self, customer_id: str, cursor: str | None = None,
                  limit: int = 50) -> PaginatedResponse[UsageEvent]:
        """Get usage history. Requires metering product."""
        return self._require_metering().get_usage(customer_id, cursor=cursor, limit=limit)

    def create_top_up(self, customer_id: str, amount_micros: int, *,
                      success_url: str, cancel_url: str) -> TopUpResult:
        """Create a top-up checkout session. Requires billing product."""
        return self._require_billing().create_top_up(
            customer_id, amount_micros, success_url, cancel_url,
        )

    def configure_auto_top_up(self, customer_id: str, threshold: int,
                              amount: int, enabled: bool = True) -> AutoTopUpResult:
        """Configure auto top-up. Requires billing product."""
        billing = self._require_billing()
        result = billing.configure_auto_topup(
            customer_id, is_enabled=enabled,
            trigger_threshold_micros=threshold,
            top_up_amount_micros=amount,
        )
        return AutoTopUpResult(**result)

    def withdraw(self, customer_id: str, amount_micros: int,
                 idempotency_key: str, description: str = "") -> WithdrawResult:
        """Withdraw from customer wallet. Requires billing product.

        Note: This delegates to billing.debit with a withdraw reference.
        The billing client doesn't have a dedicated withdraw endpoint yet,
        so we use the debit endpoint.
        """
        billing = self._require_billing()
        result = billing.debit(customer_id, amount_micros, f"withdraw:{idempotency_key}")
        return WithdrawResult(
            transaction_id=result.get("transaction_id", ""),
            balance_micros=result.get("new_balance_micros", 0),
        )

    def refund_usage(self, customer_id: str, usage_event_id: str,
                     idempotency_key: str, reason: str = "") -> RefundResult:
        """Refund a usage event. Requires billing product.

        Delegates to billing.credit with a refund reference.
        """
        billing = self._require_billing()
        result = billing.credit(
            customer_id, amount_micros=0,
            source="refund", reference=f"refund:{usage_event_id}:{idempotency_key}",
        )
        return RefundResult(
            refund_id=result.get("transaction_id", ""),
            balance_micros=result.get("new_balance_micros", 0),
        )

    def get_transactions(self, customer_id: str, cursor: str | None = None,
                         limit: int = 50) -> PaginatedResponse[WalletTransaction]:
        """Get wallet transactions. Requires billing product."""
        return self._require_billing().get_transactions(customer_id, cursor=cursor, limit=limit)

    # ---- lifecycle ----

    def close(self) -> None:
        if self.metering is not None:
            self.metering.close()
        if self.billing is not None:
            self.billing.close()
        if self.subscriptions is not None:
            self.subscriptions.close()
        if self.referrals is not None:
            self.referrals.close()
