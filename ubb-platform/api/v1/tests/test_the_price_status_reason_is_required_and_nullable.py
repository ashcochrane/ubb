"""`pricing_status_reason` is REQUIRED AND NULLABLE wherever `pricing_status`
is published (#603; the owner's amendment `6279966961`; ADR-0020).

The key is always present and null means no specific published reason
applies; there is no third "field absent" state and no default. Two halves,
because each catches what the other cannot:

* **the document** — every schema in the generated contract, components and
  webhook payloads alike, that publishes `pricing_status` also publishes
  `pricing_status_reason`, lists it as required, types it string-or-null with
  the registry's closed set on the string member, and gives it no default. A
  surface added next year that publishes the status without the reason fails
  here, by name, without anybody remembering this ticket;
* **the wire** — the routes really send the key, null on every ordinary answer
  and on a rejected batch item, and present with its value on a negative price
  (`test_a_negative_price_is_unknown_with_a_reason.py` pins that half).
"""
import json
from unittest.mock import patch

from django.test import Client, SimpleTestCase, TestCase

from api.v1.openapi_export import generated_document_text
from apps.metering.pricing.tests._helpers import (
    a_rule_that_prices_what_it_measures, declares_a_markup)
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_REASON_VALUES,
    PRICING_STATUS_UNKNOWN,
)

#: Every surface the contract publishes `pricing_status` on, as of #603. The
#: walk below finds them; this list is what makes a NEW one a decision rather
#: than a silent addition — a surface appearing or vanishing fails the census.
PUBLISHERS = {
    "ItemisedEventRow",
    "RecordUsageResponse",
    "SuppliedRevenueWindowOut",
    "UnresolvedQueueRow",
    "UsageBatchItemResponse",
    "UsageEventDetailOut",
    "UsageEventOut",
    "webhook usage.recorded",
}


def _publishers(document):
    """`{name: schema}` for every object schema carrying `pricing_status` —
    each component by name, each webhook payload by its event type."""
    found = {}
    for name, schema in document["components"]["schemas"].items():
        if "pricing_status" in schema.get("properties", {}):
            found[name] = schema
    for event_type, item in document.get("webhooks", {}).items():
        body = item["post"]["requestBody"]["content"]["application/json"][
            "schema"]
        data = body.get("properties", {}).get("data", {})
        if "pricing_status" in data.get("properties", {}):
            found[f"webhook {event_type}"] = data
    return found


class EverySurfacePublishingTheStatusPublishesTheReasonTest(SimpleTestCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.document = json.loads(generated_document_text())
        cls.publishers = _publishers(cls.document)

    def test_the_census_of_publishers_is_the_known_one(self):
        self.assertEqual(set(self.publishers), PUBLISHERS)

    def test_each_publishes_the_reason_as_required(self):
        for name, schema in self.publishers.items():
            with self.subTest(surface=name):
                self.assertIn("pricing_status_reason", schema["properties"])
                self.assertIn("pricing_status_reason",
                              schema.get("required", []))

    def test_each_types_it_string_or_null_with_the_closed_set_and_no_default(
            self):
        for name, schema in self.publishers.items():
            with self.subTest(surface=name):
                field = schema["properties"]["pricing_status_reason"]
                self.assertNotIn("default", field)
                members = field["anyOf"]
                self.assertIn({"type": "null"}, members)
                (string,) = [m for m in members if m.get("type") == "string"]
                self.assertEqual(set(string["enum"]),
                                 set(PRICING_STATUS_REASON_VALUES))
                self.assertEqual(string["x-ubb-concept"],
                                 "pricing_status_reason")


@patch("apps.platform.events.tasks.process_single_event")
class TheRoutesSendTheKeyNullOnEveryOrdinaryAnswerTest(TestCase):
    """Null, present, on a known price, a plain `unknown`, and a rejected
    batch item — through the acknowledgement, the batch, the list row and the
    detail read."""

    def setUp(self):
        self.tenant = Tenant.objects.create(name="Reason",
                                            products=["metering", "billing"])
        _, raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {raw_key}"}
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c-reason")
        self.http = Client()

    def _post(self, path, body):
        return self.http.post(path, data=json.dumps(body),
                              content_type="application/json", **self.auth)

    def _surfaces(self, event_id):
        detail = self.http.get(f"/api/v1/metering/usage/{event_id}",
                               **self.auth).json()
        (row,) = [r for r in self.http.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            **self.auth).json()["data"] if r["id"] == event_id]
        return detail, row

    def test_a_known_price_carries_a_null_reason_everywhere(self, _dispatch):
        a_rule_that_prices_what_it_measures(self.tenant)
        ack = self._post("/api/v1/metering/usage", {
            "customer_id": str(self.customer.id), "idempotency_key": "k1",
            "measurements": {"priced_calls": "3"}}).json()
        self.assertEqual(ack["pricing_status"], PRICING_STATUS_KNOWN)
        for surface in (ack, *self._surfaces(ack["event_id"])):
            self.assertIn("pricing_status_reason", surface)
            self.assertIsNone(surface["pricing_status_reason"])

    def test_a_price_unknown_for_want_of_input_carries_a_null_reason(
            self, _dispatch):
        ack = self._post("/api/v1/metering/usage", {
            "customer_id": str(self.customer.id),
            "idempotency_key": "k2"}).json()
        self.assertEqual(ack["pricing_status"], PRICING_STATUS_UNKNOWN)
        for surface in (ack, *self._surfaces(ack["event_id"])):
            self.assertIn("pricing_status_reason", surface)
            self.assertIsNone(surface["pricing_status_reason"])

    def test_an_accepted_and_a_rejected_batch_item_both_carry_the_key(
            self, _dispatch):
        declares_a_markup(self.tenant)
        results = self._post("/api/v1/metering/usage/batch", {"events": [
            {"customer_id": str(self.customer.id), "idempotency_key": "b1"},
            {"customer_id": "00000000-0000-0000-0000-000000000000",
             "idempotency_key": "b2"}]}).json()["results"]
        accepted, rejected = results
        self.assertTrue(accepted["accepted"])
        self.assertFalse(rejected["accepted"])
        for item in results:
            self.assertIn("pricing_status_reason", item)
            self.assertIsNone(item["pricing_status_reason"])
