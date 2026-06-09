from django.db import models, transaction

from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


CUSTOMER_STATUS_CHOICES = [
    ("active", "Active"),
    ("suspended", "Suspended"),
    ("closed", "Closed"),
]

ACCOUNT_TYPE_CHOICES = [("individual", "Individual"), ("business", "Business"), ("seat", "Seat")]
BILLING_TOPOLOGY_CHOICES = [("pooled", "Pooled"), ("allocated", "Allocated")]


class Customer(SoftDeleteMixin, BaseModel):
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="customers"
    )
    external_id = models.CharField(max_length=255, db_index=True)
    stripe_customer_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(
        max_length=20,
        choices=CUSTOMER_STATUS_CHOICES,
        default="active",
        db_index=True,
    )
    min_balance_micros = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)
    revenue_mode = models.CharField(max_length=20, blank=True, default="")  # "" | "billed" | "metered_only"
    account_type = models.CharField(max_length=12, choices=ACCOUNT_TYPE_CHOICES, default="individual", db_index=True)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="seats")
    billing_topology = models.CharField(max_length=10, choices=BILLING_TOPOLOGY_CHOICES, blank=True, default="")

    class Meta:
        db_table = "ubb_customer"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                condition=models.Q(deleted_at__isnull=True),
                name="uq_customer_tenant_external",
            ),
        ]

    def resolve_billing_owner(self):
        """The Customer whose wallet/card/auto-top-up funds this customer:
        the business for a POOLED seat, otherwise self."""
        if self.account_type == "seat" and self.parent_id:
            if self.parent.billing_topology == "pooled":
                return self.parent
        return self

    def soft_delete(self):
        """Soft delete customer and emit outbox event for product cleanup."""
        with transaction.atomic():
            super().soft_delete()
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import CustomerDeleted
            write_event(CustomerDeleted(
                tenant_id=str(self.tenant_id),
                customer_id=str(self.id),
            ))

    def __str__(self):
        return f"Customer({self.external_id})"

