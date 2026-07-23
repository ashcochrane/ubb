"""F4.3 — true multi-thread concurrency proofs for the grant lot ledger.

Same harness style as test_concurrency_races.py (which stays UNMODIFIED as the
zero-grant back-compat proof): TransactionTestCase + threading.Barrier so both
workers hit the critical section simultaneously through real Postgres row
locking; each worker closes its thread-local connection.

Invariants asserted:
    (c) Concurrent drawdown WITH grants — exactly ONE debit, the lot's
        remaining decremented exactly once, allocations written once.
    (d) Expiry vs drawdown at the expiry boundary — whichever order wins, the
        expired lot funds nothing: ONE expiry txn, no allocation referencing
        the expired grant, G1 holds. Plus: two concurrent expiry sweeps
        produce ONE expiry:{grant_id} txn.
"""

import threading
import uuid
from dataclasses import asdict
from datetime import timedelta
from unittest.mock import patch

from django.db import connection, transaction
from django.test import TransactionTestCase
from django.utils import timezone

from apps.billing.locking import lock_for_billing
from apps.billing.wallets.grants import GrantLedger
from apps.billing.wallets.models import (
    CreditGrant, GrantAllocation, Wallet, WalletTransaction,
)
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import UsageRecorded
from apps.platform.tenants.models import Tenant


def _committed_grant(wallet, tenant, *, kind="promo", amount=10_000_000,
                     expires_at=None):
    """Create a grant lot + GRANT txn + balance bump (committed)."""
    key = f"grant:{uuid.uuid4()}"
    with transaction.atomic():
        w, _c = lock_for_billing(wallet.customer_id)
        new_balance = w.balance_micros + amount
        txn = WalletTransaction.objects.create(
            wallet=w, transaction_type="GRANT", amount_micros=amount,
            balance_after_micros=new_balance, idempotency_key=key)
        grant = GrantLedger.create_grant(
            w, tenant.id, kind=kind, amount_micros=amount, expires_at=expires_at,
            source="api", source_reference=key, txn=txn)
        w.balance_micros = new_balance
        w.save(update_fields=["balance_micros", "updated_at"])
    return grant


class ConcurrentDrawdownWithGrants(TransactionTestCase):
    """Race (c): two threads, same usage event, wallet funded by a grant —
    one debit, lot remaining decremented once, allocations written once."""

    def test_same_event_one_debit_one_allocation(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="RACE_GRANT_DRAW", products=["metering", "billing"],
            billing_mode="prepaid")
        customer = Customer.objects.create(tenant=tenant, external_id="race_g1")
        wallet = Wallet.objects.create(customer=customer, balance_micros=0)
        grant = _committed_grant(
            wallet, tenant, kind="promo", amount=10_000_000,
            expires_at=timezone.now() + timedelta(days=5))

        ev_id = str(uuid.uuid4())
        payload = asdict(UsageRecorded(
            tenant_id=tenant.id,
            customer_id=customer.id,
            event_id=ev_id,
            billing_owner_id=customer.id,
            cost_micros=2_000_000,
        ))

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait()
                handle_usage_recorded_billing(str(uuid.uuid4()), payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"workers raised: {errors}")

        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=f"usage_deduction:{ev_id}",
            ).count(),
            1,
        )
        wallet.refresh_from_db()
        grant.refresh_from_db()
        self.assertEqual(wallet.balance_micros, 8_000_000)
        self.assertEqual(grant.remaining_micros, 8_000_000,
                         "lot remaining must be decremented exactly once")
        self.assertEqual(GrantAllocation.objects.filter(grant=grant).count(), 1,
                         "allocations must be written exactly once")
        # G1 after the race
        self.assertLessEqual(grant.remaining_micros,
                             max(wallet.balance_micros, 0))


class ConcurrentExpiryVsDrawdown(TransactionTestCase):
    """Race (d): expiry sweep vs drawdown exactly at the expiry boundary."""

    def _fixture(self):
        tenant = Tenant.objects.create(
            name="RACE_GRANT_EXP", products=["metering", "billing"],
            billing_mode="prepaid")
        customer = Customer.objects.create(tenant=tenant, external_id="race_g2")
        wallet = Wallet.objects.create(customer=customer, balance_micros=0)
        grant = _committed_grant(
            wallet, tenant, kind="promo", amount=10_000_000,
            expires_at=timezone.now() + timedelta(days=1))
        # Past the boundary, committed before the workers start.
        CreditGrant.objects.filter(pk=grant.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        return tenant, customer, wallet, grant

    def test_expiry_vs_drawdown_no_expired_lot_consumed(self):
        from apps.billing.handlers import handle_usage_recorded_billing
        from apps.billing.wallets.tasks import expire_credit_grants

        tenant, customer, wallet, grant = self._fixture()
        ev_id = str(uuid.uuid4())
        payload = asdict(UsageRecorded(
            tenant_id=tenant.id,
            customer_id=customer.id,
            event_id=ev_id,
            billing_owner_id=customer.id,
            cost_micros=2_000_000,
        ))

        barrier = threading.Barrier(2)
        errors = []

        def beat_worker():
            try:
                barrier.wait()
                expire_credit_grants()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        def drawdown_worker():
            try:
                barrier.wait()
                handle_usage_recorded_billing(str(uuid.uuid4()), payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=beat_worker),
                   threading.Thread(target=drawdown_worker)]
        # Events commit for real in TransactionTestCase; stub the outbox
        # dispatch task (no broker in tests — house pattern).
        with patch("apps.platform.events.tasks.process_single_event"):
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], f"workers raised: {errors}")

        wallet.refresh_from_db()
        grant.refresh_from_db()
        # Whichever side won the lock, the lot expired exactly once...
        self.assertEqual(grant.status, "expired")
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=f"expiry:{grant.pk}",
            ).count(),
            1,
        )
        # ...the debit landed exactly once...
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=f"usage_deduction:{ev_id}",
            ).count(),
            1,
        )
        # ...and the expired lot funded NOTHING.
        self.assertEqual(GrantAllocation.objects.filter(grant=grant).count(), 0)
        # 10 granted - 10 expired - 2 usage = -2 (base overdraft), G1 holds.
        self.assertEqual(wallet.balance_micros, -2_000_000)
        active_sum = sum(CreditGrant.objects.filter(
            wallet=wallet, status="active").values_list("remaining_micros", flat=True))
        self.assertLessEqual(active_sum, max(wallet.balance_micros, 0))

    def test_two_concurrent_beats_one_expiry_txn(self):
        from apps.billing.wallets.tasks import expire_credit_grants

        tenant, customer, wallet, grant = self._fixture()

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait()
                expire_credit_grants()
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        with patch("apps.platform.events.tasks.process_single_event"):
            for t in threads:
                t.start()
            for t in threads:
                t.join()

        self.assertEqual(errors, [], f"workers raised: {errors}")

        wallet.refresh_from_db()
        grant.refresh_from_db()
        self.assertEqual(grant.status, "expired")
        self.assertEqual(grant.remaining_micros, 0)
        self.assertEqual(grant.expired_micros, 10_000_000)
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet, idempotency_key=f"expiry:{grant.pk}",
            ).count(),
            1,
        )
        # Balance decremented exactly once: 10 - 10 = 0.
        self.assertEqual(wallet.balance_micros, 0)
