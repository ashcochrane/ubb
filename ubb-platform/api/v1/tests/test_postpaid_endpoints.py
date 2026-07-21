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
        assert r.status_code == 200
        assert r.json() == {"data": [], "next_cursor": None, "has_more": False}

    def test_usage_invoice_listed_after_create(self):
        import datetime
        from apps.billing.invoicing.models import CustomerUsageInvoice
        CustomerUsageInvoice.objects.create(tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1),
            total_billed_micros=1_000_000, currency="usd", status="pushed")
        r = self.http.get(f"/api/v1/billing/customers/{self.customer.id}/usage-invoices", **self._auth())
        assert r.status_code == 200
        b = r.json()
        rows = b["data"]
        assert b["has_more"] is False
        assert len(rows) == 1 and rows[0]["total_billed_micros"] == 1_000_000 and rows[0]["status"] == "pushed"

    def test_tenant_usage_invoices(self):
        r = self.http.get("/api/v1/billing/tenant/usage-invoices?period=2026-06", **self._auth())
        assert r.status_code == 200
        body = r.json()
        assert set(body) == {"data", "next_cursor", "has_more"}

    def test_tenant_usage_invoices_bad_period_is_a_400_problem(self):
        r = self.http.get("/api/v1/billing/tenant/usage-invoices?period=junk", **self._auth())
        assert r.status_code == 400
        assert r["Content-Type"] == "application/problem+json"
        assert r.json()["code"] == "bad_request"

    def test_postpaid_config_get_put(self):
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.status_code == 200 and r.json()["usage_line_item_group_by"] == ""
        assert r.json()["consolidate_with_subscription"] is False
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "product_id"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get("/api/v1/billing/postpaid-config", **self._auth())
        assert r.json()["usage_line_item_group_by"] == "product_id"

    def test_postpaid_config_consolidation_flag_roundtrip(self):
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "product_id",
                                           "consolidate_with_subscription": True}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200 and r.json()["consolidate_with_subscription"] is True
        # F5.5: a group_by-only PUT (flag omitted) must NOT flip the opt-in off.
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "model"}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        body = r.json()
        assert body["usage_line_item_group_by"] == "model"
        assert body["consolidate_with_subscription"] is True
        # An explicit false switches it off.
        r = self.http.put("/api/v1/billing/postpaid-config",
                          data=json.dumps({"usage_line_item_group_by": "model",
                                           "consolidate_with_subscription": False}),
                          content_type="application/json", **self._auth())
        assert r.json()["consolidate_with_subscription"] is False
