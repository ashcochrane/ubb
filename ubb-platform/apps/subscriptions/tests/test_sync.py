import pytest
import stripe
from unittest.mock import patch, MagicMock
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


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

        mock_sub = MagicMock()
        mock_sub.id = "sub_sync_1"
        mock_sub.customer = "cus_sync"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Enterprise"
        mock_sub.plan.amount = 19900  # $199
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

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

        mock_sub = MagicMock()
        mock_sub.id = "sub_unknown_cust"
        mock_sub.customer = "cus_nobody"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Pro"
        mock_sub.plan.amount = 4900
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

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

        mock_sub = MagicMock()
        mock_sub.id = "sub_exists"
        mock_sub.customer = "cus_existing"
        mock_sub.status = "active"
        mock_sub.plan.product.name = "Pro Plan"
        mock_sub.plan.amount = 4900
        mock_sub.plan.currency = "usd"
        mock_sub.plan.interval = "month"
        mock_sub.current_period_start = 1738368000
        mock_sub.current_period_end = 1740960000

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
