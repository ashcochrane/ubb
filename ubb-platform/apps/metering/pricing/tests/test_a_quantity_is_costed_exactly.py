"""A recorded quantity is costed exactly, and refused by name where the amount
cannot be held (#603 rulings 3-5 and 7, ADR-0020).

A quantity is canonical exact text, so costing never reads it as a binary
float, never through `Decimal`'s 28-digit context, and never with `Decimal`'s
`//`: the integers are built from the text's own digits and the one division
is R1's, which since #603 rounds a half-micro tie AWAY FROM ZERO. For every
non-negative result that is the arithmetic every receipt written before #603
recorded, so a whole quantity reproduces it exactly; only an exact negative tie
moves. A rule's fixed per-event component is applied as declared, whatever the
quantity's sign. The only bound is the money columns' own — a computed amount
must fit a signed 64-bit integer of micros — and an amount past it is refused,
naming the quantity and the line, never rounded and never stored as a database
error.
"""
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase

from apps.metering.pricing.models import Rate
from apps.metering.pricing.services.markup_service import ResolvedMarkup
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    MEASUREMENT_VALUE_TYPE_DECIMAL,
    RATE_STRUCTURE_FIXED_COMPONENT,
    RATE_STRUCTURE_PER_UNIT,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

#: The largest and smallest whole number of micros a money column holds.
LARGEST = 2 ** 63 - 1
SMALLEST = -(2 ** 63)


def a_rule(rate, per, fixed=0, structure=RATE_STRUCTURE_PER_UNIT):
    """A rule's terms, unsaved: `compute` reads nothing else."""
    return Rate(rate_structure=structure, rate_per_unit_micros=rate,
                unit_quantity=per, fixed_micros=fixed)


class ARuleCostsAQuantityExactlyTest(SimpleTestCase):
    """`Rate.compute` over canonical text — the table #603's rulings set."""

    def test_a_fraction_times_a_rate_is_exact_and_ties_go_away_from_zero(self):
        cases = {
            # quantity, rate, per → micros
            ("2.5", 3, 1): 8,       # 7.5 → 8
            ("-2.5", 3, 1): -8,     # -7.5 → -8, the mirror
            ("1.5", 1, 1): 2,
            ("-1.5", 1, 1): -2,
            ("0.5", 1, 1): 1,
            ("-0.5", 1, 1): -1,
            ("2.4", 1, 1): 2,
            ("-2.4", 1, 1): -2,
            ("2.6", 1, 1): 3,
            ("-2.6", 1, 1): -3,
            ("0.000001", 1_000_000, 1): 1,
            ("1.25", 1_000, 1_000): 1,    # 1.25 → 1
            ("1.5", 1_000, 1_000): 2,     # exactly half → 2
            ("-1.5", 1_000, 1_000): -2,
        }
        for (quantity, rate, per), micros in cases.items():
            with self.subTest(quantity=quantity, rate=rate, per=per):
                self.assertEqual(a_rule(rate, per).compute(quantity), micros)

    def test_digits_past_any_float_are_costed_exactly(self):
        """Forty fractional digits, each of which can decide the tie."""
        just_under_half = "0." + "4" + "9" * 39
        just_over_half = "0." + "5" + "0" * 38 + "1"
        self.assertEqual(a_rule(1, 1).compute(just_under_half), 0)
        self.assertEqual(a_rule(1, 1).compute(just_over_half), 1)
        self.assertEqual(a_rule(1, 1).compute("-" + just_over_half), -1)
        sixty = "1" + "0" * 59
        self.assertEqual(a_rule(1, 10 ** 59).compute(sixty), 1)
        self.assertEqual(a_rule(0, 1).compute(sixty), 0)

    def test_a_whole_quantity_reproduces_the_arithmetic_before_603(self):
        """Every receipt written before #603 stays true: the old formula,
        over whole non-negative quantities, against the new reader."""
        for rate, per, fixed in ((5_000, 1_000_000, 0), (333, 7, 2),
                                 (1, 2, 0), (1_000, 1, 0), (7, 1_000, 13)):
            rule = a_rule(rate, per, fixed)
            for whole in list(range(0, 300)) + [10 ** 12 + 7, 2 ** 53 + 1]:
                before = (whole * rate + per // 2) // per + fixed
                self.assertEqual(rule.compute(str(whole)), before,
                                 (rate, per, fixed, whole))

    def test_a_fixed_component_applies_as_declared_on_a_negative_quantity(
            self):
        """Ruling 5: a fixed per-event component is never turned into a
        credit by the quantity's sign."""
        self.assertEqual(a_rule(10, 1, fixed=100).compute("-3"), 70)
        self.assertEqual(a_rule(0, 1, fixed=100).compute("-3"), 100)
        once = a_rule(0, 1, fixed=250, structure=RATE_STRUCTURE_FIXED_COMPONENT)
        for quantity in ("-3", "0", "2.5", "1" + "0" * 60):
            self.assertEqual(once.compute(quantity), 250)

    def test_zero_costs_the_fixed_component_and_nothing_else(self):
        self.assertEqual(a_rule(1_000, 1, fixed=5).compute("0"), 5)

    def test_a_quantity_that_is_not_canonical_text_is_refused(self):
        """Costing reads only what the recording path stored; anything else
        is a defect in the caller, refused rather than read."""
        for bad in (12, 2.5, True, None, "1e3", " 1"):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                a_rule(1, 1).compute(bad)


class AMarginIsTakenWithTheSameRuleTest(SimpleTestCase):
    """The markup rounds by R1 too, so a negative basis's tie mirrors."""

    def test_a_tie_on_a_negative_basis_goes_away_from_zero(self):
        half = ResolvedMarkup(markup_micro_percent=50_000_000,
                              source="tenant_default", source_id="m")
        self.assertEqual(half.calculate_markup_micros(3), 2)    # 1.5 → 2
        self.assertEqual(half.calculate_markup_micros(-3), -2)  # -1.5 → -2
        self.assertEqual(half.applied_to(-3), -5)

    def test_a_non_negative_basis_is_unchanged(self):
        quarter = ResolvedMarkup(markup_micro_percent=25_000_000,
                                 source="tenant_default", source_id="m")
        for basis in (0, 1, 2, 3, 4_000_000, 1_234_567):
            self.assertEqual(
                quarter.calculate_markup_micros(basis),
                (basis * 25_000_000 + 50_000_000) // 100_000_000)


class ACostingTenantTestBase(TestCase):
    """A tenant whose `chat` declares one decimal quantity, costed at one
    micro per unit — so the quantity IS the amount and a boundary is a
    quantity."""

    QUANTITY = "seconds"

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Costed",
                                            products=["metering"])
        _, raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c-costed")
        self.http = Client()
        event_type = EventType.objects.create(
            tenant=self.tenant, key="chat",
            costing_method=COSTING_METHOD_CALCULATED)
        Measurement.objects.create(
            event_type=event_type, code=self.QUANTITY,
            value_type=MEASUREMENT_VALUE_TYPE_DECIMAL, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        event_type.publish()
        cost_rate_in_default_book(
            self.tenant, event_type="chat", measurement_key=self.QUANTITY,
            rate_per_unit_micros=1, unit_quantity=1)
        self._keys = 0

    def _item(self, quantity):
        self._keys += 1
        return {"customer_id": str(self.customer.id),
                "idempotency_key": f"k-{self._keys}", "event_type": "chat",
                "measurements": {self.QUANTITY: quantity}}

    def _record(self, quantity):
        return self.http.post("/api/v1/metering/usage",
                              data=json.dumps(self._item(quantity)),
                              content_type="application/json", **self.auth)


@patch("apps.platform.events.tasks.process_single_event")
class AnAmountPastTheMoneyBoundIsRefusedByNameTest(ACostingTenantTestBase):
    """Ruling 7: no precision cap, one bound — the computed amount must fit
    the money columns — and past it, a refusal naming what overflowed."""

    def test_the_largest_and_smallest_amounts_a_column_holds_are_recorded(
            self, _dispatch):
        for quantity, micros in ((str(LARGEST), LARGEST),
                                 (str(SMALLEST), SMALLEST)):
            with self.subTest(quantity=quantity):
                response = self._record(quantity)
                self.assertEqual(response.status_code, 200, response.content)
                self.assertEqual(response.json()["provider_cost_micros"],
                                 micros)

    def test_one_micro_past_either_end_is_refused_naming_the_quantity(
            self, _dispatch):
        for quantity in (str(LARGEST + 1), str(SMALLEST - 1),
                         "1" + "0" * 60):
            with self.subTest(quantity=quantity):
                response = self._record(quantity)
                self.assertEqual(response.status_code, 422, response.content)
                body = response.json()
                self.assertEqual(body["code"], "validation_error")
                self.assertIn(self.QUANTITY, body["detail"])
                self.assertIn(quantity, body["detail"])
                self.assertIn("money", body["detail"])
        self.assertFalse(Posting.objects.filter(tenant=self.tenant).exists())

    def test_a_long_quantity_on_a_rule_of_nothing_is_no_overflow(
            self, _dispatch):
        """The bound is on the AMOUNT, never the quantity: a sixty-digit
        quantity at a rate of nothing costs nothing and is recorded."""
        cost_rate_in_default_book(self.tenant, measurement_key="free",
                                  rate_per_unit_micros=0, unit_quantity=1)
        response = self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(self.customer.id),
                             "idempotency_key": "free",
                             "measurements": {"free": "1" + "0" * 60}}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["provider_cost_micros"], 0)

    def test_a_batch_refuses_only_the_item_that_overflows(self, _dispatch):
        response = self.http.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": [
                self._item("1"), self._item(str(LARGEST + 1)),
                self._item("2")]}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        first, second, third = response.json()["results"]
        self.assertTrue(first["accepted"], first)
        self.assertFalse(second["accepted"], second)
        self.assertEqual(second["code"], "validation_error")
        self.assertIn(self.QUANTITY, second["detail"])
        self.assertTrue(third["accepted"], third)
        self.assertEqual(Posting.objects.filter(tenant=self.tenant).count(), 2)

    def test_a_margin_past_the_bound_is_refused_too(self, _dispatch):
        """The price side's amount is a computed amount as well: a quarter
        on top of the largest cost a column holds is one no column holds."""
        declares_a_markup(self.tenant, percentage_micros=25_000_000)
        response = self._record(str(LARGEST))
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("money", response.json()["detail"])


@patch("apps.platform.events.tasks.process_single_event")
class ANegativeCostIsAKnownCostTest(ACostingTenantTestBase):
    """A negative COGS is one the records hold faithfully (6070096734's
    inspection), so it is recorded `known`, with no reason."""

    def test_a_negative_quantity_costs_a_negative_known_amount(self,
                                                                _dispatch):
        response = self._record("-2.5")
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["costing_status"], "known")
        self.assertEqual(body["provider_cost_micros"], -3)
        self.assertIsNone(body["unresolved_reason"])
        posting = Posting.objects.get(id=body["event_id"])
        self.assertEqual(posting.provider_cost_micros, -3)
