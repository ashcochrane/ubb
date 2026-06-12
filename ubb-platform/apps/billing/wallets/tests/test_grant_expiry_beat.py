"""F4.3 — expire_credit_grants beat: exactly-once expiry + one-shot warnings,
sweep fault isolation + soft-delete liveness, BalanceLow on expiry."""
import logging
import uuid
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.db import transaction
from django.utils import timezone

from apps.billing.locking import lock_for_billing
from apps.billing.topups.models import AutoTopUpConfig
from apps.billing.wallets.grants import GrantLedger
from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
from apps.billing.wallets.tasks import expire_credit_grants
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


class _Capture(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def _setup(balance=0):
    t = Tenant.objects.create(name="T", products=["metering", "billing"],
                              billing_mode="prepaid")
    c = Customer.objects.create(tenant=t, external_id="c1")
    w = Wallet.objects.create(customer=c, balance_micros=balance)
    return t, c, w


def _grant(w, t, *, kind="promo", amount=10_000_000, expires_at=None):
    key = f"grant:{uuid.uuid4()}"
    with transaction.atomic():
        wallet, _c = lock_for_billing(w.customer_id)
        new_balance = wallet.balance_micros + amount
        txn = WalletTransaction.objects.create(
            wallet=wallet, transaction_type="GRANT", amount_micros=amount,
            balance_after_micros=new_balance, idempotency_key=key)
        g = GrantLedger.create_grant(
            wallet, t.id, kind=kind, amount_micros=amount, expires_at=expires_at,
            source="api", source_reference=key, txn=txn)
        wallet.balance_micros = new_balance
        wallet.save(update_fields=["balance_micros", "updated_at"])
    w.refresh_from_db()
    g.refresh_from_db()
    return g


@pytest.mark.django_db
class TestExpiryBeat:
    def test_beat_twice_expires_exactly_once(self):
        t, c, w = _setup()
        g = _grant(w, t, amount=10_000_000,
                   expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))

        expire_credit_grants()
        expire_credit_grants()  # second sweep must be a no-op

        w.refresh_from_db()
        g.refresh_from_db()
        assert w.balance_micros == 0  # 10 granted - 10 expired
        assert g.status == "expired"
        assert g.remaining_micros == 0 and g.expired_micros == 10_000_000
        assert WalletTransaction.objects.filter(
            wallet=w, idempotency_key=f"expiry:{g.pk}").count() == 1
        assert OutboxEvent.objects.filter(
            event_type="billing.credit_grant_expired").count() == 1
        payload = OutboxEvent.objects.get(
            event_type="billing.credit_grant_expired").payload
        assert payload["grant_id"] == str(g.pk)
        assert payload["expired_micros"] == 10_000_000
        assert payload["balance_micros"] == 0

    def test_zero_remaining_grant_expires_with_no_txn(self):
        t, c, w = _setup()
        g = _grant(w, t, amount=5_000_000,
                   expires_at=timezone.now() + timedelta(days=1))
        # Deplete it fully, then make it due.
        with transaction.atomic():
            wallet, _c = lock_for_billing(w.customer_id)
            txn = WalletTransaction.objects.create(
                wallet=wallet, transaction_type="DEBIT", amount_micros=-5_000_000,
                balance_after_micros=wallet.balance_micros - 5_000_000,
                idempotency_key="debit:beatzero")
            wallet.balance_micros -= 5_000_000
            wallet.save(update_fields=["balance_micros", "updated_at"])
            GrantLedger.allocate(wallet, txn, 5_000_000)
        g.refresh_from_db()
        assert g.status == "depleted"
        CreditGrant.objects.filter(pk=g.pk).update(
            status="active", expires_at=timezone.now() - timedelta(minutes=1))
        expire_credit_grants()
        g.refresh_from_db()
        assert g.status == "expired"
        assert not WalletTransaction.objects.filter(
            wallet=w, idempotency_key=f"expiry:{g.pk}").exists()
        assert not OutboxEvent.objects.filter(
            event_type="billing.credit_grant_expired").exists()

    def test_warning_winning_update_one_shot(self):
        t, c, w = _setup()
        g = _grant(w, t, amount=10_000_000,
                   expires_at=timezone.now() + timedelta(days=3))

        expire_credit_grants()
        expire_credit_grants()  # must not warn twice

        g.refresh_from_db()
        assert g.warning_sent_at is not None
        assert g.status == "active"  # warned, not expired
        events = OutboxEvent.objects.filter(
            event_type="billing.credit_grant_expiring")
        assert events.count() == 1
        payload = events.get().payload
        assert payload["grant_id"] == str(g.pk)
        assert payload["remaining_micros"] == 10_000_000

    def test_no_warning_for_far_expiry_or_non_expiring(self):
        t, c, w = _setup()
        _grant(w, t, amount=10_000_000,
               expires_at=timezone.now() + timedelta(days=30))
        _grant(w, t, amount=10_000_000, expires_at=None)
        expire_credit_grants()
        assert not OutboxEvent.objects.filter(
            event_type="billing.credit_grant_expiring").exists()


@pytest.mark.django_db
class TestSweepFaultIsolation:
    """Fix 1: one poisoned customer must never stall the whole hourly sweep."""

    def _two_wallets(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c1 = Customer.objects.create(tenant=t, external_id="dead")
        w1 = Wallet.objects.create(customer=c1, balance_micros=0)
        c2 = Customer.objects.create(tenant=t, external_id="live")
        w2 = Wallet.objects.create(customer=c2, balance_micros=0)
        g1 = _grant(w1, t, amount=10_000_000,
                    expires_at=timezone.now() + timedelta(days=1))
        g2 = _grant(w2, t, amount=10_000_000,
                    expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk__in=[g1.pk, g2.pk]).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        return t, c1, w1, g1, c2, w2, g2

    def test_soft_deleted_customer_grant_untouched_others_swept(self):
        """A soft-deleted customer's due grant used to raise
        Customer.DoesNotExist inside lock_for_billing and kill the WHOLE task
        (forever — the grant stays due). Policy: the sweeper leaves those
        grants alone entirely (handled if the customer is restored)."""
        t, c1, w1, g1, c2, w2, g2 = self._two_wallets()
        c1.soft_delete()

        expire_credit_grants()  # must not raise

        g1.refresh_from_db()
        g2.refresh_from_db()
        w1.refresh_from_db()
        # Live wallet swept...
        assert g2.status == "expired" and g2.remaining_micros == 0
        # ...soft-deleted customer's grant completely untouched.
        assert g1.status == "active" and g1.remaining_micros == 10_000_000
        assert not WalletTransaction.objects.filter(
            wallet=w1, idempotency_key=f"expiry:{g1.pk}").exists()
        assert w1.balance_micros == 10_000_000
        # No expiring-soon warning for the dead customer either (pass 2
        # shares the liveness policy).
        assert not OutboxEvent.objects.filter(
            event_type="billing.credit_grant_expiring",
            payload__customer_id=str(c1.id)).exists()

    def test_unexpected_failure_logged_and_sweep_continues(self):
        """Even a failure the liveness filter can't predict (DB hiccup, data
        corruption) must be isolated per customer, logged, and not block the
        remaining wallets."""
        from apps.billing import locking
        t, c1, w1, g1, c2, w2, g2 = self._two_wallets()
        real = locking.lock_for_billing

        def boom(customer_id):
            if str(customer_id) == str(c1.id):
                raise RuntimeError("poisoned wallet")
            return real(customer_id)

        capture = _Capture()
        task_logger = logging.getLogger("apps.billing.wallets.tasks")
        task_logger.addHandler(capture)
        try:
            with patch("apps.billing.locking.lock_for_billing",
                       side_effect=boom):
                expire_credit_grants()  # must not raise
        finally:
            task_logger.removeHandler(capture)

        g1.refresh_from_db()
        g2.refresh_from_db()
        assert g1.status == "active"  # rolled back, untouched
        assert g2.status == "expired"  # the healthy wallet was still swept
        failures = [r for r in capture.records
                    if r.getMessage() == "grants.expiry_sweep_failed"]
        assert len(failures) == 1


@pytest.mark.django_db
class TestBalanceLowOnExpiry:
    """Fix 3: an expiry debit that leaves the balance below the auto-top-up
    trigger emits BalanceLow with the drawdown winning-branch semantics."""

    def test_expiry_below_trigger_emits_one_balance_low(self):
        t, c, w = _setup()
        AutoTopUpConfig.objects.create(
            customer=c, is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000)
        g = _grant(w, t, amount=10_000_000,
                   expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))

        expire_credit_grants()
        expire_credit_grants()  # replay: grant already expired -> no re-emit

        events = OutboxEvent.objects.filter(event_type="billing.balance_low")
        assert events.count() == 1
        payload = events.get().payload
        assert payload["customer_id"] == str(c.id)
        assert payload["balance_micros"] == 0  # 10 granted - 10 expired
        assert payload["threshold_micros"] == 5_000_000
        assert payload["suggested_topup_micros"] == 20_000_000

    def test_no_balance_low_when_above_trigger_or_disabled(self):
        t, c, w = _setup(balance=50_000_000)
        AutoTopUpConfig.objects.create(
            customer=c, is_enabled=True,
            trigger_threshold_micros=5_000_000,
            top_up_amount_micros=20_000_000)
        g = _grant(w, t, amount=10_000_000,
                   expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        expire_credit_grants()  # post-expiry balance 50 >= trigger 5
        assert not OutboxEvent.objects.filter(
            event_type="billing.balance_low").exists()


@pytest.mark.django_db
class TestExpirySkipDupObservability:
    """Fix 7: the raced-expiry IntegrityError skip is no longer silent."""

    def test_dup_expiry_skip_logs_warning(self):
        t, c, w = _setup()
        g = _grant(w, t, amount=10_000_000,
                   expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        # Simulate a raced sibling: the expiry txn already exists but the
        # grant row was not yet flipped.
        WalletTransaction.objects.create(
            wallet=w, transaction_type="GRANT_EXPIRY", amount_micros=0,
            balance_after_micros=w.balance_micros,
            idempotency_key=f"expiry:{g.pk}")

        capture = _Capture()
        grants_logger = logging.getLogger("apps.billing.wallets.grants")
        grants_logger.addHandler(capture)
        try:
            expire_credit_grants()
        finally:
            grants_logger.removeHandler(capture)

        dups = [r for r in capture.records
                if r.getMessage() == "grants.expiry_skip_dup"]
        assert len(dups) == 1
        assert dups[0].levelno == logging.WARNING
