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

    # --- Soft floor (#40, spec §F) ---

    def test_get_defaults_include_null_soft_floor(self):
        b = self.http.get(self._url(), **self._auth()).json()
        self.assertIsNone(b["soft_min_balance_micros"])

    def test_put_soft_floor_roundtrip(self):
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 5_000_000,
                             "soft_min_balance_micros": 2_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        b = self.http.get(self._url(), **self._auth()).json()
        self.assertEqual(b["soft_min_balance_micros"], 2_000_000)

    def test_put_negative_soft_floor_is_a_line_above_zero(self):
        # Unlike min_balance_micros, negative is allowed: soft=-2M places the
        # wind-down line at +2M (refuse new starts while money remains).
        r = self.http.put(
            self._url(),
            data=json.dumps({"soft_min_balance_micros": -2_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["soft_min_balance_micros"], -2_000_000)

    def test_put_soft_line_below_the_hard_floor_returns_422(self):
        # soft=8M would put the wind-down line (-8M) BELOW the stop line (-5M).
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 5_000_000,
                             "soft_min_balance_micros": 8_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json().get("code"), "invalid_config")

    def test_put_soft_floor_validates_against_the_tenant_default_hard_floor(self):
        # No profile min_balance in the payload: the effective hard floor is
        # the tenant default (0 here), so any soft value > 0 is below it.
        r = self.http.put(
            self._url(),
            data=json.dumps({"soft_min_balance_micros": 1}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 422)
        self.assertEqual(r.json().get("code"), "invalid_config")

    def test_put_omitting_soft_floor_clears_it(self):
        # PUT is a full replace: absent/null soft_min_balance_micros clears
        # the override (mirrors min_balance_micros).
        self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 5_000_000,
                             "soft_min_balance_micros": 2_000_000}),
            content_type="application/json", **self._auth())
        r = self.http.put(
            self._url(),
            data=json.dumps({"min_balance_micros": 5_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()["soft_min_balance_micros"])

    # --- pooled-seat disclosure + refusal (Task 3) ---

    def test_get_individual_discloses_self_as_owner(self):
        b = self.http.get(self._url(), **self._auth()).json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(self.customer.id))
        self.assertEqual(b["billing_owner_external_id"], "c1")

    def test_get_pooled_seat_returns_business_effective_profile(self):
        from apps.billing.wallets.models import CustomerBillingProfile
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz1",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat1",
            account_type="seat", parent=biz)
        CustomerBillingProfile.objects.create(customer=biz, min_balance_micros=9_000_000)

        b = self.http.get(self._url(seat), **self._auth()).json()
        self.assertTrue(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(biz.id))
        self.assertEqual(b["billing_owner_external_id"], "biz1")
        self.assertEqual(b["min_balance_micros"], 9_000_000)

    def test_get_allocated_seat_resolves_to_self(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz2",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat2",
            account_type="seat", parent=biz)

        b = self.http.get(self._url(seat), **self._auth()).json()
        self.assertFalse(b["is_pooled_seat"])
        self.assertEqual(b["billing_owner_id"], str(seat.id))

    def test_put_pooled_seat_refuses_with_422_naming_the_business(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz3",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat3",
            account_type="seat", parent=biz)

        r = self.http.put(
            self._url(seat),
            data=json.dumps({"min_balance_micros": 1_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 422)
        body = r.json()
        self.assertEqual(body["code"], "invalid_config")
        self.assertIn("biz3", body["detail"])

    def test_put_pooled_seat_does_not_silently_write_the_business_profile(self):
        from apps.billing.wallets.models import CustomerBillingProfile
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz4",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat4",
            account_type="seat", parent=biz)

        self.http.put(
            self._url(seat),
            data=json.dumps({"min_balance_micros": 1_000_000}),
            content_type="application/json", **self._auth())
        self.assertFalse(CustomerBillingProfile.objects.filter(customer=biz).exists())
        self.assertFalse(CustomerBillingProfile.objects.filter(customer=seat).exists())

    def test_put_allocated_seat_writes_its_own_profile(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz5",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat5",
            account_type="seat", parent=biz)

        r = self.http.put(
            self._url(seat),
            data=json.dumps({"min_balance_micros": 2_000_000}),
            content_type="application/json", **self._auth())
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["min_balance_micros"], 2_000_000)
