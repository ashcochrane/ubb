import json
from datetime import date
from django.test import TestCase, Client
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from core.vocabulary import TENANT_PRODUCT_VALUES
from apps.platform.tenants.tests._rails import RailActivated


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
            total_billed_cost_micros=50_000_000_000,
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
        self.assertEqual(body["data"][0]["total_billed_cost_micros"], 50_000_000_000)

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
            total_billed_cost_micros=50_000_000_000,
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


class TenantConfigEndpointTest(RailActivated, TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="ConfigTest",
            stripe_connected_account_id="acct_cfg",
            platform_fee_percentage=1.00,
            products=["metering"],
            billing_mode="external",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="cfg-test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    # --- GET ---

    def test_get_config_returns_200_with_expected_keys(self):
        response = self.http_client.get("/api/v1/tenant/config", **self._auth())
        self.assertEqual(response.status_code, 200)
        body = response.json()
        for key in ("billing_mode", "products",
                    "stripe_connected_account_id", "is_active"):
            self.assertIn(key, body, f"missing key: {key}")
        self.assertEqual(body["billing_mode"], "external")
        self.assertIn("metering", body["products"])
        # The strict cost-coverage setting left this response in #321 — the
        # wall it armed is gone, so there is nothing here to read back.
        self.assertNotIn("require_cost_card_coverage", body)

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

    # --- PATCH: a product the registry does not declare → 422 ---

    def test_patch_unknown_product_returns_422(self):
        """The refusal the advertised enum documents (#240).

        `TenantConfigIn.products` carries `x-ubb-concept: tenant_product`, so
        the committed contract enumerates the three declared values. That is
        the DOCUMENT narrowing: `json_schema_extra` renders an enum and does
        not validate, and typing the field `Literal[...]` is forbidden — the
        registry owns the set and the platform may not keep a second copy of
        it. So this pins the two halves agreeing: an unknown product is
        refused, by the model that imports the same set the export advertises.
        """
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"products": ["metering", "clairvoyance"]}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 422)
        body = response.json()
        self.assertEqual(body.get("code"), "invalid_config")
        self.assertIn("clairvoyance", body.get("detail", ""))

    def test_the_contract_advertises_exactly_what_that_refusal_enforces(self):
        """The other direction, and the reason the pin above is not enough.

        A contract that enumerated four values while the model accepted three
        would leave every request above still refused and the published
        document still lying. Read off the committed bytes rather than the
        runtime document — the committed one is the contract (ADR-002), and it
        is the only one carrying the metadata.
        """
        import json as _json
        from api.v1.openapi_export import COMMITTED_SPEC_PATH

        document = _json.loads(COMMITTED_SPEC_PATH.read_text(encoding="utf-8"))
        schemas = document["components"]["schemas"]
        advertised = set(
            schemas["TenantConfigOut"]["properties"]["products"]["items"]["enum"])
        self.assertEqual(advertised, set(TENANT_PRODUCT_VALUES))

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
    # knobs are retired; the two default ceilings for work with no declared
    # kind are default_task_cogs_ceiling_micros and its contained-work twin,
    # on the tenant row since #453. The
    # per-task floor snapshot (BillingTenantConfig-backed) that used to sit
    # alongside it was itself deleted — billing-surface-correctness plan,
    # task 1: an independent third floor that never read the customer's real
    # floor and could fire on a customer who just topped up.) ---

    def test_get_config_includes_task_default_knobs(self):
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertEqual(body["min_balance_micros"], 0)
        self.assertIsNone(body["default_task_cogs_ceiling_micros"])
        self.assertIsNone(body["default_subtask_cogs_ceiling_micros"])

    def test_patch_sets_min_balance_and_task_defaults(self):
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({
                "min_balance_micros": 5_000_000,
                "default_task_cogs_ceiling_micros": 50_000_000,
            }),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_task_cogs_ceiling_micros, 50_000_000)
        from apps.billing.tenant_billing.models import BillingTenantConfig
        bc = BillingTenantConfig.objects.get(tenant=self.tenant)
        # #52: the hard floor lands on BillingTenantConfig, like its siblings.
        self.assertEqual(bc.min_balance_micros, 5_000_000)
        body = response.json()
        self.assertEqual(body["min_balance_micros"], 5_000_000)
        self.assertEqual(body["default_task_cogs_ceiling_micros"], 50_000_000)

    def test_patch_task_default_limit_zero_or_negative_returns_422(self):
        for rung in ("default_task_cogs_ceiling_micros",
                     "default_subtask_cogs_ceiling_micros"):
            for bad in (0, -1):
                response = self.http_client.patch(
                    "/api/v1/tenant/config",
                    data=json.dumps({rung: bad}),
                    content_type="application/json", **self._auth(),
                )
                self.assertEqual(response.status_code, 422,
                                 f"{rung}={bad} should be rejected")
                self.assertEqual(response.json().get("code"), "invalid_config")
                self.assertIn(rung, response.json()["detail"])

    def test_patch_sets_the_contained_work_default_on_its_own(self):
        """Both rungs are on the wire (#453; only the top-level one was), and
        each moves alone: setting the contained-work default leaves the
        top-level one exactly where it stood."""
        self.tenant.default_task_cogs_ceiling_micros = 40_000_000
        self.tenant.save(update_fields=["default_task_cogs_ceiling_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"default_subtask_cogs_ceiling_micros": 4_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["default_subtask_cogs_ceiling_micros"], 4_000_000)
        self.assertEqual(body["default_task_cogs_ceiling_micros"], 40_000_000)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_subtask_cogs_ceiling_micros, 4_000_000)
        self.assertEqual(self.tenant.default_task_cogs_ceiling_micros, 40_000_000)

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

    def test_patch_lowering_hard_below_stored_soft_allowed_resolver_clamps(self):
        # Lowering the hard floor alone is NOT validated against a stored soft
        # floor — write-time validation goes stale across levels by design, so
        # the resolver, not the writer, guarantees soft <= hard (queries.py).
        # This pins that posture: the write succeeds, the stored soft stays,
        # and the effective soft clamps to the new hard.
        from apps.billing.queries import (get_billing_config,
                                          get_customer_soft_min_balance)
        bc = get_billing_config(self.tenant.id)
        bc.min_balance_micros = 10_000_000
        bc.soft_min_balance_micros = 7_000_000
        bc.save(update_fields=["min_balance_micros", "soft_min_balance_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"min_balance_micros": 5_000_000}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        bc.refresh_from_db()
        self.assertEqual(bc.min_balance_micros, 5_000_000)
        self.assertEqual(bc.soft_min_balance_micros, 7_000_000)  # stored as-is
        customer = Customer.objects.create(tenant=self.tenant, external_id="clamp-c1")
        self.assertEqual(
            get_customer_soft_min_balance(customer.id, self.tenant.id),
            5_000_000)  # clamped to the new hard at read time

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
        self.tenant.default_task_cogs_ceiling_micros = 50_000_000
        self.tenant.save(update_fields=["default_task_cogs_ceiling_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"default_task_cogs_ceiling_micros": None}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.default_task_cogs_ceiling_micros)
        self.assertIsNone(response.json()["default_task_cogs_ceiling_micros"])

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
            data=json.dumps({"billing_mode": "external"}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        bc.refresh_from_db()
        self.assertEqual(bc.soft_min_balance_micros, -2_000_000)

    def test_patch_omitting_knobs_leaves_them_unchanged(self):
        from apps.billing.queries import get_billing_config
        self.tenant.default_task_cogs_ceiling_micros = 42_000_000
        self.tenant.save(update_fields=["default_task_cogs_ceiling_micros"])
        bc = get_billing_config(self.tenant.id)
        bc.min_balance_micros = 7_000_000
        bc.save(update_fields=["min_balance_micros"])
        response = self.http_client.patch(
            "/api/v1/tenant/config",
            data=json.dumps({"billing_mode": "external"}),
            content_type="application/json", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_task_cogs_ceiling_micros, 42_000_000)
        bc.refresh_from_db()
        self.assertEqual(bc.min_balance_micros, 7_000_000)

    # --- admission control's bound (#462): on the wire for the first time ---

    def _patch(self, body):
        return self.http_client.patch(
            "/api/v1/tenant/config", data=json.dumps(body),
            content_type="application/json", **self._auth())

    def test_get_config_reads_the_admission_bound_null_by_default(self):
        body = self.http_client.get("/api/v1/tenant/config", **self._auth()).json()
        self.assertIn("max_task_starts_per_minute", body)
        self.assertIsNone(body["max_task_starts_per_minute"])

    def test_patch_sets_the_admission_bound_on_the_tenant_row(self):
        response = self._patch({"max_task_starts_per_minute": 30})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["max_task_starts_per_minute"], 30)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_task_starts_per_minute, 30)

    def test_patch_null_clears_the_admission_bound(self):
        self.tenant.max_task_starts_per_minute = 30
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        response = self._patch({"max_task_starts_per_minute": None})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["max_task_starts_per_minute"])
        self.tenant.refresh_from_db()
        self.assertIsNone(self.tenant.max_task_starts_per_minute)

    def test_patch_admission_bound_zero_or_negative_returns_422(self):
        """A bound of zero is not a rate but a refusal of every start;
        null is the one spelling of no bound."""
        for bad in (0, -1):
            response = self._patch({"max_task_starts_per_minute": bad})
            self.assertEqual(response.status_code, 422, bad)
            self.assertEqual(response.json()["code"], "invalid_config")
            self.assertIn("max_task_starts_per_minute", response.json()["detail"])
            self.assertIn("no bound", response.json()["detail"])

    def test_patch_omitting_the_admission_bound_leaves_it_unchanged(self):
        self.tenant.max_task_starts_per_minute = 30
        self.tenant.save(update_fields=["max_task_starts_per_minute"])
        response = self._patch({"billing_mode": "external"})
        self.assertEqual(response.status_code, 200, response.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.max_task_starts_per_minute, 30)


class TenantConfigCurrencyTest(TestCase):
    """UBB v1 is USD-only at the tenant door (ADR-0023, #555).

    `default_currency` admits US dollars in any spelling and refuses every
    other code with `unsupported_currency`, through the one policy. There is no
    lock any more: a tenant cannot leave USD by any path, so "money exists" has
    nothing left to guard, and `currency_locked` retired (the owner's ruling 4).

    Every refusal sends its foreign code EXPLICITLY and reads the stored row
    back: the column defaults to `usd`, so a test that only watched the status
    could be passed by a write that never happened.
    """

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

    def _assert_refused(self, offered):
        resp = self._patch({"default_currency": offered})
        self.assertEqual(resp.status_code, 422, resp.content)
        body = resp.json()
        self.assertEqual(body["code"], "unsupported_currency")
        self.assertIn(offered, body["detail"])
        self.assertIn("US dollars only", body["detail"])
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "usd")

    def test_us_dollars_in_any_spelling_are_stored_lowercase(self):
        for spelled in ("usd", "USD"):
            with self.subTest(spelled=spelled):
                resp = self._patch({"default_currency": spelled})
                self.assertEqual(resp.status_code, 200, resp.content)
                self.assertEqual(resp.json()["default_currency"], "usd")
                self.tenant.refresh_from_db()
                self.assertEqual(self.tenant.default_currency, "usd")

    def test_a_currency_ubb_can_represent_is_still_refused(self):
        """`eur` and `gbp` are in `core.money`'s minor-unit table — that is
        representation, not admission (amendment A)."""
        for offered in ("eur", "GBP"):
            with self.subTest(offered=offered):
                self._assert_refused(offered)

    def test_a_currency_ubb_cannot_represent_is_refused_the_same_way(self):
        self._assert_refused("jpy")

    def test_a_refused_patch_changes_nothing_else(self):
        """The refusal is decided before any write, so a field sent beside the
        foreign code is not half-applied."""
        resp = self._patch({"default_currency": "eur",
                            "enforcement_mode": "enforcing"})
        self.assertEqual(resp.status_code, 422, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.enforcement_mode, "off")

    def test_holding_money_changes_neither_answer(self):
        """THE RETIRED LOCK'S OWN CASES, answered by the policy alone. With
        money on record a foreign code is the same 422 — never the old 409
        `currency_locked` — and re-asserting US dollars is the same 200."""
        from apps.billing.wallets.models import Wallet, WalletTransaction
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        wallet = Wallet.objects.create(customer=customer)
        WalletTransaction.objects.create(
            wallet=wallet, transaction_type="TOP_UP",
            amount_micros=1_000_000, balance_after_micros=1_000_000)
        a_plan(tenant=self.tenant, key="pro", name="Pro",
               access_fee_micros=10_000_000, stripe_access_price_id="price_123")

        self._assert_refused("eur")
        resp = self._patch({"default_currency": "USD"})
        self.assertEqual(resp.status_code, 200, resp.content)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.default_currency, "usd")
