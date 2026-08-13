"""A supplier cost UBB has not learned yet stops being recorded as zero (#317).

The posting's supplier-cost column was `BigIntegerField(default=0)`, and there
was **no value in it meaning "not resolved"**. A supplier charge UBB had not
learned about was therefore stored as the same number as a call that genuinely
cost nothing, and every total built on the column was wrong in the direction
that looks healthy — margin better than it is, spend lower than it is.

Four columns settle it, and the whole of what this module proves is that the
difference is held **at the database** rather than by whoever remembers to look:

* the supplier cost becomes nullable, `NULL` meaning *not resolved*. Zero keeps
  its own meaning — *resolved, and it was exactly nothing*.
* `costing_status` — `known` · `unresolved` · `not_applicable`
* `unresolved_reason`, nullable, naming which input did not arrive
* `claimed_provider_cost_micros`, nullable — what the caller believes the call
  cost, which is never COGS

**Both value sets are held by reference**, imported from `core.vocabulary`,
which is what paid this file's backend entry in the migration ledger — deleted
in the same commit, because an entry cannot outlive the debt it records, and an
id quoted here would have been dangling the moment it was written.
A `choices=` built from the
imported frozensets is derived rather than restated: it cannot drift from the
registry, and the labels are the tokens themselves because the wording lives in
the console's locale catalogue (ADR-0008 §4) and a second copy of it here would
be the thing the registry exists to prevent. The line is still counted by
`tests/contracts/test_undeclared_value_sets.py`, which counts the SHAPE — a
derived list and a typed one look identical to a reader skimming a diff, so
both come past one.

**Why the illegal combinations skip model validation.** A `full_clean` that
refuses them proves something about Django, not about the table, and this
repository has already shipped a model-level guard that a production writer
bypassed by design. Each of the six illegal combinations and each of the two
out-of-set values is therefore written straight at Postgres, with nothing
between the statement and the table but the ORM's own SQL.

⚠ **They are driven as an `INSERT`, and #318 is why.** This class originally
drove each one as a raw `UPDATE` against a committed row — an `UPDATE` because a
hand-written `INSERT` would have had to name every NOT NULL column and would
then have been testing that list. #318 installed a `BEFORE UPDATE` trigger
holding this pair to `RESOLVE_ONCE`, and **a `BEFORE` trigger runs before the
table's constraints are evaluated**: every statement in this class started
failing with the trigger's message instead, so the class went on passing while
proving nothing whatever about the `CHECK`. It would have stayed green with the
constraint dropped. The statement moved to an `INSERT`, which the trigger does
not fire on, and the ORM names the columns so the objection to a hand-written
one never arises. The `UPDATE` half of the story is now
`test_a_cost_settles_once.py`, where it belongs.

**The transition classes are declared here now, and #318 is why.** This module
originally asserted the opposite — that no column of this model was declared
into a class the database defends — because a declaration ahead of its
enforcement is a promise nothing keeps, which
`apps/platform/tests/test_transition_class_declarations.py` exists to catch.
#318 landed the enforcement, so that assertion is **replaced by its inverse**
rather than deleted or loosened: the pair is declared, the claim is declared,
and the walk in that same file holds every declaration in the tree to being
defended at the database.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import (
    FROZEN, RESOLVE_ONCE, columns_declared_into_defended_classes)
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    COSTING_STATUS_VALUES,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_VALUES,
)

COST = "provider_cost_micros"
STATUS = "costing_status"
REASON = "unresolved_reason"
CLAIMED = "claimed_provider_cost_micros"


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _posting_for_a_new_customer(**kwargs):
    tenant, customer = _tenant_and_customer()
    return Posting.objects.create(tenant=tenant, customer=customer, **kwargs)


class TheColumnsAreShapedAsRuledTest(TestCase):
    """The four shapes, read off the model rather than off the migration."""

    def _field(self, name):
        return Posting._meta.get_field(name)

    def test_the_supplier_cost_is_nullable(self):
        assert self._field(COST).null

    def test_the_status_is_not_nullable(self):
        """`unresolved` is a status, not the absence of one.

        A nullable status column would be a fourth state meaning "nobody said",
        which is the ambiguity this ticket exists to remove rather than to move
        one column to the left.
        """
        assert not self._field(STATUS).null

    def test_the_reason_and_the_claimed_cost_are_nullable(self):
        assert self._field(REASON).null
        assert self._field(CLAIMED).null

    def test_the_claimed_cost_is_a_separate_column_in_the_table(self):
        """What the caller believes is never what the supplier charged.

        Two columns rather than one routed by a declaration: a field whose
        meaning flips with an Event Type's costing declaration is retroactive —
        change the declaration and every historical row changes meaning.

        Read off the TABLE rather than off the model, because the model cannot
        answer this: `_meta.get_field("x").name` is `"x"` by construction, so
        comparing two of them is a statement about the two strings this module
        typed and can never fail. What has an oracle is whether Postgres is
        holding two distinct columns, which is what a single field serving both
        meanings would break.
        """
        with connection.cursor() as cursor:
            columns = {column.name for column in
                       connection.introspection.get_table_description(
                           cursor, Posting._meta.db_table)}
        assert {COST, CLAIMED} <= columns
        assert len({COST, CLAIMED} & columns) == 2


class TheValueSetsAreHeldByReferenceTest(TestCase):
    """Imported from `core.vocabulary`, not restated here.

    The check is that the model's own `choices` agree with the registry's
    frozensets exactly. A hand-written list would pass on the day it was typed
    and drift on the day the registry moved, which is the whole of what the
    ledger entry against this file recorded before #317 paid and deleted it.
    """

    def test_the_status_choices_are_the_registry_value_set(self):
        declared = {value for value, _ in Posting._meta.get_field(STATUS).choices}
        assert declared == set(COSTING_STATUS_VALUES)

    def test_the_reason_choices_are_the_registry_value_set(self):
        declared = {value for value, _ in Posting._meta.get_field(REASON).choices}
        assert declared == set(UNRESOLVED_REASON_VALUES)

    def test_the_labels_are_the_tokens_themselves(self):
        """Wording is the console's, and this model does not author a second set.

        ADR-0008 §4 puts every human-facing label in the locale catalogue, keyed
        off the concept's `label_key_prefix`. A Django `choices` label is not a
        translation hook, so inventing English here would be a wording nobody
        can reach and one more thing to keep in step.
        """
        for field in (STATUS, REASON):
            for value, label in Posting._meta.get_field(field).choices:
                assert value == label, field


class NullAndZeroAreDistinguishableAtTheDatabaseTest(TestCase):
    """The load-bearing sentence of ADR-0007 §2, asserted as SQL.

    Two rows: one that cost nothing and one nobody has costed. The assertions
    are made with `IS NULL` and `= 0` through a cursor, because a Python read
    of two ORM attributes would be satisfied by a column that coalesced on the
    way out.
    """

    def setUp(self):
        self.free = _posting_for_a_new_customer(
            idempotency_key="free",
            **{COST: 0, STATUS: COSTING_STATUS_KNOWN})
        self.unknown = _posting_for_a_new_customer(
            idempotency_key="unknown",
            **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
               REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def _count(self, predicate):
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM {Posting._meta.db_table} "
                f"WHERE {COST} {predicate}")
            return cursor.fetchone()[0]

    def test_exactly_one_row_holds_a_resolved_zero(self):
        assert self._count("= 0") == 1

    def test_exactly_one_row_holds_no_resolved_cost_at_all(self):
        assert self._count("IS NULL") == 1

    def test_the_two_rows_are_not_the_same_row(self):
        """The vacuity guard on the pair above.

        Both counts would read 1 against a single row if either predicate were
        misspelled into something that matched everything.
        """
        assert self.free.pk != self.unknown.pk
        assert self._count("IS NOT NULL") == 1

    def test_a_sum_over_the_column_skips_the_unresolved_row(self):
        """Recorded rather than repaired here, because it is the next problem.

        SQL's `SUM` ignores NULL, so a bare aggregate now answers "0" over these
        two rows and looks exactly like a complete total. Every such aggregate
        becoming a pair — the resolved sum and its completeness — is the
        null-safety sweep's subject, and this assertion is where a reader meets
        the reason for it.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT sum({COST}), count(*), count({COST}) "
                f"FROM {Posting._meta.db_table}")
            total, rows, costed = cursor.fetchone()
        assert (total, rows, costed) == (0, 2, 1)


class TheThreeLegalCombinationsAreAdmittedTest(TestCase):
    """Each combination the rule permits, inserted through the ORM."""

    def test_known_carries_an_amount_and_no_reason(self):
        posting = _posting_for_a_new_customer(idempotency_key="k",
                           **{COST: 4_200, STATUS: COSTING_STATUS_KNOWN})
        assert (getattr(posting, COST), getattr(posting, REASON)) == (4_200, None)

    def test_known_admits_a_resolved_zero(self):
        """The meaning zero keeps, stated as its own case.

        `known` with `0` is not a degenerate row to be tolerated — it is the
        answer for a call that genuinely cost nothing, and it is the reading the
        migration gives every row that already existed.
        """
        posting = _posting_for_a_new_customer(idempotency_key="k0",
                           **{COST: 0, STATUS: COSTING_STATUS_KNOWN})
        assert getattr(posting, COST) == 0

    def test_unresolved_carries_a_reason_and_no_amount(self):
        posting = _posting_for_a_new_customer(
            idempotency_key="u",
            **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
               REASON: UNRESOLVED_REASON_COST_RATE_MISSING})
        assert getattr(posting, COST) is None

    def test_not_applicable_carries_neither(self):
        posting = _posting_for_a_new_customer(idempotency_key="n",
                           **{COST: None, STATUS: COSTING_STATUS_NOT_APPLICABLE})
        assert getattr(posting, REASON) is None

    def test_a_claimed_cost_rides_beside_any_of_them(self):
        """The caller's belief is not constrained by the rule above.

        It is not COGS and never becomes it, so an `unresolved` supplier cost
        and a claimed figure are not a contradiction — they are the ordinary
        state of a call whose supplier has not billed yet.
        """
        posting = _posting_for_a_new_customer(
            idempotency_key="c",
            **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
               REASON: UNRESOLVED_REASON_COST_RATE_MISSING,
               CLAIMED: 9_999})
        assert getattr(posting, CLAIMED) == 9_999


class EveryIllegalCombinationIsRefusedByTheDatabaseTest(TestCase):
    """The eight rows Postgres must refuse, each one an `INSERT`.

    Six combinations outside the three legal ones, plus a status and a reason
    that name nothing the registry declares. None of them travels through model
    validation, which is the point: the guarantee is a property of the table.

    **Each case names the constraint it expects to be refused by**, because
    since #318 this table has two mechanisms on it and "something refused this"
    stopped being evidence about either. See the module docstring for why the
    statement is an `INSERT`.
    """

    COMBINATION = "ck_posting_costing_status_agrees_with_the_cost"
    STATUS_VALUES = "ck_posting_costing_status"
    REASON_VALUES = "ck_posting_unresolved_reason"

    def _refused(self, constraint, **columns):
        try:
            with transaction.atomic():
                _posting_for_a_new_customer(idempotency_key="subject", **columns)
        except IntegrityError as refusal:
            assert constraint in str(refusal), str(refusal)
        else:
            self.fail("the row was admitted")

    def test_the_orm_can_insert_a_legal_combination(self):
        """The control, and it is not optional.

        Every assertion below is "this statement failed". Without one statement
        of the same shape that SUCCEEDS, a fixture that could not write at all
        would satisfy the whole class.
        """
        posting = _posting_for_a_new_customer(
            idempotency_key="subject", **{COST: 7, STATUS: COSTING_STATUS_KNOWN})
        assert getattr(posting, COST) == 7

    def test_known_without_an_amount_is_refused(self):
        self._refused(self.COMBINATION,
                      **{COST: None, STATUS: COSTING_STATUS_KNOWN, REASON: None})

    def test_known_with_a_reason_is_refused(self):
        self._refused(self.COMBINATION,
                      **{COST: 1, STATUS: COSTING_STATUS_KNOWN,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_unresolved_with_an_amount_is_refused(self):
        self._refused(self.COMBINATION,
                      **{COST: 1, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_unresolved_without_a_reason_is_refused(self):
        """The half that keeps the status honest.

        A status saying a cost is missing without saying what would settle it is
        a shrug rather than something a tenant can act on.
        """
        self._refused(self.COMBINATION,
                      **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: None})

    def test_not_applicable_with_an_amount_is_refused(self):
        self._refused(self.COMBINATION,
                      **{COST: 0, STATUS: COSTING_STATUS_NOT_APPLICABLE,
                         REASON: None})

    def test_not_applicable_with_a_reason_is_refused(self):
        self._refused(self.COMBINATION,
                      **{COST: None, STATUS: COSTING_STATUS_NOT_APPLICABLE,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_a_reason_outside_the_declared_set_is_refused(self):
        """Isolated on purpose: the rest of this row is legal.

        `unresolved` with no amount and a reason present satisfies the
        combination check completely, so the only thing left to refuse it is the
        reason's own value set — which is what makes this case evidence about
        that constraint rather than about the disjunction beside it.
        """
        self._refused(self.REASON_VALUES,
                      **{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: "supplier_was_asleep"})

    def test_a_status_outside_the_declared_set_is_refused(self):
        """The one case that cannot be isolated, and it says so.

        A status nobody declared fails the combination check as well, because
        that check enumerates the three legal statuses by name — there is no row
        carrying an undeclared status that the disjunction would tolerate. Which
        of the two constraints Postgres reports is its own business, so this
        asserts only the refusal; what proves the value set is defended in its
        own right is the structural assertion below.
        """
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _posting_for_a_new_customer(
                    idempotency_key="subject",
                    **{COST: 1, STATUS: "settled", REASON: None})

    def test_the_status_value_set_is_a_constraint_of_its_own(self):
        """Read out of `pg_constraint`, because the row above cannot show it.

        Without this, dropping `ck_posting_costing_status` would leave every
        test in this class green: the combination check would absorb the only
        statement that names it.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_get_constraintdef(c.oid) FROM pg_constraint c "
                "JOIN pg_class t ON t.oid = c.conrelid "
                "WHERE t.relname = %s AND c.conname = %s",
                [Posting._meta.db_table, self.STATUS_VALUES])
            definition = cursor.fetchone()
        assert definition is not None, f"{self.STATUS_VALUES} is not installed"
        for value in COSTING_STATUS_VALUES:
            assert f"'{value}'" in definition[0], value


class ThePostingDeclaresWhatMayHappenToItsCostTest(TestCase):
    """The tripwire's subject, asserted from this side too — now inverted.

    #317 asserted here that this model declared **nothing**, because
    `RESOLVE_ONCE` on the pair would have been a promise G19 did not yet keep.
    #318 installed the enforcement, and this class turned over with it: the same
    three columns, the same two checks, the opposite answer. It is asserted
    about this model rather than about the whole registry so that this and the
    walk in `apps/platform/tests/` fail for different reasons.

    **Relaxing it to "the posting may declare classes" would have been the
    failure it was built to catch** — a test that passes whether or not the
    declaration exists is not a weaker version of this one, it is a different
    test that checks nothing.
    """

    def test_the_cost_and_its_status_are_declared_resolve_once(self):
        """As a pair, because the amount and the status settle together."""
        assert Posting.transition_classes[COST] == RESOLVE_ONCE
        assert Posting.transition_classes[STATUS] == RESOLVE_ONCE

    def test_the_claimed_cost_is_declared_frozen(self):
        assert Posting.transition_classes[CLAIMED] == FROZEN

    def test_the_new_columns_are_the_defended_ones(self):
        """Through the walk's own entry point, and pinned as an exact set.

        A column added to this model's declarations moves this line, which is
        the point: slice 4 declares its own pair here, and it should arrive past
        a reader rather than alongside one.
        """
        declared = columns_declared_into_defended_classes([Posting])
        assert declared == [("Posting", CLAIMED, FROZEN),
                            ("Posting", STATUS, RESOLVE_ONCE),
                            ("Posting", COST, RESOLVE_ONCE)]
