import pytest
from unittest.mock import MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.webhooks import handle_payment_intent_succeeded


def _event(pi):
    return MagicMock(data=MagicMock(object=pi))


@pytest.mark.django_db
class TestPIWebhook:
    def _setup(self):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                        trigger="auto_topup", status="pending")
        return c, a

    def test_webhook_credits_once_idempotent(self):
        c, a = self._setup()
        pi = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"),
                       metadata={"topup_attempt_id": str(a.id)})
        handle_payment_intent_succeeded(_event(pi))
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000
        handle_payment_intent_succeeded(_event(pi))  # again — idempotent
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1

    def test_webhook_ignores_non_topup_pi(self):
        pi = MagicMock(id="pi_x", status="succeeded", metadata={})
        handle_payment_intent_succeeded(_event(pi))  # no metadata → no-op, no error
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_x").count() == 0
