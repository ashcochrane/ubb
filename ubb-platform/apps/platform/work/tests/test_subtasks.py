"""Subtask containment — service-level semantics (#38, spec §A/§B).

A subtask is a Task row with `parent` set: its spend rolls up into the
parent's totals (containment: the parent sees everything), its own limit
kills it ALONE, a parent's stop cascades DOWNWARD to its active
subtasks — containment cuts downward, never upward.

⚠ WHAT THE CASCADE WRITES IS NOT ALWAYS WHAT THE PARENT GOT (#408): a kill
cascades `killed`, but a CLOSE cascades `cancelled`, because the tenant
declared the delivery of the parent and declared nothing about each contained
piece.

⚠ AND WHAT IT WRITES DOWN BESIDE THE STATE IS THREE DIFFERENT RECORDS (#413).
Each ending records a reason belonging to whoever ended it — the tenant's close
writes the caller-supplied concept, UBB's own two stops write the UBB-produced
one — while the MECHANISM is the same on all three and is written on every
cascaded row, because a cascade announces nothing of its own.
"""
import uuid

from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.work import reasons
from apps.platform.work.models import Task
from apps.platform.work.services import CloseDeclaration, TaskService
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    OUTCOME_REASON_EXECUTION_FAILED, OUTCOME_REASON_PARENT_CLOSED,
    TASK_OUTCOME_DELIVERED, TASK_OUTCOME_FAILED,
    TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED, TASK_STATUS_COMPLETED,
    TASK_STATUS_EXPIRED, TASK_STATUS_FAILED, TASK_STATUS_KILLED,
    TRIGGER_SOURCE_PARENT_CASCADE)


class SubtaskTestBase(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Subtasks", products=["metering", "billing"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1")

    def _task(self, limit=None, balance=100_000_000, parent=None):
        return TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=balance,
            provider_cost_limit_micros=limit,
            billing_owner_id=self.customer.id, parent=parent)

    def _events(self, event_type):
        return OutboxEvent.objects.filter(event_type=event_type)


class CreateSubtaskTest(SubtaskTestBase):
    def test_create_task_with_parent(self):
        parent = self._task()
        sub = self._task(limit=5_000_000, parent=parent)
        self.assertEqual(sub.parent_id, parent.id)
        self.assertEqual(sub.status, TASK_STATUS_ACTIVE)
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
        self.assertEqual(killed.status, TASK_STATUS_KILLED)
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)  # containment never cuts upward

    def test_kill_parent_cascades_to_active_subtasks(self):
        parent = self._task()
        sub_active = self._task(parent=parent)
        sub_done = self._task(parent=parent)
        TaskService.close_task(sub_done.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))

        _, transitioned = TaskService.kill_task(parent.id, reason=reasons.TASK_LIMIT)
        self.assertTrue(transitioned)
        sub_active.refresh_from_db()
        sub_done.refresh_from_db()
        self.assertEqual(sub_active.status, TASK_STATUS_KILLED)
        self.assertEqual(sub_active.metadata["kill_reason"], reasons.PARENT_KILLED)
        self.assertIsNotNone(sub_active.completed_at)
        # Terminal subtasks are left untouched by the cascade.
        self.assertEqual(sub_done.status, TASK_STATUS_COMPLETED)

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
        self.assertEqual(late_sub.status, TASK_STATUS_ACTIVE)

    def test_close_parent_withdraws_active_subtasks(self):
        # The cascade WITHDRAWS rather than delivers (#408): the tenant
        # declared the delivery of the parent and declared nothing about each
        # contained piece, and `completed` may only ever mean a declaration
        # the tenant actually made.
        parent = self._task()
        sub = self._task(parent=parent)
        sub_killed = self._task(parent=parent)
        TaskService.kill_task(sub_killed.id)

        completed, transitioned = TaskService.close_task(
            parent.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, TASK_STATUS_COMPLETED)
        sub.refresh_from_db()
        sub_killed.refresh_from_db()
        self.assertEqual(sub.status, TASK_STATUS_CANCELLED)
        self.assertIsNotNone(sub.completed_at)
        # A killed subtask stays killed — cleanup never rewrites history.
        self.assertEqual(sub_killed.status, TASK_STATUS_KILLED)

    def test_complete_subtask_completes_it_alone(self):
        parent = self._task()
        sub = self._task(parent=parent)
        completed, transitioned = TaskService.close_task(
            sub.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        self.assertTrue(transitioned)
        self.assertEqual(completed.status, TASK_STATUS_COMPLETED)
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)


class CascadeRecordTest(SubtaskTestBase):
    """WHAT A CASCADE WRITES DOWN, AND WHY IT IS THREE RECORDS RATHER THAN ONE
    (#413, spec §8).

    A parent's end stops the work still running inside it, and each of the three
    endings records a reason belonging to whoever ended it. A tenant's close is a
    DECLARATION, so the work it withdrew carries `outcome_reason` — the
    caller-supplied set. UBB's own two stops carry `reason_code`, the
    UBB-produced one. Tidying the two together would put a word meaning *the
    tenant said so* on a row no tenant said anything about.

    THE MECHANISM IS THE SAME ON ALL THREE AND IS WRITTEN ON EVERY CASCADED ROW.
    A cascade emits no event — the parent's own signal is the one announcement —
    so the row is the only place a reader can find out that this piece was
    stopped by containment rather than by anything it did itself.

    ⚠ EVERY REASON BELOW IS ASSERTED BY CONSTANT IDENTITY. A case spelling the
    value would keep passing against a boundary that had stopped importing the
    registry, which is the whole debt this area is paying down — and this app
    holds other slices' retired words under ceilings on how many files may spell
    them.
    """

    def _a_parent_and_its_contained_work(self):
        parent = self._task()
        return parent, self._task(parent=parent)

    def test_a_close_cascade_records_the_withdrawal_and_its_mechanism(self):
        parent, contained = self._a_parent_and_its_contained_work()

        TaskService.close_task(parent.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))

        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_CANCELLED)
        self.assertEqual(contained.outcome_reason, OUTCOME_REASON_PARENT_CLOSED)
        self.assertEqual(contained.metadata["trigger_source"],
                         TRIGGER_SOURCE_PARENT_CASCADE)
        # The parent's own record is untouched by the cascade it caused: the
        # tenant explained the whole thing and explained none of the pieces.
        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_COMPLETED)
        self.assertEqual(parent.outcome_reason, "")

    def test_contained_work_closed_beforehand_keeps_its_own_outcome(self):
        """The cascade only ever touches work still running.

        A state nobody asserted never borrows a state that means someone did —
        and the converse is what this case pins: a declaration somebody DID make
        is never overwritten by one nobody made.
        """
        parent = self._task()
        declared = self._task(parent=parent)
        still_running = self._task(parent=parent)
        TaskService.close_task(
            declared.id,
            CloseDeclaration(TASK_OUTCOME_FAILED,
                             OUTCOME_REASON_EXECUTION_FAILED))

        TaskService.close_task(parent.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))

        declared.refresh_from_db()
        still_running.refresh_from_db()
        self.assertEqual(declared.status, TASK_STATUS_FAILED)
        self.assertEqual(declared.outcome_reason,
                         OUTCOME_REASON_EXECUTION_FAILED)
        # Not merely a surviving reason — the cascade did not touch the row at
        # all, and the mechanism it stamps is what says so.
        self.assertNotIn("trigger_source", declared.metadata)
        self.assertEqual(still_running.status, TASK_STATUS_CANCELLED)
        self.assertEqual(still_running.outcome_reason,
                         OUTCOME_REASON_PARENT_CLOSED)

    def test_a_kill_cascade_records_containment_and_its_mechanism(self):
        parent, contained = self._a_parent_and_its_contained_work()

        TaskService.kill_task(parent.id, reason=reasons.TASK_LIMIT)

        parent.refresh_from_db()
        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_KILLED)
        self.assertEqual(contained.metadata["kill_reason"],
                         reasons.PARENT_KILLED)
        self.assertEqual(contained.metadata["trigger_source"],
                         TRIGGER_SOURCE_PARENT_CASCADE)
        # IT NEVER INHERITS THE PARENT'S CAUSE, and that is the half a report of
        # what really reached a ceiling depends on: this piece crossed nothing
        # of its own.
        self.assertNotEqual(contained.metadata["kill_reason"],
                            parent.metadata["kill_reason"])

    def test_an_expiry_cascade_records_the_silence_window_and_its_mechanism(self):
        parent, contained = self._a_parent_and_its_contained_work()

        TaskService.expire_task(parent.id, reason=reasons.SILENCE_WINDOW)

        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_EXPIRED)
        self.assertEqual(contained.metadata["kill_reason"],
                         reasons.SILENCE_WINDOW)
        self.assertEqual(contained.metadata["trigger_source"],
                         TRIGGER_SOURCE_PARENT_CASCADE)

    def test_the_three_cascades_record_three_different_reasons(self):
        """The records are told apart, not merely present.

        Each case above asserts one of them; asserting the three are distinct is
        what stops a repair that collapsed them onto one value passing all three.
        """
        recorded = set()
        for stop, reason in ((TaskService.kill_task, reasons.TASK_LIMIT),
                             (TaskService.expire_task, reasons.SILENCE_WINDOW)):
            parent, contained = self._a_parent_and_its_contained_work()
            stop(parent.id, reason=reason)
            contained.refresh_from_db()
            recorded.add(contained.metadata["kill_reason"])

        parent, contained = self._a_parent_and_its_contained_work()
        TaskService.close_task(parent.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))
        contained.refresh_from_db()
        recorded.add(contained.outcome_reason)

        self.assertEqual(recorded, {reasons.PARENT_KILLED,
                                    reasons.SILENCE_WINDOW,
                                    OUTCOME_REASON_PARENT_CLOSED})


class ContainmentCutsDownwardOnlyTest(SubtaskTestBase):
    """A parent's end reaches the work inside it; nothing inside it reaches the
    parent (#413, spec §8).

    Contained work that failed is frequently recoverable — retried, sent to a
    second provider, degraded gracefully — and only the tenant's code knows
    whether the whole thing still delivered. Once that outcome IS the money, an
    automatic upward cascade would let one contained detail destroy the charge
    for work that really delivered through a fallback.

    A per-kind *this one fails its parent* flag was rejected for the same
    reason: it makes the commercial outcome a function of configuration set
    weeks earlier rather than an assertion made at the moment the answer is
    known.
    """

    def test_contained_work_that_failed_leaves_the_whole_thing_running(self):
        parent = self._task()
        contained = self._task(parent=parent)

        TaskService.close_task(
            contained.id,
            CloseDeclaration(TASK_OUTCOME_FAILED,
                             OUTCOME_REASON_EXECUTION_FAILED))

        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(parent.outcome_reason, "")
        self.assertIsNone(parent.completed_at)

    def test_the_whole_thing_still_closes_as_delivered_after_that(self):
        """The half that decides money: the outcome is an assertion made when
        the answer is known, never a function of what happened underneath."""
        parent = self._task()
        contained = self._task(parent=parent)
        fallback = self._task(parent=parent)
        TaskService.close_task(
            contained.id,
            CloseDeclaration(TASK_OUTCOME_FAILED,
                             OUTCOME_REASON_EXECUTION_FAILED))
        TaskService.close_task(fallback.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))

        delivered, transitioned = TaskService.close_task(
            parent.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))

        self.assertTrue(transitioned)
        self.assertEqual(delivered.status, TASK_STATUS_COMPLETED)
        # The failure keeps its own record; the delivery keeps its own.
        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_FAILED)
        self.assertEqual(contained.outcome_reason,
                         OUTCOME_REASON_EXECUTION_FAILED)

    def test_stopping_contained_work_leaves_the_whole_thing_counting(self):
        """Stopping one piece stops it alone, AND THE CONJUNCTION IS THE CLAIM.

        Two cases above prove each half on its own — one that the parent stays
        running, one that a late report on stopped work still rolls up — and
        neither is evidence for the other. This one acts once and asks both
        questions of the same parent afterwards, which is what *the parent keeps
        running and counting* actually means.
        """
        parent = self._task(limit=100_000_000)
        contained = self._task(parent=parent)
        TaskService.accumulate_cost(
            contained.id, billed_cost_micros=1_000_000,
            provider_cost_micros=2_000_000)

        TaskService.kill_task(contained.id, reason=reasons.SUBTASK_LIMIT)

        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        rolled_up_before = parent.total_provider_cost_micros

        TaskService.accumulate_cost(
            contained.id, billed_cost_micros=3_000_000,
            provider_cost_micros=5_000_000)
        sibling = self._task(parent=parent)
        TaskService.accumulate_cost(
            sibling.id, billed_cost_micros=1_000_000,
            provider_cost_micros=1_000_000)

        parent.refresh_from_db()
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)
        self.assertEqual(parent.total_provider_cost_micros,
                         rolled_up_before + 6_000_000)
        self.assertEqual(parent.event_count, 3)
        # And the piece that was stopped stayed stopped — the parent going on
        # is not the cascade running backwards.
        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_KILLED)


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
        self.assertEqual(parent.status, TASK_STATUS_ACTIVE)

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
        self.assertEqual(sub.status, TASK_STATUS_KILLED)
        self.assertEqual(sub.metadata["kill_reason"], reasons.PARENT_KILLED)


class KillPlanTest(SubtaskTestBase):
    """reasons.kill_plan — the single verdicts->kills map every ingest path
    shares (sync record, batch items, async settle)."""

    def _plan(self, verdicts, parent_id=None):
        unit_id = uuid.uuid4()
        defaults = {"crossed_task_limit": False, "crossed_subtask_limit": False,
                    "task_not_active": False}
        return unit_id, reasons.kill_plan(unit_id, parent_id, {**defaults, **verdicts})

    def test_top_level_task_limit(self):
        unit_id, plan = self._plan({"crossed_task_limit": True})
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
                    "task_not_active": False}
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

    def test_not_active_scope_follows_the_unit(self):
        self.assertEqual(self._fields({"task_not_active": True}),
                         (reasons.TASK_NOT_ACTIVE, "task"))
        self.assertEqual(self._fields({"task_not_active": True}, is_subtask=True),
                         (reasons.TASK_NOT_ACTIVE, "subtask"))

    def test_nothing_fired(self):
        self.assertEqual(self._fields({}), (None, None))
