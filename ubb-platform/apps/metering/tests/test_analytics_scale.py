"""F2.1 — sargable half-open UTC day windows.

Three nets over the ``effective_at__date`` -> half-open-range rewrite:

1. Boundary equivalence: the rewrite must not move any window edge by a
   microsecond — events at the exact first/last representable microsecond of
   the window must land on the same side as the old ``__date`` casts
   (exclusive-end query functions AND the inclusive-end analytics endpoints).
2. SQL-shape regression: no rewritten WHERE clause may contain the
   sargability-defeating ``AT TIME ZONE`` / ``::date`` cast. Deterministic and
   planner-independent. (TruncDate/TruncHour in SELECT/GROUP BY is legitimate
   output bucketing — only the WHERE clause is constrained.)
3. Planner proof (Postgres): with seqscan disabled, the rewritten range
   filters are actually served by the composite btrees — the whole point.
"""
import re
from datetime import date, datetime, timezone as dt_timezone

from django.db import connection
from django.test import TestCase, Client
from django.test.utils import CaptureQueriesContext

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.metering import queries
from core.time_windows import utc_day_start
from core.vocabulary import ANALYTICS_MEASURE_SUPPLIER_COGS


def _utc(y, mo, d, h=0, mi=0, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=dt_timezone.utc)


def _pin(event, effective_at):
    """effective_at is auto_now_add and Posting.save() is insert-only — a
    queryset update bypasses both and pins the timestamp."""
    Posting.objects.filter(id=event.id).update(effective_at=effective_at)


def _seed(tenant, customer, n, effective_at, billed=1_000_000, provider_cost=600_000, **extra):
    ev = Posting.objects.create(
        tenant=tenant, customer=customer,
        idempotency_key=f"idem_f21_{n}",
        billed_cost_micros=billed, provider_cost_micros=provider_cost, **extra)
    _pin(ev, effective_at)
    return ev


# The four window-edge instants around June 2026.
MAY_LAST_MICRO = _utc(2026, 5, 31, 23, 59, 59, 999999)   # outside [Jun 1, Jul 1)
JUNE_FIRST_MICRO = _utc(2026, 6, 1)                       # inside (start, inclusive)
JUNE_LAST_MICRO = _utc(2026, 6, 30, 23, 59, 59, 999999)  # inside (last representable)
JULY_FIRST_MICRO = _utc(2026, 7, 1)                       # outside (exclusive end)


class BoundaryEquivalenceTest(TestCase):
    """Events at the exact window edges; the half-open rewrite must count
    exactly the rows the old __date casts did."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="F21 Boundary", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c_f21")
        for i, ts in enumerate(
                [MAY_LAST_MICRO, JUNE_FIRST_MICRO, JUNE_LAST_MICRO, JULY_FIRST_MICRO]):
            _seed(self.tenant, self.customer, i, ts, provider="openai")

    # --- exclusive-end [start, end) functions ---

    def test_period_totals_counts_exactly_the_half_open_window(self):
        totals = queries.get_period_totals(self.tenant.id, date(2026, 6, 1), date(2026, 7, 1))
        self.assertEqual(totals["event_count"], 2)
        self.assertEqual(totals["total_cost_micros"], 2_000_000)

    def test_period_totals_edges_land_in_adjacent_windows(self):
        # The May last-microsecond event belongs to May's window only...
        may = queries.get_period_totals(self.tenant.id, date(2026, 5, 1), date(2026, 6, 1))
        self.assertEqual(may["event_count"], 1)
        # ...and the July first-microsecond event to July's window only.
        july = queries.get_period_totals(self.tenant.id, date(2026, 7, 1), date(2026, 8, 1))
        self.assertEqual(july["event_count"], 1)

    def test_customer_cost_totals_half_open(self):
        t = queries.get_customer_cost_totals(
            self.tenant.id, self.customer.id, date(2026, 6, 1), date(2026, 7, 1))
        self.assertEqual(t["event_count"], 2)
        self.assertEqual(t["billed_cost_micros"], 2_000_000)
        self.assertEqual(t["provider_cost_micros"], 1_200_000)

    def test_per_customer_cost_totals_half_open(self):
        rows = queries.get_per_customer_cost_totals(
            self.tenant.id, date(2026, 6, 1), date(2026, 7, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["event_count"], 2)

    # --- inclusive-end (date <= end_date) call sites ---
    #
    # ⚠ FOUR OF THESE WERE FIVE SEPARATE SURFACES AND ARE NOW ONE (#501). The
    # tenant-wide daily rollup, the day-or-hour series and the usage report each
    # resolved an inclusive end date for itself, and each had a case here. The
    # one economic query resolves it once, so the edge is asked once — and the
    # fixture is the thing that matters either way: an event at the last
    # representable microsecond of the end date must be INSIDE, and midnight of
    # the following day must be outside.

    def _economics(self, start, end, bucket=None):
        return queries.economics(
            self.tenant.id, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
            bucket=bucket,
            filters=queries.EconomicFilters(start_date=start, end_date=end))

    def _cost(self, answer, row=0):
        return next(entry["amount_micros"]
                    for entry in answer["rows"][row]["measures"]
                    if entry["measure"] == ANALYTICS_MEASURE_SUPPLIER_COGS)

    def test_the_one_query_takes_the_last_microsecond_of_its_end_date(self):
        answer = self._economics(date(2026, 6, 1), date(2026, 6, 30))
        # Both June events, the 06-30T23:59:59.999999 one in particular;
        # 07-01T00:00:00 and the May event are outside.
        self.assertEqual(self._cost(answer), 1_200_000)

    def test_and_the_day_before_it_belongs_to_the_previous_window(self):
        answer = self._economics(date(2026, 5, 1), date(2026, 5, 31))
        self.assertEqual(self._cost(answer), 600_000)

    def test_its_buckets_split_that_same_window(self):
        answer = self._economics(date(2026, 6, 1), date(2026, 6, 30),
                                 bucket="day")
        self.assertEqual([row["bucket_start"][:10] for row in answer["rows"]],
                         ["2026-06-01", "2026-06-30"])
        self.assertTrue(all(self._cost(answer, index) == 600_000
                            for index in range(len(answer["rows"]))))

    def test_the_route_resolves_the_same_edge(self):
        _, raw_key = TenantApiKey.create_key(self.tenant, label="f21")
        resp = Client().get(
            "/api/v1/metering/analytics/economics",
            {"measures": ANALYTICS_MEASURE_SUPPLIER_COGS,
             "start_date": "2026-06-01", "end_date": "2026-06-30"},
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self.assertEqual(self._cost(resp.json()), 1_200_000)


class SqlShapeRegressionTest(TestCase):
    """No rewritten WHERE clause may reintroduce the cast forms that defeat
    the btrees. Deterministic — inspects SQL text, not the planner."""

    @staticmethod
    def _where_clause(sql):
        m = re.search(r"\bWHERE\b(.*?)(?:\bGROUP\s+BY\b|\bORDER\s+BY\b|\bLIMIT\b|$)",
                      sql, re.IGNORECASE | re.DOTALL)
        return m.group(1) if m else ""

    def _assert_sargable(self, ctx):
        self.assertGreater(len(ctx.captured_queries), 0)
        for q in ctx.captured_queries:
            where = self._where_clause(q["sql"])
            self.assertNotIn("AT TIME ZONE", where.upper(), q["sql"])
            self.assertNotIn("::date", where.lower(), q["sql"])

    def test_rewritten_query_functions_have_cast_free_where(self):
        """⚠ FIVE OF THE EIGHT CALLS HERE WERE THE SURFACES #501 COLLAPSED, and
        the one query replaces them in this check as it does everywhere else —
        ungrouped, grouped and bucketed, because those are three different
        querysets and only the first would have been exercised by a bare call."""
        tenant = Tenant.objects.create(name="F21 Shape", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="c_f21_shape")
        s, e = date(2026, 6, 1), date(2026, 7, 1)
        window = queries.EconomicFilters(start_date=s, end_date=e)
        with CaptureQueriesContext(connection) as ctx:
            queries.get_period_totals(tenant.id, s, e)
            queries.get_customer_cost_totals(tenant.id, customer.id, s, e)
            queries.get_per_customer_cost_totals(tenant.id, s, e)
            for grouping, bucket in (((), None), (("field:provider",), None),
                                     ((), "day"), ((), "hour")):
                queries.economics(
                    tenant.id, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                    group_by=grouping, bucket=bucket, filters=window)
        self._assert_sargable(ctx)

    def test_the_economics_endpoint_has_cast_free_where(self):
        tenant = Tenant.objects.create(name="F21 Shape EP", products=["metering"])
        _, raw_key = TenantApiKey.create_key(tenant, label="f21")
        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(
                "/api/v1/metering/analytics/economics",
                {"measures": ANALYTICS_MEASURE_SUPPLIER_COGS,
                 "start_date": "2026-06-01", "end_date": "2026-06-30"},
                HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 200, resp.content)
        self._assert_sargable(ctx)


class PlannerIndexProofTest(TestCase):
    """With enable_seqscan off, the half-open range filters must be served by
    the composite btrees (plain Index Scan or Bitmap on the named index)."""

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("EXPLAIN index proof requires Postgres")
        self.tenant = Tenant.objects.create(name="F21 Planner", products=["metering"])
        self.other = Tenant.objects.create(name="F21 Planner Other")
        self.customers = [
            Customer.objects.create(tenant=self.tenant, external_id=f"c_f21_pl_{i}")
            for i in range(8)]
        other_customer = Customer.objects.create(tenant=self.other, external_id="c_f21_pl_x")
        # Enough rows that the composite indexes win on cost by a decisive
        # multiple (single-column paths must fetch 6-8x the tuples), not a
        # coin-flip that cross-suite heap/index bloat could tip.
        rows = [Posting(tenant=self.tenant, customer=self.customers[i % 8],
                           idempotency_key=f"idem_pl_{i}",
                           billed_cost_micros=1_000)
                for i in range(1000)]
        rows += [Posting(tenant=self.other, customer=other_customer,
                            idempotency_key=f"idem_plo_{i}",
                            billed_cost_micros=1_000)
                 for i in range(1000)]
        Posting.objects.bulk_create(rows, batch_size=500)
        with connection.cursor() as cur:
            # Scatter effective_at (deterministically) across Jan-Jun in ONE
            # pass: heap order stays insert order, so effective_at has ~zero
            # heap correlation — like a real production table — instead of
            # the artificially perfect correlation that would make the
            # single-column effective_at btree look cheaper than the
            # composites. The June window then selects ~17% of rows.
            cur.execute("SELECT setseed(0.42)")
            cur.execute(
                "UPDATE ubb_posting SET effective_at = "
                "timestamptz '2026-01-01 00:00:00+00' "
                "+ make_interval(days => (random() * 180)::int)")
            # F4.2: give created_at the same scatter so the arrival-basis
            # (tenant, created_at) range proof below sees a realistic
            # distribution too (bulk_create stamped every row "now").
            cur.execute("UPDATE ubb_posting SET created_at = effective_at")
            cur.execute("ANALYZE ubb_posting")
            # LOCAL: scoped to the test transaction, reverted on rollback.
            # Bitmap scans are also disabled so the choice between the
            # composite btree and the single-column FK btree is decided by
            # which one can serve the predicate as an Index Cond — at this
            # tiny table scale bitmap-heap costs otherwise coin-flip them.
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("SET LOCAL enable_bitmapscan = off")

    def _assert_range_served_by(self, qs, index_name, field="effective_at"):
        # Production sites are aggregates (ordering cleared) — mirror that.
        plan = qs.order_by().explain()
        self.assertIn(index_name, plan)
        # The actual sargability property: the range bounds must be an
        # Index Cond, not a post-scan Filter (a casted predicate could only
        # ever be a Filter, even with the index name in the plan).
        index_conds = [line for line in plan.splitlines() if "Index Cond:" in line]
        self.assertTrue(any(field in line for line in index_conds), plan)

    # A few-day window (typical analytics drill-down) keeps the range
    # estimate selective enough that the composite path costs a decisive
    # multiple less than the single-column paths on every Postgres version,
    # rather than tying within bloat noise on a whole-month window.

    def test_period_totals_window_served_by_tenant_effective_index(self):
        qs = Posting.objects.filter(
            tenant_id=self.tenant.id,
            effective_at__gte=utc_day_start(date(2026, 6, 1)),
            effective_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_tenant_effective")

    def test_customer_cost_totals_window_served_by_customer_effective_index(self):
        qs = Posting.objects.filter(
            tenant_id=self.tenant.id, customer_id=self.customers[0].id,
            effective_at__gte=utc_day_start(date(2026, 6, 1)),
            effective_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_customer_effective")

    def test_billable_created_window_served_by_tenant_created_index(self):
        """F4.2: the created-basis iter_billable_usage_events query shape
        (drawdown repair scans by ARRIVAL time) must be served by the
        (tenant, created_at) composite — the index added alongside the
        caller-timestamp work — with the created_at bounds as an Index Cond."""
        qs = Posting.objects.filter(
            tenant_id=self.tenant.id, billed_cost_micros__gt=0,
            created_at__gte=utc_day_start(date(2026, 6, 1)),
            created_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_tenant_created",
                                     field="created_at")


# ---------------------------------------------------------------------------
# F2.2 — the open bag's GIN opclass, on the bag that survived #273
# ---------------------------------------------------------------------------

class OpenBagGinSchemaTest(TestCase):
    """Assert the schema has exactly the right GIN index on the open bag.

    0022 swapped the retiring bag's index to the default opclass; #273
    folded that bag into the survivor and the index moved with the
    filtering, this time declared on the model rather than as raw SQL.

    CONCURRENTLY DDL cannot run inside a transaction, so we do not run the
    migration functions here.  Instead we assert the schema state produced by
    the migration that was already applied to the test DB (Django rebuilds the
    test DB from scratch on every run, so the migration functions execute once
    per test run in the normal migrate path — without the TestCase transaction
    wrapper because atomic=False).
    """

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("Schema assertion requires Postgres")

    def test_new_jsonb_ops_index_exists(self):
        """idx_posting_metadata (default jsonb_ops) must be present."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'ubb_posting'
                  AND indexname = 'idx_posting_metadata';
            """)
            row = cur.fetchone()
        self.assertIsNotNone(row, "idx_posting_metadata not found in pg_indexes")
        # Default jsonb_ops index has NO opclass qualifier — just 'gin (…)'
        self.assertNotIn("jsonb_path_ops", row[1],
                         f"Expected jsonb_ops (no qualifier) but got: {row[1]}")
        self.assertIn("gin", row[1].lower(), row[1])

    def test_old_jsonb_path_ops_index_absent(self):
        """idx_usage_event_tags (jsonb_path_ops) must have been dropped."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'ubb_posting'
                  AND indexname = 'idx_usage_event_tags';
            """)
            row = cur.fetchone()
        self.assertIsNone(row,
                          "Old idx_usage_event_tags (jsonb_path_ops) still present — swap failed")

    def test_exactly_one_gin_index_on_the_open_bag(self):
        """Only one GIN index on the open bag may exist."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'ubb_posting'
                  AND indexname LIKE '%metadata%';
            """)
            rows = cur.fetchall()
        self.assertEqual(len(rows), 1,
                         f"Expected exactly 1 index, found: {[r[0] for r in rows]}")


class OpenBagGinPlannerProofTest(TestCase):
    """Planner proof: both has_key (?) and containment (@>) are served by
    idx_posting_metadata (the jsonb_ops GIN index on the surviving bag).

    GIN indexes in Postgres are always accessed via Bitmap Index Scan, never
    plain Index Scan.  Therefore we CANNOT disable bitmapscan (unlike F2.1
    which proves btree index-cond access).  Instead:

    * We disable seqscan only.
    * The query filters on a highly selective value (only 1 row matches) — so
      the GIN bitmap path is decisively cheaper than any FK btree + heap filter.
    * We insert one "needle" row with a rare tag value and a large number of
      "haystack" rows with no rare key, so the GIN estimate for the selective value
      is tiny relative to the table size.

    EXPLAIN(FORMAT TEXT) output for a Bitmap path contains both
    "Bitmap Index Scan" and the index name; we assert both.
    """

    GIN_INDEX = "idx_posting_metadata"

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("EXPLAIN index proof requires Postgres")
        self.tenant = Tenant.objects.create(name="F22 GIN Planner", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_f22_gin")

        # Haystack: 1000 rows with a common key so the rare needle is selective.
        haystack = [Posting(
            tenant=self.tenant, customer=self.customer,
            idempotency_key=f"idem_f22_h{i}",
            billed_cost_micros=500, metadata={"env": "prod", "team": "common"})
            for i in range(1000)]
        Posting.objects.bulk_create(haystack, batch_size=500)

        # Needle: 1 row with a rare unique value, plus a common key for @>.
        self.needle = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="idem_f22_needle",
            billed_cost_micros=1_000,
            metadata={"env": "prod", "rare_key": "unique_val_xyz", "team": "common"})

        with connection.cursor() as cur:
            cur.execute("SELECT setseed(0.22)")
            cur.execute(
                "UPDATE ubb_posting "
                "SET effective_at = timestamptz '2026-01-01 00:00:00+00' "
                "+ make_interval(days => (random() * 180)::int) "
                "WHERE tenant_id = %s", [self.tenant.id])
            cur.execute("ANALYZE ubb_posting")
            # Disable seqscan only; bitmapscan must stay ON because GIN indexes
            # are only accessible via Bitmap Index Scan in Postgres.
            cur.execute("SET LOCAL enable_seqscan = off")

    def _explain(self, qs):
        return qs.order_by().explain()

    def test_has_key_served_by_gin_index(self):
        """metadata__has_key('rare_key') compiles to the ? operator — rare key
        means the GIN bitmap path is cheap vs. FK btree + heap filter."""
        qs = Posting.objects.filter(metadata__has_key="rare_key")
        plan = self._explain(qs)
        self.assertIn(self.GIN_INDEX, plan,
                      f"GIN index not used for has_key.  Plan:\n{plan}")

    def test_containment_served_by_same_gin_index(self):
        """metadata__contains({'rare_key': ...}) compiles to @> — jsonb_ops serves
        both ? and @>, proving the swap lost nothing for containment queries."""
        qs = Posting.objects.filter(
            metadata__contains={"rare_key": "unique_val_xyz"})
        plan = self._explain(qs)
        self.assertIn(self.GIN_INDEX, plan,
                      f"GIN index not used for containment (@>).  Plan:\n{plan}")


# ---------------------------------------------------------------------------
# F2.3 — SQL pushdown for grouped aggregation
# ---------------------------------------------------------------------------
#
# THE KEYED-ROLLUP CLASS WAS HERE AND IS GONE WITH BOTH OF ITS SUBJECTS (#501).
# It froze the output contract of the two rollups that grouped by a key read out
# of the open bag, pinned their query counts against a row-count-dependent loop,
# caught the GROUP BY trap two rows with the same key and different timestamps
# produce, and compared each against a Python reference implementation.
#
# Both rollups went with the routes that served them, and the capability has no
# replacement on purpose: the declared grouping contract publishes what a tenant
# may group by, and an unbounded keyspace is what it deliberately does not have.
#
# ⚠ WHAT DID NOT DIE WITH THEM IS THE INDEX, and it is still proved above.
# `OpenBagGinSchemaTest` and `OpenBagGinPlannerProofTest` read the bag directly
# through the ORM, because the surfaces that still filter on it — the
# per-customer event listing, and the invoice-line breakdown a later ticket
# migrates — are filter surfaces rather than grouping ones.
#
# The completeness claim this class carried for those two rollups is the one
# every other total's is asserted with, in
# `api/v1/tests/test_a_cost_total_says_what_it_excluded.py`, against the one
# economic query and per group.
