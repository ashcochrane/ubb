import pytest
from unittest.mock import patch, MagicMock

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt
from apps.billing.connectors.stripe.handlers import handle_balance_low_stripe


@pytest.mark.django_db
class TestHandleBalanceLowStripe:
    def test_creates_attempt_and_dispatches_task_when_stripe_configured(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test123",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 3_000_000
        wallet.save(update_fields=["balance_micros"])

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        with patch(
            "apps.billing.connectors.stripe.tasks.charge_auto_topup_task"
        ) as mock_task:
            mock_task.delay = MagicMock()
            handle_balance_low_stripe("evt_1", payload)
            mock_task.delay.assert_called_once()

        attempt = TopUpAttempt.objects.first()
        assert attempt is not None
        assert attempt.trigger == "auto_topup"
        assert attempt.amount_micros == 20_000_000

    def test_skips_when_no_stripe_account(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        Wallet.objects.create(customer=customer)

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        handle_balance_low_stripe("evt_1", payload)
        assert TopUpAttempt.objects.count() == 0

    def test_skips_when_no_auto_topup_config(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test123",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 3_000_000
        wallet.save(update_fields=["balance_micros"])

        # No AutoTopUpConfig created

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        handle_balance_low_stripe("evt_1", payload)
        assert TopUpAttempt.objects.count() == 0

    def test_skips_when_already_pending_attempt(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test123",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 3_000_000
        wallet.save(update_fields=["balance_micros"])

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )

        # Pre-existing pending attempt
        TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )

        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "balance_micros": 3_000_000,
            "threshold_micros": 5_000_000,
            "suggested_topup_micros": 20_000_000,
        }

        handle_balance_low_stripe("evt_1", payload)
        # Should still only be 1 attempt (the pre-existing one)
        assert TopUpAttempt.objects.count() == 1
