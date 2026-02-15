from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.metering.queries import (
    get_period_totals, get_customer_usage_for_period,
    get_usage_event_cost, get_revenue_analytics,
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
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000,
        )
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r2", idempotency_key="i2",
            cost_micros=2_000_000,
        )
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 3_000_000)
        self.assertEqual(totals["event_count"], 2)

    def test_prefers_billed_cost_over_cost(self):
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000, billed_cost_micros=1_500_000,
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
        UsageEvent.objects.create(
            tenant=other_tenant, customer=other_customer,
            request_id="r1", idempotency_key="i1", cost_micros=5_000_000,
        )
        totals = get_period_totals(self.tenant.id, self.start, self.end)
        self.assertEqual(totals["total_cost_micros"], 0)
        self.assertEqual(totals["event_count"], 0)


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
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000, billed_cost_micros=1_200_000,
            provider_cost_micros=800_000,
        )
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0]["billed_cost_micros"], 1_200_000)
        self.assertEqual(events[0]["provider_cost_micros"], 800_000)
        self.assertEqual(events[0]["cost_micros"], 1_000_000)

    def test_returns_empty_for_no_events(self):
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(events, [])

    def test_filters_by_customer(self):
        other_customer = Customer.objects.create(tenant=self.tenant, external_id="c2")
        UsageEvent.objects.create(
            tenant=self.tenant, customer=other_customer,
            request_id="r1", idempotency_key="i1", cost_micros=5_000_000,
        )
        events = get_customer_usage_for_period(
            self.tenant.id, self.customer.id, self.start, self.end,
        )
        self.assertEqual(events, [])


class GetUsageEventCostTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_returns_cost_micros(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1", cost_micros=1_000_000,
        )
        self.assertEqual(get_usage_event_cost(event.id), 1_000_000)

    def test_prefers_billed_cost(self):
        event = UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000, billed_cost_micros=1_500_000,
        )
        self.assertEqual(get_usage_event_cost(event.id), 1_500_000)

    def test_returns_none_for_missing_event(self):
        import uuid
        self.assertIsNone(get_usage_event_cost(uuid.uuid4()))


class GetRevenueAnalyticsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def test_returns_totals_and_daily(self):
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000, billed_cost_micros=1_200_000,
            provider_cost_micros=800_000,
        )
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r2", idempotency_key="i2",
            cost_micros=2_000_000, billed_cost_micros=2_500_000,
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
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000, provider_cost_micros=500_000,
        )
        result = get_revenue_analytics(self.tenant.id, start_date=today, end_date=today)
        self.assertEqual(result["total_billed_cost_micros"], 1_000_000)
        # Exclude by filtering to yesterday only
        result = get_revenue_analytics(self.tenant.id, start_date=yesterday, end_date=yesterday)
        self.assertEqual(result["total_billed_cost_micros"], 0)

    def test_markup_zero_when_no_provider_cost(self):
        UsageEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            request_id="r1", idempotency_key="i1",
            cost_micros=1_000_000,
            provider_cost_micros=None,
        )
        result = get_revenue_analytics(self.tenant.id)
        self.assertEqual(result["total_billed_cost_micros"], 1_000_000)
        self.assertEqual(result["total_markup_micros"], 0)
