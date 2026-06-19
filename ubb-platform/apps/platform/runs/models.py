from django.db import models

from core.models import BaseModel


RUN_STATUS_CHOICES = [
    ("active", "Active"),
    ("completed", "Completed"),
    ("failed", "Failed"),
    ("killed", "Killed"),
]


class Run(BaseModel):
    """Groups multiple UsageEvents into a single logical workflow execution.

    Lives in platform because both metering (UsageEvent FK) and billing
    (pre-check creation, cost tracking) need to reference it without
    cross-product imports.
    """

    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="runs"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="runs"
    )
    status = models.CharField(
        max_length=20,
        choices=RUN_STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    total_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    # Hard stop snapshots — copied from tenant config at run creation
    # so changing the tenant config doesn't affect in-flight runs.
    balance_snapshot_micros = models.BigIntegerField()
    cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    hard_stop_balance_micros = models.BigIntegerField(null=True, blank=True)

    # Tier-2 (D4/I6): the billing owner PINNED at run creation
    # (resolve_billing_owner), exactly like UsageEvent.billing_owner_id. The
    # concurrency-slot acquire/release and both reapers read this — they MUST
    # NOT re-resolve the owner (re-parenting would otherwise split the counter
    # or leak the slot). Nullable for back-compat with pre-Tier-2 rows.
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    # Tier-2 (D10): heartbeat for the stale-run reaper. Stamped on every
    # accumulate_cost. Null until the first metered event.
    last_event_at = models.DateTimeField(null=True, blank=True)
    # Tier-2 (D12): the per-task identity (tags['task'] || service || agent),
    # captured for the per-task cap + reaper attribution. "" when untagged.
    task_id = models.CharField(max_length=255, blank=True, default="")

    metadata = models.JSONField(default=dict)
    external_run_id = models.CharField(max_length=255, blank=True, default="")
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_run"
        indexes = [
            models.Index(
                fields=["customer", "-created_at"],
                name="idx_run_customer_created",
            ),
            models.Index(
                fields=["tenant", "status"],
                name="idx_run_tenant_status",
            ),
            # Tier-2 (D10): the reaper scans active runs by heartbeat staleness.
            models.Index(
                fields=["status", "last_event_at"],
                name="idx_run_status_heartbeat",
            ),
        ]

    def __str__(self):
        return f"Run({self.id}: {self.status}, cost={self.total_cost_micros})"
