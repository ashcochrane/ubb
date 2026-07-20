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

    # --- PATCH: spend-safety knobs (one-rule #37: the run-era
    # run_cost_limit_micros / hard_stop_balance_micros / max_cost_per_task_micros
    # knobs are retired; the per-task defaults are
    # default_task_provider_cost_limit_micros (RiskConfig-backed) and
    # default_task_floor_snapshot_micros (BillingTenantConfig-backed)) ---

    def test_get_config_includes_task_default_knobs(self):
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertEqual(body["min_balance_micros"], 0)
        self.assertIsNone(body["default_task_provider_cost_limit_micros"])
        self.assertIsNone(body["default_task_floor_snapshot_micros"])

    def test_patch_sets_min_balance_and_task_defaults(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({
                "min_balance_micros": 5_000_000,
                "default_task_provider_cost_limit_micros": 50_000_000,
                "default_task_floor_snapshot_micros": -5_000_000,
            }),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.gating.models import RiskConfig
        rc = RiskConfig.objects.get(tenant=self.tenant)  # created lazily
        self.assertEqual(rc.default_task_provider_cost_limit_micros, 50_000_000)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        bc = BillingTenantConfig.objects.get(tenant=self.tenant)
        # #52: the hard floor lands on BillingTenantConfig, like its siblings.
        self.assertEqual(bc.min_balance_micros, 5_000_000)
        self.assertEqual(bc.default_task_floor_snapshot_micros, -5_000_000)
        body = response.json()
        self.assertEqual(body["min_balance_micros"], 5_000_000)
        self.assertEqual(body["default_task_provider_cost_limit_micros"], 50_000_000)
        self.assertEqual(body["default_task_floor_snapshot_micros"], -5_000_000)

    def test_patch_task_default_limit_zero_or_negative_returns_422(self):
        for bad in (0, -1):
            response = self.http_client.patch(
                "/api/v1/tenant/config",
                data=json.dumps({"default_task_provider_cost_limit_micros": bad}),
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

    def test_patch_min_balance_drives_floor_resolution(self):
        # #52 acceptance: the hard floor set through tenant-config must be the
        # one get_customer_min_balance resolves for a customer with no
        # per-customer override — i.e. the floor enforcement actually uses.
        from apps.billing.queries import get_customer_min_balance
        customer = Customer.objects.create(tenant=self.tenant, external_id="floor-c1")
        self.assertEqual(get_customer_min_balance(customer.id, self.tenant.id), 0)
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"min_balance_micros": 5_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            get_customer_min_balance(customer.id, self.tenant.id), 5_000_000)

    def test_get_config_min_balance_reads_billing_config_row(self):
        # #52: the GET echoes the row resolution reads, not a dead column.
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(self.tenant.id)
        bc.min_balance_micros = 9_000_000
        bc.save(update_fields=["min_balance_micros"])
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertEqual(body["min_balance_micros"], 9_000_000)

    def test_patch_both_floors_validates_soft_against_incoming_hard(self):
        # Stored hard is 0, which would reject a positive soft; the INCOMING
        # hard (5M) allows it — one PATCH must validate against the value it
        # is itself setting (mirrors the billing-profile PUT's effective_hard).
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"min_balance_micros": 5_000_000,
                             "soft_min_balance_micros": 2_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        bc = BillingTenantConfig.objects.get(tenant=self.tenant)
        self.assertEqual(bc.min_balance_micros, 5_000_000)
        self.assertEqual(bc.soft_min_balance_micros, 2_000_000)

    def test_patch_both_floors_soft_exceeding_incoming_hard_returns_422(self):
        # Stored hard (10M) would allow soft 7M — but the PATCH lowers hard to
        # 5M in the same request, so soft must validate against the incoming
        # value. Nothing may be partially applied on the 422.
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(self.tenant.id)
        bc.min_balance_micros = 10_000_000
        bc.save(update_fields=["min_balance_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"min_balance_micros": 5_000_000,
                             "soft_min_balance_micros": 7_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json().get("code"), "invalid_config")
        bc.refresh_from_db()
        self.assertEqual(bc.min_balance_micros, 10_000_000)
        self.assertIsNone(bc.soft_min_balance_micros)

    def test_patch_null_clears_task_default_limit(self):
        from apps.billing.gating.models import RiskConfig
        RiskConfig.objects.create(
            tenant=self.tenant, default_task_provider_cost_limit_micros=50_000_000)
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"default_task_provider_cost_limit_micros": None}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        rc = RiskConfig.objects.get(tenant=self.tenant)
        self.assertIsNone(rc.default_task_provider_cost_limit_micros)
        self.assertIsNone(response.json()["default_task_provider_cost_limit_micros"])

    def test_patch_task_default_floor_lands_on_billing_config(self):
        # Negative is ALLOWED (it is a wallet-balance line, e.g. an overdraft
        # cushion), unlike the strictly-positive COGS limit.
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"default_task_floor_snapshot_micros": -5_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        bc = BillingTenantConfig.objects.get(tenant=self.tenant)
        self.assertEqual(bc.default_task_floor_snapshot_micros, -5_000_000)
        self.assertEqual(response.json()["default_task_floor_snapshot_micros"], -5_000_000)

    def test_patch_null_clears_task_default_floor(self):
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(self.tenant.id)
        bc.default_task_floor_snapshot_micros = -5_000_000
        bc.save(update_fields=["default_task_floor_snapshot_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"default_task_floor_snapshot_micros": None}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        bc.refresh_from_db()
        self.assertIsNone(bc.default_task_floor_snapshot_micros)
        self.assertIsNone(response.json()["default_task_floor_snapshot_micros"])

    def test_get_config_includes_null_soft_floor_default(self):
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertIsNone(body["soft_min_balance_micros"])

    def test_patch_soft_floor_lands_on_billing_config(self):
        # Negative is allowed (a wind-down line above zero); the value lands
        # on BillingTenantConfig — the row get_customer_soft_min_balance reads.
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"soft_min_balance_micros": -2_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        bc = BillingTenantConfig.objects.get(tenant=self.tenant)
        self.assertEqual(bc.soft_min_balance_micros, -2_000_000)
        self.assertEqual(response.json()["soft_min_balance_micros"], -2_000_000)

    def test_patch_soft_line_below_the_hard_floor_returns_422(self):
        # The tenant-default hard floor lives on BillingTenantConfig (default
        # 0): a soft value above it puts the wind-down line below the stop line.
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"soft_min_balance_micros": 1_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json().get("code"), "invalid_config")

    def test_patch_null_clears_soft_floor(self):
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(self.tenant.id)
        bc.soft_min_balance_micros = -2_000_000
        bc.save(update_fields=["soft_min_balance_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"soft_min_balance_micros": None}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        bc.refresh_from_db()
        self.assertIsNone(bc.soft_min_balance_micros)
        self.assertIsNone(response.json()["soft_min_balance_micros"])

    def test_patch_omitting_soft_floor_leaves_it_unchanged(self):
        from apps.billing.queries import get_billing_config
        bc = get_billing_config(self.tenant.id)
        bc.soft_min_balance_micros = -2_000_000
        bc.save(update_fields=["soft_min_balance_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "meter_only"}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        bc.refresh_from_db()
        self.assertEqual(bc.soft_min_balance_micros, -2_000_000)

    def test_patch_omitting_knobs_leaves_them_unchanged(self):
        from apps.billing.gating.models import RiskConfig
        from apps.billing.queries import get_billing_config
        RiskConfig.objects.create(
            tenant=self.tenant, default_task_provider_cost_limit_micros=42_000_000)
        bc = get_billing_config(self.tenant.id)
        bc.min_balance_micros = 7_000_000
        bc.default_task_floor_snapshot_micros = -3_000_000
        bc.save(update_fields=["min_balance_micros",
                               "default_task_floor_snapshot_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "meter_only"}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        rc = RiskConfig.objects.get(tenant=self.tenant)
        self.assertEqual(rc.default_task_provider_cost_limit_micros, 42_000_000)
        bc.refresh_from_db()
        self.assertEqual(bc.min_balance_micros, 7_000_000)
        self.assertEqual(bc.default_task_floor_snapshot_micros, -3_000_000)


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
        from apps.metering.pricing.models import Rate
        Rate.objects.create(
            tenant=self.tenant, card_type="cost", metric_name="tokens",
            pricing_model="per_unit", rate_per_unit_micros=10,
            currency=self.tenant.default_currency)
        self._assert_locked()

    def test_retired_rate_card_does_not_lock(self):
        from django.utils import timezone
        from apps.metering.pricing.models import Rate
        Rate.objects.create(
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
