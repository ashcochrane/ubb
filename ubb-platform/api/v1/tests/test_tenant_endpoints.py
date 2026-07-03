import json
from datetime import date
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice


class TenantBillingPeriodsEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=1.00,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=50_000_000_000,
            event_count=1000,
            platform_fee_micros=500_000_000,
        )

    def test_list_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_usage_cost_micros"], 50_000_000_000)

    def test_unauthenticated_returns_401(self):
        response = self.http_client.get("/api/v1/tenant/billing-periods")
        self.assertEqual(response.status_code, 401)


class TenantInvoicesEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="invoiced",
            total_usage_cost_micros=50_000_000_000,
            platform_fee_micros=500_000_000,
        )
        TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=period,
            total_amount_micros=500_000_000,
            status="paid",
        )

    def test_list_invoices(self):
        response = self.http_client.get(
            "/api/v1/tenant/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_amount_micros"], 500_000_000)


class TenantConfigEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="ConfigTest",
            stripe_connected_account_id="acct_cfg",
            platform_fee_percentage=1.00,
            products=["metering"],
            billing_mode="meter_only",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cfg-test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    # --- GET ---

    def test_get_config_returns_200_with_expected_keys(self):
        response = self.http_client.get("/api/v1/tenant/config", **self._auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("billing_mode", "products", "require_cost_card_coverage",
                    "stripe_connected_account_id", "is_active"):
            self.assertIn(key, body, f"missing key: {key}")
        self.assertEqual(body["billing_mode"], "meter_only")
        self.assertIn("metering", body["products"])

    # --- PATCH: happy path ---

    def test_patch_billing_mode_and_products(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "postpaid", "products": ["metering", "billing"]}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.billing_mode, "postpaid")
        self.assertIn("billing", self.tenant.products)

    # --- PATCH: require_cost_card_coverage=true with no active cost cards → 422 ---

    def test_patch_require_cost_card_coverage_without_cost_cards_returns_422(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"require_cost_card_coverage": True}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body.get("code"), "no_cost_cards")

    # --- PATCH: billing_mode=prepaid with no billing product → 422 ---

    def test_patch_billing_mode_prepaid_without_billing_product_returns_422(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "prepaid"}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body.get("code"), "invalid_config")

    # --- PATCH: spend-safety caps (previously ORM-only) ---

    def test_get_config_includes_spend_cap_defaults(self):
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertEqual(body["min_balance_micros"], 0)
        self.assertIsNone(body["run_cost_limit_micros"])
        self.assertIsNone(body["hard_stop_balance_micros"])

    def test_patch_sets_all_three_spend_caps(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({
                "min_balance_micros": 5_000_000,
                "run_cost_limit_micros": 50_000_000,
                "hard_stop_balance_micros": -5_000_000,
            }),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.min_balance_micros, 5_000_000)
        self.assertEqual(self.tenant.run_cost_limit_micros, 50_000_000)
        self.assertEqual(self.tenant.hard_stop_balance_micros, -5_000_000)
        self.assertEqual(response.json()["run_cost_limit_micros"], 50_000_000)

    def test_patch_run_cost_limit_zero_or_negative_returns_422(self):
        for bad in (0, -1):
            response = self.http_client.patch(
                "/api/v1/tenant/config",
                data=json.dumps({"run_cost_limit_micros": bad}),
                content_type="application/json", **self._auth(),
            )
            self.assertEqual(response.status_code, 422, f"value {bad} should be rejected")
            self.assertEqual(response.json().get("code"), "invalid_config")

    def test_patch_min_balance_negative_returns_422(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"min_balance_micros": -1}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json().get("code"), "invalid_config")

    def test_patch_null_clears_nullable_caps(self):
        self.tenant.run_cost_limit_micros = 50_000_000
        self.tenant.hard_stop_balance_micros = -5_000_000
        self.tenant.save()
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"run_cost_limit_micros": None, "hard_stop_balance_micros": None}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.run_cost_limit_micros)
        self.assertIsNone(self.tenant.hard_stop_balance_micros)

    def test_patch_omitting_caps_leaves_them_unchanged(self):
        self.tenant.run_cost_limit_micros = 42_000_000
        self.tenant.min_balance_micros = 7_000_000
        self.tenant.save()
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "meter_only"}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.run_cost_limit_micros, 42_000_000)
        self.assertEqual(self.tenant.min_balance_micros, 7_000_000)


class TenantConfigCurrencyTest(TestCase):
    """CUR-1: writable default_currency — 2-decimal allowlist, 409 once money exists."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="CurrencyTest", products=["metering", "billing"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cur")

    def _patch(self, body):
        return self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    # --- happy path ---

    def test_patch_default_currency_on_fresh_tenant(self):
        resp = self._patch({"default_currency": "eur"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(resp.json()["default_currency"], "eur")
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "eur")

    def test_patch_default_currency_is_lowercased(self):
        resp = self._patch({"default_currency": "GBP"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "gbp")

    # --- zero-decimal rejection ---

    def test_patch_jpy_rejected_with_clear_message(self):
        resp = self._patch({"default_currency": "jpy"})
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body.get("code"), "unsupported_currency")
        self.assertIn("2-decimal", body["error"])
        self.assertIn("jpy", body["error"])

    # --- 409 once money exists (each condition) ---

    def _make_customer(self, ext="c1"):
        from apps.platform.customers.models import Customer
        return Customer.objects.create(tenant=self.tenant, external_id=ext)

    def _assert_locked(self):
        resp = self._patch({"default_currency": "eur"})
        self.assertEqual(resp.status_code, 409, resp.content)
        body = resp.json()
        self.assertEqual(body.get("code"), "currency_locked")
        self.assertIn("money", body["error"])
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "usd")  # unchanged

    def test_409_after_wallet_transaction(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction
        wallet = Wallet.objects.create(customer=self._make_customer())
        WalletTransaction.objects.create(
            wallet=wallet, transaction_type="TOP_UP",
            amount_micros=1_000_000, balance_after_micros=1_000_000)
        self._assert_locked()

    def test_409_after_provisioned_plan_price(self):
        from apps.subscriptions.models import TenantBillingPlan
        TenantBillingPlan.objects.create(
            tenant=self.tenant, key="pro", name="Pro",
            access_fee_micros=10_000_000,
            stripe_access_price_id="price_123")
        self._assert_locked()

    def test_409_after_pushed_usage_invoice(self):
        from datetime import date
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self._make_customer(),
            period_start=date(2026, 5, 1), period_end=date(2026, 6, 1),
            status="pushed", stripe_invoice_id="in_123")
        self._assert_locked()

    def test_409_after_stripe_subscription(self):
        from django.utils import timezone
        from apps.subscriptions.models import StripeSubscription
        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=self.tenant, customer=self._make_customer(),
            stripe_subscription_id="sub_123", stripe_product_name="Pro",
            status="active", amount_micros=10_000_000, interval="month",
            current_period_start=now, current_period_end=now,
            last_synced_at=now)
        self._assert_locked()

    def test_409_after_active_rate_card(self):
        """Cards are currency-pinned: a currency change would silently stop
        every card from matching and collapse COGS to the markup fallback."""
        from apps.metering.pricing.models import RateCard
        RateCard.objects.create(
            tenant=self.tenant, card_type="cost", metric_name="tokens",
            pricing_model="per_unit", rate_per_unit_micros=10,
            currency=self.tenant.default_currency)
        self._assert_locked()

    def test_retired_rate_card_does_not_lock(self):
        from django.utils import timezone
        from apps.metering.pricing.models import RateCard
        RateCard.objects.create(
            tenant=self.tenant, card_type="cost", metric_name="tokens",
            pricing_model="per_unit", rate_per_unit_micros=10,
            currency=self.tenant.default_currency, valid_to=timezone.now())
        resp = self._patch({"default_currency": "eur"})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_unprovisioned_plan_does_not_lock(self):
        """A plan with NO provisioned Stripe prices is not money yet."""
        from apps.subscriptions.models import TenantBillingPlan
        TenantBillingPlan.objects.create(
            tenant=self.tenant, key="draft", name="Draft",
            access_fee_micros=10_000_000)
        resp = self._patch({"default_currency": "eur"})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_pending_unpushed_invoice_does_not_lock(self):
        """A fresh pending usage invoice (no Stripe pointer) is re-aggregable."""
        from datetime import date
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self._make_customer(),
            period_start=date(2026, 5, 1), period_end=date(2026, 6, 1),
            status="pending")
        resp = self._patch({"default_currency": "eur"})
        self.assertEqual(resp.status_code, 200, resp.content)

    def test_same_currency_patch_is_noop_even_with_money(self):
        """Re-asserting the CURRENT currency is not a change — no 409."""
        from apps.billing.wallets.models import Wallet, WalletTransaction
        wallet = Wallet.objects.create(customer=self._make_customer())
        WalletTransaction.objects.create(
            wallet=wallet, transaction_type="TOP_UP",
            amount_micros=1_000_000, balance_after_micros=1_000_000)
        resp = self._patch({"default_currency": "USD"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "usd")
