from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent


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

    def test_soft_delete_emits_customer_deleted_outbox_event(self):
        """soft_delete() emits a CustomerDeleted outbox event for product cleanup."""
        self.customer.soft_delete()
        event = OutboxEvent.objects.get(event_type="customer.deleted")
        self.assertEqual(event.payload["customer_id"], str(self.customer.id))
        self.assertEqual(event.payload["tenant_id"], str(self.tenant.id))

    def test_is_deleted_property(self):
        self.assertFalse(self.customer.is_deleted)
        self.customer.soft_delete()
        self.assertTrue(self.customer.is_deleted)
