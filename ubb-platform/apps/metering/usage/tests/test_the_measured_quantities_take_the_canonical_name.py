"""The measured-quantity bag takes the canonical measurement name (#274).

The bag was named for the act of metering. It is now named for the thing each
of its keys is a key **into** — the declarations #263 built beneath an Event
Type — and that is the whole point of the rename: a declared quantity is
*costable*, and an undeclared one is merely carried. The old name described a
container; the new one names a lookup.

**Nothing behavioural moves with it.** An unmatched quantity still meets a
`continue` on the price side and still contributes nothing, silently. Naming the
field for the declaration it keys into is what makes that mismatch *describable*;
slice 3 is what makes it *visible*. This module is deliberately quiet about it —
what a caller may still send is `test_negative_quantity_rejection.py`'s subject,
and that module now records both halves of it.

**ADR-0007 §1 governs the move:** `RenameField`, never add-plus-remove. The
pre-squash exemption is spent, and :class:`TheMoveIsARenameTest` is what holds
the migration to it rather than trusting the commit message.

**THE RETIRED NAME IS NEVER SPELLED HERE.** It is read off the rename operation
instead. Not because this module would be the only file left carrying the word —
it would not; the migrations tree and the contract gate's reviewed-break block
both still carry it, legitimately, and both are declared sweep exclusions. The
reason is narrower and it is about *this* file: a test module is a living
surface, so spelling the word here would re-open an extent the same commit is
paying off, and the choice would then be a hand-written exclusion or a false
ledger count. Deriving it costs one import and takes no seeding authorisation.
"""

from functools import cache
from importlib import import_module
from unittest.mock import patch

from django.core.exceptions import FieldDoesNotExist
from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from api.v1.openapi_export import GIT_ROOT
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.tests._helpers import (
    DECLARED, declares_a_caller_supplied_cost)
from apps.platform.event_types.models import Measurement
from apps.platform.tenants.models import Tenant, TenantApiKey

import json

APP_LABEL = "usage"
RENAME_MIGRATION = "0034_the_measured_quantities_take_the_canonical_name"
PARENT_MIGRATION = "0033_the_second_open_bag_folds"

#: The two names, both read off the rename itself.
#:
#: Unpacked from a one-element tuple on purpose: a migration that ever grew a
#: second `RenameField` would make `next(...)` pick one silently, and every
#: assertion below would then be about a column nobody meant.
(_RENAME,) = tuple(
    op for op in
    import_module(
        f"apps.metering.usage.migrations.{RENAME_MIGRATION}").Migration.operations
    if isinstance(op, operations.RenameField))
RETIRED_COLUMN = _RENAME.old_name
CANONICAL_COLUMN = _RENAME.new_name

#: The three published schemas the bag appears on. Named rather than discovered:
#: a walk that found two would report success just as loudly.
PUBLISHED_SCHEMAS = (
    "RecordUsageRequest",
    "RecordUsageResponse",
    "UsageEventDetailOut",
)

@cache
def schemas():
    """The published contract's schema block.

    Read on first use rather than at import, because two other test modules
    import `RETIRED_COLUMN` from here and neither of them should acquire a
    dependency on the spec file to get it.
    """
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


# A `correlation_field()` helper stood here, and #411 deleted it with its
# subject. It read the recording request's OTHER required identifier off the
# published contract rather than writing it down, because that word was retired
# and under a spread ceiling a later ticket owned. That ticket has landed: the
# field is gone, `customer_id` and `idempotency_key` are the whole required set,
# and the helper's one-element unpack — its own guard against a fourth required
# field arriving unnoticed — had nothing left to unpack.


def _tenant_and_customer():
    tenant = Tenant.objects.create(name="T")
    return tenant, Customer.objects.create(tenant=tenant, external_id="c1")


def _live_columns():
    with connection.cursor() as cursor:
        return {column.name for column in
                connection.introspection.get_table_description(
                    cursor, PostingMeasurement._meta.db_table)}


class TheMoveIsARenameTest(TestCase):
    """ADR-0007 §1, checked against the migration rather than the message."""

    def setUp(self):
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, RENAME_MIGRATION)

    def test_it_carries_no_add_plus_remove(self):
        """The failure this rule exists to stop leaves no trace afterwards.

        An `AddField` beside a `RemoveField` produces a column of the right
        name holding none of the data, and every assertion in every other class
        here would pass over it.
        """
        for op in self.migration.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertNotIsInstance(
                    op, (operations.AddField, operations.RemoveField))

    def test_it_is_the_rename_and_nothing_else(self):
        self.assertEqual([type(op).__name__ for op in self.migration.operations],
                         ["RenameField"])

    def test_it_renames_the_bag_on_the_measurement_record(self):
        self.assertEqual(_RENAME.model_name.lower(),
                         PostingMeasurement._meta.model_name)

    def test_a_row_written_before_the_rename_still_reads_after_it(self):
        """THE CLAIM ADR-0007 §1 IS ACTUALLY MAKING, run against a real table.

        `assertTrue(op.reversible)` would look like this test and prove nothing:
        `reversible` is a class attribute on `Operation` that `RenameField` never
        overrides, so it is `assertTrue(True)` — the sibling test above already
        pins the operation list, which is the whole of what that would add.

        So this drives the operation itself. A row is written, the column is
        renamed back to what it was before this migration, the row is read under
        the OLD name, and then the rename is re-applied and it is read under the
        new one. An add-plus-remove wearing a rename's clothes fails at the
        first read, which is the failure the rule exists to catch.

        PostgreSQL runs DDL inside the transaction this `TestCase` rolls back, so
        the column ends where it started no matter how this test exits.
        """
        tenant, customer = _tenant_and_customer()
        posting = Posting.objects.create(
            tenant=tenant, customer=customer, idempotency_key="idem_rename")
        PostingMeasurement.objects.create(
            posting=posting, recorded_at=timezone.now(),
            **{CANONICAL_COLUMN: {"input_tokens": 1200}})

        loader = MigrationLoader(connection)
        before = loader.project_state((APP_LABEL, PARENT_MIGRATION))
        after = before.clone()
        _RENAME.state_forwards(APP_LABEL, after)

        table = PostingMeasurement._meta.db_table
        with connection.schema_editor() as editor:
            _RENAME.database_backwards(APP_LABEL, editor, after, before)
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT {connection.ops.quote_name(RETIRED_COLUMN)} "
                f"FROM {connection.ops.quote_name(table)} WHERE posting_id = %s",
                [posting.id])
            (carried,) = cursor.fetchone()
        # A raw cursor hands JSONB back as text — the model field's decoder is
        # what usually parses it, and the whole point here is to read the column
        # without going through a model that knows this name.
        if isinstance(carried, str):
            carried = json.loads(carried)
        self.assertEqual(carried, {"input_tokens": 1200})

        with connection.schema_editor() as editor:
            _RENAME.database_forwards(APP_LABEL, editor, before, after)
        self.assertEqual(
            getattr(PostingMeasurement.objects.get(posting=posting),
                    CANONICAL_COLUMN),
            {"input_tokens": 1200})


class TheNameIsTheDeclarationsOwnTest(TestCase):
    """The rename's actual claim, and the only one worth making about a word.

    A rename that merely swapped one invented noun for another would satisfy the
    forbidden-term sweep and mean nothing. What makes this one true is that the
    bag now carries **the same name the declarations already carry**: the keys in
    it are codes of `Measurement` records hanging off an Event Type, and the
    accessor that reaches those records from the other direction is spelled the
    same way. Read from the declaration's own relation rather than typed twice,
    so that renaming either one without the other fails here.
    """

    def test_the_bag_is_named_for_what_it_is_a_key_into(self):
        accessor = (Measurement._meta.get_field("event_type")
                    .remote_field.get_accessor_name())
        self.assertEqual(CANONICAL_COLUMN, accessor)


class TheColumnCarriesTheCanonicalNameTest(TestCase):

    def test_the_record_declares_the_canonical_column(self):
        field = PostingMeasurement._meta.get_field(CANONICAL_COLUMN)
        self.assertEqual(field.get_internal_type(), "JSONField")

    def test_the_retired_column_is_gone_from_the_model(self):
        with self.assertRaises(FieldDoesNotExist):
            PostingMeasurement._meta.get_field(RETIRED_COLUMN)

    def test_the_table_carries_the_canonical_column_and_not_the_retired_one(self):
        """The model and the table are two separate claims.

        A field renamed on the model with no migration behind it leaves the old
        column in the database, where a raw query would still find it.
        """
        columns = _live_columns()
        self.assertIn(CANONICAL_COLUMN, columns)
        self.assertNotIn(RETIRED_COLUMN, columns)

    # The column's ADR-0007 §2 transition class is NOT re-asserted here.
    # `test_posting_measurement.py::TransitionClassesAreDeclaredTest` already
    # compares the declaration against `_meta.fields`, so a rename that moved
    # the field and not its declaration fails there — in the module that owns
    # the record. A second copy would fail in two places for one cause and
    # would be the one likelier to rot.


class ThePostingReadsItsQuantitiesUnderTheCanonicalNameTest(TestCase):
    """The read-only accessor #270 left on the posting moves with the column."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        self.posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_1", provider_cost_micros=1_000_000)

    def _measure(self, quantities):
        return PostingMeasurement.objects.create(
            posting=self.posting, recorded_at=timezone.now(),
            **{CANONICAL_COLUMN: quantities})

    def test_the_accessor_serves_the_childs_bag(self):
        self._measure({"input_tokens": 1200})
        self.assertEqual(getattr(self.posting, CANONICAL_COLUMN),
                         {"input_tokens": 1200})

    def test_the_retired_accessor_is_gone(self):
        self._measure({"input_tokens": 1200})
        self.assertFalse(hasattr(self.posting, RETIRED_COLUMN))

    def test_the_accessor_is_still_read_only(self):
        """One encoding of the quantities, and it lives on the child.

        ADR-0006 §4 is why this may be served and never written back; a writer
        that quietly succeeded here would be filling a column that is not there.
        """
        self._measure({"input_tokens": 1200})
        with self.assertRaises(AttributeError):
            setattr(self.posting, CANONICAL_COLUMN, {"input_tokens": 9})

    def test_an_absent_child_still_answers_an_empty_bag(self):
        self.assertEqual(getattr(self.posting, CANONICAL_COLUMN), {})


class TheRecordingPathWritesTheCanonicalColumnTest(TestCase):
    """End to end through the keyword surface both recording endpoints speak."""

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()

    def test_the_quantities_reach_the_child_record(self):
        # The retired correlation argument is passed POSITIONALLY, never named:
        # naming it here would add this file to an extent a later ticket owns
        # and make that ticket's recorded count false.
        result = UsageService.record_usage(
            self.tenant, self.customer, "idem_recorded",
            provider_cost_micros=1_000_000,
            **{CANONICAL_COLUMN: {"input_tokens": 1200, "output_tokens": 480}})
        posting = Posting.objects.get(id=result["event_id"])
        self.assertEqual(
            getattr(posting.measurement, CANONICAL_COLUMN),
            {"input_tokens": 1200, "output_tokens": 480})

    def test_the_acknowledgement_answers_under_the_canonical_name(self):
        result = UsageService.record_usage(
            self.tenant, self.customer, "idem_acked",
            provider_cost_micros=1_000_000,
            **{CANONICAL_COLUMN: {"input_tokens": 7}})
        self.assertEqual(result[CANONICAL_COLUMN], {"input_tokens": 7})
        self.assertNotIn(RETIRED_COLUMN, result)


class TheContractCarriesTheFinalNameTest(SimpleTestCase):
    """ADR-0007 §3: the final name, on the published document, in this slice.

    The sweep proves the retired word has left the contract. It cannot prove the
    canonical one arrived — a rename that dropped the property altogether would
    clear the extent just as cleanly, and every client generated from the
    document would silently stop sending a quantity.
    """

    def test_every_published_schema_carries_the_canonical_property(self):
        for name in PUBLISHED_SCHEMAS:
            with self.subTest(schema=name):
                self.assertIn(CANONICAL_COLUMN, schemas()[name]["properties"])

    def test_no_published_schema_carries_the_retired_property(self):
        for name, schema in schemas().items():
            with self.subTest(schema=name):
                self.assertNotIn(RETIRED_COLUMN, schema.get("properties", {}))

    def test_the_detail_response_pairs_the_bag_with_its_status(self):
        """The status field was named for this bag before the bag was.

        `measurements_status` says what an empty bag MEANS — pruned, never
        applicable, or genuinely empty. Until now it sat beside a differently
        named field and a reader had to be told they were about the same thing.
        """
        properties = schemas()["UsageEventDetailOut"]["properties"]
        self.assertIn(CANONICAL_COLUMN, properties)
        self.assertIn(f"{CANONICAL_COLUMN}_status", properties)


class TheStaleCallerIsAcceptedAndItsQuantitiesAreDroppedTest(TestCase):
    """WHAT THE RENAME COSTS A CALLER THAT HAS NOT MIGRATED YET.

    Taking the property off the request schema does **not** make a stale request
    fail. django-ninja keeps pydantic's `extra="ignore"`, so the retired key is
    accepted and thrown away, and the posting records with no quantities at all.

    **This one costs money, and the block in `oasdiff-warn-ignore.txt` says so.**
    Where the fold before it dropped labels, this drops the numbers the engine
    prices from: a caller relying on server-side pricing is charged as though it
    measured nothing. `test_record_usage_pricing.py` runs that end to end against
    a real cost card rather than leaving it as an inference from here.

    Pinned rather than repaired. Refusing an unknown field is a decision about
    every schema on the contract, and this ticket owns one field on three of
    them; the pre-live window (ADR-0007 §5) is what makes the break free, and the
    migration is a one-line rename in the caller.
    """

    def setUp(self):
        self.tenant, self.customer = _tenant_and_customer()
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        # The body below states the supplier's own cost, admissible only
        # against an Event Type that declares it arrives on the call (#324).
        declares_a_caller_supplied_cost(self.tenant, DECLARED)

    def _post(self, bag_key):
        return self.client.post(
            "/api/v1/metering/usage",
            data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": f"idem_{bag_key}",
                "event_type": DECLARED,
                "provider_cost_micros": 1_000_000,
                bag_key: {"input_tokens": 1200},
            }),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_retired_key_is_ignored_rather_than_refused(self, mock_process):
        response = self._post(RETIRED_COLUMN)

        self.assertEqual(response.status_code, 200)
        posting = Posting.objects.get(idempotency_key=f"idem_{RETIRED_COLUMN}")
        self.assertEqual(getattr(posting, CANONICAL_COLUMN), {})

    @patch("apps.platform.events.tasks.process_single_event")
    def test_the_canonical_key_is_the_one_that_lands(self, mock_process):
        """The control. Without it the test above passes on a broken endpoint."""
        response = self._post(CANONICAL_COLUMN)

        self.assertEqual(response.status_code, 200)
        posting = Posting.objects.get(idempotency_key=f"idem_{CANONICAL_COLUMN}")
        self.assertEqual(getattr(posting, CANONICAL_COLUMN),
                         {"input_tokens": 1200})
