import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService
from apps.billing.wallets.models import Wallet
from apps.billing.tenant_billing.models import BillingTenantConfig
from apps.metering.pricing.models import TenantMarkup


class MeteringProductGatingTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_metering_only = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj_met, self.raw_key_met = TenantApiKey.create_key(
            self.tenant_metering_only, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_metering_only, external_id="cust_met1"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_tenant_with_metering_can_record_usage(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_met_1",
                "idempotency_key": "idem_met_1",
                "provider_cost_micros": 1_500_000,
                "metadata": {"model": "gpt-4"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["new_balance_micros"])
        self.assertIn("event_id", body)

    def test_metering_only_tenant_gets_403_on_billing_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_metering_can_get_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_met}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)


class PricingMarkupsCRUDTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_get_tenant_markup_no_markup_returns_zeros(self):
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["markup_percentage_micros"], 0)
        self.assertEqual(body["fixed_uplift_micros"], 0)

    def test_put_tenant_markup_upserts(self):
        # Create
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 20000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # GET returns set values
        resp = self.http_client.get("/api/v1/metering/pricing/markup", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 20000000)

        # PUT again with different values updates in place — still exactly one row
        resp = self.http_client.put(
            "/api/v1/metering/pricing/markup",
            data=json.dumps({"markup_percentage_micros": 30000000, "fixed_uplift_micros": 500}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 30000000)
        self.assertEqual(TenantMarkup.objects.filter(tenant=self.tenant, customer__isnull=True).count(), 1)

    def test_put_and_get_customer_markup_override(self):
        resp = self.http_client.put(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            data=json.dumps({"markup_percentage_micros": 50000000, "fixed_uplift_micros": 0}),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)

        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 50000000)

    def test_get_customer_markup_falls_back_to_tenant_default(self):
        # Set only tenant default, no customer override
        TenantMarkup.objects.create(
            tenant=self.tenant, customer=None, markup_percentage_micros=15000000, fixed_uplift_micros=0
        )
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/customers/{self.customer.id}/markup",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["markup_percentage_micros"], 15000000)


class MeteringRunEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Run Tenant",
            products=["metering"],
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        BillingTenantConfig.objects.create(
            tenant=self.tenant,
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_run_met"
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": "req_1",
            "idempotency_key": "idem_1",
            "provider_cost_micros": 1_000_000,
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(data),
            content_type="application/json",
            **self._auth(),
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_run_id_success(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        resp = self._record(run_id=str(run.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["run_id"], str(run.id))
        self.assertEqual(body["run_total_cost_micros"], 1_000_000)
        self.assertFalse(body["hard_stop"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_hard_stop_returns_429(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=10_000_000, hard_stop_balance_micros=-5_000_000,
        )
        # First event under limit
        resp = self._record(
            run_id=str(run.id),
            request_id="req_hs1",
            idempotency_key="idem_hs1",
            provider_cost_micros=9_000_000,
        )
        self.assertEqual(resp.status_code, 200)

        # Second event breaches 10M ceiling
        resp = self._record(
            run_id=str(run.id),
            request_id="req_hs2",
            idempotency_key="idem_hs2",
            provider_cost_micros=2_000_000,
        )
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertTrue(body["hard_stop"])
        self.assertEqual(body["reason"], "cost_limit_exceeded")
        self.assertEqual(body["run_id"], str(run.id))

        # Run should be killed
        run.refresh_from_db()
        self.assertEqual(run.status, "killed")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_stopped_run_returns_409(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        RunService.kill_run(run.id)

        resp = self._record(run_id=str(run.id))
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["error"], "run_not_active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_close_run_success(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000
        )
        # Record some usage first
        self._record(run_id=str(run.id))

        resp = self.http_client.post(
            f"/api/v1/metering/runs/{run.id}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["run_id"], str(run.id))
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["total_cost_micros"], 1_000_000)
        self.assertEqual(body["event_count"], 1)

    def test_close_run_not_found_returns_404(self):
        import uuid
        resp = self.http_client.post(
            f"/api/v1/metering/runs/{uuid.uuid4()}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 404)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_tenant_run_id_is_404_and_not_mutated(self, mock_process):
        other_tenant = Tenant.objects.create(name="Victim", products=["metering"])
        other_customer = Customer.objects.create(tenant=other_tenant, external_id="victim_c")
        victim_run = RunService.create_run(other_tenant, other_customer, balance_snapshot_micros=20_000_000)
        resp = self._record(run_id=str(victim_run.id), request_id="req_idor1", idempotency_key="idem_idor1")
        self.assertEqual(resp.status_code, 404)
        victim_run.refresh_from_db()
        self.assertEqual(victim_run.total_cost_micros, 0)
        self.assertEqual(victim_run.event_count, 0)
        self.assertEqual(victim_run.status, "active")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_cross_customer_same_tenant_run_id_is_404(self, mock_process):
        cust_b = Customer.objects.create(tenant=self.tenant, external_id="cust_b")
        run_b = RunService.create_run(self.tenant, cust_b, balance_snapshot_micros=20_000_000)
        resp = self._record(run_id=str(run_b.id), request_id="req_idor2", idempotency_key="idem_idor2")
        self.assertEqual(resp.status_code, 404)
        run_b.refresh_from_db()
        self.assertEqual(run_b.total_cost_micros, 0)
        self.assertEqual(run_b.event_count, 0)
        self.assertEqual(run_b.status, "active")


class MeteringUsageAnalyticsEndpointTest(TestCase):
    def setUp(self):
        from apps.metering.usage.services.usage_service import UsageService

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Analytics Tenant", products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_analytics"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        for i in range(3):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id=f"req_analytics_{i}",
                idempotency_key=f"idem_analytics_{i}",
                provider_cost_micros=1_000_000,
            )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_usage_analytics(self):
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["total_events"], 3)
        self.assertEqual(body["total_billed_cost_micros"], 3_000_000)

    def test_usage_analytics_dimensions(self):
        from apps.metering.usage.services.usage_service import UsageService
        from apps.metering.pricing.models import TenantMarkup
        # a tenant-default markup so billed > provider (margin is non-zero)
        TenantMarkup.objects.create(tenant=self.tenant, customer=None, markup_percentage_micros=20_000_000)  # 20%
        other = Customer.objects.create(tenant=self.tenant, external_id="c_other")
        UsageService.record_usage(
            tenant=self.tenant, customer=other,
            request_id="req_dim_1", idempotency_key="idem_dim_1",
            provider_cost_micros=2_000_000, tags={"model": "gpt-4"}, product_id="chat",
        )
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage?tag_key=model", **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("usage_markup_margin_micros", body)
        self.assertEqual(
            body["usage_markup_margin_micros"],
            body["total_billed_cost_micros"] - body["total_provider_cost_micros"],
        )
        self.assertTrue(body["by_customer"])      # non-empty
        self.assertTrue(body["by_product"])       # non-empty (the product_id="chat" event)
        self.assertTrue(body["by_tag"])           # non-empty (tag_key=model)
        product_ids = {row["product_id"] for row in body["by_product"]}
        self.assertIn("chat", product_ids)
        tag_values = {row["tag_value"] for row in body["by_tag"]}
        self.assertIn("gpt-4", tag_values)

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        """Metering-only tenant cannot access billing endpoints."""
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_usage_analytics_multi_dimension_breakdown(self):
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme_multi")
        UsageEvent.objects.create(
            tenant=self.tenant, customer=c, request_id="r_md1", idempotency_key="i_md1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, product_id="search",
            service_id="svcA", agent_id="ag1", tags={"region": "us"},
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}"
            "&dimensions=product_id&dimensions=service_id&dimensions=tag:region",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200)
        b = resp.json()["breakdowns"]
        self.assertTrue(
            any(r["dimension"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in b["product_id"]),
            f"product_id rows: {b.get('product_id')}",
        )
        self.assertTrue(
            any(r["dimension"] == "svcA" and r["total_provider_cost_micros"] == 300_000
                for r in b["service_id"]),
            f"service_id rows: {b.get('service_id')}",
        )
        self.assertTrue(
            any(r["dimension"] == "us" and r["total_provider_cost_micros"] == 300_000
                for r in b["tag:region"]),
            f"tag:region rows: {b.get('tag:region')}",
        )

    def test_usage_analytics_rejects_unknown_dimension(self):
        resp = self.http_client.get(
            "/api/v1/metering/analytics/usage?dimensions=ssn",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 422)

    def test_usage_analytics_breakdowns_include_provider_cost(self):
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        UsageEvent.objects.create(
            tenant=self.tenant, customer=c, request_id="r1", idempotency_key="i1",
            provider_cost_micros=300_000, billed_cost_micros=500_000, product_id="search",
        )
        resp = self.http_client.get(
            f"/api/v1/metering/analytics/usage?customer_id={c.id}",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(
            any(r["customer__external_id"] == "acme" and r["total_provider_cost_micros"] == 300_000
                for r in body["by_customer"]),
            f"by_customer rows: {body['by_customer']}",
        )
        self.assertTrue(
            any(r["product_id"] == "search" and r["total_provider_cost_micros"] == 300_000
                for r in body["by_product"]),
            f"by_product rows: {body['by_product']}",
        )


class RateCardValidationTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="RateCard Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_create_rate_card_rejects_invalid_card_type(self):
        resp = self.client.post("/api/v1/metering/pricing/rate-cards",
            data=json.dumps({"card_type": "costs", "metric_name": "input_tokens"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422

    def test_create_rate_card_rejects_invalid_pricing_model(self):
        resp = self.client.post("/api/v1/metering/pricing/rate-cards",
            data=json.dumps({"card_type": "cost", "metric_name": "input_tokens", "pricing_model": "graduated"}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422

    def test_record_usage_surfaces_uncosted_metrics(self):
        # A metric with NO matching cost card -> the response lists it as uncosted.
        c = Customer.objects.create(tenant=self.tenant, external_id="acme2")
        resp = self.client.post("/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(c.id), "request_id": "r9", "idempotency_key": "i9",
                  "usage_metrics": {"unknown_metric": 100}}),
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        assert "unknown_metric" in resp.json().get("uncosted_metrics", [])

    def test_rate_card_update_keeps_lineage_and_versions_history(self):
        # create a cost card
        r1 = self.client.post("/api/v1/metering/pricing/rate-cards",
            data={"card_type": "cost", "metric_name": "tokens", "pricing_model": "per_unit",
                  "rate_per_unit_micros": 2, "unit_quantity": 1},
            content_type="application/json", HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert r1.status_code in (200, 201)
        card1 = r1.json(); cid = card1["id"]; lineage = card1["lineage_id"]
        # update the rate
        r2 = self.client.put(f"/api/v1/metering/pricing/rate-cards/{cid}",
            data={"rate_per_unit_micros": 9}, content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert r2.status_code == 200
        card2 = r2.json()
        assert card2["lineage_id"] == lineage  # same lineage
        assert card2["id"] != cid              # new version row
        # history: both versions, newest first
        h = self.client.get(f"/api/v1/metering/pricing/rate-cards/{lineage}/history",
                            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()
        assert len(h) == 2
        assert h[0]["rate_per_unit_micros"] == 9 and h[1]["rate_per_unit_micros"] == 2
        # old version has valid_to set; new version valid_to is null
        assert h[1]["valid_to"] is not None and h[0]["valid_to"] is None


class RateCardBatchCreateTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Batch RateCard Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_bulk_create_rate_cards(self):
        body = {"cards": [
            {"card_type": "cost", "metric_name": "tokens", "pricing_model": "per_unit",
             "rate_per_unit_micros": 2, "unit_quantity": 1},
            {"card_type": "cost", "metric_name": "images", "pricing_model": "flat", "fixed_micros": 500},
        ]}
        resp = self.client.post("/api/v1/metering/pricing/rate-cards/batch",
            data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code in (200, 201)
        assert resp.json()["count"] == 2
        from apps.metering.pricing.models import RateCard
        assert RateCard.objects.filter(tenant=self.tenant).count() == 2

    def test_bulk_create_is_atomic_on_invalid(self):
        from apps.metering.pricing.models import RateCard
        before = RateCard.objects.filter(tenant=self.tenant).count()
        body = {"cards": [
            {"card_type": "cost", "metric_name": "ok", "pricing_model": "per_unit",
             "rate_per_unit_micros": 1, "unit_quantity": 1},
            {"card_type": "BOGUS", "metric_name": "bad"},
        ]}
        resp = self.client.post("/api/v1/metering/pricing/rate-cards/batch",
            data=json.dumps(body), content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422
        assert RateCard.objects.filter(tenant=self.tenant).count() == before  # zero created


class UsageTimeseriesEndpointTest(TestCase):
    def setUp(self):
        self.client = Client()
        self.tenant = Tenant.objects.create(name="Timeseries Tenant", products=["metering"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def test_usage_timeseries_daily_buckets(self):
        import datetime
        from django.utils import timezone
        from apps.platform.customers.models import Customer
        from apps.metering.usage.models import UsageEvent
        c = Customer.objects.create(tenant=self.tenant, external_id="acme")
        for i, day in enumerate([1, 2, 3]):
            e = UsageEvent.objects.create(tenant=self.tenant, customer=c, request_id=f"r{i}",
                idempotency_key=f"i{i}", provider_cost_micros=100_000, billed_cost_micros=150_000)
            UsageEvent.objects.filter(id=e.id).update(
                effective_at=timezone.make_aware(timezone.datetime(2026, 6, day, 12, 0)))
        resp = self.client.get(
            "/api/v1/metering/analytics/usage/timeseries?customer_id=%s&granularity=day&start_date=2026-06-01&end_date=2026-07-01" % c.id,
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 200
        series = resp.json()["series"]
        assert len(series) == 3
        assert sum(b["provider_cost_micros"] for b in series) == 300_000

    def test_usage_timeseries_invalid_granularity_422(self):
        resp = self.client.get("/api/v1/metering/analytics/usage/timeseries?granularity=year",
                               HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert resp.status_code == 422
