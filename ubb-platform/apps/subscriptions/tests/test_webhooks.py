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


# NOTE: invoice.paid handling was retired from the subscriptions endpoint (C-1).
# ALL invoice.* reconcile — including SubscriptionInvoice creation + payment
# status — now lives on api/v1; see api/v1/tests/test_ar_reconcile.py.


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
