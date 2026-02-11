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

    def test_suspends_customer_when_below_arrears_threshold(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
            arrears_threshold_micros=1_000_000,  # $1 threshold
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

    def test_does_not_suspend_when_within_arrears_threshold(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
            arrears_threshold_micros=5_000_000,  # $5 threshold
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
