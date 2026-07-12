import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt, AutoTopUpConfig
from apps.billing.connectors.stripe.tasks import charge_auto_topup_task
from core.exceptions import StripePaymentError


@pytest.mark.django_db
class TestChargeTask:
    def _attempt(self, balance=0):
        t = Tenant.objects.create(name="T")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=balance)
        AutoTopUpConfig.objects.create(customer=c, is_enabled=True,
                                       trigger_threshold_micros=10_000_000, top_up_amount_micros=20_000_000)
        return c, TopUpAttempt.objects.create(customer=c, amount_micros=20_000_000,
                                              trigger="auto_topup", status="pending")

    def test_success_credits_via_service(self):
        c, a = self._attempt(balance=0)
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            m.return_value = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"))
            charge_auto_topup_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_1").count() == 1
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000

    def test_skip_if_already_funded(self):
        c, a = self._attempt(balance=15_000_000)  # already above the 10M trigger
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            charge_auto_topup_task(str(a.id))
            m.assert_not_called()
        a.refresh_from_db()
        assert a.status == "superseded"

    def test_sca_sets_requires_action_and_emits_event(self):
        c, a = self._attempt(balance=0)
        err = StripePaymentError("auth required"); err.code = "authentication_required"
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method", side_effect=err), \
             patch("apps.platform.events.tasks.process_single_event"), \
             patch("apps.billing.connectors.stripe.tasks.write_event") as mw:
            charge_auto_topup_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "requires_action"
        assert mw.called and type(mw.call_args.args[0]).__name__ == "AutoTopupRequiresAction"
