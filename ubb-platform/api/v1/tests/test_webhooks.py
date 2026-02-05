from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta

from apps.stripe_integration.models import StripeWebhookEvent
from apps.platform.tenants.models import Tenant
from apps.customers.models import Customer, TopUpAttempt, WalletTransaction
from api.v1.webhooks import stripe_webhook


class WebhookDispatcherTest(TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_signature_failure_returns_400(self, mock_construct):
        mock_construct.side_effect = ValueError("bad sig")
        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 400)

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_new_event_creates_webhook_event(self, mock_construct):
        mock_event = MagicMock()
        mock_event.id = "evt_test_new"
        mock_event.type = "unknown.event"
        mock_event.data.object = {}
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(StripeWebhookEvent.objects.filter(stripe_event_id="evt_test_new").exists())

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_duplicate_event_returns_already_processed(self, mock_construct):
        # Create an already-processed event
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_dup",
            event_type="checkout.session.completed",
            status="succeeded",
        )
        mock_event = MagicMock()
        mock_event.id = "evt_dup"
        mock_event.type = "checkout.session.completed"
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        event = StripeWebhookEvent.objects.get(stripe_event_id="evt_dup")
        self.assertEqual(event.duplicate_count, 1)

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_unknown_event_type_sets_skipped(self, mock_construct):
        mock_event = MagicMock()
        mock_event.id = "evt_unknown"
        mock_event.type = "not.a.real.event"
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        event = StripeWebhookEvent.objects.get(stripe_event_id="evt_unknown")
        self.assertEqual(event.status, "skipped")

    # --- Checkout completed: expired manual top-up recovery ---

    def _create_checkout_fixtures(self, attempt_status="pending", attempt_trigger="manual"):
        """Helper to create tenant, customer, wallet, and top-up attempt."""
        tenant = Tenant.objects.create(
            name="Test Tenant",
            stripe_connected_account_id="acct_test_123",
        )
        customer = Customer.objects.create(
            tenant=tenant,
            external_id="cust_ext_1",
            stripe_customer_id="cus_stripe_1",
        )
        wallet = customer.wallet  # auto-created by Customer.save()
        attempt = TopUpAttempt.objects.create(
            customer=customer,
            amount_micros=1_000_000,
            trigger=attempt_trigger,
            status=attempt_status,
        )
        return tenant, customer, wallet, attempt

    def _make_checkout_event(self, tenant, customer, attempt, event_id="evt_checkout_1"):
        """Build a mock Stripe checkout.session.completed event."""
        mock_event = MagicMock()
        mock_event.id = event_id
        mock_event.type = "checkout.session.completed"
        mock_event.account = tenant.stripe_connected_account_id
        mock_event.data.object.payment_status = "paid"
        mock_event.data.object.customer = customer.stripe_customer_id
        mock_event.data.object.client_reference_id = str(attempt.id)
        mock_event.data.object.amount_total = 100  # 100 cents = $1 = 1_000_000 micros
        mock_event.data.object.id = "cs_test_session_1"
        return mock_event

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_checkout_completed_credits_expired_manual_attempt(self, mock_construct):
        tenant, customer, wallet, attempt = self._create_checkout_fixtures(
            attempt_status="expired", attempt_trigger="manual",
        )
        mock_event = self._make_checkout_event(tenant, customer, attempt, event_id="evt_expired_manual")
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(attempt.status, "succeeded")
        expected_micros = 100 * 10_000  # 1_000_000
        self.assertEqual(wallet.balance_micros, expected_micros)
        self.assertTrue(
            WalletTransaction.objects.filter(wallet=wallet, transaction_type="TOP_UP").exists()
        )

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_checkout_completed_skips_expired_auto_topup_attempt(self, mock_construct):
        tenant, customer, wallet, attempt = self._create_checkout_fixtures(
            attempt_status="expired", attempt_trigger="auto_topup",
        )
        mock_event = self._make_checkout_event(tenant, customer, attempt, event_id="evt_expired_auto")
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(attempt.status, "expired")
        self.assertEqual(wallet.balance_micros, 0)

    @patch("api.v1.webhooks.stripe.Webhook.construct_event")
    def test_checkout_completed_skips_already_succeeded_attempt(self, mock_construct):
        tenant, customer, wallet, attempt = self._create_checkout_fixtures(
            attempt_status="succeeded", attempt_trigger="manual",
        )
        mock_event = self._make_checkout_event(tenant, customer, attempt, event_id="evt_already_ok")
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(attempt.status, "succeeded")
        self.assertEqual(wallet.balance_micros, 0)
