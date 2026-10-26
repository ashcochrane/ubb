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

"Declared" is the production sense (#605): a last publication exists — and
the supplier is the one that publication names (the consultant's review of
#618). A rename, a re-pointing or a retirement since changes nothing recording
admits or costs until the Event Type is published again
(`test_a_supplier_edit_takes_effect_only_when_published`).
"""
import json
from pathlib import Path

from django.db import connection, transaction
from django.test import SimpleTestCase
from django.test.utils import CaptureQueriesContext

from api.v1.metering_endpoints import PROVIDER_CONFLICTS_WITH_EVENT_TYPE
from api.v1.schemas import RecordUsageRequest
from api.v1.tests._helpers import (
    DeclaringTenantCase, OnTheBatchRoute, OnTheSingleRoute)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.metering.usage.models import Posting
from apps.platform.event_types.models import EventType
from apps.metering.pricing.services.resolution_run import (
    RunSelector, TheEventNamedAnotherSupplier, execute)
from apps.platform.event_types.quarantine import (
    PeriodHoldsUnresolvedValues, map_to_a_declaration, refuse_a_silent_close)
from core.time_windows import month_bounds, utc_day_start
from core.problems import PROBLEMS, VERDICTS
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    DECLARATION_STATUS_PUBLISHED,
    UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED,
)

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

    def test_an_event_pays_one_read_of_its_publication(self):
        """#605's expectation, kept through #572. The edge reads the Event
        Type's publication once, and every question about it answers from
        that read — whose supplier the call is, whether a figure may arrive,
        the quantities' value types — and the costing is handed it rather
        than asking again, so a publish cannot land between an admission and
        the costing either. The supplier is in the publication, so the read
        joins nothing."""
        with CaptureQueriesContext(connection) as captured:
            self.send("k1", **self.a_call())

        reads = [query["sql"] for query in captured.captured_queries
                 if 'FROM "ubb_event_type"' in query["sql"]]
        self.assertEqual(len(reads), 1, reads)
        self.assertNotIn('"ubb_provider"', reads[0])

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

    def test_a_supplier_edit_takes_effect_only_when_published(self):
        """THE DECISIVE CASE (#605; the consultant's review of #618). The
        supplier governing an Event Type is the one its PUBLICATION names.
        Every legal live edit — the supplier renamed, the Event Type re-pointed
        at another, the published one retired — changes nothing recording
        admits or costs, until the Event Type is published again; then the
        published supplier governs."""
        self.admin("patch", f"/providers/{DECLARED}", {"key": "openai-eu"})
        self.admin("patch", f"/event-types/{CHAT}", {"provider_key": OTHER})
        self.admin("patch", "/providers/openai-eu", {"retired": True})

        omitted = self.send("k1", **self.a_call())
        named = self.send("k2", **self.a_call(provider=DECLARED))
        renamed_code, _ = self.refused("k3", **self.a_call(provider="openai-eu"))
        repointed_code, _ = self.refused("k4", **self.a_call(provider=OTHER))

        self.assert_costed_as(omitted, DECLARED)
        self.assert_costed_as(named, DECLARED)
        self.assertEqual(renamed_code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)
        self.assertEqual(repointed_code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)

        self.admin("post", f"/event-types/{CHAT}/publish")

        self.assert_costed_as(self.send("k5", **self.a_call()), OTHER)

    def test_an_event_with_no_published_event_type_keeps_what_it_sent(self):
        """Out of #572's reach, by its own scope: naming no Event Type (#567)
        or one with no publication (#568's hold)."""
        unnamed = self.send("k1", **self.a_call(event_type="", provider=OTHER))
        held = self.send("k2", **self.a_call(event_type="acme.nobody",
                                             provider=OTHER))

        self.assert_costed_as(unnamed, OTHER)
        self.assertEqual(self.posting(held).provider, OTHER)

    def test_a_retry_is_answered_before_the_supplier_is_asked(self):
        """Replay wins (#605): the Event Type PUBLISHED naming another
        supplier since — re-pointed and published, so a fresh call naming the
        first supplier is refused — cannot refuse a retry of a call already
        recorded."""
        first = self.send("k1", **self.a_call(provider=DECLARED))
        self.admin("patch", f"/event-types/{CHAT}", {"provider_key": OTHER})
        self.admin("post", f"/event-types/{CHAT}/publish")
        code, _ = self.refused("k2", **self.a_call(provider=DECLARED))
        self.assertEqual(code, PROVIDER_CONFLICTS_WITH_EVENT_TYPE)

        again = self.send("k1", **self.a_call(provider=DECLARED))

        self.assertEqual(again["event_id"], first["event_id"])

    def test_a_held_event_naming_no_supplier_replays_under_its_answers(self):
        """Recorded while nobody had said what it was, naming no supplier;
        once the tenant maps it to an Event Type, that Event Type's supplier
        is what it costs under — as an omitted provider is at the edge."""
        posting = self.posting(self.send(
            "k1", **self.a_call(event_type="acme.chat_v2")))

        (held,) = self.held()
        map_to_a_declaration(
            held, EventType.objects.get(tenant=self.tenant, key=CHAT))

        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 3 * COST[DECLARED])
        self.assertEqual(posting.billed_cost_micros, 3 * PRICE[DECLARED])

    def test_a_held_event_naming_another_supplier_is_not_answered_by_it(self):
        """The edge would have refused this call by name; a replay may not
        cost it under the declared supplier's rules instead — that is the
        substitution #572 forbids. The mapping is refused by name, and a
        publication at the key it arrived under, naming the declared
        supplier, leaves it held too: the name is still the tenant's to
        decide."""
        posting = self.posting(self.send(
            "k1", **self.a_call(event_type="acme.chat_v2", provider=OTHER)))
        recorded = (posting.costing_status, posting.provider_cost_micros,
                    posting.billed_cost_micros)

        (held,) = self.held()
        with self.assertRaises(TheEventNamedAnotherSupplier):
            map_to_a_declaration(
                held, EventType.objects.get(tenant=self.tenant, key=CHAT))
        self.declared("acme.chat_v2", quantities=(CALLS,),
                      provider_key=DECLARED)

        held.refresh_from_db()
        self.assertTrue(held.is_unresolved)
        posting.refresh_from_db()
        self.assertEqual((posting.costing_status, posting.provider_cost_micros,
                          posting.billed_cost_micros), recorded)

    def test_a_publication_lands_though_one_held_event_cannot_be_answered(
            self):
        """THE BOUNDARY (the consultant's review of #618). Two calls held
        under one key: one named another supplier, one named none. Publishing
        the key commits the declaration whole; the sibling is answered and
        costed after it; the refused one stays visibly held, still holding the
        close — a truthful refusal of that EVENT, never a reason the Event Type
        cannot be published. A Resolution Run, the retry, answers nothing
        twice and costs nothing around the held one."""
        held_key = "acme.chat_v2"
        refused = self.posting(self.send(
            "k1", **self.a_call(event_type=held_key, provider=OTHER)))
        sibling = self.posting(self.send(
            "k2", **self.a_call(event_type=held_key)))

        self.declared(held_key, quantities=(CALLS,), provider_key=DECLARED)

        self.assertEqual(EventType.objects.get(
            tenant=self.tenant, key=held_key).declaration_status,
            DECLARATION_STATUS_PUBLISHED)
        sibling.refresh_from_db()
        self.assertEqual(sibling.provider_cost_micros, 3 * COST[DECLARED])
        self.assertEqual(sibling.billed_cost_micros, 3 * PRICE[DECLARED])
        refused.refresh_from_db()
        self.assertEqual((refused.costing_status, refused.unresolved_reason),
                         (COSTING_STATUS_UNRESOLVED,
                          UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED))
        rows = {row.event_id: row for row in self.held()}
        self.assertTrue(rows[refused.id].is_unresolved)
        self.assertFalse(rows[sibling.id].is_unresolved)
        opens, closes = month_bounds(refused.effective_at)
        with self.assertRaises(PeriodHoldsUnresolvedValues):
            refuse_a_silent_close(tenant=self.tenant,
                                  opened_at=utc_day_start(opens),
                                  closes_at=utc_day_start(closes))

        before = [(row.pk, row.resolution) for row in self.held()]
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        self.assertEqual([(row.pk, row.resolution) for row in self.held()],
                         before)
        refused.refresh_from_db()
        self.assertIsNone(refused.provider_cost_micros)
        sibling.refresh_from_db()
        self.assertEqual(sibling.provider_cost_micros, 3 * COST[DECLARED])

    def test_a_held_event_whose_supplier_its_declaration_names_replays(self):
        """The control for the case above: published naming the supplier
        the call did name, the key is the answer, and the call is costed
        under that supplier's rules."""
        posting = self.posting(self.send(
            "k1", **self.a_call(event_type="acme.chat_v2", provider=OTHER)))

        self.declared("acme.chat_v2", quantities=(CALLS,), provider_key=OTHER)

        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 3 * COST[OTHER])
        self.assertEqual(posting.billed_cost_micros, 3 * PRICE[OTHER])
        (held,) = self.held()
        self.assertFalse(held.is_unresolved)


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
            self.assertIn("the supplier that publication names decides "
                          "whose call this is", description)
            self.assertIn("takes effect when the Event Type is published "
                          "again", description)
            self.assertIn("never trusted and never replaced", description)
