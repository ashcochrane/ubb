"""A customer's price resolves through the book their Plan names (#362, #151 §7.2).

Assigning a plan is all it takes to price a customer. The Plan names the
Pricing Book its customers are priced from, the reference cannot be null, and
this module is the half of that which happens at resolution: a customer whose
ONLY route to a book is their plan gets a price, and a plan naming a book with
nothing in it gets `unknown` rather than zero.

```
  the customer's own rules   ->  an override book         (their own)
  their plan's book          ->  what the plan prices     (the selected book)
  the tenant's defaults      ->  the catalogue for all    (the selected book)
```

**WHY THE PLAN'S BOOK IS NOT AT THE CUSTOMER'S-OWN RUNG.** It is a catalogue
shared by every customer on the plan, where the two books above it hold rules
written for ONE customer. Ranked at the customer's-own rung it would sit level
with an override, and `ladder_rank`'s last key is `valid_from` — so a tenant
repricing the plan's catalogue would out-rank a deal agreed before it and
silently delete the negotiated arrangement #361 exists to honour. The two are
one rung apart, and the case that says so is here.

**AND AN EMPTY BOOK IS THE POINT RATHER THAN AN EDGE CASE.** A nullable book
reference produces an alert nobody can act on, because *"this plan has no
book"* cannot be told apart from *"this plan does not price usage"*. Required
makes the second sayable: a book holding no rules, which is the state every
plan created today is in, because UBB ships no catalogue.

⚠ **WHAT SUCH A PLAN'S CUSTOMERS ARE CHARGED IS THE MARKUP RUNG'S ANSWER AND
NOT THE BOOK'S, AND THE TICKET'S "`unknown`" IS THE END STATE RATHER THAN
TODAY'S.** No rule matches, so every event falls past the book to the rung —
and a customer on a plan ALWAYS has one, because `Plan.markup_percentage_micros`
defaults to `0` and the read contract answers with it for any live assignment.
`_priced_by_markup` reaches `unknown` only where the rung is absent. So the
answer is the zero rung's, which depends on what UBB knows the call cost, and
`AnEmptyPlanBookLeavesTheAnswerToTheMarkupRungTest` walks all three:

```
  cost unresolved       -> waived        no basis to take a margin over
  cost not_applicable   -> known, 0      the basis is genuinely zero (#147 §7.3)
  cost known            -> known, = cost an explicit zero rung pins provider cost
```

None of the three is a defect and none is this ticket's to change. The second
and third are ratified behaviour (`apps/platform/CONTEXT.md`, *Markup
precedence*: an explicit zero *"pins the customer at provider cost rather than
falling through"*). What IS transitional is that `0` here means *the tenant said
nothing*: ticket 22 (#369) deletes those columns, the rung falls to the tenant's
declared default or to nothing, and `unknown` becomes reachable. ⚠ Ticket 16
(#363) lands FIRST and a Resolution Run never reconsiders a `waived` posting,
so in that window the unresolved-cost row above is not recoverable.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.markup_service import (
    MARKUP_RUNG_PLAN, MarkupService)
from apps.metering.pricing.services.pricing_service import (
    FROM_THE_CUSTOMERS_OWN_RULES, FROM_THE_SELECTED_BOOK, PricingService,
    PricingSubject, resolve_price)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject,
    an_override_rule,
    rate_in_a_plans_book,
    rate_in_default_book,
    the_book_holding,
)
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.plans.models import Plan
from apps.platform.plans.queries import (
    get_plan_markup_for_customer, get_pricing_book_for_customer)
from apps.platform.plans.services import PlanService
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    COSTING_STATUS_NOT_APPLICABLE,
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
)

#: The quantity every case measures, in the amount that makes a per-unit rate
#: and the amount it produces the same number: a rate's denominator is a
#: million micros by default, so a million of them at `R` per denominator is
#: exactly `R`.
QUANTITY = "prompt_tokens"
ONE_DENOMINATOR = 1_000_000

PROVIDER = "openai"
EVENT_TYPE = "chat"

#: The grouping field this tenant declares, and the value a narrow rule pins.
REGION = "region"
EU = "eu"

#: Distinct powers of ten, so an assertion reading the wrong rule names it in
#: its own failure message rather than reporting a bare mismatch.
WHAT_THE_PLAN_CHARGES = 3_000_000
WHAT_THE_TENANT_DEFAULT_CHARGES = 5_000_000
WHAT_THE_DEAL_CHARGES = 7_000_000
#: The supplier's own figure, where a case needs the cost to be known. Distinct
#: from every rule amount above, so an assertion reading it names it.
WHAT_THE_CALL_COST = 11_000_000


class _ACustomerOnAPlanMixin:
    """A tenant and a customer, with nothing pricing them yet."""

    def setUp(self):
        super().setUp()
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme")

    def the_plans_rule(self, **fields):
        """A rule in the book this customer's plan prices them from."""
        return rate_in_a_plans_book(
            self.tenant, self.customer, provider=PROVIDER,
            event_type=EVENT_TYPE, measurement_key=QUANTITY,
            **{"rate_per_unit_micros": WHAT_THE_PLAN_CHARGES, **fields})

    def the_tenants_default_rule(self, **fields):
        """A rule in the tenant's default book — the catalogue for everybody."""
        return rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY,
            **{"rate_per_unit_micros": WHAT_THE_TENANT_DEFAULT_CHARGES,
               **fields})

    def _selectors(self, **overrides):
        base = {name: "" for name in Rate.SELECTORS}
        base.update(provider=PROVIDER, event_type=EVENT_TYPE)
        base.update(overrides)
        return base

    def resolved(self, as_of=None, caller_provider_cost=None, **selectors):
        return resolve_price(
            PricingSubject(
                receipt_subject=a_usage_event_subject(),
                tenant=self.tenant, customer=self.customer,
                selectors=self._selectors(**selectors),
                measurements={QUANTITY: ONE_DENOMINATOR}, currency="usd",
                caller_provider_cost=caller_provider_cost),
            as_of or timezone.now())

    def the_rule_that_answered(self, as_of=None, **selectors):
        """WHICH rule the ladder chose, off the resolver rather than the
        receipt, because these cases ask about the row."""
        return PricingService._resolve_card(
            self.tenant, self.customer, "price", self._selectors(**selectors),
            QUANTITY, "usd", as_of or timezone.now())

    def selected_books(self):
        return PricingService._selected_books(
            self.tenant, self.customer, "price", PROVIDER, "usd")


class APlanIsTheWholeRouteToABookTest(_ACustomerOnAPlanMixin, TestCase):
    """AC 4 — a customer whose ONLY route to a book is their Plan is priced.

    Nothing else in this fixture can reach a book: the tenant declares no
    default, the customer has no override book and no assignment record. If the
    plan's reference were not read at resolution there would be no candidate
    rule at all and the price would fall through to the markup rung.
    """

    def setUp(self):
        super().setUp()
        self.rule = self.the_plans_rule()

    def test_the_plans_book_prices_the_event(self):
        receipt = self.resolved()

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         WHAT_THE_PLAN_CHARGES)
        # The rule the amount came from, named. An amount alone is not evidence
        # that a rule produced it — a fallthrough to markup also returns a
        # number and raises nothing.
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(self.rule.id)})

    def test_the_route_really_is_the_only_one(self):
        """The premise, established rather than assumed.

        Without this the case above would still pass if the rule were reachable
        some other way, and every claim in this module about WHICH rung
        answered would be a claim about a fixture nobody had read.
        """
        book = the_book_holding(self.rule)

        self.assertIsNone(book.customer_id)
        self.assertFalse(book.is_default)
        self.assertEqual(
            [b.id for _, b in self.selected_books()], [book.id])

    def test_it_is_selected_at_the_selected_books_source(self):
        sources = dict(
            (book.id, source) for source, book in self.selected_books())

        self.assertEqual(sources[the_book_holding(self.rule).id],
                         FROM_THE_SELECTED_BOOK)

    def test_a_plan_the_tenant_archived_prices_nothing(self):
        """Archival has to stop a plan pricing new events, and the book it
        names is as much a part of that as the markup rung beside it.

        ⚠ The column is written directly rather than through
        `PlanService.archive`, which refuses a plan customers are still on. So
        this filter is a DEFENCE and not a path a tenant can walk today — which
        is exactly the standing of the identical filter on the markup rung it
        copies, and the reason to copy it: the two reads of one plan must not
        disagree about whether it is still in force.
        """
        plan = self.customer.plan_assignments.get().plan
        Plan.objects.filter(pk=plan.pk).update(archived_at=timezone.now())

        self.assertEqual(self.selected_books(), [])
        self.assertEqual(self.resolved()["pricing"]["status"],
                         PRICING_STATUS_UNKNOWN)

    def test_the_book_read_and_the_markup_read_agree_about_archival(self):
        """The claim above, stated where it can go wrong: two functions in one
        read contract asking the same question of one plan."""
        plan = self.customer.plan_assignments.get().plan
        Plan.objects.filter(pk=plan.pk).update(archived_at=timezone.now())

        self.assertIsNone(get_pricing_book_for_customer(
            self.tenant.id, self.customer.id))
        self.assertIsNone(get_plan_markup_for_customer(
            self.tenant.id, self.customer.id))


class AnEmptyPlanBookLeavesTheAnswerToTheMarkupRungTest(
        _ACustomerOnAPlanMixin, TestCase):
    """AC 5 — the case the nullable reference was hiding, and all three of it.

    A plan naming a book with no rules is legal, and it is how a tenant says
    *this plan does not price usage*. No rule can answer, so every event falls
    past the book to the markup rung — and the rung's answer depends on what
    UBB knows the call cost, which is why one case here would be three answers'
    worth of coverage pretending to be one.

    The module docstring carries the table and the argument. What matters at
    each assertion: the FIRST is a nothing, the SECOND and THIRD are settled
    numbers, and neither of those is a defect — a basis of genuinely zero times
    any margin is zero (#147 §7.3), and an explicit zero rung is documented as
    pinning the customer at provider cost. What makes them transitional is that
    this rung's zero was never stated by anyone.
    """

    def setUp(self):
        super().setUp()
        self.plan = a_plan(tenant=self.tenant, key="quiet")
        PlanService.assign(self.tenant, self.customer, self.plan)

    def test_the_book_is_legal_and_holds_nothing(self):
        self.assertEqual(self.plan.pricing_book.rates.count(), 0)
        self.assertEqual([b.id for _, b in self.selected_books()],
                         [self.plan.pricing_book_id])

    def test_no_rule_answers(self):
        """The book half, on its own. Everything below is the rung's."""
        self.assertIsNone(self.the_rule_that_answered())

    def test_the_rung_that_answers_is_the_plans_and_its_zero_is_nobodys(self):
        """The cause, asserted — otherwise every case below reads as a
        decision somebody made about empty books."""
        rung = MarkupService.resolve(self.tenant, self.customer)

        self.assertEqual(rung.source, MARKUP_RUNG_PLAN)
        self.assertEqual(rung.markup_micro_percent, 0)
        # And the plan never stated it: this is the model's own default, which
        # is what makes the rung's existence an accident of a column rather
        # than something the tenant decided. Ticket 22 deletes it.
        self.assertEqual(
            Plan._meta.get_field("markup_percentage_micros").default, 0)

    def test_an_unresolved_cost_is_waived_with_no_amount(self):
        """A margin over a cost UBB never learned is a decided loss, not a
        queued one — and this is the row a Resolution Run will not revisit."""
        receipt = self.resolved()

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_WAIVED)
        self.assertIsNone(receipt["totals"]["billed_cost_micros"])

    def test_an_event_type_declaring_no_cost_settles_at_zero(self):
        """Not the silent zero this programme deletes: the basis is genuinely
        zero because the tenant SAID this call has no cost, so a margin over it
        is zero and settles (#147 §7.3). Built inline rather than through a
        shared helper — one caller wants an Event Type that declares nothing,
        and a helper for it would be a fixture nobody else asks for.
        """
        EventType.objects.create(
            tenant=self.tenant, key=EVENT_TYPE,
            costing_method=COSTING_METHOD_CALCULATED)

        receipt = self.resolved()

        self.assertEqual(receipt["costing"]["status"],
                         COSTING_STATUS_NOT_APPLICABLE)
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"], 0)

    def test_a_known_cost_settles_at_the_cost_itself(self):
        """A zero rung over a known cost bills exactly what the call cost, and
        `apps/platform/CONTEXT.md` (*Markup precedence*) records that as the
        decision rather than the accident: an explicit zero *"pins the customer
        at provider cost rather than falling through"*. It is only this plan's
        zero that nobody stated."""
        receipt = self.resolved(caller_provider_cost=WHAT_THE_CALL_COST)

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         WHAT_THE_CALL_COST)
        self.assertEqual(receipt["totals"]["provider_cost_micros"],
                         WHAT_THE_CALL_COST)


class ThePlansBookIsOneRungBelowTheCustomersOwnTest(
        _ACustomerOnAPlanMixin, TestCase):
    """The rung ruling, in the direction that discriminates.

    An override and a rule in the plan's book, made identically specific and
    both matching the event. Only the SOURCE separates them — and the override
    is written FIRST, so its `valid_from` is the earlier of the two. That is
    the shape that fails if the plan's book were ranked at the customer's-own
    rung: `ladder_rank` would find both keys equal and fall to `valid_from`,
    where the plan's later rule wins and the negotiated deal disappears.
    """

    def setUp(self):
        super().setUp()
        self.deal = an_override_rule(
            self.tenant, self.customer, provider=PROVIDER,
            event_type=EVENT_TYPE, measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)
        self.plans_rule = self.the_plans_rule()

    def test_the_plans_rule_is_the_later_of_the_two(self):
        """The premise. A tie test that does not build the tie it names is
        vacuous, and here the tie is on every key ABOVE `valid_from`."""
        self.assertEqual(self.deal.specificity, self.plans_rule.specificity)
        self.assertLess(self.deal.valid_from, self.plans_rule.valid_from)

    def test_the_override_still_answers(self):
        self.assertEqual(self.the_rule_that_answered().id, self.deal.id)
        self.assertEqual(self.resolved()["totals"]["billed_cost_micros"],
                         WHAT_THE_DEAL_CHARGES)

    def test_the_two_books_are_at_different_sources(self):
        sources = dict(
            (book.id, source) for source, book in self.selected_books())

        self.assertEqual(sources[the_book_holding(self.deal).id],
                         FROM_THE_CUSTOMERS_OWN_RULES)
        self.assertEqual(sources[the_book_holding(self.plans_rule).id],
                         FROM_THE_SELECTED_BOOK)


class AtAGenuineTieThePlansBookWinsTest(_ACustomerOnAPlanMixin, TestCase):
    """At a genuine tie the plan's book wins, and the tie has to be built.

    The plan's book and the tenant's default sit at the SAME source, so
    `ladder_rank` decides nothing between two rules of equal specificity until
    its last key — `valid_from` — and only where that is equal too does the
    order `_selected_books` returns the books in get to speak. That order is
    narrowest first: the plan's book, then the tenant's answer for everybody.

    ⚠ **SO BOTH RULES ARE OPENED AT ONE INSTANT, PASSED AT INSERT.** Two rules
    created a moment apart are not tied at all, and a tie test that does not
    build the tie it names is vacuous while reading exactly like the strong
    version (#356). `Rate.valid_from` is frozen through every door, so the
    instant cannot be imposed afterwards.
    """

    def setUp(self):
        super().setUp()
        self.opened_at = timezone.now() - timedelta(days=1)
        self.plans_rule = self.the_plans_rule(valid_from=self.opened_at)
        self.default_rule = self.the_tenants_default_rule(
            valid_from=self.opened_at)

    def test_the_two_rules_are_tied_on_every_key_the_ladder_ranks(self):
        self.assertEqual(self.plans_rule.specificity,
                         self.default_rule.specificity)
        sources = dict(
            (book.id, source) for source, book in self.selected_books())
        self.assertEqual(sources[the_book_holding(self.plans_rule).id],
                         sources[the_book_holding(self.default_rule).id])
        self.assertEqual(self.plans_rule.valid_from,
                         self.default_rule.valid_from)

    def test_the_plans_book_comes_first_in_selection(self):
        self.assertEqual(
            [b.id for _, b in self.selected_books()],
            [the_book_holding(self.plans_rule).id,
             the_book_holding(self.default_rule).id])

    def test_the_plans_rule_answers(self):
        self.assertEqual(self.the_rule_that_answered().id, self.plans_rule.id)
        self.assertEqual(self.resolved()["totals"]["billed_cost_micros"],
                         WHAT_THE_PLAN_CHARGES)


class ALaterRuleInTheTenantsBookOutRanksThePlansTest(
        _ACustomerOnAPlanMixin, TestCase):
    """The other side of the same source, said out loud because it surprises.

    Where the two rules are equally specific but NOT opened at one instant,
    `ladder_rank`'s last key decides and the later rule wins — even though one
    of them is in the book the customer's plan names. That is the ranking doing
    its stated job (*"two rules a tenant made equally specific from the same
    source, where the later decision is the one they meant"*) and not an
    accident of this ticket, but it is the consequence of putting the plan's
    book at the selected-book source rather than at the customer's own, and a
    tenant who wants the plan's book to dominate writes its rule more
    specifically — which the class below proves still works.

    ⚠ **THE ALTERNATIVE WAS WORSE, WHICH IS WHY IT IS THIS WAY.** At the
    customer's-own source the plan's book would sit level with an override and
    this same key would let a plan reprice out-rank a negotiated deal agreed
    before it — silently deleting the arrangement #361 exists to honour. This
    surprise costs a tenant a catalogue edit; that one costs a customer their
    contract.
    """

    def setUp(self):
        super().setUp()
        self.plans_rule = self.the_plans_rule(
            valid_from=timezone.now() - timedelta(days=2))
        self.later = self.the_tenants_default_rule(
            valid_from=timezone.now() - timedelta(days=1))

    def test_the_later_rule_answers(self):
        self.assertEqual(self.plans_rule.specificity, self.later.specificity)
        self.assertLess(self.plans_rule.valid_from, self.later.valid_from)
        self.assertEqual(self.the_rule_that_answered().id, self.later.id)


class SpecificityStillDecidesAboveThePlansBookTest(
        _ACustomerOnAPlanMixin, TestCase):
    """Specificity before source, at the new rung.

    A narrow rule in the tenant's default book beats a broad one in the plan's
    book, because how specifically a rule names the event is compared first and
    where it came from is only the tie-break inside that level (#147 §5.2). The
    opposite ordering is the sharp edge ADR-0005 §8 named: a plan's blanket
    rule would shadow every specific price its tenant configured.
    """

    def setUp(self):
        super().setUp()
        self.slot = GroupingField.objects.create(
            tenant=self.tenant, key=REGION, slot="grouping_field_1").slot
        self.broad = self.the_plans_rule()
        self.narrow = self.the_tenants_default_rule(**{self.slot: EU})

    def test_the_narrower_default_beats_the_broader_plan_rule(self):
        self.assertGreater(self.narrow.specificity, self.broad.specificity)
        self.assertEqual(self.the_rule_that_answered(**{self.slot: EU}).id,
                         self.narrow.id)

    def test_and_the_plans_rule_still_answers_where_it_is_the_only_match(self):
        """The other half, so the case above is a statement about specificity
        rather than about the plan's book losing generally."""
        self.assertEqual(self.the_rule_that_answered().id, self.broad.id)
