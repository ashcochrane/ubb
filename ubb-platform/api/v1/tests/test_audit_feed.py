"""The tenant-facing audit feed (#82, ADR-004 §5) through real HTTP.

Proves the feed's spec promises: cursor envelope, Read floor (any tenant
principal reads it), end-customer widget tokens refused, exact-match filters,
tenant isolation, and that an operator action renders under one ``UBB operator``
name. Records are seeded through the ledger's own ``record()`` so the feed is
tested against real entries.
"""
import time

import jwt
from django.test import Client, TestCase, override_settings

from apps.platform.audit.actors import operator_actor
from apps.platform.audit.ledger import record
from apps.platform.membership import services as membership_services
from apps.platform.membership.roles import READ
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.widget_auth import create_widget_token

SECRET = "audit-feed-hs256-secret-32-bytes-and-then-some"
ISSUER = "https://clerk.test.example"


def _member_token(email, sub, exp_delta=900):
    return jwt.encode(
        {"iss": ISSUER, "sub": sub, "email": email,
         "exp": int(time.time()) + exp_delta},
        SECRET, algorithm="HS256")


@override_settings(CLERK_ISSUER=ISSUER, CLERK_HS256_SECRET=SECRET,
                   CLERK_JWKS_URL="", CLERK_JWT_PUBLIC_KEY="")
class AuditFeedTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Acme", products=["metering", "billing"])
        self.key_obj, self.key = TenantApiKey.create_key(self.tenant, label="primary")

    def _hdr(self, token):
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}

    def _seed(self, n, action="api_key.created", **kw):
        for i in range(n):
            record(action=action, tenant_id=self.tenant.id,
                   resource_type=kw.get("resource_type", "api_key"),
                   resource_id=kw.get("resource_id", f"r{i}"),
                   metadata={"i": i})

    def _get(self, token, query=""):
        return self.http.get(f"/api/v1/audit/records{query}", **self._hdr(token))

    def test_feed_returns_tenant_entries_in_the_cursor_envelope(self):
        self._seed(3)
        resp = self._get(self.key)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(set(body), {"data", "next_cursor", "has_more"})
        self.assertEqual(len(body["data"]), 3)
        row = body["data"][0]
        for field in ("id", "created_at", "action", "actor_kind",
                      "actor_display", "resource_type", "resource_id",
                      "correlation_id", "metadata"):
            self.assertIn(field, row)

    def test_cursor_pagination_walks_the_whole_feed_without_dupes(self):
        self._seed(5)
        seen = []
        cursor = ""
        for _ in range(5):
            q = f"?limit=2{f'&cursor={cursor}' if cursor else ''}"
            body = self._get(self.key, q).json()
            seen.extend(r["id"] for r in body["data"])
            cursor = body["next_cursor"]
            if not cursor:
                break
        self.assertEqual(len(seen), 5)
        self.assertEqual(len(set(seen)), 5)  # no row served twice

    def test_readable_at_read_floor(self):
        """Any tenant principal reads the trail — even a Read-only member."""
        membership_services.invite_member(self.tenant, "viewer@acme.test", READ)
        token = _member_token("viewer@acme.test", "sub_viewer")
        self.http.get("/api/v1/tenant/members", **self._hdr(token))  # activate
        self._seed(1, action="wallet.credited", resource_type="wallet")
        resp = self._get(token, "?action=wallet.credited")
        self.assertEqual(resp.status_code, 200)  # Read principal may read the trail
        self.assertEqual(len(resp.json()["data"]), 1)

    def test_end_customer_widget_token_is_refused(self):
        """A widget token authenticates /me but never the tenant audit feed."""
        from apps.platform.customers.models import Customer
        customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        widget = create_widget_token(
            self.tenant.widget_secret, str(customer.id), str(self.tenant.id))
        # Sanity: the widget token is otherwise valid on the /me surface.
        self.assertEqual(
            self.http.get("/api/v1/me/balance", **self._hdr(widget)).status_code,
            200)
        # But the feed is a tenant-principal route — refused (401).
        self.assertEqual(self._get(widget).status_code, 401)

    def test_action_filter(self):
        self._seed(2, action="api_key.created")
        self._seed(3, action="wallet.credited", resource_type="wallet")
        body = self._get(self.key, "?action=wallet.credited").json()
        self.assertEqual(len(body["data"]), 3)
        self.assertTrue(all(r["action"] == "wallet.credited" for r in body["data"]))

    def test_resource_filter_answers_who_changed_this(self):
        record(action="rate_card.published", tenant_id=self.tenant.id,
               resource_type="rate_card", resource_id="card-42", metadata={})
        record(action="rate_card.published", tenant_id=self.tenant.id,
               resource_type="rate_card", resource_id="card-99", metadata={})
        body = self._get(
            self.key,
            "?resource_type=rate_card&resource_id=card-42").json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["resource_id"], "card-42")

    def test_operator_action_renders_as_ubb_operator(self):
        record(action="wallet.credited", tenant_id=self.tenant.id,
               resource_type="wallet", resource_id="c1",
               actor=operator_actor("op_123"), metadata={})
        row = self._get(self.key, "?action=wallet.credited").json()["data"][0]
        self.assertEqual(row["actor_kind"], "operator")
        self.assertEqual(row["actor_display"], "UBB operator")

    def test_tenant_isolation(self):
        other = Tenant.objects.create(name="Other", products=["metering", "billing"])
        record(action="api_key.created", tenant_id=other.id,
               resource_type="api_key", resource_id="x", metadata={})
        self._seed(2)
        body = self._get(self.key).json()
        self.assertEqual(len(body["data"]), 2)  # never the other tenant's row
