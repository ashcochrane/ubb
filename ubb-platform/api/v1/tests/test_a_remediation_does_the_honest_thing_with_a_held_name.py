"""What a remediation does with a held name (#473, ruled 2026-10-22).

A name UBB could not place is held beside the event it arrived on, and the
tenant decides what it meant: map it to a declaration that exists, register the
name they have just declared, or dismiss it as non-economic. Four questions
followed from that, and each is a row of #473 with a test of its own here:

* **Row 1 — the consumer of the `Replay`.** A mapped or registered name hands
  its replay on, and the event it arrived on is re-costed and re-priced from
  its own moment, with every answer the tenant has given about that event
  applied — including a held quantity re-keyed to the declared name it was
  mapped to, which only the replay carries.

Every report here is recorded through the public route; the remediations are
the kernel's own services, which is where a tenant's decision is taken today.
"""
from django.db import transaction

from api.v1.tests._helpers import DeclaringTenantCase, OnTheSingleRoute
from apps.metering.pricing.services.resolution_run import (
    AnswerNamesOneQuantityTwice, RunSelector, execute)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.platform.event_types.models import Measurement
from apps.platform.event_types.quarantine import map_to_a_declaration
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    MEASUREMENT_VALUE_TYPE_INTEGER,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_CALL,
    UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED,
)

#: The Event Type every report names, and the three quantities it declares.
CHAT = "acme.chat"
INPUT, OUTPUT, CACHED = "input_tokens", "output_tokens", "cached_tokens"
#: The two misspellings that arrive, each of a name the declaration carries.
OUTPUT_MISSPELT, CACHED_MISSPELT = "outptu_tokens", "cachd_tokens"
#: A cost and a price per token for each declared quantity — distinct powers of
#: ten, so a total names the lines behind it.
COSTS = {INPUT: 1, OUTPUT: 10, CACHED: 100}
PRICES = {INPUT: 1_000, OUTPUT: 10_000, CACHED: 100_000}


class _ATenantWithOneDeclaration(OnTheSingleRoute, DeclaringTenantCase):

    def setUp(self):
        super().setUp()
        self.chat = self.declared(CHAT, quantities=(INPUT, OUTPUT, CACHED))
        for code in COSTS:
            cost_rate_in_default_book(
                self.tenant, measurement_key=code, unit_quantity=1,
                rate_per_unit_micros=COSTS[code])
            rate_in_default_book(
                self.tenant, measurement_key=code, unit_quantity=1,
                rate_per_unit_micros=PRICES[code])

    def a_report(self, **measurements):
        return self.posting(self.send("k1", event_type=CHAT,
                                      measurements=measurements))

    def declared_as(self, code):
        return Measurement.objects.get(event_type=self.chat, code=code)

    def held_as(self, name):
        (held,) = [row for row in self.held() if row.measurement_key == name]
        return held


class TheReplayReachesTheEventTest(_ATenantWithOneDeclaration):
    """Row 1. A mapped name means nothing to a re-costing that reads the
    posting's own bag, because the bag holds the misspelling; the re-keyed
    name is what the replay carries, and this is where it lands."""

    def test_a_mapped_quantity_is_costed_under_the_name_it_was_mapped_to(self):
        posting = self.a_report(**{INPUT: "10", OUTPUT_MISSPELT: "5"})
        self.assertEqual(posting.unresolved_reason,
                         UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED)

        map_to_a_declaration(self.held_as(OUTPUT_MISSPELT),
                             self.declared_as(OUTPUT))

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 5 * COSTS[OUTPUT])
        self.assertEqual(posting.pricing_status, PRICING_STATUS_KNOWN)
        self.assertEqual(posting.billed_cost_micros,
                         10 * PRICES[INPUT] + 5 * PRICES[OUTPUT])
        # The record says what the call SAID, and is read, never rewritten:
        # the measurement keeps the spelling that arrived.
        self.assertEqual(posting.measurements,
                         {INPUT: "10", OUTPUT_MISSPELT: "5"})

    def test_an_event_settles_only_once_every_name_on_it_is_answered(self):
        """Two names held on one event. The first answer re-costs nothing —
        the other name is still the tenant's to decide — and is not lost:
        the second answer's replay applies both."""
        posting = self.a_report(**{INPUT: "10", OUTPUT_MISSPELT: "5",
                                   CACHED_MISSPELT: "2"})

        map_to_a_declaration(self.held_as(OUTPUT_MISSPELT),
                             self.declared_as(OUTPUT))
        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_UNRESOLVED)
        self.assertEqual(posting.pricing_status, PRICING_STATUS_UNKNOWN)

        map_to_a_declaration(self.held_as(CACHED_MISSPELT),
                             self.declared_as(CACHED))
        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 5 * COSTS[OUTPUT]
                         + 2 * COSTS[CACHED])
        self.assertEqual(posting.billed_cost_micros,
                         10 * PRICES[INPUT] + 5 * PRICES[OUTPUT]
                         + 2 * PRICES[CACHED])

    def test_a_run_applies_the_answer_once_the_declaration_is_published(self):
        """A name mapped to a quantity the tenant has declared only in a DRAFT
        cannot settle yet — production reads the publication (#605) — so the
        replay completes nothing. The answer is not lost: once the draft is
        published, a Resolution Run re-costs the event with the same re-keyed
        bag, from the same moment. A run that re-resolved the spelling would
        hold it again forever."""
        reasoning, misspelt = "reasoning_tokens", "reasonng_tokens"
        cost_rate_in_default_book(self.tenant, measurement_key=reasoning,
                                  unit_quantity=1, rate_per_unit_micros=1_000)
        posting = self.a_report(**{INPUT: "10", misspelt: "4"})
        self.admin("put", f"/event-types/{CHAT}/measurements/{reasoning}", {
            "value_type": MEASUREMENT_VALUE_TYPE_INTEGER, "unit": UNIT_CALL,
            "source_kind": SOURCE_KIND_CALLER_SUPPLIED})

        map_to_a_declaration(self.held_as(misspelt),
                             self.declared_as(reasoning))
        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_UNRESOLVED)

        self.admin("post", f"/event-types/{CHAT}/publish")
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 4 * 1_000)

    def test_a_mapping_onto_a_name_the_event_carries_is_refused_whole(self):
        """The event already reported input tokens; mapping a misspelling
        onto that name would report them twice, and nothing may add the two
        or pick one. The replay refuses, and the decision goes with it — the
        name is still held, and the event is as it was."""
        posting = self.a_report(**{INPUT: "10", "inptu_tokens": "3"})

        # No transaction of the test's own around this: what takes the
        # decision back is the remediation's, and a wrapper here would do it
        # whether or not that one existed.
        with self.assertRaises(AnswerNamesOneQuantityTwice):
            map_to_a_declaration(self.held_as("inptu_tokens"),
                                 self.declared_as(INPUT))

        self.assertTrue(self.held_as("inptu_tokens").is_unresolved)
        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_UNRESOLVED)
