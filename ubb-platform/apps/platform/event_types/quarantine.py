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

**The safeguard is wired, and so is the quantity half of the accept path.**
:func:`refuse_a_silent_close` is consulted by ``TenantBillingService.close_period``
(#329), which calls it directly — ADR-001 lets any product import the platform
kernel, and a read contract or a hook in between would be a second definition
of "unresolved" one indirection away from the one built here.
:func:`hold_an_unrecognised_quantity` is called by ``UsageService._record_core``
(#428): the compute spine answers ``measurement_not_declared`` for a name a
declared Event Type's declaration does not carry — on the branch that rates a
report against Cost Rates, and by #428's decision only there, since the other
three branches settle or leave the cost for a reason that is not the name —
and records the quantity on the receipt, and the recording path holds it
beside the posting in the same write, so the posting's reason and the held row
cannot exist apart. Building
the safeguard beside the table is what stopped it being re-derived —
differently — by whoever wired the close, and the same argument put the join's
hold on the recording path rather than in the spine, which a Resolution Run
re-runs over stored receipts.

**And so is the Event Type half (#568).** :func:`hold_an_unrecognised_event_type`
is called by ``UsageService._record_core`` too: an event naming an Event Type
whose ``costing.cost_declaration`` is ``None`` — nobody declared the key, or it
was declared and never published, which recording reads as the same thing
(#605) — is recorded as a posting whose cost is ``unresolved``, reason
``event_type_not_declared``, and whose price is ``unknown``, and the name is
held beside it in the same write. The hold keys on the read returning nothing,
never on whether a catalogue row exists, so a never-published key cannot take a
second path. It is the posting, not this row, that is "the record": spec §3.4's
"held outside the record until registered" is not adopted, because only a
posting can carry everything else the call said and a replay needs all of it.
An event naming NO Event Type names nothing to hold and is outside this (#567).

**What a remediation entitles reaches the event (#473 row 1).** Mapping or
registering a name hands its :class:`Replay` to every consumer registered in
``hooks.py``, inside the remediation's own transaction; metering's re-costs and
re-prices the event the name arrived on, from that event's own moment, with
every answer the tenant has given about that event applied
(:func:`the_tenants_answers`). Dismissing hands nothing on: a name the tenant
has said is not economic re-costs nothing (#473 row 2) — not now, and not after
its key is published — and the event keeps the cost it was recorded with.

**A held name is answered by a PUBLICATION, and a publication answers it (#568:
"replays … once the name is declared").** Production reads only an Event
Type's last publication (#605), so a map or a register naming a declaration no
publication carries is refused (:class:`NotYetPublished`) — a name answered by
a draft would free the period close while nothing could ever cost its event.
And publishing is itself the tenant declaring the names it carries: every
undecided name held at an Event Type's key, or beneath it under a code its
publication carries, is registered and replayed
(:func:`answer_what_publications_declare`). That is the tenant's act, through
the route a tenant declares with; nothing here creates a declaration, so it is
not auto-registration.

**AFTER the publication commits, and never inside it (the consultant's review
of #618).** Publishing configuration and replaying historical events are
different responsibilities: a publication's transaction must not grow with the
backlog held under its key, and one event that cannot be answered — a call
that named another supplier, say — must not make a valid declaration
unpublishable. So ``EventType.publish`` commits the publication alone and rings
:func:`answer_after_the_publication_commits`, which enqueues the answering once
the commit lands; each held name is then answered in a transaction of its own,
and one that cannot be stays visibly held, blocking the close, with the rest
answered beside it. A Resolution Run answers what publications declare first,
too, so a run is the tenant's retry whenever the doorbell went unheard — and
answering again answers nothing twice.
"""
import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import NamedTuple
from uuid import UUID

from django.db import transaction
from django.utils import timezone

from core.exceptions import UBBError

from .hooks import hand_on
from .publication import last_published_declaration

logger = logging.getLogger(__name__)
from .models import (
    EventType,
    Measurement,
    QuarantinedKey,
    RESOLUTION_DISMISSED,
    RESOLUTION_MAPPED,
    RESOLUTION_REGISTERED,
    RESOLUTION_UNRESOLVED,
    RESOLUTIONS_NAMING_A_DECLARATION,
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


class NotYetPublished(QuarantineError):
    """No publication carries the declaration named, so it cannot answer.

    Recording costs under an Event Type's last publication and never its draft
    (#605). A held name answered by a draft would leave the period close free
    while the event it arrived on could be costed by nothing — re-resolved
    under the answer, it would only be held again, with no row left to say so.
    Publish the declaration: a publication answers every held name it
    declares by itself, once it has committed
    (:func:`answer_what_publications_declare`).
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
    """What a remediation entitles: the event to re-cost, and the decision.

    It is the cost key (#193 §B2) — tenant, Event Type, measurement, timestamp
    — plus the numbers that arrived, and the identity of the recorded event
    they arrived on. ⚠ The consumer that re-costs (metering's
    `resolution_run.replay_the_held_event`) reads the ids and the moment: it
    re-resolves the posting from its own receipt with every answer on the
    event applied (:func:`the_tenants_answers`), because one row's re-keyed
    bag would lose the answers given about the event's other names. The key
    and the bag stay on the record as what this decision said. The identity is an id and not a relation: the kernel may
    not depend on a product's tables (ADR-001), and an id is a fact about what
    arrived rather than a pointer anything here follows.

    ``quantities`` is a bag on both branches even though the two branches fill
    it from different places, because what re-costs an event should not have to
    know which kind of repair produced it. On an unrecognised Event Type it is
    everything the event carried; on an unrecognised quantity it is the single
    pair that was not costable, keyed by the DECLARED name, since the posting
    holds the rest.

    ``effective_at`` is the moment the event happened. It is never the moment
    it was repaired, and it is a separate name from ``resolved_at`` on purpose
    — one field holding "the time" would be the bug this whole record exists to
    prevent, one rename away.

    ``held_name_id`` is the held row whose remediation entitled this replay:
    what re-costs the event names it, so an amount a replay completes can be
    explained by the decision that completed it.
    """

    tenant_id: UUID
    event_id: UUID
    held_name_id: UUID
    event_type_key: str
    measurement_key: str
    quantities: dict
    effective_at: datetime


# ---------------------------------------------------------------------------
# Accept
# ---------------------------------------------------------------------------

def hold_an_unrecognised_event_type(*, tenant, event_type_key, quantities,
                                    occurred_at, event_id):
    """Hold a name that matched no production declaration. Raises nothing at
    the door.

    ``event_type_key`` is written as it arrived: no case folding, no trimming,
    no punctuation tidied. The tenant is about to be asked what this name meant,
    and what they are shown has to be what they sent.

    ``quantities`` is the whole measured bag, and it is a required argument
    rather than an optional one because this row is the kernel's own account of
    what the event carried: the posting holds the bag too, and the kernel may
    not read it (ADR-001), so a repair screen and the ``Replay`` a remediation
    hands on read it here. Pass ``{}`` for a call that measured nothing.

    ``event_id`` is the recorded event the name arrived on — the posting
    written in the same savepoint, which a replay re-costs (#568).
    """
    return _hold(tenant=tenant, unrecognised=UNRECOGNISED_EVENT_TYPE,
                 event_type_key=event_type_key, measurement_key="",
                 quantity="", quantities=_as_text(quantities),
                 occurred_at=occurred_at, event_id=event_id)


def hold_an_unrecognised_quantity(*, tenant, event_type_key, measurement_key,
                                  quantity, occurred_at, event_id):
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

    ``event_id`` is that posting's, for the reason the Event Type hold above
    carries one.
    """
    return _hold(tenant=tenant, unrecognised=UNRECOGNISED_MEASUREMENT_KEY,
                 event_type_key=event_type_key,
                 measurement_key=measurement_key, quantity=as_sent(quantity),
                 quantities={}, occurred_at=occurred_at, event_id=event_id)


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


class Answered(NamedTuple):
    """What one pass of :func:`answer_what_publications_declare` did."""

    #: Names registered, each with its replay handed on.
    registered: int
    #: Names a publication answers and which stay held all the same — refused
    #: by name, or broken — each for the tenant to see and decide.
    still_held: int


def answer_what_publications_declare(*, tenant_id, key=None):
    """Register every undecided held name a PUBLICATION now answers, and
    hand each replay on — one name at a time (#568: "replays … once the name
    is declared"; the consultant's review of #618).

    A name is answered where a publication carries it: an Event Type held at
    a key that is now published, or a quantity held beneath a published Event
    Type whose publication carries its code. Each is
    :func:`register_the_held_name` — the same act, the same checks, the same
    replay — in a transaction of its OWN, so the answering of one never rides
    on another's: a refusal by name (:class:`QuarantineError` — the call named
    a supplier the Event Type does not, an answer would carry one quantity
    twice) leaves that name held for the tenant's decision, and so does
    anything else a replay breaks on, which is logged; the rest are answered
    beside it either way.

    **Idempotent, so it is safe to run again.** Undecided names only: a
    registered one has had its replay, and a dismissed one stays dismissed
    (#473 row 2). Run by the doorbell a publication rings once it commits
    (:func:`answer_after_the_publication_commits`) for its own key, and by
    every Resolution Run for the tenant — the retry, whenever the doorbell
    went unheard. Never inside a publication's transaction.
    """
    held_names = QuarantinedKey.objects.unresolved().filter(tenant_id=tenant_id)
    if key is not None:
        held_names = held_names.filter(event_type_key=key)
    answers, registered, still_held = {}, 0, 0
    for held in held_names.order_by("occurred_at", "id"):
        if held.event_type_key not in answers:
            answers[held.event_type_key] = _what_answers(tenant_id,
                                                         held.event_type_key)
        declaration = _the_declaration_for(held, *answers[held.event_type_key])
        if declaration is None:
            continue
        try:
            with transaction.atomic():
                register_the_held_name(held, declaration)
        except QuarantineError:
            still_held += 1
        except Exception:
            # After the publication committed, nothing may undo it, and a
            # contradiction in one held record is no reason to leave the names
            # beside it unanswered. The name stays held — the close still sees
            # it — and the break is told to whoever reads the log.
            logger.exception("quarantine.answer_failed",
                             extra={"data": {"held_name_id": str(held.pk)}})
            still_held += 1
        else:
            registered += 1
    return Answered(registered=registered, still_held=still_held)


def _what_answers(tenant_id, key):
    """The publication at ``key`` and the Event Type row it is the
    publication of — or `(None, None)` where nothing is published."""
    published = last_published_declaration(tenant=tenant_id, key=key)
    if published is None:
        return None, None
    return published, EventType.objects.get(tenant_id=tenant_id, key=key)


def _the_declaration_for(held, published, event_type):
    """The declaration a publication answers ``held`` with, or `None`."""
    if published is None:
        return None
    if held.unrecognised == UNRECOGNISED_EVENT_TYPE:
        return event_type
    if held.measurement_key not in {quantity.code
                                    for quantity in published.measurements}:
        return None
    # The row the publication pinned; a draft that has withdrawn it since
    # answers nothing until it is published again.
    return event_type.measurements.filter(code=held.measurement_key).first()


def answer_after_the_publication_commits(*, tenant_id, key):
    """Ring, once the publication's transaction has committed, for the held
    names its key answers — and never inside it (the consultant's review of
    #618).

    The doorbell enqueues :func:`tasks.answer_held_names
    <apps.platform.event_types.tasks.answer_held_names>`, so a publication's
    transaction is the configuration alone and its length does not grow with
    the history held under the key. A broker that cannot be reached is logged
    and swallowed, exactly as the outbox's doorbell is: a raise here would
    fail a request whose publication has already committed, and a Resolution
    Run answers the same names whenever it runs. A publication rolled back
    rings nothing.
    """
    def ring():
        from .tasks import answer_held_names
        try:
            answer_held_names.delay(str(tenant_id), key)
        except Exception:
            logger.warning("quarantine.answer_dispatch_failed", exc_info=True,
                           extra={"data": {"tenant_id": str(tenant_id),
                                           "key": key}})

    transaction.on_commit(ring)


def dismiss_as_non_economic(held):
    """"This reaches UBB but it never cost anything." Returns no replay.

    A health check or a debug call is not a costable thing, so there is nothing
    to re-cost — and returning a replay would put a name the tenant has just
    said is not economic back onto the path a cost travels.

    **AND NOTHING RE-COSTS THE EVENT WITHOUT IT (#473 row 2, ruled
    2026-10-22).** Dismissal answers the period close's question and no other:
    the event keeps the cost and the price it was recorded with. The name is
    not an answer `the_tenants_answers` gives, so it keeps its spelling, and
    every later re-costing holds it again — none drops it from the bag and
    settles the rest.
    """
    _refuse_a_second_remediation(held)
    _remediate(held, RESOLUTION_DISMISSED, "")
    return None


def _target_key(held, declaration):
    """The declared key this held name may resolve to, or a refusal.

    The tenant is checked first and on its own, before anything about shape or
    locality, so that the cross-tenant case can never be reported as some
    tidier-sounding mismatch and dismissed as a screen bug.

    **And it must be PUBLISHED (#568, #473), which reverses what this
    function used to say.** It once refused to consult the lifecycle, because a
    declaration a tenant has just made is ``draft`` and requiring
    ``published`` would have made registration wait on a second, unrelated
    act. #605 made production read only the last publication, so a draft can
    answer for nothing; and publishing now registers the held names it
    declares by itself, so the second act is the registration. A quantity is
    published where its Event Type's last publication carries its code.
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
    published = last_published_declaration(
        tenant=held.tenant_id,
        key=declared_key if parent_key is None else parent_key)
    if published is None or (parent_key is not None and declared_key not in {
            quantity.code for quantity in published.measurements}):
        raise NotYetPublished(
            f"no publication carries '{declared_key}', and recording costs "
            f"under the last publication and never a draft (#605). Publish "
            f"it: a publication registers the held names it declares.")
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
    """Record the decision, then hand on the replay it entitles.

    The write is a conditional update rather than a ``save``: it is the point
    at which two concurrent repairs are told apart, and the condition is that
    the row is still unresolved. ``updated_at`` is set by hand because
    ``QuerySet.update`` does not run ``auto_now`` — the same reason
    ``EventType.revise_declaration`` sets it.

    **One transaction with what the decision entitles (#473 row 1).** A
    remediation naming a declaration hands its :class:`Replay` to every
    registered consumer (``hooks.hand_on``) before the transaction ends, and a
    consumer that fails takes the decision with it — a name recorded as mapped
    whose event was never re-costed would have left the period-close safeguard
    with nothing ever looking at it again. A dismissal hands nothing on.
    """
    now = timezone.now()
    with transaction.atomic():
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
        replay = _replay(held)
        hand_on(replay)
    return replay


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
                  event_id=held.event_id,
                  held_name_id=held.pk,
                  event_type_key=event_type_key,
                  measurement_key=measurement_key,
                  quantities=quantities,
                  effective_at=held.occurred_at)


class TenantsAnswers(NamedTuple):
    """What the tenant has decided about the held names on ONE recorded event,
    as the re-keying a re-costing applies (#473 row 1).

    Plain data, for the reason ``costing.py`` gives: the product that re-costs
    the event needs two facts and has no business holding rows it could save.
    """

    #: The declared key an unrecognised Event Type was mapped to or registered
    #: as, or ``None`` where this event's Event Type was never held or is still
    #: undecided — either way the event's own key is the one to cost under.
    event_type_key: str | None
    #: ``{held quantity name: the declared name it now means}`` for every
    #: quantity on this event the tenant has mapped or registered. A name still
    #: held, or dismissed, is absent: it keeps its spelling, so a re-costing
    #: holds it again — which is what keeps an undecided name undecided and a
    #: dismissed one from being re-costed (#473 row 2).
    measurement_keys: dict
    #: Whether the tenant dismissed any name on this event as non-economic. A
    #: re-costing leaves such an event alone, whatever is published later: it
    #: could only cost the event with the dismissed name or without it, and
    #: the ruling refuses both (#473 row 2).
    dismissed: bool
    #: Whether any name on this event is still undecided. A re-costing leaves
    #: such an event alone too: the decision comes first — a publication
    #: answering it, or a map — and costing around an undecided name would
    #: settle the call under a spelling, or a supplier, nobody has answered for.
    undecided: bool


def the_tenants_answers(*, tenant_id, event_id):
    """Every answer the tenant has given about the held names on one event.

    Asked of the WHOLE event rather than of the one row just remediated,
    because an event can carry two held names and a re-costing that applied
    only the latest answer would re-key one and hold the other again — and the
    first answer would then be lost to every later re-costing, since nothing
    else records it. One query, on ``ix_quarantined_key_event``.
    """
    event_type_key, measurement_keys = None, {}
    dismissed = undecided = False
    for unrecognised, measurement_key, resolution, resolved_key in (
            QuarantinedKey.objects
            .filter(tenant_id=tenant_id, event_id=event_id)
            .values_list("unrecognised", "measurement_key", "resolution",
                         "resolved_key")):
        if resolution == RESOLUTION_UNRESOLVED:
            undecided = True
        elif resolution == RESOLUTION_DISMISSED:
            dismissed = True
        elif resolution not in RESOLUTIONS_NAMING_A_DECLARATION:
            continue
        elif unrecognised == UNRECOGNISED_EVENT_TYPE:
            event_type_key = resolved_key
        else:
            measurement_keys[measurement_key] = resolved_key
    return TenantsAnswers(event_type_key=event_type_key,
                          measurement_keys=measurement_keys,
                          dismissed=dismissed, undecided=undecided)


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

    **Called by ``TenantBillingService.close_period`` (#329)**, before it
    reconciles, so a period that will not close does not first do the work of
    closing. Billing calls it directly, which is what this function being built
    beside the table was for: the one definition of "unresolved" is the one
    below, and there is no second one for a caller to drift from.

    It refuses on a held NAME and never on an unresolved COST. A held name is a
    tenant decision nobody has taken; a missing supplier figure may never
    arrive, and freezing a tenant's billing until it does would be a worse
    answer than closing on time and saying what was excluded.
    """
    held = unresolved_in_period(tenant=tenant, opened_at=opened_at,
                                closes_at=closes_at)
    if held:
        raise PeriodHoldsUnresolvedValues(opened_at, closes_at, held)
