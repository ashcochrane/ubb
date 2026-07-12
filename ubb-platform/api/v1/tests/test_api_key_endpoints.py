"""Self-serve API key lifecycle — /api/v1/tenant/api-keys (F5.2)."""
import json

from django.test import TestCase, Client

from apps.platform.events.models import OutboxEvent
from apps.platform.events.registry import handler_registry
from apps.platform.tenants.models import Tenant, TenantApiKey


class ApiKeyLifecycleTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="KeyTest", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="primary")

    def _auth(self, raw=None):
        return {"HTTP_AUTHORIZATION": f"Bearer {raw or self.raw_key}"}

    def _post(self, path, body=None, raw=None):
        return self.http_client.post(
            path, data=json.dumps(body or {}), content_type="application/json",
            **self._auth(raw))

    # --- mint ---

    def test_mint_returns_raw_key_once_and_key_works(self):
        resp = self._post("/api/v1/tenant/api-keys", {"label": "ci"})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["api_key"].startswith("ubb_live_"))
        self.assertEqual(body["label"], "ci")
        self.assertEqual(body["tenant_id"], str(self.tenant.id))
        # The minted key authenticates immediately.
        check = self.http_client.get("/api/v1/tenant/config",
                                     **self._auth(raw=body["api_key"]))
        self.assertEqual(check.status_code, 200)
        # The raw key is never listed afterwards.
        listed = self.http_client.get("/api/v1/tenant/api-keys", **self._auth())
        self.assertNotIn(body["api_key"], listed.content.decode())
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="tenant.api_key_created").count(), 1)

    def test_sandbox_mode_mint_routes_to_sibling(self):
        resp = self._post("/api/v1/tenant/api-keys", {"label": "sb", "is_test": True})
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertTrue(body["api_key"].startswith("ubb_test_"))
        self.assertNotEqual(body["tenant_id"], str(self.tenant.id))
        sandbox = Tenant.objects.get(parent_tenant=self.tenant, is_sandbox=True)
        self.assertEqual(body["tenant_id"], str(sandbox.id))
        # Strict tenant scoping: the sandbox key is NOT in the live list.
        listed = self.http_client.get("/api/v1/tenant/api-keys", **self._auth())
        self.assertNotIn(body["id"], [k["id"] for k in listed.json()["data"]])

    def test_live_mint_on_sandbox_key_is_mode_mismatch_422(self):
        sb = self._post("/api/v1/tenant/api-keys", {"is_test": True}).json()
        resp = self._post("/api/v1/tenant/api-keys", {"is_test": False},
                          raw=sb["api_key"])
        self.assertEqual(resp.status_code, 422)

    # --- list ---

    def test_list_never_exposes_hash_or_raw(self):
        resp = self.http_client.get("/api/v1/tenant/api-keys", **self._auth())
        self.assertEqual(resp.status_code, 200)
        rows = resp.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(
            set(rows[0].keys()),
            {"id", "key_prefix", "label", "is_active", "last_used_at", "created_at"})
        text = resp.content.decode()
        self.assertNotIn(self.key_obj.key_hash, text)
        self.assertNotIn(self.raw_key, text)
        self.assertEqual(rows[0]["key_prefix"], self.raw_key[:16])

    def test_list_is_tenant_scoped(self):
        other = Tenant.objects.create(name="Other")
        TenantApiKey.create_key(other, label="other")
        resp = self.http_client.get("/api/v1/tenant/api-keys", **self._auth())
        self.assertEqual(len(resp.json()["data"]), 1)

    # --- rotate ---

    def test_rotate_new_key_works_old_401s_next_request(self):
        resp = self._post(f"/api/v1/tenant/api-keys/{self.key_obj.id}/rotate")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["api_key"].startswith("ubb_live_"))
        self.assertEqual(body["label"], "primary (rotated)")
        self.assertEqual(body["revoked_key_id"], str(self.key_obj.id))
        # New key authenticates; the OLD key 401s on its very next request
        # (per-request DB lookup auth — no cache window).
        ok = self.http_client.get("/api/v1/tenant/config",
                                  **self._auth(raw=body["api_key"]))
        self.assertEqual(ok.status_code, 200)
        stale = self.http_client.get("/api/v1/tenant/config", **self._auth())
        self.assertEqual(stale.status_code, 401)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="tenant.api_key_rotated").count(), 1)

    def test_rotate_unknown_key_404(self):
        other = Tenant.objects.create(name="Other")
        other_key, _ = TenantApiKey.create_key(other, label="other")
        resp = self._post(f"/api/v1/tenant/api-keys/{other_key.id}/rotate")
        self.assertEqual(resp.status_code, 404)

    # --- revoke ---

    def test_revoke_last_active_key_409(self):
        resp = self.http_client.delete(
            f"/api/v1/tenant/api-keys/{self.key_obj.id}", **self._auth())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "last_active_key")
        self.key_obj.refresh_from_db()
        self.assertTrue(self.key_obj.is_active)

    def test_revoke_with_second_active_key_works_and_is_instant(self):
        second = self._post("/api/v1/tenant/api-keys", {"label": "second"}).json()
        resp = self.http_client.delete(
            f"/api/v1/tenant/api-keys/{second['id']}", **self._auth())
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(resp.json()["is_active"])
        # The revoked key 401s on its next request.
        stale = self.http_client.get("/api/v1/tenant/config",
                                     **self._auth(raw=second["api_key"]))
        self.assertEqual(stale.status_code, 401)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="tenant.api_key_revoked").count(), 1)

    def test_revoke_is_idempotent(self):
        second = self._post("/api/v1/tenant/api-keys", {"label": "second"}).json()
        first = self.http_client.delete(
            f"/api/v1/tenant/api-keys/{second['id']}", **self._auth())
        again = self.http_client.delete(
            f"/api/v1/tenant/api-keys/{second['id']}", **self._auth())
        self.assertEqual((first.status_code, again.status_code), (200, 200))
        # No duplicate audit event for the no-op second call.
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="tenant.api_key_revoked").count(), 1)

    def test_revoke_unknown_key_404(self):
        other = Tenant.objects.create(name="Other")
        other_key, _ = TenantApiKey.create_key(other, label="other")
        resp = self.http_client.delete(
            f"/api/v1/tenant/api-keys/{other_key.id}", **self._auth())
        self.assertEqual(resp.status_code, 404)

    # --- events ---

    def test_api_key_events_are_registered(self):
        for event_type in ("tenant.api_key_created", "tenant.api_key_rotated",
                           "tenant.api_key_revoked"):
            self.assertTrue(handler_registry.get_handlers(event_type), event_type)
