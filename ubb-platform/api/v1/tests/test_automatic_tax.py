"""automatic_tax opt-in (F5.3) — config flag, Stripe Tax preflight, subscribe surfacing."""
import json
from unittest.mock import MagicMock, patch

import stripe
from django.test import TestCase, Client

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


class AutomaticTaxConfigTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="TaxCfg", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _patch_config(self, body):
        return self.http_client.patch(
            "/api/v1/tenant/config", data=json.dumps(body),
            content_type="application/json", **self._auth())

    def _make_charge_ready(self):
        self.tenant.stripe_connected_account_id = "acct_tax"
        self.tenant.charges_enabled = True
        self.tenant.save()

    def test_get_config_exposes_flag(self):
        resp = self.http_client.get("/api/v1/tenant/config", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["automatic_tax_enabled"], False)

    def test_enable_without_stripe_tax_active_returns_422_with_message(self):
        self._make_charge_ready()
        with patch("stripe.tax.Settings.retrieve",
                   return_value=MagicMock(status="pending")) as retrieve:
            resp = self._patch_config({"automatic_tax_enabled": True})
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["code"], "stripe_tax_not_active")
        self.assertIn("pending", body["error"])
        retrieve.assert_called_once()
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.automatic_tax_enabled)

    def test_enable_when_stripe_rejects_surfaces_stripes_message(self):
        self._make_charge_ready()
        with patch("stripe.tax.Settings.retrieve",
                   side_effect=stripe.error.InvalidRequestError(
                       "You must enable Stripe Tax first", None)):
            resp = self._patch_config({"automatic_tax_enabled": True})
        self.assertEqual(resp.status_code, 422)
        body = resp.json()
        self.assertEqual(body["code"], "stripe_tax_not_active")
        self.assertIn("You must enable Stripe Tax first", body["error"])
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.automatic_tax_enabled)

    def test_enable_when_stripe_tax_active_succeeds(self):
        self._make_charge_ready()
        with patch("stripe.tax.Settings.retrieve",
                   return_value=MagicMock(status="active")):
            resp = self._patch_config({"automatic_tax_enabled": True})
        self.assertEqual(resp.status_code, 200)
        self.assertIs(resp.json()["automatic_tax_enabled"], True)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.automatic_tax_enabled)

    def test_enable_when_not_charge_ready_allows_flag_without_preflight(self):
        # Not charge-ready: the flag only matters at charge time, and every
        # charge site is itself gated on charge-ready — no preflight possible.
        with patch("stripe.tax.Settings.retrieve") as retrieve:
            resp = self._patch_config({"automatic_tax_enabled": True})
        self.assertEqual(resp.status_code, 200)
        retrieve.assert_not_called()
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.automatic_tax_enabled)

    def test_disable_never_preflights(self):
        self._make_charge_ready()
        self.tenant.automatic_tax_enabled = True
        self.tenant.save()
        with patch("stripe.tax.Settings.retrieve") as retrieve:
            resp = self._patch_config({"automatic_tax_enabled": False})
        self.assertEqual(resp.status_code, 200)
        retrieve.assert_not_called()
        self.tenant.refresh_from_db()
        self.assertFalse(self.tenant.automatic_tax_enabled)


class SubscribeTaxErrorSurfacingTest(TestCase):
    """A Stripe tax-config rejection on subscribe comes back as 422, not 500."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="TaxSub", products=["metering", "billing"],
            stripe_connected_account_id="acct_tax", charges_enabled=True,
            automatic_tax_enabled=True)
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1")
        from apps.subscriptions.models import TenantBillingPlan
        self.plan = TenantBillingPlan.objects.create(
            tenant=self.tenant, key="pro", name="Pro",
            access_fee_micros=50_000_000, interval="month",
            stripe_access_price_id="price_a",
            provisioned_at="2026-01-01T00:00:00Z")

    def test_subscribe_returns_422_with_stripe_tax_message(self):
        with patch("stripe.Subscription.create",
                   side_effect=stripe.error.InvalidRequestError(
                       "automatic_tax[enabled] cannot be `true`: no origin address",
                       None)):
            resp = self.http_client.post(
                f"/api/v1/platform/customers/{self.customer.external_id}/subscribe",
                data=json.dumps({"plan_key": "pro", "seats": 0}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 422)
        self.assertIn("automatic_tax", resp.json()["error"])
