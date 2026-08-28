from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.platform.work.services import TaskService
from apps.platform.work.tasks import close_abandoned_tasks
from core.vocabulary import (
    TASK_OUTCOME_DELIVERED,
    TASK_STATUS_ACTIVE, TASK_STATUS_COMPLETED, TASK_STATUS_EXPIRED,
    TASK_STATUS_KILLED)


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

    def test_close_abandoned_tasks_expires_stale(self):
        # `expired` means exactly *nobody ever told UBB how this ended*
        # (#408). It used to read `completed` with a marker in metadata, so
        # the state claimed a delivery the tenant never declared and only the
        # marker said otherwise. The state carries it now, so the marker is
        # gone rather than moved.
        task = self._create_stale_task()
        closed = close_abandoned_tasks()
        self.assertEqual(closed, 1)

        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_EXPIRED)
        self.assertIsNotNone(task.completed_at)
        self.assertEqual(task.metadata, {})

    def test_close_abandoned_tasks_skips_recent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )
        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)

    def test_close_abandoned_tasks_skips_already_closed(self):
        # And the tenant's declaration survives the sweeper untouched:
        # terminal to anything is never permitted, so a closed unit is not
        # re-stated as an expiry an hour later.
        task = self._create_stale_task()
        TaskService.close_task(task.id, TASK_OUTCOME_DELIVERED)

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_COMPLETED)

    def test_close_abandoned_tasks_skips_killed(self):
        task = self._create_stale_task()
        TaskService.kill_task(task.id)

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 0)

        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_KILLED)

    def test_close_abandoned_tasks_multiple(self):
        self._create_stale_task()
        self._create_stale_task()
        # One recent task should not be closed
        TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )

        closed = close_abandoned_tasks()
        self.assertEqual(closed, 2)
        self.assertEqual(
            Task.objects.filter(status=TASK_STATUS_ACTIVE).count(), 1)
