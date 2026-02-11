import pytest
from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestWalletInBillingApp:
    def test_wallet_import_from_billing(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction
        assert Wallet is not None
        assert WalletTransaction is not None

    def test_wallet_not_auto_created_via_customer(self):
        """Wallet is no longer auto-created by Customer.save()."""
        from apps.billing.wallets.models import Wallet

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(
            tenant=tenant, external_id="ext1",
        )
        assert not Wallet.objects.filter(customer=customer).exists()

    def test_wallet_deduct(self):
        from apps.billing.wallets.models import Wallet, WalletTransaction

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 10_000_000
        wallet.save(update_fields=["balance_micros"])

        txn = wallet.deduct(5_000_000, description="Test deduction")
        wallet.refresh_from_db()
        assert wallet.balance_micros == 5_000_000
        assert txn.transaction_type == "USAGE_DEDUCTION"
        assert txn.amount_micros == -5_000_000
