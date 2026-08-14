"""End-to-end product isolation tests for subscriptions (Task 14).

Verifies that product-gated endpoints correctly enforce access based on
the tenant's products field. Plan-as-kernel #8 moved subscriptions_router's
gate from the "subscriptions" product to "billing" (the write routes it now
shares were never separately gated at all). #9 then retired the
"subscriptions" product value itself, so a tenant can no longer be
configured with "subscriptions" and no "billing" — the test that asserted
that now-impossible config is gone; the two below cover the same ground
(metering-only refused, billing-tenant admitted) with configs that still
exist.
"""
import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.billing.wallets.models import Wallet


class TestSubscriptionsProductIsolation(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_metering_only_tenant_gets_403_on_subscriptions(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-iso-1")

        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{customer.id}/subscription",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        self.assertEqual(response.json()["code"], "feature_not_enabled")

    def test_billing_tenant_can_access_subscriptions(self):
        """Was "gets_403" — the whole point of #8 is that billing now covers
        the subscriptions surface it writes to, reads included."""
        tenant = Tenant.objects.create(
            name="billing-tenant", products=["metering", "billing"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-iso-2")

        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{customer.id}/subscription",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertNotEqual(response.status_code, 403)

    def test_metering_only_tenant_gets_403_on_billing(self):
        tenant = Tenant.objects.create(
            name="metering-only-2", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        response = self.http_client.get(
            f"/api/v1/billing/customers/{customer.id}/balance",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_billing_tenant_can_access_metering(self):
        tenant = Tenant.objects.create(
            name="billing-tenant-2", products=["metering", "billing"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 100_000_000
        wallet.save()
        declares_a_caller_supplied_cost(customer.tenant, DECLARED)

        response = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(customer.id),
                "request_id": "req-isolation-1",
                "idempotency_key": "idem-isolation-1",
                "event_type": DECLARED,
                "provider_cost_micros": 500_000,
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 200)
