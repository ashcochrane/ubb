from unittest.mock import patch, MagicMock
from urllib.parse import urlparse, parse_qs

from django.test import TestCase, Client, RequestFactory, override_settings

from apps.platform.tenants.models import Tenant, TenantApiKey, ConnectOAuthState


@override_settings(STRIPE_CONNECT_CLIENT_ID="ca_test")
class ConnectStartStatusTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_start_returns_authorize_url(self):
        resp = self.http_client.post(
            "/api/v1/connect/start",
            data={"return_url": "https://x/done"},
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["authorize_url"]
        self.assertTrue(url.startswith("https://connect.stripe.com/oauth/authorize"))
        # A single-use state was minted and persisted.
        self.assertTrue(ConnectOAuthState.objects.filter(tenant=self.tenant).exists())

    def test_start_requires_auth(self):
        resp = self.http_client.post(
            "/api/v1/connect/start",
            data={"return_url": "https://x/done"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 401)

    def test_status_returns_onboarded_state(self):
        self.tenant.stripe_connected_account_id = "acct_xyz"
        self.tenant.charges_enabled = True
        self.tenant.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])
        resp = self.http_client.get("/api/v1/connect/status", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["account_id"], "acct_xyz")
        self.assertTrue(body["charges_enabled"])
        self.assertTrue(body["onboarded"])

    def test_status_not_onboarded_when_no_account(self):
        resp = self.http_client.get("/api/v1/connect/status", **self._auth())
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["account_id"], "")
        self.assertFalse(body["onboarded"])

    def test_status_requires_auth(self):
        resp = self.http_client.get("/api/v1/connect/status")
        self.assertEqual(resp.status_code, 401)


@override_settings(STRIPE_CONNECT_CLIENT_ID="ca_test")
class ConnectCallbackTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Test")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")

    def _mint_state(self, return_url="https://x/done"):
        resp = self.http_client.post(
            "/api/v1/connect/start",
            data={"return_url": return_url},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(resp.status_code, 200)
        url = resp.json()["authorize_url"]
        qs = parse_qs(urlparse(url).query)
        return qs["state"][0]

    def test_callback_no_auth_redirects_to_return_url_and_persists(self):
        state = self._mint_state("https://x/done")
        oauth_resp = MagicMock()
        oauth_resp.stripe_user_id = "acct_callback"
        acct = MagicMock()
        acct.charges_enabled = True
        with patch("apps.billing.connectors.stripe.connect.stripe.OAuth.token",
                   return_value=oauth_resp), \
             patch("apps.billing.connectors.stripe.connect.stripe.Account.retrieve",
                   return_value=acct):
            resp = self.http_client.get(
                "/api/v1/connect/callback", {"code": "ac", "state": state})
        self.assertEqual(resp.status_code, 302)
        loc = resp["Location"]
        self.assertTrue(loc.startswith("https://x/done"))
        self.assertIn("connected=true", loc)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_connected_account_id, "acct_callback")
        self.assertTrue(self.tenant.charges_enabled)

    def test_callback_unknown_state_not_500_no_mutation(self):
        resp = self.http_client.get(
            "/api/v1/connect/callback", {"state": "unknownnonce"})
        # Must NOT be a 500. Either a 400 JSON or a redirect with connected=false.
        self.assertNotEqual(resp.status_code, 500)
        self.assertIn(resp.status_code, (302, 400))
        if resp.status_code == 302:
            self.assertIn("connected=false", resp["Location"])
        # No tenant was mutated.
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_connected_account_id, "")
        self.assertFalse(self.tenant.charges_enabled)

    def test_callback_unknown_state_with_return_url_lookup_fails_gracefully(self):
        # An unknown state has no row -> JsonResponse 400 (no return_url available).
        resp = self.http_client.get(
            "/api/v1/connect/callback", {"code": "ac", "state": "doesnotexist"})
        self.assertNotEqual(resp.status_code, 500)
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(resp.json()["connected"])


class AccountWebhookTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_hook", charges_enabled=True)

    def test_deauthorized_clears_account(self):
        from api.v1.webhooks import WEBHOOK_HANDLERS
        handler = WEBHOOK_HANDLERS["account.application.deauthorized"]
        event = MagicMock()
        event.account = "acct_hook"
        handler(event)
        self.tenant.refresh_from_db()
        self.assertEqual(self.tenant.stripe_connected_account_id, "")
        self.assertFalse(self.tenant.charges_enabled)

    def test_account_updated_syncs_charges_enabled(self):
        from api.v1.webhooks import WEBHOOK_HANDLERS
        self.tenant.charges_enabled = False
        self.tenant.save(update_fields=["charges_enabled", "updated_at"])
        handler = WEBHOOK_HANDLERS["account.updated"]
        event = MagicMock()
        acct = MagicMock()
        acct.id = "acct_hook"
        acct.charges_enabled = True
        event.data.object = acct
        handler(event)
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.charges_enabled)

    def test_account_updated_unknown_account_noop(self):
        from api.v1.webhooks import WEBHOOK_HANDLERS
        handler = WEBHOOK_HANDLERS["account.updated"]
        event = MagicMock()
        acct = MagicMock()
        acct.id = "acct_other"
        acct.charges_enabled = False
        event.data.object = acct
        handler(event)  # no matching tenant -> no error
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.charges_enabled)
