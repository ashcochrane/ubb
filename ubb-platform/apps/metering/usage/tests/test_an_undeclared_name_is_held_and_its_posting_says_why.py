"""One report, two records, and they agree (#428, #265, spec §3.4).

A usage report arrives beneath an Event Type the tenant declared, carrying a
quantity under a name that declaration does not mention. Two things must happen
to it, from one call, and the whole of this module is that neither happens
without the other:

* the posting is recorded — the supplier already charged for the call — with
  its cost `unresolved` and the reason `measurement_not_declared`, which is the
  value the published contract has advertised on four schemas since #323 and
  which nothing could produce until this join was built; and
* the name is **held**: a quarantine row beneath that Event Type, keeping the
  number exactly as it was sent, so a tenant can say what the name meant and a
  period holding it does not close silently (#329).

**Why the join lives on the recording path and not in the pricer.** The compute
spine decides the STATUS — it is the one place that may (#320) — and it learns
which names the declaration carries through the same read that tells it how the
Event Type costs. But the spine is also what a Resolution Run re-runs over a
stored receipt, and a hold written from inside it would mint a second held row
every time a recovery looked at the posting. So the spine RECORDS the undeclared
quantities on the receipt, and the recording core reads them off the receipt and
holds each one beside the posting it just wrote — the same terms every other
column is written on (`costing_of`).

**Where the name is NOT read, and why that is a boundary rather than a gap.**
Only the branch that rates quantities against Cost Rates ever looks a name up.
A figure the caller supplied IS the cost; a declaration that says a supplier
reports its figure is waiting on that figure whatever the bag says; an Event
Type that declares no cost at all has nothing for a name to cost. In each of
those the cost is settled or unsettled for a reason that has nothing to do with
the name, so the posting's reason cannot be the name — and the hold follows the
posting's reason by construction, so nothing is held there either. And the
registry is opt-in (`costing.cost_declaration`): a report against an Event Type
nobody declared has no declaration for a name to be missing from, and costs the
way this repository has always costed.

**The agreement test** at the foot is the one #329 claimed existed and #265's
module records did not: it records postings through the production path and
compares the period close's definition of "unaccounted for" — held names, by
the event's own moment — with the posting's own column, in both directions.
"""
from datetime import timedelta

import pytest
from django.utils import timezone

from apps.metering.pricing.receipts import (
    recorded_quantities, uncosted_quantity_keys)
from apps.metering.pricing.tests._helpers import cost_rate_in_default_book
from apps.metering.usage.models import Posting
from apps.metering.usage.services import usage_service
from apps.metering.usage.services.usage_service import UsageService
from apps.platform.customers.models import Customer
from apps.platform.event_types.models import (
    EventType,
    Measurement,
    QuarantinedKey,
    ReportedCostMapping,
    UNRECOGNISED_MEASUREMENT_KEY,
)
from apps.platform.event_types.quarantine import (
    PeriodHoldsUnresolvedValues,
    refuse_a_silent_close,
    register_the_held_name,
    unresolved_in_period,
)
from apps.platform.tenants.models import Tenant
from core.time_windows import month_bounds, utc_day_start
from core.vocabulary import (
    AMOUNT_REPRESENTATION_MICROS,
    COSTING_METHOD_CALCULATED,
    COSTING_METHOD_REPORTED,
    COSTING_STATUS_KNOWN,
    COSTING_STATUS_UNRESOLVED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
    UNRESOLVED_REASON_COST_RATE_MISSING,
    UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED,
    UNRESOLVED_REASON_REPORTED_COST_MISSING,
)

EVENT_TYPE_KEY = "acme.embed"
DECLARED_QUANTITY = "prompt_tokens"
#: The name the declaration does not mention — a plausible misspelling of a
#: quantity somebody meant, which is the commonest way one arrives.
A_NAME_NOBODY_DECLARED = "reasoning_tokens"
#: A number a numeric column with a scale would have rounded; held as text it
#: comes back exactly, which is the accept rule (#265).
AS_SENT = 1_000_000_000_007


def _tenant():
    return Tenant.objects.create(name="T", default_currency="usd")


def _customer(tenant, external_id="c1"):
    return Customer.objects.create(tenant=tenant, external_id=external_id)


def _declaration(tenant, *, key=EVENT_TYPE_KEY,
                 costing_method=COSTING_METHOD_CALCULATED,
                 quantities=(DECLARED_QUANTITY,), mapping=False):
    """An Event Type declared the way a tenant declares one, with the
    quantities it carries — the set the name below is measured against."""
    event_type = EventType.objects.create(
        tenant=tenant, key=key, costing_method=costing_method)
    for code in quantities:
        Measurement.objects.create(
            event_type=event_type, code=code, unit=UNIT_TOKEN,
            source_kind=SOURCE_KIND_CALLER_SUPPLIED)
    if mapping:
        ReportedCostMapping.objects.create(
            event_type=event_type, source_kind=SOURCE_KIND_CALLER_SUPPLIED,
            amount_representation=AMOUNT_REPRESENTATION_MICROS, currency="usd")
    return event_type


def _cost_rate(tenant, *, measurement_key=DECLARED_QUANTITY, micros=5_000):
    return cost_rate_in_default_book(
        tenant, provider="openai", event_type=EVENT_TYPE_KEY,
        measurement_key=measurement_key, rate_per_unit_micros=micros,
        unit_quantity=1_000)


def _record(tenant, customer, key, **fields):
    """One report through the production path — the only caller there is."""
    fields.setdefault("event_type", EVENT_TYPE_KEY)
    fields.setdefault("provider", "openai")
    return UsageService.record_usage(tenant, customer, key, **fields)


def _posting(result):
    return Posting.objects.get(id=result["event_id"])


def _held(tenant):
    return list(QuarantinedKey.objects.filter(tenant=tenant)
                .order_by("measurement_key"))


def _a_declared_and_rated_tenant():
    tenant = _tenant()
    _declaration(tenant)
    _cost_rate(tenant)
    return tenant, _customer(tenant)


def _the_month_of(posting):
    """The period-close window the posting's own moment falls in, half-open —
    the shape `unresolved_in_period` takes and the close asks with."""
    opens, closes = month_bounds(posting.effective_at)
    return utc_day_start(opens), utc_day_start(closes)


def _the_month_after(posting):
    opens, closes = month_bounds(posting.effective_at)
    _, following = month_bounds(utc_day_start(closes))
    return utc_day_start(closes), utc_day_start(following)


# ---------------------------------------------------------------------------
# One report produces both halves
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestOneReportProducesBothHalves:
    """The join is the point; either half alone is the state #428 was raised
    over."""

    def test_the_posting_says_the_name_is_undeclared(self):
        """The reason the contract advertised four times, produced.

        Not `cost_rate_missing`: a rate is not what is missing. The tenant's
        declaration does not carry this name, and the remedy the value names —
        decide what the name meant — is a different act from writing a rate.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        result = _record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40})

        posting = _posting(result)
        assert posting.costing_status == COSTING_STATUS_UNRESOLVED
        assert posting.unresolved_reason == \
            UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED
        assert posting.provider_cost_micros is None
        # The ack is read off the row (#317), so the same value reaches the
        # caller who sent the name.
        assert result["unresolved_reason"] == \
            UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED

    def test_the_name_is_held_beneath_the_event_type_it_arrived_under(self):
        """The other half: a held row, from the production path.

        Beneath the DECLARED Event Type — the event matched a declaration and
        only the quantity beneath it was unrecognised, which is what makes it
        `hold_an_unrecognised_quantity`'s case and not the other one. Placed by
        the event's own moment, because that is what the period close reads
        and what a replay is stamped with.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        (held,) = _held(tenant)
        assert held.unrecognised == UNRECOGNISED_MEASUREMENT_KEY
        assert held.event_type_key == EVENT_TYPE_KEY
        assert held.measurement_key == A_NAME_NOBODY_DECLARED
        assert held.occurred_at == posting.effective_at
        assert held.is_unresolved

    def test_the_number_is_held_exactly_as_it_was_sent(self):
        """Nothing is zeroed and nothing is rounded (#265).

        The declaration that would say what scale is legal for this name is
        the one that is missing, so the number is kept as text, verbatim.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        _record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: AS_SENT})

        (held,) = _held(tenant)
        assert held.quantity == str(AS_SENT)
        assert held.quantities == {}, "a quantity row carries no bag: the " \
            "posting holds the rest"

    def test_the_declared_quantity_is_costed_and_is_not_held(self):
        """The hold is about the NAME. What the declaration carries is rated
        exactly as before, its line stays on the receipt, and no row is held
        for it — one row per event per undeclared name, not per quantity."""
        tenant, customer = _a_declared_and_rated_tenant()

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        rated = posting.pricing_receipt["costing"]["detail"]["components"]
        assert [line["measurement_key"] for line in rated] == [DECLARED_QUANTITY]
        assert rated[0]["micros"] == 5_000
        assert [row.measurement_key for row in _held(tenant)] == [
            A_NAME_NOBODY_DECLARED]

    def test_every_undeclared_name_on_one_report_is_held(self):
        """Two names, two rows — each a decision the tenant has to make."""
        tenant, customer = _a_declared_and_rated_tenant()

        _record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, "reasonning_tokens": 7,
            A_NAME_NOBODY_DECLARED: 40})

        assert [row.measurement_key for row in _held(tenant)] == [
            A_NAME_NOBODY_DECLARED, "reasonning_tokens"]

    def test_the_receipt_keeps_the_undeclared_quantity_for_a_recovery(self):
        """The bag a Resolution Run re-resolves from has the number in it.

        The run reads the receipt and never the measurement rows (#350), and a
        receipt that dropped the undeclared quantity would make a re-costing
        after the tenant declares the name silently cost LESS than the call
        measured — the under-count this whole programme exists to delete. Read
        through the production reader rather than off the record's own key, so
        a key the reader does not union goes red here.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        receipt = posting.pricing_receipt
        assert recorded_quantities(receipt) == {
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}
        # And the wire's "which quantities went uncosted" names it: the ack
        # carries no other field a reader could learn the name from.
        assert uncosted_quantity_keys(receipt) == [A_NAME_NOBODY_DECLARED]

    def test_a_replay_holds_no_second_row(self):
        """One row per event (#265), and a retry is the same event.

        The idempotent replay answers before anything is priced, so the held
        row is written exactly once however many times the report is retried
        — and the replay's ack still says the reason, off the row.
        """
        tenant, customer = _a_declared_and_rated_tenant()
        first = _record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40})

        again = _record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40})

        assert again["event_id"] == first["event_id"]
        assert again["unresolved_reason"] == \
            UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED
        assert len(_held(tenant)) == 1

    def test_neither_half_survives_without_the_other(self, monkeypatch):
        """"Both outcomes, from one report": one transaction, not two.

        A hold that fails takes the posting with it. Without this a posting
        could say `measurement_not_declared` while no period close ever heard
        of the name — the exact state #428 was raised to end, reached through
        a partial write. Pinned by making the hold fail and reading what is
        left: nothing.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        def the_hold_fails(**_):
            raise RuntimeError("the held row could not be written")

        monkeypatch.setattr(usage_service, "hold_an_unrecognised_quantity",
                            the_hold_fails)

        with pytest.raises(RuntimeError):
            _record(tenant, customer, "k1", measurements={
                DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40})

        assert Posting.objects.count() == 0
        assert _held(tenant) == []


# ---------------------------------------------------------------------------
# What is not held, and why each is a boundary
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestWhatIsNotHeld:
    """Every case here is a report that costs for a reason other than the
    name, and in each the hold follows the reason: nothing is held."""

    def test_an_undeclared_event_type_holds_nothing_and_costs_as_it_always_did(self):
        """The registry is opt-in (`cost_declaration`).

        No declaration means no set of names for this one to be missing from,
        so the quantity resolves against Cost Rates the way every posting did
        before the registry existed. Holding it would refuse the opt-in.
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _cost_rate(tenant)

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        assert posting.costing_status == COSTING_STATUS_UNRESOLVED
        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert _held(tenant) == []

    def test_a_declared_but_unrated_quantity_is_a_missing_rate_not_a_missing_name(self):
        """The discriminating control: the tenant DID declare this name.

        What is missing is a rate, the remedy is to write one, and nothing
        about it is a question for the tenant to answer about spelling. A
        hold here would be the join reading "uncosted" as "unrecognised".
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, quantities=(DECLARED_QUANTITY, "image_pixels"))
        _cost_rate(tenant)

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, "image_pixels": 40}))

        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert _held(tenant) == []

    def test_a_declared_and_rated_report_is_known_and_holds_nothing(self):
        """The positive control, or every case above reads as "the join
        holds whatever arrives"."""
        tenant, customer = _a_declared_and_rated_tenant()

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000}))

        assert posting.costing_status == COSTING_STATUS_KNOWN
        assert posting.provider_cost_micros == 5_000
        assert _held(tenant) == []

    def test_both_causes_on_one_report_name_the_declaration_first(self):
        """An undeclared name beside a declared-but-unrated one.

        A posting carries ONE reason, and the name comes first: a rate cannot
        be written against a name until the tenant has said what it is, so
        the declaration is the earlier question. Only the undeclared name is
        held; the unrated one stays on the receipt for the run that will cost
        it once a rate exists, and BOTH are in the bag a recovery re-resolves
        from and in the list the wire publishes.
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, quantities=(DECLARED_QUANTITY, "image_pixels"))
        _cost_rate(tenant)

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, "image_pixels": 12,
            A_NAME_NOBODY_DECLARED: 40}))

        assert posting.unresolved_reason == \
            UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED
        assert [row.measurement_key for row in _held(tenant)] == [
            A_NAME_NOBODY_DECLARED]
        receipt = posting.pricing_receipt
        assert recorded_quantities(receipt) == {
            DECLARED_QUANTITY: 1_000, "image_pixels": 12,
            A_NAME_NOBODY_DECLARED: 40}
        assert sorted(uncosted_quantity_keys(receipt)) == [
            "image_pixels", A_NAME_NOBODY_DECLARED]

    def test_a_caller_supplied_figure_is_the_cost_and_the_name_is_not_read(self):
        """Branch one of the spine: a figure that arrived IS the answer.

        No declaration is consulted to cost it (#324 decided WHETHER it may
        arrive, before this runs), so no name is looked up, so nothing is
        unrecognised for costing. The name is carried on the posting as every
        undeclared quantity always was.
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=(DECLARED_QUANTITY,), mapping=True)

        posting = _posting(_record(
            tenant, customer, "k1", provider_cost_micros=777,
            measurements={DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        assert posting.costing_status == COSTING_STATUS_KNOWN
        assert posting.provider_cost_micros == 777
        assert _held(tenant) == []

    def test_a_reported_declaration_with_no_figure_is_waiting_on_the_supplier(self):
        """Branch three: what settles this posting is a figure arriving.

        The reason names that input and not the name, because a re-costing
        is not what recovers it (`resolution_run`'s own guard). Holding the
        name would say the period cannot close until somebody decides a
        spelling, for a cost that a spelling decision cannot settle.
        """
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, costing_method=COSTING_METHOD_REPORTED,
                     quantities=(DECLARED_QUANTITY,), mapping=True)

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        assert posting.unresolved_reason == \
            UNRESOLVED_REASON_REPORTED_COST_MISSING
        assert _held(tenant) == []

    def test_an_empty_name_is_not_a_name_and_stays_on_the_rate_path(self):
        """The one shape the held row refuses, kept out of it on purpose.

        `ck_quarantined_key_names_what_it_is_about` refuses a quantity row
        naming no quantity, and the accept rule says nothing about a name may
        refuse an event at the door. An empty key is not a spelling a tenant
        can decide about, so it is not the join's: it matches no rate and the
        posting says so, exactly as it did before.
        """
        tenant, customer = _a_declared_and_rated_tenant()

        posting = _posting(_record(tenant, customer, "k1", measurements={
            DECLARED_QUANTITY: 1_000, "": 3}))

        assert posting.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert _held(tenant) == []


# ---------------------------------------------------------------------------
# The agreement — the two definitions of "unaccounted for", compared
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheTwoDefinitionsAgree:
    """The period close asks the quarantine table which names it still holds
    (`refuse_a_silent_close`, called by `TenantBillingService.close_period`);
    the posting says why its cost is unresolved. Until #428 nothing produced
    both from one event, so the two could not be compared and #329's claim
    that "the existing test goes red the day they disagree" was unpayable.

    Every posting here is recorded through the production path. The agreement
    is stated over the whole fixture in both directions: every held name in
    the window is a posting marked `measurement_not_declared` at that moment,
    and every such posting has its name held — while a posting unresolved for
    another reason, and one that is settled, hold nothing.
    """

    def _a_month_of_reports(self):
        tenant = _tenant()
        customer = _customer(tenant)
        _declaration(tenant, quantities=(DECLARED_QUANTITY, "image_pixels"))
        _cost_rate(tenant)
        undeclared = _posting(_record(tenant, customer, "undeclared",
                                      measurements={DECLARED_QUANTITY: 1_000,
                                                    A_NAME_NOBODY_DECLARED: 40}))
        unrated = _posting(_record(tenant, customer, "unrated",
                                   measurements={"image_pixels": 12}))
        settled = _posting(_record(tenant, customer, "settled",
                                   measurements={DECLARED_QUANTITY: 1_000}))
        return tenant, (undeclared, unrated, settled)

    @staticmethod
    def _undeclared_names_on(postings):
        """The posting side's answer: `(event type, name, moment)` for every
        undeclared name on every posting whose column says so — read off the
        receipt the column was written from."""
        return {
            (posting.event_type, name, posting.effective_at)
            for posting in postings
            if posting.unresolved_reason
            == UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED
            for name in posting.pricing_receipt["costing"]["detail"][
                "undeclared_quantities"]}

    @staticmethod
    def _held_names_in(tenant, window):
        """The close's answer, through the query the close consults."""
        opened_at, closes_at = window
        return {(row.event_type_key, row.measurement_key, row.occurred_at)
                for row in unresolved_in_period(
                    tenant=tenant, opened_at=opened_at, closes_at=closes_at)}

    def test_the_close_refuses_over_exactly_the_postings_marked_undeclared(self):
        tenant, postings = self._a_month_of_reports()
        undeclared, unrated, settled = postings

        from_the_postings = self._undeclared_names_on(postings)
        from_the_close = self._held_names_in(tenant, _the_month_of(undeclared))

        assert from_the_postings, "the fixture produced no undeclared name, " \
            "so the comparison below is vacuous"
        assert from_the_close == from_the_postings
        assert unrated.unresolved_reason == UNRESOLVED_REASON_COST_RATE_MISSING
        assert settled.costing_status == COSTING_STATUS_KNOWN
        for other in (unrated, settled):
            assert not any(moment == other.effective_at
                           for _, _, moment in from_the_close)

        opened_at, closes_at = _the_month_of(undeclared)
        with pytest.raises(PeriodHoldsUnresolvedValues) as refusal:
            refuse_a_silent_close(tenant=tenant, opened_at=opened_at,
                                  closes_at=closes_at)
        assert refusal.value.held == (A_NAME_NOBODY_DECLARED,)

    def test_the_two_are_placed_by_the_events_own_moment(self):
        """Both sides read WHEN THE EVENT HAPPENED. The following month holds
        nothing while the posting is still unresolved — a held name is not
        placed by when anybody gets round to it, and neither is the column."""
        tenant, postings = self._a_month_of_reports()
        undeclared = postings[0]

        assert self._undeclared_names_on(postings)
        assert self._held_names_in(tenant, _the_month_after(undeclared)) == set()

    def test_a_backdated_report_is_held_at_its_own_moment(self):
        """The moment is the posting's `effective_at`, not when it arrived.

        Backdated inside the tenant's backfill window — relative to now, as
        `docs/conventions/testing.md` asks of anything on this path — so the
        held row and the column disagree by a day if either reads the clock.
        """
        tenant, customer = _a_declared_and_rated_tenant()
        happened_at = timezone.now() - timedelta(days=2)

        posting = _posting(_record(
            tenant, customer, "backdated", effective_at=happened_at,
            measurements={DECLARED_QUANTITY: 1_000, A_NAME_NOBODY_DECLARED: 40}))

        (held,) = _held(tenant)
        assert held.occurred_at == happened_at
        assert posting.effective_at == happened_at
        assert held.occurred_at != posting.created_at

    def test_registering_the_name_frees_the_close_and_leaves_the_posting_to_a_replay(self):
        """What #428 does NOT close, said where it can be read.

        The tenant registers the name; the close is free. The posting is still
        `unresolved` / `measurement_not_declared`: re-costing it is the replay
        the remediation returns (#265's `Replay`), and nothing in this
        repository consumes one yet. So the two halves agree at ACCEPT — which
        is the join this ticket builds — and diverge at remediation until a
        replay consumer exists. That consumer is an UNOWNED RESIDUAL; a
        Resolution Run re-resolving the receipt would settle this posting once
        the name is declared, but the mapped and dismissed paths need the
        re-keyed bag only the replay carries.
        """
        tenant, postings = self._a_month_of_reports()
        undeclared = postings[0]
        opened_at, closes_at = _the_month_of(undeclared)
        (held,) = unresolved_in_period(tenant=tenant, opened_at=opened_at,
                                       closes_at=closes_at)
        declaration = EventType.objects.get(tenant=tenant, key=EVENT_TYPE_KEY)
        register_the_held_name(held, Measurement.objects.create(
            event_type=declaration, code=A_NAME_NOBODY_DECLARED,
            unit=UNIT_TOKEN, source_kind=SOURCE_KIND_CALLER_SUPPLIED))

        refuse_a_silent_close(tenant=tenant, opened_at=opened_at,
                              closes_at=closes_at)
        undeclared.refresh_from_db()
        assert undeclared.unresolved_reason == \
            UNRESOLVED_REASON_MEASUREMENT_NOT_DECLARED
