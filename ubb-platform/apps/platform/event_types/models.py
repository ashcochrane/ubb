"""The tenant's Event Type catalogue — the vocabulary UBB meters against.

An Event Type is the aggregate root a tenant registers: what it is called, the
quantities it declares, which of those drive cost, and how that cost is arrived
at. The supplier it came from, the category it groups under and the declared
quantities themselves all live here too, so the app name under-describes its own
contents. That is deliberate (spec §A1): "catalogue" already names several other
things in live prose — the plan catalog, the webhook catalogue, the label
catalogue — so the app takes the name of the thing everything else hangs off
rather than a word a reader would have to disambiguate.

**Why this is not the app next door.** ``apps.platform.events`` is the
event-*delivery* app: the outbox, the handler checkpoints, dispatch, the webhook
catalogue and announcements. Its ``event_type`` is a webhook name such as
``usage.recorded`` — a UBB-owned notification, not a tenant-declared metered
call. Putting the tenant's metered vocabulary beside it would reproduce
ADR-0006's opening complaint, one word carrying two meanings, inside the kernel's
most-read module. ADR-0006 §7 is the rule that settles it: where infrastructure's
word collides with a domain word the infrastructure yields, and slice 0 made
exactly this move for exactly this reason when it took the platform's unit of
work out from under a framework noun.

**Why the kernel and not metering.** Rating reads this catalogue, the drawdown
reads its cost, analytics groups by it, the Code Builder reads it, and the
spend-ceiling work needs it in order to know *in advance* that the events it
governs are costable. What settles it is ADR-001's import matrix rather than a
headcount: anything may import the kernel, and no product may import another
except through a sanctioned channel — so a table several products read cannot sit
inside any one of them.

**What is here.** ``EventType`` — the aggregate root — the two optional
satellites it hangs off, ``Provider`` and ``EventCategory``, ``Measurement``,
the declared quantity, ``MeasurementConcept``, the opt-in grouping two
declarations may share, ``ReportedCostMapping``, where a supplier's own cost
figure is read from, and ``QuarantinedKey`` — the one record here that is
about a name the catalogue does NOT contain. Nothing here is wired to
anything: no rating path reads it, no cost resolves through it, no spend ceiling
consults it. Slice 2 owns the declaration; slice 3 owns every behaviour the
declaration selects. ``apps/platform/tests/test_event_type_satellite_invariants.py``
and its siblings ``test_event_type_declaration_invariants.py``,
``test_reported_cost_invariants.py`` and ``test_quarantine_invariants.py`` are
where those claims are held to the tree rather than asserted here.
"""
from decimal import Decimal, InvalidOperation
from typing import NamedTuple

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.exceptions import UBBError
from core.models import BaseModel
from core.money import SUPPORTED_CURRENCIES
from core.vocabulary import (
    AMOUNT_REPRESENTATION_VALUES,
    COSTING_METHOD_REPORTED,
    COSTING_METHOD_VALUES,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    DECLARATION_STATUS_VALUES,
    SOURCE_KIND_CALLER_SUPPLIED,
    SOURCE_KIND_CONSTANT,
    SOURCE_KIND_DERIVED,
    SOURCE_KIND_PROVIDER_RESPONSE,
    SOURCE_KIND_VALUES,
    SOURCE_SHAPE_ID_CUSTOM,
    SOURCE_SHAPE_ID_KNOWN_VALUES,
    UNIT_KNOWN_VALUES,
)

from .source_paths import advisories, path_errors

#: The shapes UBB can actually check a declared path against — every response
#: shape it knows, minus the one that names no shape at all. `custom` is a known
#: VALUE naming an unknown SHAPE, and keeping that distinction in one derived
#: name is what stops the two being conflated at the four sites that would
#: otherwise each have to remember it.
#:
#: Derived from the generated set rather than restated, so a shape UBB learns is
#: recognised on the day the registry learns it and never on the day somebody
#: remembers to update a second list.
RECOGNISED_RESPONSE_SHAPES = SOURCE_SHAPE_ID_KNOWN_VALUES - {SOURCE_SHAPE_ID_CUSTOM}

#: The record a `reported` Event Type must carry before it may be published,
#: named once, and the accessor by which the Event Type reaches it.
REPORTED_COST_MAPPING = "reported_cost_mapping"

#: The two source kinds a REPORTED COST may be declared with. The concept
#: declares four and they are shared with the quantities beside it; these two
#: are what survives the narrowing, and the other two are refused below for two
#: different reasons.
REPORTED_COST_SOURCE_KINDS = frozenset({SOURCE_KIND_PROVIDER_RESPONSE,
                                        SOURCE_KIND_CALLER_SUPPLIED})

#: What the generated integration must ask its caller for when the number is
#: not on the supplier's response. Named once here rather than spelled at the
#: builder, because the parameter a tenant's own code has to pass is part of
#: the declaration's published contract and not a rendering detail.
REPORTED_COST_PARAMETER = "reported_cost"

class KindRefusal(NamedTuple):
    """Why a source kind is not a reported cost, and whether that can change.

    ``permanent`` is the load-bearing half and it is a field rather than a turn
    of phrase in ``reason``, for the reason this whole slice keeps arriving at:
    a fact encoded only in prose is one that cannot be asked a question. A
    tenant who cannot tell "this was weighed and rejected" from "nothing has
    designed this yet" cannot tell whether to ask again, and the ticket that
    eventually designs the missing half needs to find its own obligation by
    something more reliable than reading for a caveat.
    """
    reason: str
    permanent: bool


#: What a refusal that is not permanent says about itself, composed onto the
#: reason rather than written into each one. Generated from the flag, so the
#: two can never disagree — a refusal whose prose claimed to be temporary while
#: its flag said otherwise would be the second encoding drifting from the first
#: on the one field a reader acts on.
V1_LIMITATION = (
    "This is a stated v1 limitation rather than a defect: it is refused "
    "because nothing has yet designed what it would mean, not because it was "
    "weighed and found wanting.")

#: The other two kinds the concept declares, and why each is not a reported
#: cost. Two entries rather than one list, because they are not one refusal:
#: the first is permanent and on the merits, and the second is a limitation a
#: later slice can lift.
#:
#: Their union with :data:`REPORTED_COST_SOURCE_KINDS` is exactly the concept,
#: which ``apps/platform/tests/test_reported_cost_invariants.py`` holds to the
#: registry: a fifth kind UBB learns would arrive here unruled, and the
#: database constraint below would refuse it with no reason anybody wrote.
REPORTED_COST_KIND_REFUSALS = {
    SOURCE_KIND_CONSTANT: KindRefusal(
        reason=(
            "a fixed per-call supplier cost is a configured cost rule, not a "
            "number that arrives with the event. 'Reported' cannot mean both "
            "'a number that arrives' and 'a number that never arrives' — "
            "admitting the second would make every rule about where the "
            "number comes from optional, which is the undeclared field this "
            "record exists to end. A flat supplier cost belongs on a rate."),
        permanent=True),
    SOURCE_KIND_DERIVED: KindRefusal(
        reason=(
            "a derived reported cost is refused. Its constraint is 'a named, "
            "declarative transformation', and that transformation vocabulary "
            "has no design and no owner yet — so there is nothing here for a "
            "declaration to name. Read the number from the supplier's "
            "response, or supply it from the caller; those two cover the "
            "cases this version has. A derived QUANTITY is unaffected."),
        permanent=False),
}

#: What a declared quantity's number may be. Two values, and the distinction is
#: the whole of it: a count of calls that arrived as 2.5 is a defect somewhere
#: upstream, and a declaration that cannot say so cannot catch it.
#:
#: UBB owns this pair and the registry declares no concept for it — legal, and
#: legal VISIBLY, which is what `tests/contracts/test_undeclared_value_sets.py`
#: exists to count. It stays a `choices=` list rather than becoming a concept
#: because nothing outside this model reads it: it is not on the contract, not
#: in the console's catalogue and not in the generated integration's vocabulary.
VALUE_TYPE_INTEGER = "integer"
VALUE_TYPE_DECIMAL = "decimal"
VALUE_TYPE_CHOICES = (
    (VALUE_TYPE_INTEGER, "Integer"),
    (VALUE_TYPE_DECIMAL, "Decimal"),
)
VALUE_TYPE_VALUES = frozenset(value for value, _ in VALUE_TYPE_CHOICES)

#: Which of the two names UBB failed to recognise. They are one record because
#: the answer to both is the same three words — accept, quarantine, replay —
#: and the same three remediation paths; they are told apart because what a
#: tenant maps an unrecognised Event Type to is a different declaration from
#: what they map an unrecognised quantity to.
UNRECOGNISED_EVENT_TYPE = "event_type"
UNRECOGNISED_MEASUREMENT_KEY = "measurement_key"
UNRECOGNISED_CHOICES = (
    (UNRECOGNISED_EVENT_TYPE, "Event Type"),
    (UNRECOGNISED_MEASUREMENT_KEY, "Measurement key"),
)
UNRECOGNISED_VALUES = frozenset(value for value, _ in UNRECOGNISED_CHOICES)

#: The three remediation paths, plus the state before any of them is taken.
#: Every one of them is something a TENANT does: UBB never picks one, because
#: each is a commercial call — mapping says two names were always one thing,
#: registering says a new thing exists, and dismissing says a name reaching
#: UBB was never economic at all.
#:
#: The unresolved state is the empty string rather than a token, so that "is
#: this still open" is one comparison in Python, in SQL and in a database
#: constraint, and so no row can be unresolved in one of those and resolved in
#: another.
RESOLUTION_UNRESOLVED = ""
RESOLUTION_MAPPED = "mapped"
RESOLUTION_REGISTERED = "registered"
RESOLUTION_DISMISSED = "dismissed"
RESOLUTION_CHOICES = (
    (RESOLUTION_UNRESOLVED, "Unresolved"),
    (RESOLUTION_MAPPED, "Mapped to an existing declaration"),
    (RESOLUTION_REGISTERED, "Registered as a new declaration"),
    (RESOLUTION_DISMISSED, "Dismissed as non-economic"),
)
RESOLUTION_VALUES = frozenset(value for value, _ in RESOLUTION_CHOICES)

#: The two resolutions that end with the held name MEANING a declared one. The
#: third does the opposite, and keeping the pair named once is what stops the
#: database constraint and the validator drifting into two different rules.
RESOLUTIONS_NAMING_A_DECLARATION = frozenset({RESOLUTION_MAPPED,
                                              RESOLUTION_REGISTERED})


class DeclarationIncomplete(UBBError):
    """Publication refused: the declaration does not yet pin what it must.

    An exception rather than a silent no-op, because the two outcomes a caller
    must tell apart are "published" and "not published", and a method that
    returned the record either way makes the second one easy to miss. What is
    missing travels on the exception so a caller can say which.
    """

    def __init__(self, blockers):
        self.blockers = tuple(blockers)
        super().__init__(
            f"the declaration is incomplete and stays in "
            f"{DECLARATION_STATUS_DRAFT}: {', '.join(self.blockers)}")


class DeclarationMisplaced(UBBError):
    """A part of one declaration cannot be moved to another.

    Raised rather than quietly handled, because the tidy-looking alternative —
    revise both Event Types and carry on — makes one edit do two things and
    leaves the second invisible. Withdrawing and re-declaring says the same
    thing in two acts that each read as what they are.
    """


class ValueTypeMismatch(UBBError):
    """This number is not the kind of number the declaration says it is.

    A refusal rather than a coercion, and that direction is the decision: the
    two repairs available — round it, or widen the declaration — are both
    somebody's commercial call, and a quantity silently rounded at the door is
    a quantity nobody can reconcile back to what the supplier reported.
    """



class PinnedDeclaration(models.Model):
    """What a record remembers about itself so a change to it can be SEEN.

    Publication pins a declaration, so every record that is part of one has to
    be able to answer *"is what I am about to write different from what was
    published?"* — and answering it wrongly in the safe-looking direction is how
    a tenant's deployed integration comes to be a reading of a contract that has
    moved.

    Shared rather than copied, and the reason is a defect this file already
    grew: the second copy of this machinery was written without
    ``update_fields`` widening, so a partial save un-published a declaration
    over a change that was never written and then cached the unwritten value as
    the baseline. Two encodings of one rule drift, and the one that drifts is
    the one nobody is looking at.

    A subclass declares :attr:`PINNED` and decides what a change MEANS. This
    holds only the reading of it.
    """

    #: The field names whose change makes a publication a new revision.
    PINNED = ()

    class Meta:
        abstract = True

    def _pinned_declaration(self):
        return tuple(getattr(self, name) for name in self.PINNED)

    def _pinned_baseline(self):
        """What the row's pinned elements said when this instance met them.

        Cached from the load where there was one, and otherwise READ, because
        the alternative is a guard that fails open on exactly the load a caller
        reaches for when they are being careful: ``objects.only("key")`` defers
        the rest, so a baseline taken only at load time would be absent, and
        absent is indistinguishable from unchanged. One query, and only on an
        instance that has no baseline and a row behind it.
        """
        cached = getattr(self, "_pinned_as_loaded", None)
        if cached is not None or self._state.adding or self.pk is None:
            return cached
        row = (type(self)._base_manager.filter(pk=self.pk)
               .values_list(*self.PINNED).first())
        return tuple(row) if row is not None else None

    @classmethod
    def from_db(cls, db, field_names, values):
        """Remember what was published, so a change to it can be seen.

        Only when every pinned element was actually read — a deferred load
        cannot answer the question and does not pretend to. What covers that
        case is :meth:`_pinned_baseline`, which reads it rather than assuming
        it.
        """
        instance = super().from_db(db, field_names, values)
        if set(cls.PINNED) <= set(field_names):
            instance._pinned_as_loaded = instance._pinned_declaration()
        return instance

    def _widened(self, update_fields, baseline, also=()):
        """``update_fields`` plus every pinned element that actually changed.

        Naming only the field being changed is the obvious way round a
        save-time guard, and a record that reacted to a change it did not write
        would be in a third state nobody declared. Widening by what CHANGED
        rather than by the whole pinned tuple keeps the caller's narrowing
        wherever it was honest.
        """
        if update_fields is None:
            return None
        changed = {name for name, was in zip(self.PINNED, baseline)
                   if getattr(self, name) != was}
        return tuple(set(update_fields) | changed | set(also))

    def _remember_pinned(self, update_fields):
        """Cache the baseline only where the save actually wrote all of it.

        Otherwise forget it, so the next question is answered by reading the
        row. A cache that recorded a value the database does not hold would
        make the very next change read as no change at all — which is the
        failure this whole mechanism exists to prevent, arriving through the
        mechanism itself.
        """
        wrote_all = (update_fields is None
                     or set(self.PINNED) <= set(update_fields))
        self._pinned_as_loaded = self._pinned_declaration() if wrote_all else None


class DeclarationPart(PinnedDeclaration):
    """A record that is PART of one Event Type's declaration, and behaves like one.

    Two of them exist — the declared quantity and the reported-cost mapping —
    and everything below was written twice before it was written here. That is
    not a tidiness argument: :class:`PinnedDeclaration` above records that the
    second copy of the baseline machinery shipped without ``update_fields``
    widening and un-published declarations over changes that were never
    written, and the third copy went in beside it before review caught the
    shape. Two encodings of one rule drift, and the one that drifts is the one
    nobody is looking at.

    What a part does that its parent does not: declaring one, changing one, or
    withdrawing one is a **revised publication** of the Event Type above it,
    because the code a tenant generated and deployed was generated against the
    declaration that included it.
    """

    #: The field by which this part hangs off its Event Type. A name rather
    #: than an assumption, so a part that spells it differently declares that
    #: rather than silently losing every rule below.
    PARENT = "event_type"

    class Meta:
        abstract = True

    def save(self, *, update_fields=None, **kwargs):
        """A change to a part revises the publication above it.

        Including ADDING one: a published Event Type that grows a required
        quantity, or a mapping, is a different declaration from the one a
        tenant generated their integration against.

        ``update_fields`` is widened by whichever pinned elements actually
        changed. Naming only the field being changed is the obvious way round a
        save-time guard, and a declaration returned to draft over a change the
        row never received would be a third state nobody declared.

        ``QuerySet.update()`` goes round this as it goes round every
        model-level guard in this repository — ADR-0007 §2 is explicit that
        these are a courtesy to the ordinary path and never the enforcement.
        """
        self._refuse_reparenting()
        baseline = self._pinned_baseline()
        revised = baseline is None or self._pinned_declaration() != baseline
        if revised and baseline is not None:
            update_fields = self._widened(update_fields, baseline)

        super().save(update_fields=update_fields, **kwargs)
        self._remember_pinned(update_fields)
        if revised:
            self.parent.revise_declaration()

    def delete(self, *args, **kwargs):
        """Withdrawing a part revises the publication too.

        The declaration a tenant's deployed integration was generated against
        no longer describes what UBB will accept, which is the same event as a
        changed path arriving at it from the other direction.

        A real delete rather than the data plane's soft delete
        (``docs/conventions/coding-standards.md``): that rule protects rows
        carrying money history, and a part of a declaration carries none —
        withdrawing one is an edit to a declaration. ``Provider`` earns
        ``retired_at`` because supplier COGS attribution keys on its identity;
        nothing keys on a part's. The ticket that first attaches a posting to a
        declaration is the one that can revisit this, and the one that could
        test the answer.
        """
        parent = self.parent
        outcome = super().delete(*args, **kwargs)
        parent.revise_declaration()
        return outcome

    @property
    def parent(self):
        return getattr(self, self.PARENT)

    def _refuse_reparenting(self):
        """A part belongs to the declaration it was declared under.

        Moving one is two edits wearing the clothes of one, and the half it
        hides is the damaging half: the Event Type it LEFT keeps its published
        status while losing a part of what was published — for the mapping,
        that is a live `reported` declaration with nowhere to read its cost
        from, which is precisely what :meth:`EventType.publication_blockers`
        exists to prevent and never gets asked again after publication.
        Withdraw it and declare a new one: each of those revises the right
        publication, and both are visible.

        Read from the ROW rather than from a cached load, on the same footing
        as :meth:`_pinned_baseline` and for the same reason — a guard that
        answered "unchanged" because nobody told it otherwise would fail open
        on exactly the careful caller who loaded the record narrowly.
        """
        if self._state.adding or self.pk is None:
            return
        column = f"{self.PARENT}_id"
        was = (type(self)._base_manager.filter(pk=self.pk)
               .values_list(column, flat=True).first())
        if was is None or was == getattr(self, column):
            return
        raise DeclarationMisplaced(
            f"this {type(self).__name__} was declared under Event Type {was} "
            f"and cannot be moved to {getattr(self, column)}. A part belongs "
            f"to the declaration it is part of: moving one leaves the Event "
            f"Type it left published while a part of what was published is "
            f"gone. Withdraw it and declare a new one under the other Event "
            f"Type — each of those revises the publication it should.")


class Provider(BaseModel):
    """The supplier behind a call — a per-tenant record, optional on an Event Type.

    **Why an entity and not a string.** Supplier cost resolution keys on this
    record's identity — the primary key — and never on parsing a supplier's name
    out of an Event Type key. A tenant may rename ``key`` (it is their own handle
    for their own supplier, and handles get corrected); the identity everything
    else holds does not move when they do. Parsing the name out of a key would
    have made the two inseparable, so a rename would silently re-attribute cost,
    and a key that happens to contain a dot or a slash would have decided what a
    call cost. That is the whole reason this is a record.

    **Retired, never deleted.** ``retired_at`` stops new use and leaves the past
    readable. Deleting would silently rewrite it: historical postings would lose
    their attribution and stop being reportable, which is the failure a finance
    owner discovers a quarter later and cannot repair. Same rule, and the same
    reasoning, as the Grouping Field registry next door.

    The manager is deliberately unfiltered, and there is deliberately no
    ``selectable()`` beside it. Retirement is about what may be *attached* next,
    never about what may be *read* — so hiding retired rows by default would
    make reading last quarter the clever path and the wrong answer the easy one.
    The filter that refuses a retired supplier belongs to the ticket that first
    attaches one to something, which is the ticket that can also test that the
    refusal happened. Declaring it here would be an unconsumed read in a slice
    that owns declarations only.

    **Optional, and no fictitious row.** A tenant metering its own internal work
    has no supplier, and must not be made to invent one to satisfy a schema. An
    Event Type with no Provider is a normal Event Type. A fictitious Provider is
    a defect, not a workaround — it puts a name UBB invented into a tenant's own
    COGS attribution.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="providers")
    # The tenant's own handle. Renameable BY DESIGN — see the class docstring —
    # and a plain CharField rather than a slug, because UBB does not enumerate
    # or second-guess a tenant's own catalogue of suppliers and calls, and a
    # charset UBB invented would be doing exactly that to a supplier whose real
    # name carries a slash or a space. Matches the Grouping Field key next door.
    key = models.CharField(max_length=64)
    # Retire, never delete. NULL means live.
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_provider"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_provider_key"),
        ]

    def __str__(self):
        return f"Provider({self.key})"


class EventCategory(BaseModel):
    """An optional, tenant-defined grouping for Event Types. One level, current.

    Deliberately the smallest thing that answers the question asked of it, and
    the limits are worth stating because the originating decision required more
    than this and was later amended:

    * **No hierarchy.** One level. There is no parent, and adding one is a
      decision, not a refinement.
    * **Current, not effective-dated.** The effective-dating and the historical
      reproducibility that decision required were retired when the category left
      the pricing ladder and became analytics-only. Dating a value that reaches
      no money reproduces nothing — it would be machinery built for a
      requirement that no longer exists.
    * **Never a monetary input.** It cannot reach a cost or a price by any path.
      That is what makes the point above safe rather than merely cheap.
    * **Optional.** An Event Type with no category is a normal Event Type, not
      an incomplete one.

    It carries no ``retired_at``, and that absence is a ruling rather than an
    oversight: retirement earns its place on ``Provider`` because a Provider is
    load-bearing for historical *money* attribution. Nothing here is, so the
    boring shape wins until something asks for more.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="event_categories")
    # A plain CharField for the reason given on ``Provider.key``.
    key = models.CharField(max_length=64)

    class Meta:
        db_table = "ubb_event_category"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_event_category_key"),
        ]

    def __str__(self):
        return f"EventCategory({self.key})"


class EventType(PinnedDeclaration, BaseModel):
    """A tenant-declared metered call — the aggregate root the catalogue hangs off.

    What it owns: its key, one optional supplier, one optional primary category,
    how its supplier COGS is derived, which provider response shape its declared
    paths are written against, and a declaration lifecycle. The declared
    quantities and the reported-cost mapping arrive beneath it.

    **What it deliberately does not own**, stated because merged decisions were
    later amended and reading only the originating ones would rebuild all three:

    * **No grouping axes.** They were deleted outright from the cost key.
    * **No cost amount.** The cost key collapses to tenant + Event Type +
      measurement + timestamp; the exact-variant-then-explicit-default ladder is
      gone, so there is nothing on this record for an amount to hang off.
    * **No account-level record beneath the supplier.**

    Each of those is an absence, and an absence asserted in a docstring is a
    comment. They are held to the tree in
    ``apps/platform/tests/test_event_type_declaration_invariants.py``.

    **Operational variants are their own Event Types.** A batch endpoint and a
    standard endpoint with genuinely different supplier costs are two costable
    things, and averaging them produces a number that is wrong for both — so
    variants-are-not-identities was reversed for this case and declaring the
    variant separately is the supported shape. That is why nothing here relates
    one Event Type to another: a relation would be a claim that one variant's
    cost is not its own.
    """

    #: What publication pins (#193 §B7). The response shape, the structured
    #: paths and the reported-cost mapping all belong to the published contract
    #: because an incorrect mapping produces an incorrect COGS — and the key and
    #: the costing method are named here too, because both reach the generated
    #: integration directly: one names the call, the other decides what the
    #: integration must supply.
    #:
    #: The satellites are deliberately absent. The category reaches no money and
    #: appears in nothing generated, and the supplier is an input to cost
    #: resolution rather than to the code a tenant deploys — unpublishing a
    #: tenant's live integration because they re-filed it under a different
    #: analytics grouping would be a cost with no benefit on the other side.
    #: The structured paths turned out not to fit here, and neither did the
    #: mapping. Both arrived on rows BENEATH the Event Type (#263, #266), and a
    #: tuple of this record's own field names cannot reach them: ``getattr`` on
    #: a reverse relation answers with a row, and two different declarations on
    #: one row compare equal. They pin the publication all the same, through
    #: :meth:`revise_declaration`, which each child calls — which is the
    #: obligation the tripwire in ``event_types/tests/test_event_type.py``
    #: carried, now asked of the behaviour rather than of this tuple.
    PINNED = ("key", "costing_method", "source_shape_id", "source_shape_label")

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="event_types")
    # The tenant's own key for their own call. UBB never enumerates these: doing
    # so would make the registry a catalogue of the tenant's suppliers and
    # calls, which map #137 constraint 5 forbids UBB to ship. Its length matches
    # the free-text column it replaces, so the catalogue can hold every key a
    # tenant has already recorded against.
    key = models.CharField(max_length=100)

    # Both optional, both PROTECT. A tenant metering its own internal work has
    # no supplier and must not be made to invent one; and a supplier a
    # declaration still points at cannot be deleted out from under it, which is
    # the enforcement half of "retired, never deleted".
    provider = models.ForeignKey(Provider, on_delete=models.PROTECT,
                                 null=True, blank=True,
                                 related_name="event_types")
    category = models.ForeignKey(EventCategory, on_delete=models.PROTECT,
                                 null=True, blank=True,
                                 related_name="event_types")

    # The closed vocabularies, held BY REFERENCE: the values come from
    # `core.vocabulary` at every point that reads them — `clean` below and the
    # database constraints in `Meta` — so this model cannot keep a second copy
    # that drifts from the registry.
    costing_method = models.CharField(max_length=32)
    declaration_status = models.CharField(max_length=32,
                                          default=DECLARATION_STATUS_DRAFT)

    # The response-shape declaration, declared ONCE at the Event Type so two
    # quantities beneath it can never disagree about which client they are
    # mapped to. Either a shape UBB recognises, or a name the tenant gives a
    # wrapper of their own — never both, and never a name with no shape.
    source_shape_id = models.CharField(max_length=100, blank=True, default="")
    source_shape_label = models.CharField(max_length=200, blank=True, default="")

    # The publication, as two facts rather than one. `published_revision` counts
    # the DISTINCT declarations that have been published — it is what a
    # generated integration was generated against — and it does not move when a
    # declaration returns to draft, because the code the tenant already deployed
    # did not move either.
    published_revision = models.PositiveIntegerField(default=0)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_event_type"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_event_type_key"),
            # The closed sets, at the database. A closed concept that only a
            # `clean()` defends is open to anything that writes without
            # validating, which is most of what writes.
            models.CheckConstraint(
                condition=models.Q(costing_method__in=sorted(COSTING_METHOD_VALUES)),
                name="ck_event_type_costing_method",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    declaration_status__in=sorted(DECLARATION_STATUS_VALUES)),
                name="ck_event_type_declaration_status",
            ),
            # The half of the response-shape rule that never moves. WHICH
            # shapes UBB recognises is an open set and grows without a migration
            # (ADR-0003), so that half is validated rather than constrained;
            # that a name for a shape nobody declared is meaningless is true
            # whatever UBB learns.
            models.CheckConstraint(
                condition=(models.Q(source_shape_label="")
                           | ~models.Q(source_shape_id="")),
                name="ck_event_type_shape_label_needs_a_shape",
            ),
        ]

    def __str__(self):
        return f"EventType({self.key})"

    # -- what the declared quantities say about this Event Type ---------------

    def missing_required_measurements(self, quantities):
        """Which declared quantities this Event Type needed and did not get.

        The reason ``required_for_costing`` is a field rather than a comment:
        with it, UBB can tell *"this event is fully costed"* from *"this event
        is missing an input"*, and without it the two are the same silence.

        ``quantities`` is whatever arrived, by code. A code this Event Type
        never declared contributes nothing here — which is the ticket's
        headline stated as a return value. A misspelled quantity used to hit a
        ``continue`` on the price side and be silently free; now the
        declaration it failed to match is reported as missing, and the event is
        visibly not fully costed. What becomes of the unrecognised code itself
        — quarantine, remediation, replay — is #265's, and is deliberately not
        answered here: this method reports on DECLARATIONS.
        """
        arrived = set(quantities)
        return tuple(sorted(
            declared.code for declared in self.measurements.all()
            if declared.required_for_costing and declared.code not in arrived))

    # -- the declaration lifecycle -------------------------------------------

    def revise_declaration(self):
        """A change to a record BENEATH this declaration is a revised publication.

        The structured paths belong to the published contract exactly as the
        response shape does (#193 §B7) — an incorrect path produces an
        incorrect supplier cost — but they live on rows of their own, so
        ``PINNED`` cannot reach them and the child calls this instead.

        **"Is this published?" is asked of the ROW, not of this instance**, and
        that is the whole shape of the method. A child reaches its parent
        through ``self.event_type``, which may be an instance loaded before the
        declaration was published — and a stale ``draft`` in memory would make
        this a silent no-op, which is failing open on exactly the reading that
        matters. The conditional update also cannot race with a concurrent
        publication: either it finds a published row or the publication has not
        happened yet.

        ``QuerySet.update`` is used deliberately here, the one place in this
        file it is: it goes round the model-level guard in :meth:`save`, and
        there is nothing for that guard to do — this record's OWN pinned
        elements have not moved, and the status is what is being written.
        """
        moved = (type(self)._base_manager
                 .filter(pk=self.pk,
                         declaration_status=DECLARATION_STATUS_PUBLISHED)
                 .update(declaration_status=DECLARATION_STATUS_DRAFT,
                         updated_at=timezone.now()))
        if moved:
            self.declaration_status = DECLARATION_STATUS_DRAFT

    def publication_blockers(self):
        """What stands between this declaration and publication, if anything.

        One rule today: a declaration costed from a number the supplier reports
        has nowhere to read that number from until its mapping is declared, and
        publishing it would generate an integration that computes no cost at
        all. The mapping is a record declared beneath the Event Type (#266), one
        per Event Type, so its PRESENCE is the question asked here — not the
        costing method, which is why the test for this ships a positive control
        that attaches one and watches the blocker clear.

        A missing reverse one-to-one answers `None` through `getattr`'s default.
        That the relation IS one-to-one is what makes presence one comparison,
        and it is asserted rather than defended against here: a to-many would
        answer with a manager, which is never `None`, and this rule would clear
        for every `reported` declaration in the tree at once. The test next door
        names that shape so a change to it goes red where it is made.
        """
        if self.costing_method != COSTING_METHOD_REPORTED:
            return ()
        if getattr(self, REPORTED_COST_MAPPING, None) is None:
            return (REPORTED_COST_MAPPING,)
        return ()

    def publish(self):
        """Pin this declaration, or refuse and leave it where it can be edited.

        Publishing pins what the declaration says NOW, so what makes a
        publication a new revision is that it pins something different.
        Publishing a published declaration nobody has changed therefore moves
        nothing: there is no second declaration to have been generated against.
        The test that would otherwise be missing is the one for the natural
        sequence — change it, then publish it, with no save in between.
        """
        blockers = self.publication_blockers()
        if blockers:
            raise DeclarationIncomplete(blockers)
        baseline = self._pinned_baseline()
        if (self.declaration_status == DECLARATION_STATUS_PUBLISHED
                and baseline is not None
                and self._pinned_declaration() == baseline):
            return self

        self.declaration_status = DECLARATION_STATUS_PUBLISHED
        self.published_revision += 1
        self.published_at = timezone.now()
        # Publication IS the act of pinning the current declaration, so the
        # baseline moves with it. Without this, publishing a record that was
        # loaded published and then edited would be undone by the guard in
        # `save` below, which would be reading a baseline this call has just
        # replaced.
        self._pinned_as_loaded = self._pinned_declaration()
        self.save()
        return self

    # -- what makes a change a revision rather than a reinterpretation --------

    def save(self, *, update_fields=None, **kwargs):
        """A change to a pinned element of a published declaration un-publishes it.

        In ``save`` rather than in a service, because the rule is that the
        reinterpretation can never be SILENT — and anything a caller has to
        remember to route through is a rule that holds until the first caller
        who does not. ``update_fields`` is widened rather than honoured as
        given, for the same reason: naming only the field being changed is the
        obvious way round a save-time guard, and a status that said "draft"
        while the change that caused it went unwritten would be a third state
        nobody declared.

        ``QuerySet.update()`` goes round this, as it goes round every
        model-level guard in this repository — ADR-0007 §2 is explicit that
        these are a courtesy to the ordinary path and never the enforcement.
        What enforces the vocabulary itself is in ``Meta.constraints``.
        """
        baseline = self._pinned_baseline()
        if (baseline is not None
                and self.declaration_status == DECLARATION_STATUS_PUBLISHED
                and self._pinned_declaration() != baseline):
            self.declaration_status = DECLARATION_STATUS_DRAFT
            update_fields = self._widened(update_fields, baseline,
                                          also={"declaration_status"})

        super().save(update_fields=update_fields, **kwargs)
        self._remember_pinned(update_fields)

    # -- validation ----------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        if self.costing_method not in COSTING_METHOD_VALUES:
            errors["costing_method"] = (
                f"'{self.costing_method}' is not a costing method. UBB owns this "
                f"whole value set: {', '.join(sorted(COSTING_METHOD_VALUES))}.")
        if self.declaration_status not in DECLARATION_STATUS_VALUES:
            errors["declaration_status"] = (
                f"'{self.declaration_status}' is not a declaration status. UBB "
                f"owns this whole value set: "
                f"{', '.join(sorted(DECLARATION_STATUS_VALUES))}.")

        shape_error = self._response_shape_error()
        if shape_error:
            errors["source_shape_label"] = shape_error

        if errors:
            raise ValidationError(errors)

    def _response_shape_error(self):
        """One active response shape, named exactly once.

        The named extension for a second shape is a sparse mapping profile
        BENEATH this Event Type — never a duplicated Event Type, which would
        fork a money-bearing declaration to solve a rendering problem.
        """
        if not self.source_shape_id:
            if self.source_shape_label:
                return ("names a response shape no declaration carries. Declare "
                        "the shape this Event Type's paths are written against, "
                        "or leave both empty.")
            return None
        recognised = self.source_shape_id in RECOGNISED_RESPONSE_SHAPES
        if recognised and self.source_shape_label:
            return (f"gives '{self.source_shape_id}' a second name. UBB already "
                    f"recognises that shape, and two names for one shape are two "
                    f"answers to a question with one answer.")
        if not recognised and not self.source_shape_label:
            return (f"is empty, and UBB validates nothing against "
                    f"'{self.source_shape_id}' — it recognises no shape by that "
                    f"name. Name the wrapper, so a reader of this declaration "
                    f"can tell what the paths beneath it are written against.")
        return None


class MeasurementConcept(BaseModel):
    """Two quantities a tenant has SAID mean the same thing. Opt-in, analytics-only.

    An analyst wants one chart adding a Gemini call's ``prompt_tokens`` to an
    OpenAI call's ``input_tokens``. Nothing in either declaration says those are
    one quantity, and nothing could: the declarations are Event-Type-local by
    design, and the two integrations never had to agree about spelling to both
    be correct. This record is the tenant saying it, and it is the only thing
    that ever says it.

    **Both fences are about what a NAME is not allowed to decide.** A matching
    name never automatically proves equivalence — two declarations that happen
    to share a spelling stay apart until a tenant groups them, because UBB
    cannot tell a genuine duplicate from a collision and a wrong guess silently
    merges two unrelated quantities on somebody's chart. And a differing name
    never prevents aggregation: the opt-in is the whole mechanism, so spelling
    is not consulted in either direction.

    **Analytics-only, which is a set of absences.** It carries no amount, no
    currency and no rate; nothing but a declaration may point at it; and no
    rating, cost-resolution or spend-ceiling module can see it. Those are
    properties of the tree rather than of this docstring, and
    ``apps/platform/tests/test_event_type_declaration_invariants.py`` is where
    they are held to it.

    **It is not a Grouping Field, and the distinction is the reason it is its
    own record.** A Grouping Field binds a tenant's key to one of a fixed number
    of physical slots on the posting: it groups EVENTS, the slots are finite,
    and a slot spent here is a real analytics axis nobody else can have. This
    groups measurement RECORDS. It consumes no slot, appears nowhere in the slot
    map, and is not a role on that vocabulary.

    **It carries no ``retired_at``, and that is a ruling rather than an
    oversight** — the same one ``EventCategory`` records above, for the same
    reason. Retirement earns its place on ``Provider`` because a Provider is
    load-bearing for historical *money* attribution; nothing here is. What a
    tenant does with a heading they have finished with is unassign it, which
    the declarations' ``PROTECT`` makes them do explicitly rather than by a
    delete that silently un-groups last quarter.

    **"Concept" here is the domain's word, not the vocabulary registry's.** The
    registry's concepts are UBB-owned value sets with generated artifacts behind
    them; this is a tenant's own row, holding a tenant's own key, which UBB
    never enumerates. The collision is accepted for the same reason the app's
    name is (see the module docstring): the alternatives all describe it worse,
    and the two live nowhere near each other.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="measurement_concepts")
    # A plain CharField for the reason given on ``Provider.key``: this is the
    # tenant's own heading for their own chart, and a charset UBB invented
    # would be UBB deciding what an analyst may call their own quantity.
    key = models.CharField(max_length=64)

    class Meta:
        db_table = "ubb_measurement_concept"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_measurement_concept_key"),
        ]

    def __str__(self):
        return f"MeasurementConcept({self.key})"


class Measurement(DeclarationPart, BaseModel):
    """One declared quantity beneath an Event Type — the record this slice is for.

    Before this, the measured quantities reaching the pricing engine travelled
    in a bare JSON bag whose only validation was that the numbers were not
    negative, and **a misspelled quantity was silently free**: on the price side
    it hit a ``continue``, contributed nothing, and told nobody. Every attribute
    below exists because its absence was a way for a number to mean less than
    the reader thought it did.

    * **A code and a display name**, so a quantity can be referred to and read.
    * **A value type**, so a count that must be whole cannot arrive as a
      fraction.
    * **A unit**, so a reader of an invoice line can tell what was counted. Held
      by reference to the generated vocabulary and OPEN: a tenant may declare a
      unit UBB has never heard of, because the quantity a tenant sells is the
      tenant's to choose (#193 §C5).
    * **Whether its absence blocks a complete cost**, which is what lets UBB
      tell a fully costed event from one missing an input.
    * **A source kind**, held by reference, and **a structured source path** —
      where the number comes from, and how the builder is to reach it.
    * **Optionally, one Measurement Concept** — the tenant saying that this
      quantity and another differently-named one mean the same thing, so a
      chart may add them together. Opt-in, analytics-only, and absent by
      default: a declaration that carries none is a normal declaration.

    **Declarations are Event-Type-local, and that is the correctness boundary.**
    The same code on two Event Types is two independent records that happen to
    share a spelling, which is why the uniqueness constraint is on the pair.
    Name-equality was never what made a declaration right: one correctly named
    and mapped to the wrong supplier field is wrong, and an oddly named one
    mapped correctly is right. One tenant's two supplier integrations never have
    to agree about spelling to both be correct.

    **Only a declared quantity may participate in monetary calculation** — which
    is a property of this table rather than an instruction to a later reader.
    There is exactly one place a quantity can be declared, it is keyed by the
    Event Type, and this record carries no amount and no currency of its own
    (a reported supplier cost is money with a currency and is a SIBLING of these,
    not one of them — #193 §D2, #266). ``no-cost-amount`` in
    ``apps/platform/tests/test_event_type_declaration_invariants.py`` is what
    holds that to the tree.

    **Nothing rates against these.** No rating path reads this table; slice 3
    wires it. Unknown-key handling — quarantine, remediation, replay — is #265's,
    and the only thing said about it here is that an undeclared code contributes
    nothing to :meth:`EventType.missing_required_measurements`.
    """

    #: What a change to one of these revises. The publication pins the
    #: structured paths because an incorrect path produces an incorrect supplier
    #: cost (#193 §B7) — and once a path is pinned so is everything that decides
    #: what the generated integration does with it: which quantity it names,
    #: whether it must supply one, where it reads it and what shape the number
    #: is. ``display_name`` is deliberately absent: it names the quantity for a
    #: human and reaches no emitted behaviour, so returning a live integration
    #: to draft over a corrected caption would be a cost with nothing on the
    #: other side. ``concept`` is absent for the same reason and one more: an
    #: analyst re-filing two quantities under one heading changes nothing about
    #: what UBB will accept or what the integration must send, and a grouping
    #: that could un-publish a live integration would not be analytics-only.
    PINNED = ("code", "value_type", "unit", "required_for_costing",
              "source_kind", "source_path")

    event_type = models.ForeignKey(EventType, on_delete=models.CASCADE,
                                   related_name="measurements")
    # The tenant's own name for their own quantity, and UBB never enumerates
    # these either. Its length matches the Event Type's key beside it.
    code = models.CharField(max_length=100)
    display_name = models.CharField(max_length=200, blank=True, default="")

    value_type = models.CharField(max_length=16, choices=VALUE_TYPE_CHOICES,
                                  default=VALUE_TYPE_INTEGER)
    # OPEN, so there is no constraint on WHICH unit — only that there is one.
    # A quantity with no noun beside it is a number an invoice reader cannot
    # interpret, and that is the failure this column is here to stop.
    unit = models.CharField(max_length=64)

    # The flag that makes an incomplete cost visible instead of silent.
    required_for_costing = models.BooleanField(default=False)

    # The closed vocabulary, held BY REFERENCE — from `core.vocabulary` at
    # every point that reads it, `clean` below and the database constraint in
    # `Meta`, so this model cannot keep a second copy that drifts.
    source_kind = models.CharField(max_length=32)

    # Canonical segments, never an executable expression: the builder emits
    # more than one language, and a stored expression is portable to none of
    # them. `source_paths.py` owns the whole of what that means.
    source_path = models.JSONField(default=list, blank=True)

    # The opt-in grouping, and every part of this declaration is a fence.
    # OPTIONAL, because a quantity stands alone and an analytics heading can
    # never be a precondition for declaring one. SINGULAR, because "which
    # grouping is this quantity in" has one answer or an analyst gets a
    # different total depending on which one a query took. PROTECT, because a
    # grouping deleted out from under a declaration silently un-groups
    # historical numbers — the same rule, and the same reasoning, as the
    # supplier above. And deliberately NOT in `PINNED`: see `save` below.
    concept = models.ForeignKey(MeasurementConcept, on_delete=models.PROTECT,
                                null=True, blank=True,
                                related_name="measurements")

    class Meta:
        db_table = "ubb_measurement"
        constraints = [
            # THE LOCALITY, at the database. Two Event Types may each declare
            # `prompt_tokens`; one Event Type may not declare it twice.
            models.UniqueConstraint(fields=["event_type", "code"],
                                    name="uq_measurement_code"),
            models.CheckConstraint(
                condition=models.Q(source_kind__in=sorted(SOURCE_KIND_VALUES)),
                name="ck_measurement_source_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(value_type__in=sorted(VALUE_TYPE_VALUES)),
                name="ck_measurement_value_type",
            ),
            # The only thing a database can say about an OPEN set: not which
            # unit, but that one was declared.
            models.CheckConstraint(
                condition=~models.Q(unit=""),
                name="ck_measurement_unit_is_declared",
            ),
        ]

    def __str__(self):
        return f"Measurement({self.code})"

    # -- the value type, which is the point of declaring one ------------------

    def validate_value(self, value):
        """``value`` as an exact quantity, or refuse it. Never rounds.

        The check the bare bag could not make. A count of calls declared whole
        and reported as 2.5 is a defect upstream, and the two ways to make it
        go away — round it, or widen the declaration — are both somebody's
        commercial decision rather than this method's.

        A binary float is read through its shortest round-tripping text rather
        than through its exact binary expansion, because ``0.1`` in a supplier's
        JSON means a tenth and reading it as
        ``0.1000000000000000055511151231257827`` would be UBB inventing
        precision nobody sent. What the wire may carry, and where it is parsed,
        is slice 3's.
        """
        quantity = self._as_quantity(value)
        if (self.value_type == VALUE_TYPE_INTEGER
                and quantity != quantity.to_integral_value()):
            raise ValueTypeMismatch(
                f"{self.code} is declared as a whole number and {value!r} is "
                f"not one. UBB does not round a quantity to fit a declaration: "
                f"either the value is wrong or the declaration is, and both "
                f"repairs are a commercial decision.")
        return quantity

    def _as_quantity(self, value):
        """A quantity, or a refusal. ``True`` is not the number one.

        ``bool`` is a subclass of ``int`` in Python, so a flag reaching a
        quantity column passes every numeric test there is. It is refused by
        name for that reason and no other.
        """
        if isinstance(value, bool) or value is None:
            raise ValueTypeMismatch(
                f"{self.code} is a quantity and {value!r} is not a number.")
        try:
            quantity = Decimal(str(value)) if isinstance(value, float) \
                else Decimal(value)
        except (InvalidOperation, TypeError, ValueError):
            raise ValueTypeMismatch(
                f"{self.code} is a quantity and {value!r} is not a number.")
        if not quantity.is_finite():
            raise ValueTypeMismatch(
                f"{self.code} is a quantity and {value!r} is not a finite one.")
        return quantity

    # -- what UBB has to say, and will never do ------------------------------

    def declaration_advisories(self):
        """Everything UBB advises about this declaration. It never acts on any of it.

        Two kinds, one surface, because they are the same product stance seen
        twice: UBB says what looks wrong and changes nothing. A quiet rewrite of
        a tenant's own mapping — or of their own noun — is the failure mode
        being designed out, so advice is the entire product.
        """
        return (*self._unit_advisories(), *self._path_advisories())

    def _path_advisories(self):
        """The path, against the shape its Event Type declares."""
        return advisories(self.event_type.source_shape_id, self.source_path)

    def _unit_advisories(self):
        """A unit UBB has met, spelled another way.

        A unit outside the five UBB has met is **accepted in silence** — the
        concept is open, and advising on it would be UBB leaning on a tenant to
        use UBB's catalogue. What is worth saying is the near miss: `Tokens` and
        `token` are one noun spelled twice, and two spellings on two
        declarations read as two different things on one invoice.
        """
        declared = self.unit.strip()
        if not declared or declared in UNIT_KNOWN_VALUES:
            return ()
        folded = declared.lower().removesuffix("s")
        if folded not in UNIT_KNOWN_VALUES:
            return ()
        return (f"`{declared}` is how UBB spells `{folded}` after a change of "
                f"case or number. Both are accepted and UBB will not change "
                f"yours — but one noun spelled two ways across two declarations "
                f"reads as two different things on one invoice.",)

    # -- validation -----------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        if self.source_kind not in SOURCE_KIND_VALUES:
            errors["source_kind"] = (
                f"'{self.source_kind}' is not a source kind. UBB owns this "
                f"whole value set: {', '.join(sorted(SOURCE_KIND_VALUES))}.")
        if self.value_type not in VALUE_TYPE_VALUES:
            errors["value_type"] = (
                f"'{self.value_type}' is not a value type. UBB owns this whole "
                f"value set: {', '.join(sorted(VALUE_TYPE_VALUES))}.")
        if not self.unit.strip():
            errors["unit"] = (
                "a quantity needs a noun beside it, or a reader of an invoice "
                "line cannot tell what was counted. UBB records the spellings "
                "it has met and never bounds the set — declare your own.")

        grouping_error = self._grouping_tenant_error()
        if grouping_error:
            errors["concept"] = grouping_error

        problems = path_errors(self.source_path)
        obligation = None if problems else self._path_obligation_error()
        if problems:
            errors["source_path"] = [f"the source path {problem}"
                                     for problem in problems]
        elif obligation:
            errors["source_path"] = f"the source path {obligation}"

        if errors:
            raise ValidationError(errors)

    def _grouping_tenant_error(self):
        """A grouping belongs to one tenant, and so does the quantity it groups.

        The worst outcome available to a feature whose entire job is adding
        quantities together is adding somebody else's in, so the two tenants
        are compared rather than assumed equal. No database constraint can say
        this: the declaration's tenant is its Event Type's, a table away, and a
        check constraint cannot follow a foreign key. Held here on the same
        footing as every other rule in this file — a courtesy to the ordinary
        path (ADR-0007 §2), which is all a model-level rule ever is.
        """
        if self.concept_id is None or self.event_type_id is None:
            return None
        # The owner by a narrow read rather than by walking the relation: a
        # `concept_id` naming no row would raise `DoesNotExist` out of
        # `full_clean`, and a validator that can raise something other than a
        # `ValidationError` is one every caller has to wrap.
        owner = (MeasurementConcept.objects.filter(pk=self.concept_id)
                 .values_list("tenant_id", flat=True).first())
        if owner == self.event_type.tenant_id:
            return None
        return ("is not one of this tenant's groupings. A grouping is "
                "tenant-level, and one reaching across tenants would put one "
                "tenant's numbers on another's chart — which is the whole of "
                "what this feature does, aimed at the one place it must never "
                "point.")

    def _path_obligation_error(self):
        """Which source kinds owe a path, and which may not carry one.

        Only ``provider_response`` READS one, so only it needs one — and a path
        on any other kind would be a read nothing performs, sitting in the one
        column a builder is about to emit from. The kinds that owe something
        else owe something this slice has not designed: a `derived` quantity
        needs a named transformation and the transformation vocabulary has no
        design and no owner (#193 §D4), and a single path cannot express one.
        """
        if self.source_kind == SOURCE_KIND_PROVIDER_RESPONSE:
            if not self.source_path:
                return ("is empty, and a quantity read from the supplier's "
                        "response has to say where in it. Declare the segments, "
                        "or declare a source kind that reads no response.")
            return None
        if self.source_path:
            return (f"reads a supplier response, and this quantity is declared "
                    f"as '{self.source_kind}', which reads none. A path here "
                    f"would be emitted by nothing.")
        return None


class ReportedCostMapping(DeclarationPart, BaseModel):
    """Where a supplier's own cost figure comes from — a SIBLING of the quantities.

    When an Event Type is costed from a number the supplier reports, that number
    is the cheapest COGS UBB can have and its most important field was the one
    nobody declared. Every integrator hand-wrote *"the cost is
    ``response.usage.total_cost``, and it is in dollars"* into a repository UBB
    never sees, along with the ``* 1e6`` that turned it into micros. This record
    is that sentence, declared.

    **Why it is not one of the Measurements.** A Measurement is a quantity with
    a unit; this is money with a currency. Folding it into the quantities would
    make the unit meaningless or force it to mean "currency", give the value
    type a money shape, and put a figure governed by a single shared cost bound
    under a caller-set unbounded integer. It shares the *machinery* — the source
    declaration, the response shape inherited from the Event Type, structured
    path segments, the advisory — and none of the shape.

    **The source vocabulary is shared and then narrowed.** Two of the four kinds
    are a reported cost: read it from the response (which then requires a path),
    or have the caller supply it (which then requires the generated integration
    to ask). :data:`REPORTED_COST_KIND_REFUSALS` carries the other two and the
    two different reasons they are refused.

    **What the number means is declared, and never rounded.** The amount
    representation is held by reference to the generated vocabulary, and
    ``reported_cost.py`` owns the conversion: exact whole micros or a refusal,
    because the four rounding rules govern amounts UBB *computes* and this is
    one it *observes*.

    **The currency is pinned exactly once** — a fixed code here, or a structured
    path into the supplier's response, never both and never neither. A
    supplier-returned currency that disagrees with the pinned one makes the
    generated integration fail clearly rather than convert: v1 is
    single-currency with no FX, so there is no correct conversion to perform.

    *Why the fixed code is here and not on the Event Type.* Both were
    sanctioned, both hold one code per Event Type, and one of them had to be
    chosen — declaring it in both places would be two encodings of one fact
    (ADR-0006 §4). It goes where the number it denominates is declared, and
    keeping money off the Event Type keeps ``no-cost-amount`` next door able to
    say something absolute about that record.

    **Nothing behavioural is wired.** An Event Type declared with a mapping sits
    inert: no rating path reads this, and no cost resolves through it. Whether
    the reported cost and the diagnostic claimed-cost field on the wire are one
    field routed by costing method or two is explicitly owed to slice 3 and is
    deliberately not answered here.
    """

    #: Everything that reaches the generated integration, which is everything
    #: this record has other than its parent. An incorrect mapping produces an
    #: incorrect COGS, so all of it is what publication pins (#193 §B7).
    PINNED = ("source_kind", "source_path", "amount_representation",
              "currency", "currency_path")

    # One per Event Type, at the database, by the shape of the relation itself.
    # `publication_blockers` on the parent reads this accessor's PRESENCE, and
    # a to-many here would answer with a manager — never `None` — and quietly
    # clear the blocker for every `reported` declaration in the tree at once.
    event_type = models.OneToOneField(EventType, on_delete=models.CASCADE,
                                      related_name=REPORTED_COST_MAPPING)

    # The closed vocabularies, held BY REFERENCE from `core.vocabulary` at every
    # point that reads them — `clean` below and the constraints in `Meta` — so
    # this model cannot keep a second copy that drifts from the registry. The
    # source kind is constrained to the NARROWED set rather than the concept's
    # own, because the two refusals are as much a property of this record as the
    # two admissions are.
    source_kind = models.CharField(max_length=32)
    amount_representation = models.CharField(max_length=32)

    # Canonical segments, never an executable expression — `source_paths.py`
    # owns the whole of what that means, and both of these are the same kind of
    # thing as a declared quantity's path, read against the one response shape
    # the Event Type declares.
    source_path = models.JSONField(default=list, blank=True)
    currency_path = models.JSONField(default=list, blank=True)

    # Lowercase, per the convention every currency column in this repository
    # follows and the casing the payment rail itself uses. Blank exactly when
    # the currency arrives on the supplier's response instead.
    currency = models.CharField(max_length=3, blank=True, default="")

    class Meta:
        db_table = "ubb_reported_cost_mapping"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    source_kind__in=sorted(REPORTED_COST_SOURCE_KINDS)),
                name="ck_reported_cost_source_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    amount_representation__in=sorted(
                        AMOUNT_REPRESENTATION_VALUES)),
                name="ck_reported_cost_amount_representation",
            ),
            # EXACTLY ONE of the two ways to pin the currency. The half of the
            # rule that never moves, which is why it is here and the code's own
            # validity is not: WHICH currencies UBB can hold is a table in
            # `core.money` that grows, and a constraint over it would make
            # admitting a currency a schema migration. That a cost denominated
            # twice, or not at all, is meaningless is true whatever that table
            # says.
            models.CheckConstraint(
                condition=(models.Q(currency="") ^ models.Q(currency_path=[])),
                name="ck_reported_cost_currency_pinned_once",
            ),
        ]

    def __str__(self):
        return f"ReportedCostMapping({self.event_type_id})"

    # -- what the generated integration has to do -----------------------------

    def required_runtime_parameters(self):
        """What the caller's own code must pass, because UBB cannot read it.

        The builder's half of ``caller_supplied``: a cost that is not on the
        supplier's response has to arrive from somewhere, and the only place
        left is the call itself. Empty for a cost read from the response, which
        is the point — a declaration that returned the same answer for both
        would tell the builder nothing.
        """
        if self.source_kind == SOURCE_KIND_CALLER_SUPPLIED:
            return (REPORTED_COST_PARAMETER,)
        return ()

    def declaration_advisories(self):
        """Everything UBB advises about this mapping. It never acts on any of it.

        Both paths, against the one response shape the Event Type declares. The
        same stance the declared quantities take, and for the same reason: a
        quiet rewrite of a tenant's own mapping is the failure being designed
        out, so advice is the entire product.
        """
        shape = self.event_type.source_shape_id
        return (*advisories(shape, self.source_path),
                *advisories(shape, self.currency_path))

    # -- validation -----------------------------------------------------------

    def clean(self):
        super().clean()
        errors = {}

        kind_error = self._source_kind_error()
        if kind_error:
            errors["source_kind"] = kind_error
        if self.amount_representation not in AMOUNT_REPRESENTATION_VALUES:
            errors["amount_representation"] = (
                f"'{self.amount_representation}' is not an amount "
                f"representation, so what the supplier's number means is "
                f"undeclared and the conversion to micros is back to being "
                f"hand-written. UBB owns this whole value set: "
                f"{', '.join(sorted(AMOUNT_REPRESENTATION_VALUES))}.")

        currency_error = self._currency_error()
        if currency_error:
            errors["currency"] = currency_error

        self._collect_path_error(errors, "source_path", self.source_path,
                                 self._amount_path_obligation)
        self._collect_path_error(errors, "currency_path", self.currency_path,
                                 self._currency_path_obligation)

        if errors:
            raise ValidationError(errors)

    def _source_kind_error(self):
        """The narrowing, and the two refusals stated apart.

        The limitation notice is composed from the refusal's own flag rather
        than written into its text, so a refusal cannot claim to be temporary
        while the flag a later ticket will look for says it is not.
        """
        if self.source_kind in REPORTED_COST_SOURCE_KINDS:
            return None
        refusal = REPORTED_COST_KIND_REFUSALS.get(self.source_kind)
        if refusal is not None:
            return (refusal.reason if refusal.permanent
                    else f"{refusal.reason} {V1_LIMITATION}")
        return (f"'{self.source_kind}' is not a source kind. UBB owns this "
                f"whole value set: {', '.join(sorted(SOURCE_KIND_VALUES))} — "
                f"and a reported cost narrows it to "
                f"{', '.join(sorted(REPORTED_COST_SOURCE_KINDS))}.")

    def _currency_error(self):
        """Pinned exactly once, and pinned to something UBB can hold.

        The 'exactly once' half is also a database constraint; this is the
        courtesy that says which of the two mistakes was made. The 'can hold'
        half is only here, because the table it reads grows.
        """
        pinned = bool(self.currency)
        by_path = bool(self.currency_path)
        if pinned and by_path:
            return ("this cost is denominated twice — a fixed code and a path "
                    "into the supplier's response. Two encodings of one fact "
                    "disagree eventually, and the one that is wrong is always "
                    "the one nobody is looking at. Declare one.")
        if not pinned and not by_path:
            return ("this cost is denominated in nothing. Pin a currency here, "
                    "or declare the path the supplier returns one on — a "
                    "reported cost with no currency is a number an invoice "
                    "reader cannot compare to anything, and UBB will not "
                    "assume its own default on a tenant's behalf.")
        if pinned and self.currency not in SUPPORTED_CURRENCIES:
            if self.currency.lower() in SUPPORTED_CURRENCIES:
                return (f"'{self.currency}' is a currency UBB holds, spelled "
                        f"in capitals. UBB spells currency codes in lower "
                        f"case throughout — write '{self.currency.lower()}'.")
            return (f"'{self.currency}' is not a currency UBB can hold: it "
                    f"knows no minor unit for it, so an amount in it could "
                    f"never reach the payment rail. The currencies it holds "
                    f"are {', '.join(sorted(SUPPORTED_CURRENCIES))}.")
        return None

    def _collect_path_error(self, errors, field, segments, obligation):
        """The grammar first, then the obligation — never both about one path.

        A path that is not structured data has not yet reached the question of
        whether this kind owes one, and reporting both would be two complaints
        about one mistake.
        """
        problems = path_errors(segments)
        if problems:
            errors[field] = [f"the {field.replace('_', ' ')} {problem}"
                             for problem in problems]
            return
        owed = obligation()
        if owed:
            errors[field] = f"the {field.replace('_', ' ')} {owed}"

    def _amount_path_obligation(self):
        """Only the kind that READS a response owes a path, and only it may
        carry one: a path on a caller-supplied cost is a read nothing
        performs, sitting in the one column a builder is about to emit from."""
        if self.source_kind == SOURCE_KIND_PROVIDER_RESPONSE:
            if not self.source_path:
                return ("is empty, and a cost read from the supplier's "
                        "response has to say where in it. Declare the "
                        "segments, or declare the caller supplies the number.")
            return None
        if self.source_path:
            return (f"reads a supplier response, and this cost is declared as "
                    f"'{self.source_kind}', which reads none. A path here "
                    f"would be emitted by nothing.")
        return None

    def _currency_path_obligation(self):
        """A supplier-returned currency needs a supplier-read amount.

        The currency path is read out of the same response the amount is, under
        the one shape the Event Type declares. A mapping whose number comes from
        the caller reads no response at all, so it has none to take a currency
        out of — and the fixed code is the sanctioned way to pin it there.
        """
        if (self.currency_path
                and self.source_kind != SOURCE_KIND_PROVIDER_RESPONSE):
            return (f"reads a supplier response, and this cost is declared as "
                    f"'{self.source_kind}', which reads none. Pin the currency "
                    f"as a fixed code instead.")
        return None


class QuarantinedKeyQuerySet(models.QuerySet):
    """The one question anything asks of this table: what is still open."""

    def unresolved(self):
        return self.filter(resolution=RESOLUTION_UNRESOLVED)


class QuarantinedKey(BaseModel):
    """A name UBB has never seen, held rather than thrown away (#193 §B5, §C4).

    Something arrives naming an Event Type this tenant never declared, or
    carrying a quantity code beneath a declared Event Type that the declaration
    does not mention. Two answers suggest themselves and both are wrong.

    **Throwing it away throws away real money.** A supplier has already charged
    the tenant for that call. Discarding the event because UBB did not
    recognise a name does not make the cost go away; it makes it invisible, and
    the margin it eats is found a month later as a gap nobody can explain.

    **Registering it automatically makes a typo permanent.** A misspelling that
    arrives twice would become billing vocabulary — a declared name, on an
    invoice, that nobody chose. There is no later moment at which UBB could
    tell that name from a real one, because by then it looks exactly like one.

    So the answer is neither: **accept, quarantine, replay.** The event is
    accepted and preserved, the unrecognised name is held here and marked
    unresolved, and remediation is a thing a tenant does. This record is the
    held name.

    **What this record is not.** It is not a declaration and it is not on the
    way to becoming one. Registering the name is a tenant act that creates a
    declaration by the ordinary route, and this record then says only that it
    happened; nothing here is promoted, copied or migrated into the catalogue.
    That is why it relates to no declaration at all — see ``resolved_key``
    below — and ``apps/platform/tests/test_quarantine_invariants.py`` is where
    that claim is held to the model registry rather than asserted here.

    **One row per event, not one per distinct name.** Folding identical names
    into a counter is the obvious shape and it destroys the thing this record
    exists for: replay is *from the event's own timestamp*, and a row standing
    for four thousand events has four thousand original timestamps and can
    offer none of them. What a console wants — "this name arrived 4,000 times"
    — is a query over these rows, and ADR-0006 §4 says a fact derived like that
    is not stored anyway.

    **And no uniqueness constraint, which is the same ruling from the other
    side.** Four of the columns below are the cost key (#193 §B2), and a unique
    constraint over them would read as tidiness. What it would do is refuse the
    second of two events that genuinely share a timestamp — a refusal at the
    door, which is the one outcome this whole record exists to prevent.
    """

    #: Which of the two names was not recognised.
    #:
    #: UBB owns this pair and the registry declares no concept for it, the same
    #: ruling ``Measurement.value_type`` records above and for the same reason:
    #: nothing outside this app reads it. It is not on the public contract, not
    #: in the console's label catalogue and not in the vocabulary a generated
    #: integration carries. ``tests/contracts/test_undeclared_value_sets.py``
    #: is what keeps that legality VISIBLE rather than merely true.
    unrecognised = models.CharField(max_length=32,
                                    choices=UNRECOGNISED_CHOICES)

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="quarantined_keys")

    #: The two names, held exactly as they arrived. ``event_type_key`` is
    #: always populated: on an unrecognised quantity it names the declared
    #: Event Type the quantity arrived beneath, and on an unrecognised Event
    #: Type it is the name nothing matched. Neither is ever taken apart — a
    #: supplier is a Provider record's identity and never a substring of a key
    #: (#261).
    #:
    #: **Unbounded, and that is the accept rule at the storage layer.** The
    #: bound that governs a DECLARED key sits on the declaration, and this
    #: record is about the absence of one — so a length here would be UBB
    #: deciding how long a name a tenant is allowed to get wrong. It would also
    #: refuse exactly the likeliest garbage: a client that concatenated
    #: something into its call name sends a name too LONG to be legal, and a
    #: bounded column would raise at the door on the one event the whole record
    #: exists to keep.
    event_type_key = models.TextField()
    measurement_key = models.TextField(blank=True, default="")

    #: The number that arrived under the one unrecognised name, verbatim, as
    #: text. Measurement rows only.
    #:
    #: Text rather than a numeric column, and this is the whole of "nothing is
    #: zeroed": a numeric column has a scale, the declaration that would say
    #: which scale is legal is precisely the declaration that does not exist,
    #: and a quantity quietly rounded to fit a column UBB chose is a quantity
    #: partly discarded. Unbounded for the same reason the names above are.
    #:
    #: Empty means the event carried no number for this name — a different fact
    #: from a number that was zero, and a column that could not tell those
    #: apart would answer "0" to both.
    quantity = models.TextField(blank=True, default="")

    #: The whole measured bag, as it arrived. Event Type rows only, and the
    #: asymmetry with ``quantity`` above is a merged decision rather than an
    #: accident.
    #:
    #: ``docs/plans/2026-07-31-provider-supplied-cost-decision.md`` §3.4 draws
    #: the line: an event whose Event Type is unknown is **not recorded as a
    #: usage event** — "held outside the record until registered" — because
    #: there is nothing to record it *as*. So for that case this row is the
    #: only thing that holds what arrived, and a row without the numbers would
    #: make "nothing is discarded" false and the replay uncostable. An event
    #: whose Event Type is KNOWN is a first-class posting that carries its own
    #: bag, and copying it here would be storing a fact twice (ADR-0006 §4) —
    #: which is why that case holds only the single number above, the one thing
    #: the posting's bag cannot explain on its own.
    #:
    #: Values are text, for the reason ``quantity`` is: a JSON number goes
    #: through a float, and that is the rounding this record exists to refuse.
    quantities = models.JSONField(default=dict, blank=True)

    #: When the event happened. **The load-bearing column of this record.**
    #: Remediation happens whenever somebody gets round to it, and a cost
    #: incurred in one period must not surface in another because a spelling
    #: was fixed on a Tuesday. Everything downstream reads this and never
    #: ``resolved_at``.
    occurred_at = models.DateTimeField(db_index=True)

    # How it left quarantine, and when. Empty means it has not: an unresolved
    # row is an economic value nobody has accounted for, which is exactly what
    # the period-close safeguard reads.
    resolution = models.CharField(max_length=16, blank=True, default="",
                                  choices=RESOLUTION_CHOICES)
    resolved_at = models.DateTimeField(null=True, blank=True)

    #: What the held name now means: the key of the declaration a tenant mapped
    #: it to, or registered for it. Empty on a dismissal, because a name
    #: dismissed as non-economic means nothing — recording a declaration
    #: against it would be a mapping wearing a dismissal's name.
    #:
    #: A key rather than a foreign key, and it is a decision rather than a
    #: shortcut. A relation from here into the catalogue is the
    #: auto-registration path rebuilt as a graph: once a held typo POINTS at a
    #: declaration, the next event carrying that typo can be resolved through
    #: it without a tenant deciding anything — the fence that matters most,
    #: taken down by a foreign key nobody thought was about that. It would also
    #: let a quarantine row from two years ago refuse the deletion of a
    #: declaration, under ``PROTECT``, on behalf of a typo. What guarantees
    #: this key names something real is the service that writes it, which is
    #: handed the declaration and reads the key off it.
    #:
    #: Bounded where the three columns above are not, and the asymmetry is the
    #: point: this one always holds a key UBB itself declared, so it inherits
    #: that column's length. The unbounded ones hold what a caller sent.
    resolved_key = models.CharField(max_length=100, blank=True, default="")

    objects = QuarantinedKeyQuerySet.as_manager()

    class Meta:
        db_table = "ubb_quarantined_key"
        constraints = [
            # The two closed sets, at the database. A `clean()` alone defends
            # nothing against what writes without validating, which is most of
            # what writes (ADR-0007 §2).
            models.CheckConstraint(
                condition=models.Q(unrecognised__in=sorted(UNRECOGNISED_VALUES)),
                name="ck_quarantined_key_unrecognised",
            ),
            models.CheckConstraint(
                condition=models.Q(resolution__in=sorted(RESOLUTION_VALUES)),
                name="ck_quarantined_key_resolution",
            ),
            # An unrecognised quantity has a quantity name; an unrecognised
            # Event Type has none. Without this a row could claim to be about a
            # quantity while naming none, and the remediation paths would have
            # nothing to resolve.
            models.CheckConstraint(
                condition=(
                    (models.Q(unrecognised=UNRECOGNISED_MEASUREMENT_KEY)
                     & ~models.Q(measurement_key=""))
                    | models.Q(unrecognised=UNRECOGNISED_EVENT_TYPE,
                               measurement_key="")),
                name="ck_quarantined_key_names_what_it_is_about",
            ),
            # And each kind holds the numbers ITS kind holds. Without this the
            # two columns above become interchangeable, and the reason they
            # are not — that one case has a posting behind it and the other has
            # nothing at all — stops being visible to anything but a reader.
            models.CheckConstraint(
                condition=(
                    models.Q(unrecognised=UNRECOGNISED_MEASUREMENT_KEY,
                             quantities={})
                    | models.Q(unrecognised=UNRECOGNISED_EVENT_TYPE,
                               quantity="")),
                name="ck_quarantined_key_holds_its_own_numbers",
            ),
            # Resolved and dated move together, in both directions. A
            # resolution with no date is a repair nobody can place in time; a
            # date with no resolution is a row that reads as unresolved to
            # every query and as finished to every reader.
            models.CheckConstraint(
                condition=(models.Q(resolution=RESOLUTION_UNRESOLVED,
                                    resolved_at__isnull=True)
                           | (~models.Q(resolution=RESOLUTION_UNRESOLVED)
                              & models.Q(resolved_at__isnull=False))),
                name="ck_quarantined_key_resolution_is_dated",
            ),
            # A dismissal names no declaration and the other two name one.
            # This is "dismiss as NON-ECONOMIC" enforced rather than described:
            # a dismissal able to carry a declaration key would be a fourth
            # remediation path with no name and no rule.
            models.CheckConstraint(
                condition=(
                    (models.Q(resolution__in=sorted(
                        RESOLUTIONS_NAMING_A_DECLARATION))
                     & ~models.Q(resolved_key=""))
                    | models.Q(resolution=RESOLUTION_DISMISSED, resolved_key="")
                    | models.Q(resolution=RESOLUTION_UNRESOLVED,
                               resolved_key="")),
                name="ck_quarantined_key_resolution_and_key_agree",
            ),
        ]
        indexes = [
            # Exactly the period-close safeguard's query: this tenant's open
            # rows, by when the event happened. Indexed on the column a close
            # reads and never on the repair date — the storage-level statement
            # of the rule the services enforce.
            models.Index(fields=["tenant", "occurred_at"],
                         condition=models.Q(resolution=RESOLUTION_UNRESOLVED),
                         name="ix_quarantined_key_open"),
        ]

    def __str__(self):
        return f"QuarantinedKey({self.held_name})"

    @property
    def held_name(self):
        """The name UBB did not recognise — the subject of this row.

        Read off ``unrecognised`` rather than off whichever column happens to
        be populated. ``measurement_key or event_type_key`` gives the same
        answer for every row the constraints admit and a WRONG one for a row
        being assembled, where it would silently report an Event Type as the
        held name on a half-built quantity row — and a half-built row is
        exactly what a validator and a repair screen handle.
        """
        if self.unrecognised == UNRECOGNISED_MEASUREMENT_KEY:
            return self.measurement_key
        return self.event_type_key

    @property
    def is_unresolved(self):
        """Whether this still stands between an event and a complete cost.

        A property rather than a column, per ADR-0006 §4: it is derived from
        ``resolution`` entire, and a second column agreeing with it until the
        day it did not is the shape that rule exists to refuse.
        """
        return self.resolution == RESOLUTION_UNRESOLVED

    def clean(self):
        super().clean()
        errors = {}

        if self.unrecognised not in UNRECOGNISED_VALUES:
            errors["unrecognised"] = (
                f"'{self.unrecognised}' is not something UBB can hold a name "
                f"for. UBB owns this whole value set: "
                f"{', '.join(sorted(UNRECOGNISED_VALUES))}.")
        if self.resolution not in RESOLUTION_VALUES:
            named = sorted(value for value in RESOLUTION_VALUES if value)
            errors["resolution"] = (
                f"'{self.resolution}' is not a remediation. UBB owns this "
                f"whole value set: {', '.join(named)}, or empty while the "
                f"name is still held.")
        if not self.event_type_key:
            errors["event_type_key"] = (
                "is empty. Every held name arrived under some Event Type key, "
                "including the case where that key is itself what UBB did not "
                "recognise.")

        about = self._subject_error()
        if about:
            errors["measurement_key"] = about
        numbers = self._numbers_error()
        if numbers:
            errors[numbers[0]] = numbers[1]
        dated = self._resolution_dating_error()
        if dated:
            errors["resolved_at"] = dated
        named_declaration = self._resolution_naming_error()
        if named_declaration:
            errors["resolved_key"] = named_declaration

        if errors:
            raise ValidationError(errors)

    def _subject_error(self):
        """A row says which name it is about by carrying that name."""
        if self.unrecognised == UNRECOGNISED_MEASUREMENT_KEY:
            if not self.measurement_key:
                return ("is empty on a row about an unrecognised quantity. The "
                        "name UBB did not recognise is the whole of what is "
                        "held here, and a row that lost it has nothing left to "
                        "resolve.")
            return None
        if self.measurement_key:
            return ("names a quantity on a row about an unrecognised Event "
                    "Type. The Event Type is what UBB did not recognise, so "
                    "nothing beneath it was ever looked up — naming a quantity "
                    "here would claim a lookup that never happened.")
        return None

    def _numbers_error(self):
        """Each kind holds the numbers its kind holds. Returns (field, why)."""
        if self.unrecognised == UNRECOGNISED_MEASUREMENT_KEY:
            if self.quantities:
                return ("quantities", (
                    "carries the whole measured bag on a row about ONE "
                    "unrecognised quantity. That event was recorded as a "
                    "posting and the posting holds its bag; what is not "
                    "anywhere else is the single number beside the name "
                    "nothing matched, and that is `quantity`."))
            return None
        if self.quantity:
            return ("quantity", (
                "names one number on a row about an unrecognised Event Type, "
                "where no quantity was ever looked up. The bag that arrived "
                "goes in `quantities`, which is the only place it exists — an "
                "event UBB cannot place is not recorded as a posting at all."))
        return None

    def _resolution_dating_error(self):
        """Resolved and dated move together, asked in both directions."""
        if self.is_unresolved and self.resolved_at is not None:
            return ("is set on a row that is still unresolved. A repair date "
                    "with no repair reads as open to every query and as "
                    "finished to every reader.")
        if not self.is_unresolved and self.resolved_at is None:
            return (f"is empty on a row resolved as '{self.resolution}'. When "
                    f"the repair happened is what makes it auditable — and it "
                    f"is deliberately not the moment anything replays from.")
        return None

    def _resolution_naming_error(self):
        """A dismissal names nothing; the other two name a declaration."""
        if self.resolution in RESOLUTIONS_NAMING_A_DECLARATION:
            if not self.resolved_key:
                return (f"is empty on a row resolved as '{self.resolution}'. "
                        f"Both of those resolutions say what the held name now "
                        f"MEANS, and a row that does not say it has recorded a "
                        f"decision nobody can act on.")
            return None
        if self.resolved_key:
            return ("names a declaration on a row that names none. A "
                    "dismissal says the held name is not economic, and a row "
                    "still held says nothing yet — either one carrying a "
                    "declaration key is a mapping that avoided both of the "
                    "paths a tenant would otherwise have had to choose.")
        return None

