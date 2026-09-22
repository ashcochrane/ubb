"""A cost total travels with the count of what it left out (#327).

`Posting.provider_cost_micros` became nullable in #317, `NULL` meaning *UBB has
not resolved this cost*. SQL's aggregates skip `NULL`, so from that commit every
`Sum` over the column answered **a number that looks complete and is not** — the
same defect the column had just stopped having, moved one step downstream into
every total built on it. `or 0` is not the fix: it produces a figure
indistinguishable from a whole one, which is precisely what a tenant must never
be handed.

So every supplier-cost total is now a **pair** — the resolved sum, and the count
of postings excluded from it — and the two are built together by
``core.cost_totals`` so that no reader can take one without the other.

**ONE FIXTURE, MANY ASSERTIONS.** Four postings, in two groups of two, are
enough to hold every claim in this module:

* customer ``c1``, provider ``openai`` — one **known** cost of 1.00 and one
  **unresolved** one. Every rollup that reaches this group is *partial*.
* customer ``c2``, provider ``anthropic`` — one **known** cost of 0.50 and one
  **not applicable**. Every rollup that reaches this group is *complete*.

The second group is what makes the first mean anything. `not_applicable` also
carries a `NULL` amount and is also skipped by SQL, and a naive reading of
"count the rows the sum left out" would report it as missing information — which
would mark **every metering-only tenant's every total** partial forever, and a
caveat that is always on is a caveat nobody reads. What the pair counts is the
cost UBB has **not learned yet**, never the cost that does not exist.

⚠ **THE SWEEP DECIDES HOW THIS MODULE REACHES A SURFACE.** Every retired word it
might have spelled is one a new file cannot afford — the ceiling on each is a
ceiling on SPREAD as well as a floor — so the postings below are written through
the ORM rather than through the recording route, and the grouped assertions go
through the one economic query, whose request vocabulary is the declared one.

⚠ **AND FOUR OF ITS SUBJECTS MOVED IN #501.** The tenant-wide daily revenue
rollup, the day-or-hour series, the grouped usage-only margin and the usage
report's own breakdown blocks are gone; the one economic query answers all four,
and every claim they carried is asserted against it below. The claims did not
change — a total says what it left out, per group and per bucket — but the
answer now says it as a measure's own STATE beside the count, which is stronger
than a count a reader had to know to look for.
"""
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.queries import (
    get_customer_cost_totals,
    get_per_customer_cost_totals,
)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY)
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

KNOWN_COST_MICROS = 1_000_000
OTHER_KNOWN_COST_MICROS = 500_000
ECONOMICS = "/api/v1/metering/analytics/economics"
MONEY = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
         ANALYTICS_MEASURE_GROSS_MARGIN]


@pytest.mark.django_db
class TestACostTotalSaysWhatItExcluded:
    def setup_method(self):
        # products=[...] is REQUIRED — the analytics routes are gated by
        # _product_check.
        self.tenant = Tenant.objects.create(name="T", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.c1 = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.c2 = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self.client = Client()
        self.today = timezone.now().date()
        self._seed()

    def _get(self, path):
        return self.client.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _ask(self, **params):
        """One economic question, with repeated parameters spelled properly."""
        query = []
        for name, value in params.items():
            if isinstance(value, (list, tuple)):
                query += [(name, entry) for entry in value]
            elif value is not None:
                query.append((name, value))
        response = self.client.get(
            ECONOMICS, query, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert response.status_code == 200, response.content
        return response.json()

    @staticmethod
    def _measure(body, measure, row=0):
        for entry in body["rows"][row]["measures"]:
            if entry["measure"] == measure:
                return entry
        raise AssertionError(f"{measure!r} is not in row {row}")

    def _posting(self, customer, key, **kwargs):
        """One posting. The correlation key is left at its column default on
        purpose — see the module note."""
        return Posting.objects.create(
            tenant=self.tenant, customer=customer, idempotency_key=key, **kwargs)

    def _seed(self):
        selectors_1 = dict(provider="openai", event_type="chat",
                           task_type="summarise")
        selectors_2 = dict(provider="anthropic", event_type="embed",
                           task_type="index")
        # c1: one cost UBB knows, one it does not.
        self._posting(self.c1, "k1", provider_cost_micros=KNOWN_COST_MICROS,
                      billed_cost_micros=3_000_000,
                      costing_status=COSTING_STATUS_KNOWN, **selectors_1)
        self._posting(self.c1, "k2", provider_cost_micros=None,
                      billed_cost_micros=2_000_000,
                      costing_status=COSTING_STATUS_UNRESOLVED,
                      unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
                      **selectors_1)
        # c2: one cost UBB knows, one there is nothing to know about.
        self._posting(self.c2, "k3", provider_cost_micros=OTHER_KNOWN_COST_MICROS,
                      billed_cost_micros=900_000,
                      costing_status=COSTING_STATUS_KNOWN, **selectors_2)
        self._posting(self.c2, "k4", provider_cost_micros=None,
                      billed_cost_micros=1_000_000,
                      costing_status=COSTING_STATUS_NOT_APPLICABLE, **selectors_2)

    # ---- the read contract -------------------------------------------------

    def test_the_tenant_wide_total_reports_what_it_excluded(self):
        """⚠ AND IT SAYS SO TWICE NOW. The rollup this replaced published the
        count and left a reader to notice it; the measure carries a STATE as
        well, so a figure that is a floor says it is one in the field beside
        itself."""
        cost = self._measure(self._ask(measures=[ANALYTICS_MEASURE_SUPPLIER_COGS]),
                             ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["amount_micros"] == 1_500_000
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert cost["status"] == MEASURE_STATUS_INCOMPLETE

    def test_each_day_of_the_series_carries_its_own_completeness(self):
        body = self._ask(measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                         bucket="day")
        assert len(body["rows"]) == 1
        day = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert day["amount_micros"] == 1_500_000
        assert day[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_one_customers_totals_are_partial_and_the_others_are_not(self):
        window = (self.today, self.today + timedelta(days=1))
        partial = get_customer_cost_totals(self.tenant.id, self.c1.id, *window)
        assert partial["provider_cost_micros"] == KNOWN_COST_MICROS
        assert partial[UNRESOLVED_EVENT_COUNT_KEY] == 1

        complete = get_customer_cost_totals(self.tenant.id, self.c2.id, *window)
        assert complete["provider_cost_micros"] == OTHER_KNOWN_COST_MICROS
        assert complete[UNRESOLVED_EVENT_COUNT_KEY] == 0

    def test_every_bucket_of_one_customers_series_carries_its_own_completeness(
            self):
        body = self._ask(measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                         bucket="day", customer_id=str(self.c1.id))
        assert len(body["rows"]) == 1
        cost = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["amount_micros"] == KNOWN_COST_MICROS
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_every_per_customer_row_carries_its_own_completeness(self):
        rows = {r["customer_id"]: r for r in get_per_customer_cost_totals(
            self.tenant.id, self.today, self.today + timedelta(days=1))}
        assert rows[self.c1.id][UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert rows[self.c2.id][UNRESOLVED_EVENT_COUNT_KEY] == 0

    # ---- the route ---------------------------------------------------------

    def test_every_grouped_row_carries_its_own_completeness(self):
        """The claim the four fixed breakdown blocks and the grouped margin each
        carried a copy of, asked once.

        A group whose costs are all resolved is not made partial by another
        group's that are not, and the state on each row says which it is.
        """
        for axis, partial, complete in (
                ("field:provider", "openai", "anthropic"),
                ("field:event_type", "chat", "embed"),
                ("field:task_type", "summarise", "index")):
            body = self._ask(measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                             group_by=[axis])
            by_value = {row["grouping_field_value"][0]: index
                        for index, row in enumerate(body["rows"])}
            worse = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                                  by_value[partial])
            better = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                                   by_value[complete])
            assert worse[UNRESOLVED_EVENT_COUNT_KEY] == 1, axis
            assert worse["status"] == MEASURE_STATUS_INCOMPLETE, axis
            assert better[UNRESOLVED_EVENT_COUNT_KEY] == 0, axis
            assert better["status"] == MEASURE_STATUS_KNOWN, axis

    def test_the_two_counts_are_about_different_postings(self):
        """#351's crossed case, moved here from the module that asserted it on
        the breakdown blocks (#501).

        The point is that the counts are about DIFFERENT rows. One group holds
        an unresolved COST and another an unresolved PRICE, so a row carrying
        one count for both would report each group's caveat against the wrong
        figure — and every other assertion in this class would still pass.
        """
        Posting.objects.create(
            tenant=self.tenant, customer=self.c1, idempotency_key="k5",
            provider="mistral", event_type="chat", task_type="summarise",
            provider_cost_micros=7_000, billed_cost_micros=None,
            pricing_status=PRICING_STATUS_UNKNOWN)

        body = self._ask(measures=MONEY, group_by=["field:provider"])
        by_value = {row["grouping_field_value"][0]: index
                    for index, row in enumerate(body["rows"])}

        cost_short = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                                   by_value["openai"])
        price_whole = self._measure(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                                    by_value["openai"])
        assert cost_short[UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert price_whole[UNPRICED_EVENT_COUNT_KEY] == 0

        cost_whole = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                                   by_value["mistral"])
        price_short = self._measure(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                                    by_value["mistral"])
        assert cost_whole[UNRESOLVED_EVENT_COUNT_KEY] == 0
        assert cost_whole["amount_micros"] == 7_000
        assert price_short[UNPRICED_EVENT_COUNT_KEY] == 1
        # No amount, not a zero floor (#537): the row's one posting is its
        # only piece of revenue and nobody priced it, so nothing resolved.
        assert price_short["amount_micros"] is None

    # ---- what the pair is FOR ---------------------------------------------

    def test_the_two_zeros_are_told_apart(self):
        """The whole point, and the one assertion that fails against `or 0`.

        A window holding nothing and a window holding only costs UBB has not
        learned answer the same 0 for the sum. Before the pair they were the
        same answer; now the second one says it excluded an event.
        """
        empty = get_customer_cost_totals(
            self.tenant.id, self.c1.id,
            self.today + timedelta(days=8), self.today + timedelta(days=9))
        assert empty["provider_cost_micros"] == 0
        assert empty[UNRESOLVED_EVENT_COUNT_KEY] == 0

        Posting.objects.filter(customer=self.c1,
                               costing_status=COSTING_STATUS_KNOWN).delete()
        only_unresolved = get_customer_cost_totals(
            self.tenant.id, self.c1.id, self.today, self.today + timedelta(days=1))
        assert only_unresolved["provider_cost_micros"] == 0
        assert only_unresolved[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_a_cost_that_does_not_exist_does_not_make_a_total_partial(self):
        """`not_applicable` is not missing information.

        It carries a `NULL` amount and SQL skips it exactly as it skips an
        unresolved one, so counting "rows the sum left out" would report a
        tenant whose Event Types declare no supplier cost as permanently
        incomplete. The count is of what UBB has not learned, and there is
        nothing here to learn.
        """
        window = (self.today, self.today + timedelta(days=1))
        totals = get_customer_cost_totals(self.tenant.id, self.c2.id, *window)
        assert Posting.objects.filter(
            customer=self.c2,
            costing_status=COSTING_STATUS_NOT_APPLICABLE).count() == 1
        assert totals[UNRESOLVED_EVENT_COUNT_KEY] == 0

    def test_a_window_that_costs_nothing_earns_the_whole_billed_as_margin(self):
        """The one tenant-visible number the pair CHANGED, pinned.

        The rollup this replaced answered a difference of zero whenever the
        supplier aggregate came back `None` — harmless while the column was NOT
        NULL, because `None` then meant "no rows" and billed was zero too. Since
        #317 it also means "every cost in this window is unresolved or not
        applicable", and a window that billed real money against no supplier
        cost at all is a window whose margin is ALL of it.

        Here every remaining event's Event Type declares no supplier cost, so
        the total is complete and the margin is the whole billed amount — not
        the zero the old branch would have answered. ⚠ And the margin says
        `known` rather than merely carrying a number, which is the half the old
        surface had no way to state.
        """
        Posting.objects.exclude(
            costing_status=COSTING_STATUS_NOT_APPLICABLE).delete()

        body = self._ask(measures=MONEY)
        cost = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        revenue = self._measure(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        margin = self._measure(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert cost["amount_micros"] == 0
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 0
        assert revenue["amount_micros"] == 1_000_000
        assert margin["amount_micros"] == 1_000_000
        assert margin["status"] == MEASURE_STATUS_KNOWN

    def test_the_margin_a_partial_cost_produces_is_partial_too(self):
        """Everything derived from the resolved sum inherits its completeness.

        The margin over a cost total missing an event is not a margin — it is a
        ceiling on one. ⚠ **AND IT NOW SAYS SO IN ITS OWN STATE** rather than
        leaving a reader to find the count on the measure beside it: a margin is
        no better than its worst input, so an incomplete cost makes the margin
        incomplete whatever the revenue side reads.
        """
        body = self._ask(measures=MONEY, group_by=["field:provider"])
        openai = next(index for index, row in enumerate(body["rows"])
                      if row["grouping_field_value"][0] == "openai")
        cost = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS, openai)
        margin = self._measure(body, ANALYTICS_MEASURE_GROSS_MARGIN, openai)
        assert margin["amount_micros"] == 5_000_000 - KNOWN_COST_MICROS
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert margin["status"] == MEASURE_STATUS_INCOMPLETE
