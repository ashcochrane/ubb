import pytest
from datetime import date
from decimal import Decimal
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestEconomicsService:
    def _create_tenant_and_customer(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        return tenant, customer

    def test_calculates_profitable_customer(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, customer = self._create_tenant_and_customer()
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        # Subscription: $199/mo
        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_econ_1",
            stripe_product_name="Enterprise", status="active",
            amount_micros=199_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_econ_1",
            amount_paid_micros=199_000_000,
            currency="usd",
            period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
            period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
            paid_at=now,
        )

        # Usage cost: $47.20
        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=47_200_000, event_count=500,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.subscription_revenue_micros == 199_000_000
        assert result.usage_cost_micros == 47_200_000
        assert result.gross_margin_micros == 151_800_000
        assert result.margin_percentage == Decimal("76.28")

    def test_calculates_unprofitable_customer(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, customer = self._create_tenant_and_customer()
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_econ_2",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_econ_2",
            amount_paid_micros=49_000_000, currency="usd",
            period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
            period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
            paid_at=now,
        )
        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=62_300_000, event_count=1000,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.gross_margin_micros == -13_300_000
        assert result.margin_percentage == Decimal("-27.14")

    def test_zero_revenue_gives_zero_margin(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant, customer = self._create_tenant_and_customer()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=period_start, period_end=period_end,
            total_cost_micros=10_000_000, event_count=100,
        )

        result = EconomicsService.calculate_customer_economics(
            tenant.id, customer.id, period_start, period_end,
        )

        assert result.subscription_revenue_micros == 0
        assert result.usage_cost_micros == 10_000_000
        assert result.gross_margin_micros == -10_000_000
        assert result.margin_percentage == Decimal("0")  # Can't divide by zero revenue

    def test_calculate_all_economics(self):
        from apps.subscriptions.economics.services import EconomicsService
        from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerEconomics
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant, cust1 = self._create_tenant_and_customer()
        cust2 = Customer.objects.create(tenant=tenant, external_id="cust-2")
        now = timezone.now()
        period_start = date(2026, 1, 1)
        period_end = date(2026, 2, 1)

        for i, (cust, sub_id, inv_id, rev, cost) in enumerate([
            (cust1, "sub_all_1", "in_all_1", 199_000_000, 47_200_000),
            (cust2, "sub_all_2", "in_all_2", 49_000_000, 62_300_000),
        ]):
            sub = StripeSubscription.objects.create(
                tenant=tenant, customer=cust,
                stripe_subscription_id=sub_id,
                stripe_product_name="Plan", status="active",
                amount_micros=rev, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now,
            )
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=cust, stripe_subscription=sub,
                stripe_invoice_id=inv_id, amount_paid_micros=rev, currency="usd",
                period_start=timezone.make_aware(timezone.datetime(2026, 1, 1)),
                period_end=timezone.make_aware(timezone.datetime(2026, 2, 1)),
                paid_at=now,
            )
            CustomerCostAccumulator.objects.create(
                tenant=tenant, customer=cust,
                period_start=period_start, period_end=period_end,
                total_cost_micros=cost, event_count=100,
            )

        results = EconomicsService.calculate_all_economics(
            tenant.id, period_start, period_end,
        )

        assert len(results) == 2
        assert CustomerEconomics.objects.filter(tenant=tenant).count() == 2
