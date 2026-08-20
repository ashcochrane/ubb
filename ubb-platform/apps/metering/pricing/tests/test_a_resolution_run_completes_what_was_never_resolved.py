"""A Resolution Run completes what was never resolved, and can reach nothing
else (#363, spec §10).

One mechanism replacing four documents that each described one. What each class
holds:

* *Membership is the status* — the property everything else rests on. The
  candidate set is built from `core.amount_status_pairs`, so a posting that
  already carries an amount is outside it **by construction**. Take every axis
  of the selector away and that is still true, which is what the test does.
* *A run reaches only what was never resolved* — the mix, seeded and asserted
  posting by posting: resolved, unresolved, unknown, waived, not applicable.
* *A waived charge is never completed* — a decision somebody made, and the
  thing that keeps it out is the construction rather than an exclusion.
* *A record that kept no quantities is left alone* — the guard against a silent
  zero, which is the defect this mechanism would otherwise have introduced.
* *A completion is one-time and the receipt seals* — a second run cannot
  re-complete a field, and the record it wrote cannot be edited afterwards.
* *The receipt names the run that changed it* — a number that moved can be
  explained by the act that moved it, from the record on the row.
* *A run moves no money* — nothing in the money path is touched.
* *Nothing is backdated* — no surface anywhere accepts a rule effective before
  now, including one guarded by a check.
* *The record is written once and never edited* — through all three doors.

**WHAT A RUN ACTUALLY RECOVERS, WHICH IS NARROWER THAN IT SOUNDS.** It
re-resolves at the posting's own instant, so only configuration carrying no
effective moment of its own can change the answer: the tenant's markup rung, the
plan a customer is on, an Event Type's declarations. A *rule* takes effect from
the moment it is published forward and therefore never reaches a posting that
predates it — which is the whole reason backdating is refused. The two fixtures
here are the two real shapes of that: a tenant declaring the markup rung it
never had, and a tenant correcting a typo in a declared quantity's code, which
makes a Cost Rate that has been in force all along start matching postings
recorded before the correction.

⚠ **WAIVED IS NOT THE SAME SHAPE AS THE OTHER THREE, AND THIS MODULE SAYS SO
RATHER THAN ROUNDING IT OFF.** A price is waived exactly where a margin has no
basis — that is, where the supplier cost is `unresolved` — so a posting with a
waived price produced by the recording path *always* has an unresolved cost
beside it, and is therefore in the candidate set for its COST. What ruling 12c
settles, and what is asserted here, is that a run **never completes a waived
price**: `waived` is not the price pair's unresolved status, the receipt's
pricing section is not completable, and the database refuses the move through
every door. Settling such a posting's cost does not un-waive its price, and
nothing is written here to make that true — it falls out of the construction.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The book discriminator and the
receipt column both carry ledger entries that are ceilings as well as floors, so
every rule here is built through `pricing/tests/_helpers`, which carries the
first for its callers, and the record is addressed through
`Posting.RECEIPT_COLUMN`.
"""
import ast
import inspect
import uuid
from datetime import timedelta
from unittest.mock import patch

from django.db import IntegrityError, connection, transaction
from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import ResolutionRun
from apps.metering.pricing.receipts import (
    RESOLUTION_RUN_KEY, SECTIONS, ReceiptShapeError, Resolution,
    completed_receipt)
from apps.metering.pricing.services import resolution_run
from apps.metering.pricing.services.price_resolution import (
    PriceResolution, resolve_customer_price)
from apps.metering.pricing.services.resolution_run import (
    PAIRS, RunSelector, candidates, execute, never_resolved)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup, rate_in_default_book,
    the_cost_rate_is_repriced)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.tests._helpers import (
    declares_a_caller_supplied_cost, declares_a_quantity)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    NOT_APPLICABLE_REASON_TENANT_NOT_BILLING,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_NOT_APPLICABLE,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

#: The quantity every ordinary posting here measures, priced by a Cost Rate the
#: tenant got right.
QUANTITY = "prompt_tokens"
#: A second quantity, and the one the tenant declared with a typo — so a Cost
#: Rate written against the declaration prices a name no event ever measures,
#: and every posting measuring the real one goes uncosted. Correcting the
#: declaration is the recovery: it carries no effective moment, and the rate it
#: repoints has been in force since before the posting.
SECOND_QUANTITY = "completion_tokens"
THE_TYPO = "completion_tokns"

#: What one call measures, and the denominator every rule here divides by — so a
#: rule's per-unit figure IS the amount, and an assertion says one number.
ONE_CALL = 1_000_000

CALCULATED_CALL = "chat"
#: The Event Type whose supplier reports its own figure. Recorded with none, it
#: is unresolved for a cause no re-costing can answer — and its record keeps no
#: quantities, which is what the guard against a silent zero exists for.
REPORTED_CALL = "reported.call"
#: The Event Type a price rule pins, so that some postings are priced and some
#: are not without either state being a fixture accident.
PRICED_CALL = "priced.call"

WHAT_IT_COST = 4_000_000
WHAT_THE_RULE_CHARGES = 9_000_000


class _ATenantWithUnresolvedPostingsMixin:
    """A tenant whose costs come from Cost Rates and whose prices come from
    nothing at all — which is the state most postings in this repository are
    recorded in, and the one a run exists for."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Recovery", products=["metering", "billing"])
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme")
        declares_a_quantity(self.tenant, QUANTITY)
        cost_rate_in_default_book(
            self.tenant, measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_IT_COST, unit_quantity=ONE_CALL)

    # --- seeds -------------------------------------------------------------

    def a_posting(self, key, *, event_type=CALCULATED_CALL,
                  measures=QUANTITY, **fields):
        """One recorded posting, through the real recording path.

        Recorded rather than constructed, because what a run reads is the
        receipt the engine wrote — the quantities by value, the section
        statuses, the provenance — and a hand-built row would be a fixture
        agreeing with itself.
        """
        result = UsageService.record_usage(
            self.tenant, self.customer, f"corr-{key}", key,
            event_type=event_type, measurements={measures: ONE_CALL},
            **fields)
        return Posting.objects.get(id=result["event_id"])

    def a_rate_priced_against_a_typo(self):
        """The Cost Rate the tenant meant to write, against the name they
        mistyped when they declared it."""
        declares_a_quantity(self.tenant, THE_TYPO)
        return cost_rate_in_default_book(
            self.tenant, measurement_key=THE_TYPO,
            rate_per_unit_micros=WHAT_IT_COST, unit_quantity=ONE_CALL)

    def the_tenant_corrects_the_declaration(self):
        """The recovery, and the reason it is not backdating.

        A declared quantity's code carries no effective moment — correcting one
        is a statement about the tenant's catalogue, not about a price at a
        date — and the Cost Rate it repoints has been in force since before the
        posting was recorded. A *rule* written today could not reach that
        posting at all, which is the difference this whole mechanism turns on.
        """
        Measurement.objects.filter(
            event_type__tenant=self.tenant, code=THE_TYPO).update(
            code=SECOND_QUANTITY)

    def declares_a_reported_cost(self):
        """An Event Type whose supplier reports its own figure."""
        return declares_a_caller_supplied_cost(
            self.tenant, REPORTED_CALL,
            currency=self.tenant.default_currency or "usd")

    def a_price_rule(self):
        return rate_in_default_book(
            self.tenant, event_type=PRICED_CALL, measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_THE_RULE_CHARGES, unit_quantity=ONE_CALL)

    # --- reading -----------------------------------------------------------

    @staticmethod
    def state_of(posting):
        posting.refresh_from_db()
        return (posting.costing_status, posting.provider_cost_micros,
                posting.pricing_status, posting.billed_cost_micros)

    @staticmethod
    def receipt_of(posting):
        posting.refresh_from_db()
        return getattr(posting, Posting.RECEIPT_COLUMN)

    def a_run(self, **selector):
        with transaction.atomic():
            return execute(tenant=self.tenant, selector=RunSelector(**selector))


class MembershipIsTheStatusAndNotAFilterTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """The set a run selects from is CONSTRUCTED, so there is nothing to get
    right — and no filter whose removal opens a hole."""

    def test_the_predicate_names_the_pairs_unresolved_statuses_and_nothing_else(self):
        """Read the membership term itself: one condition per pair, each naming
        that pair's ONE status meaning *not learned*, joined by OR.

        Asserted against the registry rather than against literals, so a third
        amount UBB may not have joins a run's reach on the day it is declared —
        and so this cannot pass by agreeing with a copy of itself.
        """
        predicate = never_resolved()

        self.assertEqual(
            sorted(predicate.children),
            sorted((pair.status_column, pair.unresolved_status)
                   for pair in PAIRS))
        self.assertEqual(predicate.connector, "OR")

    def test_a_posting_that_already_has_a_price_is_out_with_every_axis_removed(self):
        """AC 3, executably: remove every filter and the property survives.

        The selector's three axes are the only conditions `candidates` adds, and
        this asks for the query with all three unstated — *everything it
        matches* — which is the widest set a run can be pointed at. A priced
        posting is still not in it, because nothing about the selector was
        keeping it out.
        """
        self.a_price_rule()
        priced = self.a_posting("priced", event_type=PRICED_CALL)
        unpriced = self.a_posting("unpriced")

        self.assertEqual(priced.pricing_status, PRICING_STATUS_KNOWN)
        reachable = set(candidates(self.tenant, RunSelector())
                        .values_list("id", flat=True))

        self.assertNotIn(priced.id, reachable)
        self.assertIn(unpriced.id, reachable)

    def test_the_door_refuses_a_priced_posting_even_when_handed_one(self):
        """The second half of the same property, one layer down.

        Membership keeps a priced posting out of the set; if something ever
        handed one to the door anyway, the door's own `WHERE` clause is what
        answers — so the guarantee does not rest on the query being built
        correctly by every future caller.
        """
        self.a_price_rule()
        priced = self.a_posting("priced", event_type=PRICED_CALL)

        outcome = resolve_customer_price(posting_id=priced.pk,
                                         billed_cost_micros=1)

        self.assertIs(outcome, PriceResolution.ALREADY_RESOLVED)
        self.assertEqual(self.state_of(priced)[3], WHAT_THE_RULE_CHARGES)


class ARunReachesOnlyWhatWasNeverResolvedTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """The mix, seeded and asserted row by row."""

    def setUp(self):
        super().setUp()
        self.a_rate_priced_against_a_typo()
        self.a_price_rule()

        #: Cost known, price known. Nothing about it was ever unresolved.
        self.resolved = self.a_posting("resolved", event_type=PRICED_CALL)
        #: Cost known, price unknown — the commonest state in this repository,
        #: and the one a declared markup rung repairs.
        self.unknown_price = self.a_posting("unknown")
        #: Cost unresolved: it measured the quantity whose declaration carries
        #: the typo, so no rate matched. Its price is `unknown` too, because a
        #: tenant that has declared no rung has decided nothing.
        self.unresolved_cost = self.a_posting("unresolved",
                                              measures=SECOND_QUANTITY)
        #: A waived charge and a `not_applicable` posting, both built at the
        #: table: what is asserted about them is MEMBERSHIP, which reads
        #: columns, and neither is a state this tenant's own recording path
        #: produces alongside the three above.
        self.waived = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="w",
            costing_status=COSTING_STATUS_KNOWN, provider_cost_micros=1,
            pricing_status=PRICING_STATUS_WAIVED, billed_cost_micros=None)
        self.not_applicable = Posting.objects.create(
            tenant=self.tenant, customer=self.customer, idempotency_key="n",
            costing_status=COSTING_STATUS_NOT_APPLICABLE,
            provider_cost_micros=None,
            pricing_status=PRICING_STATUS_NOT_APPLICABLE,
            billed_cost_micros=None,
            not_applicable_reason=NOT_APPLICABLE_REASON_TENANT_NOT_BILLING)

    def test_the_seeds_are_the_five_states_they_claim_to_be(self):
        """The premise, established rather than assumed — a mix that was
        secretly three of one state would make every assertion below vacuous."""
        self.assertEqual(
            [self.state_of(p)[0::2] for p in
             (self.resolved, self.unknown_price, self.unresolved_cost,
              self.waived, self.not_applicable)],
            [(COSTING_STATUS_KNOWN, PRICING_STATUS_KNOWN),
             (COSTING_STATUS_KNOWN, PRICING_STATUS_UNKNOWN),
             (COSTING_STATUS_UNRESOLVED, PRICING_STATUS_UNKNOWN),
             (COSTING_STATUS_KNOWN, PRICING_STATUS_WAIVED),
             (COSTING_STATUS_NOT_APPLICABLE, PRICING_STATUS_NOT_APPLICABLE)])

    def test_the_run_reaches_exactly_the_two_that_say_they_were_never_resolved(self):
        reachable = set(candidates(self.tenant, RunSelector())
                        .values_list("id", flat=True))

        self.assertEqual(
            reachable, {self.unknown_price.id, self.unresolved_cost.id})

    def test_it_completes_what_the_tenant_has_since_made_resolvable(self):
        """Both repairs at once, and neither touches anything else.

        The tenant declares the markup rung it never had and corrects the
        declaration it mistyped. One posting's price settles, one posting's cost
        settles AND its price with it, and the three that were never unresolved
        are exactly where they were.
        """
        before = {p.id: self.state_of(p) for p in
                  (self.resolved, self.waived, self.not_applicable)}
        declares_a_markup(self.tenant, percentage_micros=0)
        self.the_tenant_corrects_the_declaration()

        run = self.a_run()

        self.assertEqual(
            (run.postings_examined, run.costs_settled, run.prices_resolved,
             run.postings_left_unresolved), (2, 1, 2, 0))
        self.assertEqual(
            self.state_of(self.unknown_price),
            (COSTING_STATUS_KNOWN, WHAT_IT_COST,
             PRICING_STATUS_KNOWN, WHAT_IT_COST))
        self.assertEqual(
            self.state_of(self.unresolved_cost),
            (COSTING_STATUS_KNOWN, WHAT_IT_COST,
             PRICING_STATUS_KNOWN, WHAT_IT_COST))
        for posting in (self.resolved, self.waived, self.not_applicable):
            self.assertEqual(self.state_of(posting), before[posting.id])

    def test_a_run_that_can_repair_nothing_says_so_rather_than_failing(self):
        """The tenant has configured nothing new, so nothing resolves.

        The honest outcome, and the one a green answer must not be mistaken
        for: two postings examined, nothing completed, and both said to be still
        unresolved.
        """
        run = self.a_run()

        self.assertEqual(
            (run.postings_examined, run.costs_settled, run.prices_resolved,
             run.postings_left_unresolved), (2, 0, 0, 2))
        self.assertEqual(self.state_of(self.unknown_price)[2],
                         PRICING_STATUS_UNKNOWN)


class AWaivedChargeIsNeverCompletedTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """Ruling 12c, and the thing that achieves it."""

    def setUp(self):
        super().setUp()
        self.a_rate_priced_against_a_typo()
        # The rung comes first, so the charge is waived rather than unknown: a
        # tenant who has declared a rung HAS decided something, and a margin
        # over a cost nobody learned is a decided loss.
        declares_a_markup(self.tenant, percentage_micros=0)
        self.posting = self.a_posting("waived", measures=SECOND_QUANTITY)

    def test_the_recording_path_waives_a_margin_over_a_cost_nobody_learned(self):
        """The premise, established rather than assumed."""
        self.assertEqual(
            self.state_of(self.posting),
            (COSTING_STATUS_UNRESOLVED, None, PRICING_STATUS_WAIVED, None))

    def test_settling_its_cost_does_not_un_waive_the_charge(self):
        """⚠ THE ONE THAT MATTERS, AND THE SHAPE IS NOT THE OBVIOUS ONE.

        A waived posting is in the candidate set — for its COST, which really is
        unresolved — so it is not kept out by anything, and a run does reach it.
        What a run cannot do is complete the price: `waived` is not the price
        pair's unresolved status, so the section is not completable and the
        column does not move. The charge stays waived with a settled cost beside
        it, which is what "it never stops mattering" means.
        """
        self.the_tenant_corrects_the_declaration()

        run = self.a_run()

        self.assertEqual((run.costs_settled, run.prices_resolved), (1, 0))
        self.assertEqual(
            self.state_of(self.posting),
            (COSTING_STATUS_KNOWN, WHAT_IT_COST, PRICING_STATUS_WAIVED, None))

    def test_no_statement_in_the_run_names_waived_at_all(self):
        """AC 4's second half: no exclusion list is what achieves this.

        The module that builds the candidate set is parsed, and every string it
        holds outside its prose is compared. If a waived posting were kept out
        by an exclusion, the value would be one of them; it is not, because the
        set is built from the pairs' unresolved statuses and `waived` is simply
        not one of them.
        """
        tree = ast.parse(inspect.getsource(resolution_run))
        prose = {id(node.body[0].value) for node in ast.walk(tree)
                 if isinstance(node, (ast.Module, ast.ClassDef,
                                      ast.FunctionDef))
                 and node.body and isinstance(node.body[0], ast.Expr)
                 and isinstance(node.body[0].value, ast.Constant)}
        statements = [node.value for node in ast.walk(tree)
                      if isinstance(node, ast.Constant)
                      and isinstance(node.value, str)
                      and id(node) not in prose]

        self.assertNotIn(PRICING_STATUS_WAIVED, statements)
        self.assertNotIn("exclude", [node.attr for node in ast.walk(tree)
                                     if isinstance(node, ast.Attribute)])

    def test_the_receipts_pricing_section_refuses_the_completion_too(self):
        """The same refusal at the record, which is where a second writer would
        have to go to get around the columns."""
        stored = self.receipt_of(self.posting)

        with self.assertRaisesRegex(ReceiptShapeError, PRICING_STATUS_WAIVED):
            completed_receipt(
                stored,
                sections={"pricing": Resolution(
                    method=PRICING_METHOD_DIRECT_EVENT_PRICE,
                    status=PRICING_STATUS_KNOWN, amount_micros=1, detail={})})


class ARecordThatKeptNoQuantitiesIsLeftAloneTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """⚠ THE GUARD AGAINST A SILENT ZERO — the defect this mechanism would
    otherwise have shipped, measured on the way in.

    An unresolved cost has two causes. One keeps the quantities that went
    uncosted, because #350 built the record for exactly this recovery; the other
    — a supplier declared to report its own figure, which never did — records no
    quantities at all, because what recovers it is the figure arriving. Asked to
    re-resolve the second from its record, the engine computes a cost of exactly
    zero and every condition for settling it is then satisfied.
    """

    def setUp(self):
        super().setUp()
        self.declares_a_reported_cost()
        self.posting = self.a_posting("k1", event_type=REPORTED_CALL)

    def the_tenant_says_to_calculate_it_after_all(self):
        """The correction that makes the re-resolution *believe* a cost.

        A tenant who declared that a supplier would report its own figure, and
        never received one, changes the declaration to say the cost is
        calculated from Cost Rates instead. That is live configuration with no
        effective moment — the same class of change as declaring a markup rung —
        and it is what makes this posting's cost resolvable in principle.
        """
        EventType.objects.filter(tenant=self.tenant, key=REPORTED_CALL).update(
            costing_method=COSTING_METHOD_CALCULATED)

    def test_the_two_causes_keep_different_things_on_the_record(self):
        """The premise: one record can be re-resolved and the other cannot."""
        self.a_rate_priced_against_a_typo()
        recoverable = self.a_posting("k2", measures=SECOND_QUANTITY)

        self.assertEqual(self.posting.unresolved_reason,
                         UNRESOLVED_REASON_REPORTED_COST_MISSING)
        self.assertEqual(recoverable.unresolved_reason,
                         UNRESOLVED_REASON_COST_RATE_MISSING)
        self.assertEqual(
            getattr(self.posting, Posting.RECEIPT_COLUMN)["costing"]
            ["detail"]["uncosted_quantities"], {})
        self.assertEqual(
            getattr(recoverable, Posting.RECEIPT_COLUMN)["costing"]
            ["detail"]["uncosted_quantities"], {SECOND_QUANTITY: ONE_CALL})

    def test_a_run_examines_it_completes_nothing_and_says_so(self):
        self.the_tenant_says_to_calculate_it_after_all()
        declares_a_markup(self.tenant, percentage_micros=0)

        run = self.a_run()

        self.assertEqual(
            (run.postings_examined, run.costs_settled, run.prices_resolved,
             run.postings_left_unresolved), (1, 0, 0, 1))
        self.assertEqual(self.state_of(self.posting),
                         (COSTING_STATUS_UNRESOLVED, None,
                          PRICING_STATUS_UNKNOWN, None))

    def test_removing_the_guard_settles_a_million_tokens_at_nothing(self):
        """The mutation, run rather than argued.

        Without the guard the posting settles — status `known`, amount zero,
        receipt sealed over it — for a call that measured a million of
        something, and its price settles over that zero on top. That is what the
        branch is for, and it is why the check is a question about the RECORD
        rather than about the status.
        """
        self.the_tenant_says_to_calculate_it_after_all()
        declares_a_markup(self.tenant, percentage_micros=0)

        with patch.object(resolution_run, "_the_record_cannot_be_re_resolved",
                          lambda posting, stored: False):
            run = self.a_run()

        self.assertEqual((run.costs_settled, run.prices_resolved), (1, 1))
        self.assertEqual(self.state_of(self.posting),
                         (COSTING_STATUS_KNOWN, 0, PRICING_STATUS_KNOWN, 0))


class ACompletionHappensOnceAndTheReceiptSealsTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """A run's write is the one-time completion ticket 6's rule enforces."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)
        self.first = self.a_run()

    def test_the_first_run_completes_it(self):
        self.assertEqual(self.first.prices_resolved, 1)
        self.assertEqual(self.state_of(self.posting)[2:],
                         (PRICING_STATUS_KNOWN, WHAT_IT_COST))

    def test_a_second_run_cannot_re_complete_the_same_field(self):
        """And the way it cannot is that the posting has left the set.

        No refusal, no error: the second run is an ordinary run that finds
        nothing to do, which is what makes running one twice safe.
        """
        second = self.a_run()

        self.assertEqual(
            (second.postings_examined, second.prices_resolved), (0, 0))
        self.assertEqual(self.state_of(self.posting)[3], WHAT_IT_COST)

    def test_the_receipt_is_sealed_after_it(self):
        """Ticket 6's rule, asked of the row the run wrote."""
        stored = self.receipt_of(self.posting)
        edited = {**stored, "currency": "eur"}

        with self.assertRaises(IntegrityError), transaction.atomic():
            Posting.objects.filter(pk=self.posting.pk).update(
                **{Posting.RECEIPT_COLUMN: edited})

    def test_the_completed_section_cannot_be_completed_again(self):
        """The record's own half of "once": the section is settled, and a
        settled section is sealed."""
        stored = self.receipt_of(self.posting)

        with self.assertRaisesRegex(ReceiptShapeError, PRICING_STATUS_KNOWN):
            completed_receipt(
                stored,
                sections={"pricing": Resolution(
                    method=PRICING_METHOD_DIRECT_EVENT_PRICE,
                    status=PRICING_STATUS_KNOWN, amount_micros=99, detail={})})


class TheReceiptNamesTheRunThatChangedItTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """AC 8: a number that changed can be explained by the act that changed it."""

    def setUp(self):
        super().setUp()
        self.a_rate_priced_against_a_typo()
        self.posting = self.a_posting("k1", measures=SECOND_QUANTITY)
        self.recorded = self.receipt_of(self.posting)
        declares_a_markup(self.tenant, percentage_micros=0)
        self.the_tenant_corrects_the_declaration()
        self.run_record = self.a_run()

    def test_the_provenance_names_the_run(self):
        stored = self.receipt_of(self.posting)

        self.assertEqual(stored["provenance"][RESOLUTION_RUN_KEY],
                         str(self.run_record.id))

    def test_the_run_it_names_says_who_ran_it_and_what_they_pointed_it_at(self):
        """The whole chain, walked the way a dispute would walk it: off the
        posting's own record, to the act, to the actor and the selector."""
        stored = self.receipt_of(self.posting)

        act = ResolutionRun.objects.get(
            id=stored["provenance"][RESOLUTION_RUN_KEY])

        self.assertEqual(act.tenant_id, self.tenant.id)
        self.assertEqual(act.selector, {"selected_from": None,
                                        "selected_to": None,
                                        "selected_customer_id": None,
                                        "selected_event_type": None})
        self.assertEqual((act.costs_settled, act.prices_resolved), (1, 1))

    def test_both_sections_completed_under_one_act(self):
        """Two statements, one act — so a reader asking about either number
        gets the same answer."""
        stored = self.receipt_of(self.posting)

        self.assertEqual(stored["costing"]["status"], COSTING_STATUS_KNOWN)
        self.assertEqual(stored["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(stored["totals"],
                         {"provider_cost_micros": WHAT_IT_COST,
                          "billed_cost_micros": WHAT_IT_COST})

    def test_everything_the_record_already_said_is_unchanged(self):
        """A completion adds and never rewrites, and this reads the record as
        it was written against the record as it stands — so a run that moved
        the instant it was resolved as of, or the engine that resolved it, is
        caught rather than argued about."""
        stored = self.receipt_of(self.posting)

        for key in ("receipt_schema_version", "pricing_engine_version",
                    "subject_type", "subject_id", "effective_at", "currency"):
            with self.subTest(key=key):
                self.assertEqual(stored[key], self.recorded[key])
        self.assertEqual(
            stored["provenance"]["cost_rate_ids"],
            self.recorded["provenance"].get("cost_rate_ids", {}))


class ARunMovesNoMoneyTest(_ATenantWithUnresolvedPostingsMixin, TestCase):
    """AC 10. Nothing in the money path is touched, asserted over that path's
    own records rather than over a list somebody remembered."""

    def setUp(self):
        super().setUp()
        self.posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_no_invoice_charge_or_wallet_movement_results(self):
        from apps.billing.invoicing.models import Invoice
        from apps.billing.wallets.models import WalletTransaction

        before = (Invoice.objects.count(), WalletTransaction.objects.count())

        run = self.a_run()

        self.assertEqual(run.prices_resolved, 1)
        self.assertEqual(
            (Invoice.objects.count(), WalletTransaction.objects.count()),
            before)

    def test_nothing_reaches_stripe(self):
        """The vendor library is the one door out of this system to Stripe, so
        a run that moved money through the control plane would reach it."""
        with patch("apps.billing.stripe.services.stripe_service.stripe") as sdk:
            self.a_run()

        self.assertEqual(sdk.method_calls, [])


class NoPathBackdatesARuleTest(_ATenantWithUnresolvedPostingsMixin, TestCase):
    """AC 11, over the SURFACE rather than over the run.

    A run recovers by re-resolving at a past instant, so the one input that
    would let it rewrite history is a rule dated behind the present. The claim
    is that no path accepts one — a claim about every body that could date a
    rule, not about the route this ticket adds — so it is enumerated from the
    published schemas rather than from the routes this author remembered.
    """

    #: What a body could date a rule with: a publish's own instant, and the
    #: rule columns a body would have to carry to set one directly.
    DATING_FIELDS = {"effective_at", "valid_from", "valid_to"}

    def test_the_one_field_that_dates_a_rule_is_refused_in_the_past(self):
        from core.problems import Problem
        from core.scheduling import validate_scheduled_instant

        now = timezone.now()

        with self.assertRaises(Problem) as refused:
            validate_scheduled_instant(now - timedelta(days=1), now)

        self.assertEqual(refused.exception.code, "effective_at_in_past")

    def test_no_request_body_states_a_rules_own_effective_columns(self):
        """The other half, and the one an enumeration is for: a body that could
        state the rule's effective moment DIRECTLY would go around the check
        above entirely."""
        from api.v1 import schemas

        offenders = []
        for name in dir(schemas):
            body = getattr(schemas, name)
            fields = getattr(body, "model_fields", None)
            if not isinstance(fields, dict) or not name.endswith("In"):
                continue
            offenders += [f"{name}.{field}" for field in fields
                          if field in {"valid_from", "valid_to"}]

        self.assertEqual(offenders, [])

    def test_the_runs_own_body_states_no_instant_a_rule_could_take(self):
        from api.v1.schemas import ResolutionRunIn

        stated = set(ResolutionRunIn.model_fields)

        self.assertEqual(stated & self.DATING_FIELDS, set())
        self.assertEqual(
            stated, {"selected_from", "selected_to", "selected_customer_id",
                     "selected_event_type"})

    def test_a_rule_written_today_does_not_reach_a_posting_recorded_before_it(self):
        """⚠ THE PROPERTY BACKDATING WOULD BREAK, MEASURED RATHER THAN ARGUED.

        A price rule is written now — the only thing a route can do — and a
        posting from before it is re-resolved at ITS instant, which is before
        the rule opened. So the run reaches the posting, finds nothing in force
        and leaves it. A run that resolved at *now* would have priced it, which
        is the reprice this mechanism refuses.
        """
        recorded_first = self.a_posting("first", event_type=PRICED_CALL)
        self.a_price_rule()

        run = self.a_run()

        self.assertEqual((run.postings_examined, run.prices_resolved), (1, 0))
        self.assertEqual(self.state_of(recorded_first)[2],
                         PRICING_STATUS_UNKNOWN)

    def test_a_rung_that_carries_no_effective_moment_does_reach_it(self):
        """The other side of the same rule, and the reason a run recovers
        anything at all: a markup rung is configuration with no effective
        moment, so declaring one today is what the tenant decides today about
        every event no rule ever priced."""
        posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

        run = self.a_run()

        self.assertEqual(run.prices_resolved, 1)
        self.assertEqual(self.state_of(posting)[3], WHAT_IT_COST)


class TheRunRecordIsWrittenOnceAndNeverEditedTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """The record of an irreversible act cannot itself be rewritten, through
    any of the three doors ADR-0007 §2 names."""

    def setUp(self):
        super().setUp()
        self.a_posting("k1")
        self.record = self.a_run()

    def test_the_queryset_door_is_refused(self):
        with self.assertRaisesRegex(IntegrityError, "recorded once"), \
                transaction.atomic():
            ResolutionRun.objects.filter(pk=self.record.pk).update(
                postings_examined=99)

    def test_the_save_door_is_refused(self):
        self.record.costs_settled = 99
        with self.assertRaisesRegex(IntegrityError, "recorded once"), \
                transaction.atomic():
            self.record.save()

    def test_the_raw_sql_door_is_refused(self):
        with self.assertRaisesRegex(IntegrityError, "recorded once"), \
                transaction.atomic(), connection.cursor() as cursor:
            cursor.execute(
                "UPDATE ubb_resolution_run SET actor_display = %s WHERE id = %s",
                ["somebody else", str(self.record.pk)])

    def test_the_rule_is_the_one_this_migration_installed(self):
        """Addressed by NAME and asserted as an exact set, because a table may
        come to carry more than one rule and `pg_trigger` promises no order."""
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT tgname FROM pg_trigger t JOIN pg_class c "
                "ON c.oid = t.tgrelid "
                "WHERE c.relname = %s AND NOT t.tgisinternal",
                ["ubb_resolution_run"])
            installed = {row[0] for row in cursor.fetchall()}

        self.assertEqual(installed, {"trg_resolution_run_is_never_edited"})


class ARunIsBoundedAndSaysSoTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """The bound, and the property that makes it safe."""

    def setUp(self):
        super().setUp()
        self.first = self.a_posting("k1")
        self.second = self.a_posting("k2")
        declares_a_markup(self.tenant, percentage_micros=0)

    def test_a_run_that_hit_the_bound_says_more_remains(self):
        with patch.object(resolution_run, "MAXIMUM_POSTINGS_PER_RUN", 1):
            run = self.a_run()

        self.assertEqual((run.postings_examined, run.prices_resolved), (1, 1))
        self.assertTrue(run.more_to_do)

    def test_the_next_run_continues_where_it_stopped_with_no_cursor(self):
        """Which is the whole argument for a bound: the postings a run
        completed have left the set, so *the same request again* is a different
        set of postings without anything being carried between calls."""
        with patch.object(resolution_run, "MAXIMUM_POSTINGS_PER_RUN", 1):
            first = self.a_run()
            second = self.a_run()
            third = self.a_run()

        self.assertEqual([r.prices_resolved for r in (first, second, third)],
                         [1, 1, 0])
        self.assertEqual([r.more_to_do for r in (first, second, third)],
                         [True, False, False])
        self.assertEqual(self.state_of(self.first)[2], PRICING_STATUS_KNOWN)
        self.assertEqual(self.state_of(self.second)[2], PRICING_STATUS_KNOWN)


class TheSelectorNarrowsOnThreeAxesTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """AC 6 at the service: each axis alone, and all three together."""

    def setUp(self):
        super().setUp()
        self.other = Customer.objects.create(
            tenant=self.tenant, external_id="other")
        self.earlier = timezone.now() - timedelta(days=10)
        self.later = timezone.now() - timedelta(days=1)
        self.old = self.a_posting("old", effective_at=self.earlier)
        self.recent = self.a_posting("recent", effective_at=self.later)
        self.elsewhere = self.a_posting("elsewhere", event_type=PRICED_CALL,
                                        effective_at=self.later)
        result = UsageService.record_usage(
            self.tenant, self.other, "corr-other", "other",
            event_type=CALCULATED_CALL, measurements={QUANTITY: ONE_CALL},
            effective_at=self.later)
        self.another_customers = Posting.objects.get(id=result["event_id"])

    def reached(self, **selector):
        return set(candidates(self.tenant, RunSelector(**selector))
                   .values_list("id", flat=True))

    def test_a_date_range_alone(self):
        reached = self.reached(selected_from=self.earlier - timedelta(hours=1),
                               selected_to=self.earlier + timedelta(hours=1))

        self.assertEqual(reached, {self.old.id})

    def test_the_range_is_half_open_so_a_boundary_belongs_to_one_side(self):
        """Two adjacent ranges, and the posting on the boundary is in exactly
        one of them — which is what stops a tenant running one month and then
        the next from repairing one posting twice or missing one."""
        before = self.reached(selected_to=self.later)
        on_and_after = self.reached(selected_from=self.later)

        self.assertNotIn(self.recent.id, before)
        self.assertIn(self.recent.id, on_and_after)

    def test_a_customer_alone(self):
        reached = self.reached(selected_customer=self.other)

        self.assertEqual(reached, {self.another_customers.id})

    def test_an_event_type_alone(self):
        reached = self.reached(selected_event_type=PRICED_CALL)

        self.assertEqual(reached, {self.elsewhere.id})

    def test_all_three_together(self):
        reached = self.reached(selected_from=self.later - timedelta(hours=1),
                               selected_to=self.later + timedelta(hours=1),
                               selected_customer=self.customer,
                               selected_event_type=CALCULATED_CALL)

        self.assertEqual(reached, {self.recent.id})

    def test_none_of_them_at_all_reaches_every_unresolved_posting(self):
        self.assertEqual(
            self.reached(),
            {self.old.id, self.recent.id, self.elsewhere.id,
             self.another_customers.id})


class TheCompletionUsesTheRecordsOwnTermsTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """What a run re-resolves FROM, which is the record and not the rows
    beside it."""

    def test_the_quantities_come_from_the_receipt_and_not_from_the_child_record(self):
        """#350's content obligation, used for the thing it was built for.

        The measurement record holds what was REPORTED and the receipt holds
        what was USED to compute an amount; the two are not required to agree
        and nothing reconciles them. So the child is made to disagree — ten
        times the quantity — and the run still prices over what the record says,
        which is the only source that survives the child's own retention
        horizon.

        Made to disagree rather than deleted, because a measurement may not be
        pruned while its parent is still unresolved (#354) — the very state a
        run exists for — so deleting it here would assert the prune rule instead
        of this one.
        """
        posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)
        posting.measurement.measurements = {QUANTITY: ONE_CALL * 10}
        posting.measurement.save(update_fields=["measurements"])

        run = self.a_run()

        self.assertEqual(run.prices_resolved, 1)
        self.assertEqual(self.state_of(posting)[3], WHAT_IT_COST)

    def test_the_margin_is_taken_over_the_cost_the_record_holds(self):
        """⚠ AND NOT OVER ONE RECOMPUTED FROM TODAY'S RULES, which is the other
        way history gets repriced. The Cost Rate is retired and replaced after
        the posting is recorded; the run prices over what the record says the
        call cost."""
        posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)
        the_cost_rate_is_repriced(
            self.tenant, to_micros=WHAT_IT_COST * 10,
            measurement_key=QUANTITY, unit_quantity=ONE_CALL)

        self.a_run()

        self.assertEqual(self.state_of(posting)[3], WHAT_IT_COST)


class TheRunRecordCarriesItsActorAndSelectorTest(
        _ATenantWithUnresolvedPostingsMixin, TestCase):
    """AC 1 at the service. The actor arrives through the auth seam's own
    contextvar, which is what stops this record and the ledger entry beside it
    naming two different people."""

    def test_the_selector_it_was_given_is_what_it_records(self):
        moment = timezone.now()
        run = self.a_run(selected_from=moment,
                         selected_customer=self.customer,
                         selected_event_type=CALCULATED_CALL)

        self.assertEqual(run.selector, {
            "selected_from": moment.isoformat(),
            "selected_to": None,
            "selected_customer_id": str(self.customer.id),
            "selected_event_type": CALCULATED_CALL})

    def test_an_unattributable_run_still_records_under_the_reserved_kind(self):
        """Losing the fact that a run happened is worse than losing who ran it,
        which is `record()`'s own ruling applied to the record beside it."""
        run = self.a_run()

        self.assertEqual(run.actor_kind, "system")
        self.assertEqual((run.actor_id, run.actor_display), ("", ""))

    def test_the_id_is_decided_before_the_record_and_is_the_one_on_the_receipt(self):
        posting = self.a_posting("k1")
        declares_a_markup(self.tenant, percentage_micros=0)

        run = self.a_run()

        self.assertIsInstance(run.id, uuid.UUID)
        self.assertEqual(
            self.receipt_of(posting)["provenance"][RESOLUTION_RUN_KEY],
            str(run.id))


class ThePairsAndTheSectionsAreJoinedOnceTest(TestCase):
    """The join a completion depends on, asserted where it is made.

    A section's amount key and its completable status both come from the pair
    that declares them, so the receipt's rule and the columns' rules cannot come
    to disagree — and the database rule that seals a receipt makes the same
    join, from its own copy of the tokens.
    """

    def test_every_section_is_joined_to_exactly_one_pair(self):
        self.assertEqual(set(resolution_run.PAIR_BY_SECTION), set(SECTIONS))
        self.assertEqual(len(set(resolution_run.PAIR_BY_SECTION.values())),
                         len(PAIRS))

    def test_each_section_takes_its_terms_from_that_pair(self):
        for section, pair in resolution_run.PAIR_BY_SECTION.items():
            with self.subTest(section=section):
                self.assertEqual(SECTIONS[section].completable,
                                 pair.unresolved_status)
                self.assertEqual(SECTIONS[section].amount_key,
                                 pair.amount_column)
