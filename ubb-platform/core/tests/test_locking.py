import pytest
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from core.locking import lock_for_billing, lock_customer


@pytest.mark.django_db
class TestGenericLockRow:
    def test_lock_row_returns_instance(self):
        from core.locking import lock_row
        from django.db import transaction

        tenant = Tenant.objects.create(name="LockTest")
        with transaction.atomic():
            locked = lock_row(Tenant, id=tenant.id)
        assert locked.id == tenant.id

    def test_lock_row_raises_does_not_exist(self):
        from core.locking import lock_row
        from django.db import transaction
        import uuid

        with pytest.raises(Tenant.DoesNotExist):
            with transaction.atomic():
                lock_row(Tenant, id=uuid.uuid4())


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
        self.wallet = Wallet.objects.create(customer=self.customer)

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
        from apps.billing.wallets.models import Wallet
        with self.assertRaises(Wallet.DoesNotExist):
            with transaction.atomic():
                lock_for_billing(uuid.uuid4())
