"""Contained work is sold the way the work containing it is sold (#415,
spec §9, #151 §18).

**THE INVARIANT COMPARES TWO ROWS, WHICH IS THE WHOLE REASON THIS MODULE
EXISTS.** #151 §18 records it as *"the weakest enforcement in the document, and
it guards a money-shaped rule"*: a `CHECK` is evaluated against one row and
cannot see the parent at all, so there is no column constraint that expresses
it and the choice is between a service that declines to write and a rule the
database keeps. It is a rule about who may be BORN, so it is a `BEFORE INSERT`
trigger — the shape `pricing/0020` already answers the same question with, one
app over.

**WHAT A MIXED TREE COSTS.** The parent's rollup is unconditional, so a
per-event step under a parent sold at one agreed price adds metered revenue to
a unit of work whose revenue that price was supposed to REPLACE; and an
agreed-price step under a per-event parent puts revenue at a level nothing
reports at, because a parent's close cascades over its children with no outcome
declared per child. Either way the answer is a number nobody can explain.

**THREE DOORS, AND `QuerySet.update()` IS NOT ONE OF THEM.** ADR-0007 §2 drives
its refusals through `save()`, `QuerySet.update()` and raw SQL because a
mutability class is a claim about what may happen to a row AFTER it exists.
This is not one of those claims: an update cannot create contained work, and a
unit of work is never re-parented. So the three doors here are the three ways a
row is BORN — `objects.create()`, a bare `save()`, and an INSERT going around
the ORM entirely.

⚠ **THE CONTROLS ARE WHAT MAKE THE REFUSALS EVIDENCE.** A rule that refused
every contained insert would satisfy every prohibited case below and would be a
far worse defect than the one it stops, so the matching-regime case goes through
the same three doors. And the LAST class measures what deleting the refusal
costs, because a green board over a rule that holds nothing is the failure this
repository keeps paying for.
"""
from django.db import IntegrityError, connection, models, transaction
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from apps.platform.work.services import ContainmentRegimeRefused, TaskService
from core.vocabulary import PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED

TABLE = Task._meta.db_table

#: The rule this module drives, addressed BY NAME. `ubb_task` carries one rule
#: today and this is it — but `pg_trigger` promises no order, so a second rule
#: arriving would turn any "the first row" into a coin toss between two rules
#: holding completely different things (#352).
CONTAINMENT_TRIGGER = "trg_task_containment_shares_the_pricing_regime"
CONTAINMENT_FUNCTION = "ubb_task_containment_shares_the_pricing_regime"

#: The word every refusal message must carry. Asserting the COLUMN and not only
#: that something refused: this table has two mechanisms on it now — a
#: uniqueness key on the caller's own attempt key and this rule — so *something
#: refused this* stopped being evidence the moment the second one landed.
THE_COLUMN = "pricing_mode"


def through_create(**columns):
    Task.objects.create(**columns)


def through_save(**columns):
    """`save()`, called on the base so no model-level override answers first.

    `Task.save()` guards its declared kind of work, and a plain `save()` would
    therefore run that guard before reaching the database. Calling the base
    implementation is what a writer that bypasses an override looks like — a
    data migration, a management command, a shell session — and it is the door
    the two-layer rule means.
    """
    models.Model.save(Task(**columns), force_insert=True)


def through_raw_sql(**columns):
    """An INSERT around the ORM entirely, every value prepared as its column
    takes it.

    The door is *raw SQL*, not *raw Python objects*: `get_db_prep_save` is the
    model field's own answer to how a value reaches the driver, so this writes
    exactly what the ORM writes and differs from the other two doors only in
    going around them — which is the whole point of it.

    It builds the row from an UNSAVED instance rather than from a hand-written
    column list, so a column added to this model later joins this door with no
    edit here. A hand-written list would go quietly wrong instead: the INSERT
    would omit the new column, the database would supply its default, and the
    door would stop writing what the ORM writes.
    """
    unsaved = Task(**columns)
    names, values = [], []
    for field in Task._meta.concrete_fields:
        if field.auto_created and not field.concrete:  # pragma: no cover
            continue
        value = field.pre_save(unsaved, add=True)
        names.append(field.column)
        values.append(field.get_db_prep_save(value, connection))
    placeholders = ", ".join(["%s"] * len(names))
    with connection.cursor() as cursor:
        cursor.execute(
            f"INSERT INTO {TABLE} ({', '.join(names)}) VALUES ({placeholders})",
            values)


#: All three, every time. A guard only one of them respects is the defect
#: ADR-0007 §2's two-layer rule exists to catch, in the one shape a check
#: constraint cannot take.
DOORS = (("objects.create()", through_create),
         ("save()", through_save),
         ("raw SQL", through_raw_sql))


class ContainmentRegimeTestBase(TestCase):

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Sold", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")

    def _whole_unit(self, regime=PRICING_MODE_EVENT_PRICED, **columns):
        return Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, pricing_mode=regime, **columns)

    def _contained(self, door, parent, regime):
        """Register contained work through one door, answering the refusal
        message or `None`.

        Each attempt is wrapped in its own atomic block: a refused statement
        poisons the transaction, and without a savepoint the next door in the
        loop would fail on the broken one rather than on its own subject.
        """
        try:
            with transaction.atomic():
                door(tenant=self.tenant, customer=self.customer,
                     balance_snapshot_micros=0, parent=parent,
                     pricing_mode=regime)
        except IntegrityError as refused:
            return str(refused)
        return None


class TheDatabaseRefusesAMixedTreeTest(ContainmentRegimeTestBase):
    """AC 6 — refused at CREATION, at the database, through every door.

    Not the service. A service that declines to write is a courtesy to the
    caller and is asserted at the route; what this class asserts is that the row
    cannot be born whichever door the write came through, because the doors that
    are not the route are the ones nobody is looking at.
    """

    def test_per_event_work_cannot_be_contained_by_agreed_price_work(self):
        parent = self._whole_unit(PRICING_MODE_FIXED)
        for name, door in DOORS:
            with self.subTest(door=name):
                refusal = self._contained(door, parent,
                                          PRICING_MODE_EVENT_PRICED)
                self.assertIsNotNone(refusal)
                self.assertIn(THE_COLUMN, refusal)
                self.assertIn(PRICING_MODE_FIXED, refusal)
                self.assertIn(PRICING_MODE_EVENT_PRICED, refusal)

    def test_agreed_price_work_cannot_be_contained_by_per_event_work(self):
        """The other direction, and it is a different mistake rather than the
        same one mirrored: this one puts revenue at a level nothing reports at,
        where the case above adds metered revenue underneath a price meant to
        replace it. A rule that caught only one would leave the tenant a mixed
        tree in whichever direction it did not look."""
        parent = self._whole_unit(PRICING_MODE_EVENT_PRICED)
        for name, door in DOORS:
            with self.subTest(door=name):
                refusal = self._contained(door, parent, PRICING_MODE_FIXED)
                self.assertIsNotNone(refusal)
                self.assertIn(THE_COLUMN, refusal)

    def test_no_contained_row_survives_the_refusal(self):
        """The refusal is BEFORE the write, which is what a `BEFORE INSERT`
        trigger buys over a constraint that unwinds one."""
        parent = self._whole_unit(PRICING_MODE_FIXED)
        for name, door in DOORS:
            with self.subTest(door=name):
                self._contained(door, parent, PRICING_MODE_EVENT_PRICED)
        self.assertFalse(Task.objects.filter(parent=parent).exists())


class TheRuleAdmitsEverythingItShouldTest(ContainmentRegimeTestBase):
    """THE CONTROL, and the class above is worth nothing without it.

    Every case above asserts a refusal, which a rule refusing all contained
    inserts would satisfy completely — and a system where no unit of work could
    contain any other would be a far worse defect than the one this rule stops.
    """

    def test_contained_work_sharing_the_regime_is_admitted(self):
        for regime in (PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED):
            parent = self._whole_unit(regime)
            for name, door in DOORS:
                with self.subTest(door=name, regime=regime):
                    self.assertIsNone(self._contained(door, parent, regime))
            self.assertEqual(Task.objects.filter(parent=parent).count(),
                             len(DOORS))

    def test_a_whole_unit_of_work_is_admitted_at_either_regime(self):
        """The `WHEN` clause, load-bearing rather than an optimisation: a rule
        that ran on every insert would ask about a parent that is not there,
        on the hottest registration path in the system."""
        for regime in (PRICING_MODE_EVENT_PRICED, PRICING_MODE_FIXED):
            with self.subTest(regime=regime):
                self.assertEqual(self._whole_unit(regime).pricing_mode, regime)

    def test_a_parent_that_is_not_on_disk_is_left_to_the_foreign_key(self):
        """IT REFUSES ONLY WHAT IT CAN SEE.

        Django creates every foreign key on PostgreSQL as `DEFERRABLE INITIALLY
        DEFERRED`, so a `parent_id` naming no row is refused at COMMIT by the
        key and not by this rule. Reporting *the regimes disagree* for a parent
        that does not exist would attribute a referential fault to a pricing
        rule — and the message a tenant would then be shown names two regimes,
        one of which is NULL.

        The refusal is observed by making the deferred check immediate inside
        the act, which is how this repository reads a deferred constraint at
        all; the assertion is on WHICH mechanism answered.
        """
        absent = Task(tenant=self.tenant, customer=self.customer,
                      balance_snapshot_micros=0)
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                Task.objects.create(
                    tenant=self.tenant, customer=self.customer,
                    balance_snapshot_micros=0, parent_id=absent.id,
                    pricing_mode=PRICING_MODE_FIXED)
                with connection.cursor() as cursor:
                    cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        self.assertNotIn(THE_COLUMN, str(refused.exception))
        self.assertIn("parent", str(refused.exception))


class TheServiceGivesTheRefusalASentenceTest(ContainmentRegimeTestBase):
    """The half a trigger cannot do: say which regime was contradicted.

    `TaskService.create_task` is the one service every writer of this table
    passes through, and it holds the same rule so that a caller gets a sentence
    naming both regimes instead of an `IntegrityError`. It does not REPLACE the
    trigger — the class above is what proves the row cannot be born through the
    doors that are not this one.
    """

    def test_the_service_names_both_regimes(self):
        parent = self._whole_unit(PRICING_MODE_FIXED)
        with self.assertRaises(ContainmentRegimeRefused) as refused:
            TaskService.create_task(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0, parent=parent,
                pricing_mode=PRICING_MODE_EVENT_PRICED)
        self.assertEqual(refused.exception.containing_regime,
                         PRICING_MODE_FIXED)
        self.assertEqual(refused.exception.declared_regime,
                         PRICING_MODE_EVENT_PRICED)
        self.assertIn(PRICING_MODE_FIXED, str(refused.exception))

    def test_the_service_admits_contained_work_that_agrees(self):
        parent = self._whole_unit(PRICING_MODE_FIXED)
        contained = TaskService.create_task(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, parent=parent,
            pricing_mode=PRICING_MODE_FIXED)
        self.assertEqual(contained.parent_id, parent.id)
        self.assertEqual(contained.pricing_mode, PRICING_MODE_FIXED)

    def test_a_caller_that_says_nothing_registers_per_event_work(self):
        """The default is a record rather than a filler: every caller here that
        is not a start gate — the reapers, the cascades, every fixture that
        stands a unit of work up directly — is registering work no declaration
        was consulted for, and per-event is what such a unit of work has always
        meant."""
        registered = TaskService.create_task(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0)
        self.assertEqual(registered.pricing_mode, PRICING_MODE_EVENT_PRICED)
        self.assertIsNone(registered.agreed_price_micros)


class AGreenBoardOverAGuttedRuleIsMeasuredRatherThanArguedTest(
        ContainmentRegimeTestBase):
    """AC 6's *"a test that would fail if the check were removed"*, run rather
    than asserted.

    #360's lesson is that an acceptance criterion saying *remove X and confirm*
    is an instruction to RUN something, and the one most easily satisfied by
    prose. So this replaces the rule's body in-process with one that READS both
    regimes and refuses nothing — the mutant that keeps every token in its own
    source, so a control reading `prosrc` for the column name cannot tell the
    two apart — and shows the mixed tree is then admitted at every door.

    The replacement is dropped at the end of the test's transaction with
    everything else, so nothing leaks into the rest of the suite.
    """

    GUTTED = f"""
    CREATE OR REPLACE FUNCTION {CONTAINMENT_FUNCTION}() RETURNS trigger
    LANGUAGE plpgsql AS $$
    DECLARE
        containing_regime text;
    BEGIN
        SELECT pricing_mode INTO containing_regime
        FROM ubb_task WHERE id = NEW.parent_id;
        RETURN NEW;
    END;
    $$;
    """

    def test_without_the_refusal_a_mixed_tree_is_born(self):
        parent = self._whole_unit(PRICING_MODE_FIXED)
        with connection.cursor() as cursor:
            cursor.execute(self.GUTTED)
        for name, door in DOORS:
            with self.subTest(door=name):
                self.assertIsNone(self._contained(door, parent,
                                                  PRICING_MODE_EVENT_PRICED))
        self.assertEqual(
            Task.objects.filter(parent=parent,
                                pricing_mode=PRICING_MODE_EVENT_PRICED).count(),
            len(DOORS))

    def test_the_rule_is_installed_under_the_name_this_module_addresses(self):
        """The premise every assertion above rests on, asserted rather than
        assumed: a migration that ran is evidence that a file executed, not that
        a rule is on the table. An exact SET rather than a membership test, so
        that a second rule arriving on this table is read by a person before the
        by-name addressing above quietly starts mattering."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT t.tgname FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
            self.assertEqual({row[0] for row in cursor.fetchall()},
                             {CONTAINMENT_TRIGGER})


class OnlyAWholeUnitOfWorkCarriesAnAgreedPriceTest(ContainmentRegimeTestBase):
    """The two checks beside the rule — one row each, so a `CHECK` holds them.

    ⚠ ONE DIRECTION AND ONLY ONE. *A price implies a whole unit of work sold
    that way* is a property of one row. The converse — *every whole unit of work
    sold that way carries a price* — is not expressible here and is not true
    either, because contained work under an agreed-price parent is sold that way
    too and carries no price of its own. What makes a whole one carry a price is
    the start gate refusing to register it otherwise.
    """

    def test_per_event_work_cannot_carry_an_agreed_price(self):
        with self.assertRaises(IntegrityError) as refused:
            self._whole_unit(PRICING_MODE_EVENT_PRICED,
                             agreed_price_micros=5_000_000)
        self.assertIn("ck_task_agreed_price_only_on_a_whole_fixed_unit",
                      str(refused.exception))

    def test_contained_work_cannot_carry_an_agreed_price(self):
        parent = self._whole_unit(PRICING_MODE_FIXED)
        with self.assertRaises(IntegrityError) as refused:
            Task.objects.create(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0, parent=parent,
                pricing_mode=PRICING_MODE_FIXED,
                agreed_price_micros=5_000_000)
        self.assertIn("ck_task_agreed_price_only_on_a_whole_fixed_unit",
                      str(refused.exception))

    def test_a_negative_price_is_refused_and_zero_is_not(self):
        """Zero is a price — a tenant may agree to deliver a kind of work for
        nothing — and a number below it is a sign error rather than a deal."""
        with self.assertRaises(IntegrityError) as refused:
            self._whole_unit(PRICING_MODE_FIXED, agreed_price_micros=-1)
        self.assertIn("ck_task_agreed_price_not_negative",
                      str(refused.exception))

    def test_zero_is_admitted(self):
        priced = self._whole_unit(PRICING_MODE_FIXED, agreed_price_micros=0)
        self.assertEqual(Task.objects.get(id=priced.id).agreed_price_micros, 0)
