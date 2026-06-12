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
        # No wallet exists — lock_for_billing should create one lazily

        with transaction.atomic():
            wallet, cust = lock_for_billing(customer.id)

        assert wallet.customer_id == customer.id
        assert wallet.balance_micros == 0
        assert wallet.currency == "usd"  # CUR-1: lowercase everywhere

    def test_lazy_wallet_gets_tenant_currency_lowercase(self):
        """CUR-1: a lazily-created wallet is born in the TENANT's currency."""
        tenant = self._make_tenant(default_currency="eur")
        customer = Customer.objects.create(tenant=tenant, external_id="c_eur")

        with transaction.atomic():
            wallet, _ = lock_for_billing(customer.id)

        assert wallet.currency == "eur"

    def test_lazy_wallet_lowercases_legacy_uppercase_tenant_currency(self):
        """Even a legacy uppercase tenant value lands lowercase on the wallet."""
        tenant = self._make_tenant(default_currency="EUR")
        customer = Customer.objects.create(tenant=tenant, external_id="c_EUR")

        with transaction.atomic():
            wallet, _ = lock_for_billing(customer.id)

        assert wallet.currency == "eur"

    def test_wallet_model_default_is_lowercase_usd(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c_def")
        wallet = Wallet.objects.create(customer=customer)
        assert wallet.currency == "usd"

    def test_migration_lowercases_existing_currencies(self):
        """The 0007 data migration normalizes legacy uppercase rows (wallet + grant)."""
        import importlib
        from django.apps import apps as global_apps
        from apps.billing.wallets.models import CreditGrant

        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c_mig")
        wallet = Wallet.objects.create(customer=customer, currency="USD")
        grant = CreditGrant.objects.create(
            tenant=tenant, wallet=wallet, kind="promo",
            granted_micros=1_000_000, remaining_micros=1_000_000,
            currency="USD")

        migration = importlib.import_module(
            "apps.billing.wallets.migrations."
            "0007_alter_creditgrant_currency_alter_wallet_currency")
        migration.lowercase_currencies(global_apps, None)

        wallet.refresh_from_db()
        grant.refresh_from_db()
        assert wallet.currency == "usd"
        assert grant.currency == "usd"

    def test_lock_for_billing_uses_existing_wallet(self):
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        wallet = Wallet.objects.create(customer=customer)
        wallet.balance_micros = 5000000
        wallet.save()

        with transaction.atomic():
            locked_wallet, cust = lock_for_billing(customer.id)

        assert locked_wallet.id == wallet.id
        assert locked_wallet.balance_micros == 5000000
