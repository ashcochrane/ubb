from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.wallets.tasks import reconcile_wallet_balances


def _top_up(wallet, amount_micros, key):
    """Helper: apply a keyed top-up directly (mirrors the real credit path)."""
    from django.db import transaction
    with transaction.atomic():
        locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
        locked.balance_micros += amount_micros
        locked.save(update_fields=["balance_micros", "updated_at"])
        WalletTransaction.objects.create(
            wallet=locked,
            transaction_type="TOP_UP",
            amount_micros=amount_micros,
            balance_after_micros=locked.balance_micros,
            description="top-up",
            idempotency_key=key,
        )
    wallet.refresh_from_db()


def _deduct(wallet, amount_micros, key):
    """Helper: apply a keyed deduction directly (mirrors the real drawdown path)."""
    from django.db import transaction
    with transaction.atomic():
        locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
        locked.balance_micros -= amount_micros
        locked.save(update_fields=["balance_micros", "updated_at"])
        WalletTransaction.objects.create(
            wallet=locked,
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-amount_micros,
            balance_after_micros=locked.balance_micros,
            description="usage",
            idempotency_key=key,
        )
    wallet.refresh_from_db()


class ReconcileWalletBalancesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )

    def test_no_drift_when_balanced(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        wallet = Wallet.objects.create(customer=customer)
        _top_up(wallet, 10_000_000, "topup:c1:1")

        # No ERROR should be logged; assert on INFO completion log
        with self.assertLogs("apps.billing.wallets.tasks", level="INFO") as cm:
            reconcile_wallet_balances()

        self.assertTrue(any("reconciliation complete" in msg.lower() for msg in cm.output))
        self.assertFalse(any("drift" in msg.lower() for msg in cm.output))

    def test_detects_drift(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c2"
        )
        wallet = Wallet.objects.create(customer=customer)
        # Manually set balance without matching transaction
        Wallet.objects.filter(pk=wallet.pk).update(balance_micros=50_000_000)

        with self.assertLogs("apps.billing.wallets.tasks", level="ERROR") as cm:
            reconcile_wallet_balances()

        self.assertTrue(any("drift" in msg.lower() for msg in cm.output))

    def test_no_wallets(self):
        """Runs without error when there are no wallets."""
        reconcile_wallet_balances()

    def test_balanced_with_multiple_transactions(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c3"
        )
        wallet = Wallet.objects.create(customer=customer)
        _top_up(wallet, 20_000_000, "topup:c3:1")
        _deduct(wallet, 5_000_000, "deduct:c3:1")

        # balance_micros should be 15_000_000, matching ledger — no drift logged
        with self.assertLogs("apps.billing.wallets.tasks", level="INFO") as cm:
            reconcile_wallet_balances()

        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_micros, 15_000_000)
        self.assertFalse(any("drift" in msg.lower() for msg in cm.output))
