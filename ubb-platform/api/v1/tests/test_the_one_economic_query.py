"""The one economic query, through its route (#499, slice 7 §2–§5, §10, §16).

**Tested through the route rather than through the read contract**, which is the
slice's own seam rule: a read contract tested only directly is a contract
nothing holds to its published shape. What a caller can observe is here; the
combinations a request cannot express, and the claims about WHERE a number came
from, are beside the read contract in `apps/metering/tests/`.

⚠ **THE PARITY CLASS IS THE ACCEPTANCE CRITERION AND NOT A SMOKE TEST.** Five
backend definitions of two numbers collapsed into one. While the routes carrying
the other four were still live this class ran both against one fixture and
compared; #501 deleted them, so what it compares against now is the set of
figures those routes returned, written down beside the fixture that produces
them. The cases did not get weaker — each still fails on any change to the
composition — but the thing on the right-hand side is a recorded number rather
than a second live surface, and that is stated rather than left to be noticed.

⚠ **THIS MODULE NEVER SPELLS THE PARAMETERS THIS VOCABULARY REPLACES.** The
registry retires them and the sweep refuses a living file that names one.
"""
import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone

import pytest
from django.test import Client

from apps.metering.pricing.models import Charge
from apps.metering.pricing.services.charge_projection import project_the_charge
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from apps.subscriptions.economics.models import (
    CustomerCostAccumulator, TenantSuppliedRevenue)
from apps.subscriptions.economics.services import (
    MARGIN_REVENUE_BASIS, MarginService)
from apps.subscriptions.models import StripeSubscription
from apps.subscriptions.tests._helpers import a_supplied_figure
from api.v1.schemas import EconomicMeasureOut, EconomicsOut, MeasureStatus
# The route, the tenant it takes and the two readers of its answer moved to the
# shared helpers when #502 gave them a second module to serve.
from api.v1.tests._helpers import ECONOMICS, a_tenant, ask, measure_of
from core.auth import READ
from core.retention import (
    AVAILABLE_FROM_FIELD, ECONOMIC_HORIZON_FIELD, ECONOMIC_RETENTION_YEARS,
    MEASUREMENT_HORIZON_FIELD)
from core.time_windows import (
    HOURLY_REPORT_WINDOW_MAX_DAYS, REPORT_WINDOW_MAX_DAYS)
from core.vocabulary import (
    TENANT_PRODUCT_METERING,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS, ANALYTICS_MEASURE_SUPPLIER_COGS,
    COSTING_STATUS_KNOWN, COSTING_STATUS_UNRESOLVED, MEASURE_STATUS_INCOMPLETE,
    MEASURE_STATUS_KNOWN, MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON,
    MEASURE_STATUS_VALUES, PRICING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN,
    RECOGNITION_METHOD_ON_RECEIPT, RECOGNITION_METHOD_STRAIGHT_LINE,
    REVENUE_BASIS_RECOGNISED, REVENUE_BASIS_RECORDED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: The window every fixture records into: one whole calendar month, so the
#: coarse revenue's own span and the question's period are the same shape.
OPENS, CLOSES = date(2026, 3, 1), date(2026, 3, 31)
NEXT = date(2026, 4, 1)
MARCH = datetime(2026, 3, 10, 9, 30, tzinfo=dt_timezone.utc)
ALL_FOUR = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
            ANALYTICS_MEASURE_GROSS_MARGIN, ANALYTICS_MEASURE_RECORDED_EVENTS]
MONEY = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
         ANALYTICS_MEASURE_GROSS_MARGIN]


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


def describe(path):
    """One operation's PUBLISHED description, which is what a caller reads.

    Off the live document rather than off the function's `__doc__`: a claim the
    contract has to carry is a claim about the contract, and the two differ the
    moment anything reshapes the description on its way out.
    """
    from api.v1.api import api

    document = api.get_openapi_schema()
    matched = [key for key in document["paths"] if key.endswith(path)]
    assert len(matched) == 1, f"{path} is not one operation: {matched}"
    return document["paths"][matched[0]]["get"]["description"]


#: WHAT EACH OF THE NINE ROUTES STATED ABOUT THE FIXTURE BELOW, KEPT AS
#: LITERALS BECAUSE THE ROUTES ARE GONE (#501).
#:
#: ⚠ **THIS IS THE SAME COMPARISON #499 MADE, RECORDED RATHER THAN RE-RUN.**
#: While the five surfaces were still live these cases asked each of them for
#: the same span and asserted the one query agreed. That comparison cannot be
#: made against a deleted route, and rewriting the cases to assert whatever the
#: one query happens to say would be a test that could never fail. So the
#: figures those routes returned are written down here, where a reader can see
#: them and check the arithmetic, and each case that used to compare now
#: asserts against the number its route stated. **A change to the composition
#: fails here exactly as it failed before.**
#:
#: Derived from the fixture, and every one of them checkable by hand:
#: the tenant-wide cost is the three postings' supplier costs; the revenue is
#: the first customer's two postings' billed totals plus a whole month of a
#: monthly subscription plus a supplied record spanning exactly that month.
#:
#: ⚠ **TWO OF THESE NO LONGER AGREE WITH THE ROUTES THEY RECORD, ON PURPOSE
#: (#537).** Those routes ADDED the second customer's 600,000 of priced usage to
#: the 3,100,000 the tenant supplied for the same customer and the same month —
#: on a tenant that does not bill through UBB, which is a double count. The
#: owner's ruling on claim 9 makes a supplied figure the WHOLE revenue for the
#: customer and period it covers, so that usage revenue is superseded rather
#: than added, and `SECOND_CUSTOMER` and `TENANT_REVENUE` say so. The assertions
#: are unchanged: still exact, still per customer and tenant-wide.
TENANT_COST = 400_000 + 400_000 + 250_000
SUBSCRIPTION_FOR_MARCH = 31_000_000
SUPPLIED_FOR_MARCH = 3_100_000
#: What UBB priced for the second customer inside the month the tenant's own
#: figure covers — recorded, and superseded by that figure (#537).
SUPERSEDED_USAGE_REVENUE = 600_000
#: The usage revenue the answer states: the first customer's, whose month no
#: supplied figure covers.
TENANT_USAGE_REVENUE = 1_000_000 + 1_000_000
TENANT_REVENUE = (TENANT_USAGE_REVENUE + SUBSCRIPTION_FOR_MARCH
                  + SUPPLIED_FOR_MARCH)
#: The per-customer split the list route returned, as `(revenue, cost)` pairs.
#: The first customer's revenue is its usage plus the subscription; the
#: second's is the figure the tenant supplied, and only that (#537 — the routes
#: stated `600_000 + SUPPLIED_FOR_MARCH`). ⚠ The rows come back keyed by the
#: customer's IDENTITY rather than by the tenant's own external id, which is
#: what `field:customer` groups and what the list route returned, so the test
#: builds the lookup from the fixture's own rows.
FIRST_CUSTOMER = (1_000_000 + 1_000_000 + SUBSCRIPTION_FOR_MARCH,
                  400_000 + 400_000)
SECOND_CUSTOMER = (SUPPLIED_FOR_MARCH, 250_000)


def a_monthly_subscription(tenant, customer):
    """An active monthly Stripe subscription that accrues
    `SUBSCRIPTION_FOR_MARCH` over the month every fixture here records into."""
    return StripeSubscription.objects.create(
        tenant=tenant, customer=customer,
        stripe_subscription_id=f"sub_{customer.external_id}",
        stripe_product_name="Pro", status="active",
        amount_micros=SUBSCRIPTION_FOR_MARCH, quantity=1, currency="usd",
        interval="month", current_period_start=MARCH,
        current_period_end=MARCH, last_synced_at=MARCH)


@pytest.mark.django_db
class TestOneRequestAnswersWhatFiveDefinitionsAnsweredBefore:
    """AC 1: the tenant-wide totals the tenant-wide margin route returned, and
    the per-customer rows the per-customer margin list returned, FROM ONE
    DEFINITION — and now from the only definition, because both routes are gone
    (#501).

    The fixture holds all three revenue sources at once — a Stripe subscription,
    a figure the tenant supplied and the usage UBB priced — because a query that
    composed only two of them would have agreed with the old routes on a tenant
    that happened to have only two.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.one = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.two = Customer.objects.create(tenant=self.tenant, external_id="c2")
        a_posting(self.tenant, self.one, "i1")
        a_posting(self.tenant, self.one, "i2", provider="anthropic")
        a_posting(self.tenant, self.two, "i3", provider_cost_micros=250_000,
                  billed_cost_micros=SUPERSEDED_USAGE_REVENUE)
        a_monthly_subscription(self.tenant, self.one)
        TenantSuppliedRevenue.objects.create(
            tenant=self.tenant, customer=self.two, amount_micros=3_100_000,
            currency="usd", period_start=OPENS, period_end=NEXT,
            recognition_method=RECOGNITION_METHOD_STRAIGHT_LINE,
            source_reference="inv-1")

    def _window(self):
        return {"start_date": OPENS.isoformat(), "end_date": CLOSES.isoformat()}

    def test_the_end_date_is_inclusive_and_the_boundary_day_is_inside_it(self):
        """⚠ THE BEHAVIOURAL CHANGE THE COLLAPSE CARRIES, PINNED ON THE SURFACE
        THAT SURVIVED IT.

        The deleted margin routes bounded a window at the START of their end
        date (`margin_endpoints._window` into a read contract filtering
        `effective_at__lt=utc_day_start(end)`); metering's analytics surfaces
        bound it at the NEXT midnight, and said so at the site — *inclusive date
        end == strict bound at the next UTC midnight*. **That divergence was
        itself one of the five definitions**: the same literal dates gave a
        31-day month on one surface and 30 on the other, and a caller comparing
        them saw a discrepancy neither response could explain.

        The one query takes metering's reading, which is the documented
        convention and the one a caller expects of a field called `end_date`. So
        **any caller that passed an explicit end date to a margin route sees one
        more day in the answer now**, and the discriminating fixture is a posting
        ON that day: it is inside this answer, and it was outside theirs.
        """
        a_posting(self.tenant, self.one, "on-the-boundary",
                  effective_at=datetime(2026, 3, 31, 12, 0,
                                        tzinfo=dt_timezone.utc),
                  provider_cost_micros=777_000)
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   **self._window()).json()
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == TENANT_COST + 777_000, (
            "the boundary day must be INSIDE an inclusive end date; the routes "
            "this replaced excluded it, and that difference is the point")
        # And the answer says which window it applied, so the reading is
        # readable from the response rather than inferred from a convention.
        assert body["period_end"] == CLOSES.isoformat()

    def test_the_tenant_wide_totals_are_the_ones_the_summary_route_stated(self):
        new = ask(self.key, measures=MONEY, basis=MARGIN_REVENUE_BASIS,
                  **self._window()).json()
        assert measure_of(new, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == TENANT_COST
        assert measure_of(new, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == TENANT_REVENUE
        assert measure_of(new, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] == TENANT_REVENUE - TENANT_COST

    def test_the_fixture_is_not_degenerate(self):
        """The guard the assertions above rest on: three revenue sources, all
        non-zero and all different, and a margin that is not the revenue.

        It reads the constants rather than the answer, because its whole job is
        to say that the numbers being compared are capable of disagreeing.
        """
        assert SUBSCRIPTION_FOR_MARCH > 0
        assert SUPPLIED_FOR_MARCH > 0
        assert TENANT_USAGE_REVENUE > 0
        # And the superseded usage is real money, so an answer that added it
        # back on top of the supplied figure differs from these by that much.
        assert SUPERSEDED_USAGE_REVENUE > 0
        assert len({SUBSCRIPTION_FOR_MARCH, SUPPLIED_FOR_MARCH,
                    TENANT_USAGE_REVENUE}) == 3
        assert TENANT_COST > 0 and TENANT_REVENUE != TENANT_COST

    def test_the_per_customer_rows_are_the_ones_the_list_route_stated(self):
        expected = {str(self.one.id): FIRST_CUSTOMER,
                    str(self.two.id): SECOND_CUSTOMER}
        new = ask(self.key, measures=MONEY, group_by=["field:customer"],
                  basis=MARGIN_REVENUE_BASIS, **self._window()).json()
        seen = {}
        for index, row in enumerate(new["rows"]):
            customer_id = row["grouping_field_value"][0]
            seen[customer_id] = (
                measure_of(new, ANALYTICS_MEASURE_CUSTOMER_REVENUE, index
                           )["amount_micros"],
                measure_of(new, ANALYTICS_MEASURE_SUPPLIER_COGS, index
                           )["amount_micros"])
            revenue, cost = expected[customer_id]
            assert measure_of(new, ANALYTICS_MEASURE_GROSS_MARGIN, index
                              )["amount_micros"] == revenue - cost
        assert seen == expected

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
        # ⚠ THE PRICED POSTING IS ANOTHER CUSTOMER'S, SO THESE CASES STAY ABOUT
        # GRAIN (#537). A supplied figure is the whole revenue for the customer
        # and period it covers, so a posting of `c1`'s in March would be
        # superseded by it and the part a provider row could place would be
        # nothing. What these cases need is a figure that CAN be placed beside
        # one that cannot; the supersession has its own class below.
        priced = Customer.objects.create(tenant=self.tenant, external_id="c2")
        a_posting(self.tenant, priced, "i1")
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
        assert len(body["rows"]) == 2
        for index in range(len(body["rows"])):
            assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN, index
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
class TestUsageNobodyPricedIsNeverAKnownFigure:
    """Testing Decisions claim 9, as this surface says it — in the words #537's
    ruling gave it.

    A tenant that does not bill through UBB — `a_tenant` is one — whose usage
    carries no price and whose revenue nobody supplied. #495 proved the
    supplied-revenue record's half (`unknown`, and no amount to read); this is
    the query's half.

    ⚠ **WHERE NO PIECE OF A ROW'S REVENUE HAS RESOLVED, NEITHER THE REVENUE NOR
    THE MARGIN OVER IT STATES AN AMOUNT.** Claim 9 says margin `unavailable`,
    never zero. This query's two unavailable states are about grain and about
    retention and neither applies, and the owner ruled out a sixth (#537), so
    both measures read `incomplete` with `amount_micros` null — which on this
    surface means *no figure can be stated* — beside the count of postings
    nobody priced. Until #537 the revenue was a zero floor and the margin its
    negative, and the console drew "at least −£…": #153 §17.1's defect with a
    prefix.

    **An amount under `incomplete` is a BOUND, and there is one only where some
    piece of the row's revenue DID resolve.** That is a COUNT of resolved
    pieces and never a test of the sum, because a deliberate £0 price is
    resolved and a sum cannot tell a free service from one nobody priced — the
    two cases on the zero below are what hold the count to that.

    **The rule is per row**, so one grouped answer can carry a bound on one row
    and no amount on the next.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        a_posting(self.tenant, self.customer, "i1", billed_cost_micros=None,
                  pricing_status=PRICING_STATUS_UNKNOWN)
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def test_with_nothing_resolved_the_revenue_states_no_amount(self):
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert revenue["amount_micros"] is None
        assert revenue["status"] == MEASURE_STATUS_INCOMPLETE
        assert revenue["unpriced_event_count"] == 1

    def test_with_nothing_resolved_the_margin_states_no_amount_either(self):
        """The cost side is resolved here, so the state the margin carries and
        the amount it withholds can only have come from the revenue side — the
        mirror of the class above, where they could only have come from the
        cost side."""
        body = ask(self.key, measures=MONEY, **self.window).json()
        cost = measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS)
        assert (cost["amount_micros"], cost["status"]) == (
            400_000, MEASURE_STATUS_KNOWN)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin["amount_micros"] is None
        assert margin["status"] == MEASURE_STATUS_INCOMPLETE

    def test_with_some_revenue_resolved_the_priced_part_is_a_bound(self):
        """AC 2 — the behaviour before #537, pinned beside the case it must
        not be confused with: one priced posting beside the unpriced one, and
        the priced subtotal is stated as the bound it is."""
        a_posting(self.tenant, self.customer, "i2")
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"],
                revenue["unpriced_event_count"]) == (
            1_000_000, MEASURE_STATUS_INCOMPLETE, 1)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            1_000_000 - 800_000, MEASURE_STATUS_INCOMPLETE)

    def test_a_deliberate_zero_price_is_resolved_and_known(self):
        """AC 3 — a free service: every posting priced at £0 against a known
        cost is a KNOWN revenue of nothing and a real loss (#153 §3.4). Read
        for a second customer, so the unpriced posting above is not in it."""
        free = Customer.objects.create(tenant=self.tenant, external_id="c2")
        a_posting(self.tenant, free, "free-1", billed_cost_micros=0)
        a_posting(self.tenant, free, "free-2", billed_cost_micros=0)
        body = ask(self.key, measures=MONEY, customer_id=str(free.id),
                   **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"]) == (
            0, MEASURE_STATUS_KNOWN)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            -800_000, MEASURE_STATUS_KNOWN)

    def test_a_free_service_beside_an_unpriced_one_is_a_bound_of_zero(self):
        """The same count, in the other branch. A £0 posting beside the
        unpriced one IS a resolved piece, so the row states a bound — of zero —
        where a rule reading the SUM would have stated no amount and called the
        free service unpriced."""
        a_posting(self.tenant, self.customer, "i2", billed_cost_micros=0)
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"]) == (
            0, MEASURE_STATUS_INCOMPLETE)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            -800_000, MEASURE_STATUS_INCOMPLETE)

    def test_a_subscription_is_a_resolved_piece_and_excuses_nothing(self):
        """A Stripe subscription beside the unpriced posting: a piece of the
        revenue that resolved, so the row states a bound — and, being outside
        #537's ruling, it supersedes and excuses nothing, so a bound is what
        it stays."""
        a_monthly_subscription(self.tenant, self.customer)
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"],
                revenue["unpriced_event_count"]) == (
            SUBSCRIPTION_FOR_MARCH, MEASURE_STATUS_INCOMPLETE, 1)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            SUBSCRIPTION_FOR_MARCH - 400_000, MEASURE_STATUS_INCOMPLETE)

    def test_the_rule_is_per_row_and_never_across_the_answer(self):
        """AC 6: one question grouped by customer, where one customer has a
        priced posting beside an unpriced one and the other has only the
        unpriced one. Both rows read `incomplete`; only one states an amount."""
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        a_posting(self.tenant, other, "o1")
        a_posting(self.tenant, other, "o2", billed_cost_micros=None,
                  pricing_status=PRICING_STATUS_UNKNOWN)
        body = ask(self.key, measures=MONEY, group_by=["field:customer"],
                   **self.window).json()
        rows = {row["grouping_field_value"][0]: index
                for index, row in enumerate(body["rows"])}
        stated = {
            customer.id: [
                (entry["amount_micros"], entry["status"])
                for entry in (
                    measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                               rows[str(customer.id)]),
                    measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN,
                               rows[str(customer.id)]))]
            for customer in (self.customer, other)}
        assert stated[self.customer.id] == [
            (None, MEASURE_STATUS_INCOMPLETE), (None, MEASURE_STATUS_INCOMPLETE)]
        assert stated[other.id] == [
            (1_000_000, MEASURE_STATUS_INCOMPLETE),
            (1_000_000 - 800_000, MEASURE_STATUS_INCOMPLETE)]


@pytest.mark.django_db
class TestASuppliedFigureIsTheWholeRevenueForThePeriodItCovers:
    """#537's second ruling: a tenant-supplied figure is the revenue for the
    customer and the period it covers — AUTHORITATIVE, NEVER ADDED TO.

    #153 §3.2's second posture is cost tracking plus a supplied figure, and its
    promise is revenue `known` at the supplied scope with a margin there. Before
    #537 the query could not keep it, in two ways the fixtures never exercised:
    a cost-tracking tenant's usage is unpriced BY DESIGN, and one unpriced
    posting made the row's revenue `incomplete` however much the tenant had
    told UBB — so a tenant supplying its real revenue never got a known margin;
    and a tenant that priced usage in UBB to estimate a margin AND supplied its
    invoiced revenue had both added together.

    So inside a supplied figure's covered period, for its customer, revenue
    derived from priced usage is superseded and unpriced usage excuses nothing
    — its count stays on the measure as diagnostic information. Everywhere else
    the table in the class above holds. Stripe subscription revenue is not
    touched by this ruling in either direction; the parity class holds a
    subscription beside priced usage and adds them, as it always did.

    ⚠ **THE COVERED PERIOD IS THE RECORD'S OWN SPAN, WHATEVER BASIS PLACES ITS
    AMOUNT.** Under `recorded` a figure lands whole on the day its period opens,
    so a window starting after that day receives none of it — and must receive
    none of the usage it superseded either, or two windows that partition a
    month would add up to more than the tenant said the month earned.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def supply(self, amount_micros=SUPPLIED_FOR_MARCH, *, opens=OPENS,
               closes=NEXT, method=RECOGNITION_METHOD_STRAIGHT_LINE,
               customer=None):
        """One supplied figure, through the shared defaults, over March
        unless a case says otherwise."""
        return TenantSuppliedRevenue.objects.create(**a_supplied_figure(
            tenant=self.tenant, customer=customer or self.customer,
            amount_micros=amount_micros, period_start=opens, period_end=closes,
            recognition_method=method,
            source_reference=f"inv-{opens.isoformat()}"))

    def unpriced(self, key, **overrides):
        return a_posting(self.tenant, self.customer, key,
                         billed_cost_micros=None,
                         pricing_status=PRICING_STATUS_UNKNOWN, **overrides)

    def test_supplied_over_unpriced_usage_is_a_known_revenue(self):
        """AC 4 — the cost-tracking tenant that tells UBB its revenue."""
        self.unpriced("i1")
        self.unpriced("i2")
        self.supply()
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"]) == (
            SUPPLIED_FOR_MARCH, MEASURE_STATUS_KNOWN)
        # The two postings nobody priced are still published — as what they
        # are, not as a reason the figure is short.
        assert revenue["unpriced_event_count"] == 2
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            SUPPLIED_FOR_MARCH - 800_000, MEASURE_STATUS_KNOWN)

    def test_priced_usage_under_a_supplied_figure_is_superseded_not_added(self):
        """AC 5 — the mixed case: priced usage, unpriced usage and a supplied
        figure for the same customer and month. The revenue is the supplied
        figure EXACTLY; the 1,000,000 UBB priced is not on top of it."""
        a_posting(self.tenant, self.customer, "i1")
        self.unpriced("i2")
        self.supply()
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"],
                revenue["unpriced_event_count"]) == (
            SUPPLIED_FOR_MARCH, MEASURE_STATUS_KNOWN, 1)
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            SUPPLIED_FOR_MARCH - 800_000, MEASURE_STATUS_KNOWN)

    def test_the_cost_side_still_decides_the_margin(self):
        """§15's cost-side rule is unchanged: a supplied revenue is known, and
        a margin over a cost nobody resolved is still no better than that
        cost."""
        self.unpriced("i1", provider_cost_micros=None,
                      costing_status=COSTING_STATUS_UNRESOLVED,
                      unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING)
        self.supply()
        body = ask(self.key, measures=MONEY, **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["status"] == MEASURE_STATUS_KNOWN
        margin = measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert (margin["amount_micros"], margin["status"]) == (
            SUPPLIED_FOR_MARCH, MEASURE_STATUS_INCOMPLETE)

    def _around_a_february_figure(self):
        """A quarter of usage with a figure covering February alone: each
        month holds a priced posting, and January and February an unpriced one
        besides."""
        for month, billed in ((1, 1_000_000), (2, 1_000_000), (3, 600_000)):
            day = datetime(2026, month, 10, 9, 30, tzinfo=dt_timezone.utc)
            a_posting(self.tenant, self.customer, f"priced-{month}",
                      effective_at=day, billed_cost_micros=billed)
            if month < 3:
                self.unpriced(f"unpriced-{month}", effective_at=day)
        self.supply(2_800_000, opens=date(2026, 2, 1), closes=date(2026, 3, 1))
        return {"start_date": date(2026, 1, 1).isoformat(),
                "end_date": CLOSES.isoformat()}

    def test_only_the_month_it_covers_is_superseded_or_excused(self):
        """AC 7 — one month's figure inside a longer window supersedes that
        month's priced usage and excuses that month's unpriced posting, and
        nothing else: January's unpriced posting still makes the whole window
        a bound."""
        window = self._around_a_february_figure()
        body = ask(self.key, measures=MONEY, **window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"],
                revenue["unpriced_event_count"]) == (
            1_000_000 + 2_800_000 + 600_000, MEASURE_STATUS_INCOMPLETE, 2)

    def test_each_month_takes_the_rule_for_its_own_part(self):
        """The same quarter by month, where each part is a row of its own."""
        window = self._around_a_february_figure()
        body = ask(self.key, measures=MONEY, bucket="month", **window).json()
        months = {row["bucket_start"][:7]: index
                  for index, row in enumerate(body["rows"])}
        stated = {
            month: tuple(
                measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE, index)[key]
                for key in ("amount_micros", "status", "unpriced_event_count"))
            for month, index in months.items()}
        assert stated == {
            "2026-01": (1_000_000, MEASURE_STATUS_INCOMPLETE, 1),
            "2026-02": (2_800_000, MEASURE_STATUS_KNOWN, 1),
            "2026-03": (600_000, MEASURE_STATUS_KNOWN, 0)}

    def test_the_covered_period_is_the_records_own_whichever_basis_places_it(
            self):
        """Two windows that partition March add up to the figure the tenant
        supplied for March, under either basis — which they could not if the
        usage were superseded only where the amount happened to land.

        Under `recorded` the whole figure lands on 1 March, so the later
        window reads a KNOWN nothing: the tenant has said what March earned,
        and the recorded view places it at the month's opening. Under
        `recognised` it is spread by day, 9 of 31 and 22 of 31."""
        a_posting(self.tenant, self.customer, "early",
                  effective_at=datetime(2026, 3, 5, 9, 30,
                                        tzinfo=dt_timezone.utc))
        a_posting(self.tenant, self.customer, "late")
        self.supply()
        halves = ({"start_date": OPENS.isoformat(),
                   "end_date": date(2026, 3, 9).isoformat()},
                  {"start_date": MARCH.date().isoformat(),
                   "end_date": CLOSES.isoformat()})
        for basis, expected in ((REVENUE_BASIS_RECORDED, (3_100_000, 0)),
                                (REVENUE_BASIS_RECOGNISED,
                                 (900_000, 2_200_000))):
            stated = []
            for half in halves:
                revenue = measure_of(
                    ask(self.key, measures=MONEY, basis=basis, **half).json(),
                    ANALYTICS_MEASURE_CUSTOMER_REVENUE)
                assert revenue["status"] == MEASURE_STATUS_KNOWN, basis
                stated.append(revenue["amount_micros"])
            assert tuple(stated) == expected, basis
            assert sum(stated) == SUPPLIED_FOR_MARCH, basis

    def test_every_period_each_customers_figures_name_is_covered(self):
        """Consecutive monthly figures for one customer and a single month's
        for another: each customer's usage is superseded inside every period
        ITS figures cover and nowhere else — so the second customer's January
        usage, which no figure of theirs covers, is revenue."""
        other = Customer.objects.create(tenant=self.tenant, external_id="c2")
        for month in (1, 2):
            day = datetime(2026, month, 10, 9, 30, tzinfo=dt_timezone.utc)
            for customer in (self.customer, other):
                a_posting(self.tenant, customer, f"{customer.id}-{month}",
                          effective_at=day)
        self.supply(2_000_000, opens=date(2026, 1, 1),
                    closes=date(2026, 2, 1))
        self.supply(3_000_000, opens=date(2026, 2, 1),
                    closes=date(2026, 3, 1))
        self.supply(5_000_000, opens=date(2026, 2, 1),
                    closes=date(2026, 3, 1), customer=other)
        body = ask(self.key, measures=MONEY,
                   start_date=date(2026, 1, 1).isoformat(),
                   end_date=date(2026, 2, 28).isoformat()).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"]) == (
            2_000_000 + 3_000_000 + 5_000_000 + 1_000_000,
            MEASURE_STATUS_KNOWN)

    def test_overlapping_figures_are_two_facts_and_supersede_the_usage_once(
            self):
        """⚠ THE OVERLAP INVARIANT, ASSERTED RATHER THAN ASSUMED (#537's review).

        The record permits overlapping figures for one customer — its
        uniqueness key is the period's OPENING day and the source reference —
        and #495's record rule says what they mean: "two invoices covering one
        month are two facts". So no precedence is invented here. Where figures
        overlap, the revenue is the SUM of every figure covering the stretch,
        each attributed by its own span, and the usage priced inside is
        superseded ONCE, because what a set of figures covers is their union.
        Restating one figure is a different act and lands on the same row: the
        same opening day and source reference.

        A covers March; B covers 15 March – 15 April. Priced usage on the 5th
        (inside A only) and the 20th (inside both) is not added to either."""
        for key, day in (("only-a", 5), ("both", 20)):
            a_posting(self.tenant, self.customer, key,
                      effective_at=datetime(2026, 3, day, 9, 30,
                                            tzinfo=dt_timezone.utc))
        self.supply()
        self.supply(3_100_000, opens=date(2026, 3, 15),
                    closes=date(2026, 4, 15))
        for basis, march in (
                # B opens inside March, so under `recorded` it lands whole.
                (REVENUE_BASIS_RECORDED, 3_100_000 + 3_100_000),
                # Under `recognised`, 17 of B's 31 days are March's.
                (REVENUE_BASIS_RECOGNISED, 3_100_000 + 1_700_000)):
            revenue = measure_of(
                ask(self.key, measures=MONEY, basis=basis,
                    **self.window).json(),
                ANALYTICS_MEASURE_CUSTOMER_REVENUE)
            assert (revenue["amount_micros"], revenue["status"]) == (
                march, MEASURE_STATUS_KNOWN), basis

    def test_a_covered_part_is_resolved_wherever_its_amount_lands(self):
        """A figure covering 15 March to 15 April, asked about April, beside
        unpriced usage on either side of the 15th. The covered part is a
        RESOLVED piece of April's revenue under either basis — under
        `recorded` it resolved to nothing here, because the whole figure
        landed on 15 March, exactly as a £0 price is resolved — so the row is a
        bound, from the uncovered unpriced posting, and never "no figure". Under
        `recognised` the same bound carries April's 14 days of the figure."""
        self.unpriced("covered", effective_at=datetime(
            2026, 4, 5, 9, 30, tzinfo=dt_timezone.utc))
        self.unpriced("uncovered", effective_at=datetime(
            2026, 4, 20, 9, 30, tzinfo=dt_timezone.utc))
        self.supply(opens=date(2026, 3, 15), closes=date(2026, 4, 15))
        april = {"start_date": NEXT.isoformat(),
                 "end_date": date(2026, 4, 30).isoformat()}
        for basis, amount in ((REVENUE_BASIS_RECORDED, 0),
                              (REVENUE_BASIS_RECOGNISED, 1_400_000)):
            body = ask(self.key, measures=MONEY, basis=basis, **april).json()
            revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
            assert (revenue["amount_micros"], revenue["status"],
                    revenue["unpriced_event_count"]) == (
                amount, MEASURE_STATUS_INCOMPLETE, 2), basis
            assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN
                              )["amount_micros"] == amount - 800_000, basis

    def _mirrored_into_the_alerting_accumulator(self, *postings):
        """The monthly accumulator the alerting record snapshots from, holding
        exactly these postings — the consumer of `usage.recorded` writes it in
        production, and a fixture that left it empty would let the alerting
        total agree with the query for the wrong reason (no usage at all)."""
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=OPENS,
            period_end=NEXT,
            total_provider_cost_micros=sum(p.provider_cost_micros
                                           for p in postings),
            total_billed_cost_micros=sum(p.billed_cost_micros
                                         for p in postings),
            event_count=len(postings))

    def test_the_unprofitable_alert_states_the_same_revenue_as_the_query(self):
        """ONE ECONOMIC TRUTH PER CUSTOMER AND PERIOD (#537's review).

        The alerting record decides `is_unprofitable` and fires
        `customer.unprofitable`; the live margin behind the business tree is
        the same composition. Both used to ADD the supplied figure to the
        priced usage this query supersedes — a customer the analytics call
        £3,000 was alerted on as £3,500. Never £3,500, on any of the three."""
        priced = a_posting(self.tenant, self.customer, "i1",
                           billed_cost_micros=500_000_000)
        self._mirrored_into_the_alerting_accumulator(priced)
        self.supply(3_000_000_000)

        body = ask(self.key, measures=MONEY, basis=REVENUE_BASIS_RECOGNISED,
                   **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == 3_000_000_000
        snapshot = MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, OPENS, NEXT)
        assert snapshot.total_revenue_micros == 3_000_000_000
        assert snapshot.gross_margin_micros == 3_000_000_000 - 400_000
        live = MarginService.compute_live(
            self.tenant.id, self.customer.id, OPENS, NEXT)
        assert live["total_revenue_micros"] == 3_000_000_000

    def test_the_alert_supersedes_only_the_usage_the_figure_covers(self):
        """A figure covering the second half of March: the alerting total
        keeps the priced usage from before the 15th and supersedes the usage
        after it — the query's rule, over the stretches the figure leaves."""
        before = a_posting(self.tenant, self.customer, "before",
                           billed_cost_micros=500_000_000)
        inside = a_posting(self.tenant, self.customer, "inside",
                           billed_cost_micros=200_000_000,
                           effective_at=datetime(2026, 3, 20, 9, 30,
                                                 tzinfo=dt_timezone.utc))
        self._mirrored_into_the_alerting_accumulator(before, inside)
        self.supply(1_700_000_000, opens=date(2026, 3, 15),
                    method=RECOGNITION_METHOD_ON_RECEIPT)

        body = ask(self.key, measures=MONEY, basis=REVENUE_BASIS_RECOGNISED,
                   **self.window).json()
        query_revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                                   )["amount_micros"]
        assert query_revenue == 1_700_000_000 + 500_000_000
        assert MarginService.snapshot_customer(
            self.tenant.id, self.customer.id, OPENS, NEXT
        ).total_revenue_micros == query_revenue
        assert MarginService.compute_live(
            self.tenant.id, self.customer.id, OPENS, NEXT
        )["total_revenue_micros"] == query_revenue

    def test_grouped_finer_than_the_figure_the_superseded_usage_is_not_placed(
            self):
        """At a grain the figure cannot reach, the part a row CAN place does
        not include the usage the figure superseded — so the placed part and
        the context together are the supplied figure, and not that plus what
        UBB priced."""
        a_posting(self.tenant, self.customer, "i1")
        self.supply()
        body = ask(self.key, measures=MONEY, group_by=["field:provider"],
                   **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert revenue["status"] == MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        assert revenue["amount_micros"] == 0
        assert [entry["amount_micros"] for entry in body["context"]] == [
            SUPPLIED_FOR_MARCH]
        assert measure_of(body, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] is None

    def test_a_figure_for_an_instant_covers_no_period(self):
        """⚠ AN INTERPRETATION, STATED RATHER THAN LEFT TO BE DISCOVERED. A
        record with no period end declares an instant and not a span — the
        model's own words are that null "is not unknown" and is NOT to be
        silently treated as a day — so there is no period for it to be the
        whole revenue of. Its amount is a resolved piece of revenue like any
        other, and the usage beside it is neither superseded nor excused."""
        a_posting(self.tenant, self.customer, "i1")
        self.unpriced("i2")
        self.supply(500_000, opens=date(2026, 3, 5), closes=None,
                    method=RECOGNITION_METHOD_ON_RECEIPT)
        body = ask(self.key, measures=MONEY, **self.window).json()
        revenue = measure_of(body, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert (revenue["amount_micros"], revenue["status"],
                revenue["unpriced_event_count"]) == (
            1_000_000 + 500_000, MEASURE_STATUS_INCOMPLETE, 1)


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
class TestGroupingAxesAndTheUnitOfWorkFilter:
    """The capabilities the usage analytics report carried, on the query that
    replaced it (#501).

    ⚠ **THESE CASES WERE WRITTEN AGAINST THAT ROUTE** — a tenant's own declared
    key as a grouping axis, a reserved axis beside it, a word the tenant never
    declared refused, a correlation identifier refused as an axis while working
    as a FILTER, and containment rolling a tree up. They moved here whole, and
    two of them changed answer rather than shape:

    * an absent value on a reserved axis is no longer a `(unattributed)` string.
      It is a null value with a STATUS beside it, which is what lets *nobody
      recorded a value* and *the question does not apply to these rows* be two
      different facts;
    * a word the tenant never declared is refused against the discovery
      contract rather than against a hard-coded list of reserved names, which is
      why a correlation identifier is refused by the same rule rather than by a
      special case about correlation identifiers.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant(fields=["region"])
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        self.parent = Task.objects.create(
            tenant=self.tenant, customer=self.customer,
            balance_snapshot_micros=0, task_type="invoice_batch")
        self.child = Task.objects.create(
            tenant=self.tenant, customer=self.customer, parent=self.parent,
            balance_snapshot_micros=0, task_type="ocr")
        # The two reserved axes are two ALTITUDES of one declared kind of work
        # (#407): the root's lands on the top-level column, the leaf's on the
        # contained one, and a unit with no parent contributes to neither.
        for index, (task, region, cost) in enumerate((
                (self.parent, "eu-west-1", 1_000),
                (self.child, "eu-west-1", 2_000),
                (self.child, "us-east-1", 4_000))):
            a_posting(self.tenant, self.customer, f"k{index}",
                      provider="aws_textract", event_type="ocr_page",
                      task_id=task.id, task_type="invoice_batch",
                      subtask_type=task.task_type if task.parent_id else "",
                      grouping_field_1=region,
                      provider_cost_micros=cost, billed_cost_micros=cost * 2)
        self.window = {"start_date": OPENS.isoformat(),
                       "end_date": CLOSES.isoformat()}

    def _cost_by_axis(self, body):
        return {row["grouping_field_value"][0]:
                measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS,
                           index)["amount_micros"]
                for index, row in enumerate(body["rows"])}

    def test_a_tenant_can_group_by_a_key_it_declared_itself(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   group_by=["field:region"], **self.window).json()
        assert self._cost_by_axis(body) == {"eu-west-1": 3_000,
                                            "us-east-1": 4_000}

    def test_a_reserved_axis_says_which_absence_a_blank_row_is(self):
        """The case that changed answer. The report this replaced put the
        parent's blank contained-kind under `(unattributed)`, beside every other
        kind of absence; here the value is null and the status says the value
        was never recorded — which is the truth about a unit that has no parent,
        and is a different fact from *this question does not apply*."""
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   group_by=["field:subtask_type"], **self.window).json()
        assert self._cost_by_axis(body) == {"ocr": 6_000, None: 1_000}
        blank = next(row for row in body["rows"]
                     if row["grouping_field_value"] == [None])
        assert blank["grouping_field_value_status"] == ["not_recorded"]

    def test_a_word_this_tenant_never_declared_is_refused(self):
        response = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                       group_by=["field:nope"], **self.window)
        assert response.status_code == 422
        assert "nope" in response.json()["detail"]

    def test_a_correlation_identifier_is_not_a_grouping_axis(self):
        """It would build a bucket per unit of work, which is why it was refused
        on the route this replaces (design D9). Here it is refused by the
        general rule instead: the discovery contract does not offer it, and
        nothing a tenant can declare is named that."""
        response = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                       group_by=["field:task_id"], **self.window)
        assert response.status_code == 422

    def test_but_it_filters_to_one_unit_of_work(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   task_id=str(self.parent.id), **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == 1_000

    def test_and_contained_work_rolls_the_tree_up(self):
        body = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                   task_id=str(self.parent.id), include_subtasks="true",
                   **self.window).json()
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == 7_000

    def test_a_grouped_answer_reconciles_to_the_ungrouped_one(self):
        """⚠ **NO POSTING IS SILENTLY DROPPED BY A GROUPING**, moved here from
        the class that asserted it against the report this replaced (#501).

        The discriminating fixture is the row whose axis value is BLANK. A
        grouping that quietly excluded it would answer a smaller total than the
        same question ungrouped, and a reader comparing the two would find a
        difference neither answer explained. It is a row like any other, with a
        null value and a status saying which absence it is — which is the same
        reconciliation the sentinel string bought, plus the fact it could not
        state.
        """
        whole = measure_of(
            ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                **self.window).json(),
            ANALYTICS_MEASURE_SUPPLIER_COGS)["amount_micros"]
        grouped = ask(self.key, measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                      group_by=["field:subtask_type"], **self.window).json()
        parts = [measure_of(grouped, ANALYTICS_MEASURE_SUPPLIER_COGS,
                            index)["amount_micros"]
                 for index in range(len(grouped["rows"]))]

        assert None in [row["grouping_field_value"][0]
                        for row in grouped["rows"]], (
            "no blank-valued row, so this reconciles for the wrong reason")
        assert sum(parts) == whole == 7_000


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


@pytest.mark.django_db
class TestTheTwoHorizonsOnTheWire:
    """#500, spec §13 and §16: both horizons on every answer, and a series that
    falls outside one says exactly that.

    ⚠ **THE HORIZON IS READ OFF THE ANSWER AND THE TRUNCATING QUESTION IS BUILT
    FROM IT**, which is what a caller does and what keeps this test off the
    calendar. Both horizons are measured back from the day the question is
    asked, so a fixture spelling *2020-09-16* would be a test that starts
    failing on a date nobody chose — and re-deriving *today minus six years*
    here would re-implement the arithmetic `core/tests/test_retention.py`
    already owns, leap day and all.
    """

    @pytest.fixture(autouse=True)
    def fixture(self):
        self.tenant, self.key = a_tenant()
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        a_posting(self.tenant, self.customer, "i1")

    def horizon(self):
        """The economic horizon, as this surface publishes it."""
        body = ask(self.key, measures=MONEY).json()
        return date.fromisoformat(body["economic_data_available_from"])

    def test_both_horizons_are_published_on_an_untruncated_answer(self):
        """AC 1: whether or not anything was truncated — because *when can this
        series start* is a question a caller answers BEFORE choosing a window,
        and a field that appears only once something has gone wrong is a field
        nobody builds against."""
        body = ask(self.key, measures=ALL_FOUR, start_date=OPENS.isoformat(),
                   end_date=CLOSES.isoformat()).json()

        assert date.fromisoformat(body["economic_data_available_from"])
        assert date.fromisoformat(body["measurement_data_available_from"])
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["status"] == MEASURE_STATUS_KNOWN
        assert measure_of(body, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["available_from"] is None

    def test_the_two_horizons_are_named_what_the_response_schema_names_them(
            self):
        """One spelling of each, held between the module that fills them and the
        schema that publishes them. ADR-0007 §3 makes both final, so a typo on
        either side is a published name nobody can take back."""
        published = set(EconomicsOut.model_fields)
        assert ECONOMIC_HORIZON_FIELD in published
        assert MEASUREMENT_HORIZON_FIELD in published
        assert AVAILABLE_FROM_FIELD in set(EconomicMeasureOut.model_fields)

    def test_a_window_outside_the_horizon_reads_the_state_and_never_a_zero(
            self):
        """AC 2, on the one shape guaranteed a row: an ungrouped, unbucketed
        question over a stretch the platform no longer holds.

        Before this ticket that row was ZEROS with every state `known` — a
        tenant asking what a released period cost was told it cost nothing.
        """
        opens = self.horizon() - timedelta(days=200)
        body = ask(self.key, measures=ALL_FOUR, start_date=opens.isoformat(),
                   end_date=(opens + timedelta(days=30)).isoformat()).json()

        assert len(body["rows"]) == 1
        for measure in ALL_FOUR:
            entry = measure_of(body, measure)
            assert entry["status"] == (
                MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON), measure
            assert entry["available_from"] == self.horizon().isoformat()
            assert entry["amount_micros"] is None
            assert entry["event_count"] is None

    def test_the_state_is_published_as_one_of_the_registry_s_five(self):
        """The contract half of the same payment: the field carries the concept
        and the document enumerates the whole set, rather than a bare string
        with a hand-written sentence standing in for it."""
        marker = MeasureStatus.__metadata__[0].json_schema_extra
        assert marker == {"x-ubb-concept": "measure_status"}
        assert MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON in (
            MEASURE_STATUS_VALUES)
        assert len(MEASURE_STATUS_VALUES) == 5

    def test_the_bound_is_stated_beside_the_horizon_and_is_not_raised(self):
        """AC 6: *six years available* and *at most 366 days per request* are
        two numbers that do not compose on their own, so the published
        description states them TOGETHER — and the bound itself is untouched,
        because raising it or adding an export path is a capacity decision and
        #194's.

        Read off the operation's own published description rather than off the
        docstring, because the description is what a caller gets.
        """
        published = describe(ECONOMICS)
        assert str(REPORT_WINDOW_MAX_DAYS) in published
        assert str(HOURLY_REPORT_WINDOW_MAX_DAYS) in published
        assert ECONOMIC_HORIZON_FIELD in published
        assert MEASUREMENT_HORIZON_FIELD in published
        # And the bound is the one the routes this query collapses enforce, not
        # a wider one this ticket helped itself to.
        assert (REPORT_WINDOW_MAX_DAYS, HOURLY_REPORT_WINDOW_MAX_DAYS) == (
            366, 92)

        # ⚠ THE HORIZON IS SPELLED IN WORDS ON A PUBLISHED SURFACE, SO THE ONLY
        # THING THAT CAN HOLD THE TWO TOGETHER IS A LITERAL HERE. The two bounds
        # above are read off their constants, so moving either turns this red on
        # its own; `ECONOMIC_RETENTION_YEARS` cannot be, because a description
        # is prose and "six years" is how a promise reads to the tenant who was
        # given it. So the constant is pinned to the English beside it: change
        # the constant and this fails, naming every surface that spells it.
        assert ECONOMIC_RETENTION_YEARS == 6, (
            "the horizon moved, and it is spelled IN WORDS on surfaces no "
            "gate reads: this route's description, `EconomicsOut`'s field "
            "docs, `core/retention.py`'s module docstring, "
            "`docs/conventions/api-contract.md` and "
            "`apps/metering/CONTEXT.md`. Re-run `grep -rin 'six year'` for "
            "the live list — no per-file count is given here on purpose, "
            "because one would be the next thing to go stale — re-word every "
            "hit, then this line")
        assert "six years" in published
