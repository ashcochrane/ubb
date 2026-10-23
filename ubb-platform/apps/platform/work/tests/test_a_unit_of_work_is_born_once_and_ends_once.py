"""A unit of work is born once and ends once, and the database holds both
(#562, ADR-0007 §2).

Five columns of `ubb_task` carried their write-once rule in prose until this
module's migration: the model said what may happen to them and nothing kept it.

  * `parent_id` and `task_type` are FROZEN — a unit is never re-parented and
    never re-typed, which is what lets the accumulate primitive read both
    without a lock and what keeps every settled event on the unit meaning
    what it meant when it landed.
  * `status` is RESOLVE_ONCE — `active` is the one unresolved value, and a
    unit leaves it once, for one terminal state, and never moves again.
  * `outcome_reason` and `reason_detail` are SET_ONCE — written in the same
    write that ends the work, from nothing, and never again.

**THE DATABASE KEEPS THEM, NOT THE KERNEL.** `TaskService._flip` already
refuses a second transition and the cascade already selects only running
work, which is why nothing in the tree rewrites these columns today; ADR-0007
§2 is explicit that such a guard is not enforcement, because the writers it
cannot see — a data migration, a shell session, an admin form — are the ones
nobody is watching. So every refusal below is driven through all three doors:
`save()` (on the base, so `Task.save`'s own guard on the kind cannot answer
first), `QuerySet.update()` and raw SQL.

⚠ **THE CONTROLS ARE WHAT MAKE THE REFUSALS EVIDENCE.** A rule refusing every
update to this table would satisfy every prohibited case here and stop every
recording dead: a terminal unit keeps counting late events into its totals,
and the kernel stamps its announcement after the flip. So the admitted moves
go through the same three doors — the ending write itself, every other column
on a terminal row, and a full-row save re-sending unchanged values.
"""
import importlib

from django.db import connection
from django.test import TestCase

from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from apps.platform.work.models import TERMINAL_TASK_STATUSES, Task
from apps.platform.work.services import CloseDeclaration, TaskService
from apps.platform.work.tests._helpers import DOORS, WorkTestBase, refusal_from
from core.transitions import (
    FROZEN, RESOLVE_ONCE, SET_ONCE, columns_declared_into_defended_classes)
from core.vocabulary import (
    OUTCOME_REASON_TIMEOUT, OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR,
    TASK_OUTCOME_FAILED, TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_KILLED)

TABLE = Task._meta.db_table

#: The rule this module drives, addressed BY NAME: `ubb_task` carries a second
#: rule (`work/migrations/0022`'s containment check, BEFORE INSERT), and
#: `pg_trigger` promises no order (#352).
TRANSITION_TRIGGER = "trg_task_declared_transitions"
CONTAINMENT_TRIGGER = "trg_task_containment_shares_the_pricing_regime"

#: What each column declares, as the model must say it — the COLUMN names, as
#: the Charge's pointers are declared, because the walk that reads these
#: searches a trigger body and a trigger says `NEW.parent_id`.
DECLARED = {
    "status": RESOLVE_ONCE,
    "parent_id": FROZEN,
    "task_type": FROZEN,
    "outcome_reason": SET_ONCE,
    "reason_detail": SET_ONCE,
}

MIGRATION = importlib.import_module(
    "apps.platform.work.migrations.0028_a_unit_of_work_is_born_once_and_ends_once")


def refused_as(column):
    """The opening of the one refusal that names ``column`` — the column AND
    its class, because a rule naming only "something refused" would let a
    refusal from the wrong branch, or from the containment rule beside it,
    pass for this one."""
    return f"{column} is declared {DECLARED[column]}"


class UnitOfWorkTransitionTestBase(WorkTestBase):

    def _killed(self, **kwargs):
        unit = self._task(**kwargs)
        TaskService.kill_task(unit.id, "task_cogs_ceiling")
        unit.refresh_from_db()
        return unit

    def _failed(self, reason=OUTCOME_REASON_TIMEOUT, detail="it took too long"):
        unit = self._task()
        TaskService.close_task(
            unit.id, CloseDeclaration(TASK_OUTCOME_FAILED, reason, detail))
        unit.refresh_from_db()
        return unit

    def _refused_through_every_door(self, make, column, **columns):
        """``make`` builds a FRESH row per door, so no door asserts against a
        row an earlier door already tried to move."""
        for name, door in DOORS:
            with self.subTest(door=name):
                row = make()
                message = refusal_from(door, row, **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(refused_as(column), message)

    def _admitted_through_every_door(self, make, **columns):
        for name, door in DOORS:
            with self.subTest(door=name):
                row = make()
                self.assertIsNone(refusal_from(door, row, **columns))
                row.refresh_from_db()
                for column, value in columns.items():
                    self.assertEqual(getattr(row, column), value)


class AUnitIsBornOnceTest(UnitOfWorkTransitionTestBase):
    """FROZEN: where a unit sits and what kind of work it is never move."""

    def test_contained_work_is_never_re_parented(self):
        other = self._task()
        self._refused_through_every_door(
            lambda: self._task(parent=self._task()), "parent_id",
            parent_id=other.id)

    def test_contained_work_is_never_promoted_to_a_whole_unit(self):
        self._refused_through_every_door(
            lambda: self._task(parent=self._task()), "parent_id",
            parent_id=None)

    def test_a_whole_unit_is_never_moved_inside_another(self):
        container = self._task()
        self._refused_through_every_door(
            self._task, "parent_id", parent_id=container.id)

    def test_a_typed_unit_is_never_re_typed(self):
        self._refused_through_every_door(
            lambda: self._task(task_type="transcode"), "task_type",
            task_type="classify")

    def test_an_untyped_unit_is_never_typed_later(self):
        """`""` is a value here, not an absence: *a tenant who never declared
        a vocabulary*, and every event already on the unit was settled as
        untyped work."""
        self._refused_through_every_door(
            self._task, "task_type", task_type="transcode")

    def test_a_typed_unit_is_never_untyped(self):
        self._refused_through_every_door(
            lambda: self._task(task_type="transcode"), "task_type",
            task_type="")

    def test_neither_holds_on_a_finished_unit_either(self):
        """The rule is about the column, never the state: a stopped unit is
        no more re-typeable than a running one."""
        self._refused_through_every_door(
            lambda: self._killed(task_type="transcode"), "task_type",
            task_type="classify")


class AUnitEndsOnceTest(UnitOfWorkTransitionTestBase):
    """RESOLVE_ONCE: `active` is the unresolved value; a terminal one is final."""

    def test_no_terminal_state_moves_to_another(self):
        for state in sorted(TERMINAL_TASK_STATUSES):
            other = (TASK_STATUS_COMPLETED if state != TASK_STATUS_COMPLETED
                     else TASK_STATUS_FAILED)
            with self.subTest(state=state):
                def make(state=state):
                    unit = self._task()
                    Task.objects.filter(id=unit.id).update(status=state)
                    unit.refresh_from_db()
                    return unit
                self._refused_through_every_door(make, "status", status=other)

    def test_no_terminal_state_returns_to_active(self):
        self._refused_through_every_door(
            self._killed, "status", status=TASK_STATUS_ACTIVE)

    def test_a_stop_is_never_rewritten_as_a_delivery(self):
        """The rewrite with money behind it: `completed` is what a Charge keys
        on (#416), so a killed unit rewritten as delivered would be billed for
        work UBB itself stopped."""
        self._refused_through_every_door(
            self._killed, "status", status=TASK_STATUS_COMPLETED)

    def test_a_running_unit_ends_through_every_door(self):
        """THE CONTROL: resolving the value once is the whole permitted move."""
        for state in sorted(TERMINAL_TASK_STATUSES):
            with self.subTest(state=state):
                self._admitted_through_every_door(self._task, status=state)


class AnEndingIsExplainedOnceTest(UnitOfWorkTransitionTestBase):
    """SET_ONCE: the caller's reason and its sentence are written by the write
    that ends the work, from nothing, and never again."""

    def test_a_declared_reason_is_never_rewritten(self):
        self._refused_through_every_door(
            self._failed, "outcome_reason",
            outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)

    def test_a_declared_reason_is_never_erased(self):
        self._refused_through_every_door(
            self._failed, "outcome_reason", outcome_reason="")

    def test_a_declared_sentence_is_never_rewritten(self):
        self._refused_through_every_door(
            self._failed, "reason_detail", reason_detail="it never started")

    def test_a_declared_sentence_is_never_erased(self):
        self._refused_through_every_door(
            self._failed, "reason_detail", reason_detail="")

    def test_a_stop_nobody_explained_is_never_explained_later(self):
        """`""` on a killed unit is the record that no caller declared
        anything, and that stays true: UBB's own stops record their reason
        under the OTHER concept, in `metadata`."""
        self._refused_through_every_door(
            self._killed, "outcome_reason",
            outcome_reason=OUTCOME_REASON_TIMEOUT)
        self._refused_through_every_door(
            self._killed, "reason_detail", reason_detail="after the fact")

    def test_a_running_unit_is_never_explained_before_it_ends(self):
        """Written WHEN the row enters its terminal state, which a write that
        leaves the state alone is not — and one that did would be rewritten by
        the close, which is the second write this class forbids."""
        self._refused_through_every_door(
            self._task, "outcome_reason",
            outcome_reason=OUTCOME_REASON_TIMEOUT)
        self._refused_through_every_door(
            self._task, "reason_detail", reason_detail="too early")

    def test_an_explanation_a_unit_was_born_with_is_never_rewritten(self):
        """SET_ONCE is *from nothing*: a rule about what may happen AFTER
        insert cannot stop a writer inserting a row that already carries a
        reason, but it can stop the ending write replacing it — so a set value
        stays set even on the one write that may set one."""
        def born_explained():
            return Task.objects.create(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0,
                outcome_reason=OUTCOME_REASON_TIMEOUT,
                reason_detail="written at birth")
        self._refused_through_every_door(
            born_explained, "outcome_reason", status=TASK_STATUS_FAILED,
            outcome_reason=OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR)
        self._refused_through_every_door(
            born_explained, "reason_detail", status=TASK_STATUS_FAILED,
            reason_detail="rewritten at the end")

    def test_the_ending_write_carries_both_through_every_door(self):
        """THE CONTROL: the close's own shape — the state and the explanation
        in one statement — is admitted whichever door it comes through."""
        self._admitted_through_every_door(
            self._task, status=TASK_STATUS_FAILED,
            outcome_reason=OUTCOME_REASON_TIMEOUT,
            reason_detail="it took too long")


class EverythingElseStillMovesTest(UnitOfWorkTransitionTestBase):
    """THE CONTROLS the refusals above are worth nothing without."""

    def test_a_finished_unit_keeps_counting(self):
        """A stop is a signal point and not a wall: late events land and count
        into a terminal unit's totals, and the kernel stamps the announcement
        and the mechanism on the row after the flip."""
        self._admitted_through_every_door(
            self._killed,
            total_provider_cost_micros=9_000_000,
            total_billed_cost_micros=12_000_000,
            event_count=7, unresolved_event_count=1,
            metadata={"trigger_source": "usage_ingest"})

    def test_re_sending_what_the_row_holds_is_not_a_move(self):
        """A full-row save writes every column, the five included; the rule
        judges a CHANGE, so an unchanged value is admitted on a finished unit
        and on a running one alike."""
        for make in (self._failed, lambda: self._task(parent=self._task(),
                                                      task_type="transcode")):
            unit = make()
            self._admitted_through_every_door(
                lambda unit=unit: Task.objects.get(id=unit.id),
                status=unit.status, parent_id=unit.parent_id,
                task_type=unit.task_type, outcome_reason=unit.outcome_reason,
                reason_detail=unit.reason_detail)

    def test_the_kernels_own_endings_still_land(self):
        """Every way the kernel ends work goes through the rule: a close that
        cascades `parent_closed` onto running contained work, and a kill that
        cascades onto its own."""
        closed, contained = self._a_parent_and_its_contained_work()
        TaskService.close_task(closed.id, CloseDeclaration("delivered"))
        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_CANCELLED)
        self.assertEqual(contained.outcome_reason, "parent_closed")

        killed, inside = self._a_parent_and_its_contained_work()
        TaskService.kill_task(killed.id, "task_cogs_ceiling")
        inside.refresh_from_db()
        self.assertEqual(inside.status, TASK_STATUS_KILLED)


class TheDeclarationAndTheRuleAreOneClaimTest(TestCase):
    """ADR-0007 §2 asks two things and they fail differently: a column with no
    declared class answers *what may happen to this?* nowhere, and a declared
    class with no rule behind it is the promise nothing keeps."""

    def test_the_model_declares_the_five(self):
        self.assertEqual(Task.transition_classes, DECLARED)

    def test_the_database_defends_what_the_model_declares(self):
        """Through the gate's own entry point (G19), not a second copy of its
        search."""
        declared = columns_declared_into_defended_classes([Task])
        self.assertEqual(
            declared, sorted(("Task", column, transition_class)
                             for column, transition_class in DECLARED.items()))
        self.assertEqual(
            columns_the_database_does_not_defend(declared,
                                                 declaring_models_by_table()),
            [])

    def test_both_rules_on_the_table_are_installed_by_name(self):
        """An exact SET: a third rule arriving here is read by a person before
        any by-name addressing quietly starts mattering."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
            self.assertEqual({row[0] for row in cursor.fetchall()},
                             {TRANSITION_TRIGGER, CONTAINMENT_TRIGGER})

    def test_the_migration_spells_the_unresolved_state_the_registry_names(self):
        """A migration must not import application code, so it spells
        `active` itself; this is what holds that spelling to the registry's."""
        self.assertEqual(MIGRATION.UNRESOLVED_STATUS, TASK_STATUS_ACTIVE)
        self.assertEqual(MIGRATION.TRIGGER, TRANSITION_TRIGGER)
