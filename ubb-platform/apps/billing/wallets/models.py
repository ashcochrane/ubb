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
    ("DEBIT", "Debit"),  # written by /debit (billing_endpoints) — was missing from choices
    ("GRANT", "Credit Grant"),
    ("GRANT_EXPIRY", "Credit Grant Expiry"),
    ("GRANT_VOID", "Credit Grant Void"),
]


class Wallet(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="wallet"
    )
    balance_micros = models.BigIntegerField(default=0)
    # CUR-1: lowercase everywhere; lock_for_billing sets the tenant currency
    # on lazy creation, this default only covers direct test/ORM creation.
    currency = models.CharField(max_length=3, default="usd")

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
    # Phase 1 attribution for manual adjustments (the debit/credit escape hatch):
    # reason_code categorizes the movement; actor is the caller-supplied operator
    # or system identity. Blank on automated (usage/top-up/refund/...) txns.
    reason_code = models.CharField(max_length=32, blank=True, default="", db_index=True)
    actor = models.CharField(max_length=255, blank=True, default="")

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
    # Soft floor (#40, spec §F): per-customer override for the wind-down line
    # — same orientation as min_balance_micros (the line is -value; negative
    # values place it above zero). NULL = inherit the tenant default. Must
    # resolve to a line at or above the hard floor's (the resolver clamps).
    soft_min_balance_micros = models.BigIntegerField(null=True, blank=True)
    # F4.3: when set, paid top-up credits (auto-topup + checkout) become a PAID
    # grant expiring this many days after the credit lands. NULL = top-ups
    # never expire (legacy behavior, the default).
    topup_grant_expiry_days = models.PositiveIntegerField(null=True, blank=True)

    class Meta:
        db_table = "ubb_customer_billing_profile"

    def __str__(self):
        return f"CustomerBillingProfile({self.customer.external_id})"


GRANT_KINDS = [("paid", "Paid"), ("promo", "Promo")]
GRANT_STATUSES = [
    ("active", "Active"),
    ("depleted", "Depleted"),
    ("expired", "Expired"),
    ("voided", "Voided"),
]
GRANT_SOURCES = [
    ("checkout", "Checkout"),
    ("auto_topup", "Auto Top-Up"),
    ("api", "API"),
    ("other", "Other"),
]


class CreditGrant(BaseModel):
    """A LOT of expiring (or promo) credit layered on the prepaid wallet (F4.3).

    Wallet.balance_micros stays the single spendable cache; base money is
    DERIVED (balance - sum(remaining of active grants)), never stored, so it
    cannot drift. Every grant mutation happens inside the caller's existing
    wallet lock + transaction, riding the caller's idempotency keys.

    Conservation per grant:
        granted == remaining + sum(allocations.amount - allocations.refunded)
                   + expired_micros + voided_micros
    Per wallet (G1): sum(remaining of active grants) <= max(balance, 0).
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE, related_name="credit_grants"
    )
    wallet = models.ForeignKey(
        Wallet, on_delete=models.CASCADE, related_name="credit_grants"
    )
    kind = models.CharField(max_length=10, choices=GRANT_KINDS)
    granted_micros = models.BigIntegerField()
    remaining_micros = models.BigIntegerField()
    expired_micros = models.BigIntegerField(default=0)
    voided_micros = models.BigIntegerField(default=0)
    currency = models.CharField(max_length=3, default="usd")  # CUR-1: lowercase
    expires_at = models.DateTimeField(null=True, blank=True)
    warning_sent_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=10, choices=GRANT_STATUSES, default="active")
    source = models.CharField(max_length=20, choices=GRANT_SOURCES, default="other")
    source_reference = models.CharField(max_length=255, blank=True, default="")
    source_transaction = models.OneToOneField(
        WalletTransaction, on_delete=models.SET_NULL, null=True, blank=True,
        related_name="credit_grant",
    )

    class Meta:
        db_table = "ubb_credit_grant"
        indexes = [
            models.Index(fields=["wallet", "status", "expires_at"],
                         name="idx_grant_wallet_status_exp"),
            models.Index(fields=["status", "expires_at", "warning_sent_at"],
                         name="idx_grant_status_exp_warn"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(remaining_micros__gte=0)
                & models.Q(remaining_micros__lte=models.F("granted_micros")),
                name="ck_grant_remaining_bounds",
            ),
        ]

    def __str__(self):
        return f"CreditGrant({self.kind}: {self.remaining_micros}/{self.granted_micros} [{self.status}])"


GRANT_ALLOCATION_TYPES = [
    ("usage", "Usage"),
    ("withdrawal", "Withdrawal"),
    ("clawback", "Clawback"),
    ("overage_recoup", "Overage Recoup"),
]


class GrantAllocation(BaseModel):
    """Audit row: how much of a debit (or recoup) was funded by which grant lot.

    ``refunded_micros`` is the cumulative slice of this allocation that has been
    RE-FUNDED back to the lot by a usage refund (GrantLedger.refund). Rows stay
    append-only for the consumed amount; a refund never deletes or shrinks
    ``amount_micros`` — it increments ``refunded_micros`` (capped at
    ``amount_micros``) and the grant's ``remaining_micros`` by the same value,
    keeping the conservation equation
        granted == remaining + sum(amount - refunded) + expired + voided
    exact at every step.
    """
    grant = models.ForeignKey(
        CreditGrant, on_delete=models.CASCADE, related_name="allocations"
    )
    wallet_transaction = models.ForeignKey(
        WalletTransaction, on_delete=models.CASCADE, related_name="grant_allocations"
    )
    amount_micros = models.BigIntegerField()
    refunded_micros = models.BigIntegerField(default=0)
    allocation_type = models.CharField(max_length=20, choices=GRANT_ALLOCATION_TYPES)

    class Meta:
        db_table = "ubb_grant_allocation"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_micros__gt=0),
                name="ck_grant_allocation_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(refunded_micros__gte=0)
                & models.Q(refunded_micros__lte=models.F("amount_micros")),
                name="ck_grant_alloc_refund_bounds",
            ),
        ]

    def __str__(self):
        return f"GrantAllocation({self.allocation_type}: {self.amount_micros})"
