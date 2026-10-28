from django.db import models

from core.currency_policy import usd_only_check
from core.models import BaseModel
from core.soft_delete import SoftDeleteMixin
from core.transitions import RECORD_RULE
from core.vocabulary import (
    GRANT_KIND_PAID,
    GRANT_KIND_PROMO,
    GRANT_SOURCE_API,
    GRANT_SOURCE_AUTO_TOP_UP,
    GRANT_SOURCE_CHECKOUT,
    GRANT_SOURCE_OTHER,
    GRANT_SOURCE_VALUES,
    GRANT_STATUS_ACTIVE,
    GRANT_STATUS_DEPLETED,
    GRANT_STATUS_EXPIRED,
    GRANT_STATUS_VOIDED,
    MOVEMENT_REASON_VALUES,
    WALLET_TRANSACTION_TYPE_ADJUSTMENT,
    WALLET_TRANSACTION_TYPE_DEBIT,
    WALLET_TRANSACTION_TYPE_DISPUTE_DEDUCTION,
    WALLET_TRANSACTION_TYPE_GRANT,
    WALLET_TRANSACTION_TYPE_GRANT_EXPIRY,
    WALLET_TRANSACTION_TYPE_GRANT_VOID,
    WALLET_TRANSACTION_TYPE_REFUND,
    WALLET_TRANSACTION_TYPE_STRIPE_REFUND,
    WALLET_TRANSACTION_TYPE_TOP_UP,
    WALLET_TRANSACTION_TYPE_USAGE_DEDUCTION,
    WALLET_TRANSACTION_TYPE_VALUES,
    WALLET_TRANSACTION_TYPE_WITHDRAWAL,
)


# What one wallet movement was — the registry's closed
# `wallet_transaction_type` (R10-W4), by reference. LOWERCASE since R10-W4
# (ruling 7): the ledger spelled them in upper case until then, outside the
# registry's token rule; `0014` moved the stored rows and
# `ck_wallet_transaction_type_known` admits exactly these afterwards.
WALLET_TXN_TYPES = [
    (WALLET_TRANSACTION_TYPE_TOP_UP, "Top Up"),
    (WALLET_TRANSACTION_TYPE_USAGE_DEDUCTION, "Usage Deduction"),
    (WALLET_TRANSACTION_TYPE_WITHDRAWAL, "Withdrawal"),
    (WALLET_TRANSACTION_TYPE_REFUND, "Refund"),
    (WALLET_TRANSACTION_TYPE_ADJUSTMENT, "Adjustment"),
    (WALLET_TRANSACTION_TYPE_DISPUTE_DEDUCTION, "Dispute Deduction"),
    (WALLET_TRANSACTION_TYPE_STRIPE_REFUND, "Stripe Refund"),
    (WALLET_TRANSACTION_TYPE_DEBIT, "Debit"),
    (WALLET_TRANSACTION_TYPE_GRANT, "Credit Grant"),
    (WALLET_TRANSACTION_TYPE_GRANT_EXPIRY, "Credit Grant Expiry"),
    (WALLET_TRANSACTION_TYPE_GRANT_VOID, "Credit Grant Void"),
]


class Wallet(SoftDeleteMixin, BaseModel):
    customer = models.OneToOneField(
        "customers.Customer", on_delete=models.CASCADE, related_name="wallet"
    )
    balance_micros = models.BigIntegerField(default=0)
    # CUR-1: lowercase everywhere; lock_for_billing sets the tenant currency
    # on lazy creation, this default only covers direct test/ORM creation.
    currency = models.CharField(max_length=3, default="usd")
    # Negative-balance visibility (#41, pin 10): when the balance last crossed
    # ≥0 → <0; null whenever the balance is ≥ 0. Maintained by save() below —
    # a sign-consistency invariant, not a call-site contract — so every
    # SAVE-based balance mutation (drawdown handler, credits, grants,
    # repairs, manual adjustments — all production paths today) keeps it
    # true without knowing it exists. A queryset .update(balance_micros=…)
    # bypasses save() and therefore this stamp. Purely observational:
    # nothing automatic ever reacts to it — collections stay between the
    # tenant, their customer, and Stripe.
    negative_since = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "ubb_wallet"
        # UBB v1 is USD-only (ADR-0023).
        constraints = [usd_only_check("currency", "ck_wallet_currency_usd")]

    def save(self, *args, **kwargs):
        # Self-healing negative_since: stamp on entering negative territory,
        # clear on recovery, preserve the original transition time while the
        # balance stays negative. Runs on the instance about to be persisted,
        # so it needs no old-balance read; callers passing update_fields get
        # the field appended only when it actually changed.
        from django.utils import timezone
        changed = None
        if self.balance_micros < 0 and self.negative_since is None:
            self.negative_since = timezone.now()
            changed = "negative_since"
        elif self.balance_micros >= 0 and self.negative_since is not None:
            self.negative_since = None
            changed = "negative_since"
        update_fields = kwargs.get("update_fields")
        if changed and update_fields is not None and changed not in update_fields:
            kwargs["update_fields"] = list(update_fields) + [changed]
        super().save(*args, **kwargs)

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
    # movement_reason categorises the movement — the registry's closed set,
    # held below by `ck_wallet_transaction_movement_reason_known` — and actor
    # is the caller-supplied operator or system identity. Both blank on
    # automated (usage/top-up/refund/...) txns. Named `reason_code` until
    # #479: that is the stop cause's public name, a different concept.
    movement_reason = models.CharField(max_length=32, blank=True, default="", db_index=True)
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
            # The registry's set, or none recorded (an automated movement).
            models.CheckConstraint(
                condition=models.Q(movement_reason="")
                | models.Q(movement_reason__in=sorted(MOVEMENT_REASON_VALUES)),
                name="ck_wallet_transaction_movement_reason_known",
            ),
            # The registry's eleven, lowercase (R10-W4, ruling 7). No other
            # spelling is admitted: an upper-case type is refused here, not
            # translated, and there is no per-concept token exception.
            models.CheckConstraint(
                condition=models.Q(
                    transaction_type__in=sorted(WALLET_TRANSACTION_TYPE_VALUES)),
                name="ck_wallet_transaction_type_known",
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


# A credit grant's kind, status and source — the registry's closed
# `grant_kind`, `grant_status` and `grant_source` (R10-W4), by reference.
# The source spelled `auto_topup` until R10-W4; one concept has one spelling
# (ADR-0006 §2), and `0014` moved the stored rows with the transaction types.
GRANT_KINDS = [(GRANT_KIND_PAID, "Paid"), (GRANT_KIND_PROMO, "Promo")]
GRANT_STATUSES = [
    (GRANT_STATUS_ACTIVE, "Active"),
    (GRANT_STATUS_DEPLETED, "Depleted"),
    (GRANT_STATUS_EXPIRED, "Expired"),
    (GRANT_STATUS_VOIDED, "Voided"),
]
GRANT_SOURCES = [
    (GRANT_SOURCE_CHECKOUT, "Checkout"),
    (GRANT_SOURCE_AUTO_TOP_UP, "Auto Top-Up"),
    (GRANT_SOURCE_API, "API"),
    (GRANT_SOURCE_OTHER, "Other"),
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
    status = models.CharField(max_length=10, choices=GRANT_STATUSES,
                              default=GRANT_STATUS_ACTIVE)
    source = models.CharField(max_length=20, choices=GRANT_SOURCES,
                              default=GRANT_SOURCE_OTHER)
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
            # UBB v1 is USD-only (ADR-0023).
            usd_only_check("currency", "ck_credit_grant_currency_usd"),
            # The registry's four sources (R10-W4): the run-together spelling
            # the automatic top-up's lots carried until then is refused.
            models.CheckConstraint(
                condition=models.Q(source__in=sorted(GRANT_SOURCE_VALUES)),
                name="ck_credit_grant_source_known",
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


#: WHAT RELEASED A RESERVATION — the kernel's terminal-transition listener
#: (the ordinary path: every terminal transition reaches it, #460), or the
#: backstop sweep over terminal work still holding one (a release here means
#: the listener's savepoint rolled back, and the sweep logs it as such).
RELEASED_BY_TERMINAL_TRANSITION = "terminal_transition"
RELEASED_BY_BACKSTOP_SWEEP = "backstop_sweep"
RELEASED_BY_CHOICES = [
    (RELEASED_BY_TERMINAL_TRANSITION, "The unit's terminal transition"),
    (RELEASED_BY_BACKSTOP_SWEEP, "The backstop sweep"),
]


class WalletReservation(BaseModel):
    """The agreed price a prepaid start reserved against the owner's wallet
    (#461, slice 6 §5, #139 §4.1 — Wallet policy).

    ONE ROW PER UNIT OF WORK, written in the same transaction as the start of
    a kind of work sold at one agreed price, for the price the start pinned,
    on the wallet the unit's Charge will draw down — the billing owner's.
    Affordability at a start is ``balance − open reservations`` tested against
    the tenant's own floors, and this table is the "open reservations" term:
    a row is OPEN while ``released_at`` is null and counts for nothing once
    released. A reservation moves neither the balance nor the ledger — it
    encumbers the affordability read and nothing else — so a reader of the
    wallet sees the balance, what is reserved against it, and the difference.

    Released on every terminal transition of the unit — a close in any of its
    three outcomes, a kill, an expiry, and each cascade onto contained work —
    through the kernel's terminal-transition listener registry
    (`apps/platform/work/hooks.py`; the listener is
    `wallets/reservations.release_on_terminal_transition`), and by the backstop
    sweep for a row the listener left behind. Which of the two released it is
    recorded, because a release by the sweep is evidence the ordinary path
    failed once.

    Prepaid only, by decision: a postpaid tenant has no wallet to encumber and
    a tenant that does not bill through UBB has no wallet at all; neither
    writes a row here. Event-priced work reserves nothing — it has no pinned
    price to reserve.

    ``task`` is a real foreign key onto the kernel's row (a product may import
    the kernel, ADR-001 rule 1) with no reverse accessor, so the kernel gains
    no attribute named by a product; the backstop sweep joins through it.

    THE RECORD'S WHOLE LIFECYCLE IS ONE RULE, declared as ``RECORD_RULE`` on
    every column rather than as a class per column
    (`docs/conventions/django-patterns.md`): a row is inserted once, at the
    start, and its one later transition is the release — ``released_at`` and
    ``released_by`` set together, once, by whichever of the two releasers
    reaches it first, and nothing else on the row ever changes. The check
    below holds the release's shape (a release names its releaser; an open
    row names none); the once-ness is held by both releasers writing through
    one filtered UPDATE (`reservations._release`, a no-op on a released row)
    and is proved by the repeated-close and second-sweep cases in
    `api/v1/tests/test_every_terminal_path_releases_the_reservation.py`.
    No trigger defends it at the database, which is the same footing
    `Wallet` and `WalletTransaction` stand on beside it.
    """
    tenant = models.ForeignKey(
        "tenants.Tenant", on_delete=models.CASCADE,
        related_name="wallet_reservations")
    #: The BILLING OWNER whose wallet is encumbered — the business for a pooled
    #: seat, otherwise the customer the work was started for.
    owner = models.ForeignKey(
        "customers.Customer", on_delete=models.CASCADE,
        related_name="wallet_reservations")
    task = models.OneToOneField(
        "work.Task", on_delete=models.CASCADE, related_name="+")
    amount_micros = models.BigIntegerField()
    released_at = models.DateTimeField(null=True, blank=True)
    released_by = models.CharField(
        max_length=20, choices=RELEASED_BY_CHOICES, blank=True, default="")

    transition_classes = {
        "id": RECORD_RULE, "created_at": RECORD_RULE, "updated_at": RECORD_RULE,
        "tenant": RECORD_RULE, "owner": RECORD_RULE, "task": RECORD_RULE,
        "amount_micros": RECORD_RULE, "released_at": RECORD_RULE,
        "released_by": RECORD_RULE,
    }

    class Meta:
        db_table = "ubb_wallet_reservation"
        indexes = [
            # The open-reservations read is one indexed sum per owner.
            models.Index(fields=["owner"], condition=models.Q(released_at__isnull=True),
                         name="idx_wallet_reservation_open"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(amount_micros__gte=0),
                name="ck_wallet_reservation_not_negative"),
            # A release records who released it, and nothing else does.
            models.CheckConstraint(
                condition=(models.Q(released_at__isnull=True, released_by="")
                           | models.Q(released_at__isnull=False)
                           & ~models.Q(released_by="")),
                name="ck_wallet_reservation_release_names_its_releaser"),
        ]

    def __str__(self):
        state = "open" if self.released_at is None else f"released:{self.released_by}"
        return f"WalletReservation({self.task_id}: {self.amount_micros} {state})"
