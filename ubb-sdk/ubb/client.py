from __future__ import annotations

from datetime import datetime

from ubb.exceptions import (
    UBBError, UBBValidationError,
)
from ubb.types import (
    PreCheckResult, RecordUsageResult, CloseRunResult, CustomerResult,
    BalanceResult, UsageEvent, TopUpResult, AutoTopUpResult, WithdrawResult,
    RefundResult, WalletTransaction, PaginatedResponse,
    CustomerMargin, DimensionMargin, MarginTrendPoint, CustomerRevenue,
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

    def record_usage(self, customer_id: str, request_id: str, idempotency_key: str, *,
                     provider_cost_micros: int | None = None, billed_cost_micros: int | None = None,
                     units: int | None = None, provider: str = "", event_type: str = "",
                     currency: str | None = None, tags: dict | None = None,
                     product_id: str = "", metadata: dict | None = None,
                     run_id: str | None = None,
                     usage_metrics: dict | None = None,
                     recorded_at: datetime | str | None = None,
                     raise_on_stop: bool = False) -> RecordUsageResult:
        """Record a usage event via metering — a full passthrough to
        ``MeteringClient.record_usage()`` (kept in signature parity by
        test_sdk_delegation.TestRecordUsageSignatureParity).

        Pricing: supply ``provider_cost_micros`` (explicit cost) and/or
        ``usage_metrics`` (named metrics priced server-side by the rate card);
        both are optional here and the server enforces its pricing rules.
        ``recorded_at`` backdates the event (tz-aware datetime or ISO-8601
        string, bounded by the tenant's backfill window). ``raise_on_stop``
        raises UBBCustomerStoppedError on a customer-wide stop verdict.

        Wallet deduction is handled server-side via the billing outbox handler
        — the SDK does NOT call billing.debit() to avoid double-debit.

        If run_id is provided, the event is associated with the run and the
        run's hard stop limits are checked. Raises UBBHardStopError if the run
        exceeds its limits (the run is automatically killed). Raises
        UBBRunNotActiveError if the run is already killed/completed.
        """
        metering = self._require_metering()
        return metering.record_usage(
            customer_id=customer_id,
            request_id=request_id,
            idempotency_key=idempotency_key,
            provider_cost_micros=provider_cost_micros,
            billed_cost_micros=billed_cost_micros,
            units=units,
            provider=provider,
            event_type=event_type,
            currency=currency,
            tags=tags,
            product_id=product_id,
            metadata=metadata,
            run_id=run_id,
            usage_metrics=usage_metrics,
            recorded_at=recorded_at,
            raise_on_stop=raise_on_stop,
        )

    def close_run(self, run_id: str) -> CloseRunResult:
        """Close (complete) a run. Requires metering product."""
        return self._require_metering().close_run(run_id)

    # ---- platform-level methods (use metering's HTTP client) ----

    def create_customer(self, external_id: str, stripe_customer_id: str = "",
                        metadata: dict | None = None,
                        account_type: str = "individual",
                        parent_external_id: str = "",
                        billing_topology: str = "") -> CustomerResult:
        """Create a new customer via the platform API.

        Uses metering's HTTP client (metering is always present) to call
        POST /api/v1/platform/customers.
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/platform/customers", json={
            "external_id": external_id,
            "stripe_customer_id": stripe_customer_id,
            "metadata": metadata or {},
            "account_type": account_type,
            "parent_external_id": parent_external_id,
            "billing_topology": billing_topology,
        })
        return CustomerResult(**r.json())

    def get_business(self, external_id: str) -> dict:
        """Get a business account view via the platform API.

        Uses metering's HTTP client to call
        GET /api/v1/platform/accounts/business/{external_id}.
        """
        metering = self._require_metering()
        r = metering._request("get", f"/api/v1/platform/accounts/business/{external_id}")
        return r.json()

    # ---- subscription orchestration (plan / subscribe / seats) ----

    def create_plan(self, key: str, name: str, *, access_fee_micros: int = 0,
                    per_seat_micros: int = 0, interval: str = "month") -> dict:
        """Define a tenant billing plan via the platform API.

        Calls POST /api/v1/platform/plans and returns the created plan as a dict.
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/platform/plans", json={
            "key": key,
            "name": name,
            "access_fee_micros": access_fee_micros,
            "per_seat_micros": per_seat_micros,
            "interval": interval,
        })
        return r.json()

    def subscribe_customer(self, external_id: str, plan_key: str,
                           seats: int = 0) -> dict:
        """Subscribe an end-customer to a plan (access fee + seats).

        Calls POST /api/v1/platform/customers/{external_id}/subscribe and returns
        the response dict (subscription_id, amount_micros, quantity).
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/platform/customers/{external_id}/subscribe",
            json={"plan_key": plan_key, "seats": seats},
        )
        return r.json()

    def set_seats(self, external_id: str, seats: int) -> dict:
        """Change a customer's subscribed seat count.

        Calls POST /api/v1/platform/customers/{external_id}/seats and returns
        the response dict ({"seats": seats}).
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/platform/customers/{external_id}/seats",
            json={"seats": seats},
        )
        return r.json()

    def update_plan(self, key: str, *, access_fee_micros: int | None = None,
                    per_seat_micros: int | None = None,
                    migrate_existing: bool = False) -> dict:
        """Edit a plan's fees (F5.4). Only non-None axes are changed.

        A provisioned axis gets a NEW versioned Stripe Price on the same
        Product; existing subscriptions keep their old price (grandfathered)
        unless migrate_existing=True (repointed without proration). Calls
        PATCH /api/v1/platform/plans/{key} and returns the updated plan dict
        (includes pricing_version).
        """
        metering = self._require_metering()
        body: dict = {"migrate_existing": migrate_existing}
        if access_fee_micros is not None:
            body["access_fee_micros"] = access_fee_micros
        if per_seat_micros is not None:
            body["per_seat_micros"] = per_seat_micros
        r = metering._request("patch", f"/api/v1/platform/plans/{key}", json=body)
        return r.json()

    def cancel_subscription(self, external_id: str, at_period_end: bool = True) -> dict:
        """Cancel a customer's subscription (default: at period end).

        Calls POST /api/v1/platform/customers/{external_id}/subscription/cancel
        and returns the response dict (subscription_id, status,
        cancel_at_period_end, paused).
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/platform/customers/{external_id}/subscription/cancel",
            json={"at_period_end": at_period_end},
        )
        return r.json()

    def pause_subscription(self, external_id: str) -> dict:
        """Pause a customer's subscription (collection voided; sub stays active).

        Calls POST /api/v1/platform/customers/{external_id}/subscription/pause
        and returns the response dict.
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/platform/customers/{external_id}/subscription/pause",
            json={},
        )
        return r.json()

    def resume_subscription(self, external_id: str) -> dict:
        """Resume a customer's subscription: clears pause AND any pending cancel.

        Calls POST /api/v1/platform/customers/{external_id}/subscription/resume
        and returns the response dict.
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/platform/customers/{external_id}/subscription/resume",
            json={},
        )
        return r.json()

    def get_tenant_config(self) -> dict:
        """Get the tenant's own configuration.

        Calls GET /api/v1/tenant/config and returns the response as a dict.
        """
        metering = self._require_metering()
        r = metering._request("get", "/api/v1/tenant/config")
        return r.json()

    def update_tenant_config(self, *, billing_mode: str | None = None,
                              products: list[str] | None = None,
                              require_cost_card_coverage: bool | None = None,
                              automatic_tax_enabled: bool | None = None,
                              default_currency: str | None = None) -> dict:
        """Update the tenant's own configuration.

        Calls PATCH /api/v1/tenant/config with only the provided (non-None) fields.
        Returns the updated config as a dict. ``automatic_tax_enabled=True``
        turns on Stripe Tax passthrough (subscriptions + usage invoices); the
        server preflights the connected account's Stripe Tax status when the
        tenant is charge-ready and rejects with 422 if Tax is not active.

        ``default_currency`` is a lowercase ISO code (e.g. ``"eur"``); only
        2-decimal currencies are accepted (zero-decimal currencies like jpy
        are rejected with 422 until minor-unit support lands), and the server
        refuses the change with 409 once any money exists for the tenant
        (wallet transactions, provisioned plan prices, pushed usage invoices
        or Stripe subscriptions) — set it before billing anything.
        """
        metering = self._require_metering()
        body = {}
        if billing_mode is not None:
            body["billing_mode"] = billing_mode
        if products is not None:
            body["products"] = products
        if require_cost_card_coverage is not None:
            body["require_cost_card_coverage"] = require_cost_card_coverage
        if automatic_tax_enabled is not None:
            body["automatic_tax_enabled"] = automatic_tax_enabled
        if default_currency is not None:
            body["default_currency"] = default_currency
        r = metering._request("patch", "/api/v1/tenant/config", json=body)
        return r.json()

    # ---- sandbox (F4.4) ----

    def create_sandbox(self) -> dict:
        """Provision (or fetch) the tenant's sandbox sibling and mint a test key.

        Calls POST /api/v1/tenant/sandbox (requires the LIVE ubb_live_ key) and
        returns the response dict: ``sandbox_tenant_id`` plus ``api_key`` — the
        raw ubb_test_ key, returned only in this response. Each call mints a
        fresh test key (that is also the rotation path).
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/tenant/sandbox", json={})
        return r.json()

    def get_sandbox(self) -> dict:
        """Get the tenant's sandbox status.

        Calls GET /api/v1/tenant/sandbox (live key) and returns the response
        dict: ``exists``, ``sandbox_tenant_id``, ``key_prefixes``.
        """
        metering = self._require_metering()
        r = metering._request("get", "/api/v1/tenant/sandbox")
        return r.json()

    # ---- API key lifecycle (F5.2) ----

    def list_api_keys(self) -> dict:
        """List the calling tenant's API keys (prefix + metadata only —
        never the raw key or its hash).

        Calls GET /api/v1/tenant/api-keys and returns the response dict.
        """
        metering = self._require_metering()
        r = metering._request("get", "/api/v1/tenant/api-keys")
        return r.json()

    def create_api_key(self, label: str = "", is_test: bool = False) -> dict:
        """Mint a new API key. The raw key is in this response EXACTLY once.

        Calls POST /api/v1/tenant/api-keys. ``is_test=True`` routes the mint
        to the tenant's sandbox sibling (the key lands ON the sandbox tenant
        — see the response's ``tenant_id``).
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/tenant/api-keys",
                              json={"label": label, "is_test": is_test})
        return r.json()

    def rotate_api_key(self, key_id: str) -> dict:
        """Rotate an API key: mint a successor and deactivate the old key in
        one transaction. The new raw key is in this response exactly once;
        the old key stops authenticating immediately.

        Calls POST /api/v1/tenant/api-keys/{key_id}/rotate.
        """
        metering = self._require_metering()
        r = metering._request(
            "post", f"/api/v1/tenant/api-keys/{key_id}/rotate", json={})
        return r.json()

    def revoke_api_key(self, key_id: str) -> dict:
        """Soft-revoke an API key (instant). Revoking the tenant's last
        active key is refused server-side (409 -> UBBConflictError).

        Calls DELETE /api/v1/tenant/api-keys/{key_id}.
        """
        metering = self._require_metering()
        r = metering._request("delete", f"/api/v1/tenant/api-keys/{key_id}")
        return r.json()

    # ---- Stripe Connect onboarding ----

    def start_connect_onboarding(self, return_url: str = "") -> dict:
        """Begin Stripe Connect OAuth onboarding for the tenant.

        Calls POST /api/v1/connect/start and returns the response dict,
        which contains ``authorize_url`` — redirect the tenant there to
        connect their Stripe account.
        """
        metering = self._require_metering()
        r = metering._request("post", "/api/v1/connect/start",
                              json={"return_url": return_url})
        return r.json()

    def get_connect_status(self) -> dict:
        """Get the tenant's Stripe Connect status.

        Calls GET /api/v1/connect/status and returns the response dict
        (account_id, charges_enabled, onboarded).
        """
        metering = self._require_metering()
        r = metering._request("get", "/api/v1/connect/status")
        return r.json()

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
        """Withdraw from a customer wallet. Requires billing product.

        Routes to the guarded /withdraw endpoint (floor-checked — rejects an
        overdraw), NOT the raw debit escape hatch. customer_id is the platform
        customer UUID.
        """
        billing = self._require_billing()
        result = billing.withdraw(customer_id, amount_micros, idempotency_key,
                                  description)
        return WithdrawResult(
            transaction_id=result.get("transaction_id", ""),
            balance_micros=result.get("balance_micros", 0),
        )

    def refund_usage(self, customer_id: str, usage_event_id: str,
                     idempotency_key: str, reason: str = "") -> RefundResult:
        """Refund a usage event. Requires billing product.

        Routes to the guarded, lot-aware /refund endpoint, which resolves the
        original charge amount server-side (no client-supplied amount). NOT a
        raw credit. customer_id is the platform customer UUID.
        """
        billing = self._require_billing()
        result = billing.refund(customer_id, usage_event_id, idempotency_key,
                                reason)
        return RefundResult(
            refund_id=result.get("refund_id", ""),
            balance_micros=result.get("balance_micros", 0),
        )

    def get_transactions(self, customer_id: str, cursor: str | None = None,
                         limit: int = 50) -> PaginatedResponse[WalletTransaction]:
        """Get wallet transactions. Requires billing product."""
        return self._require_billing().get_transactions(customer_id, cursor=cursor, limit=limit)

    def set_budget(self, customer_id, cap_micros, enforce_mode="advisory",
                   hard_stop_pct=100, alert_levels=None, fail_closed=False):
        return self._require_billing().set_budget(
            customer_id, cap_micros, enforce_mode, hard_stop_pct, alert_levels, fail_closed)

    def get_budget(self, customer_id):
        return self._require_billing().get_budget(customer_id)

    def get_budget_status(self, customer_id):
        return self._require_billing().get_budget_status(customer_id)

    def get_usage_invoices(self, customer_id):
        return self._require_billing().get_usage_invoices(customer_id)

    def get_postpaid_config(self):
        return self._require_billing().get_postpaid_config()

    def set_postpaid_config(self, usage_line_item_group_by="",
                            consolidate_with_subscription=None):
        return self._require_billing().set_postpaid_config(
            usage_line_item_group_by, consolidate_with_subscription)

    # ---- margin delegates ----

    def get_customer_margin(self, customer_id, start_date=None, end_date=None):
        return self._require_metering().get_customer_margin(customer_id, start_date, end_date)

    def get_margin_by_dimension(self, *, provider=False, product=False, tag_key=None,
                                start_date=None, end_date=None):
        return self._require_metering().get_margin_by_dimension(
            provider=provider, product=product, tag_key=tag_key,
            start_date=start_date, end_date=end_date)

    def get_unprofitable_customers(self, period_start=None):
        return self._require_metering().get_unprofitable_customers(period_start)

    def get_margin_trend(self, customer_id, periods=6):
        return self._require_metering().get_margin_trend(customer_id, periods)

    def set_customer_revenue(self, customer_id, recurring_amount_micros, interval="month",
                             currency="usd", effective_from=None, effective_to=None):
        return self._require_metering().set_customer_revenue(
            customer_id, recurring_amount_micros, interval, currency, effective_from, effective_to)

    def get_customer_revenue(self, customer_id):
        return self._require_metering().get_customer_revenue(customer_id)

    # ---- markup delegates ----

    def get_markup(self):
        return self._require_metering().get_markup()

    def set_markup(self, *, markup_percentage_micros=0, fixed_uplift_micros=0):
        return self._require_metering().set_markup(markup_percentage_micros=markup_percentage_micros, fixed_uplift_micros=fixed_uplift_micros)

    def get_customer_markup(self, customer_id):
        return self._require_metering().get_customer_markup(customer_id)

    def set_customer_markup(self, customer_id, *, markup_percentage_micros=0, fixed_uplift_micros=0):
        return self._require_metering().set_customer_markup(customer_id, markup_percentage_micros=markup_percentage_micros, fixed_uplift_micros=fixed_uplift_micros)

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
