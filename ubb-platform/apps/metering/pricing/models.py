import hashlib
import json

from django.db import models

from core.models import BaseModel


class TenantMarkup(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="markups",
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="markups",
        null=True, blank=True,
    )
    markup_percentage_micros = models.BigIntegerField(default=0)  # 1_000_000 == 1%
    fixed_uplift_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_tenant_markup"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant"], condition=models.Q(customer__isnull=True),
                name="uq_markup_tenant_default",
            ),
            models.UniqueConstraint(
                fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                name="uq_markup_tenant_customer",
            ),
        ]

    def calculate_markup_micros(self, provider_cost_micros: int) -> int:
        percent = (provider_cost_micros * self.markup_percentage_micros + 50_000_000) // 100_000_000
        return percent + self.fixed_uplift_micros


CARD_TYPE_CHOICES = [("cost", "Cost"), ("price", "Price")]
PRICING_MODEL_CHOICES = [("per_unit", "Per unit"), ("flat", "Flat")]


class RateCard(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="rate_cards")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_cards", null=True, blank=True)
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="", db_index=True)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    metric_name = models.CharField(max_length=100)
    dimensions = models.JSONField(default=dict)
    dimensions_hash = models.CharField(max_length=64, blank=True, default="", db_index=True)
    pricing_model = models.CharField(max_length=20, choices=PRICING_MODEL_CHOICES, default="per_unit")
    rate_per_unit_micros = models.BigIntegerField(default=0)
    unit_quantity = models.BigIntegerField(default=1_000_000)
    fixed_micros = models.BigIntegerField(default=0)
    tiers = models.JSONField(default=list, blank=True)
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="")
    valid_from = models.DateTimeField(auto_now_add=True, db_index=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_rate_card"
        indexes = [
            models.Index(fields=["tenant", "card_type", "provider", "event_type", "metric_name"],
                         name="idx_ratecard_lookup"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=True),
                name="uq_ratecard_active_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "customer", "card_type", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True, customer__isnull=False),
                name="uq_ratecard_active_customer"),
        ]

    def save(self, *args, **kwargs):
        self.dimensions_hash = hashlib.sha256(
            json.dumps(self.dimensions or {}, sort_keys=True).encode()).hexdigest()
        super().save(*args, **kwargs)

    def compute(self, units):
        if self.pricing_model == "flat":
            return self.fixed_micros
        units = units or 0
        return (units * self.rate_per_unit_micros + self.unit_quantity // 2) // self.unit_quantity + self.fixed_micros
