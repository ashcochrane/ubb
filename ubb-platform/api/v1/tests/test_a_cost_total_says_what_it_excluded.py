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

⚠ **TWO SURFACES ARE ASSERTED ELSEWHERE, AND THE SWEEP IS WHY.** Every retired
word this module might have spelled is one a new file cannot afford:

* the recording request's correlation key (slice 5's entry, 65 files) — which is
  why the postings below are written through the ORM rather than through the
  recording route;
* the request parameter naming a declared grouping key (slice 7's, and its
  completeness pin lives in `api/v1/tests/test_analytics_dimensions.py`);
* the request parameter naming a key out of the open bag (slice 7's, at eight
  files — both keyed rollups are pinned in
  `apps/metering/tests/test_analytics_scale.py`, which already carries the word
  and already owns those two surfaces).

Each of them would have made this module the file that pushed a recorded extent
wider. The behaviour is asserted in all three places; only the fixture is split.
"""
from datetime import timedelta

import pytest
from django.test import Client
from django.utils import timezone

from apps.metering.queries import (
    get_customer_cost_totals,
    get_dimensional_margin,
    get_per_customer_cost_totals,
    get_revenue_analytics,
    get_usage_timeseries,
)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

KNOWN_COST_MICROS = 1_000_000
OTHER_KNOWN_COST_MICROS = 500_000


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

    def test_the_tenant_wide_revenue_total_reports_what_it_excluded(self):
        out = get_revenue_analytics(self.tenant.id)
        assert out["total_provider_cost_micros"] == 1_500_000
        assert out[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_each_day_of_the_revenue_breakdown_carries_its_own_completeness(self):
        out = get_revenue_analytics(self.tenant.id)
        assert len(out["daily"]) == 1
        day = out["daily"][0]
        assert day["provider_cost_micros"] == 1_500_000
        assert day[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_one_customers_totals_are_partial_and_the_others_are_not(self):
        window = (self.today, self.today + timedelta(days=1))
        partial = get_customer_cost_totals(self.tenant.id, self.c1.id, *window)
        assert partial["provider_cost_micros"] == KNOWN_COST_MICROS
        assert partial[UNRESOLVED_EVENT_COUNT_KEY] == 1

        complete = get_customer_cost_totals(self.tenant.id, self.c2.id, *window)
        assert complete["provider_cost_micros"] == OTHER_KNOWN_COST_MICROS
        assert complete[UNRESOLVED_EVENT_COUNT_KEY] == 0

    def test_every_timeseries_bucket_carries_its_own_completeness(self):
        rows = get_usage_timeseries(self.tenant.id, customer_id=self.c1.id)
        assert len(rows) == 1
        assert rows[0]["provider_cost_micros"] == KNOWN_COST_MICROS
        assert rows[0][UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_every_per_customer_row_carries_its_own_completeness(self):
        rows = {r["customer_id"]: r for r in get_per_customer_cost_totals(
            self.tenant.id, self.today, self.today + timedelta(days=1))}
        assert rows[self.c1.id][UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert rows[self.c2.id][UNRESOLVED_EVENT_COUNT_KEY] == 0

    def test_every_grouped_margin_row_carries_its_own_completeness(self):
        rows = {r["grouping_field_value"]: r for r in get_dimensional_margin(
            self.tenant.id, group_by="provider")}
        assert rows["openai"]["provider_cost_micros"] == KNOWN_COST_MICROS
        assert rows["openai"][UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert rows["anthropic"][UNRESOLVED_EVENT_COUNT_KEY] == 0

    # ---- the route ---------------------------------------------------------

    def test_the_analytics_total_reports_what_it_excluded(self):
        body = self._get("/api/v1/metering/analytics/usage").json()
        assert body["total_provider_cost_micros"] == 1_500_000
        assert body[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_every_analytics_breakdown_row_carries_its_own_completeness(self):
        body = self._get("/api/v1/metering/analytics/usage").json()
        blocks = {
            "by_provider": ("provider", "openai", "anthropic"),
            "by_event_type": ("event_type", "chat", "embed"),
            "by_customer": ("customer__external_id", "c1", "c2"),
            "by_task_type": ("task_type", "summarise", "index"),
        }
        for block, (key, partial_value, complete_value) in blocks.items():
            rows = {r[key]: r for r in body[block]}
            assert rows[partial_value][UNRESOLVED_EVENT_COUNT_KEY] == 1, block
            assert rows[complete_value][UNRESOLVED_EVENT_COUNT_KEY] == 0, block

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

    def test_a_window_that_costs_nothing_reports_the_whole_billed_as_markup(self):
        """The one tenant-visible number this commit CHANGES, pinned.

        The revenue rollup used to answer a markup of zero whenever the provider
        aggregate came back `None` — harmless while the column was NOT NULL,
        because `None` then meant "no rows" and billed was zero too. Since #317
        it also means "every cost in this window is unresolved or not
        applicable", and a window that billed real money against no supplier
        cost at all is a window whose markup is ALL of it.

        Here every remaining event's Event Type declares no supplier cost, so
        the total is complete and the markup is the whole billed amount — not
        the zero the old branch would have answered.
        """
        Posting.objects.exclude(
            costing_status=COSTING_STATUS_NOT_APPLICABLE).delete()

        out = get_revenue_analytics(self.tenant.id)
        assert out["total_provider_cost_micros"] == 0
        assert out[UNRESOLVED_EVENT_COUNT_KEY] == 0
        assert out["total_billed_cost_micros"] == 1_000_000
        assert out["total_markup_micros"] == 1_000_000

    def test_the_margin_a_partial_cost_produces_is_partial_too(self):
        """Everything derived from the resolved sum inherits its completeness.

        The margin over a cost total missing an event is not a margin — it is a
        ceiling on one. It carries the same count rather than a second one,
        because there is one fact here and a total's own arithmetic cannot make
        it two.
        """
        rows = {r["grouping_field_value"]: r for r in get_dimensional_margin(
            self.tenant.id, group_by="provider")}
        assert rows["openai"]["margin_micros"] == 5_000_000 - KNOWN_COST_MICROS
        assert rows["openai"][UNRESOLVED_EVENT_COUNT_KEY] == 1
