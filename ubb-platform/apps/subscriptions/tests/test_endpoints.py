import pytest
import json
from datetime import date
from django.utils import timezone
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer


class TestSubscriptionDataEndpoints(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        _, self.raw_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1",
        )

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

    def test_subscription_detail_no_subscription_is_not_found_problem(self):
        """No subscription for the customer → 404 problem+json (#78 dialect)."""
        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{self.customer.id}/subscription",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["code"], "not_found")
        self.assertEqual(body["status"], 404)

    def test_invoices_bad_cursor_is_invalid_cursor_problem(self):
        """A malformed cursor → 400 invalid_cursor problem+json (#78 dialect)."""
        response = self.http_client.get(
            f"/api/v1/subscriptions/customers/{self.customer.id}/invoices",
            {"cursor": "not-a-cursor"},
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response["Content-Type"], "application/problem+json")
        body = response.json()
        self.assertEqual(body["code"], "invalid_cursor")
        self.assertEqual(body["status"], 400)
