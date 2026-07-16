from django.db import models

from core.models import BaseModel


TASK_STATUS_CHOICES = [
    ("active", "Active"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("killed", "Killed"),
]


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
        ]

    def __str__(self):
        return (f"Task({self.id}: {self.status}, "
                f"billed={self.total_billed_cost_micros}, "
                f"provider={self.total_provider_cost_micros})")
