import pytest
import uuid

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.tenant_billing.models import TenantBillingPeriod


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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 5_000_000,
            },
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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": event_id,
                "cost_micros": 3_000_000,
            },
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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 5_000_000,
            },
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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 500_000,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        txn = WalletTransaction.objects.get(wallet=wallet)
        assert txn.idempotency_key is not None
        assert txn.idempotency_key.startswith("usage_deduction:")

    def test_usage_deduction_replay_no_double_deduct(self):
        """Replaying the same outbox event must not create a second deduction."""
        from apps.billing.handlers import handle_usage_recorded_billing
        from django.db import IntegrityError

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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": event_uuid,
                "cost_micros": 500_000,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        # Simulate replay with same event_id
        with pytest.raises(IntegrityError):
            handle_usage_recorded_billing(str(event.id), event.payload)

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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 0,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000
        assert WalletTransaction.objects.filter(wallet=wallet).count() == 0

    def test_skips_deduction_when_cost_missing(self):
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

        handle_usage_recorded_billing(str(event.id), event.payload)

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000

    def test_suspends_customer_when_below_min_balance(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
            min_balance_micros=1_000_000,  # $1 threshold
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0  # zero balance
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 2_000_000,  # $2 deduction, puts wallet at -$2
            },
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
            min_balance_micros=5_000_000,  # $5 threshold
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 2_000_000,  # $2 deduction, wallet at -$2 (within $5 threshold)
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        customer.refresh_from_db()
        assert customer.status == "active"


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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 2_000_000,  # $2 deduction -> balance $4 (below $5)
            },
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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 100_000,  # small deduction
            },
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
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 500_000,
            },
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
            min_balance_micros=1_000_000,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 2_000_000,
            },
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
            min_balance_micros=5_000_000,
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0
        wallet.save(update_fields=["balance_micros"])

        event = OutboxEvent.objects.create(
            event_type="usage.recorded",
            payload={
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "event_id": str(uuid.uuid4()),
                "cost_micros": 2_000_000,
            },
            tenant_id=tenant.id,
        )

        handle_usage_recorded_billing(str(event.id), event.payload)

        assert not OutboxEvent.objects.filter(
            event_type="billing.customer_suspended"
        ).exists()
