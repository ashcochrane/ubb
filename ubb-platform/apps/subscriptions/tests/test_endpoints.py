import pytest
import json
from datetime import date
from django.utils import timezone
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class TestSubscriptionsProductAccess(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_returns_403_without_subscriptions_product(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_allows_subscriptions_tenant(self):
        tenant = Tenant.objects.create(
            name="sub-tenant",
            products=["metering", "subscriptions"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        # Should not be 403 (may be 200 with empty data)
        self.assertNotEqual(response.status_code, 403)


class TestEconomicsEndpoints(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        _, self.raw_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1",
        )

    def test_economics_returns_customer_data(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_ep_1",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        today = timezone.now().date()
        period_start = today.replace(day=1)
        SubscriptionInvoice.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription=sub,
            stripe_invoice_id="in_ep_1",
            amount_paid_micros=49_000_000, currency="usd",
            period_start=timezone.make_aware(
                timezone.datetime(period_start.year, period_start.month, 1)
            ),
            period_end=now,
            paid_at=now,
        )
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=period_start,
            period_end=period_start.replace(
                month=period_start.month + 1 if period_start.month < 12 else 1,
                year=period_start.year if period_start.month < 12 else period_start.year + 1,
            ),
            total_cost_micros=20_000_000, event_count=200,
        )

        response = self.http_client.get(
            "/api/v1/subscriptions/economics",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIn("customers", body)
        self.assertEqual(len(body["customers"]), 1)
        self.assertEqual(body["customers"][0]["subscription_revenue_micros"], 49_000_000)

    def test_customer_economics_endpoint(self):
        response = self.http_client.get(
            f"/api/v1/subscriptions/economics/{self.customer.id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        # Should return 200 even with no data
        self.assertEqual(response.status_code, 200)

    def test_subscription_detail_endpoint(self):
        from apps.subscriptions.models import StripeSubscription

        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_detail",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{self.customer.id}/subscription",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
