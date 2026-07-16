from django.db import models
from core.models import BaseModel


class RiskConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="risk_config")
    max_requests_per_minute = models.IntegerField(default=60)
    max_concurrent_requests = models.IntegerField(default=10)
    gate_fail_closed = models.BooleanField(default=False)
    # One-rule (#37): tenant default for Task.provider_cost_limit_micros —
    # COGS-denominated (what the job burns), applied at the start-gate when a
    # start call names no explicit limit. NULL = no default: absent both, the
    # task is uncapped and no signal ever fires.
    default_task_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    # Subtasks (#38): the same fallback for units registered with a parent
    # (parent_task_id at the start-gate). Same denomination, same NULL = no
    # default, same coverage gate.
    default_subtask_provider_cost_limit_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_risk_config"

    def __str__(self):
        return f"RiskConfig({self.tenant.name}: {self.max_requests_per_minute}rpm, {self.max_concurrent_requests}concurrent)"


def default_alert_levels():
    return [50, 80, 100, 110]


BUDGET_ENFORCE_MODES = [("advisory", "Advisory"), ("enforcing", "Enforcing")]


class BudgetConfig(BaseModel):
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="budget_configs")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE,
                                 related_name="budget_configs", null=True, blank=True)
    cap_micros = models.BigIntegerField(default=0)  # <= 0 means "no cap" (overlay inert)
    period = models.CharField(max_length=10, default="month")
    enforce_mode = models.CharField(max_length=10, choices=BUDGET_ENFORCE_MODES, default="advisory")
    hard_stop_pct = models.IntegerField(default=100)
    alert_levels = models.JSONField(default=default_alert_levels)
    fail_closed = models.BooleanField(default=False)

    class Meta:
        db_table = "ubb_budget_config"
        constraints = [
            models.UniqueConstraint(fields=["tenant"], condition=models.Q(customer__isnull=True),
                                    name="uq_budget_config_tenant_default"),
            models.UniqueConstraint(fields=["tenant", "customer"], condition=models.Q(customer__isnull=False),
                                    name="uq_budget_config_tenant_customer"),
        ]

    def __str__(self):
        return f"BudgetConfig({self.tenant_id}/{self.customer_id}: cap={self.cap_micros} {self.enforce_mode})"
