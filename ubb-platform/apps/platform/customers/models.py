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


class AutoTopUpConfig(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        Customer, on_delete=models.CASCADE, related_name="auto_top_up_config"
    )
    is_enabled = models.BooleanField(default=False)
    trigger_threshold_micros = models.BigIntegerField(default=10_000_000)  # $10
    top_up_amount_micros = models.BigIntegerField(default=20_000_000)  # $20

    class Meta:
        db_table = "ubb_auto_top_up_config"

    def __str__(self):
        return f"AutoTopUp({self.customer.external_id}: enabled={self.is_enabled})"


TOP_UP_ATTEMPT_TRIGGERS = [
    ("manual", "Manual"),
    ("auto_topup", "Auto Top-Up"),
    ("widget", "Widget"),
]

TOP_UP_ATTEMPT_STATUSES = [
    ("pending", "Pending"),
    ("succeeded", "Succeeded"),
    ("failed", "Failed"),
    ("expired", "Expired"),
]


class TopUpAttempt(BaseModel):
    """
    Persisted charge attempt — created before calling Stripe.
    Provides deterministic idempotency keys for Stripe API calls.
    """
    customer = models.ForeignKey(
        Customer, on_delete=models.CASCADE, related_name="top_up_attempts"
    )
    amount_micros = models.PositiveBigIntegerField()
    trigger = models.CharField(max_length=20, choices=TOP_UP_ATTEMPT_TRIGGERS)
    status = models.CharField(
        max_length=20, choices=TOP_UP_ATTEMPT_STATUSES, default="pending", db_index=True
    )
    stripe_payment_intent_id = models.CharField(max_length=255, blank=True, null=True)
    stripe_checkout_session_id = models.CharField(max_length=255, blank=True, null=True)
    failure_reason = models.JSONField(null=True, blank=True)

    class Meta:
        db_table = "ubb_top_up_attempt"
        constraints = [
            models.UniqueConstraint(
                fields=["customer"],
                condition=models.Q(status="pending", trigger="auto_topup"),
                name="uq_one_pending_auto_topup_per_customer",
            ),
        ]

    def __str__(self):
        return f"TopUpAttempt({self.customer.external_id}: {self.trigger} {self.status})"


# Re-exports for backward compatibility (to be removed after all imports are updated)
from apps.billing.wallets.models import Wallet, WalletTransaction, WALLET_TXN_TYPES  # noqa: E402, F401
