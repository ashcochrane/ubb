from django.db import models

from core.models import BaseModel


class Card(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant",
        on_delete=models.CASCADE,
        related_name="pricing_cards",
    )
    name = models.CharField(max_length=255)
    slug = models.CharField(max_length=255, db_index=True, default="")
    provider = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, default="")
    pricing_source_url = models.URLField(max_length=500, blank=True, default="")
    group = models.ForeignKey(
        "groups.Group",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="pricing_cards",
    )
    status = models.CharField(
        max_length=20,
        choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")],
        default="active",
    )

    class Meta:
        db_table = "ubb_card"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "slug"],
                condition=models.Q(status__in=["active", "draft"]),
                name="uq_card_slug_per_tenant",
            ),
        ]


class Rate(BaseModel):
    card = models.ForeignKey(
        Card,
        on_delete=models.CASCADE,
        related_name="rates",
    )
    metric_name = models.CharField(max_length=100, db_index=True)
    pricing_type = models.CharField(
        max_length=20,
        choices=[("per_unit", "Per Unit"), ("flat", "Flat")],
        default="per_unit",
    )
    label = models.CharField(max_length=100, blank=True, default="")
    unit = models.CharField(max_length=50, blank=True, default="")
    cost_per_unit_micros = models.BigIntegerField()
    provider_cost_per_unit_micros = models.BigIntegerField(null=True, blank=True)
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
        """Calculate cost. Flat rates ignore quantity; per-unit uses round-half-up."""
        if self.pricing_type == "flat":
            return self.cost_per_unit_micros
        return (units * self.cost_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity

