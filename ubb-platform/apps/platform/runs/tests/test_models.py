from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run


class RunModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
            run_cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_run_creation_defaults(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
        )
        self.assertEqual(run.status, "active")
        self.assertEqual(run.total_cost_micros, 0)
        self.assertEqual(run.event_count, 0)
        self.assertIsNone(run.completed_at)

    def test_run_str_representation(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=1_000_000,
            total_cost_micros=500_000,
        )
        self.assertIn("active", str(run))
        self.assertIn("500000", str(run))

    def test_run_with_all_limits(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=5_000_000,
            cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.assertEqual(run.cost_limit_micros, 10_000_000)
        self.assertEqual(run.hard_stop_balance_micros, -5_000_000)
        self.assertEqual(run.balance_snapshot_micros, 5_000_000)

    def test_run_without_limits(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
        )
        self.assertIsNone(run.cost_limit_micros)
        self.assertIsNone(run.hard_stop_balance_micros)

    def test_run_with_external_run_id(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            external_run_id="workflow-abc-123",
        )
        self.assertEqual(run.external_run_id, "workflow-abc-123")

    def test_run_with_metadata(self):
        run = Run.objects.create(
            tenant=self.tenant,
            customer=self.customer,
            balance_snapshot_micros=0,
            metadata={"workflow": "scouting", "region": "AU"},
        )
        self.assertEqual(run.metadata["workflow"], "scouting")
