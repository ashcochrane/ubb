"""GrantLedger — lot accounting for expiring credit grants (F4.3).

Design:
- The wallet's exactly-once machinery is untouched: the (wallet,
  idempotency_key) partial unique constraint on WalletTransaction plus the
  wallet row lock from lock_for_billing(). Grants are LOTS layered on top.
- Wallet.balance_micros stays the single spendable cache. Base (non-expiring)
  money is DERIVED: base = balance - sum(remaining of active grants). It is
  never stored, so it cannot drift.
- Every method here MUST be called inside the caller's existing wallet lock +
  transaction (asserted via connection.in_atomic_block). Grant mutations ride
  the caller's idempotency keys; the only keys this module owns are
  expiry:{grant_id} (GRANT_EXPIRY) written by expire_due.

Invariants:
  G1: sum(remaining of active grants) <= max(balance, 0) at all times.
  G2 (conservation, per grant):
      granted == remaining + sum(allocations) + expired_micros + voided_micros
  G3: a grant expiry can NEVER drive the balance negative — the expiry debit
      is clamped to min(remaining, max(balance, 0)) (defense-in-depth even if
      G1 was previously dented).

Consumption order: expires_at ASC NULLS LAST, promo-before-paid on ties,
created_at, id. Unallocated remainder of any debit = base money (no row).
"""
import logging
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.models import Case, F, IntegerField, Sum, When
from django.utils import timezone

logger = logging.getLogger(__name__)


class GrantLedger:
    @staticmethod
    def _active_grants(wallet):
        """Active grants in consumption order (see module docstring)."""
        from apps.billing.wallets.models import CreditGrant

        return CreditGrant.objects.filter(wallet=wallet, status="active").order_by(
            F("expires_at").asc(nulls_last=True),
            Case(When(kind="promo", then=0), default=1, output_field=IntegerField()),
            "created_at",
            "id",
        )

    @staticmethod
    def expire_due(wallet, now=None):
        """Expire every active grant whose expires_at <= now. Exactly-once per
        grant via the expiry:{grant_id} WalletTransaction key (house I2
        savepoint pattern). The expiry debit is clamped (G3) so it can never
        drive the balance negative. remaining == 0 grants flip status only
        (no transaction). Caller holds the wallet lock.
        """
        from apps.billing.wallets.models import CreditGrant, WalletTransaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import CreditGrantExpired

        assert connection.in_atomic_block
        now = now or timezone.now()
        due = list(CreditGrant.objects.filter(
            wallet=wallet, status="active",
            expires_at__isnull=False, expires_at__lte=now,
        ).order_by("expires_at", "id"))
        for grant in due:
            if grant.remaining_micros <= 0:
                grant.status = "expired"
                grant.save(update_fields=["status", "updated_at"])
                continue
            # G3 clamp: never debit below zero even if G1 was previously dented.
            debit = min(grant.remaining_micros, max(wallet.balance_micros, 0))
            new_balance = wallet.balance_micros - debit
            try:
                with transaction.atomic():  # savepoint: I2 exactly-once backstop
                    WalletTransaction.objects.create(
                        wallet=wallet,
                        transaction_type="GRANT_EXPIRY",
                        amount_micros=-debit,
                        balance_after_micros=new_balance,
                        description=f"Credit grant expired ({grant.kind})",
                        reference_id=str(grant.id),
                        idempotency_key=f"expiry:{grant.id}",
                    )
            except IntegrityError:
                continue  # raced: another path already expired this grant
            wallet.balance_micros = new_balance
            wallet.save(update_fields=["balance_micros", "updated_at"])
            grant.expired_micros = grant.remaining_micros
            grant.remaining_micros = 0
            grant.status = "expired"
            grant.save(update_fields=[
                "expired_micros", "remaining_micros", "status", "updated_at"])
            write_event(CreditGrantExpired(
                tenant_id=str(grant.tenant_id),
                customer_id=str(wallet.customer_id),
                grant_id=str(grant.id),
                kind=grant.kind,
                expired_micros=grant.expired_micros,
                balance_micros=new_balance,
            ))

    @staticmethod
    def allocate(wallet, txn, amount, *, exclude_promo=False, prefer_grant=None,
                 allocation_type="usage"):
        """Consume up to ``amount`` from active grants in consumption order,
        FK'ing GrantAllocation rows to ``txn`` (the already-created debit).
        ``prefer_grant`` is consumed first (clawback). The unallocated
        remainder is base money — no row. Returns the total allocated.
        Caller holds the wallet lock; the balance decrement is the caller's.
        """
        from apps.billing.wallets.models import GrantAllocation

        assert connection.in_atomic_block
        if amount <= 0:
            return 0
        grants = list(GrantLedger._active_grants(wallet))
        if exclude_promo:
            grants = [g for g in grants if g.kind != "promo"]
        if prefer_grant is not None:
            grants = [prefer_grant] + [g for g in grants if g.id != prefer_grant.id]
        left = amount
        rows = []
        for grant in grants:
            if left <= 0:
                break
            take = min(grant.remaining_micros, left)
            if take <= 0:
                continue
            grant.remaining_micros -= take
            fields = ["remaining_micros", "updated_at"]
            if grant.remaining_micros == 0 and grant.status == "active":
                grant.status = "depleted"
                fields.append("status")
            grant.save(update_fields=fields)
            rows.append(GrantAllocation(
                grant=grant, wallet_transaction=txn,
                amount_micros=take, allocation_type=allocation_type))
            left -= take
        if rows:
            GrantAllocation.objects.bulk_create(rows)
        return amount - left

    @staticmethod
    def create_grant(wallet, tenant_id, *, kind, amount_micros, expires_at,
                     source, source_reference, txn, currency=None):
        """Create a grant lot for a credit that just landed as ``txn`` — same
        savepoint as the credit WalletTransaction, so the lot inherits the
        credit's exactly-once key. If the pre-credit balance was negative the
        credit first pays the debt: that part is immediately self-allocated as
        ``overage_recoup`` so G1 holds (the recouped part is not spendable
        grant money). Returns the CreditGrant.
        """
        from apps.billing.wallets.models import CreditGrant, GrantAllocation

        assert connection.in_atomic_block
        grant = CreditGrant.objects.create(
            tenant_id=tenant_id,
            wallet=wallet,
            kind=kind,
            granted_micros=amount_micros,
            remaining_micros=amount_micros,
            currency=currency or wallet.currency,
            expires_at=expires_at,
            source=source,
            source_reference=source_reference,
            source_transaction=txn,
            status="active",
        )
        # Pre-credit balance derived from the credit txn itself (robust to
        # whether the caller bumps wallet.balance_micros before or after).
        old_balance = txn.balance_after_micros - txn.amount_micros
        if old_balance < 0:
            recoup = min(amount_micros, -old_balance)
            grant.remaining_micros -= recoup
            fields = ["remaining_micros", "updated_at"]
            if grant.remaining_micros == 0:
                grant.status = "depleted"
                fields.append("status")
            grant.save(update_fields=fields)
            GrantAllocation.objects.create(
                grant=grant, wallet_transaction=txn,
                amount_micros=recoup, allocation_type="overage_recoup")
        return grant

    @staticmethod
    def clawback(wallet, txn, amount, *, source_grant=None):
        """Restore G1 after a clawback debit (dispute lost / Stripe refund)
        whose WalletTransaction ``txn`` already decremented the balance.

        Naive source-lot-only voiding breaks G1 when the source lot was
        partially consumed, so this CASCADES:
          1. Void the source lot's remaining FIRST, up to the clawed-back
             amount (the reversed money was that lot's money) — recorded as a
             "clawback" allocation against the source grant; the lot's status
             becomes "voided" when zeroed.
          2. Consume remaining from OTHER active lots in normal consumption
             order until sum(remaining(active)) <= max(balance, 0) holds again.
        All in the caller's transaction, under the wallet lock.
        """
        from apps.billing.wallets.models import CreditGrant, GrantAllocation

        assert connection.in_atomic_block
        # 1. Source lot first.
        if source_grant is not None and source_grant.remaining_micros > 0 \
                and source_grant.status == "active":
            take = min(source_grant.remaining_micros, amount)
            if take > 0:
                source_grant.remaining_micros -= take
                fields = ["remaining_micros", "updated_at"]
                if source_grant.remaining_micros == 0:
                    source_grant.status = "voided"
                    fields.append("status")
                source_grant.save(update_fields=fields)
                GrantAllocation.objects.create(
                    grant=source_grant, wallet_transaction=txn,
                    amount_micros=take, allocation_type="clawback")
        # 2. Cascade until G1 holds again.
        active_sum = CreditGrant.objects.filter(
            wallet=wallet, status="active",
        ).aggregate(total=Sum("remaining_micros"))["total"] or 0
        excess = active_sum - max(wallet.balance_micros, 0)
        if excess > 0:
            GrantLedger.allocate(wallet, txn, excess, allocation_type="clawback")

    @staticmethod
    def promo_remaining(wallet):
        """Total remaining promo credit (active lots). Promo is not withdrawable."""
        from apps.billing.wallets.models import CreditGrant

        return CreditGrant.objects.filter(
            wallet=wallet, status="active", kind="promo",
        ).aggregate(total=Sum("remaining_micros"))["total"] or 0

    @staticmethod
    def balance_summary(wallet):
        """Read-only rollup for balance responses: active promo remaining,
        total remaining that can expire, and the soonest expiry."""
        from django.db.models import Min
        from apps.billing.wallets.models import CreditGrant

        agg = CreditGrant.objects.filter(
            wallet=wallet, status="active",
            expires_at__isnull=False, remaining_micros__gt=0,
        ).aggregate(expiring=Sum("remaining_micros"), next_expiry=Min("expires_at"))
        return {
            "promo_micros": GrantLedger.promo_remaining(wallet),
            "expiring_micros": agg["expiring"] or 0,
            "next_expiry_at": agg["next_expiry"].isoformat() if agg["next_expiry"] else None,
        }

    @staticmethod
    def topup_grant_expires_at(customer_id, now=None):
        """Expiry timestamp for a paid top-up grant, from the billing owner's
        CustomerBillingProfile.topup_grant_expiry_days. NULL profile/field =
        top-ups never expire (legacy)."""
        from apps.billing.wallets.models import CustomerBillingProfile

        profile = CustomerBillingProfile.objects.filter(
            customer_id=customer_id,
        ).only("topup_grant_expiry_days").first()
        days = profile.topup_grant_expiry_days if profile else None
        if not days:
            return None
        return (now or timezone.now()) + timedelta(days=days)
