import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class BudgetEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_put_get_customer_budget(self):
        r = self.http.put(f"/api/v1/billing/customers/{self.customer.id}/budget",
                          data=json.dumps({"cap_micros": 1_000_000, "enforce_mode": "enforcing"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/budget", **self._auth())
        b = r.json()
        assert b["cap_micros"] == 1_000_000 and b["enforce_mode"] == "enforcing"
        assert b["alert_levels"] == [50, 80, 100, 110]

    def test_tenant_default_budget(self):
        r = self.http.put("/api/v1/billing/budget",
                          data=json.dumps({"cap_micros": 500}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200 and r.json()["cap_micros"] == 500

    def test_budget_status(self):
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/budget/status", **self._auth())
        assert r.status_code == 200
        b = r.json()
        assert "spend_micros" in b and "cap_micros" in b and "pct" in b and "period" in b
