import uuid
from unittest.mock import patch

from django.db import transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.work.models import Task
from apps.platform.work.reasons import PARENT_KILLED, SUBTASK_LIMIT, TASK_LIMIT
from apps.platform.work.services import TaskService
from core.vocabulary import (
    TASK_OUTCOME_DELIVERED, TASK_STATUS_ACTIVE, TASK_STATUS_COMPLETED,
    TASK_STATUS_KILLED)


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
        )
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)
        self.assertEqual(task.balance_snapshot_micros, 3_000_000)
        self.assertEqual(task.provider_cost_limit_micros, 10_000_000)
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

    def _task(self, balance=20_000_000, limit=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
        )

    def test_accumulate_cost_increments_both_totals_and_count(self):
        task = self._task(limit=self.limit)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=3_000_000, provider_cost_micros=2_000_000)
        self.assertEqual(result.total_billed_cost_micros, 3_000_000)
        self.assertEqual(result.total_provider_cost_micros, 2_000_000)
        self.assertEqual(result.event_count, 1)
        self.assertIsNotNone(result.last_event_at)
        self.assertEqual(verdicts, {"crossed_task_limit": False,
                                    "crossed_subtask_limit": False,
                                    "task_not_active": False})

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=2_000_000, provider_cost_micros=1_000_000)
        self.assertEqual(result.total_billed_cost_micros, 5_000_000)
        self.assertEqual(result.total_provider_cost_micros, 3_000_000)
        self.assertEqual(result.event_count, 2)
        self.assertFalse(any(verdicts.values()))

    def test_crossing_provider_limit_returns_verdict_and_persists(self):
        task = self._task(balance=100_000_000, limit=self.limit)
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000_000, provider_cost_micros=9_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])

        # Next 2M pushes the PROVIDER total to 11M > the 10M limit — the
        # verdict fires, but the event still lands and counts (never raises,
        # never rolls back).
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000_000, provider_cost_micros=2_000_000)
        self.assertTrue(verdicts["crossed_task_limit"])
        self.assertFalse(verdicts["task_not_active"])
        self.assertEqual(result.total_provider_cost_micros, 11_000_000)
        self.assertEqual(result.total_billed_cost_micros, 2_000_000)

        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 11_000_000)
        self.assertEqual(task.total_billed_cost_micros, 2_000_000)
        self.assertEqual(task.event_count, 2)
        # accumulate_cost never kills — the caller owns the kill flow.
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)

    def test_only_the_provider_total_races_the_limit(self):
        task = self._task(balance=100_000_000, limit=self.limit)
        # Billed way past the limit, provider under it -> nothing fires.
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=50_000_000, provider_cost_micros=1_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])

    def test_accumulate_cost_null_limits_never_flags(self):
        task = self._task(balance=1_000_000)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=999_999_999_999,
            provider_cost_micros=999_999_999_999)
        self.assertEqual(result.total_billed_cost_micros, 999_999_999_999)
        self.assertEqual(result.total_provider_cost_micros, 999_999_999_999)
        self.assertEqual(result.status, TASK_STATUS_ACTIVE)
        self.assertFalse(any(verdicts.values()))

    def test_accumulate_cost_exact_limit_not_crossed(self):
        task = self._task(limit=self.limit)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=0, provider_cost_micros=10_000_000)
        self.assertEqual(result.total_provider_cost_micros, 10_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])
        self.assertEqual(result.status, TASK_STATUS_ACTIVE)

    def test_accumulate_cost_one_over_limit_crosses(self):
        task = self._task(limit=self.limit)
        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=0, provider_cost_micros=10_000_001)
        self.assertTrue(verdicts["crossed_task_limit"])
        task.refresh_from_db()
        self.assertEqual(task.total_provider_cost_micros, 10_000_001)

    def test_accumulate_cost_on_killed_task_returns_not_active_and_persists(self):
        # Limit of 1: any attributed event would cross it — but on a killed
        # task NO limit verdict fires (the signal already announced itself).
        task = self._task(limit=1)
        TaskService.kill_task(task.id)

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000, provider_cost_micros=5_000_000)
        self.assertTrue(verdicts["task_not_active"])
        self.assertFalse(verdicts["crossed_task_limit"])

        # The late event still landed, billed, and counted into BOTH totals.
        self.assertEqual(result.status, TASK_STATUS_KILLED)
        task.refresh_from_db()
        self.assertEqual(task.total_billed_cost_micros, 1_000)
        self.assertEqual(task.total_provider_cost_micros, 5_000_000)
        self.assertEqual(task.event_count, 1)

    def test_accumulate_cost_on_completed_task_returns_not_active_and_persists(self):
        task = self._task(limit=self.limit)
        TaskService.close_task(task.id, TASK_OUTCOME_DELIVERED)

        result, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=1_000, provider_cost_micros=2_000)
        self.assertTrue(verdicts["task_not_active"])
        self.assertEqual(result.status, TASK_STATUS_COMPLETED)
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
        self.assertEqual(killed.status, TASK_STATUS_KILLED)
        self.assertIsNotNone(killed.completed_at)
        self.assertEqual(killed.metadata["kill_reason"], TASK_LIMIT)

    def test_kill_task_idempotent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.kill_task(task.id)
        killed, _ = TaskService.kill_task(task.id)  # second call = no-op
        self.assertEqual(killed.status, TASK_STATUS_KILLED)

    def test_kill_task_noop_on_completed(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.close_task(task.id, TASK_OUTCOME_DELIVERED)
        result, _ = TaskService.kill_task(task.id)
        self.assertEqual(result.status, TASK_STATUS_COMPLETED)  # not changed to killed


class TaskServiceCompleteTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", products=["metering", "billing"]
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1"
        )

    def test_close_task_sets_status(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        completed, transitioned = TaskService.close_task(
            task.id, TASK_OUTCOME_DELIVERED)
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, TASK_STATUS_COMPLETED)
        self.assertIsNotNone(completed.completed_at)

    def test_close_task_idempotent(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.close_task(task.id, TASK_OUTCOME_DELIVERED)
        completed, transitioned = TaskService.close_task(
            task.id, TASK_OUTCOME_DELIVERED)
        self.assertFalse(transitioned)
        self.assertEqual(completed.status, TASK_STATUS_COMPLETED)

    def test_close_task_noop_on_killed(self):
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0
        )
        TaskService.kill_task(task.id)
        result, transitioned = TaskService.close_task(
            task.id, TASK_OUTCOME_DELIVERED)
        self.assertFalse(transitioned)
        self.assertEqual(result.status, TASK_STATUS_KILLED)  # not changed to completed


class KillTaskTransitionFlagTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="KillFlag")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="kf1")
        self.task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status=TASK_STATUS_ACTIVE,
            billing_owner_id=self.customer.id, balance_snapshot_micros=0,
        )

    def test_transitioned_true_exactly_once(self):
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertTrue(transitioned)
        self.assertEqual(task.status, TASK_STATUS_KILLED)
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertFalse(transitioned)
        self.assertEqual(task.status, TASK_STATUS_KILLED)

    def test_transitioned_false_on_completed_task(self):
        with transaction.atomic():
            TaskService.close_task(self.task.id, TASK_OUTCOME_DELIVERED)
        with transaction.atomic():
            task, transitioned = TaskService.kill_task(self.task.id)
        self.assertFalse(transitioned)
        self.assertEqual(task.status, TASK_STATUS_COMPLETED)  # kill never demotes completed


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
        self.assertEqual(task.status, TASK_STATUS_KILLED)
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

    def test_winning_kill_stamps_the_announcement(self):
        """#43 §B: the kill flip, its event, and the announce_outbox_id stamp
        are one atomic unit — the stamped id IS the emitted event's row."""
        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=10_000_000,
            billing_owner_id=self.customer.id,
        )
        TaskService.kill_and_announce(
            task.id, TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        task.refresh_from_db()
        event = self._events().get()
        self.assertEqual(task.announce_outbox_id, event.id)
        self.assertIs(event.payload["re_announcement"], False)
        # The losing replay never touches the stamp.
        TaskService.kill_and_announce(
            task.id, TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        task.refresh_from_db()
        self.assertEqual(task.announce_outbox_id, event.id)

    def test_subtask_kill_stamps_the_subtask_event(self):
        parent = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            billing_owner_id=self.customer.id,
        )
        sub = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=1_000_000,
            billing_owner_id=self.customer.id, parent=parent,
        )
        TaskService.kill_and_announce(
            sub.id, SUBTASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        sub.refresh_from_db()
        parent.refresh_from_db()
        event = OutboxEvent.objects.get(event_type="subtask.limit_exceeded")
        self.assertEqual(sub.announce_outbox_id, event.id)
        # The parent keeps running, unstamped — nothing was announced for it.
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertIsNone(parent.announce_outbox_id)

    def test_failed_event_insert_rolls_the_kill_flip_back(self):
        """#43 §A — the kill-flip sibling of delivery pin 2: the flip and its
        event are one transaction, so a failed task.limit_exceeded INSERT
        (real SQL error — only a genuine DB error aborts the transaction)
        takes the active->killed flip down with it. kill_and_announce
        swallows the failure (never a 5xx for recorded money) and the next
        event's verdict retries the kill."""
        from django.db import connection

        orig_create = OutboxEvent.objects.create

        def _create(**kwargs):
            if kwargs.get("event_type") == "task.limit_exceeded":
                with connection.cursor() as cur:
                    cur.execute("SELECT 1/0")
            return orig_create(**kwargs)

        task = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=10_000_000,
            billing_owner_id=self.customer.id,
        )
        with patch.object(OutboxEvent.objects, "create", _create):
            transitioned = TaskService.kill_and_announce(
                task.id, TASK_LIMIT,
                tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertFalse(transitioned)
        task.refresh_from_db()
        self.assertEqual(task.status, TASK_STATUS_ACTIVE)  # flip rolled back with the event
        self.assertIsNone(task.announce_outbox_id)
        self.assertEqual(self._events().count(), 0)

    def test_cascaded_children_stay_unstamped(self):
        """A cascaded child's flip is a silent state change (the parent's
        event is the one signal) — it must never look unannounced to the
        patrol, which is what a stamp of its own would fix; instead the null
        stamp + kill_reason=parent_killed marks it as nothing-to-announce."""
        parent = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=10_000_000,
            billing_owner_id=self.customer.id,
        )
        child = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            billing_owner_id=self.customer.id, parent=parent,
        )
        TaskService.kill_and_announce(
            parent.id, TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        parent.refresh_from_db()
        child.refresh_from_db()
        self.assertEqual(parent.announce_outbox_id, self._events().get().id)
        self.assertEqual(child.status, TASK_STATUS_KILLED)
        self.assertIsNone(child.announce_outbox_id)
        self.assertEqual(child.metadata["kill_reason"], PARENT_KILLED)
