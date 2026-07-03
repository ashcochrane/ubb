import json
import uuid
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class CustomerBillingProfileEndpointTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _url(self, customer=None):
        cid = (customer or self.customer).id
        return f"/api/v1/billing/customers/{cid}/billing-profile"

    def test_get_defaults_when_no_profile(self):
        r = self.http.get(self._url(), **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertIsNone(b["min_balance_micros"])
        self.assertIsNone(b["topup_grant_expiry_days"])

    def test_put_then_get_roundtrip(self):
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 500_000_000, "topup_grant_expiry_days": 90}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = self.http.get(self._url(), **self._auth()).json()
        self.assertEqual(b["min_balance_micros"], 500_000_000)
        self.assertEqual(b["topup_grant_expiry_days"], 90)

    def test_put_null_clears_override(self):
        self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 500_000_000, "topup_grant_expiry_days": 90}),
            content_type="application/json", **self._auth())
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": None, "topup_grant_expiry_days": None}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = r.json()
        self.assertIsNone(b["min_balance_micros"])
        self.assertIsNone(b["topup_grant_expiry_days"])

    def test_put_negative_min_balance_returns_422(self):
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": -1}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json().get("code"), "invalid_config")

    def test_put_nonpositive_expiry_returns_422(self):
        r = self.http.put(
            self._url(),
            data=json.dumps({"topup_grant_expiry_days": 0}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json().get("code"), "invalid_config")

    def test_unknown_customer_returns_404(self):
        r = self.http.put(
            f"/api/v1/billing/customers/{uuid.uuid4()}/billing-profile",
            data=json.dumps({"min_balance_micros": 1_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 404)
