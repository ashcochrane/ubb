"""Members & invitations over HTTP — /api/v1/tenant/{invitations,members}
(identity build 1, #79). Exercises both tenant-principal schemes end to end:
a tenant API key (Admin) and a Clerk member token, plus the end-customer widget
token that must never reach tenant management."""
import json
import time

import jwt
from django.test import Client, TestCase, override_settings

from apps.platform.events.models import OutboxEvent
from apps.platform.membership.models import ACTIVE, Member
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.widget_auth import create_widget_token

SECRET = "membership-endpoint-hs256-secret-32-bytes-plus"
ISSUER = "https://clerk.test.example"


def _member_token(email, sub, secret=SECRET, issuer=ISSUER, exp_delta=900):
    return jwt.encode(
        {"iss": issuer, "sub": sub, "email": email,
         "exp": int(time.time()) + exp_delta},
        secret, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class MembershipEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Acme", products=["metering", "billing"])
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="primary")

    # --- helpers ---

    def _hdr(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _post(self, path, body, token):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json", **self._hdr(token))

    def _invite(self, email, role, token=None):
        return self._post("/api/v1/tenant/invitations",
                          {"email": email, "role": role}, token or self.raw_key)

    # --- invitations (Admin, via API key) ---

    def test_admin_key_creates_invitation_and_event(self):
        resp = self._invite("sam@example.com", WRITE)
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["email"], "sam@example.com")
        self.assertEqual(body["role"], WRITE)
        self.assertEqual(body["status"], "pending")
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="invitation.created").exists())

    def test_invitation_and_member_lists(self):
        self._invite("sam@example.com", READ)
        inv_list = self.http.get("/api/v1/tenant/invitations", **self._hdr(self.raw_key))
        self.assertEqual(inv_list.status_code, 200)
        self.assertEqual(set(inv_list.json().keys()), {"data", "next_cursor", "has_more"})
        self.assertEqual(len(inv_list.json()["data"]), 1)
        mem_list = self.http.get("/api/v1/tenant/members", **self._hdr(self.raw_key))
        self.assertEqual(mem_list.status_code, 200)
        rows = mem_list.json()["data"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status"], "pending")
        self.assertEqual(rows[0]["clerk_user_id"], "")

    def test_create_invitation_bad_role_is_422(self):
        resp = self._invite("sam@example.com", "owner")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp["Content-Type"], "application/problem+json")
        self.assertEqual(resp.json()["code"], "validation_error")

    def test_duplicate_invite_is_409(self):
        self._invite("sam@example.com", READ)
        resp = self._invite("sam@example.com", READ)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "conflict")

    def test_revoke_invitation(self):
        inv = self._invite("sam@example.com", READ).json()
        resp = self.http.delete(f"/api/v1/tenant/invitations/{inv['id']}",
                                **self._hdr(self.raw_key))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "revoked")
        self.assertFalse(Member.objects.filter(
            tenant=self.tenant, email="sam@example.com").exists())

    def test_revoke_unknown_is_404(self):
        import uuid
        resp = self.http.delete(f"/api/v1/tenant/invitations/{uuid.uuid4()}",
                                **self._hdr(self.raw_key))
        self.assertEqual(resp.status_code, 404)

    # --- acceptance: invite -> first login activates -> member calls the API ---

    def test_member_token_activates_on_first_call_and_lists_members(self):
        self._invite("sam@example.com", WRITE)
        token = _member_token("sam@example.com", "clerk_user_1")
        # First authenticated call activates the pending member.
        resp = self.http.get("/api/v1/tenant/members", **self._hdr(token))
        self.assertEqual(resp.status_code, 200)
        member = Member.objects.get(tenant=self.tenant, email="sam@example.com")
        self.assertEqual(member.status, ACTIVE)
        self.assertEqual(member.clerk_user_id, "clerk_user_1")
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="member.activated").exists())

    # --- role floors bind on the new routes ---

    def test_read_member_cannot_create_invitation(self):
        self._invite("reader@example.com", READ)
        token = _member_token("reader@example.com", "clerk_reader")
        # Activate + confirm they CAN list members (Read floor).
        self.assertEqual(
            self.http.get("/api/v1/tenant/members", **self._hdr(token)).status_code, 200)
        # But an Admin-gated invitation is refused.
        resp = self._invite("new@example.com", READ, token=token)
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["code"], "forbidden")

    def test_admin_member_can_create_invitation(self):
        self._invite("boss@example.com", ADMIN)
        token = _member_token("boss@example.com", "clerk_boss")
        # Activate.
        self.http.get("/api/v1/tenant/members", **self._hdr(token))
        resp = self._invite("hire@example.com", WRITE, token=token)
        self.assertEqual(resp.status_code, 201)

    # --- end-customer isolation ---

    def test_widget_token_cannot_touch_tenant_management(self):
        widget = create_widget_token(
            self.tenant.widget_secret, "customer-1", str(self.tenant.id))
        for method, path in [
            ("get", "/api/v1/tenant/members"),
            ("get", "/api/v1/tenant/invitations"),
        ]:
            resp = getattr(self.http, method)(path, **self._hdr(widget))
            self.assertEqual(resp.status_code, 401, f"{method} {path}")
            self.assertEqual(resp["Content-Type"], "application/problem+json")
        # And it cannot create an invitation.
        resp = self._invite("x@example.com", READ, token=widget)
        self.assertEqual(resp.status_code, 401)

    def test_no_auth_is_401(self):
        resp = self.http.get("/api/v1/tenant/members")
        self.assertEqual(resp.status_code, 401)

    def test_member_token_authenticates_a_preexisting_tenant_route(self):
        # "member_token accepted alongside tenant_api_key on every tenant route":
        # the seam is the shared ApiKeyAuth, so a member token authenticates a
        # route that predates membership (GET /tenant/config), not just the new
        # identity routes.
        self._invite("sam@example.com", WRITE)
        token = _member_token("sam@example.com", "clerk_user_cfg")
        resp = self.http.get("/api/v1/tenant/config", **self._hdr(token))
        self.assertEqual(resp.status_code, 200)
