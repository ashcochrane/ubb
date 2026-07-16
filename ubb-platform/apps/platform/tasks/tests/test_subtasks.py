"""Subtask containment — service-level semantics (#38, spec §A/§B).

A subtask is a Task row with `parent` set: its spend rolls up into the
parent's totals (containment: the parent sees everything), its own limit
kills it ALONE, a parent kill/close cascades DOWNWARD to its active
subtasks — containment cuts downward, never upward.
"""
import uuid

from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tasks import reasons
from apps.platform.tasks.models import Task
from apps.platform.tasks.services import TaskService
from apps.platform.tenants.models import Tenant


class SubtaskTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Subtasks", products=["metering", "billing"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _task(self, limit=None, floor=None, balance=100_000_000, parent=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit, floor_snapshot_micros=floor,
            billing_owner_id=self.customer.id, parent=parent)

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)


class CreateSubtaskTest(SubtaskTestBase):
    def test_create_task_with_parent(self):
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        self.assertEqual(sub.parent_id, parent.id)
        self.assertEqual(sub.status, "active")
        self.assertEqual(list(parent.subtasks.all()), [sub])

    def test_create_task_refuses_a_subtask_parent(self):
        # One containment level at launch: the parent must itself be
        # parentless. The start-gate refuses this with
        # subtask_depth_exceeded; the service guard is defense in depth.
        parent = self._task()
        sub = self._task(parent=parent)
        with self.assertRaises(ValueError):
            self._task(parent=sub)


class RollupTest(SubtaskTestBase):
    def test_subtask_spend_rolls_up_into_parent_totals(self):
        parent = self._task()
        sub = self._task(parent=parent)
        unit, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=3_000_000, provider_cost_micros=2_000_000)

        # The named unit's totals are the subtask's.
        self.assertEqual(unit.id, sub.id)
        self.assertEqual(unit.total_billed_cost_micros, 3_000_000)
        self.assertEqual(unit.total_provider_cost_micros, 2_000_000)
        self.assertEqual(unit.event_count, 1)
        self.assertFalse(any(verdicts.values()))

        # Containment: the parent sees everything underneath it — both
        # totals, the event count, and the heartbeat.
        parent.refresh_from_db()
        self.assertEqual(parent.total_billed_cost_micros, 3_000_000)
        self.assertEqual(parent.total_provider_cost_micros, 2_000_000)
        self.assertEqual(parent.event_count, 1)
        self.assertIsNotNone(parent.last_event_at)

    def test_parent_direct_events_and_rollup_share_the_totals(self):
        parent = self._task()
        sub = self._task(parent=parent)
        TaskService.accumulate_cost(
            parent.id, billed_cost_micros=1_000_000, provider_cost_micros=1_000_000)
        TaskService.accumulate_cost(
            sub.id, billed_cost_micros=2_000_000, provider_cost_micros=2_000_000)
        parent.refresh_from_db()
        sub.refresh_from_db()
        self.assertEqual(parent.total_provider_cost_micros, 3_000_000)
        self.assertEqual(parent.event_count, 2)
        self.assertEqual(sub.total_provider_cost_micros, 2_000_000)
        self.assertEqual(sub.event_count, 1)

    def test_killed_subtask_late_events_still_roll_up(self):
        # Killed is a signal point, not a wall — a late event on a killed
        # subtask lands, bills, and KEEPS counting into the parent (the
        # parent's cap covers everything underneath it).
        parent = self._task(limit=10_000_000)
        sub = self._task(parent=parent)
        TaskService.kill_task(sub.id)

        unit, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=1_000_000, provider_cost_micros=4_000_000)
        self.assertTrue(verdicts["task_not_active"])
        parent.refresh_from_db()
        self.assertEqual(parent.total_provider_cost_micros, 4_000_000)

        # ... and can even trip the parent's limit.
        _, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=1_000_000, provider_cost_micros=7_000_000)
        self.assertTrue(verdicts["crossed_task_limit"])
        self.assertTrue(verdicts["task_not_active"])

    def test_non_active_parent_still_accumulates_but_never_flags(self):
        # The parent's signal already fired — rollup keeps recording the
        # truth without re-announcing on every late child event.
        parent = self._task(limit=1)
        sub = self._task(parent=parent)
        TaskService.kill_task(parent.id)

        _, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=2_000_000, provider_cost_micros=2_000_000)
        self.assertFalse(verdicts["crossed_task_limit"])
        parent.refresh_from_db()
        self.assertEqual(parent.total_provider_cost_micros, 2_000_000)


class SubtaskVerdictTest(SubtaskTestBase):
    def test_subtask_own_limit_fires_crossed_subtask_limit(self):
        parent = self._task(limit=100_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        unit, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=0, provider_cost_micros=6_000_000)
        self.assertTrue(verdicts["crossed_subtask_limit"])
        self.assertFalse(verdicts["crossed_task_limit"])
        self.assertFalse(verdicts["crossed_floor_snapshot"])
        self.assertFalse(verdicts["task_not_active"])

    def test_parent_limit_fires_crossed_task_limit_on_a_subtask_event(self):
        parent = self._task(limit=10_000_000)
        sub = self._task(parent=parent)  # uncapped subtask
        _, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=0, provider_cost_micros=11_000_000)
        self.assertTrue(verdicts["crossed_task_limit"])
        self.assertFalse(verdicts["crossed_subtask_limit"])

    def test_both_limits_crossing_on_one_event_fires_both(self):
        parent = self._task(limit=10_000_000)
        sub = self._task(limit=5_000_000, parent=parent)
        _, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=0, provider_cost_micros=12_000_000)
        self.assertTrue(verdicts["crossed_subtask_limit"])
        self.assertTrue(verdicts["crossed_task_limit"])

    def test_only_the_provider_total_races_a_subtask_limit(self):
        # Pin 14 (subtask leg): billed way past the limit, provider under it
        # -> nothing fires.
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        unit, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=50_000_000, provider_cost_micros=1_000_000)
        self.assertFalse(any(verdicts.values()))
        self.assertEqual(unit.total_billed_cost_micros, 50_000_000)
        self.assertEqual(unit.total_provider_cost_micros, 1_000_000)

    def test_subtask_floor_snapshot_is_its_own(self):
        # The floor snapshot stays own-row: a subtask races the snapshot it
        # took at ITS start; only the LIMIT rolls up to the parent.
        parent = self._task(floor=0, balance=100_000_000)
        sub = self._task(floor=0, balance=5_000_000, parent=parent)
        _, verdicts = TaskService.accumulate_cost(
            sub.id, billed_cost_micros=6_000_000, provider_cost_micros=0)
        self.assertTrue(verdicts["crossed_floor_snapshot"])
        self.assertFalse(verdicts["crossed_task_limit"])

    def test_top_level_verdicts_carry_the_subtask_key(self):
        # The verdict dict has ONE shape everywhere (spec §B) — a top-level
        # task simply never fires the subtask key.
        task = self._task(limit=1_000_000)
        _, verdicts = TaskService.accumulate_cost(
            task.id, billed_cost_micros=0, provider_cost_micros=2_000_000)
        self.assertIn("crossed_subtask_limit", verdicts)
        self.assertFalse(verdicts["crossed_subtask_limit"])
        self.assertTrue(verdicts["crossed_task_limit"])


class KillCascadeTest(SubtaskTestBase):
    def test_kill_subtask_kills_it_alone(self):
        parent = self._task()
        sub = self._task(parent=parent)
        killed, transitioned = TaskService.kill_task(sub.id, reason=reasons.SUBTASK_LIMIT)
        self.assertTrue(transitioned)
        self.assertEqual(killed.status, "killed")
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")  # containment never cuts upward

    def test_kill_parent_cascades_to_active_subtasks(self):
        parent = self._task()
        sub_active = self._task(parent=parent)
        sub_done = self._task(parent=parent)
        TaskService.complete_task(sub_done.id)

        _, transitioned = TaskService.kill_task(parent.id, reason=reasons.TASK_LIMIT)
        self.assertTrue(transitioned)
        sub_active.refresh_from_db()
        sub_done.refresh_from_db()
        self.assertEqual(sub_active.status, "killed")
        self.assertEqual(sub_active.metadata["kill_reason"], reasons.PARENT_KILLED)
        self.assertIsNotNone(sub_active.completed_at)
        # Terminal subtasks are left untouched by the cascade.
        self.assertEqual(sub_done.status, "completed")

    def test_kill_parent_second_call_does_not_recascade(self):
        parent = self._task()
        TaskService.kill_task(parent.id)
        # A subtask that (racily) survived the first kill is NOT re-swept by
        # an idempotent no-op kill — only the winning transition cascades.
        late_sub = Task.objects.create(
            tenant=self.tenant, customer=self.customer, parent=parent,
            balance_snapshot_micros=0)
        _, transitioned = TaskService.kill_task(parent.id)
        self.assertFalse(transitioned)
        late_sub.refresh_from_db()
        self.assertEqual(late_sub.status, "active")

    def test_complete_parent_auto_completes_active_subtasks(self):
        parent = self._task()
        sub = self._task(parent=parent)
        sub_killed = self._task(parent=parent)
        TaskService.kill_task(sub_killed.id)

        completed, transitioned = TaskService.complete_task(parent.id)
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, "completed")
        sub.refresh_from_db()
        sub_killed.refresh_from_db()
        self.assertEqual(sub.status, "completed")
        self.assertIsNotNone(sub.completed_at)
        # A killed subtask stays killed — cleanup never rewrites history.
        self.assertEqual(sub_killed.status, "killed")

    def test_complete_subtask_completes_it_alone(self):
        parent = self._task()
        sub = self._task(parent=parent)
        completed, transitioned = TaskService.complete_task(sub.id)
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, "completed")
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")


class AnnounceTest(SubtaskTestBase):
    def test_subtask_kill_announces_subtask_limit_exceeded(self):
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent,
                         balance=100_000_000)
        TaskService.accumulate_cost(
            sub.id, billed_cost_micros=8_000_000, provider_cost_micros=6_000_000)
        transitioned = TaskService.kill_and_announce(
            sub.id, reasons.SUBTASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertTrue(transitioned)

        self.assertEqual(self._events("task.limit_exceeded").count(), 0)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 1)
        payload = self._events("subtask.limit_exceeded").get().payload
        self.assertEqual(payload["subtask_id"], str(sub.id))
        self.assertEqual(payload["parent_task_id"], str(parent.id))
        self.assertEqual(payload["reason"], reasons.SUBTASK_LIMIT)
        self.assertEqual(payload["total_billed_cost_micros"], 8_000_000)
        self.assertEqual(payload["total_provider_cost_micros"], 6_000_000)
        self.assertEqual(payload["provider_cost_limit_micros"], 5_000_000)
        parent.refresh_from_db()
        self.assertEqual(parent.status, "active")

    def test_parent_kill_announces_once_and_cascades_silently(self):
        parent = self._task(limit=10_000_000)
        sub = self._task(parent=parent)
        TaskService.accumulate_cost(
            sub.id, billed_cost_micros=0, provider_cost_micros=11_000_000)
        transitioned = TaskService.kill_and_announce(
            parent.id, reasons.TASK_LIMIT,
            tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.assertTrue(transitioned)

        # ONE task.limit_exceeded for the parent; the cascade flips the
        # subtask silently (it crossed nothing of its own).
        self.assertEqual(self._events("task.limit_exceeded").count(), 1)
        self.assertEqual(self._events("subtask.limit_exceeded").count(), 0)
        payload = self._events("task.limit_exceeded").get().payload
        self.assertEqual(payload["task_id"], str(parent.id))
        # The parent's totals are the rolled-up totals.
        self.assertEqual(payload["total_provider_cost_micros"], 11_000_000)
        sub.refresh_from_db()
        self.assertEqual(sub.status, "killed")
        self.assertEqual(sub.metadata["kill_reason"], reasons.PARENT_KILLED)


class KillPlanTest(SubtaskTestBase):
    """reasons.kill_plan — the single verdicts->kills map every ingest path
    shares (sync record, batch items, async settle)."""

    def _plan(self, verdicts, parent_id=None):
        unit_id = uuid.uuid4()
        defaults = {"crossed_task_limit": False, "crossed_subtask_limit": False,
                    "crossed_floor_snapshot": False, "task_not_active": False}
        return unit_id, reasons.kill_plan(unit_id, parent_id, {**defaults, **verdicts})

    def test_top_level_task_limit(self):
        unit_id, plan = self._plan({"crossed_task_limit": True})
        self.assertEqual(plan, [(unit_id, reasons.TASK_LIMIT)])

    def test_top_level_floor(self):
        unit_id, plan = self._plan({"crossed_floor_snapshot": True})
        self.assertEqual(plan, [(unit_id, reasons.CUSTOMER_FLOOR)])

    def test_top_level_limit_beats_floor(self):
        unit_id, plan = self._plan(
            {"crossed_task_limit": True, "crossed_floor_snapshot": True})
        self.assertEqual(plan, [(unit_id, reasons.TASK_LIMIT)])

    def test_subtask_own_limit_kills_it_alone(self):
        parent_id = uuid.uuid4()
        unit_id, plan = self._plan({"crossed_subtask_limit": True}, parent_id)
        self.assertEqual(plan, [(unit_id, reasons.SUBTASK_LIMIT)])

    def test_parent_limit_on_a_subtask_event_kills_the_parent(self):
        parent_id = uuid.uuid4()
        _, plan = self._plan({"crossed_task_limit": True}, parent_id)
        self.assertEqual(plan, [(parent_id, reasons.TASK_LIMIT)])

    def test_both_cross_subtask_killed_first_then_parent(self):
        # The subtask's own announcement must precede the parent's cascade —
        # a cascade-killed subtask can no longer win its own transition.
        parent_id = uuid.uuid4()
        unit_id, plan = self._plan(
            {"crossed_subtask_limit": True, "crossed_task_limit": True}, parent_id)
        self.assertEqual(plan, [(unit_id, reasons.SUBTASK_LIMIT),
                                (parent_id, reasons.TASK_LIMIT)])

    def test_nothing_crossing_plans_nothing(self):
        _, plan = self._plan({"task_not_active": True})
        self.assertEqual(plan, [])


class StopFieldsTest(SubtaskTestBase):
    """reasons.stop_fields — the scalar (stop_reason, stop_scope) pair on the
    ack; the WIDEST tripped scope wins the scalar slot (a parent trip must
    stop the whole tree)."""

    def _fields(self, verdicts, is_subtask=False):
        defaults = {"crossed_task_limit": False, "crossed_subtask_limit": False,
                    "crossed_floor_snapshot": False, "task_not_active": False}
        return reasons.stop_fields({**defaults, **verdicts}, is_subtask=is_subtask)

    def test_task_limit_scope_task(self):
        self.assertEqual(self._fields({"crossed_task_limit": True}),
                         (reasons.TASK_LIMIT, "task"))

    def test_subtask_limit_scope_subtask(self):
        self.assertEqual(
            self._fields({"crossed_subtask_limit": True}, is_subtask=True),
            (reasons.SUBTASK_LIMIT, "subtask"))

    def test_parent_trip_wins_the_scalar_over_the_subtask_trip(self):
        self.assertEqual(
            self._fields({"crossed_subtask_limit": True,
                          "crossed_task_limit": True}, is_subtask=True),
            (reasons.TASK_LIMIT, "task"))

    def test_floor_scope_follows_the_unit(self):
        self.assertEqual(self._fields({"crossed_floor_snapshot": True}),
                         (reasons.CUSTOMER_FLOOR, "task"))
        self.assertEqual(
            self._fields({"crossed_floor_snapshot": True}, is_subtask=True),
            (reasons.CUSTOMER_FLOOR, "subtask"))

    def test_not_active_scope_follows_the_unit(self):
        self.assertEqual(self._fields({"task_not_active": True}),
                         (reasons.TASK_NOT_ACTIVE, "task"))
        self.assertEqual(self._fields({"task_not_active": True}, is_subtask=True),
                         (reasons.TASK_NOT_ACTIVE, "subtask"))

    def test_nothing_fired(self):
        self.assertEqual(self._fields({}), (None, None))
