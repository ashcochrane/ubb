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
        return c, TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                              amount_micros=20_000_000,
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
        assert mw.called and type(mw.call_args.args[0]).__name__ == "AutoTopUpRequiresAction"


@pytest.mark.django_db
class TestChargeTaskBillingOwnerRouting:
    """Task 8b sweep finding: the pre-charge lock/supersede check must route
    through the PINNED `billing_owner_id`, never `attempt.customer_id` — even
    though every real auto-topup attempt has customer_id == billing_owner_id
    by construction today (see the code comment). These tests prove it by
    construction rather than by invariant: `attempt.customer` (the initiator)
    carries no wallet/config at all, while `billing_owner_id` points at the
    funded, configured owner."""

    def test_missing_billing_owner_id_refuses_loudly(self):
        """Same deliberate failure mode as every other credit/clawback call
        site pinned in this branch: raise rather than silently fall back to
        attempt.customer_id."""
        t = Tenant.objects.create(name="T_null_owner")
        c = Customer.objects.create(tenant=t, external_id="c_null_owner")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(
            customer=c, amount_micros=20_000_000,  # billing_owner_id left NULL
            trigger="auto_topup", status="pending")

        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            with pytest.raises(RuntimeError):
                charge_auto_topup_task(str(a.id))
            m.assert_not_called()
        a.refresh_from_db()
        assert a.status == "pending"  # the guard fires before any lock/charge

    def test_routes_through_pinned_owner_not_attempt_customer(self):
        """The load-bearing assertion: no wallet is ever created on the
        initiator, and the pre-charge threshold check (and the eventual
        credit) is decided by the OWNER's wallet/config — not a phantom
        wallet lazily minted on whoever `attempt.customer` happens to be.

        Pre-fix (attempt.customer_id): the initiator has no AutoTopUpConfig,
        so the threshold reads as 0; the initiator's lazily-created wallet
        (balance 0) reads as `>= 0` and the attempt is wrongly marked
        superseded — charge_saved_payment_method is never called, and a
        phantom wallet is silently created on the initiator. Post-fix: the
        owner's real config (threshold 10M) and real wallet (balance 0) say
        the attempt is NOT yet funded, so it charges through, and no wallet
        is ever created on the initiator."""
        t = Tenant.objects.create(name="T_route_owner")
        initiator = Customer.objects.create(tenant=t, external_id="initiator")
        owner = Customer.objects.create(tenant=t, external_id="owner")
        Wallet.objects.create(customer=owner, balance_micros=0)
        AutoTopUpConfig.objects.create(
            customer=owner, is_enabled=True,
            trigger_threshold_micros=10_000_000, top_up_amount_micros=20_000_000)
        a = TopUpAttempt.objects.create(
            customer=initiator, billing_owner_id=owner.id,
            amount_micros=20_000_000, trigger="auto_topup", status="pending")

        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            m.return_value = MagicMock(
                id="pi_route_1", status="succeeded", latest_charge=MagicMock(id="ch_route_1"))
            charge_auto_topup_task(str(a.id))
            m.assert_called_once()

        a.refresh_from_db()
        assert a.status == "succeeded"
        assert WalletTransaction.objects.filter(idempotency_key="auto_topup:pi_route_1").count() == 1
        assert Wallet.objects.get(customer=owner).balance_micros == 20_000_000
        assert not Wallet.objects.filter(customer=initiator).exists()
