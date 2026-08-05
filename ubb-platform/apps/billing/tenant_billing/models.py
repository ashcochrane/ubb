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


class PlatformFeeCarry(BaseModel):
    """R3's carry-forward record for the platform fee (#199).

    Glossary entry in `apps/billing/CONTEXT.md`; the sibling that does the same
    job per customer is `PostpaidResidualLedger`. Kept separate because the two
    are keyed at different grains — the fee is computed per tenant per period,
    which is where its remainder becomes knowable.

    Both ends of the chain are stored: the carry-in costs one column and makes
    "why was March a cent larger" answerable from the row, rather than by
    re-deriving every prior month.

    Written at CLOSE, not at push, so a period that never bills still banks its
    remainder — the carry belongs to the tenant, not to the pushing act.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="platform_fee_carries"
    )
    billing_period = models.OneToOneField(
        TenantBillingPeriod, on_delete=models.CASCADE, related_name="fee_carry"
    )
    carried_in_micros = models.BigIntegerField(default=0)
    carried_out_micros = models.BigIntegerField(default=0)

    class Meta:
        db_table = "ubb_platform_fee_carry"
        constraints = [
            # A carry is a sub-minor-unit REMAINDER, so it is never negative —
            # `to_minor` floors, giving 0 <= remainder < minor_units for every
            # input, negatives included. The upper bound is deliberately NOT a
            # constraint: it is minor_units(currency), and spelling it here
            # would hard-code the bare `10_000` that core/money.py exists to
            # delete. It is asserted in the suite instead, where the currency
            # is in scope.
            models.CheckConstraint(
                condition=models.Q(carried_in_micros__gte=0)
                & models.Q(carried_out_micros__gte=0),
                name="ck_platform_fee_carry_non_negative",
            ),
        ]

    def __str__(self):
        return f"PlatformFeeCarry({self.tenant.name}: {self.carried_out_micros})"


class BillingTenantConfig(BaseModel):
    tenant = models.OneToOneField(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_config"
    )
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    platform_fee_percentage = models.DecimalField(
        max_digits=5, decimal_places=2, default=1.00
    )
    min_balance_micros = models.BigIntegerField(default=0)
    # Soft floor (#40, spec §F): tenant default for the wind-down line — same
    # orientation as min_balance_micros (the line is -value). NULL = no soft
    # floor. Customer override: CustomerBillingProfile.soft_min_balance_micros.
    soft_min_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_billing_tenant_config"

    def __str__(self):
        return f"BillingTenantConfig({self.tenant.name})"
