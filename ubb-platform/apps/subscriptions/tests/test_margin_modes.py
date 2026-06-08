import datetime
import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.subscriptions.economics.services import MarginService

PS, PE = datetime.date(2026, 6, 1), datetime.date(2026, 7, 1)


def _usage(t, c, provider, billed):
    UsageEvent.objects.create(tenant=t, customer=c, request_id="r", idempotency_key="i",
                              provider_cost_micros=provider, billed_cost_micros=billed)


@pytest.mark.django_db
class TestMarginModes:
    def test_metering_only_subtracts_cogs(self):
        from apps.subscriptions.economics.models import CustomerRevenueProfile
        t = Tenant.objects.create(name="MO", billing_mode="meter_only")
        c = Customer.objects.create(tenant=t, external_id="c1")
        CustomerRevenueProfile.objects.create(tenant=t, customer=c, recurring_amount_micros=100,
                                              effective_from=PS)
        _usage(t, c, provider=30, billed=30)
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        assert d["revenue_mode"] == "metered_only"
        assert d["gross_margin_micros"] == 70  # was 100 — COGS now visible

    def test_billed_uses_nominal_sub_not_paid_invoice(self):
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        now = timezone.now()
        sub = StripeSubscription.objects.create(tenant=t, customer=c, stripe_subscription_id="s1",
            stripe_product_name="Pro", status="active", amount_micros=20_000_000, quantity=1,
            currency="usd", interval="month", current_period_start=now, current_period_end=now,
            last_synced_at=now)
        SubscriptionInvoice.objects.create(tenant=t, customer=c, stripe_subscription=sub,
            stripe_invoice_id="in_1", amount_paid_micros=25_000_000, currency="usd",
            period_start=now, period_end=now, paid_at=now)
        _usage(t, c, provider=3_000_000, billed=5_000_000)
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        assert d["gross_margin_micros"] == 22_000_000  # nominal 20M + billed 5M - provider 3M
        assert d["total_revenue_micros"] == 25_000_000

    def test_metering_only_override_on_billed_tenant(self):
        t = Tenant.objects.create(name="PP", products=["metering", "billing"], billing_mode="postpaid")
        c = Customer.objects.create(tenant=t, external_id="c1", revenue_mode="metered_only")
        _usage(t, c, provider=30, billed=80)
        d = MarginService.compute_live(t.id, c.id, PS, PE)
        assert d["gross_margin_micros"] == -30 and d["usage_revenue_micros"] == 0
