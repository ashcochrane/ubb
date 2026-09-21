"""The one economic query at the read contract (#499, slice 7 §2–§5, §10, §15).

**What is asserted HERE rather than through a route**, because the slice's seam
rule puts everything a caller can observe on the route and the route module does
that:

* **Each measure aggregated from its own canonical source**, which is a claim
  about where a number came from and not about the number. A route can show the
  totals agree; only this can show they were not all read off one column.
* **Margin as a bucket-level subtraction.** The wire carries the result either
  way; what distinguishes the two is whether a subtraction ever happened per
  row, and that is visible here.
* **The BOUNDARY of the count's comparison rule**, which is a property of the
  whole request: what has to be shown is the one shape refused against the three
  that must not be, and a route can express one of the four at a time.
* **The revenue rows this product does not hold**, whose absence the query
  refuses — a request no caller can make, because the route always supplies them.
* **The list of axes a charge posting cannot carry**, pinned against a charge
  actually projected, so the day the projection learns to carry one the constant
  goes red instead of quietly answering `not_applicable` about it.
* **That the rebuild reads no key out of the open bag** — a claim about the
  absence of a capability, which no response can show.

⚠ **AND WHAT IS DELIBERATELY NOT HERE.** The three bucket grains, the refusal
codes and the charge exclusion on the wire are driven through the ROUTE and were
removed from this module rather than kept as a second copy: the slice's seam rule
reserves this file for what a route cannot express, and a duplicate proves only
that two tests agree with each other.

⚠ **THIS MODULE NEVER SPELLS THE PARAMETERS THIS VOCABULARY REPLACES.** The
registry retires them, the sweep refuses a living file that names one, and a new
file spelling one fails before any of this runs.
"""
import ast
import inspect
import uuid
from datetime import date, datetime, timedelta, timezone as dt_timezone

from django.test import TestCase, override_settings

from apps.metering import queries
from apps.metering.pricing.models import Charge
from apps.metering.pricing.services.charge_projection import project_the_charge
from apps.metering.queries import (
    AXES_A_CHARGE_POSTING_CANNOT_CARRY, BUCKET_DAY, ECONOMIC_MEASURES,
    GROUPED_VALUE_KEY, GROUPED_VALUE_STATUS_KEY, EconomicFilters,
    VALUE_NOT_APPLICABLE, VALUE_NOT_RECORDED, VALUE_RECORDED, economic_refusal,
    economics, grouping_axis,
)
from apps.metering.usage.models import Posting, PostingMeasurement
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType, Measurement, MeasurementConcept)
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant
from apps.platform.work.models import Task
from core.cost_totals import UNRESOLVED_EVENT_COUNT_KEY
from core.retention import MEASUREMENT_RETENTION_DAYS_SETTING
from core.vocabulary import (
    ANALYTICS_GROUPING_KIND_FIELD, ANALYTICS_GROUPING_KIND_ROLLUP,
    ANALYTICS_MEASURE_CUSTOMER_REVENUE,
    ANALYTICS_MEASURE_GROSS_MARGIN, ANALYTICS_MEASURE_RECORDED_EVENTS,
    ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT,
    COSTING_METHOD_CALCULATED, COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED, MEASURE_STATUS_INCOMPLETE, MEASURE_STATUS_KNOWN,
    MEASURE_STATUS_NOT_APPLICABLE,
    MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
    MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON,
    MEASURE_STATUS_VALUES, PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN, SOURCE_KIND_CALLER_SUPPLIED, UNIT_TOKEN,
    UNRESOLVED_REASON_COST_RATE_MISSING, USAGE_EVENT_KIND_TASK_CHARGE,
)

CUSTOMER_AXIS = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "customer")
PROVIDER_AXIS = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "provider")
EVENT_TYPE_AXIS = grouping_axis(ANALYTICS_GROUPING_KIND_FIELD, "event_type")
MEASUREMENT_ROLLUP = grouping_axis(ANALYTICS_GROUPING_KIND_ROLLUP,
                                   ANALYTICS_ROLLUP_MEASUREMENT_CONCEPT)
ALL_FOUR = list(ECONOMIC_MEASURES)
MONEY = [ANALYTICS_MEASURE_SUPPLIER_COGS, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
         ANALYTICS_MEASURE_GROSS_MARGIN]

#: The half-open window every fixture below records into, stated once.
WINDOW = (date(2026, 3, 1), date(2026, 3, 31))
MARCH = datetime(2026, 3, 10, 9, 30, tzinfo=dt_timezone.utc)


def a_posting(tenant, customer, key, **overrides):
    """One recorded posting, priced and costed unless a case says otherwise.

    The defaults make both sides RESOLVED and DIFFERENT, so a measure that
    echoed its input instead of computing would answer wrongly: a fixture where
    the price equals the cost makes the margin equal zero whatever the code
    does, and every assertion about it is then satisfiable by the wrong number.
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


def measure_of(answer, measure, row=0):
    """One measure off one row of an answer, by name rather than by position."""
    for entry in answer["rows"][row]["measures"]:
        if entry["measure"] == measure:
            return entry
    raise AssertionError(f"{measure!r} is not in the answer's row {row}")


class EachMeasureComesFromItsOwnSourceTest(TestCase):
    """§3: the measures no longer share an origin, so each is aggregated from
    its own canonical fact source.

    The discriminating fixture is a charge posting beside a metered one. It
    carries revenue and no supplier cost and is not work — so a query that read
    all four measures off one grouped aggregate over one column answers at least
    one of them wrongly, whichever column it chose.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "i1")
        a_posting(cls.tenant, cls.customer, "i2")
        task = Task.objects.create(tenant=cls.tenant, customer=cls.customer,
                                   balance_snapshot_micros=0)
        charge = Charge.objects.create(
            tenant=cls.tenant, task=task, amount_micros=2_500_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MARCH, charged_at=MARCH, idempotency_key="charge-1")
        cls.projected = project_the_charge(charge)

    def _answer(self):
        return economics(self.tenant.id, measures=ALL_FOUR,
                         filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                         covered_periods=(), contributed_revenue=())

    def test_the_count_excludes_the_charge_posting_kind(self):
        """§10: a Task must not count its own invoice as work."""
        assert measure_of(self._answer(),
                          ANALYTICS_MEASURE_RECORDED_EVENTS)["event_count"] == 2

    def test_the_count_includes_the_recorded_postings_it_does_not_exclude(self):
        """THE OTHER DIRECTION, and it is the half that makes the first one
        evidence. An exclusion that excluded everything would satisfy the test
        above exactly as the right one does."""
        Posting.objects.filter(kind=USAGE_EVENT_KIND_TASK_CHARGE).delete()
        assert measure_of(self._answer(),
                          ANALYTICS_MEASURE_RECORDED_EVENTS)["event_count"] == 2

    def test_revenue_includes_the_charge_the_count_excluded(self):
        """The same row is not work and IS money, which is the whole reason the
        two measures cannot share a source."""
        assert measure_of(self._answer(),
                          ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == 2_000_000 + 2_500_000

    def test_cost_is_the_supplier_side_and_not_the_customer_side(self):
        assert measure_of(self._answer(),
                          ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == 800_000

    def test_only_the_requested_measures_are_answered(self):
        answer = economics(self.tenant.id,
                           measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]))
        assert [entry["measure"] for entry in answer["rows"][0]["measures"]] == [
            ANALYTICS_MEASURE_SUPPLIER_COGS]


class TheChargePostingsBlankAxesArePinnedToItsWriterTest(TestCase):
    """The constant that decides `not_applicable`, held to a projected charge.

    A hand-built `Posting` would prove nothing here: the claim is about what the
    PROJECTION writes, so the fixture projects one and reads the row back.
    """

    def test_exactly_the_declared_axes_come_out_blank_on_a_projection(self):
        tenant = Tenant.objects.create(name="T", products=["metering"])
        customer = Customer.objects.create(tenant=tenant, external_id="c1")
        task = Task.objects.create(tenant=tenant, customer=customer,
                                   task_type="summarise",
                                   balance_snapshot_micros=0)
        charge = Charge.objects.create(
            tenant=tenant, task=task, amount_micros=1_000_000, currency="usd",
            agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MARCH, charged_at=MARCH, idempotency_key="charge-1")
        posting = project_the_charge(charge)

        blank = {name for name, _ in queries.ALWAYS_PRESENT_AXES
                 if name != "customer" and not getattr(posting, name)}
        assert blank == set(AXES_A_CHARGE_POSTING_CANNOT_CARRY), (
            "a projection's blank axes have moved, so the list that decides "
            "`not_applicable` now answers about the wrong ones")
        # The non-subjects, named so an omission cannot read as deliberate: the
        # kind of work IS copied from the Charge and is a real value.
        assert posting.task_type == "summarise"


class AnAbsentValueSaysWhichOfTwoThingsItMeansTest(TestCase):
    """§5's second prohibition: *we do not know which provider* and *the
    question does not apply* are two different facts and get two different
    statuses.

    The fixture puts both in one answer at once, which is the only shape that
    can tell a correct implementation from one that picked a single sentinel.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "i1", provider="openai")
        a_posting(cls.tenant, cls.customer, "i2", provider="")
        task = Task.objects.create(tenant=cls.tenant, customer=cls.customer,
                                   balance_snapshot_micros=0)
        project_the_charge(Charge.objects.create(
            tenant=cls.tenant, task=task, amount_micros=1_000_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MARCH, charged_at=MARCH, idempotency_key="charge-1"))

    def test_the_two_absences_are_two_rows_with_two_statuses(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]), covered_periods=(), contributed_revenue=())
        seen = {(row[GROUPED_VALUE_KEY][0], row[GROUPED_VALUE_STATUS_KEY][0])
                for row in answer["rows"]}
        assert seen == {("openai", VALUE_RECORDED),
                        (None, VALUE_NOT_RECORDED),
                        (None, VALUE_NOT_APPLICABLE)}

    def test_neither_absence_is_dropped_from_the_totals(self):
        """§5's third prohibition, at the row level: the surfaces this replaces
        excluded a blank axis from the grouped query altogether, so the money on
        those rows left the answer without saying so."""
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]), covered_periods=(), contributed_revenue=())
        grouped = sum(measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                                 row=index)["amount_micros"]
                      for index in range(len(answer["rows"])))
        whole = economics(self.tenant.id, measures=MONEY,
                          filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                          covered_periods=(), contributed_revenue=())
        assert grouped == measure_of(
            whole, ANALYTICS_MEASURE_CUSTOMER_REVENUE)["amount_micros"]


class TheMarginIsSubtractedAtTheBucketTest(TestCase):
    """§3/#153 §2: margin is a bucket-level subtraction, never a row-level one.

    The discriminating fixture is a bucket holding one event that earned revenue
    and one that was never going to. A row-level subtraction gives the second a
    NEGATIVE margin of its own; the bucket-level one gives the bucket a single
    difference between two totals, and the two answers differ.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "earns",
                  provider_cost_micros=400_000, billed_cost_micros=1_000_000)
        a_posting(cls.tenant, cls.customer, "never-earns",
                  provider_cost_micros=300_000, billed_cost_micros=None,
                  pricing_status=PRICING_STATUS_UNKNOWN)

    def test_the_bucket_states_one_difference_between_two_totals(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=())
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] == 1_000_000 - 700_000

    def test_a_margin_exists_once_per_bucket_and_not_once_per_event(self):
        """The SHAPE claim beside the arithmetic one: a margin belongs to a
        bucket, so nothing smaller than a bucket publishes one.

        Two postings, one bucket, ONE margin. A row-level subtraction is not
        distinguishable from a bucket-level one by arithmetic — summation is
        linear — so what tells them apart is whether anything smaller than a
        bucket ever carries a margin at all, and nothing here does.
        """
        answer = economics(self.tenant.id, measures=MONEY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=())
        assert Posting.objects.filter(tenant=self.tenant).count() == 2
        assert len(answer["rows"]) == 1
        margins = [entry for row in answer["rows"] for entry in row["measures"]
                   if entry["measure"] == ANALYTICS_MEASURE_GROSS_MARGIN]
        assert len(margins) == 1


class AMarginIsOnlyAsCompleteAsBothItsInputsTest(TestCase):
    """§15's ruling: `gross_margin`'s state is derived from BOTH inputs, never
    from the revenue side alone.

    ⚠ The fixture is the one the NON-GOAL describes: a posting whose price the
    resolver was confident about over a supplier cost nobody has learned. That
    is reachable today — the pricing service consults the costing status only
    inside its margin-over-cost branch — and #473 owns the fix. What this pins
    is that the composite does not inherit the confident half's state.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "i1",
                  provider_cost_micros=None,
                  costing_status=COSTING_STATUS_UNRESOLVED,
                  unresolved_reason=UNRESOLVED_REASON_COST_RATE_MISSING,
                  billed_cost_micros=1_000_000,
                  pricing_status=PRICING_STATUS_KNOWN)

    def test_the_revenue_side_reads_known(self):
        """The premise, asserted rather than assumed: without it the test below
        would pass over a margin that was incomplete for the other reason."""
        answer = economics(self.tenant.id, measures=MONEY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=())
        assert measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["status"] == MEASURE_STATUS_KNOWN

    def test_the_margin_reads_incomplete_anyway_with_the_unresolved_count(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=())
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_INCOMPLETE
        assert measure_of(answer, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )[UNRESOLVED_EVENT_COUNT_KEY] == 1


class TheScopeRuleWithholdsRatherThanInventsTest(TestCase):
    """§5: margin is defined at a bucket only when every revenue component in
    that bucket is attributable at that bucket's grain.

    The contributed rows stand in for the revenue this product does not hold;
    they declare a customer and nothing operational, which is exactly what a
    subscription and a supplied figure declare.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "i1")

    def _contributed(self):
        return [{"window_start": WINDOW[0], "window_end": WINDOW[1],
                 "customer_id": str(self.customer.id), "source": "subscription",
                 "amount_micros": 9_000_000, "attributable_axes": ("customer",),
                 "finest_bucket": BUCKET_DAY}]

    def test_bucketed_more_finely_than_the_record_it_is_not_placed_either(self):
        """Time is the exception and it is not an unconditional one: a figure
        whose record declares a span in whole days cannot be placed inside an
        hour, so the margin is withheld exactly as at an operational axis."""
        answer = economics(self.tenant.id, measures=MONEY, bucket="hour",
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] is None
        assert answer["context"][0]["attributable_bucket"] == BUCKET_DAY

    def test_bucketed_at_the_records_own_grain_it_is_placed(self):
        """The guard on the case above: a day bucket is exactly as fine as the
        record's span, so it places and produces a margin."""
        answer = economics(self.tenant.id, measures=MONEY, bucket=BUCKET_DAY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        assert answer["context"] == []
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_KNOWN

    def test_grouped_by_customer_the_coarse_revenue_is_part_of_the_margin(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[CUSTOMER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        assert measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == 1_000_000 + 9_000_000
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_KNOWN
        assert answer["context"] == []

    def test_grouped_by_provider_it_is_neither_distributed_nor_bucketed(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        revenue = measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE)
        assert revenue["status"] == MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        # NOT DISTRIBUTED: the row states the revenue it can attribute and no
        # share of the rest. NOT ZERO either — the posting revenue is real.
        assert revenue["amount_micros"] == 1_000_000
        # NOT AN UNATTRIBUTED BUCKET: there is no extra row holding the money.
        assert len(answer["rows"]) == 1

    def test_grouped_by_provider_no_margin_is_published_at_all(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        margin = measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert margin["status"] == MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN
        assert margin["amount_micros"] is None, (
            "a margin UBB cannot attribute at this grain is not a small margin")

    def test_the_money_it_could_not_place_is_named_rather_than_dropped(self):
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        assert [row["amount_micros"] for row in answer["context"]] == [9_000_000]
        assert answer["context"][0]["attributable_axes"] == [CUSTOMER_AXIS]

    def test_two_grains_do_not_differ_by_the_contributed_revenue(self):
        """The acceptance criterion in one assertion: the finer question must
        not answer a margin that is the coarser one MINUS the money it could not
        place — which is the shape a silent drop produces."""
        coarse = economics(self.tenant.id, measures=MONEY,
                           filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]),
                           covered_periods=(), contributed_revenue=self._contributed())
        fine = economics(self.tenant.id, measures=MONEY,
                         group_by=[PROVIDER_AXIS],
                         filters=EconomicFilters(start_date=WINDOW[0],
                                                 end_date=WINDOW[1]),
                         covered_periods=(), contributed_revenue=self._contributed())
        coarse_margin = measure_of(coarse, ANALYTICS_MEASURE_GROSS_MARGIN)
        fine_margin = measure_of(fine, ANALYTICS_MEASURE_GROSS_MARGIN)
        assert coarse_margin["amount_micros"] == 10_000_000 - 400_000
        assert fine_margin["amount_micros"] is None
        assert fine_margin["amount_micros"] != (
            coarse_margin["amount_micros"] - 9_000_000)

    def test_a_customer_with_revenue_and_no_usage_gets_a_row(self):
        """⚠ **A DELIBERATE DIFFERENCE FROM THE PER-CUSTOMER LIST THIS
        REPLACES, AND IT IS THE FIX RATHER THAN A DIVERGENCE.**

        That list is built by walking the customers who have POSTINGS, so a
        customer whose tenant supplied revenue for a period in which UBB metered
        nothing is absent from it altogether — the same hole #495 records at
        `customer_ids_with_revenue_in`, which exists because a period sweep has
        to union the two sides. Here the revenue rows make their own groups, so
        the customer appears with a real revenue, a zero cost and a margin.
        """
        quiet = Customer.objects.create(tenant=self.tenant, external_id="c2")
        contributed = self._contributed() + [
            {"window_start": WINDOW[0], "window_end": WINDOW[1],
             "customer_id": str(quiet.id), "source": "subscription",
             "amount_micros": 4_000_000, "attributable_axes": ("customer",),
             "finest_bucket": BUCKET_DAY}]
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[CUSTOMER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]), covered_periods=(), contributed_revenue=contributed)
        rows = {row[GROUPED_VALUE_KEY][0]: index
                for index, row in enumerate(answer["rows"])}
        assert str(quiet.id) in rows
        index = rows[str(quiet.id)]
        assert measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE, index
                          )["amount_micros"] == 4_000_000
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN, index
                          )["amount_micros"] == 4_000_000

    def test_with_nothing_contributed_the_finer_grain_answers_a_margin(self):
        """The guard that stops the rule reading as *no margin when grouped*.
        A tenant with no revenue outside its postings gets one at every grain."""
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], filters=EconomicFilters(start_date=WINDOW[0],
                                                   end_date=WINDOW[1]), covered_periods=(), contributed_revenue=())
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["status"] == MEASURE_STATUS_KNOWN


class ForgettingTheContributedRevenueIsRefusedTest(TestCase):
    """A revenue measure over rows this product does not hold is a question this
    module cannot answer alone, and the absence of the argument says so.

    A default of "none" would make *there was no subscription revenue* and *I
    forgot to ask* the same request, and the second answers a confident margin
    short by a subscription.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])

    def test_a_revenue_measure_without_the_rows_raises(self):
        with self.assertRaisesRegex(ValueError, "contributed_revenue"):
            economics(self.tenant.id,
                      measures=[ANALYTICS_MEASURE_CUSTOMER_REVENUE])

    def test_a_margin_without_the_rows_raises(self):
        with self.assertRaisesRegex(ValueError, "contributed_revenue"):
            economics(self.tenant.id,
                      measures=[ANALYTICS_MEASURE_GROSS_MARGIN])

    def test_a_revenue_measure_without_the_covered_periods_raises(self):
        """The rows alone are not the whole of what the other product holds:
        without the periods a supplied figure covers, the query would add the
        usage it priced inside them to the figure — a revenue counted twice
        (#537)."""
        for measure in (ANALYTICS_MEASURE_CUSTOMER_REVENUE,
                        ANALYTICS_MEASURE_GROSS_MARGIN):
            with self.assertRaisesRegex(ValueError, "covered_periods"):
                economics(self.tenant.id, measures=[measure],
                          contributed_revenue=())

    def test_stating_that_there_are_none_is_a_different_request(self):
        answer = economics(self.tenant.id,
                           measures=[ANALYTICS_MEASURE_CUSTOMER_REVENUE],
                           covered_periods=(), contributed_revenue=())
        assert measure_of(answer, ANALYTICS_MEASURE_CUSTOMER_REVENUE
                          )["amount_micros"] == 0

    def test_a_measure_that_needs_no_revenue_needs_no_rows(self):
        answer = economics(self.tenant.id,
                           measures=[ANALYTICS_MEASURE_SUPPLIER_COGS])
        assert measure_of(answer, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["amount_micros"] == 0

    def test_the_degenerate_preset_answers_over_an_empty_window(self):
        """An ungrouped, unbucketed question has exactly one row whatever the
        window holds: *what did all of this cost* is answered "nothing" when
        nothing happened, not with silence."""
        answer = economics(self.tenant.id, measures=ALL_FOUR,
                           covered_periods=(), contributed_revenue=())
        assert len(answer["rows"]) == 1
        assert measure_of(answer, ANALYTICS_MEASURE_GROSS_MARGIN
                          )["amount_micros"] == 0

    def test_a_grouped_question_over_an_empty_window_invents_no_group(self):
        """The other half, and it is a different rule: a row of a grouped answer
        IS a group, so there is none to answer with."""
        answer = economics(self.tenant.id, measures=MONEY,
                           group_by=[PROVIDER_AXIS], covered_periods=(), contributed_revenue=())
        assert answer["rows"] == []


class TheCountsComparisonRuleIsAWholeRequestPropertyTest(TestCase):
    """§10's comparison rule, and the four shapes that decide it.

    ⚠ **HERE RATHER THAN ON THE ROUTE BECAUSE THE RULE IS A PROPERTY OF THE
    WHOLE REQUEST**, so what has to be shown is the BOUNDARY between the shapes
    it refuses and the three it must not — and the route can express one of
    those four at a time while this reads the deciding function directly. The
    refused shape itself is driven through the route too, where its published
    code and message are what a caller acts on.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        GroupingField.objects.create(tenant=cls.tenant, key="region",
                                     slot="grouping_field_1", scope="event")

    def test_a_count_across_groups_that_mix_event_types_is_refused(self):
        refusal = economic_refusal(
            self.tenant.id, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            axes=[PROVIDER_AXIS])
        assert refusal is not None
        assert EVENT_TYPE_AXIS in refusal

    def test_the_same_count_is_answered_with_the_event_type_beside_it(self):
        assert economic_refusal(
            self.tenant.id, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            axes=[PROVIDER_AXIS, EVENT_TYPE_AXIS]) is None

    def test_an_ungrouped_count_compares_with_nothing_and_is_answered(self):
        assert economic_refusal(
            self.tenant.id, measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            axes=[]) is None

    def test_the_money_measures_are_not_caught_by_the_count_rule(self):
        """The rule is about a count, so the guard that it did not widen into
        every measure is worth its own case."""
        assert economic_refusal(self.tenant.id, measures=MONEY,
                                axes=[PROVIDER_AXIS]) is None


class TheBucketBoundaryIsTheOneThingARouteCannotShowTest(TestCase):
    """§16's bucketing, reduced to the two claims no response can carry.

    ⚠ **THE THREE GRAINS THEMSELVES ARE DRIVEN THROUGH THE ROUTE**, which is the
    slice's seam rule — what is left here is the two PREMISES underneath them.
    The absence rule is vacuous for time (`Posting.effective_at` is NOT NULL, so
    a bucket key is never absent where an axis value routinely is), and the
    boundary is a UTC one, which is the only thing holding the database's
    truncation and this module's Python fold to the same idea of a day.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "march",
                  effective_at=datetime(2026, 3, 2, 1, 0,
                                        tzinfo=dt_timezone.utc))
        a_posting(cls.tenant, cls.customer, "march-later",
                  effective_at=datetime(2026, 3, 2, 5, 0,
                                        tzinfo=dt_timezone.utc))
        a_posting(cls.tenant, cls.customer, "later-march",
                  effective_at=datetime(2026, 3, 20, 1, 0,
                                        tzinfo=dt_timezone.utc))

    def test_a_bucket_key_can_never_be_absent(self):
        """The premise the paragraph above rests on, read off the model."""
        assert Posting._meta.get_field("effective_at").null is False

    def test_a_bucket_boundary_is_a_utc_one(self):
        """⚠ THE TWO HALVES OF THE BUCKETING AGREE ONLY BECAUSE THE PROJECT IS
        IN UTC, AND NOTHING ELSE SAYS SO.

        The posting aggregate truncates in the DATABASE, at `settings.TIME_ZONE`;
        the contributed revenue is placed in PYTHON, by `_bucket_of`, which
        truncates at UTC because every window in this module opens at a UTC
        midnight. Move the project off UTC and the two start disagreeing by the
        offset — silently, with every chart still rendering. This is what would
        go red.
        """
        from django.conf import settings
        assert settings.TIME_ZONE == "UTC" and settings.USE_TZ
        opens = a_posting(self.tenant, self.customer, "edge",
                          effective_at=datetime(2026, 3, 5, 0, 0,
                                                tzinfo=dt_timezone.utc))
        before = a_posting(self.tenant, self.customer, "edge-before",
                           effective_at=datetime(2026, 3, 4, 23, 59,
                                                 tzinfo=dt_timezone.utc))
        answer = economics(self.tenant.id, measures=MONEY, bucket=BUCKET_DAY,
                           filters=EconomicFilters(start_date=date(2026, 3, 4),
                                                   end_date=date(2026, 3, 5)),
                           covered_periods=(), contributed_revenue=())
        # Two postings a minute apart land in two buckets, which they only do
        # if the boundary is UTC midnight: the pair straddles it by 60 seconds,
        # so any offset at all would put both on one side.
        assert (opens.effective_at - before.effective_at).total_seconds() == 60
        assert {row["bucket_start"][:10] for row in answer["rows"]} == {
            "2026-03-04", "2026-03-05"}


class TheMeasurementHeadingAnswersACountAndRefusesMoneyTest(TestCase):
    """§7's narrowing, completed: every MONEY measure is refused at the heading
    over the quantities beneath an event, and the count is what survives.

    #498 could name only one of the three — naming all of them would have made
    the discovery read the measure concept's serving consumer and paid this
    ticket's entry by mention — and said so at the time. The other two are
    declared here, and the count keeps one meaning by counting POSTINGS.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        cls.concept = MeasurementConcept.objects.create(
            tenant=cls.tenant, key="input_size")
        cls.event_type = EventType.objects.create(
            tenant=cls.tenant, key="chat.completion",
            costing_method=COSTING_METHOD_CALCULATED)
        for code in ("prompt_tokens", "cached_prompt_tokens"):
            Measurement.objects.create(
                event_type=cls.event_type, code=code, unit=UNIT_TOKEN,
                source_kind=SOURCE_KIND_CALLER_SUPPLIED, concept=cls.concept)
        cls.measured_twice = a_posting(cls.tenant, cls.customer, "i1")
        PostingMeasurement.objects.create(
            posting=cls.measured_twice, recorded_at=MARCH,
            measurements={"prompt_tokens": 600, "cached_prompt_tokens": 40})
        cls.measured_once = a_posting(cls.tenant, cls.customer, "i2")
        PostingMeasurement.objects.create(
            posting=cls.measured_once, recorded_at=MARCH,
            measurements={"prompt_tokens": 100})

    def test_every_money_measure_is_refused_at_this_heading_by_name(self):
        for measure in MONEY:
            refusal = economic_refusal(self.tenant.id, measures=[measure],
                                       axes=[MEASUREMENT_ROLLUP])
            assert refusal is not None, measure
            assert measure in refusal and MEASUREMENT_ROLLUP in refusal

    def test_the_count_counts_postings_and_not_measurement_records(self):
        """One posting measured two ways under ONE heading is one event. A
        count over the child records would answer three here."""
        answer = economics(
            self.tenant.id,
            measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            group_by=[MEASUREMENT_ROLLUP, EVENT_TYPE_AXIS],
            filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]))
        assert len(answer["rows"]) == 1
        assert answer["rows"][0][GROUPED_VALUE_KEY] == ["input_size",
                                                        "chat.completion"]
        assert measure_of(answer, ANALYTICS_MEASURE_RECORDED_EVENTS
                          )["event_count"] == 2

    def test_a_quantity_nobody_filed_is_absent_rather_than_a_sentinel(self):
        Measurement.objects.filter(code="prompt_tokens").update(concept=None)
        answer = economics(
            self.tenant.id,
            measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            group_by=[MEASUREMENT_ROLLUP, EVENT_TYPE_AXIS],
            filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]))
        # Only the posting carrying the still-filed quantity is left, and the
        # unfiled one produced no heading of its own.
        assert [row[GROUPED_VALUE_KEY][0] for row in answer["rows"]] == [
            "input_size"]
        assert measure_of(answer, ANALYTICS_MEASURE_RECORDED_EVENTS
                          )["event_count"] == 1

    def test_a_charge_projection_never_reaches_this_heading(self):
        """A charge projection never reaches this axis, and the reason is
        structural rather than an exclusion this path remembered to apply.

        A quantity is filed under a heading by the PAIR of an Event Type and a
        code, and a projection names no Event Type — so its quantities are the
        quantities of nothing declared, they are filed under no heading, and an
        identity with no heading is absent rather than present under a sentinel.
        The count is therefore unmoved in both directions: the projection adds
        no row of its own AND does not join anybody else's.
        """
        task = Task.objects.create(tenant=self.tenant, customer=self.customer,
                                   balance_snapshot_micros=0)
        charge = project_the_charge(Charge.objects.create(
            tenant=self.tenant, task=task, amount_micros=1_000_000,
            currency="usd", agreed_price_line_id=uuid.uuid4(), book_version=1,
            resolved_at=MARCH, charged_at=MARCH, idempotency_key="charge-1"))
        PostingMeasurement.objects.create(
            posting=charge, recorded_at=MARCH,
            measurements={"prompt_tokens": 5})
        answer = economics(
            self.tenant.id,
            measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            group_by=[MEASUREMENT_ROLLUP, EVENT_TYPE_AXIS],
            filters=EconomicFilters(start_date=WINDOW[0], end_date=WINDOW[1]))
        assert len(answer["rows"]) == 1
        assert answer["rows"][0][GROUPED_VALUE_KEY] == ["input_size",
                                                        "chat.completion"]
        assert measure_of(answer, ANALYTICS_MEASURE_RECORDED_EVENTS
                          )["event_count"] == 2
        # The premise, so the paragraph fails rather than ages: an Event Type
        # key is what the pair is keyed on, and a projection has none.
        assert charge.event_type == ""

    def test_the_axis_cannot_be_an_equality_filter(self):
        with self.assertRaisesRegex(ValueError, "equality filter"):
            economics(self.tenant.id,
                      measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
                      group_by=[EVENT_TYPE_AXIS],
                      filters=EconomicFilters(
                          field_filters=[(MEASUREMENT_ROLLUP, "input_size")]))


#: The open bag's column, spelled ONCE so the cases below cannot look for one
#: word while the model carries another. Held to the model by
#: `test_the_open_bag_is_still_called_what_these_cases_look_for`, which is what
#: makes a literal safe here.
THE_OPEN_BAG = "metadata"


class TheRebuildReadsNoKeyOutOfTheOpenBagTest(TestCase):
    """The widening slice 7 was named as closing, closed by construction.

    A prior slice folded a narrowly validated bag into the one open bag, which
    widened what could reach a grouping surface: a key-driven chart could be
    handed arbitrary JSON rather than a short string. The remedy recorded at the
    time was that the capability MOVES onto the declared grouping contract when
    this query rebuilds it — and this is the rebuild.

    ⚠ **A BEHAVIOURAL CHECK WOULD PROVE NOTHING HERE.** The claim is that there
    is no such parameter, and a request carrying one that the query does not
    declare is discarded before anything runs — so passing a bag key and finding
    the answer unchanged passes identically against a query that reads one. The
    claim is therefore read off the signature and off the function's own source.
    """

    def test_the_query_takes_no_free_text_key_parameter(self):
        taken = (set(inspect.signature(economics).parameters)
                 | set(EconomicFilters._fields))
        assert "field_filters" in taken, (
            "a declared equality filter is the bounded replacement, so its "
            "absence would make this whole assertion vacuous")
        assert not [name for name in taken
                    if "bag" in name or "meta" in name], taken

    def test_no_function_this_query_calls_reads_the_bag(self):
        """The stronger half, about THIS query's own reachable source.

        ⚠ **IT USED TO BE THE ONLY ALTITUDE THE CLAIM COULD BE MADE AT**, because
        the module still held a bag-reading rollup beside the query — the
        grouped margin until #501 took it with its route, then the invoice-line
        breakdown until #503 moved it onto the declared vocabulary. Neither is
        left, so the module-wide case below now says something strictly
        stronger; this one survives because it asks a different question — not
        *does anything read the bag* but *can this query reach anything that
        does* — and it is the one that fails first when a bag read arrives on a
        path into the query.
        """
        source = ast.parse(inspect.getsource(queries))
        by_name = {node.name: node for node in ast.walk(source)
                   if isinstance(node, ast.FunctionDef)}
        reached, frontier = set(), ["economics"]
        while frontier:
            name = frontier.pop()
            if name in reached or name not in by_name:
                continue
            reached.add(name)
            frontier += [call.func.id for call in ast.walk(by_name[name])
                         if isinstance(call, ast.Call)
                         and isinstance(call.func, ast.Name)]
        assert len(reached) >= 8, (
            f"only {sorted(reached)} was reached, so this proves nothing")
        for name in sorted(reached):
            spelled = {node.attr for node in ast.walk(by_name[name])
                       if isinstance(node, ast.Attribute)}
            spelled |= {node.id for node in ast.walk(by_name[name])
                        if isinstance(node, ast.Name)}
            assert "KeyTextTransform" not in spelled, name
            assert not [word for word in spelled if word.startswith("metadata")], (
                f"{name} reads the open bag")

    def test_no_function_in_this_module_reads_the_bag_at_all(self):
        """THE CASE ABOVE, RE-ARGUED AT THE ONLY ALTITUDE LEFT (#503, §11).

        Its vacuity guard used to point at the invoice-line breakdown — the last
        bag-reading function this module held — and said in terms that *when the
        ticket that migrates it lands, this guard goes red rather than quiet,
        and the case above should then be re-argued rather than re-pointed.*
        #503 migrated it, and this is the re-argument.

        **What can no longer be said is "this query does not read the bag,
        unlike its neighbour".** There is no neighbour. So the claim moves up to
        the module: metering's read contract reads the open bag NOWHERE, which
        is a stronger fact than the one it replaces and the one ADR-0005 has
        wanted since it closed the hatch — *filterable and readable, never
        groupable*, with the one remaining reader of it being the per-customer
        event list's FILTER, which lives at the route and not here.

        The reachability walk above still earns its keep: it is about which
        functions this query can reach, and it would still catch a bag read
        arriving on a path into the query before this case caught it arriving
        anywhere.
        """
        source = ast.parse(inspect.getsource(queries))
        functions = [node for node in ast.walk(source)
                     if isinstance(node, ast.FunctionDef)]
        assert len(functions) >= 30, (
            f"only {len(functions)} functions were walked, so this proves "
            "nothing about a module of this size")
        for function in functions:
            spelled = {node.attr for node in ast.walk(function)
                       if isinstance(node, ast.Attribute)}
            spelled |= {node.id for node in ast.walk(function)
                        if isinstance(node, ast.Name)}
            assert "KeyTextTransform" not in spelled, function.name
            assert not [word for word in spelled
                        if word.startswith(THE_OPEN_BAG)], (
                f"{function.name} reads the open bag")

    def test_the_open_bag_is_still_called_what_these_cases_look_for(self):
        """THE VACUITY GUARD, AND IT IS NOW ABOUT THE WORD RATHER THAN A
        NEIGHBOUR.

        With nothing left reading the bag, the way the two cases above go quiet
        is no longer *the subject was deleted* — it is *the test is looking for
        the wrong word*. Rename the column and every assertion about it passes
        over a module that reads the bag under its new name, with nothing
        raising.

        The word cannot be DERIVED — the whole claim is that nothing names it,
        so there is nothing to read it off — so it is typed once and held to the
        model here. `get_field` raises `FieldDoesNotExist` rather than returning
        a falsy value, which is what makes this an assertion rather than a
        truthiness check on an object that is always truthy.
        """
        assert Posting._meta.get_field(THE_OPEN_BAG).name == THE_OPEN_BAG


class WhichClockGovernsARowTest(TestCase):
    """§13: two horizons, and the grouping decides which one binds a row.

    ⚠ **HERE RATHER THAN AT THE ROUTE BECAUSE THE FIXTURE NEEDS A PINNED DAY.**
    Both horizons are measured back from the day the question is asked, so a
    route test has to read the horizon off the answer it is checking; only a
    direct call can hold the day still and say *this window straddles the
    horizon by exactly one day*. What a caller can OBSERVE — both horizons on
    every answer, the fifth state on the wire, `available_from` beside it — is
    driven through the route in `api/v1/tests/`.
    """

    ASKED_ON = date(2026, 9, 16)
    #: The economic horizon on that day, stated rather than computed, so this
    #: fixture says which window it is about. `core/tests/test_retention.py`
    #: owns the arithmetic and the leap day.
    HOLDS_FROM = date(2020, 9, 16)

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        cls.concept = MeasurementConcept.objects.create(
            tenant=cls.tenant, key="input_size")
        cls.event_type = EventType.objects.create(
            tenant=cls.tenant, key="chat.completion",
            costing_method=COSTING_METHOD_CALCULATED)
        Measurement.objects.create(
            event_type=cls.event_type, code="prompt_tokens", unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED, concept=cls.concept)
        # One posting recorded well inside both horizons, so nothing below is
        # answered by an empty table.
        recently = datetime(2026, 9, 2, 9, 30, tzinfo=dt_timezone.utc)
        cls.posting = a_posting(cls.tenant, cls.customer, "i1",
                                effective_at=recently)
        PostingMeasurement.objects.create(posting=cls.posting,
                                          recorded_at=recently,
                                          measurements={"prompt_tokens": 600})

    def a_question_from(self, opens, **kwargs):
        return economics(
            self.tenant.id, as_of=self.ASKED_ON,
            filters=EconomicFilters(start_date=opens,
                                    end_date=date(2026, 9, 16)),
            **kwargs)

    def test_both_horizons_are_on_the_answer_with_nothing_truncated(self):
        answer = self.a_question_from(date(2026, 9, 1), measures=MONEY,
                                      covered_periods=(), contributed_revenue=())

        assert answer["economic_data_available_from"] == "2020-09-16"
        assert answer["measurement_data_available_from"] == "2020-09-16"
        assert measure_of(answer, ANALYTICS_MEASURE_SUPPLIER_COGS
                          )["status"] == MEASURE_STATUS_KNOWN

    def test_with_no_shorter_clock_the_two_horizons_are_the_same_day(self):
        """The composition #500 publishes: nothing prunes a measurement record
        on its own, so it lives as long as the posting it hangs off."""
        answer = self.a_question_from(date(2026, 9, 1), measures=MONEY,
                                      covered_periods=(), contributed_revenue=())

        assert (answer["measurement_data_available_from"]
                == answer["economic_data_available_from"])

    @override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 90})
    def test_a_configured_shorter_clock_never_truncates_a_money_question(self):
        """⚠ **THE DECISION THAT MAKES SETTING THE NUMBER A CONFIGURATION
        CHANGE.** All four measures are economic and read from postings, so a
        shorter measurement clock must not move a single money answer — if it
        did, #190 typing a number would silently re-answer every question a
        tenant already asks.

        The window reaches back a year, well past a ninety-day clock.
        """
        answer = self.a_question_from(date(2025, 9, 16), measures=MONEY,
                                      covered_periods=(), contributed_revenue=())

        assert answer["measurement_data_available_from"] == "2026-06-18"
        for measure in MONEY:
            assert measure_of(answer, measure)["status"] != (
                MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON), measure

    @override_settings(**{MEASUREMENT_RETENTION_DAYS_SETTING: 90})
    def test_the_shorter_clock_does_bind_a_measurement_grouped_question(self):
        """The other half, and the pair is the point: the same window, the same
        day, the same tenant — and the answer differs because the rollup reads
        the child records that clock releases."""
        answer = self.a_question_from(
            date(2025, 9, 16), measures=[ANALYTICS_MEASURE_RECORDED_EVENTS],
            group_by=[MEASUREMENT_ROLLUP, EVENT_TYPE_AXIS])

        assert answer["rows"], "an empty answer would prove nothing here"
        for row in answer["rows"]:
            count = [entry for entry in row["measures"]
                     if entry["measure"] == ANALYTICS_MEASURE_RECORDED_EVENTS]
            assert count[0]["status"] == (
                MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)
            assert count[0]["available_from"] == "2026-06-18"
            assert count[0]["event_count"] is None, "never a count, never zero"

    def test_a_question_with_no_start_date_is_not_about_all_of_history(self):
        """⚠ AN ABSENT LOWER BOUND IS THE HORIZON, NOT THE BEGINNING OF TIME.

        UBB holds nothing before the horizon, so an open-ended question is a
        question from the horizon onwards. Reading it the other way would make
        the read contract's own default — the ordinary tenant-wide question,
        which names no window at all — answer *outside the retention horizon*
        about every row it has.
        """
        answer = economics(self.tenant.id, as_of=self.ASKED_ON, measures=MONEY,
                           covered_periods=(), contributed_revenue=())

        assert answer["rows"]
        for measure in MONEY:
            assert measure_of(answer, measure)["status"] == MEASURE_STATUS_KNOWN

    def test_a_bucket_is_judged_on_its_own_stretch_and_clamped_to_the_period(
            self):
        """Three day buckets around the horizon, and only the one that opens
        before it is truncated.

        DAY buckets rather than months on purpose: a month bucket opens on the
        first of its month, so which side of the horizon it falls on would
        depend on what day of the month the fixture's `as_of` is — a test that
        passes for eleven months of the year.
        """
        for offset, key in ((-1, "before"), (0, "on"), (1, "after")):
            day = self.HOLDS_FROM + timedelta(days=offset)
            a_posting(self.tenant, self.customer, f"h-{key}",
                      effective_at=datetime(day.year, day.month, day.day,
                                            12, 0, tzinfo=dt_timezone.utc))
        answer = self.a_question_from(
            self.HOLDS_FROM - timedelta(days=1),
            measures=[ANALYTICS_MEASURE_SUPPLIER_COGS], bucket=BUCKET_DAY)

        states = {row["bucket_start"][:10]: row["measures"][0]["status"]
                  for row in answer["rows"]}
        assert states[(self.HOLDS_FROM - timedelta(days=1)).isoformat()] == (
            MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON)
        assert states[self.HOLDS_FROM.isoformat()] == MEASURE_STATUS_KNOWN
        assert states[(self.HOLDS_FROM + timedelta(days=1)).isoformat()] == (
            MEASURE_STATUS_KNOWN)

    def test_the_degenerate_question_states_the_state_where_it_stated_zeros(
            self):
        """⚠ THE CASE THE FIFTH STATE EXISTS FOR, AND THE ONE SHAPE THAT IS
        GUARANTEED A ROW.

        An ungrouped, unbucketed question always has exactly one row — #499
        built that so the three-measure preset could not answer nothing — and
        over a window the platform no longer holds, that row used to be ZEROS
        with every state `known`. A tenant asking what 2015 cost was told it
        cost nothing.
        """
        answer = economics(self.tenant.id, as_of=self.ASKED_ON,
                           measures=ALL_FOUR, covered_periods=(), contributed_revenue=(),
                           filters=EconomicFilters(
                               start_date=date(2015, 1, 1),
                               end_date=date(2015, 6, 1)))

        assert len(answer["rows"]) == 1
        for measure in ALL_FOUR:
            entry = measure_of(answer, measure)
            assert entry["status"] == (
                MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON), measure
            assert entry["available_from"] == "2020-09-16"
            assert entry.get("amount_micros") is None
            assert entry.get("event_count") is None

    def test_a_grouped_question_over_a_released_stretch_has_no_row_to_state(
            self):
        """⚠ **THE LIMIT, WRITTEN DOWN RATHER THAN LEFT TO BE DISCOVERED.**

        Rows are the groups the data produces, and the groups that existed in a
        released stretch are exactly what the horizon no longer holds — so
        there is no row to carry the fifth state on, and inventing one would
        mean naming an axis value nobody can read back. What the caller gets is
        the two horizons, which say precisely why the series starts where it
        does. The wrong answer this rules out is a row of zeros under an
        invented heading; the answer it accepts is silence with a published
        reason.
        """
        answer = economics(self.tenant.id, as_of=self.ASKED_ON,
                           measures=[ANALYTICS_MEASURE_SUPPLIER_COGS],
                           group_by=[PROVIDER_AXIS],
                           filters=EconomicFilters(
                               start_date=date(2015, 1, 1),
                               end_date=date(2015, 6, 1)))

        assert answer["rows"] == []
        assert answer["economic_data_available_from"] == "2020-09-16"
        assert answer["measurement_data_available_from"] == "2020-09-16"

    def test_a_released_period_is_offered_no_remedy_it_cannot_honour(self):
        """⚠ **`context` IS A REMEDY, AND THERE IS NONE HERE.**

        Every context row names the axes and the bucket at which asking again
        WOULD produce a margin. Over a released stretch a coarser question is
        refused for the same reason this one was, so listing the money with
        that remedy beside it would publish an instruction that cannot work.
        The money is not lost — it answers on any window inside the horizon,
        which the response states.

        Reachable only because nothing prunes yet: a supplied revenue record is
        itself on the six-year clock, so once the promise is real the other
        product returns no rows for such a window at all. Which is exactly why
        this has to be decided now rather than discovered later.
        """
        contributed = [{"window_start": date(2015, 1, 1),
                        "window_end": date(2015, 6, 1),
                        "customer_id": str(self.customer.id),
                        "source": "subscription", "amount_micros": 9_000_000,
                        "attributable_axes": ("customer",),
                        "finest_bucket": BUCKET_DAY}]

        answer = economics(self.tenant.id, as_of=self.ASKED_ON,
                           measures=MONEY, group_by=[PROVIDER_AXIS],
                           filters=EconomicFilters(
                               start_date=date(2015, 1, 1),
                               end_date=date(2015, 6, 1)),
                           covered_periods=(), contributed_revenue=contributed)

        assert answer["context"] == []
        # The guard, so this is not passing because the contribution was
        # ignorable: the same shape over a window inside the horizon IS offered
        # the remedy.
        inside = economics(self.tenant.id, as_of=self.ASKED_ON,
                           measures=MONEY, group_by=[PROVIDER_AXIS],
                           filters=EconomicFilters(start_date=date(2026, 9, 1),
                                                   end_date=date(2026, 9, 16)),
                           covered_periods=(), contributed_revenue=[
                               {**contributed[0],
                                "window_start": date(2026, 9, 1),
                                "window_end": date(2026, 9, 16)}])
        assert inside["context"][0]["attributable_axes"] == [CUSTOMER_AXIS]

    def test_a_straddling_window_keeps_the_remedy_for_the_part_it_holds(self):
        """⚠ **THE TEST IS WHETHER ANY ROW COULD ANSWER, NOT WHETHER THE PERIOD
        REACHES BACK** — and the difference is a whole slice of the answer.

        A window straddling the horizon has buckets on both sides. The ones
        inside it are exactly the buckets a re-grouping WOULD produce a margin
        for, so withholding the remedy from the whole answer because its
        earliest bucket is released would refuse to help with the part that is
        perfectly answerable. The first draft of this rule did that.
        """
        after = self.HOLDS_FROM + timedelta(days=1)
        a_posting(self.tenant, self.customer, "held",
                  effective_at=datetime(after.year, after.month, after.day,
                                        12, 0, tzinfo=dt_timezone.utc))
        answer = economics(
            self.tenant.id, as_of=self.ASKED_ON, measures=MONEY,
            group_by=[PROVIDER_AXIS], bucket=BUCKET_DAY,
            filters=EconomicFilters(
                start_date=self.HOLDS_FROM - timedelta(days=1),
                end_date=after),
            covered_periods=(), contributed_revenue=[{
                "window_start": self.HOLDS_FROM - timedelta(days=1),
                "window_end": after,
                "customer_id": str(self.customer.id),
                "source": "subscription", "amount_micros": 9_000_000,
                "attributable_axes": ("customer",),
                "finest_bucket": BUCKET_DAY}])

        assert answer["context"], "the answerable buckets deserve the remedy"
        assert answer["context"][0]["attributable_axes"] == [CUSTOMER_AXIS]


class TheAnswerKeepsOneShapeWithOrWithoutAFigureTest(TestCase):
    """The control on the two branches of a row: a measure fills the SAME slot
    when its figure is gone as when it is known.

    ⚠ **THE WRONG ANSWER THIS RULES OUT IS A UNIT ERROR ON THE ROWS A READER IS
    LEAST ABLE TO CHECK.** Three measures are denominated in micros and the
    fourth is a number of records; a truncated row that nulled `amount_micros`
    on the count and left `event_count` absent would publish the count's slot as
    money's, and every state assertion in this module would still pass.
    """

    @classmethod
    def setUpTestData(cls):
        cls.tenant = Tenant.objects.create(name="T", products=["metering"])
        cls.customer = Customer.objects.create(tenant=cls.tenant,
                                               external_id="c1")
        a_posting(cls.tenant, cls.customer, "i1")

    def test_every_measure_nulls_exactly_the_slots_it_otherwise_fills(self):
        known = economics(self.tenant.id, as_of=date(2026, 9, 16),
                          measures=ALL_FOUR, covered_periods=(), contributed_revenue=(),
                          filters=EconomicFilters(start_date=WINDOW[0],
                                                  end_date=WINDOW[1]))
        gone = economics(self.tenant.id, as_of=date(2026, 9, 16),
                         measures=ALL_FOUR, covered_periods=(), contributed_revenue=(),
                         filters=EconomicFilters(start_date=date(2015, 1, 1),
                                                 end_date=date(2015, 6, 1)))

        for measure in ALL_FOUR:
            filled = measure_of(known, measure)
            emptied = measure_of(gone, measure)
            assert set(emptied) == set(filled) | {"available_from"}, measure
            for slot in set(filled) - {"measure", "status"}:
                assert filled[slot] is not None, (measure, slot)
                assert emptied[slot] is None, (measure, slot)


class TheStatesThisQueryReachesTest(TestCase):
    """The census this module keeps of its own measure states, and the one it
    declares unreachable.

    ⚠ **`not_applicable` IS NAMED AND NOT COMPUTED, AND THAT IS A DESIGN
    PROPERTY RATHER THAN AN OMISSION.** A combination a measure cannot answer is
    REFUSED against the discovery contract before a row is built, so an answer
    never contains a measure that does not apply to it. The module holds the
    concept as a SET so that a SIXTH value cannot arrive as a state the answer
    silently never carries — which is the condition the contract's `enum` needs:
    a closed set publishes whole or not at all.
    """

    def test_the_refused_value_is_named_and_never_ranked(self):
        """⚠ **NOT A RESTATEMENT OF THE MODULE'S OWN IMPORT-TIME GUARD, AND THE
        DIFFERENCE IS A REAL HOLE IT CANNOT SEE.**

        That guard asserts a UNION: the ranked states plus the named exception
        equal the registry's set. Moving `not_applicable` INTO the ranking
        satisfies it unchanged — the union is the same set — and the query
        would then carry a precedence for a state it can never produce, which
        is the first step back toward one value meaning two failures. This
        asserts the two halves separately, which is what the union cannot.

        It also pins what the ledger payment actually rests on: the module
        holding the concept's whole-set name BY REFERENCE, which is the unit
        the consumer census measures. Deleting that import to "tidy up" the
        guard would silently un-pay `g2-backend-measure_status`, and nothing
        else in the tree would notice until the next census run.
        """
        assert queries.MEASURE_STATUS_VALUES is MEASURE_STATUS_VALUES
        assert MEASURE_STATUS_NOT_APPLICABLE not in (
            queries.MEASURE_STATES_WORST_LAST)
        assert set(queries.MEASURE_STATES_WORST_LAST) < MEASURE_STATUS_VALUES

    def test_the_worst_state_is_the_one_with_no_remedy_on_this_surface(self):
        """The order is the precedence and it is load-bearing: the margin takes
        the worse of its two inputs' states, so ranking a grain problem above
        an age problem would offer a re-grouping remedy for a stretch no
        re-grouping can reach."""
        order = queries.MEASURE_STATES_WORST_LAST
        assert order[-1] == MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON
        assert order.index(MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN) > (
            order.index(MEASURE_STATUS_INCOMPLETE))

    def test_neither_unavailable_state_may_carry_a_figure(self):
        assert set(queries.MEASURE_STATES_WITH_NO_FIGURE) == {
            MEASURE_STATUS_UNAVAILABLE_AT_REQUESTED_GRAIN,
            MEASURE_STATUS_UNAVAILABLE_OUTSIDE_RETENTION_HORIZON}
