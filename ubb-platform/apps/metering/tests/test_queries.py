from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.metering.queries import (
    get_period_totals, get_customer_usage_for_period,
    get_usage_event_cost, get_revenue_analytics,
)
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY)
from core.vocabulary import (
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)


class GetPeriodTotalsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start = timezone.now().date().replace(day=1)
        if self.start.month == 12:
            self.end = self.start.replace(year=self.start.year + 1, month=1, day=1)
        else:
            self.end = self.start.replace(month=self.start.month + 1, day=1)

    def test_returns_totals_for_period(self):
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_000_000,
        )
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i2",
            billed_cost_micros=2_000_000,
        )
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 3_000_000)
        self.assertEqual(totals["event_count"], 2)

    def test_sums_billed_cost(self):
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_500_000,
        )
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 1_500_000)

    def test_returns_zeros_for_empty_period(self):
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 0)
        self.assertEqual(totals["event_count"], 0)

    def test_filters_by_tenant(self):
        other_tenant = Tenant.objects.create(name="Other")
        other_customer = Customer.objects.create(tenant=other_tenant, external_id="c2")
        Posting.objects.create(
            tenant=other_tenant, customer=other_customer,
            idempotency_key="i1", billed_cost_micros=5_000_000,
        )
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 0)
        self.assertEqual(totals["event_count"], 0)

    def test_arrival_basis_windows_on_created_at(self):
        """basis="arrival" counts a backdated event by WHEN IT ARRIVED;
        basis="effective" (default) excludes it from the current period."""
        import datetime
        e = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1", billed_cost_micros=1_000_000,
        )
        # Backdate the effective time out of the window; created_at stays now.
        Posting.objects.filter(id=e.id).update(
            effective_at=timezone.now() - datetime.timedelta(days=90))
        effective = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(effective["event_count"], 0)
        arrival = get_period_totals(self.tenant.id, self.start, self.end, basis="arrival")
        self.assertEqual(arrival["event_count"], 1)
        self.assertEqual(arrival["total_cost_micros"], 1_000_000)

    def test_invalid_basis_raises(self):
        with self.assertRaises(ValueError):
            get_period_totals(self.tenant.id, self.start, self.end, basis="bogus")

    def test_the_supplier_total_says_how_many_costs_it_excluded(self):
        """The pair, on the read contract itself (#329).

        Asserted here rather than only through billing's close, because this is
        the surface another product reads: a key that reaches the close by
        accident and falls off the contract is exactly the failure #327 found
        one layer over, where the one declared row silently dropped what two
        undeclared ones carried.
        """
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_000_000, provider_cost_micros=400_000,
        )
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i2",
            billed_cost_micros=2_000_000, provider_cost_micros=None,
            costing_status=COSTING_STATUS_UNRESOLVED,
            unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
        )

        totals = get_period_totals(self.tenant.id, self.start, self.end)

        assert totals["total_provider_cost_micros"] == 400_000
        assert totals[UNRESOLVED_EVENT_COUNT_KEY] == 1
        # THE BILLED TOTAL IS NOT WHAT THE COUNT IS ABOUT. Its column is NOT
        # NULL, so it passed over nothing and includes the very posting the
        # count excludes — a reader taking the count as a caveat on this figure
        # would report a period partial in the one number that never is.
        assert totals["total_cost_micros"] == 3_000_000
        assert totals["event_count"] == 2

    def test_a_cost_that_does_not_exist_is_not_a_cost_that_is_missing(self):
        """`not_applicable` carries a NULL amount and SQL skips it identically,
        and it must still not be counted (#327): the Event Type declares no
        supplier cost, so the total is complete. Counting it would mark every
        metering-only tenant's every period partial forever."""
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_000_000, provider_cost_micros=None,
            costing_status=COSTING_STATUS_NOT_APPLICABLE,
        )

        totals = get_period_totals(self.tenant.id, self.start, self.end)

        assert totals[UNRESOLVED_EVENT_COUNT_KEY] == 0
        assert totals["total_provider_cost_micros"] == 0


class GetCustomerUsageForPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.now = timezone.now()
        self.start = self.now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if self.start.month == 12:
            self.end = self.start.replace(year=self.start.year + 1, month=1, day=1)
        else:
            self.end = self.start.replace(month=self.start.month + 1, day=1)

    def test_returns_per_event_data(self):
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_200_000,
            provider_cost_micros=800_000,
        )
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["billed_cost_micros"], 1_200_000)
        self.assertEqual(events[0]["provider_cost_micros"], 800_000)

    def test_returns_empty_for_no_events(self):
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(events, [])

    def test_filters_by_customer(self):
        other_customer = Customer.objects.create(tenant=self.tenant, external_id="c2")
        Posting.objects.create(
            tenant=self.tenant, customer=other_customer,
            idempotency_key="i1", billed_cost_micros=5_000_000,
        )
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(events, [])


class GetUsageEventCostTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_returns_billed_cost(self):
        event = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1", billed_cost_micros=1_000_000,
        )
        self.assertEqual(get_usage_event_cost(event.id),
                         {"billed_cost_micros": 1_000_000,
                          "pricing_status": PRICING_STATUS_KNOWN})

    def test_prefers_billed_cost(self):
        event = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_500_000,
        )
        self.assertEqual(get_usage_event_cost(event.id),
                         {"billed_cost_micros": 1_500_000,
                          "pricing_status": PRICING_STATUS_KNOWN})

    def test_returns_none_for_missing_event(self):
        import uuid
        self.assertIsNone(get_usage_event_cost(uuid.uuid4()))

    def test_an_unresolved_price_is_a_row_and_not_a_missing_event(self):
        """The distinction the row shape exists for (#351).

        Both answers were `None` while this returned a bare amount, and the one
        caller — the wallet's refund path — reported the second as
        `usage_event_not_found`. A posting that exists is never `None` here,
        whatever its price.
        """
        event = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i2",
            billed_cost_micros=None, pricing_status=PRICING_STATUS_UNKNOWN)
        self.assertEqual(get_usage_event_cost(event.id),
                         {"billed_cost_micros": None,
                          "pricing_status": PRICING_STATUS_UNKNOWN})


class GetRevenueAnalyticsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_returns_totals_and_daily(self):
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_200_000,
            provider_cost_micros=800_000,
        )
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i2",
            billed_cost_micros=2_500_000,
            provider_cost_micros=1_500_000,
        )
        result = get_revenue_analytics(self.tenant.id)
        self.assertEqual(result["total_provider_cost_micros"], 2_300_000)
        self.assertEqual(result["total_billed_cost_micros"], 3_700_000)
        self.assertEqual(result["total_markup_micros"], 1_400_000)
        self.assertEqual(len(result["daily"]), 1)
        self.assertEqual(result["daily"][0]["event_count"], 2)

    def test_returns_zeros_for_no_events(self):
        result = get_revenue_analytics(self.tenant.id)
        self.assertEqual(result["total_provider_cost_micros"], 0)
        self.assertEqual(result["total_billed_cost_micros"], 0)
        self.assertEqual(result["total_markup_micros"], 0)
        self.assertEqual(result["daily"], [])

    def test_filters_by_date_range(self):
        from datetime import timedelta
        today = timezone.now().date()
        yesterday = today - timedelta(days=1)
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_000_000, provider_cost_micros=500_000,
        )
        result = get_revenue_analytics(self.tenant.id, start_date=today, end_date=today)
        self.assertEqual(result["total_billed_cost_micros"], 1_000_000)
        # Exclude by filtering to yesterday only
        result = get_revenue_analytics(self.tenant.id, start_date=yesterday, end_date=yesterday)
        self.assertEqual(result["total_billed_cost_micros"], 0)

    def test_markup_equals_billed_when_provider_cost_zero(self):
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1",
            billed_cost_micros=1_000_000,
            provider_cost_micros=0,
        )
        result = get_revenue_analytics(self.tenant.id)
        self.assertEqual(result["total_billed_cost_micros"], 1_000_000)
        self.assertEqual(result["total_markup_micros"], 1_000_000)


class GetCostTotalsTest(TestCase):
    def setUp(self):
        from django.utils import timezone
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start = timezone.now().date().replace(day=1)
        self.end = (self.start.replace(month=self.start.month % 12 + 1, day=1)
                    if self.start.month < 12 else self.start.replace(year=self.start.year + 1, month=1, day=1))
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="i1",
            provider_cost_micros=800_000, billed_cost_micros=1_000_000, provider="openai",
            grouping_field_1="chat", metadata={"model": "gpt-4"})
        Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="i2",
            provider_cost_micros=200_000, billed_cost_micros=300_000, provider="openai",
            grouping_field_1="chat", metadata={"model": "gpt-4"})

    def test_customer_cost_totals(self):
        from apps.metering.queries import get_customer_cost_totals
        t = get_customer_cost_totals(self.tenant.id, self.customer.id, self.start, self.end)
        assert t["provider_cost_micros"] == 1_000_000
        assert t["billed_cost_micros"] == 1_300_000
        assert t["event_count"] == 2

    def test_per_customer_cost_totals(self):
        from apps.metering.queries import get_per_customer_cost_totals
        rows = get_per_customer_cost_totals(self.tenant.id, self.start, self.end)
        assert len(rows) == 1
        assert rows[0]["billed_cost_micros"] == 1_300_000

    def test_dimensional_margin_by_provider(self):
        from apps.metering.queries import get_dimensional_margin
        rows = get_dimensional_margin(self.tenant.id, group_by="provider",
                                      start_date=self.start, end_date=self.end)
        assert rows[0]["grouping_field_value"] == "openai"
        assert rows[0]["margin_micros"] == 300_000

    def test_dimensional_margin_by_tag(self):
        from apps.metering.queries import get_dimensional_margin
        rows = get_dimensional_margin(self.tenant.id, tag_key="model",
                                      start_date=self.start, end_date=self.end)
        assert rows[0]["grouping_field_value"] == "gpt-4"
        assert rows[0]["margin_micros"] == 300_000


class CrossProductReadContractTest(TestCase):
    """F3.2 contract functions: the only approved cross-product Posting reads."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start = timezone.now().date().replace(day=1)
        self.end = (self.start.replace(month=self.start.month + 1, day=1)
                    if self.start.month < 12
                    else self.start.replace(year=self.start.year + 1, month=1, day=1))

    def test_effective_at_returned(self):
        from apps.metering.queries import get_usage_event_effective_at
        ev = Posting.objects.create(
            tenant=self.tenant, customer=self.customer,
            idempotency_key="i1", billed_cost_micros=1)
        self.assertEqual(get_usage_event_effective_at(ev.id), ev.effective_at)

    def test_effective_at_none_for_malformed_and_missing_ids(self):
        import uuid
        from apps.metering.queries import get_usage_event_effective_at
        self.assertIsNone(get_usage_event_effective_at("evt-1"))   # legacy non-UUID id
        self.assertIsNone(get_usage_event_effective_at(uuid.uuid4()))

    def test_customer_ids_with_usage_single_and_list_tenant(self):
        from apps.metering.queries import get_customer_ids_with_usage
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        # zero-billed usage still counts (existence-based, no billed filter)
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i1", billed_cost_micros=0)
        Posting.objects.create(tenant=self.tenant, customer=other,
                                  idempotency_key="i2", billed_cost_micros=5)
        Posting.objects.create(tenant=self.tenant, customer=other,
                                  idempotency_key="i3", billed_cost_micros=5)
        single = get_customer_ids_with_usage(self.tenant.id, self.start, self.end)
        listed = get_customer_ids_with_usage([self.tenant.id], self.start, self.end)
        self.assertEqual(sorted(map(str, single)), sorted(map(str, listed)))
        self.assertEqual(set(single), {self.customer.id, other.id})  # distinct

    def test_billed_totals_by_customer_groups_in_sql(self):
        from apps.metering.queries import get_billed_totals_by_customer
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        excluded = Customer.objects.create(tenant=self.tenant, external_id="c3")
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i1", billed_cost_micros=100)
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i2", billed_cost_micros=200)
        Posting.objects.create(tenant=self.tenant, customer=other,
                                  idempotency_key="i3", billed_cost_micros=0)
        Posting.objects.create(tenant=self.tenant, customer=excluded,
                                  idempotency_key="i4", billed_cost_micros=7)
        totals = get_billed_totals_by_customer(
            self.tenant.id, [self.customer.id, other.id], self.start, self.end)
        self.assertEqual(totals, {
            self.customer.id: {"billed_cost_micros": 300,
                               UNPRICED_EVENT_COUNT_KEY: 0},
            other.id: {"billed_cost_micros": 0, UNPRICED_EVENT_COUNT_KEY: 0}})

    def test_billed_totals_by_customer_counts_what_it_could_not_price(self):
        """The pair, over the surface that builds postpaid invoice LINES (#351).

        A seat whose every posting is unpriced billed exactly like a seat that
        emitted nothing, and this is the number that tells them apart.
        """
        from apps.metering.queries import get_billed_totals_by_customer
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="i1",
                               billed_cost_micros=100)
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="i2",
                               billed_cost_micros=None,
                               pricing_status=PRICING_STATUS_UNKNOWN)
        totals = get_billed_totals_by_customer(
            self.tenant.id, [self.customer.id], self.start, self.end)
        self.assertEqual(totals[self.customer.id],
                         {"billed_cost_micros": 100,
                          UNPRICED_EVENT_COUNT_KEY: 1})

    def test_billed_breakdown_tag_empty_string_and_missing_merge_to_other(self):
        from apps.metering.queries import get_customer_billed_breakdown
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i1",
                                  billed_cost_micros=100, metadata={"seat": "alice"})
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i2",
                                  billed_cost_micros=20, metadata={"seat": ""})
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i3",
                                  billed_cost_micros=3, metadata={})
        pairs = get_customer_billed_breakdown(
            self.tenant.id, self.customer.id, self.start, self.end, "tag:seat")
        self.assertEqual({label: billed for label, billed, _ in pairs},
                         {"alice": 100, "(other)": 23})

    def test_billed_breakdown_dim1_empty_to_other(self):
        from apps.metering.queries import get_customer_billed_breakdown
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i1",
                                  billed_cost_micros=100, grouping_field_1="chat")
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i2",
                                  billed_cost_micros=20, grouping_field_1="")
        pairs = get_customer_billed_breakdown(
            self.tenant.id, self.customer.id, self.start, self.end, "dim1")
        self.assertEqual({label: billed for label, billed, _ in pairs},
                         {"chat": 100, "(other)": 20})

    def test_a_breakdown_line_carries_what_its_own_label_could_not_price(self):
        """Per LINE (#351), because an invoice line is what a customer disputes.

        One label complete and another a floor is the ordinary case, and a count
        reported once for the whole breakdown would attach the caveat to the
        wrong line as often as the right one.
        """
        from apps.metering.queries import get_customer_billed_breakdown
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="i1",
                               billed_cost_micros=100, grouping_field_1="chat")
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="i2",
                               billed_cost_micros=None, grouping_field_1="chat",
                               pricing_status=PRICING_STATUS_UNKNOWN)
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                               idempotency_key="i3",
                               billed_cost_micros=50, grouping_field_1="batch")
        rows = get_customer_billed_breakdown(
            self.tenant.id, self.customer.id, self.start, self.end, "dim1")
        self.assertEqual({label: (billed, unpriced)
                          for label, billed, unpriced in rows},
                         {"chat": (100, 1), "batch": (50, 0)})

    def test_iter_billable_usage_events_shape_and_basis(self):
        from datetime import timedelta
        from apps.metering.queries import iter_billable_usage_events
        now = timezone.now()
        ev = Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                       idempotency_key="i1",
                                       billed_cost_micros=500)
        Posting.objects.create(tenant=self.tenant, customer=self.customer,
                                  idempotency_key="i2",
                                  billed_cost_micros=0)  # not billable -> excluded
        rows = list(iter_billable_usage_events(
            self.tenant.id, now - timedelta(hours=1), now + timedelta(hours=1)))
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0], {"id": ev.id, "billed_cost_micros": 500,
                                   "customer_id": self.customer.id,
                                   "billing_owner_id": ev.billing_owner_id})
        # basis="created": move effective_at out of the window; created_at still matches.
        Posting.objects.filter(id=ev.id).update(effective_at=now - timedelta(days=30))
        window = (now - timedelta(hours=1), now + timedelta(hours=1))
        self.assertEqual(list(iter_billable_usage_events(
            self.tenant.id, *window, basis="effective")), [])
        created_rows = list(iter_billable_usage_events(
            self.tenant.id, *window, basis="created"))
        self.assertEqual([r["id"] for r in created_rows], [ev.id])
        with self.assertRaises(ValueError):
            list(iter_billable_usage_events(self.tenant.id, *window, basis="bogus"))
