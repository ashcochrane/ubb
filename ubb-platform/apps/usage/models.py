from django.db import models

from core.models import BaseModel


BILLING_PERIOD_STATUS_CHOICES = [
    ("open", "Open"),
    ("closed", "Closed"),
    ("invoiced", "Invoiced"),
]

INVOICE_STATUS_CHOICES = [
    ("draft", "Draft"),
    ("finalized", "Finalized"),
    ("paid", "Paid"),
    ("void", "Void"),
    ("uncollectible", "Uncollectible"),
]


class Invoice(BaseModel):
    """Invoice for a billing period."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="invoices"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="invoices"
    )
    billing_period = models.OneToOneField(
        "usage.BillingPeriod", on_delete=models.CASCADE, related_name="invoice"
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


class UsageEvent(BaseModel):
    """Immutable usage event record."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="usage_events"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="usage_events"
    )
    request_id = models.CharField(max_length=255, db_index=True)
    idempotency_key = models.CharField(max_length=500, db_index=True)
    cost_micros = models.BigIntegerField()
    balance_after_micros = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    # Pricing breakdown (populated when platform prices the event)
    event_type = models.CharField(max_length=100, blank=True, default="", db_index=True)
    provider = models.CharField(max_length=100, blank=True, default="")
    usage_metrics = models.JSONField(default=dict, blank=True)
    properties = models.JSONField(default=dict, blank=True)
    provider_cost_micros = models.BigIntegerField(null=True, blank=True)
    billed_cost_micros = models.BigIntegerField(null=True, blank=True)
    pricing_provenance = models.JSONField(default=dict, blank=True)
    invoice = models.ForeignKey(
        Invoice,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="usage_events",
    )
    effective_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "ubb_usage_event"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "idempotency_key"],
                name="uq_usage_event_idempotency_v2",
            ),
        ]
        indexes = [
            models.Index(fields=["customer", "-effective_at"], name="idx_usage_customer_effective"),
        ]
        ordering = ["-effective_at"]

    def __str__(self):
        return f"UsageEvent({self.request_id}: {self.cost_micros})"

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValueError("UsageEvent records are immutable and cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValueError("UsageEvent records are immutable and cannot be deleted.")


class Refund(BaseModel):
    """Refund linked to a usage event. Only non-invoiced events can be refunded."""
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="refunds"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="refunds"
    )
    usage_event = models.OneToOneField(
        UsageEvent, on_delete=models.CASCADE, related_name="refund"
    )
    amount_micros = models.BigIntegerField()
    reason = models.TextField(blank=True, default="")
    refunded_by_api_key = models.ForeignKey(
        "tenants.TenantApiKey", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        db_table = "ubb_refund"

    def __str__(self):
        return f"Refund({self.usage_event.request_id}: {self.amount_micros})"


class BillingPeriod(BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="billing_periods"
    )
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="billing_periods"
    )
    period_start = models.DateTimeField(db_index=True)
    period_end = models.DateTimeField(db_index=True)
    status = models.CharField(
        max_length=20,
        choices=BILLING_PERIOD_STATUS_CHOICES,
        default="open",
        db_index=True,
    )
    total_cost_micros = models.BigIntegerField(default=0)
    event_count = models.IntegerField(default=0)
    invoice_attempt_number = models.PositiveIntegerField(default=0)

    class Meta:
        db_table = "ubb_billing_period"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "customer", "period_start", "period_end"],
                name="uq_billing_period",
            ),
        ]
        indexes = [
            models.Index(fields=["status", "period_end"], name="idx_billing_period_status_end"),
        ]

    def __str__(self):
        return f"BillingPeriod({self.customer.external_id}: {self.status})"
