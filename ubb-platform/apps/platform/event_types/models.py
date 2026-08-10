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

**What is here so far.** ``EventType`` — the aggregate root — and the two
optional satellites it hangs off, ``Provider`` and ``EventCategory``. The
declared quantities and the reported-cost mapping arrive in the tickets that
follow, and the recorded consumer debts naming this path stay open until the
fields that serve them are built. Nothing here is wired to anything: no rating
path reads it, no cost resolves through it, no spend ceiling consults it. Slice 2
owns the declaration; slice 3 owns every behaviour the declaration selects.
``apps/platform/tests/test_event_type_satellite_invariants.py`` and its sibling
``test_event_type_declaration_invariants.py`` are where those claims are held to
the tree rather than asserted here.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from core.models import BaseModel
from core.vocabulary import (
    COSTING_METHOD_REPORTED,
    COSTING_METHOD_VALUES,
    DECLARATION_STATUS_DRAFT,
    DECLARATION_STATUS_PUBLISHED,
    DECLARATION_STATUS_VALUES,
    SOURCE_SHAPE_ID_CUSTOM,
    SOURCE_SHAPE_ID_KNOWN_VALUES,
)

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


class DeclarationIncomplete(Exception):
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


class EventType(BaseModel):
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
    #: The structured paths and the mapping join this tuple with the records
    #: that carry them.
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

    # -- the declaration lifecycle -------------------------------------------

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
        baseline = getattr(self, "_pinned_as_loaded", None)
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

    def _pinned_declaration(self):
        return tuple(getattr(self, name) for name in self.PINNED)

    @classmethod
    def from_db(cls, db, field_names, values):
        """Remember what was published, so a change to it can be seen.

        A deferred load cannot answer the question, so it does not pretend to:
        the baseline is taken only when every pinned element was actually read.
        """
        instance = super().from_db(db, field_names, values)
        if set(cls.PINNED) <= set(field_names):
            instance._pinned_as_loaded = instance._pinned_declaration()
        return instance

    def save(self, *args, update_fields=None, **kwargs):
        """A change to a pinned element of a published declaration un-publishes it.

        In ``save`` rather than in a service, because the rule is that the
        reinterpretation can never be SILENT — and anything a caller has to
        remember to route through is a rule that holds until the first caller
        who does not. ``update_fields`` is widened rather than honoured as
        given, for the same reason: naming only the field being changed is the
        obvious way round a save-time guard.
        """
        baseline = getattr(self, "_pinned_as_loaded", None)
        if (baseline is not None
                and self.declaration_status == DECLARATION_STATUS_PUBLISHED
                and self._pinned_declaration() != baseline):
            self.declaration_status = DECLARATION_STATUS_DRAFT
            if update_fields is not None:
                update_fields = tuple(set(update_fields) | {"declaration_status"})

        super().save(*args, update_fields=update_fields, **kwargs)
        self._pinned_as_loaded = self._pinned_declaration()

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
