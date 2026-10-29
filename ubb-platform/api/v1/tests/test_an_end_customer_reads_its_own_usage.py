"""An end customer reads its own usage through the widget (#561; W5 ruling 17).

`GET /api/v1/me/economics` restores what `/me/usage-summary`'s deletion took
from widget holders (#501), over the one economic query and through a response
type the `/me` mount owns. Everything here goes through the public route with a
widget token:

- scope is the token's customer and nothing else: the route has no customer
  parameter at all, a stray one changes nothing, and two customers each read
  only their own;
- a business token reads the business's own usage — its seats are not added up;
- exactly two measures are published, `customer_revenue` and `recorded_events`,
  and nothing the tenant's answer carries beyond them reaches this one — not
  even a field later added to it;
- revenue states its basis and currency, and an unknown figure is null, never
  zero;
- the window is the shared calendar-date window;
- the metering product gates it.
"""
from datetime import date, datetime, timezone as dt_timezone
from unittest import mock

from django.test import Client, TestCase

from api.v1.api import api
from api.v1.tests._helpers import a_tenant
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.currency_policy import ECONOMIC_CURRENCY
from core.report_windows import report_window_description
from core.vocabulary import (
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_RECORDED_EVENTS,
    COSTING_STATUS_KNOWN, MEASURE_STATUS_INCOMPLETE, MEASURE_STATUS_KNOWN,
    USAGE_EVENT_KIND_METERED_USAGE, PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN,
    REVENUE_BASIS_RECORDED)
from core.widget_auth import create_widget_token
from apps.metering.usage.tests._helpers import a_posting

PATH = "/api/v1/me/economics"
NOW = datetime(2026, 3, 18, 15, 30, tzinfo=dt_timezone.utc)
IN_MARCH = datetime(2026, 3, 9, 12, 0, tzinfo=dt_timezone.utc)

#: The keys the widget answer is allowed to carry, and the keys of each measure.
ANSWER_KEYS = {"period_start", "period_end", "basis", "currency",
               ANALYTICS_MEASURE_CUSTOMER_REVENUE,
               ANALYTICS_MEASURE_RECORDED_EVENTS,
               "foreign_currency_subscription_count"}
REVENUE_KEYS = {"amount_micros", "status", "available_from"}
COUNT_KEYS = {"count", "status", "available_from"}


class _WidgetCase(TestCase):

    def setUp(self):
        clock = mock.patch("django.utils.timezone.now", return_value=NOW)
        clock.start()
        self.addCleanup(clock.stop)
        self.tenant, _ = a_tenant()
        self.alice = Customer.objects.create(tenant=self.tenant,
                                             external_id="alice")
        self.bob = Customer.objects.create(tenant=self.tenant,
                                           external_id="bob")

    def _posting(self, customer, key, *, billed, priced=True, at=IN_MARCH):
        return a_posting(
            tenant=self.tenant, customer=customer, idempotency_key=key,
            effective_at=at, kind=USAGE_EVENT_KIND_METERED_USAGE,
            provider="openai", event_type="chat.completion",
            provider_cost_micros=123, costing_status=COSTING_STATUS_KNOWN,
            billed_cost_micros=billed if priced else None,
            pricing_status=PRICING_STATUS_KNOWN if priced
            else PRICING_STATUS_UNKNOWN)

    def _token(self, customer):
        return create_widget_token(self.tenant.widget_secret,
                                   str(customer.id), str(self.tenant.id))

    def _ask(self, customer, **params):
        return Client().get(PATH, params,
                            HTTP_AUTHORIZATION=f"Bearer {self._token(customer)}")

    def _read(self, customer, **params):
        response = self._ask(customer, **params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class TheTokenIsTheOnlyScopeTest(_WidgetCase):

    def setUp(self):
        super().setUp()
        self._posting(self.alice, "a1", billed=100_000)
        self._posting(self.alice, "a2", billed=200_000)
        self._posting(self.bob, "b1", billed=7_000_000)

    def test_each_customer_reads_only_its_own_usage(self):
        alice = self._read(self.alice)
        bob = self._read(self.bob)

        self.assertEqual(
            (alice[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"],
             alice[ANALYTICS_MEASURE_RECORDED_EVENTS]["count"]),
            (300_000, 2))
        self.assertEqual(
            (bob[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"],
             bob[ANALYTICS_MEASURE_RECORDED_EVENTS]["count"]), (7_000_000, 1))

    def test_the_route_publishes_no_customer_parameter(self):
        document = api.get_openapi_schema()
        (key,) = [path for path in document["paths"] if path.endswith(
            "/me/economics")]
        published = {parameter["name"]
                     for parameter in document["paths"][key]["get"]
                     ["parameters"]}
        self.assertEqual(published, {"start_date", "end_date"})

    def test_a_stray_customer_parameter_changes_nothing(self):
        """There is no selector to honour: a caller naming another customer
        gets its own answer back, because the route never reads the name."""
        own = self._read(self.alice)
        asked_about_bob = self._read(self.alice, customer_id=str(self.bob.id))

        self.assertEqual(asked_about_bob, own)


class ABusinessReadsOnlyItsOwnUsageTest(_WidgetCase):

    def test_a_business_token_does_not_add_up_its_seats(self):
        business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=business)
        self._posting(seat, "s1", billed=5_000_000)
        self._posting(business, "own", billed=40_000)

        body = self._read(business)

        self.assertEqual(
            (body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"],
             body[ANALYTICS_MEASURE_RECORDED_EVENTS]["count"]), (40_000, 1))


class OnlyTheTwoSafeMeasuresAreShownTest(_WidgetCase):

    def setUp(self):
        super().setUp()
        self._posting(self.alice, "a1", billed=100_000)

    def test_the_answer_carries_exactly_the_widget_keys(self):
        body = self._read(self.alice)

        self.assertEqual(set(body), ANSWER_KEYS)
        self.assertEqual(set(body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]),
                         REVENUE_KEYS)
        self.assertEqual(set(body[ANALYTICS_MEASURE_RECORDED_EVENTS]),
                         COUNT_KEYS)

    def test_the_schema_is_the_mounts_own_and_names_no_tenant_measure(self):
        document = api.get_openapi_schema()
        (key,) = [path for path in document["paths"] if path.endswith(
            "/me/economics")]
        responses = document["paths"][key]["get"]["responses"]
        answered = responses.get(200) or responses["200"]
        reference = answered["content"]["application/json"]["schema"]["$ref"]
        schemas = document["components"]["schemas"]
        name = reference.rsplit("/", 1)[-1]
        self.assertEqual(name, "MeEconomicsOut")
        answer = schemas[name]
        self.assertEqual(set(answer["properties"]), ANSWER_KEYS)
        nested = {key: spec["$ref"].rsplit("/", 1)[-1]
                  for key, spec in answer["properties"].items() if "$ref" in spec}
        self.assertEqual(nested, {
            ANALYTICS_MEASURE_CUSTOMER_REVENUE: "MeCustomerRevenueOut",
            ANALYTICS_MEASURE_RECORDED_EVENTS: "MeRecordedEventsOut"})
        self.assertEqual(set(schemas["MeCustomerRevenueOut"]["properties"]),
                         REVENUE_KEYS)
        self.assertEqual(set(schemas["MeRecordedEventsOut"]["properties"]),
                         COUNT_KEYS)
        published = str([answer, schemas["MeCustomerRevenueOut"],
                         schemas["MeRecordedEventsOut"]])
        for tenant_only in ("supplier_cogs", "gross_margin",
                            "unresolved_event_count", "unpriced_event_count",
                            "grouping_field"):
            self.assertNotIn(tenant_only, published)

    def test_a_field_added_to_the_tenant_answer_never_reaches_the_widget(self):
        """Defence in depth (ruling 17): the tenant answer growing a field — at
        the top, or on a measure — leaves this one exactly as it was."""
        from api.v1 import economic_question

        real = economic_question.ask_the_economic_query
        before = self._read(self.alice)

        def grown(*args, **kwargs):
            answer, foreign = real(*args, **kwargs)
            answer["supplier_cogs_total_micros"] = 999
            for entry in answer["rows"][0]["measures"]:
                entry["supplier_cost_micros"] = 999
            return answer, foreign

        with mock.patch.object(economic_question, "ask_the_economic_query",
                               grown):
            after = self._read(self.alice)

        self.assertEqual(after, before)


class RevenueKeepsItsTruthTest(_WidgetCase):

    def test_it_names_its_basis_and_currency(self):
        self._posting(self.alice, "a1", billed=100_000)

        body = self._read(self.alice)

        self.assertEqual(body["basis"], REVENUE_BASIS_RECORDED)
        self.assertEqual(body["currency"], ECONOMIC_CURRENCY)
        self.assertEqual(body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["status"],
                         MEASURE_STATUS_KNOWN)

    def test_revenue_nobody_priced_is_null_never_zero(self):
        self._posting(self.alice, "unpriced", billed=None, priced=False)

        body = self._read(self.alice)

        revenue = body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]
        self.assertIsNone(revenue["amount_micros"])
        self.assertEqual(revenue["status"], MEASURE_STATUS_INCOMPLETE)
        self.assertEqual(body[ANALYTICS_MEASURE_RECORDED_EVENTS]["count"], 1)


class TheWindowIsTheSharedOneTest(_WidgetCase):

    def test_no_dates_is_the_month_to_date_and_is_echoed(self):
        self._posting(self.alice, "march", billed=100_000)
        self._posting(self.alice, "february", billed=900_000,
                      at=datetime(2026, 2, 27, 12, 0, tzinfo=dt_timezone.utc))

        body = self._read(self.alice)

        self.assertEqual((body["period_start"], body["period_end"]),
                         ("2026-03-01", "2026-03-18"))
        self.assertEqual(
            body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"], 100_000)

    def test_a_lone_date_is_honoured_and_the_end_is_inclusive(self):
        self._posting(self.alice, "late-on-the-ninth", billed=100_000,
                      at=datetime(2026, 3, 9, 23, 59, tzinfo=dt_timezone.utc))
        self._posting(self.alice, "the-tenth", billed=900_000,
                      at=datetime(2026, 3, 10, 0, 0, tzinfo=dt_timezone.utc))

        body = self._read(self.alice, end_date=date(2026, 3, 9).isoformat())

        self.assertEqual((body["period_start"], body["period_end"]),
                         ("2026-03-01", "2026-03-09"))
        self.assertEqual(
            body[ANALYTICS_MEASURE_CUSTOMER_REVENUE]["amount_micros"], 100_000)

    def test_a_window_past_the_bound_is_refused(self):
        response = self._ask(self.alice, start_date="2000-01-01")

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(response.json()["code"], "validation_error")

    def test_the_route_publishes_the_one_window_description(self):
        document = api.get_openapi_schema()
        (key,) = [path for path in document["paths"] if path.endswith(
            "/me/economics")]
        self.assertIn(report_window_description(),
                      document["paths"][key]["get"]["description"])


class TheMeteringProductGatesItTest(_WidgetCase):

    def test_a_tenant_without_metering_is_refused(self):
        # Written to the row: the tenant's own validation refuses a product
        # set without metering, so only a write past it reaches this state.
        Tenant.objects.filter(pk=self.tenant.pk).update(products=["billing"])

        response = self._ask(self.alice)

        self.assertEqual(response.status_code, 403, response.content)

    def test_a_tenant_with_metering_and_no_billing_is_answered(self):
        """Metering-scoped, not billing-scoped: a tenant that bills elsewhere
        still shows its customers what they used."""
        self.assertEqual(self.tenant.products, ["metering"])
        self.assertEqual(self._ask(self.alice).status_code, 200)

    def test_no_token_is_refused(self):
        self.assertEqual(Client().get(PATH).status_code, 401)
