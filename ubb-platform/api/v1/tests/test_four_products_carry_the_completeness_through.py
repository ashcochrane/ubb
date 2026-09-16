"""What a total left out survives the trip out to every product (#328).

#327 made every supplier-cost total a **pair** — the resolved sum and
``unresolved_event_count``, the number of postings whose cost UBB has not
learned — and built both halves in one place, ``core.cost_totals``. This module
is about what happens NEXT: the pair is only worth building if it is still there
when a tenant reads it, and between the read contract and the tenant sit four
products that each add the cost up again in their own way.

**A DROPPED COUNT IS WORSE THAN NO COUNT AT ALL**, because the total beside it
survives: a reader handed a figure with no caveat concludes it is whole. Three
sites did something stronger than dropping it and each needed a decision rather
than a coalesce:

* the **spike comparison** divided by a previous period's cost. A previous cost
  that is a floor makes the denominator too small and the rise too big, so the
  one direction that mattered was the one it got wrong — a false alarm about
  money. An unresolved previous cost is not a spike of any size, so the
  comparison is skipped.
* the **work unit accumulator** added each event's cost into a running total.
  It now adds the known part and counts the rest, and the total it publishes is
  a floor that says so.
* the **margin endpoints** summed the read contract's per-customer rows and
  dropped the count each row carried. A margin over a partial cost is a
  ceiling on a margin.

A fourth, in the composition layer, would have **raised** rather than answered
wrong: the per-customer report of what was spent past a stop added ``None``
into a Python sum. That report retired in #466; Stops and breaches itemises
the same events and is held to the same pair below.

⚠ **`not_applicable` IS NOT COUNTED, HERE OR ANYWHERE.** It carries a `NULL`
amount and is skipped by SQL exactly as an unresolved cost is, so every
assertion below is paired with one over an Event Type that declares no supplier
cost at all. Counting those would mark every metering-only tenant's every total
partial forever, and a caveat that is always on is a caveat nobody reads. That
ruling is #327's; what is new here is that FOUR MORE PRODUCTS have to be able to
tell the two apart, which is why ``usage.recorded`` now carries the status
beside the amount — a subscriber reading only the amount sees the same `None`
for both.

⚠ **THE POSTINGS BELOW ARE WRITTEN THROUGH THE ORM**, and the recording route is
never called, for the reason #327's module gives: the recording request's
correlation key is a retired word at a ledger this file must not widen.
"""
import json
from datetime import date, timedelta

import pytest
from django.db import transaction
from django.test import Client
from django.utils import timezone

from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work import reasons
from apps.platform.work.services import TaskService
from apps.platform.work.services import STOP_CAUSE_KEY
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    MEASURE_STATUS_INCOMPLETE,
    TASK_OUTCOME_DELIVERED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

KNOWN_COST_MICROS = 1_000_000
OTHER_KNOWN_COST_MICROS = 500_000
#: WHAT EACH POSTING IN THIS MODULE IS PRICED AT. Named since #497,
#: because it is now load-bearing in an assertion below rather than only a
#: default nobody read: every posting's customer price is revenue, so a
#: margin here is this figure times the postings less the supplier cost.
BILLED_MICROS = 3_000_000


def _posting(tenant, customer, key, *, status=COSTING_STATUS_KNOWN,
             cost=KNOWN_COST_MICROS, billed=BILLED_MICROS, **kwargs):
    """One posting in one of the three costing states.

    The amount and the status move together because the database refuses every
    other combination (``ck_posting_costing_status_agrees_with_the_cost``), so a
    fixture that got them out of step would fail as a write rather than
    quietly test a row that cannot exist.
    """
    if status == COSTING_STATUS_KNOWN:
        amount, reason = cost, None
    elif status == COSTING_STATUS_UNRESOLVED:
        amount, reason = None, UNRESOLVED_REASON_COST_RATE_MISSING
    else:
        amount, reason = None, None
    return Posting.objects.create(
        tenant=tenant, customer=customer, idempotency_key=key,
        provider_cost_micros=amount, costing_status=status,
        unresolved_reason=reason, billed_cost_micros=billed, **kwargs)


@pytest.mark.django_db
class TestTheWorkUnitTotalIsAFloor:
    """Platform's accumulator: the known part, and a count of the rest.

    The unit total is the one figure in this module that is WRITTEN rather than
    derived — it is maintained on every recording, so a cost UBB never learns
    is a gap the total can never close by re-reading. That is exactly why the
    counter has to be written beside it at the same moment.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")

    def _unit(self, **kwargs):
        with transaction.atomic():
            return TaskService.create_task(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0, **kwargs)

    def _accumulate(self, unit, *, status, cost=KNOWN_COST_MICROS, billed=1_000):
        amount = cost if status == COSTING_STATUS_KNOWN else None
        with transaction.atomic():
            return TaskService.accumulate_cost(
                unit.id, billed_cost_micros=billed, provider_cost_micros=amount,
                costing_status=status)

    def test_the_total_holds_the_known_part_and_counts_what_it_left_out(self):
        unit = self._unit()
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        unit.refresh_from_db()
        assert unit.total_provider_cost_micros == KNOWN_COST_MICROS
        assert unit.unresolved_event_count == 1
        assert unit.event_count == 2

    def test_a_cost_that_does_not_exist_leaves_the_total_whole(self):
        unit = self._unit()
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_NOT_APPLICABLE)
        unit.refresh_from_db()
        assert unit.total_provider_cost_micros == KNOWN_COST_MICROS
        assert unit.unresolved_event_count == 0

    def test_a_parent_inherits_the_gap_its_subtask_could_not_fill(self):
        """Containment carries the caveat, not just the money.

        A subtask's spend rolls into its parent, so a parent whose child
        excluded a cost has excluded it too — a parent total that read complete
        while its child's read partial would be two answers about one tree.
        """
        parent = self._unit()
        child = self._unit(parent=parent)
        self._accumulate(child, status=COSTING_STATUS_UNRESOLVED)
        parent.refresh_from_db()
        child.refresh_from_db()
        assert child.unresolved_event_count == 1
        assert parent.unresolved_event_count == 1

    def test_the_unit_receipt_says_the_total_is_a_floor(self):
        """The tenant-facing read of the same pair."""
        _, raw_key = TenantApiKey.create_key(self.tenant)
        unit = self._unit()
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        body = Client().get(f"/api/v1/tasks/{unit.id}",
                            HTTP_AUTHORIZATION=f"Bearer {raw_key}").json()
        assert body["total_provider_cost_micros"] == KNOWN_COST_MICROS
        assert body[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_the_unit_economics_rollup_carries_its_own_completeness(self):
        """Per KIND of work — the number that sets a price.

        A mean cost per job built from floors is itself a floor, and a tenant
        pricing off it is the reader with the most to lose from a silent one.
        """
        from apps.platform.work.queries import task_rollup_by_type

        partial = self._unit(task_type="summarise")
        self._accumulate(partial, status=COSTING_STATUS_KNOWN)
        self._accumulate(partial, status=COSTING_STATUS_UNRESOLVED)
        whole = self._unit(task_type="index")
        self._accumulate(whole, status=COSTING_STATUS_KNOWN)

        rows = {r["task_type"]: r for r in task_rollup_by_type(self.tenant.id)}
        assert rows["summarise"][UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert rows["index"][UNRESOLVED_EVENT_COUNT_KEY] == 0

    def test_an_absent_cost_called_known_is_refused_rather_than_dropped(self):
        """The default on the status parameter, and why it is safe.

        `costing_status` defaults to `known` so the twenty-odd callers passing
        a real amount need not restate the obvious — but that same default is
        how a caller could hand this seam a `None` with nothing said and have
        the exclusion vanish, which is "replaced by another default" rather
        than by the pair. It is the posting table's own rule (`known` implies
        the amount is NOT NULL), enforced where the accumulator can see it,
        because this total is WRITTEN: an exclusion missed here cannot be
        recovered by re-reading anything.
        """
        unit = self._unit()
        with pytest.raises(ValueError, match="costing_status"):
            with transaction.atomic():
                TaskService.accumulate_cost(
                    unit.id, billed_cost_micros=1, provider_cost_micros=None)
        unit.refresh_from_db()
        assert unit.unresolved_event_count == 0
        assert unit.event_count == 0

    def test_the_re_announcement_publishes_the_current_completeness(self):
        """A repaired delivery says exactly what the original said.

        The patrol re-mints a kill whose announcement dead-lettered, from the
        unit's CURRENT state. A re-mint that dropped the count would tell a
        consumer more than the first delivery did — the same total, minus the
        caveat that makes it a floor.
        """
        from apps.billing.gating.patrol import _remint_kill
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import TaskKilled

        unit = self._unit(task_cogs_ceiling_micros=1)
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        # Re-read before touching it: `accumulate_cost` locks and mutates its
        # OWN instance, so saving the one created above would write the totals
        # back to zero and this test would assert against a unit that never
        # accumulated anything.
        unit.refresh_from_db()
        unit.metadata = {STOP_CAUSE_KEY: reasons.TASK_COGS_CEILING}
        unit.status = "killed"
        unit.save()
        _remint_kill(unit, self.tenant)
        payload = OutboxEvent.objects.filter(
            event_type=TaskKilled.EVENT_TYPE).latest("created_at").payload
        assert payload["re_announcement"] is True
        assert payload["total_provider_cost_micros"] == KNOWN_COST_MICROS
        assert payload[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_closing_a_unit_settles_nothing_it_never_learned(self):
        """The close receipt is the last thing many callers read.

        Closing a unit changes its status and nothing about what UBB knows, so
        a total that was a floor while the unit ran is still a floor once it
        stops. A close response that dropped the count would be the one surface
        that made a partial total look final.
        """
        _, raw_key = TenantApiKey.create_key(self.tenant)
        unit = self._unit()
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        body = Client().post(
            f"/api/v1/tasks/{unit.id}/close",
            data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}").json()
        assert body["status"] == "completed"
        assert body["total_provider_cost_micros"] == KNOWN_COST_MICROS
        assert body[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_a_unit_is_not_killed_for_spend_ubb_cannot_demonstrate(self):
        """The COGS limit races the FLOOR, and that is the safe direction.

        Two events, one of them a cost UBB could not resolve, against a limit
        the pair would cross but the known part does not. The patrol passes the
        unit over: firing here would mean killing a tenant's work on a number
        nobody has stated. The count is what makes the silence readable — a
        limit that has not fired is visibly not the same as one shown to be
        safe.
        """
        from apps.billing.gating.patrol import sweep_over_limit_tasks

        unit = self._unit(task_cogs_ceiling_micros=KNOWN_COST_MICROS + 1)
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        assert sweep_over_limit_tasks(self.tenant) == 0
        unit.refresh_from_db()
        assert unit.status == "active"
        assert unit.unresolved_event_count == 1

    def test_the_kill_announcement_carries_the_floor_it_killed_on(self):
        """A limit crossing announces the total that crossed it.

        The unit was killed on a floor, so a consumer reading the announcement
        as the spend that triggered it is reading a lower bound.
        """
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import TaskKilled

        unit = self._unit(task_cogs_ceiling_micros=1)
        self._accumulate(unit, status=COSTING_STATUS_UNRESOLVED)
        self._accumulate(unit, status=COSTING_STATUS_KNOWN)
        TaskService.kill_and_announce(unit.id, reasons.TASK_COGS_CEILING,
                                      tenant_id=self.tenant.id,
                                      customer_id=self.customer.id)
        # Addressed through the schema's own constant rather than by spelling
        # the catalog name. That was originally because the announcement's type
        # was a retired word this file must not widen; the split paid that debt
        # and the constant stays, because it is the stricter assertion — it
        # goes red if the kill lane ever starts announcing a different state.
        payload = OutboxEvent.objects.get(
            event_type=TaskKilled.EVENT_TYPE).payload
        assert payload["total_provider_cost_micros"] == KNOWN_COST_MICROS
        assert payload[UNRESOLVED_EVENT_COUNT_KEY] == 1


@pytest.mark.django_db
class TestTheMarginSaysWhatItsCostExcluded:
    """Subscriptions' margin surface: a ceiling that says it is one.

    Every figure here is revenue MINUS a cost total. A cost total that is a
    floor makes the margin a ceiling — the true margin can only be smaller —
    and the count is the only thing on the page that says so.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.c1 = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.c2 = Customer.objects.create(tenant=self.tenant, external_id="c2")
        self.client = Client()
        # c1's cost is partial; c2's is whole, and one of its events has no
        # supplier cost to learn.
        _posting(self.tenant, self.c1, "k1", status=COSTING_STATUS_KNOWN)
        _posting(self.tenant, self.c1, "k2", status=COSTING_STATUS_UNRESOLVED)
        _posting(self.tenant, self.c2, "k3", status=COSTING_STATUS_KNOWN,
                 cost=OTHER_KNOWN_COST_MICROS)
        _posting(self.tenant, self.c2, "k4", status=COSTING_STATUS_NOT_APPLICABLE)

    def _get(self, path):
        return self.client.get(
            path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}").json()

    def _economics(self, **params):
        """⚠ THREE OF THIS CLASS'S SURFACES COLLAPSED INTO ONE (#501) and the
        claim travels with them: a cost total that is a floor makes the margin a
        ceiling, and the count is what says so. What the one query adds is that
        the measure says it in its own state as well."""
        query = [("measures", name) for name in (
            ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
            ANALYTICS_MEASURE_GROSS_MARGIN)]
        query += list(params.items())
        response = self.client.get("/api/v1/metering/analytics/economics",
                                   query,
                                   HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        assert response.status_code == 200, response.content
        return response.json()

    @staticmethod
    def _measure(body, measure, row=0):
        return next(entry for entry in body["rows"][row]["measures"]
                    if entry["measure"] == measure)

    def test_the_tenant_wide_summary_reports_what_its_cost_total_excluded(self):
        cost = self._measure(self._economics(),
                             ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["amount_micros"] == (
            KNOWN_COST_MICROS + OTHER_KNOWN_COST_MICROS)
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_one_customers_gap_does_not_make_anothers_margin_partial(self):
        body = self._economics(group_by="field:customer")
        counts = {
            row["grouping_field_value"][0]:
                self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                              index)[UNRESOLVED_EVENT_COUNT_KEY]
            for index, row in enumerate(body["rows"])}
        assert counts[str(self.c1.id)] == 1
        assert counts[str(self.c2.id)] == 0

    def test_one_customers_live_margin_carries_its_own_count(self):
        """The count is the subject; the margin beside it is what the count
        qualifies.

        ⚠ **THE MARGIN FIGURE HERE WAS THE DELETED SWITCH'S UNTIL #497**, and
        it read `-KNOWN_COST_MICROS` — minus the whole supplier cost, because
        this tenant meters and does not bill through UBB, so a customer-level
        setting struck both postings' customer price out of its revenue. That
        setting is gone: who raises a customer's invoices does not decide
        whether the work was sold, and the price UBB resolved is revenue. The
        expression below is written from the fixture rather than as a literal,
        so it says WHY the number is what it is.

        Nothing about this case's own claim moves. `c1` has two postings, one
        of which carries a supplier cost UBB never learned; the cost total is
        therefore a floor, the margin a CEILING, and the count beside it is
        what says so. A margin that is now positive makes that sharper rather
        than weaker — an unlearned cost can only take it down.
        """
        body = self._economics(customer_id=str(self.c1.id))
        cost = self._measure(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert cost["amount_micros"] == KNOWN_COST_MICROS
        assert cost[UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert self._measure(
            body, ANALYTICS_MEASURE_CUSTOMER_REVENUE
        )["amount_micros"] == 2 * BILLED_MICROS
        margin = self._measure(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin["amount_micros"] == 2 * BILLED_MICROS - KNOWN_COST_MICROS
        # ⚠ AND THE MARGIN SAYS IT IS A CEILING IN ITS OWN STATE, which is the
        # half the surface this replaced had no field for: a reader had to know
        # to look at the count on the measure beside it.
        assert margin["status"] == MEASURE_STATUS_INCOMPLETE

    def test_a_business_rollup_adds_its_seats_counts_up(self):
        """A rollup over seats is a total like any other.

        Its cost is the sum of the seats' costs, so its completeness is the sum
        of theirs — one seat's unresolved cost makes the business figure a
        floor.
        """
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business")
        for seat in (self.c1, self.c2):
            seat.parent = business
            seat.save(update_fields=["parent", "updated_at"])
        body = self._get("/api/v1/margin/business/biz")
        assert body["totals"][UNRESOLVED_EVENT_COUNT_KEY] == 1
        seats = {s["customer_id"]: s for s in body["seats"]}
        assert seats[str(self.c1.id)][UNRESOLVED_EVENT_COUNT_KEY] == 1
        assert seats[str(self.c2.id)][UNRESOLVED_EVENT_COUNT_KEY] == 0


@pytest.mark.django_db
class TestTheAccumulatorAndTheSnapshot:
    """Subscriptions' monthly pair: written by an event, read as a margin."""

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        self.today = timezone.now().date()
        self.period_start = self.today.replace(day=1)

    def _record(self, *, status, cost=KNOWN_COST_MICROS, billed=2_000_000):
        """Deliver one `usage.recorded` to the subscriptions handler.

        Built as `asdict(UsageRecorded(...))` rather than a literal dict, per
        `docs/conventions/testing.md`: this is a payload a consumer PARSES, and
        a literal would re-encode the field names — including `costing_status`,
        the one this ticket adds and the one the handler counts off.
        """
        from dataclasses import asdict

        from apps.platform.events.schemas import UsageRecorded
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions

        handle_usage_recorded_subscriptions("evt-1", asdict(UsageRecorded(
            tenant_id=self.tenant.id,
            customer_id=self.customer.id,
            event_id="evt-1",
            cost_micros=billed,
            billed_cost_micros=billed,
            provider_cost_micros=cost if status == COSTING_STATUS_KNOWN else None,
            costing_status=status,
            effective_at=timezone.now().isoformat())))

    def _accumulator(self):
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        return CustomerCostAccumulator.objects.get(
            tenant_id=self.tenant.id, customer_id=self.customer.id)

    def test_the_running_total_counts_the_cost_it_could_not_add(self):
        self._record(status=COSTING_STATUS_KNOWN)
        self._record(status=COSTING_STATUS_UNRESOLVED)
        acc = self._accumulator()
        assert acc.total_provider_cost_micros == KNOWN_COST_MICROS
        assert acc.unresolved_event_count == 1

    def test_a_cost_that_does_not_exist_leaves_the_running_total_whole(self):
        self._record(status=COSTING_STATUS_KNOWN)
        self._record(status=COSTING_STATUS_NOT_APPLICABLE)
        assert self._accumulator().unresolved_event_count == 0

    def test_an_event_that_bills_nothing_still_reports_the_cost_it_could_not_read(self):
        """The early return had one more thing to check.

        An event with nothing billed and nothing costed used to be skipped
        entirely, which was right while `None` meant zero. A cost UBB has not
        learned is not nothing — skipping it is how a period comes to look
        complete because the only thing missing from it was never counted.
        """
        self._record(status=COSTING_STATUS_UNRESOLVED, billed=0)
        assert self._accumulator().unresolved_event_count == 1

    def test_the_monthly_snapshot_inherits_the_accumulators_count(self):
        from apps.subscriptions.economics.services import MarginService

        self._record(status=COSTING_STATUS_KNOWN)
        self._record(status=COSTING_STATUS_UNRESOLVED)
        econ = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, self.period_start,
            self.period_start + timedelta(days=31))
        assert econ.provider_cost_micros == KNOWN_COST_MICROS
        assert econ.unresolved_event_count == 1

    def test_the_unprofitable_list_carries_the_periods_count(self):
        """⚠ TWO READS OF THE SAME SNAPSHOT UNTIL #501, AND ONE OF THEM WAS A
        REPORT.

        The trend stated the count PER POINT, because completeness varies month
        to month and one count at the top would be a claim about the wrong
        months. That reasoning was sound and the surface is gone: a reporting
        read may not take a margin figure off the alerting record at all, so the
        trend is `bucket=month` on the one economic query and carries the count
        per bucket for the same reason it carried it per point.

        What is left here is the ALERTING read, and its reason is its own: a
        margin named unprofitable on a partial cost is a CEILING — the customer
        can only be worse than the figure says, never better — so the count can
        never read as a reprieve.
        """
        from apps.subscriptions.economics.services import MarginService

        _, raw_key = TenantApiKey.create_key(self.tenant)
        self._record(status=COSTING_STATUS_UNRESOLVED)
        econ = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, self.period_start,
            self.period_start + timedelta(days=31))
        econ.is_unprofitable = True
        econ.save(update_fields=["is_unprofitable", "updated_at"])

        listed = Client().get(
            f"/api/v1/margin/unprofitable?period_start={self.period_start}",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}").json()
        assert listed["customers"][0][UNRESOLVED_EVENT_COUNT_KEY] == 1

    def test_the_economics_summary_adds_the_snapshots_counts_up(self):
        """#327 left this total a single figure and said why.

        Its `Sum` is over a NOT NULL snapshot column, so SQL's null-skipping
        could never reach it and there was nothing there to report. What it
        could inherit was a partiality from upstream — and upstream now records
        one, so the figure it publishes has something true to say.
        """
        from apps.subscriptions.economics.services import MarginService
        from apps.subscriptions.queries import get_economics_summary

        self._record(status=COSTING_STATUS_UNRESOLVED)
        MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, self.period_start,
            self.period_start + timedelta(days=31))
        summary = get_economics_summary(
            self.tenant.id, self.period_start,
            self.period_start + timedelta(days=31))
        assert summary[UNRESOLVED_EVENT_COUNT_KEY] == 1


@pytest.mark.django_db
class TestAnUnresolvedPreviousCostIsNotASpike:
    """The comparison that had to be skipped rather than defaulted.

    A cost spike is a RATIO, and the previous period is the denominator. A
    previous total that excluded costs is too small, so every ratio built on it
    is too big — the failure direction is a false alarm about somebody's money,
    which is worse than silence. There is no substitute figure to divide by
    either: the true previous cost is unknown, not zero, and that is the whole
    reason the count exists.
    """

    def setup_method(self):
        from apps.subscriptions.economics.models import MarginThresholdConfig

        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        MarginThresholdConfig.objects.create(
            tenant=self.tenant, customer=None, min_margin_pct=0,
            consecutive_periods=1, provider_cost_spike_pct=25)
        self.prev_start = date(2026, 1, 1)
        self.this_start = date(2026, 2, 1)

    def _snapshot(self, period_start, *, cost, unresolved=0):
        from apps.subscriptions.economics.models import CustomerEconomics

        return CustomerEconomics.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=period_start,
            period_end=period_start + timedelta(days=28),
            provider_cost_micros=cost, unresolved_event_count=unresolved,
            total_revenue_micros=10_000_000, gross_margin_micros=1,
            margin_percentage=10)

    def _spikes(self):
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import ProviderCostSpike

        return OutboxEvent.objects.filter(
            event_type=ProviderCostSpike.EVENT_TYPE)

    def test_a_whole_previous_cost_still_raises_the_alarm(self):
        """The control. Without it, "no event" proves nothing at all."""
        from apps.subscriptions.economics.services import MarginService

        self._snapshot(self.prev_start, cost=1_000_000)
        econ = self._snapshot(self.this_start, cost=10_000_000)
        MarginService.evaluate_and_emit(econ)
        assert self._spikes().count() == 1

    def test_a_previous_cost_that_excluded_something_raises_nothing(self):
        from apps.subscriptions.economics.services import MarginService

        prev = self._snapshot(self.prev_start, cost=1_000_000, unresolved=1)
        econ = self._snapshot(self.this_start, cost=10_000_000)
        MarginService.evaluate_and_emit(econ)
        assert self._spikes().count() == 0
        # AND THE WINDOW SAYS IT IS INCOMPLETE, which is the other half of the
        # ruling and the half a silence would not deliver. The declined
        # comparison is not announced — an event saying "I did not compare"
        # would be a signal nobody asked for — so what a reader has instead is
        # the previous window's own snapshot, which states what its cost total
        # left out on the surface that still serves it: the alerting list. ⚠ The
        # three REPORTING reads that also served it are gone (#501) — a
        # reporting surface may not take a margin figure off this record — and
        # they say the same thing from the one economic query, per bucket. That
        # row said nothing before #327; it is the report.
        prev.refresh_from_db()
        assert prev.unresolved_event_count == 1

    def test_a_spike_off_a_partial_current_cost_says_what_it_excluded(self):
        """This one still fires, and the direction is why.

        A partial CURRENT cost understates the rise, so a comparison that
        crosses the threshold has crossed it on a floor — the real rise is at
        least that steep. The alarm is sound; what the consumer needs is to
        know the number under it is a lower bound.
        """
        from apps.subscriptions.economics.services import MarginService

        self._snapshot(self.prev_start, cost=1_000_000)
        econ = self._snapshot(self.this_start, cost=10_000_000, unresolved=2)
        MarginService.evaluate_and_emit(econ)
        payload = self._spikes().get().payload
        assert payload["current_provider_cost_micros"] == 10_000_000
        assert payload[UNRESOLVED_EVENT_COUNT_KEY] == 2


@pytest.mark.django_db
class TestStopsAndBreachesAddsUpWhatItHas:
    """The composition layer's two Python sums, which would have RAISED.

    ``sum(e["provider_cost_micros"] for e in events)`` over a `None` is a
    `TypeError`, not a wrong number — a 500 on a report about money already
    spent, and reachable the moment a tenant's cost rates fall behind their
    traffic. The fix is the same pair as everywhere else: what the report can
    add up, and how many events it could not. The per-customer report that
    first carried the two sums retired in #466; its successor itemises the
    same events under the ceiling's row (`_itemised`) and totals them per
    family (`_totals`), and both are held here.
    """

    def setup_method(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        with transaction.atomic():
            self.unit = TaskService.create_task(
                tenant=self.tenant, customer=self.customer,
                balance_snapshot_micros=0, task_cogs_ceiling_micros=1)
            # Stopped on its own ceiling through the one writer of `killed`,
            # so the row carries the control the flip stamps (family, id,
            # mechanism) and the ceiling's read contract selects it.
            TaskService.kill_task(
                self.unit.id, reason=reasons.TASK_COGS_CEILING,
                tenant_id=self.tenant.id, customer_id=self.customer.id)
        self.unit.refresh_from_db()
        ctx = [{"limit": reasons.TASK_COGS_CEILING, "stop_scope": "task",
                "task_id": str(self.unit.id),
                "tripped_at": self.unit.completed_at.isoformat()}]
        _posting(self.tenant, self.customer, "k1",
                 status=COSTING_STATUS_KNOWN, stop_context=ctx)
        _posting(self.tenant, self.customer, "k2",
                 status=COSTING_STATUS_UNRESOLVED, stop_context=ctx)

    def _report(self):
        from api.v1.spend_control_endpoints import build_stops_and_breaches

        until = timezone.now() + timedelta(seconds=1)
        return build_stops_and_breaches(
            self.tenant, since=until - timedelta(days=1), until=until,
            customer=self.customer)

    def test_the_episode_total_is_the_part_the_report_could_add_up(self):
        row, = self._report().rows
        assert row.itemised.event_count == 2
        assert row.itemised.provider_cost_micros == KNOWN_COST_MICROS
        assert getattr(row.itemised, UNRESOLVED_EVENT_COUNT_KEY) == 1

    def test_the_per_family_totals_carry_the_same_count(self):
        totals, = self._report().totals
        assert totals.control_family == row_family_of(self.unit)
        assert totals.provider_cost_micros == KNOWN_COST_MICROS
        assert getattr(totals, UNRESOLVED_EVENT_COUNT_KEY) == 1


def row_family_of(unit):
    """The family the kill stamped on the unit — read off the row, by the
    kernel's own key, so the assertion names no family literal."""
    from apps.platform.work.models import STOP_CONTROL_FAMILY_KEY

    return unit.metadata[STOP_CONTROL_FAMILY_KEY]


@pytest.mark.django_db
class TestTheRewardLedgerSaysWhatItCouldNotRead:
    """Referrals: a reward computed from costs, some of which are unknown.

    Its per-event reader already skipped a `None` deliberately — the reward for
    an event whose cost UBB has not learned falls back to the estimate, which
    is a decision and a defensible one. What it did not do was say how often
    that happened, so a period reconciled entirely from estimates was written
    down the same way as one reconciled from figures.
    """

    def setup_method(self):
        from apps.referrals.models import Referral, ReferralProgram, Referrer

        self.tenant = Tenant.objects.create(name="T", products=["metering", "referrals"])
        self.referrer_customer = Customer.objects.create(
            tenant=self.tenant, external_id="ref")
        self.referred = Customer.objects.create(
            tenant=self.tenant, external_id="c1")
        ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="profit_share", reward_value="0.1",
            estimated_cost_percentage="0.3", status="active")
        referrer = Referrer.objects.create(
            tenant=self.tenant, customer=self.referrer_customer,
            referral_code="CODE", referral_link_token="tok")
        self.referral = Referral.objects.create(
            tenant=self.tenant, referrer=referrer,
            referred_customer=self.referred, referral_code_used="CODE",
            status="active", snapshot_reward_type="profit_share",
            snapshot_reward_value="0.1",
            snapshot_estimated_cost_percentage="0.3")
        self.today = timezone.now().date()

    def _reconcile(self):
        from apps.referrals.rewards.reconciliation import reconcile_referral

        return reconcile_referral(self.referral, self.today,
                                  self.today + timedelta(days=1))

    def test_the_ledger_counts_the_costs_it_had_to_estimate_around(self):
        _posting(self.tenant, self.referred, "k1", status=COSTING_STATUS_KNOWN)
        _posting(self.tenant, self.referred, "k2",
                 status=COSTING_STATUS_UNRESOLVED)
        entry = self._reconcile()
        assert entry.raw_cost_micros == KNOWN_COST_MICROS
        assert entry.unresolved_event_count == 1

    def test_a_cost_that_does_not_exist_is_not_a_cost_it_could_not_read(self):
        _posting(self.tenant, self.referred, "k1", status=COSTING_STATUS_KNOWN)
        _posting(self.tenant, self.referred, "k2",
                 status=COSTING_STATUS_NOT_APPLICABLE)
        assert self._reconcile().unresolved_event_count == 0
