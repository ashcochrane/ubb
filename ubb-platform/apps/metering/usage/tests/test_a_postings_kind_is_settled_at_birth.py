"""A posting is born one kind or the other and is never converted (#417).

`Posting.kind` is declared `FROZEN` — ADR-0007 §2's *none after insert* — and
this module is what proves the database keeps it. It is the fourth rule on
`ubb_posting` and the FIRST that admits no move at all, which makes it shaped
differently from its three neighbours rather than a fourth copy of them:

* `test_a_cost_settles_once.py`, `test_a_price_resolves_once.py` and
  `test_a_receipt_seals_once_it_is_complete.py` each prove a `RESOLVE_ONCE`
  declaration, and each opens with the ADMITTED MOVE, because a trigger that
  refused every write would satisfy every refusal beside it while making the
  column impossible to resolve.
* `FROZEN` has no admitted move to hold up as that control, so the equivalent
  job is done by `ThisRuleGuardsItsOwnColumnAndNoOthersTest` below: a rule that
  refused everything would be caught by the columns and the sibling rules it
  must leave alone, and those are asserted here rather than assumed.

**WHY THE COLUMN IS FROZEN AND NOT MERELY CHECKED.** The value-set `CHECK`
beside it says a row's kind is one of the two the registry declares; it cannot
say anything about the row that was there a moment ago, so under a `CHECK`
alone a single `UPDATE` moves a whole posting between the two populations every
kind-filtered read separates — the projected revenue and the metered events —
with every amount on the row still correct and both totals wrong afterwards.

**⚠ A GREEN G19 PROVES ONLY THAT THE COLUMN IS NAMED BY A RULE.** The gate is a
word-boundary search over this table's concatenated trigger bodies, so a
refusal branch deleted outright leaves it satisfied (#325 measured exactly
that). What proves holding is the trio below, driven through all three doors
ADR-0007 §2 names, and `AGreenDeclarationCheckDoesNotProveThisRuleHoldsTest` is
that sentence as a test.

**⚠ NAMING THE TRANSITION CLASS IS NOT ENOUGH ON THIS TABLE.**
`claimed_provider_cost_micros` is declared `FROZEN` too, and #318's rule is what
holds it — so a refusal asserting only the class token could be satisfied by the
WRONG rule refusing the write. Every refusal here asserts the COLUMN beside the
class, which is #352's lesson applied the first time a second instance of a
class joins this table.

**A `BEFORE` trigger runs before the table's constraints are evaluated**, so on
an `UPDATE` this rule answers first and `ck_posting_kind` is never consulted.
The `CHECK` is therefore proved on `INSERT`, which this trigger does not fire
on — `TheClosedSetIsHeldAtTheDatabaseTest` below is that half.
"""
import re

from django.apps import apps
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import (
    DOORS, TransitionRefusalMixin, committed_posting, rule_on_the_table,
    rules_on_the_table, through_the_queryset)
from apps.platform.tests.test_transition_class_declarations import (
    columns_the_database_does_not_defend, declaring_models_by_table)
from core.transitions import FROZEN, columns_declared_into_defended_classes
from core.vocabulary import (
    USAGE_EVENT_KIND_METERED_USAGE, USAGE_EVENT_KIND_TASK_CHARGE,
    USAGE_EVENT_KIND_VALUES,
)

KIND = "kind"

TABLE = Posting._meta.db_table

#: The rule this module is about, addressed BY NAME rather than by counting.
#: The table carries four now and `pg_trigger` promises no order at all, so an
#: assertion reading "the first row" would be reading whichever one Postgres
#: happened to hand back.
TRIGGER = "trg_posting_kind_frozen"
FUNCTION = "ubb_posting_kind_frozen"

CHECK = "ck_posting_kind"


def _metered(**columns):
    return committed_posting(**{KIND: USAGE_EVENT_KIND_METERED_USAGE,
                                **columns})


def _a_charge(**columns):
    return committed_posting(**{KIND: USAGE_EVENT_KIND_TASK_CHARGE, **columns})


class AKindIsNeverConvertedTest(TransitionRefusalMixin, TestCase):
    """The refusals, both directions, through all three doors.

    BOTH directions, because a rule written as *nothing may become a charge*
    would pass the first case and leave the one that matters more open: a
    projection relabelled as a metered event takes revenue out of the charge
    population while leaving it in every monetary total, which is the harder
    disagreement to notice.
    """

    REFUSAL_NAMES = KIND

    def test_a_metered_posting_cannot_become_a_charge(self):
        self._refused_by_the_trigger(
            _metered, FROZEN, **{KIND: USAGE_EVENT_KIND_TASK_CHARGE})

    def test_a_charge_posting_cannot_become_a_metered_event(self):
        self._refused_by_the_trigger(
            _a_charge, FROZEN, **{KIND: USAGE_EVENT_KIND_METERED_USAGE})

    def test_the_refusal_names_both_the_class_and_the_column(self):
        """⚠ THE ASSERTION THAT SEPARATES THIS RULE FROM ITS NEIGHBOUR.

        `claimed_provider_cost_micros` is `FROZEN` on this same table under
        #318's rule, so a message carrying only the class token would be
        satisfied by that rule refusing the write instead. The mixin above
        checks both for every case; this one says out loud what it is checking
        and would go red if the message were softened to name only one.
        """
        posting = _metered()
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                through_the_queryset(
                    posting, **{KIND: USAGE_EVENT_KIND_TASK_CHARGE})
        message = str(refused.exception)
        self.assertIn(FROZEN, message)
        self.assertIn(KIND, message)


class ThisRuleGuardsItsOwnColumnAndNoOthersTest(TestCase):
    """The scoping half — and on a `FROZEN` column it is the ONLY control.

    The three `RESOLVE_ONCE` modules open with an admitted move, because a
    trigger that refused every write would satisfy all their refusals. This
    column admits no move, so there is no such case to write, and what catches
    the same failure instead is the set of writes this rule must leave alone: a
    column it says nothing about, and each neighbouring rule's own permitted
    move. A badly-scoped `WHEN` clause would fire this rule on a supplier
    settlement and refuse it, and nothing in slice 3's module would notice.
    """

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        posting = _metered()
        through_the_queryset(posting, balance_after_micros=17)
        posting.refresh_from_db()
        self.assertEqual(posting.balance_after_micros, 17)

    def test_the_supplier_side_still_settles_beside_it(self):
        """A settlement is the write most likely to trip a badly-scoped `WHEN`
        clause, so the cost side's one admitted move is exercised against the
        table as it stands after this ticket."""
        from core.vocabulary import (
            COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED,
            UNRESOLVED_REASON_COST_RATE_MISSING,
        )

        posting = _metered(**{"provider_cost_micros": None,
                              "costing_status": COSTING_STATUS_UNRESOLVED,
                              "unresolved_reason":
                                  UNRESOLVED_REASON_COST_RATE_MISSING})
        through_the_queryset(
            posting, provider_cost_micros=7,
            costing_status=COSTING_STATUS_KNOWN, unresolved_reason=None)
        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 7)

    def test_a_write_that_restates_the_same_kind_is_not_refused(self):
        """⚠ `IS DISTINCT FROM` IS WHAT MAKES THIS TRUE, AND IT IS LOAD-BEARING.

        A `bulk_update` or a `save()` over a full column list re-sends every
        column including this one. A rule keyed on the column APPEARING in the
        statement rather than on its value CHANGING would refuse every such
        write on this table, which is most of what writes here. The `WHEN`
        clause asks whether the value moved.
        """
        posting = _metered()
        through_the_queryset(posting,
                             **{KIND: USAGE_EVENT_KIND_METERED_USAGE,
                                "balance_after_micros": 9})
        posting.refresh_from_db()
        self.assertEqual(posting.balance_after_micros, 9)
        self.assertEqual(posting.kind, USAGE_EVENT_KIND_METERED_USAGE)


class TheClosedSetIsHeldAtTheDatabaseTest(TestCase):
    """`ck_posting_kind`, proved on `INSERT` — the statement the trigger does
    not see.

    A closed concept that only `clean()` defends is open to everything that
    writes without validating, and most of what writes here does. The four
    value-set checks already on this table make the same argument; this is the
    fifth, and it is proved the same way they are.
    """

    def test_a_kind_nobody_declared_is_refused(self):
        with self.assertRaises(IntegrityError) as refused:
            with transaction.atomic():
                committed_posting(**{KIND: "invented"})
        self.assertIn(CHECK, str(refused.exception))

    def test_every_declared_value_is_admitted(self):
        """The control, and it is what keeps the check from being satisfiable
        by a rule that refused the whole column."""
        for value in sorted(USAGE_EVENT_KIND_VALUES):
            with self.subTest(kind=value):
                posting = committed_posting(**{KIND: value})
                posting.refresh_from_db()
                self.assertEqual(posting.kind, value)


class TheRuleIsHeldByAFourthTriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is not evidence that a rule is installed — it is
    evidence that a file executed. What matters is what `pg_trigger` holds now,
    on the table the model actually uses.
    """

    def _trigger_row(self):
        return rule_on_the_table(TRIGGER)

    def test_the_posting_table_carries_exactly_the_four_declared_rules(self):
        """One rule per declared subject, and the set says which.

        The set is spelled out here rather than imported from a shared
        constant, for the reason the three modules beside this one each spell
        their own: an assertion every module took from one place could be
        satisfied by editing that place, and what this line is for is making a
        rule's arrival on this table something a reader of THIS module has to
        agree to.
        """
        self.assertEqual(
            rules_on_the_table(),
            {TRIGGER, "trg_posting_declared_transitions",
             "trg_posting_price_transitions", "trg_posting_receipt_sealing"})

    def test_it_fires_before_each_updated_row_and_on_nothing_else(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        The INSERT bit being OFF is the load-bearing half here, not a formality:
        this migration's whole cost argument is that the hottest insert path in
        the system never enters this function, and `docs/conventions/
        django-patterns.md` requires a new rule to assert its statement mask
        rather than describe it.
        """
        tgtype, _ = self._trigger_row()
        self.assertTrue(tgtype & (1 << 0), "not FOR EACH ROW")
        self.assertTrue(tgtype & (1 << 1), "not BEFORE")
        self.assertTrue(tgtype & (1 << 4), "does not fire on UPDATE")
        self.assertFalse(tgtype & (1 << 2), "fires on INSERT")
        self.assertFalse(tgtype & (1 << 3), "fires on DELETE")

    def test_the_rule_names_the_values_the_registry_declares(self):
        """The migration froze two literals; this is what keeps them honest.

        A migration records the schema as it was on the day it ran, so it may
        not import living constants — and the copy that leaves behind goes
        stale in silence. Reading the installed function's source out of
        `pg_proc` and comparing it against the registry is what turns a rename
        in `domain-vocabulary/` red here rather than leaving a message naming a
        value nothing can hold.
        """
        _, source = self._trigger_row()
        body = re.sub(r"--[^\n]*", "", source)
        for value in USAGE_EVENT_KIND_VALUES:
            self.assertIn(value, body)


#: A rule that NAMES this column and refuses nothing — what G19's declaration
#: check cannot tell apart from the shipped one. Postgres runs
#: `CREATE OR REPLACE FUNCTION` inside the transaction a `TestCase` rolls back,
#: so the shipped rule is restored when the case ends and nothing else ever
#: sees this one.
TOOTHLESS = f"""
CREATE OR REPLACE FUNCTION {FUNCTION}() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    -- kind is named here, and nothing at all is refused.
    RETURN NEW;
END;
$$;
"""


class AGreenDeclarationCheckDoesNotProveThisRuleHoldsTest(TestCase):
    """Why this module exists, as a test rather than as a paragraph.

    G19's declaration check walks the declarations and asks the database
    whether each declared column is NAMED by a rule on its table. That is a
    genuinely good edge — it judges a new declaration on the day it is made —
    and it is not a statement about behaviour. This class measures the
    difference on a database where the first is true and the second is false.
    """

    def _install_the_toothless_rule(self):
        with connection.cursor() as cursor:
            cursor.execute(TOOTHLESS)

    def test_the_column_is_declared_into_a_class_the_database_must_defend(self):
        """The premise, established rather than assumed.

        Without this the cases below could pass on a tree where nothing was
        declared at all — a clean board over an empty walk, which is the
        vacuity the gate's own guard exists to catch.
        """
        declared = dict(
            (column, transition_class)
            for _, column, transition_class
            in columns_declared_into_defended_classes([Posting]))
        self.assertEqual(declared[KIND], FROZEN)

    def _the_declaration_check_over_the_whole_tree(self):
        """G19's check exactly as the gate runs it — every declarer, not this
        one. `apps.get_models()` rather than `[Posting]`: a gate asked about one
        model is not the gate."""
        return columns_the_database_does_not_defend(
            columns_declared_into_defended_classes(apps.get_models()),
            declaring_models_by_table())

    def test_the_shipped_rule_passes_the_declaration_check_and_holds(self):
        """Both halves true at once, which is the state to compare against."""
        self.assertEqual(self._the_declaration_check_over_the_whole_tree(), [])
        for name, door in DOORS:
            with self.subTest(door=name):
                with self.assertRaises(IntegrityError):
                    with transaction.atomic():
                        door(_metered(),
                             **{KIND: USAGE_EVENT_KIND_TASK_CHARGE})

    def test_a_rule_that_refuses_nothing_still_passes_the_declaration_check(
            self):
        """⚠ The sentence this module exists for, measured."""
        self._install_the_toothless_rule()
        self.assertEqual(self._the_declaration_check_over_the_whole_tree(), [])

    def test_and_the_refusals_above_go_red_against_that_same_rule(self):
        """The other half — the refusals stop refusing, through every door."""
        self._install_the_toothless_rule()
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _metered()
                door(posting, **{KIND: USAGE_EVENT_KIND_TASK_CHARGE})
                posting.refresh_from_db()
                self.assertEqual(posting.kind, USAGE_EVENT_KIND_TASK_CHARGE)
