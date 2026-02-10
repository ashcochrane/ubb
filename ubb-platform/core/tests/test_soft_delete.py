from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet
from apps.billing.topups.models import AutoTopUpConfig


class SoftDeleteTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    def test_soft_delete_hides_from_default_queryset(self):
        self.customer.soft_delete()
        self.assertFalse(Customer.objects.filter(id=self.customer.id).exists())

    def test_soft_deleted_visible_via_all_objects(self):
        self.customer.soft_delete()
        self.assertTrue(Customer.all_objects.filter(id=self.customer.id).exists())

    def test_restore(self):
        self.customer.soft_delete()
        self.customer.restore()
        self.assertTrue(Customer.objects.filter(id=self.customer.id).exists())

    def test_delete_calls_soft_delete(self):
        self.customer.delete()
        self.assertFalse(Customer.objects.filter(id=self.customer.id).exists())
        self.assertTrue(Customer.all_objects.filter(id=self.customer.id).exists())

    def test_cascade_soft_deletes_wallet(self):
        self.customer.soft_delete()
        self.assertFalse(Wallet.objects.filter(customer=self.customer).exists())
        self.assertTrue(Wallet.all_objects.filter(customer=self.customer).exists())

    def test_cascade_soft_deletes_auto_top_up_config(self):
        AutoTopUpConfig.objects.create(
            customer=self.customer,
            is_enabled=True,
            trigger_threshold_micros=0,
            top_up_amount_micros=20_000_000,
        )
        self.customer.soft_delete()
        self.assertFalse(AutoTopUpConfig.objects.filter(customer=self.customer).exists())

    def test_is_deleted_property(self):
        self.assertFalse(self.customer.is_deleted)
        self.customer.soft_delete()
        self.assertTrue(self.customer.is_deleted)
