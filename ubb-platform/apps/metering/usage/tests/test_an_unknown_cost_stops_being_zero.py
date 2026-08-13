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

**Why the illegal combinations are attempted through raw SQL.** A `full_clean`
that refuses them proves something about Django, not about the table, and this
repository has already shipped a model-level guard that a production writer
bypassed by design. Each of the six illegal combinations and each of the two
out-of-set values is therefore driven straight at Postgres, through a cursor,
on a row the ORM has already committed. An `UPDATE` rather than an `INSERT`
because a hand-written `INSERT` would have to name every NOT NULL column on
this table and would then be testing that list; a `CHECK` constraint holds on
both statements, and the legal combinations below are inserted through the ORM
so that both statements are covered between them.

**No transition class is declared here**, and that is a requirement rather than
an omission: `RESOLVE_ONCE` on this pair is a promise the database does not yet
keep, and `apps/platform/tests/test_transition_class_declarations.py` exists to
catch a column declared into a defended class before the defence lands. The
declaration and the enforcement arrive together in the next ticket.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import columns_declared_into_defended_classes
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
    """The eight statements Postgres must refuse, driven through a cursor.

    Six combinations outside the three legal ones, plus a status and a reason
    that name nothing the registry declares. None of them travels through model
    validation, which is the point: the guarantee is a property of the table.
    """

    def setUp(self):
        self.posting = _posting_for_a_new_customer(idempotency_key="subject",
                                **{COST: 1, STATUS: COSTING_STATUS_KNOWN})

    def _write(self, **columns):
        assignments = ", ".join(f"{name} = %s" for name in columns)
        with connection.cursor() as cursor:
            cursor.execute(
                f"UPDATE {Posting._meta.db_table} SET {assignments} WHERE id = %s",
                [*columns.values(), str(self.posting.pk)])

    def _refused(self, **columns):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                self._write(**columns)

    def test_the_cursor_can_write_a_legal_combination(self):
        """The control, and it is not optional.

        Every assertion below is "this statement failed". Without one statement
        of the same shape that SUCCEEDS, a misspelled column name or a cursor
        that could not write at all would satisfy the whole class.
        """
        self._write(**{COST: 7, STATUS: COSTING_STATUS_KNOWN, REASON: None})
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {COST} FROM {Posting._meta.db_table} WHERE id = %s",
                [str(self.posting.pk)])
            assert cursor.fetchone()[0] == 7

    def test_known_without_an_amount_is_refused(self):
        self._refused(**{COST: None, STATUS: COSTING_STATUS_KNOWN, REASON: None})

    def test_known_with_a_reason_is_refused(self):
        self._refused(**{COST: 1, STATUS: COSTING_STATUS_KNOWN,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_unresolved_with_an_amount_is_refused(self):
        self._refused(**{COST: 1, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_unresolved_without_a_reason_is_refused(self):
        """The half that keeps the status honest.

        A status saying a cost is missing without saying what would settle it is
        a shrug rather than something a tenant can act on.
        """
        self._refused(**{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: None})

    def test_not_applicable_with_an_amount_is_refused(self):
        self._refused(**{COST: 0, STATUS: COSTING_STATUS_NOT_APPLICABLE,
                         REASON: None})

    def test_not_applicable_with_a_reason_is_refused(self):
        self._refused(**{COST: None, STATUS: COSTING_STATUS_NOT_APPLICABLE,
                         REASON: UNRESOLVED_REASON_COST_RATE_MISSING})

    def test_a_status_outside_the_declared_set_is_refused(self):
        self._refused(**{COST: 1, STATUS: "settled", REASON: None})

    def test_a_reason_outside_the_declared_set_is_refused(self):
        self._refused(**{COST: None, STATUS: COSTING_STATUS_UNRESOLVED,
                         REASON: "supplier_was_asleep"})


class ThisTicketDeclaresNoTransitionClassTest(TestCase):
    """The tripwire's subject, asserted from this side too.

    `RESOLVE_ONCE` is the class this pair will take, and declaring it here would
    put a column into a class G19 defends before G19 defends anything —
    a promise with nothing behind it, which is exactly what
    `test_no_column_is_declared_into_a_class_the_database_defends` is built to
    catch. Asserted about this model rather than about the whole registry so
    that the two checks fail for different reasons.
    """

    def test_the_posting_declares_no_transition_classes_at_all(self):
        assert not getattr(Posting, "transition_classes", None)

    def test_the_new_columns_are_in_no_defended_class(self):
        declared = columns_declared_into_defended_classes([Posting])
        assert declared == []
