import pytest
from unittest.mock import MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.topups.services import AutoTopUpService


@pytest.mark.django_db
class TestApplyTopupCredit:
    def _setup(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_topup", status="pending")
        pi = MagicMock(id="pi_1", latest_charge=MagicMock(id="ch_1"))
        return c, a, pi

    def test_credits_once_and_is_idempotent(self):
        c, a, pi = self._setup()
        assert AutoTopUpService.apply_topup_credit(a, pi) is True
        w = Wallet.objects.get(customer=c)
        assert w.balance_micros == 20_000_000
        txn = WalletTransaction.objects.get(idempotency_key="auto_topup:pi_1")
        assert txn.amount_micros == 20_000_000
        a.refresh_from_db()
        assert a.status == "succeeded" and a.stripe_payment_intent_id == "pi_1" and a.stripe_charge_id == "ch_1"
        assert AutoTopUpService.apply_topup_credit(a, pi) is False  # second call no-ops
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1
        w.refresh_from_db()
        assert w.balance_micros == 20_000_000


@pytest.mark.django_db
class TestApplyTopupCreditBillingOwnerRouting:
    """Task 7 — apply_topup_credit must credit the PINNED billing_owner_id,
    never attempt.customer_id. Covers all three topologies; the manual/
    widget-triggered attempt shape (customer=seat, billing_owner_id=owner)
    is realistic here too since handle_payment_intent_succeeded routes ANY
    trigger through this same method, not just auto_topup."""

    def _seat_and_owner(self, topology, external_prefix):
        t = Tenant.objects.create(name=f"T_{external_prefix}")
        if topology is None:
            customer = Customer.objects.create(tenant=t, external_id=f"{external_prefix}_ind")
            return customer, customer
        biz = Customer.objects.create(
            tenant=t, external_id=f"{external_prefix}_biz",
            account_type="business", billing_topology=topology)
        seat = Customer.objects.create(
            tenant=t, external_id=f"{external_prefix}_seat",
            account_type="seat", parent=biz)
        owner = biz if topology == "pooled" else seat
        return seat, owner

    def _run(self, topology, prefix, pi_id):
        customer, owner = self._seat_and_owner(topology, prefix)
        Wallet.objects.create(customer=owner, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=customer, billing_owner_id=owner.id,
            amount_micros=5_000_000, trigger="manual", status="pending")
        pi = MagicMock(id=pi_id, latest_charge=MagicMock(id=f"ch_{pi_id}"))
        assert AutoTopUpService.apply_topup_credit(attempt, pi) is True
        return customer, owner

    def test_individual_credits_self(self):
        customer, owner = self._run(None, "ind", "pi_ind")
        assert Wallet.objects.get(customer=owner).balance_micros == 5_000_000

    def test_pooled_seat_credits_business_no_wallet_on_seat(self):
        seat, biz = self._run("pooled", "pooled", "pi_pooled")
        assert Wallet.objects.get(customer=biz).balance_micros == 5_000_000
        assert not Wallet.objects.filter(customer=seat).exists()

    def test_allocated_seat_credits_self(self):
        seat, owner = self._run("allocated", "alloc", "pi_alloc")
        assert seat.id == owner.id
        assert Wallet.objects.get(customer=seat).balance_micros == 5_000_000

    def test_missing_billing_owner_id_refuses_loudly(self):
        t = Tenant.objects.create(name="T_null")
        c = Customer.objects.create(tenant=t, external_id="null_owner")
        Wallet.objects.create(customer=c, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=c, amount_micros=1_000_000,  # billing_owner_id left NULL
            trigger="manual", status="pending")
        pi = MagicMock(id="pi_null", latest_charge=MagicMock(id="ch_null"))
        with pytest.raises(RuntimeError):
            AutoTopUpService.apply_topup_credit(attempt, pi)
