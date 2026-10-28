from django.db import models

from core.currency_policy import usd_only_check
from core.models import BaseModel
from core.vocabulary import (
    BILLING_PERIOD_STATUS_CLOSED,
    BILLING_PERIOD_STATUS_INVOICED,
    BILLING_PERIOD_STATUS_INVOICING,
    BILLING_PERIOD_STATUS_OPEN,
    TENANT_INVOICE_STATUS_DRAFT,
    TENANT_INVOICE_STATUS_FINALIZED,
    TENANT_INVOICE_STATUS_PAID,
    TENANT_INVOICE_STATUS_UNCOLLECTIBLE,
    TENANT_INVOICE_STATUS_VOID,
)


# The registry's closed `billing_period_status` and `tenant_invoice_status`
# (R10-W4), by reference.
TENANT_BILLING_PERIOD_STATUS_CHOICES = [
    (BILLING_PERIOD_STATUS_OPEN, "Open"),
    (BILLING_PERIOD_STATUS_CLOSED, "Closed"),
    (BILLING_PERIOD_STATUS_INVOICING, "Invoicing"),
    (BILLING_PERIOD_STATUS_INVOICED, "Invoiced"),
]

TENANT_INVOICE_STATUS_CHOICES = [
    (TENANT_INVOICE_STATUS_DRAFT, "Draft"),
    (TENANT_INVOICE_STATUS_FINALIZED, "Finalized"),
    (TENANT_INVOICE_STATUS_PAID, "Paid"),
    (TENANT_INVOICE_STATUS_VOID, "Void"),
    (TENANT_INVOICE_STATUS_UNCOLLECTIBLE, "Uncollectible"),
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
    #: Σ `billed_cost_micros` over the period's postings, placed by ARRIVAL
    #: (#516) — Task Charges included, because fixed-price revenue is
    #: revenue and UBB's platform fee is a percentage of this. Named for
    #: what it aggregates since #516, which retired the "usage cost" name.
    total_billed_cost_micros = models.BigIntegerField(default=0)
    #: Every real `metered_usage` event recorded in the period, priced or
    #: not — and never a Task Charge, which is synthetic revenue rather
    #: than an event the tenant recorded (#563). So the money above
    #: includes what this count excludes, deliberately. Published under
    #: this same name, the registry's measure (`analytics_measure`); the
    #: column took it by `RenameField` in R10-W4 (ruling 1), so the stored
    #: name and the published one are one name.
    recorded_events = models.BigIntegerField(default=0)
    platform_fee_micros = models.BigIntegerField(default=0)
    #: THE CURRENCY THIS PERIOD'S MONEY IS IN, stamped from the tenant when
    #: the period opens. A fact about money names its currency (#145 §7.2),
    #: and the platform fee is invoiced in it — read off this row, never
    #: stated by the invoice call (#565).
    currency = models.CharField(max_length=3, default="usd")

    class Meta:
        db_table = "ubb_tenant_billing_period"
        constraints = [
            # UBB v1 is USD-only (ADR-0023).
            usd_only_check("currency", "ck_billing_period_currency_usd"),
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
