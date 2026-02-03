from django.test import TestCase
from apps.tenants.models import Tenant
from apps.customers.models import Customer, Wallet
from core.locking import lock_for_billing, lock_customer


class LockForBillingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant,
            external_id="cust_1",
        )

    def test_lock_for_billing_returns_wallet_and_customer(self):
        from django.db import transaction
        with transaction.atomic():
            wallet, customer = lock_for_billing(self.customer.id)
            self.assertIsInstance(wallet, Wallet)
            self.assertIsInstance(customer, Customer)
            self.assertEqual(wallet.customer_id, self.customer.id)
            self.assertEqual(customer.id, self.customer.id)

    def test_lock_customer_returns_customer(self):
        from django.db import transaction
        with transaction.atomic():
            customer = lock_customer(self.customer.id)
            self.assertIsInstance(customer, Customer)
            self.assertEqual(customer.id, self.customer.id)

    def test_lock_for_billing_nonexistent_raises(self):
        import uuid
        from django.db import transaction
        from apps.customers.models import Wallet
        with self.assertRaises(Wallet.DoesNotExist):
            with transaction.atomic():
                lock_for_billing(uuid.uuid4())
