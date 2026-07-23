import pytest
import uuid
from dataclasses import asdict

from apps.platform.events.schemas import UsageRecorded
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.tenant_billing.models import BillingTenantConfig, TenantBillingPeriod


@pytest.mark.django_db
class TestBillingOutboxHandler:
    def test_wallet_deduction_handler(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=5_000_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 5_000_000

    def test_wallet_transaction_created(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event_id = str(uuid.uuid4())
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=event_id,
                cost_micros=3_000_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        txn = WalletTransaction.objects.get(wallet=wallet)
        assert txn.transaction_type == "USAGE_DEDUCTION"
        assert txn.amount_micros == -3_000_000
        assert txn.balance_after_micros == 7_000_000
        assert txn.reference_id == event_id

    def test_handler_accumulates_billing_period(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=5_000_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        period = TenantBillingPeriod.objects.get(tenant=tenant)
        assert period.total_usage_cost_micros == 5_000_000

    def test_usage_deduction_idempotency_key(self):
        """WalletTransaction should have idempotency_key based on outbox event ID."""
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=500_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        txn = WalletTransaction.objects.get(wallet=wallet)
        assert txn.idempotency_key is not None
        assert txn.idempotency_key.startswith("usage_deduction:")

    def test_usage_deduction_replay_no_double_deduct(self):
        """Replaying the same outbox event must not create a second deduction (silent no-op)."""
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event_uuid = str(uuid.uuid4())
        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=event_uuid,
                cost_micros=500_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        # Simulate replay with same event_id — must be a silent no-op, not raise
        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 9_500_000  # debited exactly once
        txn_count = WalletTransaction.objects.filter(wallet=wallet).count()
        assert txn_count == 1

    def test_skips_deduction_for_zero_cost(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=0,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000
        assert WalletTransaction.objects.filter(wallet=wallet).count() == 0

    def test_malformed_payload_missing_cost_is_loud_not_zero(self):
        # #114: cost_micros is required-since-birth on UsageRecorded — the
        # typed write side cannot produce a payload without it, so the handler
        # treats one as malformed (loud TypeError -> outbox retry/dead-letter)
        # instead of silently deducting zero. The wallet is untouched.
        import pytest
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
            },
            tenant_id=tenant.id,
        )

        with pytest.raises(TypeError):
            handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000

    def test_suspends_customer_when_below_min_balance(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        BillingTenantConfig.objects.create(
            tenant=tenant,
            min_balance_micros=1_000_000,  # $1 threshold
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0  # zero balance
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=2_000_000,  # $2 deduction, puts wallet at -$2
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        customer.refresh_from_db()
        assert customer.status == "suspended"

    def test_does_not_suspend_when_within_min_balance(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        BillingTenantConfig.objects.create(
            tenant=tenant,
            min_balance_micros=5_000_000,  # $5 threshold
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=2_000_000,  # $2 deduction, wallet at -$2 (within $5 threshold)
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        customer.refresh_from_db()
        assert customer.status == "active"

    def test_drawdown_invokes_budget_record(self):
        from unittest.mock import patch
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet

        tenant = Tenant.objects.create(name="T", products=["metering", "billing"],
                                       stripe_connected_account_id="acct_test")
        customer = Customer.objects.create(tenant=tenant, external_id="ext_b")
        w = Wallet.objects.create(customer=customer)
        w.balance_micros = 10_000_000
        w.save(update_fields=["balance_micros"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id, customer_id=customer.id,
                event_id=str(uuid.uuid4()), cost_micros=2_000_000)))
        with patch("apps.billing.gating.services.budget_service.BudgetService.record_usage_spend") as mock_rec:
            handle_usage_recorded_billing(str(event.id), event.payload)
        mock_rec.assert_called_once()
        assert str(mock_rec.call_args.args[0].id) == str(customer.id)  # the customer
        assert mock_rec.call_args.args[1] == 2_000_000                 # billed amount

    def test_postpaid_tenant_skips_wallet_deduction(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet
        tenant = Tenant.objects.create(name="PP", products=["metering", "billing"],
                                       billing_mode="postpaid")
        customer = Customer.objects.create(tenant=tenant, external_id="pp1")
        w = Wallet.objects.create(customer=customer)
        w.balance_micros = 10_000_000
        w.save(update_fields=["balance_micros"])
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id, customer_id=customer.id,
                event_id=str(uuid.uuid4()), cost_micros=2_000_000)))
        handle_usage_recorded_billing(str(event.id), event.payload)
        w.refresh_from_db()
        assert w.balance_micros == 10_000_000  # untouched — postpaid is invoiced, not drawn down

    def test_overage_event_fires_once_on_crossing_below_zero(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet
        tenant = Tenant.objects.create(name="OV", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=tenant, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=1_000_000)
        ev_id = str(uuid.uuid4())
        payload = asdict(UsageRecorded(
            tenant_id=tenant.id, customer_id=c.id, event_id=ev_id,
            billing_owner_id=c.id, cost_micros=1_500_000))
        e = OutboxEvent.objects.create(event_type="usage.recorded", tenant_id=tenant.id, payload=payload)
        handle_usage_recorded_billing(str(e.id), payload)
        assert OutboxEvent.objects.filter(
            event_type="billing.balance_overage").count() == 1

    def test_redelivery_does_not_double_debit_or_refire_overage(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet, WalletTransaction
        tenant = Tenant.objects.create(name="OV2", products=["metering", "billing"], billing_mode="prepaid")
        c = Customer.objects.create(tenant=tenant, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=1_000_000)
        ev_id = str(uuid.uuid4())
        payload = asdict(UsageRecorded(
            tenant_id=tenant.id, customer_id=c.id, event_id=ev_id,
            billing_owner_id=c.id, cost_micros=1_500_000))
        e = OutboxEvent.objects.create(event_type="usage.recorded", tenant_id=tenant.id, payload=payload)
        handle_usage_recorded_billing(str(e.id), payload)
        emitted = OutboxEvent.objects.exclude(id=e.id).count()
        handle_usage_recorded_billing(str(e.id), payload)   # re-deliver
        # I2: the replay emits nothing new — no overage re-fire.
        assert OutboxEvent.objects.exclude(id=e.id).count() == emitted
        w.refresh_from_db()
        assert w.balance_micros == -500_000                      # debited once
        assert WalletTransaction.objects.filter(wallet=w, idempotency_key=f"usage_deduction:{ev_id}").count() == 1

    def test_pooled_seat_debits_business_wallet_records_spend_on_seat(self):
        import uuid
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.models import Wallet, WalletTransaction
        tenant = Tenant.objects.create(name="PB", products=["metering", "billing"], billing_mode="prepaid")
        biz = Customer.objects.create(tenant=tenant, external_id="biz", account_type="business",
                                      billing_topology="pooled")
        seat = Customer.objects.create(tenant=tenant, external_id="s1", account_type="seat", parent=biz)
        bw = Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        event = OutboxEvent.objects.create(
            event_type="usage.recorded", tenant_id=tenant.id,
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id, customer_id=seat.id,
                event_id=str(uuid.uuid4()), cost_micros=2_000_000)))
        handle_usage_recorded_billing(str(event.id), event.payload)
        bw.refresh_from_db()
        assert bw.balance_micros == 8_000_000  # the BUSINESS pool was debited
        assert not Wallet.objects.filter(customer=seat).exists()  # seat has no wallet
        assert WalletTransaction.objects.filter(wallet=bw, transaction_type="USAGE_DEDUCTION").count() == 1


class TestBillingHandlerEmitsBalanceLow:
    """After wallet deduction, if balance drops below auto-topup threshold,
    emit a balance.low event instead of dispatching a Stripe task."""

    @pytest.mark.django_db
    def test_emits_balance_low_when_below_threshold(self):
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.topups.models import AutoTopUpConfig

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 6_000_000  # $6
        wallet.save(update_fields=["balance_micros"])

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,  # $5 threshold
            top_up_amount_micros=20_000_000,
        )

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=2_000_000,  # $2 deduction -> balance $4 (below $5)
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        low_event = OutboxEvent.objects.filter(
            event_type="billing.balance_low"
        ).first()
        assert low_event is not None
        assert low_event.payload["balance_micros"] == 4_000_000
        assert low_event.payload["suggested_topup_micros"] == 20_000_000

    @pytest.mark.django_db
    def test_does_not_emit_balance_low_when_above_threshold(self):
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.topups.models import AutoTopUpConfig

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 20_000_000  # $20
        wallet.save(update_fields=["balance_micros"])

        AutoTopUpConfig.objects.create(
            customer=customer,
            is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000,
        )

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=100_000,  # small deduction
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        assert not OutboxEvent.objects.filter(
            event_type="billing.balance_low"
        ).exists()

    @pytest.mark.django_db
    def test_does_not_emit_when_no_auto_topup_config(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 1_000_000
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=500_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        assert not OutboxEvent.objects.filter(
            event_type="billing.balance_low"
        ).exists()


class TestBillingHandlerEmitsCustomerSuspended:
    @pytest.mark.django_db
    def test_emits_customer_suspended_on_min_balance_breach(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        BillingTenantConfig.objects.create(
            tenant=tenant,
            min_balance_micros=1_000_000,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=2_000_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        suspended_event = OutboxEvent.objects.filter(
            event_type="billing.customer_suspended"
        ).first()
        assert suspended_event is not None
        assert suspended_event.payload["reason"] == "min_balance_exceeded"
        assert suspended_event.payload["balance_micros"] == -2_000_000

    @pytest.mark.django_db
    def test_does_not_emit_suspended_when_within_threshold(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        BillingTenantConfig.objects.create(
            tenant=tenant,
            min_balance_micros=5_000_000,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload=asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                event_id=str(uuid.uuid4()),
                cost_micros=2_000_000,
            )),
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        assert not OutboxEvent.objects.filter(
            event_type="billing.customer_suspended"
        ).exists()
