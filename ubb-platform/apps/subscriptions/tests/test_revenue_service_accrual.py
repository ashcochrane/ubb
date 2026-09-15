import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.economics.revenue import RevenueService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)  # full June


@pytest.mark.django_db
class TestAccrual:
    # THE POSTURE RESOLVER'S CASE WAS HERE AND IS GONE (#497, slice 7 §9). It
    # drove the rule this class's subject no longer has: a per-customer
    # override of whether usage counted as revenue, falling back to the
    # tenant's billing mode. Nothing here resolves revenue existence from a
    # billing mode any more, so there is no rule left to drive — and its
    # replacement is not another case in this module but
    # `test_who_invoices_decides_only_who_invoices.py`, which asserts that the
    # two postures get one answer rather than that the resolver picks between
    # them correctly.

    def test_subscription_nominal_full_month(self):
        # amount_micros now holds the FULL per-interval total; quantity is informational and
        # must NOT be multiplied in (it is already summed into amount_micros by _sum_items).
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_1",
            stripe_product_name="Pro", status="active", amount_micros=130_000_000, quantity=10,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 130_000_000

    def test_unpaid_subscription_included(self):
        # During a failed-payment window Stripe marks the subscription `unpaid`;
        # the postpaid push still includes it, so accrued nominal must too.
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_u",
            stripe_product_name="Pro", status="unpaid", amount_micros=130_000_000, quantity=10,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 130_000_000

    def test_canceled_subscription_excluded(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_x",
            stripe_product_name="Pro", status="canceled", amount_micros=10_000_000, quantity=3,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 0
