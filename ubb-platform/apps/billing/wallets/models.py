from django.db import models

from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin


WALLET_TXN_TYPES = [
    ("TOP_UP", "Top Up"),
    ("USAGE_DEDUCTION", "Usage Deduction"),
    ("WITHDRAWAL", "Withdrawal"),
    ("REFUND", "Refund"),
    ("ADJUSTMENT", "Adjustment"),
    ("DISPUTE_DEDUCTION", "Dispute Deduction"),
    ("STRIPE_REFUND", "Stripe Refund"),
]


class Wallet(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="wallet"
    )
    balance_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="USD")

    class Meta:
        db_table = "ubb_wallet"

    def __str__(self):
        return f"Wallet({self.customer.external_id}: {self.balance_micros})"



class WalletTransaction(BaseModel):
    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="transactions"
    )
    transaction_type = models.CharField(
        max_length=20, choices=WALLET_TXN_TYPES, db_index=True
    )
    amount_micros = models.BigIntegerField()
    balance_after_micros = models.BigIntegerField()
    description = models.TextField(blank=True, default="")
    reference_id = models.CharField(max_length=255, blank=True, default="", db_index=True)
    idempotency_key = models.CharField(max_length=500, blank=True, null=True, db_index=True)
    usage_event_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ubb_wallet_transaction"
        indexes = [
            models.Index(fields=["wallet", "created_at"], name="idx_wallet_txn_wallet_created"),
        ]
        ordering = ["-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["wallet", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False),
                name="uq_wallet_txn_idempotency",
            ),
        ]

    def __str__(self):
        return f"WalletTxn({self.transaction_type}: {self.amount_micros})"


class CustomerBillingProfile(BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE,
        related_name="billing_profile"
    )
    min_balance_micros = models.BigIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_billing_profile"

    def __str__(self):
        return f"CustomerBillingProfile({self.customer.external_id})"
