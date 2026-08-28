"""get_customer_usage_summary — the /me usage-summary read contract (F5.1).

The rollup lost its quantity half in #272: the posting's inline unit total, the
`Sum` that aggregated it, the `or 0` that rendered a null of it as a zero, and
the grand total it fed are all gone. What is left is the money and the count,
per Event Type.

`test_a_row_carries_no_quantity_of_its_own` is the one assertion here that would
have been pointless before: it pins the shape of a row so that a later slice
re-introducing a quantity has to come past a test that says this was decided.
"""
import datetime

from django.test import TestCase
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import Posting
from apps.metering.queries import get_customer_usage_summary
from core.vocabulary import PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN


def _month_window():
    start = timezone.now().date().replace(day=1)
    end = timezone.now().date() + datetime.timedelta(days=1)
    return start, end


class GetCustomerUsageSummaryTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.start, self.end = _month_window()

    def _event(self, customer, key, *, event_type="", billed=0,
               pricing_status=PRICING_STATUS_KNOWN):
        return Posting.objects.create(
            tenant=self.tenant, customer=customer,
            idempotency_key=f"i-{key}",
            event_type=event_type, billed_cost_micros=billed,
            pricing_status=pricing_status,
        )

    def test_groups_by_event_type_and_totals_equal_sum_of_rows(self):
        self._event(self.customer, "1", event_type="tokens", billed=1_000_000)
        self._event(self.customer, "2", event_type="tokens", billed=500_000)
        self._event(self.customer, "3", event_type="images", billed=2_000_000)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["event_count"], 3)
        self.assertEqual(s["total_billed_micros"], 3_500_000)
        # Largest-billed first.
        self.assertEqual([m["event_type"] for m in s["metrics"]], ["images", "tokens"])
        self.assertEqual(s["total_billed_micros"],
                         sum(m["billed_cost_micros"] for m in s["metrics"]))
        self.assertEqual(s["event_count"], sum(m["event_count"] for m in s["metrics"]))

    def test_a_row_carries_no_quantity_of_its_own(self):
        """The retirement, stated where a reader of this module would look.

        A row is an Event Type, its money and how many postings made it. The
        nameless integer that used to ride beside them died with the column, and
        a summary field derived from nothing is exactly the shape that let a
        null read as a zero to an end customer.
        """
        self._event(self.customer, "1", event_type="calls", billed=300_000)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        # `unpriced_event_count` joins both shapes in #351 and is NOT the
        # quantity this test retired: it is a count of postings the money above
        # it could not include, not a magnitude summed across Event Types.
        self.assertEqual(set(s), {"total_billed_micros", "unpriced_event_count",
                                  "event_count", "metrics"})
        self.assertEqual(set(s["metrics"][0]),
                         {"event_type", "billed_cost_micros",
                          "unpriced_event_count", "event_count"})

    def test_a_zero_billed_row_still_counts_its_events(self):
        """The other half of what the coalescing used to hide.

        A row that cost nothing is still a row: the count is the surviving
        evidence that something happened, now that no quantity rides beside it.
        """
        self._event(self.customer, "1", event_type="calls", billed=0)
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["metrics"][0]["billed_cost_micros"], 0)
        self.assertEqual(s["metrics"][0]["event_count"], 1)
        self.assertEqual(s["event_count"], 1)

    def test_excludes_events_outside_the_window(self):
        e = self._event(self.customer, "old", event_type="tokens", billed=900_000)
        Posting.objects.filter(id=e.id).update(
            effective_at=timezone.now() - datetime.timedelta(days=70))
        s = get_customer_usage_summary(self.tenant.id, self.customer.id, self.start, self.end)
        self.assertEqual(s["event_count"], 0)
        self.assertEqual(s["metrics"], [])

    def test_excludes_other_customers(self):
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self._event(other, "x", event_type="tokens", billed=700_000)
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
        self._event(seat_a, "a1", event_type="tokens", billed=100_000)
        self._event(seat_b, "b1", event_type="tokens", billed=200_000)
        self._event(seat_b, "b2", event_type="images", billed=1_000_000)
        # An unrelated individual must never leak into the business rollup.
        self._event(self.customer, "z", event_type="tokens", billed=9_000_000)
        s = get_customer_usage_summary(self.tenant.id, business.id, self.start, self.end)
        self.assertEqual(s["event_count"], 3)
        self.assertEqual(s["total_billed_micros"], 1_300_000)
        rows = {m["event_type"]: m for m in s["metrics"]}
        self.assertEqual(rows["tokens"]["billed_cost_micros"], 300_000)
        self.assertEqual(rows["tokens"]["event_count"], 2)

    def test_business_with_no_seats_returns_zeros(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz0", account_type="business")
        s = get_customer_usage_summary(self.tenant.id, business.id, self.start, self.end)
        self.assertEqual(s, {"total_billed_micros": 0,
                             "unpriced_event_count": 0,
                             "event_count": 0, "metrics": []})

    def test_the_grand_count_is_the_sum_of_the_rows_counts(self):
        """The same "by construction" relation the totals have (#351).

        A caveat that did not add up the way the money does would let a reader
        reconcile the rows against the total and conclude the total was whole.
        """
        self._event(self.customer, "1", event_type="calls", billed=300_000)
        self._event(self.customer, "2", event_type="calls", billed=None,
                    pricing_status=PRICING_STATUS_UNKNOWN)
        self._event(self.customer, "3", event_type="tokens", billed=None,
                    pricing_status=PRICING_STATUS_UNKNOWN)
        s = get_customer_usage_summary(
            self.tenant.id, self.customer.id, self.start, self.end)
        rows = {m["event_type"]: m for m in s["metrics"]}
        self.assertEqual(rows["calls"]["unpriced_event_count"], 1)
        self.assertEqual(rows["tokens"]["unpriced_event_count"], 1)
        self.assertEqual(s["unpriced_event_count"], 2)
        # And the money still only counts what UBB resolved.
        self.assertEqual(s["total_billed_micros"], 300_000)

    def test_seat_sees_only_its_own_usage(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz2", account_type="business",
            billing_topology="pooled")
        seat_a = Customer.objects.create(
            tenant=self.tenant, external_id="s-a2", account_type="seat", parent=business)
        seat_b = Customer.objects.create(
            tenant=self.tenant, external_id="s-b2", account_type="seat", parent=business)
        self._event(seat_a, "a1", event_type="tokens", billed=100_000)
        self._event(seat_b, "b1", event_type="tokens", billed=200_000)
        s = get_customer_usage_summary(self.tenant.id, seat_a.id, self.start, self.end)
        self.assertEqual(s["event_count"], 1)
        self.assertEqual(s["total_billed_micros"], 100_000)
