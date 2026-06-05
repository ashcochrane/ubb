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

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        """Metering-only tenant cannot access billing endpoints."""
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)
