"""get_customer_usage_summary — the /me usage-summary read contract (F5.1)."""
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.metering.queries import get_customer_usage_summary


def _month_window():
    start = timezone.now().date().replace(day=1)
    end = timezone.now().date() + datetime.timedelta(days=1)
    return start, end


class GetCustomerUsageSummaryTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start, self.end = _month_window()

    def _event(self, customer, key, *, event_type="", units=None, billed=0):
        return UsageEvent.objects.create(
            tenant=self.tenant, customer=customer,
            request_id=f"r-{key}", idempotency_key=f"i-{key}",
            event_type=event_type, units=units, billed_cost_micros=billed,
        )

    def test_groups_by_event_type_and_totals_equal_sum_of_rows(self):
        self._event(self.customer, "1", event_type="tokens", units=100, billed=1_000_000)
        self._event(self.customer, "2", event_type="tokens", units=50, billed=500_000)
        self._event(self.customer, "3", event_type="images", units=2, billed=2_000_000)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["event_count"], 3)
        self.assertEqual(s["total_units"], 152)
        self.assertEqual(s["total_billed_micros"], 3_500_000)
        # Largest-billed first.
        self.assertEqual([m["event_type"] for m in s["metrics"]], ["images", "tokens"])
        self.assertEqual(s["total_units"], sum(m["units"] for m in s["metrics"]))
        self.assertEqual(s["total_billed_micros"],
                         sum(m["billed_cost_micros"] for m in s["metrics"]))
        self.assertEqual(s["event_count"], sum(m["event_count"] for m in s["metrics"]))

    def test_null_units_sum_as_zero(self):
        self._event(self.customer, "1", event_type="calls", units=None, billed=300_000)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["metrics"][0]["units"], 0)
        self.assertEqual(s["total_units"], 0)
        self.assertEqual(s["event_count"], 1)

    def test_excludes_events_outside_the_window(self):
        e = self._event(self.customer, "old", event_type="tokens", units=9, billed=900_000)
        UsageEvent.objects.filter(id=e.id).update(
            effective_at=timezone.now() - datetime.timedelta(days=70))
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["event_count"], 0)
        self.assertEqual(s["metrics"], [])

    def test_excludes_other_customers(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self._event(other, "x", event_type="tokens", units=7, billed=700_000)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["event_count"], 0)

    def test_business_aggregates_across_seats(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled")
        seat_a = Customer.objects.create(
            tenant=self.tenant, external_id="s-a", account_type="seat", parent=business)
        seat_b = Customer.objects.create(
            tenant=self.tenant, external_id="s-b", account_type="seat", parent=business)
        self._event(seat_a, "a1", event_type="tokens", units=10, billed=100_000)
        self._event(seat_b, "b1", event_type="tokens", units=20, billed=200_000)
        self._event(seat_b, "b2", event_type="images", units=1, billed=1_000_000)
        # An unrelated individual must never leak into the business rollup.
        self._event(self.customer, "z", event_type="tokens", units=99, billed=9_000_000)
        s = get_customer_usage_summary(self.tenant.id, business.id, self.start, self.end)
        self.assertEqual(s["event_count"], 3)
        self.assertEqual(s["total_units"], 31)
        self.assertEqual(s["total_billed_micros"], 1_300_000)
        rows = {m["event_type"]: m for m in s["metrics"]}
        self.assertEqual(rows["tokens"]["units"], 30)
        self.assertEqual(rows["tokens"]["billed_cost_micros"], 300_000)

    def test_business_with_no_seats_returns_zeros(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz0", account_type="business")
        s = get_customer_usage_summary(self.tenant.id, business.id, self.start, self.end)
        self.assertEqual(s, {"total_units": 0, "total_billed_micros": 0,
                             "event_count": 0, "metrics": []})

    def test_seat_sees_only_its_own_usage(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz2", account_type="business",
            billing_topology="pooled")
        seat_a = Customer.objects.create(
            tenant=self.tenant, external_id="s-a2", account_type="seat", parent=business)
        seat_b = Customer.objects.create(
            tenant=self.tenant, external_id="s-b2", account_type="seat", parent=business)
        self._event(seat_a, "a1", event_type="tokens", units=10, billed=100_000)
        self._event(seat_b, "b1", event_type="tokens", units=20, billed=200_000)
        s = get_customer_usage_summary(self.tenant.id, seat_a.id, self.start, self.end)
        self.assertEqual(s["event_count"], 1)
        self.assertEqual(s["total_billed_micros"], 100_000)
