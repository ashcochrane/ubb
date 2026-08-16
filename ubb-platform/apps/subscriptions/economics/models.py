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
    # HOW MANY OF THOSE EVENTS THE PROVIDER TOTAL COULD NOT INCLUDE (#328).
    #
    # The handler adds each event's supplier cost as it arrives, and a cost UBB
    # has not resolved (#317) contributes nothing — so without this the running
    # total would be a floor that reads like a figure. Written in the same
    # atomic increment as the amount, because a total and its completeness that
    # can be updated separately will eventually disagree.
    #
    # An event whose Event Type declares no supplier cost is NOT counted: there
    # is nothing missing about a cost that does not exist (#327).
    unresolved_event_count = models.IntegerField(default=0)

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
    # WHAT THE FROZEN COST TOTAL LEFT OUT, copied from the accumulator this
    # snapshot is taken from (#328).
    #
    # It makes `provider_cost_micros` above a floor and every figure derived
    # from it a bound: `gross_margin_micros` is a CEILING on the margin, and
    # `margin_percentage` a ceiling on the percentage. The column stays NOT
    # NULL — SQL's null-skipping never reaches a snapshot, so `Sum` over it is
    # complete by construction and what travels is this count, not a null.
    #
    # It is also what the cost-spike comparison consults: a previous period
    # whose cost excluded something is too small a denominator, so the rise
    # computed against it would be too big. See MarginService.evaluate_and_emit.
    unresolved_event_count = models.IntegerField(default=0)
    gross_margin_micros = models.BigIntegerField(default=0)
    total_revenue_micros = models.BigIntegerField(default=0)
    revenue_mode = models.CharField(max_length=20, blank=True, default="")
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
