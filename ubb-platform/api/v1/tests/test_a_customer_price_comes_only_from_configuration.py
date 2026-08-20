"""A customer price is CONFIGURED. It is never sent on the call (#365).

The recording request used to carry the customer's price, which bypassed
configuration entirely: a per-customer figure worked out somewhere else and
pasted in, going stale the moment the supplier moved and answerable to no rule
anybody could read back. This module is the pair of claims that replace it.

* **A price a tenant states through a rule resolves.** That is the replacement,
  and it is asserted first because every refusal below is worthless without it —
  a route that refused the field and had no other way to price an event would
  have removed the capability rather than moved it.

* **There is no request-side path to the same outcome.** Not under the old name,
  not under a new one, and not through the service the routes call. Django Ninja
  DROPS a body key no schema publishes rather than refusing it, so "we deleted
  the field" on its own would leave a client that has not been updated posting
  prices into silence and reading `200` as agreement — the old name is therefore
  REFUSED by name, while every other unknown key keeps the ratified drop. That
  asymmetry is deliberate and has its own case, with the measurement behind it.
  A price under a name UBB never published reaches nothing whatever it does.

**AND NO CLAIMED PRICE EITHER, WHICH IS THE PART THAT WILL BE RE-PROPOSED.**
The cost side has two wire fields — the supplier's own reported figure and the
caller's belief about it — and the symmetry does not carry over. Cost is
OBSERVED: a caller's belief about it is diagnostic, because their supplier's
invoice is an external fact they may genuinely have seen. Price is DECIDED: a
caller's belief about their own tenant's price is not an observation of
anything, so a field for it would be the field this ticket deletes wearing a
name that says it does not count — and a number that does not count is a number
somebody eventually makes count. #151 §9.2 records that invariant and records
why it was worth writing down: *"it is small, it looks helpful, and the argument
against it lives three documents away."*

The set assertion at the foot is what refuses one, under any name.
"""

import json

from django.test import Client, SimpleTestCase, TestCase

from api.v1.schemas import RecordUsageRequest
from apps.metering.pricing.tests._helpers import rate_in_default_book
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.work.services import TaskService
from core.vocabulary import (
    PRICING_METHOD_DIRECT_EVENT_PRICE,
    PRICING_STATUS_KNOWN,
)

# The recording body comes from there rather than being built here: the request
# still requires a correlation value whose word is RETIRED under a ledger entry
# capping how many files may spell it, and that module is already counted.
from api.v1.tests.test_metering_endpoints import (
    THE_WHOLE_RECORDING_REQUEST, usage_payload)

#: The rule's terms, and the quantity it prices. Three calls' worth of that
#: quantity is a price no default could coincide with.
THE_QUANTITY = "calls"
WHAT_THE_RULE_CHARGES_PER_CALL = 2_500_000
HOW_MANY_CALLS = 3
WHAT_THE_RULE_CHARGES = WHAT_THE_RULE_CHARGES_PER_CALL * HOW_MANY_CALLS

#: A price a caller might once have pasted into the payload. Deliberately
#: nothing like the figure above, so a body that reached the amount would be
#: visible rather than plausible.
WHAT_A_CALLER_WOULD_HAVE_SENT = 11_000_000


class _ARecordingTenant(TestCase):
    """A metering tenant, its customer, and the one route that records."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Configured Price",
                                            products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="configured")

    def post(self, correlation, **body):
        """One recording call. The status is the caller's to assert."""
        return self.http.post(
            "/api/v1/metering/usage",
            data=json.dumps(usage_payload(self.customer, correlation, **body)),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def record(self, correlation, **body):
        response = self.post(correlation, **body)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()

    def refused(self, correlation, **body):
        response = self.post(correlation, **body)
        self.assertEqual(response.status_code, 422, response.content)
        return response.json()

    def a_direct_price_rule(self):
        """The replacement, stated the way a tenant states it.

        A rule that declares no method prices the event's own quantities by its
        own terms, which is `direct_event_price` — an amount attached to the
        event regardless of what the call cost. That is the same method the
        deleted field produced, reached through configuration instead of
        through the payload.
        """
        return rate_in_default_book(
            self.tenant, measurement_key=THE_QUANTITY,
            rate_per_unit_micros=WHAT_THE_RULE_CHARGES_PER_CALL,
            unit_quantity=1)


class APriceIsSuppliedThroughConfigurationTest(_ARecordingTenant):
    """The positive half. Every refusal in the class below needs this first."""

    def test_a_direct_price_rule_resolves_the_customers_price(self):
        """The replacement, end to end: a rule in, a resolved price out."""
        self.a_direct_price_rule()

        ack = self.record("configured",
                          measurements={THE_QUANTITY: HOW_MANY_CALLS})

        self.assertEqual(ack["billed_cost_micros"], WHAT_THE_RULE_CHARGES)
        self.assertEqual(ack["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(ack["pricing_method"],
                         PRICING_METHOD_DIRECT_EVENT_PRICE)

    def test_the_resolved_price_is_the_one_the_record_keeps(self):
        """Read back off the row, not off the answer that produced it.

        An ack echoing a figure the posting does not hold would be a price a
        tenant is told and never charged.
        """
        self.a_direct_price_rule()

        ack = self.record("stored",
                          measurements={THE_QUANTITY: HOW_MANY_CALLS})

        self.assertEqual(
            Posting.objects.get(id=ack["event_id"]).billed_cost_micros,
            WHAT_THE_RULE_CHARGES)

    def test_every_response_that_carries_a_price_still_carries_it(self):
        """⚠ THE DELETION WAS BY CLASS, AND THIS IS THE OTHER DIRECTION.

        THE FOUR ARE THE TICKET'S FOUR — the occurrences it lists in the
        request/response schema module beside the one that goes: the ack, the
        ack's whole-job total, the usage-event list row and the usage-event
        detail. A deletion done by searching for the word would have taken all
        four, so each is read here with one configured price in it.

        ⚠ THAT IS NOT THE SAME COUNT AS THE SCHEMAS PUBLISHING THE NAME, and
        conflating the two is easy: SIX response schemas carry
        `billed_cost_micros`, and which ones is asserted as an exact set against
        the document in `test_two_request_fields_each_with_one_meaning.py`. This
        case covers three of those six plus the whole-job total, which is the
        one the document check CANNOT cover — its key is
        `task_total_billed_cost_micros`, a different token, so a
        property-name assertion walks straight past it and only a figure read
        off a job says it survived. The two checks are complementary rather than
        two counts of one thing.
        """
        self.a_direct_price_rule()
        job = TaskService.create_task(
            self.tenant, self.customer, balance_snapshot_micros=0,
            provider_cost_limit_micros=None,
            billing_owner_id=self.customer.id)

        ack = self.record("four-surfaces", task_id=str(job.id),
                          measurements={THE_QUANTITY: HOW_MANY_CALLS})
        listed = self.http.get(
            f"/api/v1/metering/customers/{self.customer.id}/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        detail = self.http.get(
            f"/api/v1/metering/usage/{ack['event_id']}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertEqual(detail.status_code, 200, detail.content)
        self.assertEqual(ack["billed_cost_micros"], WHAT_THE_RULE_CHARGES)
        self.assertEqual(ack["task_total_billed_cost_micros"],
                         WHAT_THE_RULE_CHARGES)
        self.assertEqual(listed.json()["data"][0]["billed_cost_micros"],
                         WHAT_THE_RULE_CHARGES)
        self.assertEqual(detail.json()["billed_cost_micros"],
                         WHAT_THE_RULE_CHARGES)


class ThereIsNoRequestSidePathToAPriceTest(_ARecordingTenant):
    """The other half of the claim: configuration is the ONLY door."""

    def test_a_body_carrying_a_customer_price_is_refused(self):
        """⚠ Refused, not dropped — and that is the whole acceptance criterion.

        Django Ninja discards a body key no schema publishes and answers `200`,
        so deleting the field alone would leave a client that has not been
        updated sending its own prices into a route that agrees with everything
        and reads none of it. A caller who has one to send has a rule to write
        instead, and they should learn that from a status code.
        """
        self.a_direct_price_rule()

        body = self.refused(
            "sent-a-price",
            measurements={THE_QUANTITY: HOW_MANY_CALLS},
            billed_cost_micros=WHAT_A_CALLER_WOULD_HAVE_SENT)

        self.assertEqual(body["type"].rsplit("/", 1)[-1], "validation_error")
        self.assertIn("billed_cost_micros",
                      json.dumps(body["errors"]),
                      "the refusal does not name the key it refused")
        self.assertEqual(Posting.objects.count(), 0,
                         "the refusal recorded the event anyway")

    def test_the_same_call_without_it_is_recorded_at_the_rules_price(self):
        """The refusal is about the FIELD, not about the call.

        Without this an implementation that refused the whole shape would pass
        the case above while breaking the rule that governs this route: an
        event that reaches UBB is recorded.
        """
        self.a_direct_price_rule()

        ack = self.record("same-call-no-price",
                          measurements={THE_QUANTITY: HOW_MANY_CALLS})

        self.assertEqual(ack["billed_cost_micros"], WHAT_THE_RULE_CHARGES)

    def test_another_unknown_key_is_still_dropped_and_that_is_the_posture(self):
        """⚠ THE ASYMMETRY, ASSERTED, BECAUSE IT IS DELIBERATE AND COSTLY.

        This route DROPS a body key it does not publish and answers 200 — argued
        in #272 and pinned in three places since, because a re-model that
        renames wire fields every slice would otherwise break a caller
        mid-migration once per rename. So the refusal above is a headstone on
        one name rather than a rule about unknown keys, and it has that form's
        cost: it answers for the name it holds and for no other spelling.

        The general rule was tried first and measured: `extra="forbid"` on this
        schema reddened 64 cases, three of which exist purely to state that a
        stale caller is accepted. This case is what stops the next author
        reaching for it again without reading why.

        A price under an INVENTED name is therefore dropped, not refused — and
        it reaches nothing, which is the half that actually matters and is
        asserted here rather than assumed.
        """
        self.a_direct_price_rule()

        ack = self.record("invented-a-name",
                          measurements={THE_QUANTITY: HOW_MANY_CALLS},
                          suggested_price_micros=WHAT_A_CALLER_WOULD_HAVE_SENT)

        self.assertEqual(ack["billed_cost_micros"], WHAT_THE_RULE_CHARGES)
        self.assertNotIn(str(WHAT_A_CALLER_WOULD_HAVE_SENT), json.dumps(ack),
                         "a price under an invented name reached the response")
        self.assertEqual(
            Posting.objects.get(id=ack["event_id"]).billed_cost_micros,
            WHAT_THE_RULE_CHARGES)

    def test_the_batch_route_refuses_it_too(self):
        """The other recording surface, which shares the item schema.

        A caller who could not send a price one at a time but could send a
        hundred at once would have the door open by another name.

        ⚠ AND IT IS THE WHOLE BATCH, NOT THE ITEM — asserted rather than left to
        be discovered, because that is the opposite of what this route does with
        an inadmissible SUPPLIER cost, where item two lands and item one comes
        back rejected. The difference is which layer answers. Per-item verdicts
        are for the ADMISSION checks the handler runs, and the handler runs
        after the body has parsed; a key the schema refuses is a parse failure,
        so it never reaches the loop that could have been selective. That has
        always been true here — a negative amount or a missing customer takes
        the same whole-batch 422 — so this joins an existing class rather than
        opening a new one, and it is the loud failure the deletion wants: a
        client sending prices has not been updated, and updating half its call
        sites should not look like success.
        """
        self.a_direct_price_rule()

        response = self.http.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": [
                usage_payload(self.customer, "batch-clean",
                              measurements={THE_QUANTITY: HOW_MANY_CALLS}),
                usage_payload(
                    self.customer, "batch-price",
                    measurements={THE_QUANTITY: HOW_MANY_CALLS},
                    billed_cost_micros=WHAT_A_CALLER_WOULD_HAVE_SENT)]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(Posting.objects.count(), 0,
                         "the clean sibling was recorded beside a body the "
                         "schema never parsed")

    def test_the_service_the_routes_call_has_no_keyword_for_it_either(self):
        """A door one layer below the wire is still a door.

        ⚠ The message is asserted, not just the exception: `assertRaises(
        TypeError)` around a call passing an unknown keyword asserts only that
        Python refuses unknown keywords, and passes identically against a
        service that never had this one.

        The two correlation values go in POSITIONALLY, for `usage_payload`'s
        reason in the module this imports from: one of their names is a retired
        word whose ledger entry caps how many files may still spell it, and this
        one does not have to be among them.
        """
        with self.assertRaisesRegex(TypeError, "billed_cost_micros"):
            UsageService.record_usage(
                self.tenant, self.customer, "no-such-keyword",
                "no-such-keyword",
                billed_cost_micros=WHAT_A_CALLER_WOULD_HAVE_SENT)


class TheRequestCarriesNoAmountTheCallerDecidesTest(SimpleTestCase):
    """Ruling 2, as a property of the published set rather than a sentence.

    Both money fields the recording request still carries are COGS-side: what
    the supplier says the call cost, and what the caller believes it cost. A
    third one would be a price, whatever it was called.
    """

    def test_every_amount_on_the_request_is_a_cost(self):
        published = {name for name in THE_WHOLE_RECORDING_REQUEST
                     if name.endswith("_micros")}

        self.assertEqual(published, {"provider_cost_micros",
                                     "claimed_provider_cost_micros"})

    def test_the_schema_class_agrees_with_that_set(self):
        """The class, not only the constant the tests share.

        A field added to the request and left out of the constant would be one
        every assertion above walked straight past.
        """
        declared = {name for name in RecordUsageRequest.model_fields
                    if name.endswith("_micros")}

        self.assertEqual(declared, {"provider_cost_micros",
                                    "claimed_provider_cost_micros"})
