from django.db import models

from core.models import BaseModel

# Ten tenant-owned slots (D2), widened from six in #276 and spelled for the
# concept they hold rather than for the retired one (ADR-0006 §2 — no short
# form beside a long form).
#
# WHY TEN. #273 closed the free-form grouping escape hatch: the surviving open
# bag is filterable and readable but never groupable, so demand that used to
# land there now has to arrive as a DECLARATION or not arrive at all. Ten is v1
# product headroom for that demand.
#
# It is NOT justified by migration cost, and the sentence that used to stand
# here said it was. Adding a nullable column to a modern Postgres table is a
# catalog write, so "adding columns later is the expensive move" was false when
# it was written; the expensive move is the per-slot index it used to imply,
# which is why the widening and the index drop are one change (see
# `apps.metering.usage.models.Posting`).
SLOT_CHOICES = [(f"grouping_field_{i}", f"grouping_field_{i}") for i in range(1, 11)]

#: The slots that exist, in declaration order — the one derivation, so that a
#: widening moves one line and not four.
#:
#: A STORED SLOT IS A COLUMN NAME on `Posting`, `Task` and `Rate`, which is why
#: this is worth naming rather than restating as a `range` at each use: a slot
#: outside this tuple is not a bad label, it is a declaration bound to a column
#: that does not exist, and every event recorded against it would fail at insert.
#: `DimensionService.admit` returns `{slot: value}` and the recording path hands
#: that map straight to `create()` as keyword arguments.
SLOTS = tuple(slot for slot, _ in SLOT_CHOICES)

#: How wide a column holding one of the identifiers above has to be. Derived so
#: the bound and the vocabulary cannot drift apart — a hand-typed width is how
#: a widening ships with a column that silently truncates the widest member.
SLOT_MAX_LENGTH = max(len(slot) for slot, _ in SLOT_CHOICES)

# The level at which a grouping field's value is CONSTANT (D6). Task- and
# subtask-scoped values are set once on the unit and inherited by its events;
# event-scoped values are sent per call.
SCOPE_CHOICES = [("task", "Task"), ("subtask", "Subtask"), ("event", "Event")]

# Always-present axes that are never declared and never retired (D1). A tenant
# may not bind one of these words to a dim slot.
RESERVED_KEYS = ("provider", "event_type", "task_type", "subtask_type")

# Correlation identifiers (D9): unbounded by construction, so they are filter
# parameters and may never be declared as dimensions.
FORBIDDEN_KEYS = ("task_id", "subtask_id", "request_id", "idempotency_key",
                  "customer_id", "event_id")


class GroupingField(BaseModel):
    """One declared slicing axis, binding a tenant's own key to a physical slot.

    The registry is the SINGLE vocabulary for analytics grouping and rate
    selection (D1) — nothing may be grouped by or priced on that is not
    declared here.

    Immutability (D8): `slot` and `scope` never change. Re-slotting would
    silently change the meaning of every historical row in that column;
    re-scoping would make old and new rows disagree about where a value came
    from. `key` is a display label and may be renamed; the slot is identity.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="grouping_fields")
    key = models.CharField(max_length=64)
    slot = models.CharField(max_length=SLOT_MAX_LENGTH, choices=SLOT_CHOICES)
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default="event")
    # Keyspace guard, not an invariant (D4): bounding distinct values is what
    # makes the rate cache safely keyed by them. Raise only, never lower.
    max_cardinality = models.IntegerField(default=100)
    # Retire, never delete (D8): stops accepting new values while historical
    # rows keep their meaning and stay groupable.
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_grouping_field"
        # The CONSTRAINT names still spell the retired noun, and deliberately.
        # A table is renamed in place (`AlterModelTable` -> `ALTER TABLE ...
        # RENAME TO`), which carries its rows, keys, indexes and constraints
        # with it. A constraint has no such operation: Django can only
        # `RemoveConstraint` then `AddConstraint`, which is a DROP and a CREATE
        # — the add-plus-remove ADR-0007 §1 refuses, on a unique index that is
        # load-bearing while it is gone. ADR-0006 §9's rule is about the TABLE
        # name, and the table now tracks its model; these names are physical
        # identifiers no query spells and no gate reads.
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_dimension_def_key"),
            models.UniqueConstraint(fields=["tenant", "slot"],
                                    name="uq_dimension_def_slot"),
        ]

    def __str__(self):
        return f"GroupingField({self.key} -> {self.slot}, {self.scope})"


class GroupingFieldValue(BaseModel):
    """The distinct-value ledger backing the cardinality cap (D4).

    One row per (tenant, key, value) ever admitted. Also the read model for
    `GET /dimensions/{key}/values`, which is what a tenant dashboard needs to
    build a filter dropdown.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="grouping_field_values")
    key = models.CharField(max_length=64)
    value = models.CharField(max_length=100)

    class Meta:
        db_table = "ubb_grouping_field_value"
        # Kept for the reason stated on the model above.
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key", "value"],
                                    name="uq_dimension_value"),
        ]
        indexes = [
            models.Index(fields=["tenant", "key"], name="idx_dimvalue_tenant_key"),
        ]

    def __str__(self):
        return f"GroupingFieldValue({self.key}={self.value})"
