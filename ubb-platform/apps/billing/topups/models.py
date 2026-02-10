from django.db import models

from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


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


class AutoTopUpConfig(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="auto_top_up_config"
    )
    is_enabled = models.BooleanField(default=False)
    trigger_threshold_micros = models.BigIntegerField(default=10_000_000)  # $10
    top_up_amount_micros = models.BigIntegerField(default=20_000_000)  # $20

    class Meta:
        db_table = "ubb_auto_top_up_config"

    def __str__(self):
        return f"AutoTopUp({self.customer.external_id}: enabled={self.is_enabled})"


class TopUpAttempt(BaseModel):
    """
    Persisted charge attempt -- created before calling Stripe.
    Provides deterministic idempotency keys for Stripe API calls.
    """
    customer = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE, related_name="top_up_attempts"
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
