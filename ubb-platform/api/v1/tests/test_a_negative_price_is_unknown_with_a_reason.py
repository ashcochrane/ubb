"""A negative final economic amount: represented where the records can carry
it, explicitly unresolved where they cannot (#603 ruling 8; the owner's Q1
ruling `6279554922` and its amendment `6279966961`; ADR-0020).

**THE TWO HALVES DIFFER, AND THE INSPECTION SAYS WHY.** A negative supplier
cost is one every record that holds a known cost holds faithfully, so it is
recorded `known` with no reason. A negative customer price is one the money
rails cannot carry — the drawdown, the live counter, the Pool and postpaid
lines all act on a known price — so it is recorded `unknown` with the
`pricing_status_reason` `negative_price_unsupported`: never clamped to zero,
never dropped, never `known`, and never published as though it were a price.

**DECIDED ON THE POSTING'S TOTAL, NOT PER COMPONENT** (ruling 8): components can
cancel, and a fixed per-event component can change the sign on its own. And it
is NOT retried by the normal resolver: configuration has not gone missing, so a
Resolution Run does not select it, while the unpriced count still counts it —
it is an amount the totals do not include.
"""
import json
from datetime import timedelta
from unittest.mock import patch

from django.test import Client, TestCase
from django.utils import timezone

from apps.metering.pricing.services import resolution_run
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup, rate_in_default_book)
from apps.metering.queries import get_customer_cost_totals
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    MEASUREMENT_VALUE_TYPE_DECIMAL,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED,
    PRICING_STATUS_UNKNOWN,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

CHAT = "chat"
SECONDS = "seconds"
CALLS = "calls"

#: What a unit sells for and what it costs, deliberately different so a price
#: and a cost are never the same number by accident.
PRICE_PER_UNIT = 1_000
COST_PER_UNIT = 1


class ANegativeEconomicsTenantTestBase(TestCase):
    """A billing tenant whose `chat` declares two decimal quantities, each
    priced and costed per unit."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Signed", products=["metering", "billing"])
        _, raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c-signed")
        self.http = Client()
        event_type = EventType.objects.create(
            tenant=self.tenant, key=CHAT,
            costing_method=COSTING_METHOD_CALCULATED)
        for code in (SECONDS, CALLS):
            Measurement.objects.create(
                event_type=event_type, code=code,
                value_type=MEASUREMENT_VALUE_TYPE_DECIMAL, unit=UNIT_TOKEN,
                source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        event_type.publish()
        for code in (SECONDS, CALLS):
            cost_rate_in_default_book(
                self.tenant, event_type=CHAT, measurement_key=code,
                rate_per_unit_micros=COST_PER_UNIT, unit_quantity=1)
        self._keys = 0

    def _price_every_quantity(self, **fields):
        for code in (SECONDS, CALLS):
            rate_in_default_book(
                self.tenant, event_type=CHAT, measurement_key=code,
                rate_per_unit_micros=PRICE_PER_UNIT, unit_quantity=1,
                **fields)

    def _record(self, measurements):
        self._keys += 1
        response = self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps({"customer_id": str(self.customer.id),
                             "idempotency_key": f"k-{self._keys}",
                             "event_type": CHAT,
                             "measurements": measurements}),
            content_type="application/json", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


@patch("apps.platform.events.tasks.process_single_event")
class ANegativePriceIsUnknownWithItsReasonTest(
        ANegativeEconomicsTenantTestBase):

    def setUp(self):
        super().setUp()
        self._price_every_quantity()

    def test_the_posting_says_unknown_and_why_and_holds_no_amount(
            self, _dispatch):
        body = self._record({SECONDS: "-3"})
        posting = Posting.objects.get(id=body["event_id"])
        self.assertEqual(posting.pricing_status, PRICING_STATUS_UNKNOWN)
        self.assertEqual(posting.pricing_status_reason,
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(posting.billed_cost_micros)
        self.assertIsNone(posting.not_applicable_reason)

    def test_the_acknowledgement_says_it(self, _dispatch):
        body = self._record({SECONDS: "-3"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(body["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(body["billed_cost_micros"])
        self.assertIsNone(body["pricing_method"])

    def test_the_detail_read_and_the_list_row_say_it(self, _dispatch):
        body = self._record({SECONDS: "-3"})
        detail = self.http.get(
            f"/api/v1/metering/usage/{body['event_id']}", **self.auth).json()
        self.assertEqual(detail["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(detail["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(detail["billed_cost_micros"])
        rows = self.http.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            **self.auth).json()["data"]
        (row,) = rows
        self.assertEqual(row["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(row["billed_cost_micros"])

    def test_the_receipt_keeps_the_reason_in_its_pricing_detail(
            self, _dispatch):
        body = self._record({SECONDS: "-3"})
        receipt = Posting.objects.get(id=body["event_id"]).pricing_receipt
        self.assertEqual(receipt["pricing"]["status"], PRICING_STATUS_UNKNOWN)
        self.assertIsNone(receipt["pricing"]["method"])
        self.assertEqual(
            receipt["pricing"]["detail"]["pricing_status_reason"],
            PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(receipt["totals"]["billed_cost_micros"])

    def test_the_usage_recorded_payload_says_it(self, _dispatch):
        body = self._record({SECONDS: "-3"})
        (event,) = [e for e in OutboxEvent.objects.filter(
            event_type="usage.recorded")
            if e.payload["event_id"] == body["event_id"]]
        self.assertEqual(event.payload["pricing_status"],
                         PRICING_STATUS_UNKNOWN)
        self.assertEqual(event.payload["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertIsNone(event.payload["billed_cost_micros"])
        self.assertIsNone(event.payload["cost_micros"])

    def test_the_computed_number_is_published_nowhere_as_a_price(
            self, _dispatch):
        """-3 seconds at 1,000 a second is -3,000: no amount field on any
        surface may say so."""
        body = self._record({SECONDS: "-3"})
        detail = self.http.get(
            f"/api/v1/metering/usage/{body['event_id']}", **self.auth).json()
        for surface in (body, detail):
            for field in ("billed_cost_micros",):
                self.assertIsNone(surface[field])
            self.assertIsNone(surface["pricing_receipt"]["totals"][
                "billed_cost_micros"])
            self.assertNotIn("-3000", json.dumps(
                {k: v for k, v in surface.items()
                 if k != "pricing_receipt"}))

    def test_it_is_counted_among_the_amounts_not_included(self, _dispatch):
        self._record({SECONDS: "2"})
        self._record({SECONDS: "-3"})
        today = timezone.now().date()
        totals = get_customer_cost_totals(
            self.tenant.id, self.customer.id, today - timedelta(days=1),
            today + timedelta(days=1))
        self.assertEqual(totals["billed_cost_micros"], 2 * PRICE_PER_UNIT)
        self.assertEqual(totals["unpriced_event_count"], 1)

    def test_a_resolution_run_does_not_select_it(self, _dispatch):
        """Configuration has not gone missing, so the normal resolver has
        nothing to retry — while a price unknown for want of a rule IS a
        candidate, which is the control. Both carry a KNOWN cost, so neither
        is selected for its cost: the price is the only thing asked."""
        unsupported = self._record({SECONDS: "-3"})
        # A call measuring nothing matches no price rule, and this tenant has
        # no markup rung: `unknown`, for want of configuration, reason null.
        missing_price = Posting.objects.get(id=self._record({})["event_id"])
        self.assertEqual(missing_price.costing_status, "known")
        self.assertEqual(missing_price.pricing_status, PRICING_STATUS_UNKNOWN)
        self.assertIsNone(missing_price.pricing_status_reason)
        self.assertEqual(Posting.objects.get(
            id=unsupported["event_id"]).costing_status, "known")
        selected = set(resolution_run.candidates(
            self.tenant, resolution_run.RunSelector()).values_list(
                "id", flat=True))
        self.assertIn(missing_price.id, selected)
        self.assertNotIn(unsupported["event_id"],
                         {str(i) for i in selected})


@patch("apps.platform.events.tasks.process_single_event")
class TheSignIsDecidedOnThePostingsTotalTest(ANegativeEconomicsTenantTestBase):
    """Components can cancel: the amount the posting carries is the whole."""

    def setUp(self):
        super().setUp()
        self._price_every_quantity()

    def test_components_that_cancel_are_a_known_zero(self, _dispatch):
        body = self._record({SECONDS: "3", CALLS: "-3"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["billed_cost_micros"], 0)
        self.assertIsNone(body["pricing_status_reason"])
        self.assertEqual(body["costing_status"], "known")
        self.assertEqual(body["provider_cost_micros"], 0)

    def test_a_negative_whole_is_unknown_though_one_component_is_positive(
            self, _dispatch):
        body = self._record({SECONDS: "3", CALLS: "-5"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(body["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        self.assertEqual(body["provider_cost_micros"], -2)

    def test_a_positive_whole_is_known_though_one_component_is_negative(
            self, _dispatch):
        body = self._record({SECONDS: "5", CALLS: "-3"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["billed_cost_micros"], 2 * PRICE_PER_UNIT)
        self.assertIsNone(body["pricing_status_reason"])


@patch("apps.platform.events.tasks.process_single_event")
class AFixedComponentDecidesTheSignOnItsOwnTest(
        ANegativeEconomicsTenantTestBase):
    """Quantity sign is not final-money sign (the owner's Q2 ruling): a fixed
    per-event component applied as declared can keep a negative quantity's
    price positive."""

    def test_a_fixed_component_outweighing_the_credit_is_a_known_price(
            self, _dispatch):
        rate_in_default_book(
            self.tenant, event_type=CHAT, measurement_key=SECONDS,
            rate_per_unit_micros=PRICE_PER_UNIT, unit_quantity=1,
            fixed_micros=5_000)
        body = self._record({SECONDS: "-3"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["billed_cost_micros"], 2_000)


@patch("apps.platform.events.tasks.process_single_event")
class AMarginOverANegativeCostTest(ANegativeEconomicsTenantTestBase):
    """The markup rung's answer is a computed price like any other."""

    def test_a_margin_over_a_negative_known_cost_is_unknown_with_its_reason(
            self, _dispatch):
        declares_a_markup(self.tenant, percentage_micros=25_000_000)
        body = self._record({SECONDS: "-4000000"})
        self.assertEqual(body["costing_status"], "known")
        self.assertEqual(body["provider_cost_micros"], -4_000_000)
        self.assertEqual(body["pricing_status"], PRICING_STATUS_UNKNOWN)
        self.assertEqual(body["pricing_status_reason"],
                         PRICING_STATUS_REASON_NEGATIVE_PRICE_UNSUPPORTED)
        receipt = Posting.objects.get(id=body["event_id"]).pricing_receipt
        self.assertNotIn("markup", receipt["pricing"]["detail"])

    def test_a_margin_over_a_zero_cost_is_a_known_zero(self, _dispatch):
        declares_a_markup(self.tenant, percentage_micros=25_000_000)
        body = self._record({SECONDS: "0"})
        self.assertEqual(body["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(body["billed_cost_micros"], 0)
        self.assertIsNone(body["pricing_status_reason"])
