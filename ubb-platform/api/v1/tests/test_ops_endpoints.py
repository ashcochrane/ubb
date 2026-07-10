from django.test import Client, TestCase, override_settings

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
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
        self.assertEqual(self._get(token="anything").status_code, 404)

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
