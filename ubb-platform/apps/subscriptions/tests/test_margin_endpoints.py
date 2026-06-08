import json
from unittest.mock import patch
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService


class MarginEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Heyotis", products=["metering"])  # NO subscriptions
        _, self.key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        with patch("apps.platform.events.tasks.process_single_event"):
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer, request_id="r1", idempotency_key="i1",
                provider_cost_micros=800_000, billed_cost_micros=1_000_000, provider="openai")
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer, request_id="r2", idempotency_key="i2",
                provider_cost_micros=200_000, billed_cost_micros=300_000, provider="openai")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_metering_tenant_can_access_margin(self):
        r = self.http.get("/api/v1/margin/summary", **self._auth())
        assert r.status_code == 200  # NOT gated behind subscriptions product

    def test_set_revenue_and_customer_margin(self):
        r = self.http.put(
            f"/api/v1/margin/customers/{self.customer.id}/revenue",
            data=json.dumps({"recurring_amount_micros": 500_000_000}),
            content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get(f"/api/v1/margin/{self.customer.id}", **self._auth())
        assert r.status_code == 200
        b = r.json()
        assert b["provider_cost_micros"] == 1_000_000
        assert b["usage_billed_micros"] == 1_300_000
        # metered_only mode: usage excluded from revenue; margin = subscription_revenue - provider_cost
        assert b["gross_margin_micros"] == b["subscription_revenue_micros"] - 1_000_000

    def test_by_dimension_provider(self):
        r = self.http.get("/api/v1/margin/by-dimension?provider=1", **self._auth())
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert any(row["dimension"] == "openai" and row["margin_micros"] == 300_000 for row in rows)

    def test_threshold_get_default_and_put(self):
        r = self.http.get("/api/v1/margin/threshold", **self._auth())
        assert r.status_code == 200 and r.json()["provider_cost_spike_pct"] == 25.0
        r = self.http.put("/api/v1/margin/threshold",
                          data=json.dumps({"min_margin_pct": 15.0}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get("/api/v1/margin/threshold", **self._auth())
        assert r.json()["min_margin_pct"] == 15.0

    def test_unprofitable_empty(self):
        r = self.http.get("/api/v1/margin/unprofitable", **self._auth())
        assert r.status_code == 200 and r.json()["customers"] == []
