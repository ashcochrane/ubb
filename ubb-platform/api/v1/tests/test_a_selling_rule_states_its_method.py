"""A selling rule states its pricing method; nothing else states one (R10-W4).

#190 comment 5831552855 §1: the rates route hid each rule's method, so a
`margin_over_cost` rule — stored with zero terms by `ck_rate_never_composes` —
read exactly as a direct price of zero. The owner's ruling 4 (2026-10-27) went
further than publishing what a null meant: the null that MEANT
`direct_event_price` is gone from storage. Every rule in a Pricing Book states
its method, a cost book's rate states none, and the database holds both halves
(`ck_rate_a_selling_rule_states_its_method`, driven through every door by
`TheTableHoldsTheRuleTest`). The backfill that stated the method on rules
stored before the ruling (`pricing/0034`) was run here through the executor
until the cutover (#190) deleted it with every such row.
"""
import json
from pathlib import Path
from types import SimpleNamespace

from django.db import IntegrityError, connection, transaction
from django.test import Client, TestCase

from api.v1.tests._helpers import a_tenant
from apps.metering.pricing.models import (
    STATES_ITS_SELLING_METHOD_CHECK, Rate)
from apps.metering.pricing.services.pricing_service import _priced_by_rules
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book, the_book_holding)
from apps.platform.event_types.tests._helpers import declares_a_quantity
from core.vocabulary import (
    COSTING_STATUS_KNOWN, PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST, PRICING_METHOD_VALUES)

#: The committed contract a client generates from.
SPEC = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"

QUANTITY = "input_tokens"
ANOTHER_QUANTITY = "output_tokens"


class _APricingTenantTestCase(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant, self.raw_key = a_tenant(
            "Selling", products=("metering", "billing"))
        for code in (QUANTITY, ANOTHER_QUANTITY):
            declares_a_quantity(self.tenant, code)

    def _get(self, path):
        return self.http.get(path, HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json",
                              HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def _rates(self, book):
        answered = self._get(f"/api/v1/metering/pricing/books/{book.id}/rates")
        self.assertEqual(answered.status_code, 200, answered.content)
        return {row["id"]: row for row in answered.json()["data"]}


class TheRatesRouteSaysEachRulesMethodTest(_APricingTenantTestCase):

    def test_a_margin_rule_and_a_zero_price_read_differently(self):
        """The done condition: the same zero terms, two methods, two readings."""
        margin = rate_in_default_book(
            self.tenant, provider="p1", measurement_key=QUANTITY,
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)
        free = rate_in_default_book(
            self.tenant, provider="p2", measurement_key=QUANTITY,
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE,
            rate_per_unit_micros=0, fixed_micros=0)

        rows = self._rates(the_book_holding(margin))

        terms = ("rate_structure", "rate_per_unit_micros", "unit_quantity",
                 "fixed_micros")
        self.assertEqual({k: rows[str(margin.id)][k] for k in terms},
                         {k: rows[str(free.id)][k] for k in terms})
        self.assertEqual(rows[str(margin.id)]["pricing_method"],
                         PRICING_METHOD_MARGIN_OVER_COST)
        self.assertEqual(rows[str(free.id)]["pricing_method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_a_cost_rate_states_no_method_and_says_so(self):
        cost = cost_rate_in_default_book(self.tenant, measurement_key=QUANTITY,
                                         rate_per_unit_micros=5)

        row = self._rates(the_book_holding(cost))[str(cost.id)]

        self.assertIn("pricing_method", row)
        self.assertIsNone(row["pricing_method"])


class APublishStatesTheMethodTest(_APricingTenantTestCase):

    def _publish(self, book, change):
        declared = self._post(
            f"/api/v1/metering/pricing/books/{book.id}/publishes",
            {"changes": [change]})
        return declared

    def test_an_add_naming_no_method_opens_a_rule_stating_a_direct_price(self):
        anchor = rate_in_default_book(self.tenant, measurement_key=QUANTITY,
                                      rate_per_unit_micros=1)
        book = the_book_holding(anchor)
        declared = self._publish(book, {
            "line": "rate", "kind": "add", "measurement_key": ANOTHER_QUANTITY,
            "rate_per_unit_micros": 3})
        self.assertEqual(declared.status_code, 200, declared.content)
        published = self._post(
            f"/api/v1/metering/pricing/books/{book.id}/publishes/"
            f"{declared.json()['id']}/publish", {})
        self.assertEqual(published.status_code, 200, published.content)

        opened = Rate.objects.get(pricing_book=book,
                                  measurement__code=ANOTHER_QUANTITY)
        self.assertEqual(opened.pricing_method, PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(self._rates(book)[str(opened.id)]["pricing_method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_a_cost_books_change_naming_a_method_is_refused_by_name(self):
        cost = cost_rate_in_default_book(self.tenant, measurement_key=QUANTITY,
                                         rate_per_unit_micros=5)
        book = the_book_holding(cost)

        for method in (PRICING_METHOD_DIRECT_EVENT_PRICE,
                       PRICING_METHOD_MARGIN_OVER_COST):
            with self.subTest(method=method):
                refused = self._publish(book, {
                    "line": "rate", "kind": "add",
                    "measurement_key": ANOTHER_QUANTITY,
                    "rate_per_unit_micros": 3, "pricing_method": method})

                self.assertEqual(refused.status_code, 422, refused.content)
                self.assertEqual(refused.json()["code"], "validation_error")
                self.assertIn("pricing_method", refused.json()["detail"])
        self.assertEqual(Rate.objects.filter(cost_book=book).count(), 1)

    def test_a_diff_states_a_selling_rules_method_and_a_cost_rates_null(self):
        """`RuleTermsOut` (the owner's review of #620): present on every diff
        row, the method a Pricing Book rule will state, and null on a cost
        book's rate — which derives no customer price — never omitted."""
        anchor = rate_in_default_book(self.tenant, measurement_key=QUANTITY,
                                      rate_per_unit_micros=1)
        cost = cost_rate_in_default_book(self.tenant, measurement_key=QUANTITY,
                                         rate_per_unit_micros=5)
        for book, expected in ((the_book_holding(anchor),
                                PRICING_METHOD_DIRECT_EVENT_PRICE),
                               (the_book_holding(cost), None)):
            with self.subTest(book=type(book).__name__):
                declared = self._publish(book, {
                    "line": "rate", "kind": "add",
                    "measurement_key": ANOTHER_QUANTITY,
                    "rate_per_unit_micros": 3})
                self.assertEqual(declared.status_code, 200, declared.content)
                (row,) = declared.json()["diff"]
                self.assertIn("pricing_method", row["after"])
                self.assertEqual(row["after"]["pricing_method"], expected)


class TheContractStatesTheMethodWhereItAlwaysExistsTest(TestCase):
    """The committed contract, read as a client generator reads it: required
    and never null where every row is a selling rule, required and nullable
    where a cost rate shares the row (the owner's review of #620)."""

    def _property(self, schema, field):
        spec = json.loads(SPEC.read_text(encoding="utf-8"))
        node = spec["components"]["schemas"][schema]
        return field in node.get("required", []), node["properties"][field]

    def test_an_inherited_rule_always_states_one(self):
        required, node = self._property("InheritedPricingRule", "pricing_method")
        self.assertTrue(required)
        self.assertNotIn("anyOf", node)
        self.assertEqual(set(node["enum"]), set(PRICING_METHOD_VALUES))

    def test_a_diff_row_states_one_or_says_null_never_omits(self):
        required, node = self._property("RuleTermsOut", "pricing_method")
        self.assertTrue(required)
        self.assertIn({"type": "null"}, node["anyOf"])


class TheTableHoldsTheRuleTest(TestCase):
    """Every door: a row created, updated through the queryset, and by SQL."""

    def setUp(self):
        self.tenant, _ = a_tenant("Table")
        declares_a_quantity(self.tenant, QUANTITY)
        self.selling = rate_in_default_book(self.tenant, measurement_key=QUANTITY)
        self.cost = cost_rate_in_default_book(self.tenant, measurement_key=QUANTITY)

    def _refused(self, write):
        with self.assertRaisesRegex(IntegrityError, STATES_ITS_SELLING_METHOD_CHECK):
            with transaction.atomic():
                write()

    def test_a_selling_rule_with_no_method_is_refused_through_every_door(self):
        self._refused(lambda: Rate.objects.filter(pk=self.selling.pk).update(
            pricing_method=None))
        self._refused(lambda: Rate.objects.create(
            tenant=self.tenant, pricing_book=the_book_holding(self.selling),
            measurement=self.selling.measurement, provider="other",
            pricing_method=None))

        def raw():
            with connection.cursor() as cursor:
                cursor.execute("UPDATE ubb_rate SET pricing_method = NULL "
                               "WHERE id = %s", [str(self.selling.pk)])
        self._refused(raw)

    def test_a_method_off_a_selling_rule_is_refused(self):
        for method in (PRICING_METHOD_DIRECT_EVENT_PRICE,
                       PRICING_METHOD_MARGIN_OVER_COST):
            with self.subTest(method=method):
                self._refused(lambda: Rate.objects.filter(pk=self.cost.pk).update(
                    pricing_method=method, rate_per_unit_micros=0,
                    fixed_micros=0))
                self._refused(lambda: Rate.objects.create(
                    tenant=self.tenant, measurement=self.cost.measurement,
                    provider="nowhere", pricing_method=method,
                    rate_per_unit_micros=0, fixed_micros=0))

    def test_both_methods_on_a_selling_rule_and_none_elsewhere_are_admitted(self):
        Rate.objects.filter(pk=self.selling.pk).update(
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)
        Rate.objects.filter(pk=self.selling.pk).update(
            pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.cost.refresh_from_db()
        self.assertIsNone(self.cost.pricing_method)


class TheResolverRefusesARuleWithNoMethodTest(TestCase):
    """The null branch is gone: a rule the table cannot hold is refused, never
    read as a direct price (ruling 4's notes: no silent default)."""

    def test_a_rule_with_no_method_is_refused_not_defaulted(self):
        with self.assertRaisesRegex(ValueError, "states its pricing method"):
            _priced_by_rules([SimpleNamespace(pricing_method=None)], 5,
                             COSTING_STATUS_KNOWN)

    def test_a_stated_direct_price_answers_its_own_terms(self):
        self.assertEqual(
            _priced_by_rules(
                [SimpleNamespace(pricing_method=PRICING_METHOD_DIRECT_EVENT_PRICE)],
                5, COSTING_STATUS_KNOWN)[:2],
            (5, PRICING_METHOD_DIRECT_EVENT_PRICE))
