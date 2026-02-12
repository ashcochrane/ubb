from unittest.mock import patch, MagicMock, PropertyMock
from django.test import TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.topups.models import TopUpAttempt
from apps.billing.wallets.models import Wallet, WalletTransaction
from api.v1.webhooks import stripe_webhook
from apps.billing.connectors.stripe.webhooks import (
    handle_charge_dispute_created,
    handle_charge_dispute_closed,
    handle_charge_refunded,
)


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
        wallet = Wallet.objects.create(customer=customer)
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


class ChargeDisputeCreatedTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_dispute_1",
        )

    def test_logs_dispute_for_known_charge(self):
        event = MagicMock()
        event.data.object.charge = "ch_dispute_1"
        event.data.object.amount = 500
        event.data.object.reason = "fraudulent"
        event.account = "acct_test"

        # Should not raise — just logs
        handle_charge_dispute_created(event)

        # Balance unchanged — dispute created is for flagging only
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)

    def test_skips_unknown_charge(self):
        event = MagicMock()
        event.data.object.charge = "ch_unknown"
        event.data.object.amount = 500
        event.data.object.reason = "fraudulent"
        event.account = "acct_test"

        # Should not raise
        handle_charge_dispute_created(event)


class ChargeDisputeClosedTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_dispute_2",
        )

    def test_deducts_wallet_on_lost_dispute(self):
        event = MagicMock()
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 500  # 500 cents = 5_000_000 micros
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 5_000_000)  # 10M - 5M
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, transaction_type="DISPUTE_DEDUCTION",
        )
        self.assertEqual(txn.amount_micros, -5_000_000)
        self.assertEqual(txn.idempotency_key, "dispute:ch_dispute_2")

    def test_skips_won_dispute(self):
        event = MagicMock()
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "won"
        event.data.object.amount = 500
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)
        self.assertFalse(WalletTransaction.objects.filter(
            transaction_type="DISPUTE_DEDUCTION",
        ).exists())

    def test_idempotent_on_duplicate(self):
        event = MagicMock()
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 500
        event.account = "acct_test"

        handle_charge_dispute_closed(event)
        handle_charge_dispute_closed(event)  # Second call

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 5_000_000)  # Only deducted once
        self.assertEqual(
            WalletTransaction.objects.filter(transaction_type="DISPUTE_DEDUCTION").count(), 1,
        )

    def test_skips_unknown_charge(self):
        event = MagicMock()
        event.data.object.charge = "ch_unknown"
        event.data.object.status = "lost"
        event.data.object.amount = 500
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)


class ChargeRefundedTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_refund_1",
        )

    def test_deducts_wallet_on_stripe_refund(self):
        event = MagicMock()
        event.data.object.id = "ch_refund_1"
        event.data.object.amount_refunded = 300  # 300 cents = 3_000_000 micros
        event.account = "acct_test"

        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)  # 10M - 3M
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, transaction_type="STRIPE_REFUND",
        )
        self.assertEqual(txn.amount_micros, -3_000_000)
        self.assertEqual(txn.idempotency_key, "stripe_refund:ch_refund_1")

    def test_idempotent_on_duplicate(self):
        event = MagicMock()
        event.data.object.id = "ch_refund_1"
        event.data.object.amount_refunded = 300
        event.account = "acct_test"

        handle_charge_refunded(event)
        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)
        self.assertEqual(
            WalletTransaction.objects.filter(transaction_type="STRIPE_REFUND").count(), 1,
        )

    def test_skips_unknown_charge(self):
        event = MagicMock()
        event.data.object.id = "ch_unknown"
        event.data.object.amount_refunded = 300
        event.account = "acct_test"

        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)
