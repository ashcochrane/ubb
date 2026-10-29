"""A unit of work is born once and ends once, and the database holds both
(#562, ADR-0007 §2).

Five columns of `ubb_task` carried their write-once rule in prose until #562
gave them `trg_task_declared_transitions` (installed by `work/0028` before the
cutover, #190; by `work/0002_the_database_rules` since): the model said what
may happen to them and nothing kept it.

  * `parent_id` and `task_type` are FROZEN — a unit is never re-parented and
    never re-typed, which is what lets the accumulate primitive read both
    without a lock and what keeps every settled event on the unit meaning
    what it meant when it landed.
  * `status` is RESOLVE_ONCE — `active` is the one unresolved value, and a
    unit leaves it once, for one terminal state, and never moves again.
  * `outcome_reason` and `reason_detail` are SET_ONCE — written in the same
    write that ends the work, from nothing, and never again.

And six more since R10-W2 (`work/0029` before the cutover), which widened the
same rule rather than adding a second one:

  * what UBB recorded when it stopped the unit — `reason_code`,
    `trigger_source`, `control_family`, `control_id` — is SET_ONCE, from
    nothing to a value, once: the unit read publishes these as UBB's own
    assertions (#551), so a rewrite would be a stop UBB never made;
  * the expiry policy the start published — `start_absolute_deadline_seconds`
    and `start_silence_window_seconds` — is FROZEN, because a replay of the
    start answers from it (ADR-0019).

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
import re

from django.test import TestCase

from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from apps.platform.work import reasons
from apps.platform.work.models import (
    STOP_CAUSE_KEY, STOP_CONTROL_FAMILY_KEY, STOP_CONTROL_ID_KEY,
    STOP_MECHANISM_KEY, TERMINAL_TASK_STATUSES, Task)
from apps.platform.work.services import (
    CloseDeclaration, TaskService, ceiling_control_id)
from apps.platform.work.tests._helpers import (
    DOORS, WorkTestBase, refusal_from, rule_names_on)
from core.transitions import (
    FROZEN, RESOLVE_ONCE, SET_ONCE, columns_declared_into_defended_classes)
from core.vocabulary import (
    CONTROL_FAMILY_CEILING, CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
    OUTCOME_REASON_PARENT_CLOSED, OUTCOME_REASON_TIMEOUT,
    OUTCOME_REASON_UPSTREAM_PROVIDER_ERROR, TASK_OUTCOME_DELIVERED,
    TASK_OUTCOME_FAILED, TASK_STATUS_ACTIVE, TASK_STATUS_CANCELLED,
    TASK_STATUS_COMPLETED, TASK_STATUS_FAILED, TASK_STATUS_KILLED,
    TRIGGER_SOURCE_PARENT_CASCADE, TRIGGER_SOURCE_STALE_REAPER,
    TRIGGER_SOURCE_USAGE_INGEST)

TABLE = Task._meta.db_table

#: The rule this module drives, addressed BY NAME: `ubb_task` carries a second
#: rule (`trg_task_containment_shares_the_pricing_regime`, BEFORE INSERT), and
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
    STOP_CAUSE_KEY: SET_ONCE,
    STOP_MECHANISM_KEY: SET_ONCE,
    STOP_CONTROL_FAMILY_KEY: SET_ONCE,
    STOP_CONTROL_ID_KEY: SET_ONCE,
    "start_absolute_deadline_seconds": FROZEN,
    "start_silence_window_seconds": FROZEN,
}

#: What UBB recorded when it stopped the unit, and the expiry policy the start
#: published — the two groups R10-W2 added.
STOP_FACTS = (STOP_CAUSE_KEY, STOP_MECHANISM_KEY, STOP_CONTROL_FAMILY_KEY,
              STOP_CONTROL_ID_KEY)
SNAPSHOT = ("start_absolute_deadline_seconds", "start_silence_window_seconds")

#: The rules migration that installs the rule; its text is read off the
#: module constant (a name starting with a digit, so `import_module`).
RULES = importlib.import_module(
    "apps.platform.work.migrations.0002_the_database_rules")


def refused_as(column):
    """The opening of the one refusal that names ``column`` — the column AND
    its class, because a rule naming only "something refused" would let a
    refusal from the wrong branch, or from the containment rule beside it,
    pass for this one."""
    return f"{column} is declared {DECLARED[column]}"


class UnitOfWorkTransitionTestBase(WorkTestBase):

    def _killed(self, **kwargs):
        unit = self._task(**kwargs)
        TaskService.kill_task(unit.id, reasons.TASK_COGS_CEILING)
        unit.refresh_from_db()
        return unit

    def _stopped_by_ubb(self):
        """A unit UBB stopped through the announcing seam, so all four of its
        stop facts are recorded — the mechanism included, which the seam
        stamps after the flip."""
        unit = self._task()
        TaskService.kill_and_announce(
            unit.id, reasons.TASK_COGS_CEILING, tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            trigger_source=TRIGGER_SOURCE_USAGE_INGEST,
            control_id=ceiling_control_id(unit))
        unit.refresh_from_db()
        self.assertTrue(all(getattr(unit, column) for column in STOP_FACTS))
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

    def test_a_finished_unit_is_never_re_typed_either(self):
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
        under the OTHER concept, in UBB's own `reason_code`."""
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


class AStopIsRecordedOnceTest(UnitOfWorkTransitionTestBase):
    """SET_ONCE: what UBB recorded when it stopped the unit — the cause, the
    mechanism, the control's family and its identity — goes from nothing to a
    value once and never moves again. No caller writes these (a start's
    `metadata` is the caller's own bag and never reaches them); this is what
    keeps every OTHER writer from rewriting a stop UBB made."""

    REWRITES = {
        STOP_CAUSE_KEY: reasons.SILENCE_WINDOW,
        STOP_MECHANISM_KEY: TRIGGER_SOURCE_STALE_REAPER,
        STOP_CONTROL_FAMILY_KEY: CONTROL_FAMILY_CUSTOMER_SPEND_POOL,
        STOP_CONTROL_ID_KEY: "another-control",
    }

    def test_a_recorded_stop_is_never_rewritten(self):
        for column, value in self.REWRITES.items():
            with self.subTest(column=column):
                self._refused_through_every_door(
                    self._stopped_by_ubb, column, **{column: value})

    def test_a_recorded_stop_is_never_erased(self):
        for column in STOP_FACTS:
            with self.subTest(column=column):
                self._refused_through_every_door(
                    self._stopped_by_ubb, column, **{column: None})

    def test_the_kernels_own_recording_lands_through_every_door(self):
        """THE CONTROL, in the kernel's two shapes: the cause, family and
        control on the write that ends the work, and the mechanism after it —
        the announcing seam stamps that on a unit already stopped."""
        self._admitted_through_every_door(
            self._task, status=TASK_STATUS_KILLED,
            **{STOP_CAUSE_KEY: reasons.TASK_COGS_CEILING,
               STOP_CONTROL_FAMILY_KEY: CONTROL_FAMILY_CEILING,
               STOP_CONTROL_ID_KEY: str(self.tenant.id)})
        self._admitted_through_every_door(
            self._killed, **{STOP_MECHANISM_KEY: TRIGGER_SOURCE_USAGE_INGEST})


class TheExpiryTheStartPublishedNeverMovesTest(UnitOfWorkTransitionTestBase):
    """FROZEN: the two windows the start resolved and published (#540) are
    what a replay of that start answers from. The sweepers never read them —
    they resolve the live ladder each time they run — so nothing has reason to
    move them, and a writer that did would make a replay say something the
    start never said."""

    def test_neither_published_window_is_ever_rewritten(self):
        for column in SNAPSHOT:
            with self.subTest(column=column):
                self._refused_through_every_door(
                    self._task, column, **{column: 60})

    def test_neither_published_window_is_ever_erased(self):
        for column in SNAPSHOT:
            with self.subTest(column=column):
                self._refused_through_every_door(
                    self._task, column, **{column: None})

    def test_a_unit_born_without_one_is_never_given_one_later(self):
        """FROZEN is from insert, as the kind of work is: a row written past
        the start has no start response to repeat, and none is invented for
        it afterwards."""
        def unregistered():
            return Task.objects.create(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0)
        self._refused_through_every_door(
            unregistered, "start_absolute_deadline_seconds",
            start_absolute_deadline_seconds=60)


class EverythingElseStillMovesTest(UnitOfWorkTransitionTestBase):
    """THE CONTROLS the refusals above are worth nothing without."""

    def test_a_finished_unit_keeps_counting(self):
        """A stop is a signal point and not a wall: late events land and count
        into a terminal unit's totals, and the caller's own bag is no part of
        the rule."""
        self._admitted_through_every_door(
            self._killed,
            total_provider_cost_micros=9_000_000,
            total_billed_cost_micros=12_000_000,
            recorded_events=7, unresolved_event_count=1,
            metadata={"kept": "the caller's own key"})

    def test_re_sending_what_the_row_holds_is_not_a_move(self):
        """A full-row save writes every column, every declared one included;
        the rule judges a CHANGE, so an unchanged value is admitted on a
        finished unit and on a running one alike."""
        for make in (self._failed, self._stopped_by_ubb,
                     lambda: self._task(parent=self._task(),
                                        task_type="transcode")):
            unit = make()
            self._admitted_through_every_door(
                lambda unit=unit: Task.objects.get(id=unit.id),
                **{column: getattr(unit, column) for column in DECLARED})

    def test_the_kernels_own_endings_still_land(self):
        """Every way the kernel ends work goes through the rule: a close that
        cascades `parent_closed` onto running contained work, and a kill that
        cascades onto its own — each piece recording the cascade as its
        mechanism."""
        closed, contained = self._a_parent_and_its_contained_work()
        TaskService.close_task(closed.id,
                               CloseDeclaration(TASK_OUTCOME_DELIVERED))
        contained.refresh_from_db()
        self.assertEqual(contained.status, TASK_STATUS_CANCELLED)
        self.assertEqual(contained.outcome_reason, OUTCOME_REASON_PARENT_CLOSED)
        self.assertEqual(contained.trigger_source, TRIGGER_SOURCE_PARENT_CASCADE)

        killed, inside = self._a_parent_and_its_contained_work()
        TaskService.kill_task(killed.id, reasons.TASK_COGS_CEILING)
        inside.refresh_from_db()
        self.assertEqual(inside.status, TASK_STATUS_KILLED)
        self.assertEqual(inside.trigger_source, TRIGGER_SOURCE_PARENT_CASCADE)


class TheDeclarationAndTheRuleAreOneClaimTest(TestCase):
    """ADR-0007 §2 asks two things and they fail differently: a column with no
    declared class answers *what may happen to this?* nowhere, and a declared
    class with no rule behind it is the promise nothing keeps."""

    def test_the_model_declares_the_eleven(self):
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
        self.assertEqual(rule_names_on(TABLE),
                         {TRANSITION_TRIGGER, CONTAINMENT_TRIGGER})

    def test_the_rule_spells_the_unresolved_state_the_registry_names(self):
        """A migration must not import application code, so the rule's text
        (`TASK_DECLARED_TRANSITIONS`) spells `active` itself — once for the
        RESOLVE_ONCE branch and once for each SET_ONCE explanation's "from
        nothing, on the ending write" — and this is what holds that spelling to
        the registry's. Before the cutover (#190) the spelling was `work/0028`'s
        `UNRESOLVED_STATUS` constant."""
        body = RULES.TASK_DECLARED_TRANSITIONS
        self.assertIn(f"CREATE TRIGGER {TRANSITION_TRIGGER}\n", body)
        spelled = re.findall(r"(?:OLD|NEW)\.status\s*(?:<>|=)\s*'([^']*)'", body)
        self.assertEqual(len(spelled), 5, spelled)
        self.assertEqual(set(spelled), {TASK_STATUS_ACTIVE})

    def test_the_rule_watches_and_refuses_every_declared_column(self):
        """The `WHEN` clause must name every declared column — one it missed
        would never enter the function, and its refusal could never fire — and
        the function must carry each column's own refusal, opening with the
        class the model declares. The stop facts are the SET_ONCE-from-NULL
        branch: UBB writes them from nothing, once."""
        body = RULES.TASK_DECLARED_TRANSITIONS
        when = re.search(r"^WHEN \((.*)\)$", body, re.MULTILINE)
        self.assertIsNotNone(when, "the rule carries no WHEN clause")
        watched = re.findall(r"OLD\.(\w+) IS DISTINCT FROM NEW\.(\w+)",
                             when.group(1))
        self.assertTrue(all(old == new for old, new in watched), watched)
        self.assertEqual(len(watched), len(DECLARED))
        self.assertEqual({old for old, _ in watched}, set(DECLARED))
        for column in DECLARED:
            with self.subTest(column=column):
                self.assertIn(f"'{refused_as(column)}", body)
        self.assertEqual(
            tuple(re.findall(
                r"IF OLD\.(\w+) IS NOT NULL AND NEW\.\1 IS DISTINCT FROM OLD\.\1",
                body)),
            STOP_FACTS)
