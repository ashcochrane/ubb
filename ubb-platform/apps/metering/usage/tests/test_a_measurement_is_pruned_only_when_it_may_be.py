"""A measurement record may only be pruned when both its conditions hold (#354).

The posting / measurement split (2026-08-03) gave the child record a
**whole-record rule** rather than per-column transition classes, because it has
no per-column lifecycle to describe::

    INSERT   once, in the same transaction as its posting
    UPDATE   never — no column of a measurement record is ever rewritten
    DELETE   permitted only at or after prunable_at, and only while the
             parent posting is not unresolved

**This module is the third line, and only the third line.** It is the one the
split decision said was *"a cross-table condition on a `DELETE`, evaluated
against the parent's `costing_status`/`pricing_status`"* — unexpressible until
the second of those two statuses landed, which it did four tickets ago.

⚠ **NOTHING COUNTS THIS RULE.** It has no entry in the migration ledger and no
row in the gate manifest, and slice 4 owns no manifest row at all. There is no
number to decrement, no allowlist to shrink and no tripwire to fire: **a fully
green board is no evidence whatsoever that this rule exists.** The spec calls it
the single largest silent-omission risk in the slice, and the only thing standing
between it and quiet non-existence is this module. Deleting this file would be
noticed by nothing.

**Why it is not part of gate G19, and why G19 is nonetheless what it extends.**
G19's statement is about *field* transition classes, and every column of this
record is declared `RECORD_RULE`, which `core/transitions.py` places outside
`DATABASE_DEFENDED`. So no amount of column-declaration work reaches this rule
and no declaration here would be honest — `ThisRuleDeclaresNoColumnIntoADefendedClassTest`
below is that sentence held to. What G19's own notes did carry was the deferral,
by name, and this is the ticket that pays it: an **extension** of the installed
gate rather than a re-owning of its row.

**The two conditions, and why neither is sufficient alone.**

* An instant with no status check prunes a record whose posting is still waiting
  to be resolved, and destroys the inputs a recovery run needs — on exactly the
  records that most need fixing.
* A status check with no instant prunes a record before its retention obligation
  is up.

`TheTwoConditionsAreIndependentlyLoadBearingTest` is that paragraph measured
rather than argued: it replaces the shipped rule with one missing each **cause**
in turn and watches the matching deletes become admitted while the other stays
refused. Removing the *cause* rather than the token is #331's lesson — a fault
with two causes reads exactly like a vacuous control — and it is also why every
refusal below is built with exactly ONE condition failing: a record refused for
both reasons at once would stay refused through either mutation and prove
nothing about either.

**⚠ "NOT UNRESOLVED" IS THE SHAPE OF THE PREDICATE, AND NOT "IS RESOLVED".** A
posting whose price is `waived` or `not_applicable`, or whose cost is
`not_applicable`, has nothing outstanding: somebody made a decision, and its
measurements are prunable on time. Only `costing_status = unresolved` and
`pricing_status = unknown` mean UBB is missing information — which is exactly
the one status per pair that `core.amount_status_pairs` names, and the tokens
this rule freezes are taken from there rather than spelled twice.

⚠ **This is the opposite direction from the three rules on the parent table**,
where whitelisting the one completable status is what stops a waived charge
being turned into a charged amount. The difference is what the predicate is
*for*: a transition rule asks whether a write may happen and must not admit one
it has no positive reason to; this one asks whether anything still needs the
record, and a decision already taken is not a need. `ThePredicateIsNotUnresolvedRatherThanIsResolvedTest`
is that distinction, over all three decided statuses.

**Where a NULL `prunable_at` lands, which is the live case today.** The column
ships with no clock behind it — no job, no schedule, no owner, no default — and
`TheHorizonHasNoClockBehindItTest` in `test_posting_measurement.py` exists to
stop one being started by accident. So **every** measurement record in the tree
has a NULL horizon, and this rule refuses every one of them: an instant nobody
has named is not an instant that has passed. That is the conservative reading
and it is the only one the column's own meaning supports — `prunable_at` names
*"the moment a permission begins"*, so no value is no permission.

**The mechanism is a `BEFORE DELETE` trigger on the child's own table.** A
`CHECK` cannot see a `DELETE` at all, a model-level `delete()` override is not
enforcement (ADR-0007 §2 is explicit, and this repository has already shipped a
guard a production writer bypassed by design), and the three doors below are
what a guard living in Python does not cover.

**⚠ It deliberately does NOT ride the parent table's mechanism.** The three
rules on `ubb_posting` are `BEFORE UPDATE` triggers over declared columns; this
is a different table, a different statement and a whole-record rule rather than
a column one, and folding it in would put a cross-table lookup into the hottest
update path in the system to enforce something that path never does.

**And this rule costs the hot path nothing, which is proved rather than
measured.** ADR-0007's Consequences require a database-enforced transition's
**per-insert and per-update cost** to be measured rather than assumed. A
`BEFORE DELETE` trigger cannot fire on an `INSERT` or an `UPDATE`, so that cost
is zero by construction — and `test_it_fires_before_each_deleted_row_and_on_nothing_else`
reads the statement mask out of `pg_trigger` and holds it there, which is a
stronger statement than a benchmark reporting a small number. The recording path
inserts into this table on every metered call and deletes from it never.

**⚠ THERE IS A THIRD CONDITION AND IT IS NOT IN THE TICKET.** A posting on a
**sandbox** tenant is exempt, because the ticket's two would refuse
`reset_sandbox_tenant` outright and leave the sandbox unable to serve traffic —
and no test in the tree would have caught it. `ADiscardIsNotAPruneTest` below
carries the whole argument, its control, and the reason the exemption cannot be
turned on for a live tenant; the migration's docstring carries the two
mechanisms that would have expressed *the posting is going too* without a proxy,
and why each is a larger decision than this rule.

**What this ticket does NOT enforce, said out loud.** The record rule's `UPDATE`
line is still declared and unenforced, so a writer can set `prunable_at` to the
past and then prune. That hole is not opened by this rule and not closed by it:
this ticket's subject is the `DELETE` condition, and claiming the whole record
rule was enforced would be the shape of defect where a docstring asserts an
obligation that only half holds. `release_and_prune` in `tests/_helpers.py` is
the one place in the tree that walks through it, and it says so.
"""
import re

from django.apps import apps
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.utils import timezone

from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.tests._helpers import committed_posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from core.amount_status_pairs import CUSTOMER_PRICE, SUPPLIER_COST
from core.transitions import (
    DATABASE_DEFENDED, RECORD_RULE, columns_declared_into_defended_classes)
from core.vocabulary import (
    COSTING_STATUS_NOT_APPLICABLE, NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    PRICING_STATUS_NOT_APPLICABLE, PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING)

TABLE = PostingMeasurement._meta.db_table
TRIGGER = "trg_posting_measurement_pruning"
FUNCTION = "ubb_posting_measurement_pruning"
MIGRATION = "0041_a_measurement_is_pruned_only_when_it_may_be"

#: The tokens each refusal must NAME, beside the record rule it enforces. Two
#: conditions on one record share a mechanism, so "something refused this" stops
#: being evidence the moment the second condition lands — which is the lesson
#: three rules on the parent table paid for. Each class states which.
NAMES_THE_INSTANT = "prunable_at"
NAMES_THE_STATUSES = (SUPPLIER_COST.status_column, CUSTOMER_PRICE.status_column)

#: The record rule, named in every refusal so a reader of a traceback lands on
#: the docstring that states all three of its lines rather than on this one.
RECORD_RULE_TOKEN = "whole-record rule"


# --- Building a posting in each of the states the predicate reads ------------
#
# The four legal combinations of each pair are held by a `CHECK` on the posting
# table, so each shape below carries the amount and the reason its status
# requires rather than the status alone.

def _resolved_posting(**columns):
    """A posting with nothing outstanding on either pair — the default.

    `committed_posting` leaves both statuses at their column defaults, which are
    `known` on both sides, with a zero amount that agrees with them.
    """
    return committed_posting(**columns)


def _cost_is_unresolved():
    return committed_posting(
        provider_cost_micros=None,
        costing_status=SUPPLIER_COST.unresolved_status,
        unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)


def _price_is_unknown():
    return committed_posting(
        billed_cost_micros=None,
        pricing_status=CUSTOMER_PRICE.unresolved_status)


def _measurement(posting, prunable_at):
    return PostingMeasurement.objects.create(
        posting=posting, measurements={"input_tokens": 1200},
        recorded_at=posting.created_at, prunable_at=prunable_at)


def _long_past():
    return timezone.now() - timezone.timedelta(days=365)


def _far_future():
    return timezone.now() + timezone.timedelta(days=365)


def _the_databases_own_now():
    """`now()` as the trigger will read it, which is not `timezone.now()`.

    Postgres' `now()` is the *transaction* timestamp, and a Django `TestCase`
    runs its whole body in one transaction — so this is the exact instant the
    rule compares against, and a record given it is a record sitting precisely
    on the boundary the condition says is admitted.
    """
    with connection.cursor() as cursor:
        cursor.execute("SELECT now()")
        return cursor.fetchone()[0]


# --- The three doors, DELETE-shaped ------------------------------------------
#
# Deliberately NOT the doors in `tests/_helpers.py`: those write columns through
# `save()`, `QuerySet.update()` and raw SQL, which is the shape a field
# transition rule is driven through. This rule is about whether a row may cease
# to exist, so its doors are the three statements that remove one, and they live
# here because exactly one module has the rule they belong to.

def _through_the_instance(measurement):
    measurement.delete()


def _through_the_queryset(measurement):
    PostingMeasurement.objects.filter(pk=measurement.pk).delete()


def _through_raw_sql(measurement):
    with connection.cursor() as cursor:
        cursor.execute(f"DELETE FROM {TABLE} WHERE id = %s",
                       [str(measurement.pk)])


DOORS = (("delete()", _through_the_instance),
         ("QuerySet.delete()", _through_the_queryset),
         ("raw SQL", _through_raw_sql))


class PruneRefusalMixin:
    """Drive a prohibited delete through all three doors and read the refusal."""

    #: What this class's refusals must NAME beside the record rule. Set it per
    #: class; `_refused` will not run without one. There is deliberately no
    #: default: a default is the vacuous version of exactly this check, and this
    #: rule has two conditions whose refusals must stay tellable apart.
    REFUSAL_NAMES = None

    def _refusal(self, door, measurement):
        """The message Postgres refused with, or `None` if it did not refuse."""
        try:
            with transaction.atomic():
                door(measurement)
        except IntegrityError as refusal:
            return str(refusal)
        return None

    def _refused_through_every_door(self, make_measurement):
        self.assertIsNotNone(
            self.REFUSAL_NAMES,
            "set REFUSAL_NAMES on this class: a refusal that names only the "
            "record rule cannot tell this rule's two conditions apart")
        names = ((self.REFUSAL_NAMES,) if isinstance(self.REFUSAL_NAMES, str)
                 else self.REFUSAL_NAMES)
        for name, door in DOORS:
            with self.subTest(door=name):
                measurement = make_measurement()
                message = self._refusal(door, measurement)
                self.assertIsNotNone(message, "the delete was admitted")
                self.assertIn(RECORD_RULE_TOKEN, message)
                for token in names:
                    self.assertIn(token, message)
                self.assertTrue(
                    PostingMeasurement.objects.filter(
                        pk=measurement.pk).exists(),
                    "the row went even though the statement was refused")

    def _admitted_through_every_door(self, make_measurement):
        for name, door in DOORS:
            with self.subTest(door=name):
                measurement = make_measurement()
                with transaction.atomic():
                    door(measurement)
                self.assertFalse(
                    PostingMeasurement.objects.filter(
                        pk=measurement.pk).exists())


class ARecordIsNotPrunableBeforeItsInstantTest(PruneRefusalMixin, TestCase):
    """The first condition, with the second one satisfied throughout.

    Every posting here is resolved on both pairs, so the *only* thing that can
    refuse these deletes is the instant. That is not tidiness: a record refused
    for both reasons would stay refused with this condition deleted, and the
    mutation below would report it green.
    """

    REFUSAL_NAMES = NAMES_THE_INSTANT

    def test_a_record_with_no_prunable_instant_is_refused(self):
        """The live case: nothing in the tree sets this column.

        An instant nobody has named is not an instant that has passed, and the
        alternative reading — no horizon means prune whenever — would make the
        rule admit every record in the system on the day it shipped.
        """
        self._refused_through_every_door(
            lambda: _measurement(_resolved_posting(), None))

    def test_a_record_whose_instant_has_not_arrived_is_refused(self):
        self._refused_through_every_door(
            lambda: _measurement(_resolved_posting(), _far_future()))


class ARecordIsNotPrunableWhileItsPostingIsUnresolvedTest(PruneRefusalMixin,
                                                          TestCase):
    """The second condition, with the first one satisfied throughout.

    Every record here is long past its instant, so the *only* thing that can
    refuse these deletes is the parent's status — the mirror of the class above,
    and the same reason.
    """

    REFUSAL_NAMES = NAMES_THE_STATUSES

    def test_an_unresolved_supplier_cost_holds_the_measurement(self):
        self._refused_through_every_door(
            lambda: _measurement(_cost_is_unresolved(), _long_past()))

    def test_an_unknown_customer_price_holds_the_measurement(self):
        self._refused_through_every_door(
            lambda: _measurement(_price_is_unknown(), _long_past()))

    def test_the_instant_having_passed_does_not_release_it(self):
        """Stated as its own case because it is the whole of the conjunction.

        The record below is a year past its horizon and still refused, which is
        the sentence "both, not either" makes.
        """
        measurement = _measurement(_cost_is_unresolved(), _long_past())
        self.assertLess(measurement.prunable_at, timezone.now())

        message = self._refusal(_through_the_queryset, measurement)
        self.assertIsNotNone(message)
        self.assertIn(SUPPLIER_COST.status_column, message)


class ARuleRefusingEveryDeleteWouldSatisfyTheRefusalsAloneTest(PruneRefusalMixin,
                                                               TestCase):
    """THE ADMITTED MOVE, and it is the control rather than a courtesy.

    Every other assertion in this module is *"this delete was refused"*, which a
    rule refusing **every** delete satisfies completely — while making the
    retention promise unkeepable, which is a worse defect than the one being
    fixed and one no later job could repair. G19's own cost-side trio names its
    admitted move beside its refusals for exactly this reason, and the class is
    named for the job rather than for the happy path.
    """

    def test_a_prunable_record_on_a_resolved_posting_goes_through_every_door(self):
        self._admitted_through_every_door(
            lambda: _measurement(_resolved_posting(), _long_past()))

    def test_a_record_exactly_at_its_instant_is_admitted(self):
        """`>=`, not `>`, read against the clock the rule itself reads.

        The instant comes from the database rather than from Python, so this is
        the boundary and not merely a value near it — `now()` inside the trigger
        is the same transaction timestamp this row was given.
        """
        measurement = _measurement(_resolved_posting(),
                                   _the_databases_own_now())

        _through_the_queryset(measurement)

        self.assertFalse(
            PostingMeasurement.objects.filter(pk=measurement.pk).exists())

    def test_the_posting_itself_is_untouched_by_the_prune(self):
        """The reason the split exists, asserted where it could regress.

        Pruning is a `DELETE` from the child table and *"the posting is never
        written to at all"* — the whole argument for two records rather than a
        scheduled destructive write against the six-year table.
        """
        posting = _resolved_posting()
        measurement = _measurement(posting, _long_past())
        before = Posting.objects.get(pk=posting.pk).updated_at

        _through_the_queryset(measurement)

        self.assertEqual(Posting.objects.get(pk=posting.pk).updated_at, before)


class ThePredicateIsNotUnresolvedRatherThanIsResolvedTest(TestCase):
    """The three decided statuses, each of which permits the prune.

    `waived`, `not_applicable` on the price side and `not_applicable` on the
    cost side all carry a NULL amount, exactly as the two unresolved statuses
    do — the amount cannot tell a decision somebody made from information UBB is
    missing, and the status is the only thing that can. A predicate written as
    *is resolved* would hold these records forever for a resolution that is
    never coming.
    """

    def _prunes(self, posting):
        measurement = _measurement(posting, _long_past())
        _through_the_queryset(measurement)
        return not PostingMeasurement.objects.filter(
            pk=measurement.pk).exists()

    def test_a_waived_price_does_not_hold_the_measurement(self):
        self.assertTrue(self._prunes(committed_posting(
            billed_cost_micros=None, pricing_status=PRICING_STATUS_WAIVED)))

    def test_a_not_applicable_price_does_not_hold_the_measurement(self):
        self.assertTrue(self._prunes(committed_posting(
            billed_cost_micros=None,
            pricing_status=PRICING_STATUS_NOT_APPLICABLE,
            not_applicable_reason=NOT_APPLICABLE_REASON_TENANT_NOT_BILLING)))

    def test_a_not_applicable_cost_does_not_hold_the_measurement(self):
        self.assertTrue(self._prunes(committed_posting(
            provider_cost_micros=None,
            costing_status=COSTING_STATUS_NOT_APPLICABLE)))

    def test_the_two_statuses_it_does_hold_for_are_the_registrys_own(self):
        """The predicate reads one status per pair, and the registry names it.

        Asserted against `core.amount_status_pairs` rather than against two
        literals, so a rename in the vocabulary turns this red rather than
        leaving a rule that quietly matches nothing.
        """
        self.assertEqual(
            {SUPPLIER_COST.unresolved_status, CUSTOMER_PRICE.unresolved_status},
            {"unresolved", "unknown"})


class ThisRuleDeclaresNoColumnIntoADefendedClassTest(TestCase):
    """The rule adds a database defence and no declaration, which is the point.

    G19's statement is about field transition classes. This record has none —
    every column of it declares `RECORD_RULE`, which sits outside
    `DATABASE_DEFENDED` — so declaring one here to make the walk notice this
    rule would be a false statement about a column, in the gate whose whole
    subject is that declarations are true.
    """

    def test_every_column_of_the_child_still_declares_the_record_rule(self):
        self.assertEqual(
            set(PostingMeasurement.transition_classes.values()), {RECORD_RULE})
        self.assertNotIn(RECORD_RULE, DATABASE_DEFENDED)

    def test_the_child_contributes_no_column_to_the_defended_walk(self):
        declared = columns_declared_into_defended_classes(apps.get_models())

        self.assertEqual(
            [triple for triple in declared
             if triple[0] == PostingMeasurement.__name__], [])
        self.assertGreaterEqual(
            len(declared), 1,
            "the walk found nothing at all, so it says nothing about this record")

    def test_the_declaration_check_reports_a_clean_board_over_this_table(self):
        """Through the gate's own entry point, not a copy of its search.

        Two copies of one search agreeing with each other is not evidence; this
        is the third caller `columns_the_database_does_not_defend` was made
        public for.
        """
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes(apps.get_models()),
                declaring_models_by_table()), [])


class TheModelIsNotWhereThisIsEnforcedTest(TestCase):
    """No `delete()` override stands in front of the database rule.

    ADR-0007 §2 is explicit that a model-level guard is not enforcement, and the
    split decision refuses one for this record by name. Two of the three doors
    above go nowhere near a model instance, so a guard that existed would be
    covering the one door that needs it least.
    """

    def test_the_model_ships_no_delete_guard(self):
        self.assertIs(PostingMeasurement.delete,
                      PostingMeasurement.__bases__[0].delete)

    def test_a_door_that_never_loads_the_model_is_still_refused(self):
        measurement = _measurement(_resolved_posting(), None)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_raw_sql(measurement)


def _rules_on_the_child_table():
    """Every non-internal trigger on the child table, as a SET of names."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
        return {name for (name,) in cursor.fetchall()}


def _this_rule():
    """This rule's `(tgtype, prosrc)`, asked for BY NAME, or `None`."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgtype, p.prosrc FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE c.relname = %s AND t.tgname = %s", [TABLE, TRIGGER])
        return cursor.fetchone()


def _body_without_its_comments():
    """The rule's source with `--` comments stripped.

    ⚠ An SQL comment inside `prosrc` satisfies "the column is named in the
    trigger body" completely — #325 shipped a fix that passed with the whole
    branch deleted, because the comment explaining that branch still spelled the
    column. Every assertion below reads this rather than `prosrc`.
    """
    _, source = _this_rule()
    return re.sub(r"--[^\n]*", "", source)


class TheRuleIsHeldByATriggerOnTheChildTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is not evidence that a rule is installed — it is
    evidence that a file executed.
    """

    def test_the_child_table_carries_exactly_this_one_rule(self):
        """An exact set, so a second rule arriving here is something a reader
        of this module has to agree to rather than something a count absorbs."""
        self.assertEqual(_rules_on_the_child_table(), {TRIGGER})

    def test_it_fires_before_each_deleted_row_and_on_nothing_else(self):
        """`BEFORE DELETE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        **The two `assertFalse`s are ADR-0007's Consequences discharged.** That
        clause requires a database-enforced transition's per-insert and
        per-update cost to be measured rather than assumed; a trigger that
        cannot fire on either statement pays zero on both, which is a stronger
        claim than a benchmark reporting a small number and one that cannot
        drift. The recording path inserts into this table on every metered call.

        Row-level and `BEFORE`: an `AFTER` trigger would refuse by rolling back
        a row already gone, and a statement-level one cannot see `OLD` at all,
        which is the only thing this rule reads.
        """
        tgtype, _ = _this_rule()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 3), "does not fire on DELETE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 4), "fires on UPDATE")

    def test_it_judges_every_delete_rather_than_a_filtered_subset(self):
        """No `WHEN` clause, unlike all three rules on the parent table.

        Those fire only when a declared column moves, which is what keeps an
        unrelated update out of their bodies. Every `DELETE` here is exactly the
        statement under judgement, so a `WHEN` clause could only ever exempt
        one.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_triggerdef(t.oid) FROM pg_trigger t "
                "JOIN pg_class c ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND t.tgname = %s", [TABLE, TRIGGER])
            definition, = cursor.fetchone()
        self.assertNotIn("WHEN", definition)

    def test_the_rule_names_the_statuses_the_registry_declares(self):
        """The frozen tokens, held to the sources that own them.

        A trigger body is SQL living in the database, so it cannot import
        `core.amount_status_pairs` the way living code does. Each token is
        derived here from the registry entry that owns it and asserted **joined
        to its column, in one comparison** — a body naming `unresolved` and
        `costing_status` in two unrelated places would satisfy two separate
        `assertIn`s completely, which is the shape that let a rule refusing the
        wrong thing pass its fidelity check one ticket ago.

        The left-hand side is matched with a leading `\\w*` because the rule
        reads each status into a local named for its own column rather than
        comparing the column in place. Pinning the local's exact spelling here
        would make this a test of a variable name; what it has to hold is that
        the token and the column meet in a single predicate.
        """
        body = _body_without_its_comments()

        for pair in (SUPPLIER_COST, CUSTOMER_PRICE):
            with self.subTest(pair=pair.status_column):
                self.assertRegex(
                    body,
                    rf"\b\w*{re.escape(pair.status_column)}\s*=\s*"
                    rf"'{re.escape(pair.unresolved_status)}'")

    def test_the_statuses_it_compares_are_read_off_the_parent_posting(self):
        """The other half of the fidelity check, and it is not decoration.

        The assertion above says a status token meets a column name in one
        predicate; it cannot say the value on the left came from the posting
        this record belongs to. A rule reading its own table, or a constant,
        would satisfy it exactly. This asserts the columns are selected from the
        posting table, keyed on the child's own foreign key.
        """
        body = _body_without_its_comments()

        for pair in (SUPPLIER_COST, CUSTOMER_PRICE):
            with self.subTest(pair=pair.status_column):
                self.assertRegex(body, rf"\bp\.{re.escape(pair.status_column)}\b")
        self.assertRegex(body, r"FROM\s+ubb_posting\s+p\b")
        self.assertRegex(body, r"WHERE\s+p\.id\s*=\s*OLD\.posting_id\b")

    def test_the_rule_names_the_horizon_column_the_model_declares(self):
        self.assertIn(
            PostingMeasurement._meta.get_field("prunable_at").column,
            _body_without_its_comments())

    def test_the_reverse_is_exercised_rather_than_merely_declared(self):
        """Forward and back, against a real database, with a real refusal.

        `docs/conventions/django-patterns.md` asks for a reverse *a test
        actually runs*, and this migration's shape is why: a `RunPython` whose
        two halves are DDL strings, where a typo in the reverse is invisible
        until the day somebody needs it.

        Asserted by BEHAVIOUR at both ends. With the rule out, a record that no
        clock has released is deleted — which is the state the tree was in
        before this ticket, and the thing worth being able to get back to.
        """
        migration = MigrationLoader(connection).get_migration("usage", MIGRATION)
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython))

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.assertEqual(_rules_on_the_child_table(), set())
        released = _measurement(_resolved_posting(), None)
        _through_the_queryset(released)
        self.assertFalse(
            PostingMeasurement.objects.filter(pk=released.pk).exists())

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        self.assertEqual(_rules_on_the_child_table(), {TRIGGER})
        held = _measurement(_resolved_posting(), None)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(held)


#: The shipped rule with one refusal's CAUSE removed and everything else left
#: standing — the parent lookup, the sandbox scope, the surviving refusal, and
#: **every column name the real rule spells**. That last part is the method: a
#: mutation that deleted the token would be caught by anything asserting the
#: rule names a column, and would prove nothing about whether the rule holds.
#: Each mutant keeps the removed condition's column in the surviving branch's
#: message, where it says something and enforces nothing —
#: `test_both_mutants_still_spell_every_column_the_real_rule_spells` is what
#: holds them to it.
_MUTANT_PREAMBLE = """
CREATE OR REPLACE FUNCTION {function}() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE
    parent_is_sandbox     boolean;
    parent_{cost_status}  text;
    parent_{price_status} text;
BEGIN
    SELECT t.is_sandbox, p.{cost_status}, p.{price_status}
      INTO parent_is_sandbox, parent_{cost_status}, parent_{price_status}
      FROM {posting} p
      JOIN ubb_tenant t ON t.id = p.tenant_id
     WHERE p.id = OLD.posting_id;

    IF parent_is_sandbox THEN
        RETURN OLD;
    END IF;
"""

_MUTANT_CLOSE = """
    RETURN OLD;
END;
$$;
"""

#: No comparison against `prunable_at` anywhere — but the column is still read
#: and still named, in the status branch's message.
_WITHOUT_THE_INSTANT = _MUTANT_PREAMBLE + """
    IF parent_{cost_status} = '{cost_unresolved}'
       OR parent_{price_status} = '{price_unresolved}' THEN
        RAISE EXCEPTION 'whole-record rule: {cost_status} is %, '
                        '{price_status} is %, prunable_at is %',
            parent_{cost_status}, parent_{price_status},
            COALESCE(OLD.prunable_at::text, 'unset')
            USING ERRCODE = '23000';
    END IF;
""" + _MUTANT_CLOSE

#: No comparison against either status — but both are still read off the parent
#: and still named, in the instant branch's message.
_WITHOUT_THE_STATUS = _MUTANT_PREAMBLE + """
    IF OLD.prunable_at IS NULL OR now() < OLD.prunable_at THEN
        RAISE EXCEPTION 'whole-record rule: prunable_at is %, '
                        '{cost_status} is %, {price_status} is %',
            COALESCE(OLD.prunable_at::text, 'unset'),
            parent_{cost_status}, parent_{price_status}
            USING ERRCODE = '23000';
    END IF;
""" + _MUTANT_CLOSE


class TheTwoConditionsAreIndependentlyLoadBearingTest(TestCase):
    """The mutation, as a live test rather than as a number in a commit message.

    Each condition is removed **at its cause** and both outcomes are asserted
    together: the deletes that condition refused become admitted, and the
    deletes the *other* condition refuses are still refused. One without the
    other proves nothing — a rule that refused everything would satisfy the
    second assertion, and a rule that refused nothing would satisfy the first.

    ⚠ This is also why every refusal in the classes above is built with exactly
    ONE condition failing. A record refused for both reasons at once stays
    refused through either mutation, which is #331's lesson in this rule's own
    shape: a fault with two causes reads exactly like a vacuous control, and the
    two are repaired differently.
    """

    def _install(self, template):
        with connection.cursor() as cursor:
            cursor.execute(template.format(
                function=FUNCTION, posting=Posting._meta.db_table,
                cost_status=SUPPLIER_COST.status_column,
                cost_unresolved=SUPPLIER_COST.unresolved_status,
                price_status=CUSTOMER_PRICE.status_column,
                price_unresolved=CUSTOMER_PRICE.unresolved_status))

    def _deletes(self, measurement):
        try:
            with transaction.atomic():
                _through_the_queryset(measurement)
        except IntegrityError:
            return False
        return True

    def test_without_the_instant_an_unreleased_record_is_pruned(self):
        never_released = _measurement(_resolved_posting(), None)
        still_unresolved = _measurement(_cost_is_unresolved(), _long_past())

        self._install(_WITHOUT_THE_INSTANT)

        self.assertTrue(
            self._deletes(never_released),
            "the instant condition refused this and its cause is gone")
        self.assertFalse(
            self._deletes(still_unresolved),
            "the status condition was not the thing removed")

    def test_without_the_status_an_unresolved_postings_record_is_pruned(self):
        still_unresolved = _measurement(_price_is_unknown(), _long_past())
        never_released = _measurement(_resolved_posting(), None)

        self._install(_WITHOUT_THE_STATUS)

        self.assertTrue(
            self._deletes(still_unresolved),
            "the status condition refused this and its cause is gone")
        self.assertFalse(
            self._deletes(never_released),
            "the instant condition was not the thing removed")

    def test_both_mutants_still_spell_every_column_the_real_rule_spells(self):
        """The control on the method: neither mutation is a token edit.

        If a mutant stopped naming the column whose condition it drops, the two
        tests above would be measuring a rule that stopped *mentioning*
        something rather than one that stopped *enforcing* it — and every
        assertion in this module that reads the body for a name would catch the
        mutation for the wrong reason.
        """
        for name, template in (("without the instant", _WITHOUT_THE_INSTANT),
                               ("without the status", _WITHOUT_THE_STATUS)):
            with self.subTest(mutant=name):
                self._install(template)
                body = _this_rule()[1]
                for token in (NAMES_THE_INSTANT, *NAMES_THE_STATUSES):
                    self.assertIn(token, body)


def _sandbox_posting(**columns):
    """A posting on a sandbox tenant, built the way the table's checks require.

    `ck_sandbox_iff_parent` holds `is_sandbox` to *if and only if it has a
    parent tenant*, so a sandbox cannot be conjured by flipping a flag — which
    is the reason this condition cannot be turned on to escape the rule.
    """
    live = Tenant.objects.create(name="live")
    sandbox = Tenant.objects.create(name="live sandbox", is_sandbox=True,
                                    parent_tenant=live)
    customer = Customer.objects.create(tenant=sandbox, external_id="c1")
    columns.setdefault("idempotency_key", "k")
    return Posting.objects.create(tenant=sandbox, customer=customer, **columns)


class ADiscardIsNotAPruneTest(TestCase):
    """A sandbox's measurements come away, and a live tenant's in the same shape
    do not.

    ⚠ **This condition is not in the ticket.** It is here because the ticket's
    two would refuse `reset_sandbox_tenant` outright: that task hard-deletes a
    sandbox tenant's customers, Django's collector deletes each measurement
    before its posting, and every one of those rows has a NULL horizon while
    many belong to unresolved postings. Its per-label handler collects the
    failures and raises, leaving the sandbox `is_active = False`. **No existing
    test would have caught it** — every sandbox fixture builds its postings
    through `Posting.objects.create` and so has no measurement children at all,
    which is why `test_sandbox.py` now seeds one.

    The rule's subject is *pruning*: removing the detail while the durable
    economic record survives it. Neither obligation it protects — the six-year
    retention promise, and the inputs a resolution run needs — exists for a
    sandbox, which is a sibling tenant row carrying disposable traffic behind
    `ubb_test_` keys and a reset button. Discarding is not pruning, and the rule
    says so positively rather than through a session setting or a temporary
    drop, either of which would be a door.

    The condition it stands in for — *the posting itself is going too* — is not
    expressible in a `BEFORE DELETE` trigger under Django's collector, which
    deletes the child while its parent is still on disk. The migration's
    docstring carries that argument and the two mechanisms that could express
    it, both of which are larger decisions than this rule.
    """

    def _prunes(self, measurement):
        try:
            with transaction.atomic():
                _through_the_queryset(measurement)
        except IntegrityError:
            return False
        return not PostingMeasurement.objects.filter(
            pk=measurement.pk).exists()

    def test_a_sandbox_record_comes_away_in_the_state_a_reset_finds_it_in(self):
        """NULL horizon and an unresolved posting — both conditions failing.

        That is not a contrived shape: it is what every measurement a sandbox
        has ever recorded looks like, because nothing sets the horizon and an
        unpriced or uncosted event is the ordinary case in test traffic.
        """
        posting = _sandbox_posting(
            provider_cost_micros=None,
            costing_status=SUPPLIER_COST.unresolved_status,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)

        self.assertTrue(self._prunes(_measurement(posting, None)))

    def test_it_comes_away_through_every_door(self):
        for name, door in DOORS:
            with self.subTest(door=name):
                measurement = _measurement(_sandbox_posting(), None)
                with transaction.atomic():
                    door(measurement)
                self.assertFalse(
                    PostingMeasurement.objects.filter(
                        pk=measurement.pk).exists())

    def test_a_live_tenants_record_in_the_same_state_is_refused(self):
        """The control, and without it the class above proves nothing.

        Two records identical in every respect the child table can see — same
        NULL horizon, same unresolved parent — and the only difference is which
        tenant owns the posting.
        """
        live = _measurement(_cost_is_unresolved(), None)

        self.assertFalse(self._prunes(live))

    def test_the_exemption_cannot_be_turned_on_for_a_live_tenant(self):
        """`is_sandbox` is held by a `CHECK`, not by convention.

        A rule that can be escaped by setting a boolean is a rule with a door.
        This one cannot: a sandbox is a tenant with a parent, and the table
        refuses the combination that would make an ordinary tenant one.
        """
        live = Tenant.objects.create(name="live only")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Tenant.objects.filter(pk=live.pk).update(is_sandbox=True)

    def test_the_rule_reads_the_flag_off_the_tenant_that_owns_the_posting(self):
        """Joined through the posting, so a sandbox cannot lend its exemption.

        Read out of the installed body rather than inferred from the behaviour
        above, because the two tenants in this module differ in more than one
        way and a rule keyed on the wrong one would answer correctly here by
        accident.
        """
        body = _body_without_its_comments()

        self.assertRegex(body, r"JOIN\s+ubb_tenant\s+t\s+ON\s+t\.id\s*=\s*p\.tenant_id")
        self.assertRegex(body, r"\bt\.is_sandbox\b")
