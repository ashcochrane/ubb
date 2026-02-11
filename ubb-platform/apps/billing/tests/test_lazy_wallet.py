import pytest
from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.billing.locking import lock_for_billing


@pytest.mark.django_db
class TestLazyWalletCreation:
    def _make_tenant(self, **kwargs):
        defaults = {
            "name": "Test Tenant",
            "products": ["metering", "billing"],
        }
        defaults.update(kwargs)
        return Tenant.objects.create(**defaults)

    def test_lock_for_billing_creates_wallet_if_missing(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        # Customer.save() currently creates a wallet; delete it to simulate lazy path
        Wallet.objects.filter(customer=customer).delete()

        with transaction.atomic():
            wallet, cust = lock_for_billing(customer.id)

        assert wallet.customer_id == customer.id
        assert wallet.balance_micros == 0
        assert wallet.currency == "USD"

    def test_lock_for_billing_uses_existing_wallet(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        # Wallet auto-created with balance 0; credit it
        wallet = customer.wallet
        wallet.balance_micros = 5000000
        wallet.save()

        with transaction.atomic():
            locked_wallet, cust = lock_for_billing(customer.id)

        assert locked_wallet.id == wallet.id
        assert locked_wallet.balance_micros == 5000000
