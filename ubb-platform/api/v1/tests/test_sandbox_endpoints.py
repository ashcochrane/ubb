"""F4.4 sandbox endpoints: /api/v1/tenant/sandbox (self-serve provisioning)
and /api/v1/sandbox/reset (sandbox-key-only reset)."""
import json
from unittest.mock import patch

from django.test import Client, TestCase

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox


class TenantSandboxEndpointTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.live = Tenant.objects.create(
            name="Live Co", products=["metering"], billing_mode="meter_only")
        _, self.live_key = TenantApiKey.create_key(self.live, label="t")

    def _auth(self, key):
        return {"HTTP_AUTHORIZATION": f"Bearer {key}"}

    def test_post_creates_sandbox_and_returns_raw_test_key_once(self):
        resp = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["api_key"].startswith("ubb_test_"))
        sandbox = Tenant.objects.get(parent_tenant=self.live, is_sandbox=True)
        self.assertEqual(body["sandbox_tenant_id"], str(sandbox.id))
        # The minted key authenticates AS the sandbox tenant
        key_obj = TenantApiKey.verify_key(body["api_key"])
        self.assertEqual(key_obj.tenant_id, sandbox.id)

    def test_post_twice_same_sandbox_fresh_key(self):
        first = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        second = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        self.assertEqual(first["sandbox_tenant_id"], second["sandbox_tenant_id"])
        self.assertNotEqual(first["api_key"], second["api_key"])
        self.assertEqual(
            Tenant.objects.filter(parent_tenant=self.live, is_sandbox=True).count(), 1)

    def test_post_with_sandbox_key_403(self):
        body = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        resp = self.http.post("/api/v1/tenant/sandbox", **self._auth(body["api_key"]))
        self.assertEqual(resp.status_code, 403)

    def test_get_before_and_after_create(self):
        before = self.http.get("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        self.assertFalse(before["exists"])
        self.assertIsNone(before["sandbox_tenant_id"])

        created = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        after = self.http.get("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        self.assertTrue(after["exists"])
        self.assertEqual(after["sandbox_tenant_id"], created["sandbox_tenant_id"])
        self.assertEqual(after["key_prefixes"], [created["api_key"][:16]])
        # the raw key is never echoed back by GET
        self.assertNotIn("api_key", after)

    def test_get_with_sandbox_key_403(self):
        body = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        resp = self.http.get("/api/v1/tenant/sandbox", **self._auth(body["api_key"]))
        self.assertEqual(resp.status_code, 403)

    def test_sandbox_key_sees_only_the_sandbox_tenant(self):
        """Isolation at the API layer: each key reads its OWN tenant config."""
        body = self.http.post("/api/v1/tenant/sandbox", **self._auth(self.live_key)).json()
        live_cfg = self.http.get("/api/v1/tenant/config", **self._auth(self.live_key)).json()
        sb_cfg = self.http.get("/api/v1/tenant/config", **self._auth(body["api_key"])).json()
        self.assertEqual(live_cfg["name"], "Live Co")
        self.assertEqual(sb_cfg["name"], "Live Co (sandbox)")


class SandboxResetEndpointTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.live = Tenant.objects.create(name="Live Co", products=["metering"])
        _, self.live_key = TenantApiKey.create_key(self.live, label="t")
        self.sandbox = get_or_create_sandbox(self.live)
        _, self.test_key = TenantApiKey.create_key(self.sandbox, label="t", is_test=True)

    def _auth(self, key):
        return {"HTTP_AUTHORIZATION": f"Bearer {key}"}

    def test_live_key_403_and_no_task(self):
        with patch("apps.platform.tenants.tasks.reset_sandbox_tenant.delay") as mock_delay:
            resp = self.http.post(
                "/api/v1/sandbox/reset", data=json.dumps({}),
                content_type="application/json", **self._auth(self.live_key))
        self.assertEqual(resp.status_code, 403)
        mock_delay.assert_not_called()

    def test_sandbox_key_202_enqueues_keep_config_default_true(self):
        with patch("apps.platform.tenants.tasks.reset_sandbox_tenant.delay") as mock_delay:
            resp = self.http.post(
                "/api/v1/sandbox/reset", data=json.dumps({}),
                content_type="application/json", **self._auth(self.test_key))
        self.assertEqual(resp.status_code, 202)
        self.assertEqual(resp.json()["keep_config"], True)
        mock_delay.assert_called_once_with(str(self.sandbox.id), True)

    def test_keep_config_false_is_threaded(self):
        with patch("apps.platform.tenants.tasks.reset_sandbox_tenant.delay") as mock_delay:
            resp = self.http.post(
                "/api/v1/sandbox/reset", data=json.dumps({"keep_config": False}),
                content_type="application/json", **self._auth(self.test_key))
        self.assertEqual(resp.status_code, 202)
        mock_delay.assert_called_once_with(str(self.sandbox.id), False)

    def test_unauthenticated_401(self):
        resp = self.http.post("/api/v1/sandbox/reset")
        self.assertEqual(resp.status_code, 401)
