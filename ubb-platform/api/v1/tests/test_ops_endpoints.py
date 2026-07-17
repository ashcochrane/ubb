from django.test import Client, TestCase, override_settings

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.metering.usage.models import RawIngestEvent


class OpsIngestHealthEndpointTest(TestCase):
    """Operator-facing: gated on UBB_OPS_TOKEN, NOT tenant API keys.
    Unset token -> 404 (fail closed, invisible)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Ops")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="op1")
        RawIngestEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            billing_owner_id=self.customer.id, idempotency_key="op-k1",
            payload={}, status="pending")

    def _get(self, token=None, query=""):
        headers = {"HTTP_X_OPS_TOKEN": token} if token is not None else {}
        return self.http_client.get(
            f"/api/v1/metering/ops/ingest-health{query}", **headers)

    def test_unset_token_404s(self):
        # UBB_OPS_TOKEN defaults to "" in tests (no env var set).
        resp = self._get(token="anything")
        self.assertEqual(resp.status_code, 404)
        # The gated-off 404 must be indistinguishable from Django's standard
        # 404 for an unmatched route — a ninja JSON 404 here would let an
        # attacker fingerprint the endpoint's existence even with no token.
        self.assertNotIn("application/json", resp.get("Content-Type", ""))

    def test_unset_token_404_matches_unregistered_path(self):
        # Same status + content-type as a genuinely unregistered path under
        # the same prefix — the whole point of "invisible".
        real_404 = self._get(token="anything")
        fake_path_resp = self.http_client.get(
            "/api/v1/metering/this-route-does-not-exist")
        self.assertEqual(real_404.status_code, fake_path_resp.status_code)
        self.assertEqual(
            real_404.get("Content-Type"), fake_path_resp.get("Content-Type"))

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_wrong_or_missing_token_401s(self):
        self.assertEqual(self._get(token="wrong").status_code, 401)
        self.assertEqual(self._get().status_code, 401)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_correct_token_returns_metrics(self):
        resp = self._get(token="s3cret")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["pending_count"], 1)
        for key in ("oldest_pending_age_seconds", "retrying_count",
                    "failed_count", "generated_at"):
            self.assertIn(key, body)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_tenant_filter(self):
        other_t = Tenant.objects.create(name="OpsOther")
        other_c = Customer.objects.create(tenant=other_t, external_id="op2")
        RawIngestEvent.objects.create(
            tenant=other_t, customer=other_c, billing_owner_id=other_c.id,
            idempotency_key="op-k2", payload={}, status="pending")
        resp = self._get(token="s3cret", query=f"?tenant_id={self.tenant.id}")
        self.assertEqual(resp.json()["pending_count"], 1)
        resp = self._get(token="s3cret")
        self.assertEqual(resp.json()["pending_count"], 2)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_patrol_counters_ride_the_surface(self):
        # #44 §F: patrol outcomes join this surface, composed from billing's
        # read contract, with the same optional tenant filter.
        from django.utils import timezone
        from apps.billing.gating.models import PatrolOutcome
        other_t = Tenant.objects.create(name="OpsOther")
        today = timezone.now().date()
        PatrolOutcome.objects.create(tenant=self.tenant, day=today,
                                     outcome="reminted", count=3)
        PatrolOutcome.objects.create(tenant=other_t, day=today,
                                     outcome="sweep_killed", count=2)
        body = self._get(token="s3cret").json()
        self.assertEqual(body["patrol_reminted_7d"], 3)
        self.assertEqual(body["patrol_sweep_killed_7d"], 2)
        self.assertEqual(body["patrol_flag_realigned_7d"], 0)
        scoped = self._get(
            token="s3cret", query=f"?tenant_id={self.tenant.id}").json()
        self.assertEqual(scoped["patrol_reminted_7d"], 3)
        self.assertEqual(scoped["patrol_sweep_killed_7d"], 0)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_correct_token_malformed_tenant_id_422s(self):
        # Signature stays `tenant_id: str` so ninja can't 422 this BEFORE the
        # token gate runs (that would re-open the fingerprinting hole) — the
        # view parses it manually AFTER both token checks pass.
        resp = self._get(token="s3cret", query="?tenant_id=not-a-uuid")
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"], "invalid_tenant_id")

    def test_tenant_api_key_does_not_grant_access_unset_token(self):
        # A valid tenant Bearer key must never substitute for the ops token.
        key_obj, raw_key = TenantApiKey.create_key(self.tenant, label="ops-probe")
        resp = self.http_client.get(
            "/api/v1/metering/ops/ingest-health",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 404)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_tenant_api_key_does_not_grant_access_set_token(self):
        key_obj, raw_key = TenantApiKey.create_key(self.tenant, label="ops-probe")
        resp = self.http_client.get(
            "/api/v1/metering/ops/ingest-health",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 401)


class OpsIngestHealthSchemaDisclosureTest(TestCase):
    """The ops endpoint must not appear in the public, unauthenticated
    OpenAPI schema/docs — that alone would fingerprint its existence even
    with UBB_OPS_TOKEN unset."""

    def test_not_listed_in_openapi_schema(self):
        resp = Client().get("/api/v1/metering/openapi.json")
        self.assertEqual(resp.status_code, 200)
        self.assertNotIn("ops/ingest-health", resp.content.decode())
