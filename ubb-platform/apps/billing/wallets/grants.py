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
      granted == remaining + sum(allocations.amount - allocations.refunded)
                 + expired_micros + voided_micros
      (refunded is the slice of a usage allocation re-funded back to the lot
      by GrantLedger.refund; a clawed-back source lot's remaining moves to
      voided_micros, NOT into an allocation row — one representation each.)
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

        Returns the number of grants expired by THIS call (status flips +
        winning debits), so the beat can report wallets actually expired-upon.
        """
        from apps.billing.topups.models import AutoTopUpConfig
        from apps.billing.wallets.models import CreditGrant, WalletTransaction
        from apps.platform.events.outbox import write_event
        from apps.platform.events.schemas import BalanceLow, CreditGrantExpired

        assert connection.in_atomic_block
        now = now or timezone.now()
        due = list(CreditGrant.objects.filter(
            wallet=wallet, status="active",
            expires_at__isnull=False, expires_at__lte=now,
        ).order_by("expires_at", "id"))
        expired_count = 0
        for grant in due:
            if grant.remaining_micros <= 0:
                grant.status = "expired"
                grant.save(update_fields=["status", "updated_at"])
                expired_count += 1
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
                # raced: another path already expired this grant
                logger.warning("grants.expiry_skip_dup", extra={"data": {
                    "grant_id": str(grant.id), "wallet_id": str(wallet.id)}})
                continue
            wallet.balance_micros = new_balance
            wallet.save(update_fields=["balance_micros", "updated_at"])
            # += (not =): a partially clawed-back lot may already carry
            # voided_micros; expiry must never clobber sibling buckets.
            grant.expired_micros += grant.remaining_micros
            grant.remaining_micros = 0
            grant.status = "expired"
            grant.save(update_fields=[
                "expired_micros", "remaining_micros", "status", "updated_at"])
            expired_count += 1
            write_event(CreditGrantExpired(
                tenant_id=str(grant.tenant_id),
                customer_id=str(wallet.customer_id),
                grant_id=str(grant.id),
                kind=grant.kind,
                expired_micros=grant.expired_micros,
                balance_micros=new_balance,
            ))
            # An expiry debit can drop the balance below the auto-top-up
            # trigger exactly like a usage drawdown. Mirror the drawdown
            # winning-branch semantics (apps/billing/handlers.py): emit only
            # in the winning (exactly-once) debit branch, condition is simply
            # new_balance < threshold — the debit's idempotency key is the
            # dedup, same as the drawdown path. debit > 0 guard: a clamped
            # no-op debit changed nothing, so it must not re-alert.
            if debit > 0:
                config = AutoTopUpConfig.objects.filter(
                    customer_id=wallet.customer_id, is_enabled=True).first()
                if config and new_balance < config.trigger_threshold_micros:
                    write_event(BalanceLow(
                        tenant_id=str(grant.tenant_id),
                        customer_id=str(wallet.customer_id),
                        balance_micros=new_balance,
                        threshold_micros=config.trigger_threshold_micros,
                        suggested_topup_micros=config.top_up_amount_micros,
                    ))
        return expired_count

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
             amount (the reversed money was that lot's money) — recorded in
             the lot's voided_micros (the SAME bucket the void endpoint uses,
             so voided reporting sums match; deliberately NOT also written as
             a clawback allocation — one representation per micro keeps the
             conservation equation exact). The lot's status becomes "voided"
             when zeroed.
          2. Consume remaining from OTHER active lots in normal consumption
             order until sum(remaining(active)) <= max(balance, 0) holds again
             — these ARE "clawback" allocations (consumption, not voiding).
        All in the caller's transaction, under the wallet lock.
        """
        from apps.billing.wallets.models import CreditGrant

        assert connection.in_atomic_block
        # 1. Source lot first.
        if source_grant is not None and source_grant.remaining_micros > 0 \
                and source_grant.status == "active":
            take = min(source_grant.remaining_micros, amount)
            if take > 0:
                source_grant.remaining_micros -= take
                source_grant.voided_micros += take
                fields = ["remaining_micros", "voided_micros", "updated_at"]
                if source_grant.remaining_micros == 0:
                    source_grant.status = "voided"
                    fields.append("status")
                source_grant.save(update_fields=fields)
        # 2. Cascade until G1 holds again.
        active_sum = CreditGrant.objects.filter(
            wallet=wallet, status="active",
        ).aggregate(total=Sum("remaining_micros"))["total"] or 0
        excess = active_sum - max(wallet.balance_micros, 0)
        if excess > 0:
            GrantLedger.allocate(wallet, txn, excess, allocation_type="clawback")

    @staticmethod
    def refund(wallet, original_txn):
        """Lot-aware usage refund: re-fund the grant lots that funded
        ``original_txn`` (a USAGE_DEDUCTION). The caller has ALREADY credited
        the full refund to wallet.balance_micros; this method re-attributes as
        much of that credit as possible back to the funding lots so a
        promo-funded charge refunds as promo (never withdrawable), not cash.

        Per usage allocation of the original debit, the re-fundable slice is
            min(amount - refunded,            # never re-fund the same micro twice
                granted - remaining,          # CheckConstraint: remaining <= granted
                G1 budget)                    # see below
        applied as remaining += take, allocation.refunded += take — which
        keeps G2 (granted == remaining + sum(amount - refunded) + expired +
        voided) exact. A depleted lot that regains remaining flips back to
        active.

        EXPIRED / VOIDED lots are NOT re-funded: their unspent remainder was
        already destroyed (expiry debit) or clawed back (dispute/refund/void),
        so re-inflating them would double-create money. That share of the
        refund stays as base credit.

        G1 budget (overage-recoup parity with create_grant): if the wallet was
        overdrawn, the refund credit first pays the debt — only the part that
        lifts the balance above the active-lot total may go back into lots,
        so sum(remaining(active)) <= max(balance, 0) keeps holding.

        Returns the total re-funded into lots (the remainder stays base).
        Caller holds the wallet lock.
        """
        from apps.billing.wallets.models import CreditGrant

        assert connection.in_atomic_block
        if original_txn is None:
            return 0
        allocations = list(
            original_txn.grant_allocations.filter(allocation_type="usage")
            .select_related("grant").order_by("created_at", "id"))
        if not allocations:
            return 0
        active_sum = CreditGrant.objects.filter(
            wallet=wallet, status="active",
        ).aggregate(total=Sum("remaining_micros"))["total"] or 0
        budget = max(wallet.balance_micros, 0) - active_sum
        total = 0
        for alloc in allocations:
            if budget <= 0:
                break
            grant = alloc.grant
            if grant.status not in ("active", "depleted"):
                continue  # expired/voided share lands as base (see docstring)
            take = min(alloc.amount_micros - alloc.refunded_micros,
                       grant.granted_micros - grant.remaining_micros,
                       budget)
            if take <= 0:
                continue
            grant.remaining_micros += take
            fields = ["remaining_micros", "updated_at"]
            if grant.status == "depleted":
                grant.status = "active"
                fields.append("status")
            grant.save(update_fields=fields)
            alloc.refunded_micros += take
            alloc.save(update_fields=["refunded_micros", "updated_at"])
            budget -= take
            total += take
        return total

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
