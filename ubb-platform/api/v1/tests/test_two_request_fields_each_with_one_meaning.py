"""A number the supplier reported and a number the caller believes (#324).

Two different facts, and after this ticket they arrive on two different fields.
Before it, one field carried both and neither the caller nor UBB could tell
which had arrived:

* `provider_cost_micros` is what the **supplier** says the call cost. It is
  COGS. It is admissible only where the Event Type declares the reported
  costing method **and** a mapping whose source kind is the caller-supplied
  one — the declaration that says "this number arrives on the call". Anywhere
  else it is **refused, naming that declaration** — a 422 on the single route,
  and a rejected item verdict on the batch route, whose body is 200 whatever
  its items say. The alternative is the failure this module exists to stop: a
  caller sending the figure somewhere UBB will never read it as cost and never
  finding out. Django Ninja **drops** a body key no schema publishes rather
  than refusing it, and a wrong request that answers `200` is invisible to
  every gate in this repository.

* `claimed_provider_cost_micros` is what the **caller** believes it cost. It is
  accepted on any event, recorded as stated, and is never COGS: never rated,
  never summed into a cost total, never the number beside it.

**WHY NOT ONE FIELD ROUTED BY THE DECLARATION.** A field whose meaning flips
with a declaration the caller cannot see at the call site is retroactive —
change the Event Type and every historical row on that key changes meaning,
with nothing recording which meaning was in force when the row was written. Two
fields make each row self-describing.

The values are imported, never spelled: `core.vocabulary` is generated from
`domain-vocabulary/`, and a literal here would be a second copy of a set the
registry owns (ADR-0008 §3).
"""

import json
from pathlib import Path

from django.test import Client, SimpleTestCase, TestCase

from api.v1.schemas import RecordUsageRequest
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType, ReportedCostMapping
from apps.platform.event_types.tests._helpers import (
    declares_a_caller_supplied_cost)
from apps.platform.grouping_fields.models import (
    GroupingField, GroupingFieldValue)
from apps.platform.tenants.models import Tenant, TenantApiKey
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_NOT_APPLICABLE,
    COSTING_STATUS_UNRESOLVED,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

# The recording body and the whole published parameter set both come from
# there rather than being built here. TWO of the request's keys are retired
# words whose ledger entries cap how many files may still contain them — a
# ceiling on SPREAD, not only a count of what is left to fix — and that module
# is already counted for both. Nothing here spells either.
from api.v1.tests.test_metering_endpoints import (
    THE_WHOLE_RECORDING_REQUEST, declared_grouping_values, usage_payload)

#: The committed contract, at the git root — `ubb/openapi/v1.json`. The same
#: address `test_the_cost_reaches_the_contract.py` reads it from.
SPEC_PATH = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"

#: The supplier's own figure, and the caller's belief about the same call. Two
#: numbers that cannot be confused for one another in a failure message, and
#: neither of which is a plausible default.
SUPPLIER = 4_200
CLAIMED = 987_654


class _RecordingCase(TestCase):
    """A tenant with metering on, and the two routes that record against it."""

    def setUp(self):
        self.http = Client()
        self.tenant = Tenant.objects.create(name="Two Fields",
                                            products=["metering"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="two_fields")

    def declare(self, key, *, costing_method=COSTING_METHOD_REPORTED,
                source_kind=None):
        """An Event Type for `key`, with a reported-cost mapping when asked.

        `source_kind=None` declares no mapping at all, which is the commonest
        shape and the one every calculated declaration has.

        The ADMITTING pair has its own door — `declares_a_caller_supplied_cost`
        — and every test below that wants the figure accepted goes through it,
        so this repository states that combination in one place and the shapes
        that merely resemble it are spelled here.
        """
        event_type = EventType.objects.create(
            tenant=self.tenant, key=key, costing_method=costing_method)
        if source_kind is not None:
            ReportedCostMapping.objects.create(
                event_type=event_type, source_kind=source_kind,
                source_path=(["usage", "total_cost"]
                             if source_kind == SOURCE_KIND_PROVIDER_RESPONSE
                             else []),
                amount_representation=AMOUNT_REPRESENTATION_MICROS,
                currency="usd")
        return event_type

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

    def post_batch(self, *items):
        return self.http.post(
            "/api/v1/metering/usage/batch",
            data=json.dumps({"events": list(items)}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

    def detail(self, event_id):
        response = self.http.get(
            f"/api/v1/metering/usage/{event_id}",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class TheSupplierCostIsAdmissibleOnlyWhereItIsDeclaredTest(_RecordingCase):
    """One declaration admits it. Everything else is a refusal, not a drop."""

    def test_the_declared_pair_admits_it(self):
        """The positive control every refusal below is worthless without."""
        declares_a_caller_supplied_cost(self.tenant, "acme.embed")

        ack = self.record("admitted", event_type="acme.embed",
                          provider_cost_micros=SUPPLIER)

        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)

    def test_no_declaration_at_all_refuses_it(self):
        """The commonest shape: a caller who never declared an Event Type.

        The registry is opt-in, so this is not a misconfiguration — it is a
        tenant who has not adopted it. What they may not do is assert the
        supplier's own number against nothing.
        """
        body = self.refused("undeclared", event_type="acme.embed",
                            provider_cost_micros=SUPPLIER)

        self.assertEqual(body["code"], "validation_error")
        self.assertEqual(Posting.objects.count(), 0,
                         "the refusal recorded the event anyway")

    def test_an_event_naming_no_event_type_refuses_it(self):
        """A request that names no Event Type has no declaration to read.

        The key is optional on the recording request and always has been, so
        this is the shape of every call in the repository that predates the
        registry. It is refused for the same reason as the case above rather
        than being waved through as "nothing to check against".
        """
        self.refused("no-key", provider_cost_micros=SUPPLIER)

        self.assertEqual(Posting.objects.count(), 0)

    def test_a_calculated_declaration_refuses_it(self):
        """The tenant declared that UBB works this cost out from rates.

        Accepting the caller's figure here would silently override the
        declaration on one call, which is exactly the retroactive ambiguity two
        fields exist to prevent.
        """
        self.declare("acme.calc", costing_method=COSTING_METHOD_CALCULATED)

        self.refused("calculated", event_type="acme.calc",
                     provider_cost_micros=SUPPLIER)

    def test_a_reported_cost_read_off_the_suppliers_response_refuses_it(self):
        """The sharp one: the METHOD is right and the SOURCE KIND is not.

        This declaration says the figure is read out of the supplier's own
        response by the generated integration. A number arriving on the call
        instead did not come from where the tenant declared it comes from, and
        a check that stopped at the costing method would admit it.
        """
        self.declare("acme.read", source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        self.refused("provider-response", event_type="acme.read",
                     provider_cost_micros=SUPPLIER)

    def test_a_reported_declaration_with_no_mapping_refuses_it(self):
        """`reported` alone does not say WHERE the figure comes from.

        A declaration with no mapping is one a tenant has started and not
        finished — its postings say `reported_cost_missing` — and the missing
        half is precisely the half that would admit this field.
        """
        self.declare("acme.half")

        self.refused("no-mapping", event_type="acme.half",
                     provider_cost_micros=SUPPLIER)

    def test_the_refusal_names_the_declaration_that_would_admit_it(self):
        """A 422 that says only "no" leaves the integrator guessing.

        Both halves of the declaration are named, from the registry rather than
        spelled, so a caller reading the body knows what to declare.
        """
        body = self.refused("named", event_type="acme.embed",
                            provider_cost_micros=SUPPLIER)

        detail = body["detail"]
        self.assertIn(COSTING_METHOD_REPORTED, detail)
        self.assertIn(SOURCE_KIND_CALLER_SUPPLIED, detail)
        self.assertIn("claimed_provider_cost_micros", detail,
                      "the refusal names no field the caller MAY use")

    def test_the_same_event_without_the_figure_is_recorded(self):
        """The refusal is about the FIELD, not about the Event Type.

        The same declaration that refuses the figure records the event happily
        without it. Without this an implementation that refused every event on
        an inadmissible Event Type would pass every case above while breaking
        the one rule that governs this route: an event that reaches UBB is
        recorded.
        """
        self.declare("acme.calc", costing_method=COSTING_METHOD_CALCULATED)

        ack = self.record("no-figure", event_type="acme.calc")

        self.assertIsNone(ack["provider_cost_micros"])
        self.assertEqual(ack["costing_status"],
                         COSTING_STATUS_NOT_APPLICABLE)

    def test_the_refusal_spends_nothing_of_the_tenants_keyspace(self):
        """A refused request must not have WRITTEN on its way to being refused.

        The grouping-field admission on both routes records novel values
        against a per-key cardinality cap, and it used to run first. A request
        refused here would then have burned a value out of a cap it never got
        to use — permanently, since the ledger of admitted values is not
        rolled back by a later refusal, and a tenant near their cap could be
        pushed over it by requests that recorded nothing.

        This is what the ordering in both routes is for, and the order is
        invisible in a diff, so it is asserted rather than commented.
        """
        GroupingField.objects.create(
            tenant=self.tenant, key="model", slot="grouping_field_1",
            scope="event", max_cardinality=5)

        self.refused("burns-nothing", event_type="acme.embed",
                     provider_cost_micros=SUPPLIER,
                     **declared_grouping_values({"model": "gpt-4"}))

        self.assertEqual(GroupingFieldValue.objects.count(), 0,
                         "the refusal spent a novel grouping value on a "
                         "request that was never recorded")

    def test_the_batch_route_refuses_the_item_and_records_its_siblings(self):
        """Per ITEM, like every other validation failure on that route.

        A batch is N independent singles. Refusing the whole batch for one
        item's inadmissible field would throw away N-1 events the supplier has
        already charged for.
        """
        declares_a_caller_supplied_cost(self.tenant, "acme.embed")

        response = self.post_batch(
            usage_payload(self.customer, "batch-bad", event_type="acme.calc",
                          provider_cost_micros=SUPPLIER),
            usage_payload(self.customer, "batch-good", event_type="acme.embed",
                          provider_cost_micros=SUPPLIER))

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["accepted"], body["rejected"]), (1, 1))
        refused, recorded = body["results"]
        self.assertFalse(refused["accepted"])
        self.assertEqual(refused["code"], "validation_error")
        self.assertIn(SOURCE_KIND_CALLER_SUPPLIED, refused["detail"])
        self.assertTrue(recorded["accepted"])
        self.assertEqual(recorded["provider_cost_micros"], SUPPLIER)


class TheClaimedCostIsAcceptedAnywhereTest(_RecordingCase):
    """The caller's own belief: accepted everywhere, and never COGS."""

    def test_it_is_accepted_where_the_supplier_cost_is_refused(self):
        """The pair, on the same undeclared tenant, one call apart.

        Nothing about the claim consults a declaration — that is the whole
        difference between the two fields, and it is asserted against the
        exact request shape refused above.
        """
        ack = self.record("claim-undeclared", event_type="acme.embed",
                          claimed_provider_cost_micros=CLAIMED)

        self.assertEqual(ack["claimed_provider_cost_micros"], CLAIMED)
        self.assertEqual(ack["provider_cost_micros"], 0,
                         "the claim became the supplier cost — the two fields "
                         "have run together, which is the failure this ticket "
                         "is about")

    def test_it_is_accepted_beside_an_unresolved_cost(self):
        """The case it exists for: the supplier has not billed yet.

        A `reported` declaration with nothing to report leaves the posting
        `unresolved` — and the caller's own estimate rides beside it without
        settling anything, which is what "never COGS" means at the moment it
        would be most tempting to read it as one.
        """
        declares_a_caller_supplied_cost(self.tenant, "acme.embed")

        ack = self.record("claim-unresolved", event_type="acme.embed",
                          claimed_provider_cost_micros=CLAIMED)

        self.assertEqual(ack["claimed_provider_cost_micros"], CLAIMED)
        self.assertIsNone(ack["provider_cost_micros"])
        self.assertEqual(ack["costing_status"], COSTING_STATUS_UNRESOLVED)
        self.assertEqual(ack["unresolved_reason"],
                         UNRESOLVED_REASON_REPORTED_COST_MISSING)

    def test_it_is_recorded_as_stated_and_read_back(self):
        """The round trip the request half completes.

        #323 published the field on all three responses and nothing could put
        a value in it. This is the first call in the repository that can.
        """
        ack = self.record("claim-stored", claimed_provider_cost_micros=CLAIMED)

        stored = Posting.objects.get(id=ack["event_id"])
        self.assertEqual(stored.claimed_provider_cost_micros, CLAIMED)
        self.assertEqual(self.detail(ack["event_id"])[
            "claimed_provider_cost_micros"], CLAIMED)

    def test_it_is_never_read_by_rating(self):
        """Two identical calls, one carrying a claim. Both cost the same.

        The claim is a wildly different number from the rate's own answer, so
        a spine that read it — as a cost, as a markup basis, as a fallback —
        could not produce the same two amounts.
        """
        cost_rate_in_default_book(
            self.tenant, measurement_key="calls",
            rate_per_unit_micros=1_000, unit_quantity=1)

        plain = self.record("rated-plain", measurements={"calls": 3})
        claimed = self.record("rated-claimed", measurements={"calls": 3},
                              claimed_provider_cost_micros=CLAIMED)

        self.assertEqual(plain["provider_cost_micros"], 3_000)
        self.assertEqual(claimed["provider_cost_micros"], 3_000)
        self.assertEqual(claimed["billed_cost_micros"],
                         plain["billed_cost_micros"])
        # ONE KEY OF THE WHOLE RESPONSE, which is stronger than checking the
        # two amounts and the recorded receipt by name: it covers every key the
        # detail body has, including the ones this ticket does not know about.
        detail = self.detail(claimed["event_id"])
        carrying = sorted(key for key, value in detail.items()
                          if str(CLAIMED) in json.dumps(value))
        self.assertEqual(carrying, ["claimed_provider_cost_micros"],
                         "the caller's belief reached something other than "
                         "its own field")

    def test_it_is_never_summed_into_a_cost_total(self):
        """A total over the column, with a claim recorded against it.

        The read that matters is the tenant's own analytics rollup: if a claim
        ever joined a cost total it would inflate margin on a number nobody
        supplied.
        """
        cost_rate_in_default_book(
            self.tenant, measurement_key="calls",
            rate_per_unit_micros=1_000, unit_quantity=1)
        self.record("total-one", measurements={"calls": 2})
        self.record("total-two", measurements={"calls": 2},
                    claimed_provider_cost_micros=CLAIMED)

        response = self.http.get(
            "/api/v1/metering/analytics/usage",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["total_provider_cost_micros"], 4_000)


class TheWholeRequestIsPublishedTest(SimpleTestCase):
    """What the recording request publishes, asserted as a WHOLE set.

    A per-key assertion passes while an unpublished key rides along beside it,
    and this repository has already paid for that once: a read route sent two
    query parameters it publishes nowhere and answered `200` on the axis
    default for years, because the framework drops what no schema declares.
    The set is the assertion; the two new fields are members of it.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.schemas = json.loads(
            SPEC_PATH.read_text(encoding="utf-8"))["components"]["schemas"]

    def test_the_document_publishes_exactly_this_parameter_set(self):
        published = frozenset(
            self.schemas["RecordUsageRequest"]["properties"])

        self.assertEqual(published, THE_WHOLE_RECORDING_REQUEST)

    def test_the_schema_class_declares_exactly_the_same_set(self):
        """The other direction: a field on the class nobody published.

        Both routes take their body from this class, so a field declared here
        and missing from the document above would be one a caller could send
        and no generated client could know about.
        """
        self.assertEqual(frozenset(RecordUsageRequest.model_fields),
                         THE_WHOLE_RECORDING_REQUEST)

    def test_the_claim_carries_the_shared_amount_bound(self):
        """The same bound every other cost figure on this request carries."""
        claim = self.schemas["RecordUsageRequest"]["properties"][
            "claimed_provider_cost_micros"]
        supplier = self.schemas["RecordUsageRequest"]["properties"][
            "provider_cost_micros"]

        self.assertEqual(_bounds(claim), _bounds(supplier))

    def test_the_three_unrelated_amounts_keep_their_own_bound(self):
        """The same literal, three schemas along, and NOT the same rule.

        `amount_micros` on the wallet writes is `gt=0` — a movement of nothing
        is not a movement — while a cost of zero is an ordinary, resolved
        amount. They share a ceiling and nothing else, so a search-and-replace
        that harmonised them would quietly admit a zero-amount debit.
        """
        ceiling = _bounds(self.schemas["RecordUsageRequest"]["properties"][
            "claimed_provider_cost_micros"])[1]

        for name in ("DebitRequest", "CreditRequest", "CreateGrantRequest"):
            with self.subTest(schema=name):
                node = self.schemas[name]["properties"]["amount_micros"]
                self.assertEqual(node.get("exclusiveMinimum"), 0,
                                 f"{name}.amount_micros stopped refusing zero")
                self.assertEqual(node.get("maximum"), ceiling,
                                 f"{name}.amount_micros no longer carries the "
                                 f"shared ceiling")

    def test_the_request_still_carries_the_directly_supplied_price(self):
        """`billed_cost_micros` STAYS on the request, and this is why.

        #146 §8 — this slice's own source decision — says slice 3 deletes it.
        It does not. Its declared replacement is slice 4's direct-price rules,
        so deleting the field here would leave a window in which nothing can
        supply a price directly: a caller with a negotiated price and no rate
        would have no way to state it at all. The field goes in slice 4,
        TOGETHER WITH its replacement, and this test is what carries the
        ruling forward rather than a sentence in a merged commit message.

        The schemas that publish a field of the SAME NAME on the way back are
        kept by #146 §8.1 and are not this ticket's to touch. That half is
        counted rather than asserted in prose: the request is one of the
        schemas carrying the name, and every other one is a response.

        ⚠ SIX RESPONSES SINCE #364, and the sixth is on the RESPONSE side of
        that line rather than an erosion of it. `UnresolvedQueueRow` publishes
        the price a posting has — which for most rows in that queue is `null`,
        with `pricing_status` beside it saying UBB could not resolve one. The
        set is pinned rather than counted precisely so that a seventh carrier
        is read by a person, and reading this one confirms the request half is
        untouched: the field a caller may SEND still appears on exactly one
        schema, and ticket 18 is still the ticket that deletes it.
        """
        self.assertIn("billed_cost_micros", THE_WHOLE_RECORDING_REQUEST)
        self.assertIn(
            "billed_cost_micros",
            self.schemas["RecordUsageRequest"]["properties"])
        carrying = {name for name, schema in self.schemas.items()
                    if "billed_cost_micros" in schema.get("properties", {})}
        self.assertEqual(carrying - {"RecordUsageRequest"}, {
            "GroupingFieldMarginRow", "RecordUsageResponse",
            "UnresolvedQueueRow", "UsageEventDetailOut", "UsageEventOut",
            "UsageMetricOut"})


def _bounds(node):
    """The (minimum, maximum) an integer-or-null property admits.

    Django Ninja renders an optional bounded integer as a two-member `anyOf`,
    so the bound sits in the integer branch rather than on the node.
    """
    for member in node.get("anyOf", (node,)):
        if member.get("type") == "integer":
            return member.get("minimum"), member.get("maximum")
    raise AssertionError(f"no integer branch to bound: {json.dumps(node)}")
