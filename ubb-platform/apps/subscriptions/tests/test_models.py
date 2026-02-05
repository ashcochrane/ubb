import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestStripeSubscription:
    def test_create_stripe_subscription(self):
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_123abc",
            stripe_product_name="Pro Plan", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        sub.refresh_from_db()
        assert sub.stripe_subscription_id == "sub_123abc"
        assert sub.status == "active"
        assert sub.amount_micros == 49_000_000

    def test_stripe_subscription_id_is_unique(self):
        from apps.subscriptions.models import StripeSubscription
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        with pytest.raises(IntegrityError):
            StripeSubscription.objects.create(
                tenant=tenant, customer=customer,
                stripe_subscription_id="sub_dup",
                stripe_product_name="Plan", status="active",
                amount_micros=10_000_000, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now,
            )


@pytest.mark.django_db
class TestSubscriptionInvoice:
    def test_create_subscription_invoice(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_test",
            stripe_product_name="Enterprise", status="active",
            amount_micros=199_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        invoice = SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_abc123", amount_paid_micros=199_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now,
        )
        invoice.refresh_from_db()
        assert invoice.stripe_invoice_id == "in_abc123"
        assert invoice.amount_paid_micros == 199_000_000

    def test_stripe_invoice_id_is_unique(self):
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv_dup",
            stripe_product_name="Plan", status="active",
            amount_micros=10_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )
        SubscriptionInvoice.objects.create(
            tenant=tenant, customer=customer, stripe_subscription=sub,
            stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
            currency="usd", period_start=now, period_end=now, paid_at=now,
        )
        with pytest.raises(IntegrityError):
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=customer, stripe_subscription=sub,
                stripe_invoice_id="in_dup", amount_paid_micros=10_000_000,
                currency="usd", period_start=now, period_end=now, paid_at=now,
            )


@pytest.mark.django_db
class TestCustomerCostAccumulator:
    def test_create_accumulator(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        acc = CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            total_cost_micros=5_000_000, event_count=10,
        )
        acc.refresh_from_db()
        assert acc.total_cost_micros == 5_000_000
        assert acc.event_count == 10

    def test_accumulator_unique_constraint(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator
        from django.db import IntegrityError
        from datetime import date

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        CustomerCostAccumulator.objects.create(
            tenant=tenant, customer=customer,
            period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
        )
        with pytest.raises(IntegrityError):
            CustomerCostAccumulator.objects.create(
                tenant=tenant, customer=customer,
                period_start=date(2026, 1, 1), period_end=date(2026, 2, 1),
            )
