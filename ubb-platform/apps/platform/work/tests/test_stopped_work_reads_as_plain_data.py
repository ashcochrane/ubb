"""The kernel's three reads behind the two spend-control reports (#465,
slice 6 §14): a ceiling's episodes, every completed unit's utilisation, and
the work a customer-wide stop swept — plain data off the rows, never ORM
objects (ADR-001), joined by the composition layer and by nothing here.

WHICH UNITS ARE A CEILING'S EPISODES, AND WHICH NEVER ARE (#153 §10.2, §10.4).
A row is a unit UBB stopped on its OWN cost ceiling: `killed` with the
ceiling's cause. An indeterminate unit is never one — the ceiling fires on the
known total alone, so a unit with unresolved cost below the line is never
killed by it and cannot appear. An expiry is never one: a window running out
writes `expired`, a state this read does not select. Contained work the
cascade stopped is never one: it crossed nothing of its own and carries the
cascade's cause. A pool's kill is never one: it carries the pool's word.

THE PAIR AT THE CROSSING COMES OFF THE ORIGINAL ANNOUNCEMENT, THE PAIR AT THE
END OFF THE ROW. The row's two counters keep moving after the kill (every
late event lands and counts), so the row can only say where the unit ENDED;
what it read when the ceiling fired is what the kill announced — read off
the first `task.killed` / `subtask.killed` the unit emitted, never a patrol's
re-mint, which carries the row as it stood at repair time. Where no
announcement survives outbox retention the pair is null, never zero.
"""
from datetime import timedelta

from django.utils import timezone

from apps.platform.events.models import OutboxEvent
from apps.platform.events.schemas import SubtaskKilled, TaskKilled
from apps.platform.work import queries, reasons
from apps.platform.work.models import STOP_CAUSE_KEY, Task
from apps.platform.work.services import (
    CloseDeclaration, TaskService, ceiling_control_id)
from apps.platform.work.tests._helpers import WorkTestBase
from apps.platform.customers.models import Customer
from core.crossing import (
    CEILING_REMAINING_MICROS_KEY, CEILING_STATUS_KEY, CEILING_USED_PERCENTAGE_KEY)
from core.vocabulary import (
    CEILING_BASIS_COST, CEILING_STATUS_CEILING_REACHED,
    CEILING_STATUS_INDETERMINATE, CEILING_STATUS_NOT_APPLICABLE,
    CEILING_STATUS_WITHIN_CEILING, CONTROL_FAMILY_CEILING,
    TASK_OUTCOME_DELIVERED, TASK_STATUS_COMPLETED, TRIGGER_SOURCE_POOL_CROSSING,
    TRIGGER_SOURCE_USAGE_INGEST)


class StoppedWorkTestBase(WorkTestBase):
    def _unit_with_cost(self, *, ceiling, known, unresolved=0, parent=None,
                        task_type="", customer=None):
        unit = TaskService.create_task(
            self.tenant, customer or self.customer, balance_snapshot_micros=0,
            task_cogs_ceiling_micros=ceiling, task_type=task_type,
            billing_owner_id=(customer or self.customer).id, parent=parent)
        Task.objects.filter(id=unit.id).update(
            total_provider_cost_micros=known, unresolved_event_count=unresolved)
        unit.refresh_from_db()
        return unit

    def _kill_on_the_ceiling(self, unit, *, trigger_source=TRIGGER_SOURCE_USAGE_INGEST):
        self.assertTrue(TaskService.kill_and_announce(
            unit.id, reasons.TASK_COGS_CEILING, tenant_id=self.tenant.id,
            customer_id=unit.customer_id, trigger_source=trigger_source,
            control_id=ceiling_control_id(unit)))
        unit.refresh_from_db()
        return unit

    def _episodes(self, **filters):
        return queries.ceiling_episodes(self.tenant.id, **filters)


class CeilingEpisodesTest(StoppedWorkTestBase):
    def test_a_unit_killed_on_its_ceiling_is_an_episode_with_both_pairs(self):
        unit = self._unit_with_cost(ceiling=10, known=12, unresolved=1,
                                    task_type="pipeline")
        self._kill_on_the_ceiling(unit)
        # Late events keep landing after the kill: the row moves on, the
        # announcement does not.
        Task.objects.filter(id=unit.id).update(
            total_provider_cost_micros=15, unresolved_event_count=2)

        [row] = self._episodes()
        self.assertEqual(row["task_id"], str(unit.id))
        self.assertIsNone(row["parent_task_id"])
        self.assertEqual(row["customer_id"], str(self.customer.id))
        self.assertEqual(row["task_type"], "pipeline")
        self.assertEqual(row["stop_scope"], reasons.unit_scope(is_subtask=False))
        self.assertEqual(row["reason_code"], reasons.TASK_COGS_CEILING)
        self.assertEqual(row["control_family"], CONTROL_FAMILY_CEILING)
        self.assertEqual(row["control_id"], str(self.tenant.id))
        self.assertEqual(row["ceiling_basis"], CEILING_BASIS_COST)
        self.assertEqual(row["trigger_source"], TRIGGER_SOURCE_USAGE_INGEST)
        self.assertEqual(row["task_cogs_ceiling_micros"], 10)
        self.assertEqual(row["opened_at"], unit.completed_at)
        self.assertEqual(row["crossed_provider_cost_micros"], 12)
        self.assertEqual(row["crossed_unresolved_event_count"], 1)
        self.assertEqual(row["final_provider_cost_micros"], 15)
        self.assertEqual(row["final_unresolved_event_count"], 2)

    def test_the_crossing_pair_is_null_where_no_announcement_survives(self):
        unit = self._unit_with_cost(ceiling=10, known=12)
        self._kill_on_the_ceiling(unit)
        OutboxEvent.objects.filter(event_type=TaskKilled.EVENT_TYPE).delete()

        [row] = self._episodes()
        self.assertIsNone(row["crossed_provider_cost_micros"])
        self.assertIsNone(row["crossed_unresolved_event_count"])
        self.assertEqual(row["final_provider_cost_micros"], 12)

    def test_a_re_mint_is_never_read_as_the_crossing(self):
        """A patrol re-mint carries the row as it stands at repair time — the
        FIRST announcement is the one that read the crossing."""
        unit = self._unit_with_cost(ceiling=10, known=12)
        self._kill_on_the_ceiling(unit)
        Task.objects.filter(id=unit.id).update(total_provider_cost_micros=99)
        original = OutboxEvent.objects.get(event_type=TaskKilled.EVENT_TYPE)
        OutboxEvent.objects.create(
            tenant_id=self.tenant.id, event_type=TaskKilled.EVENT_TYPE,
            payload={**original.payload, "re_announcement": True,
                     "total_provider_cost_micros": 99})

        [row] = self._episodes()
        self.assertEqual(row["crossed_provider_cost_micros"], 12)

    def test_contained_work_killed_on_its_own_ceiling_lists_at_its_altitude(self):
        parent = self._unit_with_cost(ceiling=None, known=0)
        piece = self._unit_with_cost(ceiling=5, known=7, parent=parent)
        self._kill_on_the_ceiling(piece)

        [row] = self._episodes()
        self.assertEqual(row["task_id"], str(piece.id))
        self.assertEqual(row["parent_task_id"], str(parent.id))
        self.assertEqual(row["stop_scope"], reasons.unit_scope(is_subtask=True))
        self.assertEqual(row["crossed_provider_cost_micros"], 7)
        self.assertEqual(OutboxEvent.objects.filter(
            event_type=SubtaskKilled.EVENT_TYPE).count(), 1)

    def test_what_is_never_an_episode(self):
        """A cascade-killed piece, a pool's kill, an expiry, an active unit
        that is indeterminate, and a completed unit — none is a ceiling's."""
        parent = self._unit_with_cost(ceiling=10, known=12)
        contained = self._unit_with_cost(ceiling=None, known=0, parent=parent)
        self._kill_on_the_ceiling(parent)          # cascades onto `contained`
        pooled = self._unit_with_cost(ceiling=100, known=1)
        self.assertTrue(TaskService.kill_and_announce(
            pooled.id, reasons.CUSTOMER_SPEND_POOL, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_POOL_CROSSING, control_id="the-pool"))
        expired = self._unit_with_cost(ceiling=100, known=1)
        TaskService.expire_task(expired.id, reasons.ABSOLUTE_DEADLINE,
                                control_id=str(self.tenant.id))
        indeterminate = self._unit_with_cost(ceiling=100, known=1, unresolved=3)
        self.assertEqual(indeterminate.ceiling_assessment.status,
                         CEILING_STATUS_INDETERMINATE)
        done = self._unit_with_cost(ceiling=100, known=1)
        TaskService.close_task(done.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))

        listed = {row["task_id"] for row in self._episodes()}
        self.assertEqual(listed, {str(parent.id)})
        contained.refresh_from_db()
        self.assertEqual(contained.metadata[STOP_CAUSE_KEY], reasons.PARENT_KILLED)

    def test_each_filter_narrows(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="cust-2")
        mine = self._kill_on_the_ceiling(
            self._unit_with_cost(ceiling=1, known=2, task_type="a"))
        theirs = self._kill_on_the_ceiling(
            self._unit_with_cost(ceiling=1, known=2, task_type="b", customer=other))

        def ids(**filters):
            return {row["task_id"] for row in self._episodes(**filters)}

        self.assertEqual(ids(), {str(mine.id), str(theirs.id)})
        self.assertEqual(ids(customer_id=other.id), {str(theirs.id)})
        self.assertEqual(ids(task_type="a"), {str(mine.id)})
        self.assertEqual(ids(since=timezone.now() + timedelta(hours=1)), set())
        self.assertEqual(ids(until=mine.completed_at), set())
        self.assertEqual(ids(since=mine.completed_at,
                             until=mine.completed_at + timedelta(seconds=1)),
                         {str(mine.id), str(theirs.id)})

    def test_a_tenant_with_no_stopped_work_answers_nothing(self):
        self._unit_with_cost(ceiling=10, known=1)
        self.assertEqual(self._episodes(), [])


class CeilingUtilisationTest(StoppedWorkTestBase):
    def _rows(self, **filters):
        return {row["task_id"]: row
                for row in queries.ceiling_utilisation(self.tenant.id, **filters)}

    def test_every_completed_unit_carries_its_assessment_and_nulls_where_no_ceiling(self):
        within = self._unit_with_cost(ceiling=100, known=25, task_type="a")
        TaskService.close_task(within.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        floor = self._unit_with_cost(ceiling=100, known=25, unresolved=1)
        TaskService.close_task(floor.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        reached = self._kill_on_the_ceiling(self._unit_with_cost(ceiling=10, known=12))
        uncapped = self._unit_with_cost(ceiling=None, known=25)
        TaskService.close_task(uncapped.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        still_running = self._unit_with_cost(ceiling=100, known=1)

        rows = self._rows()
        self.assertNotIn(str(still_running.id), rows)
        self.assertEqual(set(rows), {str(within.id), str(floor.id),
                                     str(reached.id), str(uncapped.id)})
        row = rows[str(within.id)]
        self.assertEqual(row[CEILING_STATUS_KEY], CEILING_STATUS_WITHIN_CEILING)
        self.assertEqual(row[CEILING_USED_PERCENTAGE_KEY], 25)
        self.assertEqual(row[CEILING_REMAINING_MICROS_KEY], 75)
        self.assertEqual(row["task_type"], "a")
        self.assertEqual(row["task_cogs_ceiling_micros"], 100)
        self.assertEqual(row["final_provider_cost_micros"], 25)
        self.assertEqual(row["final_unresolved_event_count"], 0)
        self.assertIsNotNone(row["completed_at"])
        self.assertIsNone(row["parent_task_id"])
        self.assertEqual(rows[str(floor.id)][CEILING_STATUS_KEY],
                         CEILING_STATUS_INDETERMINATE)
        self.assertEqual(rows[str(floor.id)]["final_unresolved_event_count"], 1)
        self.assertEqual(rows[str(reached.id)][CEILING_STATUS_KEY],
                         CEILING_STATUS_CEILING_REACHED)
        self.assertEqual(rows[str(reached.id)][CEILING_REMAINING_MICROS_KEY], 0)
        no_ceiling = rows[str(uncapped.id)]
        self.assertEqual(no_ceiling[CEILING_STATUS_KEY], CEILING_STATUS_NOT_APPLICABLE)
        self.assertIsNone(no_ceiling[CEILING_USED_PERCENTAGE_KEY])
        self.assertIsNone(no_ceiling[CEILING_REMAINING_MICROS_KEY])
        self.assertIsNone(no_ceiling["task_cogs_ceiling_micros"])

    def test_each_filter_narrows(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="cust-2")
        mine = self._unit_with_cost(ceiling=100, known=1, task_type="a")
        TaskService.close_task(mine.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        theirs = self._unit_with_cost(ceiling=100, known=1, task_type="b",
                                      customer=other)
        TaskService.close_task(theirs.id, CloseDeclaration(TASK_OUTCOME_DELIVERED))
        mine.refresh_from_db()

        self.assertEqual(set(self._rows()), {str(mine.id), str(theirs.id)})
        self.assertEqual(set(self._rows(customer_id=other.id)), {str(theirs.id)})
        self.assertEqual(set(self._rows(task_type="a")), {str(mine.id)})
        self.assertEqual(self._rows(until=mine.completed_at), {})
        self.assertEqual(set(self._rows(since=mine.completed_at)),
                         {str(mine.id), str(theirs.id)})


class CustomerWideStopsAppliedTest(StoppedWorkTestBase):
    def test_only_the_pools_kills_are_listed(self):
        swept = self._unit_with_cost(ceiling=100, known=1)
        self.assertTrue(TaskService.kill_and_announce(
            swept.id, reasons.CUSTOMER_SPEND_POOL, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_POOL_CROSSING, control_id="the-pool"))
        self._kill_on_the_ceiling(self._unit_with_cost(ceiling=1, known=2))
        swept.refresh_from_db()

        [row] = queries.customer_wide_stops_applied(self.tenant.id)
        self.assertEqual(row, {
            "task_id": str(swept.id), "customer_id": str(self.customer.id),
            "billing_owner_id": str(self.customer.id),
            "reason_code": reasons.CUSTOMER_SPEND_POOL,
            "control_id": "the-pool", "stopped_at": swept.completed_at})
        self.assertEqual(queries.customer_wide_stops_applied(
            self.tenant.id, since=swept.completed_at + timedelta(seconds=1)), [])


class TheRollupNoLongerCountsReachedCeilingsTest(StoppedWorkTestBase):
    def test_the_reached_count_left_the_task_analytics_row(self):
        """Testing Decisions claim 14: the count moved to Utilisation and
        headroom and LEFT the task analytics report."""
        unit = self._unit_with_cost(ceiling=10, known=12, task_type="a")
        Task.objects.filter(id=unit.id).update(status=TASK_STATUS_COMPLETED)
        [row] = queries.task_rollup_by_type(self.tenant.id)
        self.assertNotIn("limit_hit_count", row)
        self.assertEqual(row["run_count"], 1)
