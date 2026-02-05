from django.db import models
from core.models import BaseModel


class CustomerCostAccumulator(BaseModel):
    """Lightweight accumulator for per-customer, per-period usage costs.

    Populated by the usage.recorded event handler. Avoids cross-product
    imports — subscriptions has its own copy of cost data.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="cost_accumulators"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="cost_accumulators"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    total_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_cost_accumulator"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_cost_accumulator_tenant_customer_period",
            ),
        ]

    def __str__(self):
        return f"CostAccumulator({self.customer_id}: {self.period_start})"


class CustomerEconomics(BaseModel):
    """Per-customer, per-period unit economics snapshot."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="customer_economics"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="economics"
    )
    period_start = models.DateField()
    period_end = models.DateField()
    subscription_revenue_micros = models.BigIntegerField(default=0)
    usage_cost_micros = models.BigIntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    margin_percentage = models.DecimalField(max_digits=7, decimal_places=2, default=0)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_economics"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start"],
                name="uq_economics_tenant_customer_period",
            ),
        ]

    def __str__(self):
        return f"Economics({self.customer_id}: {self.margin_percentage}%)"
