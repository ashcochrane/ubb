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
    def test_resolve_revenue_mode_default_and_override(self):
        t = Tenant.objects.create(name="MO", billing_mode="meter_only")
        c = Customer.objects.create(tenant=t, external_id="c1")
        assert RevenueService.resolve_revenue_mode(t, c) == "metered_only"
        tb = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        cb = Customer.objects.create(tenant=tb, external_id="c1")
        assert RevenueService.resolve_revenue_mode(tb, cb) == "billed"
        cb.revenue_mode = "metered_only"; cb.save(update_fields=["revenue_mode"])
        assert RevenueService.resolve_revenue_mode(tb, cb) == "metered_only"  # override wins

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

    def test_canceled_subscription_excluded(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="sub_x",
            stripe_product_name="Pro", status="canceled", amount_micros=10_000_000, quantity=3,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        assert RevenueService.subscription_nominal_for_window(t.id, c.id, PS, PE) == 0
