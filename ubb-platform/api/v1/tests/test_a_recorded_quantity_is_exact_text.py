"""A recorded Measurement quantity is exact text, end to end (#603, ADR-0020).

The wire carries every quantity as a canonical exact signed-decimal STRING,
whatever its value type, through #571's one grammar
(`apps/platform/event_types/exact_decimals.py`). A JSON number is refused, even
a whole one, because in most clients it has already been a binary float on the
way; what crosses is canonicalised before anything stores it, and the same text
is what storage, the acknowledgement's echo, the detail read and the receipt's
components hold — byte for byte, at every length.

**Negatives are recordable and zero is a real value.** The door used to refuse a
negative quantity (the money-model decision's §6.2(2), "quantities are
non-negative integers", and the door's "Fix 1"); #603's rulings retired both,
and this module is where the old refusal's pins were inverted rather than
deleted. Whether a quantity may carry a fraction is its declaration's
`value_type`, read off the Event Type's last publication; a key no publication
declares has no value type and is held as text.
"""
import json
from unittest.mock import patch

from django.test import Client, TestCase

from apps.metering.pricing.receipts import QUANTITY_KEY
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType, Measurement, QuarantinedKey)
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    MEASUREMENT_VALUE_TYPE_DECIMAL,
    MEASUREMENT_VALUE_TYPE_INTEGER,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

#: The Event Type this module records under, declaring one quantity of each
#: value type.
CHAT = "chat"
WHOLE = "calls"
FRACTIONAL = "seconds"

#: Sixty significant digits — far past what a binary float or `Decimal`'s
#: default 28-digit context holds.
SIXTY_DIGITS = "1" + "2345678901" * 5 + "234567890"
#: Forty fractional digits, canonical (no trailing zero).
FORTY_FRACTIONAL_DIGITS = "0." + "0123456789" * 3 + "0123456789"
#: The first whole number a binary float cannot hold: as a double it reads
#: back as ...992.
TWO_TO_THE_53_PLUS_ONE = "9007199254740993"

#: Every value this module crosses, by the quantity it is declared under.
CROSSES = {
    WHOLE: ["12", "-3", "0", SIXTY_DIGITS, "-" + SIXTY_DIGITS,
            TWO_TO_THE_53_PLUS_ONE],
    FRACTIONAL: ["2.5", "-0.5", "-3", FORTY_FRACTIONAL_DIGITS,
                 SIXTY_DIGITS + "." + SIXTY_DIGITS[::-1]],
}

#: What the wire refuses, each with why: never canonicalised, never read.
REFUSED = {
    "a JSON whole number": 12,
    "a JSON float": 2.5,
    "a JSON boolean": True,
    "JSON null": None,
    "leading whitespace": " 1",
    "trailing whitespace": "1 ",
    "an exponent": "1e3",
    "a digit separator": "1_0",
    "a leading plus": "+1",
    "no digit before the point": ".5",
    "no digit after the point": "5.",
    "empty text": "",
    "not a number": "NaN",
    "another script's digit": chr(0x0661),
    "a grouping comma": "1,000",
}


class ARecordedQuantityTestBase(TestCase):
    """A metering tenant whose `chat` declares one quantity of each value type,
    published, each costed at nothing per unit — so a component is written for
    every value whatever its size, and no amount can overflow."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Exact", products=["metering"])
        _, raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c-exact")
        self.http = Client()
        event_type = EventType.objects.create(
            tenant=self.tenant, key=CHAT,
            costing_method=COSTING_METHOD_CALCULATED)
        for code, value_type in ((WHOLE, MEASUREMENT_VALUE_TYPE_INTEGER),
                                 (FRACTIONAL, MEASUREMENT_VALUE_TYPE_DECIMAL)):
            Measurement.objects.create(
                event_type=event_type, code=code, value_type=value_type,
                unit=UNIT_TOKEN, source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        event_type.publish()
        for code in (WHOLE, FRACTIONAL):
            cost_rate_in_default_book(
                self.tenant, event_type=CHAT, measurement_key=code,
                rate_per_unit_micros=0, unit_quantity=1)
        self._keys = 0

    def _key(self):
        self._keys += 1
        return f"k-{self._keys}"

    def _item(self, measurements, **extra):
        return {"customer_id": str(self.customer.id),
                "idempotency_key": self._key(), "event_type": CHAT,
                "measurements": measurements, **extra}

    def _record(self, measurements, **extra):
        return self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps(self._item(measurements, **extra)),
            content_type="application/json", **self.auth)

    def _record_batch(self, *bags):
        return self.http.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": [self._item(bag) for bag in bags]}),
            content_type="application/json", **self.auth)

    def _detail(self, event_id):
        return self.http.get(f"/api/v1/metering/usage/{event_id}", **self.auth)

    def _every_record_holds(self, event_id, bag):
        """The four places a recorded quantity is held or answered, each the
        same canonical text: storage, the detail read, and the receipt's
        components (the echo is asserted by the caller, which has it)."""
        posting = Posting.objects.select_related("measurement").get(
            id=event_id)
        self.assertEqual(posting.measurement.measurements, bag)
        detail = self._detail(event_id)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(detail.json()["measurements"], bag)
        receipt = posting.pricing_receipt
        self.assertEqual(receipt["receipt_schema_version"], 2)
        self.assertEqual(
            {c["measurement_key"]: c[QUANTITY_KEY]
             for c in receipt["costing"]["detail"]["components"]},
            bag)


@patch("apps.platform.events.tasks.process_single_event")
class EveryValueCrossesByteForByteTest(ARecordedQuantityTestBase):
    """What the caller wrote, canonical, is what every record holds."""

    def test_through_the_single_route(self, _dispatch):
        for code, values in CROSSES.items():
            for value in values:
                with self.subTest(code=code, value=value):
                    response = self._record({code: value})
                    self.assertEqual(response.status_code, 200,
                                     response.content)
                    body = response.json()
                    self.assertEqual(body["measurements"], {code: value})
                    self._every_record_holds(body["event_id"], {code: value})

    def test_through_the_batch_route(self, _dispatch):
        bags = [{code: value} for code, values in CROSSES.items()
                for value in values]
        response = self._record_batch(*bags)
        self.assertEqual(response.status_code, 200, response.content)
        results = response.json()["results"]
        for bag, result in zip(bags, results):
            with self.subTest(bag=bag):
                self.assertTrue(result["accepted"], result)
                self.assertEqual(result["measurements"], bag)
                self._every_record_holds(result["event_id"], bag)

    def test_the_text_is_exact_where_a_number_would_not_be(self, _dispatch):
        """The control on the premise: each long value is one a JSON number
        would have changed, so crossing it unchanged is evidence."""
        self.assertNotEqual(str(int(float(TWO_TO_THE_53_PLUS_ONE))),
                            TWO_TO_THE_53_PLUS_ONE)
        self.assertNotEqual(repr(float(FORTY_FRACTIONAL_DIGITS)),
                            FORTY_FRACTIONAL_DIGITS)


@patch("apps.platform.events.tasks.process_single_event")
class AValueIsCanonicalisedBeforeAnythingHoldsItTest(
        ARecordedQuantityTestBase):
    """Every spelling of one number is one record: no unnecessary leading
    zero, no trailing fractional zero or point, and `0` for every zero."""

    SPELLINGS = {
        (WHOLE, "007"): "7",
        (WHOLE, "-0"): "0",
        (WHOLE, "-000"): "0",
        (WHOLE, "12.0"): "12",
        (FRACTIONAL, "01.500"): "1.5",
        (FRACTIONAL, "-0.000"): "0",
        (FRACTIONAL, "-00.250"): "-0.25",
    }

    def test_each_spelling_is_held_in_its_canonical_form(self, _dispatch):
        for (code, written), canonical in self.SPELLINGS.items():
            with self.subTest(written=written):
                response = self._record({code: written})
                self.assertEqual(response.status_code, 200, response.content)
                body = response.json()
                self.assertEqual(body["measurements"], {code: canonical})
                self._every_record_holds(body["event_id"], {code: canonical})


@patch("apps.platform.events.tasks.process_single_event")
class WhatTheWireRefusesTest(ARecordedQuantityTestBase):
    """Refused at the door, before anything is recorded, naming the quantity."""

    def test_each_refusal_is_a_422_naming_the_quantity(self, _dispatch):
        for why, value in REFUSED.items():
            with self.subTest(why=why):
                response = self._record({WHOLE: value, FRACTIONAL: "1"})
                self.assertEqual(response.status_code, 422, response.content)
                body = response.json()
                self.assertEqual(body["code"], "validation_error")
                said = json.dumps(body["errors"])
                self.assertIn(WHOLE, said)
                self.assertNotIn(FRACTIONAL, said)
        self.assertFalse(Posting.objects.filter(tenant=self.tenant).exists())

    def test_a_json_number_is_refused_even_when_it_is_whole(self, _dispatch):
        """The case a tolerant wire would admit: `12` is exact in Python, but
        `9007199254740993` sent as a number has already lost its last digit in
        most clients, and the server cannot tell the two apart."""
        response = self._record({WHOLE: 12})
        self.assertEqual(response.status_code, 422, response.content)
        self.assertIn("string", json.dumps(response.json()).lower())

    def test_a_malformed_value_refuses_the_whole_batch_body(self, _dispatch):
        """The schema refuses the whole batch body for a malformed value —
        it is the request that is malformed, before any item is an item, as
        every other schema refusal on that body is. Pinned so the per-item
        refusals below are read for what they are: refusals made after the
        door, by declaration or by costing."""
        response = self._record_batch({WHOLE: "1"}, {WHOLE: 2})
        self.assertEqual(response.status_code, 422, response.content)


@patch("apps.platform.events.tasks.process_single_event")
class TheDeclaredValueTypeDecidesAFractionTest(ARecordedQuantityTestBase):
    """`integer` requires a whole value and `decimal` permits a fraction — the
    Measurement's own reader, asked of its last publication."""

    def test_an_integer_quantity_refuses_a_fraction(self, _dispatch):
        response = self._record({WHOLE: "2.5"})
        self.assertEqual(response.status_code, 422, response.content)
        detail = response.json()["detail"]
        self.assertIn(WHOLE, detail)
        self.assertIn("whole", detail)
        self.assertIn("2.5", detail)
        self.assertFalse(Posting.objects.filter(tenant=self.tenant).exists())

    def test_a_decimal_quantity_takes_the_same_fraction(self, _dispatch):
        response = self._record({FRACTIONAL: "2.5"})
        self.assertEqual(response.status_code, 200, response.content)

    def test_a_whole_value_written_with_a_point_is_whole(self, _dispatch):
        """`12.0` is twelve: canonicalised first, so it is whole by the time
        the value type is asked."""
        response = self._record({WHOLE: "12.000"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["measurements"], {WHOLE: "12"})

    def test_a_batch_refuses_only_the_item_that_breaks_its_declaration(
            self, _dispatch):
        response = self._record_batch(
            {WHOLE: "1"}, {WHOLE: "2.5"}, {FRACTIONAL: "2.5"})
        self.assertEqual(response.status_code, 200, response.content)
        first, second, third = response.json()["results"]
        self.assertTrue(first["accepted"])
        self.assertFalse(second["accepted"])
        self.assertEqual(second["code"], "validation_error")
        self.assertIn(WHOLE, second["detail"])
        self.assertTrue(third["accepted"])
        self.assertEqual(Posting.objects.filter(tenant=self.tenant).count(), 2)

    def test_a_key_no_publication_declares_is_held_as_its_canonical_text(
            self, _dispatch):
        """An undeclared name has no value type to ask, so a fraction is
        accepted and held — in quarantine, as text, canonical."""
        response = self._record({"frames": "2.50", WHOLE: "1"})
        self.assertEqual(response.status_code, 200, response.content)
        held = QuarantinedKey.objects.get(tenant=self.tenant,
                                          measurement_key="frames")
        self.assertEqual(held.quantity, "2.5")
        self.assertEqual(response.json()["measurements"],
                         {"frames": "2.5", WHOLE: "1"})


@patch("apps.platform.events.tasks.process_single_event")
class ANegativeQuantityAndZeroAreRecordedTest(ARecordedQuantityTestBase):
    """The door's old refusal of a negative, inverted (#603 ruling 2), and
    zero as a value rather than a missing one (ruling 6)."""

    def test_a_negative_quantity_is_recorded(self, _dispatch):
        response = self._record({WHOLE: "-5"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["measurements"], {WHOLE: "-5"})

    def test_one_negative_among_many_is_recorded_with_them(self, _dispatch):
        response = self._record({WHOLE: "10", FRACTIONAL: "-1.5"})
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["measurements"],
                         {WHOLE: "10", FRACTIONAL: "-1.5"})

    def test_zero_is_recorded_as_zero(self, _dispatch):
        response = self._record({WHOLE: "0"})
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual(body["measurements"], {WHOLE: "0"})
        self.assertEqual(body["costing_status"], "known")
        self.assertEqual(body["provider_cost_micros"], 0)


@patch("apps.platform.events.tasks.process_single_event")
class WhatTheBagStillAcceptsTest(ARecordedQuantityTestBase):
    """The other half of the old module, carried over (#274): no key pattern,
    no required bag, and a name nothing declares still accepted."""

    def test_a_key_of_any_shape_is_accepted(self, _dispatch):
        response = self.http.post(
            "/api/v1/metering/usage", data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": "any-shape",
                "measurements": {"Input-Tokens": "1", "cost centre": "2",
                                 "x": "3"}}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)

    def test_an_absent_bag_is_accepted(self, _dispatch):
        response = self.http.post(
            "/api/v1/metering/usage", data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": "no-bag"}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["measurements"], {})

    def test_a_key_no_declaration_matches_leaves_its_cost_unresolved(
            self, _dispatch):
        response = self.http.post(
            "/api/v1/metering/usage", data=json.dumps({
                "customer_id": str(self.customer.id),
                "idempotency_key": "undeclared",
                "measurements": {"nothing_declares_this": "5000"}}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertIsNone(body["provider_cost_micros"])
        self.assertEqual(body["costing_status"], "unresolved")
        self.assertEqual(body["uncosted_measurement_keys"],
                         ["nothing_declares_this"])
