import logging

import pytest
from dataclasses import asdict
from unittest.mock import patch, MagicMock

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import WalletBalanceLow
from apps.billing.wallets.models import Wallet
from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt
from apps.billing.connectors.stripe.handlers import handle_balance_low_stripe


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestHandleWalletBalanceLowStripe:
    @pytest.mark.django_db(transaction=True)
    def test_creates_attempt_and_dispatches_task_when_stripe_configured(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="acct_test123", charges_enabled=True,
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

        payload = asdict(WalletBalanceLow(
            tenant_id=tenant.id,
            customer_id=customer.id,
            balance_micros=3_000_000,
            threshold_micros=5_000_000,
            suggested_topup_micros=20_000_000,
        ))

        with patch(
            "apps.billing.connectors.stripe.tasks.charge_auto_top_up_task"
        ) as mock_task:
            mock_task.delay = MagicMock()
            handle_balance_low_stripe("evt_1", payload)
            mock_task.delay.assert_called_once()

        attempt = TopUpAttempt.objects.first()
        assert attempt is not None
        assert attempt.trigger == "auto_top_up"
        assert attempt.amount_micros == 20_000_000

    def test_skips_when_no_stripe_account(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        Wallet.objects.create(customer=customer)

        payload = asdict(WalletBalanceLow(
            tenant_id=tenant.id,
            customer_id=customer.id,
            balance_micros=3_000_000,
            threshold_micros=5_000_000,
            suggested_topup_micros=20_000_000,
        ))

        handle_balance_low_stripe("evt_1", payload)
        assert TopUpAttempt.objects.count() == 0

    def test_skips_when_no_auto_top_up_config(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="acct_test123", charges_enabled=True,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 3_000_000
        wallet.save(update_fields=["balance_micros"])

        # No AutoTopUpConfig created

        payload = asdict(WalletBalanceLow(
            tenant_id=tenant.id,
            customer_id=customer.id,
            balance_micros=3_000_000,
            threshold_micros=5_000_000,
            suggested_topup_micros=20_000_000,
        ))

        handle_balance_low_stripe("evt_1", payload)
        assert TopUpAttempt.objects.count() == 0

    def test_skips_when_already_pending_attempt(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="acct_test123", charges_enabled=True,
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
            trigger="auto_top_up",
            status="pending",
        )

        payload = asdict(WalletBalanceLow(
            tenant_id=tenant.id,
            customer_id=customer.id,
            balance_micros=3_000_000,
            threshold_micros=5_000_000,
            suggested_topup_micros=20_000_000,
        ))

        handle_balance_low_stripe("evt_1", payload)
        # Should still only be 1 attempt (the pre-existing one)
        assert TopUpAttempt.objects.count() == 1

    def test_a_tenant_that_left_prepaid_is_refused_by_name_and_the_event_is_consumed(self):
        """Stage A (2026-11-02): the wallet boundary refuses a tenant whose
        billing mode holds no wallet. A low balance is only ever announced by
        a prepaid drawdown, so this handler meets the refusal only when the
        tenant left `prepaid` between the announcement and its handling —
        built here by switching the tenant after the payload is written. The
        refusal is recorded by name and the event is CONSUMED: no attempt, no
        charge task, and no exception for the outbox to retry for hours and
        then dead-letter."""
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="acct_test123", charges_enabled=True,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        Wallet.objects.create(customer=customer, balance_micros=3_000_000)
        AutoTopUpConfig.objects.create(
            customer=customer, is_enabled=True,
            trigger_threshold_micros=5_000_000, top_up_amount_micros=20_000_000,
        )
        payload = asdict(WalletBalanceLow(
            tenant_id=tenant.id, customer_id=customer.id,
            balance_micros=3_000_000, threshold_micros=5_000_000,
            suggested_topup_micros=20_000_000,
        ))
        tenant.billing_mode = "external"
        tenant.save()

        # The `apps` loggers do not propagate (config/settings.py), so the
        # record is read off the module's own logger.
        capture = _Capture()
        handler_logger = logging.getLogger("apps.billing.connectors.stripe.handlers")
        handler_logger.addHandler(capture)
        try:
            with patch("apps.billing.connectors.stripe.tasks.charge_auto_top_up_task") as mock_task:
                handle_balance_low_stripe("evt_1", payload)  # no raise
                mock_task.delay.assert_not_called()
        finally:
            handler_logger.removeHandler(capture)

        assert TopUpAttempt.objects.count() == 0
        recorded = [r for r in capture.records
                    if r.getMessage() == "auto_top_up.refused_no_wallet_subject"]
        assert len(recorded) == 1
        assert recorded[0].levelno == logging.WARNING
        assert recorded[0].data["billing_mode"] == "external"
