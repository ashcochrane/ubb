import pytest
from unittest.mock import MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.tests.test_sync import FakeStripeSub, _licensed_item


def _sub_event(account, sub_id, customer, status, *, items):
    """Build a webhook event whose data.object is a Basil-shaped subscription (items.data[])."""
    event = MagicMock()
    event.account = account
    event.data.object = FakeStripeSub(
        id=sub_id, customer=customer, status=status, currency="usd",
        items={"data": items})
    return event


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

        event = _sub_event("acct_123", "sub_new", "cus_abc", "active", items=[
            _licensed_item(4900, qty=1, product_name="Pro Plan"),  # access $49
            _licensed_item(0, qty=5),                              # 5 seats @ $0
        ])

        handle_subscription_created(event)

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_new")
        assert sub.tenant == tenant
        assert sub.customer == customer
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000  # 4900 cents * 10_000
        assert sub.status == "active"
        assert sub.quantity == 5


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

        event = _sub_event("acct_dup", "sub_dup", "cus_dup", "active", items=[
            _licensed_item(4900, qty=1, product_name="Pro Plan"),
        ])

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

        event = _sub_event(None, "sub_upd", customer.stripe_customer_id, "past_due", items=[
            _licensed_item(4900, qty=1, product_name="Pro"),  # access $49
            _licensed_item(1000, qty=4),                      # grew to 4 seats @ $10
        ])

        handle_subscription_updated(event)

        sub.refresh_from_db()
        assert sub.status == "past_due"
        # update re-sums the items, so amount_micros + seat qty reflect the new shape
        assert sub.amount_micros == (4900 + 1000 * 4) * 10_000
        assert sub.quantity == 4


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
