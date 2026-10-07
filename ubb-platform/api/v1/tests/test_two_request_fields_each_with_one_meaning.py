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

**WHICH declaration admits the figure is the Event Type's LAST PUBLICATION
(#605).** Draft changes do not affect production recording. Production uses the
Event Type's last published declaration; changes take effect when they are
published. The same holds for every other declaration fact recording reads —
the costing method, the no-cost state, the missing-cost answer and the declared
quantity names — because the owner ruled them one unit (comment `6041500996`).
An Event Type declared and never published has no production declaration, so a
recording against it takes whatever path an undeclared key takes: the cases
below compare the two outcomes to EACH OTHER, never to what that path happens
to answer today, because #568 owns it. And a replay answers what was recorded
BEFORE any of this is asked, so a later publication cannot make a successful
write unreplayable. Each of those runs on the single route and on a batch item,
through the tenant's own Event Type routes.
"""

import json
from pathlib import Path
from typing import NamedTuple

from django.test import Client, SimpleTestCase, TestCase
from django.utils import timezone

from api.v1.schemas import RecordUsageRequest
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    REPORTED_COST_MAPPING, EventType, QuarantinedKey, ReportedCostMapping)
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
    UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED,
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
                source_kind=None, published=True):
        """An Event Type for `key`, with a reported-cost mapping when asked.

        `source_kind=None` declares no mapping at all, which is the commonest
        shape and the one every calculated declaration has.

        PUBLISHED unless asked otherwise, because the publication is what
        recording reads (#605): a draft here would be a declaration production
        has never seen, and a refusal below would pass for the wrong reason.

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
        if published:
            event_type.publish()
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
        finished, and the missing half is precisely the half that would admit
        this field. It cannot be published until the mapping is declared —
        the blocker says so — so production never reads it at all (#605), and
        the figure is refused as it is against a key nobody declared.
        """
        half = self.declare("acme.half", published=False)
        self.assertEqual(half.publication_blockers(), (REPORTED_COST_MAPPING,))

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
            "/api/v1/metering/analytics/economics",
            {"measures": "supplier_cogs"},
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")

        self.assertEqual(response.status_code, 200, response.content)
        cost = next(entry for entry in response.json()["rows"][0]["measures"]
                    if entry["measure"] == "supplier_cogs")
        self.assertEqual(cost["amount_micros"], 4_000)


# ---------------------------------------------------------------------------
# #605 — the last publication governs, on both routes
# ---------------------------------------------------------------------------

#: The supplier's response shape a `provider_response` mapping is read under.
SHAPE = "openai.responses.python.v1"

#: What a recording concluded about cost and price, as the acknowledgement
#: says it. The keys two outcomes are compared on — every one a column, or read
#: off the receipt, so a replay answers each as the recording did.
COSTING_FACTS = ("costing_status", "unresolved_reason", "provider_cost_micros",
                 "claimed_provider_cost_micros", "billed_cost_micros",
                 "pricing_status", "not_applicable_reason",
                 "uncosted_measurement_keys", "pricing_method")

#: The same conclusions as the posting stores them.
ECONOMIC_COLUMNS = ("costing_status", "unresolved_reason",
                    "provider_cost_micros", "claimed_provider_cost_micros",
                    "billed_cost_micros", "pricing_status",
                    "not_applicable_reason")


class Outcome(NamedTuple):
    """One recording, the same shape whichever route answered it.

    `body` is the acknowledgement where the event was recorded, and the
    refusal's `code` and `detail` where it was not.
    """

    accepted: bool
    body: dict


class _PublicationCase(_RecordingCase):
    """The tenant's own Event Type routes, beside the recording ones.

    Every declaration below is made, edited and published the way a tenant
    does it — nothing writes a catalogue row directly — because the claim is
    about what the lifecycle a tenant drives leaves production reading.
    """

    def admin(self, method, path, data=None):
        response = getattr(self.http, method)(
            f"/api/v1/event-types{path}", data=json.dumps(data or {}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}")
        self.assertLess(response.status_code, 300, response.content)

    def declared(self, key, *, costing_method, quantities=(),
                 source_kind=None):
        """A draft Event Type, with each quantity and mapping beneath it."""
        self.admin("post", "", {"key": key, "costing_method": costing_method,
                                "source_shape_id": SHAPE})
        for code in quantities:
            self.quantity(key, code)
        if source_kind is not None:
            self.mapping(key, source_kind)

    def published(self, key, **declaration):
        self.declared(key, **declaration)
        self.publish(key)

    def publish(self, key):
        self.admin("post", f"/{key}/publish")

    def quantity(self, key, code):
        self.admin("put", f"/{key}/measurements/{code}",
                   {"value_type": "integer", "unit": "call",
                    "source_kind": SOURCE_KIND_CALLER_SUPPLIED})

    def withdraw_quantity(self, key, code):
        self.admin("delete", f"/{key}/measurements/{code}")

    def mapping(self, key, source_kind):
        reads_the_response = source_kind == SOURCE_KIND_PROVIDER_RESPONSE
        self.admin("put", f"/{key}/reported-cost-mapping", {
            "source_kind": source_kind,
            "amount_representation": AMOUNT_REPRESENTATION_MICROS,
            "source_path": ["usage", "total_cost"] if reads_the_response else [],
            "currency": "usd"})

    def withdraw_mapping(self, key):
        self.admin("delete", f"/{key}/reported-cost-mapping")

    def costing_method(self, key, method):
        self.admin("patch", f"/{key}", {"costing_method": method})

    def rate(self, code, micros=1_000):
        """A Cost Rate for `code`, at `micros` a unit. The rate names a
        declaration of its own (`declares_a_quantity`), never the Event Type
        under test, so withdrawing a quantity there is never refused."""
        cost_rate_in_default_book(self.tenant, measurement_key=code,
                                  rate_per_unit_micros=micros, unit_quantity=1)

    def admitted(self, outcome):
        self.assertTrue(outcome.accepted, outcome.body)
        return outcome.body

    def refused_the_supplier_cost(self, outcome):
        """The #324 refusal, by its own message — not merely a refusal."""
        self.assertFalse(outcome.accepted, outcome.body)
        self.assertEqual(outcome.body["code"], "validation_error")
        self.assertIn("provider_cost_micros is the supplier's own reported "
                      "cost", outcome.body["detail"])
        self.assertIn(SOURCE_KIND_CALLER_SUPPLIED, outcome.body["detail"])

    def held(self, key):
        """What was held for `key`, without the key: the quantity names and
        numbers a remediation would have to decide about."""
        return sorted(
            (row.unrecognised, row.measurement_key, row.quantity,
             json.dumps(row.quantities, sort_keys=True))
            for row in QuarantinedKey.objects.filter(tenant=self.tenant,
                                                     event_type_key=key))


class _OnTheSingleRoute(_PublicationCase):
    """`POST /usage`: a 200 recorded it, a 422 did not."""

    def send(self, correlation, **body):
        response = self.post(correlation, **body)
        self.assertIn(response.status_code, (200, 422), response.content)
        answer = response.json()
        if response.status_code == 200:
            return Outcome(True, answer)
        return Outcome(False, {"code": answer["code"],
                               "detail": answer["detail"]})


class _OnTheBatchRoute(_PublicationCase):
    """One item of `POST /usage/batch`: the item's own verdict says which."""

    def send(self, correlation, **body):
        response = self.post_batch(
            usage_payload(self.customer, correlation, **body))
        self.assertEqual(response.status_code, 200, response.content)
        verdict = dict(response.json()["results"][0])
        if verdict.pop("accepted"):
            return Outcome(True, verdict)
        return Outcome(False, {"code": verdict["code"],
                               "detail": verdict["detail"]})


class _TheSupplierCostFollowsThePublication:
    """The owner's example, in both directions (#605).

    A deployed integration was generated against the publication. A draft edit
    to the mapping's source kind must not start refusing the figure that
    integration sends — nor start admitting one it does not — until the edit
    is published.
    """

    def test_a_draft_to_provider_response_leaves_the_figure_admitted(self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.mapping("acme.embed", SOURCE_KIND_PROVIDER_RESPONSE)

        ack = self.admitted(self.send("draft", event_type="acme.embed",
                                      provider_cost_micros=SUPPLIER))

        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)

        self.publish("acme.embed")

        self.refused_the_supplier_cost(self.send(
            "published", event_type="acme.embed",
            provider_cost_micros=SUPPLIER))

    def test_a_draft_to_caller_supplied_leaves_the_figure_refused(self):
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        self.mapping("acme.read", SOURCE_KIND_CALLER_SUPPLIED)

        self.refused_the_supplier_cost(self.send(
            "draft", event_type="acme.read", provider_cost_micros=SUPPLIER))
        self.assertEqual(Posting.objects.count(), 0)

        self.publish("acme.read")

        ack = self.admitted(self.send("published", event_type="acme.read",
                                      provider_cost_micros=SUPPLIER))
        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)

    def test_a_withdrawn_mapping_in_draft_leaves_the_figure_admitted(self):
        """The edit that cannot even be published: a `reported` declaration
        with no mapping is blocked. Production keeps the publication it has."""
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.withdraw_mapping("acme.embed")

        ack = self.admitted(self.send("withdrawn", event_type="acme.embed",
                                      provider_cost_micros=SUPPLIER))

        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)


class TheSupplierCostFollowsThePublicationOnTheSingleRouteTest(
        _TheSupplierCostFollowsThePublication, _OnTheSingleRoute):
    pass


class TheSupplierCostFollowsThePublicationOnTheBatchRouteTest(
        _TheSupplierCostFollowsThePublication, _OnTheBatchRoute):
    pass


class _EveryOtherFactFollowsThePublication:
    """The rest of the one unit the owner ruled on (#605): the costing method,
    the no-cost state, the missing-cost answer and the declared quantity names.
    Each is changed in draft, recorded against, then published and recorded
    against again."""

    def costing(self, correlation, key, **body):
        ack = self.admitted(self.send(correlation, event_type=key, **body))
        return ack["costing_status"], ack["unresolved_reason"]

    def test_a_draft_from_reported_to_calculated_waits_for_publication(self):
        self.rate("calls")
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       quantities=("calls",),
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        missing = (COSTING_STATUS_UNRESOLVED,
                   UNRESOLVED_REASON_REPORTED_COST_MISSING)
        self.assertEqual(self.costing("before", "acme.embed",
                                      measurements={"calls": 3}), missing)

        self.costing_method("acme.embed", COSTING_METHOD_CALCULATED)

        self.assertEqual(self.costing("draft", "acme.embed",
                                      measurements={"calls": 3}), missing)

        self.publish("acme.embed")

        ack = self.admitted(self.send("published", event_type="acme.embed",
                                      measurements={"calls": 3}))
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 3_000)

    def test_a_draft_from_calculated_to_reported_waits_for_publication(self):
        self.rate("calls")
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED,
                       quantities=("calls",))

        self.costing_method("acme.calc", COSTING_METHOD_REPORTED)
        self.mapping("acme.calc", SOURCE_KIND_CALLER_SUPPLIED)

        ack = self.admitted(self.send("draft", event_type="acme.calc",
                                      measurements={"calls": 3}))
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 3_000)
        self.refused_the_supplier_cost(self.send(
            "draft-figure", event_type="acme.calc",
            provider_cost_micros=SUPPLIER))

        self.publish("acme.calc")

        self.assertEqual(
            self.costing("published", "acme.calc", measurements={"calls": 3}),
            (COSTING_STATUS_UNRESOLVED,
             UNRESOLVED_REASON_REPORTED_COST_MISSING))

    def test_a_quantity_added_in_draft_is_not_declared_until_published(self):
        self.rate("calls")
        self.rate("tokens")
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED,
                       quantities=("calls",))
        report = {"calls": 1, "tokens": 1}
        held = (COSTING_STATUS_UNRESOLVED,
                UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED)

        self.quantity("acme.calc", "tokens")

        self.assertEqual(self.costing("draft", "acme.calc",
                                      measurements=report), held)
        self.assertEqual(len(self.held("acme.calc")), 1)

        self.publish("acme.calc")

        ack = self.admitted(self.send("published", event_type="acme.calc",
                                      measurements=report))
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 2_000)
        self.assertEqual(len(self.held("acme.calc")), 1)

    def test_a_quantity_withdrawn_in_draft_stays_declared_until_published(self):
        self.rate("calls")
        self.rate("tokens")
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED,
                       quantities=("calls", "tokens"))
        report = {"calls": 1, "tokens": 1}

        self.withdraw_quantity("acme.calc", "tokens")

        ack = self.admitted(self.send("draft", event_type="acme.calc",
                                      measurements=report))
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 2_000)
        self.assertEqual(self.held("acme.calc"), [])

        self.publish("acme.calc")

        self.assertEqual(
            self.costing("published", "acme.calc", measurements=report),
            (COSTING_STATUS_UNRESOLVED,
             UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED))

    def test_a_draft_that_would_declare_a_cost_waits_for_publication(self):
        """Published with nothing to cost; a draft quantity changes nothing."""
        self.rate("calls")
        self.published("acme.free", costing_method=COSTING_METHOD_CALCULATED)
        self.assertEqual(
            self.costing("before", "acme.free", measurements={"calls": 3}),
            (COSTING_STATUS_NOT_APPLICABLE, None))

        self.quantity("acme.free", "calls")

        self.assertEqual(
            self.costing("draft", "acme.free", measurements={"calls": 3}),
            (COSTING_STATUS_NOT_APPLICABLE, None))

        self.publish("acme.free")

        self.assertEqual(
            self.costing("published", "acme.free", measurements={"calls": 3}),
            (COSTING_STATUS_KNOWN, None))

    def test_a_draft_that_would_declare_no_cost_waits_for_publication(self):
        """The inverse, through the half the quantities do not cover: a
        published MAPPING is enough to carry a cost, so withdrawing it in
        draft changes nothing until the withdrawal is published.

        The call measures nothing. This declaration declares no quantity, so
        any name it reported would be held as undeclared — a third answer that
        would hide the two this case is about."""
        self.published("acme.mapped", costing_method=COSTING_METHOD_CALCULATED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.assertEqual(self.costing("before", "acme.mapped"),
                         (COSTING_STATUS_KNOWN, None))

        self.withdraw_mapping("acme.mapped")

        self.assertEqual(self.costing("draft", "acme.mapped"),
                         (COSTING_STATUS_KNOWN, None))

        self.publish("acme.mapped")

        self.assertEqual(self.costing("published", "acme.mapped"),
                         (COSTING_STATUS_NOT_APPLICABLE, None))


class EveryOtherFactFollowsThePublicationOnTheSingleRouteTest(
        _EveryOtherFactFollowsThePublication, _OnTheSingleRoute):
    pass


class EveryOtherFactFollowsThePublicationOnTheBatchRouteTest(
        _EveryOtherFactFollowsThePublication, _OnTheBatchRoute):
    pass


class _ANeverPublishedEventTypeIsRecordedAsAnUndeclaredOne:
    """Declared and never published → no production declaration (#605).

    The ruling is DELEGATION: recording against such a key takes exactly the
    path a key nobody declared takes, with no refusal and no implementation of
    its own. What that path does is #568's to decide, so nothing here says
    what it answers — every case records one body against a key nobody
    declared and the same body against a key declared and never published,
    and compares the two outcomes to each other.

    Two drafts, chosen so a draft that LEAKED would differ from the undeclared
    path on every body: a `reported` one admitting a caller-supplied figure,
    and a `calculated` one whose declared names would hold the unknown one.
    """

    BODIES = {
        "quantities": {"measurements": {"calls": 3}},
        "a name nobody declared": {"measurements": {"calls": 3,
                                                    "mystery": 2}},
        "the supplier's own figure": {"provider_cost_micros": SUPPLIER},
    }

    DRAFTS = {
        "reported": {"costing_method": COSTING_METHOD_REPORTED,
                     "quantities": ("calls",),
                     "source_kind": SOURCE_KIND_CALLER_SUPPLIED},
        "calculated": {"costing_method": COSTING_METHOD_CALCULATED,
                       "quantities": ("calls",)},
    }

    def comparable(self, outcome, key):
        """An outcome with `key` taken out, which is all two keys may differ
        by: a refusal's message names the Event Type it was asked about."""
        if not outcome.accepted:
            return (False, outcome.body["code"],
                    outcome.body["detail"].replace(repr(key), "<key>"))
        posting = Posting.objects.get(id=outcome.body["event_id"])
        return (True,
                {fact: outcome.body[fact] for fact in COSTING_FACTS},
                {column: getattr(posting, column)
                 for column in ECONOMIC_COLUMNS},
                self.held(key))

    def test_each_body_is_recorded_as_against_a_key_nobody_declared(self):
        self.rate("calls")
        for draft, declaration in self.DRAFTS.items():
            for case, (name, body) in enumerate(self.BODIES.items()):
                with self.subTest(draft=draft, body=name):
                    unpublished = f"draft.{draft}.case{case}"
                    undeclared = f"nobody.{draft}.case{case}"
                    self.declared(unpublished, **declaration)

                    against_the_draft = self.send(
                        unpublished, event_type=unpublished, **body)
                    against_nothing = self.send(
                        undeclared, event_type=undeclared, **body)

                    self.assertEqual(
                        self.comparable(against_the_draft, unpublished),
                        self.comparable(against_nothing, undeclared))


class ANeverPublishedEventTypeOnTheSingleRouteTest(
        _ANeverPublishedEventTypeIsRecordedAsAnUndeclaredOne,
        _OnTheSingleRoute):
    pass


class ANeverPublishedEventTypeOnTheBatchRouteTest(
        _ANeverPublishedEventTypeIsRecordedAsAnUndeclaredOne,
        _OnTheBatchRoute):
    pass


class _AReplayAnswersWhatWasRecorded:
    """Replay wins (#605, owner ruling 2).

    Once an event is recorded under an idempotency key, a retry answers the
    original acknowledgement — whatever has been published since, and before
    any admission is asked, so current configuration cannot make an already
    successful write unreplayable. Keyed exactly as it always was, by the
    tenant, the customer and the key: no body is compared.
    """

    def replays(self, original, replay):
        """The replay IS the original: the same event, the same conclusions,
        and nothing new recorded."""
        self.assertEqual(replay["event_id"], original["event_id"])
        self.assertEqual({fact: replay[fact] for fact in COSTING_FACTS},
                         {fact: original[fact] for fact in COSTING_FACTS})
        self.assertEqual(replay["measurements"], original["measurements"])
        self.assertEqual(Posting.objects.count(), 1)

    def test_a_replay_records_nothing_new(self):
        self.rate("calls")
        original = self.admitted(self.send("once", measurements={"calls": 3}))

        self.replays(original, self.admitted(
            self.send("once", measurements={"calls": 3})))

    def test_a_replay_after_the_source_kind_is_republished(self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        original = self.admitted(self.send(
            "kind", event_type="acme.embed", provider_cost_micros=SUPPLIER))
        self.mapping("acme.embed", SOURCE_KIND_PROVIDER_RESPONSE)
        self.publish("acme.embed")

        self.replays(original, self.admitted(self.send(
            "kind", event_type="acme.embed", provider_cost_micros=SUPPLIER)))

    def test_a_replay_after_the_costing_method_is_republished(self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        original = self.admitted(self.send(
            "method", event_type="acme.embed", provider_cost_micros=SUPPLIER))
        self.costing_method("acme.embed", COSTING_METHOD_CALCULATED)
        self.publish("acme.embed")

        self.replays(original, self.admitted(self.send(
            "method", event_type="acme.embed", provider_cost_micros=SUPPLIER)))

    def test_a_replay_after_the_quantities_are_republished(self):
        """The original held a name; declaring it since neither re-costs the
        recorded event nor holds the name a second time."""
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED,
                       quantities=("calls",))
        report = {"calls": 1, "tokens": 1}
        original = self.admitted(self.send(
            "names", event_type="acme.calc", measurements=report))
        self.assertEqual(original["unresolved_reason"],
                         UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED)
        self.quantity("acme.calc", "tokens")
        self.publish("acme.calc")

        self.replays(original, self.admitted(self.send(
            "names", event_type="acme.calc", measurements=report)))
        self.assertEqual(len(self.held("acme.calc")), 1)

    def test_a_replay_after_its_grouping_field_is_retired(self):
        """The Grouping Field registry is current configuration too, and its
        admission WRITES: a replay neither re-admits nor records a value.

        No tenant route retires a field, so the setup writes `retired_at`
        directly; the replay carries a value the retired field would refuse,
        which only an admission that ran would notice.
        """
        GroupingField.objects.create(
            tenant=self.tenant, key="model", slot="grouping_field_1",
            scope="event", max_cardinality=5)
        original = self.admitted(self.send(
            "grouped", **declared_grouping_values({"model": "gpt-4"})))
        GroupingField.objects.filter(tenant=self.tenant, key="model").update(
            retired_at=timezone.now())

        self.replays(original, self.admitted(self.send(
            "grouped", **declared_grouping_values({"model": "gpt-5"}))))
        self.assertEqual(
            sorted(GroupingFieldValue.objects.values_list("value", flat=True)),
            ["gpt-4"])

    def test_a_replay_with_a_different_body_answers_the_original(self):
        """No body is compared, as before #605 — and a different body is not
        a new event either: it carries a figure nothing here admits, which only
        an admission that ran would refuse."""
        self.rate("calls")
        original = self.admitted(self.send("body", measurements={"calls": 3}))

        replay = self.admitted(self.send("body", measurements={"calls": 9},
                                         claimed_provider_cost_micros=CLAIMED,
                                         provider_cost_micros=SUPPLIER))

        self.replays(original, replay)
        self.assertEqual(replay["measurements"], {"calls": 3})

    def test_a_replay_is_the_same_customers(self):
        """The lookup's scope is unchanged: the same key under another
        customer of the tenant is that customer's own new event."""
        self.rate("calls")
        first = self.admitted(self.send("shared", measurements={"calls": 3}))
        self.customer = Customer.objects.create(tenant=self.tenant,
                                                external_id="another")

        second = self.admitted(self.send("shared", measurements={"calls": 4}))

        self.assertNotEqual(second["event_id"], first["event_id"])
        self.assertEqual(second["measurements"], {"calls": 4})
        self.assertEqual(Posting.objects.count(), 2)

    def test_a_refused_new_event_writes_nothing(self):
        """Replay-first moves no refusal: a NEW event the publication does not
        admit records nothing and spends no grouping value."""
        GroupingField.objects.create(
            tenant=self.tenant, key="model", slot="grouping_field_1",
            scope="event", max_cardinality=5)

        self.refused_the_supplier_cost(self.send(
            "new", event_type="acme.embed", provider_cost_micros=SUPPLIER,
            **declared_grouping_values({"model": "gpt-4"})))

        self.assertEqual(Posting.objects.count(), 0)
        self.assertEqual(GroupingFieldValue.objects.count(), 0)


class AReplayAnswersWhatWasRecordedOnTheSingleRouteTest(
        _AReplayAnswersWhatWasRecorded, _OnTheSingleRoute):
    pass


class AReplayAnswersWhatWasRecordedOnTheBatchRouteTest(
        _AReplayAnswersWhatWasRecorded, _OnTheBatchRoute):
    pass


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

    def test_the_price_is_now_read_back_and_never_sent(self):
        """`billed_cost_micros` is a RESPONSE field and nothing else (#365).

        This case used to hold the question — *why is the caller's price still
        here?* — and #146 §8's answer was that slice 3 deletes it. Slice 3 did
        not, and was right not to: the direct-price rules that replace it are
        slice 4's, so deleting the field first would have left a window in which
        nothing could supply a customer price directly. The field and its
        replacement land in one slice, and this case now carries the claim that
        replaced the question.

        THE DELETION WAS BY CLASS AND NOT BY TOKEN, WHICH IS WHY BOTH
        DIRECTIONS ARE ASSERTED. The name appears on seven published schemas;
        exactly one of them is a request, and a grep-shaped deletion would have
        been wrong in both directions at once — taking the six a tenant reads
        their own resolved prices back from, or missing the one that goes. So
        the request half is asserted ABSENT and the response half is asserted as
        an exact SET: an eighth carrier, or a lost seventh, is read by a person.

        `UnresolvedQueueRow` is the newest of the six (#364) and publishes the
        price a posting has — `null` for most rows in that queue, with
        `pricing_status` beside it saying UBB could not resolve one. That is the
        response side of the line rather than an erosion of it: what a tenant
        may READ has grown, and what a caller may SEND is now nothing.

        Where a price comes from instead is
        `test_a_customer_price_comes_only_from_configuration.py`, which asserts
        the rule resolving one and the request refusing to carry one.

        NINE SINCE #465: Stops and breaches itemises the events that landed
        past a stop, and each itemised row, the block that totals them and
        the per-family totals row publish the price a posting has — the
        response side of the line again, on the one report whose subject is
        what was spent past a stop.

        SEVEN SINCE #501, AND THE FALL IS THE POINT RATHER THAN A CORRECTION.
        The grouped margin row and the per-Event-Type usage row went with the
        routes that served them, so two of the nine response schemas carrying
        this property are gone. The one economic query publishes the same money
        under a MEASURE's own name with a state beside it, which is why nothing
        on this list replaces them: the property name itself is what the
        collapse stopped using for a total.
        """
        self.assertNotIn("billed_cost_micros", THE_WHOLE_RECORDING_REQUEST)
        self.assertNotIn(
            "billed_cost_micros",
            self.schemas["RecordUsageRequest"]["properties"])
        carrying = {name for name, schema in self.schemas.items()
                    if "billed_cost_micros" in schema.get("properties", {})}
        self.assertEqual(carrying, {
            "RecordUsageResponse", "UnresolvedQueueRow", "UsageEventDetailOut",
            "UsageEventOut", "ItemisedEventRow", "ItemisedEventsOut",
            "SpendControlFamilyTotalsRow"})


def _bounds(node):
    """The (minimum, maximum) an integer-or-null property admits.

    Django Ninja renders an optional bounded integer as a two-member `anyOf`,
    so the bound sits in the integer branch rather than on the node.
    """
    for member in node.get("anyOf", (node,)):
        if member.get("type") == "integer":
            return member.get("minimum"), member.get("maximum")
    raise AssertionError(f"no integer branch to bound: {json.dumps(node)}")
