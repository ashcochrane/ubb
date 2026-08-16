"""The rate's quantity name takes the canonical measurement name (#275).

A rate prices one named quantity. The column holding that name was spelled for
the metered *entity* — the sense the industry gives the word — rather than for
the quantity inside it, which is the mis-translation #145 §10 recorded and the
one this slice is paying off across the whole tree.

**THE HALF THAT IS NOT DONE IS THE POINT OF THIS MODULE.** The name is still
free text after the rename. Nothing checks that a rate names a quantity anybody
declared, and a rate naming one nobody did is still writable and still matches
nothing. That is not an oversight left behind by the rename — it is slice 2's
ruling, ADR-0007 §3's "final name, final contract, implementation partly built",
and slice 3 is what replaces the text with a reference to the declared record
the text is a name *of*. :class:`TheNameIsStillFreeTextAndThatIsSliceThreesTest`
is here so the next reader finds that written down beside a test that runs it,
rather than inferring a bug from a `CharField`.

**Why a column an entity rebuilt in slice 4 is renamed at this slice at all.**
The debt reaches the model, the book service, the pricing spine, the resolved-
rate cache and roughly a dozen pricing tests, while the rate itself survives to
slice 4 — which looks exactly like the "renaming a table a later slice deletes"
work the migration decision warns against. The ledger owns it at slice 2, an
owner may move earlier but never later, and there is no re-owning mechanism.

**ONE CLASS LEFT THIS MODULE WHEN THE COLUMN DID (#326).**
`ARowWrittenBeforeTheRenameStillReadsAfterItTest` wrote a row, drove the rename
backwards over the live table and read the value under the old name, which is
ADR-0007 §1's claim asked of a database rather than of a migration file. The
column it round-tripped no longer exists — slice 3 replaced it with a reference
and dropped it — so keeping the class would have meant rebuilding a table shape
this repository deliberately removed, in order to assert something about it.
**The claim is still made, by the migration that removed the column:**
``test_a_rate_names_a_declared_quantity.py`` runs that migration's own data
function forwards and backwards over real rows, including the ones it could not
place. What remains here is what can still be asked: the operation list, the two
database objects, and the published name.

**THE RETIRED NAME IS NEVER SPELLED HERE.** It is read off the rename operation
instead, exactly as #274 does. A test module is a living surface, so spelling it
would re-open an extent this same commit is paying off, and the choice would
then be a hand-written exclusion or a false ledger count. Deriving it costs one
import and takes no seeding authorisation. The same rule is why the discriminator
between cost and price books, the book foreign key and the shape-of-charge column
are never named below either: all three are retired words slice 4 owns, and a
count recorded there is a ceiling as much as a floor.
"""

import json
from functools import cache
from importlib import import_module

from django.core.exceptions import FieldDoesNotExist
from django.db import (IntegrityError, connection, migrations as operations,
                       transaction)
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

from api.v1.openapi_export import GIT_ROOT
from api.v1.schemas import RateIn
from apps.metering.pricing.models import NAMES_ONE_QUANTITY_CHECK, Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.platform.event_types.models import Measurement
from apps.platform.event_types.quantities import declaration_named
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant

APP_LABEL = "pricing"
RENAME_MIGRATION = "0016_the_rates_quantity_name_takes_the_canonical_name"
PARENT_MIGRATION = "0015_remove_rate_uq_rate_active_in_book_rate_dim1_and_more"

#: The two names, both read off the rename itself.
#:
#: Unpacked from a one-element tuple on purpose: a migration that ever grew a
#: second `RenameField` would make `next(...)` pick one silently, and every
#: assertion below would then be about a column nobody meant.
(_RENAME,) = tuple(
    op for op in
    import_module(
        f"apps.metering.pricing.migrations.{RENAME_MIGRATION}").Migration.operations
    if isinstance(op, operations.RenameField))
RETIRED_COLUMN = _RENAME.old_name
CANONICAL_COLUMN = _RENAME.new_name

#: WHAT THE NAME BECAME (#326). Spelled rather than read off an operation,
#: because the move that replaced the text with a reference is not a rename and
#: carries no operation holding both names. `CANONICAL_COLUMN` above is still
#: the name a tenant writes and reads on the wire — that is the whole reason
#: this module's contract assertions below did not move — and this is the field
#: the rate now holds it BY.
DECLARATION_FIELD = "measurement"

#: The two database objects over the quantity a rate prices. They survived the
#: RENAME untouched — the claim the state-only half of `0016` makes — and were
#: REBUILT by the conversion that replaced the column with a reference, because
#: an index over a text column and one over a foreign key are not the same
#: object. Their names did not change, which is why these two constants did not.
LOOKUP_INDEX = "idx_ratecard_lookup"
ACTIVE_ROW_UNIQUE = "uq_rate_active_in_book"

#: The three published schemas the name appears on — the write, the reprice and
#: the read. Named rather than discovered: a walk that found two would report
#: success just as loudly.
PUBLISHED_SCHEMAS = ("RateIn", "RateChangeIn", "RateOut")


@cache
def schemas():
    """The published contract's schema block."""
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


def _table_constraints():
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(
            cursor, Rate._meta.db_table)


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

        NESTED OPERATIONS ARE WALKED, which is what stops this being a restating
        of the operation-list test below. `SeparateDatabaseAndState` carries two
        lists of its own, and a field add hidden in either of them is invisible
        to a check that only reads the top level — while being exactly the shape
        this rule forbids, and a shape this migration's second operation makes
        possible for the first time.
        """
        for op in self._every_operation():
            with self.subTest(operation=type(op).__name__):
                self.assertNotIsInstance(
                    op, (operations.AddField, operations.RemoveField))

    def _every_operation(self):
        for op in self.migration.operations:
            yield op
            yield from getattr(op, "database_operations", ())
            yield from getattr(op, "state_operations", ())

    def test_it_renames_the_column_on_the_rate(self):
        self.assertEqual(_RENAME.model_name.lower(), Rate._meta.model_name)

    def test_the_only_database_work_is_the_rename(self):
        """The second operation is a state correction and must stay one.

        Django's project state does not carry a field rename into `Meta.indexes`
        or `Meta.constraints`, so the two objects built over this column have to
        be re-described or the autodetector proposes the change again on every
        run. Postgres has already carried them across the `ALTER TABLE ...
        RENAME COLUMN`, so re-describing them is a bookkeeping act — and doing it
        with real operations instead would drop and rebuild a live unique index
        to record a spelling. This asserts the database half is empty, which is
        the whole difference between those two readings.
        """
        (state_only,) = [op for op in self.migration.operations
                         if isinstance(op, operations.SeparateDatabaseAndState)]
        self.assertEqual(list(state_only.database_operations), [])
        self.assertEqual(
            [type(op).__name__ for op in state_only.state_operations],
            ["RemoveIndex", "AddIndex", "RemoveConstraint", "AddConstraint"])

    def test_it_is_the_rename_and_the_state_correction_and_nothing_else(self):
        self.assertEqual([type(op).__name__ for op in self.migration.operations],
                         ["RenameField", "SeparateDatabaseAndState"])


class TheDatabaseObjectsFollowedTheColumnTest(TestCase):
    """The claim the state-only half rests on, asked of the database.

    Declaring an index in `state_operations` says nothing about what is in
    Postgres; if the rename had NOT carried these two objects, the migration
    would have left an index over a column that no longer exists and this suite
    would be the last place to find out. So both are read back off the live
    table by introspection.

    **BOTH OBJECTS MOVED A SECOND TIME (#326)**, and this class moved with them
    rather than being left asserting the previous shape. The rename carried them
    across a spelling; the conversion to a reference REWROTE them, because a
    partial unique index and a lookup index over a text column are not the same
    database objects over a foreign key. Their job is unchanged and that is what
    is asserted: each still names the column that says which quantity a rate
    prices, and neither still names one that is gone.

    That the unique constraint still *fires* is `test_rate_card_model.py`'s,
    which drives it with a duplicate insert. Asserting it twice would fail in
    two places for one cause, and this is the copy that would rot.
    """

    def setUp(self):
        self.reference_column = Rate._meta.get_field(DECLARATION_FIELD).column

    def test_the_lookup_index_covers_the_reference(self):
        columns = _table_constraints()[LOOKUP_INDEX]["columns"]
        self.assertIn(self.reference_column, columns)
        self.assertNotIn(CANONICAL_COLUMN, columns)
        self.assertNotIn(RETIRED_COLUMN, columns)

    def test_the_active_row_uniqueness_covers_the_reference(self):
        columns = _table_constraints()[ACTIVE_ROW_UNIQUE]["columns"]
        self.assertIn(self.reference_column, columns)
        self.assertNotIn(CANONICAL_COLUMN, columns)
        self.assertNotIn(RETIRED_COLUMN, columns)

    def test_the_table_carries_the_reference_and_neither_text_column(self):
        """The model and the table are two separate claims.

        A field replaced on the model with no migration behind it leaves the old
        column in the database, where a raw query would still find it — and a
        text column left beside the reference is a second answer to "which
        quantity does this rate price" for anything reading the table directly.
        """
        with connection.cursor() as cursor:
            columns = {column.name for column in
                       connection.introspection.get_table_description(
                           cursor, Rate._meta.db_table)}
        self.assertIn(self.reference_column, columns)
        self.assertNotIn(CANONICAL_COLUMN, columns)
        self.assertNotIn(RETIRED_COLUMN, columns)


class TheNameIsAReferenceAndSliceThreePaidItTest(TestCase):
    """THE WINDOW SLICE 2 OPENED, CLOSED BY SLICE 3 (#326).

    This class was `TheNameIsStillFreeTextAndThatIsSliceThreesTest` and said
    what slice 2 deliberately did not build: the rate and the declaration agreed
    by spelling alone, and a rate naming a quantity nobody declared was
    writable. Its two tests were written to FAIL when slice 3 landed, and this
    is that landing — so each is replaced by its successor at its own address
    rather than deleted, and the class name follows the claim it now makes.
    Relaxing either would leave this file green while proving the opposite of
    what it was written to prove.

    The third test between them is untouched: what it asserts about the retired
    name is as true after the conversion as before it, and it is the one
    assertion here that neither slice's work can weaken.
    """

    def test_the_column_is_a_reference_rather_than_free_text(self):
        """The successor to `test_the_column_is_free_text_rather_than_a_reference`.

        That test asserted a `CharField` whose `is_relation` was false. The same
        two questions are asked here and answered the other way, plus the one
        the predecessor could not ask: WHAT it references. A relation to some
        other record would satisfy "is a relation" and price nothing a tenant
        declared.
        """
        field = Rate._meta.get_field(DECLARATION_FIELD)
        self.assertTrue(field.is_relation)
        self.assertIs(field.related_model, Measurement)

    def test_the_retired_name_is_gone_from_the_model(self):
        with self.assertRaises(FieldDoesNotExist):
            Rate._meta.get_field(RETIRED_COLUMN)

    def test_a_rate_may_not_name_a_quantity_nobody_declared(self):
        """The inversion of `test_a_rate_may_still_name_a_quantity_nobody_declared`.

        That test performed a write against a name no declaration carries and
        asserted it SUCCEEDED. The write performed here is the same one — the
        same name, and a name rather than an absence, because "a rate carrying
        no quantity at all is refused" is a weaker claim that would pass while
        the defect stood. It is refused by the database rather than by a
        `clean()` a caller can skip, which is the difference between a rule and
        a habit (ADR-0007 §2).

        THE PREMISE GUARD BELOW IS UNCHANGED, and it is what makes the refusal
        mean something. Without it a fixture that seeded the name would leave
        this test refusing a write for some other reason entirely and reporting
        it as this one.

        The lookup is asserted beside it because the two answer different
        questions: nothing to reference is why the route answers 422, and the
        refusal below is why the ORM is not a way around the route.
        """
        tenant = Tenant.objects.create(name="T")
        undeclared = "a_quantity_no_declaration_carries"
        # A guard on the premise, not evidence for the claim: the declarations
        # table is empty in this test, so it can only ever hold. It is here so a
        # future fixture that seeds declarations cannot make the write below
        # accidentally legitimate without this line going red first.
        self.assertFalse(Measurement.objects.filter(code=undeclared).exists())

        self.assertIsNone(
            declaration_named(tenant=tenant, measurement_key=undeclared))

        with transaction.atomic(), \
                self.assertRaisesRegex(IntegrityError, undeclared):
            Rate.objects.create(tenant=tenant,
                                undeclared_measurement_key=undeclared)


class TheReceiptNamesTheQuantityCanonicallyTest(TestCase):
    """The priced-line receipt moved with the column.

    Asserted positively only. That the retired word has left this module's
    source is the forbidden-term sweep's verdict, taken over the whole backend
    and recorded in the ledger; re-taking it here would need the word spelled,
    which is the one thing this file must not do.

    Receipts written before this commit are NOT rewritten and still carry the
    old key — a receipt records what the engine did on a day, and back-dating it
    to a vocabulary that did not exist then would make it a worse record. The
    engine version stamped beside it does NOT separate the two and is
    deliberately not bumped: it describes what the engine computed, and every
    amount is identical either side of a rename. `pricing_service._compute`
    argues that in full.
    """

    def test_a_priced_line_carries_the_canonical_name(self):
        tenant = Tenant.objects.create(name="T")
        rate = Rate.objects.create(
            tenant=tenant, rate_per_unit_micros=2_000_000, unit_quantity=1_000_000,
            measurement=declares_a_quantity(tenant, "input_tokens"))

        receipt = PricingService._compute(
            measurements={"input_tokens": 3},
            caller_provider_cost=None, caller_billed=None,
            resolve_declaration=lambda: None,
            resolve_card=lambda kind, key: rate,
            apply_markup=lambda provider_cost: provider_cost).pricing_receipt

        # Every priced line, not one picked out by the cost/price discriminator:
        # that discriminator is a retired word slice 4 owns, and naming it here
        # would push its recorded extent up by this file. Asserting over the
        # whole list is also the stronger claim — a line that kept the old key
        # would leave a `None` in this set rather than being filtered away.
        self.assertTrue(receipt["metrics"])
        self.assertEqual({entry.get(CANONICAL_COLUMN)
                          for entry in receipt["metrics"]},
                         {"input_tokens"})


class TheContractCarriesTheFinalNameTest(SimpleTestCase):
    """ADR-0007 §3: the final name, on the published document, in this slice.

    The sweep proves the retired word has left the contract. It cannot prove the
    canonical one arrived — a rename that dropped the property altogether would
    clear the extent just as cleanly, and every client generated from the
    document would silently stop naming which quantity a rate prices.
    """

    def test_every_published_schema_carries_the_canonical_property(self):
        for name in PUBLISHED_SCHEMAS:
            with self.subTest(schema=name):
                self.assertIn(CANONICAL_COLUMN, schemas()[name]["properties"])

    def test_no_published_schema_carries_the_retired_property(self):
        for name, schema in schemas().items():
            with self.subTest(schema=name):
                self.assertNotIn(RETIRED_COLUMN, schema.get("properties", {}))

    def test_the_write_side_still_requires_it(self):
        """The rename did not quietly make the name optional.

        A rename that landed the property as optional would satisfy every other
        assertion here while letting a rate be written with no quantity named —
        and it would also make the accepted-break block's central claim false,
        since a stale caller is refused precisely BECAUSE the replacement is
        required.

        Both write schemas, not one. It is required on all three of them (on the
        read side that means the server always sends it), but the two that a
        caller fills are the ones this claim is about.
        """
        for name in ("RateIn", "RateChangeIn"):
            with self.subTest(schema=name):
                self.assertIn(CANONICAL_COLUMN, schemas()[name]["required"])


class TheStaleWriterIsRefusedRatherThanIgnoredTest(SimpleTestCase):
    """WHAT THE RENAME COSTS A CALLER THAT HAS NOT MIGRATED — and it is LOUD.

    This is the opposite of what the three retirements before it cost. Where a
    dropped OPTIONAL property is silently ignored (django-ninja keeps pydantic's
    `extra="ignore"`, so #272, #273 and #274 all left a stale caller with a 200
    and quietly missing data), the property renamed here is **required**: the
    retired key is thrown away and the canonical one is then absent, so the
    request is refused at validation with nothing written.

    Saying so is the point. A reader who has learnt "these renames accept stale
    callers silently" from the last three tickets would carry a false rule into
    this one, and the difference is not a subtlety — it is 422-and-nothing-
    happens versus 200-and-something-wrong-happens.

    The refusal is exercised on the request model itself rather than over HTTP
    because that model IS what django-ninja validates the body with, and the
    endpoint's happy path is already driven end to end in
    `api/v1/tests/test_rate_card_crud.py`.
    """

    def test_a_body_carrying_only_the_retired_key_is_refused(self):
        from pydantic import ValidationError

        with self.assertRaises(ValidationError) as refusal:
            RateIn(**{RETIRED_COLUMN: "input_tokens"})

        missing = {tuple(error["loc"]) for error in refusal.exception.errors()
                   if error["type"] == "missing"}
        self.assertIn((CANONICAL_COLUMN,), missing)

    def test_a_body_carrying_the_canonical_key_is_accepted(self):
        """The control. Without it the test above passes on a broken schema."""
        payload = RateIn(**{CANONICAL_COLUMN: "input_tokens"})
        self.assertEqual(getattr(payload, CANONICAL_COLUMN), "input_tokens")
