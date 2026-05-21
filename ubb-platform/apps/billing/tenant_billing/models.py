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
    event_count = models.BigIntegerField(default=0)
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


class ProductFeeConfig(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="fee_configs"
    )
    product = models.CharField(max_length=100)
    fee_type = models.CharField(max_length=100)
    config = models.JSONField(default=dict)

    class Meta:
        db_table = "ubb_product_fee_config"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "product"],
                name="uq_fee_config_tenant_product",
            ),
        ]

    def __str__(self):
        return f"ProductFeeConfig({self.tenant.name}: {self.product} [{self.fee_type}])"


class TenantInvoiceLineItem(BaseModel):
    invoice = models.ForeignKey(
        TenantInvoice, on_delete=models.CASCADE, related_name="line_items"
    )
    product = models.CharField(max_length=100)
    description = models.CharField(max_length=255)
    amount_micros = models.BigIntegerField()

    class Meta:
        db_table = "ubb_tenant_invoice_line_item"

    def __str__(self):
        return f"LineItem({self.product}: {self.amount_micros})"


class BillingTenantConfig(BaseModel):
    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_config"
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    min_balance_micros = models.BigIntegerField(default=0)
    run_cost_limit_micros = models.BigIntegerField(null=True, blank=True)
    hard_stop_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_tenant_config"

    def __str__(self):
        return f"BillingTenantConfig({self.tenant.name})"
