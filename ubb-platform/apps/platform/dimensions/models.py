from django.db import models

from core.models import BaseModel

# Six tenant-owned slots (D2). A seventh axis requires a migration, so six is
# deliberately generous — adding columns later is the expensive move.
SLOT_CHOICES = [(f"dim{i}", f"dim{i}") for i in range(1, 7)]

# The level at which a dimension's value is CONSTANT (D6). Task- and
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


class DimensionDef(BaseModel):
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
                               related_name="dimension_defs")
    key = models.CharField(max_length=64)
    slot = models.CharField(max_length=8, choices=SLOT_CHOICES)
    scope = models.CharField(max_length=8, choices=SCOPE_CHOICES, default="event")
    # Keyspace guard, not an invariant (D4): bounding distinct values is what
    # makes the rate cache safely dimension-keyed. Raise only, never lower.
    max_cardinality = models.IntegerField(default=100)
    # Retire, never delete (D8): stops accepting new values while historical
    # rows keep their meaning and stay groupable.
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_dimension_def"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key"],
                                    name="uq_dimension_def_key"),
            models.UniqueConstraint(fields=["tenant", "slot"],
                                    name="uq_dimension_def_slot"),
        ]

    def __str__(self):
        return f"DimensionDef({self.key} -> {self.slot}, {self.scope})"


class DimensionValue(BaseModel):
    """The distinct-value ledger backing the cardinality cap (D4).

    One row per (tenant, key, value) ever admitted. Also the read model for
    `GET /dimensions/{key}/values`, which is what a tenant dashboard needs to
    build a filter dropdown.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="dimension_values")
    key = models.CharField(max_length=64)
    value = models.CharField(max_length=100)

    class Meta:
        db_table = "ubb_dimension_value"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "key", "value"],
                                    name="uq_dimension_value"),
        ]
        indexes = [
            models.Index(fields=["tenant", "key"], name="idx_dimvalue_tenant_key"),
        ]

    def __str__(self):
        return f"DimensionValue({self.key}={self.value})"
