import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import Rate
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book, rate_in_default_book
from core.vocabulary import COSTING_METHOD_CALCULATED


class RecordUsageReceiptTest(TestCase):
    """The recording ack carries the receipt, under the receipt's own name.

    The module and the class took that name in #370 with the wire key. The word
    they carried before was the record's retired spelling, and it survives now
    only as the name of a SECTION inside the record — so a module named for it
    would have been the second public name for one concept that ADR-0006 §2
    refuses, in the commit that removed the first.
    """

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Provenance Tenant", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_provenance_1"
        )
        # cost Rate: 5_000 micros per 1_000_000 input_tokens
        # => 1000 tokens => 1000 * 5_000 / 1_000_000 = 5 micros
        cost_rate_in_default_book(self.tenant, provider="openai",
            event_type="chat",
            measurement_key="input_tokens",
            rate_per_unit_micros=5_000,
            unit_quantity=1_000_000,
        )

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    @patch("apps.platform.events.tasks.process_single_event")
    def test_response_includes_the_pricing_receipt_and_measurements(
            self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": "idem_provenance_1",
                "provider": "openai",
                "event_type": "chat",
                "measurements": {"input_tokens": 1000},
                # no provider_cost_micros — should be derived from rate card
            }),
            content_type="application/json",
            **self._auth(),
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["provider_cost_micros"], 5)
        self.assertEqual(body["pricing_receipt"]["costing"]["method"],
                         COSTING_METHOD_CALCULATED)
        self.assertEqual(body["measurements"], {"input_tokens": 1000})
