"""The poll sync, driven with the REAL stripe-python object model (Stage C1a,
F-3b / F-2).

``Subscription.list`` answers a genuine ``stripe.ListObject`` of
``stripe.Subscription``s built by ``construct_from`` — expanded as the sync
asks (``data.items.data.price.product``), so a product is a ``Product``
object and NOT a dict. The dict-subclass ``FakeStripeSub`` that lived here
kept the ``.get`` code green while every real object errored
(``{synced 0, skipped 1, errors 1}`` — findings F-3b); it is gone.
"""
import logging

import pytest
import stripe
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.tests._helpers import (
    SK, a_licensed_item, a_mirrored_subscription, a_subscription_dict)

SYNC = "apps.subscriptions.stripe.sync"


def _page(sub_dicts, *, has_more=False):
    """A genuine stripe.ListObject page of real Subscriptions."""
    return stripe.ListObject.construct_from(
        {"object": "list", "data": sub_dicts, "has_more": has_more,
         "url": "/v1/subscriptions"}, SK)


def _sub(id, customer, status, *, items, currency="usd"):
    return a_subscription_dict(id, customer, status, items=items, currency=currency)


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.django_db
class TestFullSync:
    def test_syncs_active_subscriptions(self):
        """One real expanded subscription → synced 1, product name kept."""
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_sync",
        )

        page = _page([_sub("sub_sync_1", "cus_sync", "active",
                           items=[a_licensed_item(19900, product_name="Enterprise")])])  # $199
        real = page.data[0]
        assert isinstance(real, stripe.Subscription) and not hasattr(real, "get")
        assert isinstance(real.items.data[0].price.product, stripe.Product)

        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page) as listed:
            result = sync_subscriptions(tenant)

        assert result == {"synced": 1, "skipped": 0, "errors": 0}
        # Through the wrapper (F-2): the key is the wrapper's kwarg.
        assert listed.call_args.kwargs["api_key"] == "sk_test_sentinel"
        assert listed.call_args.kwargs["expand"] == ["data.items.data.price.product"]

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_sync_1")
        assert sub.stripe_product_name == "Enterprise"
        assert sub.amount_micros == 199_000_000
        assert sub.current_period_start is not None

    def test_a_subscription_on_the_second_page_is_synced_too(self):
        """auto_paging_iter() fetches page two lazily through next_page."""
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "billing"],
            stripe_connected_account_id="acct_pages")
        for n in (1, 2):
            Customer.objects.create(tenant=tenant, external_id=f"cust-{n}",
                                    stripe_customer_id=f"cus_{n}")
        page1 = _page([_sub("sub_page_1", "cus_1", "active",
                            items=[a_licensed_item(1000, product_name="One")])], has_more=True)
        page2 = _page([_sub("sub_page_2", "cus_2", "active",
                            items=[a_licensed_item(2000, product_name="Two")])])
        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page1), \
             patch.object(stripe.ListObject, "next_page", side_effect=[page2, _page([])]):
            result = sync_subscriptions(tenant)
        assert result == {"synced": 2, "skipped": 0, "errors": 0}
        assert StripeSubscription.objects.get(
            stripe_subscription_id="sub_page_2").stripe_product_name == "Two"

    def test_a_failure_fetching_page_two_is_caught_inside_the_try(self):
        """A page-two fetch failure is the listing failing: errors 1, nothing
        raised, the partial page not acted on."""
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test", products=["metering", "billing"],
            stripe_connected_account_id="acct_page_fail")
        Customer.objects.create(tenant=tenant, external_id="cust-1", stripe_customer_id="cus_1")
        page1 = _page([_sub("sub_page_1", "cus_1", "active",
                            items=[a_licensed_item(1000, product_name="One")])], has_more=True)
        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page1), \
             patch.object(stripe.ListObject, "next_page",
                          side_effect=stripe.error.APIConnectionError("page two lost")):
            result = sync_subscriptions(tenant)  # no raise
        assert result == {"synced": 0, "skipped": 0, "errors": 1}
        assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_page_1").exists()

    def test_skips_subscription_with_unknown_customer(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test2",
        )

        page = _page([_sub("sub_unknown_cust", "cus_nobody", "active",
                           items=[a_licensed_item(4900, product_name="Pro")])])

        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page):
            result = sync_subscriptions(tenant)

        assert result["synced"] == 0
        assert result["skipped"] == 1
        assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_unknown_cust").exists()

    def test_updates_existing_subscription(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_test3",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_existing",
        )
        now = timezone.now()
        a_mirrored_subscription(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_exists",
            stripe_product_name="Old Plan", status="trialing",
            amount_micros=29_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        page = _page([_sub("sub_exists", "cus_existing", "active",
                           items=[a_licensed_item(4900, product_name="Pro Plan")])])

        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page):
            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_exists")
        assert sub.status == "active"
        assert sub.stripe_product_name == "Pro Plan"
        assert sub.amount_micros == 49_000_000

    def test_syncs_multi_item_subscription(self):
        # Multi-item sub: access ($10) + 3 seats ($10 each) -> amount = (1000 + 1000*3)*10_000,
        # seat_qty taken from the seat line (qty 3). Replaces the old single-`quantity` test:
        # the deprecated `subscription.plan` shape collapsed this to one item; we now sum items.
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_qty",
        )
        Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_qty",
        )

        page = _page([_sub("sub_qty_1", "cus_qty", "active", items=[
            a_licensed_item(1000, qty=1, product_name="Enterprise"),  # access $10
            a_licensed_item(1000, qty=3),                             # 3 seats @ $10
        ])])

        with patch(f"{SYNC}.stripe.Subscription.list", return_value=page):
            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_qty_1")
        assert sub.quantity == 3
        assert sub.amount_micros == (1000 + 1000 * 3) * 10_000

    def test_sync_handles_stripe_api_error(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_api_err",
        )

        with patch(f"{SYNC}.stripe.Subscription.list",
                   side_effect=stripe.error.APIError("Internal server error")):
            result = sync_subscriptions(tenant)

        assert result["errors"] == 1
        assert result["synced"] == 0

    def test_sync_handles_stripe_auth_error(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_auth_err",
        )

        with patch(f"{SYNC}.stripe.Subscription.list",
                   side_effect=stripe.error.AuthenticationError("Invalid API Key")):
            result = sync_subscriptions(tenant)

        assert result["errors"] == 1
        assert result["synced"] == 0

    def test_an_unset_live_key_never_reaches_transport(self, settings):
        """F-2: with STRIPE_SECRET_KEY unset the live tenant's list is refused
        by the wrapper before any request is built. Before C1a the raw SDK
        call sent the request with an empty key."""
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="test", products=["metering", "billing"],
            stripe_connected_account_id="acct_no_key")
        settings.STRIPE_SECRET_KEY = ""
        transport = MagicMock(name="request_raw")
        capture = _Capture()
        logging.getLogger(SYNC).addHandler(capture)
        try:
            with patch("stripe._api_requestor._APIRequestor.request_raw", transport):
                result = sync_subscriptions(tenant)
        finally:
            logging.getLogger(SYNC).removeHandler(capture)
        transport.assert_not_called()
        assert result == {"synced": 0, "skipped": 0, "errors": 1}
        assert [r.levelno for r in capture.records] == [logging.WARNING]
