"""End to end: minting an API key records an audit entry, with BOTH tenant-
principal actor kinds exercised — an api_key mints (actor kind `api_key`) and a
Clerk-verified Admin member mints (actor kind `member`) — proving the auth-seam
capture + record() path works through real HTTP (ADR-004; issue #81 AC 2)."""
import time

import jwt
from django.test import Client, TestCase, override_settings

from apps.platform.audit.models import AuditRecord
from apps.platform.membership import services as membership_services
from apps.platform.membership.roles import ADMIN
from apps.platform.tenants.models import Tenant, TenantApiKey

SECRET = "audit-hs256-secret-32-bytes-and-then-some"
ISSUER = "https://clerk.test.example"


def _member_token(email, sub, exp_delta=900):
    return jwt.encode(
        {"iss": ISSUER, "sub": sub, "email": email,
         "exp": int(time.time()) + exp_delta},
        SECRET, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class ApiKeyMintAuditTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Acme", products=["metering"])
        self.key_obj, self.admin_key = TenantApiKey.create_key(
            self.tenant, label="primary")

    def _hdr(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _mint(self, token, label="minted"):
        return self.http.post(
            "/api/v1/tenant/api-keys",
            data='{"label": "%s"}' % label,
            content_type="application/json",
            **self._hdr(token))

    # --- api_key actor ------------------------------------------------------

    def test_mint_by_api_key_records_api_key_actor(self):
        resp = self._mint(self.admin_key, label="ci")
        self.assertEqual(resp.status_code, 201)
        new_key_id = resp.json()["id"]

        rec = AuditRecord.objects.get(action="api_key.created",
                                      resource_id=new_key_id)
        self.assertEqual(rec.actor_kind, "api_key")
        self.assertEqual(rec.actor_id, str(self.key_obj.id))
        self.assertEqual(rec.actor_display, "primary")
        self.assertEqual(rec.resource_type, "api_key")
        self.assertEqual(rec.tenant_id, self.tenant.id)
        self.assertEqual(rec.metadata["label"], "ci")
        self.assertEqual(rec.metadata["mode"], "live")

    # --- member actor -------------------------------------------------------

    def test_mint_by_member_records_member_actor(self):
        membership_services.invite_member(self.tenant, "admin@acme.com", ADMIN)
        token = _member_token("admin@acme.com", "clerk_admin")
        # First authenticated call activates the pending member.
        self.http.get("/api/v1/tenant/members", **self._hdr(token))

        resp = self._mint(token, label="from-member")
        self.assertEqual(resp.status_code, 201)
        new_key_id = resp.json()["id"]

        rec = AuditRecord.objects.get(action="api_key.created",
                                      resource_id=new_key_id)
        self.assertEqual(rec.actor_kind, "member")
        self.assertEqual(rec.actor_display, "admin@acme.com")
        self.assertEqual(rec.tenant_id, self.tenant.id)
        self.assertNotEqual(rec.actor_id, "")

    # --- properties ---------------------------------------------------------

    def test_audit_row_carries_the_request_correlation_id(self):
        cid = "22222222-2222-2222-2222-222222222222"
        resp = self.http.post(
            "/api/v1/tenant/api-keys",
            data='{"label": "corr"}',
            content_type="application/json",
            HTTP_X_CORRELATION_ID=cid,
            **self._hdr(self.admin_key))
        rec = AuditRecord.objects.get(resource_id=resp.json()["id"])
        self.assertEqual(rec.correlation_id, cid)

    def test_metadata_never_holds_the_raw_key_or_hash(self):
        # No before/after snapshot machinery: only curated metadata is stored, so
        # the raw key / hash structurally cannot leak into the ledger (ADR-004 §4).
        resp = self._mint(self.admin_key, label="secretcheck")
        raw_key = resp.json()["api_key"]
        rec = AuditRecord.objects.get(resource_id=resp.json()["id"])
        blob = str(rec.metadata)
        self.assertNotIn(raw_key, blob)
        self.assertNotIn(self.key_obj.key_hash, blob)
        # key_prefix (public, non-secret) is fine to keep.
        self.assertIn("key_prefix", rec.metadata)

    def test_no_audit_row_when_mint_is_unauthenticated(self):
        before = AuditRecord.objects.count()
        resp = self.http.post(
            "/api/v1/tenant/api-keys", data='{"label": "x"}',
            content_type="application/json")  # no bearer token
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(AuditRecord.objects.count(), before)
