"""A rate names the declared quantity it prices, or it is refused (#326).

Slice 2 renamed the column and said, in the model, in the migration and in a
test module built to fail today, that slice 3 would replace the name with a
reference to the declared record the name is a name *of*. This module is where
that lands. Three separate claims live here and they fail for different reasons:

* **The conversion carries its data.** A representation move under ADR-0007 §1
  is create, carry, remove — hand-ordered, because the autodetector writes an
  add-plus-remove that empties what it claims to move and, run without a
  terminal, never asks. The reverse is RUN here rather than asserted to exist.
* **A rate naming a quantity nobody declared is refused**, at the route with a
  422 that spends nothing, and at the database for every other door.
* **A rate the conversion could not place is deactivated** — it keeps its row,
  it keeps its name, it stops resolving, and it is neither deleted nor pointed
  at somebody else's declaration.

**WHAT DID NOT CHANGE IS ASSERTED TOO, because it is the thing most likely to
have.** Resolution still matches on the NAME, so a rate that leaves the Event
Type unpinned still prices the quantity under every Event Type declaring it.
Matching by the reference's identity instead would have looked like a tidier
spelling of the same rule and been a different one.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The cost/price discriminator,
the book pointer and the shape-of-charge column are all names slice 4 owns, and
the ledger's counts are ceilings as much as floors — so rates are built through
`_helpers.cost_rate_in_default_book`, which carries the first for its callers,
and the other two are never passed at all because the model's defaults are
already what every case here wants.
"""

import json
from importlib import import_module

from django.db import (IntegrityError, connection, migrations as operations,
                       transaction)
from django.db.migrations.loader import MigrationLoader
from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.models import NAMES_ONE_QUANTITY_CHECK, Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    cost_book, cost_rate_in_default_book)
from apps.platform.audit.models import AuditRecord
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.quantities import declaration_named
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

APP_LABEL = "pricing"
CONVERSION = "0019_the_rates_quantity_name_becomes_a_reference"
PARENT = "0018_a_rate_takes_effect_from_the_moment_the_tenant_chooses"
#: The rule the check could not state — who may be INSERTed (#326, review pass).
DECLARATION_RULE = "0020_a_new_rate_names_a_declaration_or_is_refused"
DECLARATION_TRIGGER = "trg_rate_names_a_declaration"

#: The column the conversion removed, named once here because the historical
#: model this module replays is the only thing that still has it.
TEXT_COLUMN = "measurement_key"

DECLARED_NAME = "input_tokens"
UNDECLARED_NAME = "typo_tokens"

#: The partial unique index the conversion rebuilt over the reference. Named
#: because every refusal here asserts WHICH mechanism refused: several on this
#: table answer `IntegrityError` and they hold entirely different things.
ACTIVE_ROW_UNIQUE = "uq_rate_active_in_book"


def _migration():
    return MigrationLoader(connection).get_migration(APP_LABEL, CONVERSION)


def _tenant(name="T"):
    return Tenant.objects.create(name=name, default_currency="usd")


class TheConversionIsHandOrderedTest(TestCase):
    """ADR-0007 §1, read off the migration rather than off its message.

    The rule's failure mode leaves no trace: an `AddField` beside a
    `RemoveField` produces a column of the right shape holding none of the data,
    and every assertion about the new field passes straight over it. What
    separates this migration from that one is not the operations it uses — it
    uses both — but that something carries the data BETWEEN them, and that the
    something reverses.
    """

    def setUp(self):
        self.operations = _migration().operations

    def _index_of(self, op_type, **match):
        for index, op in enumerate(self.operations):
            if isinstance(op, op_type) and all(
                    getattr(op, key) == value for key, value in match.items()):
                return index
        self.fail(f"the conversion carries no {op_type.__name__} {match}")

    def test_the_data_moves_before_the_column_goes(self):
        """The whole of the rule, as three positions in one list."""
        self.assertLess(self._index_of(operations.AddField, name="measurement"),
                        self._index_of(operations.RunPython))
        self.assertLess(self._index_of(operations.RunPython),
                        self._index_of(operations.RemoveField, name=TEXT_COLUMN))

    def test_the_objects_over_the_column_go_before_the_data_moves(self):
        """The ordering that makes the REVERSE work, which is easy to get wrong.

        Operations un-apply in reverse, so dropping the two database objects
        first is what rebuilds them last — after the reverse has put the names
        back. Built in the obvious order, the reverse would rebuild a partial
        unique index over a column every row had just been handed the same empty
        string in, and the migration would be reversible only against an empty
        table.
        """
        moves_data = self._index_of(operations.RunPython)
        for dropped in (operations.RemoveIndex, operations.RemoveConstraint):
            with self.subTest(operation=dropped.__name__):
                self.assertLess(self._index_of(dropped), moves_data)
        for rebuilt in (operations.AddIndex, operations.AddConstraint):
            with self.subTest(operation=rebuilt.__name__):
                self.assertGreater(self._index_of(rebuilt), moves_data)

    def test_the_reverse_is_not_a_noop(self):
        """A reverse nobody wrote is a `noop` with better manners.

        That it also RUNS is `TheReverseIsExercisedTest` below; this is the
        cheap half, and it is here because the expensive half would pass on a
        migration whose reverse silently did nothing to a table with no rows.
        """
        run_python = self.operations[self._index_of(operations.RunPython)]
        self.assertIsNot(run_python.reverse_code, operations.RunPython.noop)

    def test_every_operation_can_be_reversed(self):
        for op in self.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)

    def test_the_autodetector_did_not_write_this(self):
        """The tell, and it is the one thing a reader can check by eye.

        Run without a terminal, `makemigrations` never asks whether a column was
        renamed — it writes the add-plus-remove and names the functions nothing.
        Both halves of this migration's data function are named for what they
        do, which is not proof of authorship but IS the property that goes
        missing when somebody regenerates the file to fix a conflict.
        """
        run_python = self.operations[self._index_of(operations.RunPython)]
        self.assertEqual(run_python.code.__name__,
                         "point_each_rate_at_its_declaration")
        self.assertEqual(run_python.reverse_code.__name__,
                         "restore_the_name_as_text")


class TheReverseIsExercisedTest(TestCase):
    """Forward and back, against a real database, with rows of both kinds.

    The conversion's callables run against the state they see inside the
    migration: the two new columns present, the text column not yet dropped. The
    live table has moved on — that column went in this migration — so `setUp`
    reconciles the table with the historical model that writes to it, for this
    test's own duration, exactly as `usage/tests/test_posting_measurement.py`
    does for the fold it replays.

    IT ALSO DROPS THE CHECK, and that is not a convenience. The constraint
    describes the world AFTER the conversion: every rate names its quantity
    exactly once, through one of two columns. The rows this test writes are
    pre-conversion rows, which name it through neither — that is what the
    conversion is for. Replaying a migration means reconstructing the table it
    ran against, and a rule added by the migration is part of what has to come
    off. PostgreSQL runs DDL inside the transaction this `TestCase` rolls back,
    so nothing here outlives the test.
    """

    def setUp(self):
        loader = MigrationLoader(connection)
        self.migration = loader.get_migration(APP_LABEL, CONVERSION)
        # Every node this conversion depends on, read off the migration rather
        # than named: the parent alone is not enough, because the reference it
        # adds points into another app and a state that has never heard of that
        # app cannot resolve it.
        state = loader.project_state(
            [tuple(node) for node in self.migration.dependencies])
        for op in self.migration.operations:
            if isinstance(op, operations.AddField):
                op.state_forwards(APP_LABEL, state)
        self.historical = state.apps
        self.Rate = self.historical.get_model(APP_LABEL, "Rate")
        self._reconcile(self.Rate)
        self.run_python = next(op for op in self.migration.operations
                               if isinstance(op, operations.RunPython))

    def _reconcile(self, model):
        """Make the live table accept the historical model's writes."""
        table = model._meta.db_table
        with connection.cursor() as cursor:
            live = {column.name: column for column in
                    connection.introspection.get_table_description(
                        cursor, table)}
        with connection.schema_editor() as editor:
            for field in model._meta.local_fields:
                if field.column not in live:
                    editor.add_field(model, field)
        # AND A COLUMN THE HISTORICAL MODEL HAS NEVER HEARD OF LOSES ITS
        # `NOT NULL`, for the same reason the check and the trigger come off
        # below: it is not part of the table this migration ran against.
        #
        # ⚠ **A LATER *RENAME* IS WHAT MAKES THIS BITE, AND IT LOOKS NOTHING
        # LIKE ONE.** The historical model writes every column it knows and
        # Django keeps no database-level defaults, so a column added after this
        # migration is simply absent from the INSERT — harmless while every such
        # column is nullable. #366 renamed a NOT NULL column that this state
        # knows under its OLD name: the loop above helpfully re-adds the old
        # spelling, the new one is left out of the INSERT, and the write fails
        # on a column whose value the historical row genuinely has, under
        # another name. Reconstructing the older table is the honest repair; the
        # alternative is teaching this fixture every future rename.
        known = {field.column for field in model._meta.local_fields}
        with connection.cursor() as cursor:
            for name, column in live.items():
                if name not in known and not column.null_ok:
                    cursor.execute(
                        f"ALTER TABLE {connection.ops.quote_name(table)} "
                        f"ALTER COLUMN {connection.ops.quote_name(name)} "
                        f"DROP NOT NULL")
        with connection.cursor() as cursor:
            cursor.execute(
                f"ALTER TABLE {connection.ops.quote_name(table)} "
                f"DROP CONSTRAINT IF EXISTS {NAMES_ONE_QUANTITY_CHECK}")
            # And the rule `0020` installs, for the same reason and one more:
            # the rows this test writes are pre-conversion rows, which reference
            # no declaration BECAUSE the conversion has not run — that is the
            # state it exists to fix. A rule added AFTER the migration being
            # replayed is not part of the table it ran against.
            cursor.execute(
                f"DROP TRIGGER IF EXISTS {DECLARATION_TRIGGER} "
                f"ON {connection.ops.quote_name(table)}")

    def _run(self, code):
        with connection.schema_editor() as editor:
            code(self.historical, editor)

    def _rate(self, tenant, name):
        return self.Rate.objects.create(
            tenant_id=tenant.id, valid_from=timezone.now(),
            **{TEXT_COLUMN: name})

    def test_a_declared_name_becomes_the_reference_and_comes_back(self):
        tenant = _tenant()
        declaration = declares_a_quantity(tenant, DECLARED_NAME)
        rate = self._rate(tenant, DECLARED_NAME)

        self._run(self.run_python.code)

        rate.refresh_from_db()
        self.assertEqual(rate.measurement_id, declaration.id)
        self.assertEqual(rate.undeclared_measurement_key, "")

        # Blanked first: a reverse that wrote nothing at all would otherwise
        # pass on the value the forward pass never removed.
        self.Rate.objects.filter(pk=rate.pk).update(**{TEXT_COLUMN: ""})

        self._run(self.run_python.reverse_code)

        self.assertEqual(
            self.Rate.objects.values_list(TEXT_COLUMN, flat=True).get(pk=rate.pk),
            DECLARED_NAME)

    def test_a_name_no_declaration_matches_is_deactivated_and_comes_back(self):
        """The population the conversion exists to be careful with.

        Three claims in one pass, because they are three ways of getting this
        wrong: the row is still there (not deleted), it references nothing (not
        repointed at the declaration sitting next to it), and its name survives
        — which is both the evidence a tenant needs and the only thing the
        reverse can rebuild the column from.
        """
        tenant = _tenant()
        declares_a_quantity(tenant, DECLARED_NAME)
        placed = self._rate(tenant, DECLARED_NAME)
        deactivated = self._rate(tenant, UNDECLARED_NAME)

        self._run(self.run_python.code)

        self.assertEqual(self.Rate.objects.filter(pk=deactivated.pk).count(), 1)
        deactivated.refresh_from_db()
        self.assertIsNone(deactivated.measurement_id)
        self.assertEqual(deactivated.undeclared_measurement_key, UNDECLARED_NAME)
        placed.refresh_from_db()
        self.assertIsNotNone(placed.measurement_id)

        self.Rate.objects.all().update(**{TEXT_COLUMN: ""})

        self._run(self.run_python.reverse_code)

        self.assertEqual(
            dict(self.Rate.objects.values_list("pk", TEXT_COLUMN)),
            {placed.pk: DECLARED_NAME, deactivated.pk: UNDECLARED_NAME})

    def test_the_earliest_declaration_wins_where_a_name_is_declared_twice(self):
        """Locality means one tenant can carry one name under two Event Types.

        Which one a rate ends up referencing changes nothing it prices — the
        resolver matches on the name — but it must be the same one the live
        lookup would pick, or two rates written for one name in one book stop
        colliding and the rebuilt unique constraint quietly stops refusing what
        it refused before.
        """
        tenant = _tenant()
        first = declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        second = Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        rate = self._rate(tenant, DECLARED_NAME)

        self._run(self.run_python.code)

        rate.refresh_from_db()
        self.assertEqual(rate.measurement_id, first.id)
        self.assertNotEqual(rate.measurement_id, second.id)
        self.assertEqual(
            declaration_named(tenant=tenant, measurement_key=DECLARED_NAME).id,
            rate.measurement_id)

    def test_another_tenants_declaration_is_not_borrowed(self):
        """The one direction this must never point.

        A backfill matching on the name alone would hand one tenant's rate the
        other tenant's declaration, and every later read would be a cross-tenant
        one. Nothing about the name says who declared it.
        """
        mine, theirs = _tenant("mine"), _tenant("theirs")
        declares_a_quantity(theirs, DECLARED_NAME)
        rate = self._rate(mine, DECLARED_NAME)

        self._run(self.run_python.code)

        rate.refresh_from_db()
        self.assertIsNone(rate.measurement_id)
        self.assertEqual(rate.undeclared_measurement_key, DECLARED_NAME)


class ARateNamingAnUndeclaredQuantityIsRefusedTest(TestCase):
    """The point of the conversion, asked at both doors it has.

    A typo used to sit on a rate matching nothing, costing nothing and looking
    configured. The tenant-facing answer is a 422 naming the fix; the answer for
    every other door — a script, a shell, a later service — is the database's,
    because a model-level guard is not enforcement (ADR-0007 §2).
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Refusal", products=["metering"], default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="rates")
        self.http = Client()
        # Built through the helper rather than over the route: the book create
        # body names the cost/price discriminator, which is a retired word slice
        # 4 owns and whose ledger count is a ceiling as much as a floor.
        self.book = cost_book(self.tenant, key="openai", provider="openai").id

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _add_rate(self, measurement_key):
        return self._post(
            f"/api/v1/metering/pricing/rate-cards/{self.book}/rates",
            {"measurement_key": measurement_key, "provider": "openai",
             "rate_per_unit_micros": 5})

    def test_the_route_refuses_a_name_this_tenant_has_not_declared(self):
        self.assertFalse(
            Measurement.objects.filter(code=UNDECLARED_NAME).exists())

        response = self._add_rate(UNDECLARED_NAME)

        self.assertEqual(response.status_code, 422, response.content)
        body = response.json()
        self.assertEqual(body["code"], "validation_error")
        # The name the tenant sent, and what to do about it. A refusal that
        # named neither would send them to read the source.
        self.assertIn(UNDECLARED_NAME, body["detail"])
        self.assertIn("declare", body["detail"])

    def test_the_same_name_is_accepted_once_it_is_declared(self):
        """The control. Without it the refusal above passes on a broken route."""
        declares_a_quantity(self.tenant, UNDECLARED_NAME)

        response = self._add_rate(UNDECLARED_NAME)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["measurement_key"], UNDECLARED_NAME)

    def test_the_refusal_spends_nothing(self):
        """A refusal placed under a write spends what it refuses (#324).

        This route writes twice — the rate, and the audit record beside it — and
        the lookup that refuses is a pure read, so it hoists above both for
        free. **Today that ordering is structural rather than chosen**: the
        create needs the declaration the lookup returns, so it cannot precede
        it, and this test cannot be made red by moving the lookup.

        It is here for what a diff will not show later. A refused write on this
        route is expected to leave the tenant's account exactly as it was, and
        the way that stops being true is a NEW write appearing above the
        refusal — the shape #324 shipped and had to unpick, where an
        admission-time write recorded against a request that recorded nothing.
        A statement of the property, not a mutation of it.
        """
        rates = Rate.objects.count()
        # Every audit entry this tenant has, not the one this route writes: the
        # claim is that the refusal recorded NOTHING, and a per-action check
        # would pass while some other entry rode along beside it.
        recorded = AuditRecord.objects.filter(tenant_id=self.tenant.id).count()

        self.assertEqual(self._add_rate(UNDECLARED_NAME).status_code, 422)

        self.assertEqual(Rate.objects.count(), rates)
        self.assertEqual(
            AuditRecord.objects.filter(tenant_id=self.tenant.id).count(),
            recorded)

    def test_the_database_refuses_a_new_rate_naming_an_undeclared_quantity(self):
        """THE DOOR THE ROUTE IS NOT STANDING AT, and the check does not close it.

        `ck_rate_names_one_quantity` was written to. It cannot: a check is
        evaluated against one row and is satisfied by a rate INSERTED with no
        reference and a loose name — which is exactly the defect this slice
        deletes, one `Rate.objects.create` away from the route that refuses it.
        Review found that; `0020`'s `BEFORE INSERT` trigger is what actually
        closes it, and the message it raises carries the name that was refused.
        """
        self.assertFalse(
            Measurement.objects.filter(code=UNDECLARED_NAME).exists())
        with self.assertRaisesRegex(IntegrityError, UNDECLARED_NAME):
            Rate.objects.create(tenant=self.tenant,
                                undeclared_measurement_key=UNDECLARED_NAME)

    def test_a_row_may_not_claim_both_a_declaration_and_a_loose_name(self):
        """The check, on the write where it IS the mechanism.

        Exactly one of the two columns says which quantity a rate prices. A row
        carrying both would make `measurement_key` a question with two answers,
        which is the shape ADR-0006 §4 refuses everywhere else.

        The trigger does not fire here — its `WHEN` clause asks whether the
        reference is null and this row has one — so the refusal is the check's,
        and the assertion says which. Insert order matters on this table now: a
        `BEFORE` trigger runs ahead of the table's checks, so a test that drove
        this shape with a null reference would be asserting the other rule while
        reading as though it asserted this one.
        """
        declaration = declares_a_quantity(self.tenant, DECLARED_NAME)
        with self.assertRaisesRegex(IntegrityError, NAMES_ONE_QUANTITY_CHECK):
            Rate.objects.create(tenant=self.tenant, measurement=declaration,
                                undeclared_measurement_key=UNDECLARED_NAME)

    def test_a_deactivated_rate_may_not_be_stripped_of_its_name(self):
        """The check's other case, which only an UPDATE can reach.

        A placeless rate that lost its name would price nothing and say nothing
        — unreadable, unfixable, and indistinguishable from a row somebody meant
        to leave empty. The trigger cannot hold this: it fires on INSERT, and
        this row was not inserted, it was left behind by the conversion.
        """
        rate = cost_rate_in_default_book(self.tenant,
                                         measurement_key=DECLARED_NAME)
        Rate.objects.filter(pk=rate.pk).update(
            measurement=None, undeclared_measurement_key=UNDECLARED_NAME)

        with self.assertRaisesRegex(IntegrityError, NAMES_ONE_QUANTITY_CHECK):
            Rate.objects.filter(pk=rate.pk).update(
                undeclared_measurement_key="")


class TheDeclarationTriggerReversesTest(TestCase):
    """`0020` installs a rule; dropping it puts the table back.

    A reverse nobody has run is a `noop` with better manners — and this one has
    real work to undo, since a trigger and its function both outlive the
    migration that made them. Driven the way `0018`'s is: the refusal fires,
    the reverse runs, the same write is then accepted, and the forward runs
    again so the class leaves the table as it found it.
    """

    def setUp(self):
        self.tenant = _tenant()
        self.migration = MigrationLoader(connection).get_migration(
            APP_LABEL, DECLARATION_RULE)
        (self.rule,) = [op for op in self.migration.operations
                        if isinstance(op, operations.RunPython)]

    def _run(self, code):
        with connection.schema_editor() as editor:
            code(None, editor)

    def _refused(self):
        """The write, in its own transaction.

        A failed statement poisons the surrounding one until it is rolled back,
        and this test issues three — so each refusal is fenced or the second
        write reports the first one's failure.
        """
        with transaction.atomic():
            Rate.objects.create(tenant=self.tenant,
                                undeclared_measurement_key=UNDECLARED_NAME)

    def test_the_refusal_goes_away_and_comes_back(self):
        with self.assertRaisesRegex(IntegrityError, UNDECLARED_NAME):
            self._refused()

        self._run(self.rule.reverse_code)
        # Accepted with the rule gone, which is what proves the rule was doing
        # the refusing rather than something else on this table.
        self._refused()

        self._run(self.rule.code)
        with self.assertRaisesRegex(IntegrityError, UNDECLARED_NAME):
            self._refused()


class ADeactivatedRateKeepsItsNameAndPricesNothingTest(TestCase):
    """What a tenant sees afterwards, which is the reason for the rule.

    Deleting the row would have destroyed the evidence they need to fix it;
    repointing it would have invented a declaration they never made. So it stays,
    it still says what it was written to price, and it prices nothing.
    """

    def setUp(self):
        self.tenant = _tenant()
        self.rate = cost_rate_in_default_book(
            self.tenant, provider="openai", measurement_key=DECLARED_NAME,
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)
        # What the conversion leaves behind, written directly because the route
        # can no longer produce it — which is the point of the refusal above.
        Rate.objects.filter(pk=self.rate.pk).update(
            measurement=None, undeclared_measurement_key=UNDECLARED_NAME)
        self.rate.refresh_from_db()

    def test_it_still_answers_with_the_name_it_was_written_with(self):
        self.assertEqual(self.rate.measurement_key, UNDECLARED_NAME)

    def test_it_resolves_against_nothing_including_its_own_name(self):
        for name in (UNDECLARED_NAME, DECLARED_NAME):
            with self.subTest(quantity=name):
                self.assertIsNone(PricingService._resolve_card(
                    self.tenant, None, "cost", {"provider": "openai"}, name,
                    "usd", timezone.now()))

    def test_it_is_still_there(self):
        self.assertTrue(Rate.objects.filter(pk=self.rate.pk).exists())


class TheRebuiltObjectsStillEnforceWhatTheyDidTest(TestCase):
    """The unique constraint, driven rather than read.

    `test_the_rates_quantity_name_takes_the_canonical_name.py` asserts that both
    objects now name the reference; this asserts the one that has behaviour
    still HAS it. The two are different claims and the gap between them is where
    a rewritten constraint quietly stops refusing.
    """

    def test_two_active_rates_for_one_quantity_in_one_book_still_collide(self):
        tenant = _tenant()
        cost_rate_in_default_book(tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)
        # The constraint by name, not "something refused this": this index, the
        # check, the reference's foreign key and two triggers all answer
        # `IntegrityError` on this table, and the rule the models file states
        # for its own check applies here first.
        with self.assertRaisesRegex(IntegrityError, ACTIVE_ROW_UNIQUE):
            cost_rate_in_default_book(tenant, provider="openai",
                                      measurement_key=DECLARED_NAME)

    def test_the_pair_still_collides_when_the_name_is_declared_twice(self):
        """The case the conversion could have lost, and the reason for the pick.

        Two Event Types may each declare `input_tokens`; they are two records
        that happen to share a spelling. Resolution matches on the spelling, so
        two rates naming it in one book are still two rates that both match one
        event — and if the write had resolved the name to whichever declaration
        it liked, they would reference different rows and the constraint would
        let both stand. The lookup being deterministic is what keeps this red.
        """
        tenant = _tenant()
        declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)

        cost_rate_in_default_book(tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)
        with self.assertRaisesRegex(IntegrityError, ACTIVE_ROW_UNIQUE):
            cost_rate_in_default_book(tenant, provider="openai",
                                      measurement_key=DECLARED_NAME)


class ResolutionStillMatchesOnTheNameTest(TestCase):
    """WHAT THIS COMMIT DELIBERATELY DID NOT CHANGE.

    A rate holds the declared record now, and the tempting next step — match on
    that record instead of on its name — is a different rule wearing the same
    words. Declarations are Event-Type-local, so a rate with the Event Type
    unpinned prices the quantity under every Event Type that declares it, and
    identity matching would narrow that to one of them with nothing announcing
    the change. `Measurement`'s own docstring called this before the reference
    existed: *a Cost Rate still matches on `measurement_key`*.
    """

    def test_a_rate_prices_the_name_under_an_event_type_it_does_not_reference(self):
        tenant = _tenant()
        # Declared under one Event Type...
        declares_a_quantity(tenant, DECLARED_NAME, key="first.call")
        # ...and independently under another, which is a different record that
        # happens to share a spelling.
        Measurement.objects.create(
            event_type=EventType.objects.create(
                tenant=tenant, key="second.call",
                costing_method=COSTING_METHOD_CALCULATED),
            code=DECLARED_NAME, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        rate = cost_rate_in_default_book(
            tenant, provider="openai", measurement_key=DECLARED_NAME,
            rate_per_unit_micros=5_000, unit_quantity=1_000_000)

        resolved = PricingService._resolve_card(
            tenant, None, "cost", {"provider": "openai",
                                   "event_type": "second.call"},
            DECLARED_NAME, "usd", timezone.now())

        self.assertEqual(resolved.id, rate.id)
        self.assertNotEqual(rate.measurement.event_type.key, "second.call")


class AQuantityARatePricesCannotBeWithdrawnTest(TestCase):
    """`PROTECT`, rendered as a 409 rather than as a 500.

    The refusal is the one `withdraw_event_category` already makes for the same
    shape. The alternative was to withdraw the declaration and deactivate the
    rates behind it, which would rewrite a tenant's pricing on their behalf.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Withdraw", products=["metering"], default_currency="usd")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="withdraw")
        self.http = Client()
        self.declaration = declares_a_quantity(self.tenant, DECLARED_NAME)
        self.path = (f"/api/v1/event-types/"
                     f"{self.declaration.event_type.key}/measurements/"
                     f"{DECLARED_NAME}")

    def _withdraw(self):
        return self.http.delete(
            self.path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def test_it_is_refused_while_a_rate_prices_it(self):
        cost_rate_in_default_book(self.tenant, provider="openai",
                                  measurement_key=DECLARED_NAME)

        response = self._withdraw()

        self.assertEqual(response.status_code, 409, response.content)
        self.assertEqual(response.json()["code"], "conflict")
        self.assertIn(DECLARED_NAME, response.json()["detail"])
        self.assertTrue(
            Measurement.objects.filter(pk=self.declaration.pk).exists())

    def test_it_is_withdrawn_when_nothing_prices_it(self):
        """The control: the refusal above is about the rate, not about the route."""
        self.assertEqual(self._withdraw().status_code, 204)
        self.assertFalse(
            Measurement.objects.filter(pk=self.declaration.pk).exists())
