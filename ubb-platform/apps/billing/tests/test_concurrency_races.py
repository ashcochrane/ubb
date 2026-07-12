"""
True multi-thread concurrency tests for exactly-once money invariants.

Uses TransactionTestCase (NOT @pytest.mark.django_db) so that setup data is
committed before worker threads start, and workers can see each other's
transactions through real Postgres row locking.

Each worker closes its thread-local DB connection in a finally: block to avoid
connection leaks.  A threading.Barrier(N) forces all workers into the critical
section simultaneously, maximising the real race window.

Invariants asserted:
    (a) Concurrent drawdown  — exactly ONE WalletTransaction debit for the same
        usage event_id, wallet balance decremented exactly once.
    (b) Concurrent auto top-up credit — exactly ONE WalletTransaction credit for
        the same payment_intent.id, wallet balance incremented exactly once.
"""

import threading
import uuid
from unittest.mock import MagicMock

from django.db import connection
from django.test import TransactionTestCase

from apps.billing.topups.models import TopUpAttempt
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant


class ConcurrentDrawdownRace(TransactionTestCase):
    """Race (a): two threads call handle_usage_recorded_billing with the same
    usage event_id — only one debit must land."""

    def test_two_concurrent_drawdowns_same_event_one_debit(self):
        from apps.billing.handlers import handle_usage_recorded_billing

        tenant = Tenant.objects.create(
            name="RACE_DRAW",
            products=["metering", "billing"],
            billing_mode="prepaid",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="race_c1")
        wallet = Wallet.objects.create(customer=customer, balance_micros=10_000_000)

        ev_id = str(uuid.uuid4())
        outbox_id = str(uuid.uuid4())
        payload = {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "event_id": ev_id,
            "billing_owner_id": str(customer.id),
            "cost_micros": 2_000_000,
        }

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait()
                handle_usage_recorded_billing(outbox_id, payload)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")

        # Exactly one debit record.
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet,
                idempotency_key=f"usage_deduction:{ev_id}",
            ).count(),
            1,
            "expected exactly one WalletTransaction for the usage event",
        )

        # Balance decremented once (10_000_000 - 2_000_000 = 8_000_000).
        wallet.refresh_from_db()
        self.assertEqual(
            wallet.balance_micros,
            8_000_000,
            f"expected balance 8_000_000 (debited once) but got {wallet.balance_micros}",
        )


class ConcurrentTopUpCreditRace(TransactionTestCase):
    """Race (b): two threads call AutoTopUpService.apply_topup_credit with the
    same payment_intent.id — only one credit must land."""

    def test_two_concurrent_topup_credits_same_pi_one_credit(self):
        from apps.billing.topups.services import AutoTopUpService

        tenant = Tenant.objects.create(
            name="RACE_TOPUP",
            products=["metering", "billing"],
            billing_mode="prepaid",
        )
        customer = Customer.objects.create(tenant=tenant, external_id="race_c2")
        wallet = Wallet.objects.create(customer=customer, balance_micros=0)

        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=20_000_000,
            trigger="auto_topup",
            status="pending",
        )

        # Fake PaymentIntent — apply_topup_credit reads `.id` via hasattr check.
        pi_id = f"pi_{uuid.uuid4().hex[:12]}"
        payment_intent = MagicMock(
            id=pi_id,
            status="succeeded",
            latest_charge=MagicMock(id=f"ch_{uuid.uuid4().hex[:12]}"),
        )

        barrier = threading.Barrier(2)
        errors = []

        def worker():
            try:
                barrier.wait()
                AutoTopUpService.apply_topup_credit(attempt, payment_intent)
            except Exception as exc:  # noqa: BLE001
                errors.append(repr(exc))
            finally:
                connection.close()

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        self.assertEqual(errors, [], f"workers raised unexpected exceptions: {errors}")

        # Exactly one credit record.
        self.assertEqual(
            WalletTransaction.objects.filter(
                wallet=wallet,
                idempotency_key=f"auto_topup:{pi_id}",
            ).count(),
            1,
            "expected exactly one WalletTransaction for the top-up credit",
        )

        # Balance incremented once (0 + 20_000_000 = 20_000_000).
        wallet.refresh_from_db()
        self.assertEqual(
            wallet.balance_micros,
            20_000_000,
            f"expected balance 20_000_000 (credited once) but got {wallet.balance_micros}",
        )
