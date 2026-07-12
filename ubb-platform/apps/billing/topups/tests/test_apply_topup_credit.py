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
        a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
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
