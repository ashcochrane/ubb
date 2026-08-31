"""How a kind of work is sold, and why that declaration never moves (#414,
spec §9/§10).

Every revenue path in UBB is per-event. A tenant who quotes one agreed price
for a delivered piece of work has to reverse-engineer a per-event rate that
happens to sum to that number, which it will not, because how many events the
work takes is not knowable when the price is quoted. `pricing_mode` is the
declaration that makes the other answer sayable: `event_priced` prices each
event as it arrives, `fixed` replaces metered revenue for the whole delivered
piece of work with one agreed number.

**THE REGIME IS DECLARED INTO `FROZEN` AND THE DATABASE IS WHAT KEEPS IT.**
ADR-0007 §2 admits no transition after insert for that class and says outright
that a model-level guard alone is not enforcement — *"the repository has
already shipped one that a production writer bypassed by design"* — so the
refusals below are driven through all three doors: `save()`,
`QuerySet.update()` and raw SQL. A route that declines to write is a courtesy
to the caller and is asserted separately, in `api/v1/tests/`.

**Changing the regime means retiring this kind of work and declaring a
replacement**, which is why freezing costs the tenant a path rather than an
answer. That path runs through the registry's write surface, so it is proved
where a tenant actually calls it; what belongs here is the half the database
owns.

⚠ **THE CONTROLS ARE WHAT MAKE THE REFUSALS EVIDENCE.** A rule that refused
every update to this table would satisfy every prohibited-transition case in
this module, and would be a far worse defect than the one it was installed to
stop — a kind of work whose ceiling could never be raised again. So the
admitted moves go through the same three doors, and so does the equal-value
write, because the trigger's `WHEN` clause is the thing that keeps an
idempotent re-declaration free.
"""
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from apps.platform.work.models import TaskType
from apps.platform.work.queries import declared_task_types, task_type_policy
from core.transitions import FROZEN, columns_declared_into_defended_classes
from core.vocabulary import (
    PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED, PRICING_MODE_VALUES,
    TASK_TYPE_KIND_SUBTASK, TASK_TYPE_KIND_TASK)

PRICING_MODE = "pricing_mode"
CEILING = "default_provider_cost_limit_micros"
TABLE = TaskType._meta.db_table

#: The rule this module's refusals belong to, addressed BY NAME. `ubb_task_type`
#: carries one rule today and this is it — but `pg_trigger` promises no order,
#: so a second rule arriving would silently turn any "the first row" into a coin
#: toss between two rules holding completely different things (#352).
TRANSITION_TRIGGER = "trg_task_type_declared_transitions"


def through_the_queryset(kind_of_work, **columns):
    TaskType.objects.filter(pk=kind_of_work.pk).update(**columns)


def through_save(kind_of_work, **columns):
    """`save()`, called on the base so no model-level override can answer first.

    `TaskType` has no `save()` guard of its own, so a plain `save()` would reach
    the database today. Calling the base implementation is what a writer that
    bypasses an override looks like — a `bulk_update`, a data migration, a shell
    session — and it is the door ADR-0007 §2 means, so this case stays honest on
    the day somebody adds one.
    """
    for name, value in columns.items():
        setattr(kind_of_work, name, value)
    models.Model.save(kind_of_work)


def through_raw_sql(kind_of_work, **columns):
    """Raw SQL, around the ORM entirely, each value prepared as its column takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_value` is the
    model field's own answer to how a value reaches the driver, so this writes
    exactly what the ORM writes and differs from the other two doors only in
    going around them — which is the whole point of it.
    """
    assignments = ", ".join(f"{name} = %s" for name in columns)
    values = [TaskType._meta.get_field(name).get_db_prep_value(value, connection)
              for name, value in columns.items()]
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s",
                       [*values, str(kind_of_work.pk)])


#: All three, every time. A guard only one of them respects is the defect
#: ADR-0007 §2's two-layer rule exists to catch.
DOORS = (("QuerySet.update()", through_the_queryset),
         ("save()", through_save),
         ("raw SQL", through_raw_sql))


class KindOfWorkTestBase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Sold", products=["metering"])

    def _kind(self, key="transcode", *, kind=TASK_TYPE_KIND_TASK, **columns):
        return TaskType.objects.create(tenant=self.tenant, key=key, kind=kind,
                                       **columns)


class TheRegimeIsDeclaredOnTheKindOfWorkTest(KindOfWorkTestBase):
    """§9 — the declaration exists, holds both answers, and defaults to today's.

    ⚠ The default is not a convenience. Every declaration that predates this
    column was made when per-event was the only regime there was, so
    `event_priced` is what those rows have always meant and writing it down is a
    record rather than a guess. A nullable column would have invented a third
    state — *nobody said* — for a question every existing row has already
    answered.
    """

    def test_a_kind_of_work_declared_before_this_column_is_event_priced(self):
        self.assertEqual(self._kind().pricing_mode, PRICING_MODE_EVENT_PRICED)

    def test_a_kind_of_work_can_be_declared_at_one_agreed_price(self):
        declared = self._kind(pricing_mode=PRICING_MODE_FIXED)
        self.assertEqual(TaskType.objects.get(id=declared.id).pricing_mode,
                         PRICING_MODE_FIXED)

    def test_the_two_answers_are_the_registrys_rather_than_this_models(self):
        """The G2 payment, asserted as the identity it is.

        The column's choices are built from the generated constants, so the set
        it admits IS the registry's set. Asserting two literals instead would be
        asserting that two spellings agree, which is exactly the drift a value
        set held by reference exists to make impossible.
        """
        admitted = {value for value, _ in
                    TaskType._meta.get_field(PRICING_MODE).choices}
        self.assertEqual(admitted, set(PRICING_MODE_VALUES))

    def test_the_read_contract_carries_the_regime(self):
        """Both read paths, because billing resolves a price through one of them
        and the registry surface answers through the other."""
        self._kind("transcode", pricing_mode=PRICING_MODE_FIXED)
        self.assertEqual(
            task_type_policy(self.tenant.id, "transcode",
                             TASK_TYPE_KIND_TASK)[PRICING_MODE],
            PRICING_MODE_FIXED)
        self.assertEqual(
            [row[PRICING_MODE] for row in declared_task_types(self.tenant.id)],
            [PRICING_MODE_FIXED])

    def test_the_two_altitudes_are_two_declarations(self):
        """One word, two altitudes, two answers — which is what the uniqueness
        key already promised and what ticket 10's equality check will compare.

        Contained work inherits its parent's regime and is refused if it
        disagrees; that comparison reads two ROWS, so no column constraint can
        express it and it does not live here. What lives here is the fact that
        makes the comparison possible at all: the two rows can genuinely differ.
        """
        self._kind("transcode", kind=TASK_TYPE_KIND_TASK,
                   pricing_mode=PRICING_MODE_FIXED)
        self._kind("transcode", kind=TASK_TYPE_KIND_SUBTASK,
                   pricing_mode=PRICING_MODE_EVENT_PRICED)
        self.assertEqual(
            {(row["kind"], row[PRICING_MODE])
             for row in declared_task_types(self.tenant.id)},
            {(TASK_TYPE_KIND_TASK, PRICING_MODE_FIXED),
             (TASK_TYPE_KIND_SUBTASK, PRICING_MODE_EVENT_PRICED)})


class TheRegimeIsFrozenTest(KindOfWorkTestBase):
    """AC 2 — the DATABASE refuses a change to the regime after insert.

    Not the service. A service that declines to write is a message to the
    caller; what ADR-0007 §2 requires is that the row cannot move whichever door
    the write came through, because the doors that are not the route are the
    ones nobody is looking at: a data migration, a management command, a shell
    session.

    ⚠ EVERY CASE ASSERTS THE COLUMN AS WELL AS THE CLASS. This table carries one
    rule today, so *something refused this* happens to be unambiguous — and it
    stops being evidence the moment a second rule lands, which is the trap #352
    paid for one table over. The refusal names both, and so does every assertion
    about it.
    """

    def _refusal(self, door, kind_of_work, **columns):
        """What Postgres refused with, or `None` where it admitted the write."""
        try:
            with transaction.atomic():
                door(kind_of_work, **columns)
        except IntegrityError as refused:
            return str(refused)
        return None

    def _refused_through_every_door(self, make, **columns):
        """`make` takes the door's name so each case gets its OWN row.

        One row reused across the three doors would have the first refusal leave
        it untouched and the next two assert against a row the previous case
        already tried to move; one row created per door under a shared key would
        collide on `uq_task_type_key` and fail for a reason that is not the
        subject.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                message = self._refusal(door, make(name), **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(FROZEN, message)
                self.assertIn(PRICING_MODE, message)

    def test_per_event_cannot_become_one_agreed_price(self):
        self._refused_through_every_door(
            lambda door: self._kind(f"to-fixed-{door}"),
            pricing_mode=PRICING_MODE_FIXED)

    def test_one_agreed_price_cannot_become_per_event(self):
        """The other direction, and it is the one with money already quoted
        behind it: work sold at an agreed price and then re-declared per-event
        prices everything that kind of work does next against rules nobody
        quoted."""
        self._refused_through_every_door(
            lambda door: self._kind(f"to-event-{door}",
                                    pricing_mode=PRICING_MODE_FIXED),
            pricing_mode=PRICING_MODE_EVENT_PRICED)

    def test_the_regime_cannot_ride_along_with_a_permitted_change(self):
        """A statement that also moves a mutable column is still refused.

        The interesting shape, because it is what an ordinary re-declaration
        looks like: a tenant raising a ceiling and flipping the regime in one
        statement. The rule judges the COLUMN, never the statement.
        """
        self._refused_through_every_door(
            lambda door: self._kind(f"ride-{door}"),
            pricing_mode=PRICING_MODE_FIXED,
            **{CEILING: 9_000_000})

    def test_re_declaring_the_same_regime_is_not_a_change(self):
        """The `WHEN` clause, load-bearing rather than an optimisation.

        The registry's write surface is an idempotent PUT that writes every
        column of a declaration on every call, so a rule that fired on equal
        values would refuse a tenant re-sending the declaration it already made.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                kind_of_work = self._kind(f"same-{name}",
                                          pricing_mode=PRICING_MODE_FIXED)
                self.assertIsNone(
                    self._refusal(door, kind_of_work,
                                  pricing_mode=PRICING_MODE_FIXED))
                kind_of_work.refresh_from_db()
                self.assertEqual(kind_of_work.pricing_mode, PRICING_MODE_FIXED)

    def test_everything_else_about_a_kind_of_work_still_moves(self):
        """THE CONTROL, and this class is worth nothing without it.

        Every case above asserts a refusal, which a rule refusing all updates to
        this table would satisfy completely — and a registry whose ceilings and
        windows could never be revised would be a worse defect than the one this
        rule exists to stop. The declaration's three bounds are mutable by design
        and stay so.
        """
        for name, door in DOORS:
            with self.subTest(door=name):
                kind_of_work = self._kind(f"movable-{name}")
                self.assertIsNone(
                    self._refusal(door, kind_of_work,
                                  silence_window_seconds=1200,
                                  absolute_deadline_seconds=7200,
                                  **{CEILING: 7_000_000}))
                kind_of_work.refresh_from_db()
                self.assertEqual(getattr(kind_of_work, CEILING), 7_000_000)


class TheRegimeIsDeclaredIntoATransitionClassTest(TestCase):
    """AC 2's other half — the declaration and the rule are the same claim.

    ADR-0007 §2 asks two things and they fail differently: a column with no
    declared class answers *what may happen to this?* nowhere, and a declared
    class with no rule behind it is the promise nothing keeps. The first is read
    here; the second goes through the gate's OWN entry point rather than through
    a second copy of its search, because two copies of one search agreeing prove
    nothing about the database.
    """

    def test_the_column_declares_frozen(self):
        self.assertEqual(TaskType.transition_classes, {PRICING_MODE: FROZEN})

    def test_the_database_defends_what_the_model_declares(self):
        declared = columns_declared_into_defended_classes([TaskType])
        self.assertEqual(declared, [("TaskType", PRICING_MODE, FROZEN)])
        self.assertEqual(
            columns_the_database_does_not_defend(declared,
                                                 declaring_models_by_table()),
            [])

    def test_the_rule_is_installed_under_the_name_this_module_addresses(self):
        """The premise every assertion above rests on, asserted rather than
        assumed: a migration that ran is evidence that a file executed, not that
        a rule is on the table. An exact SET rather than a membership test, so
        that a second rule arriving is read by a person before the by-name
        addressing above quietly starts mattering."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
            self.assertEqual({row[0] for row in cursor.fetchall()},
                             {TRANSITION_TRIGGER})
