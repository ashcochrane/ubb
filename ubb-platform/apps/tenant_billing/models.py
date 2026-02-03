from django.db import models

from core.models import BaseModel


TENANT_BILLING_PERIOD_STATUS_CHOICES = [
    ("open", "Open"),
    ("closed", "Closed"),
    ("invoicing", "Invoicing"),
    ("invoiced", "Invoiced"),
]

TENANT_INVOICE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("paid", "Paid"),
    ("void", "Void"),
    ("uncollectible", "Uncollectible"),
]


class TenantBillingPeriod(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_periods"
    )
    period_start = models.DateField(db_index=True)
    period_end = models.DateField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=TENANT_BILLING_PERIOD_STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    total_usage_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    platform_fee_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_tenant_billing_period"
        constraints = [
            # Composite uniqueness for idempotent period creation
            models.UniqueConstraint(
                fields=["tenant", "period_start", "period_end"],
                name="uq_tenant_billing_period",
            ),
            # Only one open period per tenant at a time
            models.UniqueConstraint(
                fields=["tenant"],
                condition=models.Q(status="open"),
                name="uq_one_open_period_per_tenant",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "period_end"], name="idx_tbp_status_end"),
        ]

    def __str__(self):
        return f"TenantBillingPeriod({self.tenant.name}: {self.period_start} - {self.period_end})"


class TenantInvoice(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="platform_invoices"
    )
    billing_period = models.OneToOneField(
        TenantBillingPeriod, on_delete=models.CASCADE, related_name="invoice"
    )
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    total_amount_micros = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=TENANT_INVOICE_STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_tenant_invoice"

    def __str__(self):
        return f"TenantInvoice({self.tenant.name}: {self.status})"
