"""F4.4 inbound-webhook livemode anti-collision.

A Stripe Connect acct_ id is IDENTICAL in test and live mode, so once a live
tenant and its sandbox sibling have both connected the same account, the
event.account match alone cannot tell them apart. Every account-based lookup
must bind event.livemode to the tenant mode; the dedicated /test endpoints
verify with STRIPE_TEST_WEBHOOK_SECRET and accept only livemode=False.
"""
import json
from unittest.mock import MagicMock, patch

from django.test import Client, TestCase, override_settings

from api.v1.webhooks import (
    handle_account_deauthorized,
    handle_account_updated,
    stripe_webhook,
    stripe_webhook_test,
)
from apps.billing.connectors.stripe.webhooks import handle_checkout_completed
from apps.billing.stripe.models import StripeWebhookEvent
from apps.billing.wallets.models import Wallet
from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox

ACCT = "acct_shared_1"


class _SharedAccountFixture(TestCase):
    """Live tenant + sandbox sibling, BOTH connected to the same acct_ id,
    with byte-identical customer/wallet rows on each side."""

    def setUp(self):
        self.live = Tenant.objects.create(
            name="Live Co", products=["metering", "billing"],
            stripe_connected_account_id=ACCT, charges_enabled=True)
        self.sandbox = get_or_create_sandbox(self.live)
        Tenant.objects.filter(id=self.sandbox.id).update(
            stripe_connected_account_id=ACCT, charges_enabled=True)
        self.sandbox.refresh_from_db()

        self.live_customer = Customer.objects.create(
            tenant=self.live, external_id="alice", stripe_customer_id="cus_same")
        self.sb_customer = Customer.objects.create(
            tenant=self.sandbox, external_id="alice", stripe_customer_id="cus_same")
        self.live_wallet = Wallet.objects.create(customer=self.live_customer)
        self.sb_wallet = Wallet.objects.create(customer=self.sb_customer)


class HandlerLivemodeRoutingTest(_SharedAccountFixture):
    def _account_event(self, livemode, charges_enabled=False):
        event = MagicMock()
        event.livemode = livemode
        event.account = ACCT
        event.data.object.id = ACCT
        event.data.object.charges_enabled = charges_enabled
        return event

    def test_account_updated_livemode_false_touches_only_sandbox(self):
        handle_account_updated(self._account_event(livemode=False, charges_enabled=False))
        self.live.refresh_from_db(); self.sandbox.refresh_from_db()
        self.assertTrue(self.live.charges_enabled)       # untouched
        self.assertFalse(self.sandbox.charges_enabled)   # updated

    def test_account_updated_livemode_true_touches_only_live(self):
        handle_account_updated(self._account_event(livemode=True, charges_enabled=False))
        self.live.refresh_from_db(); self.sandbox.refresh_from_db()
        self.assertFalse(self.live.charges_enabled)      # updated
        self.assertTrue(self.sandbox.charges_enabled)    # untouched

    def test_account_deauthorized_livemode_false_clears_only_sandbox(self):
        event = MagicMock()
        event.livemode = False
        event.account = ACCT
        handle_account_deauthorized(event)
        self.live.refresh_from_db(); self.sandbox.refresh_from_db()
        self.assertEqual(self.live.stripe_connected_account_id, ACCT)
        self.assertEqual(self.sandbox.stripe_connected_account_id, "")

    def _checkout_event(self, livemode):
        event = MagicMock()
        event.livemode = livemode
        event.account = ACCT
        session = event.data.object
        session.payment_status = "paid"
        session.customer = "cus_same"
        session.client_reference_id = None
        session.amount_total = 100  # $1
        session.id = f"cs_lm_{livemode}"
        session.payment_intent = None
        return event

    def test_checkout_completed_livemode_false_credits_only_sandbox_wallet(self):
        handle_checkout_completed(self._checkout_event(livemode=False))
        self.live_wallet.refresh_from_db(); self.sb_wallet.refresh_from_db()
        self.assertEqual(self.live_wallet.balance_micros, 0)
        self.assertEqual(self.sb_wallet.balance_micros, 1_000_000)

    def test_checkout_completed_livemode_true_credits_only_live_wallet(self):
        handle_checkout_completed(self._checkout_event(livemode=True))
        self.live_wallet.refresh_from_db(); self.sb_wallet.refresh_from_db()
        self.assertEqual(self.live_wallet.balance_micros, 1_000_000)
        self.assertEqual(self.sb_wallet.balance_micros, 0)

    def test_subscription_created_routes_by_livemode(self):
        from apps.subscriptions.api.webhooks import handle_subscription_created
        from apps.subscriptions.models import StripeSubscription

        event = MagicMock()
        event.livemode = False
        event.account = ACCT
        sub = event.data.object
        sub.customer = "cus_same"
        sub.id = "sub_modeshared"
        sub.status = "active"
        sub.get = lambda k, d=None: {"currency": "usd", "status": "active"}.get(k, d)
        from django.utils import timezone as djtz
        now = djtz.now()
        with patch("apps.subscriptions.api.webhooks._sum_items",
                   return_value=(1_000_000, 1, "month")), \
             patch("apps.subscriptions.api.webhooks._period_start", return_value=now), \
             patch("apps.subscriptions.api.webhooks._period_end", return_value=now), \
             patch("apps.subscriptions.api.webhooks._product_name", return_value="Plan"):
            handle_subscription_created(event)
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_modeshared")
        self.assertEqual(mirror.tenant_id, self.sandbox.id)
        self.assertEqual(mirror.customer_id, self.sb_customer.id)

    def test_payment_failed_port_binds_livemode(self):
        from django.utils import timezone as djtz

        from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
        from apps.subscriptions.ports import mark_invoice_payment_failed_for_subscription

        now = djtz.now()
        for tenant, customer, sub_id in (
            (self.live, self.live_customer, "sub_shared"),
            (self.sandbox, self.sb_customer, "sub_shared_sb"),
        ):
            sub = StripeSubscription.objects.create(
                tenant=tenant, customer=customer, stripe_subscription_id=sub_id,
                status="active", amount_micros=0, currency="usd", interval="month",
                current_period_start=now, current_period_end=now, last_synced_at=now)
            SubscriptionInvoice.objects.create(
                tenant=tenant, customer=customer, stripe_subscription=sub,
                stripe_invoice_id=f"in_{sub_id}", amount_paid_micros=0,
                currency="usd", status="open", period_start=now, period_end=now)

        # livemode=False with the LIVE sub id: account matches, mode must not.
        stamped = mark_invoice_payment_failed_for_subscription(
            ACCT, "sub_shared", "in_sub_shared", MagicMock(), livemode=False)
        self.assertFalse(stamped)
        # livemode=False with the sandbox sub id: stamps.
        stamped = mark_invoice_payment_failed_for_subscription(
            ACCT, "sub_shared_sb", "in_sub_shared_sb", MagicMock(hosted_invoice_url="",
                                                                invoice_pdf=""),
            livemode=False)
        self.assertTrue(stamped)


class EndpointModeGateTest(TestCase):
    """Dispatcher-level gates: test endpoint = test events only; live endpoint
    rejects test events ONLY once STRIPE_TEST_WEBHOOK_SECRET is configured."""

    def setUp(self):
        self.factory_client = Client()

    def _post(self, view, event):
        from django.test import RequestFactory
        request = RequestFactory().post(
            "/api/v1/webhooks/stripe", content_type="application/json")
        with patch("api.v1.webhooks.stripe.Webhook.construct_event",
                   return_value=event):
            return view(request)

    def _event(self, event_id, livemode):
        event = MagicMock()
        event.id = event_id
        event.type = "not.a.real.event"
        event.livemode = livemode
        return event

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_test_x")
    def test_live_endpoint_rejects_test_event_when_test_secret_configured(self):
        resp = self._post(stripe_webhook, self._event("evt_lm_1", livemode=False))
        self.assertEqual(resp.status_code, 400)
        # rejected BEFORE the dedup table — nothing recorded
        self.assertFalse(StripeWebhookEvent.objects.filter(stripe_event_id="evt_lm_1").exists())

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="")
    def test_live_endpoint_accepts_test_event_without_test_secret(self):
        """All-test dev setups (sk_test on the live endpoint) keep working."""
        resp = self._post(stripe_webhook, self._event("evt_lm_2", livemode=False))
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(StripeWebhookEvent.objects.filter(stripe_event_id="evt_lm_2").exists())

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_test_x")
    def test_test_endpoint_rejects_livemode_true(self):
        resp = self._post(stripe_webhook_test, self._event("evt_lm_3", livemode=True))
        self.assertEqual(resp.status_code, 400)
        self.assertFalse(StripeWebhookEvent.objects.filter(stripe_event_id="evt_lm_3").exists())

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_test_x")
    def test_test_endpoint_accepts_test_event(self):
        resp = self._post(stripe_webhook_test, self._event("evt_lm_4", livemode=False))
        self.assertEqual(resp.status_code, 200)
        event = StripeWebhookEvent.objects.get(stripe_event_id="evt_lm_4")
        self.assertEqual(event.status, "skipped")  # unknown type, but processed

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="")
    def test_test_endpoint_400_when_secret_unset(self):
        """An empty secret must never verify a signature."""
        from django.test import RequestFactory
        request = RequestFactory().post(
            "/api/v1/webhooks/stripe/test", content_type="application/json")
        resp = stripe_webhook_test(request)
        self.assertEqual(resp.status_code, 400)

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_test_x")
    def test_subscriptions_test_endpoint_gates(self):
        from apps.subscriptions.api.endpoints import subscriptions_stripe_webhook_test
        from django.test import RequestFactory

        request = RequestFactory().post(
            "/api/v1/subscriptions/webhooks/stripe/test", content_type="application/json")
        with patch("apps.subscriptions.api.endpoints.stripe.Webhook.construct_event",
                   return_value=self._event("evt_lm_5", livemode=True)):
            self.assertEqual(subscriptions_stripe_webhook_test(request).status_code, 400)
        with patch("apps.subscriptions.api.endpoints.stripe.Webhook.construct_event",
                   return_value=self._event("evt_lm_6", livemode=False)):
            self.assertEqual(subscriptions_stripe_webhook_test(request).status_code, 200)

    @override_settings(STRIPE_TEST_WEBHOOK_SECRET="")
    def test_subscriptions_test_endpoint_400_when_secret_unset(self):
        from apps.subscriptions.api.endpoints import subscriptions_stripe_webhook_test
        from django.test import RequestFactory

        request = RequestFactory().post(
            "/api/v1/subscriptions/webhooks/stripe/test", content_type="application/json")
        self.assertEqual(subscriptions_stripe_webhook_test(request).status_code, 400)

    def test_test_endpoints_are_routed(self):
        """urls.py mounts both /test endpoints (404 would mean unmounted; an
        unsigned POST is 400)."""
        with override_settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_test_x"):
            resp = self.factory_client.post(
                "/api/v1/webhooks/stripe/test", data="{}",
                content_type="application/json")
            self.assertEqual(resp.status_code, 400)
            resp = self.factory_client.post(
                "/api/v1/subscriptions/webhooks/stripe/test", data="{}",
                content_type="application/json")
            self.assertEqual(resp.status_code, 400)


class PaymentIntentModeGuardTest(_SharedAccountFixture):
    """payment_intent.* handlers match the attempt by metadata UUID; the mode
    guard keeps a wrong-mode replay off the wallet even when the account matches."""

    def _pi_event(self, attempt, livemode):
        event = MagicMock()
        event.livemode = livemode
        event.account = ACCT
        pi = event.data.object
        pi.metadata = {"topup_attempt_id": str(attempt.id)}
        pi.id = "pi_mode_1"
        pi.status = "succeeded"
        return event

    def test_succeeded_ignores_wrong_mode_event(self):
        from apps.billing.connectors.stripe.webhooks import handle_payment_intent_succeeded
        from apps.billing.topups.models import TopUpAttempt

        attempt = TopUpAttempt.objects.create(
            customer=self.sb_customer, amount_micros=1_000_000,
            trigger="auto", status="pending")
        # livemode=True event naming a SANDBOX attempt: must not credit.
        with patch("apps.billing.topups.services.AutoTopUpService.apply_topup_credit") as credit:
            handle_payment_intent_succeeded(self._pi_event(attempt, livemode=True))
            credit.assert_not_called()
            handle_payment_intent_succeeded(self._pi_event(attempt, livemode=False))
            credit.assert_called_once()

    def test_payment_failed_ignores_wrong_mode_event(self):
        from apps.billing.connectors.stripe.webhooks import (
            handle_payment_intent_payment_failed,
        )
        from apps.billing.topups.models import TopUpAttempt

        attempt = TopUpAttempt.objects.create(
            customer=self.sb_customer, amount_micros=1_000_000,
            trigger="auto", status="pending")
        event = self._pi_event(attempt, livemode=True)
        event.data.object.last_payment_error = None
        handle_payment_intent_payment_failed(event)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "pending")  # untouched

        event = self._pi_event(attempt, livemode=False)
        event.data.object.last_payment_error = None
        handle_payment_intent_payment_failed(event)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "failed")
