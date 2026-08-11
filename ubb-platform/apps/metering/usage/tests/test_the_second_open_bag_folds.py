"""The second open bag folds into the first, and the fold reverses (#273).

The mirror of #272's module next door, and the distinction between them is the
whole point. That column was RETIRED — there was nowhere to carry it — so its
reverse honestly restores a shape and not any contents. This column MOVED, so
ADR-0007 §1 applies in full and the tenant's data has to come out the other
side. `TheReverseIsExercisedTest` runs all three legs of that against a real
PostgreSQL table.

WHAT A MERGE CANNOT DO, AND WHAT THIS MODULE PINS INSTEAD OF GLOSSING:

- **It cannot pick a winner.** Two bags can hold the same key with different
  values, and only the tenant knows which was meant. The fold raises rather
  than choosing, and `test_a_disagreeing_key_refuses_rather_than_losing_a_value`
  is what makes that a decision rather than an accident waiting for real rows.
- **It cannot be un-merged.** After the fold, which key came from which bag is
  genuinely gone — recording it would mean writing provenance into a keyspace
  the tenant authored. So the reverse gives BOTH bags the merged contents.
  Nothing is lost in either direction and the round trip is total, which
  `test_folding_a_reversed_fold_changes_nothing` proves by running it.

`TheBagIsNotAGroupingAxisTest` at the foot carries the other half of the
ticket, and states exactly how far it reaches.
"""

from importlib import import_module

from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import Posting

APP_LABEL = "usage"
FOLD_MIGRATION = "0033_the_second_open_bag_folds"
PARENT_MIGRATION = "0032_the_inline_unit_total_dies"

#: The retiring bag, READ OFF THE MIGRATION RATHER THAN SPELLED HERE.
#:
#: Every other module in this tree that proves a rename happened had to be
#: excluded from the forbidden-term sweep in order to name the word it was
#: retiring. This one does not, because the one place the retired name still
#: legitimately lives — the migration that drops it, inside the excluded
#: migrations tree — is also the only place a reader should be looking it up.
#: Deriving it costs one import and takes no seeding authorisation, and a
#: leftover hit in this file would have said the removal was incomplete when
#: it was not.
RETIRED_COLUMN = next(
    op.name for op in
    import_module(
        f"apps.metering.usage.migrations.{FOLD_MIGRATION}").Migration.operations
    if isinstance(op, operations.RemoveField))
#: The surviving bag, which keeps its name and is free to be written down.
SURVIVING_COLUMN = "metadata"


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name for column in
                connection.introspection.get_table_description(
                    cursor, Posting._meta.db_table)}


class TheSecondBagIsGoneTest(TestCase):
    def test_the_model_declares_no_such_field(self):
        assert RETIRED_COLUMN not in {f.name for f in Posting._meta.get_fields()}

    def test_the_table_carries_no_such_column(self):
        """The model and the table are two separate claims.

        A field removed from the model with no migration behind it leaves the
        column in the database, where a raw query would still find it.
        """
        assert RETIRED_COLUMN not in _live_columns()

    def test_the_surviving_bag_is_still_there(self):
        """A fold that dropped both bags would pass every absence test above."""
        assert SURVIVING_COLUMN in _live_columns()

    def test_the_surviving_bag_carries_the_filtering_index(self):
        """FILTERING IS WHAT SURVIVES THE FOLD, and filtering a JSON bag
        without a GIN index is a sequential scan of the largest table in the
        system. 0022 put one on the retiring bag for exactly the containment
        and key-exists lookups that now run against this one.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT indexdef FROM pg_indexes WHERE tablename = %s "
                "AND indexname = %s",
                [Posting._meta.db_table, "idx_posting_metadata"])
            row = cursor.fetchone()
        assert row is not None, "the surviving bag has no GIN index"
        assert "gin" in row[0].lower()
        # Default `jsonb_ops`, not `jsonb_path_ops`: only the default opclass
        # serves the key-exists operator `__has_key` compiles to (0022).
        assert "jsonb_path_ops" not in row[0]


class TheMigrationCarriesItsDataTest(TestCase):
    """The operation ORDER, read off the migration rather than assumed."""

    def setUp(self):
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, FOLD_MIGRATION)

    def _index_of(self, op_type):
        for index, op in enumerate(self.migration.operations):
            if isinstance(op, op_type):
                return index
        self.fail(f"the migration carries no {op_type.__name__}")

    def test_the_data_moves_before_the_column_goes(self):
        """ADR-0007 §1. A `RemoveField` that runs first is an add-plus-remove
        wearing a data migration's clothes: it empties what it claims to move.
        """
        self.assertLess(self._index_of(operations.RunPython),
                        self._index_of(operations.RemoveField))

    def test_the_reverse_is_not_a_noop(self):
        run_python = self.migration.operations[
            self._index_of(operations.RunPython)]
        self.assertIsNot(run_python.reverse_code, operations.RunPython.noop)

    def test_every_operation_can_be_reversed(self):
        for op in self.migration.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)


class TheReverseIsExercisedTest(TestCase):
    """Forward and back, against a real database, with real rows.

    The fold's callables run against the state they see inside the migration:
    the retiring column still present. The live table has moved on — this
    migration is what dropped it — so `setUp` restores whatever the historical
    model has and the table does not, for the test's own duration. PostgreSQL
    runs DDL inside the transaction this `TestCase` rolls back, so the column
    leaves with everything else and no other test ever sees it.

    RECONCILED BY COMPARISON RATHER THAN BY NAME, per the fixture next door:
    naming the column would send this red on the next commit that drops a
    different one, and that failure reads as a broken reverse rather than as a
    stale fixture.
    """

    def setUp(self):
        loader = MigrationLoader(connection)
        self.migration = loader.get_migration(APP_LABEL, FOLD_MIGRATION)
        state = loader.project_state((APP_LABEL, PARENT_MIGRATION))
        self.historical = state.apps
        self.Posting = self.historical.get_model(APP_LABEL, "Posting")
        live = _live_columns()
        with connection.schema_editor() as editor:
            for field in self.Posting._meta.local_fields:
                if field.column not in live:
                    editor.add_field(self.Posting, field)
        self.run_python = next(op for op in self.migration.operations
                               if isinstance(op, operations.RunPython))
        self.tenant, self.customer = _tenant_and_customer()
        self._n = 0

    def _posting(self, retiring, surviving):
        """Both bags, by role rather than by name — see `RETIRED_COLUMN`."""
        self._n += 1
        return self.Posting.objects.create(
            tenant_id=self.tenant.id, customer_id=self.customer.id,
            idempotency_key=f"i{self._n}",
            **{RETIRED_COLUMN: retiring, SURVIVING_COLUMN: surviving})

    def _run(self, code):
        with connection.schema_editor() as editor:
            code(self.historical, editor)

    def _bags(self, posting):
        return self.Posting.objects.values(
            RETIRED_COLUMN, SURVIVING_COLUMN).get(pk=posting.pk)

    def test_every_key_survives_the_fold(self):
        posting = self._posting(retiring={"department": "sales", "x": "1"},
                                surviving={"trace": "abc"})

        self._run(self.run_python.code)

        self.assertEqual(self._bags(posting)[SURVIVING_COLUMN],
                         {"department": "sales", "x": "1", "trace": "abc"})

    def test_a_posting_with_no_second_bag_is_left_alone(self):
        """NULL is what a posting that carried no labels stored, and the
        surviving bag's own contents are not disturbed by a fold with nothing
        to fold in.
        """
        posting = self._posting(retiring=None, surviving={"trace": "abc"})

        self._run(self.run_python.code)

        self.assertEqual(self._bags(posting)[SURVIVING_COLUMN], {"trace": "abc"})

    def test_an_agreeing_key_merges_rather_than_refusing(self):
        """Same key, same value: nothing is lost by merging it, so it merges.
        The guard is about disagreement, not about overlap.
        """
        posting = self._posting(retiring={"seat": "alice"},
                                surviving={"seat": "alice", "trace": "abc"})

        self._run(self.run_python.code)

        self.assertEqual(self._bags(posting)[SURVIVING_COLUMN],
                         {"seat": "alice", "trace": "abc"})

    def test_a_disagreeing_key_refuses_rather_than_losing_a_value(self):
        """THE ONE CASE WHERE A MERGE DESTROYS DATA, MADE LOUD.

        UBB cannot pick a winner on the tenant's behalf — the two bags
        disagreed about one key and only the tenant knows which answer was
        meant. The failure names the posting and the key so the operator can
        resolve it, rather than discovering the loss in an invoice.
        """
        posting = self._posting(retiring={"seat": "alice"},
                                surviving={"seat": "bob"})

        with self.assertRaises(ValueError) as raised:
            self._run(self.run_python.code)

        self.assertIn("seat", str(raised.exception))
        self.assertIn(str(posting.pk), str(raised.exception))

    def test_the_reverse_gives_both_bags_the_merged_contents(self):
        """The split is unrecoverable, so the reverse does not invent one.

        Duplication is not loss: every key the tenant authored is readable
        through both names after the reverse, and neither bag is a guess about
        which name it arrived under.
        """
        posting = self._posting(retiring={"department": "sales"},
                                surviving={"trace": "abc"})
        self._run(self.run_python.code)

        self._run(self.run_python.reverse_code)

        bags = self._bags(posting)
        self.assertEqual(bags[SURVIVING_COLUMN],
                         {"department": "sales", "trace": "abc"})
        self.assertEqual(bags[RETIRED_COLUMN],
                         {"department": "sales", "trace": "abc"})

    def test_the_reverse_leaves_an_empty_bag_null(self):
        """`{}` would claim the tenant authored an empty bag; NULL is what the
        restored column meant for a posting that carried no labels."""
        posting = self._posting(retiring=None, surviving={})
        self._run(self.run_python.code)

        self._run(self.run_python.reverse_code)

        self.assertIsNone(self._bags(posting)[RETIRED_COLUMN])

    def test_folding_a_reversed_fold_changes_nothing(self):
        """The round trip is TOTAL, which is what makes the duplicating
        reverse honest rather than convenient: every key the reverse copies
        back meets itself on the way forward, which is the agreeing-key case
        the guard permits — not the disagreeing one it refuses.
        """
        posting = self._posting(retiring={"department": "sales"},
                                surviving={"trace": "abc"})
        self._run(self.run_python.code)
        folded = self._bags(posting)[SURVIVING_COLUMN]

        self._run(self.run_python.reverse_code)
        self._run(self.run_python.code)

        self.assertEqual(self._bags(posting)[SURVIVING_COLUMN], folded)


class TheBagIsNotAGroupingAxisTest(TestCase):
    """FILTERABLE AND READABLE, NEVER GROUPABLE — as far as slice 2 reaches.

    **Read the limit of this claim before trusting it.** What it pins is that
    the surviving bag, BY ITS OWN NAME, is not a grouping axis anywhere: it is
    not a groupable column, and naming it as an invoice-line grouping does not
    read it. That is the part of "an unbounded free-text key can never drive an
    invoice line label" slice 2 can honestly deliver.

    WHAT IT DOES NOT PIN, DELIBERATELY: the keyed analytics parameter and the
    `tag:` grouping prefix still read keys out of this bag, so an unbounded key
    CAN still reach a chart and an invoice line today. Those three surfaces —
    the keyed analytics parameter, the keyed margin breakdown and the
    key-driven invoice line labels — carry two G7 ledger entries of their own,
    both owned by slice 7, and slice 7 is where the capability moves onto the
    declared grouping contract. Slice 2 folded the field; moving the capability
    early would be building another slice's design without it.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()

    def test_the_bag_is_not_a_groupable_column(self):
        """The margin breakdown's `group_by` is a closed list of resolved
        columns, and the open bag is not one of them — nor is any key inside
        it, which is the whole difference between a declared axis and a bag.
        """
        from apps.metering.queries import get_dimensional_margin
        for named in (SURVIVING_COLUMN, f"{SURVIVING_COLUMN}__department"):
            with self.subTest(group_by=named):
                with self.assertRaises(ValueError):
                    get_dimensional_margin(self.tenant.id, group_by=named)

    def test_the_bag_is_not_a_declarable_grouping_field_target(self):
        """A declared Grouping Field binds a tenant key to a physical SLOT.
        There is no slot that is the bag, so no declaration can point at it.
        """
        from apps.platform.grouping_fields.models import SLOT_CHOICES
        assert SURVIVING_COLUMN not in dict(SLOT_CHOICES)

    def test_naming_the_bag_as_an_invoice_line_grouping_does_not_read_it(self):
        """The postpaid line-label reader groups by a resolved column, and
        being handed the bag's own name does not make it read the bag.
        """
        from apps.metering.queries import get_customer_billed_breakdown
        from datetime import date
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i_lbl",
            billed_cost_micros=500_000, dim1="",
            metadata={"seat": "alice"})

        rows = get_customer_billed_breakdown(
            self.tenant.id, self.customer.id, date(2020, 1, 1),
            date(2100, 1, 1), group_by=SURVIVING_COLUMN)

        # The bag held "alice"; the label is the empty-dim1 collapse, not it.
        self.assertEqual(rows, [("(other)", 500_000)])
