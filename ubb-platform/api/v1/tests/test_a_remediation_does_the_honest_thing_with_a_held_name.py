"""What a remediation does with a held name (#473, ruled 2026-10-22).

A name UBB could not place is held beside the event it arrived on, and the
tenant decides what it meant: map it to a declaration that exists, register the
name they have just declared, or dismiss it as non-economic. Four questions
followed from that, and each is a row of #473 with a test of its own here:

* **Row 1 — the consumer of the `Replay`.** A mapped or registered name hands
  its replay on, and the event it arrived on is re-costed and re-priced from
  its own moment, with every answer the tenant has given about that event
  applied — including a held quantity re-keyed to the declared name it was
  mapped to, which the posting's own bag cannot say. A publication that
  declares a held name registers it by itself, and only a publication can
  answer one: production reads nothing else (#605).

The owner ruled the other three on 2026-10-22, adopting the close-out report's
recommendations:

* **Row 2 — dismissal does not re-cost.** A name the tenant says is not
  economic frees the period close, and the event keeps the cost and price it
  was recorded with: no replay, and no later run re-costs it — not without the
  name, and not with it once its key is published.
* **Row 3 — deletion is refused while held names depend on it.** An Event Type
  with an undecided quantity held beneath it cannot be deleted, through any
  door; a held name already decided, or held for a reason no declaration
  answers, does not hold it.
* **Row 4 — unresolved economics are never published as known.** A posting
  whose cost waits on a held name carries an `unknown` price — not one a rule
  matching a spelling produced, and not a `waived` one a margin rung produced.

Every report here is recorded through the public route, and every
declaration and publication made through the tenant's own routes; a map and a
dismissal are the kernel's own services, which is where those decisions are
taken today, and no route deletes an Event Type, so row 3 is asked of the
ORM's doors.
"""
from datetime import timedelta

import pytest
from django.db import IntegrityError, connection, migrations, transaction
from django.db.migrations.loader import MigrationLoader

from api.v1.tests._helpers import DeclaringTenantCase, OnTheSingleRoute
from apps.metering.pricing.services.resolution_run import (
    AnswerNamesOneQuantityTwice, RunSelector, execute)
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, declares_a_markup, rate_in_default_book)
from apps.metering.usage.models import Posting
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import EventType, Measurement
from apps.platform.event_types.models import RESOLUTION_DISMISSED
from apps.platform.event_types.quarantine import (
    NotYetPublished, dismiss_as_non_economic, map_to_a_declaration,
    refuse_a_silent_close)
from apps.platform.event_types.tests._helpers import declares_an_event_type
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from apps.platform.tenants.tasks import reset_sandbox_tenant_sync
from core.time_windows import month_bounds, utc_day_start
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_REASON_EVENT_TYPE_NOT_DECLARED,
    PRICING_STATUS_REASON_MEASUREMENT_NOT_DECLARED,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED,
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

    def test_a_name_mapped_to_a_draft_waits_for_the_publication(self):
        """A quantity the tenant has declared only in a DRAFT answers for
        nothing — production reads the publication (#605) — so a mapping to
        it is refused by name, and the name stays held. Published, it is the
        answer, and the replay settles the event from its own moment."""
        reasoning, misspelt = "reasoning_tokens", "reasonng_tokens"
        cost_rate_in_default_book(self.tenant, measurement_key=reasoning,
                                  unit_quantity=1, rate_per_unit_micros=1_000)
        posting = self.a_report(**{INPUT: "10", misspelt: "4"})
        self.declares_a_quantity(CHAT, reasoning, publish=False)

        with self.assertRaises(NotYetPublished):
            map_to_a_declaration(self.held_as(misspelt),
                                 self.declared_as(reasoning))
        self.assertTrue(self.held_as(misspelt).is_unresolved)

        self.admin("post", f"/event-types/{CHAT}/publish")
        map_to_a_declaration(self.held_as(misspelt),
                             self.declared_as(reasoning))

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 4 * 1_000)

    def test_a_run_applies_the_answer_the_replay_could_not_settle_on(self):
        """Mapped while no rate reached the declared name at the event's
        moment, the replay completes nothing — and the answer is not lost: a
        Resolution Run, once a rate is in force at that moment, re-costs the
        event under the same re-keyed bag. A run that re-resolved the spelling
        would hold the name again forever."""
        reasoning, misspelt = "reasoning_tokens", "reasonng_tokens"
        self.declares_a_quantity(CHAT, reasoning)
        posting = self.a_report(**{INPUT: "10", misspelt: "4"})

        map_to_a_declaration(self.held_as(misspelt),
                             self.declared_as(reasoning))
        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_UNRESOLVED)

        cost_rate_in_default_book(
            self.tenant, measurement_key=reasoning, unit_quantity=1,
            rate_per_unit_micros=1_000,
            valid_from=posting.effective_at - timedelta(days=1))
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 4 * 1_000)

    def test_a_publication_declaring_a_held_quantity_registers_it(self):
        """The tenant declares the very name that arrived, through the
        catalogue routes: the publication is the registration, and the event
        settles from its own moment."""
        reasoning = "reasoning_tokens"
        cost_rate_in_default_book(self.tenant, measurement_key=reasoning,
                                  unit_quantity=1, rate_per_unit_micros=1_000)
        posting = self.a_report(**{INPUT: "10", reasoning: "4"})
        self.assertTrue(self.held_as(reasoning).is_unresolved)

        self.declares_a_quantity(CHAT, reasoning)

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros,
                         10 * COSTS[INPUT] + 4 * 1_000)
        self.assertEqual(self.held_as(reasoning).resolved_key, reasoning)

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


#: The posting columns a re-costing would move, and the record beside them.
WHAT_A_RE_COSTING_MOVES = ("costing_status", "unresolved_reason",
                           "provider_cost_micros", "pricing_status",
                           "billed_cost_micros", "pricing_status_reason",
                           Posting.RECEIPT_COLUMN)


def as_recorded(posting):
    posting.refresh_from_db()
    return {column: getattr(posting, column)
            for column in WHAT_A_RE_COSTING_MOVES}


class ADismissedNameReCostsNothingTest(_ATenantWithOneDeclaration):
    """Row 2. Dismissal is the tenant answering the CLOSE's question — this
    was never economic — and not a request to re-cost the event without the
    name. So the period can close, and the event keeps exactly what it was
    recorded with, now and under every later run: the cost still waits on a
    name no declaration carries, and the price over it is still unknown."""

    def test_a_dismissal_frees_the_close_and_leaves_the_event_as_recorded(self):
        posting = self.a_report(**{INPUT: "10", OUTPUT_MISSPELT: "5"})
        recorded = as_recorded(posting)

        replay = dismiss_as_non_economic(self.held_as(OUTPUT_MISSPELT))

        self.assertIsNone(replay)
        self.assertEqual(as_recorded(posting), recorded)
        opens, closes = month_bounds(posting.effective_at)
        refuse_a_silent_close(tenant=self.tenant,
                              opened_at=utc_day_start(opens),
                              closes_at=utc_day_start(closes))

    def test_no_later_run_re_costs_it_without_the_dismissed_name(self):
        """The re-costing a run WOULD do, if a dismissed name were dropped
        from the bag, is a settled cost and price over input tokens alone —
        exactly what the ruling refused."""
        posting = self.a_report(**{INPUT: "10", OUTPUT_MISSPELT: "5"})
        recorded = as_recorded(posting)
        dismiss_as_non_economic(self.held_as(OUTPUT_MISSPELT))

        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        self.assertEqual(as_recorded(posting), recorded)

    def test_a_dismissed_event_type_re_costs_nothing_either(self):
        posting = self.posting(self.send(
            "k2", event_type="acme.never_declared",
            measurements={INPUT: "10"}))
        recorded = as_recorded(posting)
        self.assertEqual(recorded["unresolved_reason"],
                         UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED)
        # The price's stated reason is history the dismissal keeps, compared
        # below with everything else a re-costing would move.
        self.assertEqual(recorded["pricing_status_reason"],
                         PRICING_STATUS_REASON_EVENT_TYPE_NOT_DECLARED)

        (held,) = self.held()
        dismiss_as_non_economic(held)
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        self.assertEqual(as_recorded(posting), recorded)

    def test_publishing_a_dismissed_key_later_re_costs_nothing(self):
        """The tenant dismissed the Event Type and later declares the same
        key for real. The dismissed call stays dismissed: the publication
        does not register it, and no run costs it under the new declaration —
        that would re-cost history the tenant said was never economic."""
        never = "acme.never_declared"
        posting = self.posting(self.send("k2", event_type=never,
                                         measurements={INPUT: "10"}))
        recorded = as_recorded(posting)
        (held,) = self.held()
        dismiss_as_non_economic(held)

        self.declared(never, quantities=(INPUT,))
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        self.assertEqual(as_recorded(posting), recorded)
        held.refresh_from_db()
        self.assertEqual(held.resolution, RESOLUTION_DISMISSED)

    def test_declaring_a_dismissed_quantity_later_re_costs_nothing(self):
        """The same for a quantity: declared and published beneath the
        Event Type after it was dismissed, it does not reach the call the
        tenant said it never cost."""
        reasoning = "reasoning_tokens"
        cost_rate_in_default_book(self.tenant, measurement_key=reasoning,
                                  unit_quantity=1, rate_per_unit_micros=1_000)
        posting = self.a_report(**{INPUT: "10", reasoning: "4"})
        recorded = as_recorded(posting)
        dismiss_as_non_economic(self.held_as(reasoning))

        self.declares_a_quantity(CHAT, reasoning)
        with transaction.atomic():
            execute(tenant=self.tenant, selector=RunSelector())

        self.assertEqual(as_recorded(posting), recorded)
        self.assertEqual(self.held_as(reasoning).resolution,
                         RESOLUTION_DISMISSED)


class ADeclarationIsNotDeletedFromUnderItsHeldNamesTest(
        OnTheSingleRoute, DeclaringTenantCase):
    """Row 3, at every door a deletion has. No route deletes an Event Type,
    so these are the ORM's: an instance, a queryset and raw SQL. The rule is
    asked when the deletion commits (`event_types/0011`), so each door is
    driven inside a savepoint and the deferred check is run before it ends —
    which is what a commit would do."""

    def setUp(self):
        super().setUp()
        self.declared(CHAT, quantities=(INPUT,))
        self.send("k1", event_type=CHAT,
                  measurements={INPUT: "10", OUTPUT_MISSPELT: "5"})

    def declaration(self, key=CHAT):
        """Read afresh each time: an instance's `delete()` sets its own key to
        `None` even when the deletion is rolled back, so a held instance would
        answer every later question about a row that was never touched."""
        return EventType.objects.filter(tenant=self.tenant, key=key).first()

    DOORS = {
        "an instance": lambda event_type: event_type.delete(),
        "a queryset": lambda event_type: EventType.objects.filter(
            pk=event_type.pk).delete(),
        # Its parts too, as the ORM's cascade takes them: left behind, they
        # would answer with their own foreign key before the rule under test
        # is asked.
        "raw sql": lambda event_type: connection.cursor().execute(
            "DELETE FROM ubb_measurement WHERE event_type_id = %s; "
            "DELETE FROM ubb_event_type WHERE id = %s",
            [event_type.pk, event_type.pk]),
    }

    def committed(self, *acts):
        """Each act, and then the check a commit runs, in one savepoint."""
        try:
            with transaction.atomic():
                for act in acts:
                    act()
                connection.check_constraints()
        finally:
            with connection.cursor() as cursor:
                cursor.execute("SET CONSTRAINTS ALL DEFERRED")

    def test_every_door_is_refused_while_a_name_is_held_beneath_it(self):
        for door, delete in self.DOORS.items():
            with self.subTest(door=door):
                with self.assertRaises(IntegrityError) as refusal:
                    self.committed(lambda: delete(self.declaration()))
                self.assertIn("held name", str(refusal.exception))
                self.assertIsNotNone(self.declaration())

    def test_a_decided_name_no_longer_holds_it(self):
        (held,) = self.held()
        dismiss_as_non_economic(held)

        self.committed(lambda: self.declaration().delete())

        self.assertIsNone(self.declaration())

    def test_a_key_declared_again_in_the_same_change_is_not_refused(self):
        """The held names are still answerable, against the declaration at
        the same key — which is what the rule asks of what is LEFT."""
        original = self.declaration().pk

        self.committed(
            lambda: self.declaration().delete(),
            lambda: declares_an_event_type(self.tenant, CHAT,
                                           quantities=(INPUT,)))

        self.assertNotEqual(self.declaration().pk, original)

    def test_the_reverse_is_exercised_rather_than_merely_declared(self):
        """`docs/conventions/django-patterns.md`: a reverse that a test runs.
        Asserted by behaviour at both ends — reversed out, the deletion lands;
        re-applied, the same deletion of another declaration is refused again.
        Postgres runs the DDL inside this test's transaction, which takes it
        back, so no other test sees the table without its rule."""
        migration = MigrationLoader(connection).get_migration(
            "event_types",
            "0011_a_declaration_is_not_deleted_from_under_its_held_names")
        (run_python,) = [operation for operation in migration.operations
                         if isinstance(operation, migrations.RunPython)]

        with connection.schema_editor() as editor:
            run_python.reverse_code(None, editor)
        self.committed(lambda: self.declaration().delete())
        self.assertIsNone(self.declaration())

        with connection.schema_editor() as editor:
            run_python.code(None, editor)
        second = "acme.second"
        self.declared(second, quantities=(INPUT,))
        self.send("k2", event_type=second,
                  measurements={INPUT: "1", OUTPUT_MISSPELT: "1"})
        with self.assertRaises(IntegrityError):
            self.committed(lambda: self.declaration(second).delete())
        self.assertIsNotNone(self.declaration(second))

    def test_an_event_type_held_at_a_draft_key_does_not_hold_the_draft(self):
        """An unrecognised EVENT TYPE is held because no publication answers
        its key, so a draft at that key is nothing it depends on."""
        self.declared("acme.draft", quantities=(INPUT,), publish=False)
        self.send("k2", event_type="acme.draft", measurements={INPUT: "1"})

        self.committed(lambda: self.declaration("acme.draft").delete())

        self.assertIsNone(self.declaration("acme.draft"))


@pytest.mark.django_db(transaction=True)
def test_a_full_reset_takes_the_held_names_first():
    """Row 3 must not refuse a sandbox's own wipe. That wipe commits once per
    model, and its generic sweep reaches an Event Type before the held names
    in the same app — so this is the one place the rule's commit-time check
    meets a real commit, and why it runs outside a test transaction."""
    live = Tenant.objects.create(name="Live", products=["metering"])
    sandbox = get_or_create_sandbox(live)
    customer = Customer.objects.create(tenant=sandbox, external_id="c1")
    declares_an_event_type(sandbox, CHAT, quantities=(INPUT,))
    UsageService.record_usage(sandbox, customer, "k1", event_type=CHAT,
                              measurements={INPUT: "10", OUTPUT_MISSPELT: "5"})

    result = reset_sandbox_tenant_sync(sandbox.id, keep_config=False)

    assert result["status"] == "completed"
    assert not EventType.objects.filter(tenant=sandbox).exists()


class AnUnresolvedSpellingIsNeverPricedKnownTest(_ATenantWithOneDeclaration):
    """Row 4. Shown red against `_priced_by_rules` as it stood at
    `9c1a7747`, which answered `known` whenever no rule declared a margin,
    whatever the cost's status: a price rule matching the misspelling, and the
    rules for the names that did resolve, priced the event as though the call
    were understood."""

    def test_a_rule_at_the_spelling_does_not_price_it_known(self):
        rate_in_default_book(self.tenant, measurement_key=OUTPUT_MISSPELT,
                             unit_quantity=1, rate_per_unit_micros=7)

        ack = self.send("k1", event_type=CHAT,
                        measurements={INPUT: "10", OUTPUT_MISSPELT: "5"})

        posting = self.posting(ack)
        for said in (ack, {"pricing_status": posting.pricing_status,
                           "billed_cost_micros": posting.billed_cost_micros,
                           "pricing_status_reason":
                               posting.pricing_status_reason}):
            self.assertEqual(said["pricing_status"], PRICING_STATUS_UNKNOWN)
            self.assertIsNone(said["billed_cost_micros"])
            # Unknown WITH its stated reason, as ruled — the cost's cause.
            self.assertEqual(said["pricing_status_reason"],
                             PRICING_STATUS_REASON_MEASUREMENT_NOT_DECLARED)
        self.assertIsNone(ack["pricing_method"])
        self.assertEqual(
            posting.pricing_receipt["provenance"]["price_rate_ids"], {})


class AMarginOverAHeldNameIsNotWaivedTest(OnTheSingleRoute,
                                          DeclaringTenantCase):
    """Row 4's other half. With no rule to price the event, the markup rung
    used to answer `waived` over a cost UBB did not have — a decided loss,
    terminal, so the event could never be priced once the name was answered.
    The price waits on the same decision the cost does."""

    def test_the_price_is_unknown_and_a_mapping_completes_it(self):
        chat = self.declared(CHAT, quantities=(INPUT, OUTPUT))
        cost_rate_in_default_book(self.tenant, measurement_key=INPUT,
                                  unit_quantity=1, rate_per_unit_micros=100)
        cost_rate_in_default_book(self.tenant, measurement_key=OUTPUT,
                                  unit_quantity=1, rate_per_unit_micros=100)
        declares_a_markup(self.tenant, percentage_micros=50_000_000)

        posting = self.posting(self.send(
            "k1", event_type=CHAT,
            measurements={INPUT: "10", OUTPUT_MISSPELT: "5"}))
        self.assertEqual(posting.pricing_status, PRICING_STATUS_UNKNOWN)
        self.assertEqual(posting.pricing_status_reason,
                         PRICING_STATUS_REASON_MEASUREMENT_NOT_DECLARED)

        (held,) = self.held()
        map_to_a_declaration(held, Measurement.objects.get(event_type=chat,
                                                           code=OUTPUT))

        posting.refresh_from_db()
        self.assertEqual(posting.provider_cost_micros, 1_500)
        self.assertEqual(posting.pricing_status, PRICING_STATUS_KNOWN)
        self.assertEqual(posting.billed_cost_micros, 2_250)
        self.assertIsNone(posting.pricing_status_reason)
