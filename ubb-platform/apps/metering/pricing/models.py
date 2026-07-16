import hashlib
import json
import uuid

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

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(tenant_id)
        return result


CARD_TYPE_CHOICES = [("cost", "Cost"), ("price", "Price")]
# per_unit/flat only: ADR-0003 — the MVP launches without tiered pricing
# (graduated/package deleted end to end, not gated), so every arrival-time
# estimate equals the settled price by construction.
PRICING_MODEL_CHOICES = [
    ("per_unit", "Per unit"),
    ("flat", "Flat"),
]


class Rate(BaseModel):
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
    currency = models.CharField(max_length=3, default="usd")
    product_id = models.CharField(max_length=100, blank=True, default="")
    rate_card = models.ForeignKey("pricing.RateCard", on_delete=models.PROTECT,
                                  related_name="rates", null=True, blank=True)
    book_version_from = models.PositiveIntegerField(default=1)
    book_version_to = models.PositiveIntegerField(null=True, blank=True)
    lineage_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)
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
                fields=["rate_card", "provider", "event_type", "metric_name",
                        "dimensions_hash", "currency"],
                condition=models.Q(valid_to__isnull=True),
                name="uq_rate_active_in_book"),
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


class RateCard(BaseModel):
    """Container grouping many Rates, versioned and assigned as a unit.

    Naming wart: the physical table is `ubb_rate_card_container` because the
    legacy `ubb_rate_card` table now backs the `Rate` model (the old, misnamed
    RateCard). The Python names are correct: RateCard = the sheet, Rate = a line.
    """
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_containers")
    card_type = models.CharField(max_length=10, choices=CARD_TYPE_CHOICES, db_index=True)
    # provider_key pins the book to one provider so the per-provider default
    # invariant is DB-enforceable ("" is the no-provider bucket).
    provider_key = models.CharField(max_length=100, blank=True, default="")
    currency = models.CharField(max_length=3, default="usd")
    key = models.SlugField(max_length=64)
    name = models.CharField(max_length=255, blank=True, default="")
    version = models.PositiveIntegerField(default=1)
    is_default = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_rate_card_container"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "card_type", "key"], name="uq_ratecard_tenant_key"),
            models.UniqueConstraint(
                fields=["tenant", "card_type", "provider_key", "currency"],
                condition=models.Q(is_default=True),
                name="uq_ratecard_one_default_per_provider"),
        ]

    def __str__(self):
        return f"RateCard({self.key} v{self.version})"


class RateCardAssignment(BaseModel):
    """A customer's assigned PRICE book (one per customer per currency)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE,
                               related_name="rate_card_assignments")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="rate_card_assignments")
    rate_card = models.ForeignKey(RateCard, on_delete=models.CASCADE,
                                  related_name="assignments")
    currency = models.CharField(max_length=3, default="usd")

    class Meta:
        db_table = "ubb_rate_card_assignment"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "currency"],
                name="uq_assignment_customer_currency"),
        ]
