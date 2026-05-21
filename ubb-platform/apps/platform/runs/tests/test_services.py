from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.platform.runs.services import RunService, HardStopExceeded, RunNotActive


class RunServiceCreateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_create_run_with_explicit_limits(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=3_000_000,
            cost_limit_micros=10_000_000,
            hard_stop_balance_micros=-5_000_000,
        )
        self.assertEqual(run.status, "active")
        self.assertEqual(run.balance_snapshot_micros, 3_000_000)
        self.assertEqual(run.cost_limit_micros, 10_000_000)
        self.assertEqual(run.hard_stop_balance_micros, -5_000_000)
        self.assertEqual(run.total_cost_micros, 0)
        self.assertEqual(run.event_count, 0)
        self.assertEqual(run.tenant_id, self.tenant.id)
        self.assertEqual(run.customer_id, self.customer.id)

    def test_create_run_null_limits(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0,
        )
        self.assertIsNone(run.cost_limit_micros)
        self.assertIsNone(run.hard_stop_balance_micros)

    def test_create_run_with_metadata_and_external_id(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0,
            metadata={"foo": "bar"}, external_run_id="ext-123",
        )
        self.assertEqual(run.metadata, {"foo": "bar"})
        self.assertEqual(run.external_run_id, "ext-123")


class RunServiceAccumulateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )
        self.cost_limit = 10_000_000
        self.hard_stop = -5_000_000

    def test_accumulate_cost_increments_total_and_count(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        result = RunService.accumulate_cost(run.id, 3_000_000)
        self.assertEqual(result.total_cost_micros, 3_000_000)
        self.assertEqual(result.event_count, 1)

        result = RunService.accumulate_cost(run.id, 2_000_000)
        self.assertEqual(result.total_cost_micros, 5_000_000)
        self.assertEqual(result.event_count, 2)

    def test_accumulate_cost_ceiling_exceeded_raises(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        # Accumulate up to 9M (under 10M limit)
        RunService.accumulate_cost(run.id, 9_000_000)

        # Next 2M would push to 11M > 10M limit
        with self.assertRaises(HardStopExceeded) as ctx:
            RunService.accumulate_cost(run.id, 2_000_000)
        self.assertEqual(ctx.exception.reason, "cost_limit_exceeded")
        self.assertEqual(ctx.exception.total_cost_micros, 11_000_000)

        # Run is NOT modified (caller handles kill)
        run.refresh_from_db()
        self.assertEqual(run.status, "active")
        self.assertEqual(run.total_cost_micros, 9_000_000)

    def test_accumulate_cost_floor_exceeded_raises(self):
        # balance=3M, hard_stop_balance=-5M
        # So total cost can go up to 8M before floor is hit (3M - 8M = -5M)
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=3_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        RunService.accumulate_cost(run.id, 7_000_000)  # est balance = -4M, above -5M

        # Next 2M: est balance = 3M - 9M = -6M < -5M floor
        with self.assertRaises(HardStopExceeded) as ctx:
            RunService.accumulate_cost(run.id, 2_000_000)
        self.assertEqual(ctx.exception.reason, "balance_floor_exceeded")
        self.assertEqual(ctx.exception.estimated_balance, -6_000_000)

        # Run is NOT modified
        run.refresh_from_db()
        self.assertEqual(run.status, "active")
        self.assertEqual(run.total_cost_micros, 7_000_000)

    def test_accumulate_cost_null_limits_never_stops(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=1_000_000,
        )
        # Accumulate a huge amount — no limits should fire
        result = RunService.accumulate_cost(run.id, 999_999_999_999)
        self.assertEqual(result.total_cost_micros, 999_999_999_999)
        self.assertEqual(result.status, "active")

    def test_accumulate_cost_exact_ceiling_allowed(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        # Accumulate exactly to the limit (10M)
        result = RunService.accumulate_cost(run.id, 10_000_000)
        self.assertEqual(result.total_cost_micros, 10_000_000)
        self.assertEqual(result.status, "active")

    def test_accumulate_cost_one_over_ceiling_raises(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        with self.assertRaises(HardStopExceeded):
            RunService.accumulate_cost(run.id, 10_000_001)

    def test_accumulate_cost_on_killed_run_raises_not_active(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        RunService.kill_run(run.id)

        with self.assertRaises(RunNotActive) as ctx:
            RunService.accumulate_cost(run.id, 1_000)
        self.assertEqual(ctx.exception.status, "killed")

    def test_accumulate_cost_on_completed_run_raises_not_active(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=20_000_000,
            cost_limit_micros=self.cost_limit, hard_stop_balance_micros=self.hard_stop,
        )
        RunService.complete_run(run.id)

        with self.assertRaises(RunNotActive) as ctx:
            RunService.accumulate_cost(run.id, 1_000)
        self.assertEqual(ctx.exception.status, "completed")


class RunServiceKillTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_kill_run_sets_status_and_completed_at(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        killed = RunService.kill_run(run.id, reason="cost_limit_exceeded")
        self.assertEqual(killed.status, "killed")
        self.assertIsNotNone(killed.completed_at)
        self.assertEqual(killed.metadata["kill_reason"], "cost_limit_exceeded")

    def test_kill_run_idempotent(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        RunService.kill_run(run.id)
        killed = RunService.kill_run(run.id)  # second call = no-op
        self.assertEqual(killed.status, "killed")

    def test_kill_run_noop_on_completed(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        RunService.complete_run(run.id)
        result = RunService.kill_run(run.id)
        self.assertEqual(result.status, "completed")  # not changed to killed


class RunServiceCompleteTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_complete_run_sets_status(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        completed = RunService.complete_run(run.id)
        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)

    def test_complete_run_idempotent(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        RunService.complete_run(run.id)
        completed = RunService.complete_run(run.id)
        self.assertEqual(completed.status, "completed")

    def test_complete_run_noop_on_killed(self):
        run = RunService.create_run(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        RunService.kill_run(run.id)
        result = RunService.complete_run(run.id)
        self.assertEqual(result.status, "killed")  # not changed to completed
