from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task


class TaskModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_task_creation_defaults(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
        )
        self.assertEqual(task.status, "active")
        self.assertEqual(task.total_billed_cost_micros, 0)
        self.assertEqual(task.total_provider_cost_micros, 0)
        self.assertEqual(task.event_count, 0)
        self.assertIsNone(task.completed_at)

    def test_task_str_representation(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
            total_billed_cost_micros=500_000,
        )
        self.assertIn("active", str(task))
        self.assertIn("500000", str(task))

    def test_task_with_all_limits(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=5_000_000,
            provider_cost_limit_micros=10_000_000,
            floor_snapshot_micros=-5_000_000,
        )
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)
        self.assertEqual(task.floor_snapshot_micros, -5_000_000)
        self.assertEqual(task.balance_snapshot_micros, 5_000_000)

    def test_task_without_limits(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
        )
        self.assertIsNone(task.provider_cost_limit_micros)
        self.assertIsNone(task.floor_snapshot_micros)

    def test_task_with_external_task_id(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            external_task_id="workflow-abc-123",
        )
        self.assertEqual(task.external_task_id, "workflow-abc-123")

    def test_task_with_metadata(self):
        task = Task.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            metadata={"workflow": "scouting", "region": "AU"},
        )
        self.assertEqual(task.metadata["workflow"], "scouting")
