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
