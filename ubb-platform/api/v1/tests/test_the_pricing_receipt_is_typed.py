"""The Pricing Receipt is published as a typed schema, version 2 only (#558).

The record crossed three responses untyped, so the closed concepts riding inside
it reached the wire advertised nowhere. It is `PricingReceipt` now: every level
closed except the `detail` and `provenance` containers, which ADR-0020's
additive rule keeps open — and which publish exactly what was stored, so a key
the record does not carry stays absent rather than arriving as null. The owner's
ruling 3 (2026-10-27): version 2 only, with no legacy branch, because receipts
older than 2 existed only on development databases, which the cutover (#190)
reset rather than accommodating them in the launch contract.
"""
import copy
import json

from django.test import Client, TestCase
from pydantic import ValidationError

from api.v1.schemas import PricingReceipt
from api.v1.tests._helpers import a_tenant, usage_payload
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup)
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from core.vocabulary import PRICING_METHOD_MARGIN_OVER_COST

VERSION = 2


class _ARecordingTenantTestCase(TestCase):

    def setUp(self):
        self.http = Client()
        self.tenant, self.key = a_tenant("Typed")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="c1")
        declares_a_markup(self.tenant, percentage_micros=20_000_000)
        cost_rate_in_default_book(self.tenant, measurement_key="input_tokens",
                                  rate_per_unit_micros=1_000, unit_quantity=1_000)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {self.key}"}

    def _record(self, key):
        answered = self.http.post(
            "/api/v1/metering/usage", content_type="application/json",
            data=json.dumps(usage_payload(self.customer, key,
                                          measurements={"input_tokens": "1200"})),
            **self.auth)
        self.assertEqual(answered.status_code, 200, answered.content)
        return answered.json()


class EveryRouteCarryingTheRecordPublishesItTypedTest(_ARecordingTenantTestCase):

    def test_the_ack_and_the_detail_publish_the_stored_record_exactly(self):
        ack = self._record("typed-1")
        stored = getattr(Posting.objects.get(id=ack["event_id"]),
                         Posting.RECEIPT_COLUMN)

        detail = self.http.get(f"/api/v1/metering/usage/{ack['event_id']}",
                               **self.auth)

        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(stored["receipt_schema_version"], VERSION)
        # The whole record, as stored, on both routes: no typed key the record
        # does not hold arrives as a null, and nothing stored is dropped.
        self.assertEqual(ack["pricing_receipt"], stored)
        self.assertEqual(detail.json()["pricing_receipt"], stored)
        self.assertEqual(ack["pricing_receipt"]["pricing"]["method"],
                         PRICING_METHOD_MARGIN_OVER_COST)

    def test_a_key_the_record_does_not_hold_stays_absent(self):
        """The cost detail names a reported-cost source only where the cost
        was reported; this one was rated, so the key is not there — and the
        typed container must not invent it as null."""
        receipt = self._record("typed-2")["pricing_receipt"]

        self.assertNotIn("reported_cost_source_kind", receipt["costing"]["detail"])
        self.assertNotIn("resolution_run_id", receipt["provenance"])

    def test_a_rejected_batch_item_carries_a_null_receipt(self):
        answered = self.http.post(
            "/api/v1/metering/usage/batch", content_type="application/json",
            data=json.dumps({"events": [
                usage_payload(self.customer, "ok",
                              measurements={"input_tokens": "1200"}),
                {**usage_payload(self.customer, "bad"),
                 "customer_id": "00000000-0000-0000-0000-000000000000"}]}),
            **self.auth)

        self.assertEqual(answered.status_code, 200, answered.content)
        accepted, rejected = answered.json()["results"]
        self.assertEqual(accepted["pricing_receipt"]["receipt_schema_version"],
                         VERSION)
        self.assertFalse(rejected["accepted"])
        self.assertIn("pricing_receipt", rejected)
        self.assertIsNone(rejected["pricing_receipt"])


class TheTypeIsVersionTwoAndOpenOnlyWhereTheRuleSaysTest(_ARecordingTenantTestCase):

    def test_an_additive_detail_key_is_kept_and_published(self):
        receipt = copy.deepcopy(self._record("typed-3")["pricing_receipt"])
        receipt["costing"]["detail"]["a_key_a_later_writer_adds"] = ["kept"]
        receipt["provenance"]["a_later_id"] = "kept"

        published = PricingReceipt.model_validate(receipt).model_dump(mode="json")

        self.assertEqual(published, receipt)

    def test_a_record_older_than_version_two_does_not_validate(self):
        """No legacy branch: a v1 component holds its quantity as a number, and
        an unversioned record has no sections at all."""
        v2 = self._record("typed-4")["pricing_receipt"]
        v1 = copy.deepcopy(v2)
        v1["receipt_schema_version"] = 1
        component = v1["costing"]["detail"]["components"][0]
        component["units"] = int(component["units"])
        legacy = {"engine_version": "2.1.0",
                  "metrics": [{"measurement_key": "input_tokens", "units": 3}]}

        for record in (v1, legacy):
            with self.subTest(version=record.get("receipt_schema_version")):
                with self.assertRaises(ValidationError):
                    PricingReceipt.model_validate(record)

    def test_the_version_alone_refuses_an_older_record(self):
        """A record that priced no quantity holds no component, so nothing but
        its declared version tells version 1 from version 2 — and the type
        refuses it on that alone. The same record at version 2 validates, so
        the refusal is carried by the version and by nothing else."""
        v2 = copy.deepcopy(self._record("typed-5")["pricing_receipt"])
        for section in ("costing", "pricing"):
            v2[section]["detail"].pop("components", None)
        v1 = {**v2, "receipt_schema_version": 1}

        PricingReceipt.model_validate(v2)
        with self.assertRaises(ValidationError):
            PricingReceipt.model_validate(v1)
