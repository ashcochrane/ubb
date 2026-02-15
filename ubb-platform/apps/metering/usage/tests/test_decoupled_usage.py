import pytest
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet


@pytest.mark.django_db
class TestDecoupledUsageService:
    def test_record_usage_does_not_deduct_wallet(self):
        """After decoupling, UsageService should NOT touch the wallet."""
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        with patch("apps.platform.events.tasks.process_single_event"):
            UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=5_000_000,
            )

        wallet.refresh_from_db()
        assert wallet.balance_micros == 10_000_000  # Unchanged!

    def test_record_usage_does_not_suspend_customer(self):
        """Suspension is now billing's responsibility via outbox handler."""
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 0  # Zero balance
        wallet.save(update_fields=["balance_micros"])

        with patch("apps.platform.events.tasks.process_single_event"):
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=100_000_000,  # Way over threshold
            )

        customer.refresh_from_db()
        assert customer.status == "active"  # Not suspended by metering
        assert result["suspended"] is False
