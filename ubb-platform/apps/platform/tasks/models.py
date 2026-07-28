from django.db import models

from core.models import BaseModel


TASK_STATUS_CHOICES = [
    ("active", "Active"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("killed", "Killed"),
]

TASK_TYPE_KIND_CHOICES = [("task", "Task"), ("subtask", "Subtask")]


def _empty_list():
    return []


class TaskType(BaseModel):
    """The tenant's declared work vocabulary, carrying POLICY (design D7).

    Before this existed, a unit's COGS ceiling came from the per-call
    `provider_cost_limit_micros` or one tenant-wide default
    (RiskConfig.default_task_provider_cost_limit_micros) — so every kind of job
    shared one ceiling, and a job that legitimately costs 50x its sibling forced
    you to either cap both at the large number or let the client declare its own
    spending limit. The ceiling now belongs to the KIND of work, server-side: a
    start call may request lower, never higher.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="task_types")
    key = models.SlugField(max_length=64)
    kind = models.CharField(max_length=8, choices=TASK_TYPE_KIND_CHOICES,
                            default="task")
    # COGS-denominated, matching Task.provider_cost_limit_micros. NULL = fall
    # back to the RiskConfig tenant default, then to uncapped.
    default_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # Declared dimension keys a start call MUST supply for this kind of work.
    required_dimensions = models.JSONField(default=_empty_list, blank=True)
    retired_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task_type"
        constraints = [
            models.UniqueConstraint(fields=["tenant", "kind", "key"],
                                    name="uq_task_type_key"),
        ]

    def __str__(self):
        return f"TaskType({self.kind}:{self.key})"


class Task(BaseModel):
    """The registered unit of agent work — groups multiple UsageEvents into a
    single logical workflow execution.

    Lives in platform because both metering (UsageEvent FK) and billing
    (start-gate creation, cost tracking) need to reference it without
    cross-product imports.

    One-rule model: limits are signal points, never billing walls. A task
    flips to "killed" the moment its limit trips (the flip is the durable
    record that the stop signal fired), but late events still land, bill,
    and keep counting into both totals.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="tasks"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="tasks"
    )
    # Subtask containment (#38): a subtask IS a Task row with `parent` set —
    # one model, one containment level at launch (the parent must itself be
    # parentless; the generic self-FK makes deepening later a validation
    # change, not a remodel). Immutable after creation — a unit is never
    # re-parented, which is what lets accumulate read it without a lock.
    # Lock-ordering refinement (see core/locking.py): within Task, a
    # transaction that locks both a parent and its child locks the PARENT
    # first (rollup, cascade kill/close, and subtask registration all comply).
    parent = models.ForeignKey(
        "self", on_delete=models.CASCADE, null=True, blank=True,
        related_name="subtasks",
    )
    # The KIND of work this instance is (design D7). Immutable after creation
    # for the same reason `parent` is: accumulate_cost reads it without a
    # lock, and a re-typed task would retroactively change what every
    # already-settled event on it means. "" = untyped (a tenant who never
    # declared a vocabulary).
    task_type = models.CharField(max_length=64, blank=True, default="", db_index=True)
    # Set instead of task_type when `parent` is set. Same immutability.
    subtask_type = models.CharField(max_length=64, blank=True, default="",
                                    db_index=True)
    # Task-scoped dimension values (design D6), bound to slots by the tenant's
    # DimensionDef registry. Inherited by EVERY event in this task's tree,
    # including events on its subtasks, so a caller sets them once per job
    # instead of on every metered call. Immutable with the task.
    dim1 = models.CharField(max_length=100, blank=True, default="")
    dim2 = models.CharField(max_length=100, blank=True, default="")
    dim3 = models.CharField(max_length=100, blank=True, default="")
    dim4 = models.CharField(max_length=100, blank=True, default="")
    dim5 = models.CharField(max_length=100, blank=True, default="")
    dim6 = models.CharField(max_length=100, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=TASK_STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    # Both running totals, denominationally explicit, maintained on EVERY
    # accumulate — including events landing after a kill. Only the provider
    # total races provider_cost_limit_micros.
    total_billed_cost_micros = models.BigIntegerField(default=0)
    total_provider_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    # Signal-point snapshots — copied from the start call / tenant config at
    # task creation so a config change never affects an in-flight task.
    balance_snapshot_micros = models.BigIntegerField()
    # COGS limit: measures what the job actually burns (provider cost),
    # never the tenant's markup policy.
    provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # Wallet-floor snapshot. Billed denomination — wallet-shaped things stay
    # billed; only the task limit above is provider-denominated.
    floor_snapshot_micros = models.BigIntegerField(null=True, blank=True)

    # Tier-2 (D4/I6): the billing owner PINNED at task creation
    # (resolve_billing_owner), exactly like UsageEvent.billing_owner_id. The
    # concurrency-slot acquire/release and both reapers read this — they MUST
    # NOT re-resolve the owner (re-parenting would otherwise split the counter
    # or leak the slot). Nullable for back-compat with pre-Tier-2 rows.
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Tier-2 (D10): heartbeat for the stale-task reaper. Stamped on every
    # accumulate_cost. Null until the first metered event.
    last_event_at = models.DateTimeField(null=True, blank=True)
    # Announcement bookkeeping (delivery spec §B, #43): the OutboxEvent id of
    # this unit's kill announcement (task.limit_exceeded /
    # subtask.limit_exceeded), stamped by kill_and_announce inside the same
    # transaction as the winning flip + emission. Stays null on silent
    # cascaded kills (the parent's event is the one signal) and on
    # completed/failed units (nothing to announce). Plain UUID, not an FK —
    # outbox cleanup deletes terminally-successful rows and the stamp must
    # keep meaning "announced" (see apps.platform.events.announcements).
    announce_outbox_id = models.UUIDField(null=True, blank=True)

    metadata = models.JSONField(default=dict)
    external_task_id = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_task"
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="idx_task_customer_created",
            ),
            models.Index(
                fields=["tenant", "status"],
                name="idx_task_tenant_status",
            ),
            # Tier-2 (D10): the reaper scans active tasks by heartbeat staleness.
            models.Index(
                fields=["status", "last_event_at"],
                name="idx_task_status_heartbeat",
            ),
            # Tier-2 (P5): the concurrency cap counts active tasks per owner.
            models.Index(
                fields=["billing_owner_id", "status"],
                name="idx_task_owner_status",
            ),
            # #44 (delivery spec §C.4): the patrol's task sweep scans active
            # LIMITED tasks per tenant every hour — the partial index keeps
            # that scan proportional to the small set of tasks that can still
            # cross, never to tenant history.
            models.Index(
                fields=["tenant"],
                condition=models.Q(status="active",
                                   provider_cost_limit_micros__isnull=False),
                name="idx_task_active_limited",
            ),
            # Unit-economics rollup (design D7): mean/p95 cost per KIND of job.
            models.Index(fields=["tenant", "task_type", "-created_at"],
                         name="idx_task_type_created"),
        ]

    def __str__(self):
        return (f"Task({self.id}: {self.status}, "
                f"billed={self.total_billed_cost_micros}, "
                f"provider={self.total_provider_cost_micros})")

    def save(self, *args, **kwargs):
        """Guard the two immutable type fields (D7/D8).

        `_loaded_types` is stamped either by `from_db` (a row read back from
        the database) or, right below, immediately after this instance's own
        first INSERT — so the very object returned by `.create()` also arms
        the guard for its next in-memory `.save()`, with no refetch required.
        A freshly constructed, never-yet-saved instance has no
        `_loaded_types` and skips the check on that first save.
        """
        was_adding = self._state.adding
        if not was_adding and hasattr(self, "_loaded_types"):
            was_task, was_subtask = self._loaded_types
            if self.task_type != was_task:
                raise ValueError(
                    f"task_type is immutable: {was_task!r} -> {self.task_type!r}")
            if self.subtask_type != was_subtask:
                raise ValueError(
                    f"subtask_type is immutable: {was_subtask!r} -> "
                    f"{self.subtask_type!r}")
        super().save(*args, **kwargs)
        if was_adding:
            self._loaded_types = (self.task_type, self.subtask_type)

    @classmethod
    def from_db(cls, db, field_names, values):
        instance = super().from_db(db, field_names, values)
        if "task_type" in field_names and "subtask_type" in field_names:
            instance._loaded_types = (instance.task_type, instance.subtask_type)
        return instance
