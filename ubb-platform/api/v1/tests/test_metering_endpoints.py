import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


class MeteringProductGatingTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant_no_metering = Tenant.objects.create(
            name="No Metering", products=["billing"]
        )
        self.key_obj_no, self.raw_key_no = TenantApiKey.create_key(
            self.tenant_no_metering, label="test"
        )
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

    def test_tenant_without_metering_gets_403_on_usage(self):
        customer = Customer.objects.create(
            tenant=self.tenant_no_metering, external_id="cust_no_met"
        )
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(customer.id),
                "request_id": "req_gate_1",
                "idempotency_key": "idem_gate_1",
                "cost_micros": 1_000_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_tenant_with_metering_can_record_usage(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_met_1",
                "idempotency_key": "idem_met_1",
                "cost_micros": 1_500_000,
                "metadata": {"model": "gpt-4"},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIsNone(body["new_balance_micros"])
        self.assertIn("event_id", body)

    def test_tenant_without_metering_gets_403_on_usage_history(self):
        customer = Customer.objects.create(
            tenant=self.tenant_no_metering, external_id="cust_no_met2"
        )
        response = self.http_client.get(
            f"/api/v1/metering/customers/{customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_no}",
        )
        self.assertEqual(response.status_code, 403)

    def test_tenant_with_metering_can_get_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key_yes}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)
