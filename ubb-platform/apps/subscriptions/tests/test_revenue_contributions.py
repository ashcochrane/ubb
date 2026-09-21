"""The revenue half of the one economic query, at its read contract (#499).

**Asserted here rather than through the route** for the one reason the seam rule
allows: these are claims about what this product HANDS OVER, and the route's
answer folds them into a total where a wrong window and a wrong basis are no
longer distinguishable. The composed answer is tested through the route, in
`api/v1/tests/test_the_one_economic_query.py`.
"""
from datetime import date

from django.test import TestCase
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.economics.revenue import RevenueService
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.queries import (
    REVENUE_ATTRIBUTABLE_AXES, REVENUE_FINEST_BUCKET, REVENUE_SOURCES,
    REVENUE_SOURCE_SUBSCRIPTION, REVENUE_SOURCE_TENANT_SUPPLIED,
    revenue_contributions, supplied_revenue_covered_periods,
)
from core.vocabulary import (
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE,
    REVENUE_BASIS_RECOGNISED, REVENUE_BASIS_RECORDED,
)

OPENS, NEXT = date(2026, 3, 1), date(2026, 4, 1)
MONTH = [(OPENS, NEXT)]
#: March has 31 days, so a figure that divides by day is exact at 3,100,000 and
#: a window of ten days takes exactly 1,000,000 of it. A round span is what lets
#: an off-by-one in the window show up as a wrong number rather than as
#: rounding.
SUPPLIED = 3_100_000


class _ATenantWithTwoCustomers(TestCase):
    """The tenant both read contracts below are asked about, and the one way a
    case here supplies a figure for it."""

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        cls.other = Customer.objects.create(tenant=cls.tenant,
                                            external_id="c2")

    def a_supplied_figure(self, customer=None, *, method, amount=SUPPLIED,
                          reference="inv-1", period_start=OPENS,
                          period_end=NEXT):
        return TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=customer or self.customer,
            amount_micros=amount, currency="usd", period_start=period_start,
            period_end=period_end, recognition_method=method,
            source_reference=reference)


class RevenueContributionsTest(_ATenantWithTwoCustomers):

    def a_subscription(self, customer=None, *, amount=31_000_000,
                       status="active", interval="month"):
        now = timezone.now()
        return StripeSubscription.objects.create(
            tenant=self.tenant, customer=customer or self.customer,
            stripe_subscription_id=f"sub_{status}_{amount}",
            stripe_product_name="Pro", status=status, amount_micros=amount,
            quantity=1, currency="usd", interval=interval,
            current_period_start=now, current_period_end=now,
            last_synced_at=now)

    def test_each_row_says_where_it_came_from(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        self.a_subscription()
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED)
        assert {row["source"] for row in rows} == set(REVENUE_SOURCES)

    def test_the_two_sources_are_never_summed_into_one_row(self):
        """#496's subject, one layer out: summing them here would destroy the
        provenance the record exists to carry, before the query ever saw it."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        self.a_subscription()
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED)
        assert len(rows) == 2
        assert {row["amount_micros"] for row in rows} == {SUPPLIED, 31_000_000}

    def test_every_row_declares_what_it_can_be_attributed_at(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        self.a_subscription()
        for row in revenue_contributions(self.tenant.id, windows=MONTH,
                                         basis=REVENUE_BASIS_RECORDED):
            assert row["attributable_axes"] == REVENUE_ATTRIBUTABLE_AXES
            assert row["finest_bucket"] == REVENUE_FINEST_BUCKET

    def test_a_stated_zero_is_a_row_and_not_a_silence(self):
        """A tenant recording a free month is stating that revenue was nothing,
        which is a different fact from having supplied nothing at all."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT, amount=0)
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED)
        assert [row["amount_micros"] for row in rows] == [0]

    def test_a_subscription_that_accrues_nothing_is_a_silence(self):
        """The other direction, and it is deliberately the OPPOSITE rule:
        nobody wrote a zero down, so emitting one would put a row against every
        customer in every bucket of every query."""
        self.a_subscription()
        rows = revenue_contributions(
            self.tenant.id, windows=[(date(2027, 1, 1), date(2027, 1, 1))],
            basis=REVENUE_BASIS_RECORDED)
        assert rows == []

    def test_the_basis_changes_the_supplied_view_and_not_the_stripe_one(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        self.a_subscription()
        half = [(OPENS, date(2026, 3, 11))]
        recorded = revenue_contributions(self.tenant.id, windows=half,
                                         basis=REVENUE_BASIS_RECORDED)
        recognised = revenue_contributions(self.tenant.id, windows=half,
                                           basis=REVENUE_BASIS_RECOGNISED)
        supplied = {basis: next(row["amount_micros"] for row in rows
                                if row["source"] == REVENUE_SOURCE_TENANT_SUPPLIED)
                    for basis, rows in (("recorded", recorded),
                                        ("recognised", recognised))}
        stripe = {basis: next(row["amount_micros"] for row in rows
                              if row["source"] == REVENUE_SOURCE_SUBSCRIPTION)
                  for basis, rows in (("recorded", recorded),
                                      ("recognised", recognised))}
        # Ten of thirty-one days under the spreading method; the whole amount on
        # the day the record opens under the other.
        assert supplied["recorded"] == SUPPLIED
        assert supplied["recognised"] == SUPPLIED * 10 // 31
        # ⚠ Stripe states an amount per interval and nothing else, so there is
        # no second reading of it to offer and a basis that moved it would be
        # publishing one that means nothing on half the rows.
        assert stripe["recorded"] == stripe["recognised"]

    def test_one_window_per_bucket_and_the_database_read_once(self):
        """The shape the query needs: a year bucketed by day must not be a year
        of queries."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        self.a_subscription()
        days = [(date(2026, 3, day), date(2026, 3, day + 1))
                for day in range(1, 11)]
        with self.assertNumQueries(2):
            rows = revenue_contributions(self.tenant.id, windows=days,
                                         basis=REVENUE_BASIS_RECOGNISED)
        assert len({row["window_start"] for row in rows}) == 10

    def test_a_window_gets_only_its_own_share(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        rows = revenue_contributions(
            self.tenant.id, basis=REVENUE_BASIS_RECOGNISED,
            windows=[(date(2026, 3, 1), date(2026, 3, 11)),
                     (date(2026, 3, 11), date(2026, 3, 21))])
        assert [row["amount_micros"] for row in rows] == [
            SUPPLIED * 10 // 31, SUPPLIED * 10 // 31]

    def test_one_customers_revenue_is_not_anothers(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        self.a_supplied_figure(self.other, method=RECOGNITION_METHOD_ON_RECEIPT,
                               amount=500_000, reference="inv-2")
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED)
        assert {row["customer_id"]: row["amount_micros"] for row in rows} == {
            str(self.customer.id): SUPPLIED, str(self.other.id): 500_000}

    def test_narrowing_to_one_customer_leaves_the_others_out(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        self.a_supplied_figure(self.other, method=RECOGNITION_METHOD_ON_RECEIPT,
                               amount=500_000, reference="inv-2")
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED,
                                     customer_ids=[self.customer.id])
        assert [row["customer_id"] for row in rows] == [str(self.customer.id)]

    def test_another_tenants_revenue_is_never_anybodys(self):
        theirs = Tenant.objects.create(name="Other", products=["metering"])
        TenantSuppliedRevenue.objects.create(
            tenant=theirs,
            customer=Customer.objects.create(tenant=theirs, external_id="x"),
            amount_micros=9_000_000, currency="usd", period_start=OPENS,
            period_end=NEXT, recognition_method=RECOGNITION_METHOD_ON_RECEIPT,
            source_reference="inv-x")
        assert revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED) == []

    def test_a_basis_the_registry_does_not_declare_is_refused(self):
        with self.assertRaisesRegex(ValueError, "declared revenue basis"):
            revenue_contributions(self.tenant.id, windows=MONTH,
                                  basis="whatever")

    def test_no_windows_is_no_answer_rather_than_the_whole_history(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        assert revenue_contributions(self.tenant.id, windows=[],
                                     basis=REVENUE_BASIS_RECORDED) == []

    def test_only_the_accruing_statuses_contribute(self):
        self.a_subscription(status="canceled")
        assert revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED) == []
        self.a_subscription(status="past_due")
        rows = revenue_contributions(self.tenant.id, windows=MONTH,
                                     basis=REVENUE_BASIS_RECORDED)
        assert [row["source"] for row in rows] == [REVENUE_SOURCE_SUBSCRIPTION]

    def test_the_status_list_is_the_one_the_per_customer_accrual_uses(self):
        """One list, because two would be two answers to *which subscriptions
        count* — and the per-customer figure is what the margin surfaces this
        query replaces were built on."""
        self.a_subscription()
        whole = sum(row["amount_micros"] for row in revenue_contributions(
            self.tenant.id, windows=MONTH, basis=REVENUE_BASIS_RECORDED))
        per_customer = RevenueService.accrued_subscription_revenue(
            self.tenant.id, self.customer.id, OPENS, NEXT)
        # Non-degenerate: two ways of reaching a figure agree for free when the
        # figure is zero, so the case would pass over a status list that
        # admitted nothing at all.
        assert per_customer > 0
        assert whole == per_customer


class SuppliedRevenueCoveredPeriodsTest(_ATenantWithTwoCustomers):
    """The spans a tenant-supplied figure is the WHOLE revenue for (#537).

    The one economic query supersedes the revenue it derived from priced usage
    inside these spans, for these customers, and excuses the usage nobody
    priced there. **What it is handed is the record's own span and nothing the
    basis decides**: `revenue_contributions` above says where an AMOUNT lands,
    which under `recorded` is the day a period opens, and a window starting
    after that day gets none of it — while the usage inside that window is
    still inside a month the tenant has stated the whole revenue of.
    """

    def covered(self, opens=OPENS, closes=NEXT, **kwargs):
        return supplied_revenue_covered_periods(
            self.tenant.id, opens=opens, closes=closes, **kwargs)

    def test_a_figure_covers_the_span_it_declares_for_its_customer(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        assert self.covered() == [{"customer_id": str(self.customer.id),
                                   "period_start": OPENS, "period_end": NEXT}]

    def test_a_figure_opening_before_the_window_still_covers_it(self):
        """The case the basis would have lost: under `recorded` this record
        contributes nothing to a window opening on the tenth."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT)
        tenth = date(2026, 3, 10)
        assert revenue_contributions(self.tenant.id, windows=[(tenth, NEXT)],
                                     basis=REVENUE_BASIS_RECORDED) == []
        assert [(row["period_start"], row["period_end"])
                for row in self.covered(opens=tenth)] == [(OPENS, NEXT)]

    def test_a_stated_zero_covers_its_span_like_any_other_figure(self):
        """A free month is the whole revenue of that month, and it is nothing
        (#153 §3.4) — which is a statement about the usage in it too."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE,
                               amount=0)
        assert len(self.covered()) == 1

    def test_a_figure_for_an_instant_covers_no_span(self):
        """A null period end is the record saying it is a point in time and
        not a span, and the model refuses to read it as a day — so there is
        no period for it to be the whole revenue of."""
        self.a_supplied_figure(method=RECOGNITION_METHOD_ON_RECEIPT,
                               period_end=None)
        assert self.covered() == []

    def test_a_figure_outside_the_window_covers_nothing_in_it(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        assert self.covered(opens=NEXT, closes=date(2026, 5, 1)) == []
        assert self.covered(opens=date(2026, 2, 1), closes=OPENS) == []

    def test_a_subscription_covers_nothing(self):
        """Stripe subscription revenue is outside #537's ruling: it is added
        to what UBB priced, as it always was, and supersedes none of it."""
        now = timezone.now()
        StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.customer,
            stripe_subscription_id="sub_1", stripe_product_name="Pro",
            status="active", amount_micros=31_000_000, quantity=1,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now)
        assert self.covered() == []

    def test_narrowing_to_one_customer_leaves_the_others_out(self):
        self.a_supplied_figure(method=RECOGNITION_METHOD_STRAIGHT_LINE)
        self.a_supplied_figure(self.other,
                               method=RECOGNITION_METHOD_STRAIGHT_LINE)
        assert [row["customer_id"] for row in self.covered(
            customer_ids=[self.other.id])] == [str(self.other.id)]

    def test_another_tenants_figure_covers_nothing_here(self):
        stranger = Tenant.objects.create(name="U", products=["metering"])
        TenantSuppliedRevenue.objects.create(
            tenant=stranger,
            customer=Customer.objects.create(tenant=stranger,
                                             external_id="c1"),
            amount_micros=SUPPLIED, currency="usd", period_start=OPENS,
            period_end=NEXT,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference="inv-x")
        assert self.covered() == []
