import pytest
from unittest.mock import MagicMock, patch
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt
from apps.billing.connectors.stripe.webhooks import (
    handle_payment_intent_succeeded,
    handle_payment_intent_payment_failed,
)


def _event(pi, account=None):
    # account defaults to None (no event.account) — the cross-account guard only
    # fires when event.account is present AND differs from the attempt's tenant.
    return MagicMock(data=MagicMock(object=pi), account=account)


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


@pytest.mark.django_db
class TestPIWebhookCrossAccountGuard:
    """B4: the payment_intent handlers must verify event.account against the
    attempt's tenant.stripe_connected_account_id before acting on the credit."""

    def _setup(self, acct="acct_tenant_1"):
        t = Tenant.objects.create(name="T", stripe_connected_account_id=acct)
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                        trigger="auto_topup", status="pending")
        return t, c, a

    def test_succeeded_mismatched_account_is_skipped(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = MagicMock(id="pi_cross", status="succeeded",
                       latest_charge=MagicMock(id="ch_1"),
                       metadata={"topup_attempt_id": str(a.id)})
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(pi, account="acct_DIFFERENT"))
        m.assert_not_called()

    def test_succeeded_matching_account_applies_credit(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = MagicMock(id="pi_match", status="succeeded",
                       latest_charge=MagicMock(id="ch_1"),
                       metadata={"topup_attempt_id": str(a.id)})
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(pi, account="acct_tenant_1"))
        m.assert_called_once()

    def test_succeeded_no_account_applies_credit(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = MagicMock(id="pi_noacct", status="succeeded",
                       latest_charge=MagicMock(id="ch_1"),
                       metadata={"topup_attempt_id": str(a.id)})
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as m:
            handle_payment_intent_succeeded(_event(pi, account=None))  # falsy → no guard
        m.assert_called_once()

    def test_failed_mismatched_account_is_skipped(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = MagicMock(id="pi_cross_f", metadata={"topup_attempt_id": str(a.id)},
                       last_payment_error=MagicMock(message="card declined"))
        handle_payment_intent_payment_failed(_event(pi, account="acct_DIFFERENT"))
        a.refresh_from_db()
        assert a.status == "pending"  # untouched — cross-account guard fired

    def test_failed_matching_account_marks_failed(self):
        t, c, a = self._setup(acct="acct_tenant_1")
        pi = MagicMock(id="pi_match_f", metadata={"topup_attempt_id": str(a.id)},
                       last_payment_error=MagicMock(message="card declined"))
        handle_payment_intent_payment_failed(_event(pi, account="acct_tenant_1"))
        a.refresh_from_db()
        assert a.status == "failed"
