"""The receipt's column takes the ratified name of what it holds (#370).

The record had three names — this column's, an endpoint docstring calling it the
receipt, and `apps/metering/CONTEXT.md` calling it the audit trail, which
already named the governance ledger. The registry ratified one of them
(`pricing_receipt_subject_type`) and retired the other two as aliases; the word
`provenance` survives as the name of a SECTION inside the record and nowhere
else. `usage/migrations/0042` moves the column and the wire key moves with it.

**THE RETIRED NAME IS NEVER SPELLED HERE**, and that is not decoration: the
sweep's ledger entries for this word reached ZERO on all four surfaces in the
same commit, so a living test module containing it would put the count back
above its entry — and the entry is gone, which makes any occurrence at all an
unaccounted site. It is read off the rename operation instead, exactly as
`pricing/tests/test_the_rates_quantity_name_takes_the_canonical_name.py` and
`pricing/tests/test_the_markup_record_is_deleted.py` do. Deriving it costs one
import and takes no seeding authorisation.

**WHAT THIS MODULE IS FOR, AND WHAT IT IS NOT.** Three claims, none of which the
other modules over this column can make:

- the move is a RENAME and carries its rows (ADR-0007 §1);
- nothing rewrote a receipt on the way past — there is no data migration, which
  is a read-path decision rather than an omission (#148 §4.6);
- the SEALING RULE followed the column, which is the half a rename does not do
  for you.

That the rule still refuses what it refuses is
`test_a_receipt_seals_once_it_is_complete.py`'s, driven through three doors
against real rows. Asserting it twice would fail in two places for one cause.
"""

import re
from importlib import import_module

from django.db import connection, migrations as operations
from django.test import SimpleTestCase, TestCase

from apps.metering.usage.models import Posting
from apps.metering.usage.tests._helpers import rule_on_the_table

RENAME_MIGRATION = "0042_the_receipt_takes_the_ratified_name_of_what_it_holds"

MIGRATION = import_module(
    f"apps.metering.usage.migrations.{RENAME_MIGRATION}")

#: The rule the rename had to carry, named as the migration names it.
TRIGGER = MIGRATION.TRIGGER

#: THE RETIRED SPELLING, DERIVED. Unpacked from a one-element tuple on purpose,
#: following `pricing/tests/test_the_rates_quantity_name_takes_the_canonical_
#: name.py`: a migration that grew a second `RenameField` would make `next(...)`
#: pick one silently, and every assertion here would then be about a column
#: nobody meant.
(_RENAME,) = tuple(op for op in MIGRATION.Migration.operations
                   if isinstance(op, operations.RenameField))
RETIRED = _RENAME.old_name

#: THE RATIFIED SPELLING, taken from the MODEL rather than from the same
#: migration: a constant compared against itself is a statement about a file.
RATIFIED = Posting.RECEIPT_COLUMN


class TheMoveIsARenameTest(TestCase):
    """ADR-0007 §1, checked against the migration rather than against prose."""

    def test_it_carries_no_add_plus_remove(self):
        """The failure this rule exists to stop leaves no trace afterwards.

        An `AddField` beside a `RemoveField` produces a column of the right name
        holding an empty record, and every other assertion in this suite passes
        over it — including the endpoint test that reads a receipt back, because
        that test writes its own row after the migration has run. The receipt is
        the authoritative record of what a tenant was charged and re-deriving one
        from today's configuration is the failure #148 §3 exists to prevent, so
        what would be lost here is not recoverable from anywhere.

        NESTED OPERATIONS ARE WALKED. `SeparateDatabaseAndState` carries two
        lists of its own, and a field add hidden in either is invisible to a
        check that reads only the top level.
        """
        for op in self._every_operation():
            with self.subTest(operation=type(op).__name__):
                self.assertNotIsInstance(
                    op, (operations.AddField, operations.RemoveField))

    def test_the_rename_moves_the_column_to_the_name_the_model_uses(self):
        """Both ends, and the new one taken from the MODEL rather than the
        migration — otherwise this compares a file with itself."""
        rename = _RENAME

        self.assertEqual(rename.model_name, "posting")
        self.assertEqual(rename.new_name, RATIFIED)
        self.assertNotEqual(rename.old_name, RATIFIED)

    def test_the_column_answers_to_the_ratified_name_and_not_the_retired_one(
            self):
        """Asked of the live table, because a migration that ran is evidence
        that a file executed and not that a column moved."""
        columns = self._columns_of_the_posting_table()

        self.assertIn(RATIFIED, columns)
        self.assertNotIn(RETIRED, columns)

    def _every_operation(self):
        for op in MIGRATION.Migration.operations:
            yield op
            for nested in (list(getattr(op, "database_operations", []))
                           + list(getattr(op, "state_operations", []))):
                yield nested

    def _columns_of_the_posting_table(self):
        with connection.cursor() as cursor:
            return {column.name for column
                    in connection.introspection.get_table_description(
                        cursor, Posting._meta.db_table)}


class NoDataMigrationRewritesAReceiptTest(SimpleTestCase):
    """AC (#370): old receipts are read, never rewritten — including here.

    The receipts on this column exist in two SHAPES, and #148 §4.6 governs both:
    a receipt records what the engine did on a day, and back-dating one into a
    shape that did not exist then makes it a worse record rather than a better
    one. What eventually removes the older shape is #155 §11's cutover squash.

    So the claim is that this migration touches no ROW. It is asserted over the
    SQL the migration actually runs rather than over its operation types,
    because `RunPython` is exactly the operation a data migration would use and
    this migration has two of them — for DDL, because a column rename does not
    reach inside a `plpgsql` body. Reading their statements is what tells the
    two apart.
    """

    #: ROW-WRITING STATEMENT SHAPES, not bare verbs — and the difference is the
    #: whole reason this is a regular expression. The rule's own definition says
    #: `BEFORE UPDATE ON ubb_posting`, so a check for the WORD `UPDATE` would
    #: condemn the DDL that installs it and this class would be red for every
    #: migration that ever installs a trigger. `SELECT` is absent deliberately:
    #: a read rewrites nothing.
    WRITES_ROWS = (
        r"\bUPDATE\s+\w+\s+SET\b",
        r"\bINSERT\s+INTO\b",
        r"\bDELETE\s+FROM\b",
    )

    def test_the_migration_runs_ddl_and_never_touches_a_row(self):
        statements = self._statements_the_migration_runs()
        self.assertTrue(statements, "no SQL was captured — the walk is broken")

        for statement in statements:
            for shape in self.WRITES_ROWS:
                with self.subTest(shape=shape):
                    self.assertIsNone(
                        re.search(shape, statement, re.IGNORECASE),
                        f"this migration runs a statement that writes rows, so "
                        f"it is a data migration: {statement[:200]}")

    def test_the_control_the_matcher_would_see_a_data_statement(self):
        """The vacuity guard, and it is the arm that carries this class.

        An absence check over a matcher nobody exercised reports a clean
        migration for a matcher that matches nothing — and narrowing the shapes
        above to statements rather than verbs is exactly the edit that could
        have done it. So each shape is fired at a statement it must catch, and
        at the DDL it must NOT, which is the pair that says the narrowing was to
        the right width.
        """
        writes = (f"UPDATE ubb_posting SET {RATIFIED} = '{{}}'",
                  "INSERT INTO ubb_posting (id) VALUES (1)",
                  "DELETE FROM ubb_posting WHERE id = 1")
        for statement in writes:
            with self.subTest(statement=statement):
                self.assertTrue(
                    any(re.search(shape, statement, re.IGNORECASE)
                        for shape in self.WRITES_ROWS), statement)

        installs = "CREATE TRIGGER t BEFORE UPDATE ON ubb_posting FOR EACH ROW"
        for shape in self.WRITES_ROWS:
            with self.subTest(shape=shape):
                self.assertIsNone(re.search(shape, installs, re.IGNORECASE))

    def _statements_the_migration_runs(self):
        """Every SQL string the migration's `RunPython` halves execute.

        Captured through a stand-in for the schema editor rather than run: the
        subject is what the migration WOULD run, and running it here would drop
        the rule out from under the rest of the suite.
        """
        captured = []

        class _Capturing:
            @staticmethod
            def execute(sql, params=None):
                captured.append(sql)

        for op in MIGRATION.Migration.operations:
            if isinstance(op, operations.RunPython):
                op.code(None, _Capturing)
                op.reverse_code(None, _Capturing)
        return captured


class TheSealingRuleFollowedTheColumnTest(TestCase):
    """The half a rename does not do for you, asked of the live database.

    `ALTER TABLE ... RENAME COLUMN` carries every row, every index and every
    constraint, and it carries a trigger's `WHEN` clause too, because Postgres
    stores that as a parsed expression over attribute numbers. It does NOT carry
    the trigger FUNCTION's body: `pg_proc.prosrc` is text, so a body reading
    `OLD.<old name>` survives the rename intact and spelling a column that no
    longer exists. The rule stays listed in `pg_trigger`, the declaration gate
    over it stays green, and the first `UPDATE` to fire it fails at runtime.

    That is why `0042` takes the rule off the table and puts it back around the
    rename rather than renaming underneath it — and why this class reads the
    body rather than trusting the migration's own account of itself.
    """

    def test_the_rules_body_names_the_ratified_column(self):
        _, body = rule_on_the_table(TRIGGER)

        self.assertIn(RATIFIED, body)

    def test_the_rules_body_no_longer_names_the_retired_column(self):
        """The direction that would have been silent.

        A body still naming the old column is not a subtle wrong answer: it is a
        rule that cannot run. Asserted separately from the arm above because the
        two fail for different reasons — one says the rule was never re-created,
        the other says it was re-created from the wrong text.
        """
        _, body = rule_on_the_table(TRIGGER)

        self.assertNotIn(RETIRED, body)

    def test_every_refusal_names_the_column_a_reader_will_go_looking_for(self):
        """The messages are what tell this rule apart from the two beside it on
        this table, so a message naming a column nobody can find is worse than a
        bare refusal.

        ⚠ **THE NUMBER IS DERIVED FROM THE BODY, NOT WRITTEN HERE**, and the
        first draft of this test is why: it asserted six and the rule raises
        SEVEN. A literal count taken from a reading is a claim about my memory,
        it goes stale the day a refusal is added or removed, and — worse — it
        goes stale in the passing direction, because a refusal added WITHOUT the
        column name would leave the count of NAMED messages where it was.
        Counting the `RAISE` statements and requiring every one of them to be a
        named refusal makes that case red.

        `test_a_receipt_seals_once_it_is_complete.py` asserts what each message
        SAYS, driven through real statements. What is asserted here is only that
        the rename reached them.
        """
        _, body = rule_on_the_table(TRIGGER)
        raises = body.count("RAISE EXCEPTION")
        named = body.count(f"{RATIFIED} is declared resolve_once")

        self.assertTrue(raises, "the rule raises nothing — the walk is broken")
        self.assertEqual(named, raises)
        self.assertNotIn(f"{RETIRED} is declared", body)
