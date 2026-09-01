"""The `kind` discriminator pins slice 5 can write — G14's pins 2 and 4
(#154 §3.8, #187 §28).

**THIS MODULE IS NAMED FOR A MANIFEST ROW, AND THE ROW IS STILL OWED.** G14
states four pins. #417 landed the column all four are about, found that only two
of them have a subject to gate, and took the escape the row's own notes
authorise: it re-owned the row to slice 7 rather than installing half a gate.
These two are written anyway, and that is not a contradiction — they guard THIS
slice's own new column, and without them nothing stops a charge posting
inflating a unit of work's event count between here and slice 7.

1. `recorded_events` counts `metered_usage` only — **not pinnable**, slice 7's.
   The measure exists only as vocabulary: a registry value and a generated
   constant, with no query computing it anywhere.
2. `Task.event_count` counts `metered_usage` only — **PINNABLE, and here.** The
   column exists today, in this slice's own app.
3. The provider and measurement analytics exclude `task_charge` — **not
   pinnable in final form**, slice 7's. The surfaces exist, and slice 7
   collapses five of them into one, so a gate written against the five would be
   rewritten rather than kept.
4. Revenue and monetary totals may include both kinds, per their economic
   fields — **PINNABLE, and here.** The reads exist today.

⚠ **PINS 2 AND 4 PULL IN OPPOSITE DIRECTIONS AND THAT IS THE WHOLE POINT.** A
charge posting is a real posting carrying real revenue, so every MONETARY total
must include it or a tenant's own margin under-reports what they sold. It is not
a reported event, so every COUNT of events must exclude it or a per-event
average, a rate limit and a spend-per-call figure all quietly gain a
denominator nobody billed. A rule of the shape *charge postings are/are not
counted* would get one of the two wrong; what decides is the ECONOMIC FIELD each
measure is about.

⚠ **PIN 1 IS NOT ASSERTED HERE AND ITS ABSENCE IS DELIBERATE.**
`get_customer_cost_totals` and the daily rollup beside it carry an
`event_count`, and it counts every posting including a projection. That is
NOT pin 1 arriving early and must not be read as it: pin 1 is about
`recorded_events`, a declared measure with no query behind it, and the counts
those reads carry are denominators for their own totals rather than a claim
about what was reported. Slice 7 builds the measure and the row stays owed
until it does.
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
from apps.metering.queries import (
    get_customer_cost_totals, get_revenue_analytics,
)
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.work.models import Task
from core.vocabulary import USAGE_EVENT_KIND_TASK_CHARGE

#: A window wide enough to hold everything a case in this module records. The
#: reads under test window on dates, and a case whose fixture fell outside its
#: own window would assert an empty total in both directions.
WINDOW_START = date.today() - timedelta(days=1)
WINDOW_END = date.today() + timedelta(days=2)


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
        """⚠ **THE METERED SALE COMES FROM WORK PRICED PER EVENT (#418).** A
        metered posting under the FIXED-price piece of work bills nothing now —
        its revenue is the agreed price this case is already adding up — so
        leaving it there would have made the two amounts one amount counted
        twice, and the sum below arithmetic about nothing.
        """
        started = self._priced_work()
        self._a_metered_sale(self._start(task_type=SOLD_PER_EVENT))

        self._close(started)

        totals = get_revenue_analytics(str(self.tenant.id))
        assert totals["total_billed_cost_micros"] == (
            THE_AGREED_PRICE + A_METERED_SALE)

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

        totals = get_revenue_analytics(str(self.tenant.id))
        assert totals["total_provider_cost_micros"] == 3_000_000
        assert totals["unresolved_event_count"] == 0

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

        totals = get_revenue_analytics(str(self.tenant.id))
        assert totals["total_markup_micros"] == THE_AGREED_PRICE - 3_000_000

    def test_the_customers_monetary_totals_hold_it_too(self):
        """The per-customer read, which is what a bill is reconciled against.
        A revenue figure that appeared in the tenant-wide rollup and not here
        would put one customer's invoice and the tenant's own margin report in
        disagreement about the same sale.

        The metered sale is under work priced per event, for the reason the
        revenue case above gives.
        """
        started = self._priced_work()
        self._a_metered_sale(self._start(task_type=SOLD_PER_EVENT))

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

        The metered sale is under work priced per event, for the reason the
        revenue case above gives — and here it is load-bearing rather than
        tidy, because a metered posting that billed nothing would leave the
        total equal to the agreed price alone and this case would be comparing
        one number against an unrelated constant.
        """
        started = self._priced_work()
        self._a_metered_sale(self._start(task_type=SOLD_PER_EVENT))

        self._close(started)

        assert THE_AGREED_PRICE != A_METERED_SALE
        assert self._postings_on(started).filter(
            kind=USAGE_EVENT_KIND_TASK_CHARGE).count() == 1
        assert self._totals()["billed_cost_micros"] > A_METERED_SALE
        assert self._totals()["billed_cost_micros"] > THE_AGREED_PRICE
