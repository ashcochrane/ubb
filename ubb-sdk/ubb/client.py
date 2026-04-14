from __future__ import annotations

from ubb.exceptions import (
    UBBError, UBBValidationError,
)
from ubb.types import (
    PreCheckResult, RecordUsageResult, CloseRunResult, CustomerResult,
    BalanceResult, UsageEvent, TopUpResult, AutoTopUpResult, WithdrawResult,
    RefundResult, WalletTransaction, PaginatedResponse,
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
                 max_retries: int = 3,
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
            MeteringClient(api_key, base_url, timeout, max_retries=max_retries) if metering else None
        )
        self.billing: BillingClient | None = (
            BillingClient(api_key, base_url, timeout, max_retries=max_retries) if billing else None
        )

        from ubb.subscriptions import SubscriptionsClient

        self.subscriptions: SubscriptionsClient | None = (
            SubscriptionsClient(api_key, base_url, timeout, max_retries=max_retries) if subscriptions else None
        )

        from ubb.referrals import ReferralsClient

        self.referrals: ReferralsClient | None = (
            ReferralsClient(api_key, base_url, timeout, max_retries=max_retries) if referrals else None
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

    def pre_check(self, customer_id: str, start_run: bool = False,
                  run_metadata: dict | None = None,
                  external_run_id: str = "") -> PreCheckResult:
        """Pre-check whether a request should proceed.

        If billing is enabled, delegates to billing pre-check which checks
        customer status, rate limits, and wallet balance vs arrears threshold.
        If billing is not enabled, returns trivially allowed.

        If start_run=True and the check passes, a Run is created server-side
        and its ID is returned in the result.
        """
        if self.billing:
            check = self.billing.pre_check(
                customer_id,
                start_run=start_run,
                run_metadata=run_metadata,
                external_run_id=external_run_id,
            )
            return PreCheckResult(
                allowed=check.get("allowed", check.get("can_proceed", True)),
                can_proceed=check.get("can_proceed", check.get("allowed", True)),
                balance_micros=check.get("balance_micros"),
                run_id=check.get("run_id"),
                cost_limit_micros=check.get("cost_limit_micros"),
                hard_stop_balance_micros=check.get("hard_stop_balance_micros"),
            )

        return PreCheckResult(allowed=True, can_proceed=True)

    def start_run(self, customer_id: str, metadata: dict | None = None,
                  external_run_id: str = "") -> PreCheckResult:
        """Start a run: pre-check + create a Run if allowed.

        Convenience wrapper around pre_check(start_run=True).
        Requires billing product.
        """
        self._require_billing()
        return self.pre_check(
            customer_id,
            start_run=True,
            run_metadata=metadata,
            external_run_id=external_run_id,
        )

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str,
                     event_type: str, provider: str, usage_metrics: dict,
                     group: str | None = None,
                     run_id: str | None = None) -> RecordUsageResult:
        """Record a usage event via metering.

        Delegates to metering.record_usage(). Wallet deduction is handled
        server-side via the billing outbox handler — the SDK does NOT call
        billing.debit() to avoid double-debit.

        If run_id is provided, the event is associated with the run and
        the run's hard stop limits are checked. Raises UBBHardStopError
        if the run exceeds its limits (the run is automatically killed).
        Raises UBBRunNotActiveError if the run is already killed/completed.
        """
        metering = self._require_metering()

        return metering.record_usage(
            customer_id=customer_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            event_type=event_type,
            provider=provider,
            usage_metrics=usage_metrics,
            group=group,
            run_id=run_id,
        )

    def close_run(self, run_id: str) -> CloseRunResult:
        """Close (complete) a run. Requires metering product."""
        return self._require_metering().close_run(run_id)

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
        """Withdraw from customer wallet. Requires billing product."""
        return self._require_billing().withdraw(
            customer_id, amount_micros, idempotency_key, description,
        )

    def refund_usage(self, customer_id: str, usage_event_id: str,
                     idempotency_key: str, reason: str = "") -> RefundResult:
        """Refund a usage event. Requires billing product."""
        return self._require_billing().refund(
            customer_id, usage_event_id, idempotency_key, reason,
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
