import pytest
import stripe
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


class FakeStripeSub(dict):
    """Mimics a Stripe Subscription object (Basil shape): attribute access for top-level
    scalars AND dict/index access for nested resources (items.data[]), like a real StripeObject."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

    def __getattr__(self, name):
        try:
            return self[name]
        except KeyError as exc:
            raise AttributeError(name) from exc


def _sub(id, customer, status, *, items, currency="usd"):
    return FakeStripeSub(id=id, customer=customer, status=status, currency=currency,
                         items={"data": items})


def _licensed_item(unit_amount, qty=1, *, interval="month", product_name=None,
                   period_start=1738368000, period_end=1740960000):
    price = {"unit_amount": unit_amount,
             "recurring": {"interval": interval, "usage_type": "licensed"}}
    if product_name is not None:
        price["product"] = {"name": product_name}
    return {"price": price, "quantity": qty,
            "current_period_start": period_start, "current_period_end": period_end}


@pytest.mark.django_db
class TestFullSync:
    def test_syncs_active_subscriptions(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_sync",
        )

        mock_sub = _sub("sub_sync_1", "cus_sync", "active",
                        items=[_licensed_item(19900, product_name="Enterprise")])  # $199

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        assert result["skipped"] == 0

        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_sync_1")
        assert sub.stripe_product_name == "Enterprise"
        assert sub.amount_micros == 199_000_000

    def test_skips_subscription_with_unknown_customer(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test2",
        )

        mock_sub = _sub("sub_unknown_cust", "cus_nobody", "active",
                        items=[_licensed_item(4900, product_name="Pro")])

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 0
        assert result["skipped"] == 1
        assert not StripeSubscription.objects.filter(stripe_subscription_id="sub_unknown_cust").exists()

    def test_updates_existing_subscription(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions
        from apps.subscriptions.models import StripeSubscription

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_test3",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_existing",
        )
        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=tenant, customer=customer,
            stripe_subscription_id="sub_exists",
            stripe_product_name="Old Plan", status="trialing",
            amount_micros=29_000_000, currency="usd", interval="month",
            current_period_start=now, current_period_end=now, last_synced_at=now,
        )

        mock_sub = _sub("sub_exists", "cus_existing", "active",
                        items=[_licensed_item(4900, product_name="Pro Plan")])

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

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
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_qty",
        )
        Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_qty",
        )

        mock_sub = _sub("sub_qty_1", "cus_qty", "active", items=[
            _licensed_item(1000, qty=1, product_name="Enterprise"),  # access $10
            _licensed_item(1000, qty=3),                             # 3 seats @ $10
        ])

        mock_list = MagicMock()
        mock_list.auto_paging_iter.return_value = [mock_sub]

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.return_value = mock_list

            result = sync_subscriptions(tenant)

        assert result["synced"] == 1
        sub = StripeSubscription.objects.get(stripe_subscription_id="sub_qty_1")
        assert sub.quantity == 3
        assert sub.amount_micros == (1000 + 1000 * 3) * 10_000

    def test_sync_handles_stripe_api_error(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_api_err",
        )

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.side_effect = stripe.error.APIError(
                "Internal server error"
            )
            mock_stripe.error = stripe.error

            result = sync_subscriptions(tenant)

        assert result["errors"] == 1
        assert result["synced"] == 0

    def test_sync_handles_stripe_auth_error(self):
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_auth_err",
        )

        with patch("apps.subscriptions.stripe.sync.stripe") as mock_stripe:
            mock_stripe.Subscription.list.side_effect = stripe.error.AuthenticationError(
                "Invalid API Key"
            )
            mock_stripe.error = stripe.error

            result = sync_subscriptions(tenant)

        assert result["errors"] == 1
        assert result["synced"] == 0
