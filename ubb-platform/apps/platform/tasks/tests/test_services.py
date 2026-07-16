import uuid

from django.db import transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks.models import Task
from apps.platform.tasks.reasons import TASK_LIMIT
from apps.platform.tasks.services import TaskService


class TaskServiceCreateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_create_task_with_explicit_limits(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=3_000_000,
            provider_cost_limit_micros=10_000_000,
            floor_snapshot_micros=-5_000_000,
        )
        self.assertEqual(task.status, "active")
        self.assertEqual(task.balance_snapshot_micros, 3_000_000)
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)
        self.assertEqual(task.floor_snapshot_micros, -5_000_000)
        self.assertEqual(task.total_billed_cost_micros, 0)
        self.assertEqual(task.total_provider_cost_micros, 0)
        self.assertEqual(task.event_count, 0)
        self.assertEqual(task.tenant_id, self.tenant.id)
        self.assertEqual(task.customer_id, self.customer.id)

    def test_create_task_null_limits(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
        )
        self.assertIsNone(task.provider_cost_limit_micros)
        self.assertIsNone(task.floor_snapshot_micros)

    def test_create_task_with_metadata_and_external_id(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            metadata={"foo": "bar"}, external_task_id="ext-123",
        )
        self.assertEqual(task.metadata, {"foo": "bar"})
        self.assertEqual(task.external_task_id, "ext-123")


class TaskServiceAccumulateTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )
        self.limit = 10_000_000
        self.floor = -5_000_000

    def _task(self, balance=20_000_000, limit=None, floor=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit, floor_snapshot_micros=floor,
        )

    def test_accumulate_cost_increments_both_totals_and_count(self):
        task = self._task(limit=self.limit, floor=self.floor)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=3_000_000, provider_cost_micros=2_000_000)
        self.assertEqual(result.total_billed_cost_micros, 3_000_000)
        self.assertEqual(result.total_provider_cost_micros, 2_000_000)
        self.assertEqual(result.event_count, 1)
        self.assertIsNotNone(result.last_event_at)
        self.assertEqual(verdicts, {"crossed_task_limit": False,
                                    "crossed_subtask_limit": False,
                                    "crossed_floor_snapshot": False,
                                    "task_not_active": False})

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=2_000_000, provider_cost_micros=1_000_000)
        self.assertEqual(result.total_billed_cost_micros, 5_000_000)
        self.assertEqual(result.total_provider_cost_micros, 3_000_000)
        self.assertEqual(result.event_count, 2)
        self.assertFalse(any(verdicts.values()))

    def test_crossing_provider_limit_returns_verdict_and_persists(self):
        task = self._task(balance=100_000_000, limit=self.limit, floor=self.floor)
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000_000, provider_cost_micros=9_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])

        # Next 2M pushes the PROVIDER total to 11M > the 10M limit — the
        # verdict fires, but the event still lands and counts (never raises,
        # never rolls back).
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000_000, provider_cost_micros=2_000_000)
        self.assertTrue(verdicts["crossed_task_limit"])
        self.assertFalse(verdicts["crossed_floor_snapshot"])
        self.assertFalse(verdicts["task_not_active"])
        self.assertEqual(result.total_provider_cost_micros, 11_000_000)
        self.assertEqual(result.total_billed_cost_micros, 2_000_000)

        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(task.total_billed_cost_micros, 2_000_000)
        self.assertEqual(task.event_count, 2)
        # accumulate_cost never kills — the caller owns the kill flow.
        self.assertEqual(task.status, "active")

    def test_only_the_provider_total_races_the_limit(self):
        task = self._task(balance=100_000_000, limit=self.limit)
        # Billed way past the limit, provider under it -> nothing fires.
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=50_000_000, provider_cost_micros=1_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])

    def test_crossing_floor_snapshot_returns_verdict_and_persists(self):
        # balance=3M, floor=-5M: the BILLED total may reach 8M before the
        # estimated balance (3M - total_billed) drops below the floor.
        task = self._task(balance=3_000_000, floor=self.floor)
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=7_000_000, provider_cost_micros=0)
        self.assertFalse(verdicts["crossed_floor_snapshot"])  # est -4M >= -5M

        # Next 2M: est balance = 3M - 9M = -6M < -5M floor.
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=2_000_000, provider_cost_micros=0)
        self.assertTrue(verdicts["crossed_floor_snapshot"])
        self.assertFalse(verdicts["crossed_task_limit"])
        self.assertEqual(result.total_billed_cost_micros, 9_000_000)

        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 9_000_000)
        self.assertEqual(task.event_count, 2)
        self.assertEqual(task.status, "active")

    def test_accumulate_cost_null_limits_never_flags(self):
        task = self._task(balance=1_000_000)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=999_999_999_999,
            provider_cost_micros=999_999_999_999)
        self.assertEqual(result.total_billed_cost_micros, 999_999_999_999)
        self.assertEqual(result.total_provider_cost_micros, 999_999_999_999)
        self.assertEqual(result.status, "active")
        self.assertFalse(any(verdicts.values()))

    def test_accumulate_cost_exact_limit_not_crossed(self):
        task = self._task(limit=self.limit, floor=self.floor)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=0, provider_cost_micros=10_000_000)
        self.assertEqual(result.total_provider_cost_micros, 10_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])
        self.assertEqual(result.status, "active")

    def test_accumulate_cost_one_over_limit_crosses(self):
        task = self._task(limit=self.limit, floor=self.floor)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=0, provider_cost_micros=10_000_001)
        self.assertTrue(verdicts["crossed_task_limit"])
        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 10_000_001)

    def test_accumulate_cost_on_killed_task_returns_not_active_and_persists(self):
        # Limit of 1: any attributed event would cross it — but on a killed
        # task NO limit verdict fires (the signal already announced itself).
        task = self._task(limit=1, floor=self.floor)
        TaskService.kill_task(task.id)

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000, provider_cost_micros=5_000_000)
        self.assertTrue(verdicts["task_not_active"])
        self.assertFalse(verdicts["crossed_task_limit"])
        self.assertFalse(verdicts["crossed_floor_snapshot"])

        # The late event still landed, billed, and counted into BOTH totals.
        self.assertEqual(result.status, "killed")
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 1_000)
        self.assertEqual(task.total_provider_cost_micros, 5_000_000)
        self.assertEqual(task.event_count, 1)

    def test_accumulate_cost_on_completed_task_returns_not_active_and_persists(self):
        task = self._task(limit=self.limit, floor=self.floor)
        TaskService.complete_task(task.id)

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000, provider_cost_micros=2_000)
        self.assertTrue(verdicts["task_not_active"])
        self.assertEqual(result.status, "completed")
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 1_000)
        self.assertEqual(task.total_provider_cost_micros, 2_000)
        self.assertEqual(task.event_count, 1)


class TaskServiceKillTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_kill_task_sets_status_and_completed_at(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        killed, _ = TaskService.kill_task(task.id, reason=TASK_LIMIT)
        self.assertEqual(killed.status, "killed")
        self.assertIsNotNone(killed.completed_at)
        self.assertEqual(killed.metadata["kill_reason"], TASK_LIMIT)

    def test_kill_task_idempotent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.kill_task(task.id)
        killed, _ = TaskService.kill_task(task.id)  # second call = no-op
        self.assertEqual(killed.status, "killed")

    def test_kill_task_noop_on_completed(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.complete_task(task.id)
        result, _ = TaskService.kill_task(task.id)
        self.assertEqual(result.status, "completed")  # not changed to killed


class TaskServiceCompleteTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_complete_task_sets_status(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        completed, transitioned = TaskService.complete_task(task.id)
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, "completed")
        self.assertIsNotNone(completed.completed_at)

    def test_complete_task_idempotent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.complete_task(task.id)
        completed, transitioned = TaskService.complete_task(task.id)
        self.assertFalse(transitioned)
        self.assertEqual(completed.status, "completed")

    def test_complete_task_noop_on_killed(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.kill_task(task.id)
        result, transitioned = TaskService.complete_task(task.id)
        self.assertFalse(transitioned)
        self.assertEqual(result.status, "killed")  # not changed to completed


class KillTaskTransitionFlagTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="KillFlag")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="kf1")
        self.task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            billing_owner_id=self.customer.id, balance_snapshot_micros=0,
        )

    def test_transitioned_true_exactly_once(self):
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertTrue(transitioned)
        self.assertEqual(task.status, "killed")
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertFalse(transitioned)
        self.assertEqual(task.status, "killed")

    def test_transitioned_false_on_completed_task(self):
        with transaction.atomic():
            TaskService.complete_task(self.task.id)
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertFalse(transitioned)
        self.assertEqual(task.status, "completed")  # kill never demotes completed


class KillAndAnnounceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Announce", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def _events(self):
        return OutboxEvent.objects.filter(event_type="task.limit_exceeded")

    def test_emits_limit_event_exactly_once(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=10_000_000,
            billing_owner_id=self.customer.id,
        )
        TaskService.accumulate_cost(
            task.id, billed_cost_micros=15_000_000, provider_cost_micros=11_000_000)

        transitioned = TaskService.kill_and_announce(
            task.id, TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertTrue(transitioned)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")
        self.assertEqual(task.metadata["kill_reason"], TASK_LIMIT)

        self.assertEqual(self._events().count(), 1)
        payload = self._events().get().payload
        self.assertEqual(payload["task_id"], str(task.id))
        self.assertEqual(payload["reason"], TASK_LIMIT)
        self.assertEqual(payload["tenant_id"], str(self.tenant.id))
        self.assertEqual(payload["customer_id"], str(self.customer.id))
        self.assertEqual(payload["billing_owner_id"], str(self.customer.id))
        self.assertEqual(payload["total_billed_cost_micros"], 15_000_000)
        self.assertEqual(payload["total_provider_cost_micros"], 11_000_000)
        self.assertEqual(payload["provider_cost_limit_micros"], 10_000_000)
        self.assertNotIn("scope", payload)

        # Second call: the transition already happened — no second event.
        transitioned = TaskService.kill_and_announce(
            task.id, TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertFalse(transitioned)
        self.assertEqual(self._events().count(), 1)

    def test_never_raises_on_bogus_task_id(self):
        transitioned = TaskService.kill_and_announce(
            uuid.uuid4(), TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertFalse(transitioned)
        self.assertEqual(self._events().count(), 0)
