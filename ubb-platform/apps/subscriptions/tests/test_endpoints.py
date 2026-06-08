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
