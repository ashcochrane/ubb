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
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_economics(
            tenant.id, customer.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result is None


@pytest.mark.django_db
class TestGetEconomicsSummary:
    def test_returns_zeros_when_no_data(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        result = get_economics_summary(
            tenant.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result == {
            "subscription_revenue_micros": 0,
            "usage_billed_micros": 0,
            "provider_cost_micros": 0,
            # A window with no snapshots excluded nothing — the empty sum is
            # complete, and this is the zero that says so (#328).
            "unresolved_event_count": 0,
            "total_margin_micros": 0,
            "customer_count": 0,
        }

    def test_aggregates_multiple_customers(self):
        from apps.subscriptions.economics.models import CustomerEconomics

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        c1 = Customer.objects.create(tenant=tenant, external_id="c1")
        c2 = Customer.objects.create(tenant=tenant, external_id="c2")

        CustomerEconomics.objects.create(
            tenant=tenant, customer=c1,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subscription_revenue_micros=100_000_000,
            usage_billed_micros=30_000_000,
            provider_cost_micros=20_000_000,
            gross_margin_micros=110_000_000,
            margin_percentage=70,
        )
        CustomerEconomics.objects.create(
            tenant=tenant, customer=c2,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            subscription_revenue_micros=200_000_000,
            usage_billed_micros=80_000_000,
            provider_cost_micros=60_000_000,
            # One of the two customers' months excluded a cost, so the tenant's
            # total is a floor by exactly that much (#328).
            unresolved_event_count=3,
            gross_margin_micros=220_000_000,
            margin_percentage=60,
        )

        result = get_economics_summary(
            tenant.id,
            date(2026, 1, 1), date(2026, 2, 1),
        )
        assert result == {
            "subscription_revenue_micros": 300_000_000,
            "usage_billed_micros": 110_000_000,
            "provider_cost_micros": 80_000_000,
            "unresolved_event_count": 3,
            "total_margin_micros": 330_000_000,
            "customer_count": 2,
        }

    def test_this_totals_completeness_is_inherited_rather_than_measured(self):
        """Why this one total's count comes from a column (#327, #328).

        Every supplier-cost total in the tree reports the count of postings it
        excluded, because the posting's column is nullable and SQL skips nulls
        silently. This total does not sum that column — it sums a monthly
        SNAPSHOT of it, which cannot be unknown, so null-skipping can never
        reach it and its own `Sum` is complete by construction. #327 therefore
        left it a single figure rather than publishing a zero nothing computed.

        What changed in #328 is upstream: the accumulator these snapshots are
        built from now counts the costs it could not add, and the snapshot
        freezes that count. So the pair here is REAL and inherited — the sum of
        numbers each row measured — rather than derived from the nullness of
        anything in this query.

        Both halves are asserted, because either one going false would make the
        read contract's docstring wrong in a different way: if the cost column
        became nullable the figure would need a count of its OWN, and if the
        count column went away there would be nothing to inherit.
        """
        from apps.subscriptions.economics.models import CustomerEconomics

        cost = CustomerEconomics._meta.get_field("provider_cost_micros")
        assert cost.null is False
        count = CustomerEconomics._meta.get_field("unresolved_event_count")
        assert count.null is False


@pytest.mark.django_db
class TestGetCustomerSubscription:
    def test_returns_none_when_no_subscription(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        result = get_customer_subscription(tenant.id, customer.id)
        assert result is None

    def test_returns_latest_subscription(self):
        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
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
