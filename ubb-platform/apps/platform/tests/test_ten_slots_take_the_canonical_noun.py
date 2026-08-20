"""Ten slots, no per-slot index, and the columns under the canonical noun (#276).

Three claims land together and each one is here because the other two make it
cheap to get wrong.

**Ten, not six.** #273 closed the free-form grouping escape hatch, so demand that
used to land in the open bag has to arrive declared or not at all. Ten is v1
product headroom for that. The four always-present axes are untouched, which is
what stops "ten" quietly meaning "six plus the four you already had".

**No slot carries an index.** Six of them used to, on top of a composite that led
with two — seven index writes per row on the hottest insert path. Widening under
that arrangement would have taxed every insert for capacity nobody is using yet.
:class:`NoSlotCarriesAnIndexTest` is the half of that claim a migration cannot
make on its own: an operation list says what was asked for, and only the live
catalogue says what is there.

**The columns take the canonical noun.** Not because the forbidden-term sweep
demanded it — the abbreviation they carried is not a whole-token match for the
retired word and the sweep never counted it — but because ADR-0006 §2 refuses a
short form beside a long form, and because these columns were being rebuilt
anyway.

**THE RETIRED SPELLING IS READ OFF THE MIGRATIONS, NOT TYPED — AND NOT FOR THE
USUAL REASON.** #274 and #275 derived theirs because spelling a swept word in a
living test module would have re-opened an extent the same commit was paying
off. That does not apply here: this abbreviation is not a swept term, and this
module could spell it freely. It is derived anyway because the derivation is a
stronger assertion than the assertion it feeds — it pins that the migration
renames these six columns and no others, so a seventh rename, or a rename of
something else, fails here rather than passing quietly.

**What this module does not cover, deliberately.** The registry's own invariants
— slot rebinding, scope change, the cardinality cap, the two refusal lists, and a
retired field staying resolvable — live in ``test_grouping_field_invariants.py``,
re-pointed by this ticket to exercise all ten slots rather than a hard-coded
first one. Re-asserting them here would put two copies of one rule in two files,
and this is the copy that would rot.
"""

import json
from functools import cache
from importlib import import_module

from django.db import connection, migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import SimpleTestCase, TestCase

from api.v1.openapi_export import GIT_ROOT
from apps.metering.pricing.models import Rate
from apps.metering.usage.models import Posting
from apps.platform.grouping_fields.models import (
    RESERVED_KEYS, SLOT_CHOICES, SLOT_MAX_LENGTH, GroupingField,
)
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task

REGISTRY_APP = "grouping_fields"
REWRITE_MIGRATION = "0004_the_stored_slot_identifier_takes_the_canonical_noun"
REGISTRY_PARENT = "0003_the_grouping_field_takes_its_name"

#: The three tables that hold slot values, and the migration that reshaped each.
#: Named rather than discovered: a walk that found two of the three would report
#: success exactly as loudly as one that found all three.
RESHAPED = (
    (Posting, "usage", "0035_ten_slots_and_the_six_per_slot_indexes_dropped"),
    (Rate, "pricing", "0017_ten_slots_on_the_rate"),
    (Task, "work", "0013_ten_slots_on_the_task"),
)

#: The composite that led with two slots, and the two that lead with the columns
#: a slot query actually filters on.
RETIRED_COMPOSITE = "idx_usage_dim_attribution"
SURVIVING_COMPOSITES = {
    "idx_usage_tenant_effective": ["tenant_id", "effective_at"],
    "idx_usage_customer_effective": ["customer_id", "effective_at"],
}

SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)


def _operations(app_label, migration_name):
    return import_module(
        f"apps.{'platform' if app_label in ('grouping_fields', 'work') else 'metering'}"
        f".{app_label}.migrations.{migration_name}").Migration.operations


def _renames(app_label, migration_name):
    """{retired: canonical} read off one migration's `RenameField` operations."""
    return {op.old_name: op.new_name
            for op in _operations(app_label, migration_name)
            if isinstance(op, operations.RenameField)}


def _additions(app_label, migration_name):
    return [op.name for op in _operations(app_label, migration_name)
            if isinstance(op, operations.AddField)]


@cache
def schemas():
    """The published contract's schema block."""
    return json.loads(
        (GIT_ROOT / "openapi" / "v1.json").read_text(encoding="utf-8")
    )["components"]["schemas"]


def _constraints(table):
    with connection.cursor() as cursor:
        return connection.introspection.get_constraints(cursor, table)


def _columns(table):
    with connection.cursor() as cursor:
        return {column.name for column in
                connection.introspection.get_table_description(cursor, table)}


class TheRegistryDeclaresTenSlotsTest(SimpleTestCase):
    """The count, and the four axes it deliberately does not include."""

    def test_there_are_ten(self):
        self.assertEqual(len(SLOT_CHOICES), 10)

    def test_they_are_numbered_one_to_ten_under_the_canonical_noun(self):
        self.assertEqual(SLOTS,
                         tuple(f"grouping_field_{i}" for i in range(1, 11)))

    def test_the_four_always_present_axes_are_unchanged(self):
        """Ten TENANT slots, on top of these — not ten in total.

        These four are never declared and never retired, and a widening that
        quietly absorbed them would leave a tenant six new slots rather than
        four, with four of its axes suddenly re-declarable.
        """
        self.assertEqual(RESERVED_KEYS,
                         ("provider", "event_type", "task_type", "subtask_type"))
        for axis in RESERVED_KEYS:
            with self.subTest(axis=axis):
                self.assertNotIn(axis, SLOTS)

    def test_the_widest_identifier_is_seventeen_characters(self):
        """The literal the migration had to hard-code, pinned from the outside.

        `SLOT_MAX_LENGTH` is DEFINED as this maximum, so asserting the two are
        equal would be asserting the definition — green whatever the vocabulary
        said. The number is written out instead, because a migration cannot
        import a module-level constant and expect it to mean the same thing
        forever: `0004`'s `max_length=17` is frozen, and this is what holds the
        live vocabulary to it.
        """
        self.assertEqual(max(len(slot) for slot in SLOTS), 17)


class TheStoredSlotColumnIsWideEnoughTest(TestCase):
    """Asked of Postgres, which is the only place the answer can be wrong.

    Three declarations have to agree about how wide this column is: the
    vocabulary, the model field, and migration `0004`'s frozen literal. The
    model field is derived from the vocabulary so those two cannot disagree —
    but the migration cannot be, and the LIVE column is whatever the migration
    built. A migration that said `max_length=8` would leave every canonical
    identifier truncating on write, and nothing else in this module would
    notice: a truncated slot is still a string, and the registry would simply
    stop resolving.
    """

    def test_the_live_column_admits_the_widest_identifier(self):
        """Read from `information_schema` rather than through Django.

        `get_table_description` builds its `FieldInfo` from the driver's cursor
        description, and psycopg reports no length for `varchar` there —
        `internal_size` comes back `None`, which compares against nothing. The
        catalogue knows.
        """
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT character_maximum_length FROM information_schema.columns "
                "WHERE table_name = %s AND column_name = %s",
                [GroupingField._meta.db_table, "slot"])
            (width,) = cursor.fetchone()
        self.assertIsNotNone(width, "the slot column is not a bounded varchar")
        self.assertGreaterEqual(width, max(len(slot) for slot in SLOTS))

    def test_the_widest_identifier_round_trips_through_the_database(self):
        """The behaviour the width is for, driven rather than measured.

        Postgres truncates silently only under some settings and errors under
        others, so reading the declared width proves the declaration and not the
        outcome. This writes the longest slot there is and reads it back.
        """
        widest = max(SLOTS, key=len)
        field = GroupingField.objects.create(
            tenant=Tenant.objects.create(name="T"), key="region", slot=widest,
            scope="task")
        self.assertEqual(GroupingField.objects.get(id=field.id).slot, widest)


class EveryTableThatHoldsSlotsHasTenOfThemTest(TestCase):
    """The three tables, each asked about its model AND about its columns.

    A field renamed on the model with no migration behind it leaves the old
    column in the database, where a raw query would still find it — so both
    halves are asked separately rather than one being inferred from the other.
    """

    def test_the_six_renames_are_exactly_the_six_slots(self):
        for model, app_label, migration in RESHAPED:
            with self.subTest(model=model.__name__):
                renames = _renames(app_label, migration)
                self.assertEqual(sorted(renames.values()),
                                 sorted(SLOTS[:6]))

    def test_the_four_additions_are_exactly_the_new_slots(self):
        for model, app_label, migration in RESHAPED:
            with self.subTest(model=model.__name__):
                self.assertEqual(sorted(_additions(app_label, migration)),
                                 sorted(SLOTS[6:]))

    def test_no_slot_was_dropped_and_re_added(self):
        """ADR-0007 §1, asked of the operations rather than of the commit message.

        An `AddField` beside a `RemoveField` produces a column of the right name
        holding none of the data, and every other assertion in this module would
        pass straight over it. `AddField` alone is legitimate here — four of
        these columns never existed — so what is forbidden is the removal.

        Nested operations are walked: `SeparateDatabaseAndState` carries two
        lists of its own, and a removal hidden in either is invisible to a check
        that reads only the top level.
        """
        for _, app_label, migration in RESHAPED:
            for op in self._every_operation(app_label, migration):
                with self.subTest(app=app_label, operation=type(op).__name__):
                    self.assertNotIsInstance(op, operations.RemoveField)

    @staticmethod
    def _every_operation(app_label, migration):
        for op in _operations(app_label, migration):
            yield op
            yield from getattr(op, "database_operations", ())
            yield from getattr(op, "state_operations", ())

    def test_the_model_carries_the_ten_and_not_the_retired_six(self):
        for model, app_label, migration in RESHAPED:
            names = {f.name for f in model._meta.get_fields()}
            for canonical in SLOTS:
                with self.subTest(model=model.__name__, slot=canonical):
                    self.assertIn(canonical, names)
            for retired in _renames(app_label, migration):
                with self.subTest(model=model.__name__, retired=retired):
                    self.assertNotIn(retired, names)

    def test_the_table_carries_the_ten_and_not_the_retired_six(self):
        for model, app_label, migration in RESHAPED:
            columns = _columns(model._meta.db_table)
            for canonical in SLOTS:
                with self.subTest(table=model._meta.db_table, slot=canonical):
                    self.assertIn(canonical, columns)
            for retired in _renames(app_label, migration):
                with self.subTest(table=model._meta.db_table, retired=retired):
                    self.assertNotIn(retired, columns)


class NoSlotCarriesAnIndexTest(TestCase):
    """Read off the live catalogue, because that is the only place it is true.

    A migration's operation list records what was asked for. This asks Postgres
    what is actually built over ``ubb_posting`` — which is the question that
    matters, since the cost this ticket is removing is paid per insert by
    whatever the catalogue says, not by whatever the migration said.
    """

    def setUp(self):
        self.objects = _constraints(Posting._meta.db_table)

    def test_the_slot_columns_are_there_to_be_indexed(self):
        """The vacuity guard.

        Every assertion below is of the form "no database object covers a slot".
        If the columns were missing or spelled differently, all of them would
        hold for the wrong reason and this file would read as a green board over
        a table that had lost its slots entirely.
        """
        self.assertTrue(set(SLOTS) <= _columns(Posting._meta.db_table))

    def test_no_index_covers_a_slot(self):
        for name, spec in self.objects.items():
            if not (spec["index"] or spec["unique"] or spec["primary_key"]):
                continue
            with self.subTest(object=name):
                self.assertFalse(
                    set(spec["columns"]) & set(SLOTS),
                    f"{name} still covers a slot: {spec['columns']}")

    def test_the_composite_that_led_with_two_slots_is_gone(self):
        """Named, so that "no index covers a slot" cannot pass by accident.

        The check above would also hold if this index had been left in place
        over some OTHER pair of columns, or renamed. This one asks for the
        specific object by the specific name it had.
        """
        self.assertNotIn(RETIRED_COMPOSITE, self.objects)

    def test_the_surviving_composites_match_a_real_query_shape(self):
        """What replaced it, and why nothing replaced it in kind.

        No query selects rows by a slot. Every read of one is a `GROUP BY` of a
        single slot inside a tenant (sometimes a customer) and an `effective_at`
        window, so the columns that select the rows are the two below and the
        slot is only the group key. The lone predicate on a slot anywhere is
        `get_dimensional_margin`'s `.exclude(<slot>="")`, a negation no btree
        index would serve. Both indexes below already existed; the dropped
        composite was a mis-ordered variant of the first, leading with two
        columns no query selects on.
        """
        for name, expected in SURVIVING_COMPOSITES.items():
            with self.subTest(index=name):
                self.assertEqual(self.objects[name]["columns"], expected)


class TheStoredSlotIdentifierIsRewrittenBothWaysTest(TestCase):
    """THE REVERSE, DRIVEN — not asserted from `op.reversible`.

    `reversible` on a `RunPython` is `True` whenever a reverse callable was
    passed, which says nothing about whether the callable works. #274 shipped
    exactly that shape of dead gate on a `RenameField` and /code-review caught
    it. So this writes a row, runs the migration's own reverse against the real
    table, reads the value back through a raw cursor — deliberately bypassing
    the model, which is the only thing that knows the canonical spelling — and
    then runs it forwards again.

    A stored slot is not a label: it IS a column name, handed to the posting's
    `create()` as a keyword argument. A reverse that quietly did nothing would
    leave a downgraded schema whose registry names columns it no longer has.

    PostgreSQL runs this inside the transaction the `TestCase` rolls back.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        (self.rewrite,) = [op for op in
                           _operations(REGISTRY_APP, REWRITE_MIGRATION)
                           if isinstance(op, operations.RunPython)]
        loader = MigrationLoader(connection)
        self.after = loader.project_state((REGISTRY_APP, REWRITE_MIGRATION))
        self.before = loader.project_state((REGISTRY_APP, REGISTRY_PARENT))
        self.retired = _renames(*RESHAPED[0][1:])

    def _stored_slot(self, field_id):
        with connection.cursor() as cursor:
            cursor.execute(
                f"SELECT slot FROM {connection.ops.quote_name(GroupingField._meta.db_table)} "
                "WHERE id = %s", [field_id])
            (slot,) = cursor.fetchone()
        return slot

    def _run(self, forwards):
        with connection.schema_editor() as editor:
            if forwards:
                self.rewrite.database_forwards(
                    REGISTRY_APP, editor, self.before, self.after)
            else:
                self.rewrite.database_backwards(
                    REGISTRY_APP, editor, self.after, self.before)

    def test_the_identifier_survives_the_round_trip(self):
        field = GroupingField.objects.create(
            tenant=self.tenant, key="region", slot="grouping_field_2", scope="task")

        self._run(forwards=False)
        self.assertEqual(self._stored_slot(field.id),
                         {v: k for k, v in self.retired.items()}["grouping_field_2"])

        self._run(forwards=True)
        self.assertEqual(self._stored_slot(field.id), "grouping_field_2")

    def test_the_reverse_refuses_a_slot_the_old_vocabulary_cannot_express(self):
        """Slots seven to ten have nowhere to go, and the reverse says so.

        The columns behind them did not exist before this ticket. Rewriting the
        rest and leaving this one would produce a registry pointing at a column
        the downgraded schema does not have — a declared field that silently
        groups nothing. Refusing is louder and cheaper to undo, and it leaves
        the reverse available the moment the declaration is removed.
        """
        GroupingField.objects.create(
            tenant=self.tenant, key="tier", slot="grouping_field_9", scope="task")

        with self.assertRaises(RuntimeError) as refusal:
            self._run(forwards=False)
        self.assertIn("grouping_field_9", str(refusal.exception))

    def test_the_reverse_runs_when_nothing_is_bound_above_six(self):
        """The control. Without it the refusal above passes on a broken reverse."""
        GroupingField.objects.create(
            tenant=self.tenant, key="region", slot="grouping_field_6", scope="task")
        self._run(forwards=False)  # no raise
        self._run(forwards=True)

    def test_the_forward_rewrite_refuses_a_slot_it_does_not_understand(self):
        """Data neither vocabulary contains is not silently left behind.

        `choices` is not enforced by the database, so a row like this is
        reachable. Leaving it alone while rewriting its neighbours is the one
        outcome that produces a half-translated registry.
        """
        GroupingField.objects.filter(
            id=GroupingField.objects.create(
                tenant=self.tenant, key="region", slot="grouping_field_1",
                scope="task").id).update(slot="whatever")

        with self.assertRaises(RuntimeError) as refusal:
            self._run(forwards=True)
        self.assertIn("whatever", str(refusal.exception))


class SlotOrderIsNotAlphabeticalOrderTest(TestCase):
    """The trap that only exists above nine slots.

    Sorted as text, ``grouping_field_10`` falls between ``grouping_field_1`` and
    ``grouping_field_2``. The registry's read contract promises slot order, and
    the database sort that delivered it for six slots delivers something else
    for ten. Nothing else in this ticket would have failed if this had been
    missed — the values would all be correct and merely out of order.
    """

    def test_the_tenth_slot_does_not_sort_between_the_first_and_the_second(self):
        from apps.platform.grouping_fields.queries import declared_dimensions

        tenant = Tenant.objects.create(name="T")
        for position, slot in enumerate(SLOTS):
            GroupingField.objects.create(
                tenant=tenant, key=f"key_{position}", slot=slot, scope="event")

        self.assertEqual([row["slot"] for row in declared_dimensions(tenant.id)],
                         list(SLOTS))


#: The three schemas that publish a rate's selector list, and the reason they
#: are named here rather than discovered: a walk that found two would report
#: success just as loudly as one that found three.
RATE_SCHEMAS = ("RateIn", "RateChangeIn", "RateOut")


class ThePublishedContractCaughtUpWithTheWideningTest(SimpleTestCase):
    """⚠ INVERTED BY #366. This class was
    `ThePublishedContractIsUnchangedByTheWideningTest`, and its two headline
    tests asserted the opposite of what they assert now.

    **What #276 promised and why the promise expired.** Its acceptance criteria
    forbade it to rename a published property, so it widened the COLUMNS to ten
    and left the contract naming six of them under an older spelling. The two
    tests below were written to hold that line — one guarding against a future
    commit re-spelling the published properties to match the columns, the other
    proving the old spellings were still there. #193 §L put "the rate selector
    list" in slice 4 expressly "so that no ticket quietly widens", and #366 took
    it: the three schemas publish all ten slots, under the column names.

    **Each test is replaced by its successor at its own address rather than
    deleted**, which is slice 3's pattern for a tripwire and the only way a
    reader arriving at the old claim finds out what happened to it. Relaxing
    either — dropping the guard, or weakening "still carries" to "carries
    something" — would have left this file green while proving the opposite of
    what it was written to prove.

    **The gap that closed was FUNCTIONAL, not cosmetic**, and that is why the
    promise could not simply be renewed. Six published names over ten columns
    meant a reprice body left the other four empty, and empty is what matches a
    rule leaving a slot unpinned — so a rule pinned on the seventh slot was
    writable server-side and matched by no publish body at all.
    `api/v1/tests/test_a_rate_on_any_slot_can_be_repriced.py` drives that end to
    end.

    Two published values moved with #276's own widening and still hold below:
    the declaration body's item cap was the slot count, and the slot property's
    length bound was the width of the old identifiers.
    """

    def test_only_the_rate_schemas_expose_a_slot_column(self):
        """The successor to `test_no_published_schema_exposes_a_slot_column`.

        That test asserted NO schema names a slot column, as a guard against
        exactly the commit that has now happened. The guard's subject was always
        the rest of the contract rather than the rate, and that half is
        unchanged: a posting's grouping values are the TENANT's facts, keyed by
        the tenant's own declared key, so a physical slot there would leak UBB's
        internal identity for a binding the tenant knows by another name. A
        rule's selector list is the RULE's own shape — it is pinned on the
        columns it is pinned on.

        ⚠ Held as an exact set on the rate schemas rather than as a bare
        intersection, so a conversion that published four of the ten and stopped
        fails here. The whole-document form of this claim, over every property
        naming a slot in EITHER spelling, is
        `api/v1/tests/test_grouping_values_on_the_contract.py`'s equality; this
        one is the widening's own side of it and is what says the ten reached
        the contract at all.
        """
        for name, schema in schemas().items():
            with self.subTest(schema=name):
                exposed = set(schema.get("properties", {})) & set(SLOTS)
                if name in RATE_SCHEMAS:
                    self.assertEqual(exposed, set(SLOTS),
                                     f"{name} publishes some slots and not all")
                else:
                    self.assertFalse(exposed,
                                     f"{name} exposes a physical slot column")

    def test_the_rate_schemas_no_longer_carry_the_older_spelling(self):
        """The successor to
        `test_the_rate_schemas_still_carry_the_properties_they_carried`.

        That test read the retired spellings off #276's own `RenameField`
        operations and asserted the contract still published them. It is the
        same six names, read the same way, asserted the other way round — which
        is what makes this a replacement rather than a deletion, and what stops
        a rename from landing as a DELETION of the properties. The test above
        is the half that says the ten arrived; this is the half that says the
        six did not survive beside them, because two published spellings for one
        selector is the thing the join dictionary was and the thing #366 removed.
        """
        retired = _renames(*RESHAPED[1][1:])
        for name in RATE_SCHEMAS:
            with self.subTest(schema=name):
                self.assertFalse(
                    set(retired) & set(schemas()[name]["properties"]),
                    f"{name} still publishes a slot under its older spelling")

    def test_the_declaration_body_admits_one_item_per_slot(self):
        registry = schemas()["DimensionRegistryIn"]
        (listed,) = [name for name, spec in registry["properties"].items()
                     if spec.get("type") == "array"]
        self.assertEqual(registry["properties"][listed]["maxItems"], len(SLOTS))

    def test_the_slot_property_admits_the_widest_identifier(self):
        self.assertEqual(schemas()["DimensionDefIn"]["properties"]["slot"]["maxLength"],
                         SLOT_MAX_LENGTH)
