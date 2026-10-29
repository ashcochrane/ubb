"""The usage record is the Posting, and its table carries its keys and indexes
under their final names (#269, #190).

`Posting` sits on `ubb_posting`; `Refund.posting` points at it, and the tenant
and the customer reach it as `postings`. What this module holds of that table is
what a reader, a query planner and an idempotent retry each rely on:

* its primary key is the client-generated `id`, and it owns no sequence;
* `uq_posting_idempotency` exists under that name and still bites;
* the five indexes the usage row always carried (`idx_posting_customer_effective`,
  `_tenant_effective`, `_work_attribution`, `_tenant_created` and
  `_stop_context`), and `idx_posting_metadata` for the open bag's filters, exist
  under those names;
* the inbound foreign key from `ubb_refund` lands on it;
* its `currency` column is a three-character code defaulting to `usd` (what
  holds the VALUE is #555's `ck_posting_currency_usd`, asserted with every
  currency column in `apps/platform/tests/test_v1_is_usd_only.py`).

**Every name is the FINAL one, asserted BY NAME.** A constraint or index rebuilt
under Django's own naming would still work and would carry a different name,
which is how one would discover afterwards that it had been rebuilt rather than
declared; the names are what `Posting.Meta` declares and what the schema
migration creates.

Before the cutover (#190) these facts were held in `test_posting_rename.py`,
over the table `usage/0030` renamed: the rename's operations and the SQL it
rendered (a rename and never a create-plus-drop, in an order that left the
inbound foreign key alone), the retired table gone rather than left beside it,
and the constraint and indexes carried under the names they arrived with. The
cutover's fresh schema creates them under their final names
(`uq_usage_event_idempotency_v2` became `uq_posting_idempotency`, each
`idx_usage_*` an `idx_posting_*`), and the claims about the rename retired with
the migration that made it. What survived them is here.
"""
import datetime

from django.db import IntegrityError, connection
from django.test import TestCase

from apps.metering.usage.models import BackfillDirtyPeriod, Posting, Refund
from apps.metering.usage.tests._helpers import a_posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

TABLE = "ubb_posting"
FOREIGN_KEY_COLUMN = "posting_id"
REFUND_TABLE = "ubb_refund"

#: The unique constraint and the named indexes the table carries, spelled out
#: under their final names. Listed here, rather than read off the model, so a
#: change that quietly renames or rebuilds one goes red against a reader of
#: THIS module.
IDEMPOTENCY_CONSTRAINT = "uq_posting_idempotency"
NAMED_INDEXES = (
    "idx_posting_customer_effective",
    "idx_posting_tenant_effective",
    "idx_posting_work_attribution",
    "idx_posting_tenant_created",
    "idx_posting_stop_context",
    "idx_posting_metadata",
)


def _table_of(name):
    """The live table for a name, or `None`."""
    with connection.cursor() as cur:
        cur.execute("SELECT to_regclass(%s)", [name])
        return cur.fetchone()[0]


class ThePostingTableCarriesItsKeysAndIndexesTest(TestCase):
    """Read against the database this suite's own migrations built."""

    def test_the_table_tracks_the_model_name(self):
        # ADR-0006 §9. G9 in apps/platform/tests/test_model_naming.py derives
        # the same name mechanically; it is spelled out here because the
        # assertions below address the table literally.
        self.assertEqual(Posting._meta.db_table, TABLE)
        self.assertIsNotNone(_table_of(TABLE))

    def test_the_primary_key_is_the_id(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT a.attname
                FROM pg_index i
                JOIN pg_attribute a
                  ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                WHERE i.indrelid = %s::regclass AND i.indisprimary
            """, [TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()], ["id"])

    def test_the_table_owns_no_sequence(self):
        """Stated rather than asserted vacuously.

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
            """, [TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()], [])

    def test_the_unique_idempotency_constraint_carries_its_final_name(self):
        """By NAME, not merely by existence.

        A drop-and-recreate under Django's own naming would produce a working
        unique index with a different name, which is how one would discover
        afterwards that the constraint had been rebuilt rather than declared.
        """
        with connection.cursor() as cur:
            cur.execute("""
                SELECT conname FROM pg_constraint
                WHERE conrelid = %s::regclass AND contype = 'u'
            """, [TABLE])
            self.assertIn(IDEMPOTENCY_CONSTRAINT,
                          {row[0] for row in cur.fetchall()})

    def test_it_refuses_a_duplicate_idempotency_key(self):
        """The constraint is not just present, it bites.

        A constraint can exist as a catalogue row and still not cover the
        columns it was written for — this is the behaviour the row is there to
        produce, and it is what makes a retried recording a replay.
        """
        tenant = Tenant.objects.create(name="T")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        a_posting(tenant=tenant, customer=customer, idempotency_key="dup")

        with self.assertRaises(IntegrityError) as refusal:
            a_posting(tenant=tenant, customer=customer, idempotency_key="dup")
        self.assertIn(IDEMPOTENCY_CONSTRAINT, str(refusal.exception))

    def test_every_named_index_is_present_under_its_final_name(self):
        with connection.cursor() as cur:
            cur.execute("SELECT indexname FROM pg_indexes WHERE tablename = %s",
                        [TABLE])
            live = {row[0] for row in cur.fetchall()}

        missing = sorted(set(NAMED_INDEXES) - live)
        self.assertEqual(missing, [], f"named indexes are missing: {live}")

    def test_the_inbound_foreign_key_points_at_the_posting_table(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT a.attname
                FROM pg_constraint c
                JOIN pg_attribute a
                  ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey)
                WHERE c.conrelid = %s::regclass
                  AND c.confrelid = %s::regclass
                  AND c.contype = 'f'
            """, [REFUND_TABLE, TABLE])
            self.assertEqual([row[0] for row in cur.fetchall()],
                             [FOREIGN_KEY_COLUMN])


class ThePostingsNeighboursPointAtItTest(TestCase):
    """The two models in the same module that reference the posting."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.posting = a_posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_1",
            billed_cost_micros=1_000_000)

    def test_the_refund_points_at_the_posting_by_its_name(self):
        refund = Refund.objects.create(
            tenant=self.tenant, customer=self.customer, posting=self.posting,
            amount_micros=500_000)

        self.assertEqual(Refund.objects.get(posting=self.posting), refund)
        self.assertEqual(self.posting.refund, refund)

    def test_the_refunds_string_traverses_to_its_parent(self):
        """`__str__` reads a field ON THE POSTING, so a broken relation raises
        `AttributeError` the first time anything prints one — in the admin, in a
        shell, or inside a log line during an incident.

        The value it prints is asserted next door in `test_models.py`, not here:
        that is the model's own test module and owns what the string SAYS, and
        this one owns only that the traversal resolves. Asserting the value here
        too would be a second place to edit for one change.
        """
        refund = Refund.objects.create(
            tenant=self.tenant, customer=self.customer, posting=self.posting,
            amount_micros=500_000)

        rendered = str(refund)

        self.assertTrue(rendered.startswith("Refund("), rendered)
        self.assertIn("500000", rendered)

    def test_the_backfill_marker_keeps_its_own_table_and_writes(self):
        """It references the posting by (tenant, customer) rather than by a
        foreign key, so there is nothing on it to point at the posting — which
        is exactly why it is worth pinning that it has its own table and takes
        a row."""
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


class TheCurrencyColumnTest(TestCase):
    """The posting's currency column, by shape and by default.

    What holds its VALUE is #555's, and is asserted where every currency
    column is (`apps/platform/tests/test_v1_is_usd_only.py`).
    """

    def test_the_column_is_a_three_character_code(self):
        with connection.cursor() as cur:
            cur.execute("""
                SELECT data_type, character_maximum_length, column_default
                FROM information_schema.columns
                WHERE table_name = %s AND column_name = 'currency'
            """, [TABLE])
            row = cur.fetchone()

        self.assertIsNotNone(row, "the posting table carries no currency column")
        data_type, width, _default = row
        self.assertEqual((data_type, width), ("character varying", 3))

    def test_it_defaults_to_the_lowercase_code(self):
        """Spec §K2: lowercase stands.

        Eight columns default to a lowercase code under an in-code convention
        comment, against a merged decision whose SQL sketch is uppercase. There
        is no currency concept in `domain-vocabulary/` at all, so no oracle
        settles the casing — the sketch was illustrative, the convention is
        consistent, and it matches the payment rail's own casing.
        """
        tenant = Tenant.objects.create(name="T")
        customer = Customer.objects.create(tenant=tenant, external_id="c1")

        posting = a_posting(
            tenant=tenant, customer=customer,
            idempotency_key="i1")

        self.assertEqual(Posting._meta.get_field("currency").default, "usd")
        self.assertEqual(posting.currency, "usd")
