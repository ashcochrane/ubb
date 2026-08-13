"""The usage invoice line's grouped value takes the canonical noun (#312).

One real column moves in this commit, and ADR-0007 §1's rule about how is the
one rule here that cannot be checked by reading the diff: an `AddField` beside a
`RemoveField` produces a column of exactly the right name, and every other
assertion in this module would pass over it while every line label on every
pushed invoice had been dropped. So the shape is asserted against the migration,
and then the claim the shape is making — that rows come with it — is driven
against a real table.

**THE RETIRED NAME IS NEVER SPELLED HERE**, on the same rule #274 and #275
established: a test module is a living surface, so spelling the word would
re-open the very extent this commit pays off, and the choice would then be a
hand-written exclusion or a false ledger count. It is read off the rename
operation, which is also the stronger form — a test naming its own expectation
twice cannot disagree with itself.

**The contract claim is an ABSENCE and it is checked in both directions.** This
column is internal: written in `postpaid_service`, read by this app's tests, and
published nowhere. That is what let a real column be renamed in a commit whose
whole point is that `openapi/v1.json` regenerates byte-identical — so "no schema
carries either name" is not a formality, it is the evidence for the claim.
"""

import json
import datetime
from importlib import import_module

from django.core.exceptions import FieldDoesNotExist
from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

from api.v1.openapi_export import GIT_ROOT
from apps.billing.invoicing.models import CustomerUsageInvoice, UsageInvoiceLineItem
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

APP_LABEL = "invoicing"
RENAME_MIGRATION = "0008_the_usage_line_names_its_grouped_value"
PARENT_MIGRATION = "0007_consolidated_postpaid"

#: Both names, read off the rename itself.
#:
#: Unpacked from a one-element tuple on purpose: a migration that ever grew a
#: second `RenameField` would make `next(...)` pick one silently, and every
#: assertion below would then be about a column nobody meant.
(_RENAME,) = tuple(
    op for op in
    import_module(
        f"apps.billing.invoicing.migrations.{RENAME_MIGRATION}").Migration.operations
    if isinstance(op, operations.RenameField))
RETIRED_COLUMN = _RENAME.old_name
CANONICAL_COLUMN = _RENAME.new_name


def every_operation(migration):
    """Every operation in a migration, including the nested ones.

    `SeparateDatabaseAndState` carries two operation lists of its own, and a
    field add hidden in either is invisible to a check that reads only the top
    level — while being exactly the shape ADR-0007 §1 forbids. Module level so
    the negative control below drives the same walk the guard does; a control
    that re-implemented the walk would prove the control correct, not the guard.
    """
    for op in migration.operations:
        yield op
        yield from getattr(op, "database_operations", ())
        yield from getattr(op, "state_operations", ())


def _an_invoice():
    tenant = Tenant.objects.create(name="T")
    customer = Customer.objects.create(tenant=tenant, external_id="c1")
    return CustomerUsageInvoice.objects.create(
        tenant=tenant, customer=customer,
        period_start=datetime.date(2026, 6, 1), period_end=datetime.date(2026, 7, 1),
        total_billed_micros=1_000_000, currency="usd")


class TheMoveIsARenameTest(TestCase):
    """ADR-0007 §1, checked against the migration rather than the message."""

    def setUp(self):
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, RENAME_MIGRATION)

    def test_it_carries_no_add_plus_remove(self):
        for op in every_operation(self.migration):
            with self.subTest(operation=type(op).__name__):
                self.assertNotIsInstance(
                    op, (operations.AddField, operations.RemoveField))

    def test_it_is_the_rename_and_nothing_else(self):
        self.assertEqual([type(op).__name__ for op in self.migration.operations],
                         ["RenameField"])

    def test_it_renames_the_column_on_the_usage_invoice_line(self):
        self.assertEqual(_RENAME.model_name.lower(),
                         UsageInvoiceLineItem._meta.model_name)


class TheGuardWouldCatchTheForbiddenShapeTest(SimpleTestCase):
    """The vacuity half: a walk that found nothing and a walk that looked
    nowhere report the same clean result, and they are not the same fact.

    This is what `makemigrations` actually emits for this change when it is run
    without a TTY — it never asks "did you rename this?", so it proposes the add
    and the remove — plus the harder variant, the same pair buried inside a
    `SeparateDatabaseAndState` where a top-level-only check cannot see it.
    """

    class _Migration:
        def __init__(self, operations_):
            self.operations = operations_

    def _forbidden(self):
        return (operations.AddField(model_name="usageinvoicelineitem",
                                    name="grouping_field_value",
                                    field=None),
                operations.RemoveField(model_name="usageinvoicelineitem",
                                       name="whatever_it_was_called"))

    def _walk(self, operations_):
        return [type(op).__name__
                for op in every_operation(self._Migration(operations_))]

    def test_the_walk_sees_an_add_beside_a_remove(self):
        self.assertEqual(self._walk(self._forbidden()),
                         ["AddField", "RemoveField"])

    def test_the_walk_reaches_the_pair_nested_below_the_top_level(self):
        nested = operations.SeparateDatabaseAndState(
            database_operations=list(self._forbidden()), state_operations=[])
        self.assertEqual(
            self._walk([nested]),
            ["SeparateDatabaseAndState", "AddField", "RemoveField"])


class ARowWrittenBeforeTheRenameStillReadsAfterItTest(TestCase):
    """THE CLAIM ADR-0007 §1 IS ACTUALLY MAKING, run against a real table.

    `assertTrue(op.reversible)` would look like this test and prove nothing:
    `reversible` is a class attribute on `Operation` that `RenameField` never
    overrides, so it is `assertTrue(True)`, and the operation list is pinned
    above already.

    So this drives the operation. A line is written, the column is renamed back
    to what it was before this migration, the value is read under the OLD name
    through a raw cursor — deliberately bypassing the model, which is the only
    thing that knows the new name — and the rename is then re-applied and the
    value read under the new one. An add-plus-remove wearing a rename's clothes
    fails at the first read, which is the failure the rule exists to catch.

    PostgreSQL runs DDL inside the transaction this `TestCase` rolls back, so
    the column ends where it started however this test exits.
    """

    def test_the_label_survives_the_round_trip(self):
        line = UsageInvoiceLineItem.objects.create(
            usage_invoice=_an_invoice(), amount_micros=1_000_000,
            **{CANONICAL_COLUMN: "prod_a"})

        loader = MigrationLoader(connection)
        before = loader.project_state((APP_LABEL, PARENT_MIGRATION))
        after = before.clone()
        _RENAME.state_forwards(APP_LABEL, after)

        table = UsageInvoiceLineItem._meta.db_table
        with connection.schema_editor() as editor:
            _RENAME.database_backwards(APP_LABEL, editor, after, before)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {connection.ops.quote_name(RETIRED_COLUMN)} "
                f"FROM {connection.ops.quote_name(table)} WHERE id = %s",
                [line.id])
            (carried,) = cursor.fetchone()
        self.assertEqual(carried, "prod_a")

        with connection.schema_editor() as editor:
            _RENAME.database_forwards(APP_LABEL, editor, before, after)
        self.assertEqual(
            getattr(UsageInvoiceLineItem.objects.get(id=line.id), CANONICAL_COLUMN),
            "prod_a")


class TheTableAndTheModelBothMovedTest(TestCase):
    """Two separate claims, and only one of them is about the model.

    A field renamed on the model with no migration behind it leaves the old
    column in the database, where a raw query would still find it — and the
    reverse, a migration with no model change, leaves the model reading a column
    that is not there.
    """

    def test_the_table_carries_the_canonical_column_and_not_the_retired_one(self):
        with connection.cursor() as cursor:
            columns = {column.name for column in
                       connection.introspection.get_table_description(
                           cursor, UsageInvoiceLineItem._meta.db_table)}
        self.assertIn(CANONICAL_COLUMN, columns)
        self.assertNotIn(RETIRED_COLUMN, columns)

    def test_the_retired_name_is_gone_from_the_model(self):
        with self.assertRaises(FieldDoesNotExist):
            UsageInvoiceLineItem._meta.get_field(RETIRED_COLUMN)

    def test_a_pushed_line_is_still_written_and_read_by_its_label(self):
        """The column is not merely present — the write path fills it.

        A rename that left the service writing nothing would satisfy every
        structural assertion here and quietly empty every future invoice line.
        """
        invoice = _an_invoice()
        UsageInvoiceLineItem.objects.create(
            usage_invoice=invoice, amount_micros=600_000,
            **{CANONICAL_COLUMN: "prod_a"})
        self.assertEqual(
            list(invoice.line_items.values_list(CANONICAL_COLUMN, "amount_micros")),
            [("prod_a", 600_000)])


class TheContractIsWhereTheCanonicalNameCameFromTest(SimpleTestCase):
    """Why a real column could move in a zero-spec-diff commit — and where the
    word it moved to was already in use.

    Two claims, and they are not the same one twice. The ABSENCE is why this
    rename is not a contract change: nothing published carried the retired name,
    so the spec regenerates byte-identical. The PRESENCE is why the replacement
    was not invented here — `GroupingFieldMarginRow` is a DECLARED schema on
    `/margin/by-grouping-field`, and its own comment states the reading this
    whole commit rests on: the property holds *the value the row groups, not the
    axis it was grouped on*. The two open-dict analytics rollups and this column
    now say what that schema has said all along.

    That makes this the pin under the ruling. If the published property is ever
    renamed, three sites that were deliberately spelled to match it are wrong,
    and this is where a reader finds that out.
    """

    PUBLISHED_ROW = "GroupingFieldMarginRow"

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schemas = json.loads(
            (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
        )["components"]["schemas"]

    def test_no_published_schema_carries_the_retired_name(self):
        for name, schema in self.schemas.items():
            with self.subTest(schema=name):
                self.assertNotIn(RETIRED_COLUMN, schema.get("properties", {}))

    def test_the_declared_margin_row_publishes_the_canonical_name(self):
        self.assertIn(CANONICAL_COLUMN,
                      self.schemas[self.PUBLISHED_ROW]["properties"])
