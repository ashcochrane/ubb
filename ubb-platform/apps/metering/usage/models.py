from django.db import models

from core.models import BaseModel


class EventBatch(BaseModel):
    """Tracks operator-initiated batch event pushes for audit trail."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="event_batches"
    )
    action = models.CharField(
        max_length=20,
        choices=[("added", "Added"), ("reversed", "Reversed")],
    )
    reason = models.TextField(blank=True, default="")
    row_count = models.IntegerField()
    author = models.CharField(max_length=255)
    reversed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_event_batch"
        ordering = ["-created_at"]

    def __str__(self):
        return f"EventBatch({self.action}: {self.row_count} rows)"


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
    cost_micros = models.BigIntegerField()
    balance_after_micros = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    # Pricing breakdown (populated when platform prices the event)
    provider = models.CharField(max_length=100, blank=True, default="")
    usage_metrics = models.JSONField(default=dict, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    provider_cost_micros = models.BigIntegerField(null=True, blank=True)
    billed_cost_micros = models.BigIntegerField(null=True, blank=True)
    pricing_provenance = models.JSONField(default=dict, blank=True)
    group = models.CharField(max_length=255, null=True, blank=True, db_index=True)
    run = models.ForeignKey(
        "runs.Run", on_delete=models.CASCADE, related_name="usage_events",
        null=True, blank=True,
    )
    card = models.ForeignKey(
        "pricing.Card", on_delete=models.SET_NULL,
        null=True, blank=True, related_name="usage_events",
    )
    card_slug = models.CharField(max_length=255, blank=True, default="", db_index=True)
    card_name = models.CharField(max_length=255, blank=True, default="")
    batch = models.ForeignKey(
        EventBatch, on_delete=models.SET_NULL,
        null=True, blank=True, related_name="events",
    )
    effective_at = models.DateTimeField(auto_now_add=True, db_index=True)

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
        ]
        ordering = ["-effective_at"]

    def __str__(self):
        return f"UsageEvent({self.request_id}: {self.cost_micros})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("UsageEvent records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("UsageEvent records are immutable and cannot be deleted.")


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
