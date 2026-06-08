from django.db import models
from core.models import BaseModel


class CustomerCostAccumulator(BaseModel):
    """Per-customer, per-month provider + billed cost totals (event-driven)."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="cost_accumulators")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="cost_accumulators")
    period_start = models.DateField()
    period_end = models.DateField()
    total_provider_cost_micros = models.BigIntegerField(default=0)
    total_billed_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_cost_accumulator"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_cost_accumulator_tenant_customer_period")]

    def __str__(self):
        return f"CostAccumulator({self.customer_id}: {self.period_start})"


class CustomerEconomics(BaseModel):
    """Per-customer, per-month margin snapshot. revenue = subscription + usage_billed; cost = provider."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="customer_economics")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="economics")
    period_start = models.DateField()
    period_end = models.DateField()
    subscription_revenue_micros = models.BigIntegerField(default=0)  # manual + stripe
    usage_billed_micros = models.BigIntegerField(default=0)
    provider_cost_micros = models.BigIntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    margin_percentage = models.DecimalField(max_digits=7, decimal_places=2, default=0)
    is_unprofitable = models.BooleanField(default=False)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_economics"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer", "period_start"],
            name="uq_economics_tenant_customer_period")]

    def __str__(self):
        return f"Economics({self.customer_id}: {self.margin_percentage}%)"


class CustomerRevenueProfile(BaseModel):
    """Manual per-customer recurring revenue the tenant collects externally."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="revenue_profiles")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="revenue_profiles")
    recurring_amount_micros = models.BigIntegerField(default=0)
    interval = models.CharField(max_length=10, default="month")
    currency = models.CharField(max_length=3, default="usd")
    effective_from = models.DateField()
    effective_to = models.DateField(null=True, blank=True)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_customer_revenue_profile"
        constraints = [models.UniqueConstraint(
            fields=["tenant", "customer"], name="uq_revenue_profile_tenant_customer")]


class MarginThresholdConfig(BaseModel):
    """Per-tenant default (+ optional per-customer override) for unprofitable + spike detection."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="margin_thresholds")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="margin_thresholds", null=True, blank=True)
    min_margin_pct = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    consecutive_periods = models.IntegerField(default=1)
    provider_cost_spike_pct = models.DecimalField(max_digits=6, decimal_places=2, default=25)

    class Meta:
        app_label = "subscriptions"
        db_table = "ubb_margin_threshold_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_margin_threshold_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_margin_threshold_tenant_customer"),
        ]
