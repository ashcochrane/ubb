import hashlib
import json

from django.db import models

from core.models import BaseModel


class ProviderRate(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="provider_rates",
    )
    provider = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    metric_name = models.CharField(max_length=100, db_index=True)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, db_index=True, blank=True)
    cost_per_unit_micros = models.BigIntegerField()
    unit_quantity = models.BigIntegerField(default=1_000_000)
    currency = models.CharField(max_length=3, default="USD")
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_provider_rate"
        indexes = [
            models.Index(
                fields=["tenant", "provider", "event_type", "metric_name"],
                name="idx_provrate_tenant_lookup",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "metric_name", "dimensions_hash"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_provrate_active_per_tenant",
            ),
        ]

    def save(self, *args, **kwargs):
        canonical = json.dumps(self.dimensions, sort_keys=True)
        self.dimensions_hash = hashlib.sha256(canonical.encode()).hexdigest()
        super().save(*args, **kwargs)

    def calculate_cost_micros(self, units: int) -> int:
        """Round-half-up cost calculation."""
        return (units * self.cost_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity


class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="markups",
    )
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    markup_percentage_micros = models.BigIntegerField(default=0)
    fixed_uplift_micros = models.BigIntegerField(default=0)
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_tenant_markup"
        indexes = [
            models.Index(
                fields=["tenant", "event_type", "provider"],
                name="idx_markup_tenant_lookup",
            ),
        ]

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        """Calculate markup with round-half-up on the percentage portion."""
        percent = (
            provider_cost_micros * self.markup_percentage_micros + 50_000_000
        ) // 100_000_000
        return percent + self.fixed_uplift_micros
