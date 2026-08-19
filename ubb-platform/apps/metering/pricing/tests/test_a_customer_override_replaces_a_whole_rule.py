"""A customer override replaces a whole rule, method included (#361, #151 §6).

A tenant honours a negotiated deal by giving one customer their own pricing
rule. **The override replaces the whole rule — never a number inside one** — so
a customer on cost-plus and a customer on a flat price are both expressible,
and a rule can be read on its own without tracing a chain.

```
Book rule                          Customer override        Resolved
  direct_event_price $0.02   ->      direct_event_price $0.015    $0.015
  margin_over_cost   10%     ->      direct_event_price $0.015    $0.015
```

**WHY HALF A RULE IS NOT A REPLACEMENT** (#151 §6.2). A replacement that had to
keep the method it replaced would be an amendment wearing a replacement's name,
and "override" would need a second meaning. It also protects the deal: under
complete replacement a later change to the book's method cannot silently
reinterpret an existing negotiated arrangement.

**AND THE HOLE A NUMBER-ONLY OVERRIDE WOULD REOPEN** (#151 §6.3). If a customer
genuinely negotiated cost-plus and the book's rule is a flat price, a
number-only override leaves the tenant one route: estimate that customer's
typical cost, do the arithmetic by hand, and enter a flat number that
*approximates* the deal. That is a price computed outside UBB and pasted in,
going stale the moment the supplier moves — the caller-supplied price #146 §8
deleted, arriving through the configuration door instead of the payload one.

**WHAT EACH CLASS BELOW IS FOR.**

* *An override supplies the whole rule* — every field of the resolved answer is
  the override's and none is the inherited rule's, including the method and the
  grouping value it pins.
* *An override can change the method* — the case the ruling exists for, asserted
  against the same subject resolved before the override was written.
* *No partial override is expressible* — at the service. An `add` inherits
  nothing: a field it leaves out takes the rule's own default, never the value
  of the rule it out-ranks.
* *A negotiated deal survives changes to the standard book* — the tenant
  reprices their default and the override's resolved price does not move,
  re-resolved rather than re-read out of a local.
* *Specificity decides, and source is the tie-break inside it* — the two
  directions that matter: a narrow override beats a broad default, and a BROAD
  override does not shadow a narrow rule in the catalogue. The second is the
  discriminating one — it is the only shape where the two keys disagree, and
  inverting the ranking key reddens it and nothing else.
* *The override book is ahead of the assigned one* — the tie between the two
  ways the customer's-own rung is reached, built rather than hoped for.
* *The inherited rule is the ladder one rung shorter* — what a client starts an
  override from, which is the one question that asks resolution to leave a rung
  out.
* *An override is published, dated forward and reversed* — tickets 12 and 13's
  machinery on a customer's own book. ⚠ Their PUBLISHING path is untouched;
  what this commit extends is the change BODY, which is additive and is this
  ticket's own work.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The cost/price discriminator
and the container's pointer both carry ledger entries that are ceilings as well
as floors, so every book and every rule here is built through ``_helpers``,
which carries both for its callers, and a rule's container is reached through
its own reverse relation.
"""

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import (
    CHANGE_ADD, CHANGE_REPRICE, CHANGE_RETIRE, Rate)
from apps.metering.pricing.services.book_service import (
    BookService, plan_changes)
from apps.metering.pricing.services.pricing_service import (
    FROM_THE_CUSTOMERS_OWN_RULES, PricingService, PricingSubject, ladder_rank,
    resolve_price)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject,
    an_override_rule,
    rate_in_default_book,
    the_book_holding,
)
from apps.platform.customers.models import Customer
from apps.platform.grouping_fields.models import GroupingField
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_STATUS_KNOWN,
)

#: The one quantity every case measures, in the amount that makes a per-unit
#: rate and the amount it produces the same number: a rate's denominator is a
#: million micros by default, so a million of them at `R` per denominator is
#: exactly `R`. Said once, so every figure below reads as the rule it came from.
QUANTITY = "prompt_tokens"
ONE_DENOMINATOR = 1_000_000

PROVIDER = "openai"
EVENT_TYPE = "chat"

#: The grouping field this tenant declares, and the value the narrow rules pin.
#: A declared key rather than a slot, because that is the only way a rule's
#: selector can be written through any surface a tenant reaches.
REGION = "region"
EU = "eu"

#: Distinct powers of ten, so an assertion reading the wrong rule names it in
#: its own failure message rather than reporting a bare mismatch.
WHAT_THE_CATALOGUE_CHARGES = 2_000_000
WHAT_THE_DEAL_CHARGES = 7_000_000
WHAT_THE_REPRICE_MOVES_IT_TO = 9_000_000


class _ACustomerWithADealMixin:
    """A tenant, a customer, and the two rules a negotiated deal is made of."""

    def setUp(self):
        super().setUp()
        self.tenant = Tenant.objects.create(name="T", default_currency="usd")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="acme")
        self.slot = GroupingField.objects.create(
            tenant=self.tenant, key=REGION, slot="grouping_field_1").slot

    def the_catalogues_rule(self, **fields):
        """The rule this customer inherits: the tenant's book, pinning nothing
        beyond the event's own axes."""
        return rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY,
            **{"rate_per_unit_micros": WHAT_THE_CATALOGUE_CHARGES, **fields})

    def the_deal(self, **fields):
        """One of this customer's own rules — a whole rule, at its own rung."""
        return an_override_rule(
            self.tenant, self.customer, provider=PROVIDER,
            event_type=EVENT_TYPE, measurement_key=QUANTITY,
            **{"rate_per_unit_micros": WHAT_THE_DEAL_CHARGES, **fields})

    def _selectors(self, **overrides):
        base = {name: "" for name in Rate.SELECTORS}
        base.update(provider=PROVIDER, event_type=EVENT_TYPE)
        base.update(overrides)
        return base

    def resolved(self, as_of=None, **selectors):
        return resolve_price(
            PricingSubject(
                receipt_subject=a_usage_event_subject(),
                tenant=self.tenant, customer=self.customer,
                selectors=self._selectors(**selectors),
                measurements={QUANTITY: ONE_DENOMINATOR}, currency="usd"),
            as_of or timezone.now())

    def the_rule_that_answered(self, as_of=None, **selectors):
        """WHICH rule the ladder chose, off the resolver rather than the
        receipt, because the question these cases ask is about the row."""
        return PricingService._resolve_card(
            self.tenant, self.customer, "price", self._selectors(**selectors),
            QUANTITY, "usd", as_of or timezone.now())


class AnOverrideSuppliesTheWholeRuleTest(_ACustomerWithADealMixin, TestCase):
    """AC 1 — the method, the value and the pinned grouping values are all the
    override's, and none of them is the inherited rule's.

    The two rules differ in every one of the three, so no assertion here can
    pass by coincidence: the inherited rule takes a margin over cost, charges a
    different figure and pins no region; the override attaches a price to the
    event, charges its own figure and pins one.
    """

    def setUp(self):
        super().setUp()
        self.inherited = self.the_catalogues_rule(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)
        self.override = self.the_deal(
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE,
            **{self.slot: EU})

    def test_the_rule_that_answers_is_the_override_and_not_the_one_it_replaces(self):
        answered = self.the_rule_that_answered(**{self.slot: EU})

        self.assertEqual(answered.id, self.override.id)
        self.assertNotEqual(answered.id, self.inherited.id)

    def test_its_method_its_value_and_its_pinned_grouping_value_are_all_its_own(self):
        answered = self.the_rule_that_answered(**{self.slot: EU})

        self.assertEqual(answered.pricing_method,
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(answered.rate_per_unit_micros, WHAT_THE_DEAL_CHARGES)
        self.assertEqual(getattr(answered, self.slot), EU)
        # And each one differs from what the inherited rule would have said,
        # which is what makes the three assertions above evidence rather than
        # three readings of a value both rules happen to share.
        self.assertNotEqual(answered.pricing_method,
                            self.inherited.pricing_method)
        self.assertNotEqual(answered.rate_per_unit_micros,
                            self.inherited.rate_per_unit_micros)
        self.assertNotEqual(getattr(answered, self.slot),
                            getattr(self.inherited, self.slot))

    def test_the_receipt_names_the_overrides_method_and_charges_its_amount(self):
        receipt = self.resolved(**{self.slot: EU})

        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         WHAT_THE_DEAL_CHARGES)
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(self.override.id)})

    def test_an_override_at_the_same_specificity_still_replaces_the_rule(self):
        """The override does not merely out-specify the rule it replaces.

        The case above wins on specificity as well as on source, which is the
        ordinary shape of a deal. This one pins exactly what the catalogue's
        rule pins, so the two are tied on the major key and the CUSTOMER'S OWN
        source is the only thing that separates them — *replace the rule at the
        level you are overriding*, which is what "override" means (#147 §4.1).
        """
        tied = an_override_rule(
            self.tenant, self.customer, provider=PROVIDER,
            event_type=EVENT_TYPE, measurement_key="completion_tokens",
            rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)
        rate_in_default_book(
            self.tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key="completion_tokens",
            rate_per_unit_micros=WHAT_THE_CATALOGUE_CHARGES)

        answered = PricingService._resolve_card(
            self.tenant, self.customer, "price", self._selectors(),
            "completion_tokens", "usd", timezone.now())

        self.assertEqual(answered.id, tied.id)
        self.assertEqual(answered.specificity, 2)


class AnOverrideCanChangeTheMethodTest(_ACustomerWithADealMixin, TestCase):
    """AC 2 — a customer moved from `margin_over_cost` onto a flat price.

    The ruling's own worked example, and the property the console's override
    editor exists to make explicit: changing the method stays possible, and the
    backend does not forbid it.

    ⚠ **THE BEFORE STATE IS RESOLVED RATHER THAN ASSUMED.** The same subject is
    priced before the override is written and after it, so what the assertions
    compare is two answers to one question — which is the only way to say the
    method came FROM the override rather than merely being the value that
    happens to sit on it.
    """

    def setUp(self):
        super().setUp()
        self.the_catalogues_rule(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)

    def test_on_cost_plus_before_and_on_a_flat_price_after(self):
        """The rule the ladder chose, before and after, read off its method.

        ⚠ **THE RULE RATHER THAN THE RECEIPT'S STATUS, ON PURPOSE.** A rule
        declaring a margin does not settle while markup is a separate record —
        it carries no percentage to compute with — and WHICH unsettled answer
        it gets depends on whether UBB learned the supplier's cost, which is
        the cost side's question and not this one. The method on the chosen
        rule is the fact this ruling is about, and it is decided by nothing
        else.
        """
        before = self.the_rule_that_answered()
        self.the_deal(pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)
        after = self.the_rule_that_answered()

        self.assertEqual(before.pricing_method, PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(after.pricing_method, PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_the_resolved_receipt_names_the_overrides_method(self):
        self.the_deal(pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)
        receipt = self.resolved()

        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         WHAT_THE_DEAL_CHARGES)

    def test_two_customers_of_one_tenant_read_differently_and_that_is_correct(self):
        """Two events of the same Event Type may legitimately read differently.

        #148 §17 raised this as a worry and it resolves itself: the receipt
        records the method and the applied value per event, by value, precisely
        so it can be shown.
        """
        self.the_deal(pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)
        everybody_else = Customer.objects.create(
            tenant=self.tenant, external_id="beta")

        on_the_deal = self.resolved()
        self.customer = everybody_else
        on_the_catalogue = self.the_rule_that_answered()

        self.assertEqual(on_the_deal["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(on_the_catalogue.pricing_method,
                         PRICING_METHOD_MARGIN_OVER_COST)


class NoPartialOverrideIsExpressibleTest(_ACustomerWithADealMixin, TestCase):
    """AC 3, at the service — there is no path that takes a value from one rule
    and a method from another.

    Two halves, and the second is the one a reading of the code cannot give
    you. An added rule is planned with NO outgoing rule at all, so there is
    nothing for it to inherit from; and a body that states a value and no
    method produces a rule whose method is its own default, never the method of
    the rule it out-ranks.
    """

    def setUp(self):
        super().setUp()
        self.the_catalogues_rule(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)
        self.book = BookService.the_customers_own_book(
            self.tenant, self.customer)

    def _an_added_override(self, **stated):
        return {"kind": CHANGE_ADD, "measurement_key": QUANTITY,
                "provider": PROVIDER, "event_type": EVENT_TYPE,
                **{name: "" for name in Rate.SELECTORS
                   if name not in ("provider", "event_type")},
                **stated}

    def test_an_added_override_supersedes_nothing_so_there_is_nothing_to_inherit(self):
        planned = plan_changes(
            self.book,
            [self._an_added_override(rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)],
            timezone.now())

        self.assertEqual(len(planned), 1)
        self.assertIsNone(planned[0].outgoing)

    def test_a_value_with_no_method_stated_takes_the_rules_own_default(self):
        """The sharp case: the rule it out-ranks declares a margin, and the
        override that states only a price does NOT come out declaring one."""
        record = BookService.declare(
            self.book,
            [self._an_added_override(rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)],
            effective_at=timezone.now())
        BookService.publish_declared(record)

        answered = self.the_rule_that_answered()
        self.assertIsNone(answered.pricing_method)
        # And it prices the event by its own terms, which is what a rule
        # declaring no method means at resolution — not the margin it would
        # have inherited under a partial override.
        receipt = self.resolved()
        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         WHAT_THE_DEAL_CHARGES)

    def test_a_withdrawal_states_neither_a_value_nor_a_method(self):
        """The other direction: retiring an override opens no rule, so a body
        that states terms for it is refused rather than half-applied."""
        self.the_deal()

        with self.assertRaisesRegex(
                ValueError, "states neither terms nor a method"):
            plan_changes(
                self.book,
                [{**self._an_added_override(
                    pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE),
                  "kind": CHANGE_RETIRE}],
                timezone.now())

    def test_a_method_outside_the_ratified_pair_is_refused(self):
        with self.assertRaisesRegex(ValueError, "pricing_method must be one of"):
            plan_changes(
                self.book,
                [self._an_added_override(pricing_method="cost_plus_ten")],
                timezone.now())


class ANegotiatedDealSurvivesChangesToTheStandardBookTest(
        _ACustomerWithADealMixin, TestCase):
    """AC 4 — editing the tenant's defaults does not silently reinterpret a
    contract.

    ⚠ **RE-RESOLVED RATHER THAN RE-READ.** The price is resolved again after
    the reprice lands, against the database, rather than compared with a local
    the first resolution returned — a local being unchanged is a property of
    Python, not of the record.
    """

    def setUp(self):
        super().setUp()
        self.inherited = self.the_catalogues_rule()
        self.override = self.the_deal()

    def _reprice_the_catalogue(self):
        record = BookService.declare(
            the_book_holding(self.inherited),
            [{"kind": CHANGE_REPRICE, "measurement_key": QUANTITY,
              "provider": PROVIDER, "event_type": EVENT_TYPE,
              **{name: "" for name in Rate.SELECTORS
                 if name not in ("provider", "event_type")},
              "rate_per_unit_micros": WHAT_THE_REPRICE_MOVES_IT_TO}],
            effective_at=timezone.now())
        return BookService.publish_declared(record)

    def test_the_overrides_resolved_price_does_not_move(self):
        before = self.resolved()["totals"]["billed_cost_micros"]

        self._reprice_the_catalogue()

        after = self.resolved()
        self.assertEqual(before, WHAT_THE_DEAL_CHARGES)
        self.assertEqual(after["totals"]["billed_cost_micros"],
                         WHAT_THE_DEAL_CHARGES)
        self.assertNotEqual(after["totals"]["billed_cost_micros"],
                            WHAT_THE_REPRICE_MOVES_IT_TO)
        self.assertEqual(after["provenance"]["price_rate_ids"],
                         {QUANTITY: str(self.override.id)})

    def test_the_reprice_really_did_land(self):
        """The control the case above needs to mean anything: a customer with
        no deal DOES move to the new price."""
        self._reprice_the_catalogue()
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="beta")

        self.assertEqual(self.resolved()["totals"]["billed_cost_micros"],
                         WHAT_THE_REPRICE_MOVES_IT_TO)


class SpecificityDecidesAndSourceIsTheTieBreakTest(
        _ACustomerWithADealMixin, TestCase):
    """AC 5 — the two directions, and the second is the discriminating one.

    A narrow override beating a broad default is the ordinary shape of a deal
    and both ranking keys agree on it. The case that separates the keys is the
    other way round: a BROAD override against a NARROW rule in the catalogue,
    where source says the override and specificity says the catalogue.
    Specificity is major, so the catalogue wins — which is what stops a small
    blanket discount silently deleting every specific price a tenant
    configured, with nothing anywhere reporting that it had (#147 §5.2).
    """

    def test_a_narrow_override_beats_a_broad_default(self):
        self.the_catalogues_rule()
        narrow = self.the_deal(**{self.slot: EU})

        answered = self.the_rule_that_answered(**{self.slot: EU})

        self.assertEqual(answered.id, narrow.id)

    def test_a_broad_override_does_not_shadow_a_narrow_rule_in_the_catalogue(self):
        """The one shape where the two keys disagree.

        The override pins the region and nothing else; the catalogue's rule
        pins the provider, the Event Type AND the region. Under
        source-before-specificity the blanket deal would answer; under
        specificity-before-source the catalogue's rule does.
        """
        narrow_in_the_catalogue = self.the_catalogues_rule(**{self.slot: EU})
        blanket_deal = an_override_rule(
            self.tenant, self.customer, measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_THE_DEAL_CHARGES, **{self.slot: EU})

        answered = self.the_rule_that_answered(**{self.slot: EU})

        self.assertEqual(answered.id, narrow_in_the_catalogue.id)
        self.assertNotEqual(answered.id, blanket_deal.id)
        self.assertGreater(narrow_in_the_catalogue.specificity,
                           blanket_deal.specificity)


class TheOverrideBookIsAheadOfTheAssignedOneTest(_ACustomerWithADealMixin,
                                                 TestCase):
    """The two ways the customer's-own rung is reached, and the tie between them.

    A customer's own rules are reachable twice while the assignment record
    still exists: the book carrying the customer, and the book assigned to
    them. Both carry the SAME source, so the ranking cannot separate them — and
    `_selected_books` says in its own words that the order it returns them in
    decides that tie. An ordering claim nothing exercises is the vacuous shape
    this programme has already paid for once.

    ⚠ **THE TIE IS BUILT RATHER THAN HOPED FOR.** Every key above the one under
    test is neutralised: the two rules pin exactly the same selectors (equal
    specificity), come from the same source, and are given the same
    `valid_from` — two rules created a microsecond apart are not tied at all,
    which is how the last test of this shape came to be green over a reversed
    key.
    """

    def test_at_a_genuine_tie_the_override_book_answers(self):
        # ⚠ THE SHARED INSTANT IS PASSED AT INSERT, NOT SET AFTERWARDS.
        # `valid_from` is FROZEN and a trigger holds it through `save()`,
        # `QuerySet.update()` and raw SQL alike, so the only way two rules
        # share an opening moment is to be born with it.
        moment = timezone.now() - timedelta(hours=1)
        assigned = rate_in_default_book(
            self.tenant, customer=self.customer, provider=PROVIDER,
            event_type=EVENT_TYPE, measurement_key=QUANTITY,
            rate_per_unit_micros=WHAT_THE_CATALOGUE_CHARGES,
            valid_from=moment)
        override = self.the_deal(valid_from=moment)

        answered = self.the_rule_that_answered()

        self.assertEqual(ladder_rank(answered, FROM_THE_CUSTOMERS_OWN_RULES),
                         ladder_rank(assigned, FROM_THE_CUSTOMERS_OWN_RULES),
                         "the two rules are not actually tied")
        self.assertEqual(answered.id, override.id)


class TheInheritedRuleIsTheLadderOneRungShorterTest(
        _ACustomerWithADealMixin, TestCase):
    """AC 8, at the service — what a client starts an override FROM.

    A read, and the only question that asks the ladder to leave a rung out:
    *what would this customer be charged if they had no deal*. Its own class
    rather than a third case in the ranking one above, because it is a
    different subject — the ranking cases are about which rule wins, these are
    about a rule that deliberately did not compete.
    """

    def test_the_inherited_rule_is_what_a_client_starts_an_override_from(self):
        """AC 8, at the service — the ladder with the customer's own book taken
        out of it, which is what "what would they get without this deal" means.
        """
        inherited = self.the_catalogues_rule()
        self.the_deal(**{self.slot: EU})

        starting_point = PricingService.the_rule_a_customer_inherits(
            tenant=self.tenant, customer=self.customer,
            selectors=self._selectors(**{self.slot: EU}),
            measurement_key=QUANTITY, currency="usd", as_of=timezone.now())

        self.assertEqual(starting_point.id, inherited.id)
        # And the real answer is still the override's, so the read above is a
        # question about a hypothetical rather than a change to the ladder.
        self.assertNotEqual(self.the_rule_that_answered(**{self.slot: EU}).id,
                            inherited.id)

    def test_nothing_is_inherited_where_no_book_in_play_prices_the_quantity(self):
        self.the_deal()

        self.assertIsNone(PricingService.the_rule_a_customer_inherits(
            tenant=self.tenant, customer=self.customer,
            selectors=self._selectors(), measurement_key=QUANTITY,
            currency="usd", as_of=timezone.now()))


class AnOverrideIsPublishedDatedForwardAndReversedTest(
        _ACustomerWithADealMixin, TestCase):
    """AC 6 and AC 7 — tickets 12 and 13's machinery, on a customer's book.

    ⚠ **"UNCHANGED" IS TRUE OF THE PATH AND NOT OF THE MODULE.** This commit
    edits `plan_changes`, `_terms_of` and `_default_terms` so a change body can
    state a rule's method — additive, and this ticket's own subject. What it
    does not touch is how a rule is identified, how one is closed and its
    replacement opened, or how a scheduled change is reversed, and those are
    what these cases exercise.

    An override is created through a publish on the customer's own book, dated
    forward the way any change is, and reversed by a FURTHER publish rather
    than by deleting anything. The reversal property is the one that fails
    silently if overrides took a second path, so it is asserted here rather
    than assumed from the fact that the same functions were called.
    """

    def setUp(self):
        super().setUp()
        self.the_catalogues_rule()
        self.book = BookService.the_customers_own_book(
            self.tenant, self.customer)
        self.boundary = timezone.now() + timedelta(days=30)

    def _declare(self, kind, effective_at, **stated):
        return BookService.declare(
            self.book,
            [{"kind": kind, "measurement_key": QUANTITY, "provider": PROVIDER,
              "event_type": EVENT_TYPE,
              **{name: "" for name in Rate.SELECTORS
                 if name not in ("provider", "event_type")},
              **stated}],
            effective_at=effective_at)

    def test_declaring_an_override_writes_no_rule(self):
        """A draft closes nothing and opens nothing, which is what makes an
        override freely editable and freely discardable before it lands."""
        record = self._declare(CHANGE_ADD, self.boundary,
                               rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)

        self.assertEqual(self.book.rates.count(), 0)
        self.assertEqual(record.opened_rule_ids, [])
        self.assertEqual(record.closed_rule_ids, [])
        # And the customer is still on the catalogue's price.
        self.assertEqual(self.resolved()["totals"]["billed_cost_micros"],
                         WHAT_THE_CATALOGUE_CHARGES)

    def test_a_forward_dated_override_answers_at_its_instant_and_not_before(self):
        record = self._declare(CHANGE_ADD, self.boundary,
                               rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)
        BookService.publish_declared(record)

        a_moment = timedelta(microseconds=1)
        self.assertEqual(
            self.resolved(self.boundary - a_moment)["totals"]["billed_cost_micros"],
            WHAT_THE_CATALOGUE_CHARGES)
        self.assertEqual(
            self.resolved(self.boundary)["totals"]["billed_cost_micros"],
            WHAT_THE_DEAL_CHARGES)

    def test_a_scheduled_override_is_reversed_by_a_further_publish(self):
        """The reversal, and it is a further publish rather than a deletion.

        The withdrawal retires the rule the first publish opened, at the same
        instant, so the override's window is `[T, T)` — empty, resolving for no
        instant, which is correct because it never took effect. Nothing is
        deleted and no close is moved.
        """
        declared = self._declare(CHANGE_ADD, self.boundary,
                                 rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)
        BookService.publish_declared(declared)
        opened = Rate.objects.get(pk=declared.opened_rule_ids[0])

        withdrawal = self._declare(CHANGE_RETIRE, self.boundary)
        BookService.publish_declared(withdrawal)

        self.assertEqual(withdrawal.closed_rule_ids, [str(opened.pk)])
        self.assertEqual(withdrawal.opened_rule_ids, [])
        opened.refresh_from_db()
        self.assertEqual(opened.valid_from, self.boundary)
        self.assertEqual(opened.valid_to, self.boundary)
        # The rule still exists — the record of the decision is not erased —
        # and the customer is on the catalogue's price at every instant.
        self.assertEqual(
            self.resolved(self.boundary)["totals"]["billed_cost_micros"],
            WHAT_THE_CATALOGUE_CHARGES)
        self.assertEqual(
            self.the_rule_that_answered(self.boundary + timedelta(days=1)).rate_per_unit_micros,
            WHAT_THE_CATALOGUE_CHARGES)

    def test_withdrawing_an_override_revives_nothing(self):
        """The rule the customer inherits was there all along.

        A withdrawal reopens no row and re-creates none: what changes is that
        the override stops out-ranking the catalogue's rule, which is why the
        reversal needs no mechanism of its own. ⚠ It out-ranks it on SOURCE
        here, not on specificity — the two pin exactly the same selectors —
        so "the narrower rule stops winning" would be a false account of this
        case even though it is the usual one.
        """
        declared = self._declare(CHANGE_ADD, timezone.now(),
                                 rate_per_unit_micros=WHAT_THE_DEAL_CHARGES)
        BookService.publish_declared(declared)
        inherited_before = PricingService.the_rule_a_customer_inherits(
            tenant=self.tenant, customer=self.customer,
            selectors=self._selectors(), measurement_key=QUANTITY,
            currency="usd", as_of=timezone.now())

        withdrawal = self._declare(CHANGE_RETIRE,
                                   timezone.now() + timedelta(days=1))
        BookService.publish_declared(withdrawal)

        answered = self.the_rule_that_answered(
            timezone.now() + timedelta(days=2))
        self.assertEqual(answered.id, inherited_before.id)
