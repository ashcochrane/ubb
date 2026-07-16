from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tasks.tasks import close_abandoned_tasks


class CloseAbandonedTasksTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def _create_stale_task(self, **kwargs):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000, **kwargs
        )
        # Backdate created_at to make it stale (>1 hour old)
        Task.objects.filter(id=task.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        return task

    def test_close_abandoned_tasks_closes_stale(self):
        task = self._create_stale_task()
        closed = close_abandoned_tasks()
        self.assertEqual(closed, 1)

        task.refresh_from_db()
        self.assertEqual(task.status, "completed")
        self.assertIsNotNone(task.completed_at)
        self.assertTrue(task.metadata.get("auto_closed"))

    def test_close_abandoned_tasks_skips_recent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )
        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, "active")

    def test_close_abandoned_tasks_skips_already_closed(self):
        task = self._create_stale_task()
        TaskService.complete_task(task.id)

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, "completed")

    def test_close_abandoned_tasks_skips_killed(self):
        task = self._create_stale_task()
        TaskService.kill_task(task.id)

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, "killed")

    def test_close_abandoned_tasks_multiple(self):
        self._create_stale_task()
        self._create_stale_task()
        # One recent task should not be closed
        TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 2)
        self.assertEqual(Task.objects.filter(status="active").count(), 1)
