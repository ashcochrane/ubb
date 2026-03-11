from datetime import date

import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.queries import (
    get_customer_economics,
    get_economics_summary,
    get_customer_subscription,
)
from apps.subscriptions.models import StripeSubscription


@pytest.mark.django_db
class TestGetCustomerEconomics:
    def test_returns_none_when_no_data(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_economics(
            tenant.id, customer.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result is None


@pytest.mark.django_db
class TestGetEconomicsSummary:
    def test_returns_zeros_when_no_data(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "subscriptions"])
        result = get_economics_summary(
            tenant.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result == {
            "total_revenue_micros": 0,
            "total_cost_micros": 0,
            "total_margin_micros": 0,
            "customer_count": 0,
        }

    def test_aggregates_multiple_customers(self):
        from apps.subscriptions.economics.models import CustomerEconomics

        tenant = Tenant.objects.create(name="Test", products=["metering", "subscriptions"])
        c1 = Customer.objects.create(tenant=tenant, external_id="c1")
        c2 = Customer.objects.create(tenant=tenant, external_id="c2")

        CustomerEconomics.objects.create(
            tenant=tenant, customer=c1,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subscription_revenue_micros=100_000_000,
            usage_cost_micros=30_000_000,
            gross_margin_micros=70_000_000,
            margin_percentage=70,
        )
        CustomerEconomics.objects.create(
            tenant=tenant, customer=c2,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subscription_revenue_micros=200_000_000,
            usage_cost_micros=80_000_000,
            gross_margin_micros=120_000_000,
            margin_percentage=60,
        )

        result = get_economics_summary(
            tenant.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result == {
            "total_revenue_micros": 300_000_000,
            "total_cost_micros": 110_000_000,
            "total_margin_micros": 190_000_000,
            "customer_count": 2,
        }


@pytest.mark.django_db
class TestGetCustomerSubscription:
    def test_returns_none_when_no_subscription(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_subscription(tenant.id, customer.id)
        assert result is None

    def test_returns_latest_subscription(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(
            tenant=tenant,
            customer=customer,
            stripe_subscription_id="sub_123",
            stripe_product_name="Pro",
            status="active",
            amount_micros=100_000_000,
            interval="month",
            current_period_start=now,
            current_period_end=now,
            last_synced_at=now,
        )
        result = get_customer_subscription(tenant.id, customer.id)
        assert result.id == sub.id
