import pytest
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.queries import get_customer_subscription
from apps.subscriptions.models import StripeSubscription

# THE TWO SNAPSHOT READS' TESTS WERE HERE AND ARE GONE WITH THEM (#502, slice 7
# §8): one customer's stored margin row, and the tenant-wide total aggregated
# off the stored margin columns. Both are now `GET /metering/analytics/economics`
# — the first with `customer_id=` as a filter, the second with no grouping — and
# `api/v1/tests/test_a_closed_period_restates_when_its_facts_resolve.py` is where
# that answer is proved to move when a closed period's facts do.
#
# One claim outlived its reason and moved rather than going with them: that the
# stored cost column and its count are `NOT NULL`. It used to be why the
# tenant-wide `Sum` could report a total without reporting a floor; it is now
# what keeps the cost-spike ratio from dividing by an unknown, and it is
# asserted in `test_the_snapshot_is_an_alerting_record.py` beside the evaluator
# that depends on it.


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
