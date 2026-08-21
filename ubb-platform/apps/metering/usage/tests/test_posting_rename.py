"""The usage row became the Posting at no cost to a row, a key or an index (#269).

`UsageEvent` is `Posting`, `ubb_usage_event` is `ubb_posting`, and
`Refund.usage_event` is `Refund.posting`. Three ways to lose data, and the
migration takes none of them:

1. **A model rename Django was not told about is a create-plus-drop.** Run
   non-interactively, `makemigrations` never asks "did you rename this?" — it
   emits a `CreateModel` and a `DeleteModel`, builds an empty table beside the
   full one and drops the original. ADR-0007 §1 refuses it and the pre-squash
   exemption is spent.
2. **A field rename Django was not told about is an add-plus-remove**, which
   empties the column it claims to move.
3. **A table rename ordered the other way round rebuilds the inbound foreign
   key.** `RenameModel` runs first precisely so that `ubb_refund`'s constraint
   still points at a table whose name has not changed yet, and Django's
   re-point emits nothing.

So the SQL is read rather than assumed, in both directions. `collect_sql`
renders what the migration would run without running it — the same entry point
`manage.py sqlmigrate` uses — which is the only way to assert "this renames and
does not rebuild" as a fact about the database instead of a fact about the
operations list. `RenameIsARenameTest` below is that half; the classes after it
read the database this suite's own migrations actually built.

**This module spells the retired model, table and column names**, because
proving a rename means naming what was renamed — the same reason
`events/tests/test_webhook_event_rename.py` spells thirteen retired event names
and `grouping_fields/tests/test_app_label_move.py` spells a retired app label.
Both are declared exclusions under `checks-whose-subject-is-a-retired-word` in
`gates/forbidden-term-sweep.yaml`, and **this file needs no entry beside them**:
none of `UsageEvent`, `usage_event` or `ubb_usage_event` is a retired term in
`domain-vocabulary/`, so the sweep has nothing here to find. Recorded rather
than left silent, because the exclusion is the shape a reader will look for.

---

**THE CURRENCY CHECK CONSTRAINT DOES NOT EXIST, AND THIS TICKET DOES NOT
INVENT ONE.** The spec hands slice 2 "the posting's currency CHECK constraint"
and argues it is safe because "non-conforming input is rejected at the API door,
so no real posting is ever blocked by it". Measured against the tree, both
halves are wrong:

* **There is no such constraint to carry.** None of the eight currency columns
  has ever had one. `CHECK (currency = 'USD')` is a *sketch* in the measurement
  vocabulary decision (§7.1), never built — no model declares it, no migration
  adds it, and no `RunSQL` anywhere in `usage/migrations/` writes one. A rename
  cannot make a constraint survive that was never there. (One CHECK in the tree
  does touch a column named `currency`, and it is not this rule wearing another
  name — see `test_no_stamped_currency_column_carries_a_check_constraint`.)
* **The API door does not enforce it.** `test_omitted_currency_defaults_to_
  tenant_currency` in `api/v1/tests/test_metering_endpoints.py` records a
  posting at `currency='eur'` through the public endpoint and asserts a 200,
  because the recording path stamps `Tenant.default_currency` and that field
  accepts any three-letter code. Adding the constraint would turn that green
  200 into a database error — a real posting blocked by it, which is the exact
  outcome the spec's safety argument says cannot happen.

So the currency column rides along with its `usd` default and its `varchar(3)`
width and nothing else, which is what `TheCurrencyColumnRodeAlongTest` pins.
**Adding the constraint is not deferred here — it is unbuildable until the
USD-only rule reaches the door**, and that is nobody's ticket today. It joins
the others as an unowned gap rather than being smuggled in under a rename.
"""
from django.db import connection
from django.db import migrations as operations
from django.db.migrations.loader import MigrationLoader
from django.test import TestCase

from apps.metering.usage.models import BackfillDirtyPeriod, Posting, Refund
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

APP_LABEL = "usage"
RENAME_MIGRATION = "0030_the_usage_row_becomes_the_posting"

OLD_TABLE = "ubb_usage_event"
NEW_TABLE = "ubb_posting"
OLD_COLUMN = "usage_event_id"
NEW_COLUMN = "posting_id"
REFUND_TABLE = "ubb_refund"

#: The constraint and the named indexes the table carried in, spelled out.
#: Every one still names the retired noun on purpose — there is no rename
#: operation for either that Django will emit, only a drop and a re-create,
#: which is the add-plus-remove this migration exists to avoid. ADR-0006 §9's
#: rule is about the table name. Listed here so that a later change quietly
#: rebuilding one goes red.
#:
#: SIX CAME ACROSS AND ONE HAS SINCE BEEN RETIRED. `idx_usage_dim_attribution`
#: led with two slot columns, and #276 dropped it deliberately: nothing in this
#: repository filters on a slot, so it could only ever be scanned whole. It is
#: named in `DELIBERATELY_DROPPED` rather than deleted from this file, because
#: an index silently disappearing from a list of indexes that must survive is
#: exactly the accident this list exists to catch.
CARRIED_CONSTRAINT = "uq_usage_event_idempotency_v2"
CARRIED_INDEXES = (
    "idx_usage_customer_effective",
    "idx_usage_tenant_effective",
    "idx_usage_work_attribution",
    "idx_usage_tenant_created",
    "idx_usage_stop_context",
)
DELIBERATELY_DROPPED = ("idx_usage_dim_attribution",)

#: The other currency columns, by table. **This ticket does not claim them.**
#: One decision hands their constraints to the cutover decision and that
#: document assigns them to no slice, so the gap is recorded by name here rather
#: than silently inherited — see the module docstring for why the posting's own
#: is in the same position.
#:
#: Seven was the spec's own denominator, taken from the measurement vocabulary
#: decision's §7.3 table, and it was the seven columns that default to `usd` the
#: way the posting's does. **FIVE ARE LEFT (#368)** — the two paid below. **The
#: tree holds others that were deliberately never listed**:
#: `ReportedCostMapping.currency` is a DECLARED pin rather than a stamped copy
#: (it defaults to `''`, and #266 landed it in this same slice), and
#: `StripeSubscription` and `SubscriptionInvoice` mirror the payment rail's own
#: field. None is a copy of the tenant's frozen choice, which is what §7.3's
#: list is about.
#:
#: ⚠ **AND `ubb_cost_book.currency` DOES NOT JOIN THIS LIST, WHICH IS THE TEST
#: THE LIST'S OWN RULE HAD TO PASS (#368).** A cost book declares the currency
#: its supplier bills in: the column has **no default**, and
#: `ck_cost_book_names_its_currency` refuses the empty string. It is the
#: `ReportedCostMapping` shape exactly — a declaration, not a stamped copy of a
#: choice made elsewhere — so admitting it here would be recording a debt that
#: is not owed, which is the mirror of the failure this list exists to prevent.
UNOWNED_CURRENCY_COLUMNS = (
    # ⚠ **THE RULE TABLE'S ENTRY FOLLOWED ITS RENAME RATHER THAN BEING DELETED
    # (#367).** Slice 4 moved this table to the name a rule's own name asks for.
    # A rename moves a table; it does not touch the column — the rule's currency
    # is still an unconstrained `usd`-defaulted copy of the tenant's frozen
    # choice, and this list exists to say so. Deleting the line would have
    # retired a live gap by spelling, which is the opposite of what the list is
    # for.
    #
    # ⚠⚠ **#367 HANDED THAT DISAGREEMENT FORWARD AND #368 RESOLVED IT, WITH
    # TWO LINES DELETED AND THIS ONE KEPT.** Ticket 21 read *"All three of this
    # slice's lines are deleted — two renamed tables and one deleted table"*;
    # #367's note answered that a rename discharges nothing, and asked whoever
    # landed the split to decide rather than delete by default. Measured on the
    # commit: the tripwire fired on exactly TWO of the three, and this line was
    # not one of them.
    #
    #   * `ubb_rate_card_assignment` — the table is DELETED, so the line goes.
    #   * `ubb_rate_card_container` — the container split, and the Pricing Book
    #     it became **has no currency column at all**. That is #367's own
    #     escape clause reached the strong way: the gap is not constrained, it
    #     is gone, because a tenant has exactly one currency (CUR-1) and a
    #     column repeating it was the copy this list is about. The line goes.
    #   * `ubb_rate` — **stays.** A rule still carries a `usd`-defaulted
    #     currency nobody owns. Nothing in #368 touches it, and deleting it
    #     because a ticket's arithmetic expected three would be exactly the
    #     retire-a-gap-by-spelling the note above refuses. It is handed
    #     forward, unpaid and named.
    "ubb_rate",                      # Rate
    "ubb_wallet",                    # Wallet
    "ubb_credit_grant",              # CreditGrant
    "ubb_customer_usage_invoice",    # CustomerUsageInvoice
    "ubb_customer_revenue_profile",  # CustomerRevenueProfile
)

#: Operations that would cost rows, keys or indexes. `AlterModelTable`,
#: `RenameModel` and `RenameField` are renames; these are not, and none of them
#: belongs in a rename migration.
DESTRUCTIVE = (
    operations.CreateModel, operations.DeleteModel,
    operations.AddField, operations.RemoveField,
    operations.AddConstraint, operations.RemoveConstraint,
    operations.AddIndex, operations.RemoveIndex,
    operations.RunSQL,
)


def _table_of(name):
    """The live table for a model, looked up by its `db_table`."""
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", [name])
        return cur.fetchone()[0]


class RenameIsARenameTest(TestCase):
    """The migration moves the table and the column; it rebuilds neither."""

    def setUp(self):
        self.loader = MigrationLoader(connection)
        self.migration = self.loader.get_migration(APP_LABEL, RENAME_MIGRATION)

    def _sql(self, *, backwards):
        return "\n".join(
            self.loader.collect_sql([(self.migration, backwards)]))

    def test_it_carries_no_operation_that_would_cost_a_row(self):
        offenders = sorted(type(op).__name__ for op in self.migration.operations
                           if isinstance(op, DESTRUCTIVE))
        self.assertEqual(offenders, [], "a rename migration may not drop or "
                                        "create a table, column or constraint")

    def test_the_model_is_renamed_rather_than_replaced(self):
        renamed = {(op.old_name, op.new_name)
                   for op in self.migration.operations
                   if isinstance(op, operations.RenameModel)}
        self.assertEqual(renamed, {("UsageEvent", "Posting")})

    def test_the_refund_field_is_renamed_rather_than_re_added(self):
        renamed = {(op.model_name, op.old_name, op.new_name)
                   for op in self.migration.operations
                   if isinstance(op, operations.RenameField)}
        self.assertEqual(renamed, {("refund", "usage_event", "posting")})

    def test_the_rename_model_runs_before_the_table_is_renamed(self):
        """The ordering is what stops the inbound foreign key being rebuilt.

        With `AlterModelTable` first, `RenameModel`'s re-point of
        `ubb_refund`'s constraint would see a target table that had already
        moved, and Django's answer to that is a drop and a re-add.
        """
        kinds = [type(op).__name__ for op in self.migration.operations]
        self.assertLess(kinds.index("RenameModel"),
                        kinds.index("AlterModelTable"))

    def test_every_operation_can_be_reversed(self):
        for op in self.migration.operations:
            with self.subTest(operation=type(op).__name__):
                self.assertTrue(op.reversible)

    def test_the_sql_renames_the_table_and_the_column_in_place(self):
        """This is also the vacuity guard for the absences below.

        An empty render — a migration that resolved to nothing, a loader that
        read the wrong node — would satisfy "no CREATE TABLE" and "no DROP
        TABLE" perfectly. Asserting the renames are PRESENT is what proves the
        SQL was actually produced, so the absences mean something.
        """
        sql = self._sql(backwards=False)

        self.assertIn(f'ALTER TABLE "{OLD_TABLE}" RENAME TO "{NEW_TABLE}"', sql)
        self.assertIn(f'RENAME COLUMN "{OLD_COLUMN}" TO "{NEW_COLUMN}"', sql)

    def test_the_sql_neither_creates_nor_drops_a_table_key_or_index(self):
        # Guarded against vacuity by the test above, which proves this same
        # render is non-empty. `DROP CONSTRAINT` covers the primary key, the
        # unique idempotency constraint and the inbound foreign key alike.
        sql = self._sql(backwards=False)

        self.assertNotIn("CREATE TABLE", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertNotIn("DROP CONSTRAINT", sql)
        self.assertNotIn("DROP INDEX", sql)
        self.assertNotIn("DROP COLUMN", sql)

    def test_the_related_name_changes_emit_no_sql_at_all(self):
        """`related_name` is a non-database attribute.

        The three `AlterField`s exist so the migration state matches the models
        and `makemigrations --check` stays clean. If one of them ever started
        emitting DDL it would mean the field had changed in some other way too,
        and this rename would be carrying a schema change nobody declared.
        """
        renames = {"RenameModel", "AlterModelTable", "RenameField"}
        only_alters = [op for op in self.migration.operations
                       if type(op).__name__ not in renames]
        self.assertEqual([type(op).__name__ for op in only_alters],
                         ["AlterField"] * 3)

        # Two DDL statements, and only two: the table rename and the column
        # rename. A third would mean an `AlterField` had started emitting SQL,
        # which would mean the field changed in some way nobody declared.
        statements = [line for line in self._sql(backwards=False).splitlines()
                      if line.strip().upper().startswith("ALTER TABLE")]
        self.assertEqual(len(statements), 2, statements)

    def test_the_reverse_puts_the_table_and_the_column_back(self):
        sql = self._sql(backwards=True)

        self.assertIn(f'ALTER TABLE "{NEW_TABLE}" RENAME TO "{OLD_TABLE}"', sql)
        self.assertIn(f'RENAME COLUMN "{NEW_COLUMN}" TO "{OLD_COLUMN}"', sql)


class TheTableCarriedEverythingTest(TestCase):
    """Read against the database this suite's own migrations built.

    The SQL render above proves the migration says the right thing; this proves
    the database ended up in the state it describes. Both are needed: a render
    is a claim about a statement, and a catalogue read is the outcome.
    """

    def test_the_table_tracks_the_model_name(self):
        # ADR-0006 §9, and the thing the migration has to land on. G9 in
        # apps/platform/tests/test_model_naming.py derives the same name
        # mechanically; it is spelled out here because the migration targets it
        # literally.
        self.assertEqual(Posting._meta.db_table, NEW_TABLE)
        self.assertIsNotNone(_table_of(NEW_TABLE))

    def test_the_retired_table_is_gone_rather_than_left_beside_it(self):
        """A create-plus-drop that failed halfway leaves both.

        So does a `RenameModel` whose `AlterModelTable` was forgotten, and that
        one is silent: the models would read the new table, the rows would sit
        in the old one, and every query would return nothing.
        """
        self.assertIsNone(_table_of(OLD_TABLE))

    def test_the_primary_key_came_across_intact(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
            """, [NEW_TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()], ["id"])

    def test_the_unique_idempotency_constraint_kept_its_identity(self):
        """By NAME, not merely by existence.

        A drop-and-recreate under Django's own naming would produce a working
        unique index with a different name, which is how you would discover
        afterwards that the constraint had been rebuilt rather than carried.
        """
        with connection.cursor() as cur:
            cur.execute("""
                SELECT conname FROM pg_constraint
                WHERE conrelid = %s::regclass AND contype = 'u'
            """, [NEW_TABLE])
            self.assertIn(CARRIED_CONSTRAINT, {row[0] for row in cur.fetchall()})

    def test_it_still_refuses_a_duplicate_idempotency_key(self):
        """The constraint is not just present, it still bites.

        A constraint can survive a rename as a catalogue row and still have
        stopped covering the columns it was written for — this is the behaviour
        the row is there to produce.
        """
        from django.db import IntegrityError

        tenant = Tenant.objects.create(name="T")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        Posting.objects.create(tenant=tenant, customer=customer,
                               idempotency_key="dup")

        with self.assertRaises(IntegrityError):
            Posting.objects.create(tenant=tenant, customer=customer,
                                   idempotency_key="dup")

    def test_every_named_index_came_across(self):
        with connection.cursor() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s",
                        [NEW_TABLE])
            live = {row[0] for row in cur.fetchall()}

        missing = sorted(set(CARRIED_INDEXES) - live)
        self.assertEqual(missing, [], f"indexes did not follow the table: {live}")
        # The other half: an index this repository decided to stop paying for
        # must not quietly come back. Without this, moving a name out of the
        # list above would be indistinguishable from forgetting it.
        self.assertEqual(sorted(set(DELIBERATELY_DROPPED) & live), [])

    def test_the_inbound_foreign_key_still_points_at_the_renamed_table(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = %s::regclass
                  AND c.confrelid = %s::regclass
                  AND c.contype = 'f'
            """, [REFUND_TABLE, NEW_TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()], [NEW_COLUMN])

    def test_the_table_owns_no_sequence_to_carry(self):
        """Stated rather than asserted vacuously.

        "Sequences survive the rename" is one of this ticket's acceptance
        criteria, and the honest answer is that there is nothing to survive:
        `core.models.BaseModel` gives every row a client-generated `UUIDField`
        primary key, so no serial column and no owned sequence exists. A test
        that looked for one and found none would read as a pass either way —
        this pins the reason.
        """
        self.assertEqual(Posting._meta.pk.get_internal_type(), "UUIDField")

        with connection.cursor() as cur:
            cur.execute("""
                SELECT c.relname FROM pg_class c
                JOIN pg_depend d ON d.objid = c.oid
                WHERE c.relkind = 'S' AND d.refobjid = %s::regclass
            """, [NEW_TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()], [])


class TheNeighboursMovedWithItTest(TestCase):
    """The two models in the same module that reference the renamed one."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.posting = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_1",
            billed_cost_micros=1_000_000)

    def test_the_refund_points_at_the_posting_by_its_new_name(self):
        refund = Refund.objects.create(
            tenant=self.tenant, customer=self.customer, posting=self.posting,
            amount_micros=500_000)

        self.assertEqual(Refund.objects.get(posting=self.posting), refund)
        self.assertEqual(self.posting.refund, refund)

    def test_the_refunds_string_still_traverses_to_its_parent(self):
        """`__str__` reads a field ON THE POSTING, so a half-done rename raises
        `AttributeError` the first time anything prints one — in the admin, in a
        shell, or inside a log line during an incident.

        The value it prints is asserted next door in `test_models.py`, not here.
        That field is a retired term with a live ledger debt (its deletion is
        slice 5's), and the sweep's `term_spread` rule refuses a 66th file
        naming it while the debt stands — a debt is a finite migration plan, not
        a licence for the word to reach further. `test_models.py` is already one
        of the sixty-five and is the model's own test module, so the assertion
        goes there and this one proves the traversal.
        """
        refund = Refund.objects.create(
            tenant=self.tenant, customer=self.customer, posting=self.posting,
            amount_micros=500_000)

        rendered = str(refund)

        self.assertTrue(rendered.startswith("Refund("), rendered)
        self.assertIn("500000", rendered)

    def test_the_backfill_marker_is_unchanged_and_still_writes(self):
        """It references the posting by (tenant, customer) rather than by a
        foreign key, so the rename gives it nothing to re-point — which is
        exactly why it is worth pinning that it kept its own table and still
        takes a row."""
        import datetime

        self.assertEqual(BackfillDirtyPeriod._meta.db_table,
                         "ubb_backfill_dirty_period")
        marker = BackfillDirtyPeriod.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 7, 1))

        self.assertEqual(str(marker),
                         f"BackfillDirtyPeriod({self.customer.id}: 2026-07-01)")

    def test_the_reverse_accessors_take_the_canonical_noun(self):
        self.assertEqual(list(self.tenant.postings.all()), [self.posting])
        self.assertEqual(list(self.customer.postings.all()), [self.posting])


class TheCurrencyColumnRodeAlongTest(TestCase):
    """Slice 2's only currency column, and what it does and does not carry.

    Read the module docstring first: the CHECK constraint the spec hands this
    ticket does not exist and cannot be written truthfully today.
    """

    def test_the_column_survived_the_rename_on_the_new_table(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT data_type, character_maximum_length, column_default
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'currency'
            """, [NEW_TABLE])
            row = cur.fetchone()

        self.assertIsNotNone(row, "the currency column did not follow the table")
        data_type, width, _default = row
        self.assertEqual((data_type, width), ("character varying", 3))

    def test_it_still_defaults_to_the_lowercase_code(self):
        """Spec §K2: lowercase stands.

        Eight columns default to a lowercase code under an in-code convention
        comment, against a merged decision whose SQL sketch is uppercase. There
        is no currency concept in `domain-vocabulary/` at all, so no oracle
        settles the casing — the sketch was illustrative, the convention is
        consistent, and it matches the payment rail's own casing.
        """
        tenant = Tenant.objects.create(name="T")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")

        posting = Posting.objects.create(
            tenant=tenant, customer=customer,
            idempotency_key="i1")

        self.assertEqual(Posting._meta.get_field("currency").default, "usd")
        self.assertEqual(posting.currency, "usd")

    def test_no_stamped_currency_column_carries_a_check_constraint(self):
        """The finding, pinned so it cannot be quietly assumed away.

        This is what makes the module docstring's first claim checkable rather
        than a note. The day somebody builds the USD-only rule — at the door
        first, then in the database — this goes red and names the tables that
        moved, which is the right moment to revisit who owns the others.

        Scoped to the columns §7.3's table is about, and the exclusion is
        the interesting part. `ubb_reported_cost_mapping` DOES carry a CHECK
        touching `currency` — `ck_reported_cost_currency_pinned_once`, landed by
        #266 in this same slice — and it is not a counter-example: it is an XOR
        between a pinned code and a path to read one from, on a column that
        DECLARES which currency a supplier reports in. It constrains the shape
        of a declaration, not the value of a stamped copy. Widening this test to
        every table would make it fail on that and teach the next reader the
        wrong lesson.
        """
        tables = [NEW_TABLE, *UNOWNED_CURRENCY_COLUMNS]
        with connection.cursor() as cur:
            cur.execute("""
                SELECT c.conrelid::regclass::text, c.conname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.contype = 'c'
                  AND a.attname = 'currency'
                  AND c.conrelid::regclass::text = ANY(%s)
            """, [tables])
            found = sorted(f"{table}.{name}" for table, name in cur.fetchall())

        self.assertEqual(found, [], "a currency CHECK constraint now exists — "
                                    "see this module's docstring")

    def test_the_unowned_columns_are_not_touched_by_this_ticket(self):
        """Recorded as a gap, not claimed.

        The vacuity risk is the point: if one of these tables were renamed or
        dropped from under the list, "this ticket did not touch it" would pass
        by naming nothing. So each is resolved against the live catalogue first.

        **This test is MEANT to go red when a later slice does its job**, which
        is the same shape as `test_every_seeded_entry_is_still_a_real_violation`
        in `apps/platform/tests/test_model_naming.py`: a record of a debt that
        must be edited when the debt is paid, so paying it and recording the
        payment are one act rather than two.

        **IT HAS NOW FIRED ONCE AND THE COUNT IN ITS NAME WENT WITH IT (#368).**
        Two of the seven were paid in the commit that split the container: the
        assignment table was deleted outright, and the container's own line
        went because the Pricing Book it became has no currency column at all.
        Five are left. The failure message says what to do about it, because a
        tripwire whose message reads as "restore the table" would be worse than
        no tripwire at all — and the list's own comment records why the rule
        table's line was NOT one of the two, which is the half a ticket's
        arithmetic got wrong.
        """
        stale = (
            "this list records the unowned currency-constraint gap as it stood "
            "at #269. If a later slice deleted or rebuilt the table, the fix is "
            "to DELETE the line from UNOWNED_CURRENCY_COLUMNS in this module — "
            "not to restore the table. Slice 4 is expected to do exactly that "
            "to ubb_rate_card_assignment."
        )
        with connection.cursor() as cur:
            for table in UNOWNED_CURRENCY_COLUMNS:
                with self.subTest(table=table):
                    self.assertIsNotNone(
                        _table_of(table), f"{table} no longer exists — {stale}")
                    cur.execute("""
                        SELECT count(*) FROM information_schema.columns
                        WHERE table_name = %s AND column_name = 'currency'
                    """, [table])
                    self.assertEqual(
                        cur.fetchone()[0], 1,
                        f"{table} lost its currency column — {stale}")


class TheHistoryStillReplaysTest(TestCase):
    """A rename migration is worthless if the chain in front of it cannot run.

    The suite's own test database is built by replaying every migration, so
    reaching this assertion at all is most of the proof.

    **There is deliberately no "this is the last migration in the app" test.**
    It would read as a tighter check and would in fact be a trap: #270 — the
    ticket this one blocks — adds the child record to this same app, so the
    assertion would go red on the very next commit in the chain while proving
    nothing the ticket asks for. "Nothing in this app is waiting to be made" is
    already the job of `makemigrations --check`, which is an acceptance
    criterion in its own right and does not rot as the chain grows.
    """

    def test_it_replaces_nothing(self):
        """It has to run on every database that needs it, so a `replaces` here
        would skip it on exactly those."""
        loader = MigrationLoader(connection)

        self.assertFalse(
            loader.get_migration(APP_LABEL, RENAME_MIGRATION).replaces)
