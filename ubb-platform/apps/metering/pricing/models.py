from django.db import models

from core.models import BaseModel


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
