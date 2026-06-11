from django.db import models

from core.models import BaseModel


INVOICE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("paid", "Paid"),
    ("void", "Void"),
]


class Invoice(BaseModel):
    """Receipt invoice for a top-up payment."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="invoices"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="invoices"
    )
    top_up_attempt = models.OneToOneField(
        "topups.TopUpAttempt", on_delete=models.CASCADE, related_name="invoice"
    )
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    total_amount_micros = models.BigIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=INVOICE_STATUS_CHOICES,
        default="draft",
        db_index=True,
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ubb_invoice"
        indexes = [
            models.Index(fields=["customer", "status"], name="idx_invoice_customer_status"),
        ]

    def __str__(self):
        return f"Invoice({self.customer.external_id}: {self.status})"


USAGE_INVOICE_STATUS = [
    ("pending", "Pending"), ("pushing", "Pushing"), ("pushed", "Pushed"),
    ("skipped", "Skipped"), ("failed", "Failed"), ("failed_permanent", "Failed permanent"),
]

USAGE_INVOICE_PUSH_PHASE = [
    ("", "Not started"), ("invoice_created", "Invoice created"),
    ("items_pinned", "Items pinned"), ("finalized", "Finalized"),
]


class CustomerUsageInvoice(BaseModel):
    """A postpaid customer's usage for one calendar month, pushed to Stripe as line items."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE, related_name="usage_invoices")
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE, related_name="usage_invoices")
    period_start = models.DateField()
    period_end = models.DateField()
    total_billed_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")
    status = models.CharField(max_length=20, choices=USAGE_INVOICE_STATUS, default="pending", db_index=True)
    stripe_invoice_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    skip_reason = models.CharField(max_length=50, blank=True, default="")
    push_attempts = models.PositiveIntegerField(default=0)
    first_attempted_at = models.DateTimeField(null=True, blank=True)
    last_attempt_error = models.TextField(blank=True, default="")
    push_phase = models.CharField(max_length=20, choices=USAGE_INVOICE_PUSH_PHASE, blank=True, default="")
    # Incremented by repush_usage_invoice --rebill-void: rotates every Stripe
    # idempotency-key family so a replay inside Stripe's 24h key window can never
    # return the recorded (now-void) invoice. Generation 0 keeps the exact legacy
    # key strings for in-flight rows.
    rebill_generation = models.PositiveIntegerField(default=0)
    # Frozen-at-first-claim aggregation: [[label, amount_micros], ...]. Pinned in
    # Phase 1 of the first push attempt so line_index identity is stable across
    # retries even if the tenant flips usage_line_item_group_by mid-retry.
    line_snapshot = models.JSONField(default=list, blank=True)
    residual_micros = models.BigIntegerField(default=0)
    pushed_at = models.DateTimeField(null=True, blank=True)
    payment_status = models.CharField(max_length=20, null=True, blank=True)  # open|paid|void|uncollectible (NULL = not yet collectible)
    paid_at = models.DateTimeField(null=True, blank=True)
    payment_failed_at = models.DateTimeField(null=True, blank=True)
    hosted_invoice_url = models.CharField(max_length=1000, blank=True, default="")
    invoice_pdf = models.CharField(max_length=1000, blank=True, default="")

    class Meta:
        db_table = "ubb_customer_usage_invoice"
        constraints = [models.UniqueConstraint(
            fields=["customer", "period_start"], name="uq_usage_invoice_customer_period")]

    def __str__(self):
        return f"UsageInvoice({self.customer_id}: {self.period_start} {self.status})"


class UsageInvoiceLineItem(BaseModel):
    usage_invoice = models.ForeignKey(CustomerUsageInvoice, on_delete=models.CASCADE, related_name="line_items")
    dimension = models.CharField(max_length=255, blank=True, default="")
    amount_micros = models.BigIntegerField(default=0)
    stripe_invoice_item_id = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        db_table = "ubb_usage_invoice_line_item"


class PostpaidUsageConfig(BaseModel):
    tenant = models.OneToOneField("tenants.Tenant", on_delete=models.CASCADE, related_name="postpaid_config")
    usage_line_item_group_by = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        db_table = "ubb_postpaid_usage_config"
