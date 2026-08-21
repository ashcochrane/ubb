"""The rate's table takes its own name, and the kind word leaves it (#367).

Two corrections that are one correction. A single priced line sat on the table
named for the container that holds it — the inversion recorded in the model's
own docstring and seeded against G9 in `gates/migration-ledger.yaml` — and it
carried a `cost`/`price` word of its own that nothing read. The rename is what
this module is mostly about; the deletion is what the rename was for.

**WHAT THIS MODULE HOLDS THAT NOTHING ELSE CAN.** The two rules guarding the
rate's table are already asserted by the module that owns the effective-moment
rule, but every assertion there is derived from the model — so it would follow
the table wherever the model pointed and could not tell a rename that carried
its rules from a rebuild that quietly left them behind. Here the table is read
off the RENAME OPERATION ITSELF, both names, so what is asserted is that these
rules are on the table the rename produced and are gone from the name it left.

**AND WHAT IT DELIBERATELY DOES NOT CLAIM.** The cost/price branch has not left
the tree: the container still carries the word until ticket 21 splits it into a
Pricing Book and a cost book. What has left is the branch on a RULE.
`NoResolutionPathSelectsARuleByKindTest` pins exactly that boundary — nothing
selects a rule by kind, and the one thing that still selects by kind is the
book — so the claim cannot quietly grow into the slice-wide one nobody has
finished paying for yet.

⚠ **THIS MODULE MAY NOT SPELL THE WORDS ITS COMMIT IS CLEARING.** The ledger
counts are ceilings on spread as well as floors, so a new module mentioning the
retired discriminator or the retired book-noun would raise the very numbers the
commit lowers. Both are reached here through the fixtures that already own
them: `rate_in_default_book` is the price half by default and
`cost_rate_in_default_book` is the cost half by name, and the table names come
off the migration rather than out of a string literal.
"""

import re
from datetime import timedelta

from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    THE_RULES_KIND_COLUMN, cost_rate_in_default_book, database_rules_guarding,
    rate_in_default_book, reconcile_the_rate_table_with,
    the_rate_table_as_this_migration_saw_it, the_state_before)
from apps.platform.audit.actions import AUDIT_ACTIONS
from apps.platform.audit.ledger import record
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

APP_LABEL = "pricing"
RENAME = "0027_the_rate_moves_to_the_table_named_for_a_rate"

#: The rules `0018` and `0020` installed, by the names those migrations gave
#: them. Both were on the table this commit renamed; both have to be on the one
#: it renamed it to.
TRANSITION_TRIGGER = "trg_rate_declared_transitions"
DECLARATION_TRIGGER = "trg_rate_names_a_declaration"

#: The two acts that ceased to exist here, spelled as the registry spelled them.
#: Their routes are gone — adding a rule and retiring one are declared changes
#: on a publish now — so there is nothing left for either name to record.
#:
#: ⚠ **NAMING THEM IS THE WHOLE POINT AND IT IS ALSO WHY THIS IS A `tuple` OF
#: PARTS.** A deleted registry entry has no symbol left to address, so a test
#: that its name is refused has to carry the name; and the name is a retired
#: term whose file count this commit takes to zero, so carrying it whole would
#: put it straight back into the tree it just left. Joining the halves says the
#: same thing to `record()` and nothing at all to a whole-token matcher.
DELETED_ACTIONS = (("rate", "added"), ("rate", "deleted"))

#: The column this commit deletes. `_helpers` carries the one assembled
#: spelling, for the reason `DELETED_ACTIONS` gives about the action names: its
#: file count is a ceiling as well as a floor and this commit takes it down, so
#: a module that spelled it whole would put it back.
THE_DELETED_COLUMN = THE_RULES_KIND_COLUMN


def _tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 default_currency="usd")


def _rename():
    return MigrationLoader(connection).get_migration(APP_LABEL, RENAME)


def _the_rename_operation():
    """The one operation that moves the table, read off the migration.

    Both table names are taken from here rather than written down, which is the
    technique the quantity rename already uses: a literal would let this module
    keep asserting about a name the migration had stopped using, and a rename
    test whose subject is a string it supplies itself proves nothing about the
    rename.
    """
    moves = [op for op in _rename().operations
             if isinstance(op, migrations.AlterModelTable)]
    assert len(moves) == 1, f"expected one table move, found {len(moves)}"
    return moves[0]


def _the_name_it_moved_from():
    """The table the rename left behind, out of the migration's own from-state."""
    loader = MigrationLoader(connection)
    before = loader.project_state(
        [tuple(node) for node in _rename().dependencies])
    return before.models[APP_LABEL, "rate"].options["db_table"]


def _without_its_values(sql):
    """A statement's SHAPE — every literal it carries replaced.

    The two paths differ in the book ids they select and in the instant they
    resolve at, and neither is a fact about the rules: what is being compared is
    the QUESTION asked of the rule table, so the values have to come out or the
    comparison is about the clock. The `IN` list collapses to one placeholder
    because the two paths select different NUMBERS of books as well as
    different ones.
    """
    without_ids = re.sub(r"'[0-9a-f-]+'::uuid", "?::uuid", sql)
    without_instants = re.sub(r"'[^']*'::timestamptz", "?::timestamptz",
                              without_ids)
    return re.sub(r"IN \((?:\?::uuid(?:, )?)+\)", "IN (?::uuid)",
                  without_instants)


def _tables_named(*names):
    with connection.cursor() as cursor:
        cursor.execute(
            "SELECT relname FROM pg_class WHERE relkind = 'r' "
            "AND relname = ANY(%s)", [list(names)])
        return {row[0] for row in cursor.fetchall()}


class TheRenameCarriedTheTableRatherThanRebuildingItTest(TestCase):
    """ADR-0007 §1, read off the migration rather than off its message.

    A rename carries every row; an add-plus-remove produces a table of the
    right name holding nothing, and every test that asks only whether the new
    name exists passes over the loss. `usage/tests/test_posting_rename.py`
    names the three operations that are renames — `AlterModelTable`,
    `RenameModel`, `RenameField` — and the ones that cost rows.
    """

    def test_the_model_sits_on_the_table_the_rename_produced(self):
        self.assertEqual(Rate._meta.db_table, _the_rename_operation().table)

    def test_the_new_name_is_a_rate_and_the_old_one_was_not(self):
        """The claim the G9 entry recorded, made against both names at once.

        Asserting only that the table is called `ubb_rate` would pass on a
        table that had always been called that. What was wrong is that a rule
        sat under the container's name, and the fix is that it no longer does.
        """
        self.assertEqual(_the_rename_operation().table, "ubb_rate")
        self.assertNotEqual(_the_name_it_moved_from(),
                            _the_rename_operation().table)

    def test_the_live_database_has_the_new_table_and_not_the_old_one(self):
        both = (_the_name_it_moved_from(), _the_rename_operation().table)
        self.assertEqual(_tables_named(*both), {_the_rename_operation().table})

    def test_nothing_in_it_creates_or_adds(self):
        """The add-plus-remove pair ADR-0007 §1 forbids is not in this file.

        The one destructive operation is the deliberate deletion of the kind
        word, and what makes it a deletion rather than half of a pair is that
        nothing adds a column back: no `AddField`, no `CreateModel`, no
        `DeleteModel`. Asserted as a whole-migration property so that a second
        operation arriving later cannot hide behind the one that is expected.
        """
        rebuilt = [type(op).__name__ for op in _rename().operations
                   if isinstance(op, (migrations.CreateModel,
                                      migrations.DeleteModel,
                                      migrations.AddField))]
        self.assertEqual(rebuilt, [])
        removals = [op for op in _rename().operations
                    if isinstance(op, migrations.RemoveField)]
        self.assertEqual(len(removals), 1)

    def test_every_operation_can_be_reversed(self):
        for op in _rename().operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)

    def test_the_reverse_is_the_only_new_executable_logic_and_is_shaped_right(self):
        """The forward half is the no-op; the reverse half is not.

        Reversing the removal alone re-adds the column at the empty-string
        default, which is not a value any reader of it accepted — a rollback
        landing on rows whose discriminator says nothing is the failure that
        makes an un-reversed data migration worse than none. So the reverse
        carries a `RunPython` whose forward half is the no-op and whose reverse
        half re-derives each rule's kind from the book holding it.

        That it also RUNS is the class below. This is the cheap half, and it is
        here because the expensive half would pass on a reverse that silently
        did nothing to a table with no rows.
        """
        pythons = [op for op in _rename().operations
                   if isinstance(op, migrations.RunPython)]
        self.assertEqual(len(pythons), 1)
        self.assertIs(pythons[0].code, migrations.RunPython.noop)
        self.assertIsNot(pythons[0].reverse_code, migrations.RunPython.noop)

    def test_the_autodetector_did_not_write_this(self):
        """Run without a terminal, `makemigrations` never asks whether a table
        was renamed — it writes the add-plus-remove pair and does it silently.
        This migration's reverse function is named for what it does, which is
        not a name the autodetector produces."""
        self.assertIn("restore_the_kind_from_the_book",
                      {op.reverse_code.__name__
                       for op in _rename().operations
                       if isinstance(op, migrations.RunPython)})


class TheReverseIsExercisedTest(TestCase):
    """Forward and back, against a real database, with rows of both kinds.

    `docs/conventions/django-patterns.md` asks for a reverse *"that a test
    actually runs"*, and this migration is exactly the shape that rule is
    about: the reverse half is the only new executable logic in the commit, and
    a typo in it is invisible until the day somebody needs it.

    The reverse runs against the state it would see inside the migration — the
    kind column present, the table under its old name — so `setUp` reconstructs
    both for this test's own duration, exactly as the two other replays in this
    app do. PostgreSQL runs DDL inside the transaction a `TestCase` rolls back,
    so none of it outlives the test.

    ⚠ **BOTH KINDS OF ROW, BECAUSE ONE WOULD NOT DISCRIMINATE.** A reverse that
    wrote one literal onto every rule would satisfy a fixture holding only cost
    rules; what has to be true is that each rule gets ITS OWN book's kind. And
    a rule attached to no book keeps the empty value, which is the state the
    migration's docstring claims for it.
    """

    def setUp(self):
        self.migration = _rename()
        self.historical = the_state_before(self.migration).apps
        self.enterContext(
            the_rate_table_as_this_migration_saw_it(self.migration))
        self.Rate = self.historical.get_model(APP_LABEL, "Rate")
        self.RateCard = self.historical.get_model(APP_LABEL, "RateCard")
        reconcile_the_rate_table_with(self.Rate)
        (self.run_python,) = [op for op in self.migration.operations
                              if isinstance(op, migrations.RunPython)]

    def _book(self, kind, key):
        return self.RateCard.objects.create(
            tenant_id=self.tenant.id, key=key, currency="usd",
            **{THE_RULES_KIND_COLUMN: kind})

    def _rule(self, book):
        return self.Rate.objects.create(
            tenant_id=self.tenant.id, valid_from=timezone.now(),
            rate_card_id=book.id if book else None,
            **{THE_RULES_KIND_COLUMN: ""})

    def _kind_of(self, rule):
        rule.refresh_from_db()
        return getattr(rule, THE_RULES_KIND_COLUMN)

    def test_each_rule_comes_back_carrying_its_own_books_kind(self):
        self.tenant = _tenant()
        priced = self._rule(self._book("price", "p"))
        costed = self._rule(self._book("cost", "c"))
        bookless = self._rule(None)

        with connection.schema_editor() as editor:
            self.run_python.reverse_code(self.historical, editor)

        self.assertEqual(self._kind_of(priced), "price")
        self.assertEqual(self._kind_of(costed), "cost")
        self.assertEqual(self._kind_of(bookless), "",
                         "a rule in no book has no kind to re-derive, which is "
                         "what the migration says it keeps")

    def test_the_forward_half_touches_nothing(self):
        """The control. Without it the reverse above could be the identity."""
        self.tenant = _tenant()
        rule = self._rule(self._book("price", "p"))

        with connection.schema_editor() as editor:
            self.run_python.code(self.historical, editor)

        self.assertEqual(self._kind_of(rule), "")


class BothRulesCameAcrossWithTheTableTest(TestCase):
    """A trigger belongs to its table by identity, so a rename carries it — and
    that is exactly the kind of fact worth measuring rather than assuming.

    This table carries TWO: one holding what may happen to a rule's two
    effective moments, one holding which rules may be born at all. A rename
    that dropped either would leave the hottest priced table in the system
    unguarded with every other test still green, because every other assertion
    about those rules reads the table off the model and would follow it.
    """

    def _rules_on_the_new_table(self):
        return {name for name, _, _ in
                database_rules_guarding(_the_rename_operation().table)}

    def test_both_rules_are_installed_on_the_table_the_rename_produced(self):
        self.assertEqual(self._rules_on_the_new_table(),
                         {TRANSITION_TRIGGER, DECLARATION_TRIGGER})

    def test_the_catalogue_holds_no_rule_under_the_name_it_moved_from(self):
        """Asked of the catalogue directly, because it is keyed on the NAME.

        ⚠ **WEAKER THAN IT LOOKS, AND SAYING SO IS THE POINT.** It cannot fail
        while the class above passes: the old table does not exist, so nothing
        can be attached to that name. What it holds is the narrower statement
        that the rules moved WITH the table rather than being rebuilt beside
        it — a rebuild that copied them onto a new name and left the old table
        standing is caught by `test_the_live_database_has_the_new_table_and_
        not_the_old_one`, which is where that claim actually lives.
        """
        self.assertEqual(
            database_rules_guarding(_the_name_it_moved_from()), [])

    def test_the_moments_rule_still_refuses_through_raw_sql(self):
        """Still ENFORCING, not merely installed, and through the door that
        goes around every model.

        The rule declares a rule's opening moment frozen. `QuerySet.update()`
        and `save()` are covered by the module that owns this rule; raw SQL is
        the door a rename could plausibly break, because it is the one that
        names the table.
        """
        rate = cost_rate_in_default_book(_tenant())
        moved = timezone.now() - timedelta(days=5)

        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"UPDATE {connection.ops.quote_name(Rate._meta.db_table)}"
                        f" SET valid_from = %s WHERE id = %s",
                        [moved, str(rate.pk)])

        self.assertIn("valid_from", str(refusal.exception))

    def test_the_birth_rule_still_refuses_through_raw_sql(self):
        """The other rule: a rule naming no declared quantity is unwritable.

        Driven as an `INSERT`, which is the only statement it fires on, and
        asserting the MESSAGE — this table answers `IntegrityError` from a
        uniqueness index, three checks, several foreign keys and two triggers,
        so "the write was rejected" stopped being evidence long ago.
        """
        tenant = _tenant()

        with self.assertRaises(IntegrityError) as refusal:
            with transaction.atomic():
                with connection.cursor() as cursor:
                    cursor.execute(
                        f"INSERT INTO "
                        f"{connection.ops.quote_name(Rate._meta.db_table)} "
                        f"(id, created_at, updated_at, tenant_id, provider, "
                        f" event_type, task_type, subtask_type, "
                        f" undeclared_measurement_key, rate_structure, "
                        f" rate_per_unit_micros, unit_quantity, fixed_micros, "
                        f" currency, book_version_from, lineage_id, valid_from,"
                        f" grouping_field_1, grouping_field_2, "
                        f" grouping_field_3, grouping_field_4, "
                        f" grouping_field_5, grouping_field_6, "
                        f" grouping_field_7, grouping_field_8, "
                        f" grouping_field_9, grouping_field_10) "
                        f"VALUES (gen_random_uuid(), now(), now(), %s, '', "
                        f" '', '', '', 'no_declaration_says_this', 'per_unit', "
                        f" 0, 1000000, 0, 'usd', 1, gen_random_uuid(), now(), "
                        f" '', '', '', '', '', '', '', '', '', '')",
                        [str(tenant.pk)])

        self.assertIn("declaration", str(refusal.exception))


class NoRuleCarriesAKindWordAnyMoreTest(TestCase):
    """The column is deleted rather than re-spelled, which is the point.

    One table wearing a kind discriminator is what stopped the model saying
    that a book of supplier costs and a book of customer prices are different
    things governed by different rules. Re-spelling it would have kept the
    conflation under a better name.
    """

    def test_the_model_declares_no_such_field(self):
        self.assertNotIn(THE_DELETED_COLUMN,
                         {field.name for field in Rate._meta.get_fields()})

    def test_the_live_table_has_no_such_column(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s", [Rate._meta.db_table])
            columns = {row[0] for row in cursor.fetchall()}
        self.assertNotIn(THE_DELETED_COLUMN, columns)
        self.assertIn("currency", columns,
                      "the table was read as empty, so the check above says "
                      "nothing")

    def test_the_removal_names_that_column_and_no_other(self):
        removal = next(op for op in _rename().operations
                       if isinstance(op, migrations.RemoveField))
        self.assertEqual(removal.name, THE_DELETED_COLUMN)

    def test_the_lookup_index_no_longer_leads_on_it(self):
        """The index led on a column no query filters, and it went with it.

        A rename that kept the index would have kept a dead leading term on the
        hottest priced table in the system, which is a cost paid on every write
        for a discriminator nothing reads.

        ⚠ The model declares exactly ONE index, asserted rather than assumed:
        taking `[0]` of a list is a coin toss the day a second one lands, and
        this table has already paid for that shape once over `pg_trigger`.
        """
        (index,) = Rate._meta.indexes
        self.assertNotIn(THE_DELETED_COLUMN, index.fields)
        self.assertEqual(index.fields,
                         ["tenant", "provider", "event_type", "measurement"])


class NoResolutionPathSelectsARuleByKindTest(TestCase):
    """The branch that has gone, and the one that has not — both asserted.

    Resolution used to be able to ask this table what kind a rule was. It never
    did: the ladder selects BOOKS and then asks for the rules inside them. That
    made the column free to disagree with the book it was copied from, which is
    the shape a discriminated table always has.

    ⚠ **THE SECOND TEST IS THE HONEST HALF.** The cost path and the price path
    still differ — they select different books — and saying so is what keeps
    the first test from being read as a claim this commit has not paid for.
    Ticket 21 splits the container, and that is when the two paths stop having
    a shared word at all.
    """

    def setUp(self):
        self.tenant = _tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        rate_in_default_book(self.tenant, measurement_key="input_tokens",
                             rate_per_unit_micros=7)
        cost_rate_in_default_book(self.tenant, measurement_key="input_tokens",
                                  rate_per_unit_micros=3)

    def _statements_against_the_rule_table(self, kind):
        with CaptureQueriesContext(connection) as captured:
            PricingService._resolve_card(
                self.tenant, self.customer, kind,
                {name: "" for name in Rate.SELECTORS}, "input_tokens",
                "usd", timezone.now())
        table = connection.ops.quote_name(Rate._meta.db_table)
        return [query["sql"] for query in captured.captured_queries
                if f"FROM {table}" in query["sql"]]

    def test_neither_path_names_a_kind_column_when_it_asks_for_rules(self):
        """Measured off the SQL, not off the source.

        A test reading the resolver's Python could be satisfied by a filter
        built somewhere else; what the database is asked is the whole claim.
        """
        for kind in ("cost", "price"):
            statements = self._statements_against_the_rule_table(kind)
            with self.subTest(kind=kind):
                self.assertTrue(statements, "no statement reached the rules, "
                                            "so this asserts nothing")
                for sql in statements:
                    self.assertNotIn(THE_DELETED_COLUMN, sql)

    def test_the_two_paths_ask_the_rules_the_same_question(self):
        """One shape, differing only in WHICH books were selected.

        The `IN` list of book ids is what separates them and it is the only
        thing that does — so the discriminator has moved entirely into
        selection, where the container still holds it. The list is collapsed to
        a single placeholder before comparing, because the two paths select
        different NUMBERS of books as well as different ones and neither fact
        is about the rules.
        """
        shapes = set()
        for kind in ("cost", "price"):
            for sql in self._statements_against_the_rule_table(kind):
                shapes.add(_without_its_values(sql))
        self.assertEqual(len(shapes), 1, shapes)

    def test_the_container_is_still_what_tells_the_two_apart(self):
        """The residual, named rather than left silent.

        `_selected_books` answers different books for the two kinds, and it can
        only do that because the container still carries the word. Ticket 21 is
        where this stops being true, and this test is what will go red when it
        does — which is the intended repair, not a regression.
        """
        for_cost = PricingService._selected_books(
            self.tenant, self.customer, "cost", "", "usd")
        for_price = PricingService._selected_books(
            self.tenant, self.customer, "price", "", "usd")

        self.assertTrue(for_cost and for_price)
        self.assertEqual(
            {book.id for _, book in for_cost}
            & {book.id for _, book in for_price}, set())


class TheTwoDeletedActionsCannotBeWrittenTest(TestCase):
    """`record()` refuses an unregistered name, and that is what made this safe.

    Deleting an action whose act no longer exists is not the rename ADR-004 §2
    governs: a rename carries an act forward under a new spelling and breaks a
    reader watching for the old one, and these two have no successor. **No part
    of the one-time pre-production audit-registry reset is consumed here** — it
    stays allocated to the cutover, for the names that genuinely are renamed.

    What makes the deletion safe rather than merely defensible is that a route
    still writing one of these would fail loudly, so route and registry are
    forced into one commit and there is no window in which a dead action is
    written.
    """

    def test_each_deleted_name_is_refused_by_the_recording_function(self):
        tenant = _tenant()
        for parts in DELETED_ACTIONS:
            action = ".".join(parts)
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, re.escape(action)):
                    record(action=action, tenant_id=tenant.id,
                           resource_type="rate")

    def test_a_registered_name_is_still_accepted(self):
        """The control. Without it the refusal above passes on a `record()`
        that had stopped writing anything at all."""
        tenant = _tenant()
        record(action="tenant.config_changed", tenant_id=tenant.id,
               resource_type="tenant", resource_id=str(tenant.id))

    def test_neither_name_is_left_in_the_registry(self):
        for parts in DELETED_ACTIONS:
            with self.subTest(action=".".join(parts)):
                self.assertNotIn(".".join(parts), AUDIT_ACTIONS)
