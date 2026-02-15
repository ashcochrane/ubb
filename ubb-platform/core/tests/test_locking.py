import pytest
import uuid
from django.db import transaction
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from core.locking import lock_row, lock_customer


@pytest.mark.django_db
class TestGenericLockRow:
    def test_lock_row_returns_instance(self):
        tenant = Tenant.objects.create(name="LockTest")
        with transaction.atomic():
            locked = lock_row(Tenant, id=tenant.id)
        assert locked.id == tenant.id

    def test_lock_row_raises_does_not_exist(self):
        with pytest.raises(Tenant.DoesNotExist):
            with transaction.atomic():
                lock_row(Tenant, id=uuid.uuid4())


class TestLockCustomer(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust_1"
        )

    def test_lock_customer_returns_customer(self):
        with transaction.atomic():
            customer = lock_customer(self.customer.id)
            self.assertIsInstance(customer, Customer)
            self.assertEqual(customer.id, self.customer.id)

    def test_lock_customer_nonexistent_raises(self):
        with self.assertRaises(Customer.DoesNotExist):
            with transaction.atomic():
                lock_customer(uuid.uuid4())
