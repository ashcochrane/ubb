"""A published Event Type's own Provider decides what a call costs (#572).

Slice 2's spec, #193 §B3: *"Cost resolution keys on the Provider's identity"*,
and an Event Type names its Provider. Until this, recording selected Cost Rates
and price rules by the free-text `provider` the caller sent and never read the
Event Type's — so a call could be costed as one supplier's while its declaration
named another. The owner's ruling (#184, batch item 8):

* for a declared Event Type, its declared Provider is **authoritative**;
* an explicitly supplied **conflicting** provider is **refused** — never
  silently trusted, never silently replaced — with a named 422,
  `provider_conflicts_with_event_type`, in the error-code catalogue;
* a matching or omitted provider proceeds;
* the batch does the same, per item;
* events naming no Event Type, or one with no publication (#568's), are
  unchanged here.

"Declared" is the production sense (#605): a last publication exists. The
supplier itself is not pinned by publication, so its key is read as the
catalogue holds it now.
"""
import json
from pathlib import Path

from django.test import SimpleTestCase

from api.v1.metering_endpoints import PROVIDER_CONFLICTS_WITH_EVENT_TYPE
from api.v1.schemas import RecordUsageRequest
from api.v1.tests._helpers import (
    DeclaringTenantCase, OnTheBatchRoute, OnTheSingleRoute)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.metering.usage.models import Posting
from apps.platform.event_types.models import EventType
from apps.platform.event_types.quarantine import map_to_a_declaration
from core.problems import PROBLEMS, VERDICTS
from core.vocabulary import COSTING_STATUS_KNOWN

CHAT = "acme.chat"
CALLS = "calls"
#: The supplier the Event Type names, and another one the caller might.
DECLARED, OTHER = "openai", "anthropic"
#: What a call costs and sells for at each supplier — distinct, so a figure
#: names the supplier whose rules produced it.
COST = {DECLARED: 1_000, OTHER: 9_000}
PRICE = {DECLARED: 5_000, OTHER: 50_000}

SPEC = Path(__file__).resolve().parents[4] / "openapi" / "v1.json"


class _ATenantWithASupplier(DeclaringTenantCase):
    """Two suppliers' rules for one quantity, and an Event Type naming one."""

    def setUp(self):
        super().setUp()
        for supplier in (DECLARED, OTHER):
            self.admin("post", "/providers", {"key": supplier})
            cost_rate_in_default_book(
                self.tenant, provider=supplier, measurement_key=CALLS,
                unit_quantity=1, rate_per_unit_micros=COST[supplier])
            rate_in_default_book(
                self.tenant, provider=supplier, measurement_key=CALLS,
                unit_quantity=1, rate_per_unit_micros=PRICE[supplier])
        self.declared(CHAT, quantities=(CALLS,), provider_key=DECLARED)

    def a_call(self, **body):
        body.setdefault("event_type", CHAT)
        body.setdefault("measurements", {CALLS: "3"})
        return body

    def assert_costed_as(self, ack, supplier):
        posting = self.posting(ack)
        self.assertEqual(posting.provider, supplier)
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros, 3 * COST[supplier])
        self.assertEqual(posting.billed_cost_micros, 3 * PRICE[supplier])
        self.assertEqual(ack["provider_cost_micros"], 3 * COST[supplier])


class _TheDeclaredProviderDecides:

    def test_an_omitted_provider_records_and_costs_as_the_declared_one(self):
        ack = self.send("k1", **self.a_call())

        self.assert_costed_as(ack, DECLARED)

    def test_the_declared_provider_sent_explicitly_proceeds(self):
        ack = self.send("k1", **self.a_call(provider=DECLARED))

        self.assert_costed_as(ack, DECLARED)

    def test_a_different_provider_is_refused_by_name(self):
        code, detail = self.refused("k1", **self.a_call(provider=OTHER))

        self.assertEqual(code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)
        self.assertIn(repr(OTHER), detail)
        self.assertIn(repr(DECLARED), detail)
        self.assertFalse(Posting.objects.filter(tenant=self.tenant).exists())

    def test_an_event_type_naming_no_supplier_refuses_any(self):
        """No supplier is a statement — internal work — not a blank a caller
        may fill: a provider sent for it is refused, and none proceeds."""
        self.declared("acme.internal", quantities=(CALLS,))

        code, _ = self.refused("k1", **self.a_call(event_type="acme.internal",
                                                   provider=DECLARED))
        ack = self.send("k2", **self.a_call(event_type="acme.internal"))

        self.assertEqual(code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)
        self.assertEqual(self.posting(ack).provider, "")

    def test_a_renamed_supplier_is_known_by_its_new_key(self):
        """The supplier is not pinned by publication, so its key is read as
        the catalogue holds it now: the new key is recorded, and the old one
        is no longer the supplier this Event Type names."""
        self.admin("patch", f"/providers/{DECLARED}", {"key": "openai-eu"})

        ack = self.send("k1", **self.a_call())
        code, _ = self.refused("k2", **self.a_call(provider=DECLARED))

        self.assertEqual(self.posting(ack).provider, "openai-eu")
        self.assertEqual(code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)

    def test_an_event_with_no_published_event_type_keeps_what_it_sent(self):
        """Out of #572's reach, by its own scope: naming no Event Type (#567)
        or one with no publication (#568's hold)."""
        unnamed = self.send("k1", **self.a_call(event_type="", provider=OTHER))
        held = self.send("k2", **self.a_call(event_type="acme.nobody",
                                             provider=OTHER))

        self.assert_costed_as(unnamed, OTHER)
        self.assertEqual(self.posting(held).provider, OTHER)

    def test_a_retry_is_answered_before_the_supplier_is_asked(self):
        """Replay wins (#605): the Event Type naming another supplier since
        cannot refuse a retry of a call already recorded."""
        first = self.send("k1", **self.a_call(provider=DECLARED))
        self.admin("patch", f"/event-types/{CHAT}", {"provider_key": OTHER})

        again = self.send("k1", **self.a_call(provider=DECLARED))

        self.assertEqual(again["event_id"], first["event_id"])

    def test_a_held_event_type_replays_under_the_supplier_its_answer_names(self):
        """Recorded while nobody had said what it was, with the provider it
        sent; once the tenant maps it to an Event Type, that Event Type's
        supplier is authoritative for the replay as it is for a recording."""
        posting = self.posting(self.send(
            "k1", **self.a_call(event_type="acme.chat_v2", provider=OTHER)))

        (held,) = self.held()
        map_to_a_declaration(
            held, EventType.objects.get(tenant=self.tenant, key=CHAT))

        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 3 * COST[DECLARED])
        self.assertEqual(posting.billed_cost_micros, 3 * PRICE[DECLARED])


class TheDeclaredProviderDecidesOnTheSingleRouteTest(
        _TheDeclaredProviderDecides, OnTheSingleRoute, _ATenantWithASupplier):
    pass


class TheDeclaredProviderDecidesOnTheBatchRouteTest(
        _TheDeclaredProviderDecides, OnTheBatchRoute, _ATenantWithASupplier):
    pass


class TheRefusalIsNamedOnTheContractTest(SimpleTestCase):
    """The named code is in the catalogue the SDK's exceptions are generated
    from, for both routes, and the field says what it means where a generated
    client's user reads it — on the class, and in the committed spec, which
    the drift gate holds to the class."""

    def test_the_catalogue_registers_it_as_a_422_for_both_routes(self):
        self.assertEqual(PROBLEMS[PROVIDER_CONFLICTS_WITH_EVENT_TYPE]["status"],
                         422)
        self.assertIn(PROVIDER_CONFLICTS_WITH_EVENT_TYPE,
                      VERDICTS["ingest_rejections"])

    def test_the_provider_field_says_its_rule(self):
        published = json.loads(SPEC.read_text(encoding="utf-8"))[
            "components"]["schemas"]["RecordUsageRequest"]["properties"][
            "provider"]["description"]
        for description in (
                RecordUsageRequest.model_fields["provider"].description,
                published):
            self.assertIn(PROVIDER_CONFLICTS_WITH_EVENT_TYPE, description)
            self.assertIn("own provider decides", description)
            self.assertIn("never trusted and never replaced", description)
