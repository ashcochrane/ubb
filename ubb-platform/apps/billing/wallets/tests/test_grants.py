"""F4.3 — expiring credit grants: GrantLedger + path wiring (single-threaded).

Concurrency proofs live in apps/billing/tests/test_concurrency_races_grants.py.
"""
import uuid
from datetime import timedelta
from unittest.mock import MagicMock

import pytest
from django.db import transaction
from django.utils import timezone

from apps.billing.handlers import handle_usage_recorded_billing
from apps.billing.locking import lock_for_billing
from apps.billing.topups.models import TopUpAttempt
from apps.billing.topups.services import AutoTopUpService
from apps.billing.wallets.grants import GrantLedger
from apps.billing.wallets.models import (
    CreditGrant, CustomerBillingProfile, GrantAllocation, Wallet, WalletTransaction,
)
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.tenants.models import Tenant


def _make_grant(wallet, tenant, *, kind, amount, expires_at=None, source="api",
                source_reference=""):
    """Create a grant lot the way the API does: GRANT txn + lot in one
    transaction under the wallet lock."""
    key = f"grant:{uuid.uuid4()}"
    with transaction.atomic():
        w, _c = lock_for_billing(wallet.customer_id)
        new_balance = w.balance_micros + amount
        txn = WalletTransaction.objects.create(
            wallet=w, transaction_type="GRANT", amount_micros=amount,
            balance_after_micros=new_balance, description="test grant",
            idempotency_key=key)
        grant = GrantLedger.create_grant(
            w, tenant.id, kind=kind, amount_micros=amount, expires_at=expires_at,
            source=source, source_reference=source_reference or key, txn=txn)
        w.balance_micros = new_balance
        w.save(update_fields=["balance_micros", "updated_at"])
    wallet.refresh_from_db()
    grant.refresh_from_db()
    return grant


def _drawdown(tenant, customer, cost, event_id=None):
    """Drive the real live drawdown handler once."""
    event_id = event_id or str(uuid.uuid4())
    payload = {
        "tenant_id": str(tenant.id), "customer_id": str(customer.id),
        "event_id": event_id, "billing_owner_id": str(customer.id),
        "cost_micros": cost,
    }
    handle_usage_recorded_billing(str(uuid.uuid4()), payload)
    return event_id


def _active_sum(wallet):
    from django.db.models import Sum
    return CreditGrant.objects.filter(wallet=wallet, status="active").aggregate(
        t=Sum("remaining_micros"))["t"] or 0


def _assert_g1(wallet):
    wallet.refresh_from_db()
    assert _active_sum(wallet) <= max(wallet.balance_micros, 0)


@pytest.mark.django_db
class TestAllocationOrder:
    def test_consumption_order_matrix(self):
        """promo+1d -> promo+2d -> paid+2d -> promo-never -> paid-never -> base."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=20_000_000)  # base 20
        now = timezone.now()
        # Scrambled creation order to prove ordering is not insertion order.
        paid_never = _make_grant(w, t, kind="paid", amount=10_000_000)
        promo_2d = _make_grant(w, t, kind="promo", amount=10_000_000,
                               expires_at=now + timedelta(days=2))
        paid_2d = _make_grant(w, t, kind="paid", amount=10_000_000,
                              expires_at=now + timedelta(days=2))
        promo_1d = _make_grant(w, t, kind="promo", amount=10_000_000,
                               expires_at=now + timedelta(days=1))
        promo_never = _make_grant(w, t, kind="promo", amount=10_000_000)
        w.refresh_from_db()
        assert w.balance_micros == 70_000_000

        def remaining():
            return {g.pk: CreditGrant.objects.get(pk=g.pk).remaining_micros
                    for g in (promo_1d, promo_2d, paid_2d, promo_never, paid_never)}

        def alloc_sum(event_id):
            from django.db.models import Sum
            txn = WalletTransaction.objects.get(
                wallet=w, idempotency_key=f"usage_deduction:{event_id}")
            return GrantAllocation.objects.filter(wallet_transaction=txn).aggregate(
                t=Sum("amount_micros"))["t"] or 0

        e1 = _drawdown(t, c, 15_000_000)  # promo_1d(10) + promo_2d(5)
        r = remaining()
        assert r[promo_1d.pk] == 0 and r[promo_2d.pk] == 5_000_000
        assert r[paid_2d.pk] == 10_000_000
        assert alloc_sum(e1) == 15_000_000

        e2 = _drawdown(t, c, 12_000_000)  # promo_2d(5) + paid_2d(7)
        r = remaining()
        assert r[promo_2d.pk] == 0 and r[paid_2d.pk] == 3_000_000
        assert alloc_sum(e2) == 12_000_000

        e3 = _drawdown(t, c, 14_000_000)  # paid_2d(3) + promo_never(10) + paid_never(1)
        r = remaining()
        assert r[paid_2d.pk] == 0 and r[promo_never.pk] == 0
        assert r[paid_never.pk] == 9_000_000
        assert alloc_sum(e3) == 14_000_000

        e4 = _drawdown(t, c, 14_000_000)  # paid_never(9) + base(5)
        r = remaining()
        assert r[paid_never.pk] == 0
        assert alloc_sum(e4) == 9_000_000  # the base remainder has no row

        w.refresh_from_db()
        assert w.balance_micros == 15_000_000  # 70 - 55, all of it base
        for g in (promo_1d, promo_2d, paid_2d, promo_never, paid_never):
            g.refresh_from_db()
            assert g.status == "depleted"
        _assert_g1(w)


@pytest.mark.django_db
class TestLazyExpiry:
    def test_drawdown_expires_due_lot_before_consuming(self):
        """Freeze past expires_at WITHOUT the beat: the drawdown expires the
        lot in-line first and never consumes it."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=5_000_000)  # base 5
        g = _make_grant(w, t, kind="promo", amount=10_000_000,
                        expires_at=timezone.now() + timedelta(days=1))
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))

        ev = _drawdown(t, c, 4_000_000)

        w.refresh_from_db()
        g.refresh_from_db()
        assert g.status == "expired"
        assert g.remaining_micros == 0 and g.expired_micros == 10_000_000
        expiry_txn = WalletTransaction.objects.get(
            wallet=w, idempotency_key=f"expiry:{g.pk}")
        assert expiry_txn.amount_micros == -10_000_000
        assert expiry_txn.balance_after_micros == 5_000_000  # 15 - 10
        # The usage debit came out of base — no allocation rows at all.
        usage_txn = WalletTransaction.objects.get(
            wallet=w, idempotency_key=f"usage_deduction:{ev}")
        assert not GrantAllocation.objects.filter(wallet_transaction=usage_txn).exists()
        assert w.balance_micros == 1_000_000  # 5 base + 10 grant - 10 expired - 4 usage
        _assert_g1(w)

    def test_replay_same_event_one_deduction_allocations_once(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        g = _make_grant(w, t, kind="paid", amount=10_000_000,
                        expires_at=timezone.now() + timedelta(days=5))
        ev = str(uuid.uuid4())
        _drawdown(t, c, 3_000_000, event_id=ev)
        _drawdown(t, c, 3_000_000, event_id=ev)  # replay
        w.refresh_from_db()
        g.refresh_from_db()
        assert w.balance_micros == 7_000_000
        assert g.remaining_micros == 7_000_000
        assert WalletTransaction.objects.filter(
            wallet=w, idempotency_key=f"usage_deduction:{ev}").count() == 1
        assert GrantAllocation.objects.filter(grant=g).count() == 1
        _assert_g1(w)


@pytest.mark.django_db
class TestOverageRecoup:
    def test_grant_into_negative_balance_self_allocates(self):
        """Balance -30, grant +100 -> remaining 70, one overage_recoup, balance 70."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        _drawdown(t, c, 30_000_000)  # overdraw to -30 through the real path
        w.refresh_from_db()
        assert w.balance_micros == -30_000_000

        g = _make_grant(w, t, kind="paid", amount=100_000_000)
        w.refresh_from_db()
        assert w.balance_micros == 70_000_000
        assert g.remaining_micros == 70_000_000
        recoups = GrantAllocation.objects.filter(grant=g, allocation_type="overage_recoup")
        assert recoups.count() == 1
        assert recoups.get().amount_micros == 30_000_000
        _assert_g1(w)


@pytest.mark.django_db
class TestG3ExpiryNeverNegative:
    def test_expiry_clamped_after_partial_spend(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        g = _make_grant(w, t, kind="promo", amount=10_000_000,
                        expires_at=timezone.now() + timedelta(days=1))
        _drawdown(t, c, 8_000_000)  # remaining 2, balance 2
        CreditGrant.objects.filter(pk=g.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        from apps.billing.wallets.tasks import expire_credit_grants
        expire_credit_grants()
        w.refresh_from_db()
        assert w.balance_micros == 0
        for txn in WalletTransaction.objects.filter(
                wallet=w, transaction_type="GRANT_EXPIRY"):
            assert txn.balance_after_micros >= 0
        assert not OutboxEvent.objects.filter(
            event_type__in=["billing.balance_overage",
                            "billing.customer_suspended"]).exists()

    def test_expiry_clamped_even_when_invariant_was_dented(self):
        """Defense-in-depth: remaining > balance (corrupted) still cannot
        drive the balance negative."""
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        g = _make_grant(w, t, kind="paid", amount=10_000_000,
                        expires_at=timezone.now() - timedelta(seconds=1))
        Wallet.objects.filter(pk=w.pk).update(balance_micros=4_000_000)  # dent
        from apps.billing.wallets.tasks import expire_credit_grants
        expire_credit_grants()
        w.refresh_from_db()
        g.refresh_from_db()
        assert w.balance_micros == 0  # clamped at zero, NOT -6
        assert g.status == "expired" and g.remaining_micros == 0
        txn = WalletTransaction.objects.get(wallet=w, idempotency_key=f"expiry:{g.pk}")
        assert txn.amount_micros == -4_000_000
        assert txn.balance_after_micros == 0
        assert not OutboxEvent.objects.filter(
            event_type__in=["billing.balance_overage",
                            "billing.customer_suspended"]).exists()


@pytest.mark.django_db
class TestTopUpGrants:
    def test_apply_topup_credit_twice_one_topup_one_grant(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                        trigger="auto_topup", status="pending")
        pi = MagicMock(id="pi_g1", latest_charge=MagicMock(id="ch_g1"))
        assert AutoTopUpService.apply_topup_credit(a, pi) is True
        assert AutoTopUpService.apply_topup_credit(a, pi) is False
        w.refresh_from_db()
        assert w.balance_micros == 20_000_000
        assert WalletTransaction.objects.filter(
            wallet=w, idempotency_key="auto_topup:pi_g1").count() == 1
        grants = CreditGrant.objects.filter(wallet=w)
        assert grants.count() == 1
        g = grants.get()
        assert g.kind == "paid" and g.source == "auto_topup"
        assert g.source_reference == str(a.id)
        assert g.granted_micros == 20_000_000 and g.remaining_micros == 20_000_000
        assert g.expires_at is None  # no profile -> never expires
        assert g.source_transaction.idempotency_key == "auto_topup:pi_g1"
        _assert_g1(w)

    def test_topup_grant_expiry_days_honored(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        CustomerBillingProfile.objects.create(customer=c, topup_grant_expiry_days=30)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=5_000_000,
                                        trigger="auto_topup", status="pending")
        pi = MagicMock(id="pi_g2", latest_charge=MagicMock(id="ch_g2"))
        before = timezone.now()
        assert AutoTopUpService.apply_topup_credit(a, pi) is True
        g = CreditGrant.objects.get(source_reference=str(a.id))
        assert g.expires_at is not None
        assert before + timedelta(days=29) < g.expires_at < before + timedelta(days=31)

    def test_checkout_completed_creates_grant_once(self):
        from apps.billing.connectors.stripe.webhooks import handle_checkout_completed
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid",
                                  stripe_connected_account_id="acct_g1")
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    stripe_customer_id="cus_g1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=1_000_000,
                                        trigger="manual", status="pending")
        event = MagicMock()
        event.account = "acct_g1"
        event.data.object.payment_status = "paid"
        event.data.object.customer = "cus_g1"
        event.data.object.client_reference_id = str(a.id)
        event.data.object.amount_total = 100  # cents -> 1_000_000 micros
        event.data.object.id = "cs_g1"
        event.data.object.payment_intent = None
        handle_checkout_completed(event)
        a.refresh_from_db()
        a.status = "pending"  # simulate redelivery racing the attempt stamp
        a.save(update_fields=["status"])
        handle_checkout_completed(event)  # duplicate webhook
        w.refresh_from_db()
        assert w.balance_micros == 1_000_000
        grants = CreditGrant.objects.filter(wallet=w)
        assert grants.count() == 1
        g = grants.get()
        assert g.kind == "paid" and g.source == "checkout"
        assert g.source_reference == str(a.id)
        assert g.source_transaction.idempotency_key == "topup:cs_g1"
        _assert_g1(w)


@pytest.mark.django_db
class TestClawbackCascade:
    def test_dispute_of_partially_consumed_lot_cascades(self):
        """Base 0; promo A=10 far; paid B=20 near; spend 15 (B first -> B=5);
        dispute the 20 top-up -> void B's 5, then consume 10 from A; G1 holds;
        A's later expiry debits 0."""
        from apps.billing.connectors.stripe.webhooks import handle_charge_dispute_closed
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid",
                                  stripe_connected_account_id="acct_d1")
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    stripe_customer_id="cus_d1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=c, amount_micros=20_000_000, trigger="manual",
            status="succeeded", stripe_charge_id="ch_d1")
        a_far = timezone.now() + timedelta(days=30)
        b_near = timezone.now() + timedelta(days=2)
        grant_a = _make_grant(w, t, kind="promo", amount=10_000_000, expires_at=a_far)
        grant_b = _make_grant(w, t, kind="paid", amount=20_000_000, expires_at=b_near,
                              source="checkout", source_reference=str(attempt.id))
        w.refresh_from_db()
        assert w.balance_micros == 30_000_000

        _drawdown(t, c, 15_000_000)  # B (near) consumed first
        grant_a.refresh_from_db(); grant_b.refresh_from_db()
        assert grant_b.remaining_micros == 5_000_000
        assert grant_a.remaining_micros == 10_000_000

        event = MagicMock()
        event.data.object.id = "dp_d1"
        event.data.object.charge = "ch_d1"
        event.data.object.status = "lost"
        event.data.object.amount = 2000  # cents -> 20_000_000 micros
        event.account = "acct_d1"
        handle_charge_dispute_closed(event)

        w.refresh_from_db()
        grant_a.refresh_from_db(); grant_b.refresh_from_db()
        assert w.balance_micros == -5_000_000
        assert grant_b.status == "voided" and grant_b.remaining_micros == 0
        # Fix 6: the source lot's clawed remaining is recorded in
        # voided_micros (same bucket as the void endpoint), NOT as a clawback
        # allocation — one representation per micro.
        assert grant_b.voided_micros == 5_000_000
        assert grant_a.remaining_micros == 0  # cascaded
        assert _active_sum(w) == 0  # G1 restored
        dispute_txn = WalletTransaction.objects.get(
            wallet=w, idempotency_key="dispute:dp_d1")
        clawbacks = GrantAllocation.objects.filter(
            wallet_transaction=dispute_txn, allocation_type="clawback")
        assert {(cb.grant_id, cb.amount_micros) for cb in clawbacks} == {
            (grant_a.id, 10_000_000)}
        # Conservation (G2) for both lots under the new representation.
        assert grant_b.granted_micros == 20_000_000 \
            == grant_b.remaining_micros + 15_000_000 + grant_b.expired_micros \
            + grant_b.voided_micros  # 0 + 15 usage alloc + 0 + 5 voided
        assert grant_a.granted_micros == 10_000_000 \
            == grant_a.remaining_micros + 10_000_000 + grant_a.expired_micros \
            + grant_a.voided_micros  # 0 + 10 clawback alloc + 0 + 0

        # A's later expiry debits 0 (it is no longer active).
        CreditGrant.objects.filter(pk=grant_a.pk).update(
            expires_at=timezone.now() - timedelta(seconds=1))
        from apps.billing.wallets.tasks import expire_credit_grants
        expire_credit_grants()
        assert not WalletTransaction.objects.filter(
            wallet=w, idempotency_key=f"expiry:{grant_a.pk}").exists()
        w.refresh_from_db()
        assert w.balance_micros == -5_000_000

    def test_refund_clawback_shrinks_source_lot(self):
        """Partial Stripe refund: only the refunded slice leaves the lot."""
        from apps.billing.connectors.stripe.webhooks import handle_charge_refunded
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid",
                                  stripe_connected_account_id="acct_r1")
        c = Customer.objects.create(tenant=t, external_id="c1",
                                    stripe_customer_id="cus_r1")
        w = Wallet.objects.create(customer=c, balance_micros=50_000_000)  # base 50
        attempt = TopUpAttempt.objects.create(
            customer=c, amount_micros=20_000_000, trigger="manual",
            status="succeeded", stripe_charge_id="ch_r1")
        g = _make_grant(w, t, kind="paid", amount=20_000_000,
                        source="checkout", source_reference=str(attempt.id))

        refund = MagicMock(id="re_r1", amount=1000)  # 10_000_000 micros
        charge = MagicMock(id="ch_r1", amount_refunded=1000)
        charge.refunds.data = [refund]
        event = MagicMock()
        event.data.object = charge
        event.account = "acct_r1"
        handle_charge_refunded(event)
        handle_charge_refunded(event)  # redelivery

        w.refresh_from_db(); g.refresh_from_db()
        assert w.balance_micros == 60_000_000  # 70 - 10
        assert g.remaining_micros == 10_000_000  # only the refunded slice
        assert g.status == "active"
        # Fix 6: the clawed slice lives in voided_micros, not an allocation.
        assert g.voided_micros == 10_000_000
        assert GrantAllocation.objects.filter(
            grant=g, allocation_type="clawback").count() == 0
        assert g.granted_micros == g.remaining_micros + g.voided_micros  # G2
        _assert_g1(w)


@pytest.mark.django_db
class TestReconcileGrants:
    def test_corrupted_grant_logs_loud(self):
        from apps.billing.wallets.tasks import reconcile_wallet_balances
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        g = _make_grant(w, t, kind="promo", amount=10_000_000)
        _drawdown(t, c, 4_000_000)  # remaining 6, one allocation of 4
        # Bump remaining raw: 10 != 8 + 4 breaks conservation (G2) and
        # 8 > balance 6 breaks G1 — both must log loud.
        CreditGrant.objects.filter(pk=g.pk).update(remaining_micros=8_000_000)
        import logging
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("apps.billing.wallets.tasks")
        handler = Capture()
        logger.addHandler(handler)
        try:
            reconcile_wallet_balances()
        finally:
            logger.removeHandler(handler)
        errors = [r.getMessage() for r in records if r.levelno >= logging.ERROR]
        assert any("drift" in m.lower() for m in errors)

    def test_healthy_grants_silent(self):
        """Healthy path stays silent INCLUDING after a lot-aware refund: the
        re-fund moves remaining += take while sum(alloc - refunded) -= take,
        so granted == remaining + sum(alloc - refunded) + expired + voided
        keeps holding."""
        from apps.billing.wallets.tasks import reconcile_wallet_balances
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        w = Wallet.objects.create(customer=c, balance_micros=0)
        g = _make_grant(w, t, kind="promo", amount=10_000_000,
                        expires_at=timezone.now() + timedelta(days=3))
        ev = _drawdown(t, c, 4_000_000)
        # Lot-aware refund of the drawdown (endpoint-equivalent inline).
        with transaction.atomic():
            wallet, _c = lock_for_billing(w.customer_id)
            GrantLedger.expire_due(wallet)
            original = WalletTransaction.objects.get(
                wallet=wallet, idempotency_key=f"usage_deduction:{ev}")
            wallet.balance_micros += 4_000_000
            wallet.save(update_fields=["balance_micros", "updated_at"])
            WalletTransaction.objects.create(
                wallet=wallet, transaction_type="REFUND",
                amount_micros=4_000_000,
                balance_after_micros=wallet.balance_micros,
                idempotency_key=f"refund:{ev}")
            assert GrantLedger.refund(wallet, original) == 4_000_000
        g.refresh_from_db()
        assert g.remaining_micros == 10_000_000  # lot fully restored
        alloc = GrantAllocation.objects.get(grant=g)
        assert alloc.refunded_micros == 4_000_000
        import logging
        records = []

        class Capture(logging.Handler):
            def emit(self, record):
                records.append(record)

        logger = logging.getLogger("apps.billing.wallets.tasks")
        handler = Capture()
        logger.addHandler(handler)
        try:
            reconcile_wallet_balances()
        finally:
            logger.removeHandler(handler)
        errors = [r.getMessage() for r in records if r.levelno >= logging.ERROR]
        assert errors == []
