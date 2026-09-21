"""G14's four `kind` discriminator pins (#154 §3.8, #187 §28, #189 §22).

**THIS MODULE IS WHERE THE MANIFEST ROW RUNS, AND THE ROW IS INSTALLED.** G14
states four pins. #417 landed the column all four are about, found that only two
of them had a subject to gate, and took the escape the row's notes authorised:
it re-owned the row to slice 7 rather than installing half a gate, and wrote
pins 2 and 4 here to guard its own new column in the meantime. Slice 7 built
the other two's subjects — the one economic query that computes the events
measure (#499), and the single surface the five analytics routes collapsed into
(#501) — and #511 wrote pins 1 and 3 here and installed the row. G14's
`enforced_by` in `gates/manifest.yaml` names a node of every pin, all in this
module.

1. `recorded_events` counts `metered_usage` only — slice 7's, through the one
   query's route, against a charge the real close projected. #499's own tests
   already assert the exclusion at the read contract
   (`apps/metering/tests/test_the_one_economic_query.py`) and, through the
   route, on the event-type axis (`TestTheCountAndTheChargeItMustNotCount` in
   `api/v1/tests/test_the_one_economic_query.py`); this one states it in the
   row's terms, over every kind the registry declares.
2. `Task.event_count` counts `metered_usage` only — slice 5's.
3. The provider and measurement analytics exclude `task_charge` — slice 7's, on
   the one surface they collapsed into, where *excluded* means credited to no
   provider and filed under no heading, and never dropped from the answer.
4. Revenue and monetary totals may include both kinds, per their economic
   fields — slice 5's.

⚠ **PINS 2 AND 4 PULL IN OPPOSITE DIRECTIONS AND THAT IS THE WHOLE POINT.** A
charge posting is a real posting carrying real revenue, so every MONETARY total
must include it or a tenant's own margin under-reports what they sold. It is not
a reported event, so every COUNT of events must exclude it or a per-event
average, a rate limit and a spend-per-call figure all quietly gain a
denominator nobody billed. A rule of the shape *charge postings are/are not
counted* would get one of the two wrong; what decides is the ECONOMIC FIELD each
measure is about.

⚠ **PIN 1 IS NOT THE COUNT ON THE PER-CUSTOMER COST TOTALS, AND WHOEVER FINDS
THAT COUNT FIRST MUST NOT TAKE IT FOR ONE.** `get_customer_cost_totals` carries
an `event_count`, and it counts every posting including a projection. That is
NOT pin 1 and must not be read as it, nor "fixed" to agree with it: pin 1 is
about `recorded_events`, whose own query excludes the charge posting kind, and
the count that read carries is a denominator for its own totals rather than a
claim about what was reported. The two answer different questions from the same
rows, which is exactly why one of them is a pin and the other is not.
"""
import uuid
from datetime import date, timedelta

import pytest

from api.v1.tests.test_a_delivered_unit_of_work_is_charged_once import (
    SOLD_PER_EVENT, THE_AGREED_PRICE,
)
from api.v1.tests.test_the_charge_reaches_the_rails_as_one_marked_posting import (
    A_METERED_SALE, ProjectionTestBase,
)
from api.v1.tests._helpers import (
    MONEY_MEASURES, ask, measure_of, tenant_wide_money,
)
from apps.metering.pricing.tests._helpers import (
    PRICED_QUANTITY, a_rule_that_prices_what_it_measures, priced_at,
)
from apps.metering.queries import (
    GROUPED_VALUE_KEY, GROUPED_VALUE_STATUS_KEY, VALUE_NOT_APPLICABLE,
    VALUE_RECORDED, get_customer_cost_totals, grouping_axis,
)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.event_types.models import (
    EventType, Measurement, MeasurementConcept,
)
from apps.platform.work.models import Task
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD, ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE, ANALYTICS_MEASURE_GROSS_MARGIN,
    ANALYTICS_MEASURE_RECORDED_EVENTS, ANALYTICS_MEASURE_SUPPLIER_COGS,
    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT, COSTING_METHOD_CALCULATED,
    SOURCE_KIND_CALLER_SUPPLIED, UNIT_CALL, USAGE_EVENT_KIND_METERED_USAGE,
    USAGE_EVENT_KIND_TASK_CHARGE, USAGE_EVENT_KIND_VALUES,
)

#: A window wide enough to hold everything a case in this module records. The
#: reads under test window on dates, and a case whose fixture fell outside its
#: own window would assert an empty total in both directions.
WINDOW_START = date.today() - timedelta(days=1)
WINDOW_END = date.today() + timedelta(days=2)

#: The supplier every metered call in pins 1 and 3 names, and what each one
#: cost. A real provider on the metered side is what gives the provider axis a
#: row the charge could be wrongly credited to; with none, both kinds would sit
#: under an absent value and pin 3 would be comparing two absences.
A_PROVIDER = "openai"
A_SUPPLIER_COST = 3_000_000

#: The heading a tenant files the metered quantity under, for pin 3's
#: measurement half.
A_HEADING = "billable_calls"

PROVIDER_AXIS = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "provider")
EVENT_TYPE_AXIS = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "event_type")
MEASUREMENT_HEADING = grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                                    ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)


def tenant_wide(tenant_id):
    """PIN 4's tenant-wide read, over this module's window.

    It read the daily revenue rollup until #501 deleted that rollup with its
    route; the one economic query answers the same question. The claims did not
    change — both kinds count, per their ECONOMIC FIELDS — and the subtraction
    that used to be published under a name suggesting a rate is now the margin
    measure, computed once at the bucket.
    """
    return tenant_wide_money(tenant_id, start_date=WINDOW_START,
                             end_date=WINDOW_END)


class ADeliveredPieceOfWorkBesideItsCalls(ProjectionTestBase):
    """PINS 1 AND 3's fixture: one posting of every kind, in one window.

    One piece of work sold at an agreed price, delivered through the real close,
    so the charge posting is the one the projection writes rather than a row
    built by hand. One metered call UNDER that work, which is the shape the
    reporting contract was written about — a piece of work sold whole, and the
    supplier calls it made. And one metered call under work priced per event,
    so the metered side carries REVENUE as well as cost, and a charge credited
    to the wrong row moves a figure that was not zero.

    The agreed price and the metered sale are distinct and neither is zero, so
    a total that picked one of them up in the wrong place cannot come out equal
    by coincidence.
    """

    METERED_CALLS = 2

    def setup_method(self):
        super().setup_method()
        a_rule_that_prices_what_it_measures(self.tenant,
                                            event_type=SOLD_PER_EVENT)
        self.delivered = self._priced_work()
        self._a_call(self.delivered)
        self._a_call(self._start(task_type=SOLD_PER_EVENT))
        closed = self._close(self.delivered)
        assert closed.status_code == 200, closed.content

    def _a_call(self, task_id):
        """One metered call under ``task_id``, naming its provider and cost.

        Not `_a_metered_sale`: that one declares a price rule on every call and
        names no supplier, and the provider axis needs both a provider and a
        supplier cost to have a row the charge could be wrongly credited to.
        The rule is declared once, in `setup_method`.
        """
        UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type=SOLD_PER_EVENT, task_id=task_id, provider=A_PROVIDER,
            provider_cost_micros=A_SUPPLIER_COST,
            measurements=priced_at(A_METERED_SALE))

    def _ask(self, **params):
        """One question to the one economic query's route, over the window."""
        answered = ask(self.raw_key, start_date=WINDOW_START.isoformat(),
                       end_date=WINDOW_END.isoformat(), **params)
        assert answered.status_code == 200, answered.content
        return answered.json()


@pytest.mark.django_db
class TestTheEventsMeasureCountsTheMeteredKindOnly(
        ADeliveredPieceOfWorkBesideItsCalls):
    """PIN 1 — `recorded_events` counts `metered_usage` only.

    Asked through the route of the one economic query, which is the measure's
    only implementation and the surface a caller reads it on. ⚠ **NOT the count
    on the per-customer cost totals**, which counts the projection too; the
    module docstring says why that one is not a pin.
    """

    def _counted(self):
        return self._ask(measures=[ANALYTICS_MEASURE_RECORDED_EVENTS,
                                   ANALYTICS_MEASURE_CUSTOMER_REVENUE])

    def test_the_count_is_the_metered_calls_and_not_the_charge(self):
        assert measure_of(self._counted(), ANALYTICS_MEASURE_RECORDED_EVENTS
                          )["event_count"] == self.METERED_CALLS

    def test_the_charge_it_left_out_is_inside_the_same_answer(self):
        """THE VACUITY GUARD, read off the same response as the count. A
        charge dated outside the window would satisfy the case above by never
        having been in scope; the revenue beside the count says it was, because
        the agreed price is in it."""
        assert measure_of(self._counted(), ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == THE_AGREED_PRICE + A_METERED_SALE

    def test_every_kind_the_registry_declares_is_in_scope(self):
        """WHAT MAKES *ONLY* A CLAIM. With a posting of every kind the registry
        declares in the fixture — and the case above showing that the one the
        count leaves out is inside the answer's window — a count equal to the
        metered calls has been checked against every alternative there is.

        The query excludes the charge kind by name rather than admitting the
        metered kind by name, and the two agree only while the registry declares
        exactly these two. The day it declares a third this goes red, and
        whoever adds it decides here whether it is counted — rather than the
        count quietly taking it because it is not the one kind the query names.
        """
        kinds = list(Posting.objects.filter(tenant=self.tenant)
                     .values_list("kind", flat=True))
        assert set(kinds) == USAGE_EVENT_KIND_VALUES
        assert kinds.count(USAGE_EVENT_KIND_METERED_USAGE) == self.METERED_CALLS


@pytest.mark.django_db
class TestAChargePostingDoesNotInflateTheEventCount(ProjectionTestBase):
    """PIN 2 — `Task.event_count` counts `metered_usage` only.

    The column is a running counter maintained by `TaskService.accumulate_cost`
    on every metered recording. The projection does not call it, and this is
    what says so from outside: a caller reading *this unit of work handled N
    calls* must not be told a number that includes the row UBB wrote to charge
    for the work.
    """

    def test_delivering_priced_work_leaves_the_event_count_where_it_was(self):
        started = self._priced_work()
        self._a_metered_sale(started)
        before = Task.objects.get(id=started).event_count

        self._close(started)

        assert before == 1
        assert Task.objects.get(id=started).event_count == before

    def test_the_projection_is_nonetheless_attributed_to_that_unit_of_work(
            self):
        """THE DISCRIMINATING HALF, and without it the pin above is satisfied
        by a projection that forgot to name the unit of work at all.

        The posting DOES carry `task_id` — that is what puts this revenue in the
        same analytics bucket as that unit's COGS. What it does not do is
        increment the counter. A projection detached from the work would pass
        every count assertion here and lose the attribution the whole projection
        exists for.
        """
        started = self._priced_work()

        self._close(started)

        projection = self._projection_of(started)
        assert str(projection.task_id) == str(started)
        assert Task.objects.get(id=started).event_count == 0

    def test_a_unit_of_work_with_no_metered_calls_still_counts_none(self):
        """The zero case, which is the one a fixed-price tenant lives in. A
        counter that gained one per charge would report every delivered unit of
        work as having handled exactly one call."""
        started = self._priced_work()

        self._close(started)

        assert Task.objects.get(id=started).event_count == 0

    def test_the_billed_total_on_the_unit_of_work_is_unmoved_too(self):
        """⚠ THE COUNTER AND THE MONEY MOVE IN ONE `UPDATE`, so this is not a
        second claim — it is what pin 2 costs, said out loud rather than left
        for a reader to discover.

        `accumulate_cost` writes `event_count` and both running totals in one
        statement, so a projection cannot add the revenue without adding to the
        count. The unit's own billed total therefore stays at what its METERED
        calls billed, and the agreed price lives on the Charge and on the
        posting. Pin 4 below is what makes that revenue visible where it is
        supposed to be visible.

        ⚠ **AND UNDER THIS REGIME WHAT ITS METERED CALLS BILLED IS NOTHING
        (#418).** Every posting under a piece of work sold at one agreed price
        carries `not_applicable` rather than an amount, because the customer
        revenue for it is the agreed price. So the total is zero from BOTH
        directions — the projection does not add to it and the metered calls
        have nothing to add — and the assertion says so in both, because a bare
        `== 0` would be satisfied by a fixture that recorded no calls at all.
        """
        started = self._priced_work()
        metered = self._a_metered_sale(started)

        self._close(started)

        assert metered.billed_cost_micros is None
        assert Task.objects.get(id=started).total_billed_cost_micros == 0


@pytest.mark.django_db
class TestTheProviderAndMeasurementAnalyticsExcludeTheChargeKind(
        ADeliveredPieceOfWorkBesideItsCalls):
    """PIN 3 — the provider and measurement analytics exclude `task_charge`.

    Written against the one surface both became when #501 collapsed the five:
    the economic query grouped by the provider axis, and grouped by the heading
    a tenant files its measured quantities under.

    ⚠ **EXCLUDED MEANS CREDITED TO NO PROVIDER, AND NEVER DROPPED.** The
    reporting contract this pin comes from keeps a charge posting out of
    provider analytics because it does not represent a provider operation. The
    one query also refuses to drop money silently (#189 §5), so on the provider
    axis the charge's revenue stays in the answer — on the row whose provider
    says the question DOES NOT APPLY, and on no provider's row. A pin asserting
    that row away would be asserting the defect §5 removed.
    """

    def _by_provider(self):
        body = self._ask(measures=MONEY_MEASURES, group_by=[PROVIDER_AXIS])
        return {(row[GROUPED_VALUE_KEY][0], row[GROUPED_VALUE_STATUS_KEY][0]):
                {entry["measure"]: entry["amount_micros"]
                 for entry in row["measures"]}
                for row in body["rows"]}

    def test_no_provider_is_credited_with_the_charge(self):
        """The provider's row holds the metered calls' money and nothing else:
        both calls' supplier cost, and the one sale that billed."""
        served = self._by_provider()[(A_PROVIDER, VALUE_RECORDED)]
        assert served[ANALYTICS_MEASURE_SUPPLIER_COGS] == (
            self.METERED_CALLS * A_SUPPLIER_COST)
        assert served[ANALYTICS_MEASURE_CUSTOMER_REVENUE] == A_METERED_SALE

    def test_the_charge_sits_where_the_provider_question_does_not_apply(self):
        """And not under `not_recorded`, which would say a provider served it
        and UBB failed to learn which — counting the charge as a provider
        operation of unknown origin, which is inclusion under another name."""
        rows = self._by_provider()
        assert set(rows) == {(A_PROVIDER, VALUE_RECORDED),
                             (None, VALUE_NOT_APPLICABLE)}
        charged = rows[(None, VALUE_NOT_APPLICABLE)]
        assert charged[ANALYTICS_MEASURE_CUSTOMER_REVENUE] == THE_AGREED_PRICE
        assert charged[ANALYTICS_MEASURE_SUPPLIER_COGS] == 0

    def test_excluding_it_from_every_provider_drops_none_of_its_money(self):
        """THE OTHER DIRECTION. An exclusion that removed the row would pass
        both cases above and lose the tenant's biggest sale from the answer."""
        grouped = sum(row[ANALYTICS_MEASURE_CUSTOMER_REVENUE]
                      for row in self._by_provider().values())
        assert grouped == THE_AGREED_PRICE + A_METERED_SALE
        assert grouped == measure_of(self._ask(measures=MONEY_MEASURES),
                                     ANALYTICS_MEASURE_CUSTOMER_REVENUE
                                     )["amount_micros"]

    def _file_the_metered_quantity_under_a_heading(self):
        """What a tenant does to opt in: declare the Event Type's quantity and
        file it under a heading of its own.

        Done AFTER the recordings, which the heading allows because it reads
        its membership live — and which keeps the declaration from changing how
        the calls above were costed or priced, so both pins stand on one
        fixture.
        """
        heading = MeasurementConcept.objects.create(tenant=self.tenant,
                                                    key=A_HEADING)
        event_type = EventType.objects.create(
            tenant=self.tenant, key=SOLD_PER_EVENT,
            costing_method=COSTING_METHOD_CALCULATED)
        Measurement.objects.create(
            event_type=event_type, code=PRICED_QUANTITY, unit=UNIT_CALL,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED, concept=heading)

    def test_the_heading_counts_the_metered_calls_and_never_the_charge(self):
        """One row, holding both calls, and no row at all for the charge — not
        even a `not_applicable` one, because a projection carries no quantity
        to file. The count is the only measure this axis answers, so it is the
        only door the charge could come in by.

        ⚠ **THREE THINGS KEEP THE CHARGE OFF THIS AXIS, AND THEY HOLD
        DIFFERENT HALVES OF IT.** The charge makes no ROW because the
        projection writes no quantity and names no Event Type, which is half of
        the pair a quantity is filed by — either suffices. The fold's own skip
        of the charge kind holds only the COUNT, since it still opens a row for
        every pair it sees. So a projection that learned to carry a quantity
        under the calls' own Event Type would join their row and count nothing,
        and this case would stay green; one filed under any other pair would
        open a row of its own at zero, and turn it red.

        ⚠ The single row is also this case's vacuity guard: with nothing filed
        under the heading the answer is empty, and an assertion that the charge
        is absent from an empty answer would hold over nothing.
        """
        self._file_the_metered_quantity_under_a_heading()

        body = self._ask(measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
                         group_by=[MEASUREMENT_HEADING, EVENT_TYPE_AXIS])

        assert [(row[GROUPED_VALUE_KEY],
                 measure_of(body, ANALYTICS_MEASURE_RECORDED_EVENTS,
                            row=index)["event_count"])
                for index, row in enumerate(body["rows"])] == [
            ([A_HEADING, SOLD_PER_EVENT], self.METERED_CALLS)]


@pytest.mark.django_db
class TestRevenueAndMonetaryTotalsIncludeBothKinds(ProjectionTestBase):
    """PIN 4 — both kinds count, per their ECONOMIC FIELDS.

    Not *both kinds are added everywhere*: a projection contributes revenue and
    contributes nothing to supplier cost, because those are the fields it
    carries. A total that excluded it would under-report what the tenant sold;
    one that added its zero supplier cost as though it were a measured call
    would be arithmetic nobody chose, which is why the cost side is asserted
    beside the revenue side rather than left implied.
    """

    def _totals(self):
        return get_customer_cost_totals(
            str(self.tenant.id), str(self.customer.id),
            WINDOW_START, WINDOW_END)

    def test_the_revenue_total_holds_the_agreed_price_and_the_metered_sale(
            self):
        """The metered sale comes from work priced per event (#418) —
        `_a_second_sale_that_really_bills` carries the reason."""
        started = self._priced_work()
        self._a_second_sale_that_really_bills()

        self._close(started)

        measures = tenant_wide(self.tenant.id)
        assert measures[ANALYTICS_MEASURE_CUSTOMER_REVENUE][
            "amount_micros"] == THE_AGREED_PRICE + A_METERED_SALE

    def test_the_supplier_total_is_the_metered_cost_alone(self):
        """The projection's zero is real and settled, so it adds nothing — and
        `unresolved_event_count` stays where it was, because a charge posting is
        not a cost UBB failed to learn."""
        started = self._priced_work()
        UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type=SOLD_PER_EVENT, task_id=started,
            provider_cost_micros=3_000_000)

        self._close(started)

        cost = tenant_wide(self.tenant.id)[ANALYTICS_MEASURE_SUPPLIER_COGS]
        assert cost["amount_micros"] == 3_000_000
        assert cost["unresolved_event_count"] == 0

    def test_the_margin_nets_the_agreed_price_against_the_work_it_cost(self):
        """WHAT PIN 4 IS FOR. Revenue and COGS for one unit of work land in one
        figure because both are postings, which is the whole argument for a
        projection over a revenue entity of its own."""
        started = self._priced_work()
        UsageService.record_usage(
            self.tenant, self.customer, f"call-{uuid.uuid4()}",
            event_type=SOLD_PER_EVENT, task_id=started,
            provider_cost_micros=3_000_000)

        self._close(started)

        measures = tenant_wide(self.tenant.id)
        assert measures[ANALYTICS_MEASURE_GROSS_MARGIN][
            "amount_micros"] == THE_AGREED_PRICE - 3_000_000

    def test_the_customers_monetary_totals_hold_it_too(self):
        """The per-customer read, which is what a bill is reconciled against.
        A revenue figure that appeared in the tenant-wide rollup and not here
        would put one customer's invoice and the tenant's own margin report in
        disagreement about the same sale.

        The metered sale is under work priced per event, for the reason
        `_a_second_sale_that_really_bills` gives.
        """
        started = self._priced_work()
        self._a_second_sale_that_really_bills()

        self._close(started)

        totals = self._totals()
        assert totals["billed_cost_micros"] == THE_AGREED_PRICE + A_METERED_SALE
        assert totals["unpriced_event_count"] == 0

    def test_a_total_that_dropped_the_projection_would_be_visibly_short(self):
        """THE VACUITY GUARD. Every assertion above is an equality, and an
        equality is satisfied by a fixture where the two kinds happen to sum to
        the same thing whichever one is missing. This is the case that says the
        numbers are different: the agreed price and the metered sale are
        distinct amounts, and both are inside the total.

        The metered sale is under work priced per event, and here that is
        load-bearing rather than tidy: a metered posting that billed nothing
        would leave the total equal to the agreed price alone, and this case
        would be comparing one number against an unrelated constant.
        """
        started = self._priced_work()
        self._a_second_sale_that_really_bills()

        self._close(started)

        assert THE_AGREED_PRICE != A_METERED_SALE
        assert self._postings_on(started).filter(
            kind=USAGE_EVENT_KIND_TASK_CHARGE).count() == 1
        assert self._totals()["billed_cost_micros"] > A_METERED_SALE
        assert self._totals()["billed_cost_micros"] > THE_AGREED_PRICE
