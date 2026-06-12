from django.db import models
from django.utils import timezone

from core.models import BaseModel

RESERVED_DIM_KEYS = ("product", "service", "agent")


class UsageEvent(BaseModel):
    """Immutable usage event record."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="usage_events"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="usage_events"
    )
    request_id = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.CharField(max_length=500, db_index=True)
    balance_after_micros = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    # Pricing breakdown (populated when platform prices the event)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="")
    units = models.BigIntegerField(null=True, blank=True)
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    service_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    agent_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider_cost_micros = models.BigIntegerField(default=0)
    billed_cost_micros = models.BigIntegerField(default=0)
    pricing_provenance = models.JSONField(default=dict, blank=True)
    usage_metrics = models.JSONField(default=dict, blank=True)
    tags = models.JSONField(null=True, blank=True)
    run = models.ForeignKey(
        "runs.Run", on_delete=models.CASCADE, related_name="usage_events",
        null=True, blank=True,
    )
    # When the usage economically HAPPENED (caller-suppliable, bounded by
    # Tenant.backfill_window_days). created_at (BaseModel) is when it ARRIVED;
    # arrival-basis consumers (drawdown repair, platform fee) window on that.
    effective_at = models.DateTimeField(default=timezone.now, db_index=True)
    billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ubb_usage_event"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "idempotency_key"],
                name="uq_usage_event_idempotency_v2",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
            models.Index(fields=["tenant", "-effective_at"], name="idx_usage_tenant_effective"),
            models.Index(fields=["tenant", "product_id", "service_id", "agent_id", "-effective_at"],
                         name="idx_usage_attribution"),
            # Arrival-basis scans (drawdown repair, platform-fee reconcile).
            models.Index(fields=["tenant", "created_at"], name="idx_usage_tenant_created"),
        ]
        ordering = ["-effective_at"]

    def __str__(self):
        return f"UsageEvent({self.request_id}: {self.billed_cost_micros})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("UsageEvent records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("UsageEvent records are immutable and cannot be deleted.")


class BackfillDirtyPeriod(BaseModel):
    """Marker: a usage event was backfilled into a PRIOR calendar month for this
    (tenant, customer). Written in the same transaction as the UsageEvent insert
    (savepoint-IntegrityError-swallow on the unique constraint), consumed by the
    hourly ``resnapshot_dirty_periods`` task via the apps.metering.queries
    contract — the consumer re-snapshots the period's margin then deletes the
    marker, so a crash before delete is retried."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="backfill_dirty_periods"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="backfill_dirty_periods"
    )
    period_start = models.DateField()

    class Meta:
        db_table = "ubb_backfill_dirty_period"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_backfill_dirty_period",
            ),
        ]

    def __str__(self):
        return f"BackfillDirtyPeriod({self.customer_id}: {self.period_start})"


class Refund(BaseModel):
    """Refund linked to a usage event."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="refunds"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="refunds"
    )
    usage_event = models.OneToOneField(
        UsageEvent, on_delete=models.CASCADE, related_name="refund"
    )
    amount_micros = models.BigIntegerField()
    reason = models.TextField(blank=True, default="")
    refunded_by_api_key = models.ForeignKey(
        "tenants.TenantApiKey", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = "ubb_refund"

    def __str__(self):
        return f"Refund({self.usage_event.request_id}: {self.amount_micros})"
