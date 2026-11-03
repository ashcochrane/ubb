"""The subscription webhook handlers, driven with the REAL stripe-python object
model (Stage C1a, F-3b).

Every event is a genuine ``stripe.Event`` whose ``data.object`` is a real
``stripe.Subscription`` — a StripeObject with no ``.get``, whose
``pause_collection`` is a StripeObject when present and whose ``price.product``
is a ``Product`` object only when expanded. Before C1a the handlers read
``.get(...)`` and every genuine ``customer.subscription.created`` /
``updated`` answered a retryable 500 (findings F-3b).
"""
import pytest
import stripe
from unittest.mock import MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.tests._helpers import (
    a_licensed_item, a_mirrored_subscription, a_subscription_dict,
    a_subscription_event)


def _sub_event(account, sub_id, customer, status, *, items, kind="customer.subscription.created",
               **extra):
    """A real webhook event whose data.object is a Basil-shaped subscription (items.data[])."""
    return a_subscription_event(
        f"evt_{sub_id}", kind,
        a_subscription_dict(sub_id, customer, status, items=items, **extra),
        account=account)


@pytest.mark.django_db
class TestHandleSubscriptionCreated:
    def test_creates_local_mirror(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_123",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_abc",
        )

        event = _sub_event("acct_123", "sub_new", "cus_abc", "active", items=[
            a_licensed_item(4900, qty=1, product_name="Pro Plan"),  # access $49
            a_licensed_item(0, qty=5),                              # 5 seats @ $0
        ])
        real = event.data.object
        assert isinstance(real, stripe.Subscription) and not hasattr(real, "get")

        handle_subscription_created(event)

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_new")
        assert sub.tenant == tenant
        assert sub.customer == customer
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000  # 4900 cents * 10_000
        assert sub.status == "active"
        assert sub.quantity == 5

    def test_an_unexpanded_product_id_leaves_the_name_blank(self):
        """Stripe sends ``price.product`` as an id string unless expanded; a
        string has no name — never a crash, never the id as a name."""
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "billing"],
            stripe_connected_account_id="acct_unexp")
        Customer.objects.create(tenant=tenant, external_id="cust-1", stripe_customer_id="cus_unexp")
        event = _sub_event("acct_unexp", "sub_unexp", "cus_unexp", "active",
                           items=[a_licensed_item(4900, qty=1)])
        assert isinstance(event.data.object.items.data[0].price.product, str)
        handle_subscription_created(event)
        assert StripeSubscription.objects.get(stripe_subscription_id="sub_unexp").stripe_product_name == ""

    def test_duplicate_delivery_is_idempotent(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_dup",
        )
        Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_dup",
        )

        event = _sub_event("acct_dup", "sub_dup", "cus_dup", "active", items=[
            a_licensed_item(4900, qty=1, product_name="Pro Plan"),
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
            name="test", products=["metering", "billing"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_upd",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = _sub_event(None, "sub_upd", customer.stripe_customer_id, "past_due",
                           kind="customer.subscription.updated", items=[
            a_licensed_item(4900, qty=1, product_name="Pro"),  # access $49
            a_licensed_item(1000, qty=4),                      # grew to 4 seats @ $10
        ])

        handle_subscription_updated(event)

        sub.refresh_from_db()
        assert sub.status == "past_due"
        # update re-sums the items, so amount_micros + seat qty reflect the new shape
        assert sub.amount_micros == (4900 + 1000 * 4) * 10_000
        assert sub.quantity == 4

    def test_copies_lifecycle_flags_into_mirror(self):
        """F5.4: cancel_at_period_end + pause_collection presence -> mirror flags.
        On the real object ``pause_collection`` is a StripeObject when present
        (truthy even when empty) and None when Stripe reports it gone."""
        from apps.subscriptions.api.webhooks import handle_subscription_updated
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()
        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_flags",
            stripe_product_name="Pro", status="active",
            amount_micros=49_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        event = _sub_event(None, "sub_flags", "", "active",
                           kind="customer.subscription.updated",
                           cancel_at_period_end=True,
                           pause_collection={"behavior": "void", "resumes_at": None},
                           items=[a_licensed_item(4900, qty=1)])
        assert isinstance(event.data.object.pause_collection, stripe.StripeObject)
        handle_subscription_updated(event)

        sub.refresh_from_db()
        assert sub.status == "active"  # Stripe keeps active under pause/pending-cancel
        assert sub.cancel_at_period_end is True
        assert sub.paused is True

        # Flags clear when Stripe reports them gone (e.g. after resume).
        event = _sub_event(None, "sub_flags", "", "active",
                           kind="customer.subscription.updated",
                           cancel_at_period_end=False, pause_collection=None,
                           items=[a_licensed_item(4900, qty=1)])
        handle_subscription_updated(event)
        sub.refresh_from_db()
        assert sub.cancel_at_period_end is False
        assert sub.paused is False

    def test_flags_absent_from_the_object_read_as_clear(self):
        from apps.subscriptions.api.webhooks import handle_subscription_updated

        tenant = Tenant.objects.create(name="test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()
        sub = a_mirrored_subscription(
            tenant=tenant, customer=customer, stripe_subscription_id="sub_absent",
            stripe_product_name="Pro", status="active", amount_micros=49_000_000,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now, paused=True,
            cancel_at_period_end=True)
        event = _sub_event(None, "sub_absent", "", "active",
                           kind="customer.subscription.updated",
                           items=[a_licensed_item(4900, qty=1)])
        handle_subscription_updated(event)
        sub.refresh_from_db()
        assert (sub.cancel_at_period_end, sub.paused) == (False, False)


@pytest.mark.django_db
class TestHandleSubscriptionDeleted:
    def test_marks_as_canceled(self):
        from apps.subscriptions.api.webhooks import handle_subscription_deleted
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "billing"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        now = timezone.now()

        sub = a_mirrored_subscription(
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
            products=["metering", "billing"],
            stripe_connected_account_id="acct_no_cust",
        )

        event = MagicMock()
        event.account = "acct_no_cust"
        event.data.object.id = "sub_unknown"
        event.data.object.customer = "cus_nonexistent"

        with pytest.raises(Customer.DoesNotExist):
            handle_subscription_created(event)
