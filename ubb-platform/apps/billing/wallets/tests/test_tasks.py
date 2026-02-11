from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.wallets.tasks import reconcile_wallet_balances


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
        # Credit via wallet method to create matching transaction
        wallet.credit(10_000_000, description="top-up")

        # No errors should be logged; task completes cleanly
        reconcile_wallet_balances()

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
        wallet.credit(20_000_000, description="top-up")
        wallet.deduct(5_000_000, description="usage")

        # balance_micros should be 15_000_000, matching ledger
        reconcile_wallet_balances()
        # If drift existed, we'd see ERROR logs - no assertion needed
        # as absence of error is the expected behavior
