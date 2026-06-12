"""Fix 8 — seeded random-sequence invariant fuzz for the grant lot ledger.

~200 random ops against ONE wallet, each driven through the real money path
(or an exact inline mirror of the endpoint where the path needs HTTP auth):
grant paid/promo with/without expiry, usage debit, withdraw, expiry sweep
with time travel, void, dispute clawback, lot-aware usage refund.

After EVERY op assert:
  G1:     sum(remaining of active grants) <= max(balance, 0)
  G2:     per grant, granted == remaining + sum(alloc.amount - alloc.refunded)
          + expired_micros + voided_micros
  Ledger: balance == sum of all WalletTransaction amounts
On failure the full op sequence is printed for deterministic replay
(random.Random(42)).
"""
import random
import uuid
from datetime import timedelta

import pytest
from django.db import transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.locking import lock_for_billing
from apps.billing.wallets.grants import GrantLedger
from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
from apps.billing.wallets.tasks import expire_credit_grants
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant

M = 1_000_000
OPS = 200


@pytest.mark.django_db
class TestGrantLedgerInvariantFuzz:
    def _check(self, w, i, ops_log):
        w.refresh_from_db()
        problems = []
        ledger = WalletTransaction.objects.filter(wallet=w).aggregate(
            t=Sum("amount_micros"))["t"] or 0
        if w.balance_micros != ledger:
            problems.append(
                f"balance {w.balance_micros} != ledger sum {ledger}")
        active_sum = CreditGrant.objects.filter(
            wallet=w, status="active").aggregate(
            t=Sum("remaining_micros"))["t"] or 0
        if active_sum > max(w.balance_micros, 0):
            problems.append(
                f"G1: active remaining {active_sum} > "
                f"max(balance {w.balance_micros}, 0)")
        annotated = CreditGrant.objects.filter(wallet=w).annotate(
            a=Coalesce(Sum("allocations__amount_micros"), 0),
            r=Coalesce(Sum("allocations__refunded_micros"), 0))
        for g in annotated:
            expected = (g.remaining_micros + (g.a - g.r)
                        + g.expired_micros + g.voided_micros)
            if g.granted_micros != expected:
                problems.append(
                    f"G2 grant {g.id} [{g.status}]: granted "
                    f"{g.granted_micros} != remaining {g.remaining_micros} "
                    f"+ (alloc {g.a} - refunded {g.r}) + expired "
                    f"{g.expired_micros} + voided {g.voided_micros}")
        if problems:
            seq = "\n".join(f"  {n:3d}: {op}" for n, op in enumerate(ops_log))
            pytest.fail(
                f"invariants broken after op #{i} ({ops_log[-1]}):\n  "
                + "\n  ".join(problems) + f"\nop sequence:\n{seq}")

    def test_random_sequence_holds_invariants(self):
        rng = random.Random(42)
        tenant = Tenant.objects.create(
            name="FUZZ", products=["metering", "billing"],
            billing_mode="prepaid")
        customer = Customer.objects.create(tenant=tenant, external_id="fuzz")
        w = Wallet.objects.create(customer=customer, balance_micros=0)
        ops_log = []
        debited = []  # (event_id, cost) pairs that produced a USAGE_DEDUCTION
        start = timezone.now()

        def op_grant():
            kind = rng.choice(["paid", "promo"])
            amount = rng.randint(1, 50) * M
            expires = rng.choice(
                [None, start + timedelta(days=rng.randint(1, 30))])
            key = f"grant:{uuid.uuid4()}"
            with transaction.atomic():
                wallet, _c = lock_for_billing(w.customer_id)
                new_balance = wallet.balance_micros + amount
                txn = WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="GRANT",
                    amount_micros=amount, balance_after_micros=new_balance,
                    idempotency_key=key)
                GrantLedger.create_grant(
                    wallet, tenant.id, kind=kind, amount_micros=amount,
                    expires_at=expires, source="api", source_reference=key,
                    txn=txn)
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
            return (f"grant kind={kind} amount={amount} "
                    f"expires={'yes' if expires else 'no'}")

        def op_debit():
            cost = rng.randint(1, 40) * M
            ev = str(uuid.uuid4())
            handle_usage_recorded_billing(str(uuid.uuid4()), {
                "tenant_id": str(tenant.id), "customer_id": str(customer.id),
                "event_id": ev, "billing_owner_id": str(customer.id),
                "cost_micros": cost})
            debited.append((ev, cost))
            return f"debit cost={cost} ev={ev[:8]}"

        def op_withdraw():
            with transaction.atomic():
                wallet, _c = lock_for_billing(w.customer_id)
                GrantLedger.expire_due(wallet)
                avail = (wallet.balance_micros
                         - GrantLedger.promo_remaining(wallet))
                if avail <= 0:
                    return "withdraw skipped (nothing available)"
                amount = min(rng.randint(1, max(avail // M, 1)) * M, avail)
                wallet.balance_micros -= amount
                wallet.save(update_fields=["balance_micros", "updated_at"])
                txn = WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="WITHDRAWAL",
                    amount_micros=-amount,
                    balance_after_micros=wallet.balance_micros,
                    idempotency_key=f"wd:{uuid.uuid4()}")
                GrantLedger.allocate(wallet, txn, amount, exclude_promo=True,
                                     allocation_type="withdrawal")
            return f"withdraw amount={amount}"

        def op_expire_sweep():
            candidates = list(CreditGrant.objects.filter(
                wallet=w, status="active", expires_at__isnull=False,
            ).values_list("id", flat=True))
            label = "expire_sweep (no expiring lots)"
            if candidates:
                victim = rng.choice(candidates)
                CreditGrant.objects.filter(pk=victim).update(
                    expires_at=timezone.now() - timedelta(seconds=1))
                label = f"expire_sweep time-travelled lot={victim}"
            expire_credit_grants()
            return label

        def op_void():
            with transaction.atomic():
                wallet, _c = lock_for_billing(w.customer_id)
                GrantLedger.expire_due(wallet)
                candidates = list(CreditGrant.objects.filter(
                    wallet=wallet, status="active",
                ).values_list("id", flat=True))
                if not candidates:
                    return "void skipped (no active lots)"
                grant = CreditGrant.objects.get(pk=rng.choice(candidates))
                debit = min(grant.remaining_micros,
                            max(wallet.balance_micros, 0))
                new_balance = wallet.balance_micros - debit
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="GRANT_VOID",
                    amount_micros=-debit, balance_after_micros=new_balance,
                    reference_id=str(grant.id),
                    idempotency_key=f"grant_void:{grant.id}")
                wallet.balance_micros = new_balance
                wallet.save(update_fields=["balance_micros", "updated_at"])
                grant.voided_micros += grant.remaining_micros
                grant.remaining_micros = 0
                grant.status = "voided"
                grant.save(update_fields=[
                    "voided_micros", "remaining_micros", "status",
                    "updated_at"])
            return f"void lot={grant.id} debit={debit}"

        def op_clawback():
            amount = rng.randint(1, 30) * M
            with transaction.atomic():
                wallet, _c = lock_for_billing(w.customer_id)
                GrantLedger.expire_due(wallet)
                source = None
                if rng.random() < 0.7:
                    ids = list(CreditGrant.objects.filter(
                        wallet=wallet).values_list("id", flat=True))
                    if ids:
                        source = CreditGrant.objects.get(pk=rng.choice(ids))
                wallet.balance_micros -= amount
                wallet.save(update_fields=["balance_micros", "updated_at"])
                txn = WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="DISPUTE_DEDUCTION",
                    amount_micros=-amount,
                    balance_after_micros=wallet.balance_micros,
                    idempotency_key=f"dispute:{uuid.uuid4()}")
                GrantLedger.clawback(wallet, txn, amount, source_grant=source)
            return (f"clawback amount={amount} "
                    f"source={source.id if source is not None else None}")

        def op_refund():
            if not debited:
                return "refund skipped (nothing debited)"
            # Deliberately allows re-refunding the same event under a new
            # key: the refunded_micros caps must keep the lots exact.
            ev, cost = rng.choice(debited)
            with transaction.atomic():
                wallet, _c = lock_for_billing(w.customer_id)
                GrantLedger.expire_due(wallet)
                original = WalletTransaction.objects.filter(
                    wallet=wallet,
                    idempotency_key=f"usage_deduction:{ev}").first()
                wallet.balance_micros += cost
                wallet.save(update_fields=["balance_micros", "updated_at"])
                WalletTransaction.objects.create(
                    wallet=wallet, transaction_type="REFUND",
                    amount_micros=cost,
                    balance_after_micros=wallet.balance_micros,
                    reference_id=ev,
                    idempotency_key=f"refund:{ev}:{uuid.uuid4()}")
                refunded = GrantLedger.refund(wallet, original)
            return f"refund ev={ev[:8]} cost={cost} to_lots={refunded}"

        weighted = ([op_grant] * 4 + [op_debit] * 5 + [op_withdraw] * 2
                    + [op_expire_sweep] * 2 + [op_void] + [op_clawback]
                    + [op_refund] * 2)
        for i in range(OPS):
            op_fn = rng.choice(weighted)
            ops_log.append(op_fn())
            self._check(w, i, ops_log)
