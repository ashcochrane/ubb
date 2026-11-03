import pytest
from unittest.mock import patch, MagicMock
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.wallets.models import Wallet, WalletTransaction
from apps.billing.topups.models import TopUpAttempt, AutoTopUpConfig
from apps.billing.connectors.stripe.tasks import charge_auto_top_up_task
from core.exceptions import NoWalletSubjectError, StripePaymentError


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestChargeTask:
    def _attempt(self, balance=0):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=balance)
        AutoTopUpConfig.objects.create(customer=c, is_enabled=True,
                                       trigger_threshold_micros=10_000_000, top_up_amount_micros=20_000_000)
        return c, TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                              amount_micros=20_000_000,
                                              trigger="auto_top_up", status="pending")

    def test_success_credits_via_service(self):
        c, a = self._attempt(balance=0)
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            m.return_value = MagicMock(id="pi_1", status="succeeded", latest_charge=MagicMock(id="ch_1"))
            charge_auto_top_up_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "succeeded"
        assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_1").count() == 1
        assert Wallet.objects.get(customer=c).balance_micros == 20_000_000

    def test_skip_if_already_funded(self):
        c, a = self._attempt(balance=15_000_000)  # already above the 10M trigger
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            charge_auto_top_up_task(str(a.id))
            m.assert_not_called()
        a.refresh_from_db()
        assert a.status == "superseded"

    def test_an_attempt_whose_tenant_left_prepaid_fails_by_name_and_charges_nothing(self):
        """Stage A (2026-11-02): the wallet boundary refuses before the charge
        when the attempt's tenant no longer holds a wallet (it left `prepaid`
        after the attempt was minted). Stripe is never asked, the refusal is
        recorded on the attempt as its terminal failure — by name, the way
        every non-retryable outcome of this task is — and the task raises
        nothing, so nothing is retried."""
        c, a = self._attempt(balance=0)
        tenant = c.tenant
        tenant.billing_mode = "external"
        tenant.save()
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            charge_auto_top_up_task(str(a.id))  # no raise
            m.assert_not_called()
        a.refresh_from_db()
        assert a.status == "failed"
        assert a.failure_reason["error_type"] == "NoWalletSubjectError"
        assert "billing mode (external)" in a.failure_reason["message"]
        assert Wallet.objects.get(customer=c).balance_micros == 0
        assert not WalletTransaction.objects.filter(wallet__customer=c).exists()

    def test_a_refusal_after_a_successful_charge_fails_the_task_once_and_credits_nothing(self):
        """The one window the pre-charge guard cannot close: the tenant leaves
        `prepaid` between the guard and the credit, after Stripe has taken
        the money. That refusal is deliberately NOT caught — marking the
        attempt failed would be a lie about a charge that succeeded — so the
        task fails loudly, exactly once (its autoretry is for Stripe's
        transient errors only), the attempt stays `pending` with no credit
        recorded, and the hourly Stripe reconcile reports it by name until
        it is dealt with (`test_reconcile_repair.py`)."""
        c, a = self._attempt(balance=0)

        def charged_then_the_tenant_left(customer, amount_micros, attempt):
            tenant = customer.tenant
            tenant.billing_mode = "external"
            tenant.save()
            return MagicMock(id="pi_late", status="succeeded",
                             latest_charge=MagicMock(id="ch_late"))

        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method",
                   side_effect=charged_then_the_tenant_left):
            with pytest.raises(NoWalletSubjectError):
                charge_auto_top_up_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "pending"
        assert a.stripe_payment_intent_id in (None, "")
        assert not WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_late").exists()
        assert Wallet.objects.get(customer=c).balance_micros == 0

    def test_sca_sets_requires_action_and_emits_event(self):
        c, a = self._attempt(balance=0)
        err = StripePaymentError("auth required"); err.code = "authentication_required"
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method", side_effect=err), \
             patch("apps.platform.events.tasks.process_single_event"), \
             patch("apps.billing.connectors.stripe.tasks.write_event") as mw:
            charge_auto_top_up_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "requires_action"
        assert mw.called and type(mw.call_args.args[0]).__name__ == "AutoTopUpRequiresAction"


def _real_card_error(code, decline_code, payment_intent_id):
    """A CardError as stripe-python 15.2.0 builds it from Stripe's response:
    decline_code and the PaymentIntent live on ``e.error``, not top-level."""
    import stripe
    body = {"error": {"type": "card_error", "code": code, "message": "declined"}}
    if decline_code is not None:
        body["error"]["decline_code"] = decline_code
    body["error"]["payment_intent"] = {"id": payment_intent_id, "object": "payment_intent"}
    return stripe.error.CardError("declined", "payment_method", code, json_body=body)


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestTheAttemptRecordsThePaymentIntentStripeNamed:
    """O-1 (Stage C1a): a declined or SCA-blocked auto top-up records the
    PaymentIntent id and decline code Stripe attached to the real CardError —
    driven through the real wrapper (``stripe_call`` mapping a genuine
    ``CardError``), not a hand-built StripePaymentError. Before C1a
    ``stripe_payment_intent_id`` stayed null on every decline and SCA."""

    def _attempt(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c1")
        Wallet.objects.create(customer=c, balance_micros=0)
        AutoTopUpConfig.objects.create(customer=c, is_enabled=True,
                                       trigger_threshold_micros=10_000_000,
                                       top_up_amount_micros=20_000_000)
        return c, TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                              amount_micros=20_000_000,
                                              trigger="auto_top_up", status="pending")

    def _charge_raising(self, card_error):
        from apps.billing.stripe.services.stripe_service import stripe_call

        def charge(customer, amount_micros, attempt):
            # The real path: the SDK raises CardError inside the wrapper, which
            # maps it to StripePaymentError off the real error shape.
            return stripe_call(MagicMock(side_effect=card_error), api_key="sk_test_sentinel")
        return charge

    def test_an_sca_challenge_records_the_payment_intent_id(self):
        _, a = self._attempt()
        err = _real_card_error("authentication_required", None, "pi_sca_1")
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method",
                   side_effect=self._charge_raising(err)), \
             patch("apps.platform.events.tasks.process_single_event"):
            charge_auto_top_up_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "requires_action"
        assert a.stripe_payment_intent_id == "pi_sca_1"
        assert a.failure_reason["payment_intent_id"] == "pi_sca_1"
        assert a.failure_reason["code"] == "authentication_required"

    def test_a_decline_records_the_payment_intent_id_and_the_decline_code(self):
        c, a = self._attempt()
        err = _real_card_error("card_declined", "insufficient_funds", "pi_declined_1")
        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method",
                   side_effect=self._charge_raising(err)):
            charge_auto_top_up_task(str(a.id))
        a.refresh_from_db()
        assert a.status == "failed"
        assert a.stripe_payment_intent_id == "pi_declined_1"
        assert a.failure_reason["error_type"] == "StripePaymentError"
        assert a.failure_reason["code"] == "card_declined"
        assert a.failure_reason["decline_code"] == "insufficient_funds"
        assert a.failure_reason["payment_intent_id"] == "pi_declined_1"
        assert Wallet.objects.get(customer=c).balance_micros == 0


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestTheDefaultPaymentMethodOnARealCustomer:
    """Stage C1a (F-3a, ``stripe_api.py``): the off-session charge uses the
    customer's DEFAULT payment method, read off a genuine ``stripe.Customer``
    (``invoice_settings`` is a StripeObject: no ``.get``). Before C1a the
    dict-style read raised, was swallowed, and the FIRST listed card was
    charged instead of the default — silently."""

    def _customer(self):
        t = Tenant.objects.create(name="T", products=["metering", "billing"],
                                  billing_mode="prepaid",
                                  stripe_connected_account_id="acct_x", charges_enabled=True)
        c = Customer.objects.create(tenant=t, external_id="c1", stripe_customer_id="cus_1")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(customer=c, billing_owner_id=c.id,
                                        amount_micros=20_000_000,
                                        trigger="auto_top_up", status="pending")
        return c, a

    def _stripe(self, default_payment_method):
        """Real SDK objects for every read the charge makes; the PaymentIntent
        create is captured so the chosen payment method can be asserted."""
        import stripe
        sk = "sk_test_sentinel"
        pms = stripe.ListObject.construct_from(
            {"object": "list", "has_more": False, "url": "/v1/payment_methods",
             "data": [{"id": "pm_first_listed", "object": "payment_method", "type": "card"},
                      {"id": "pm_default", "object": "payment_method", "type": "card"}]}, sk)
        cust = stripe.Customer.construct_from(
            {"id": "cus_1", "object": "customer",
             "invoice_settings": {"default_payment_method": default_payment_method,
                                  "custom_fields": None, "footer": None}}, sk)
        created = {}

        def fake(fn, **kw):
            name = getattr(fn, "__qualname__", "")
            if name == "PaymentMethod.list":
                return pms
            if name == "Customer.retrieve":
                return cust
            assert name == "PaymentIntent.create", name
            created.update(kw)
            return stripe.PaymentIntent.construct_from(
                {"id": "pi_1", "object": "payment_intent", "status": "succeeded"}, sk)
        return fake, created

    def test_the_customers_default_card_is_charged_not_the_first_listed(self):
        from apps.billing.connectors.stripe.stripe_api import charge_saved_payment_method
        c, a = self._customer()
        fake, created = self._stripe("pm_default")
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call", side_effect=fake):
            intent = charge_saved_payment_method(c, 20_000_000, a)
        assert intent.id == "pi_1"
        assert created["payment_method"] == "pm_default"

    def test_with_no_default_the_first_listed_card_is_charged(self):
        from apps.billing.connectors.stripe.stripe_api import charge_saved_payment_method
        c, a = self._customer()
        fake, created = self._stripe(None)
        with patch("apps.billing.connectors.stripe.stripe_api.stripe_call", side_effect=fake):
            charge_saved_payment_method(c, 20_000_000, a)
        assert created["payment_method"] == "pm_first_listed"


@pytest.mark.usefixtures("rail_activated")
@pytest.mark.django_db
class TestChargeTaskBillingOwnerRouting:
    """Task 8b sweep finding: the pre-charge lock/supersede check must route
    through the PINNED `billing_owner_id`, never `attempt.customer_id` — even
    though every real auto top-up attempt has customer_id == billing_owner_id
    by construction today (see the code comment). These tests prove it by
    construction rather than by invariant: `attempt.customer` (the initiator)
    carries no wallet/config at all, while `billing_owner_id` points at the
    funded, configured owner."""

    def test_missing_billing_owner_id_refuses_loudly(self):
        """Same deliberate failure mode as every other credit/clawback call
        site pinned in this branch: raise rather than silently fall back to
        attempt.customer_id."""
        t = Tenant.objects.create(name="T_null_owner", products=["metering", "billing"],
                                  billing_mode="prepaid")
        c = Customer.objects.create(tenant=t, external_id="c_null_owner")
        Wallet.objects.create(customer=c, balance_micros=0)
        a = TopUpAttempt.objects.create(
            customer=c, amount_micros=20_000_000,  # billing_owner_id left NULL
            trigger="auto_top_up", status="pending")

        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            with pytest.raises(RuntimeError):
                charge_auto_top_up_task(str(a.id))
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
        t = Tenant.objects.create(name="T_route_owner", products=["metering", "billing"],
                                  billing_mode="prepaid")
        initiator = Customer.objects.create(tenant=t, external_id="initiator")
        owner = Customer.objects.create(tenant=t, external_id="owner")
        Wallet.objects.create(customer=owner, balance_micros=0)
        AutoTopUpConfig.objects.create(
            customer=owner, is_enabled=True,
            trigger_threshold_micros=10_000_000, top_up_amount_micros=20_000_000)
        a = TopUpAttempt.objects.create(
            customer=initiator, billing_owner_id=owner.id,
            amount_micros=20_000_000, trigger="auto_top_up", status="pending")

        with patch("apps.billing.connectors.stripe.tasks.charge_saved_payment_method") as m:
            m.return_value = MagicMock(
                id="pi_route_1", status="succeeded", latest_charge=MagicMock(id="ch_route_1"))
            charge_auto_top_up_task(str(a.id))
            m.assert_called_once()

        a.refresh_from_db()
        assert a.status == "succeeded"
        assert WalletTransaction.objects.filter(idempotency_key="auto_top_up:pi_route_1").count() == 1
        assert Wallet.objects.get(customer=owner).balance_micros == 20_000_000
        assert not Wallet.objects.filter(customer=initiator).exists()
