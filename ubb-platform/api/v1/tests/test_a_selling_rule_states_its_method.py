"""A selling rule states its pricing method; nothing else states one (R10-W4).

#190 comment 5831552855 §1: the rates route hid each rule's method, so a
`margin_over_cost` rule — stored with zero terms by `ck_rate_never_composes` —
read exactly as a direct price of zero. The owner's ruling 4 (2026-10-27) went
further than publishing what a null meant: the null that MEANT
`direct_event_price` is gone from storage. Every rule in a Pricing Book states
its method, a cost book's rate states none, and the database holds both halves.
"""
import json
from types import SimpleNamespace

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import Client, TestCase

from apps.metering.pricing.models import (
    STATES_ITS_SELLING_METHOD_CHECK, CostBook, PricingBook, Rate)
from apps.metering.pricing.services.pricing_service import _priced_by_rules
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, database_rules_guarding, rate_in_default_book,
    the_book_holding)
from apps.platform.event_types.tests._helpers import declares_a_quantity
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_STATUS_KNOWN, PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_METHOD_MARGIN_OVER_COST)

QUANTITY = "input_tokens"
ANOTHER_QUANTITY = "output_tokens"


class _APricingTenantTestCase(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(
            name="Selling", products=["metering", "billing"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="k")
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


class TheTableHoldsTheRuleTest(TestCase):
    """Every door: a row created, updated through the queryset, and by SQL."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Table", products=["metering"])
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


class TheBackfillStatesTheMethodTest(TestCase):
    """`pricing/0034` run for real, through the executor and back."""

    BEFORE = ("pricing", "0033_rules_charges_and_cost_books_are_usd_only")
    AFTER = ("pricing", "0034_a_selling_rule_states_its_method")

    def _migrate_to(self, target):
        with connection.cursor() as cursor:
            cursor.execute("SET CONSTRAINTS ALL IMMEDIATE")
        MigrationExecutor(connection).migrate([target])

    def tearDown(self):
        self._migrate_to(self.AFTER)

    def _method(self, rate):
        with connection.cursor() as cursor:
            cursor.execute("SELECT pricing_method FROM ubb_rate WHERE id = %s",
                           [str(rate.pk)])
            return cursor.fetchone()[0]

    def test_a_null_on_a_selling_rule_becomes_a_stated_direct_price(self):
        tenant = Tenant.objects.create(name="Old", products=["metering"])
        declares_a_quantity(tenant, QUANTITY)
        selling = rate_in_default_book(tenant, measurement_key=QUANTITY)
        margin = rate_in_default_book(
            tenant, provider="m", measurement_key=QUANTITY,
            pricing_method=PRICING_METHOD_MARGIN_OVER_COST,
            rate_per_unit_micros=0, fixed_micros=0)
        cost = cost_rate_in_default_book(tenant, measurement_key=QUANTITY)
        triggers = sorted(name for name, _, _ in database_rules_guarding("ubb_rate"))

        self._migrate_to(self.BEFORE)
        with connection.cursor() as cursor:
            cursor.execute("UPDATE ubb_rate SET pricing_method = NULL "
                           "WHERE id = %s", [str(selling.pk)])
        self._migrate_to(self.AFTER)

        self.assertEqual(self._method(selling), PRICING_METHOD_DIRECT_EVENT_PRICE)
        self.assertEqual(self._method(margin), PRICING_METHOD_MARGIN_OVER_COST)
        self.assertIsNone(self._method(cost))
        # No trigger was lifted for the step, and none went missing.
        self.assertEqual(
            sorted(name for name, _, _ in database_rules_guarding("ubb_rate")),
            triggers)
        self.assertEqual(len(triggers), 2)

        self._migrate_to(self.BEFORE)
        self.assertEqual(self._method(selling), PRICING_METHOD_DIRECT_EVENT_PRICE)
