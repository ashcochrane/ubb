"""A recording acknowledgement that carries a stop says which mechanism applied
it, the bound it was measured against and the amount measured (#569).

Three fields join `stop`, `stop_reason` and `stop_scope` on every
acknowledgement — the single route's and every batch item's — and each is
always present, null where it does not apply, and never 0 for "does not
apply":

    stop_reason          trigger_source             bound                     measured
    task_cogs_ceiling    usage_ingest               the governing unit's      its supplier cost
                                                    pinned ceiling            (COGS) total
    customer_spend_pool  the episode's opener       the Pool's stop line      month-to-date
                                                                              billed charges
    hard_floor           the episode's opener       the floor as a balance    the wallet balance
                                                    (0 is a real floor)
    task_not_active      null                       null                      null
    (no stop)            null                       null                      null

The figures are the bound the stop names AS RESOLVED WHEN THE STOP WAS
ESTABLISHED and the amount measured against it at that moment. For a
customer-wide stop that was already standing when a report arrived, they
are the stop episode's opening facts — never today's counter, Pool or
configuration — and `trigger_source` is the mechanism that opened the
episode: this recording's live debit or a usage report's drawdown
(`usage_ingest`), the hourly reconcile (`enforcement_patrol`), or the
drawdown of a delivered fixed-price unit's Charge (`charge_projection`).

Every case runs on both recording routes: the shape is a mixin, bound twice,
and each binding says how its route records one report (#609's pattern).
"""
import datetime
import json
from pathlib import Path
from unittest import mock

from django.db import DatabaseError
from django.test import SimpleTestCase
from django.utils import timezone
from pydantic import ValidationError

from api.v1.schemas import RecordUsageResponse, UsageBatchItemResponse
from apps.billing.gating.models import CustomerSpendPool
from apps.billing.gating.services.live_counter import Door
from apps.billing.gating.services.stop_signal_service import StopSignalService
from apps.billing.gating.tasks import (
    reconcile_customer_spend_pool_counters, reconcile_live_ledgers)
from apps.billing.gating.tests.test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid import (
    DOORBELL, SOLD_WHOLE, THE_AGREED_PRICE, PoolTestBase, ThroughABatchItem,
    ThroughTheSingleRoute)
from apps.billing.wallets.models import CustomerBillingProfile, Wallet
from apps.metering.pricing.tests._helpers import a_price_for_whole_work
from apps.platform.work import reasons
from apps.platform.work.models import TaskType
from core.vocabulary import (
    CUSTOMER_BILLING_MODE_POSTPAID,
    PRICING_MODE_FIXED, PRICING_STATUS_KNOWN, SPEND_POOL_ENFORCE_MODE_BLOCKING,
    TASK_OUTCOME_DELIVERED, TASK_TYPE_KIND_TASK, TRIGGER_SOURCE_CHARGE_PROJECTION,
    TRIGGER_SOURCE_ENFORCEMENT_PATROL, TRIGGER_SOURCE_USAGE_INGEST)

#: Every stop fact an acknowledgement carries, in the order the body sends
#: them. Each is ALWAYS present, so an assertion reads the key, never `.get`.
STOP_FACTS = ("stop", "stop_reason", "stop_scope", "trigger_source",
              "stop_bound_micros", "stop_measured_micros")

#: The three #569 adds: how the stop was applied, and on what figures.
HOW_IT_WAS_APPLIED = STOP_FACTS[3:]

#: The committed contract, at the git root — `ubb/openapi/v1.json`.
CONTRACT = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"


class ReadsAStopAcknowledgement:
    """What a case here and in the replay module needs to record a report and
    read its stop facts; no cases of its own. A binding supplies
    `_through_the_route`."""

    # -- one recording ------------------------------------------------------

    def _report(self, customer=None, *, bills=1_000, **fields):
        """One usage report for `customer` (the tenant's standalone customer
        by default), through the bound route: the acknowledgement as a
        caller reads it."""
        return self._through_the_route(customer or self.customer,
                                       bills=bills, **fields)

    # -- what an acknowledgement says ---------------------------------------

    def _facts(self, ack):
        for key in STOP_FACTS:
            self.assertIn(key, ack)   # present, never omitted
        return {key: ack[key] for key in STOP_FACTS}

    def _assert_stopped(self, ack, reason, scope, trigger, *, bound, measured):
        self.assertEqual(self._facts(ack), {
            "stop": True, "stop_reason": reason, "stop_scope": scope,
            "trigger_source": trigger, "stop_bound_micros": bound,
            "stop_measured_micros": measured}, ack)

    def _assert_not_stopped(self, ack):
        self.assertEqual(self._facts(ack), {
            "stop": False, "stop_reason": None, "stop_scope": None,
            "trigger_source": None, "stop_bound_micros": None,
            "stop_measured_micros": None}, ack)

    # -- fixtures -----------------------------------------------------------

    def _pool_line(self, customer, *, cap, pct):
        """A blocking Pool whose stop line (`cap * pct // 100`) differs from
        its cap, so a test can tell the line from the cap."""
        return CustomerSpendPool.objects.create(
            tenant=self.tenant, customer=customer, cap_micros=cap,
            enforce_mode=SPEND_POOL_ENFORCE_MODE_BLOCKING, hard_stop_pct=pct)

    def _wallet(self, customer, balance, *, floor=None):
        Wallet.objects.filter(customer=customer).update(balance_micros=balance)
        if floor is not None:
            CustomerBillingProfile.objects.create(
                customer=customer, min_balance_micros=floor)

    def _the_live_lane_is_off(self):
        self.tenant.live_counter_maintenance_enabled = False
        self.tenant.save(update_fields=["live_counter_maintenance_enabled"])


class AStopAcknowledgementSaysWhatStoppedIt(ReadsAStopAcknowledgement):
    """The shared shape. Each binding below runs every case on one route and
    supplies `_through_the_route`, the one thing the two routes differ in."""

    # -- a unit's ceiling, crossed by this report ---------------------------

    def test_a_ceiling_this_report_crosses_names_its_bound_and_the_units_cogs(self):
        unit = self._unit(task_cogs_ceiling_micros=5_000_000)
        self._assert_not_stopped(
            self._report(task_id=unit, provider_cost_micros=3_000_000))

        ack = self._report(task_id=unit, provider_cost_micros=2_500_000)

        self._assert_stopped(ack, reasons.TASK_COGS_CEILING, "task",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=5_000_000, measured=5_500_000)

    def test_contained_work_crossing_its_own_ceiling_carries_its_own_figures(self):
        parent = self._unit(task_cogs_ceiling_micros=20_000_000)
        contained = self._unit(parent_task_id=parent,
                               task_cogs_ceiling_micros=4_000_000)

        ack = self._report(task_id=contained, provider_cost_micros=4_200_000)

        self._assert_stopped(ack, reasons.TASK_COGS_CEILING, "subtask",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=4_000_000, measured=4_200_000)

    def test_a_task_scoped_stop_on_contained_work_carries_the_parents_figures(self):
        """Both ceilings cross on the contained unit's report; the widest
        scope wins the scalar slot, and the figures follow the scope — the
        PARENT's ceiling and rolled-up total, never the contained unit's
        own (5,000,000 / 5,100,000)."""
        parent = self._unit(task_cogs_ceiling_micros=6_000_000)
        contained = self._unit(parent_task_id=parent,
                               task_cogs_ceiling_micros=5_000_000)
        self._report(task_id=parent, provider_cost_micros=3_000_000)

        ack = self._report(task_id=contained, provider_cost_micros=5_100_000)

        self._assert_stopped(ack, reasons.TASK_COGS_CEILING, "task",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=6_000_000, measured=8_100_000)
        self.assertEqual(ack["parent_task_id"], parent)

    # -- the one verdict that is not a bound, and no stop -------------------

    def test_a_report_on_ended_work_names_no_mechanism_and_no_figures(self):
        unit = self._unit(task_cogs_ceiling_micros=1_000_000)
        self._report(task_id=unit, provider_cost_micros=1_000_000)  # ends it

        late = self._report(task_id=unit, provider_cost_micros=500)

        self._assert_stopped(late, reasons.TASK_NOT_ACTIVE, "task", None,
                             bound=None, measured=None)

    def test_a_report_on_ended_contained_work_names_its_own_altitude(self):
        parent = self._unit()
        contained = self._unit(parent_task_id=parent,
                               task_cogs_ceiling_micros=1_000_000)
        self._report(task_id=contained, provider_cost_micros=1_000_000)

        late = self._report(task_id=contained, provider_cost_micros=500)

        self._assert_stopped(late, reasons.TASK_NOT_ACTIVE, "subtask", None,
                             bound=None, measured=None)

    def test_no_stop_is_every_fact_null_and_present(self):
        self._assert_not_stopped(self._report())

    # -- a customer-wide stop this report's live debit opens -----------------

    def test_a_pool_this_report_crosses_names_its_stop_line_and_the_charges(self):
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._assert_not_stopped(self._report(bills=5_000_000))

        ack = self._report(bills=4_000_000)

        self._assert_stopped(ack, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)

    def test_a_floor_this_report_crosses_names_the_floor_as_a_balance(self):
        self._wallet(self.customer, 3_000_000, floor=1_000_000)

        ack = self._report(bills=4_500_000)

        self._assert_stopped(ack, reasons.HARD_FLOOR, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=-1_000_000, measured=-1_500_000)

    def test_a_real_zero_floor_is_published_as_zero(self):
        self._wallet(self.customer, 2_000_000)

        ack = self._report(bills=2_500_000)

        self._assert_stopped(ack, reasons.HARD_FLOOR, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=0, measured=-500_000)

    # -- a stop already standing: the episode's opener and its figures ------

    def test_a_later_report_carries_the_episodes_opening_figures(self):
        """The counter has moved on to 10,000,000; the acknowledgement says
        what the episode opened on."""
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._report(bills=9_000_000)

        later = self._report(bills=1_000_000)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)

    def test_a_later_report_keeps_the_opening_bound_after_the_pool_changes(self):
        """ADR-0019 §2: the bound is the one the episode OPENED on. The tenant lowers
        the Pool while the episode stands; a later report still names the
        stop line it opened on (8,000,000), not today's (3,000,000)."""
        pool = self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._report(bills=9_000_000)
        CustomerSpendPool.objects.filter(id=pool.id).update(
            cap_micros=6_000_000, hard_stop_pct=50)

        later = self._report(bills=1_000_000)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)

    def test_a_usage_reports_drawdown_opens_its_episode_as_usage_ingest(self):
        """With the live lane off the recording route detects nothing; the
        durable drawdown of THAT usage report opens the floor's episode, on
        the balance it drew down to."""
        self._the_live_lane_is_off()
        self._wallet(self.customer, 3_000_000)
        self._assert_not_stopped(self._report(bills=4_000_000))
        self._drain()

        later = self._report()

        self._assert_stopped(later, reasons.HARD_FLOOR, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=0, measured=-1_000_000)

    def test_the_hourly_reconcile_opens_its_episode_as_the_patrol(self):
        self._the_live_lane_is_off()
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._assert_not_stopped(self._report(bills=9_000_000))
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            reconcile_live_ledgers()

        later = self._report(bills=1_000_000)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_ENFORCEMENT_PATROL,
                             bound=8_000_000, measured=9_000_000)

    def test_a_flag_set_again_after_a_flush_says_how_the_episode_opened(self):
        """The patrol opened the floor's episode; Redis then lost the flag.
        The next report's live debit sets the flag afresh but loses the
        ledger's transition to the episode already open — so the flag is
        re-aligned to how THAT episode opened, never this report's crossing."""
        Wallet.objects.filter(customer=self.customer).update(
            balance_micros=-1_000_000)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            reconcile_live_ledgers()
        Door.delete_stop(self.customer.id)

        later = self._report(bills=1_000)

        self._assert_stopped(later, reasons.HARD_FLOOR, "customer",
                             TRIGGER_SOURCE_ENFORCEMENT_PATROL,
                             bound=0, measured=-1_000_000)

    def test_facts_a_failed_drive_left_on_the_flag_follow_the_ledger(self):
        """A pooled seat's drawdown found its own Pool line crossed, but the
        ledger drive RAISED, so the flag was set with no episode open and
        carries no facts — the failure path's window, which a report inside
        it acknowledges as it stands (ADR-0019, Consequences). The seat-level
        beat then opens the episode as the patrol, and the flag's facts are
        re-aligned to the ledger's: later reports carry how the episode
        opened. Nothing else re-points a seat's flag, so only the
        re-alignment can repair it."""
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._report(self.seat1, bills=3_200_000)
        ledger_down = mock.patch.object(
            StopSignalService, "drive_stop",
            side_effect=DatabaseError("the ledger is unavailable"))
        with ledger_down:
            self._drain()
        self._assert_stopped(self._report(self.seat1),
                             reasons.CUSTOMER_SPEND_POOL, "customer", None,
                             bound=None, measured=None)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            reconcile_customer_spend_pool_counters()

        later = self._report(self.seat1)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_ENFORCEMENT_PATROL,
                             bound=3_000_000, measured=3_201_000)

    def test_a_charges_drawdown_opens_its_episode_as_the_charge_projection(self):
        """A delivered fixed-price unit's Charge reaches the money rails as
        one posting, which the live lane never sees; its drawdown crosses the
        customer's Pool, and the episode is the projection's — not a usage
        report's."""
        TaskType.objects.create(tenant=self.tenant, key=SOLD_WHOLE,
                                kind=TASK_TYPE_KIND_TASK,
                                pricing_mode=PRICING_MODE_FIXED, uncapped=True)
        a_price_for_whole_work(self.tenant, task_type=SOLD_WHOLE,
                               amount_micros=THE_AGREED_PRICE)
        self._pool_line(self.customer, cap=8_000_000, pct=90)
        unit = self._unit(task_type=SOLD_WHOLE)
        with mock.patch(DOORBELL), self.captureOnCommitCallbacks(execute=True):
            closed = self.http.post(
                f"/api/v1/tasks/{unit}/close",
                data=json.dumps({"outcome": TASK_OUTCOME_DELIVERED}),
                **self._headers())
        self.assertEqual(closed.status_code, 200, closed.content)
        self._drain()

        later = self._report()

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_CHARGE_PROJECTION,
                             bound=7_200_000, measured=THE_AGREED_PRICE)

    # -- ADR-0019 §7: a report the live debit does not count still hears the stop ----

    def test_a_report_that_costs_nothing_carries_the_standing_stop(self):
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._report(bills=9_000_000)

        nothing = self._report(bills=0)

        self.assertEqual(nothing["billed_cost_micros"], 0)
        self._assert_stopped(nothing, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)

    def test_a_report_ubb_cannot_price_carries_the_standing_stop(self):
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._report(bills=9_000_000)

        unpriced = self._report(measurements={})

        self.assertIsNone(unpriced["billed_cost_micros"])
        self.assertNotEqual(unpriced["pricing_status"], PRICING_STATUS_KNOWN)
        self._assert_stopped(unpriced, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)

    def test_a_pooled_seats_own_stop_reaches_a_report_that_costs_nothing(self):
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._report(self.seat1, bills=3_200_000)
        self._drain()

        nothing = self._report(self.seat1, bills=0)

        self._assert_stopped(nothing, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=3_000_000, measured=3_200_000)
        self.biz.refresh_from_db()
        self.assertEqual(self.biz.status, "active")

    # -- ADR-0019 §4: two standing Pool lines, and whose figures are frozen ---------

    def test_both_levels_standing_name_the_business_line_and_its_figures(self):
        """The two lines carry identical words; only the figures can show
        which one was named. The business's (4,500,000 / 5,000,000) differ
        from the seat's own (3,000,000 / 3,200,000)."""
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._pool_line(self.biz, cap=5_000_000, pct=90)
        self._report(self.seat1, bills=3_200_000)
        self._drain()                                  # the seat's own line
        self._report(self.seat1, bills=1_800_000)      # the business's line

        later = self._report(self.seat1)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=4_500_000, measured=5_000_000)

    def test_the_seats_own_line_alone_is_named_with_its_figures(self):
        self._a_pooled_business_with_two_seats()
        self._default_pool(3_000_000)
        self._pool_line(self.biz, cap=50_000_000, pct=90)
        self._report(self.seat1, bills=3_200_000)
        self._drain()

        later = self._report(self.seat1)

        self._assert_stopped(later, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=3_000_000, measured=3_200_000)
        self._assert_not_stopped(self._report(self.seat2))


class ABackDatedPostpaidReportHearsTheStandingStop(ReadsAStopAcknowledgement):
    """The third report the live debit does not count (ADR-0019 §7): a
    postpaid report back-dated into an earlier month moves no counter (I9) —
    and still reads the standing stop, its acknowledgement kept for good."""

    def test_a_report_back_dated_into_last_month_carries_the_standing_stop(self):
        self.tenant.backfill_window_days = 60
        self.tenant.save(update_fields=["backfill_window_days"])
        self._pool_line(self.customer, cap=10_000_000, pct=80)
        self._report(bills=9_000_000)
        last_month = timezone.now().replace(day=1) - datetime.timedelta(days=2)

        back_dated = self._report(bills=1_000_000,
                                  effective_at=last_month.isoformat())

        self._assert_stopped(back_dated, reasons.CUSTOMER_SPEND_POOL, "customer",
                             TRIGGER_SOURCE_USAGE_INGEST,
                             bound=8_000_000, measured=9_000_000)
        self.assertEqual(Door.spend(self.customer.id), 9_000_000)


class ABackDatedPostpaidReportOnTheSingleRouteTest(
        ABackDatedPostpaidReportHearsTheStandingStop, ThroughTheSingleRoute,
        PoolTestBase):
    MODE = CUSTOMER_BILLING_MODE_POSTPAID


class ABackDatedPostpaidReportOnABatchItemTest(
        ABackDatedPostpaidReportHearsTheStandingStop, ThroughABatchItem,
        PoolTestBase):
    MODE = CUSTOMER_BILLING_MODE_POSTPAID


class AStopAcknowledgementOnTheSingleRouteTest(
        AStopAcknowledgementSaysWhatStoppedIt, ThroughTheSingleRoute,
        PoolTestBase):
    pass


class AStopAcknowledgementOnABatchItemTest(
        AStopAcknowledgementSaysWhatStoppedIt, ThroughABatchItem, PoolTestBase):
    pass


class TheThreeAreRequiredKeysWhoseValuesMayBeNullTest(SimpleTestCase):
    """The owner's review of #612: `trigger_source`, `stop_bound_micros` and
    `stop_measured_micros` are REQUIRED AND NULLABLE on both recording
    responses — in the class and in the committed contract the SDK is
    generated from. Null says "does not apply"; a missing key would be a
    third state, the server not sending what it promised, and the contract
    leaves none. The two figures are SIGNED: a hard floor's bound and measure
    sit below zero (`test_a_floor_this_report_crosses_names_the_floor_as_a_balance`
    sends -1,000,000 and -1,500,000 through both routes), so no minimum
    belongs on either."""

    RESPONSES = (RecordUsageResponse, UsageBatchItemResponse)

    def test_each_is_required_in_the_class(self):
        for model in self.RESPONSES:
            for field in HOW_IT_WAS_APPLIED:
                with self.subTest(model=model.__name__, field=field):
                    self.assertTrue(model.model_fields[field].is_required())

    def test_each_is_required_and_nullable_in_the_contract_with_no_minimum(self):
        schemas = json.loads(CONTRACT.read_text(encoding="utf-8"))[
            "components"]["schemas"]
        for model in self.RESPONSES:
            schema = schemas[model.__name__]
            for field in HOW_IT_WAS_APPLIED:
                with self.subTest(model=model.__name__, field=field):
                    self.assertIn(field, schema["required"])
                    branches = schema["properties"][field]["anyOf"]
                    self.assertIn({"type": "null"}, branches)
                    self.assertNotIn("default", schema["properties"][field])
                    for branch in branches:
                        self.assertFalse(
                            {"minimum", "exclusiveMinimum"} & branch.keys(),
                            branch)

    def test_a_body_without_one_is_refused_and_a_negative_figure_is_kept(self):
        bodies = {
            RecordUsageResponse: {"event_id": "e1", "suspended": False,
                                  "costing_status": "known",
                                  "pricing_status": "known"},
            # A rejected item recorded nothing; it carries the three as null.
            UsageBatchItemResponse: {"accepted": False, "code": "refused"},
        }
        nothing = dict.fromkeys(HOW_IT_WAS_APPLIED)
        for model, body in bodies.items():
            for missing in HOW_IT_WAS_APPLIED:
                with self.subTest(model=model.__name__, missing=missing):
                    without = {**body, **nothing}
                    del without[missing]
                    with self.assertRaises(ValidationError):
                        model.model_validate(without)
            below = model.model_validate({
                **body, "trigger_source": TRIGGER_SOURCE_USAGE_INGEST,
                "stop_bound_micros": -1_000_000,
                "stop_measured_micros": -1_500_000})
            self.assertEqual(
                (below.stop_bound_micros, below.stop_measured_micros),
                (-1_000_000, -1_500_000))
