"""Role floors bind across the tenant surface (identity build 2, #80).

Seam 2 (HTTP behaviour through the test client). The walker (test_role_floors)
proves every route *declares* the carve-table floor; here we prove the floor is
actually *enforced* end to end — a Read principal sees money and changes
nothing, a Write principal does data ops but not rule/money changes, an Admin
does everything — plus the last-Admin guard and the provisioning bootstrap.

Members authenticate exactly as in production: a Clerk session JWT (HS256 in the
suite, per core.clerk_auth) that activates the invited Member on first call.
"""
import json
import time

import jwt
from django.core.management import call_command
from django.test import Client, TestCase, override_settings

from apps.platform.events.models import OutboxEvent
from apps.platform.membership import services as membership_services
from apps.platform.membership.models import ACTIVE, PENDING, Invitation, Member
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey

SECRET = "role-floor-hs256-secret-32-bytes-and-then-some"
ISSUER = "https://clerk.test.example"


def _member_token(email, sub, exp_delta=900):
    return jwt.encode(
        {"iss": ISSUER, "sub": sub, "email": email,
         "exp": int(time.time()) + exp_delta},
        SECRET, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class RoleFloorEnforcementTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Acme", products=["metering", "billing", "subscriptions", "referrals"])
        self.key_obj, self.admin_key = TenantApiKey.create_key(self.tenant, label="primary")

    # --- helpers ---

    def _hdr(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _member(self, email, role, sub):
        """Invite + activate a member of ``role`` and return its token."""
        membership_services.invite_member(self.tenant, email, role)
        token = _member_token(email, sub)
        # First authenticated call activates the pending member.
        self.http.get("/api/v1/tenant/members", **self._hdr(token))
        return token

    def _call(self, method, path, token, body=None):
        kw = self._hdr(token)
        if body is not None:
            return getattr(self.http, method)(
                path, data=json.dumps(body),
                content_type="application/json", **kw)
        return getattr(self.http, method)(path, **kw)

    def _is_forbidden(self, resp):
        return resp.status_code == 403 and resp.json().get("code") == "forbidden"

    # --- the refusal matrix -------------------------------------------------

    # (method, path, floor, body). Bodies are valid where the route requires
    # one, so request parsing succeeds and the floor gate — not a 422 — is what
    # answers. Chosen to span products (billing, metering, subscriptions,
    # platform, tenant) and all three floors.
    MATRIX = [
        ("get", "/api/v1/tenant/config", READ, None),
        ("get", "/api/v1/billing/budget", READ, None),
        ("get", "/api/v1/metering/pricing/markup", READ, None),
        ("post", "/api/v1/subscriptions/sync", WRITE, None),
        ("patch", "/api/v1/tenant/config", ADMIN, {}),
        ("post", "/api/v1/tenant/api-keys", ADMIN, {}),
    ]

    def _assert_matrix(self, token, principal_role):
        rank = {READ: 0, WRITE: 1, ADMIN: 2}
        for method, path, floor, body in self.MATRIX:
            resp = self._call(method, path, token, body)
            if rank[principal_role] >= rank[floor]:
                self.assertFalse(
                    self._is_forbidden(resp),
                    f"{principal_role} should pass the {floor} floor on "
                    f"{method} {path} (got {resp.status_code} "
                    f"{resp.json().get('code')})")
            else:
                self.assertTrue(
                    self._is_forbidden(resp),
                    f"{principal_role} should be refused (403 forbidden) on "
                    f"{method} {path} (got {resp.status_code} "
                    f"{resp.json().get('code')})")

    def test_read_member_sees_but_cannot_change(self):
        token = self._member("reader@x.com", READ, "clerk_read")
        self._assert_matrix(token, READ)

    def test_write_member_does_data_ops_not_rule_changes(self):
        token = self._member("writer@x.com", WRITE, "clerk_write")
        self._assert_matrix(token, WRITE)

    def test_admin_member_does_everything(self):
        token = self._member("admin@x.com", ADMIN, "clerk_admin")
        self._assert_matrix(token, ADMIN)

    def test_admin_api_key_satisfies_every_floor(self):
        # Every migrated key is Admin — the whole existing suite runs on keys, so
        # floors must be transparent to key traffic.
        self._assert_matrix(self.admin_key, ADMIN)

    def test_read_member_reaches_money_with_200(self):
        """A Read principal genuinely reaches money (not just 'not forbidden')."""
        token = self._member("finance@x.com", READ, "clerk_fin")
        resp = self.http.get("/api/v1/tenant/config", **self._hdr(token))
        self.assertEqual(resp.status_code, 200)
        resp = self.http.get("/api/v1/billing/budget", **self._hdr(token))
        self.assertEqual(resp.status_code, 200)

    # --- last-Admin guard ---------------------------------------------------

    def _active_admin(self, email, sub):
        token = self._member(email, ADMIN, sub)
        return Member.objects.get(tenant=self.tenant, email=email), token

    def test_cannot_demote_last_active_admin(self):
        owner, _ = self._active_admin("owner@x.com", "clerk_owner")
        resp = self._call("patch", f"/api/v1/tenant/members/{owner.id}",
                          self.admin_key, {"role": WRITE})
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "last_active_admin")
        owner.refresh_from_db()
        self.assertEqual(owner.role, ADMIN)  # unchanged

    def test_cannot_remove_last_active_admin(self):
        owner, _ = self._active_admin("owner@x.com", "clerk_owner")
        resp = self._call("delete", f"/api/v1/tenant/members/{owner.id}",
                          self.admin_key)
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(resp.json()["code"], "last_active_admin")
        self.assertTrue(Member.objects.filter(id=owner.id).exists())

    def test_demote_and_remove_work_when_another_admin_remains(self):
        first, _ = self._active_admin("first@x.com", "clerk_first")
        second, _ = self._active_admin("second@x.com", "clerk_second")
        # Two admins: demoting one is allowed and lands.
        resp = self._call("patch", f"/api/v1/tenant/members/{first.id}",
                          self.admin_key, {"role": READ})
        self.assertEqual(resp.status_code, 200)
        first.refresh_from_db()
        self.assertEqual(first.role, READ)
        # Now `second` is the last admin — removing it is refused...
        resp = self._call("delete", f"/api/v1/tenant/members/{second.id}",
                          self.admin_key)
        self.assertEqual(resp.status_code, 409)
        # ...but removing the demoted (non-admin) member is fine.
        resp = self._call("delete", f"/api/v1/tenant/members/{first.id}",
                          self.admin_key)
        self.assertEqual(resp.status_code, 200)
        self.assertFalse(Member.objects.filter(id=first.id).exists())

    def test_removed_member_cannot_authenticate_next_request(self):
        # A non-admin member so the guard doesn't block removal.
        reader = Member.objects.get(
            tenant=self.tenant,
            email=self._invite_and_id("gone@x.com", READ, "clerk_gone"))
        token = _member_token("gone@x.com", "clerk_gone")
        self.http.get("/api/v1/tenant/members", **self._hdr(token))  # activate
        self._call("delete", f"/api/v1/tenant/members/{reader.id}", self.admin_key)
        # The removed principal 401s on its very next request.
        resp = self.http.get("/api/v1/tenant/config", **self._hdr(token))
        self.assertEqual(resp.status_code, 401)

    def _invite_and_id(self, email, role, sub):
        membership_services.invite_member(self.tenant, email, role)
        return email

    def test_role_change_of_pending_member_updates_invitation(self):
        inv = membership_services.invite_member(self.tenant, "pend@x.com", READ)
        member = Member.objects.get(tenant=self.tenant, email="pend@x.com")
        resp = self._call("patch", f"/api/v1/tenant/members/{member.id}",
                          self.admin_key, {"role": ADMIN})
        self.assertEqual(resp.status_code, 200)
        member.refresh_from_db()
        inv.refresh_from_db()
        self.assertEqual(member.role, ADMIN)
        self.assertEqual(inv.role, ADMIN)  # invitation kept in step

    def test_role_change_bad_role_is_422(self):
        member = Member.objects.get(
            tenant=self.tenant,
            email=self._invite_and_id("x@x.com", READ, "s"))
        resp = self._call("patch", f"/api/v1/tenant/members/{member.id}",
                          self.admin_key, {"role": "owner"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["code"], "validation_error")

    def test_member_routes_require_admin(self):
        member = Member.objects.get(
            tenant=self.tenant,
            email=self._invite_and_id("target@x.com", READ, "s"))
        reader = self._member("plainreader@x.com", READ, "clerk_pr")
        for method, body in [("patch", {"role": WRITE}), ("delete", None)]:
            resp = self._call(method, f"/api/v1/tenant/members/{member.id}",
                              reader, body)
            self.assertTrue(self._is_forbidden(resp), f"{method} should be Admin-gated")

    # --- bootstrap ----------------------------------------------------------

    def test_bootstrap_owner_creates_first_admin_invitation(self):
        fresh = Tenant.objects.create(name="Fresh", products=["metering"])
        inv = membership_services.bootstrap_owner_admin(fresh, "Boss@Fresh.com")
        self.assertIsNotNone(inv)
        self.assertEqual(inv.role, ADMIN)
        self.assertEqual(inv.email, "boss@fresh.com")  # normalized
        member = Member.objects.get(tenant=fresh, email="boss@fresh.com")
        self.assertEqual(member.role, ADMIN)
        self.assertEqual(member.status, PENDING)
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="invitation.created").exists())

    def test_bootstrap_is_idempotent(self):
        fresh = Tenant.objects.create(name="Fresh", products=["metering"])
        membership_services.bootstrap_owner_admin(fresh, "boss@fresh.com")
        # Re-provisioning must not raise or duplicate.
        again = membership_services.bootstrap_owner_admin(fresh, "boss@fresh.com")
        self.assertIsNotNone(again)
        self.assertEqual(
            Invitation.objects.filter(tenant=fresh, email="boss@fresh.com").count(), 1)

    def test_bootstrapped_owner_activates_as_admin_and_can_admin(self):
        fresh = Tenant.objects.create(name="Fresh", products=["metering"])
        membership_services.bootstrap_owner_admin(fresh, "boss@fresh.com")
        token = _member_token("boss@fresh.com", "clerk_boss")
        # First login activates the owner as an Admin...
        resp = self.http.get("/api/v1/tenant/members", **self._hdr(token))
        self.assertEqual(resp.status_code, 200)
        member = Member.objects.get(tenant=fresh, email="boss@fresh.com")
        self.assertEqual(member.status, ACTIVE)
        self.assertEqual(member.role, ADMIN)
        # ...and can immediately perform an Admin op (invite a teammate).
        resp = self._call("post", "/api/v1/tenant/invitations", token,
                          {"email": "hire@fresh.com", "role": WRITE})
        self.assertEqual(resp.status_code, 201)

    def test_seed_command_owner_email_yields_admin_invitation(self):
        call_command("seed_dev_data", "--stripe-account", "acct_test",
                     "--tenant-name", "SeedCo", "--billing-mode", "meter_only",
                     "--owner-email", "founder@seedco.com")
        tenant = Tenant.objects.get(name="SeedCo")
        inv = Invitation.objects.get(tenant=tenant, email="founder@seedco.com")
        self.assertEqual(inv.role, ADMIN)
        self.assertEqual(inv.status, "pending")
