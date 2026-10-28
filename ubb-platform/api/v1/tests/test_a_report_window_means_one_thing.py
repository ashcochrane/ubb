"""Every calendar-date report route reads its window one way (#542, #543,
#514; W5 rulings 1–6).

Six routes take a pair of calendar dates. Before W5 five of them disagreed: two read
`end_date` as exclusive, two dropped a lone date or bounded only a supplied
pair, and one answered all of history when no date was sent. Each now resolves
its window through `core/report_windows.py`, and this module asks every one of
them the same questions through its public route:

- no dates is the UTC month to date;
- a lone start date runs to today, and a lone end date starts on the first of
  its own month — neither is ever dropped;
- the end date is INCLUSIVE: a fact late on it is in, a fact at the next UTC
  midnight is out;
- 366 calendar dates are answered and 367 refused, a window that runs
  backwards is refused, and a lone start date long ago is refused rather than
  answered unbounded;
- every route publishes the one window description, and every date parameter
  says it is inclusive.

⚠ **ONE PROBE PER ROUTE, AND EACH READS WHICH FACTS COUNTED, NOT A COUNT.**
Every fact carries an amount that is a distinct power of two, so the one figure
a route answers decodes into exactly the set of facts its window took in — a
window off by a day on either end names the fact it gained or lost. The clock
is frozen mid-month (`NOW`), because a window test that can fail on the first
of a month or near UTC midnight is a defect (#589, #560).
"""
from datetime import date, datetime, timedelta, timezone as dt_timezone
from unittest import mock

from django.test import Client, TestCase

from api.v1.tests._helpers import a_tenant, measure_of
from api.v1.tests.test_the_one_economic_query import describe
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.work.models import Task
from apps.referrals.models import ReferralProgram, Referral, Referrer
from apps.referrals.rewards.models import ReferralRewardLedger
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from core.report_windows import (
    END_DATE_DESCRIPTION, START_DATE_DESCRIPTION, report_window_description)
from core.widget_auth import create_widget_token
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_KNOWN,
    PRICING_STATUS_KNOWN, RECOGNITION_METHOD_ON_RECEIPT, TASK_STATUS_COMPLETED)

UTC = dt_timezone.utc
#: The frozen clock: the 18th of March, mid-afternoon UTC. Today is the 18th.
NOW = datetime(2026, 3, 18, 15, 30, tzinfo=UTC)

#: The facts every probe seeds, each at an instant chosen to sit on one side of
#: a boundary some question draws. A date-only probe keeps the instant's date.
FACTS = {
    "feb_28_late": datetime(2026, 2, 28, 23, 59, 59, 999999, tzinfo=UTC),
    "mar_01_first_instant": datetime(2026, 3, 1, 0, 0, tzinfo=UTC),
    "mar_10_late": datetime(2026, 3, 10, 23, 59, 59, 999999, tzinfo=UTC),
    "mar_11_first_instant": datetime(2026, 3, 11, 0, 0, tzinfo=UTC),
    "mar_18_today": datetime(2026, 3, 18, 9, 0, tzinfo=UTC),
    "mar_19_tomorrow": datetime(2026, 3, 19, 0, 0, tzinfo=UTC),
}
#: A distinct power of two per fact, so a sum decodes into the facts behind it.
BIT = {label: 2 ** (10 + position) for position, label in enumerate(FACTS)}


def _decoded(total):
    return {label for label, bit in BIT.items() if total & bit}


class _Probe:
    """One report route: how to seed a dated fact, and what the answer counted."""

    path = None
    start_name, end_name = "start_date", "end_date"

    def __init__(self, case):
        self.case = case

    def ask(self, **params):
        query = {name: value.isoformat() for name, value in params.items()}
        response = Client().get(self.url(), query,
                                HTTP_AUTHORIZATION=f"Bearer {self.case.key}")
        return response

    def url(self):
        return self.path

    def echoed(self, body):
        """The window the answer says it applied, where the route echoes one."""
        return None


class EconomicQuery(_Probe):
    path = "/api/v1/metering/analytics/economics"

    def seed(self, label, instant):
        Posting.objects.create(
            tenant=self.case.tenant, customer=self.case.customer,
            idempotency_key=f"econ-{label}", effective_at=instant,
            provider="openai", event_type="chat.completion",
            provider_cost_micros=BIT[label],
            costing_status=COSTING_STATUS_KNOWN, billed_cost_micros=0,
            pricing_status=PRICING_STATUS_KNOWN)

    def ask(self, **params):
        query = {name: value.isoformat() for name, value in params.items()}
        query["measures"] = ANALYTICS_MEASURE_SUPPLIER_COGS
        # Its own customer only: the business probe's seat posts in this tenant.
        query["customer_id"] = str(self.case.customer.id)
        return Client().get(self.path, query,
                            HTTP_AUTHORIZATION=f"Bearer {self.case.key}")

    def counted(self, body):
        return _decoded(measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
                        ["amount_micros"] or 0)

    def echoed(self, body):
        return body["period_start"], body["period_end"]


class TaskAnalytics(_Probe):
    path = "/api/v1/metering/analytics/tasks"

    def seed(self, label, instant):
        unit = Task.objects.create(
            tenant=self.case.tenant, customer=self.case.customer,
            balance_snapshot_micros=0, task_type="report_window",
            status=TASK_STATUS_COMPLETED, total_provider_cost_micros=BIT[label],
            recorded_events=1)
        Task.objects.filter(id=unit.id).update(created_at=instant)

    def counted(self, body):
        return _decoded(sum(row["total_provider_cost_micros"]
                            for row in body["rows"]))


class SuppliedRevenue(_Probe):
    def url(self):
        return (f"/api/v1/margin/customers/{self.case.customer.id}"
                f"/supplied-revenue")

    def seed(self, label, instant):
        TenantSuppliedRevenue.objects.create(
            tenant=self.case.tenant, customer=self.case.customer,
            amount_micros=BIT[label], currency="usd",
            period_start=instant.date(), period_end=None,
            recognition_method=RECOGNITION_METHOD_ON_RECEIPT,
            source_reference=label)

    def counted(self, body):
        return {record["source_reference"] for record in body["records"]}

    def echoed(self, body):
        return body["window"]["start"], body["window"]["end"]


class BusinessRollup(_Probe):
    def url(self):
        return f"/api/v1/margin/business/{self.case.business.external_id}"

    def seed(self, label, instant):
        Posting.objects.create(
            tenant=self.case.tenant, customer=self.case.seat,
            idempotency_key=f"seat-{label}", effective_at=instant,
            provider="openai", event_type="chat.completion",
            provider_cost_micros=BIT[label],
            costing_status=COSTING_STATUS_KNOWN, billed_cost_micros=0,
            pricing_status=PRICING_STATUS_KNOWN)

    def counted(self, body):
        return _decoded(body["totals"]["provider_cost_micros"])


class ReferralEarnings(_Probe):
    path = "/api/v1/referrals/analytics/earnings"
    start_name, end_name = "period_start", "period_end"

    def ask(self, start_date=None, end_date=None):
        query = {}
        if start_date is not None:
            query["period_start"] = start_date.isoformat()
        if end_date is not None:
            query["period_end"] = end_date.isoformat()
        return Client().get(self.path, query,
                            HTTP_AUTHORIZATION=f"Bearer {self.case.key}")

    def seed(self, label, instant):
        # A ledger period one day long, so it overlaps a window exactly when
        # its day is inside it.
        ReferralRewardLedger.objects.create(
            referral=self.case.referral, period_start=instant.date(),
            period_end=instant.date(), referred_spend_micros=0,
            reward_micros=BIT[label], calculation_method="actual_cost")

    def counted(self, body):
        return _decoded(body["total_earned_micros"])

    def echoed(self, body):
        return body["period_start"], body["period_end"]


class WidgetUsage(_Probe):
    """The end customer's own usage summary (#561), asked with a widget token
    for a customer of its own, so its revenue decodes the facts it seeded."""

    path = "/api/v1/me/economics"

    def ask(self, **params):
        query = {name: value.isoformat() for name, value in params.items()}
        token = create_widget_token(self.case.tenant.widget_secret,
                                    str(self.case.widget_customer.id),
                                    str(self.case.tenant.id))
        return Client().get(self.path, query,
                            HTTP_AUTHORIZATION=f"Bearer {token}")

    def seed(self, label, instant):
        Posting.objects.create(
            tenant=self.case.tenant, customer=self.case.widget_customer,
            idempotency_key=f"widget-{label}", effective_at=instant,
            provider="openai", event_type="chat.completion",
            provider_cost_micros=0, costing_status=COSTING_STATUS_KNOWN,
            billed_cost_micros=BIT[label], pricing_status=PRICING_STATUS_KNOWN)

    def counted(self, body):
        return _decoded(body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"]
                        or 0)

    def echoed(self, body):
        return body["period_start"], body["period_end"]


PROBES = (EconomicQuery, TaskAnalytics, SuppliedRevenue, BusinessRollup,
          ReferralEarnings, WidgetUsage)


class EveryReportRouteReadsItsWindowOneWayTest(TestCase):

    def setUp(self):
        clock = mock.patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.tenant, self.key = a_tenant(products=("metering", "referrals"))
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="allocated")
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=self.business)
        self.widget_customer = Customer.objects.create(tenant=self.tenant,
                                                       external_id="widget")
        ReferralProgram.objects.create(tenant=self.tenant,
                                       reward_type="revenue_share",
                                       reward_value=0.10)
        referrer = Referrer.objects.create(tenant=self.tenant,
                                           customer=self.customer)
        referred = Customer.objects.create(tenant=self.tenant,
                                           external_id="referred")
        self.referral = Referral.objects.create(
            tenant=self.tenant, referrer=referrer, referred_customer=referred,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type="revenue_share", snapshot_reward_value=0.10)
        self.probes = [probe(self) for probe in PROBES]
        for probe in self.probes:
            for label, instant in FACTS.items():
                probe.seed(label, instant)

    def _answers(self, **params):
        for probe in self.probes:
            response = probe.ask(**params)
            with self.subTest(route=type(probe).__name__):
                self.assertEqual(response.status_code, 200, response.content)
            yield probe, response.json()

    def _assert_window(self, expected_facts, expected_echo, **params):
        for probe, body in self._answers(**params):
            with self.subTest(route=type(probe).__name__):
                self.assertEqual(probe.counted(body), expected_facts)
                if probe.echoed(body) is not None:
                    self.assertEqual(probe.echoed(body),
                                     tuple(day.isoformat()
                                           for day in expected_echo))

    def test_no_dates_is_the_utc_month_to_date(self):
        self._assert_window(
            {"mar_01_first_instant", "mar_10_late", "mar_11_first_instant",
             "mar_18_today"},
            (date(2026, 3, 1), date(2026, 3, 18)))

    def test_a_lone_start_date_runs_to_today(self):
        self._assert_window(
            {"feb_28_late", "mar_01_first_instant", "mar_10_late",
             "mar_11_first_instant", "mar_18_today"},
            (date(2026, 2, 28), date(2026, 3, 18)),
            start_date=date(2026, 2, 28))

    def test_a_lone_end_date_starts_on_the_first_of_its_month(self):
        self._assert_window(
            {"mar_01_first_instant", "mar_10_late"},
            (date(2026, 3, 1), date(2026, 3, 10)),
            end_date=date(2026, 3, 10))

    def test_a_lone_end_date_in_an_earlier_month_starts_on_that_months_first(self):
        """Its OWN month, never today's: a window from the first of March to
        the end of February would run backwards."""
        self._assert_window(
            {"feb_28_late"}, (date(2026, 2, 1), date(2026, 2, 28)),
            end_date=date(2026, 2, 28))

    def test_the_end_date_is_inclusive_and_the_next_midnight_is_not(self):
        self._assert_window(
            {"feb_28_late", "mar_01_first_instant", "mar_10_late"},
            (date(2026, 2, 28), date(2026, 3, 10)),
            start_date=date(2026, 2, 28), end_date=date(2026, 3, 10))

    def test_one_date_alone_is_a_window_of_one_day(self):
        self._assert_window(
            {"mar_10_late"}, (date(2026, 3, 10), date(2026, 3, 10)),
            start_date=date(2026, 3, 10), end_date=date(2026, 3, 10))

    def test_366_calendar_dates_are_answered(self):
        for probe in self.probes:
            response = probe.ask(start_date=date(2024, 1, 1),
                                 end_date=date(2024, 12, 31))
            with self.subTest(route=type(probe).__name__):
                self.assertEqual(response.status_code, 200, response.content)

    def _assert_refused(self, **params):
        for probe in self.probes:
            response = probe.ask(**params)
            with self.subTest(route=type(probe).__name__):
                self.assertEqual(response.status_code, 422, response.content)
                self.assertEqual(response.json()["code"], "validation_error")
                yield probe, response.json()["detail"]

    def test_367_calendar_dates_are_refused(self):
        for probe, detail in self._assert_refused(start_date=date(2024, 1, 1),
                                                  end_date=date(2025, 1, 1)):
            self.assertIn("at most 366 calendar dates", detail)

    def test_a_window_that_runs_backwards_is_refused(self):
        for probe, detail in self._assert_refused(start_date=date(2026, 3, 10),
                                                  end_date=date(2026, 3, 9)):
            self.assertEqual(
                detail, f"{probe.start_name} must not fall after {probe.end_name}")

    def test_a_lone_start_date_after_today_is_refused(self):
        list(self._assert_refused(start_date=date(2026, 3, 19)))

    def test_a_lone_start_date_long_ago_is_refused_never_answered_unbounded(self):
        """#542's hole: a lone date used to escape the ceiling on one route and
        be silently dropped on two others. Resolved first, it is a window of
        twenty-six years, and the ceiling refuses it."""
        for probe, detail in self._assert_refused(start_date=date(2000, 1, 1)):
            self.assertIn("at most 366 calendar dates", detail)


class AnHourlyQuestionKeepsTheTighterCeilingTest(TestCase):

    def setUp(self):
        self.tenant, self.key = a_tenant()

    def _ask(self, start, end):
        return Client().get(EconomicQuery.path, {
            "measures": ANALYTICS_MEASURE_SUPPLIER_COGS, "bucket": "hour",
            "start_date": start.isoformat(), "end_date": end.isoformat()},
            HTTP_AUTHORIZATION=f"Bearer {self.key}")

    def test_92_calendar_dates_are_answered_and_93_refused(self):
        opens = date(2026, 1, 1)
        answered = self._ask(opens, opens + timedelta(days=91))
        refused = self._ask(opens, opens + timedelta(days=92))
        self.assertEqual(answered.status_code, 200, answered.content)
        self.assertEqual(refused.status_code, 422, refused.content)
        self.assertIn("an hourly report window spans at most 92 calendar dates",
                      refused.json()["detail"])


class EveryReportRoutePublishesTheOneWindowDescriptionTest(TestCase):
    """#514 and #543: every calendar-date report says, in its published
    description, that both dates are inclusive, how many dates one request may
    span and how longer history is read; every date parameter says it is
    inclusive."""

    ROUTES = {
        "/metering/analytics/economics": ("start_date", "end_date"),
        "/metering/analytics/tasks": ("start_date", "end_date"),
        "/margin/customers/{customer_id}/supplied-revenue":
            ("start_date", "end_date"),
        "/margin/business/{external_id}": ("start_date", "end_date"),
        "/referrals/analytics/earnings": ("period_start", "period_end"),
        "/me/economics": ("start_date", "end_date"),
    }

    def test_each_route_states_the_window(self):
        for path, names in self.ROUTES.items():
            with self.subTest(path=path):
                self.assertIn(report_window_description(*names), describe(path))

    def test_each_date_parameter_says_it_is_inclusive(self):
        from api.v1.api import api

        document = api.get_openapi_schema()
        for path, (start, end) in self.ROUTES.items():
            (key,) = [key for key in document["paths"] if key.endswith(path)]
            published = {parameter["name"]: parameter.get("description")
                         for parameter in document["paths"][key]["get"]
                         ["parameters"]}
            with self.subTest(path=path):
                self.assertEqual(published[start], START_DATE_DESCRIPTION)
                self.assertEqual(published[end], END_DATE_DESCRIPTION)
