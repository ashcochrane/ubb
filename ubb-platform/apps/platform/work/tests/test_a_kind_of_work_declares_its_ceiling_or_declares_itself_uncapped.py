"""A kind of work declares its ceiling, or declares itself uncapped — and the
DATABASE is what refuses a declaration that says neither, or both (#453,
slice 6 §2, #150 §8, TD claim 3).

Before this rule a null ceiling was a silence: the ladder fell through to a
tenant default, and then to nothing, with no signal anywhere. In a product
whose core promise is spend control, "I thought a ceiling was on" was not
falsifiable from the API. So a declaration answers the question exactly once —
`task_cogs_ceiling_micros` carries a figure with `uncapped` false, or no figure
with `uncapped` true — and `ck_task_type_ceiling_or_uncapped` holds that
exclusive-or as a check constraint rather than a serializer rule (ADR-0007
§2): a data migration, a shell session or a bulk write meets the same refusal
the registry route renders as a validation problem.

**Every refusal asserts the CONSTRAINT'S OWN NAME.** This table already
carries one rule (the frozen regime's trigger, `0021`), so *something refused
this* stopped being evidence the moment a second rule landed (#352). A check
is evaluated on INSERT as well as UPDATE and no trigger on this table fires on
an INSERT, so the insert cases meet the check directly; the update cases go
through the three doors ADR-0007 §2 names, and the trigger's `WHEN` clause
keeps it out of their way because none of them moves the regime.

**The controls are what make the refusals evidence.** A rule refusing every
write to these two columns would satisfy every refusal below, and a registry
whose kinds of work could never move between a figure and uncapped would be a
worse defect than the one this rule stops — both columns are ordinary mutable
columns (ADR-0012's Consequences). So the two admitted shapes are driven
through every door too, in both directions.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.work.models import TaskType
from apps.platform.work.tests._helpers import DOORS, refusal_from
from core.vocabulary import TASK_TYPE_KIND_TASK

CEILING = "task_cogs_ceiling_micros"
UNCAPPED = "uncapped"
RULE = "ck_task_type_ceiling_or_uncapped"
TABLE = TaskType._meta.db_table

#: The two shapes the rule refuses, named for what a declaration says.
NEITHER = {CEILING: None, UNCAPPED: False}
BOTH = {CEILING: 5_000_000, UNCAPPED: True}
#: The two it admits.
A_FIGURE = {CEILING: 5_000_000, UNCAPPED: False}
NONE_BY_DECLARATION = {CEILING: None, UNCAPPED: True}


class DeclaredCeilingTestBase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Declared", products=["metering"])

    def _kind(self, key, **columns):
        return TaskType.objects.create(tenant=self.tenant, key=key,
                                      kind=TASK_TYPE_KIND_TASK, **columns)


class TheDatabaseRefusesNeitherAndBothTest(DeclaredCeilingTestBase):

    def test_the_rule_is_installed_under_the_name_this_module_addresses(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT conname FROM pg_constraint WHERE conrelid = %s::regclass "
                "AND contype = 'c'", [TABLE])
            checks = {name for (name,) in cursor.fetchall()}
        self.assertIn(RULE, checks)

    def test_an_insert_stating_neither_is_refused_at_the_database(self):
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                self._kind("silent", **NEITHER)
        self.assertIn(RULE, str(refused.exception))
        self.assertEqual(TaskType.objects.count(), 0)

    def test_an_insert_stating_both_is_refused_at_the_database(self):
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                self._kind("greedy", **BOTH)
        self.assertIn(RULE, str(refused.exception))
        self.assertEqual(TaskType.objects.count(), 0)

    def test_the_models_own_default_is_not_an_answer(self):
        """`uncapped` defaults to false, so a row created naming no ceiling at
        all is the NEITHER shape — the honest outcome for a writer that said
        nothing, and the one the route can never produce. Pinned so the
        default is never quietly made true, which would turn every fixture
        that forgot the ceiling into a declaration of uncapped."""
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                self._kind("forgot")
        self.assertIn(RULE, str(refused.exception))

    def _refused_through_every_door(self, standing_shape, **columns):
        for name, door in DOORS:
            with self.subTest(door=name):
                row = self._kind(f"row-{name}", **standing_shape)
                message = refusal_from(door, row, **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(RULE, message)
                row.refresh_from_db()
                self.assertEqual({CEILING: getattr(row, CEILING),
                                  UNCAPPED: getattr(row, UNCAPPED)},
                                 standing_shape)

    def test_a_figure_cannot_be_cleared_without_declaring_uncapped(self):
        self._refused_through_every_door(A_FIGURE, **{CEILING: None})

    def test_uncapped_cannot_be_withdrawn_without_stating_a_figure(self):
        self._refused_through_every_door(NONE_BY_DECLARATION, **{UNCAPPED: False})

    def test_a_figure_cannot_be_added_beside_uncapped(self):
        self._refused_through_every_door(NONE_BY_DECLARATION,
                                         **{CEILING: 5_000_000})

    def test_uncapped_cannot_be_declared_beside_a_figure(self):
        self._refused_through_every_door(A_FIGURE, **{UNCAPPED: True})


class TheTwoAnswersMoveFreelyTest(DeclaredCeilingTestBase):
    """THE CONTROLS. Both columns stay ordinary mutable columns: a kind of work
    moves from a figure to uncapped and back through every door, and a figure
    is revised in place, exactly as the registry's whole-vocabulary PUT does
    it (`api/v1/tests/test_task_type_registry.py`)."""

    def _admitted_through_every_door(self, standing_shape, **columns):
        for name, door in DOORS:
            with self.subTest(door=name):
                row = self._kind(f"row-{name}", **standing_shape)
                self.assertIsNone(refusal_from(door, row, **columns))
                row.refresh_from_db()
                for column, value in columns.items():
                    self.assertEqual(getattr(row, column), value)

    def test_a_figure_becomes_uncapped_when_both_columns_move_together(self):
        self._admitted_through_every_door(A_FIGURE, **NONE_BY_DECLARATION)

    def test_uncapped_becomes_a_figure_when_both_columns_move_together(self):
        self._admitted_through_every_door(NONE_BY_DECLARATION, **A_FIGURE)

    def test_a_figure_is_revised_in_place(self):
        self._admitted_through_every_door(A_FIGURE, **{CEILING: 9_000_000})

    def test_neither_column_is_declared_into_a_transition_class(self):
        """ADR-0012's Consequences, read off the model rather than assumed:
        the frozen regime is the only declared column, so nothing about the
        ceiling or the flag is held by a transition rule."""
        self.assertNotIn(CEILING, TaskType.transition_classes)
        self.assertNotIn(UNCAPPED, TaskType.transition_classes)
