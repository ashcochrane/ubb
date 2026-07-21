"""The tenant-principal auth seam with both schemes (identity build 1, #79):
a Clerk member token and a tenant API key resolve through the one
``ApiKeyAuth``; the role floor helper gates on the resolved principal."""
import time

import jwt
from django.test import RequestFactory, TestCase, override_settings

from apps.platform.membership import services
from apps.platform.membership.roles import ADMIN, READ, WRITE
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.auth import ApiKeyAuth, require_role
from core.problems import Problem
from core.widget_auth import create_widget_token

SECRET = "member-auth-hs256-secret-at-least-32-bytes"
ISSUER = "https://clerk.test.example"


def _member_token(email, sub, secret=SECRET, issuer=ISSUER, exp_delta=900):
    return jwt.encode(
        {"iss": issuer, "sub": sub, "email": email,
         "exp": int(time.time()) + exp_delta},
        secret, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class MemberAuthSeamTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.auth = ApiKeyAuth()
        self.tenant = Tenant.objects.create(name="Acme")
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")

    def test_member_token_authenticates_and_sets_tenant(self):
        services.invite_member(self.tenant, "sam@example.com", WRITE)
        token = _member_token("sam@example.com", "user_1")
        request = self.factory.get("/")
        principal = self.auth.authenticate(request, token)
        self.assertIsNotNone(principal)
        self.assertEqual(request.tenant.id, self.tenant.id)
        self.assertEqual(principal.role, WRITE)
        self.assertFalse(request.sandbox)

    def test_api_key_still_authenticates(self):
        request = self.factory.get("/")
        principal = self.auth.authenticate(request, self.raw_key)
        self.assertIsNotNone(principal)
        self.assertEqual(request.tenant.id, self.tenant.id)
        # Every existing key carries the Admin role post-migration.
        self.assertEqual(principal.role, ADMIN)

    def test_widget_token_is_not_a_tenant_principal(self):
        # An end-customer widget JWT must never authenticate a tenant route.
        widget = create_widget_token(
            self.tenant.widget_secret, "cust-1", str(self.tenant.id))
        request = self.factory.get("/")
        self.assertIsNone(self.auth.authenticate(request, widget))

    def test_unknown_email_member_token_rejected(self):
        token = _member_token("stranger@example.com", "user_x")
        request = self.factory.get("/")
        self.assertIsNone(self.auth.authenticate(request, token))

    def test_garbage_token_rejected(self):
        request = self.factory.get("/")
        self.assertIsNone(self.auth.authenticate(request, "not-a-token"))


class RequireRoleTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(name="Acme")

    def _request_with_role(self, role):
        request = self.factory.get("/")
        member = services.invite_member(self.tenant, "sam@example.com", role)
        # give the request an auth principal at the requested role
        request.auth = self.tenant.members.get(email="sam@example.com")
        return request

    def test_admin_satisfies_admin_floor(self):
        request = self._request_with_role(ADMIN)
        require_role(request, ADMIN)  # no raise

    def test_read_fails_admin_floor(self):
        request = self._request_with_role(READ)
        with self.assertRaises(Problem) as ctx:
            require_role(request, ADMIN)
        self.assertEqual(ctx.exception.code, "forbidden")

    def test_read_satisfies_read_floor(self):
        request = self._request_with_role(READ)
        require_role(request, READ)  # no raise

    def test_api_key_admin_satisfies_every_floor(self):
        key_obj, _ = TenantApiKey.create_key(self.tenant)
        request = self.factory.get("/")
        request.auth = key_obj
        require_role(request, ADMIN)
        require_role(request, WRITE)
        require_role(request, READ)
