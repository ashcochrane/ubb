import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class PostpaidEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_list_customer_usage_invoices_empty(self):
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/usage-invoices", **self._auth())
        assert r.status_code == 200 and r.json() == []

    def test_usage_invoice_listed_after_create(self):
        import datetime
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1),
            total_billed_micros=1_000_000, currency="usd", status="pushed")
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/usage-invoices", **self._auth())
        assert r.status_code == 200
        b = r.json()
        assert len(b) == 1 and b[0]["total_billed_micros"] == 1_000_000 and b[0]["status"] == "pushed"

    def test_tenant_usage_invoices(self):
        r = self.http.get("/api/v1/billing/tenant/usage-invoices?period=2026-06", **self._auth())
        assert r.status_code == 200 and "invoices" in r.json()

    def test_postpaid_config_get_put(self):
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.status_code == 200 and r.json()["usage_line_item_group_by"] == ""
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "product_id"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.json()["usage_line_item_group_by"] == "product_id"
