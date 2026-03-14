"""End-to-end product isolation tests for subscriptions (Task 14).

Verifies that product-gated endpoints correctly enforce access based on
the tenant's products field, specifically for the subscriptions product.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


class TestSubscriptionsProductIsolation(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_metering_only_tenant_gets_403_on_subscriptions(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_billing_tenant_gets_403_on_subscriptions(self):
        tenant = Tenant.objects.create(
            name="billing-tenant", products=["metering", "billing"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_subscriptions_tenant_can_access_subscriptions(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertNotEqual(response.status_code, 403)

    def test_subscriptions_tenant_gets_403_on_billing(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = self.http_client.get(
            f"/api/v1/billing/customers/{customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_subscriptions_tenant_can_access_metering(self):
        tenant = Tenant.objects.create(
            name="sub-tenant", products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        from apps.metering.pricing.models import ProviderRate
        ProviderRate.objects.create(
            tenant=tenant,
            provider="test_provider",
            event_type="test_event",
            metric_name="tokens",
            dimensions={},
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )

        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(customer.id),
                "request_id": "req-isolation-1",
                "idempotency_key": "idem-isolation-1",
                "event_type": "test_event",
                "provider": "test_provider",
                "usage_metrics": {"tokens": 1},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 200)
