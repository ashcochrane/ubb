from django.db import models

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
    arrears_threshold_micros = models.BigIntegerField(null=True, blank=True)
    metadata = models.JSONField(default=dict)

    class Meta:
        db_table = "ubb_customer"
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "external_id"],
                name="uq_customer_tenant_external",
            ),
        ]

    def get_arrears_threshold(self):
        """Return customer-level threshold or fall back to tenant default."""
        if self.arrears_threshold_micros is not None:
            return self.arrears_threshold_micros
        return self.tenant.arrears_threshold_micros

    def save(self, *args, **kwargs):
        is_new = self._state.adding
        super().save(*args, **kwargs)
        if is_new:
            Wallet.objects.create(customer=self)

    def soft_delete(self):
        """Cascade soft delete to related records."""
        super().soft_delete()
        try:
            self.wallet.soft_delete()
        except Wallet.DoesNotExist:
            pass
        try:
            self.auto_top_up_config.soft_delete()
        except AutoTopUpConfig.DoesNotExist:
            pass

    def __str__(self):
        return f"Customer({self.external_id})"


# Re-exports for backward compatibility (to be removed after all imports are updated)
from apps.billing.wallets.models import Wallet, WalletTransaction, WALLET_TXN_TYPES  # noqa: E402, F401
from apps.billing.topups.models import AutoTopUpConfig, TopUpAttempt, TOP_UP_ATTEMPT_TRIGGERS, TOP_UP_ATTEMPT_STATUSES  # noqa: E402, F401
