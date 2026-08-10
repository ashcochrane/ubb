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

**What is here so far.** ``EventType`` — the aggregate root — the two optional
satellites it hangs off, ``Provider`` and ``EventCategory``, and ``Measurement``,
the declared quantity. The reported-cost mapping arrives in the ticket that
follows, and the recorded consumer debts naming this path stay open until the
fields that serve them are built. Nothing here is wired to anything: no rating
path reads it, no cost resolves through it, no spend ceiling consults it. Slice 2
owns the declaration; slice 3 owns every behaviour the declaration selects.
``apps/platform/tests/test_event_type_satellite_invariants.py`` and its sibling
``test_event_type_declaration_invariants.py`` are where those claims are held to
the tree rather than asserted here.
"""
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.exceptions import UBBError
from core.models import BaseModel
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    COSTING_METHOD_VALUES,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    DECLARATION_STATUS_VALUES,
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
#: named once. It is declared beneath the Event Type and arrives in #266.
REPORTED_COST_MAPPING = "reported_cost_mapping"

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
    #: The structured paths turned out not to fit here: they arrived on rows
    #: BENEATH the Event Type (#263), and a tuple of this record's own field
    #: names cannot reach them. They pin the publication all the same, through
    #: :meth:`revise_declaration`, which the child calls. The mapping still
    #: joins this tuple, and the tripwire for that is in
    #: ``event_types/tests/test_event_type.py``.
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
        """
        if self.costing_method != COSTING_METHOD_REPORTED:
            return ()
        declared = getattr(self, REPORTED_COST_MAPPING, None)
        # A missing reverse one-to-one answers `None` through `getattr`'s
        # default. A to-many relation would answer with a MANAGER, which is
        # never `None` — so the shape #266 happens to choose would decide
        # whether this rule ran at all. Asking an emptiness question of
        # whatever arrives fails CLOSED in both, which is the only direction
        # of error that keeps an incomplete declaration unpublished.
        if declared is None or (hasattr(declared, "exists")
                                and not declared.exists()):
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


class Measurement(PinnedDeclaration, BaseModel):
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
    #: other side.
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

    # -- publication reaches down here too ------------------------------------

    def save(self, *, update_fields=None, **kwargs):
        """Declaring a quantity, or changing one, revises the publication.

        Including ADDING one: a published Event Type that grows a required
        quantity is a different declaration from the one a tenant generated
        their integration against, and leaving it published would mean the
        deployed code was generated against a contract that has moved.

        ``update_fields`` is widened by whichever pinned elements actually
        changed, exactly as the parent's own guard widens: without it,
        ``save(update_fields=["display_name"])`` after editing a path would
        return the declaration to draft over a change the row never received.

        ``QuerySet.update()`` goes round this as it goes round every
        model-level guard here — ADR-0007 §2 is explicit that these are a
        courtesy to the ordinary path and never the enforcement. What defends
        the emitted code itself is :func:`source_paths.render`, which re-asks
        the grammar at the moment a path becomes code.
        """
        baseline = self._pinned_baseline()
        revised = baseline is None or self._pinned_declaration() != baseline
        if revised and baseline is not None:
            update_fields = self._widened(update_fields, baseline)

        super().save(update_fields=update_fields, **kwargs)
        self._remember_pinned(update_fields)
        if revised:
            self.event_type.revise_declaration()

    def delete(self, *args, **kwargs):
        """Withdrawing a quantity revises the publication too.

        The declaration a tenant's deployed integration was generated against
        no longer describes what UBB will accept, and that is the same event as
        a changed path arriving at it from the other direction.

        A real delete rather than the data plane's soft delete
        (``docs/conventions/coding-standards.md``): that rule protects rows
        carrying money history, and this record carries none — it is part of a
        declaration, and withdrawing a quantity is an edit to one. ``Provider``
        next door earns ``retired_at`` because supplier COGS attribution keys
        on its identity; nothing keys on a Measurement's. The ticket that first
        attaches a posting to a declaration is the one that can revisit this,
        and it is the one that could test the answer.
        """
        event_type = self.event_type
        outcome = super().delete(*args, **kwargs)
        event_type.revise_declaration()
        return outcome

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

        problems = path_errors(self.source_path)
        obligation = None if problems else self._path_obligation_error()
        if problems:
            errors["source_path"] = [f"the source path {problem}"
                                     for problem in problems]
        elif obligation:
            errors["source_path"] = f"the source path {obligation}"

        if errors:
            raise ValidationError(errors)

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

