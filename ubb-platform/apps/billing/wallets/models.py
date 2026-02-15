from django.db import models, transaction

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

    @transaction.atomic
    def deduct(self, amount_micros, description="", reference_id=""):
        """Deduct from wallet balance. Allows negative balance."""
        wallet = Wallet.objects.select_for_update().get(pk=self.pk)
        wallet.balance_micros -= amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])
        self.balance_micros = wallet.balance_micros

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="USAGE_DEDUCTION",
            amount_micros=-amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=description,
            reference_id=reference_id,
        )
        return txn

    @transaction.atomic
    def credit(self, amount_micros, description="", reference_id="",
               transaction_type="TOP_UP"):
        """Credit wallet balance."""
        wallet = Wallet.objects.select_for_update().get(pk=self.pk)
        wallet.balance_micros += amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])
        self.balance_micros = wallet.balance_micros

        txn = WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type=transaction_type,
            amount_micros=amount_micros,
            balance_after_micros=wallet.balance_micros,
            description=description,
            reference_id=reference_id,
        )
        return txn


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
