"""A cost settles once, and the table refuses every other move (#318).

#317 made `provider_cost_micros` nullable so that *not resolved* became sayable,
and put the three legal combinations of amount, status and reason into a `CHECK`.
A `CHECK` sees one row at a time. It cannot see the row that was there a moment
ago, so it cannot tell **completing a blank** from **changing an answer** — and
that difference is the whole of ADR-0007 §2's `RESOLVE_ONCE`:

    resolution completes previously unknown information; correction changes a
    value that was already asserted. Completing a blank is permitted once.
    Replacing a known value is prohibited.

The `OLD → NEW` rules are therefore carried by a **database trigger**, and this
module is what says so. Two declarations are under test, both made on the model
in `transition_classes`:

* `provider_cost_micros` + `costing_status` — `RESOLVE_ONCE`, **as a pair**. The
  one permitted move is `unresolved` → `known`, which sets the amount, clears
  the reason and moves the status in a single statement. Nothing else.
* `claimed_provider_cost_micros` — `FROZEN`. A claim is a record of what the
  caller said at the time; editing it rewrites what was said.

**Why not a model-level `save()` guard.** ADR-0007 §2 answers this, and it names
this repository: *"a model-level guard alone is not enforcement; the repository
has already shipped one that a production writer bypassed by design."* `Posting`
carries such a guard — `save()` refuses every update — and
`TheModelGuardIsNotTheEnforcementTest` below reaches around it in the same way a
bulk writer, a data migration or a management command would, and finds the
database still holding the line.

**Which mechanism refuses which statement, asserted rather than assumed.** Some
prohibited moves are also impossible under #317's combination `CHECK` — an
amount arriving without its status is one — and a test that only asserted "this
was refused" could not tell the two apart, which is how a live constraint and a
dead one come to look identical. Every refusal below therefore asserts **the
message Postgres answers with**: the trigger names the transition class it is
holding, and a `CHECK` names its own constraint.

⚠ **AND SINCE #352 THE CLASS ALONE IS NOT ENOUGH.** The table carries a second
rule over the customer price pair, declared `RESOLVE_ONCE` exactly as this one
is — so both triggers' messages carry that token, and a refusal asserting only
the class would be satisfied by the wrong rule refusing the write. Each class
below states the COLUMN its refusals must name in `REFUSAL_NAMES`, and
`_helpers.TransitionRefusalMixin` will not run without one.

That distinction turned out sharper than expected, and it is worth knowing
before reading further: **a `BEFORE` trigger runs before the table's constraints
are evaluated**, so on an `UPDATE` the trigger answers first and the combination
`CHECK` is never consulted. The `CHECK` is therefore proved on `INSERT`, which
this trigger does not fire on — below in
`test_a_half_settled_row_cannot_be_inserted_in_the_first_place`, and in the
class #317 wrote, which moved to `INSERT` for this reason when this ticket
landed.

**Mutation-checked before it was believed.** Dropping the trigger turns every
case in this module red bar the `INSERT` one and the permitted-move control;
dropping the combination `CHECK` turns the `INSERT` one red and leaves the rest
green. Two mechanisms, two failure sets, neither carrying the other.
"""
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import (
    DOORS, TransitionRefusalMixin, committed_posting, rule_on_the_table,
    rules_on_the_table, through_raw_sql, through_save, through_the_queryset)
from core.transitions import FROZEN, RESOLVE_ONCE
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED,
)

COST = "provider_cost_micros"
STATUS = "costing_status"
REASON = "unresolved_reason"
CLAIMED = "claimed_provider_cost_micros"

TABLE = Posting._meta.db_table

#: This rule, addressed BY NAME. The table carries a second one since #352 —
#: the price pair's, over disjoint columns — and `pg_trigger` promises no order,
#: so every question below asks for this one rather than for "the trigger".
TRIGGER = "trg_posting_declared_transitions"


_posting = committed_posting


def _unresolved(**columns):
    return _posting(**{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
                       REASON: UNRESOLVED_REASON_COST_RATE_MISSING, **columns})


def _settled(amount=100, **columns):
    return _posting(**{COST: amount, STATUS: COSTING_STATUS_KNOWN, **columns})


def _not_applicable(**columns):
    return _posting(**{COST: None, STATUS: COSTING_STATUS_NOT_APPLICABLE,
                       **columns})


_through_the_queryset = through_the_queryset
_through_raw_sql = through_raw_sql
_through_save = through_save


class TheOnePermittedMoveIsAdmittedTest(TransitionRefusalMixin, TestCase):
    """The control, and the class is worthless without it.

    Every other assertion here is "this statement was refused", which a trigger
    that refused *everything* would satisfy completely — and a table that
    accepted no settlement at all would be a worse defect than the one this
    ticket fixes. So the permitted move is driven through the same three doors
    first.
    """

    SETTLEMENT = {COST: 4_200, STATUS: COSTING_STATUS_KNOWN, REASON: None}

    def test_an_unresolved_cost_settles_through_every_door(self):
        for name, door in DOORS:
            with self.subTest(door=name):
                posting = _unresolved()
                door(posting, **self.SETTLEMENT)
                posting.refresh_from_db()
                self.assertEqual(
                    (getattr(posting, COST), getattr(posting, STATUS),
                     getattr(posting, REASON)),
                    (4_200, COSTING_STATUS_KNOWN, None))

    def test_a_settlement_of_exactly_zero_is_admitted(self):
        """Zero is a resolved amount, not a missing one.

        The distinction #317's column exists to hold: a call that genuinely cost
        nothing settles at `0` and is `known`, and it must not be turned away by
        a rule written as if a settlement always carries a positive number.
        """
        posting = _unresolved()
        _through_the_queryset(posting, **{**self.SETTLEMENT, COST: 0})
        posting.refresh_from_db()
        self.assertEqual(getattr(posting, COST), 0)

    def test_a_column_the_rule_says_nothing_about_still_writes(self):
        """The trigger guards four columns, not the table.

        A posting's balance and attribution columns are written by paths that
        have nothing to do with costing, and a rule that quietly froze the whole
        row would break them somewhere far from here.
        """
        posting = _settled()
        _through_the_queryset(posting, balance_after_micros=17)
        posting.refresh_from_db()
        self.assertEqual(posting.balance_after_micros, 17)


class TheSettledAmountIsNotEditableTest(TransitionRefusalMixin, TestCase):
    """Replacing a known value is a correction, and corrections are prohibited.

    ADR-0007 §2: a correction *"must be a separate record beside the original"*.
    A `CHECK` cannot see this — `known` with an amount is legal on both sides of
    the write — so every case in this class is the trigger's alone.
    """

    REFUSAL_NAMES = COST

    def test_a_settled_amount_cannot_be_overwritten(self):
        self._refused_by_the_trigger(_settled, RESOLVE_ONCE, **{COST: 999})

    def test_a_settled_cost_cannot_be_unsettled(self):
        """The status cannot move backwards, even into a legal combination."""
        self._refused_by_the_trigger(
            _settled, RESOLVE_ONCE,
            **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
               REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_a_settled_posting_cannot_become_not_applicable(self):
        self._refused_by_the_trigger(
            _settled, RESOLVE_ONCE,
            **{COST: None, STATUS: COSTING_STATUS_NOT_APPLICABLE, REASON: None})


class OnlyAnUnresolvedCostSettlesTest(TransitionRefusalMixin, TestCase):
    """`not_applicable` is a terminal answer, not a waiting room.

    An Event Type that declares no cost produces a posting that will never have
    one. Settling it would invent a supplier charge for work no supplier billed
    for, and every combination involved is legal to the `CHECK` on both sides.
    """

    REFUSAL_NAMES = COST

    def test_a_not_applicable_posting_cannot_be_settled(self):
        self._refused_by_the_trigger(
            _not_applicable, RESOLVE_ONCE,
            **{COST: 100, STATUS: COSTING_STATUS_KNOWN})

    def test_an_unresolved_posting_cannot_be_written_off_as_not_applicable(self):
        """The other way out of `unresolved`, and it is closed too.

        A cost nobody could resolve is not the same fact as a cost that was
        never going to exist, and letting the first become the second would make
        an unresolved total shrink by relabelling rather than by settling.
        """
        self._refused_by_the_trigger(
            _unresolved, RESOLVE_ONCE,
            **{STATUS: COSTING_STATUS_NOT_APPLICABLE, REASON: None})

    def test_the_reason_cannot_be_re_diagnosed_in_place(self):
        """The reason moves only as part of the settlement that clears it.

        Re-labelling why a cost is missing, without settling it, rewrites what
        the system said was wrong at the time — and it does it on a row a tenant
        may already have been shown.
        """
        self._refused_by_the_trigger(
            _unresolved, RESOLVE_ONCE,
            **{REASON: UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED})


class TheAmountAndTheStatusNeverSeparateTest(TransitionRefusalMixin, TestCase):
    """Half a settlement is refused, and the two statements fail differently.

    A settlement is one statement moving amount, status and reason together.

    **On an `UPDATE` the trigger answers first, and it answers alone.** A
    `BEFORE` trigger runs before the table's constraints are evaluated, so a
    half-settlement never reaches the combination `CHECK` at all — this was
    measured, not assumed: written the other way round, this class failed with
    the trigger's message in its hands. That ordering is why #317's own
    combination cases moved to `INSERT` when this ticket landed: on `UPDATE`
    they had stopped being evidence about the `CHECK`.

    **On an `INSERT` the trigger is silent by construction** — it fires on
    `UPDATE` only, because an inserted row has no previous state to compare
    against — and the `CHECK` is the whole of the defence. The last case here is
    the one statement in this module that the trigger does not touch.
    """

    REFUSAL_NAMES = COST
    COMBINATION = "ck_posting_costing_status_agrees_with_the_cost"

    def test_a_settlement_that_moves_the_amount_alone_is_refused(self):
        self._refused_by_the_trigger(_unresolved, RESOLVE_ONCE, **{COST: 50})

    def test_a_settlement_that_moves_the_status_alone_is_refused(self):
        self._refused_by_the_trigger(
            _unresolved, RESOLVE_ONCE,
            **{STATUS: COSTING_STATUS_KNOWN, REASON: None})

    def test_a_settlement_that_leaves_the_reason_behind_is_refused(self):
        self._refused_by_the_trigger(
            _unresolved, RESOLVE_ONCE,
            **{COST: 50, STATUS: COSTING_STATUS_KNOWN})

    def test_the_amount_alone_cannot_move_on_a_settled_row(self):
        """The same rule from the other side, where the `CHECK` is content."""
        self._refused_by_the_trigger(_settled, RESOLVE_ONCE, **{COST: 51})

    def test_a_half_settled_row_cannot_be_inserted_in_the_first_place(self):
        """The `CHECK`'s half, on the statement the trigger does not see.

        Without this case the trigger could be doing all of the work here and
        the class would not notice — which is exactly what had happened to
        #317's cases by the time this one was written.
        """
        try:
            with transaction.atomic():
                _posting(**{COST: 50, STATUS: COSTING_STATUS_UNRESOLVED,
                            REASON: UNRESOLVED_REASON_COST_RATE_MISSING})
        except IntegrityError as refusal:
            self.assertIn(self.COMBINATION, str(refusal))
        else:
            self.fail("the row was admitted")


class TheClaimedCostIsFrozenTest(TransitionRefusalMixin, TestCase):
    """What the caller said is a record of what was said.

    It is never COGS and is never summed into one. Its value is evidence about a
    moment, so it does not acquire a value after insert and does not change one.
    """

    REFUSAL_NAMES = CLAIMED

    def test_a_claimed_cost_cannot_be_edited(self):
        self._refused_by_the_trigger(
            lambda: _settled(**{CLAIMED: 7}), FROZEN, **{CLAIMED: 8})

    def test_a_claimed_cost_cannot_be_added_after_the_fact(self):
        """`FROZEN` is *none after insert*, and that includes filling a blank.

        `RESOLVE_ONCE` is the class for a column that legitimately arrives late;
        this one is not it. A claim supplied after the call is not the caller's
        belief at the time, and treating it as one would let a later opinion be
        read as contemporaneous evidence.
        """
        self._refused_by_the_trigger(_settled, FROZEN, **{CLAIMED: 9})

    def test_a_claimed_cost_cannot_be_cleared(self):
        self._refused_by_the_trigger(
            lambda: _settled(**{CLAIMED: 7}), FROZEN, **{CLAIMED: None})


class TheModelGuardIsNotTheEnforcementTest(TestCase):
    """ADR-0007 §2's named failure, tested rather than trusted.

    `Posting.save()` refuses every update. That refusal is a convenience for the
    ordinary recording path and it is **not** what holds `RESOLVE_ONCE`: it is
    written in Python, so it protects exactly the writers that go through it.
    The settlement door does not, and neither does a bulk writer, a data
    migration or a shell session.
    """

    def test_the_model_still_refuses_an_update_through_its_own_door(self):
        posting = _settled()
        setattr(posting, COST, 5)
        with self.assertRaises(ValueError):
            posting.save()

    def test_reaching_around_that_guard_lands_on_the_database(self):
        posting = _settled()
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                _through_save(posting, **{COST: 5})
        self.assertIn(RESOLVE_ONCE, str(refusal.exception))

    def test_the_guard_being_absent_would_change_nothing(self):
        """The same write, through the door the guard does not cover at all.

        `QuerySet.update()` never calls `save()`. If the model guard were the
        enforcement, this statement would land — which is the whole argument for
        putting the rule in the table.
        """
        posting = _settled()
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(posting, **{COST: 5})


class TheRuleIsHeldByATriggerOnThisTableTest(TestCase):
    """The mechanism, read off the live database rather than off the migration.

    A migration that ran is not evidence that a rule is installed — it is
    evidence that a file executed. What matters is what `pg_trigger` holds now,
    on the table the model actually uses.

    **⚠ THIS CLASS ASKED FOR "THE TRIGGER" UNTIL #352, AND THERE ARE THREE.**
    It counted the table's rules and then indexed the first row returned, which
    was correct exactly while one existed: `pg_trigger` promises no order, so
    the day slice 4 installed the price pair's rule beside this one, "the first
    row" became whichever one Postgres happened to hand back. Both questions are
    now asked **by name**, and the count is an exact set — which is what made
    the receipt's rule arriving in #353 a decision somebody makes here rather
    than a number that still looks right.
    """

    def _trigger_row(self):
        """This rule's row, by name. Never "the table's trigger"."""
        return rule_on_the_table(TRIGGER)

    def _triggers_on_the_table(self):
        return rules_on_the_table()

    def test_the_posting_table_carries_exactly_the_three_declared_rules(self):
        """One rule per declared subject, and the set says which.

        The price pair's rule is a SECOND trigger rather than a second branch
        inside this one, and the receipt's is a THIRD; all three are
        deliberately the same mechanism. They govern disjoint columns, each
        `WHEN` clause names only its own, and dropping any one leaves the others
        standing. What would have been wrong is a second *kind* of mechanism —
        a `CHECK` or a `RULE` holding one subject while a trigger holds another.

        The set is spelled out here rather than imported from a shared constant,
        for the reason the declaration set is: an assertion every module took
        from one place could be satisfied by editing that place, and what this
        line is for is making a rule's arrival on this table something a reader
        of THIS module has to agree to.
        """
        self.assertEqual(self._triggers_on_the_table(),
                         {TRIGGER, "trg_posting_price_transitions",
                          "trg_posting_receipt_sealing"})

    def test_it_fires_before_each_updated_row(self):
        """`BEFORE UPDATE ... FOR EACH ROW`, read out of `tgtype`'s bits.

        Row-level and before the write: an `AFTER` trigger would refuse by
        rolling back work already done, and a statement-level one cannot see the
        old row at all, which is the only thing this rule is about.
        """
        tgtype, _ = self._trigger_row()
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

        `apps` is passed as `None` deliberately: neither half consults the
        historical model state, because a trigger is not model state — which is
        the same fact that keeps `makemigrations --check` quiet about it.

        **The other two rules are asserted still standing while this one is
        out**, because a reverse that dropped a neighbour too would otherwise
        show up as an unrelated failure in another module.
        """
        migration = MigrationLoader(connection).get_migration(
            "usage", "0037_a_cost_settles_once_and_the_table_holds_it")
        run_python = next(op for op in migration.operations
                          if isinstance(op, migrations.RunPython))
        settled = _settled()

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.assertIsNone(self._trigger_row())
        self.assertEqual(self._triggers_on_the_table(),
                         {"trg_posting_price_transitions",
                          "trg_posting_receipt_sealing"})
        _through_the_queryset(settled, **{COST: 999})
        settled.refresh_from_db()
        self.assertEqual(getattr(settled, COST), 999)

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        self.assertIsNotNone(self._trigger_row())
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _through_the_queryset(settled, **{COST: 1_000})

    def test_the_rule_names_the_status_values_the_registry_declares(self):
        """The one place a token is spelled outside `domain-vocabulary/`.

        A trigger body is frozen SQL living in the database, so it cannot import
        `core.vocabulary` the way the model does. If a value is ever renamed in
        the registry, the constants below move and this assertion goes red,
        which is what forces the migration that would otherwise be forgotten —
        leaving a rule that quietly matched nothing.
        """
        _, source = self._trigger_row()
        self.assertIn(f"'{COSTING_STATUS_UNRESOLVED}'", source)
        self.assertIn(f"'{COSTING_STATUS_KNOWN}'", source)
