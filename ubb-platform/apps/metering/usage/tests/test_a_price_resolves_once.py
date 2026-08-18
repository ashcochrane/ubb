"""A customer price resolves once, and the table refuses every other move (#352).

#351 made `billed_cost_micros` nullable so that *not resolved* became sayable,
and put the four legal combinations of amount, status and reason into a `CHECK`.
A `CHECK` sees one row at a time. It cannot see the row that was there a moment
ago, so it cannot tell **completing a blank** from **changing an answer** — and
that difference is the whole of ADR-0007 §2's `RESOLVE_ONCE`:

    resolution completes previously unknown information; correction changes a
    value that was already asserted. Completing a blank is permitted once.
    Replacing a known value is prohibited.

This module is the price half of what `test_a_cost_settles_once.py` proves for
the supplier side, one slice later. One declaration is under test, made on the
model in `transition_classes`:

* `billed_cost_micros` + `pricing_status` — `RESOLVE_ONCE`, **as a pair**. The
  one permitted move is `unknown` → `known`, which completes the amount and
  moves the status in a single statement. Nothing else.

**There is no `FROZEN` case here, and its absence is a decision.** The cost side
declares one because a caller may report what it believes a call cost, and what
was said is a record of what was said. The spec's ruling 2 refuses the price-side
symmetry outright: a cost is *observed* and a price is *decided*, so there is no
claimed-price column for a class to be declared over. A reader expecting the two
sides to mirror exactly should stop here rather than go looking for one.

**⚠ WHY THIS MODULE EXISTS SEPARATELY FROM THE DECLARATION.** G19 walks the
declarations and asks, for each declared column, whether the table's rules name
it — a **word-boundary search over the concatenated trigger bodies**. #325
measured that deleting a refusal branch outright leaves that search satisfied,
because the branch's own `WHEN` clause and comments still spell the column. So
**a green G19 proves only that this column is NAMED by a rule, never that the
rule holds.** What proves holding is the trio below, and
`AGreenDeclarationCheckDoesNotProveTheRuleHoldsTest` is that sentence as a test:
it replaces the shipped rule with one that names both columns and refuses
nothing, watches the gate stay green, and watches the write go through.

**The admitted move is not a courtesy, it is the control.** Every other
assertion here is *"this statement was refused"*, which a trigger that refused
**every** write would satisfy completely — and a table that admitted no
resolution at all would be a worse defect than the one being fixed. The class
carrying it is named for that job.

**Which mechanism refuses which statement, asserted rather than assumed.** Some
prohibited moves are also impossible under #351's combination `CHECK`. Every
refusal below therefore asserts **the message Postgres answers with**: the
trigger names the transition class it is holding, and a `CHECK` names its own
constraint. That distinction has teeth here, because this table now carries
**two** triggers and three `CHECK`s over two sibling pairs, and "something
refused this" stopped being evidence the moment the second one landed.

**A `BEFORE` trigger runs before the table's constraints are evaluated**, so on
an `UPDATE` the trigger answers first and the combination `CHECK` is never
consulted. The `CHECK` is therefore proved on `INSERT`, which this trigger does
not fire on — that is `test_a_price_ubb_cannot_resolve_stops_being_zero.py`'s
whole subject, and it is why every case in that module is an `INSERT`.
"""
import re

from django.db import IntegrityError, connection, migrations, models, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from core.transitions import (
    RESOLVE_ONCE, columns_declared_into_defended_classes)
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
)

PRICE = "billed_cost_micros"
STATUS = "pricing_status"
REASON = "not_applicable_reason"

TABLE = Posting._meta.db_table

#: The rule this module is about, addressed BY NAME rather than by counting.
#: The table carries two now, and `pg_trigger` promises no order at all, so an
#: assertion reading "the first row" would be reading whichever one Postgres
#: happened to hand back.
TRIGGER = "trg_posting_price_transitions"
FUNCTION = "ubb_posting_price_transitions"

MIGRATION = "0039_a_price_resolves_once_and_the_table_holds_it"


def _posting(**columns):
    """A committed posting, each with a tenant and customer of its own."""
    tenant = Tenant.objects.create(name="T")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    columns.setdefault("idempotency_key", "k")
    return Posting.objects.create(tenant=tenant, customer=customer, **columns)


def _unknown(**columns):
    """A price UBB could not resolve — the one state a resolution may start in."""
    return _posting(**{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN,
                       REASON: None, **columns})


def _resolved(amount=100, **columns):
    return _posting(**{PRICE: amount, STATUS: PRICING_STATUS_KNOWN, **columns})


def _waived(**columns):
    return _posting(**{PRICE: None, STATUS: PRICING_STATUS_WAIVED,
                       REASON: None, **columns})


def _not_applicable(reason=NOT_APPLICABLE_REASON_FIXED_TASK_PRICING, **columns):
    return _posting(**{PRICE: None, STATUS: PRICING_STATUS_NOT_APPLICABLE,
                       REASON: reason, **columns})


# --- The three doors ADR-0007 §2 names, each writing the same columns --------
#
# A guard only one of them respects is the defect the rule exists to catch, so
# every prohibited transition below is driven through all three. They are spelled
# again here rather than imported from the cost module: that module is slice 3's
# record and a shared helper would let either file's deletion take both trios
# down with it.

def _through_the_queryset(posting, **columns):
    Posting.objects.filter(pk=posting.pk).update(**columns)


def _through_raw_sql(posting, **columns):
    assignments = ", ".join(f"{name} = %s" for name in columns)
    with connection.cursor() as cursor:
        cursor.execute(f"UPDATE {TABLE} SET {assignments} WHERE id = %s",
                       [*columns.values(), str(posting.pk)])


def _through_save(posting, **columns):
    """`save()`, reaching around the model's own refusal on the way.

    `Posting.save()` raises on any update, so a plain `save()` never reaches the
    database and would prove nothing about it. Calling the base implementation is
    what a writer that bypasses the override looks like — a `bulk_update`, a data
    migration, a shell session — and it is the door ADR-0007 §2 means.
    """
    for name, value in columns.items():
        setattr(posting, name, value)
    models.Model.save(posting)


DOORS = (("QuerySet.update()", _through_the_queryset),
         ("raw SQL", _through_raw_sql),
         ("save()", _through_save))


class TransitionRefusalMixin:

    def _refusal(self, door, posting, **columns):
        """The message Postgres refused with, or `None` if it did not refuse."""
        try:
            with transaction.atomic():
                door(posting, **columns)
        except IntegrityError as refusal:
            return str(refusal)
        return None

    def _refused_by_the_trigger(self, posting_factory, transition_class,
                                **columns):
        for name, door in DOORS:
            with self.subTest(door=name):
                message = self._refusal(door, posting_factory(), **columns)
                self.assertIsNotNone(message, "the write was admitted")
                self.assertIn(transition_class, message)


class ATriggerRefusingEveryWriteWouldSatisfyTheRefusalsAloneTest(
        TransitionRefusalMixin, TestCase):
    """The admitted move, and the trio is worthless without it.

    Every other class in this module asserts that a statement was refused. A
    trigger with a single unconditional `RAISE` at the top of its body would
    make every one of them pass, while making the price column impossible to
    resolve — a worse defect than recording an unresolved price as zero, because
    it cannot be repaired by a later run.

    G19's own enforcement nodes name the cost side's equivalent beside its
    refusals for exactly this reason. This is the price side's, driven through
    the same three doors, and the class is named for the failure it catches
    rather than for the behaviour it exercises.
    """

    RESOLUTION = {PRICE: 4_200, STATUS: PRICING_STATUS_KNOWN}

    def test_an_unknown_price_resolves_through_every_door(self):
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _unknown()
                door(posting, **self.RESOLUTION)
                posting.refresh_from_db()
                self.assertEqual(
                    (getattr(posting, PRICE), getattr(posting, STATUS),
                     getattr(posting, REASON)),
                    (4_200, PRICING_STATUS_KNOWN, None))

    def test_a_resolution_of_exactly_zero_is_admitted(self):
        """Zero is a resolved price, not a missing one.

        The distinction #351's column exists to hold: an event a rule prices at
        nothing resolves at `0` and is `known`, and it must not be turned away
        by a rule written as if a resolution always carries a positive number.
        """
        posting = _unknown()
        _through_the_queryset(posting, **{**self.RESOLUTION, PRICE: 0})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, PRICE), 0)

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        """The trigger guards three columns, not the table.

        A posting's balance and attribution columns are written by paths that
        have nothing to do with pricing, and a rule that quietly froze the whole
        row would break them somewhere far from here.
        """
        posting = _resolved()
        _through_the_queryset(posting, balance_after_micros=17)
        posting.refresh_from_db()
        self.assertEqual(posting.balance_after_micros, 17)

    def test_the_supplier_side_still_settles_beside_it(self):
        """The two rules govern disjoint columns, and neither eats the other.

        This table now carries two triggers over two sibling pairs. The failure
        that would make installing a second one a mistake is a rule that fires
        on the other's statement and refuses it, and a settlement is the write
        most likely to trip a badly-scoped `WHEN` clause — so the cost side's
        one admitted move is exercised here too, against the table as it stands
        after this ticket rather than as slice 3 left it.
        """
        from core.vocabulary import (
            COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED,
            UNRESOLVED_REASON_COST_RATE_MISSING)

        posting = _posting(**{"provider_cost_micros": None,
                              "costing_status": COSTING_STATUS_UNRESOLVED,
                              "unresolved_reason":
                                  UNRESOLVED_REASON_COST_RATE_MISSING})
        _through_the_queryset(
            posting, provider_cost_micros=7, costing_status=COSTING_STATUS_KNOWN,
            unresolved_reason=None)
        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 7)


class TheResolvedPriceIsNotEditableTest(TransitionRefusalMixin, TestCase):
    """Replacing a known value is a correction, and corrections are prohibited.

    ADR-0007 §2: a correction *"must be a separate record beside the original"*.
    A `CHECK` cannot see this — `known` with an amount is legal on both sides of
    the write — so every case in this class is the trigger's alone.
    """

    def test_a_resolved_price_cannot_be_overwritten(self):
        self._refused_by_the_trigger(_resolved, RESOLVE_ONCE, **{PRICE: 999})

    def test_a_resolved_price_cannot_be_unresolved(self):
        """The status cannot move backwards, even into a legal combination."""
        self._refused_by_the_trigger(
            _resolved, RESOLVE_ONCE,
            **{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN})

    def test_a_resolved_posting_cannot_be_waived_after_the_fact(self):
        """A charge that exists is not waived by deleting the number.

        Waiving is a decision not to pursue a charge, and it is made about a
        posting before there is one to pursue. Applying it afterwards would take
        a resolved amount out of every total that has already reported it, with
        nothing left on the row to say a number was ever there.
        """
        self._refused_by_the_trigger(
            _resolved, RESOLVE_ONCE,
            **{PRICE: None, STATUS: PRICING_STATUS_WAIVED})

    def test_a_resolved_posting_cannot_become_not_applicable(self):
        self._refused_by_the_trigger(
            _resolved, RESOLVE_ONCE,
            **{PRICE: None, STATUS: PRICING_STATUS_NOT_APPLICABLE,
               REASON: NOT_APPLICABLE_REASON_FIXED_TASK_PRICING})


class OnlyAnUnknownPriceResolvesTest(TransitionRefusalMixin, TestCase):
    """`unknown` is the only state a resolution may start in.

    The spec's ruling 12c decides the sharpest of these: a run's membership is
    *"the status itself, not a separate flag"*, so a `waived` posting is outside
    it **by construction**. `waived` is a decision somebody made; `unknown` is
    information UBB does not have. If the table admitted the first as a
    resolution source, the difference would survive only as long as everyone
    remembered the selector.
    """

    def test_a_waived_posting_is_never_a_resolution_candidate(self):
        self._refused_by_the_trigger(
            _waived, RESOLVE_ONCE,
            **{PRICE: 100, STATUS: PRICING_STATUS_KNOWN})

    def test_a_not_applicable_posting_cannot_be_priced(self):
        """A subject that generates no customer revenue never acquires one.

        Every combination involved is legal to the `CHECK` on both sides, so
        this refusal is the trigger's alone.
        """
        self._refused_by_the_trigger(
            _not_applicable, RESOLVE_ONCE,
            **{PRICE: 100, STATUS: PRICING_STATUS_KNOWN, REASON: None})

    def test_an_unknown_posting_cannot_be_waived_instead_of_resolved(self):
        """The other way out of `unknown`, and it is closed.

        A price nobody could resolve is not the same fact as a charge somebody
        decided not to pursue. Letting the first become the second would make
        the unresolved queue shrink by relabelling rather than by resolving —
        and the two carry an identical pair of absent columns, so nothing on the
        row would show it had happened.
        """
        self._refused_by_the_trigger(
            _unknown, RESOLVE_ONCE, **{STATUS: PRICING_STATUS_WAIVED})

    def test_an_unknown_posting_cannot_be_written_off_as_not_applicable(self):
        self._refused_by_the_trigger(
            _unknown, RESOLVE_ONCE,
            **{STATUS: PRICING_STATUS_NOT_APPLICABLE,
               REASON: NOT_APPLICABLE_REASON_FIXED_TASK_PRICING})

    def test_the_reason_cannot_be_re_diagnosed_in_place(self):
        """Which cause produced `not_applicable` is settled when it is written.

        Re-labelling it rewrites what the system said at the time, on a row a
        tenant may already have been shown, and the two causes send a reader to
        different places: one says this tenant bills nobody through UBB, the
        other says this Task was sold for one agreed price.
        """
        self._refused_by_the_trigger(
            _not_applicable, RESOLVE_ONCE,
            **{REASON: NOT_APPLICABLE_REASON_TENANT_NOT_BILLING})


class TheAmountAndTheStatusNeverSeparateTest(TransitionRefusalMixin, TestCase):
    """Half a resolution is refused, from both sides.

    A resolution is one statement moving the amount and the status together. A
    row that had completed its amount and not said so would be counted as
    unresolved by every total built on the pair, while carrying a number the
    tenant can see — which is the ambiguity #351 removed, re-created one column
    to the left.

    **On an `UPDATE` the trigger answers first, and it answers alone.** A
    `BEFORE` trigger runs before the table's constraints are evaluated, so a
    half-resolution never reaches the combination `CHECK`. That is why #351's
    own combination cases are `INSERT`s: on `UPDATE` they would have been
    evidence about this trigger instead.
    """

    def test_a_resolution_that_moves_the_amount_alone_is_refused(self):
        self._refused_by_the_trigger(_unknown, RESOLVE_ONCE, **{PRICE: 50})

    def test_a_resolution_that_moves_the_status_alone_is_refused(self):
        self._refused_by_the_trigger(
            _unknown, RESOLVE_ONCE, **{STATUS: PRICING_STATUS_KNOWN})

    def test_a_resolution_that_carries_a_reason_is_refused(self):
        """`not_applicable_reason` is read only where the status is that.

        A resolved posting carrying one would be a row saying both that it has
        a price and that it never could have had one.
        """
        self._refused_by_the_trigger(
            _unknown, RESOLVE_ONCE,
            **{PRICE: 50, STATUS: PRICING_STATUS_KNOWN,
               REASON: NOT_APPLICABLE_REASON_FIXED_TASK_PRICING})

    def test_the_amount_alone_cannot_move_on_a_resolved_row(self):
        """The same rule from the other side, where the `CHECK` is content."""
        self._refused_by_the_trigger(_resolved, RESOLVE_ONCE, **{PRICE: 51})


class TheModelGuardIsNotTheEnforcementTest(TestCase):
    """ADR-0007 §2's named failure, tested rather than trusted.

    `Posting.save()` refuses every update. That refusal is a convenience for the
    ordinary recording path and it is **not** what holds `RESOLVE_ONCE`: it is
    written in Python, so it protects exactly the writers that go through it —
    and neither a bulk writer, a data migration nor a shell session does.
    """

    def test_the_model_still_refuses_an_update_through_its_own_door(self):
        posting = _resolved()
        setattr(posting, PRICE, 5)
        with self.assertRaises(ValueError):
            posting.save()

    def test_reaching_around_that_guard_lands_on_the_database(self):
        posting = _resolved()
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_save(posting, **{PRICE: 5})
        self.assertIn(RESOLVE_ONCE, str(refusal.exception))

    def test_the_guard_being_absent_would_change_nothing(self):
        """The same write, through the door the guard does not cover at all.

        `QuerySet.update()` never calls `save()`. If the model guard were the
        enforcement, this statement would land — which is the whole argument for
        putting the rule in the table.
        """
        posting = _resolved()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(posting, **{PRICE: 5})


def _triggers_on_the_table():
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgname FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "WHERE c.relname = %s AND NOT t.tgisinternal", [TABLE])
        return {name for (name,) in cursor.fetchall()}


def _this_trigger():
    """This rule's row, asked for BY NAME. Module-level, so that the mutation
    class below can read the shipped body without standing a test case up."""
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT t.tgtype, p.prosrc FROM pg_trigger t "
            "JOIN pg_class c ON c.oid = t.tgrelid "
            "JOIN pg_proc p ON p.oid = t.tgfoid "
            "WHERE c.relname = %s AND t.tgname = %s", [TABLE, TRIGGER])
        return cursor.fetchone()


class TheRuleIsHeldByASecondTriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is not evidence that a rule is installed — it is
    evidence that a file executed. What matters is what `pg_trigger` holds now,
    on the table the model actually uses.

    **The mechanism is slice 3's, extended to a second rule, and that was the
    constraint rather than the preference.** A `CHECK` cannot see `OLD` at all,
    so it can carry this pair's legal combinations — #351 has it doing exactly
    that — and can never carry a transition. A Postgres `RULE` rewrites the
    statement rather than judging it. Two *different* mechanisms holding sibling
    pairs on one table is how the two rules come to disagree, so this is another
    `BEFORE UPDATE ... FOR EACH ROW` trigger: same shape, same door coverage,
    same error class, its own columns.
    """

    def test_the_table_carries_exactly_the_two_declared_rules(self):
        """An exact set, and it is addressed by name in both directions.

        Slice 3 asserted "exactly one trigger" here, which was true and is not.
        A count is what would have gone quietly wrong: a third rule arriving, or
        this one being dropped while another was added, keeps any count that was
        merely bumped. Naming both is what makes a future arrival a decision.
        """
        self.assertEqual(
            _triggers_on_the_table(),
            {"trg_posting_declared_transitions", TRIGGER})

    def test_it_fires_before_each_updated_row(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        Row-level and before the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing this rule is about.
        """
        tgtype, _ = _this_trigger()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_the_reverse_is_exercised_rather_than_merely_declared(self):
        """Forward and back, against a real database, with a real refusal.

        `docs/conventions/django-patterns.md` asks for a reverse *"that a test
        actually runs"*, and the reason is exactly this migration's shape: a
        `RunPython` whose two halves are DDL strings, where a typo in the
        reverse is invisible until the day somebody needs it and no other test
        will ever execute that branch.

        It is asserted by BEHAVIOUR at both ends rather than by counting
        catalogue rows: with the rule reversed out, a write it refuses is
        admitted; with it re-applied, the same write is refused again. Postgres
        runs DDL inside the transaction this `TestCase` rolls back, so all of it
        leaves with the test and no other test sees a table without its rule.

        **The cost side's trigger is left standing throughout**, and the set is
        asserted at both ends, so a reverse that took the neighbouring rule down
        with it would fail here rather than somewhere unrelated.
        """
        migration = MigrationLoader(connection).get_migration("usage", MIGRATION)
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython))
        resolved = _resolved()

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.assertEqual(_triggers_on_the_table(),
                         {"trg_posting_declared_transitions"})
        _through_the_queryset(resolved, **{PRICE: 999})
        resolved.refresh_from_db()
        self.assertEqual(getattr(resolved, PRICE), 999)

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        self.assertEqual(_triggers_on_the_table(),
                         {"trg_posting_declared_transitions", TRIGGER})
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(resolved, **{PRICE: 1_000})

    def test_the_rule_names_the_status_values_the_registry_declares(self):
        """The one place a token is spelled outside `domain-vocabulary/`.

        A trigger body is frozen SQL living in the database, so it cannot import
        `core.vocabulary` the way the model does. If a value is ever renamed in
        the registry, the constants below move and this assertion goes red,
        which is what forces the migration that would otherwise be forgotten —
        leaving a rule that quietly matched nothing.
        """
        _, source = _this_trigger()
        self.assertIn(f"'{PRICING_STATUS_UNKNOWN}'", source)
        self.assertIn(f"'{PRICING_STATUS_KNOWN}'", source)


#: A replacement body that NAMES both declared columns and refuses nothing.
#:
#: The `WHEN` clause on the shipped trigger is unchanged — only the function it
#: calls is swapped — so both columns are still spelled in what
#: `pg_get_triggerdef` returns, and both are spelled again in the body below.
#: That is the whole of what G19's declaration check looks for.
#:
#: It is a deliberately *plausible* mutation rather than an empty function: this
#: is what deleting a refusal branch from the shipped rule leaves behind, which
#: is the mutation #325 measured on the cost side and found the gate content
#: with.
TOOTHLESS = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF NEW.{PRICE} IS DISTINCT FROM OLD.{PRICE}
       OR NEW.{STATUS} IS DISTINCT FROM OLD.{STATUS}
       OR NEW.{REASON} IS DISTINCT FROM OLD.{REASON} THEN
        NULL;
    END IF;
    RETURN NEW;
END;
$$;
"""


class AGreenDeclarationCheckDoesNotProveTheRuleHoldsTest(TestCase):
    """Why this module exists, as a test rather than as a paragraph.

    G19 has two kinds of enforcement node. The first walks the declarations and
    asks the database whether each declared column is named by a rule on its
    table; it names no column, so it judges this slice's pair on the day it is
    declared, and that is a genuinely good edge. The second kind is the trio
    above.

    **Only the second kind proves anything about behaviour**, and this class is
    the measurement of the difference. It replaces the shipped rule with one
    that still names both columns and refuses nothing, then asserts, on the same
    database in the same test:

    * the declaration check reports a clean board, over the **whole tree**,
      through its own entry point — not a re-implementation of its regex here,
      which would prove only that two copies of one search agree; and
    * the write that rule exists to refuse is admitted.

    Postgres runs `CREATE OR REPLACE FUNCTION` inside the transaction this
    `TestCase` rolls back, so the shipped rule is restored when the test ends
    and nothing else ever sees the toothless one.
    """

    def _install_the_toothless_rule(self):
        with connection.cursor() as cursor:
            cursor.execute(TOOTHLESS)

    def test_the_pair_is_declared_into_a_class_the_database_must_defend(self):
        """The premise, established rather than assumed.

        Without this the class below could pass on a tree where nothing was
        declared at all — a clean board over an empty walk, which is the vacuity
        the gate's own guard exists to catch.
        """
        declared = dict(
            (column, transition_class)
            for _, column, transition_class
            in columns_declared_into_defended_classes([Posting]))
        self.assertEqual(declared[PRICE], RESOLVE_ONCE)
        self.assertEqual(declared[STATUS], RESOLVE_ONCE)

    def test_the_shipped_rule_passes_the_declaration_check_and_holds(self):
        """Both halves true at once, which is the state to compare against."""
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes([Posting]),
                declaring_models_by_table()),
            [])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(_resolved(), **{PRICE: 999})

    def test_a_rule_that_refuses_nothing_still_passes_the_declaration_check(self):
        """⚠ The sentence this ticket exists for, measured.

        A green G19 says the column is NAMED by a rule. It does not say the rule
        holds, and here is a database where the first is true and the second is
        false.
        """
        self._install_the_toothless_rule()
        self.assertEqual(
            columns_the_database_does_not_defend(
                columns_declared_into_defended_classes([Posting]),
                declaring_models_by_table()),
            [])

    def test_and_the_trio_above_goes_red_against_that_same_rule(self):
        """The other half — the refusals stop refusing, and the control stands.

        Three of the trio's shapes are exercised against the toothless rule:
        a correction, a resolution from a state that is not `unknown`, and a
        half-resolution. Each is admitted, which is what "the trio goes red"
        means in a test that must itself stay green.

        The admitted move is checked here too, and it still works — because a
        mutation that broke it would make the trio fail for a reason that has
        nothing to do with the refusals, and that is the shape a two-cause
        fault takes.
        """
        self._install_the_toothless_rule()

        correction = _resolved()
        _through_the_queryset(correction, **{PRICE: 999})
        correction.refresh_from_db()
        self.assertEqual(getattr(correction, PRICE), 999)

        waived = _waived()
        _through_the_queryset(waived, **{PRICE: 1, STATUS: PRICING_STATUS_KNOWN})
        waived.refresh_from_db()
        self.assertEqual(getattr(waived, STATUS), PRICING_STATUS_KNOWN)

        half = _resolved()
        _through_raw_sql(half, **{PRICE: 3})
        half.refresh_from_db()
        self.assertEqual(getattr(half, PRICE), 3)

        admitted = _unknown()
        _through_the_queryset(admitted, **{PRICE: 7,
                                           STATUS: PRICING_STATUS_KNOWN})
        admitted.refresh_from_db()
        self.assertEqual(getattr(admitted, PRICE), 7)

    def test_the_column_is_named_by_the_shipped_rule_in_a_refusing_branch(self):
        """The distinction the check cannot draw, drawn here by hand.

        The toothless body above and the shipped one are both bodies in which a
        word-boundary search for the column succeeds. What separates them is a
        `RAISE` reachable from the branch that names it — a property no regex
        over the concatenated definitions can express, and the reason this
        module's other classes are the evidence rather than this one.
        """
        _, shipped = _this_trigger()
        self.assertTrue(re.search(rf"\b{PRICE}\b", shipped))
        self.assertIn("RAISE EXCEPTION", shipped)
        self.assertNotIn("RAISE", TOOTHLESS)
