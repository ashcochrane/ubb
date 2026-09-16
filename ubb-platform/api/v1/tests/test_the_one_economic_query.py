"""The one economic query, through its route (#499, slice 7 §2–§5, §10, §16).

**Tested through the route rather than through the read contract**, which is the
slice's own seam rule: a read contract tested only directly is a contract
nothing holds to its published shape. What a caller can observe is here; the
combinations a request cannot express, and the claims about WHERE a number came
from, are beside the read contract in `apps/metering/tests/`.

⚠ **THE PARITY CLASS IS THE ACCEPTANCE CRITERION AND NOT A SMOKE TEST.** Five
backend definitions of two numbers collapse into one, and the only way to show
that the one is the same as the five is to run both against one fixture and
compare. The two routes it compares against are still live — they collapse in
the next ticket — so this is the window in which the comparison can be made at
all, and it is made here deliberately.

⚠ **THIS MODULE NEVER SPELLS THE PARAMETERS THIS VOCABULARY REPLACES.** The
registry retires them and the sweep refuses a living file that names one.
"""
import uuid
from datetime import date, datetime, timezone as dt_timezone

import pytest
from django.test import Client

from apps.metering.pricing.models import Charge
from apps.metering.pricing.services.charge_projection import project_the_charge
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.models import Task
from apps.subscriptions.economics.models import TenantSuppliedRevenue
from apps.subscriptions.economics.services import MARGIN_REVENUE_BASIS
from apps.subscriptions.models import StripeSubscription
from core.auth import READ
from core.time_windows import HOURLY_REPORT_WINDOW_MAX_DAYS
from core.vocabulary import (
    TENANT_PRODUCT_METERING,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS, ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED, MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_KNOWN, MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    PRICING_STATUS_KNOWN, RECOGNITION_METHOD_STRAIGHT_LINE,
    REVENUE_BASIS_RECORDED, UNRESOLVED_REASON_COST_RATE_MISSING,
)

ECONOMICS = "/api/v1/metering/analytics/economics"
SUMMARY = "/api/v1/margin/summary"
PER_CUSTOMER = "/api/v1/margin/customers"

#: The window every fixture records into: one whole calendar month, so the
#: coarse revenue's own span and the question's period are the same shape.
OPENS, CLOSES = date(2026, 3, 1), date(2026, 3, 31)
NEXT = date(2026, 4, 1)
MARCH = datetime(2026, 3, 10, 9, 30, tzinfo=dt_timezone.utc)
ALL_FOUR = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
            ANALYTICS_MEASURE_GROSS_MARGIN, ANALYTICS_MEASURE_RECORDED_EVENTS]
MONEY = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
         ANALYTICS_MEASURE_GROSS_MARGIN]


def a_tenant(name="T", *, fields=()):
    """A metering tenant and a raw key for it.

    `products=["metering"]` is not optional — the route is product-gated, so a
    tenant without it answers 403 rather than 200, which reads as an auth bug.
    """
    tenant = Tenant.objects.create(name=name, products=["metering"])
    for position, key in enumerate(fields, start=1):
        GroupingField.objects.create(tenant=tenant, key=key,
                                     slot=f"grouping_field_{position}",
                                     scope="event")
    _, raw_key = TenantApiKey.create_key(tenant)
    return tenant, raw_key


def a_posting(tenant, customer, key, **overrides):
    """One recorded posting, priced and costed unless a case says otherwise.

    The defaults make both sides resolved and DIFFERENT: a fixture whose price
    equals its cost makes the margin zero whatever the code does, and every
    assertion about it is then satisfiable by the wrong number.
    """
    fields = {"tenant": tenant, "customer": customer, "idempotency_key": key,
              "effective_at": MARCH, "provider": "openai",
              "event_type": "chat.completion",
              "provider_cost_micros": 400_000,
              "costing_status": COSTING_STATUS_KNOWN,
              "billed_cost_micros": 1_000_000,
              "pricing_status": PRICING_STATUS_KNOWN}
    fields.update(overrides)
    return Posting.objects.create(**fields)


def ask(raw_key, **params):
    """One economic question, with the measures and axes repeated properly."""
    query = []
    for name, value in params.items():
        if isinstance(value, (list, tuple)):
            query += [(name, entry) for entry in value]
        elif value is not None:
            query.append((name, value))
    return Client().get(ECONOMICS, query,
                        HTTP_AUTHORIZATION=f"Bearer {raw_key}")


def measure_of(body, measure, row=0):
    for entry in body["rows"][row]["measures"]:
        if entry["measure"] == measure:
            return entry
    raise AssertionError(f"{measure!r} is not in row {row} of the answer")


@pytest.mark.django_db
class TestOneRequestAnswersWhatFiveDefinitionsAnsweredBefore:
    """AC 1: the same tenant-wide totals the tenant-wide margin route returned,
    and the same per-customer rows the per-customer margin list returned, FROM
    ONE DEFINITION.

    The fixture holds all three revenue sources at once — a Stripe subscription,
    a figure the tenant supplied and the usage UBB priced — because a query that
    composed only two of them would agree with the old routes on a tenant that
    happened to have only two.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.one = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.two = Customer.objects.create(tenant=self.tenant, external_id="c2")
        a_posting(self.tenant, self.one, "i1")
        a_posting(self.tenant, self.one, "i2", provider="anthropic")
        a_posting(self.tenant, self.two, "i3", provider_cost_micros=250_000,
                  billed_cost_micros=600_000)
        StripeSubscription.objects.create(
            tenant=self.tenant, customer=self.one,
            stripe_subscription_id="sub_1", stripe_product_name="Pro",
            status="active", amount_micros=31_000_000, quantity=1,
            currency="usd", interval="month", current_period_start=MARCH,
            current_period_end=MARCH, last_synced_at=MARCH)
        TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.two, amount_micros=3_100_000,
            currency="usd", period_start=OPENS, period_end=NEXT,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference="inv-1")

    #: ⚠ **THE TWO SURFACES DISAGREE ABOUT WHETHER `end_date` IS INCLUSIVE, AND
    #: THE PARITY COMPARISON HAS TO SPAN-ALIGN THEM RATHER THAN PRETEND.**
    #:
    #: The margin routes bound the window at the START of their end date
    #: (`margin_endpoints._window` into `get_per_customer_cost_totals`, which
    #: filters `effective_at__lt=utc_day_start(end)`); metering's analytics
    #: surfaces bound it at the NEXT midnight and say so at the site — *inclusive
    #: date end == strict bound at the next UTC midnight*. The one query takes
    #: metering's, which is the documented convention, the one a caller expects
    #: of a field called `end_date`, and the one its own filters already used.
    #:
    #: So the comparison below asks each surface for the same half-open span,
    #: spelled the way that surface spells it. **That divergence is itself a
    #: fifth definition of these two numbers** — it is why a 31-day month read
    #: one way and 30 days read the other — and it is the kind of thing the
    #: collapse removes. The ticket that deletes these routes inherits a real
    #: behavioural change for any caller passing an explicit end date, and this
    #: is where that is written down.
    OLD_WINDOW = {"start_date": OPENS.isoformat(), "end_date": NEXT.isoformat()}

    def _window(self):
        return {"start_date": OPENS.isoformat(), "end_date": CLOSES.isoformat()}

    def _old_summary(self):
        return Client().get(SUMMARY, self.OLD_WINDOW,
                            HTTP_AUTHORIZATION=f"Bearer {self.key}").json()

    def test_the_end_date_is_inclusive_here_and_exclusive_on_the_old_route(self):
        """The premise the comparison rests on, MEASURED and not assumed — and
        the finding the collapse inherits, in one case.

        The discriminating fixture is a posting ON the end date. The old route
        bounds at the START of its end date and drops it; this one bounds at the
        next midnight and keeps it. Asking both for the same literal dates
        therefore produces two different costs, which is the whole point.
        """
        a_posting(self.tenant, self.one, "on-the-boundary",
                  effective_at=datetime(2026, 3, 31, 12, 0,
                                        tzinfo=dt_timezone.utc),
                  provider_cost_micros=777_000)
        dates = {"start_date": OPENS.isoformat(), "end_date": CLOSES.isoformat()}
        mine = measure_of(ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                              **dates).json(),
                          ANALYTICS_MEASURE_SUPPLIER_COGS)["amount_micros"]
        theirs = Client().get(
            SUMMARY, dates,
            HTTP_AUTHORIZATION=f"Bearer {self.key}").json()["provider_cost_micros"]
        assert mine - theirs == 777_000, (
            "the two surfaces must differ by exactly the boundary day's cost; "
            "if they agree, one of the two conventions has moved")
        # And the one query says which window it applied, so the difference is
        # readable from the answer rather than inferred.
        assert ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   **dates).json()["period_end"] == CLOSES.isoformat()

    def test_the_tenant_wide_totals_agree_with_the_route_it_replaces(self):
        old = self._old_summary()
        new = ask(self.key, measures=MONEY, basis=MARGIN_REVENUE_BASIS,
                  **self._window()).json()
        assert measure_of(new, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == old["provider_cost_micros"]
        assert measure_of(new, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == old["total_revenue_micros"]
        assert measure_of(new, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] == old["gross_margin_micros"]

    def test_the_fixture_is_not_degenerate(self):
        """The guard the comparison above rests on: three sources, all non-zero
        and all different. Two equal figures agree for free."""
        old = self._old_summary()
        assert old["subscription_revenue_micros"] > 0
        assert old["supplied_revenue_micros"] > 0
        assert old["usage_revenue_micros"] > 0
        assert old["gross_margin_micros"] != old["total_revenue_micros"]

    def test_the_per_customer_rows_agree_with_the_list_it_replaces(self):
        old = Client().get(PER_CUSTOMER, self.OLD_WINDOW,
                           HTTP_AUTHORIZATION=f"Bearer {self.key}").json()
        new = ask(self.key, measures=MONEY, group_by=["field:customer"],
                  basis=MARGIN_REVENUE_BASIS, **self._window()).json()
        was = {row["customer_id"]: row for row in old["customers"]}
        for index, row in enumerate(new["rows"]):
            before = was[row["grouping_field_value"][0]]
            assert measure_of(new, ANALYTICS_MEASURE_CUSTOMER_REVENUE, index
                              )["amount_micros"] == (
                before["subscription_revenue_micros"]
                + before["supplied_revenue_micros"]
                + before["usage_revenue_micros"])
            assert measure_of(new, ANALYTICS_MEASURE_GROSS_MARGIN, index
                              )["amount_micros"] == before["gross_margin_micros"]
        assert len(new["rows"]) == len(was) == 2

    def test_the_answer_always_states_the_basis_it_served(self):
        served = ask(self.key, measures=MONEY, **self._window()).json()
        assert served["basis"] == REVENUE_BASIS_RECORDED
        chosen = ask(self.key, measures=MONEY, basis=MARGIN_REVENUE_BASIS,
                     **self._window()).json()
        assert chosen["basis"] == MARGIN_REVENUE_BASIS

    def test_the_answer_echoes_the_request_a_row_is_aligned_to(self):
        body = ask(self.key, measures=MONEY,
                   group_by=["field:customer", "field:provider"],
                   **self._window()).json()
        assert body["group_by"] == ["field:customer", "field:provider"]
        for row in body["rows"]:
            assert len(row["grouping_field_value"]) == 2
            assert len(row["grouping_field_value_status"]) == 2


@pytest.mark.django_db
class TestTheScopeRuleOnTheWire:
    """AC 2 and AC 3: the coarse revenue is context on the finer chart and
    produces no margin there — not zero, not an unattributed bucket, and not
    distributed."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        a_posting(self.tenant, self.customer, "i1")
        TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.customer, amount_micros=9_000_000,
            currency="usd", period_start=OPENS, period_end=NEXT,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference="inv-1")
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def test_supplied_at_customer_grain_grouped_by_provider_says_so(self):
        body = ask(self.key, measures=MONEY, group_by=["field:provider"],
                   basis=MARGIN_REVENUE_BASIS, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert revenue["status"] == MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        assert revenue["amount_micros"] == 1_000_000  # not zero, not the whole
        assert len(body["rows"]) == 1                 # no unattributed bucket

    def test_no_margin_is_drawn_and_the_money_is_named_instead(self):
        body = ask(self.key, measures=MONEY, group_by=["field:provider"],
                   basis=MARGIN_REVENUE_BASIS, **self.window).json()
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin["amount_micros"] is None
        assert margin["status"] == MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        assert [entry["amount_micros"] for entry in body["context"]] == [9_000_000]
        assert body["context"][0]["attributable_axes"] == ["field:customer"]
        assert body["context"][0]["source"] == "tenant_supplied"

    def test_two_grains_do_not_differ_by_the_coarse_revenue(self):
        coarse = ask(self.key, measures=MONEY, basis=MARGIN_REVENUE_BASIS,
                     **self.window).json()
        fine = ask(self.key, measures=MONEY, group_by=["field:provider"],
                   basis=MARGIN_REVENUE_BASIS, **self.window).json()
        assert measure_of(coarse, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] == 10_000_000 - 400_000
        assert measure_of(fine, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] is None

    def test_a_question_that_asked_no_revenue_gets_no_revenue_context(self):
        """Context is the money a grouping could not place, so it belongs to a
        question that asked about money. On a cost-only question it would be
        noise about a number the caller did not request — and the rows behind it
        would be two queries against another product for an answer that has
        nowhere to put them."""
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   group_by=["field:provider"], **self.window).json()
        assert body["context"] == []
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["status"] == MEASURE_STATUS_KNOWN

    def test_asking_for_revenue_beside_it_brings_the_context_back(self):
        """The guard on the case above: the absence is about the MEASURE SET
        and not about the grouping, which is unchanged between the two."""
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS,
                                       ANALYTICS_MEASURE_CUSTOMER_REVENUE],
                   group_by=["field:provider"], **self.window).json()
        assert [entry["amount_micros"] for entry in body["context"]] == [
            9_000_000]

    def test_grouped_by_the_axis_it_admits_the_margin_is_drawn(self):
        """The guard: the rule withholds where it must and not everywhere."""
        body = ask(self.key, measures=MONEY, group_by=["field:customer"],
                   basis=MARGIN_REVENUE_BASIS, **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_KNOWN
        assert body["context"] == []


@pytest.mark.django_db
class TestAMarginIsNoBetterThanItsWorstInput:
    """AC 4: gross margin reads `incomplete` when the cost side is incomplete
    EVEN WHERE the revenue side reads `known`, with the unresolved count."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        customer = Customer.objects.create(tenant=self.tenant,
                                           external_id="c1")
        a_posting(self.tenant, customer, "i1", provider_cost_micros=None,
                  costing_status=COSTING_STATUS_UNRESOLVED,
                  unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def test_the_revenue_side_reads_known_and_the_margin_does_not(self):
        body = ask(self.key, measures=MONEY, **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["status"] == MEASURE_STATUS_KNOWN
        assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_INCOMPLETE

    def test_the_unresolved_count_travels_with_the_cost(self):
        body = ask(self.key, measures=MONEY, **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["unresolved_event_count"] == 1


@pytest.mark.django_db
class TestWhatTheSurfaceRefuses:
    """AC 5 and AC 6: what a caller is told instead of a subtly wrong answer."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()

    def test_a_request_with_no_measures_is_refused(self):
        answered = ask(self.key)
        assert answered.status_code == 422
        assert answered.json()["code"] == "validation_error"
        for measure in ALL_FOUR:
            assert measure in answered.json()["detail"]

    def test_a_measure_name_that_is_not_one_is_refused_by_name(self):
        answered = ask(self.key, measures=["profit"])
        assert answered.status_code == 422
        assert "profit" in answered.json()["detail"]

    def test_an_unsupported_measure_at_an_axis_names_both(self):
        answered = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                       group_by=["rollup:measurement_concept"])
        assert answered.status_code == 422
        body = answered.json()
        assert body["code"] == "unanswerable_combination"
        assert ANALYTICS_MEASURE_SUPPLIER_COGS in body["detail"]
        assert "rollup:measurement_concept" in body["detail"]

    def test_a_count_compared_across_mixed_event_types_is_refused(self):
        answered = ask(self.key, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
                       group_by=["field:provider"])
        assert answered.status_code == 422
        assert answered.json()["code"] == "unanswerable_combination"
        assert "field:event_type" in answered.json()["detail"]

    def test_the_same_count_is_answered_with_the_event_type_beside_it(self):
        answered = ask(self.key, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
                       group_by=["field:provider", "field:event_type"])
        assert answered.status_code == 200

    def test_a_refused_request_and_a_malformed_one_earn_different_codes(self):
        """A caller fixes a malformed request and ASKS A DIFFERENT QUESTION
        after a refused one, so one code for both would give away exactly the
        distinguishability the refusal was bought for."""
        malformed = ask(self.key, measures=["profit"]).json()["code"]
        refused = ask(self.key, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
                      group_by=["field:provider"]).json()["code"]
        assert malformed != refused

    def test_a_window_past_the_bound_is_refused(self):
        answered = ask(self.key, measures=MONEY, start_date="2020-01-01",
                       end_date="2026-01-01")
        assert answered.status_code == 422
        assert answered.json()["code"] == "validation_error"

    def test_an_hourly_question_keeps_the_tighter_ceiling(self):
        """The bound this query inherits from the timeseries route it replaces.
        Taking that route's job without its bound would answer, over the widest
        window, the report its predecessor refused."""
        span = {"start_date": "2026-01-01", "end_date": "2026-06-01"}
        assert ask(self.key, measures=MONEY, bucket="day",
                   **span).status_code == 200
        refused = ask(self.key, measures=MONEY, bucket="hour", **span)
        assert refused.status_code == 422
        assert str(HOURLY_REPORT_WINDOW_MAX_DAYS) in refused.json()["detail"]

    def test_an_hourly_question_inside_the_tighter_ceiling_is_answered(self):
        """The guard: the bound is about the SPAN and not about the bucket."""
        assert ask(self.key, measures=MONEY, bucket="hour",
                   start_date="2026-03-01", end_date="2026-03-20"
                   ).status_code == 200

    def test_a_bucket_that_is_not_one_is_refused_by_name(self):
        answered = ask(self.key, measures=MONEY, bucket="fortnight")
        assert answered.status_code == 422
        assert "fortnight" in answered.json()["detail"]

    def test_an_axis_this_tenant_never_declared_is_refused(self):
        answered = ask(self.key, measures=MONEY, group_by=["field:nope"])
        assert answered.status_code == 422
        assert "nope" in answered.json()["detail"]

    def test_a_filter_that_is_not_a_pair_is_refused(self):
        answered = ask(self.key, measures=MONEY, where=["field:region"])
        assert answered.status_code == 422
        assert answered.json()["code"] == "validation_error"


@pytest.mark.django_db
class TestTheCountAndTheChargeItMustNotCount:
    """AC 6's first half, through the route and in both directions."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        a_posting(self.tenant, self.customer, "i1")
        task = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0)
        project_the_charge(Charge.objects.create(
            tenant=self.tenant, task=task, amount_micros=5_000_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MARCH, charged_at=MARCH, idempotency_key="charge-1"))
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def _rows(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS,
                                       ANALYTICS_MEASURE_CUSTOMER_REVENUE],
                   group_by=["field:event_type"], basis=MARGIN_REVENUE_BASIS,
                   **self.window).json()
        return {row["grouping_field_value"][0]: (
            row["grouping_field_value_status"][0],
            {entry["measure"]: (entry["amount_micros"] if entry["amount_micros"]
                                is not None else entry["event_count"])
             for entry in row["measures"]})
            for row in body["rows"]}

    def test_the_charge_is_not_counted_as_work(self):
        rows = self._rows()
        assert rows["chat.completion"][1][
            ANALYTICS_MEASURE_RECORDED_EVENTS] == 1
        assert rows[None][1][ANALYTICS_MEASURE_RECORDED_EVENTS] == 0

    def test_the_charge_is_still_revenue(self):
        """The other direction: excluding it from the count must not exclude it
        from the money, or a Task's price would vanish from the answer."""
        rows = self._rows()
        assert rows[None][1][ANALYTICS_MEASURE_CUSTOMER_REVENUE] == 5_000_000

    def test_its_absent_event_type_says_the_question_does_not_apply(self):
        """Not `(unattributed)`, which is what the surfaces this replaces put
        both kinds of absence under."""
        assert self._rows()[None][0] == "not_applicable"


@pytest.mark.django_db
class TestBucketingOnTheWire:
    """AC 8: hour, day and month bucketing sit on the same query as grouping."""

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        customer = Customer.objects.create(tenant=self.tenant,
                                           external_id="c1")
        for hour, key in ((1, "a"), (5, "b")):
            a_posting(self.tenant, customer, key,
                      effective_at=datetime(2026, 3, 2, hour, 0,
                                            tzinfo=dt_timezone.utc))
        a_posting(self.tenant, customer, "c",
                  effective_at=datetime(2026, 3, 20, 1, 0,
                                        tzinfo=dt_timezone.utc))
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    @pytest.mark.parametrize("bucket,rows", [("hour", 3), ("day", 2),
                                             ("month", 1)])
    def test_each_bucket_splits_the_period_its_own_way(self, bucket, rows):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   bucket=bucket, **self.window).json()
        assert body["bucket"] == bucket
        assert len(body["rows"]) == rows

    def test_no_bucket_is_the_whole_period_as_one_row(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   **self.window).json()
        assert body["bucket"] is None
        assert len(body["rows"]) == 1
        assert body["rows"][0]["bucket_start"] is None

    def test_bucketing_composes_with_grouping(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   bucket="day", group_by=["field:provider"],
                   **self.window).json()
        assert len(body["rows"]) == 2
        assert {row["grouping_field_value"][0] for row in body["rows"]} == {
            "openai"}


@pytest.mark.django_db
class TestTheSurfaceIsGatedLikeItsNeighbours:
    """The floor and the product check, and the one of them that cannot be
    driven from outside.

    ⚠ **THE METERING PRODUCT REFUSAL IS UNREACHABLE FOR EVERY TENANT, AND THAT
    IS A FACT ABOUT THE TREE RATHER THAN A GAP HERE.** `Tenant.save` fills an
    empty product list with metering and `Tenant.clean` refuses one without it,
    so no tenant exists that the check could turn away. Writing a 403 case would
    have produced a green test over a 200 — it did, on the first run — so the
    check is asserted where it IS decidable, at the declaration, and the
    non-event is written down rather than dressed up as coverage.
    """

    def test_an_unauthenticated_caller_is_refused(self):
        assert Client().get(ECONOMICS).status_code == 401

    def test_the_route_is_declared_at_the_read_floor(self):
        """Read floor, and deliberately: a finance operator building a chart is
        exactly who asks this, and the axes it groups by are the tenant's own
        declarations, which the same floor already reads next door."""
        from api.v1.metering_endpoints import (
            list_grouping_options, query_economics)
        assert (query_economics._role_floor
                == list_grouping_options._role_floor == READ)

    def test_no_tenant_can_be_built_that_the_product_check_would_refuse(self):
        """The premise the paragraph above rests on, read off the model."""
        tenant = Tenant.objects.create(name="T", products=[])
        assert TENANT_PRODUCT_METERING in tenant.products
