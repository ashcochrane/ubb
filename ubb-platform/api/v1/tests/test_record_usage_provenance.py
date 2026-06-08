import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard


class RecordUsageProvenanceTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Provenance Tenant", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_provenance_1"
        )
        # cost RateCard: 5_000 micros per 1_000_000 input_tokens
        # => 1000 tokens => 1000 * 5_000 / 1_000_000 = 5 micros
        RateCard.objects.create(
            tenant=self.tenant,
            customer=None,
            card_type="cost",
            provider="openai",
            event_type="chat",
            metric_name="input_tokens",
            rate_per_unit_micros=5_000,
            unit_quantity=1_000_000,
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    @patch("apps.platform.events.tasks.process_single_event")
    def test_response_includes_pricing_provenance_and_usage_metrics(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_provenance_1",
                "idempotency_key": "idem_provenance_1",
                "provider": "openai",
                "event_type": "chat",
                "usage_metrics": {"input_tokens": 1000},
                # no provider_cost_micros — should be derived from rate card
            }),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider_cost_micros"], 5)
        self.assertEqual(body["pricing_provenance"]["cost_source"], "rate_card")
        self.assertEqual(body["usage_metrics"], {"input_tokens": 1000})
