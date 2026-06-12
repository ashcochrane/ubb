"""F4.3 — expire_credit_grants beat: exactly-once expiry + one-shot warnings."""
import uuid
from datetime import timedelta

import pytest
from django.db import transaction
from django.utils import timezone

from apps.billing.locking import lock_for_billing
from apps.billing.wallets.grants import GrantLedger
from apps.billing.wallets.models import CreditGrant, Wallet, WalletTransaction
from apps.billing.wallets.tasks import expire_credit_grants
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


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
