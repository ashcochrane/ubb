"""A number the supplier reported and a number the caller believes (#324, #570).

Different facts, and they arrive on different fields. Before #324 one field
carried both and neither the caller nor UBB could tell which had arrived:

* `provider_cost_micros` is the supplier cost **supplied directly by the
  caller**. It is COGS. It is admissible only where the Event Type declares the
  reported costing method **and** a mapping whose source kind is the
  caller-supplied one — the declaration that says "the caller supplies this
  number". Anywhere else it is **refused, naming the field that is admissible
  there, or that none is** — a 422 on the single route, and a rejected item
  verdict on the batch route, whose body is 200 whatever its items say. The
  alternative is the failure this module exists to stop: a caller sending the
  figure somewhere UBB will never read it as cost and never finding out.
  Django Ninja **drops** a body key no schema publishes rather than refusing
  it, and a wrong request that answers `200` is invisible to every gate in this
  repository.

* `provider_response_cost_micros` is the supplier cost the caller **obtained
  from the provider's response** (#570). It is COGS too, and it is the only
  field that may carry it: admissible only where the mapping's source kind is
  `provider_response`, refused anywhere else in the same way. UBB cannot verify
  how the figure was obtained, and admits it because the declared source says
  that is where it comes from. It is a TRANSPORT and not a second cost fact:
  the figure lands in the one supplier-cost column and is read back as
  `provider_cost_micros`, which on every response is the resolved cost
  whichever valid transport supplied it. Both fields on one event are refused
  — nothing is summed or chosen.

* `claimed_provider_cost_micros` is what the **caller** believes it cost. It is
  accepted on any event, recorded as stated, and is never COGS: never rated,
  never summed into a cost total, never the number beside it.

THE ADMISSION MATRIX (owner ruling on #570, comment `6040966104`), the same on
the single route and on a batch item:

    published declaration          provider_cost_micros   provider_response_…
    reported + caller_supplied     admitted               refused
    reported + provider_response   refused                admitted
    calculated, or none at all     refused                refused
    reported, no mapping           refused                refused

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

from api.v1 import metering_endpoints, verification
from api.v1.integration_blueprint import _event_type_content
from api.v1.schemas import (
    IntegrationBlueprintVerificationRecordIn, RecordUsageRequest)
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    REPORTED_COST_MAPPING, EventType, QuarantinedKey, ReportedCostMapping)
from apps.platform.event_types.publication import last_published_declaration
from core.problems import Problem
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
    GROUPING_FIELD_SCOPE_EVENT,
    MEASUREMENT_VALUE_TYPE_INTEGER,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    UNIT_CALL,
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
#: A supplier figure read off the provider's response (#570) — a third number,
#: so a case can tell which transport's figure reached the posting.
FROM_THE_RESPONSE = 7_350

#: The two transports a supplier cost may arrive on (#570), and the source
#: kind whose published mapping admits each — the matrix's two columns.
CALLER_FIELD = "provider_cost_micros"
RESPONSE_FIELD = "provider_response_cost_micros"
ADMITTED_BY = {SOURCE_KIND_CALLER_SUPPLIED: CALLER_FIELD,
               SOURCE_KIND_PROVIDER_RESPONSE: RESPONSE_FIELD}

#: How every refusal of a figure opens: the meaning of the field refused. Held
#: here rather than imported, so a reworded message is a red test to read.
OPENS_WITH = {
    CALLER_FIELD: "provider_cost_micros is a supplier cost supplied directly "
                  "by the caller",
    RESPONSE_FIELD: "provider_response_cost_micros is a supplier cost the "
                    "caller obtained from the provider's response",
}
#: What a refusal says where no transport is admissible at all.
NEITHER = ("neither provider_cost_micros nor provider_response_cost_micros "
           "is admissible")
#: What a refusal of both transports on one event says.
BOTH_SENT = ("provider_cost_micros and provider_response_cost_micros were "
             "both sent")
NOTHING_CHOSEN = "nothing is summed or chosen"


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
        response by the generated integration. A number supplied directly by
        the caller did not come from where the tenant declared it comes from,
        and a check that stopped at the costing method would admit it. Since
        #570 that figure has its own transport, so the refusal says which one
        to send it on instead of leaving the caller nowhere to go.
        """
        self.declare("acme.read", source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        body = self.refused("provider-response", event_type="acme.read",
                            provider_cost_micros=SUPPLIER)

        self.assertTrue(body["detail"].startswith(OPENS_WITH[CALLER_FIELD]),
                        body["detail"])
        self.assertIn(f"admissible only as {RESPONSE_FIELD}", body["detail"])
        self.assertEqual(Posting.objects.count(), 0)

    def test_the_same_figure_read_off_the_response_is_admitted_on_its_own_field(
            self):
        """The inversion of the case above (#570): the declaration that
        refuses `provider_cost_micros` admits the figure on the transport whose
        published meaning is "obtained from the provider's response"."""
        self.declare("acme.read", source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        ack = self.record("read", event_type="acme.read",
                          provider_response_cost_micros=FROM_THE_RESPONSE)

        self.assertEqual(ack["provider_cost_micros"], FROM_THE_RESPONSE)
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)

    def test_a_reported_declaration_with_no_mapping_is_answered_as_undeclared(self):
        """`reported` alone does not say WHERE the figure comes from.

        A declaration with no mapping is one a tenant has started and not
        finished, and the missing half is precisely the half that would admit
        this field. It cannot be published until the mapping is declared —
        the blocker says so — so production never reads it at all (#605): the
        figure meets whatever a key nobody declared meets, compared here to
        that rather than to what it is today (#568 owns that path).
        """
        half = self.declare("acme.half", published=False)
        self.assertEqual(half.publication_blockers(), (REPORTED_COST_MAPPING,))

        against_the_draft = self.post("no-mapping", event_type="acme.half",
                                      provider_cost_micros=SUPPLIER)
        against_nothing = self.post("nobody", event_type="nobody.declared",
                                    provider_cost_micros=SUPPLIER)

        def outcome(response, key):
            body = response.json()
            if response.status_code == 200:
                return 200, {fact: body[fact] for fact in COSTING_FACTS}
            return (response.status_code, body["code"],
                    body["detail"].replace(repr(key), "<key>"))

        self.assertEqual(outcome(against_the_draft, "acme.half"),
                         outcome(against_nothing, "nobody.declared"))

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
        self.assertIn(SOURCE_KIND_PROVIDER_RESPONSE, detail)
        self.assertIn(NEITHER, detail)
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

    Every Event Type a case records against is declared, edited and
    published the way a tenant does it, through these routes, because the
    claim is about what the lifecycle a tenant drives leaves production
    reading. Two things are set up below the routes, and each says so: the
    Cost Rates (`rate`), whose own quantity declarations come from the shared
    rate fixture under an Event Type no case records against, and a retired
    Grouping Field (`retire`), which no route can produce.
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
                   {"value_type": MEASUREMENT_VALUE_TYPE_INTEGER,
                    "unit": UNIT_CALL,
                    "source_kind": SOURCE_KIND_CALLER_SUPPLIED})

    def withdraw_quantity(self, key, code):
        self.admin("delete", f"/{key}/measurements/{code}")

    def mapping(self, key, source_kind, currency="usd"):
        reads_the_response = source_kind == SOURCE_KIND_PROVIDER_RESPONSE
        self.admin("put", f"/{key}/reported-cost-mapping", {
            "source_kind": source_kind,
            "amount_representation": AMOUNT_REPRESENTATION_MICROS,
            "source_path": ["usage", "total_cost"] if reads_the_response else [],
            "currency": currency})

    def published_reported_with_no_mapping(self, key):
        """The matrix's fourth row, which no route can publish: `publish`
        refuses a `reported` declaration with no mapping (the blocker below),
        so the lifecycle never hands it to recording. The rule is asked of the
        published copy all the same, so the copy is written here as
        publication would have kept it — admission must not depend on the
        blocker having held."""
        self.declared(key, costing_method=COSTING_METHOD_REPORTED)
        draft = EventType.objects.get(tenant=self.tenant, key=key)
        self.assertEqual(draft.publication_blockers(), (REPORTED_COST_MAPPING,))
        EventType.objects.filter(pk=draft.pk).update(
            published_revision=1,
            published_declaration=draft._declaration_to_pin())

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

    def a_grouping_field(self):
        """An event-scoped Grouping Field with room for new values."""
        GroupingField.objects.create(
            tenant=self.tenant, key="model", slot="grouping_field_1",
            scope=GROUPING_FIELD_SCOPE_EVENT, max_cardinality=5)

    def retire(self, key):
        """A Grouping Field retired. Written to the row: no tenant route
        retires one."""
        GroupingField.objects.filter(tenant=self.tenant, key=key).update(
            retired_at=timezone.now())

    def admitted(self, outcome):
        self.assertTrue(outcome.accepted, outcome.body)
        return outcome.body

    def refused_the_figure(self, outcome, field):
        """A supplier-cost refusal (#324, #570) of `field`, which every one
        opens by saying what that field means. Returns the message."""
        self.assertFalse(outcome.accepted, outcome.body)
        self.assertEqual(outcome.body["code"], "validation_error")
        detail = outcome.body["detail"]
        self.assertTrue(detail.startswith(OPENS_WITH[field]), detail)
        return detail

    def refused_for_its_other_transport(self, outcome, field, *, admissible):
        """The declared source admits a figure — on the OTHER field, which
        the message names, with the source kind that admits it."""
        detail = self.refused_the_figure(outcome, field)
        self.assertIn(f"admissible only as {admissible}: send it there",
                      detail)
        (kind,) = [kind for kind, transport in ADMITTED_BY.items()
                   if transport == admissible]
        self.assertIn(f"'{kind}'", detail)
        self.assertNotIn(NEITHER, detail)

    def refused_with_nothing_admissible(self, outcome, field):
        """No published declaration admits either transport, so the message
        says neither is, which declarations would, and the field accepted on
        any event."""
        detail = self.refused_the_figure(outcome, field)
        self.assertIn(NEITHER, detail)
        self.assertIn(f"'{SOURCE_KIND_CALLER_SUPPLIED}' (for {CALLER_FIELD})",
                      detail)
        self.assertIn(
            f"'{SOURCE_KIND_PROVIDER_RESPONSE}' (for {RESPONSE_FIELD})", detail)
        self.assertIn("claimed_provider_cost_micros", detail)

    def refused_as_both(self, outcome, *, admissible):
        """Both transports on one event: refused whatever is declared, saying
        nothing is summed or chosen, and naming the one field that would be
        admitted alone — or that neither would."""
        self.assertFalse(outcome.accepted, outcome.body)
        self.assertEqual(outcome.body["code"], "validation_error")
        detail = outcome.body["detail"]
        self.assertTrue(detail.startswith(BOTH_SENT), detail)
        self.assertIn(NOTHING_CHOSEN, detail)
        if admissible is None:
            self.assertIn(NEITHER, detail)
        else:
            self.assertIn(f"admits only {admissible}: send the figure there "
                          f"alone", detail)
            self.assertNotIn(NEITHER, detail)

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
    """The owner's example, in both directions (#605), for both transports
    (#570).

    A deployed integration was generated against the publication. A draft edit
    to the mapping's source kind must not start refusing the figure that
    integration sends — nor start admitting one it does not — on EITHER
    transport, until the edit is published. Then the admission flips, on both.
    """

    def test_a_draft_to_provider_response_leaves_the_figure_admitted(self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.mapping("acme.embed", SOURCE_KIND_PROVIDER_RESPONSE)

        ack = self.admitted(self.send("draft", event_type="acme.embed",
                                      provider_cost_micros=SUPPLIER))

        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)
        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.refused_for_its_other_transport(self.send(
            "draft-response", event_type="acme.embed",
            provider_response_cost_micros=FROM_THE_RESPONSE),
            RESPONSE_FIELD, admissible=CALLER_FIELD)

        self.publish("acme.embed")

        self.refused_for_its_other_transport(self.send(
            "published", event_type="acme.embed",
            provider_cost_micros=SUPPLIER),
            CALLER_FIELD, admissible=RESPONSE_FIELD)
        ack = self.admitted(self.send(
            "published-response", event_type="acme.embed",
            provider_response_cost_micros=FROM_THE_RESPONSE))
        self.assertEqual(ack["provider_cost_micros"], FROM_THE_RESPONSE)

    def test_a_draft_to_caller_supplied_leaves_the_figure_refused(self):
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        self.mapping("acme.read", SOURCE_KIND_CALLER_SUPPLIED)

        self.refused_for_its_other_transport(self.send(
            "draft", event_type="acme.read", provider_cost_micros=SUPPLIER),
            CALLER_FIELD, admissible=RESPONSE_FIELD)
        self.assertEqual(Posting.objects.count(), 0)
        ack = self.admitted(self.send(
            "draft-response", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE))
        self.assertEqual(ack["provider_cost_micros"], FROM_THE_RESPONSE)

        self.publish("acme.read")

        ack = self.admitted(self.send("published", event_type="acme.read",
                                      provider_cost_micros=SUPPLIER))
        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)
        self.refused_for_its_other_transport(self.send(
            "published-response", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE),
            RESPONSE_FIELD, admissible=CALLER_FIELD)

    def test_a_withdrawn_mapping_in_draft_leaves_the_figure_admitted(self):
        """The edit that cannot even be published: a `reported` declaration
        with no mapping is blocked. Production keeps the publication it has."""
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.withdraw_mapping("acme.embed")

        ack = self.admitted(self.send("withdrawn", event_type="acme.embed",
                                      provider_cost_micros=SUPPLIER))

        self.assertEqual(ack["provider_cost_micros"], SUPPLIER)

    def test_a_withdrawn_response_mapping_in_draft_leaves_its_figure_admitted(
            self):
        """The same, for the transport the response mapping admits."""
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        self.withdraw_mapping("acme.read")

        ack = self.admitted(self.send(
            "withdrawn", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE))

        self.assertEqual(ack["provider_cost_micros"], FROM_THE_RESPONSE)


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
        self.refused_with_nothing_admissible(self.send(
            "draft-figure", event_type="acme.calc",
            provider_cost_micros=SUPPLIER), CALLER_FIELD)

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

    Four drafts, one for each way a leaked draft would show: a `reported` one
    admitting a caller-supplied figure, another admitting a figure read off
    the provider's response (#570), a `calculated` one whose declared names
    would hold the unknown one, and one declaring nothing, which would carry no
    cost. For every body at least one of them, had it leaked, would answer
    differently from the undeclared path.
    """

    BODIES = {
        "quantities": {"measurements": {"calls": 3}},
        "a name nobody declared": {"measurements": {"calls": 3,
                                                    "mystery": 2}},
        "the supplier's own figure": {"provider_cost_micros": SUPPLIER},
        "a figure read off the response": {
            "provider_response_cost_micros": FROM_THE_RESPONSE},
    }

    DRAFTS = {
        "reported": {"costing_method": COSTING_METHOD_REPORTED,
                     "quantities": ("calls",),
                     "source_kind": SOURCE_KIND_CALLER_SUPPLIED},
        "response": {
            "costing_method": COSTING_METHOD_REPORTED,
            "quantities": ("calls",),
            "source_kind": SOURCE_KIND_PROVIDER_RESPONSE},
        "calculated": {"costing_method": COSTING_METHOD_CALCULATED,
                       "quantities": ("calls",)},
        "nothing": {"costing_method": COSTING_METHOD_CALCULATED},
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

        No tenant route retires a field, so `retire` writes `retired_at`
        directly; the replay carries a value the retired field would refuse,
        which only an admission that ran would notice.
        """
        self.a_grouping_field()
        original = self.admitted(self.send(
            "grouped", **declared_grouping_values({"model": "gpt-4"})))
        self.retire("model")

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
        admit records nothing and spends no grouping value — on either
        transport, and for each kind of refusal."""
        self.a_grouping_field()
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        grouped = declared_grouping_values({"model": "gpt-4"})

        self.refused_with_nothing_admissible(self.send(
            "new", event_type="nobody.declared",
            provider_response_cost_micros=FROM_THE_RESPONSE, **grouped),
            RESPONSE_FIELD)
        self.refused_for_its_other_transport(self.send(
            "other", event_type="acme.embed",
            provider_response_cost_micros=FROM_THE_RESPONSE, **grouped),
            RESPONSE_FIELD, admissible=CALLER_FIELD)
        self.refused_as_both(self.send(
            "both", event_type="acme.embed", provider_cost_micros=SUPPLIER,
            provider_response_cost_micros=FROM_THE_RESPONSE, **grouped),
            admissible=CALLER_FIELD)
        self.refused_with_nothing_admissible(self.send(
            "old", event_type="nobody.declared", provider_cost_micros=SUPPLIER,
            **grouped), CALLER_FIELD)

        self.assertEqual(Posting.objects.count(), 0)
        self.assertEqual(GroupingFieldValue.objects.count(), 0)

    def test_a_figure_read_off_the_response_replays_what_was_recorded(self):
        """The new transport joins the existing policy and adds none (#570):
        one posting, then the original acknowledgement for the same body, for
        a different figure (no body is compared), and after a publication
        that would now refuse the field — a replay never meets the matrix."""
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        original = self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE))
        self.assertEqual(original["provider_cost_micros"], FROM_THE_RESPONSE)
        self.assertEqual(Posting.objects.count(), 1)

        self.replays(original, self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE)))
        self.replays(original, self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE + 1)))

        self.mapping("acme.read", SOURCE_KIND_CALLER_SUPPLIED)
        self.publish("acme.read")
        self.refused_for_its_other_transport(self.send(
            "new-after", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE),
            RESPONSE_FIELD, admissible=CALLER_FIELD)

        self.replays(original, self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE)))


class AReplayAnswersWhatWasRecordedOnTheSingleRouteTest(
        _AReplayAnswersWhatWasRecorded, _OnTheSingleRoute):
    pass


class AReplayAnswersWhatWasRecordedOnTheBatchRouteTest(
        _AReplayAnswersWhatWasRecorded, _OnTheBatchRoute):
    pass


# ---------------------------------------------------------------------------
# #570 — a figure read off the provider's response has its own transport
# ---------------------------------------------------------------------------

class _TheAdmissionMatrix:
    """The owner's matrix (#570, comment `6040966104`), cell by cell, read off
    the PUBLISHED declaration (#605): each row is published through the
    tenant's routes, and each case sends one transport, the other, then both.

    An admitted figure is the supplier cost; a refused one says which field IS
    admissible for the declared source, or that none is; both on one event are
    refused whatever is declared.
    """

    def row(self, key, *, admits, figure_reaches=None):
        """Every cell of one row, against the Event Type `key`."""
        for field, figure in ((CALLER_FIELD, SUPPLIER),
                              (RESPONSE_FIELD, FROM_THE_RESPONSE)):
            outcome = self.send(f"{key}-{field}", event_type=key,
                                **{field: figure})
            if field == admits:
                ack = self.admitted(outcome)
                self.assertEqual(ack["provider_cost_micros"], figure)
                self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
            elif admits is None:
                self.refused_with_nothing_admissible(outcome, field)
            else:
                self.refused_for_its_other_transport(outcome, field,
                                                     admissible=admits)
        self.refused_as_both(self.send(
            f"{key}-both", event_type=key, provider_cost_micros=SUPPLIER,
            provider_response_cost_micros=FROM_THE_RESPONSE),
            admissible=admits)
        self.assertEqual(Posting.objects.count(), 0 if admits is None else 1)

    def test_reported_and_caller_supplied_admits_only_provider_cost_micros(
            self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.row("acme.embed", admits=CALLER_FIELD)

    def test_reported_and_provider_response_admits_only_its_own_field(self):
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        self.row("acme.read", admits=RESPONSE_FIELD)

    def test_calculated_admits_neither(self):
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED)
        self.row("acme.calc", admits=None)

    def test_calculated_with_a_response_mapping_still_admits_neither(self):
        """The METHOD decides first: a mapping beneath a calculated Event Type
        names where a figure would come from, and the tenant declared that UBB
        works the cost out from rates instead."""
        self.published("acme.calc", costing_method=COSTING_METHOD_CALCULATED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)
        self.row("acme.calc", admits=None)

    def test_no_declaration_at_all_admits_neither(self):
        self.row("nobody.declared", admits=None)

    def test_reported_with_no_mapping_admits_neither(self):
        self.published_reported_with_no_mapping("acme.half")
        self.row("acme.half", admits=None)

    def test_an_event_naming_no_event_type_admits_neither(self):
        """The recording request's key is optional; with none there is no
        declaration to read, and the message says so rather than naming one."""
        for field, figure in ((CALLER_FIELD, SUPPLIER),
                              (RESPONSE_FIELD, FROM_THE_RESPONSE)):
            detail = self.refused_the_figure(
                self.send(f"unnamed-{field}", **{field: figure}), field)
            self.assertIn(NEITHER, detail)
            self.assertIn("names no Event Type", detail)
        self.refused_as_both(self.send(
            "unnamed-both", provider_cost_micros=SUPPLIER,
            provider_response_cost_micros=FROM_THE_RESPONSE), admissible=None)
        self.assertEqual(Posting.objects.count(), 0)


class TheAdmissionMatrixOnTheSingleRouteTest(_TheAdmissionMatrix,
                                             _OnTheSingleRoute):
    pass


class TheAdmissionMatrixOnTheBatchRouteTest(_TheAdmissionMatrix,
                                            _OnTheBatchRoute):
    pass


def _every_key(value):
    """Every key of a JSON body, at any depth."""
    if isinstance(value, dict):
        for key, inner in value.items():
            yield key
            yield from _every_key(inner)
    elif isinstance(value, list):
        for inner in value:
            yield from _every_key(inner)


class _AFigureReadOffTheResponseIsTheSupplierCost:
    """What an admitted `provider_response_cost_micros` becomes (#570): the
    posting's one supplier-cost column, costed exactly as a caller-supplied
    figure is — the spine's "a figure that arrived" branch — and read back as
    `provider_cost_micros`. It is a transport and never echoed under its own
    name, and it never touches the caller's claim."""

    def test_it_is_the_postings_supplier_cost_and_read_back_as_one(self):
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        ack = self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=FROM_THE_RESPONSE))

        self.assertEqual((ack["costing_status"], ack["unresolved_reason"],
                          ack["provider_cost_micros"]),
                         (COSTING_STATUS_KNOWN, None, FROM_THE_RESPONSE))
        posting = Posting.objects.get(id=ack["event_id"])
        self.assertEqual(posting.provider_cost_micros, FROM_THE_RESPONSE)
        self.assertIsNone(posting.claimed_provider_cost_micros,
                          "the figure was taken for the caller's claim")
        self.assertIsNone(ack["claimed_provider_cost_micros"])
        receipt = getattr(posting, Posting.RECEIPT_COLUMN)
        self.assertEqual(receipt["costing"]["method"],
                         COSTING_METHOD_REPORTED)
        detail = self.detail(ack["event_id"])
        self.assertEqual(detail["provider_cost_micros"], FROM_THE_RESPONSE)
        for body in (ack, detail):
            self.assertNotIn(RESPONSE_FIELD, set(_every_key(body)),
                             "the transport was echoed as a second cost fact")

    def test_it_is_costed_exactly_as_a_caller_supplied_figure_is(self):
        """One path, not two: the same number on each transport, each under
        the declaration that admits it, reaches the same conclusions."""
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        supplied = self.admitted(self.send(
            "supplied", event_type="acme.embed", provider_cost_micros=SUPPLIER))
        read = self.admitted(self.send(
            "read", event_type="acme.read",
            provider_response_cost_micros=SUPPLIER))

        self.assertEqual({fact: read[fact] for fact in COSTING_FACTS},
                         {fact: supplied[fact] for fact in COSTING_FACTS})
        stored = {key: {column: getattr(posting, column)
                        for column in ECONOMIC_COLUMNS}
                  for key, posting in (
                      ("supplied", Posting.objects.get(id=supplied["event_id"])),
                      ("read", Posting.objects.get(id=read["event_id"])))}
        self.assertEqual(stored["read"], stored["supplied"])

    def test_without_it_the_reported_cost_is_still_missing(self):
        """Nothing is made up: a `provider_response` event that carries no
        figure is unresolved, as it was before the transport existed."""
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        ack = self.admitted(self.send("none", event_type="acme.read"))

        self.assertEqual((ack["costing_status"], ack["unresolved_reason"]),
                         (COSTING_STATUS_UNRESOLVED,
                          UNRESOLVED_REASON_REPORTED_COST_MISSING))
        self.assertIsNone(ack["provider_cost_micros"])
        self.assertIsNone(
            Posting.objects.get(id=ack["event_id"]).provider_cost_micros)


class AFigureReadOffTheResponseOnTheSingleRouteTest(
        _AFigureReadOffTheResponseIsTheSupplierCost, _OnTheSingleRoute):
    pass


class AFigureReadOffTheResponseOnTheBatchRouteTest(
        _AFigureReadOffTheResponseIsTheSupplierCost, _OnTheBatchRoute):
    pass


class _TheCurrencyRuleIsTheSharedOne:
    """The new transport takes the event-currency path the caller-supplied
    one takes and no other (#570 ruling 5): the event's `currency` must match
    the tenant's, with no FX and no second check of its own. So each currency
    is sent on both transports, each under the declaration that admits it,
    and the two outcomes are compared to EACH OTHER — including for a tenant
    whose currency is not USD, where a check of the new field's own would
    show."""

    CURRENCIES = (None, "usd", "USD", "eur", "EUR")

    def comparable(self, outcome):
        if not outcome.accepted:
            return False, outcome.body["code"], outcome.body["detail"]
        return True, {fact: outcome.body[fact] for fact in COSTING_FACTS}

    def outcomes(self, tenant_currency):
        self.tenant.default_currency = tenant_currency
        self.tenant.save(update_fields=["default_currency"])
        self.declared("acme.embed", costing_method=COSTING_METHOD_REPORTED)
        self.mapping("acme.embed", SOURCE_KIND_CALLER_SUPPLIED,
                     currency=tenant_currency)
        self.publish("acme.embed")
        self.declared("acme.read", costing_method=COSTING_METHOD_REPORTED)
        self.mapping("acme.read", SOURCE_KIND_PROVIDER_RESPONSE,
                     currency=tenant_currency)
        self.publish("acme.read")
        answers = {}
        for case, currency in enumerate(self.CURRENCIES):
            sent = {} if currency is None else {"currency": currency}
            supplied = self.send(f"supplied-{case}", event_type="acme.embed",
                                 provider_cost_micros=SUPPLIER, **sent)
            read = self.send(f"read-{case}", event_type="acme.read",
                             provider_response_cost_micros=SUPPLIER, **sent)
            with self.subTest(tenant=tenant_currency, currency=currency):
                self.assertEqual(self.comparable(read),
                                 self.comparable(supplied))
            answers[currency] = read
        return answers

    def test_a_usd_tenant(self):
        answers = self.outcomes("usd")

        self.assertTrue(answers[None].accepted)
        self.assertTrue(answers["USD"].accepted)
        refused = answers["eur"]
        self.assertFalse(refused.accepted)
        self.assertTrue(refused.body["detail"].startswith(
            "currency mismatch: event currency 'eur' does not match tenant "
            "currency 'usd'"), refused.body["detail"])

    def test_a_tenant_whose_currency_is_not_usd(self):
        answers = self.outcomes("eur")

        self.assertTrue(answers["eur"].accepted, answers["eur"].body)
        self.assertTrue(answers["EUR"].accepted)
        self.assertFalse(answers["usd"].accepted)


class TheCurrencyRuleOnTheSingleRouteTest(_TheCurrencyRuleIsTheSharedOne,
                                          _OnTheSingleRoute):
    pass


class TheCurrencyRuleOnTheBatchRouteTest(_TheCurrencyRuleIsTheSharedOne,
                                         _OnTheBatchRoute):
    pass


class TheBatchRefusesOneTransportAndRecordsItsSiblingsTest(_PublicationCase):
    """Per ITEM (#570 ruling 1): one batch, each transport admitted where its
    mapping is published and refused where it is not, both on one item
    refused — and every admitted sibling recorded."""

    def test_each_item_answers_for_itself(self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        def item(correlation, key, **figures):
            return usage_payload(self.customer, correlation, event_type=key,
                                 **figures)

        response = self.post_batch(
            item("wrong", "acme.embed",
                 provider_response_cost_micros=FROM_THE_RESPONSE),
            item("read", "acme.read",
                 provider_response_cost_micros=FROM_THE_RESPONSE),
            item("both", "acme.read", provider_cost_micros=SUPPLIER,
                 provider_response_cost_micros=FROM_THE_RESPONSE),
            item("supplied", "acme.embed", provider_cost_micros=SUPPLIER))

        self.assertEqual(response.status_code, 200, response.content)
        body = response.json()
        self.assertEqual((body["accepted"], body["rejected"]), (2, 2))
        wrong, read, both, supplied = body["results"]
        self.refused_for_its_other_transport(
            Outcome(False, wrong), RESPONSE_FIELD, admissible=CALLER_FIELD)
        self.refused_as_both(Outcome(False, both), admissible=RESPONSE_FIELD)
        self.assertEqual((read["accepted"], read["provider_cost_micros"]),
                         (True, FROM_THE_RESPONSE))
        self.assertEqual((supplied["accepted"],
                          supplied["provider_cost_micros"]), (True, SUPPLIER))
        self.assertEqual(
            sorted(Posting.objects.values_list("provider_cost_micros",
                                               flat=True)),
            sorted([FROM_THE_RESPONSE, SUPPLIER]))


class AVerificationRecordTakesTheSameTransportTest(_PublicationCase):
    """Verify's recording input carries "the same fields, with the same
    rules, as on a recording" (`IntegrationBlueprintVerificationRecordIn`), so
    it gains the transport with the recording request (#570).

    It cannot be driven through Verify's route before #583: a Blueprint
    holding a `provider_response` mapping is blocked, and Verify refuses one
    that is not complete. So the record is made as the run makes it — from
    the configuration's own account of the published Event Type
    (`_event_type_content`), through `_recording`, into the recording route's
    `record` — and asked the matrix's cells directly.
    """

    def verify_record(self, key, position, **figures):
        claim = IntegrationBlueprintVerificationRecordIn(event_type=key,
                                                         **figures)
        declared = _event_type_content({
            "declaration": last_published_declaration(tenant=self.tenant,
                                                      key=key),
            "provider_key": None})
        recording = verification._recording(self.customer, declared, claim,
                                            None, position)
        try:
            return Outcome(True, metering_endpoints.record(self.tenant,
                                                           recording))
        except Problem as refusal:
            return Outcome(False, {"code": refusal.code,
                                   "detail": refusal.detail})

    def test_the_record_admits_each_transport_where_its_mapping_is_published(
            self):
        self.published("acme.embed", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_CALLER_SUPPLIED)
        self.published("acme.read", costing_method=COSTING_METHOD_REPORTED,
                       source_kind=SOURCE_KIND_PROVIDER_RESPONSE)

        read = self.admitted(self.verify_record(
            "acme.read", 0, provider_response_cost_micros=FROM_THE_RESPONSE))
        self.refused_for_its_other_transport(
            self.verify_record("acme.read", 1, provider_cost_micros=SUPPLIER),
            CALLER_FIELD, admissible=RESPONSE_FIELD)
        self.refused_for_its_other_transport(
            self.verify_record("acme.embed", 2,
                               provider_response_cost_micros=FROM_THE_RESPONSE),
            RESPONSE_FIELD, admissible=CALLER_FIELD)
        self.refused_as_both(self.verify_record(
            "acme.read", 3, provider_cost_micros=SUPPLIER,
            provider_response_cost_micros=FROM_THE_RESPONSE),
            admissible=RESPONSE_FIELD)

        self.assertEqual(read["provider_cost_micros"], FROM_THE_RESPONSE)
        self.assertEqual(read["costing_status"], COSTING_STATUS_KNOWN)

    def test_the_input_carries_the_field_with_the_recording_requests_bounds(
            self):
        verify = IntegrationBlueprintVerificationRecordIn.model_fields
        record = RecordUsageRequest.model_fields
        for name in (CALLER_FIELD, RESPONSE_FIELD):
            with self.subTest(field=name):
                self.assertEqual(verify[name].metadata, record[name].metadata)
                self.assertEqual(verify[name].description,
                                 record[name].description)


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

    def test_the_figure_read_off_the_response_carries_the_same_bound(self):
        """#570: the same amount on another transport, so the same bound —
        and it is optional, like the field beside it."""
        request = self.schemas["RecordUsageRequest"]
        self.assertEqual(_bounds(request["properties"][RESPONSE_FIELD]),
                         _bounds(request["properties"][CALLER_FIELD]))
        self.assertEqual(_bounds(request["properties"][RESPONSE_FIELD]),
                         (0, 999_999_999_999))
        self.assertNotIn(RESPONSE_FIELD, request.get("required", []))

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


#: What each published meaning must say (#570 ruling 2), held here rather
#: than read off the constants that publish them, so a reverted wording is a
#: red test rather than a constant agreeing with itself.
SAYS_SUPPLIED_BY_THE_CALLER = (
    "supplied directly by the caller",
    "source_kind is `caller_supplied`")
SAYS_OBTAINED_FROM_THE_RESPONSE = (
    "as the caller obtained it from the provider's response",
    "source_kind is `provider_response`",
    "UBB cannot verify how the figure was obtained",
    "not echoed under its own name")
SAYS_RESOLVED = (
    "The supplier cost (COGS) UBB resolved for this event",
    "whichever valid source supplied it",
    "`provider_cost_micros` or `provider_response_cost_micros`")
SAYS_THE_CLAIM_IS_NEVER_COGS = (
    "never COGS",
    "The supplier cost UBB treats as COGS is the one it resolves")
#: The sentence #570 falsified: two request fields now carry a supplier cost
#: UBB treats as cost, so neither is "the only one".
FALSIFIED = "the only one UBB treats as cost"

#: The schemas a recording publishes its supplier cost back on, beside the
#: caller's claim.
RECORDING_RESPONSES = ("RecordUsageResponse", "UsageEventOut",
                       "UsageEventDetailOut")
#: The two request schemas that take a supplier cost.
RECORDING_REQUESTS = ("RecordUsageRequest",
                      "IntegrationBlueprintVerificationRecordIn")


class EachSupplierCostFieldPublishesItsOwnMeaningTest(SimpleTestCase):
    """The three meanings (#570 ruling 2), each the field's PUBLISHED
    description, walked off the committed contract."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.spec = json.loads(SPEC_PATH.read_text(encoding="utf-8"))
        cls.schemas = cls.spec["components"]["schemas"]

    def said(self, schema, field):
        return self.schemas[schema]["properties"][field].get("description",
                                                             "")

    def says(self, schema, field, phrases):
        description = self.said(schema, field)
        for phrase in phrases:
            self.assertIn(phrase, description, f"{schema}.{field}")

    def test_each_request_field_says_where_its_figure_comes_from(self):
        for schema in RECORDING_REQUESTS:
            with self.subTest(schema=schema):
                self.says(schema, CALLER_FIELD, SAYS_SUPPLIED_BY_THE_CALLER)
                self.says(schema, RESPONSE_FIELD,
                          SAYS_OBTAINED_FROM_THE_RESPONSE)
        # One wording per field across both requests.
        for field in (CALLER_FIELD, RESPONSE_FIELD):
            self.assertEqual(*(self.said(schema, field)
                               for schema in RECORDING_REQUESTS))

    def test_each_response_publishes_the_one_resolved_amount(self):
        for schema in RECORDING_RESPONSES:
            with self.subTest(schema=schema):
                self.says(schema, CALLER_FIELD, SAYS_RESOLVED)
                self.assertEqual(self.said(schema, CALLER_FIELD),
                                 self.said(RECORDING_RESPONSES[0],
                                           CALLER_FIELD))

    def test_the_claims_meaning_is_true_on_the_request_and_every_response(
            self):
        for schema in ("RecordUsageRequest", *RECORDING_RESPONSES):
            with self.subTest(schema=schema):
                self.says(schema, "claimed_provider_cost_micros",
                          SAYS_THE_CLAIM_IS_NEVER_COGS)
        self.assertNotIn(FALSIFIED, json.dumps(self.spec))

    def test_no_response_carries_the_transport(self):
        """A transport, not a second cost fact: no response model gains it.
        Held twice — as the exact set of schemas naming it, and by walking
        every schema any operation answers with, refs followed."""
        carrying = {name for name, schema in self.schemas.items()
                    if RESPONSE_FIELD in schema.get("properties", {})}
        self.assertEqual(carrying, set(RECORDING_REQUESTS))

        answered = set()
        for operations in self.spec["paths"].values():
            for operation in operations.values():
                for response in operation.get("responses", {}).values():
                    answered |= _schemas_reached(response, self.schemas)
        self.assertGreater(len(answered), 50, "the walk reached nothing")
        self.assertIn("RecordUsageResponse", answered)
        self.assertEqual(
            {name for name in answered
             if RESPONSE_FIELD in self.schemas[name].get("properties", {})},
            set())


def _schemas_reached(node, schemas, seen=None):
    """Every component schema `node` reaches through `$ref`, transitively."""
    seen = set() if seen is None else seen
    if isinstance(node, dict):
        ref = node.get("$ref", "")
        if ref.startswith("#/components/schemas/"):
            name = ref.rsplit("/", 1)[-1]
            if name not in seen:
                seen.add(name)
                _schemas_reached(schemas[name], schemas, seen)
        for value in node.values():
            _schemas_reached(value, schemas, seen)
    elif isinstance(node, list):
        for value in node:
            _schemas_reached(value, schemas, seen)
    return seen


def _bounds(node):
    """The (minimum, maximum) an integer-or-null property admits.

    Django Ninja renders an optional bounded integer as a two-member `anyOf`,
    so the bound sits in the integer branch rather than on the node.
    """
    for member in node.get("anyOf", (node,)):
        if member.get("type") == "integer":
            return member.get("minimum"), member.get("maximum")
    raise AssertionError(f"no integer branch to bound: {json.dumps(node)}")
