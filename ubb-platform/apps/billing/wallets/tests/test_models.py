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

    def test_wallet_transaction_deduction(self):
        """WalletTransaction with idempotency_key correctly records a deduction."""
        from apps.billing.wallets.models import Wallet, WalletTransaction
        from django.db import transaction as db_transaction

        tenant = Tenant.objects.create(name="Test", products=["metering", "billing"])
        customer = Customer.objects.create(tenant=tenant, external_id="ext1")
        wallet = Wallet.objects.create(customer=customer, balance_micros=10_000_000)

        with db_transaction.atomic():
            locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
            locked.balance_micros -= 5_000_000
            locked.save(update_fields=["balance_micros", "updated_at"])
            txn = WalletTransaction.objects.create(
                wallet=locked,
                transaction_type="USAGE_DEDUCTION",
                amount_micros=-5_000_000,
                balance_after_micros=locked.balance_micros,
                description="Test deduction",
                idempotency_key="test_deduct_1",
            )

        wallet.refresh_from_db()
        assert wallet.balance_micros == 5_000_000
        assert txn.transaction_type == "USAGE_DEDUCTION"
        assert txn.amount_micros == -5_000_000
