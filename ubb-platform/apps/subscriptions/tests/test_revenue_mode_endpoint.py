import json
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class RevenueModeEndpointTest(TestCase):
    def setUp(self):
        self.http = Client()
        # Tenant with both products, default billing_mode is "meter_only"
        self.tenant = Tenant.objects.create(
            name="BillingCo", products=["metering", "billing"], billing_mode="postpaid")
        _, self.key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="rc1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _url(self, customer_id):
        return f"/api/v1/margin/customers/{customer_id}/revenue-mode"

    def test_put_valid_mode_and_get(self):
        """PUT a valid revenue_mode → 200 with resolved; subsequent GET reflects it."""
        r = self.http.put(
            self._url(self.customer.id),
            data=json.dumps({"revenue_mode": "metered_only"}),
            content_type="application/json",
            **self._auth(),
        )
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["resolved"] == "metered_only", body

        # GET should now return the stored mode
        r2 = self.http.get(self._url(self.customer.id), **self._auth())
        assert r2.status_code == 200, r2.content
        body2 = r2.json()
        assert body2["revenue_mode"] == "metered_only", body2

    def test_put_invalid_mode_returns_422(self):
        """PUT with an unrecognised revenue_mode → 422 problem+json (#78 dialect)."""
        r = self.http.put(
            self._url(self.customer.id),
            data=json.dumps({"revenue_mode": "bogus"}),
            content_type="application/json",
            **self._auth(),
        )
        assert r.status_code == 422, r.content
        assert r["Content-Type"] == "application/problem+json"
        body = r.json()
        assert body["code"] == "invalid_revenue_mode", body
        assert body["status"] == 422, body
        assert "bogus" in body["detail"], body

    def test_meter_only_tenant_default_derivation(self):
        """A meter_only tenant's customer with no override resolves to metered_only."""
        meter_tenant = Tenant.objects.create(
            name="MeterOnly", products=["metering"], billing_mode="meter_only")
        _, meter_key = TenantApiKey.create_key(meter_tenant, label="meter-test")
        customer = Customer.objects.create(
            tenant=meter_tenant, external_id="mc1", revenue_mode="")

        r = self.http.get(
            f"/api/v1/margin/customers/{customer.id}/revenue-mode",
            **{"HTTP_AUTHORIZATION": f"Bearer {meter_key}"},
        )
        assert r.status_code == 200, r.content
        body = r.json()
        assert body["resolved"] == "metered_only", body
