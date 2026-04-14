import hashlib
import json

from django.db import models

from core.models import BaseModel


class Card(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pricing_cards",
    )
    name = models.CharField(max_length=255)
    provider = models.CharField(max_length=100, db_index=True)
    event_type = models.CharField(max_length=100, db_index=True)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, db_index=True, blank=True)
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=[("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        db_table = "ubb_card"
        indexes = [
            models.Index(
                fields=["tenant", "provider", "event_type"],
                name="idx_card_tenant_lookup",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "provider", "event_type", "dimensions_hash"],
                condition=models.Q(status="active"),
                name="uq_card_active_per_tenant",
            ),
        ]

    def save(self, *args, **kwargs):
        canonical = json.dumps(self.dimensions, sort_keys=True)
        self.dimensions_hash = hashlib.sha256(canonical.encode()).hexdigest()
        super().save(*args, **kwargs)


class Rate(BaseModel):
    card = models.ForeignKey(
        Card,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    metric_name = models.CharField(max_length=100, db_index=True)
    cost_per_unit_micros = models.BigIntegerField()
    unit_quantity = models.BigIntegerField(default=1_000_000)
    currency = models.CharField(max_length=3, default="USD")
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ubb_rate"
        constraints = [
            models.UniqueConstraint(
                fields=["card", "metric_name"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_per_card_metric",
            ),
        ]

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
    margin_pct = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0,
        help_text="Target margin %. 0 = pass-through.",
    )
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

    def apply_margin(self, provider_cost_micros: int) -> int:
        """Apply margin to provider cost. margin_pct=50 means 50% margin: cost / 0.50."""
        if self.margin_pct <= 0:
            return provider_cost_micros
        from decimal import Decimal

        divisor = Decimal("1") - (self.margin_pct / Decimal("100"))
        return int((Decimal(provider_cost_micros) / divisor).quantize(Decimal("1")))
