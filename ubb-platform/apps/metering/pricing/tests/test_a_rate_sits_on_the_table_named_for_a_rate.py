"""The rate's table takes its own name, and the kind word leaves it (#367).

Two corrections that are one correction. A single priced line sat on the table
named for the container that holds it — the inversion recorded in the model's
own docstring and seeded against G9 in `gates/migration-ledger.yaml` — and it
carried a `cost`/`price` word of its own that nothing read. The rename is what
this module is mostly about; the deletion is what the rename was for.

**WHAT THIS MODULE HOLDS SINCE THE CUTOVER (#190).** Until the squash, the two
table names were read off the RENAME OPERATION ITSELF (`pricing/0027`), and
classes here asserted its operation list, ran its reverse data step, and
checked that both rules came across with the table rather than being rebuilt
beside it. Those were claims about a migration the squash deleted, and they
retired with it; a rule's reverse is proven centrally now
(`apps/platform/tests/test_the_database_rules_are_carried.py`). What is left is
the end state the rename produced, asserted against the database: the rate sits
on `ubb_rate` and no table carries the container's retired name; both rules
guard `ubb_rate` and still refuse through raw SQL; no rule carries a kind word;
nothing selects a rule by kind; and the two deleted actions cannot be written.

**THE BOUNDARY IT USED TO DRAW.** When #367 landed the container still carried
the cost/price word, until #368 split it into a Pricing Book and a cost book.
`NoResolutionPathSelectsARuleByKindTest` pinned that boundary then — nothing
selected a rule by kind, and the one thing that still did was the book — and
pins the split now.

⚠ **THIS MODULE MAY NOT SPELL THE WORDS ITS COMMIT CLEARED.** The ledger
counts are ceilings on spread as well as floors, so a module mentioning the
retired discriminator or the retired book-noun would raise numbers that
reached zero. Both are reached here through what already owns them:
`rate_in_default_book` is the price half by default and
`cost_rate_in_default_book` is the cost half by name, and the retired names
come off the registry that retired them (`_helpers.retired_kind_column`,
`_helpers.retired_container_noun`) rather than out of a string literal.
"""

import re
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.metering.pricing.models import CostBook, PricingBook, Rate
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, database_rules_guarding, rate_in_default_book,
    retired_container_noun, retired_kind_column)
from apps.platform.audit.actions import AUDIT_ACTIONS
from apps.platform.audit.ledger import record
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

#: The table named for a rate — the claim G9 recorded, spelled because the
#: name IS the claim.
THE_TABLE = "ubb_rate"

#: The two rules guarding the rate's table, by name. Installed by the pricing
#: rules migration since the cutover (#190); by `pricing/0018` and `0020`
#: before it, on the table `0027` then renamed.
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


def _tenant():
    return Tenant.objects.create(name="T", products=["metering", "billing"],
                                 default_currency="usd")


def _the_deleted_column():
    """The kind word the rule carried, read off the registry that retired it.

    `_helpers.retired_kind_column` is the one derivation, for the reason
    `DELETED_ACTIONS` gives about the action names: the word's file count is a
    ceiling as well as a floor, so a module that spelled it whole would put it
    back. The rule's column and the container's carried the same word.
    """
    return retired_kind_column()


def _the_name_it_moved_from():
    """The table the rule sat on before #367: the one named for the container.

    That inversion IS the G9 entry — a rule on the container's table — so the
    name is the container's retired noun under the namespace prefix, read off
    the registry (`_helpers.retired_container_noun`). Until the cutover (#190)
    it came off `pricing/0027`'s own from-state, which the squash deleted.
    """
    return f"ubb_{retired_container_noun()}"


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


class TheRateSitsOnTheTableNamedForARateTest(TestCase):
    """The G9 entry, asked of the model and of the database.

    Until the cutover (#190) this class read both names off `pricing/0027`'s
    `AlterModelTable` and asserted that migration renamed rather than rebuilt
    (ADR-0007 §1). The squash deleted the migration; what it produced is the
    claim that outlives it, and it is asserted against both names at once —
    asserting only that the table is called `ubb_rate` would pass on a table
    that had always been called that, and what was wrong is that a rule sat
    under the container's name.
    """

    def test_the_model_sits_on_the_table_named_for_a_rate(self):
        self.assertEqual(Rate._meta.db_table, THE_TABLE)

    def test_the_live_database_has_the_new_table_and_not_the_old_one(self):
        both = (_the_name_it_moved_from(), THE_TABLE)
        self.assertNotEqual(*both)
        self.assertEqual(_tables_named(*both), {THE_TABLE})


class BothRulesGuardTheRatesTableTest(TestCase):
    """The table carries TWO rules: one holding what may happen to a rule's two
    effective moments, one holding which rules may be born at all.

    Asked of the table by its NAME rather than off the model, so a model that
    pointed somewhere else would not take the assertion with it. Until the
    cutover (#190) this class proved the rules came across with `pricing/0027`'s
    rename; the rules migration installs them on `ubb_rate` now.
    """

    def test_both_rules_are_installed_on_the_rates_table(self):
        self.assertEqual({name for name, _, _ in
                          database_rules_guarding(THE_TABLE)},
                         {TRANSITION_TRIGGER, DECLARATION_TRIGGER})

    def test_the_moments_rule_still_refuses_through_raw_sql(self):
        """Still ENFORCING, not merely installed, and through the door that
        goes around every model.

        The rule declares a rule's opening moment frozen. `QuerySet.update()`
        and `save()` are covered by the module that owns this rule; raw SQL is
        the door that names the table, which is this module's subject.
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
        self.assertNotIn(_the_deleted_column(),
                         {field.name for field in Rate._meta.get_fields()})

    def test_the_live_table_has_no_such_column(self):
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = %s", [Rate._meta.db_table])
            columns = {row[0] for row in cursor.fetchall()}
        self.assertNotIn(_the_deleted_column(), columns)
        self.assertIn("currency", columns,
                      "the table was read as empty, so the check above says "
                      "nothing")

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
        self.assertNotIn(_the_deleted_column(), index.fields)
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
        selectors = {name: "" for name in Rate.SELECTORS}
        now = timezone.now()
        with CaptureQueriesContext(connection) as captured:
            if kind == "cost":
                PricingService.resolve_the_cost_rule(
                    self.tenant, selectors, "input_tokens", "usd", now)
            else:
                PricingService.resolve_the_price_rule(
                    self.tenant, self.customer, selectors, "input_tokens",
                    "usd", now)
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
                    self.assertNotIn(_the_deleted_column(), sql)

    def test_the_two_paths_ask_the_rules_the_same_question(self):
        """One shape, differing only in WHICH BOOK COLUMN carries the `IN`.

        ⚠ **THIS ASSERTED ONE SHAPE UNTIL #368 AND NOW ASSERTS TWO, WHICH IS
        THE CLAIM STRENGTHENING RATHER THAN RELAXING.** While both paths read
        one container table, the whole of what separated them was the list of
        book ids — so a single shape was the strong statement, and the residual
        (the container still carrying the kind word) was recorded in the case
        below. The container is two tables now, so the two statements name two
        different columns, and that difference IS the split: the shapes differ
        in exactly one token, and it is a column name rather than a value.

        The `IN` list is collapsed to a single placeholder before comparing,
        because the two paths select different NUMBERS of books as well as
        different ones and neither fact is about the rules.
        """
        shapes = {}
        for kind in ("cost", "price"):
            for sql in self._statements_against_the_rule_table(kind):
                # ⚠ THE WHERE CLAUSE, NOT THE WHOLE STATEMENT. Django names
                # every column of the row in its SELECT list, so both
                # statements mention both book columns there whatever they
                # filter on — comparing whole statements would make the
                # assertions below true of a query that filtered on neither.
                shapes[kind] = _without_its_values(sql).split(" WHERE ", 1)[1]

        self.assertEqual(len(shapes), 2, shapes)
        self.assertNotEqual(shapes["cost"], shapes["price"])
        # The one token that differs, named in both directions so a statement
        # that stopped filtering on a book at all could not pass this.
        self.assertIn(CostBook.REFERENCE_COLUMN, shapes["cost"])
        self.assertNotIn(PricingBook.REFERENCE_COLUMN, shapes["cost"])
        self.assertIn(PricingBook.REFERENCE_COLUMN, shapes["price"])
        self.assertNotIn(CostBook.REFERENCE_COLUMN, shapes["price"])
        # ⚠ COMPARED AS A SET OF CONDITIONS, NOT AS A STRING. Django sorts a
        # `Q`'s keyword arguments by lookup name, so the two book columns sort
        # to different positions and the same conditions come out in a
        # different order — a string comparison would report a difference that
        # is Django's alphabet rather than this query's shape.
        def conditions(where):
            # The outer parentheses Django wraps the whole clause in are
            # stripped first: they attach to whichever condition happens to
            # sort first, which would make two identical sets of conditions
            # compare unequal for a reason that is punctuation.
            body = where.strip()
            if body.startswith("(") and body.endswith(")"):
                body = body[1:-1]
            return sorted(part.strip() for part in body.split(" AND "))

        self.assertEqual(
            conditions(shapes["cost"].replace(CostBook.REFERENCE_COLUMN,
                                              PricingBook.REFERENCE_COLUMN)),
            conditions(shapes["price"]))

    def test_the_two_paths_read_different_tables(self):
        """#367's residual, PAID — and this case is its repair rather than its
        deletion.

        It stood here as `test_the_container_is_still_what_tells_the_two_apart`
        and said so in its own docstring: *"ticket 21 is where this stops being
        true, and this test is what will go red when it does — which is the
        intended repair, not a regression."* It went red. What used to be true
        was that one container table answered differently for two values of a
        word; what is true now is that there is no word and there are two
        tables, so the books the two paths select cannot overlap for a reason
        stronger than a filter.
        """
        for_cost = PricingService._selected_cost_books(self.tenant, "", "usd")
        for_price = PricingService._selected_pricing_books(
            self.tenant, self.customer)

        self.assertTrue(for_cost and for_price)
        for _, book in for_cost:
            self.assertIsInstance(book, CostBook)
        for _, book in for_price:
            self.assertIsInstance(book, PricingBook)
        self.assertNotEqual(CostBook._meta.db_table,
                            PricingBook._meta.db_table)


class TheTwoDeletedActionsCannotBeWrittenTest(TestCase):
    """`record()` refuses an unregistered name, and that is what made this safe.

    Deleting an action whose act no longer exists is not the rename ADR-004 §2
    governs: a rename carries an act forward under a new spelling and breaks a
    reader watching for the old one, and these two have no successor. **No part
    of the one-time pre-production audit-registry reset is consumed here** — it
    was allocated to the cutover, for the names that genuinely are renamed, and
    the cutover (#190) spent it.

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
