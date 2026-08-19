"""Price resolution is one function of a subject and an instant (#356).

``resolve_price(subject, as_of)`` takes everything configuration-dependent as
its subject and the moment to resolve as of as its second argument, and returns
the Pricing Receipt that explains its answer. **No clock is read inside it**,
which is why the first class below can freeze time to one value, pass a
different instant, and require the answer to follow the parameter.

**WHY THIS SEAM IS WORTH TESTING AT AND NOT THROUGH HTTP.** Six behaviours are
otherwise only observable in combination — the four-rung ladder,
specificity-before-source, markup as a rung rather than a multiplier,
forward-dated boundaries, the price statuses, and the receipt's own shape.
Through the recording route each combination costs a fixture and puts an
endpoint's serialization between the assertion and the behaviour. Here they are
one table.

**THE LADDER IS FOUR RUNGS AND THE RANKING IS COMPOSITE** (#147 §5.1): how
specifically a rule names the event is compared FIRST, and where the rule came
from is only the tie-break within a level. So:

    1. the customer's own rule for this exact Event Type
    2. the selected book's rule for this exact Event Type
    3. the customer's blanket rule
    4. the selected book's default rule
    then the markup rung, and then `unknown`

That ordering is one sentence — *most specific wins; at equal specificity the
customer's own answer wins* — and it is what stops a small blanket discount
silently deleting every specific price a tenant configured.

**MARKUP IS A RUNG, NOT A MULTIPLIER.** It is reached only where rule
resolution returned nothing. "Base cost -> markup -> final charge" is false for
any tenant with pricing rules and this module asserts it is false, by a case
where a rule exists and the markup is provably not applied.

**THE RETIRED WORDS THIS MODULE NEVER SPELLS.** The cost/price discriminator,
the container's pointer and the shape-of-charge column all have ledger entries
that are ceilings as well as floors, so every rule here is built through
``_helpers``, which carries the first two for its callers, and the third is
never passed because the model's default is already the per-unit arithmetic
every case wants.
"""

from datetime import timedelta
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Rate, TenantMarkup
from apps.metering.pricing.services.pricing_service import (
    FROM_THE_CUSTOMERS_OWN_RULES,
    FROM_THE_SELECTED_BOOK,
    PricingSubject,
    ladder_rank,
    resolve_price,
)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject,
    cost_rate_in_default_book,
    rate_in_a_book_nothing_selects,
    rate_in_default_book,
    rate_in_the_providers_default_book,
)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    PRICING_STATUS_WAIVED,
    UNRESOLVED_REASON_COST_RATE_MISSING,
)

#: The one quantity every case here measures, in the amount that makes a
#: per-unit rate and the amount it produces the same number: the rate's
#: denominator is a million micros by default, so a million of them priced at
#: `R` per denominator is exactly `R`. That is arithmetic this module is not
#: about, said once, so every expected figure below is readable as the rung it
#: came from rather than as a sum somebody has to redo.
QUANTITY = "prompt_tokens"
ONE_DENOMINATOR = 1_000_000

PROVIDER = "openai"
EVENT_TYPE = "chat"

#: What each rung charges. Distinct powers of ten so an assertion that reads the
#: wrong rung names it in its own failure message.
RUNG_1_CUSTOMERS_OWN_EXACT = 1_000_000
RUNG_2_BOOKS_EXACT = 2_000_000
RUNG_3_CUSTOMERS_BLANKET = 3_000_000
RUNG_4_BOOKS_DEFAULT = 4_000_000

#: What the supplier charged, and the markup rung over it. 20% of 500_000 is
#: 100_000, so the markup rung answers 600_000 — a figure no rule above
#: produces, which is what lets one assertion tell "the markup applied" from
#: "a rule did".
SUPPLIER_COST = 500_000
MARKUP_PERCENTAGE = 20_000_000
MARKUP_OVER_THE_SUPPLIER_COST = 600_000


def _selectors(**overrides):
    base = {name: "" for name in Rate.SELECTORS}
    base.update(provider=PROVIDER, event_type=EVENT_TYPE)
    base.update(overrides)
    return base


class _ALadderMixin:
    """The four rungs, the markup rung and the cost beneath them, built to order.

    Every case builds the SAME configuration minus the rungs above the one it is
    about, so each answer is a rung winning against everything below it rather
    than a rung answering because nothing else was there. The distinction
    matters: precedence is only observable where the loser exists.
    """

    def _tenant_and_customer(self):
        tenant = Tenant.objects.create(name="T", default_currency="usd")
        return tenant, Customer.objects.create(tenant=tenant, external_id="c1")

    def _build(self, tenant, customer, rungs):
        built = {}
        if "cost" in rungs:
            cost_rate_in_default_book(
                tenant, provider=PROVIDER, event_type=EVENT_TYPE,
                measurement_key=QUANTITY,
                rate_per_unit_micros=SUPPLIER_COST)
        if "markup" in rungs:
            TenantMarkup.objects.create(
                tenant=tenant, markup_percentage_micros=MARKUP_PERCENTAGE)
        # Built low rung first so the customer's book exists before its blanket
        # rule joins it; `rate_in_default_book` reuses one book per customer.
        if "book_default" in rungs:
            built["book_default"] = rate_in_default_book(
                tenant, measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_4_BOOKS_DEFAULT)
        if "customer_blanket" in rungs:
            built["customer_blanket"] = rate_in_default_book(
                tenant, customer=customer, measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_3_CUSTOMERS_BLANKET)
        if "book_exact" in rungs:
            built["book_exact"] = rate_in_default_book(
                tenant, provider=PROVIDER, event_type=EVENT_TYPE,
                measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_2_BOOKS_EXACT)
        if "customer_exact" in rungs:
            built["customer_exact"] = rate_in_default_book(
                tenant, customer=customer, provider=PROVIDER,
                event_type=EVENT_TYPE, measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_1_CUSTOMERS_OWN_EXACT)
        return built

    def _subject(self, tenant, customer, **overrides):
        return PricingSubject(
            receipt_subject=a_usage_event_subject(),
            tenant=tenant, customer=customer,
            selectors=_selectors(),
            measurements={QUANTITY: ONE_DENOMINATOR},
            currency="usd",
            **overrides)

    def _resolve(self, tenant, customer, rungs, **overrides):
        built = self._build(tenant, customer, rungs)
        receipt = resolve_price(self._subject(tenant, customer, **overrides),
                                timezone.now())
        return built, receipt


#: THE TABLE. Each row is one configuration and the whole of what the receipt
#: must then say about the customer's price. `wins` names the rule the answer
#: must be attributable to, or `None` where the answer came from a rung that is
#: not a rule — which is exactly what the provenance column has to be able to
#: express.
LADDER_CASES = [
    dict(
        name="rung 1 — the customer's own rule for this Event Type",
        rungs=("cost", "markup", "book_default", "customer_blanket",
               "book_exact", "customer_exact"),
        method=PRICING_METHOD_DIRECT_EVENT_PRICE,
        amount=RUNG_1_CUSTOMERS_OWN_EXACT,
        status=PRICING_STATUS_KNOWN,
        cost_reason=None, wins="customer_exact"),
    dict(
        name="rung 2 — the selected book's rule for this Event Type",
        rungs=("cost", "markup", "book_default", "customer_blanket",
               "book_exact"),
        method=PRICING_METHOD_DIRECT_EVENT_PRICE,
        amount=RUNG_2_BOOKS_EXACT,
        status=PRICING_STATUS_KNOWN,
        cost_reason=None, wins="book_exact"),
    dict(
        name="rung 3 — the customer's blanket rule",
        rungs=("cost", "markup", "book_default", "customer_blanket"),
        method=PRICING_METHOD_DIRECT_EVENT_PRICE,
        amount=RUNG_3_CUSTOMERS_BLANKET,
        status=PRICING_STATUS_KNOWN,
        cost_reason=None, wins="customer_blanket"),
    dict(
        name="rung 4 — the selected book's default rule",
        rungs=("cost", "markup", "book_default"),
        method=PRICING_METHOD_DIRECT_EVENT_PRICE,
        amount=RUNG_4_BOOKS_DEFAULT,
        status=PRICING_STATUS_KNOWN,
        cost_reason=None, wins="book_default"),
    dict(
        name="the markup rung — reached only because no rule was",
        rungs=("cost", "markup"),
        method=PRICING_METHOD_MARGIN_OVER_COST,
        amount=MARKUP_OVER_THE_SUPPLIER_COST,
        status=PRICING_STATUS_KNOWN,
        cost_reason=None, wins=None),
    dict(
        name="the markup rung over a cost UBB never learned — waived",
        rungs=("markup",),
        method=None,
        amount=None,
        status=PRICING_STATUS_WAIVED,
        cost_reason=UNRESOLVED_REASON_COST_RATE_MISSING, wins=None),
    dict(
        name="no rule and no markup — unknown, and never a zero",
        rungs=("cost",),
        method=None,
        amount=None,
        status=PRICING_STATUS_UNKNOWN,
        cost_reason=None, wins=None),
]


class TheLadderAnswersOneRungAtATimeTest(_ALadderMixin, TestCase):
    """One table of cases over the whole ladder, receipt by receipt.

    Each row asserts everything the receipt says about the price: the method,
    the applied value, the status, the reason where there is one, and the
    provenance. Asserting only the amount would let a receipt name the wrong
    method beside the right number, which is the failure the record exists to
    make impossible.

    ⚠ **THE REASON THERE IS ONE OF IS THE COST SIDE'S, AND THAT IS NOT AN
    OMISSION.** A price side reason exists — `not_applicable_reason`, coined and
    declared with the four statuses — and nothing writes it, because
    `not_applicable` is a fact about the tenant's posture and the job's pricing
    regime rather than about resolution (`pricing/applicability.py` holds the
    rule and says why it has no caller). What the ladder does produce a reason
    for is the waived row: the cost it could not take a margin over says which
    input never arrived, which is what turns "this went unpriced" into something
    a tenant can fix.
    """

    def test_each_rung_answers_and_says_so_on_the_receipt(self):
        for case in LADDER_CASES:
            with self.subTest(case["name"]):
                tenant, customer = self._tenant_and_customer()
                built, receipt = self._resolve(tenant, customer, case["rungs"])
                pricing = receipt["pricing"]

                self.assertEqual(pricing["method"], case["method"])
                self.assertEqual(receipt["totals"]["billed_cost_micros"],
                                 case["amount"])
                self.assertEqual(pricing["status"], case["status"])
                self.assertEqual(
                    receipt["costing"]["detail"]["unresolved_reason"],
                    case["cost_reason"])

                expected_ids = ({QUANTITY: str(built[case["wins"]].id)}
                                if case["wins"] else {})
                self.assertEqual(receipt["provenance"]["price_rate_ids"],
                                 expected_ids)

    def test_an_unpriced_subject_is_never_recorded_as_a_zero(self):
        """The claim the status exists to make, stated on its own.

        `unknown` and a zero are the two answers a reader cannot tell apart once
        a number is written down, and a zero is the one that looks settled. The
        amount is absent, not zero, and the status says why.
        """
        tenant, customer = self._tenant_and_customer()
        _, receipt = self._resolve(tenant, customer, rungs=("cost",))

        self.assertIsNone(receipt["totals"]["billed_cost_micros"])
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_UNKNOWN)
        self.assertIsNone(receipt["pricing"]["method"])


class SpecificityBeatsSourceTest(_ALadderMixin, TestCase):
    """A rule that pins more beats a rule that pins less, from either book.

    This is the property the whole ranking exists for. Under the alternative —
    the customer's own contract answering first at every level — a blanket
    override shadows every specific rule the tenant configured, so agreeing a
    small discount silently deletes a catalogue, with nothing reporting that it
    had.
    """

    def test_a_narrow_rule_in_the_book_beats_a_broad_one_the_customer_owns(self):
        tenant, customer = self._tenant_and_customer()
        built, receipt = self._resolve(
            tenant, customer, rungs=("cost", "markup", "customer_blanket",
                                     "book_exact"))

        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         RUNG_2_BOOKS_EXACT)
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(built["book_exact"].id)})

    def test_at_equal_specificity_the_customers_own_answer_wins(self):
        """The tie-break, and the half that makes "override" mean something."""
        tenant, customer = self._tenant_and_customer()
        built, receipt = self._resolve(
            tenant, customer, rungs=("cost", "markup", "book_exact",
                                     "customer_exact"))

        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         RUNG_1_CUSTOMERS_OWN_EXACT)
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(built["customer_exact"].id)})

    def test_the_ranking_is_specificity_major_and_source_minor(self):
        """The composite rule itself, asserted where it is stated.

        It used to be a sentence on a computed field that counts selectors,
        which is one of the two ingredients and cannot say how they combine.
        """
        tenant, customer = self._tenant_and_customer()
        built = self._build(tenant, customer,
                            rungs=("book_default", "customer_blanket",
                                   "book_exact", "customer_exact"))
        ranked = sorted(
            [(built["book_default"], FROM_THE_SELECTED_BOOK),
             (built["customer_blanket"], FROM_THE_CUSTOMERS_OWN_RULES),
             (built["book_exact"], FROM_THE_SELECTED_BOOK),
             (built["customer_exact"], FROM_THE_CUSTOMERS_OWN_RULES)],
            key=lambda pair: ladder_rank(*pair), reverse=True)

        self.assertEqual([rule.rate_per_unit_micros for rule, _ in ranked],
                         [RUNG_1_CUSTOMERS_OWN_EXACT, RUNG_2_BOOKS_EXACT,
                          RUNG_3_CUSTOMERS_BLANKET, RUNG_4_BOOKS_DEFAULT])

    def test_an_unbreakable_tie_falls_to_the_narrower_book_every_time(self):
        """The tie the ladder does NOT claim to break, pinned anyway (#356).

        Two rules of equal specificity from the same source — one in the
        tenant's book for this provider, one in the provider-agnostic book —
        are separated by nothing `ladder_rank` reads. Ranking is a stable sort,
        and the candidates now arrive from ONE query, so without an order
        imposed on them the answer would be whatever row order the database
        happened to give: a tenant's price decided by a query plan, and
        differently on different days. The narrower book wins, which is the
        answer the tiered walk gave and the only one anybody can predict.

        ⚠ **BUILDING THE TIE TAKES CARE, AND THE FIRST DRAFT OF THIS TEST DID
        NOT HAVE ONE.** Both rules must leave the provider UNPINNED, or the one
        in the provider's book wins on specificity and the tie-break is never
        reached — which is why the fixture separates the book's provider from
        the rule's selector. And both must carry the SAME effective moment,
        because `ladder_rank`'s last key is `valid_from` and two rules created a
        microsecond apart are not tied at all.

        Run repeatedly because that is what an ordering claim means: once could
        be luck.
        """
        tenant, customer = self._tenant_and_customer()
        moment = timezone.now() - timedelta(days=1)
        for attempt in range(5):
            # Cleared at the TOP of each round rather than the bottom: a failing
            # assertion would otherwise skip the cleanup, and the next round's
            # insert would fail the active-rule uniqueness index instead of the
            # claim — four cascading errors hiding the one real answer.
            Rate.objects.filter(tenant=tenant).delete()
            in_the_providers_book = rate_in_the_providers_default_book(
                tenant, PROVIDER, measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_2_BOOKS_EXACT, valid_from=moment)
            rate_in_default_book(
                tenant, measurement_key=QUANTITY,
                rate_per_unit_micros=RUNG_4_BOOKS_DEFAULT, valid_from=moment)
            receipt = resolve_price(self._subject(tenant, customer),
                                    timezone.now())

            with self.subTest(attempt=attempt):
                self.assertEqual(receipt["provenance"]["price_rate_ids"],
                                 {QUANTITY: str(in_the_providers_book.id)})

    def test_the_computed_field_counts_and_no_longer_decides(self):
        """The statement is made ONCE, and not here (#356).

        A property that counts pinned selectors knows one of the ranking's two
        ingredients and nothing about how they combine, so a ranking rule stated
        on it is a rule stated where it cannot be true or false. What is left is
        a count, and a pointer at the function that ranks.
        """
        doc = Rate.specificity.__doc__

        self.assertIn("ladder_rank", doc)
        for verb in ("beats", "tie-breaker", "wins"):
            self.assertNotIn(
                verb, doc,
                f"{verb!r} restates the ranking rule on the computed field")


class NoRuleFallsThroughBetweenBooksTest(_ALadderMixin, TestCase):
    """A book resolution did not select is not reachable, ever.

    Once the books in play are chosen, a rule missing from them does not fall
    through to another book's rule: it falls to the markup rung, and if there is
    no markup it falls to `unknown`. The case is built with a rule that matches
    the event on every selector, so what is being asserted is reachability
    rather than matching.
    """

    def _rule_in_a_book_nothing_selects(self, tenant):
        return rate_in_a_book_nothing_selects(
            tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY, rate_per_unit_micros=RUNG_2_BOOKS_EXACT)

    def test_a_matching_rule_in_an_unselected_book_falls_to_the_markup(self):
        tenant, customer = self._tenant_and_customer()
        self._rule_in_a_book_nothing_selects(tenant)
        _, receipt = self._resolve(tenant, customer, rungs=("cost", "markup"))

        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         MARKUP_OVER_THE_SUPPLIER_COST)
        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(receipt["provenance"]["price_rate_ids"], {})

    def test_with_no_markup_either_it_falls_all_the_way_to_unknown(self):
        tenant, customer = self._tenant_and_customer()
        self._rule_in_a_book_nothing_selects(tenant)
        _, receipt = self._resolve(tenant, customer, rungs=("cost",))

        self.assertIsNone(receipt["totals"]["billed_cost_micros"])
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_UNKNOWN)


class TheMarkupIsARungAndNotAMultiplierTest(_ALadderMixin, TestCase):
    """Markup applies only where rule resolution returned nothing.

    "Base cost -> markup -> final charge" is false for any tenant with pricing
    rules and stays false. The case below has both a rule and a markup, and the
    answer is the rule's figure exactly — not the rule's figure marked up, and
    not the cost marked up.
    """

    def test_a_rule_answers_and_the_markup_is_not_applied_to_it(self):
        tenant, customer = self._tenant_and_customer()
        built, receipt = self._resolve(
            tenant, customer, rungs=("cost", "markup", "book_default"))

        self.assertEqual(receipt["totals"]["billed_cost_micros"],
                         RUNG_4_BOOKS_DEFAULT)
        self.assertNotEqual(receipt["totals"]["billed_cost_micros"],
                            MARKUP_OVER_THE_SUPPLIER_COST)
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(built["book_default"].id)})

    def test_the_markup_rung_names_the_method_it_is(self):
        """A markup and a rule declaring a margin are ONE method at two rungs.

        Which is exactly why specificity-before-source is coherent: a tenant
        reading two receipts, one saying "your book's rule" and one saying "your
        tenant default", is reading one method with two sources.
        """
        tenant, customer = self._tenant_and_customer()
        _, receipt = self._resolve(tenant, customer, rungs=("cost", "markup"))

        self.assertEqual(receipt["pricing"]["method"],
                         PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)


class AMarginIsOneMethodAtTwoRungsTest(_ALadderMixin, TestCase):
    """A rule declaring a margin gets the markup rung's answers, not its own.

    A markup and a `margin_over_cost` rule are the SAME METHOD at two rungs,
    which is exactly why specificity-before-source is coherent — so a tenant
    must not get a different status for writing the percentage in a different
    place. Both cases below are the rule rung; their answers are
    `a_margin_has_no_basis`'s, which the markup rung asks too.

    ⚠ **NEITHER SETTLES, AND THE SECOND IS A RESIDUAL RATHER THAN A RULING.**
    No percentage column exists on a rule while markup is a separate record —
    the check that keeps a rule from composing refuses the two money terms this
    table can express — so a margin rule carries nothing to compute with. The
    ticket that moves a percentage onto the rule is the ticket that makes the
    believed-basis case settle. What must NOT happen meanwhile is the engine
    computing the rule's zero terms and reporting a settled zero, which is the
    silent price this slice exists to delete.
    """

    def _a_margin_rule_in_the_book(self, tenant):
        return rate_in_default_book(
            tenant, provider=PROVIDER, event_type=EVENT_TYPE,
            measurement_key=QUANTITY,
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST)

    def test_over_a_cost_ubb_never_learned_the_charge_is_waived(self):
        tenant, customer = self._tenant_and_customer()
        rule = self._a_margin_rule_in_the_book(tenant)
        _, receipt = self._resolve(tenant, customer, rungs=("markup",))

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_WAIVED)
        self.assertIsNone(receipt["totals"]["billed_cost_micros"])
        self.assertIsNone(receipt["pricing"]["method"])
        # The rule is still on the record: it matched, and what it could not do
        # is compute. A receipt that named no rule here would say the tenant
        # had configured nothing.
        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(rule.id)})

    def test_over_a_believed_cost_it_is_unknown_and_never_a_settled_zero(self):
        tenant, customer = self._tenant_and_customer()
        self._a_margin_rule_in_the_book(tenant)
        _, receipt = self._resolve(tenant, customer, rungs=("cost", "markup"))

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_UNKNOWN)
        self.assertIsNone(receipt["totals"]["billed_cost_micros"])
        self.assertIsNone(receipt["pricing"]["method"])

    def test_the_markup_rung_is_not_reached_past_a_rule_that_could_not_compute(self):
        """AC: markup is reached only where rule resolution returned NOTHING.

        A rule that matched and could not compute is not nothing, and the
        difference is visible: the markup rung would have answered a number
        here, over a cost it believes.
        """
        tenant, customer = self._tenant_and_customer()
        self._a_margin_rule_in_the_book(tenant)
        _, receipt = self._resolve(tenant, customer, rungs=("cost", "markup"))

        self.assertNotEqual(receipt["totals"]["billed_cost_micros"],
                            MARKUP_OVER_THE_SUPPLIER_COST)


class TheInstantIsAParameterAndNotAClockReadTest(_ALadderMixin, TestCase):
    """The as-of instant arrives as an argument, and nothing reads a clock.

    This is the live defect the seam fixes rather than a testing convenience: a
    resolution keyed on the current instant answers for the wrong moment the
    day a boundary is dated forward, and a row that faithfully carries a future
    boundary is not the same as a row honoured at one.
    """

    def _a_rule_that_replaces_another_at(self, tenant, boundary):
        """Two versions of one rule, closed and opened at the same instant."""
        outgoing = rate_in_default_book(
            tenant, measurement_key=QUANTITY,
            rate_per_unit_micros=RUNG_4_BOOKS_DEFAULT,
            valid_from=boundary - timedelta(days=30), valid_to=boundary)
        incoming = rate_in_default_book(
            tenant, measurement_key=QUANTITY,
            rate_per_unit_micros=RUNG_3_CUSTOMERS_BLANKET,
            valid_from=boundary)
        return outgoing, incoming

    def test_the_answer_follows_the_argument_and_not_the_frozen_clock(self):
        tenant, customer = self._tenant_and_customer()
        boundary = timezone.now() + timedelta(days=7)
        outgoing, incoming = self._a_rule_that_replaces_another_at(
            tenant, boundary)

        before = resolve_price(self._subject(tenant, customer),
                               boundary - timedelta(seconds=1))
        after = resolve_price(self._subject(tenant, customer),
                              boundary + timedelta(seconds=1))

        self.assertEqual(before["provenance"]["price_rate_ids"],
                         {QUANTITY: str(outgoing.id)})
        self.assertEqual(after["provenance"]["price_rate_ids"],
                         {QUANTITY: str(incoming.id)})

    def test_resolution_reads_no_clock_at_all(self):
        """The strong form: a clock that raises does not stop it answering.

        A test that only compared two answers would pass against an
        implementation that read the clock for something else — the effective
        instant it stamps on the record, say — and stamped the wrong moment on
        every receipt.
        """
        tenant, customer = self._tenant_and_customer()
        boundary = timezone.now() + timedelta(days=7)
        _, incoming = self._a_rule_that_replaces_another_at(tenant, boundary)
        as_of = boundary + timedelta(seconds=1)
        subject = self._subject(tenant, customer)

        def _the_clock_is_not_available():
            raise AssertionError("resolve_price read the clock")

        with patch.object(timezone, "now", _the_clock_is_not_available):
            receipt = resolve_price(subject, as_of)

        self.assertEqual(receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(incoming.id)})
        self.assertEqual(receipt["effective_at"], as_of.isoformat())
