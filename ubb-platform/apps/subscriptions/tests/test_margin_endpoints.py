import datetime
import json
from unittest.mock import patch
from django.test import TestCase, Client
from django.utils import timezone
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, priced_at)
from apps.metering.usage.services.usage_service import UsageService
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_SUPPLIER_COGS, PRICING_STATUS_UNKNOWN,
    RECOGNITION_METHOD_STRAIGHT_LINE, REVENUE_BASIS_RECOGNISED)


class MarginEndpointsTest(TestCase):
    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Heyotis", products=["metering"])  # NO subscriptions
        _, self.key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        # The two events still bill exactly what they always billed — but a
        # customer price is UBB's to resolve now (#365), so the amounts are
        # CONFIGURED rather than stated on the call.
        a_rule_that_prices_what_it_measures(self.tenant)
        with patch("apps.platform.events.tasks.process_single_event"):
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer, idempotency_key="i1",
                provider_cost_micros=800_000, measurements=priced_at(1_000_000),
                provider="openai")
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer, idempotency_key="i2",
                provider_cost_micros=200_000, measurements=priced_at(300_000),
                provider="openai")

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def test_metering_tenant_can_access_margin(self):
        """The gate, on a surface this module still owns.

        It asked the tenant-wide margin total until #501 collapsed that route;
        the claim is about the PRODUCT check rather than about the report, so it
        moved to the alerting list beside it — which is gated identically and is
        one of the surfaces §14 keeps.
        """
        r = self.http.get("/api/v1/margin/unprofitable", **self._auth())
        assert r.status_code == 200  # NOT gated behind subscriptions product

    def _measure(self, body, measure):
        return next(entry for entry in body["rows"][0]["measures"]
                    if entry["measure"] == measure)

    def _one_customers_margin(self):
        """This customer's economics, month to date, on the surface that
        answers it since #501 — the one query, filtered."""
        response = self.http.get(
            "/api/v1/metering/analytics/economics",
            {"measures": [ANALYTICS_MEASURE_SUPPLIER_COGS,
                          ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                          ANALYTICS_MEASURE_GROSS_MARGIN],
             "customer_id": str(self.customer.id),
             "basis": REVENUE_BASIS_RECOGNISED},
            **self._auth())
        assert response.status_code == 200, response.content
        return response.json()

    def test_supply_revenue_and_read_the_customers_margin(self):
        """The workflow the retired recurring pair used to serve (#496).

        It is the same journey — state what this customer pays you, then read
        the margin — through the record that says which period the figure was
        about and where it came from.

        ⚠ **WHERE THE SOURCE IS NAMED CHANGED WITH THE COLLAPSE (#501), AND
        THAT IS WORTH STATING RATHER THAN QUIETLY DROPPING.** One customer's
        margin used to publish a field per revenue source, so the total could be
        taken apart on the same response. The one economic query answers
        `customer_revenue` as ONE measure from one definition — which is the
        point of it — so the way to take a total apart is to ask the
        supplied-revenue read, which names the figure, its basis, its period and
        its source reference. Both halves are asserted below, because the
        journey is only served if both work.

        ⚠ **THE READ IS MONTH-TO-DATE, SO THE EXPECTED SHARE IS COMPUTED, NOT
        TYPED.** The default window runs from the first of the month through
        today, and a supplied figure reaches margin on the `recognised` basis —
        the retired accrual's own day-proration. Hard-coding the whole month's
        amount would pass only on the last day of a month, and a hard-coded
        fraction would rot on the first of the next one.
        """
        today = timezone.now().date()
        period_start = today.replace(day=1)
        period_end = (period_start.replace(year=period_start.year + 1, month=1)
                      if period_start.month == 12
                      else period_start.replace(month=period_start.month + 1))
        r = self.http.post(
            f"/api/v1/margin/customers/{self.customer.id}/supplied-revenue",
            data=json.dumps({
                "amount_micros": 500_000_000, "currency": "usd",
                "period_start": period_start.isoformat(),
                "period_end": period_end.isoformat(),
                "recognition_method": RECOGNITION_METHOD_STRAIGHT_LINE,
                "source_reference": "INV-9001"}),
            content_type="application/json", **self._auth())
        assert r.status_code == 200, r.content

        days_in_period = (period_end - period_start).days
        days_read = (today + datetime.timedelta(days=1) - period_start).days
        expected_supplied = 500_000_000 * days_read // days_in_period

        body = self._one_customers_margin()
        assert self._measure(
            body, ANALYTICS_MEASURE_SUPPLIER_COGS)["amount_micros"] == 1_000_000
        # The supplied figure is the WHOLE revenue for this customer and the
        # month it covers (#537), so the 1,300,000 UBB priced for the two events
        # inside that month is superseded rather than added — which is what the
        # case without a supplied figure below still reads. Until #537 this
        # asserted supplied + billed: a tenant billing elsewhere, counted twice.
        assert self._measure(
            body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)["amount_micros"] == (
            expected_supplied)
        assert self._measure(
            body, ANALYTICS_MEASURE_GROSS_MARGIN)["amount_micros"] == (
            expected_supplied - 1_000_000)

        # And the total can still be taken apart, on the read that owns the
        # figure: the supplied share, under the basis it was attributed on,
        # with the reference that says where the number came from.
        supplied = self.http.get(
            f"/api/v1/margin/customers/{self.customer.id}/supplied-revenue",
            {"basis": REVENUE_BASIS_RECOGNISED}, **self._auth()).json()
        assert supplied["totals"] == [{"currency": "usd",
                                       "amount_micros": expected_supplied}]
        assert supplied["records"][0]["source_reference"] == "INV-9001"

    def test_a_customer_with_no_supplied_figure_reads_nothing_supplied(self):
        """The other posture, which must stay first-class (#153 §3.2).

        A cost-tracking-only tenant is not a tenant that earned nothing. The
        margin surface has no state to say so with — its revenue measure is one
        figure from one definition — so what answers the question is the
        supplied-revenue read, and an EMPTY list of totals there is how
        `unknown` is served. Asserting the margin alone would bless a number
        that cannot distinguish *supplied nothing* from *supplied zero*.
        """
        body = self._one_customers_margin()
        assert self._measure(
            body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)["amount_micros"] == 1_300_000

        r = self.http.get(
            f"/api/v1/margin/customers/{self.customer.id}/supplied-revenue",
            **self._auth())
        assert r.status_code == 200, r.content
        assert r.json()["pricing_status"] == PRICING_STATUS_UNKNOWN
        assert r.json()["totals"] == []

    def test_the_retired_recurring_pair_is_gone(self):
        """Both operations, both verbs — the break block's one path (#496).

        A route that answered on either verb would mean the contract still
        publishes it whatever the regenerated document says.
        """
        path = f"/api/v1/margin/customers/{self.customer.id}/revenue"
        assert self.http.get(path, **self._auth()).status_code == 404
        assert self.http.put(
            path, data=json.dumps({"recurring_amount_micros": 1}),
            content_type="application/json", **self._auth()).status_code == 404

    # THE LIST, THE TREND AND THE THREE GROUPED-BREAKDOWN CASES WERE HERE AND
    # ARE GONE WITH THEIR ROUTES (#501). Two of them existed only to prove a
    # #86 path move — that a named subpath was no longer shadowed by a bare
    # mount root — and both of the paths they pinned have now left the contract
    # entirely, which is a stronger statement than either was making.
    #
    # The behaviour they covered is asserted where it now lives: the
    # per-customer rows and the grouped breakdown in
    # `api/v1/tests/test_the_one_economic_query.py`, each against the figures
    # these routes returned, and the per-group completeness count in
    # `api/v1/tests/test_a_cost_total_says_what_it_excluded.py`. That the nine
    # paths answer nothing at all is
    # `api/v1/tests/test_the_collapse_and_what_survived_it.py`.

    def test_threshold_get_default_and_put(self):
        r = self.http.get("/api/v1/margin/threshold", **self._auth())
        assert r.status_code == 200 and r.json()["provider_cost_spike_pct"] == 25.0
        r = self.http.put("/api/v1/margin/threshold",
                          data=json.dumps({"min_margin_pct": 15.0}),
                          content_type="application/json", **self._auth())
        assert r.status_code == 200
        r = self.http.get("/api/v1/margin/threshold", **self._auth())
        assert r.json()["min_margin_pct"] == 15.0

    def test_unprofitable_empty(self):
        r = self.http.get("/api/v1/margin/unprofitable", **self._auth())
        assert r.status_code == 200 and r.json()["customers"] == []

    #: The read this module still owns that resolves a window, so the bound the
    #: collapsed reports shared is still asserted here. ⚠ The one query has its
    #: OWN case for the same ceiling, and the two differ: this one bounds only
    #: where both dates were sent, and that one bounds the RESOLVED span, which
    #: is the escape #499 closed and #501 took away with the routes that had it.
    A_WINDOWED_READ = "/api/v1/margin/customers/{}/supplied-revenue"

    def test_window_over_366_days_refused(self):
        """An explicit report window longer than 366 days → 422 problem+json."""
        r = self.http.get(
            self.A_WINDOWED_READ.format(self.customer.id)
            + "?start_date=2024-01-01&end_date=2025-06-01",
            **self._auth())
        assert r.status_code == 422, r.content
        assert r["Content-Type"] == "application/problem+json"
        body = r.json()
        assert body["code"] == "validation_error", body
        assert body["detail"] == "date window must not exceed 366 days", body

    def test_window_exactly_366_days_allowed(self):
        """The boundary itself (one leap year, 366 days) is accepted."""
        r = self.http.get(
            self.A_WINDOWED_READ.format(self.customer.id)
            + "?start_date=2024-01-01&end_date=2025-01-01",
            **self._auth())
        assert r.status_code == 200, r.content
