"""The posting's inline unit total is dropped, and the drop reverses (#272).

Slice 2 had to settle whether the child record #270 created carries one column
or two. **One.** The nameless inline quantity does not follow the measured ones
across — under the split it would have acquired a shorter life than the billed
total sitting beside it on the same response, while the read contract's `or 0`
coalescing went on rendering its absence as a currency zero on the end
customer's own view.

TWO DIFFERENT CLAIMS LIVE HERE, and only the first is about this database.

1. **The column is gone and the drop reverses.** Exercised against a real
   PostgreSQL table below, because ADR-0007 asks migrations to be reversible and
   a reverse nobody has run is a `noop` with better manners.
2. **Every READER is gone** — the read contract, six public schemas, the
   customer-facing summary, the SDK and the console. That claim spans four
   surfaces, so it is not this module's; it belongs to
   `tests/contracts/test_the_inline_unit_total_is_gone.py`, which can see all of
   them at once. Both are needed: a column dropped while a reader survives is a
   500, and a reader deleted while the column survives is a retirement that did
   not happen.

WHAT THE REVERSE HONESTLY RESTORES IS THE SHAPE, NOT THE CONTENTS. This is a
retirement, not a move: there is nowhere for the data to go, so a restored row
reads NULL — a value the column always allowed and which every reader already
coalesced. `test_the_reverse_restores_a_nullable_column` says so in an assertion
rather than in a comment, because "reversible" reads as "lossless" unless
somebody writes down that it is not.
"""

from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.metering.usage.models import Posting

APP_LABEL = "usage"
MIGRATION = "0032_the_inline_unit_total_dies"
PARENT_MIGRATION = "0031_the_measurements_become_a_child_record"

#: The column, by the name the database knew it by.
COLUMN = "units"


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name: column for column in
                connection.introspection.get_table_description(
                    cursor, Posting._meta.db_table)}


class TheColumnIsGoneTest(TestCase):
    def test_the_model_declares_no_such_field(self):
        assert COLUMN not in {field.name for field in Posting._meta.get_fields()}

    def test_the_table_carries_no_such_column(self):
        """The model and the table are two separate claims.

        A field removed from the model with no migration behind it leaves the
        column in the database, where the next `makemigrations` would offer to
        drop it a second time and a raw query would still find it.
        """
        assert COLUMN not in _live_columns()


class TheDropIsReversibleTest(TestCase):
    """Forward and back, against the real table.

    The whole round trip runs inside this `TestCase`'s transaction. PostgreSQL
    runs DDL transactionally, so the restored column leaves with the rollback and
    no other test can ever see it — which is what makes exercising a schema
    migration in place safe, and far safer than a `TransactionTestCase` round
    trip that leaves the database at the parent migration when it fails midway.
    """

    def setUp(self):
        loader = MigrationLoader(connection)
        migration = loader.get_migration(APP_LABEL, MIGRATION)
        self.operation = next(
            op for op in migration.operations
            if isinstance(op, operations.RemoveField) and op.name == COLUMN)
        self.before = loader.project_state((APP_LABEL, PARENT_MIGRATION))
        self.after = self.before.clone()
        self.operation.state_forwards(APP_LABEL, self.after)

    def test_the_reverse_puts_the_column_back_and_forward_takes_it_away(self):
        assert COLUMN not in _live_columns()

        with connection.schema_editor() as editor:
            self.operation.database_backwards(
                APP_LABEL, editor, self.after, self.before)
        assert COLUMN in _live_columns(), "the reverse restored nothing"

        with connection.schema_editor() as editor:
            self.operation.database_forwards(
                APP_LABEL, editor, self.before, self.after)
        assert COLUMN not in _live_columns(), (
            "the forward direction left the column behind after a reverse, so "
            "the two directions do not agree")

    def test_the_reverse_restores_a_nullable_column(self):
        """A retirement's reverse restores the shape and not the contents.

        Every row reads NULL afterwards. That is not a defect to repair later —
        there is no other copy of these values, and the ruling is that there
        should not be. The column being nullable is what makes the restored
        state legal at all, and it is why this reverse can exist without
        inventing data.
        """
        with connection.schema_editor() as editor:
            self.operation.database_backwards(
                APP_LABEL, editor, self.after, self.before)

        restored = _live_columns()[COLUMN]
        assert restored.null_ok, (
            "the restored column is NOT NULL, so reversing this migration on a "
            "non-empty table would fail or invent a value")

    def test_the_migration_removes_exactly_this_one_field(self):
        """A vacuity guard on `setUp`'s search.

        Everything above is stated about whatever operation that `next()` found.
        If the migration ever carried a second removal, or none, the round trip
        would be proving something about a different column — or about nothing.
        """
        loader = MigrationLoader(connection)
        removals = [op for op in loader.get_migration(
            APP_LABEL, MIGRATION).operations
            if isinstance(op, operations.RemoveField)]

        assert [op.name for op in removals] == [COLUMN]
        assert [op.model_name for op in removals] == ["posting"]
