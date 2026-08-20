"""What went unresolved, what recovering it would be worth, and what waiving
has cost (#364, spec §10 ruling 12c and §24; user stories 34, 40 and 42).

Ticket 16 built the mechanism; these are its outputs, and the reason the fourth
of the four recovery mechanisms is not a fourth build. What each class holds:

* *The queue is the set a run is aimed at* — the same postings, by
  construction rather than by a filter written twice, with the reason the
  record holds beside each one.
* *A projection is the run with the writing taken out* — the same evaluation,
  and the figure it reports is what the run then actually completes. Measured
  by running one, not argued.
* *A total says how many it could not include* — skip-and-count on all three
  surfaces, in both directions: an unresolved amount is counted, an amount the
  declaration says does not exist is not.
* *What waiving has cost, and on what basis* — a waived posting carries no
  price by construction, so the figure is the supplier cost paid on those
  calls, and the response says so in its own words.
* *None of the three moves money* — no invoice, no wallet movement, no call to
  Stripe, and not one column of one posting written by reading any of them.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** Book construction and the
discriminator that separates a cost book from a price one are carried by
`pricing/tests/_helpers`; the receipt column is reached through
`ATenantWithUnresolvedPostingsMixin.receipt_of`.
"""
import dataclasses
import inspect
from unittest.mock import patch

from django.test import TestCase

from apps.metering.pricing.services import resolution_run
from apps.metering.pricing.services.resolution_run import (
    RunSelector, candidates)
from apps.metering.pricing.tests._helpers import (
    A_REAL_MARKUP, PRICED_CALL, SECOND_QUANTITY, WHAT_IT_COST,
    WHAT_IT_WOULD_BILL, WHAT_THE_RULE_CHARGES,
    ATenantWithUnresolvedPostingsMixin, declares_a_markup)
from apps.metering.queries import (
    get_projected_adjustment, get_unresolved_queue, get_waived_loss)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType
from core.cost_totals import (
    UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY)
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: An Event Type that declares no supplier cost at all: the calculated method,
#: no declared quantity and no cost mapping — the three halves
#: `event_types.costing.declares_no_cost` asks for. A posting against it costs
#: `not_applicable`, which is the reading a completeness count must NOT count.
FREE_CALL = "free.call"

PROJECTED = "projected_billed_cost_micros"


class _AReadingMixin(ATenantWithUnresolvedPostingsMixin):
    """The three reads, at the read contract, for this tenant."""

    def the_queue(self, **filters):
        return get_unresolved_queue(self.tenant.id, **filters)

    def the_projection(self, **filters):
        return get_projected_adjustment(self.tenant.id, **filters)

    def the_waived_loss(self, **filters):
        return get_waived_loss(self.tenant.id, **filters)

    @staticmethod
    def ids_in(queue):
        return {row["usage_event_id"] for row in queue["data"]}

    def declares_an_event_type_with_no_cost(self):
        return EventType.objects.create(
            tenant=self.tenant, key=FREE_CALL,
            costing_method=COSTING_METHOD_CALCULATED)


class TheQueueIsTheSetARunIsAimedAtTest(_AReadingMixin, TestCase):
    """AC 1. The working list, and it is the run's own candidate set.

    Not "a query that returns the same rows today": the queue calls
    `resolution_run.candidates`, so a membership rule that moved would move
    both. What this asserts is the property that makes the list worth working
    through — everything in it is something a run over the same filter would
    take up, and nothing that already has a number is.
    """

    def setUp(self):
        super().setUp()
        # A cost UBB worked out and a price nothing gave it.
        self.unpriced = self.a_posting("unpriced")
        # A cost UBB could NOT work out, because the tenant mistyped the
        # quantity their Cost Rate prices. Its recorded reason is the queue's
        # whole subject.
        self.a_rate_priced_against_a_typo()
        self.uncosted = self.a_posting("uncosted", measures=SECOND_QUANTITY)
        # And one with both halves settled, which must not appear.
        self.a_price_rule()
        self.priced = self.a_posting("priced", event_type=PRICED_CALL)

    def test_the_queue_is_exactly_what_a_run_would_take_up(self):
        self.assertEqual(
            self.ids_in(self.the_queue()),
            {str(pk) for pk in candidates(self.tenant, RunSelector())
             .values_list("id", flat=True)})

    def test_a_posting_that_already_has_both_numbers_is_not_in_it(self):
        """The property the run has by construction, read through the queue: a
        list that offered up a priced posting would be offering to change a
        number that exists."""
        self.assertEqual(
            self.state_of(self.priced),
            (COSTING_STATUS_KNOWN, WHAT_IT_COST,
             PRICING_STATUS_KNOWN, WHAT_THE_RULE_CHARGES))
        self.assertNotIn(str(self.priced.id), self.ids_in(self.the_queue()))

    def test_each_row_carries_the_reason_the_record_holds(self):
        rows = {row["usage_event_id"]: row for row in self.the_queue()["data"]}

        uncosted = rows[str(self.uncosted.id)]
        self.assertEqual(uncosted["costing_status"], COSTING_STATUS_UNRESOLVED)
        self.assertEqual(uncosted["unresolved_reason"],
                         UNRESOLVED_REASON_COST_RATE_MISSING)

        unpriced = rows[str(self.unpriced.id)]
        self.assertEqual(unpriced["pricing_status"], PRICING_STATUS_UNKNOWN)
        # ⚠ NULL RATHER THAN A REASON, AND THAT IS THE RECORD SPEAKING. The
        # engine writes a cause for an unresolved COST and none for an
        # unresolved price; this surface reports what is recorded instead of
        # deriving a second answer that would go stale silently.
        self.assertIsNone(unpriced["unresolved_reason"])
        self.assertEqual(unpriced["costing_status"], COSTING_STATUS_KNOWN)

    def test_no_amount_UBB_does_not_have_is_rendered_as_a_number(self):
        """AC 8, at the row. `unknown` is a status and never a currency amount:
        a price UBB could not resolve is `None` here, not a zero and not a word
        in a money field."""
        rows = {row["usage_event_id"]: row for row in self.the_queue()["data"]}

        self.assertIsNone(rows[str(self.unpriced.id)]["billed_cost_micros"])
        self.assertIsNone(rows[str(self.uncosted.id)]["provider_cost_micros"])
        for row in rows.values():
            for key, value in row.items():
                if key.endswith("_micros"):
                    with self.subTest(key=key):
                        self.assertIsInstance(value, (int, type(None)))


class TheThreeSurfacesFilterOnTheRunsOwnAxesTest(_AReadingMixin, TestCase):
    """AC 1's second half, and ruling 12b: the same axes a run accepts."""

    #: Every read surface, and the run selector they must all agree with.
    SURFACES = (get_unresolved_queue, get_projected_adjustment, get_waived_loss)

    def setUp(self):
        super().setUp()
        self.other = Customer.objects.create(tenant=self.tenant,
                                             external_id="other")
        self.mine = self.a_posting("mine")
        self.elsewhere = self.a_posting("elsewhere", event_type="other.call")
        from apps.metering.pricing.tests._helpers import an_unresolved_posting
        self.theirs = an_unresolved_posting(self.tenant, self.other, "theirs")

    def test_every_surface_offers_the_selectors_axes_and_no_others(self):
        """⚠ THE STRUCTURAL HALF, WHICH THE BEHAVIOURAL ONES CANNOT MAKE. A
        fourth axis added to a run that one of these surfaces did not offer
        would leave a tenant unable to ask of the queue what they can ask of
        the run, and every case below would still pass."""
        axes = {field.name for field in dataclasses.fields(RunSelector)}

        for surface in self.SURFACES:
            with self.subTest(surface=surface.__name__):
                offered = {
                    name.removesuffix("_id")
                    for name in inspect.signature(surface).parameters
                    if name.startswith("selected_")}
                self.assertEqual(offered, axes)

    def test_a_customer_narrows_it(self):
        self.assertEqual(
            self.ids_in(self.the_queue(selected_customer_id=self.other.id)),
            {str(self.theirs.id)})

    def test_an_event_type_narrows_it(self):
        self.assertEqual(
            self.ids_in(self.the_queue(selected_event_type="other.call")),
            {str(self.elsewhere.id)})

    def test_the_date_range_is_half_open_so_a_boundary_belongs_to_one_side(self):
        """Running one month and then the next must repair each posting exactly
        once, which is a property of the boundary rather than of the range."""
        instant = self.mine.effective_at

        self.assertIn(str(self.mine.id),
                      self.ids_in(self.the_queue(selected_from=instant)))
        self.assertNotIn(str(self.mine.id),
                         self.ids_in(self.the_queue(selected_to=instant)))


class AProjectionIsTheRunWithTheWritingTakenOutTest(_AReadingMixin, TestCase):
    """AC 2. What a recovery would be worth, per customer, with its receipts."""

    def setUp(self):
        super().setUp()
        from apps.metering.pricing.tests._helpers import an_unresolved_posting
        self.first = self.a_posting("first")
        self.second = self.a_posting("second")
        # ⚠ THE SECOND CUSTOMER'S BACKLOG IS BUILT BEFORE THE RUNG, LIKE THE
        # FIRST ONE'S. A posting recorded after the rung exists prices
        # immediately and is not unresolved at all — so seeding one afterwards
        # would leave this class asserting per-customer behaviour over a single
        # customer's rows.
        self.other = Customer.objects.create(tenant=self.tenant,
                                             external_id="two")
        self.theirs = an_unresolved_posting(self.tenant, self.other, "theirs")
        # The rung the tenant never had. It carries no effective moment, so
        # declaring it now is what makes these postings resolvable at the
        # instant they happened.
        #
        # ⚠ A REAL PERCENTAGE, NOT ZERO. A rung of nothing prices a call at
        # exactly what it cost, and every figure below would then be satisfied
        # by a projection that echoed the supplier cost instead of re-resolving
        # a price. `A_REAL_MARKUP` records the measurement.
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

    def rows_by_customer(self):
        return {row["customer_id"]: row for row in self.the_projection()["rows"]}

    def only_row(self):
        """This customer's row — the one the two postings in `setUp` produced."""
        return self.rows_by_customer()[str(self.customer.id)]

    def test_it_reports_per_customer_what_a_recovery_would_settle(self):
        """One customer's backlog is not another's decision, so the figures do
        not pool: a tenant deciding whether to go back to somebody is deciding
        about that somebody."""
        rows = self.rows_by_customer()

        mine = rows[str(self.customer.id)]
        self.assertEqual(mine["currency"], "usd")
        self.assertEqual(mine[PROJECTED], 2 * WHAT_IT_WOULD_BILL)
        self.assertEqual(mine["recoverable_event_count"], 2)
        self.assertEqual(mine[UNPRICED_EVENT_COUNT_KEY], 0)

        self.assertEqual(rows[str(self.other.id)][PROJECTED],
                         WHAT_IT_WOULD_BILL)
        self.assertEqual(rows[str(self.other.id)]["recoverable_event_count"], 1)

    def test_the_figure_is_a_price_and_not_the_cost_it_was_derived_from(self):
        """The premise every case in this class rests on, established rather
        than assumed: the rung is real, so a projection that answered what the
        call COST would be answering a different number."""
        self.assertNotEqual(WHAT_IT_WOULD_BILL, WHAT_IT_COST)
        self.assertEqual(self.only_row()[PROJECTED], 2 * WHAT_IT_WOULD_BILL)

    def test_the_figure_is_what_a_run_then_actually_completes(self):
        """⚠ THE LOAD-BEARING ONE. A projection produced by a second
        implementation would agree with the run on the day it was written and
        drift afterwards, and a tenant deciding whether to go back to a
        customer would be deciding on the wrong number. Measured by running
        one."""
        projected = self.only_row()[PROJECTED]

        self.a_run()

        self.assertEqual(
            projected,
            sum(posting.billed_cost_micros for posting in
                Posting.objects.filter(tenant=self.tenant,
                                       customer=self.customer)))

    def test_the_receipts_behind_the_figure_are_reachable(self):
        """Each posting named by the row explains its own amount — the record
        is what a tenant takes to their customer, not the total."""
        named = self.only_row()["usage_event_ids"]

        self.assertEqual(set(named), {str(self.first.id), str(self.second.id)})
        for event_id in named:
            with self.subTest(event_id=event_id):
                receipt = self.receipt_of(Posting.objects.get(id=event_id))
                self.assertEqual(receipt["subject_id"], event_id)

    def test_reading_it_writes_nothing(self):
        """AC 4. A decision record is not a mutation: no original charge is
        edited and no historical total moves, asserted over every column of
        every posting rather than over the two a reader would think to check."""
        before = _every_column_of_every_posting(self.tenant)

        self.the_projection()
        self.the_queue()
        self.the_waived_loss()

        self.assertEqual(_every_column_of_every_posting(self.tenant), before)

    def test_no_run_record_is_created_by_projecting(self):
        from apps.metering.pricing.models import ResolutionRun

        self.the_projection()

        self.assertEqual(ResolutionRun.objects.count(), 0)


class ATotalSaysHowManyItCouldNotIncludeTest(_AReadingMixin, TestCase):
    """AC 6. Slice 3's rule on all three surfaces, in BOTH directions.

    An unresolved amount is skipped and counted, so the total is a floor that
    says how far it falls short; an amount the declaration says does not exist
    is skipped and NOT counted, because nothing about it is missing. A total
    that silently omitted rows would be a wrong number wearing a right one's
    clothes; one that caveated every metering-only tenant's every figure
    forever would be a caveat nobody reads.
    """

    def setUp(self):
        super().setUp()
        self.unpriced = self.a_posting("unpriced")
        self.a_rate_priced_against_a_typo()
        self.uncosted = self.a_posting("uncosted", measures=SECOND_QUANTITY)
        self.declares_an_event_type_with_no_cost()
        self.free = self.a_posting("free", event_type=FREE_CALL)

    def only_total(self):
        totals = self.the_queue()["totals"]
        self.assertEqual(len(totals), 1)
        return totals[0]

    def test_the_three_postings_are_in_the_three_states_the_rule_is_about(self):
        """The premise, established rather than assumed: a fixture that had
        drifted into two of one state would make the two directions below
        indistinguishable."""
        self.assertEqual(
            [self.state_of(posting)[:2]
             for posting in (self.unpriced, self.uncosted, self.free)],
            [(COSTING_STATUS_KNOWN, WHAT_IT_COST),
             (COSTING_STATUS_UNRESOLVED, None),
             (COSTING_STATUS_NOT_APPLICABLE, None)])

    def test_the_queues_total_counts_the_unresolved_and_not_the_absent(self):
        total = self.only_total()

        self.assertEqual(total["provider_cost_micros"], WHAT_IT_COST)
        self.assertEqual(total[UNRESOLVED_EVENT_COUNT_KEY], 1)
        self.assertEqual(total["queued_event_count"], 3)

    def test_a_projection_that_can_value_nothing_says_so_rather_than_zero(self):
        """⚠ THE DEFECT THIS COUNT EXISTS FOR. With no markup rung declared
        nothing here is recoverable, and the figure is zero — the same zero as
        *there was nothing to recover*. The count beside it is the only thing
        that tells a tenant which of those they are looking at."""
        row = self.the_projection()["rows"][0]

        self.assertEqual(row[PROJECTED], 0)
        self.assertEqual(row[UNPRICED_EVENT_COUNT_KEY], 3)
        self.assertEqual(row["recoverable_event_count"], 0)

    def test_a_price_a_recovery_would_waive_is_skipped_and_not_counted(self):
        """The other direction, on the projection. Declaring the rung makes the
        uncosted posting's charge WAIVED rather than unknown — a decision, not
        missing information — so it leaves the count while the two that are
        genuinely unresolvable stay in it."""
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

        row = self.the_projection()["rows"][0]

        self.assertEqual(self.state_of(self.uncosted)[2:],
                         (PRICING_STATUS_UNKNOWN, None))
        self.assertEqual(row["recoverable_event_count"], 2)
        self.assertEqual(row[UNPRICED_EVENT_COUNT_KEY], 0)
        self.assertEqual(row[PROJECTED], WHAT_IT_WOULD_BILL)


class OnePassIsBoundedAndCountsWhatItDidNotReachTest(_AReadingMixin, TestCase):
    """AC 6, for the second reason a projected figure can be short.

    ⚠ **A BOUND NOBODY IS TOLD ABOUT IS THE DEFECT THIS PROGRAMME EXISTS TO
    DELETE, WEARING A PERFORMANCE ARGUMENT.** Re-resolving costs a handful of
    queries per posting, so one pass has to stop somewhere — but a total that
    stopped early and said nothing reads as *that was all of them*. Review
    found the first draft reporting the truncation as a BOOLEAN and asserting
    it nowhere: the cap could have been deleted with every test still green.

    A run's own bound IS a boolean, and the asymmetry is the point rather than
    an inconsistency: a run writes, so *send it again* is an instruction that
    makes progress, and the number left is answered by doing so. A projection
    changes nothing, so sending it again returns the same truncated figure
    forever and the only honest report is how many it did not reach.
    """

    def setUp(self):
        super().setUp()
        self.first = self.a_posting("first")
        self.second = self.a_posting("second")
        self.third = self.a_posting("third")
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

    def test_it_says_how_many_the_bound_left_out(self):
        with patch.object(resolution_run, "MAXIMUM_POSTINGS_PER_RUN", 1):
            projection = self.the_projection()

        self.assertEqual(projection["postings_examined"], 1)
        self.assertEqual(projection["postings_not_examined"], 2)
        self.assertEqual(projection["rows"][0][PROJECTED], WHAT_IT_WOULD_BILL)

    def test_a_pass_that_reached_everything_says_nothing_was_left(self):
        """The other side, so the count is not a constant wearing a report's
        clothes: with no truncation it is zero, and the figure is whole."""
        projection = self.the_projection()

        self.assertEqual(projection["postings_examined"], 3)
        self.assertEqual(projection["postings_not_examined"], 0)
        self.assertEqual(projection["rows"][0][PROJECTED],
                         3 * WHAT_IT_WOULD_BILL)

    def test_reading_it_again_answers_the_same_truncated_figure(self):
        """⚠ WHY THIS IS A COUNT AND NOT AN INSTRUCTION. A run's `more_to_do`
        means *send the same body again and I will continue*; a projection
        completes nothing, so the second read reaches exactly the same postings
        and reports exactly the same number. A flag here would be telling a
        tenant to do something that changes nothing."""
        with patch.object(resolution_run, "MAXIMUM_POSTINGS_PER_RUN", 1):
            first = self.the_projection()
            second = self.the_projection()

        self.assertEqual(first["rows"], second["rows"])
        self.assertEqual(first["postings_not_examined"],
                         second["postings_not_examined"])

    def test_the_queues_totals_are_over_the_whole_filter_not_one_pass(self):
        """The two surfaces have different denominators and each says so. The
        queue totals every posting the filter matched; the projection values
        only what one pass examined. Read together without this being pinned,
        a tenant would take the two counts for the same population."""
        with patch.object(resolution_run, "MAXIMUM_POSTINGS_PER_RUN", 1):
            queue = self.the_queue()
            projection = self.the_projection()

        self.assertEqual(queue["totals"][0]["queued_event_count"], 3)
        self.assertEqual(projection["postings_examined"], 1)


class WhatWaivingHasCostTest(_AReadingMixin, TestCase):
    """AC 5, and ruling 12c's second half.

    `waived` is never a candidate for a run — a decision somebody made is not
    information UBB is missing — but the loss it represents is reported, as
    money, because a misconfiguration that is losing a tenant money should be
    visible as money (user story 42).

    ⚠ **AND THE BASIS HAD TO BE DECIDED, BECAUSE A WAIVED POSTING CARRIES A
    NULL PRICE BY CONSTRUCTION.** A charge is waived exactly where the margin
    rule could not compute, so there is no set of prices to add up and a figure
    offered as forgone revenue would be a number nobody ever stated. The basis
    is the supplier cost paid on those calls: money that left the tenant's
    account with nothing charged against it.
    """

    def setUp(self):
        super().setUp()
        # The rung comes first, so a cost UBB cannot work out makes the charge
        # WAIVED rather than unknown.
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)
        self.a_rate_priced_against_a_typo()
        self.cost_unresolved = self.a_posting("waived-a",
                                              measures=SECOND_QUANTITY)
        self.cost_resolved = self.a_posting("waived-b",
                                            measures=SECOND_QUANTITY)

    def the_tenant_recovers_one_of_the_two_costs(self):
        """⚠ THE ONLY PATH TO A WAIVED POSTING WHOSE COST IS SETTLED, AND IT IS
        A REAL ONE. Correcting the mistyped declaration lets a run settle the
        supplier cost; the charge stays waived, because `waived` is not the
        price pair's unresolved status and nothing may complete it. That state
        is exactly what puts a number in this figure."""
        self.the_tenant_corrects_the_declaration()
        self.a_run(selected_customer=self.customer,
                   selected_from=self.cost_resolved.effective_at)

    def only_row(self):
        rows = self.the_waived_loss()["rows"]
        self.assertEqual(len(rows), 1)
        return rows[0]

    def test_both_postings_are_waived_and_one_cost_is_recovered(self):
        """The premise the figure is taken over, established in the fixture
        rather than asserted about it."""
        self.the_tenant_recovers_one_of_the_two_costs()

        self.assertEqual(self.state_of(self.cost_unresolved),
                         (COSTING_STATUS_UNRESOLVED, None,
                          PRICING_STATUS_WAIVED, None))
        self.assertEqual(self.state_of(self.cost_resolved),
                         (COSTING_STATUS_KNOWN, WHAT_IT_COST,
                          PRICING_STATUS_WAIVED, None))

    def test_the_figure_is_the_supplier_cost_on_calls_nobody_was_charged_for(self):
        self.the_tenant_recovers_one_of_the_two_costs()

        row = self.only_row()

        self.assertEqual(row["provider_cost_micros"], WHAT_IT_COST)
        self.assertEqual(row[UNRESOLVED_EVENT_COUNT_KEY], 1)
        self.assertEqual(row["waived_event_count"], 2)
        self.assertEqual(row["currency"], "usd")

    def test_the_response_states_its_basis_in_its_own_words(self):
        """A figure whose basis is not stated is a number a tenant will read as
        revenue lost, which it cannot be — so the sentence travels with the
        number rather than living only in this repository."""
        basis = self.the_waived_loss()["basis"]

        self.assertTrue(basis)
        self.assertIn("supplier", basis.lower())
        self.assertIn("never carried a price", basis)
        self.assertIn("not in the figure and are counted beside it", basis)

    def test_every_surface_states_its_own(self):
        for name, answered in (("queue", self.the_queue()),
                               ("projection", self.the_projection()),
                               ("waived", self.the_waived_loss())):
            with self.subTest(surface=name):
                self.assertTrue(answered["basis"].strip())

    def test_a_waived_posting_is_never_offered_as_something_to_recover(self):
        """Ruling 12c, read through the queue. The cost half of a waived
        posting IS a candidate while it is unresolved — that is the shape the
        run's own record settles — and once it is settled the posting leaves
        the queue entirely with its charge still waived."""
        self.the_tenant_recovers_one_of_the_two_costs()

        queued = self.ids_in(self.the_queue())

        self.assertIn(str(self.cost_unresolved.id), queued)
        self.assertNotIn(str(self.cost_resolved.id), queued)


class NoneOfTheThreeMovesMoneyTest(_AReadingMixin, TestCase):
    """AC 3. Asserted over the money path's own records and over the vendor
    library, rather than over a list somebody remembered."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=A_REAL_MARKUP)

    def all_three(self):
        return (self.the_queue(), self.the_projection(), self.the_waived_loss())

    def test_no_invoice_and_no_wallet_movement_results(self):
        """⚠ NAMED FOR WHAT IT CHECKS. The AC says "no invoice, credit note,
        charge or wallet movement", and this asserts over the two models that
        exist: UBB has no Charge or CreditNote table at all, because Stripe
        owns the billing engine and UBB drives it rather than reimplementing
        it. Those two halves of the AC are met by there being nothing to move,
        which the Stripe case below is what actually covers — a name promising
        four checks over two models would be the false claim this repository
        keeps paying for."""
        from apps.billing.invoicing.models import Invoice
        from apps.billing.wallets.models import WalletTransaction

        before = (Invoice.objects.count(), WalletTransaction.objects.count())

        self.all_three()

        self.assertEqual(
            (Invoice.objects.count(), WalletTransaction.objects.count()),
            before)

    def test_nothing_reaches_stripe(self):
        """The vendor library is the one door out of this system to Stripe, so
        a surface that moved money through the control plane would reach it."""
        with patch("apps.billing.stripe.services.stripe_service.stripe") as sdk:
            self.all_three()

        self.assertEqual(sdk.method_calls, [])

    def test_the_projection_is_worth_something_so_the_absence_means_something(self):
        """⚠ A 'NOTHING HAPPENED' CASE OVER A SURFACE WITH NOTHING TO REPORT
        proves nothing at all. This pins that the projection above really did
        have a figure to move money for and declined to."""
        self.assertEqual(self.the_projection()["rows"][0][PROJECTED],
                         WHAT_IT_WOULD_BILL)


def _every_column_of_every_posting(tenant):
    """Each posting's whole row, in a stable order.

    Every column rather than the four a reader would check: `updated_at` rides
    along deliberately, so a write that touched a row and changed nothing else
    is still caught, and "nothing was written" means the rows were not written
    to at all.
    """
    columns = [field.attname for field in Posting._meta.concrete_fields]
    return [{column: getattr(posting, column) for column in columns}
            for posting in Posting.objects.filter(tenant=tenant).order_by("id")]
