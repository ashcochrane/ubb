from django.test import TestCase

from apps.customers.models import Customer, Wallet, WalletTransaction
from apps.platform.tenants.models import Tenant


class CustomerModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")

    def test_create_customer(self):
        customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_42",
        )
        self.assertEqual(customer.status, "active")
        self.assertTrue(hasattr(customer, "wallet"))

    def test_wallet_created_with_customer(self):
        customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="user_42",
        )
        wallet = Wallet.objects.get(customer=customer)
        self.assertEqual(wallet.balance_micros, 0)

    def test_wallet_deduct(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u1"
        )
        wallet = customer.wallet
        wallet.balance_micros = 10_000_000  # $10
        wallet.save()
        txn = wallet.deduct(amount_micros=1_500_000, description="usage")
        self.assertEqual(wallet.balance_micros, 8_500_000)
        self.assertEqual(txn.transaction_type, "USAGE_DEDUCTION")

    def test_wallet_credit(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u2"
        )
        wallet = customer.wallet
        txn = wallet.credit(amount_micros=20_000_000, description="top-up")
        self.assertEqual(wallet.balance_micros, 20_000_000)
        self.assertEqual(txn.transaction_type, "TOP_UP")

    def test_wallet_deduct_allows_negative(self):
        customer = Customer.objects.create(
            tenant=self.tenant, external_id="u3"
        )
        wallet = customer.wallet
        txn = wallet.deduct(amount_micros=1_000_000, description="usage")
        self.assertEqual(wallet.balance_micros, -1_000_000)
