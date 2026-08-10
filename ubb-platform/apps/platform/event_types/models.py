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

**What is here so far.** The two optional satellites the Event Type hangs off —
``Provider`` and ``EventCategory`` — and nothing else. The Event Type itself, the
declared quantities and the reported-cost mapping arrive in the tickets that
follow, and the recorded consumer debts naming this path stay open until the
fields that serve them are built. Neither satellite is wired to anything: no
rating path reads them, no cost resolves through them, no spend ceiling consults
them. Slice 2 owns the declaration; slice 3 owns every behaviour the declaration
selects. ``apps/platform/tests/test_event_type_satellite_invariants.py`` is where
that claim is held to the tree rather than asserted here.
"""

from django.db import models

from core.models import BaseModel


class ProviderQuerySet(models.QuerySet):
    def selectable(self):
        """The Providers a NEW declaration may choose.

        The default manager stays deliberately unfiltered: retirement is about
        what may be *attached* next, never about what may be *read*. A report
        over last quarter must still resolve the supplier behind last quarter's
        postings, and a manager that hid retired rows by default would make that
        the hard path and the wrong answer the easy one.
        """
        return self.filter(retired_at__isnull=True)


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

    **Optional, and no fictitious row.** A tenant metering its own internal work
    has no supplier, and must not be made to invent one to satisfy a schema. An
    Event Type with no Provider is a normal Event Type. A fictitious Provider is
    a defect, not a workaround — it puts a name UBB invented into a tenant's own
    COGS attribution.
    """

    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="providers")
    # The tenant's own handle. Renameable BY DESIGN — see the class docstring.
    key = models.SlugField(max_length=64)
    # Retire, never delete. NULL means live.
    retired_at = models.DateTimeField(null=True, blank=True)

    objects = ProviderQuerySet.as_manager()

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
    key = models.SlugField(max_length=64)

    class Meta:
        db_table = "ubb_event_category"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_event_category_key"),
        ]

    def __str__(self):
        return f"EventCategory({self.key})"
