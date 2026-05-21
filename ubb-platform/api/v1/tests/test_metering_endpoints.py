import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Card, Rate


class MeteringProductGatingTest(TestCase):
    """Metering-only tenant can use metering endpoints, gets 403 on billing."""

    def setUp(self):
        self.http_client = Client()
        self.tenant_with_metering = Tenant.objects.create(
            name="Has Metering", products=["metering"]
        )
        self.key_obj_yes, self.raw_key_yes = TenantApiKey.create_key(
            self.tenant_with_metering, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant_with_metering, external_id="cust_met1"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])
        card = Card.objects.create(
            tenant=self.tenant_with_metering,
            name="Test Card",
            slug="test_card",
            provider="test_provider",
        )
        Rate.objects.create(
            card=card,
            metric_name="tokens",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_tenant_with_metering_can_record_usage(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_met_1",
                "idempotency_key": "idem_met_1",
                "pricing_card": "test_card",
                "usage_metrics": {"tokens": 1},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("eventId", body)

    def test_tenant_with_metering_can_get_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("hasMore", body)

    def test_metering_only_tenant_gets_403_on_billing_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 403)

    def test_metering_only_tenant_gets_403_on_billing_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 403)


class MeteringRunEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Run Tenant",
            products=["metering"],
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_run_met"
        )
        # Rate: 1 micro per token
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            slug="test_card_run",
            provider="test_provider",
        )
        Rate.objects.create(
            card=card,
            metric_name="tokens",
            cost_per_unit_micros=1,
            unit_quantity=1,
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _record(self, **extra):
        data = {
            "customer_id": str(self.customer.id),
            "request_id": "req_1",
            "idempotency_key": "idem_1",
            "pricing_card": "test_card_run",
            "usage_metrics": {"tokens": 1_000_000},
        }
        data.update(extra)
        return self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(data),
            content_type="application/json",
            **self._auth(),
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_with_run_id_success(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=10_000_000, hard_stop_balance_micros=-5_000_000,
        )
        resp = self._record(run_id=str(run.id))
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["runId"], str(run.id))
        self.assertEqual(body["runTotalCostMicros"], 1_000_000)
        self.assertFalse(body["hardStop"])

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_hard_stop_returns_429(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=10_000_000, hard_stop_balance_micros=-5_000_000,
        )
        # First event under limit
        resp = self._record(
            run_id=str(run.id),
            request_id="req_hs1",
            idempotency_key="idem_hs1",
            usage_metrics={"tokens": 9_000_000},
        )
        self.assertEqual(resp.status_code, 200)

        # Second event breaches 10M ceiling
        resp = self._record(
            run_id=str(run.id),
            request_id="req_hs2",
            idempotency_key="idem_hs2",
            usage_metrics={"tokens": 2_000_000},
        )
        self.assertEqual(resp.status_code, 429)
        body = resp.json()
        self.assertTrue(body["hardStop"])
        self.assertEqual(body["reason"], "cost_limit_exceeded")
        self.assertEqual(body["runId"], str(run.id))

        # Run should be killed
        run.refresh_from_db()
        self.assertEqual(run.status, "killed")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_record_usage_stopped_run_returns_409(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
        )
        RunService.kill_run(run.id)

        resp = self._record(run_id=str(run.id))
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["error"], "run_not_active")  # value stays snake_case

    @patch("apps.platform.events.tasks.process_single_event")
    def test_close_run_success(self, mock_process):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
        )
        # Record some usage first
        self._record(run_id=str(run.id))

        resp = self.http_client.post(
            f"/api/v1/metering/runs/{run.id}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["runId"], str(run.id))
        self.assertEqual(body["status"], "completed")
        self.assertEqual(body["totalCostMicros"], 1_000_000)
        self.assertEqual(body["eventCount"], 1)

    def test_close_run_not_found_returns_404(self):
        import uuid
        resp = self.http_client.post(
            f"/api/v1/metering/runs/{uuid.uuid4()}/close",
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(resp.status_code, 404)


class MeteringUsageAnalyticsEndpointTest(TestCase):
    def setUp(self):
        from apps.metering.usage.services.usage_service import UsageService

        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Analytics Tenant", products=["metering"],
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_analytics"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            slug="test_card_hard_stop",
            provider="test_provider",
        )
        Rate.objects.create(
            card=card,
            metric_name="tokens",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )
        for i in range(3):
            UsageService.record_usage(
                tenant=self.tenant,
                customer=self.customer,
                request_id=f"req_analytics_{i}",
                idempotency_key=f"idem_analytics_{i}",
                pricing_card="test_card_hard_stop",
                usage_metrics={"tokens": 1},
            )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def test_usage_analytics(self):
        response = self.http_client.get(
            "/api/v1/metering/analytics/usage",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["totalEvents"], 3)
        self.assertEqual(body["totalBilledCostMicros"], 3_000_000)
        # Verify by_card aggregation
        self.assertIn("byCard", body)
        self.assertIsInstance(body["byCard"], list)
        self.assertEqual(len(body["byCard"]), 1)
        card_entry = body["byCard"][0]
        self.assertEqual(card_entry["cardSlug"], "test_card_hard_stop")
        self.assertEqual(card_entry["cardName"], "Test Card")
        self.assertEqual(card_entry["eventCount"], 3)
        self.assertEqual(card_entry["totalCostMicros"], 3_000_000)

class CardOutShapeTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.api_key, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000, label="Input", unit="per 1M tokens",
        )

    def test_card_out_has_dimensions_not_rates(self):
        resp = self.http_client.get(
            f"/api/v1/metering/pricing/cards/{self.card.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        body = resp.json()
        # Renamed from rates -> dimensions
        assert "dimensions" in body
        assert "rates" not in body
        # eventType gone
        assert "eventType" not in body
        # Each dimension has providerCostPerUnitMicros
        assert "providerCostPerUnitMicros" in body["dimensions"][0]
