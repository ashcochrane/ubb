"""A customer price UBB could not resolve stops being recorded as zero (#351).

The mirror of what #317 did for the supplier cost, one slice later and for the
other side of the margin. The posting's customer-price column was
`BigIntegerField(default=0)` and there was **no value in it meaning "not
resolved"**, so *"we priced this at nothing"* and *"we could not price this"*
were the same row. A customer who should have been charged and was not looked
exactly like a customer correctly charged nothing, and there was no queue of the
first kind to work through.

Three columns settle it, and the whole of what this module proves is that the
difference is held **at the database** rather than by whoever remembers to look:

* the customer price becomes nullable, `NULL` meaning *not resolved*. Zero keeps
  its own meaning — *resolved, and it was exactly nothing*.
* `pricing_status` — `known` · `waived` · `unknown` · `not_applicable`
* `not_applicable_reason`, nullable — which of two mutually exclusive causes
  produced a subject that generates no customer revenue at this level

**Four statuses and only two column shapes, deliberately.** `waived` and
`unknown` carry exactly the same pair of absent fields, and that is the point:
the distinction between *a charge somebody decided not to pursue* and
*information UBB does not have* is a decision, not a shape, and the status
column is what carries it. A fifth combination invented to make them differ at
the table would be encoding the same fact twice.

**Why the illegal combinations skip model validation.** A `full_clean` that
refuses them proves something about Django, not about the table, and this
repository has already shipped a model-level guard that a production writer
bypassed by design. Each illegal combination and each out-of-set value is
therefore written straight at Postgres, with nothing between the statement and
the table but the ORM's own SQL.

⚠ **They are driven as an `INSERT`, and #318 is why** — the reason
`test_an_unknown_cost_stops_being_zero.py` records at length. This table carries
a `BEFORE UPDATE` trigger, and a `BEFORE` trigger runs before the table's
constraints are evaluated, so a raw `UPDATE` would fail with the trigger's
message and this class would go on passing with the `CHECK` dropped.

**No transition class is declared here, and that is #352's work rather than an
omission.** Declaring a column into a database-defended class *before* the
database defends it is exactly what
`apps/platform/tests/test_transition_class_declarations.py` exists to catch, and
slice 3 hit that edge. The declaration and its trigger land together, in one
commit, in the ticket after this one — and this module pins the absence so that
doing it here would go red rather than quietly turning G19.
"""
from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.transitions import columns_declared_into_defended_classes
from core.vocabulary import (
    NOT_APPLICABLE_REASON_FIXED_TASK_PRICING,
    NOT_APPLICABLE_REASON_VALUES,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_VALUES,
    PRICING_STATUS_WAIVED,
)

PRICE = "billed_cost_micros"
STATUS = "pricing_status"
REASON = "not_applicable_reason"


#: The four combinations `ck_posting_pricing_status_agrees_with_the_price`
#: admits, as (status, amount, reason). `0` and a real declared reason stand for
#: "an amount is present" and "a reason is present" — the constraint is about
#: presence, and using a legal value keeps every refusal below attributable to
#: the disjunction rather than to one of the two value-set checks.
THE_FOUR_LEGAL_COMBINATIONS = (
    (PRICING_STATUS_KNOWN, 0, None),
    (PRICING_STATUS_WAIVED, None, None),
    (PRICING_STATUS_UNKNOWN, None, None),
    (PRICING_STATUS_NOT_APPLICABLE, None,
     NOT_APPLICABLE_REASON_FIXED_TASK_PRICING),
)

#: Everything else in the space — DERIVED, so the set cannot fall behind the
#: rule. Four statuses × amount present/absent × reason present/absent is
#: sixteen; take the four above away and twelve must be refused.
THE_TWELVE_ILLEGAL_COMBINATIONS = tuple(
    combination
    for combination in (
        (status, amount, reason)
        for status in sorted(PRICING_STATUS_VALUES)
        for amount in (0, None)
        for reason in (NOT_APPLICABLE_REASON_FIXED_TASK_PRICING, None)
    )
    if combination not in THE_FOUR_LEGAL_COMBINATIONS
)


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _posting_for_a_new_customer(**kwargs):
    tenant, customer = _tenant_and_customer()
    return Posting.objects.create(tenant=tenant, customer=customer, **kwargs)


class TheColumnsAreShapedAsRuledTest(TestCase):
    """The three shapes, read off the model rather than off the migration."""

    def _field(self, name):
        return Posting._meta.get_field(name)

    def test_the_customer_price_is_nullable(self):
        """The default stays 0, which is not a leftover.

        A writer that says nothing about customer price still records `known`
        and zero — the reading every row had before this column could be null,
        and the one the migration gives every row that already existed. What
        changed is that `NULL` became SAYABLE.
        """
        assert self._field(PRICE).null
        assert self._field(PRICE).default == 0

    def test_the_status_is_not_nullable(self):
        """`unknown` is a status, not the absence of one.

        A nullable status column would be a fifth state meaning "nobody said",
        which is the ambiguity this ticket exists to remove rather than to move
        one column to the left.
        """
        assert not self._field(STATUS).null

    def test_the_reason_is_nullable(self):
        assert self._field(REASON).null


class TheValueSetsAreHeldByReferenceTest(TestCase):
    """Imported from `core.vocabulary`, not restated here.

    The check is that the model's own `choices` agree with the registry's
    frozensets exactly. A hand-written list would pass on the day it was typed
    and drift on the day the registry moved — which is what the two migration
    ledger entries this commit deletes recorded.
    """

    def test_the_status_choices_are_the_registry_value_set(self):
        declared = {value for value, _ in Posting._meta.get_field(STATUS).choices}
        assert declared == set(PRICING_STATUS_VALUES)

    def test_the_reason_choices_are_the_registry_value_set(self):
        declared = {value for value, _ in Posting._meta.get_field(REASON).choices}
        assert declared == set(NOT_APPLICABLE_REASON_VALUES)

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

    Two rows: one priced at nothing and one nobody could price. The assertions
    are made with `IS NULL` and `= 0` through a cursor, because a Python read of
    two ORM attributes would be satisfied by a column that coalesced on the way
    out.
    """

    def setUp(self):
        self.free = _posting_for_a_new_customer(
            idempotency_key="free",
            **{PRICE: 0, STATUS: PRICING_STATUS_KNOWN})
        self.unknown = _posting_for_a_new_customer(
            idempotency_key="unknown",
            **{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN})

    def _count(self, predicate):
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT count(*) FROM {Posting._meta.db_table} "
                f"WHERE {PRICE} {predicate}")
            return cursor.fetchone()[0]

    def test_exactly_one_row_holds_a_resolved_zero(self):
        assert self._count("= 0") == 1

    def test_exactly_one_row_holds_no_resolved_price_at_all(self):
        assert self._count("IS NULL") == 1

    def test_the_two_rows_are_not_the_same_row(self):
        """The vacuity guard on the pair above.

        Both counts would read 1 against a single row if either predicate were
        misspelled into something that matched everything.
        """
        assert self.free.pk != self.unknown.pk
        assert self._count("IS NOT NULL") == 1

    def test_a_sum_over_the_column_skips_the_unresolved_row(self):
        """The whole reason this commit also repairs 39 readers.

        SQL's `SUM` ignores NULL, so a bare aggregate answers "0" over these two
        rows and looks exactly like a complete total. Every such aggregate
        becoming a pair — the resolved sum and its completeness — is the
        null-safety sweep, and this assertion is where a reader meets the reason
        for it.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT sum({PRICE}), count(*), count({PRICE}) "
                f"FROM {Posting._meta.db_table}")
            total, rows, priced = cursor.fetchone()
        assert (total, rows, priced) == (0, 2, 1)


class TheFourLegalCombinationsAreAdmittedTest(TestCase):
    """Each combination the rule permits, inserted through the ORM."""

    def test_known_carries_an_amount_and_no_reason(self):
        posting = _posting_for_a_new_customer(
            idempotency_key="k", **{PRICE: 4_200, STATUS: PRICING_STATUS_KNOWN})
        assert (getattr(posting, PRICE), getattr(posting, REASON)) == (4_200, None)

    def test_known_admits_a_resolved_zero(self):
        """The meaning zero keeps, stated as its own case.

        `known` with `0` is not a degenerate row to be tolerated — it is the
        answer for a call that was genuinely priced at nothing, and it is the
        reading the migration gives every row that already existed.
        """
        posting = _posting_for_a_new_customer(
            idempotency_key="k0", **{PRICE: 0, STATUS: PRICING_STATUS_KNOWN})
        assert getattr(posting, PRICE) == 0

    def test_waived_carries_neither(self):
        posting = _posting_for_a_new_customer(
            idempotency_key="w", **{PRICE: None, STATUS: PRICING_STATUS_WAIVED})
        assert (getattr(posting, PRICE), getattr(posting, REASON)) == (None, None)

    def test_unknown_carries_neither(self):
        posting = _posting_for_a_new_customer(
            idempotency_key="u", **{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN})
        assert (getattr(posting, PRICE), getattr(posting, REASON)) == (None, None)

    def test_waived_and_unknown_are_the_same_shape_and_different_rows(self):
        """The distinction the STATUS carries, asserted as such.

        Two rows whose every other column agrees, told apart by one value. If
        the pair were ever collapsed into one status, this is the test that
        would have to be deleted rather than adjusted — which is what makes it
        worth writing down.
        """
        waived = _posting_for_a_new_customer(
            idempotency_key="w2", **{PRICE: None, STATUS: PRICING_STATUS_WAIVED})
        unknown = _posting_for_a_new_customer(
            idempotency_key="u2", **{PRICE: None, STATUS: PRICING_STATUS_UNKNOWN})
        assert getattr(waived, PRICE) == getattr(unknown, PRICE)
        assert getattr(waived, REASON) == getattr(unknown, REASON)
        assert getattr(waived, STATUS) != getattr(unknown, STATUS)

    def test_not_applicable_carries_a_reason_and_no_amount(self):
        posting = _posting_for_a_new_customer(
            idempotency_key="n",
            **{PRICE: None, STATUS: PRICING_STATUS_NOT_APPLICABLE,
               REASON: NOT_APPLICABLE_REASON_FIXED_TASK_PRICING})
        assert getattr(posting, PRICE) is None
        assert getattr(posting, REASON) == NOT_APPLICABLE_REASON_FIXED_TASK_PRICING


class EveryIllegalCombinationIsRefusedByTheDatabaseTest(TestCase):
    """The rows Postgres must refuse, each one an `INSERT`.

    ⚠ **THE WHOLE SPACE, NOT A SELECTION.** Four statuses × amount present or
    absent × reason present or absent is SIXTEEN combinations; four are legal,
    so twelve must be refused. `THE_TWELVE_ILLEGAL_COMBINATIONS` below is
    derived from the space rather than hand-listed, because a hand-listed set
    is one somebody stops adding to — an earlier draft of this class asserted
    eight of the twelve and read as though it were exhaustive.

    Plus a status and a reason that name nothing the registry declares. None of
    it travels through model validation, which is the point: the guarantee is a
    property of the table.

    **Each case names the constraint it expects to be refused by**, because this
    table carries two mechanisms and "something refused this" is not evidence
    about either. See the module docstring for why the statement is an `INSERT`.
    """

    COMBINATION = "ck_posting_pricing_status_agrees_with_the_price"
    STATUS_VALUES = "ck_posting_pricing_status"
    REASON_VALUES = "ck_posting_not_applicable_reason"

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
            idempotency_key="subject",
            **{PRICE: 7, STATUS: PRICING_STATUS_KNOWN})
        assert getattr(posting, PRICE) == 7

    def test_the_twelve_illegal_combinations_are_each_refused(self):
        """Every combination outside the four legal ones, derived not listed.

        Each is driven as its own `subTest`, so a failure names the row rather
        than the first row of twelve. The amounts are `0` and the reasons are a
        real declared value on purpose: this class is about the DISJUNCTION, and
        a bogus reason or an out-of-set status would be refused by one of the
        value-set checks instead — those two cases are below, isolated.

        ⚠ `0` IS THE AMOUNT THAT MATTERS HERE. `waived` with `0` is the row a
        writer reaches for when it wants to record a charge nobody will pursue
        as "nothing", which is precisely the reading the waive exists to keep
        out of the column.
        """
        for status, amount, reason in THE_TWELVE_ILLEGAL_COMBINATIONS:
            with self.subTest(status=status, amount=amount, reason=reason):
                self._refused(self.COMBINATION,
                              **{PRICE: amount, STATUS: status, REASON: reason})

    def test_the_derived_set_is_the_whole_space_minus_the_legal_four(self):
        """The vacuity guard on the loop above.

        A derived set that derived nothing would make the loop pass by iterating
        over an empty list. This pins the arithmetic: sixteen combinations, four
        legal, twelve refused.
        """
        assert len(THE_FOUR_LEGAL_COMBINATIONS) == 4
        assert len(THE_TWELVE_ILLEGAL_COMBINATIONS) == 12
        assert not (set(THE_TWELVE_ILLEGAL_COMBINATIONS)
                    & set(THE_FOUR_LEGAL_COMBINATIONS))

    def test_an_illegal_combination_written_as_literal_sql_is_refused(self):
        """The AC's own words: refused "through raw SQL", not only the model.

        Everything above is an ORM `INSERT`, which sends the statement without
        `full_clean` and is what slice 3's equivalent class settled on — a
        hand-written `INSERT` would otherwise have to name every NOT NULL column
        and would then be testing that list rather than the constraint.

        This one case pays the difference anyway, on the cheapest possible
        statement: an `UPDATE` of the three columns on a row the ORM already
        committed. Nothing Django knows about is between it and the table.
        """
        posting = _posting_for_a_new_customer(
            idempotency_key="raw", **{PRICE: 5, STATUS: PRICING_STATUS_KNOWN})
        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {Posting._meta.db_table} "
                        f"SET {PRICE} = 0, {STATUS} = %s, {REASON} = NULL "
                        f"WHERE id = %s",
                        [PRICING_STATUS_WAIVED, str(posting.pk)])
        assert self.COMBINATION in str(refusal.exception), str(refusal.exception)

    def test_a_reason_outside_the_declared_set_is_refused(self):
        """Isolated on purpose: the rest of this row is legal.

        `not_applicable` with no amount and a reason present satisfies the
        combination check completely, so the only thing left to refuse it is the
        reason's own value set — which is what makes this case evidence about
        that constraint rather than about the disjunction beside it.
        """
        self._refused(self.REASON_VALUES,
                      **{PRICE: None, STATUS: PRICING_STATUS_NOT_APPLICABLE,
                         REASON: "customer_asked_nicely"})

    def test_a_status_outside_the_declared_set_is_refused(self):
        """The one case that cannot be isolated, and it says so.

        A status nobody declared fails the combination check as well, because
        that check enumerates the four legal statuses by name. Which of the two
        constraints Postgres reports is its own business, so this asserts only
        the refusal; what proves the value set is defended in its own right is
        the structural assertion below.
        """
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _posting_for_a_new_customer(
                    idempotency_key="subject",
                    **{PRICE: 1, STATUS: "invoiced", REASON: None})

    def test_the_status_value_set_is_a_constraint_of_its_own(self):
        """Read out of `pg_constraint`, because the row above cannot show it.

        Without this, dropping `ck_posting_pricing_status` would leave every
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
        for value in PRICING_STATUS_VALUES:
            assert f"'{value}'" in definition[0], value


class ThePriceIsNotYetDeclaredIntoADefendedClassTest(TestCase):
    """#352 declares and enforces in one commit; this pins that it has not yet.

    The transition-class walk holds every declaration in the tree to being
    defended at the database, so declaring this pair here — with no trigger on
    the table naming either column — would turn G19 red on this commit for no
    reason at all. The declaration is not "nearly done" work left out; it is the
    next ticket's subject, and the two land together or not at all.
    """

    def test_neither_new_column_is_declared(self):
        assert STATUS not in Posting.transition_classes
        assert REASON not in Posting.transition_classes

    def test_the_defended_set_is_still_slice_threes_three(self):
        """Through the walk's own entry point, and pinned as an exact set.

        The same assertion `test_an_unknown_cost_stops_being_zero.py` makes, and
        deliberately duplicated rather than shared: that module pins the set
        slice 3 established, this one pins that slice 4's biggest schema commit
        did not quietly join it. A single shared assertion could be satisfied by
        either file being deleted.
        """
        declared = columns_declared_into_defended_classes([Posting])
        assert [column for _, column, _ in declared] == [
            "claimed_provider_cost_micros", "costing_status",
            "provider_cost_micros"]
