"""A markup charge can be explained: which percentage, and from where (#357).

**THE DEFECT THIS MODULE CLOSES.** Markup is the DEFAULT pricing path — it is
what runs when no rule matches, so it produces most of the prices in the system
— and the record it left said only that markup had happened. Not which
percentage, not which rung of configuration supplied it, not which record it
came from. A tenant asked by their own customer *"why is this line £36?"* had
nothing to show them, and could not reconstruct it afterwards either, because a
markup record can be edited.

**THE RULING: A RESOLVED MARKUP IS A RESOLVED RULE, AND IS RECORDED LIKE ONE**
(#147 §9.1). The receipt names the method, holds the applied percentage BY
VALUE, and names in `provenance` the rung and the record the percentage came
from. There is no second shape for "it was markup": it is what the receipt
already requires of every priced event, applied to the path that produces most
of them.

**WHICH IS WHY SPECIFICITY-BEFORE-SOURCE IS COHERENT.** A markup and a rule
declaring `margin_over_cost` are the SAME METHOD AT TWO RUNGS. A tenant reading
two receipts, one saying *"your book's rule"* and one saying *"your tenant
default"*, is reading one method with two sources — not two methods — and that
is only true if both are recorded the same way.

**⚠ UBB SHIPS NO CATALOGUE.** No seeded markup, no default percentage, no
starter value. A tenant that has declared nothing has NO markup rung and
resolution answers `unknown`. That is the constraint a helpful default is most
likely to violate, so it is asserted here against the record itself as well as
against the resolver.

**THE WORD IS "MARKUP" AND IT IS RETAINED DELIBERATELY** (#147 §9.1, #154 §3).
It must not drift into "margin", which names only the displayed derived figure.
What is retired is the unit SPELLING, where millionths of a percent hid under a
money suffix — and the replacement rung this module resolves through is
declared in the honest one.
"""
from collections import namedtuple
from uuid import uuid4

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import TenantDefaultMarkup
from apps.metering.pricing.receipts import (
    REQUIRED_MARKUP_KEYS,
    SECTION_KEYS,
    TOP_LEVEL_KEYS,
)
from apps.metering.pricing.services.markup_service import (
    MARKUP_RUNG_TENANT_DEFAULT,
)
from apps.metering.pricing.services.pricing_service import (
    PricingSubject,
    resolve_price,
)
from apps.metering.pricing.tests._helpers import (
    a_usage_event_subject,
    cost_rate_in_default_book,
    declares_a_markup,
    rate_in_default_book,
)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST,
    PRICING_METHOD_VALUES,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
)

QUANTITY = "prompt_tokens"
ONE_DENOMINATOR = 1_000_000

#: What the supplier charged, the rung taken over it, and the answer. 20% of
#: 500_000 is 100_000, so the customer pays 600_000 — a figure that is neither
#: the cost nor a rule's, which is what lets one assertion say which rung
#: answered.
SUPPLIER_COST = 500_000
DECLARED_MARKUP = 20_000_000
MARKED_UP = 600_000

#: What the rule rung charges, in the comparison that shows there is one shape.
#: Deliberately not the marked-up figure.
A_RULES_PRICE = 7_000_000


def _selectors():
    from apps.metering.pricing.models import Rate
    return {name: "" for name in Rate.SELECTORS}


def _key_paths(value, prefix=()):
    """Every key path in a record, as a set — the record's SHAPE.

    Recursive because "there is no second shape for markup" is a claim about the
    whole record and not only its top level: a `markup_applied` flag beside
    `method` in the price section, or a ninth top-level key, would both satisfy
    a comparison of top-level keys alone.

    ⚠ **AND WHAT IT CANNOT SEE IS SAID OUT LOUD.** The two OPEN containers —
    `pricing.detail` and `provenance` — are where this commit writes, so keys
    differing INSIDE them are the expected difference rather than a second
    shape, and the case below excludes them by path. A flag added in there would
    pass. That is the limit of what "one shape" can mean for a record whose
    method-specific parts are deliberately open, and the boundary is what
    constrains their contents instead.
    """
    if not isinstance(value, dict):
        return set()
    paths = set()
    for key, inner in value.items():
        paths.add(prefix + (key,))
        paths |= _key_paths(inner, prefix + (key,))
    return paths


#: WHAT A CASE HAS TO HAND once it has priced an event through the markup rung.
#:
#: Named rather than positional, because the four travel together through every
#: case here and three of them are only interesting beside the fourth — the
#: record the percentage came from is what the receipt has to name, and reading
#: it out of a tuple by index is how an assertion comes to be about whichever
#: element moved.
MarkupPriced = namedtuple("MarkupPriced", "tenant customer rung receipt")


class _AMarkupPricedEventMixin:
    """One tenant, one cost, and the rungs each case wants — nothing else."""

    def _tenant_and_customer(self):
        tenant = Tenant.objects.create(name="T", default_currency="usd")
        return tenant, Customer.objects.create(tenant=tenant, external_id="c1")

    def _a_supplier_cost(self, tenant):
        cost_rate_in_default_book(
            tenant, measurement_key=QUANTITY,
            rate_per_unit_micros=SUPPLIER_COST)

    def _resolve(self, tenant, customer):
        return resolve_price(
            PricingSubject(
                receipt_subject=a_usage_event_subject(),
                tenant=tenant, customer=customer, selectors=_selectors(),
                measurements={QUANTITY: ONE_DENOMINATOR}, currency="usd"),
            timezone.now())

    def _priced_by_the_markup_rung(self):
        """A tenant whose only price rung is the markup it declared."""
        tenant, customer = self._tenant_and_customer()
        self._a_supplier_cost(tenant)
        rung = declares_a_markup(tenant, percentage_micros=DECLARED_MARKUP)
        return MarkupPriced(tenant, customer, rung,
                            self._resolve(tenant, customer))

    def _stored(self, tenant, customer, receipt):
        """The receipt written down, so a later read is a read of the RECORD.

        A resolution that is never persisted cannot be shown to have survived
        anything: a dictionary in a local variable does not change because a row
        did, so asserting that it has not is asserting a property of Python. The
        receipt's whole claim is about what a tenant can still be shown after
        the configuration behind it has moved, and that claim is only askable of
        a record that went to the database and came back.

        Addressed through the model's own column constant, never spelled: the
        column still carries a word the registry retired and the ticket that
        renames it is not this one.
        """
        posting = Posting.objects.create(
            tenant=tenant, customer=customer,
            idempotency_key=str(uuid4()),
            **{Posting.RECEIPT_COLUMN: receipt})
        return posting


class TheReceiptRecordsTheAppliedPercentageTest(_AMarkupPricedEventMixin,
                                                TestCase):
    """The number a tenant has to be able to show, on the record, by value."""

    def test_the_method_is_named_and_the_percentage_is_on_the_record(self):
        receipt = self._priced_by_the_markup_rung().receipt
        pricing = receipt["pricing"]

        self.assertEqual(pricing["method"], PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(pricing["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"], MARKED_UP)
        self.assertEqual(pricing["detail"]["markup"]["micro_percent"],
                         DECLARED_MARKUP)

    def test_a_reader_holding_only_the_record_can_redo_the_sum(self):
        """The content obligation, asked of the rung that produces most prices.

        A percentage with no basis beside it is not reproducible — and the basis
        cannot always be taken from the totals, because a cost the tenant
        declared does not exist nulls that column while still being a genuine
        zero to take a margin over. So the terms carry the basis too, and this
        redoes the arithmetic from the record alone.

        ⚠ **THERE WAS A THIRD TERM UNTIL #369** — a flat per-event addend, which
        two now-deleted rungs could supply. The sum below no longer adds it, and
        the exactness case beside this one is what refuses it coming back.
        """
        receipt = self._priced_by_the_markup_rung().receipt
        terms = receipt["pricing"]["detail"]["markup"]

        basis = terms["basis_micros"]
        margin = (basis * terms["micro_percent"] + 50_000_000) // 100_000_000
        self.assertEqual(basis + margin,
                         receipt["totals"]["billed_cost_micros"])

    def test_the_terms_are_the_whole_of_what_the_record_promises(self):
        """Exact, not a minimum: a term arriving here is a decision."""
        receipt = self._priced_by_the_markup_rung().receipt

        self.assertEqual(set(receipt["pricing"]["detail"]["markup"]),
                         set(REQUIRED_MARKUP_KEYS))


class TheProvenanceNamesTheRungAndTheRecordTest(_AMarkupPricedEventMixin,
                                                TestCase):
    """Which rung supplied the percentage, and which record held it."""

    def test_both_are_named(self):
        priced = self._priced_by_the_markup_rung()

        self.assertEqual(priced.receipt["provenance"]["markup"],
                         {"rung": MARKUP_RUNG_TENANT_DEFAULT,
                          "record_id": str(priced.rung.id)})

    def test_the_recorded_percentage_survives_an_edit_to_that_record(self):
        """The reason the receipt holds VALUES and keeps pointers apart.

        Configuration can be edited; a receipt cannot. Re-resolving after the
        edit answers the new percentage — which is what makes this a real edit
        rather than a no-op — while the record written before it still says what
        the tenant was actually charged, and still names the row.

        ⚠ **THE RECEIPT IS READ BACK OUT OF THE DATABASE AND NOT OUT OF A
        LOCAL.** A dictionary in a variable does not change because a row did,
        so a case that resolved, edited and then re-read its own local would be
        asserting a property of Python rather than anything about the record.
        """
        priced = self._priced_by_the_markup_rung()
        posting = self._stored(priced.tenant, priced.customer, priced.receipt)

        priced.rung.markup_micro_percent = 90_000_000
        priced.rung.save()
        after = self._resolve(priced.tenant, priced.customer)

        self.assertEqual(after["pricing"]["detail"]["markup"]["micro_percent"],
                         90_000_000)
        posting.refresh_from_db()
        stored = getattr(posting, Posting.RECEIPT_COLUMN)
        self.assertEqual(stored["pricing"]["detail"]["markup"]["micro_percent"],
                         DECLARED_MARKUP)
        self.assertEqual(stored["totals"]["billed_cost_micros"], MARKED_UP)
        self.assertEqual(stored["provenance"]["markup"]["record_id"],
                         str(priced.rung.id))

    def test_a_withdrawn_rung_leaves_the_stored_receipt_intact(self):
        """A pointer may dangle; the explanation may not.

        Withdrawing the rung deletes the record the receipt names. The row it
        names is gone and every term it was charged on is still on the stored
        record, which is the whole of why `provenance` holds ids and `detail`
        holds values.
        """
        priced = self._priced_by_the_markup_rung()
        posting = self._stored(priced.tenant, priced.customer, priced.receipt)
        record_id = str(priced.rung.id)

        priced.rung.delete()

        self.assertFalse(TenantDefaultMarkup.objects.exists())
        posting.refresh_from_db()
        stored = getattr(posting, Posting.RECEIPT_COLUMN)
        self.assertEqual(stored["provenance"]["markup"]["record_id"], record_id)
        self.assertEqual(stored["pricing"]["detail"]["markup"]["micro_percent"],
                         DECLARED_MARKUP)


class ThereIsNoSecondShapeForMarkupTest(_AMarkupPricedEventMixin, TestCase):
    """A markup-resolved receipt and a rule-resolved one are one record.

    Not "similar": the same shape, with the same fields answering the same
    questions out of the same vocabularies. What differs is which records the
    provenance names and which terms the detail carries — and both of those are
    the open, per-method parts of the record that a rule-resolved receipt uses
    too. Anything else differing would be a second shape, which is exactly what
    a reader comparing two receipts must not have to learn.
    """

    def _priced_by_a_rule(self):
        tenant, customer = self._tenant_and_customer()
        self._a_supplier_cost(tenant)
        declares_a_markup(tenant, percentage_micros=DECLARED_MARKUP)
        rule = rate_in_default_book(
            tenant, measurement_key=QUANTITY,
            rate_per_unit_micros=A_RULES_PRICE)
        return rule, self._resolve(tenant, customer)

    def test_both_records_have_the_same_shape_outside_the_open_containers(self):
        by_markup = self._priced_by_the_markup_rung().receipt
        _, by_rule = self._priced_by_a_rule()

        differing = _key_paths(by_markup) ^ _key_paths(by_rule)
        self.assertTrue(
            all(path[:2] in (("pricing", "detail"),) or path[0] == "provenance"
                for path in differing),
            f"a key outside the open containers tells the two apart: "
            f"{sorted(differing)}")

    def test_the_declared_parts_of_the_record_are_identical_key_for_key(self):
        by_markup = self._priced_by_the_markup_rung().receipt
        _, by_rule = self._priced_by_a_rule()

        self.assertEqual(set(by_markup), set(by_rule))
        self.assertEqual(set(by_markup["pricing"]), set(by_rule["pricing"]))
        self.assertEqual(set(by_markup["totals"]), set(by_rule["totals"]))
        # ...and both are the DECLARED shape, not merely each other. Comparing
        # the two alone would stay green the day they drift together.
        self.assertEqual(set(by_markup), set(TOP_LEVEL_KEYS))
        self.assertEqual(set(by_markup["pricing"]), set(SECTION_KEYS))
        self.assertEqual(set(by_rule["costing"]), set(SECTION_KEYS))

    def test_one_method_field_answers_for_both_out_of_one_vocabulary(self):
        by_markup = self._priced_by_the_markup_rung().receipt
        _, by_rule = self._priced_by_a_rule()

        self.assertIn(by_markup["pricing"]["method"], PRICING_METHOD_VALUES)
        self.assertIn(by_rule["pricing"]["method"], PRICING_METHOD_VALUES)
        self.assertEqual(by_rule["pricing"]["method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(by_markup["pricing"]["status"],
                         by_rule["pricing"]["status"])

    def test_the_provenance_is_what_says_which_of_them_answered(self):
        rung_receipt = self._priced_by_the_markup_rung().receipt
        rule, rule_receipt = self._priced_by_a_rule()

        self.assertEqual(rung_receipt["provenance"]["price_rate_ids"], {})
        self.assertIn("markup", rung_receipt["provenance"])
        self.assertEqual(rule_receipt["provenance"]["price_rate_ids"],
                         {QUANTITY: str(rule.id)})
        self.assertNotIn("markup", rule_receipt["provenance"])


class NoMarkupIsSeededAnywhereTest(_AMarkupPricedEventMixin, TestCase):
    """A tenant that has declared nothing has no rung, and no rung is `unknown`.

    The constraint most likely to be violated by a helpful default, so it is
    asserted at both places one could be introduced: the column, which has no
    default to fall back on, and resolution, which must not read an absence as a
    zero or as the supplier's own figure.
    """

    def test_a_new_tenant_has_no_declared_rung(self):
        tenant, _ = self._tenant_and_customer()

        self.assertFalse(
            TenantDefaultMarkup.objects.filter(tenant=tenant).exists())

    def test_resolution_answers_unknown_rather_than_zero_or_the_cost(self):
        tenant, customer = self._tenant_and_customer()
        self._a_supplier_cost(tenant)

        receipt = self._resolve(tenant, customer)

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_UNKNOWN)
        self.assertIsNone(receipt["totals"]["billed_cost_micros"])
        self.assertIsNone(receipt["pricing"]["method"])
        self.assertNotIn("markup", receipt["pricing"]["detail"])
        self.assertNotIn("markup", receipt["provenance"])
        # And the cost IS known, so `unknown` here is a statement about the
        # price and not a consequence of an unresolved basis.
        self.assertEqual(receipt["totals"]["provider_cost_micros"],
                         SUPPLIER_COST)

    def test_a_rung_of_zero_is_a_decision_and_an_absent_rung_is_not(self):
        """The distinction the whole rule turns on, in one pair of receipts.

        A declared zero says *charge my customer what the call cost*, and
        settles at the supplier's figure with the percentage on the record. No
        declaration says nothing, and answers `unknown`. The two used to be one
        number.
        """
        tenant, customer = self._tenant_and_customer()
        self._a_supplier_cost(tenant)
        declares_a_markup(tenant, percentage_micros=0)

        receipt = self._resolve(tenant, customer)

        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_KNOWN)
        self.assertEqual(receipt["totals"]["billed_cost_micros"], SUPPLIER_COST)
        self.assertEqual(receipt["pricing"]["detail"]["markup"]["micro_percent"],
                         0)
