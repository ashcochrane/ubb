from django.db import models, transaction

from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


CUSTOMER_STATUS_CHOICES = [
    ("active", "Active"),
    ("suspended", "Suspended"),
    ("closed", "Closed"),
]


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

    class Meta:
        db_table = "ubb_customer"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uq_customer_tenant_external",
            ),
        ]

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

