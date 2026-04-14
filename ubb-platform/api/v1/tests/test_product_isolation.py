"""End-to-end product isolation tests (Task 26).

Verifies that product-gated endpoints correctly enforce access based on
the tenant's products field.
"""
import json
from unittest.mock import patch

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.models import Card, Rate


class TestMeteringOnlyTenant(TestCase):
    """Tenant with products=["metering"] can use metering endpoints but not billing."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Metering Only", products=["metering"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_met_only"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=card,
            metric_name="tokens",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_can_record_usage_on_metering_endpoint(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_iso_1",
                "idempotency_key": "idem_iso_1",
                "event_type": "test_event",
                "provider": "test_provider",
                "usage_metrics": {"tokens": 1},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("event_id", body)

    def test_can_get_usage_history_on_metering_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)

    def test_gets_403_on_billing_balance(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_gets_403_on_billing_pre_check(self):
        response = self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_gets_403_on_billing_transactions(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_gets_403_on_billing_auto_topup(self):
        response = self.http_client.put(
            f"/api/v1/billing/customers/{self.customer.id}/auto-top-up",
            data=json.dumps({
                "is_enabled": True,
                "trigger_threshold_micros": 5_000_000,
                "top_up_amount_micros": 50_000_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)


class TestBillingOnlyTenant(TestCase):
    """Tenant with products=["billing"] can use billing endpoints but not metering."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Billing Only", products=["billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_bill_only"
        )

    def test_can_check_balance_on_billing_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("balance_micros", body)
        self.assertIn("currency", body)

    def test_can_pre_check_on_billing_endpoint(self):
        response = self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("allowed", body)

    def test_can_list_transactions_on_billing_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)

    def test_can_list_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/billing/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("data", body)
        self.assertIn("has_more", body)

    def test_gets_403_on_metering_usage(self):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_iso_2",
                "idempotency_key": "idem_iso_2",
                "event_type": "test_event",
                "provider": "test_provider",
                "usage_metrics": {"tokens": 1},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_gets_403_on_metering_usage_history(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 403)


class TestBothProductsTenant(TestCase):
    """Tenant with products=["metering", "billing"] can use both endpoints."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Both Products", products=["metering", "billing"]
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(
            self.tenant, label="test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_both"
        )
        wallet = Wallet.objects.create(customer=self.customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=card,
            metric_name="tokens",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_can_record_usage_on_metering_endpoint(self, mock_process):
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_both_1",
                "idempotency_key": "idem_both_1",
                "event_type": "test_event",
                "provider": "test_provider",
                "usage_metrics": {"tokens": 1},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)

    def test_can_get_usage_history_on_metering_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)

    def test_can_check_balance_on_billing_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body["balance_micros"], 10_000_000)

    def test_can_pre_check_on_billing_endpoint(self):
        response = self.http_client.post(
            "/api/v1/billing/pre-check",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)

    def test_can_list_transactions_on_billing_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/transactions",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_can_record_usage_then_check_balance(self, mock_process):
        """Cross-product workflow: record usage via metering, check balance via billing.

        After decoupling, metering does NOT deduct the wallet. Wallet balance
        stays unchanged until billing's outbox handler processes the event.
        """
        # Record usage
        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "request_id": "req_cross_1",
                "idempotency_key": "idem_cross_1",
                "event_type": "test_event",
                "provider": "test_provider",
                "usage_metrics": {"tokens": 2},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)

        # Balance unchanged (billing handles deduction via outbox)
        response = self.http_client.get(
            f"/api/v1/billing/customers/{self.customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        balance_body = response.json()
        self.assertEqual(balance_body["balance_micros"], 10_000_000)
