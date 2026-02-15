import pytest
from unittest.mock import MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestHandleSubscriptionCreated:
    def test_creates_local_mirror(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_123",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_abc",
        )

        event = MagicMock()
        event.account = "acct_123"
        event.data.object.id = "sub_new"
        event.data.object.customer = "cus_abc"
        event.data.object.status = "active"
        event.data.object.current_period_start = 1738368000  # unix timestamp
        event.data.object.current_period_end = 1740960000
        event.data.object.plan.product.name = "Pro Plan"
        event.data.object.plan.amount = 4900  # cents
        event.data.object.plan.currency = "usd"
        event.data.object.plan.interval = "month"

        handle_subscription_created(event)

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_new")
        assert sub.tenant == tenant
        assert sub.customer == customer
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000  # 4900 cents * 10_000
        assert sub.status == "active"


    def test_duplicate_delivery_is_idempotent(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_dup",
        )
        Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_dup",
        )

        event = MagicMock()
        event.account = "acct_dup"
        event.data.object.id = "sub_dup"
        event.data.object.customer = "cus_dup"
        event.data.object.status = "active"
        event.data.object.current_period_start = 1738368000
        event.data.object.current_period_end = 1740960000
        event.data.object.plan.product.name = "Pro Plan"
        event.data.object.plan.amount = 4900
        event.data.object.plan.currency = "usd"
        event.data.object.plan.interval = "month"

        handle_subscription_created(event)
        handle_subscription_created(event)

        assert StripeSubscription.objects.filter(stripe_subscription_id="sub_dup").count() == 1


@pytest.mark.django_db
class TestHandleSubscriptionUpdated:
    def test_updates_existing_mirror(self):
        from apps.subscriptions.api.webhooks import handle_subscription_updated
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_upd",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "sub_upd"
        event.data.object.status = "past_due"
        event.data.object.current_period_start = 1738368000
        event.data.object.current_period_end = 1740960000

        handle_subscription_updated(event)

        sub.refresh_from_db()
        assert sub.status == "past_due"


@pytest.mark.django_db
class TestHandleSubscriptionDeleted:
    def test_marks_as_canceled(self):
        from apps.subscriptions.api.webhooks import handle_subscription_deleted
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_del",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "sub_del"

        handle_subscription_deleted(event)

        sub.refresh_from_db()
        assert sub.status == "canceled"


@pytest.mark.django_db
class TestHandleInvoicePaid:
    def test_creates_subscription_invoice(self):
        from apps.subscriptions.api.webhooks import handle_invoice_paid
        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice

        tenant = Tenant.objects.create(
            name="test", products=["metering", "subscriptions"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_inv",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = MagicMock()
        event.data.object.id = "in_paid123"
        event.data.object.subscription = "sub_inv"
        event.data.object.amount_paid = 4900  # cents
        event.data.object.currency = "usd"
        event.data.object.period_start = 1738368000
        event.data.object.period_end = 1740960000
        event.data.object.status_transitions.paid_at = 1738400000

        handle_invoice_paid(event)

        inv = SubscriptionInvoice.objects.get(stripe_invoice_id="in_paid123")
        assert inv.amount_paid_micros == 49_000_000
        assert inv.stripe_subscription == sub

    def test_skips_non_subscription_invoice(self):
        from apps.subscriptions.api.webhooks import handle_invoice_paid
        from apps.subscriptions.models import SubscriptionInvoice

        event = MagicMock()
        event.data.object.subscription = None  # Not a subscription invoice

        handle_invoice_paid(event)

        assert SubscriptionInvoice.objects.count() == 0

    def test_invoice_paid_raises_on_missing_subscription(self):
        from apps.subscriptions.api.webhooks import handle_invoice_paid
        from apps.subscriptions.models import StripeSubscription

        event = MagicMock()
        event.account = "acct_unknown"
        event.data.object.id = "in_missing_sub"
        event.data.object.subscription = "sub_nonexistent"

        with pytest.raises(StripeSubscription.DoesNotExist):
            handle_invoice_paid(event)


@pytest.mark.django_db
class TestSubscriptionCreatedUnknownCustomer:
    def test_subscription_created_raises_on_unknown_customer(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created

        Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_no_cust",
        )

        event = MagicMock()
        event.account = "acct_no_cust"
        event.data.object.id = "sub_unknown"
        event.data.object.customer = "cus_nonexistent"

        with pytest.raises(Customer.DoesNotExist):
            handle_subscription_created(event)
