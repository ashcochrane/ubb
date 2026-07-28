import pytest
from django.db import transaction

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.billing.locking import lock_for_billing
from core.exceptions import NotBillingOwnerError


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


@pytest.mark.django_db
class TestLockForBillingOwnerRatchet:
    """Task 8c — the ratchet against the seat/owner defect found seven times
    (five endpoints in Task 3, refund_usage's follow-up, TopUpAttempt in
    Task 7, the dispute/refund clawback in Task 8a). Every instance was the
    same shape: a caller reached ``lock_for_billing`` with a seat id, and the
    lazy ``Wallet.objects.create`` above turned that into a silent phantom
    wallet nothing else ever reads, instead of a loud failure.

    This class pins the guard added to ``lock_for_billing`` itself: it now
    refuses any id that is not itself a billing owner. This is deliberately
    the STRONGEST option from Task 8c's menu (over an AST/static guard or a
    per-path test) because it fires at the one seam every money-moving path
    already goes through — a future eighth instance becomes a hard failure
    at the first test run, not a silent phantom wallet someone has to notice.

    ``test_lock_for_billing_refuses_pooled_seat`` fails against the
    pre-Task-3 (and pre-Task-8c) shape of ``lock_for_billing`` — verified by
    running it against the unpatched function before adding the guard: it
    raised no exception and created a wallet on the seat. git blame on
    ``apps/billing/locking.py`` confirms this function was untouched by every
    earlier task on this branch (Task 3, 7) — the guard added here is the
    first change to it."""

    def _pooled_seat(self, tenant):
        biz = Customer.objects.create(
            tenant=tenant, external_id="biz_ratchet",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=tenant, external_id="seat_ratchet",
            account_type="seat", parent=biz)
        return biz, seat

    def _make_tenant(self, **kwargs):
        defaults = {"name": "Ratchet Tenant", "products": ["metering", "billing"]}
        defaults.update(kwargs)
        return Tenant.objects.create(**defaults)

    def test_lock_for_billing_refuses_pooled_seat(self):
        """The load-bearing pin: a pooled seat's id is refused loudly, and —
        unlike the pre-guard behaviour — no wallet is ever created on it."""
        tenant = self._make_tenant()
        biz, seat = self._pooled_seat(tenant)

        with transaction.atomic():
            with pytest.raises(NotBillingOwnerError):
                lock_for_billing(seat.id)

        assert not Wallet.objects.filter(customer=seat).exists()
        assert not Wallet.objects.filter(customer=biz).exists()

    def test_lock_for_billing_allows_the_resolved_owner(self):
        """The correctly-resolved caller shape (every real call site in this
        codebase) is unaffected: locking the OWNER's id still works."""
        tenant = self._make_tenant()
        biz, seat = self._pooled_seat(tenant)

        with transaction.atomic():
            wallet, cust = lock_for_billing(biz.id)

        assert wallet.customer_id == biz.id
        assert cust.id == biz.id

    def test_lock_for_billing_allows_allocated_seat_self(self):
        """A non-pooled ("allocated") seat resolves to itself — same as an
        individual customer — so locking its own id is still allowed."""
        tenant = self._make_tenant()
        biz = Customer.objects.create(
            tenant=tenant, external_id="biz_alloc_ratchet",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=tenant, external_id="seat_alloc_ratchet",
            account_type="seat", parent=biz)

        with transaction.atomic():
            wallet, cust = lock_for_billing(seat.id)

        assert wallet.customer_id == seat.id
        assert cust.id == seat.id

    def test_lock_for_billing_allows_individual_customer(self):
        """An ordinary individual customer (no parent at all) is its own
        owner — the overwhelmingly common case — and is unaffected."""
        tenant = self._make_tenant()
        customer = Customer.objects.create(tenant=tenant, external_id="indiv_ratchet")

        with transaction.atomic():
            wallet, cust = lock_for_billing(customer.id)

        assert wallet.customer_id == customer.id
