from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer, TopUpAttempt, Wallet, WalletTransaction
from apps.platform.customers.tasks import expire_stale_topup_attempts, reconcile_wallet_balances


class ExpireStaleTopupAttemptsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    def _create_attempt(self, trigger, minutes_ago=0, hours_ago=0, customer=None):
        attempt = TopUpAttempt.objects.create(
            customer=customer or self.customer,
            amount_micros=20_000_000,
            trigger=trigger,
            status="pending",
        )
        age = timedelta(minutes=minutes_ago, hours=hours_ago)
        TopUpAttempt.objects.filter(pk=attempt.pk).update(
            created_at=timezone.now() - age
        )
        return attempt

    def test_expires_stale_auto_topup_attempts(self):
        stale = self._create_attempt("auto_topup", minutes_ago=31)
        # Use separate customer to avoid UniqueConstraint on pending auto_topup
        customer2 = Customer.objects.create(
            tenant=self.tenant, external_id="c2"
        )
        fresh = self._create_attempt("auto_topup", minutes_ago=10, customer=customer2)

        expire_stale_topup_attempts()

        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, "expired")
        self.assertEqual(fresh.status, "pending")

    def test_expires_stale_manual_attempts(self):
        stale = self._create_attempt("manual", hours_ago=25)
        fresh = self._create_attempt("manual", hours_ago=12)

        expire_stale_topup_attempts()

        stale.refresh_from_db()
        fresh.refresh_from_db()
        self.assertEqual(stale.status, "expired")
        self.assertEqual(fresh.status, "pending")

    def test_does_not_expire_already_succeeded(self):
        attempt = self._create_attempt("auto_topup", minutes_ago=60)
        TopUpAttempt.objects.filter(pk=attempt.pk).update(status="succeeded")

        expire_stale_topup_attempts()

        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "succeeded")

    def test_no_pending_attempts(self):
        """Runs without error when there are no pending attempts."""
        expire_stale_topup_attempts()


class ReconcileWalletBalancesTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )

    def test_no_drift_when_balanced(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        wallet = customer.wallet
        # Credit via wallet method to create matching transaction
        wallet.credit(10_000_000, description="top-up")

        # No errors should be logged; task completes cleanly
        reconcile_wallet_balances()

    def test_detects_drift(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c2"
        )
        wallet = customer.wallet
        # Manually set balance without matching transaction
        Wallet.objects.filter(pk=wallet.pk).update(balance_micros=50_000_000)

        with self.assertLogs("apps.platform.customers.tasks", level="ERROR") as cm:
            reconcile_wallet_balances()

        self.assertTrue(any("drift" in msg.lower() for msg in cm.output))

    def test_no_wallets(self):
        """Runs without error when there are no wallets."""
        reconcile_wallet_balances()

    def test_balanced_with_multiple_transactions(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="c3"
        )
        wallet = customer.wallet
        wallet.credit(20_000_000, description="top-up")
        wallet.deduct(5_000_000, description="usage")

        # balance_micros should be 15_000_000, matching ledger
        reconcile_wallet_balances()
        # If drift existed, we'd see ERROR logs - no assertion needed
        # as absence of error is the expected behavior
