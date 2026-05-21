import uuid as _uuid
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.pricing.models import Card
from apps.metering.usage.models import UsageEvent
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey


def _create_event(tenant, customer, card=None, days_ago=0, billed=1000, provider_cost=800, group=None):
    event = UsageEvent.objects.create(
        tenant=tenant,
        customer=customer,
        request_id=f"req_{_uuid.uuid4().hex[:8]}",
        idempotency_key=f"idem_{_uuid.uuid4().hex[:8]}",
        cost_micros=billed,
        provider=card.provider if card else "",
        provider_cost_micros=provider_cost,
        billed_cost_micros=billed,
        card=card,
        group=group,
    )
    if days_ago > 0:
        target = timezone.now() - timedelta(days=days_ago)
        UsageEvent.objects.filter(id=event.id).update(effective_at=target)
    return event


@pytest.mark.django_db
class TestDashboardStats:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="DashTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1",
        )
        self.client = Client()

    def test_stats_endpoint_returns_200(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4",
            slug="gpt4",
            provider="openai",
        )
        _create_event(
            self.tenant, self.customer, card=card,
            days_ago=5, billed=10000, provider_cost=6000, group="research",
        )

        resp = self.client.get(
            "/api/v1/platform/dashboard/stats?range=30d",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revenueMicros"] == 10000
        assert data["apiCostsMicros"] == 6000
        assert data["grossMarginMicros"] == 4000
        assert data["marginPercentage"] == 40.0
        assert "sparklines" in data
        assert len(data["sparklines"]["revenue"]) >= 1

    def test_stats_empty_returns_zeros(self):
        resp = self.client.get(
            "/api/v1/platform/dashboard/stats?range=30d",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["revenueMicros"] == 0
        assert data["apiCostsMicros"] == 0
        assert data["grossMarginMicros"] == 0
        assert data["marginPercentage"] == 0.0
        assert data["costPerDollarRevenue"] == 0.0
        assert data["sparklines"]["revenue"] == []


@pytest.mark.django_db
class TestDashboardCharts:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="ChartTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1",
        )
        self.client = Client()

    def test_charts_endpoint_returns_200(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            slug="gemini_flash",
            provider="google",
        )
        _create_event(
            self.tenant, self.customer, card=card,
            days_ago=2, billed=5000, provider_cost=3000, group="research",
        )

        resp = self.client.get(
            "/api/v1/platform/dashboard/charts?range=30d",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "revenueTimeSeries" in data
        assert "costByGroup" in data
        assert "costByCard" in data
        assert "revenueByGroup" in data
        assert "marginByGroup" in data
        assert len(data["revenueTimeSeries"]) >= 1

    def test_cost_by_group_stacked_series_shape(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4",
            slug="gpt4",
            provider="openai",
        )
        # Two events in different groups on the same day
        _create_event(
            self.tenant, self.customer, card=card,
            days_ago=3, billed=5000, provider_cost=3000, group="research",
        )
        _create_event(
            self.tenant, self.customer, card=card,
            days_ago=3, billed=4000, provider_cost=2000, group="chat",
        )

        resp = self.client.get(
            "/api/v1/platform/dashboard/charts?range=30d",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        cbg = resp.json()["costByGroup"]

        # Check series has both groups
        series_keys = {s["key"] for s in cbg["series"]}
        assert "research" in series_keys
        assert "chat" in series_keys

        # Check data rows have all keys present
        for row in cbg["data"]:
            assert "date" in row
            for key in series_keys:
                assert key in row


@pytest.mark.django_db
class TestDashboardCustomers:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="CustTest",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_customers_endpoint_returns_data(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme_corp",
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4",
            slug="gpt4",
            provider="openai",
        )
        _create_event(
            self.tenant, customer, card=card,
            days_ago=5, billed=10000, provider_cost=6000, group="research",
        )

        resp = self.client.get(
            "/api/v1/platform/dashboard/customers?range=30d",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["customers"]) == 1
        row = data["customers"][0]
        assert row["externalId"] == "acme_corp"
        assert row["revenueMicros"] == 10000
        assert row["apiCostsMicros"] == 6000
        assert row["marginMicros"] == 4000
        assert row["marginPercentage"] == 40.0
        assert row["eventCount"] == 1
