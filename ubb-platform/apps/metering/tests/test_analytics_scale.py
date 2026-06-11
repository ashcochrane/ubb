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

    def test_usage_timeseries_half_open(self):
        series = queries.get_usage_timeseries(
            self.tenant.id, start_date=date(2026, 6, 1), end_date=date(2026, 7, 1))
        self.assertEqual([s["bucket"] for s in series], ["2026-06-01", "2026-06-30"])
        self.assertTrue(all(s["event_count"] == 1 for s in series))

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
            cur.execute("ANALYZE ubb_usage_event")
            # LOCAL: scoped to the test transaction, reverted on rollback.
            # Bitmap scans are also disabled so the choice between the
            # composite btree and the single-column FK btree is decided by
            # which one can serve the predicate as an Index Cond — at this
            # tiny table scale bitmap-heap costs otherwise coin-flip them.
            cur.execute("SET LOCAL enable_seqscan = off")
            cur.execute("SET LOCAL enable_bitmapscan = off")

    def _assert_range_served_by(self, qs, index_name):
        # Production sites are aggregates (ordering cleared) — mirror that.
        plan = qs.order_by().explain()
        self.assertIn(index_name, plan)
        # The actual sargability property: the effective_at bounds must be an
        # Index Cond, not a post-scan Filter (a casted predicate could only
        # ever be a Filter, even with the index name in the plan).
        index_conds = [line for line in plan.splitlines() if "Index Cond:" in line]
        self.assertTrue(any("effective_at" in line for line in index_conds), plan)

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
