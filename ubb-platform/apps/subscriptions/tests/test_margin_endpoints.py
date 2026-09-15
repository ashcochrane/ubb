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
    PRICING_STATUS_UNKNOWN, RECOGNITION_METHOD_STRAIGHT_LINE)


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
        r = self.http.get("/api/v1/margin/summary", **self._auth())
        assert r.status_code == 200  # NOT gated behind subscriptions product

    def test_supply_revenue_and_read_the_customers_margin(self):
        """The workflow the retired recurring pair used to serve (#496).

        It is the same journey — state what this customer pays you, then read
        the margin — through the record that says which period the figure was
        about and where it came from. ⚠ **AND THE MARGIN NAMES THE SOURCE**:
        the supplied figure is its own field on the response, so the total
        beside it can be taken apart by whoever reads it, which is the thing
        the retired pair made impossible.

        ⚠ **THE READ IS MONTH-TO-DATE, SO THE EXPECTED SHARE IS COMPUTED, NOT
        TYPED.** This route's default window runs from the first of the month
        to tomorrow, and a supplied figure reaches margin on the `recognised`
        basis — the retired accrual's own day-proration. Hard-coding the whole
        month's amount here would pass only on the last day of a month, and a
        hard-coded fraction would rot on the first of the next one. The
        arithmetic below is the route's own, which is what makes this case
        calendar-proof rather than calendar-lucky.
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

        r = self.http.get(f"/api/v1/margin/customers/{self.customer.id}", **self._auth())
        assert r.status_code == 200
        b = r.json()
        days_in_period = (period_end - period_start).days
        days_read = (today + datetime.timedelta(days=1) - period_start).days
        expected_supplied = 500_000_000 * days_read // days_in_period

        assert b["provider_cost_micros"] == 1_000_000
        assert b["usage_billed_micros"] == 1_300_000
        assert b["supplied_revenue_micros"] == expected_supplied
        assert b["subscription_revenue_micros"] == 0
        # metered_only mode: usage excluded from revenue; margin = revenue - provider_cost
        assert b["gross_margin_micros"] == expected_supplied - 1_000_000
        assert b["total_revenue_micros"] == expected_supplied

    def test_a_customer_with_no_supplied_figure_reads_nothing_supplied(self):
        """The other posture, which must stay first-class (#153 §3.2).

        A cost-tracking-only tenant is not a tenant that earned nothing — but
        this surface has no state to say so with, so what it owes is a zero
        that cannot be mistaken for a supplied figure, and the read that DOES
        answer the question. Both are asserted, because asserting only the
        first would bless the zero.
        """
        r = self.http.get(f"/api/v1/margin/customers/{self.customer.id}", **self._auth())
        assert r.json()["supplied_revenue_micros"] == 0

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

    def test_list_all_customer_margins(self):
        # #86 sweep: the root margin list moved from GET /margin to the explicit
        # GET /margin/customers segment — proving the named subpaths (/summary,
        # /by-grouping-field, ...) are no longer shadowed by a bare mount root.
        r = self.http.get("/api/v1/margin/customers", **self._auth())
        self.assertEqual(r.status_code, 200, r.content)
        body = r.json()
        self.assertIn("customers", body)
        self.assertTrue(
            any(c["customer_id"] == str(self.customer.id) for c in body["customers"]))

    def test_customer_margin_trend_new_path(self):
        # #86 sweep: GET /margin/{customer_id}/trend -> /margin/customers/{id}/trend
        # (the bare-{customer_id} shadow is gone; a UUID no longer competes with
        # /summary et al. at the mount root).
        r = self.http.get(
            f"/api/v1/margin/customers/{self.customer.id}/trend", **self._auth())
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["customer_id"], str(self.customer.id))
        self.assertIn("points", r.json())

    def test_by_grouping_field_provider(self):
        # Ported off the old `provider: int` pseudo-flag (#128 rework) to the
        # real group_by string.
        r = self.http.get("/api/v1/margin/by-grouping-field?group_by=provider", **self._auth())
        assert r.status_code == 200
        rows = r.json()["rows"]
        assert any(row["grouping_field_value"] == "openai"
                   and row["margin_micros"] == 300_000 for row in rows)

    def test_by_grouping_field_unknown_group_by_is_422(self):
        r = self.http.get("/api/v1/margin/by-grouping-field?group_by=nope", **self._auth())
        assert r.status_code == 422

    def test_by_grouping_field_publishes_what_the_margin_excluded(self):
        """The DECLARED row of the three rollups reaches the tenant whole (#327).

        A margin over a cost total missing an event is a ceiling on a margin,
        and this is the only one of the three rollups over these axes whose row
        is a schema — so it is the only one where an unnamed key is silently
        DROPPED rather than merely undocumented. Both review axes found this
        row shedding the count on the way out.

        The provider group is partial and the row still states the margin it
        can: 1,300,000 billed against the 1,000,000 UBB knows it paid, with one
        event's cost excluded.
        """
        from apps.metering.usage.models import Posting

        Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="i3",
            provider="openai", billed_cost_micros=0, provider_cost_micros=None,
            costing_status="unresolved", unresolved_reason="cost_rate_missing")

        r = self.http.get("/api/v1/margin/by-grouping-field?group_by=provider",
                          **self._auth())
        assert r.status_code == 200
        row = next(x for x in r.json()["rows"]
                   if x["grouping_field_value"] == "openai")
        assert row["provider_cost_micros"] == 1_000_000
        assert row["margin_micros"] == 300_000
        assert row["unresolved_event_count"] == 1

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

    def test_window_over_366_days_refused(self):
        """An explicit report window longer than 366 days → 422 problem+json."""
        r = self.http.get(
            "/api/v1/margin/summary?start_date=2024-01-01&end_date=2025-06-01",
            **self._auth())
        assert r.status_code == 422, r.content
        assert r["Content-Type"] == "application/problem+json"
        body = r.json()
        assert body["code"] == "validation_error", body
        assert body["detail"] == "date window must not exceed 366 days", body

    def test_window_exactly_366_days_allowed(self):
        """The boundary itself (one leap year, 366 days) is accepted."""
        r = self.http.get(
            "/api/v1/margin/summary?start_date=2024-01-01&end_date=2025-01-01",
            **self._auth())
        assert r.status_code == 200, r.content
