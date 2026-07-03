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
from apps.metering.usage.models import UsageEvent
from apps.metering import queries
from core.time_windows import utc_day_start


def _utc(y, mo, d, h=0, mi=0, s=0, us=0):
    return datetime(y, mo, d, h, mi, s, us, tzinfo=dt_timezone.utc)


def _pin(event, effective_at):
    """effective_at is auto_now_add and UsageEvent.save() is insert-only — a
    queryset update bypasses both and pins the timestamp."""
    UsageEvent.objects.filter(id=event.id).update(effective_at=effective_at)


def _seed(tenant, customer, n, effective_at, billed=1_000_000, provider_cost=600_000, **extra):
    ev = UsageEvent.objects.create(
        tenant=tenant, customer=customer,
        request_id=f"req_f21_{n}", idempotency_key=f"idem_f21_{n}",
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

    def test_dimensional_margin_half_open(self):
        rows = queries.get_dimensional_margin(
            self.tenant.id, group_by="provider",
            start_date=date(2026, 6, 1), end_date=date(2026, 7, 1))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dimension"], "openai")
        self.assertEqual(rows[0]["event_count"], 2)

    # --- inclusive-end (date <= end_date) call sites ---

    def test_revenue_analytics_inclusive_end(self):
        result = queries.get_revenue_analytics(
            self.tenant.id, start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        # Includes BOTH June events (the 06-30T23:59:59.999999 one in particular),
        # excludes 07-01T00:00:00 and the May event.
        self.assertEqual(result["total_billed_cost_micros"], 2_000_000)
        self.assertEqual(len(result["daily"]), 2)

    def test_revenue_analytics_inclusive_end_includes_last_microsecond_of_end_date(self):
        result = queries.get_revenue_analytics(
            self.tenant.id, start_date=date(2026, 5, 1), end_date=date(2026, 5, 31))
        self.assertEqual(result["total_billed_cost_micros"], 1_000_000)

    def test_usage_analytics_endpoint_inclusive_end(self):
        _, raw_key = TenantApiKey.create_key(self.tenant, label="f21")
        resp = Client().get(
            "/api/v1/metering/analytics/usage?start_date=2026-06-01&end_date=2026-06-30",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # 06-30T23:59:59.999999 included; 07-01T00:00:00 and May excluded.
        self.assertEqual(body["total_events"], 2)
        self.assertEqual(body["total_billed_cost_micros"], 2_000_000)

    def test_usage_timeseries_inclusive_end(self):
        # Aligned with the /analytics/usage rollup: end_date is INCLUSIVE, so
        # the 06-30 bucket is present (its last-microsecond event counts) while
        # the 07-01T00:00:00 event and the May event are excluded.
        series = queries.get_usage_timeseries(
            self.tenant.id, start_date=date(2026, 6, 1), end_date=date(2026, 6, 30))
        self.assertEqual([s["bucket"] for s in series], ["2026-06-01", "2026-06-30"])
        self.assertTrue(all(s["event_count"] == 1 for s in series))


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
        tenant = Tenant.objects.create(name="F21 Shape", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="c_f21_shape")
        s, e = date(2026, 6, 1), date(2026, 7, 1)
        with CaptureQueriesContext(connection) as ctx:
            queries.get_period_totals(tenant.id, s, e)
            queries.get_revenue_analytics(tenant.id, start_date=s, end_date=date(2026, 6, 30))
            queries.get_customer_cost_totals(tenant.id, customer.id, s, e)
            queries.get_usage_timeseries(tenant.id, start_date=s, end_date=e)
            queries.get_usage_timeseries(tenant.id, granularity="hour", start_date=s, end_date=e)
            queries.get_per_customer_cost_totals(tenant.id, s, e)
            queries.get_dimensional_margin(tenant.id, group_by="provider", start_date=s, end_date=e)
            queries.get_dimensional_margin(tenant.id, tag_key="model", start_date=s, end_date=e)
        self._assert_sargable(ctx)

    def test_usage_analytics_endpoint_has_cast_free_where(self):
        tenant = Tenant.objects.create(name="F21 Shape EP", products=["metering"])
        _, raw_key = TenantApiKey.create_key(tenant, label="f21")
        client = Client()
        with CaptureQueriesContext(connection) as ctx:
            resp = client.get(
                "/api/v1/metering/analytics/usage?start_date=2026-06-01&end_date=2026-06-30",
                HTTP_AUTHORIZATION=f"Bearer {raw_key}")
        self.assertEqual(resp.status_code, 200)
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
        rows = [UsageEvent(tenant=self.tenant, customer=self.customers[i % 8],
                           request_id=f"req_pl_{i}", idempotency_key=f"idem_pl_{i}",
                           billed_cost_micros=1_000)
                for i in range(1000)]
        rows += [UsageEvent(tenant=self.other, customer=other_customer,
                            request_id=f"req_plo_{i}", idempotency_key=f"idem_plo_{i}",
                            billed_cost_micros=1_000)
                 for i in range(1000)]
        UsageEvent.objects.bulk_create(rows, batch_size=500)
        with connection.cursor() as cur:
            # Scatter effective_at (deterministically) across Jan-Jun in ONE
            # pass: heap order stays insert order, so effective_at has ~zero
            # heap correlation — like a real production table — instead of
            # the artificially perfect correlation that would make the
            # single-column effective_at btree look cheaper than the
            # composites. The June window then selects ~17% of rows.
            cur.execute("SELECT setseed(0.42)")
            cur.execute(
                "UPDATE ubb_usage_event SET effective_at = "
                "timestamptz '2026-01-01 00:00:00+00' "
                "+ make_interval(days => (random() * 180)::int)")
            # F4.2: give created_at the same scatter so the arrival-basis
            # (tenant, created_at) range proof below sees a realistic
            # distribution too (bulk_create stamped every row "now").
            cur.execute("UPDATE ubb_usage_event SET created_at = effective_at")
            cur.execute("ANALYZE ubb_usage_event")
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
        qs = UsageEvent.objects.filter(
            tenant_id=self.tenant.id,
            effective_at__gte=utc_day_start(date(2026, 6, 1)),
            effective_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_tenant_effective")

    def test_customer_cost_totals_window_served_by_customer_effective_index(self):
        qs = UsageEvent.objects.filter(
            tenant_id=self.tenant.id, customer_id=self.customers[0].id,
            effective_at__gte=utc_day_start(date(2026, 6, 1)),
            effective_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_customer_effective")

    def test_billable_created_window_served_by_tenant_created_index(self):
        """F4.2: the created-basis iter_billable_usage_events query shape
        (drawdown repair scans by ARRIVAL time) must be served by the
        (tenant, created_at) composite — the index added alongside the
        caller-timestamp work — with the created_at bounds as an Index Cond."""
        qs = UsageEvent.objects.filter(
            tenant_id=self.tenant.id, billed_cost_micros__gt=0,
            created_at__gte=utc_day_start(date(2026, 6, 1)),
            created_at__lt=utc_day_start(date(2026, 6, 4)))
        self._assert_range_served_by(qs, "idx_usage_tenant_created",
                                     field="created_at")


# ---------------------------------------------------------------------------
# F2.2 — tags GIN opclass swap tests
# ---------------------------------------------------------------------------

class TagsGinSchemaTest(TestCase):
    """Assert the post-0022 schema has exactly the right tags GIN index.

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
        """idx_usage_event_tags_ops (default jsonb_ops) must be present."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname, indexdef
                FROM pg_indexes
                WHERE tablename = 'ubb_usage_event'
                  AND indexname = 'idx_usage_event_tags_ops';
            """)
            row = cur.fetchone()
        self.assertIsNotNone(row, "idx_usage_event_tags_ops not found in pg_indexes")
        # Default jsonb_ops index has NO opclass qualifier — just 'gin (tags)'
        self.assertNotIn("jsonb_path_ops", row[1],
                         f"Expected jsonb_ops (no qualifier) but got: {row[1]}")
        self.assertIn("gin", row[1].lower(), row[1])

    def test_old_jsonb_path_ops_index_absent(self):
        """idx_usage_event_tags (jsonb_path_ops) must have been dropped."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'ubb_usage_event'
                  AND indexname = 'idx_usage_event_tags';
            """)
            row = cur.fetchone()
        self.assertIsNone(row,
                          "Old idx_usage_event_tags (jsonb_path_ops) still present — swap failed")

    def test_exactly_one_tags_gin_index(self):
        """Only one GIN index on the tags column must exist post-swap."""
        with connection.cursor() as cur:
            cur.execute("""
                SELECT indexname
                FROM pg_indexes
                WHERE tablename = 'ubb_usage_event'
                  AND indexname LIKE '%tags%';
            """)
            rows = cur.fetchall()
        self.assertEqual(len(rows), 1,
                         f"Expected exactly 1 tags index, found: {[r[0] for r in rows]}")


class TagsGinPlannerProofTest(TestCase):
    """Planner proof: both has_key (?) and containment (@>) are served by
    idx_usage_event_tags_ops (the new jsonb_ops GIN index from F2.2).

    GIN indexes in Postgres are always accessed via Bitmap Index Scan, never
    plain Index Scan.  Therefore we CANNOT disable bitmapscan (unlike F2.1
    which proves btree index-cond access).  Instead:

    * We disable seqscan only.
    * The query filters on a highly selective value (only 1 row matches) — so
      the GIN bitmap path is decisively cheaper than any FK btree + heap filter.
    * We insert one "needle" row with a rare tag value and a large number of
      "haystack" rows with no tags, so the GIN estimate for the selective value
      is tiny relative to the table size.

    EXPLAIN(FORMAT TEXT) output for a Bitmap path contains both
    "Bitmap Index Scan" and the index name; we assert both.
    """

    GIN_INDEX = "idx_usage_event_tags_ops"

    def setUp(self):
        if connection.vendor != "postgresql":
            self.skipTest("EXPLAIN index proof requires Postgres")
        self.tenant = Tenant.objects.create(name="F22 GIN Planner", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c_f22_gin")

        # Haystack: 1000 rows with common tag so the rare-value needle is selective.
        haystack = [UsageEvent(
            tenant=self.tenant, customer=self.customer,
            request_id=f"req_f22_h{i}", idempotency_key=f"idem_f22_h{i}",
            billed_cost_micros=500, tags={"env": "prod", "team": "common"})
            for i in range(1000)]
        UsageEvent.objects.bulk_create(haystack, batch_size=500)

        # Needle: 1 row with a rare unique tag value, plus a common key for @>.
        self.needle = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="req_f22_needle", idempotency_key="idem_f22_needle",
            billed_cost_micros=1_000,
            tags={"env": "prod", "rare_key": "unique_val_xyz", "team": "common"})

        with connection.cursor() as cur:
            cur.execute("SELECT setseed(0.22)")
            cur.execute(
                "UPDATE ubb_usage_event "
                "SET effective_at = timestamptz '2026-01-01 00:00:00+00' "
                "+ make_interval(days => (random() * 180)::int) "
                "WHERE tenant_id = %s", [self.tenant.id])
            cur.execute("ANALYZE ubb_usage_event")
            # Disable seqscan only; bitmapscan must stay ON because GIN indexes
            # are only accessible via Bitmap Index Scan in Postgres.
            cur.execute("SET LOCAL enable_seqscan = off")

    def _explain(self, qs):
        return qs.order_by().explain()

    def test_has_key_served_by_gin_index(self):
        """tags__has_key('rare_key') compiles to the ? operator — rare key
        means the GIN bitmap path is cheap vs. FK btree + heap filter."""
        qs = UsageEvent.objects.filter(tags__has_key="rare_key")
        plan = self._explain(qs)
        self.assertIn(self.GIN_INDEX, plan,
                      f"GIN index not used for has_key.  Plan:\n{plan}")

    def test_containment_served_by_same_gin_index(self):
        """tags__contains({'rare_key': ...}) compiles to @> — jsonb_ops serves
        both ? and @>, proving the swap lost nothing for containment queries."""
        qs = UsageEvent.objects.filter(
            tags__contains={"rare_key": "unique_val_xyz"})
        plan = self._explain(qs)
        self.assertIn(self.GIN_INDEX, plan,
                      f"GIN index not used for containment (@>).  Plan:\n{plan}")


# ---------------------------------------------------------------------------
# F2.3 — SQL pushdown for tag/dimension aggregation
# ---------------------------------------------------------------------------

class TagGroupByPushdownTest(TestCase):
    """Output-contract freeze, query-count pins, GROUP-BY-trap regression, and
    BEFORE/AFTER equivalence for the two tag-aggregation rewrites.

    Dataset (tag key = "env"):
      A  env=prod,     billed=3_000_000  provider=1_000_000  effective_at=T1
      B  env=prod,     billed=2_000_000  provider=500_000    effective_at=T2  <- GROUP-BY trap
      C  env=staging,  billed=4_000_000  provider=2_000_000
      D  env=""        billed=1_000_000  provider=400_000    <- empty-string tag value

    All four rows have tags__has_key("env") so all appear in the output.

    Expected get_dimensional_margin (sorted -margin_micros):
      prod    prov=1_500_000 billed=5_000_000 margin=3_500_000 count=2
      staging prov=2_000_000 billed=4_000_000 margin=2_000_000 count=1
      ""      prov=400_000   billed=1_000_000 margin=600_000   count=1

    Expected by_tag (sorted -total_cost_micros):
      prod    total=5_000_000 prov=1_500_000 count=2
      staging total=4_000_000 prov=2_000_000 count=1
      ""      total=1_000_000 prov=400_000   count=1
    """

    TAG_KEY = "env"

    def setUp(self):
        self.tenant = Tenant.objects.create(name="F23 Tag Pushdown", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c_f23")
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="f23")

        def _create(n, tags, billed, provider, ts):
            ev = UsageEvent.objects.create(
                tenant=self.tenant, customer=self.customer,
                request_id=f"req_f23_{n}", idempotency_key=f"idem_f23_{n}",
                billed_cost_micros=billed, provider_cost_micros=provider,
                tags=tags)
            _pin(ev, ts)
            return ev

        _create("A", {"env": "prod"},    3_000_000, 1_000_000, _utc(2026, 6, 1))
        _create("B", {"env": "prod"},    2_000_000,   500_000, _utc(2026, 6, 2))  # different ts
        _create("C", {"env": "staging"}, 4_000_000, 2_000_000, _utc(2026, 6, 1))
        _create("D", {"env": ""},        1_000_000,   400_000, _utc(2026, 6, 1))

    # ------------------------------------------------------------------
    # Reference implementations (the OLD Python-loop logic) used in
    # BEFORE/AFTER equivalence assertions.
    # ------------------------------------------------------------------

    @staticmethod
    def _old_get_dimensional_margin_tag(tenant_id, tag_key):
        """Inline replica of the pre-rewrite tag_key branch."""
        from collections import defaultdict
        from apps.metering.usage.models import UsageEvent as UE

        def _row(dim, provider, billed, count):
            return {"dimension": dim, "provider_cost_micros": provider or 0,
                    "billed_cost_micros": billed or 0,
                    "margin_micros": (billed or 0) - (provider or 0),
                    "event_count": count}

        agg = defaultdict(lambda: {"p": 0, "b": 0, "n": 0})
        for tags, p, b in UE.objects.filter(
                tenant_id=tenant_id, tags__has_key=tag_key
        ).values_list("tags", "provider_cost_micros", "billed_cost_micros"):
            k = (tags or {}).get(tag_key)
            agg[k]["p"] += p or 0
            agg[k]["b"] += b or 0
            agg[k]["n"] += 1
        rows = [_row(k, v["p"], v["b"], v["n"]) for k, v in agg.items()]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    @staticmethod
    def _old_by_tag(tenant_id, tag_key):
        """Inline replica of the pre-rewrite by_tag block."""
        from collections import defaultdict
        from apps.metering.usage.models import UsageEvent as UE

        agg = defaultdict(lambda: {"event_count": 0, "total_cost_micros": 0,
                                   "total_provider_cost_micros": 0})
        for tags, billed, provider in UE.objects.filter(
                tenant_id=tenant_id, tags__has_key=tag_key
        ).values_list("tags", "billed_cost_micros", "provider_cost_micros"):
            val = (tags or {}).get(tag_key)
            agg[val]["event_count"] += 1
            agg[val]["total_cost_micros"] += billed or 0
            agg[val]["total_provider_cost_micros"] += provider or 0
        return [
            {"tag_value": k, "event_count": v["event_count"],
             "total_cost_micros": v["total_cost_micros"],
             "total_provider_cost_micros": v["total_provider_cost_micros"]}
            for k, v in sorted(agg.items(), key=lambda kv: -kv[1]["total_cost_micros"])
        ]

    # ------------------------------------------------------------------
    # Output-contract freeze for get_dimensional_margin
    # ------------------------------------------------------------------

    def test_dimensional_margin_output_contract(self):
        """Hardcoded expected output — pins the new implementation's contract."""
        rows = queries.get_dimensional_margin(self.tenant.id, tag_key=self.TAG_KEY)
        self.assertEqual(len(rows), 3)
        # sort: -margin_micros => prod 3_500_000, staging 2_000_000, "" 600_000
        self.assertEqual(rows[0]["dimension"], "prod")
        self.assertEqual(rows[0]["provider_cost_micros"], 1_500_000)
        self.assertEqual(rows[0]["billed_cost_micros"], 5_000_000)
        self.assertEqual(rows[0]["margin_micros"], 3_500_000)
        self.assertEqual(rows[0]["event_count"], 2)

        self.assertEqual(rows[1]["dimension"], "staging")
        self.assertEqual(rows[1]["provider_cost_micros"], 2_000_000)
        self.assertEqual(rows[1]["billed_cost_micros"], 4_000_000)
        self.assertEqual(rows[1]["margin_micros"], 2_000_000)
        self.assertEqual(rows[1]["event_count"], 1)

        self.assertEqual(rows[2]["dimension"], "")
        self.assertEqual(rows[2]["provider_cost_micros"], 400_000)
        self.assertEqual(rows[2]["billed_cost_micros"], 1_000_000)
        self.assertEqual(rows[2]["margin_micros"], 600_000)
        self.assertEqual(rows[2]["event_count"], 1)

    # ------------------------------------------------------------------
    # Output-contract freeze for by_tag endpoint
    # ------------------------------------------------------------------

    def test_by_tag_output_contract(self):
        """Hardcoded expected output for the by_tag block via HTTP endpoint."""
        resp = Client().get(
            f"/api/v1/metering/analytics/usage?tag_key={self.TAG_KEY}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(resp.status_code, 200)
        by_tag = resp.json()["by_tag"]
        self.assertEqual(len(by_tag), 3)
        # sort: -total_cost_micros => prod 5_000_000, staging 4_000_000, "" 1_000_000
        self.assertEqual(by_tag[0]["tag_value"], "prod")
        self.assertEqual(by_tag[0]["total_cost_micros"], 5_000_000)
        self.assertEqual(by_tag[0]["total_provider_cost_micros"], 1_500_000)
        self.assertEqual(by_tag[0]["event_count"], 2)

        self.assertEqual(by_tag[1]["tag_value"], "staging")
        self.assertEqual(by_tag[1]["total_cost_micros"], 4_000_000)
        self.assertEqual(by_tag[1]["total_provider_cost_micros"], 2_000_000)
        self.assertEqual(by_tag[1]["event_count"], 1)

        self.assertEqual(by_tag[2]["tag_value"], "")
        self.assertEqual(by_tag[2]["total_cost_micros"], 1_000_000)
        self.assertEqual(by_tag[2]["total_provider_cost_micros"], 400_000)
        self.assertEqual(by_tag[2]["event_count"], 1)

    # ------------------------------------------------------------------
    # GROUP-BY trap regression: rows with same tag value but different
    # effective_at must collapse into a single output row.
    # ------------------------------------------------------------------

    def test_dimensional_margin_collapses_same_tag_different_timestamps(self):
        """Rows A and B both have env=prod but different effective_at.
        Without .order_by(), Meta.ordering adds effective_at to GROUP BY,
        shattering them into two rows.  Assert exactly one row for prod."""
        rows = queries.get_dimensional_margin(self.tenant.id, tag_key=self.TAG_KEY)
        prod_rows = [r for r in rows if r["dimension"] == "prod"]
        self.assertEqual(len(prod_rows), 1,
                         "GROUP-BY trap: prod split into multiple rows (missing .order_by())")
        self.assertEqual(prod_rows[0]["event_count"], 2)

    def test_by_tag_collapses_same_tag_different_timestamps(self):
        """Same GROUP-BY trap check for the endpoint by_tag block."""
        resp = Client().get(
            f"/api/v1/metering/analytics/usage?tag_key={self.TAG_KEY}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        by_tag = resp.json()["by_tag"]
        prod_rows = [r for r in by_tag if r["tag_value"] == "prod"]
        self.assertEqual(len(prod_rows), 1,
                         "GROUP-BY trap: prod split into multiple rows (missing .order_by())")
        self.assertEqual(prod_rows[0]["event_count"], 2)

    # ------------------------------------------------------------------
    # Query-count pins
    # ------------------------------------------------------------------

    def test_dimensional_margin_is_exactly_one_query(self):
        """get_dimensional_margin(tag_key=...) must issue exactly 1 SQL query."""
        with CaptureQueriesContext(connection) as ctx:
            queries.get_dimensional_margin(self.tenant.id, tag_key=self.TAG_KEY)
        self.assertEqual(len(ctx.captured_queries), 1,
                         f"Expected 1 query, got {len(ctx.captured_queries)}: "
                         f"{[q['sql'] for q in ctx.captured_queries]}")

    def test_by_tag_endpoint_query_count_does_not_grow_with_rows(self):
        """Endpoint query count must be the same for 50 rows as for 500 rows.

        Seeds an isolated tenant with 50 and 500 rows (different effective_at
        to exercise the GROUP-BY fix) and asserts the query count is identical.
        A Python-loop implementation would issue 1 query for 50 rows and still
        just 1 query for 500 rows (loop is Python, not SQL), BUT the important
        property here is that the SQL-pushdown implementation doesn't accidentally
        regress to N queries.  We also verify the counts are reasonable (<10).
        """
        def _count_queries_for_n_rows(n):
            t = Tenant.objects.create(
                name=f"F23 Scale {n}", products=["metering"])
            c = Customer.objects.create(tenant=t, external_id=f"c_f23_scale_{n}")
            _, key = TenantApiKey.create_key(t, label="f23s")
            evs = []
            for i in range(n):
                evs.append(UsageEvent(
                    tenant=t, customer=c,
                    request_id=f"req_f23s_{n}_{i}",
                    idempotency_key=f"idem_f23s_{n}_{i}",
                    billed_cost_micros=1_000,
                    provider_cost_micros=500,
                    tags={"env": "prod" if i % 2 == 0 else "staging"},
                ))
            UsageEvent.objects.bulk_create(evs, batch_size=200)
            client = Client()
            with CaptureQueriesContext(connection) as ctx:
                resp = client.get(
                    f"/api/v1/metering/analytics/usage?tag_key={self.TAG_KEY}",
                    HTTP_AUTHORIZATION=f"Bearer {key}")
            self.assertEqual(resp.status_code, 200)
            return len(ctx.captured_queries)

        q50 = _count_queries_for_n_rows(50)
        q500 = _count_queries_for_n_rows(500)
        self.assertEqual(q50, q500,
                         f"Query count changed with row count: {q50} vs {q500}")
        self.assertLess(q50, 10,
                        f"Unexpectedly many queries ({q50}) for tag analytics endpoint")

    # ------------------------------------------------------------------
    # BEFORE/AFTER equivalence — new SQL output == old Python-loop output
    # ------------------------------------------------------------------

    def test_dimensional_margin_equivalence_with_old_loop(self):
        """New SQL implementation must return the same result as the old loop."""
        new_result = queries.get_dimensional_margin(self.tenant.id, tag_key=self.TAG_KEY)
        old_result = self._old_get_dimensional_margin_tag(self.tenant.id, self.TAG_KEY)
        self.assertEqual(new_result, old_result,
                         "SQL pushdown result differs from old Python-loop reference")

    def test_by_tag_equivalence_with_old_loop(self):
        """New SQL implementation must match old Python-loop for by_tag."""
        resp = Client().get(
            f"/api/v1/metering/analytics/usage?tag_key={self.TAG_KEY}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        new_by_tag = resp.json()["by_tag"]
        old_by_tag = self._old_by_tag(self.tenant.id, self.TAG_KEY)
        # Normalise: old loop returns Python dicts; new returns dicts from JSON.
        self.assertEqual(new_by_tag, old_by_tag,
                         "SQL pushdown by_tag result differs from old Python-loop reference")
