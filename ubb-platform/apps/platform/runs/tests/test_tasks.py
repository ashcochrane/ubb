from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService
from apps.platform.runs.tasks import close_abandoned_runs


class CloseAbandonedRunsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def _create_stale_run(self, **kwargs):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000, **kwargs
        )
        # Backdate created_at to make it stale (>1 hour old)
        Run.objects.filter(id=run.id).update(
            created_at=timezone.now() - timedelta(hours=2)
        )
        return run

    def test_close_abandoned_runs_closes_stale(self):
        run = self._create_stale_run()
        closed = close_abandoned_runs()
        self.assertEqual(closed, 1)

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")
        self.assertIsNotNone(run.completed_at)
        self.assertTrue(run.metadata.get("auto_closed"))

    def test_close_abandoned_runs_skips_recent(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )
        closed = close_abandoned_runs()
        self.assertEqual(closed, 0)

        run.refresh_from_db()
        self.assertEqual(run.status, "active")

    def test_close_abandoned_runs_skips_already_closed(self):
        run = self._create_stale_run()
        RunService.complete_run(run.id)

        closed = close_abandoned_runs()
        self.assertEqual(closed, 0)

        run.refresh_from_db()
        self.assertEqual(run.status, "completed")

    def test_close_abandoned_runs_skips_killed(self):
        run = self._create_stale_run()
        RunService.kill_run(run.id)

        closed = close_abandoned_runs()
        self.assertEqual(closed, 0)

        run.refresh_from_db()
        self.assertEqual(run.status, "killed")

    def test_close_abandoned_runs_multiple(self):
        self._create_stale_run()
        self._create_stale_run()
        # One recent run should not be closed
        RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=10_000_000
        )

        closed = close_abandoned_runs()
        self.assertEqual(closed, 2)
        self.assertEqual(Run.objects.filter(status="active").count(), 1)
