"""An event naming an Event Type with no production declaration is held (#568).

The governing decision is slice 2's spec, #193 §B5, restating #138: *"Unknown
Event Types. Accept, quarantine, replay — unamended. Never auto-register. The
period-close safeguard survives."* Before this, such an event was costed
against whatever Cost Rates matched its quantities' spellings and priced by
whatever rules did — as though the tenant had said what the call was.

What it does now, through both recording routes:

* it is **recorded** — the supplier has already charged for the call — with
  **no supplier cost and no customer price**: cost `unresolved`, reason
  `event_type_not_declared`, price `unknown`, and no rule consulted on either
  side;
* its name is **visibly held**: a held row beside the posting, written in the
  same savepoint and keeping the bag as it arrived, and the posting in every
  read that lists what UBB could not resolve;
* a period holding it **does not close silently**;
* and once the tenant says what it was — registers the name, or maps it to a
  declaration that exists — it **replays from its own moment**, never the
  repair's.

**"No production declaration" is the read returning nothing, and only that**
(#605's delegation, `#568 6043472550`): nobody declared the key, or it was
declared and never published. A catalogue row is not asked about, so a draft
takes no path of its own; the equivalence tests in
`test_two_request_fields_each_with_one_meaning.py` compare the two to each
other and stay green. An event naming NO Event Type is outside this (#567's
ruling) and costs as it always did.

Every case runs on the single route and on a batch item, and reads what the
tenant reads — the acknowledgement — and what later reads answer from — the
stored row.
"""
from datetime import timedelta

from django.utils import timezone

from api.v1.tests._helpers import (
    DeclaringTenantCase, OnTheBatchRoute, OnTheSingleRoute)
from apps.metering.pricing.receipts import HELD_NAME_KEY
from apps.metering.pricing.tests._helpers import (
    cost_rate_in_default_book, rate_in_default_book)
from apps.platform.event_types.models import (
    RESOLUTION_MAPPED, RESOLUTION_REGISTERED, UNRECOGNISED_EVENT_TYPE)
from apps.platform.event_types.quarantine import (
    PeriodHoldsUnresolvedValues, map_to_a_declaration,
    refuse_a_silent_close, register_the_held_name)
from core.time_windows import month_bounds, utc_day_start
from core.vocabulary import (
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    PRICING_STATUS_KNOWN,
    PRICING_STATUS_UNKNOWN,
    UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED,
)

#: A key nobody declares.
NOBODY = "acme.nobody_declared"
#: The quantity every report here carries, and the number it carries.
CALLS = "calls"
THREE = "3"
#: A cost and a price per call, distinct so a figure names the rule behind it.
COST_PER_CALL = 1_000
PRICE_PER_CALL = 5_000
#: What the same call costs and sells for under the rules that replaced them —
#: what a replay stamped with the REPAIR'S moment would answer.
LATER_COST_PER_CALL = 9_000
LATER_PRICE_PER_CALL = 50_000


class _Holding(DeclaringTenantCase):
    """The shared tenant, with this module's rules and report."""

    def rules(self, *, cost=COST_PER_CALL, price=PRICE_PER_CALL, **window):
        """A Cost Rate and a price rule for `calls`, pinning no Event Type —
        so the path #568 replaces would cost AND price any report of calls,
        whatever it named. `window` dates both."""
        cost_rate_in_default_book(
            self.tenant, measurement_key=CALLS, unit_quantity=1,
            rate_per_unit_micros=cost, **window)
        rate_in_default_book(
            self.tenant, measurement_key=CALLS, unit_quantity=1,
            rate_per_unit_micros=price, **window)

    def a_report(self, correlation="k1", **body):
        body.setdefault("event_type", NOBODY)
        body.setdefault("measurements", {CALLS: THREE})
        return self.send(correlation, **body)

    def assert_held_with_no_cost_and_no_price(self, ack):
        """The acknowledgement and the stored row say the same thing: no
        cost, no price, and the reason naming the Event Type."""
        posting = self.posting(ack)
        for said in (ack, {column: getattr(posting, column) for column in (
                "costing_status", "unresolved_reason", "provider_cost_micros",
                "billed_cost_micros", "pricing_status")}):
            self.assertEqual(said["costing_status"], COSTING_STATUS_UNRESOLVED)
            self.assertEqual(said["unresolved_reason"],
                             UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED)
            self.assertIsNone(said["provider_cost_micros"])
            self.assertIsNone(said["billed_cost_micros"])
            self.assertEqual(said["pricing_status"], PRICING_STATUS_UNKNOWN)
        return posting


class _AnEventTypeNobodyPublishedIsHeld:

    def test_it_is_recorded_with_no_cost_and_no_price(self):
        """A Cost Rate and a price rule both match its quantity's spelling,
        and neither is consulted: a rule id on the record would say the
        tenant's configuration costed and priced a call nobody has
        described."""
        self.rules()

        ack = self.a_report()

        posting = self.assert_held_with_no_cost_and_no_price(ack)
        self.assertIsNone(ack["pricing_method"])
        self.assertEqual(ack["uncosted_measurement_keys"], [CALLS])
        receipt = posting.pricing_receipt
        self.assertEqual(receipt["costing"]["detail"]["components"], [])
        self.assertEqual(receipt["pricing"]["detail"]["components"], [])
        self.assertEqual(receipt["provenance"]["cost_rate_ids"], {})
        self.assertEqual(receipt["provenance"]["price_rate_ids"], {})

    def test_its_name_is_held_beside_the_posting_with_what_it_carried(self):
        self.rules()

        posting = self.posting(self.a_report())

        (held,) = self.held()
        self.assertEqual(held.unrecognised, UNRECOGNISED_EVENT_TYPE)
        self.assertEqual(held.event_type_key, NOBODY)
        self.assertEqual(held.quantities, {CALLS: THREE})
        self.assertEqual(held.event_id, posting.id)
        self.assertEqual(held.occurred_at, posting.effective_at)
        self.assertTrue(held.is_unresolved)

    def test_a_key_declared_and_never_published_is_held_the_same_way(self):
        """The hold keys on the publication read returning nothing — never on
        whether the catalogue has a row (#605's delegation)."""
        self.rules()
        self.declared(NOBODY, quantities=(CALLS,), publish=False)

        self.assert_held_with_no_cost_and_no_price(self.a_report())

        (held,) = self.held()
        self.assertEqual(held.event_type_key, NOBODY)

    def test_a_published_event_type_is_costed_and_nothing_is_held(self):
        """The control: every case above is about the publication."""
        self.rules()
        self.declared(NOBODY, quantities=(CALLS,))

        ack = self.a_report()

        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 3 * COST_PER_CALL)
        self.assertEqual(ack["billed_cost_micros"], 3 * PRICE_PER_CALL)
        self.assertEqual(self.held(), [])

    def test_an_event_naming_no_event_type_is_not_held(self):
        """#567's ruling: an event naming none names nothing to hold, and
        costs against Cost Rates as everything did before the registry."""
        self.rules()

        ack = self.a_report(event_type="")

        self.assertEqual(ack["costing_status"], COSTING_STATUS_KNOWN)
        self.assertEqual(ack["provider_cost_micros"], 3 * COST_PER_CALL)
        self.assertEqual(ack["pricing_status"], PRICING_STATUS_KNOWN)
        self.assertEqual(self.held(), [])

    def test_a_retry_holds_no_second_row(self):
        """One row per event, and a retry is the same event: answered from
        the original before anything is asked again (#605)."""
        self.rules()
        first = self.a_report()

        again = self.a_report()

        self.assertEqual(again["event_id"], first["event_id"])
        self.assertEqual(again["unresolved_reason"],
                         UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED)
        self.assertEqual(len(self.held()), 1)

    def test_it_is_visible_where_a_tenant_reads_what_is_unresolved(self):
        """Held for REMEDIATION means a tenant can find it: the queue of what
        UBB could not resolve lists it with the reason, and so does the
        event's own read."""
        self.rules()
        event_id = self.a_report()["event_id"]

        queue = self.read("/pricing/unresolved-queue")["data"]
        detail = self.read(f"/usage/{event_id}")

        (row,) = [row for row in queue if row["usage_event_id"] == event_id]
        self.assertEqual(row["unresolved_reason"],
                         UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED)
        self.assertEqual(row["event_type"], NOBODY)
        self.assertEqual(detail["unresolved_reason"],
                         UNRESOLVED_REASON_EVENT_TYPE_NOT_DECLARED)

    def test_a_period_holding_it_does_not_close_silently(self):
        """The safeguard `TenantBillingService.close_period` consults
        (#329), asked of the month the event happened in."""
        self.rules()
        posting = self.posting(self.a_report())
        opens, closes = month_bounds(posting.effective_at)

        with self.assertRaises(PeriodHoldsUnresolvedValues) as refusal:
            refuse_a_silent_close(tenant=self.tenant,
                                  opened_at=utc_day_start(opens),
                                  closes_at=utc_day_start(closes))

        self.assertEqual(refusal.exception.held, (NOBODY,))

    def test_it_replays_from_its_own_moment_once_the_name_is_registered(self):
        """The decisive case for "never the repair date". The rules changed
        between the call and the tenant's decision; the replay costs and
        prices the call as of when it happened. Stamped with the repair's
        moment it would answer the later rules' figures."""
        happened_at = timezone.now() - timedelta(days=3)
        changed_at = happened_at + timedelta(days=1)
        self.rules(valid_from=happened_at - timedelta(days=1),
                   valid_to=changed_at)
        self.rules(valid_from=changed_at, cost=LATER_COST_PER_CALL,
                   price=LATER_PRICE_PER_CALL)
        posting = self.assert_held_with_no_cost_and_no_price(
            self.a_report(effective_at=happened_at.isoformat()))

        (held,) = self.held()
        register_the_held_name(held, self.declared(NOBODY, quantities=(CALLS,)))

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros, 3 * COST_PER_CALL)
        self.assertEqual(posting.pricing_status, PRICING_STATUS_KNOWN)
        self.assertEqual(posting.billed_cost_micros, 3 * PRICE_PER_CALL)
        self.assertEqual(posting.effective_at, happened_at)
        receipt = posting.pricing_receipt
        self.assertEqual(receipt["provenance"][HELD_NAME_KEY], str(held.pk))
        held.refresh_from_db()
        self.assertEqual(held.resolution, RESOLUTION_REGISTERED)
        # And the decision is what the close reads: nothing is held now.
        opens, closes = month_bounds(happened_at)
        refuse_a_silent_close(tenant=self.tenant,
                              opened_at=utc_day_start(opens),
                              closes_at=utc_day_start(closes))

    def test_a_call_that_measured_nothing_replays_to_a_settled_zero(self):
        """The whole bag is kept, so an EMPTY bag is the call's own — a call
        that measured nothing — and its replay settles at zero. A record that
        kept no bag at all could not tell that from a silent zero, which is
        why a run leaves such a record alone; this one is not that record."""
        posting = self.assert_held_with_no_cost_and_no_price(
            self.a_report(measurements={}))

        (held,) = self.held()
        register_the_held_name(held, self.declared(NOBODY,
                                                   quantities=(CALLS,)))

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros, 0)

    def test_it_replays_under_the_declaration_it_is_mapped_to(self):
        """A misspelling mapped to the Event Type it meant is costed under
        THAT key: the only Cost Rate pins the declared key, so a replay under
        the misspelling would find none. The posting keeps the name it arrived
        with — what the call said is read, never rewritten."""
        meant = self.declared("acme.meant", quantities=(CALLS,))
        cost_rate_in_default_book(
            self.tenant, event_type=meant.key, measurement_key=CALLS,
            unit_quantity=1, rate_per_unit_micros=COST_PER_CALL)
        posting = self.posting(self.a_report())

        (held,) = self.held()
        map_to_a_declaration(held, meant)

        posting.refresh_from_db()
        self.assertEqual(posting.costing_status, COSTING_STATUS_KNOWN)
        self.assertEqual(posting.provider_cost_micros, 3 * COST_PER_CALL)
        self.assertEqual(posting.event_type, NOBODY)
        held.refresh_from_db()
        self.assertEqual(held.resolution, RESOLUTION_MAPPED)
        self.assertEqual(held.resolved_key, meant.key)


class AnEventTypeNobodyPublishedIsHeldOnTheSingleRouteTest(
        _AnEventTypeNobodyPublishedIsHeld, OnTheSingleRoute, _Holding):
    pass


class AnEventTypeNobodyPublishedIsHeldOnTheBatchRouteTest(
        _AnEventTypeNobodyPublishedIsHeld, OnTheBatchRoute, _Holding):
    pass
