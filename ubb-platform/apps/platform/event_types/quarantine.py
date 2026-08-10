"""Accept, quarantine, replay — what happens to a name UBB has never seen.

An event arrives naming an Event Type this tenant never declared, or carrying a
quantity code the declaration beneath it does not mention. Two answers suggest
themselves and both are wrong, which is why this module exists rather than a
branch somewhere on the recording path.

**Throwing it away throws away real supplier cost.** The call already happened
and the supplier has already charged for it. Refusing the event does not undo
the spend; it hides it, and the missing margin turns up a month later as a gap
nobody can account for.

**Registering it automatically makes a typo permanent.** A misspelling that
arrives twice would become declared billing vocabulary — on an invoice, under a
name no human chose. After that there is no test that tells it from a real one,
because it now looks exactly like one.

So: **accept** the event and preserve it whole; **quarantine** the unrecognised
name as unresolved, so the event is visibly not fully costed rather than
silently free; and on tenant-driven remediation **replay** the event *from its
original timestamp*. Never the repair date — a cost incurred in one period must
not surface in another because somebody fixed a spelling on a Tuesday.

**The three remediation paths, and why they are three.** Map it to a
declaration that already exists; register the name the tenant has just
declared; or dismiss it as non-economic. They record three different tenant
decisions, and collapsing any two would lose the one thing an auditor reading
this table later needs to know — which of them was made.

**Never auto-register, enforced rather than promised.** Nothing here creates a
declaration. :func:`register_the_held_name` is *handed* one the tenant made by
the ordinary route and does no more than record that it happened, so this
module cannot register a name even by accident.
``apps/platform/tests/test_quarantine_invariants.py`` holds that to the source.

**Nothing here is wired, and that is slice 2's shape rather than an omission.**
No recording path calls these functions, no costing status is written, and the
period-close path does not yet consult :func:`refuse_a_silent_close`. Slice 2
owns the declaration and the machinery; slice 3 owns every behaviour that reads
it (#193 §L). The safeguard is built now because it is a statement about what
this table means, and building it beside the table is what stops it being
re-derived — differently — by whoever wires the close.
"""
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from core.exceptions import UBBError

from .models import (
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

#: Which declaration each held name resolves to. An unrecognised Event Type is
#: answered by an Event Type; an unrecognised quantity by a Measurement beneath
#: the Event Type the event already matched. Stated as a mapping so that adding
#: a third kind of held name forces a decision here rather than falling through
#: whichever branch happened to be last.
RESOLVES_TO = {
    UNRECOGNISED_EVENT_TYPE: EventType,
    UNRECOGNISED_MEASUREMENT_KEY: Measurement,
}


class QuarantineError(UBBError):
    """A remediation that cannot mean what it says.

    Subclassed from UBB's own base rather than raised as ``Exception``, per
    ``docs/conventions/coding-standards.md``: a caller catching broad enough to
    swallow one of these would be catching everything.
    """


class AlreadyResolved(QuarantineError):
    """This name has already been remediated, and by somebody else's decision.

    The ordinary way two operators collide: both open the same held name, one
    resolves it, and the second one's screen still says unresolved. Letting the
    second repair land would overwrite the first — and the audit record would
    then show only the later one, which is the version least likely to be the
    one anybody remembers making.
    """

    def __init__(self, held):
        self.held = held
        super().__init__(f"'{held.held_name}' has already been resolved")


class NotThisTenants(QuarantineError):
    """The declaration belongs to another tenant.

    The one direction this feature must never point. A repair reaching across
    tenants attributes one tenant's supplier cost to another's invoice, and it
    would do it through a screen whose entire job is picking a declaration off
    a list.
    """


class WrongDeclaration(QuarantineError):
    """The declaration cannot be what this event failed to match.

    Either it is the wrong kind of record — a quantity offered for an
    unrecognised Event Type resolves to a name that means something else
    entirely — or it is declared beneath a different Event Type. Declarations
    are Event-Type-local (#193 §C2), so the same code beneath two Event Types
    is two independent records, and only one of them is beneath the declaration
    this event actually matched.
    """


class NotTheHeldName(QuarantineError):
    """This remediation is the other one.

    Mapping means "it was always this other thing", so the declaration's key
    must differ from the held name — if a declaration existed at that spelling,
    nothing was ever unrecognised. Registering means the held name BECOMES
    vocabulary, so it must not differ. Keeping the two apart is what makes the
    recorded decision readable a year later.
    """


class PeriodHoldsUnresolvedValues(QuarantineError):
    """The period cannot close silently, because part of it is unaccounted for.

    "The month is closed" must never mean "the month is closed except for the
    parts nobody looked at". Each held name below is a supplier charge that has
    not been costed and that no tenant has yet said is non-economic.
    """

    def __init__(self, opened_at, closes_at, held):
        self.opened_at = opened_at
        self.closes_at = closes_at
        self.held = tuple(row.held_name for row in held)
        super().__init__(
            f"the period {opened_at.isoformat()} to {closes_at.isoformat()} "
            f"holds {len(self.held)} unresolved value(s): "
            f"{', '.join(self.held)}")


@dataclass(frozen=True)
class Replay:
    """What re-costing an event needs, and nothing else.

    It is the cost key (#193 §B2) — tenant, Event Type, measurement, timestamp
    — plus the numbers that arrived. No posting identifier travels here: the
    kernel may not point into a product's tables (ADR-001), and for the case
    that matters most there is no posting to point at.

    ``quantities`` is a bag on both branches even though the two branches fill
    it from different places, because what re-costs an event should not have to
    know which kind of repair produced it. On an unrecognised Event Type it is
    everything the event carried, since nothing else holds it; on an
    unrecognised quantity it is the single pair that was not costable, since
    the posting holds the rest.

    ``effective_at`` is the moment the event happened. It is never the moment
    it was repaired, and it is a separate name from ``resolved_at`` on purpose
    — one field holding "the time" would be the bug this whole record exists to
    prevent, one rename away.
    """

    tenant_id: UUID
    event_type_key: str
    measurement_key: str
    quantities: dict
    effective_at: datetime


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------

def hold_an_unrecognised_event_type(*, tenant, event_type_key, quantities,
                                    occurred_at):
    """Hold a name that matched no declaration. Raises nothing at the door.

    ``event_type_key`` is written as it arrived: no case folding, no trimming,
    no punctuation tidied. The tenant is about to be asked what this name meant,
    and what they are shown has to be what they sent.

    ``quantities`` is the whole measured bag, and it is a required argument
    rather than an optional one because forgetting it loses the event's
    numbers permanently. An event UBB cannot place is not recorded as a
    posting at all (``docs/plans/2026-07-31-provider-supplied-cost-decision.md``
    §3.4, "held outside the record until registered") — this row is the only
    thing holding them. Pass ``{}`` for a call that measured nothing.
    """
    return _hold(tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                 event_type_key=event_type_key, measurement_key="",
                 quantity="", quantities=_as_text(quantities),
                 occurred_at=occurred_at)


def hold_an_unrecognised_quantity(*, tenant, event_type_key, measurement_key,
                                  quantity, occurred_at):
    """Hold a quantity code the matched declaration does not declare.

    ``event_type_key`` names a DECLARED Event Type here — the event matched a
    declaration and only the quantity beneath it was unrecognised, which is
    what makes this a different thing to resolve. It is recorded, never taken
    apart: a supplier is a Provider record's identity, never a substring of a
    key (#261).

    No bag travels with it: that event IS recorded as a posting, which carries
    its own measured quantities. What the posting cannot explain is the single
    number beside a name nothing matched, and that is what ``quantity`` holds —
    as text, because a numeric column has a scale and the declaration that
    would say which scale is legal for this name is precisely the one missing.
    """
    return _hold(tenant=tenant, unrecognised=UNRECOGNISED_MEASUREMENT_KEY,
                 event_type_key=event_type_key,
                 measurement_key=measurement_key, quantity=as_sent(quantity),
                 quantities={}, occurred_at=occurred_at)


def _as_text(quantities):
    """The measured bag with its values as text."""
    return {name: as_sent(value) for name, value in quantities.items()}


def as_sent(value):
    """A number as text, exactly and in the notation it was written in.

    A JSON number is a float once it has been through a serialiser, and the
    rounding that follows is the thing this record exists to refuse — so the
    bag is text-valued, and this is what puts a number into it.

    ``Decimal`` gets an explicit fixed-point format rather than ``str``,
    which is the one case where the obvious call is wrong: ``str(Decimal(
    "0.000000000000000001"))`` is ``'1E-18'``. Nothing is lost, but the tenant
    who is about to be asked what this number meant did not write that, and a
    repair screen showing them a value they do not recognise is the same defect
    as rounding it, arriving as a display. ``Decimal`` is exactly what a
    careful JSON reader produces, so this is the common path rather than a
    corner.
    """
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def _hold(**fields):
    """One row per event, saved. Nothing about the NAME can refuse it.

    ``full_clean`` is deliberately absent, and its absence is the accept rule.
    It enforces ``max_length`` — and the likeliest garbage a broken client
    sends is a name too LONG to be legal, which is exactly the event that must
    not be refused at the door. The columns that hold what arrived carry no
    length for the same reason. What still holds is every database constraint,
    which is where the row's own coherence is enforced (ADR-0007 §2); a caller
    that assembles an incoherent row gets an ``IntegrityError``, and no caller
    can assemble one through the two functions above.
    """
    row = QuarantinedKey(**fields)
    row.save()
    return row


# ---------------------------------------------------------------------------
# Replay — the three remediation paths
# ---------------------------------------------------------------------------

def map_to_a_declaration(held, declaration):
    """"We already declare this; they spelled it differently."

    Returns the :class:`Replay` for the event, stamped with the moment the
    event happened.
    """
    _refuse_a_second_remediation(held)
    declared_key = _target_key(held, declaration)
    if declared_key == held.held_name:
        raise NotTheHeldName(
            f"'{declared_key}' is the held name itself. A declaration at that "
            f"spelling is not what this event failed to match — if it existed, "
            f"nothing was unrecognised. Registering the name is the other path.")
    return _remediate(held, RESOLUTION_MAPPED, declared_key)


def register_the_held_name(held, declaration):
    """"This is real" — recorded against a declaration the TENANT made.

    The declaration arrives as an argument. Nothing here creates one, which is
    what makes "never auto-register" a property of this module rather than a
    promise about how carefully it is called.
    """
    _refuse_a_second_remediation(held)
    declared_key = _target_key(held, declaration)
    if declared_key != held.held_name:
        raise NotTheHeldName(
            f"'{declared_key}' is not the held name '{held.held_name}'. "
            f"Registering means the name that arrived becomes vocabulary; a "
            f"different spelling means it did not, and what that describes is "
            f"a mapping.")
    return _remediate(held, RESOLUTION_REGISTERED, declared_key)


def dismiss_as_non_economic(held):
    """"This reaches UBB but it never cost anything." Returns no replay.

    A health check or a debug call is not a costable thing, so there is nothing
    to re-cost — and returning a replay would put a name the tenant has just
    said is not economic back onto the path a cost travels.
    """
    _refuse_a_second_remediation(held)
    _remediate(held, RESOLUTION_DISMISSED, "")
    return None


def _target_key(held, declaration):
    """The declared key this held name may resolve to, or a refusal.

    The tenant is checked first and on its own, before anything about shape or
    locality, so that the cross-tenant case can never be reported as some
    tidier-sounding mismatch and dismissed as a screen bug.

    **The declaration's lifecycle is deliberately not consulted**, which looks
    like an omission and is not. A declaration a tenant has just made is
    ``draft`` by construction, so requiring ``published`` here would make
    registration — the commonest remediation of the three — impossible until a
    second, unrelated act. What a replay may legally cost against is a rating
    question, and rating is slice 3's entire subject (#193 §L); deciding it
    here would be this slice answering a question the next one owns.
    """
    expected = RESOLVES_TO[held.unrecognised]
    if not isinstance(declaration, expected):
        raise WrongDeclaration(
            f"a '{held.unrecognised}' resolves to a {expected.__name__}, and "
            f"this is a {type(declaration).__name__}. The two name different "
            f"things, and the key would be recorded in a column a replay "
            f"reads.")

    if expected is EventType:
        owner_id, parent_key, declared_key = (
            declaration.tenant_id, None, declaration.key)
    else:
        parent = declaration.event_type
        owner_id, parent_key, declared_key = (
            parent.tenant_id, parent.key, declaration.code)

    if owner_id != held.tenant_id:
        raise NotThisTenants(
            f"'{declared_key}' belongs to another tenant. A repair that "
            f"reached across tenants would put one tenant's supplier cost on "
            f"another's invoice.")
    if parent_key is not None and parent_key != held.event_type_key:
        raise WrongDeclaration(
            f"'{declared_key}' is declared beneath '{parent_key}', and this "
            f"event matched '{held.event_type_key}'. Declarations are "
            f"Event-Type-local (#193 §C2): the same code beneath two Event "
            f"Types is two independent records.")
    return declared_key


def _refuse_a_second_remediation(held):
    """Asked of the ROW, because the caller's instance may be stale.

    A clear refusal before any work is done. What actually enforces it is the
    conditional update in :func:`_remediate`, which cannot race with a
    concurrent repair; this exists so that the common case — an operator
    holding a screen somebody else has already dealt with — reads as the thing
    that happened rather than as a lost update.
    """
    still_held = (QuarantinedKey.objects.unresolved()
                  .filter(pk=held.pk).exists())
    if not still_held:
        raise AlreadyResolved(held)


def _remediate(held, resolution, declared_key):
    """Record the decision, then describe the replay it entitles.

    The write is a conditional update rather than a ``save``: it is the point
    at which two concurrent repairs are told apart, and the condition is that
    the row is still unresolved. ``updated_at`` is set by hand because
    ``QuerySet.update`` does not run ``auto_now`` — the same reason
    ``EventType.revise_declaration`` sets it.
    """
    now = timezone.now()
    moved = (QuarantinedKey.objects.unresolved()
             .filter(pk=held.pk)
             .update(resolution=resolution, resolved_key=declared_key,
                     resolved_at=now, updated_at=now))
    if not moved:
        raise AlreadyResolved(held)

    held.resolution = resolution
    held.resolved_key = declared_key
    held.resolved_at = now

    if resolution == RESOLUTION_DISMISSED:
        return None
    return _replay(held)


def _replay(held):
    """The cost key, with the ORIGINAL moment on it.

    Built from ``occurred_at`` and from the DECLARED key rather than the held
    one: replaying the misspelling would re-run the failure the repair just
    fixed.
    """
    if held.unrecognised == UNRECOGNISED_EVENT_TYPE:
        event_type_key, measurement_key = held.resolved_key, ""
        quantities = dict(held.quantities)
    else:
        event_type_key, measurement_key = held.event_type_key, held.resolved_key
        # Keyed by the DECLARED name, not the typo: this bag is what re-costing
        # looks the quantity up by, and the misspelling matches no declaration
        # by construction — it is the reason this row exists.
        quantities = {held.resolved_key: held.quantity}
    return Replay(tenant_id=held.tenant_id,
                  event_type_key=event_type_key,
                  measurement_key=measurement_key,
                  quantities=quantities,
                  effective_at=held.occurred_at)


# ---------------------------------------------------------------------------
# The period-close safeguard
# ---------------------------------------------------------------------------

def unresolved_in_period(*, tenant, opened_at, closes_at):
    """This tenant's still-held names whose EVENTS fall in the window.

    Placed by ``occurred_at`` and never by when anybody got round to the
    repair: a January call repaired in March belongs to January in both
    directions — it blocks January's close while it is held, and it must never
    appear in February's.

    The window is half-open. A closed one would place an event landing exactly
    on the boundary in two months at once, and the same held supplier charge
    would then refuse two different period closes.

    The two instants are keyword-only because they are the same type and the
    failure from swapping them is silent: an inverted window matches nothing,
    reports nothing held, and lets the period close — which is the exact
    outcome this function exists to prevent.
    """
    return tuple(QuarantinedKey.objects.unresolved()
                 .filter(tenant=tenant, occurred_at__gte=opened_at,
                         occurred_at__lt=closes_at)
                 .order_by("occurred_at", "id"))


def refuse_a_silent_close(*, tenant, opened_at, closes_at):
    """Raise if this period holds economic values nobody has accounted for.

    A refusal rather than a warning, and rather than a flag on the closed
    period: the two outcomes a caller must tell apart are "closed" and "not
    closed", and a function that returned either way makes the second easy to
    miss — which is the exact failure mode "does not close SILENTLY" names.

    Dismissed names do not appear here, and that is the word "economic" doing
    its work: dismissal is the tenant answering this question, and a close that
    still refused afterwards would leave the period permanently unclosable.

    **Nothing calls this yet.** The period close belongs to billing and slice 3
    owns wiring it (#193 §L). It is built beside the table it reads so that
    whoever wires it inherits this definition of "unresolved" rather than
    writing a second one.
    """
    held = unresolved_in_period(tenant=tenant, opened_at=opened_at,
                                closes_at=closes_at)
    if held:
        raise PeriodHoldsUnresolvedValues(opened_at, closes_at, held)
