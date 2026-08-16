"""Accept, quarantine, replay — the three words, tested (#265, #193 §B5/§C4).

Something arrives that UBB has never seen. A supplier has already charged the
tenant for it, so throwing it away throws away real supplier cost; and
registering it automatically would let a typo become permanent billing
vocabulary. Everything below is one of those two failures, held open.

* **Accept.** Nothing is discarded, nothing is zeroed, nothing raises at the
  door — including the number, which is preserved exactly as sent because the
  declaration that would say what shape it may take is the one that is missing.
* **Quarantine.** The unrecognised name is held and marked unresolved, and the
  event is not fully costed until somebody resolves it. **Never
  auto-registered**, however many times it arrives.
* **Replay.** Remediation is tenant-driven — map, register, or dismiss as
  non-economic — and on resolution the event replays **from its original
  timestamp, never the repair date**.
* **And a period holding unresolved economic values does not close silently.**
  "The month is closed" must never mean "closed except for the parts nobody
  looked at."

**What is deliberately not here, and the AC slice 2 could not pay in full.**
Slice 2 wired none of this: no recording path called any of it and no costing
status existed, so the ticket's *"its event is marked not fully costed"* had
**no mark to make** — there was no posting here to carry one. What was paid
instead is the read that mark is computed from — see
``test_a_held_quantity_is_reported_as_unaccounted_for_until_resolved``, which
is deliberately asserted through the query rather than through the row's own
field, because the second would pass however badly the query behaved.

**Both halves are now paid, in two different places** — the mark exists (#320)
and is asserted on the posting by metering's own uncostable-event module, and
the period close consults the query below (#329).

⚠ **What is NOT paid is an agreement between them, and #329's ticket says
otherwise.** It calls the test below *"the existing test that goes red the day
the two definitions disagree"*. It cannot: it creates no posting, reads no
costing status and imports nothing from pricing, so a drift on the pricing side
leaves it green. It is a one-sided test and always was — deliberately, because
when it was written the other side did not exist.

**The agreement is unbuildable until the accept half is wired, which is why
this is recorded rather than papered over.** Nothing on the recording path calls
:func:`hold_an_unrecognised_quantity`, so no posting and no held row are ever
produced by the same event; there is no case in which the two definitions can be
compared. The commit that gives the recording path a caller is the one that can
assert an event marked `unresolved` is also the event the close refuses over,
and it is the commit that should.

The structural half — that a held name can never become a declaration, by
relation or by identity — is a property of the model registry and of this
module's source, and lives in
``apps/platform/tests/test_quarantine_invariants.py`` next door. The one thing
that gate cannot see, a declaration written through a PARAMETER, is closed here
instead by ``TestNothingIsAutoRegistered``, which counts and re-reads the
declaration rows either side of every path.
"""
from datetime import datetime, timedelta, timezone as utc
from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.platform.event_types.models import (
    EventType,
    Measurement,
    QuarantinedKey,
    RESOLUTION_DISMISSED,
    RESOLUTION_MAPPED,
    RESOLUTION_REGISTERED,
    RESOLUTION_UNRESOLVED,
    UNRECOGNISED_EVENT_TYPE,
    UNRECOGNISED_MEASUREMENT_KEY,
)
from apps.platform.event_types.quarantine import (
    AlreadyResolved,
    NotTheHeldName,
    NotThisTenants,
    PeriodHoldsUnresolvedValues,
    WrongDeclaration,
    dismiss_as_non_economic,
    hold_an_unrecognised_event_type,
    hold_an_unrecognised_quantity,
    map_to_a_declaration,
    refuse_a_silent_close,
    register_the_held_name,
    unresolved_in_period,
)
from apps.platform.tenants.models import Tenant
from core.vocabulary import (
    COSTING_METHOD_CALCULATED,
    SOURCE_KIND_CALLER_SUPPLIED,
    UNIT_TOKEN,
)

#: A period, and a repair that happens months after it. Every timestamp below
#: is an explicit past instant rather than an offset from now, because the one
#: thing these tests are about is two moments being told apart — and a fixture
#: that derived the event's time from the clock the repair reads would be
#: asserting the property using the very thing that could break it.
JANUARY = datetime(2026, 1, 15, 9, 30, tzinfo=utc.utc)
JANUARY_OPENS = datetime(2026, 1, 1, tzinfo=utc.utc)
JANUARY_CLOSES = datetime(2026, 2, 1, tzinfo=utc.utc)
FEBRUARY_OPENS = JANUARY_CLOSES
FEBRUARY_CLOSES = datetime(2026, 3, 1, tzinfo=utc.utc)


def _tenant(name="T"):
    return Tenant.objects.create(name=name)


def _event_type(tenant, key="acme.embed", **kwargs):
    kwargs.setdefault("costing_method", COSTING_METHOD_CALCULATED)
    return EventType.objects.create(tenant=tenant, key=key, **kwargs)


def _measurement(event_type, code="prompt_tokens", **kwargs):
    kwargs.setdefault("unit", UNIT_TOKEN)
    kwargs.setdefault("source_kind", SOURCE_KIND_CALLER_SUPPLIED)
    return Measurement.objects.create(event_type=event_type, code=code, **kwargs)


# ---------------------------------------------------------------------------
# Accept — nothing is discarded, nothing is zeroed
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNothingIsThrownAway:
    """A supplier has already charged for this. It is kept."""

    def test_an_unrecognised_event_type_is_accepted_rather_than_refused(self):
        """The door does not close. That is the whole of "accept".

        The natural implementation of "UBB does not know this name" is to raise
        — and it is wrong for a reason no error message can recover: the money
        has already been spent, and refusing the event deletes UBB's only
        record of it.
        """
        tenant = _tenant()

        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        assert held.pk is not None
        assert held.unrecognised == UNRECOGNISED_EVENT_TYPE
        assert held.is_unresolved

    def test_the_name_is_held_exactly_as_it_arrived(self):
        """Preserved verbatim, because a normalised name is a guess.

        Folding case or trimming punctuation to make a name "tidier" is UBB
        deciding what the tenant meant — and the tenant is about to be asked
        exactly that question. What they are shown has to be what they sent.
        """
        tenant = _tenant()
        as_sent = "  ACME.Embed-v2  "

        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key=as_sent,
            quantities={}, occurred_at=JANUARY)

        held.refresh_from_db()
        assert held.event_type_key == as_sent

    def test_the_number_survives_a_round_trip_undisturbed(self):
        """"Nothing is zeroed", stated about the column that could zero it.

        A numeric column has a scale. The declaration that would say which
        scale is legal for this name is precisely the declaration that does not
        exist — so a quantity written into one UBB chose is a quantity partly
        thrown away, and the tenant would be resolving a number that is no
        longer the one they sent.
        """
        tenant = _tenant()
        declared = _event_type(tenant)
        awkward = "0.000000000000000001"

        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity=awkward,
            occurred_at=JANUARY)

        held.refresh_from_db()
        assert held.quantity == awkward

    def test_a_name_too_long_to_be_legal_is_still_accepted(self):
        """The garbage most likely to arrive, and the one a bound would refuse.

        A client that concatenated something into its call name sends a name
        LONGER than any declared key may be. That is precisely the event whose
        supplier cost is real and whose name is wrong — so a length check at
        the door would refuse the one case the record exists for, and would do
        it while reporting a validation error rather than a lost charge.
        """
        tenant = _tenant()
        far_too_long = "acme.embed/" + "x" * 500

        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key=far_too_long,
            quantities={}, occurred_at=JANUARY)

        held.refresh_from_db()
        assert held.event_type_key == far_too_long
        assert len(far_too_long) > EventType._meta.get_field("key").max_length

    def test_an_unplaceable_event_keeps_every_number_it_carried(self):
        """The bag, because for this case nothing else in UBB holds it.

        `docs/plans/2026-07-31-provider-supplied-cost-decision.md` §3.4 draws
        the line: an event whose Event Type is unknown is NOT recorded as a
        usage event — "held outside the record until registered" — because
        there is nothing to record it as. So the numbers it carried exist here
        or nowhere, and a row without them would make the eventual replay
        uncostable while looking complete.
        """
        tenant = _tenant()

        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={"prompt_tokens": 4096,
                        "reasoning_tokens": Decimal("0.000000000000000001")},
            occurred_at=JANUARY)

        held.refresh_from_db()
        assert held.quantities == {"prompt_tokens": "4096",
                                   "reasoning_tokens": "0.000000000000000001"}

    def test_a_number_that_was_absent_is_not_a_number_that_was_zero(self):
        """The distinction a zeroing implementation destroys.

        "No quantity arrived under this name" and "a quantity of zero arrived"
        are different facts about what the supplier did, and only one of them
        means nothing was consumed. A column that answered "0" to both would
        make the second unprovable and the first invisible.
        """
        tenant = _tenant()
        declared = _event_type(tenant)

        absent = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity="",
            occurred_at=JANUARY)
        zero = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity="0",
            occurred_at=JANUARY)

        assert absent.quantity == ""
        assert zero.quantity == "0"

    def test_an_unrecognised_quantity_names_the_event_type_it_arrived_under(self):
        """The Event Type here is DECLARED — only the quantity was not.

        Which is what makes the two cases different records to resolve: this
        one already knows which declaration the tenant is working within, and
        the other does not know anything.
        """
        tenant = _tenant()
        declared = _event_type(tenant)

        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity="12",
            occurred_at=JANUARY)

        assert held.unrecognised == UNRECOGNISED_MEASUREMENT_KEY
        assert held.event_type_key == declared.key
        assert held.measurement_key == "reasoning_tokens"

    def test_a_held_quantity_is_reported_as_unaccounted_for_until_resolved(self):
        """AC 2's second half, paid as far as slice 2 can pay it — read this.

        The ticket asks that the event be "marked not fully costed". **No such
        mark exists in slice 2 and cannot**: the costing status is slice 3's by
        #193 §L, and there is no posting here to carry one. So the honest thing
        this slice can assert is the QUERY — that an event with a held name is
        discoverable as unaccounted-for by the same read the period close uses,
        and stops being so on resolution. That is what slice 3's column will be
        computed from.

        Asserted through ``unresolved_in_period`` rather than through
        ``held.is_unresolved``, and the difference is the point: the second
        would be re-reading the field the resolution had just written, which
        passes whatever the read does and would go on passing if the read broke.
        """
        tenant = _tenant()
        declared = _event_type(tenant)

        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity="12",
            occurred_at=JANUARY)

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == (held,)

        register_the_held_name(held, _measurement(declared,
                                                  code="reasoning_tokens"))

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == ()


# ---------------------------------------------------------------------------
# Quarantine — never auto-registered, however many times it arrives
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestNothingIsAutoRegistered:
    """The fence that matters most: a typo cannot become vocabulary."""

    def test_a_name_arriving_again_and_again_declares_nothing(self):
        """Repetition is not evidence, and this is where that gets decided.

        "It has arrived a hundred times, it must be real" is the reasoning that
        turns a misspelling into a line on an invoice. It is also indistinguish-
        able from a client deployed with a typo in it, which is the commoner
        case — so the count buys nothing and the fence holds at any number.
        """
        tenant = _tenant()

        for _ in range(25):
            hold_an_unrecognised_event_type(
                tenant=tenant, event_type_key="acme.embed",
                quantities={}, occurred_at=JANUARY)

        assert EventType.objects.count() == 0
        assert Measurement.objects.count() == 0

    def test_an_unrecognised_quantity_declares_nothing_either(self):
        """The same fence beneath a declaration that DOES exist.

        This is the tidier temptation: the Event Type is known, so adding one
        more quantity to it looks like housekeeping rather than like inventing
        billing vocabulary. It is the same act.
        """
        tenant = _tenant()
        declared = _event_type(tenant)
        _measurement(declared)

        for _ in range(25):
            hold_an_unrecognised_quantity(
                tenant=tenant, event_type_key=declared.key,
                measurement_key="reasonning_tokens", quantity="7",
                occurred_at=JANUARY)

        assert list(declared.measurements.values_list("code", flat=True)) == [
            "prompt_tokens"]

    def test_every_event_keeps_its_own_row_and_its_own_moment(self):
        """Why the rows are not folded into a counter.

        Four thousand events under one held name have four thousand original
        timestamps, and replay is from the event's own. A row standing for all
        of them could offer none of them, so the aggregate that looks like an
        obvious saving is the thing that would make the next requirement
        unimplementable.
        """
        tenant = _tenant()
        moments = [JANUARY + timedelta(hours=hour) for hour in range(3)]

        for moment in moments:
            hold_an_unrecognised_event_type(
                tenant=tenant, event_type_key="acme.embed",
                quantities={}, occurred_at=moment)

        assert sorted(QuarantinedKey.objects.values_list("occurred_at",
                                                         flat=True)) == moments

    def test_resolving_writes_no_declaration_and_alters_none(self):
        """The gap the source rule next door cannot close, closed here.

        ``test_quarantine_invariants.py`` walks this module's source for a
        declaration write, and one shape is beyond any syntactic rule: the
        declaration arrives as a PARAMETER, so ``declaration.save()`` names
        nothing a walker can tie to a class. That is not a hypothetical hole —
        it is the shape all three remediation paths are built around.

        So it is closed by effect rather than by spelling. Every declaration in
        the tenant's catalogue is read before and after all three paths run,
        including the lifecycle columns: creating one fails, and so does
        publishing somebody's draft on their behalf, which is the tidier
        version of the same over-reach.
        """
        tenant = _tenant()
        declared = _event_type(tenant, key="acme.embed")
        quantity = _measurement(declared, code="prompt_tokens")

        def snapshot():
            return (
                sorted(EventType.objects.values_list(
                    "key", "declaration_status", "published_revision")),
                sorted(Measurement.objects.values_list("code", "event_type_id")),
            )

        before = snapshot()
        mapped = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)
        registered = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="prompt_tokens", quantity="7",
            occurred_at=JANUARY)
        dismissed = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.healthcheck",
            quantities={}, occurred_at=JANUARY)

        map_to_a_declaration(mapped, declared)
        register_the_held_name(registered, quantity)
        dismiss_as_non_economic(dismissed)

        assert snapshot() == before


# ---------------------------------------------------------------------------
# Replay — the three remediation paths, and the timestamp each replays from
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestMappingToAnExistingDeclaration:
    """Path one: "we already declare this, they spelled it differently"."""

    def test_the_held_name_records_the_declaration_it_now_means(self):
        tenant = _tenant()
        declared = _event_type(tenant, key="acme.embed")
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)

        map_to_a_declaration(held, declared)

        held.refresh_from_db()
        assert held.resolution == RESOLUTION_MAPPED
        assert held.resolved_key == "acme.embed"
        assert not held.is_unresolved

    def test_a_quantity_maps_to_a_declaration_beneath_its_own_event_type(self):
        tenant = _tenant()
        declared = _event_type(tenant)
        quantity = _measurement(declared, code="prompt_tokens")
        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="promt_tokens", quantity="41",
            occurred_at=JANUARY)

        replay = map_to_a_declaration(held, quantity)

        assert replay.measurement_key == "prompt_tokens"
        assert replay.event_type_key == declared.key

    def test_mapping_to_a_quantity_under_another_event_type_is_refused(self):
        """Declarations are Event-Type-local (#193 §C2), and so is the repair.

        The same code beneath two Event Types is two independent records that
        happen to share a spelling — so "map it to the prompt_tokens one" is an
        ambiguous instruction unless UBB refuses the one that is not beneath
        this event's own declaration.
        """
        tenant = _tenant()
        mine = _event_type(tenant, key="acme.embed")
        somebody_elses = _measurement(_event_type(tenant, key="acme.rerank"))
        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=mine.key,
            measurement_key="promt_tokens", quantity="41",
            occurred_at=JANUARY)

        with pytest.raises(WrongDeclaration):
            map_to_a_declaration(held, somebody_elses)

    def test_mapping_to_the_held_name_itself_is_refused(self):
        """Mapping means "it was always this other thing", so it must differ.

        A declaration whose key equals the held name cannot be what this event
        failed to match — if it existed at that spelling, nothing was ever
        unrecognised. What the caller means is a registration, and the two are
        kept apart because they record different tenant decisions.
        """
        tenant = _tenant()
        declared = _event_type(tenant, key="acme.embed")
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        with pytest.raises(NotTheHeldName):
            map_to_a_declaration(held, declared)

    def test_mapping_to_another_tenants_declaration_is_refused(self):
        """The one direction this feature must never point.

        A repair that reached across tenants would attribute one tenant's
        supplier cost to another's invoice — and it would do it through a
        screen whose whole purpose is picking a declaration off a list.
        """
        tenant = _tenant()
        theirs = _event_type(_tenant("Other"), key="acme.embed")
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)

        with pytest.raises(NotThisTenants):
            map_to_a_declaration(held, theirs)

    def test_mapping_an_event_type_to_a_quantity_is_refused(self):
        """The two kinds resolve to different things, and mixing them is caught.

        An unrecognised Event Type resolves to an Event Type. Handing it a
        quantity would record a declaration key that means something else
        entirely, in a column a replay reads.
        """
        tenant = _tenant()
        quantity = _measurement(_event_type(tenant))
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)

        with pytest.raises(WrongDeclaration):
            map_to_a_declaration(held, quantity)


@pytest.mark.django_db
class TestRegisteringTheHeldName:
    """Path two: "this is real, declare it" — the tenant's act, never UBB's."""

    def test_the_declaration_the_tenant_made_is_recorded_against_the_name(self):
        """UBB does not create it here; it is handed one and records it.

        The service takes the declaration as an argument rather than building
        one, which is what makes "never auto-register" a property of the code
        rather than a promise: this path cannot run without a tenant having
        already made the declaration by the ordinary route.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        declared = _event_type(tenant, key="acme.embed")
        register_the_held_name(held, declared)

        held.refresh_from_db()
        assert held.resolution == RESOLUTION_REGISTERED
        assert held.resolved_key == "acme.embed"

    def test_registering_a_quantity_records_the_code_that_was_declared(self):
        tenant = _tenant()
        declared = _event_type(tenant)
        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="reasoning_tokens", quantity="41",
            occurred_at=JANUARY)

        quantity = _measurement(declared, code="reasoning_tokens")
        replay = register_the_held_name(held, quantity)

        assert replay.measurement_key == "reasoning_tokens"

    def test_registering_under_a_different_spelling_is_refused(self):
        """The line between the two paths, enforced from this side.

        Registering means the arrived name BECOMES vocabulary. If the tenant
        wanted a different spelling then the arrived name is not becoming
        anything, and what they have described is a mapping — which records a
        different decision and reads differently to anyone auditing it later.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)

        declared = _event_type(tenant, key="acme.embed")
        with pytest.raises(NotTheHeldName):
            register_the_held_name(held, declared)


@pytest.mark.django_db
class TestDismissingAsNonEconomic:
    """Path three: "this reaches UBB but it never cost anything"."""

    def test_a_dismissal_names_no_declaration_and_replays_nothing(self):
        """The one path with no replay, and that is the meaning of it.

        A health check or a debug call is not a costable thing, so there is
        nothing to re-cost. Returning a replay here would put a non-economic
        name back on the path a cost travels, which is the whole of what the
        tenant just said it is not.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.healthcheck",
            quantities={}, occurred_at=JANUARY)

        assert dismiss_as_non_economic(held) is None

        held.refresh_from_db()
        assert held.resolution == RESOLUTION_DISMISSED
        assert held.resolved_key == ""
        assert held.resolved_at is not None


@pytest.mark.django_db
class TestAResolutionHappensOnce:
    """A second resolution would silently overwrite the first one's record."""

    @pytest.mark.parametrize("second", [
        lambda held, declared: map_to_a_declaration(held, declared),
        lambda held, declared: register_the_held_name(held, declared),
        lambda held, declared: dismiss_as_non_economic(held),
    ])
    def test_a_resolved_name_cannot_be_resolved_again(self, second):
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)
        dismiss_as_non_economic(held)

        declared = _event_type(tenant, key="acme.embed")
        with pytest.raises(AlreadyResolved):
            second(held, declared)

    def test_the_refusal_reads_the_row_rather_than_this_instance(self):
        """A stale instance is the ordinary way two operators collide.

        Two people open the same held name; one resolves it; the second one's
        object still says unresolved. Asking the instance would let the second
        repair overwrite the first, and the audit record would show only the
        later one — the same reasoning ``EventType.revise_declaration`` gives
        for asking the row.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)
        stale = QuarantinedKey.objects.get(pk=held.pk)
        dismiss_as_non_economic(held)

        assert stale.is_unresolved
        with pytest.raises(AlreadyResolved):
            dismiss_as_non_economic(stale)


@pytest.mark.django_db
class TestReplayIsFromTheOriginalMoment:
    """A cost incurred in one period must not surface in another."""

    def test_the_replay_carries_the_event_time_and_not_the_repair_time(self):
        """The headline, and the one number this whole record exists to keep.

        Somebody fixes a spelling in August. The call happened in January and
        the supplier billed it in January. A replay stamped with the repair
        date moves real supplier cost between two closed periods, and both of
        them are then wrong — the one that lost it and the one that gained it.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)
        declared = _event_type(tenant, key="acme.embed")

        replay = map_to_a_declaration(held, declared)

        held.refresh_from_db()
        assert replay.effective_at == JANUARY
        assert held.resolved_at > JANUARY
        assert replay.effective_at != held.resolved_at

    def test_the_replay_carries_the_declared_name_rather_than_the_typo(self):
        """Replaying the misspelling would re-run the failure it repairs."""
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={}, occurred_at=JANUARY)
        declared = _event_type(tenant, key="acme.embed")

        replay = map_to_a_declaration(held, declared)

        assert replay.event_type_key == "acme.embed"
        assert replay.measurement_key == ""

    def test_the_replay_carries_the_number_under_the_name_it_now_has(self):
        """Verbatim from the door to the re-costing — and re-keyed.

        The bag a replay hands on is looked up by name, and the name it
        arrived under matches no declaration by construction: that is the
        reason the row exists. Keying it by the typo would hand re-costing a
        bag it cannot read, which is the original failure repeated one step
        later.
        """
        tenant = _tenant()
        declared = _event_type(tenant)
        held = hold_an_unrecognised_quantity(
            tenant=tenant, event_type_key=declared.key,
            measurement_key="promt_tokens", quantity="0.000000000000000001",
            occurred_at=JANUARY)

        replay = map_to_a_declaration(held, _measurement(declared))

        assert replay.quantities == {
            "prompt_tokens": "0.000000000000000001"}
        assert replay.tenant_id == tenant.id

    def test_an_unplaceable_event_replays_with_everything_it_carried(self):
        """The other branch, where the bag is the only copy there has ever been."""
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed-v2",
            quantities={"prompt_tokens": 4096}, occurred_at=JANUARY)

        replay = map_to_a_declaration(held, _event_type(tenant, key="acme.embed"))

        assert replay.quantities == {"prompt_tokens": "4096"}
        assert replay.effective_at == JANUARY


# ---------------------------------------------------------------------------
# The period-close safeguard
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestAPeriodDoesNotCloseSilently:
    """"Closed" must never mean "closed except for the parts nobody read"."""

    def test_a_period_holding_an_unresolved_name_refuses_to_close(self):
        tenant = _tenant()
        hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        with pytest.raises(PeriodHoldsUnresolvedValues) as refusal:
            refuse_a_silent_close(tenant=tenant, opened_at=JANUARY_OPENS,
                                  closes_at=JANUARY_CLOSES)

        assert refusal.value.held == ("acme.embed",)

    def test_a_period_whose_names_are_all_resolved_closes(self):
        """The positive control, without which the safeguard is unsatisfiable.

        A refusal that fired whatever the state of the table would have to be
        switched off to close anything, and a safeguard nobody can satisfy is a
        safeguard somebody deletes.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)
        register_the_held_name(held, _event_type(tenant, key="acme.embed"))

        refuse_a_silent_close(tenant=tenant, opened_at=JANUARY_OPENS,
                              closes_at=JANUARY_CLOSES)

    def test_a_dismissed_name_does_not_block_the_close(self):
        """"Unresolved ECONOMIC values" — the tenant has said this is not one.

        Dismissal is the tenant answering the question the safeguard asks. A
        close that still refused afterwards would make dismissal meaningless
        and leave the period permanently unclosable.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.healthcheck",
            quantities={}, occurred_at=JANUARY)
        dismiss_as_non_economic(held)

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == ()

    def test_the_safeguard_reads_the_event_time_and_not_the_repair_time(self):
        """The two rules meeting, and the shape of the bug if either slips.

        A January call repaired in March belongs to January in both directions:
        it blocked January's close while it was held, and it must not appear in
        February's — which is what would happen to any implementation that
        placed a held name in a period by when somebody got round to it.
        """
        tenant = _tenant()
        held = hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == (held,)
        assert unresolved_in_period(tenant=tenant, opened_at=FEBRUARY_OPENS,
                                    closes_at=FEBRUARY_CLOSES) == ()

        register_the_held_name(held, _event_type(tenant, key="acme.embed"))
        assert timezone.now() > FEBRUARY_CLOSES

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == ()
        assert unresolved_in_period(tenant=tenant, opened_at=FEBRUARY_OPENS,
                                    closes_at=FEBRUARY_CLOSES) == ()

    def test_another_tenants_held_name_does_not_block_this_close(self):
        tenant = _tenant()
        hold_an_unrecognised_event_type(
            tenant=_tenant("Other"), event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY)

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == ()

    def test_the_window_excludes_the_instant_the_next_period_opens(self):
        """Half-open, so one event cannot block two closes.

        A closed interval would place an event falling exactly on the boundary
        in both months, and the same held supplier cost would refuse two
        different period closes.
        """
        tenant = _tenant()
        hold_an_unrecognised_event_type(
            tenant=tenant, event_type_key="acme.embed",
            quantities={}, occurred_at=JANUARY_CLOSES)

        assert unresolved_in_period(tenant=tenant, opened_at=JANUARY_OPENS,
                                    closes_at=JANUARY_CLOSES) == ()
        assert len(unresolved_in_period(tenant=tenant, opened_at=FEBRUARY_OPENS,
                                        closes_at=FEBRUARY_CLOSES)) == 1


# ---------------------------------------------------------------------------
# The row rules, at the database and in the validator
# ---------------------------------------------------------------------------

@pytest.mark.django_db
class TestTheHeldRowCannotBeIncoherent:
    """Every rule below is one a repair screen could otherwise write past."""

    def test_a_quantity_row_must_name_the_quantity(self):
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_MEASUREMENT_KEY,
                event_type_key="acme.embed", occurred_at=JANUARY)

    def test_an_event_type_row_may_not_name_a_quantity(self):
        """Nothing beneath an unrecognised Event Type was ever looked up."""
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", measurement_key="prompt_tokens",
                occurred_at=JANUARY)

    def test_a_resolution_without_a_date_is_refused(self):
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", occurred_at=JANUARY,
                resolution=RESOLUTION_MAPPED, resolved_key="acme.embed")

    def test_a_date_without_a_resolution_is_refused(self):
        """Checked in both directions: the row would read as open to a query
        and as finished to a person."""
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", occurred_at=JANUARY,
                resolution=RESOLUTION_UNRESOLVED, resolved_at=timezone.now())

    def test_a_dismissal_may_not_name_a_declaration(self):
        """The fourth remediation path, refused before anyone invents it."""
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", occurred_at=JANUARY,
                resolution=RESOLUTION_DISMISSED, resolved_at=timezone.now(),
                resolved_key="acme.embed")

    def test_a_mapping_must_say_what_the_name_now_means(self):
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", occurred_at=JANUARY,
                resolution=RESOLUTION_MAPPED, resolved_at=timezone.now())

    def test_a_remediation_outside_the_value_set_is_refused(self):
        tenant = _tenant()
        with pytest.raises(IntegrityError), transaction.atomic():
            QuarantinedKey.objects.create(
                tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                event_type_key="acme.embed", occurred_at=JANUARY,
                resolution="ignored", resolved_at=timezone.now())

    def test_the_validator_says_the_same_things_the_database_does(self):
        """A courtesy to the ordinary path (ADR-0007 §2), checked once.

        The database is the enforcement. This exists so a form or a repair
        screen gets a sentence rather than an ``IntegrityError``, and it is
        pinned here so the two cannot drift into disagreeing.
        """
        tenant = _tenant()
        row = QuarantinedKey(tenant=tenant,
                             unrecognised=UNRECOGNISED_MEASUREMENT_KEY,
                             event_type_key="acme.embed", occurred_at=JANUARY)

        with pytest.raises(ValidationError) as invalid:
            row.full_clean()

        assert "measurement_key" in invalid.value.message_dict

    def test_the_validator_refuses_a_name_it_arrived_without(self):
        tenant = _tenant()
        row = QuarantinedKey(tenant=tenant,
                             unrecognised=UNRECOGNISED_EVENT_TYPE,
                             event_type_key="", occurred_at=JANUARY)

        with pytest.raises(ValidationError) as invalid:
            row.full_clean()

        assert "event_type_key" in invalid.value.message_dict
