import hashlib
import hmac
import json
import logging
import time

import stripe
from unittest.mock import patch, MagicMock, PropertyMock
from django.test import Client, TestCase, RequestFactory
from django.utils import timezone
from datetime import timedelta

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.tests._rails import RailActivated
from apps.platform.customers.models import Customer
from apps.billing.topups.models import TopUpAttempt
from apps.billing.wallets.models import Wallet, WalletTransaction
from api.v1.webhooks import stripe_webhook
from apps.billing.connectors.stripe.webhooks import (
    handle_checkout_completed,
    handle_charge_dispute_created,
    handle_charge_dispute_closed,
    handle_charge_refunded,
)

#: The pinned SDK's sentinel key: `construct_from` needs one, and the conftest
#: guard blocks every network call anyway.
SK = "sk_test_sentinel"


def a_refund_dict(refund_id, amount, *, currency="usd", status="succeeded", charge=None):
    """One Stripe Refund as the API serialises it (only the fields UBB reads,
    plus the identity fields every Refund carries)."""
    return {"id": refund_id, "object": "refund", "amount": amount, "currency": currency,
            "status": status, "charge": charge, "reason": None}


def a_charge_dict(charge_id, *, amount_refunded, currency="usd", amount=None,
                  refunds=None, refunded=None):
    """One Stripe Charge as the API serialises it since 2022-11-15: the
    cumulative ``amount_refunded`` is always present; ``refunds`` is ABSENT
    unless expanded (pass ``refunds=[...]`` to model the expansion or an older
    API version's inline list)."""
    amount = (amount if amount is not None else max(amount_refunded or 0, 500))
    charge = {"id": charge_id, "object": "charge", "amount": amount,
              "amount_refunded": amount_refunded, "currency": currency,
              "refunded": (refunded if refunded is not None
                           else bool(amount_refunded) and amount_refunded >= amount),
              "status": "succeeded"}
    if refunds is not None:
        charge["refunds"] = {"object": "list", "data": refunds, "has_more": False,
                             "url": f"/v1/charges/{charge_id}/refunds"}
    return charge


def a_charge(*args, **kwargs):
    """A genuine ``stripe.Charge`` (no ``.get``; nested ``refunds`` a ListObject
    of real ``stripe.Refund``s when present)."""
    return stripe.Charge.construct_from(a_charge_dict(*args, **kwargs), SK)


def a_refund_event(charge, *, account, event_id="evt_refund", type="charge.refunded"):
    """A real ``stripe.Event`` whose ``data.object`` is a real Charge."""
    return stripe.Event.construct_from({
        "id": event_id, "object": "event", "type": type, "livemode": True,
        "created": int(time.time()), "account": account,
        "data": {"object": charge.to_dict() if hasattr(charge, "to_dict") else charge}}, SK)


class WebhookDispatcherTest(RailActivated, TestCase):
    def setUp(self):
        self.factory = RequestFactory()

    @patch("stripe.Webhook.construct_event")
    def test_signature_failure_returns_400(self, mock_construct):
        mock_construct.side_effect = ValueError("bad sig")
        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 400)

    @patch("stripe.Webhook.construct_event")
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

    @patch("stripe.Webhook.construct_event")
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

    @patch("stripe.Webhook.construct_event")
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
            # The wallet holder (Stage A, 2026-11-02): a top-up credits a
            # wallet, and only `prepaid` holds one.
            products=["metering", "billing"], billing_mode="prepaid",
        )
        customer = Customer.objects.create(
            tenant=tenant,
            external_id="cust_ext_1",
            stripe_customer_id="cus_stripe_1",
        )
        wallet = Wallet.objects.create(customer=customer)
        attempt = TopUpAttempt.objects.create(
            customer=customer,
            billing_owner_id=customer.id,
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
        mock_event.data.object.currency = "usd"
        mock_event.data.object.id = "cs_test_session_1"
        return mock_event

    @patch("stripe.Webhook.construct_event")
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
            WalletTransaction.objects.filter(wallet=wallet, transaction_type="top_up").exists()
        )

    @patch("stripe.Webhook.construct_event")
    def test_checkout_completed_credits_expired_widget_attempt(self, mock_construct):
        """C1b: widget Checkout attempts expire after 24h now, so a session
        that completes late is recovered exactly as the tenant route's is —
        the money was taken, so it is credited."""
        tenant, customer, wallet, attempt = self._create_checkout_fixtures(
            attempt_status="expired", attempt_trigger="widget",
        )
        mock_event = self._make_checkout_event(tenant, customer, attempt, event_id="evt_expired_widget")
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        attempt.refresh_from_db()
        wallet.refresh_from_db()
        self.assertEqual(attempt.status, "succeeded")
        self.assertEqual(wallet.balance_micros, 1_000_000)

    @patch("stripe.Webhook.construct_event")
    def test_checkout_completed_skips_expired_auto_top_up_attempt(self, mock_construct):
        tenant, customer, wallet, attempt = self._create_checkout_fixtures(
            attempt_status="expired", attempt_trigger="auto_top_up",
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

    @patch("stripe.Webhook.construct_event")
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


class HandleCheckoutCompletedTest(RailActivated, TestCase):
    """Tests for Phase 1 hardening: null safety, PI extraction, idempotency."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"], billing_mode="prepaid",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=0)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id,
            amount_micros=1_000_000,
            trigger="manual", status="pending",
        )

    def _make_event(self, amount_total=100, session_id="cs_test_1"):
        event = MagicMock()
        event.account = self.tenant.stripe_connected_account_id
        event.data.object.payment_status = "paid"
        event.data.object.customer = self.customer.stripe_customer_id
        event.data.object.client_reference_id = str(self.attempt.id)
        event.data.object.amount_total = amount_total
        event.data.object.currency = "usd"
        event.data.object.id = session_id
        event.data.object.payment_intent = None
        return event

    def test_checkout_completed_null_amount_total(self):
        event = self._make_event(amount_total=None)
        handle_checkout_completed(event)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_a_session_in_another_currency_credits_nothing(self):
        """§0.4 B: an amount Stripe states is read in the currency Stripe states,
        never scaled by the tenant's setting. A session in a currency UBB does
        not admit is refused, and nothing is credited at a guessed scale."""
        from core.currency_policy import CurrencyDisagreement
        event = self._make_event(amount_total=100)
        event.data.object.currency = "eur"

        with self.assertRaisesRegex(CurrencyDisagreement, "'eur'"):
            handle_checkout_completed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)
        self.assertFalse(WalletTransaction.objects.exists())

    def test_checkout_completed_zero_amount(self):
        event = self._make_event(amount_total=0)
        handle_checkout_completed(event)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 0)
        self.assertFalse(WalletTransaction.objects.exists())

    @patch("apps.billing.connectors.stripe.webhooks.stripe.PaymentIntent.retrieve")
    def test_checkout_completed_stripe_retrieve_failure_still_credits_wallet(self, mock_retrieve):
        mock_retrieve.side_effect = stripe.error.APIConnectionError("network error")
        event = self._make_event(amount_total=100)
        event.data.object.payment_intent = "pi_test_1"

        handle_checkout_completed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 1_000_000)  # 100 cents * 10_000
        txn = WalletTransaction.objects.get(wallet=self.wallet, transaction_type="top_up")
        self.assertEqual(txn.amount_micros, 1_000_000)
        # Attempt should still succeed (just without charge_id)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "succeeded")
        self.assertEqual(self.attempt.stripe_payment_intent_id, "pi_test_1")
        self.assertFalse(self.attempt.stripe_charge_id)

    def test_checkout_completed_with_an_unset_live_key_credits_and_never_reaches_transport(self):
        """Stage C1a (F-2): the PaymentIntent retrieve goes through the
        wrapper, which refuses an empty live key BEFORE any request is built;
        the Checkout money already landed, so the wallet is still credited
        (without a charge id). Before C1a the raw SDK call sent the request
        with an empty key."""
        event = self._make_event(amount_total=100)
        event.data.object.payment_intent = "pi_test_nokey"
        transport = MagicMock(name="request_raw")
        with self.settings(STRIPE_SECRET_KEY=""), \
             patch("stripe._api_requestor._APIRequestor.request_raw", transport):
            handle_checkout_completed(event)
        transport.assert_not_called()
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 1_000_000)
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.status, "succeeded")
        self.assertEqual(self.attempt.stripe_payment_intent_id, "pi_test_nokey")
        self.assertFalse(self.attempt.stripe_charge_id)

    def test_checkout_completed_reads_a_real_payment_intent_through_the_wrapper(self):
        event = self._make_event(amount_total=100)
        event.data.object.payment_intent = "pi_test_real"
        pi = stripe.PaymentIntent.construct_from(
            {"id": "pi_test_real", "object": "payment_intent", "status": "succeeded",
             "latest_charge": {"id": "ch_real", "object": "charge"}}, "sk_test_sentinel")
        with patch("apps.billing.connectors.stripe.webhooks.stripe.PaymentIntent.retrieve",
                   return_value=pi) as retrieve:
            handle_checkout_completed(event)
        self.assertEqual(retrieve.call_args.kwargs["id"], "pi_test_real")
        self.assertEqual(retrieve.call_args.kwargs["api_key"], "sk_test_sentinel")
        self.attempt.refresh_from_db()
        self.assertEqual(self.attempt.stripe_charge_id, "ch_real")

    def test_checkout_completed_duplicate_webhook_no_double_credit(self):
        event = self._make_event(amount_total=100, session_id="cs_dup_1")

        handle_checkout_completed(event)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 1_000_000)

        # Reset attempt to pending to simulate a second webhook delivery
        # (the idempotency should be on the WalletTransaction, not the attempt)
        self.attempt.refresh_from_db()
        first_balance = self.wallet.balance_micros

        # Second call — should be idempotent
        handle_checkout_completed(event)
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, first_balance)
        self.assertEqual(
            WalletTransaction.objects.filter(transaction_type="top_up").count(), 1,
        )


class PooledSeatTopUpWebhookTest(RailActivated, TestCase):
    """Task 7 — checkout.session.completed must credit the billing OWNER's
    wallet, never the seat's, even though the credit lands via a webhook
    long after the request that started the top-up. This async boundary is
    what makes this instance worse than the five synchronous writes Task 3
    already fixed: a synchronous test would not catch a regression here."""

    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(
            name="Pooled Webhook Tenant", stripe_connected_account_id="acct_pooled",
            products=["metering", "billing"], billing_mode="prepaid",
        )

    def _pooled_seat(self, stripe_customer_id):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id=f"biz_{stripe_customer_id}",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id=f"seat_{stripe_customer_id}",
            account_type="seat", parent=biz, stripe_customer_id=stripe_customer_id)
        return biz, seat

    def _event(self, customer_stripe_id, attempt, amount_total=100, session_id="cs_pooled_1"):
        event = MagicMock()
        event.account = self.tenant.stripe_connected_account_id
        event.data.object.payment_status = "paid"
        event.data.object.customer = customer_stripe_id
        event.data.object.client_reference_id = str(attempt.id) if attempt else ""
        event.data.object.amount_total = amount_total
        event.data.object.currency = "usd"
        event.data.object.id = session_id
        event.data.object.payment_intent = None
        return event

    def test_webhook_credits_business_wallet_not_seat(self):
        """The load-bearing assertion: the business's wallet moves, and no
        phantom wallet is ever created on the seat."""
        biz, seat = self._pooled_seat("cus_seat_1")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=biz.id,
            amount_micros=1_000_000, trigger="manual", status="pending")

        event = self._event("cus_seat_1", attempt, session_id="cs_pooled_1")
        handle_checkout_completed(event)

        biz_wallet.refresh_from_db()
        self.assertEqual(biz_wallet.balance_micros, 1_000_000)
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "succeeded")

    def test_webhook_via_full_dispatcher_credits_business_wallet(self):
        """Same assertion, driven through the actual HTTP webhook endpoint
        (signature verification mocked) — the most faithful rendition of
        "the webhook path", matching WebhookDispatcherTest's own harness."""
        biz, seat = self._pooled_seat("cus_seat_2")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=biz.id,
            amount_micros=2_000_000, trigger="manual", status="pending")

        event = self._event("cus_seat_2", attempt, amount_total=200,
                            session_id="cs_pooled_dispatch")
        event.type = "checkout.session.completed"
        event.id = "evt_pooled_dispatch"

        with patch("stripe.Webhook.construct_event", return_value=event):
            request = self.factory.post(
                "/api/v1/webhooks/stripe/", content_type="application/json")
            response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        biz_wallet.refresh_from_db()
        self.assertEqual(biz_wallet.balance_micros, 2_000_000)
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())

    def test_webhook_allocated_seat_resolves_to_self(self):
        """Non-pooled ("allocated") seat: resolves to self, same as an
        individual customer — unchanged behaviour."""
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_alloc",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_alloc", account_type="seat",
            parent=biz, stripe_customer_id="cus_seat_alloc")
        seat_wallet = Wallet.objects.create(customer=seat, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=seat.id,
            amount_micros=1_000_000, trigger="manual", status="pending")

        event = self._event("cus_seat_alloc", attempt, session_id="cs_alloc_1")
        handle_checkout_completed(event)

        seat_wallet.refresh_from_db()
        self.assertEqual(seat_wallet.balance_micros, 1_000_000)

    def test_webhook_missing_billing_owner_id_refuses_loudly(self):
        """Data-integrity gap: an attempt somehow lacking its pinned owner
        must not silently default to the seat. Task 7's deliberate failure
        mode is to raise (visible in error tracking; Stripe retries a non-2xx
        response) rather than answer 200 having credited nothing, or worse,
        having credited the seat."""
        biz, seat = self._pooled_seat("cus_seat_null")
        Wallet.objects.create(customer=biz, balance_micros=0)
        attempt = TopUpAttempt.objects.create(
            customer=seat, amount_micros=1_000_000,  # billing_owner_id left NULL
            trigger="manual", status="pending")

        event = self._event("cus_seat_null", attempt, session_id="cs_null_owner")
        with self.assertRaises(RuntimeError):
            handle_checkout_completed(event)
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())

    def test_webhook_no_correlating_attempt_resolves_owner_fresh(self):
        """An out-of-band Checkout Session this codebase never created (no
        client_reference_id, so no TopUpAttempt to correlate) has nothing
        pinned to consult — resolves the CURRENT owner fresh via the same
        resolver every other read/write in this bug's fix uses, rather than
        crediting the seat's raw Customer id."""
        biz, seat = self._pooled_seat("cus_seat_noattempt")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=0)

        event = self._event("cus_seat_noattempt", None, session_id="cs_no_attempt_1")
        handle_checkout_completed(event)

        biz_wallet.refresh_from_db()
        self.assertEqual(biz_wallet.balance_micros, 1_000_000)
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())


class ChargeDisputeCreatedTest(RailActivated, TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"], billing_mode="prepaid",
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
        event.data.object.currency = "usd"
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
        event.data.object.currency = "usd"
        event.data.object.reason = "fraudulent"
        event.account = "acct_test"

        # Should not raise
        handle_charge_dispute_created(event)


class ChargeDisputeClosedTest(RailActivated, TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"], billing_mode="prepaid",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_dispute_2",
        )

    def test_deducts_wallet_on_lost_dispute(self):
        event = MagicMock()
        event.data.object.id = "dp_test_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 500  # 500 cents = 5_000_000 micros
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 5_000_000)  # 10M - 5M
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, transaction_type="dispute_deduction",
        )
        self.assertEqual(txn.amount_micros, -5_000_000)
        self.assertEqual(txn.idempotency_key, "dispute:dp_test_1")

    def test_skips_won_dispute(self):
        event = MagicMock()
        event.data.object.id = "dp_won_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "won"
        event.data.object.amount = 500
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)
        self.assertFalse(WalletTransaction.objects.filter(
            transaction_type="dispute_deduction",
        ).exists())

    def test_idempotent_on_duplicate(self):
        event = MagicMock()
        event.data.object.id = "dp_idem_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 500
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)
        handle_charge_dispute_closed(event)  # Second call

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 5_000_000)  # Only deducted once
        self.assertEqual(
            WalletTransaction.objects.filter(transaction_type="dispute_deduction").count(), 1,
        )

    def test_skips_unknown_charge(self):
        event = MagicMock()
        event.data.object.id = "dp_unknown_1"
        event.data.object.charge = "ch_unknown"
        event.data.object.status = "lost"
        event.data.object.amount = 500
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)

    def test_dispute_closed_null_amount(self):
        event = MagicMock()
        event.data.object.id = "dp_null_amt_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = None
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)  # No deduction
        self.assertFalse(WalletTransaction.objects.filter(
            transaction_type="dispute_deduction",
        ).exists())

    def test_dispute_suspends_when_below_min(self):
        """Dispute deduction that drops balance below min_balance suspends customer."""
        # Balance: 10M, dispute: 1100 cents = 11M micros → balance = -1M
        # Default min_balance is 0, so -1M < -0 → suspend
        event = MagicMock()
        event.data.object.id = "dp_suspend_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 1100  # 1100 cents = 11_000_000 micros
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")
        # R10 Stage C2 (F-6): the suspension says why, and announces itself.
        from apps.platform.events.models import OutboxEvent
        from apps.platform.work import reasons
        self.assertEqual(self.customer.suspension_reason, reasons.DISPUTE_LOST)
        suspended = OutboxEvent.objects.filter(
            event_type="customer.suspended", payload__customer_id=str(self.customer.id))
        self.assertEqual(suspended.count(), 1)
        self.assertEqual(suspended.get().payload["reason"], reasons.DISPUTE_LOST)
        self.assertEqual(suspended.get().payload["balance_micros"], -1_000_000)

    def _lost_dispute_past_the_floor(self):
        event = MagicMock()
        event.data.object.id = "dp_c2_lost"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 1100  # 11M micros: 10M -> -1M, past the 0 floor
        event.data.object.currency = "usd"
        event.account = "acct_test"
        handle_charge_dispute_closed(event)
        self.customer.refresh_from_db()
        from apps.platform.work import reasons
        self.assertEqual((self.customer.status, self.customer.suspension_reason),
                         ("suspended", reasons.DISPUTE_LOST))

    def _reactivated(self):
        from apps.platform.events.models import OutboxEvent
        from apps.platform.events.schemas import CustomerReactivated
        return OutboxEvent.objects.filter(
            event_type=CustomerReactivated.EVENT_TYPE,
            payload__customer_id=str(self.customer.id))

    def test_a_lost_dispute_suspension_clears_only_when_the_durable_balance_recovers(self):
        """RULED Q4 b: `dispute_lost` clears through the durable balance-
        recovery rule — the balance back at or above the floor, the very
        condition the suspend tested — and by nothing else. This tenant is
        `off`: no enforcing artefact is involved."""
        from apps.billing.wallets import operations as wallet_ops
        from apps.platform.work import reasons
        self._lost_dispute_past_the_floor()                      # balance -1M
        with self.captureOnCommitCallbacks(execute=True):
            wallet_ops.credit(customer_id=self.customer.id, tenant=self.tenant,
                              amount_micros=500_000, idempotency_key="c2_cr_1")  # -0.5M: still past
        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "suspended")
        self.assertFalse(self._reactivated().exists())
        with patch("apps.platform.events.tasks.process_single_event"), \
                self.captureOnCommitCallbacks(execute=True):
            wallet_ops.credit(customer_id=self.customer.id, tenant=self.tenant,
                              amount_micros=1_500_000, idempotency_key="c2_cr_2")  # 1M: recovered
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.status, self.customer.suspension_reason), ("active", ""))
        self.assertEqual(self._reactivated().count(), 1)
        payload = self._reactivated().get().payload
        self.assertEqual(payload["reason_code"], reasons.DISPUTE_LOST)
        self.assertEqual(payload["balance_micros"], 1_000_000)

    def test_a_paid_invoice_never_clears_a_lost_dispute_suspension(self):
        """RULED Q4 b/the additions: payment resolution clears `payment_failed`
        and nothing else — a lost dispute is a wallet fact, not an AR one."""
        from datetime import date
        from apps.billing.invoicing.models import CustomerUsageInvoice
        from api.v1.webhooks import handle_invoice_paid
        from apps.platform.work import reasons
        self._lost_dispute_past_the_floor()
        CustomerUsageInvoice.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1), status="pushed", stripe_invoice_id="in_c2_disp",
            payment_status="open", payment_failed_at=timezone.now())
        inv = MagicMock()
        inv.id = "in_c2_disp"
        inv.subscription = None
        inv.parent = None
        inv.hosted_invoice_url = ""
        inv.invoice_pdf = ""
        event = MagicMock(account="acct_test", livemode=True)
        event.data.object = inv
        handle_invoice_paid(event)
        row = CustomerUsageInvoice.objects.get(stripe_invoice_id="in_c2_disp")
        self.assertEqual((row.payment_status, row.payment_failed_at), ("paid", None))
        self.customer.refresh_from_db()
        self.assertEqual((self.customer.status, self.customer.suspension_reason),
                         ("suspended", reasons.DISPUTE_LOST))
        self.assertFalse(self._reactivated().exists())

    def test_dispute_no_suspend_when_above_min(self):
        """Dispute deduction that keeps balance above min_balance does not suspend."""
        event = MagicMock()
        event.data.object.id = "dp_nosuspend_1"
        event.data.object.charge = "ch_dispute_2"
        event.data.object.status = "lost"
        event.data.object.amount = 200  # 200 cents = 2_000_000 micros → balance = 8M
        event.data.object.currency = "usd"
        event.account = "acct_test"

        handle_charge_dispute_closed(event)

        self.customer.refresh_from_db()
        self.assertEqual(self.customer.status, "active")
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 8_000_000)


class ChargeRefundedTest(RailActivated, TestCase):
    """The handler over genuine ``stripe.Charge`` objects (C1b moved these six
    off ``MagicMock``: the handler now reads the Charge's own ``currency`` and
    cumulative ``amount_refunded``, which a mock does not carry)."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"], billing_mode="prepaid",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_1",
        )
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_refund_1",
        )

    def _event(self, charge_id, amount_refunded, refunds=None, **kw):
        return a_refund_event(
            a_charge(charge_id, amount_refunded=amount_refunded, refunds=refunds, **kw),
            account="acct_test")

    def test_a_refund_in_another_currency_claws_back_nothing(self):
        """§0.4 B, money moving out: the refund's own currency decides the
        scale, and one UBB does not admit is refused — the wallet keeps every
        micro rather than losing a guessed amount."""
        from core.currency_policy import CurrencyDisagreement
        event = self._event("ch_refund_1", 300, refunds=[
            a_refund_dict("re_eur", 300, currency="eur")])

        with self.assertRaisesRegex(CurrencyDisagreement, "'eur'"):
            handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)

    def test_deducts_wallet_on_stripe_refund(self):
        event = self._event("ch_refund_1", 300, refunds=[a_refund_dict("re_single", 300)])

        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)  # 10M - 3M
        txn = WalletTransaction.objects.get(
            wallet=self.wallet, transaction_type="stripe_refund",
        )
        self.assertEqual(txn.amount_micros, -3_000_000)
        self.assertEqual(txn.idempotency_key, "stripe_refund:re_single")

    def test_idempotent_on_duplicate(self):
        event = self._event("ch_refund_1", 300, refunds=[a_refund_dict("re_idem", 300)])

        handle_charge_refunded(event)
        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 7_000_000)
        self.assertEqual(
            WalletTransaction.objects.filter(transaction_type="stripe_refund").count(), 1,
        )

    def test_skips_unknown_charge(self):
        event = self._event("ch_unknown", 300, refunds=[a_refund_dict("re_unknown", 300)])

        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)

    def test_charge_refunded_null_amount_refunded(self):
        event = self._event("ch_refund_1", None, refunds=[], refunded=False)

        handle_charge_refunded(event)

        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 10_000_000)  # No deduction
        self.assertFalse(WalletTransaction.objects.filter(
            transaction_type="stripe_refund",
        ).exists())

    def test_two_partial_refunds_both_debited(self):
        # Partial refund #1: $1 (re_1)
        handle_charge_refunded(self._event("ch_refund_1", 100, refunds=[
            a_refund_dict("re_1", 100)]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 9_000_000)
        # Partial refund #2: another $1 (re_2), same charge (cumulative 200c)
        handle_charge_refunded(self._event("ch_refund_1", 200, refunds=[
            a_refund_dict("re_1", 100), a_refund_dict("re_2", 100)]))
        self.wallet.refresh_from_db()
        self.assertEqual(self.wallet.balance_micros, 8_000_000)
        self.assertEqual(WalletTransaction.objects.filter(transaction_type="stripe_refund").count(), 2)
        self.assertTrue(WalletTransaction.objects.filter(idempotency_key="stripe_refund:re_2").exists())


class PooledSeatClawbackWebhookTest(RailActivated, TestCase):
    """Task 8a — the seventh instance of the seat/owner defect: dispute-lost
    and Stripe-refund clawbacks (`handle_charge_dispute_closed`,
    `handle_charge_refunded`) passed `attempt.customer_id` (the SEAT) into
    the wallet ops instead of `attempt.billing_owner_id` (pinned at creation
    by Task 7). This clawback moves money OUT: on a pooled seat the original
    credit landed on the business (Task 7), so debiting the seat instead
    mints a phantom seat wallet, drives it negative, and leaves the business
    holding a credit that was never actually reversed. Same shape and same
    three-topology coverage as PooledSeatTopUpWebhookTest above."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Clawback Tenant", stripe_connected_account_id="acct_clawback",
            products=["metering", "billing"], billing_mode="prepaid",
        )

    def _pooled_seat(self, suffix):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id=f"biz_{suffix}",
            account_type="business", billing_topology="pooled")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id=f"seat_{suffix}",
            account_type="seat", parent=biz, stripe_customer_id=f"cus_{suffix}")
        return biz, seat

    def _dispute_event(self, charge_id, dispute_id, amount=500, status="lost"):
        event = MagicMock()
        event.data.object.id = dispute_id
        event.data.object.charge = charge_id
        event.data.object.status = status
        event.data.object.amount = amount
        event.data.object.currency = "usd"
        event.account = "acct_clawback"
        return event

    def _refund_event(self, charge_id, refund_id, amount=300):
        return a_refund_event(
            a_charge(charge_id, amount_refunded=amount,
                     refunds=[a_refund_dict(refund_id, amount)]),
            account="acct_clawback")

    # ---- dispute-lost clawback ----

    def test_dispute_closed_debits_business_wallet_not_seat(self):
        biz, seat = self._pooled_seat("dispute_pooled")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        attempt = TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=biz.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_pooled_dispute")

        handle_charge_dispute_closed(
            self._dispute_event("ch_pooled_dispute", "dp_pooled_1", amount=500))

        biz_wallet.refresh_from_db()
        self.assertEqual(biz_wallet.balance_micros, 5_000_000)  # 10M - 5M
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())

    def test_dispute_closed_suspends_business_owner_not_seat(self):
        """A clawback that crosses the floor suspends the OWNER — the row
        RiskService.check actually reads for every seat funded by this
        wallet — never the seat."""
        biz, seat = self._pooled_seat("dispute_suspend")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=3_000_000)
        attempt = TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=biz.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_pooled_suspend")

        # 500 cents = 5_000_000 micros; 3M - 5M = -2M, below the default 0 floor.
        handle_charge_dispute_closed(
            self._dispute_event("ch_pooled_suspend", "dp_pooled_2", amount=500))

        biz.refresh_from_db()
        seat.refresh_from_db()
        self.assertEqual(biz.status, "suspended")
        self.assertEqual(seat.status, "active")  # the seat itself is untouched

    def test_dispute_closed_allocated_seat_resolves_to_self(self):
        """Non-pooled ("allocated") seat: resolves to self, unchanged
        behaviour — same as an individual customer."""
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_alloc_dispute",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_alloc_dispute", account_type="seat",
            parent=biz, stripe_customer_id="cus_alloc_dispute")
        seat_wallet = Wallet.objects.create(customer=seat, balance_micros=10_000_000)
        TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=seat.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_alloc_dispute")

        handle_charge_dispute_closed(
            self._dispute_event("ch_alloc_dispute", "dp_alloc_1", amount=500))

        seat_wallet.refresh_from_db()
        self.assertEqual(seat_wallet.balance_micros, 5_000_000)

    def test_dispute_closed_missing_billing_owner_id_refuses_loudly(self):
        """Same deliberate failure mode as the credit path (Task 7): a NULL
        billing_owner_id must raise rather than silently debit the seat."""
        biz, seat = self._pooled_seat("dispute_null")
        Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        TopUpAttempt.objects.create(
            customer=seat, amount_micros=5_000_000,  # billing_owner_id left NULL
            trigger="manual", status="succeeded", stripe_charge_id="ch_null_dispute")

        with self.assertRaises(RuntimeError):
            handle_charge_dispute_closed(
                self._dispute_event("ch_null_dispute", "dp_null_1", amount=500))
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())

    # ---- Stripe-initiated refund clawback ----

    def test_refund_debits_business_wallet_not_seat(self):
        biz, seat = self._pooled_seat("refund_pooled")
        biz_wallet = Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=biz.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_pooled_refund")

        handle_charge_refunded(
            self._refund_event("ch_pooled_refund", "re_pooled_1", amount=300))

        biz_wallet.refresh_from_db()
        self.assertEqual(biz_wallet.balance_micros, 7_000_000)  # 10M - 3M
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())

    def test_refund_allocated_seat_resolves_to_self(self):
        biz = Customer.objects.create(
            tenant=self.tenant, external_id="biz_alloc_refund",
            account_type="business", billing_topology="allocated")
        seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat_alloc_refund", account_type="seat",
            parent=biz, stripe_customer_id="cus_alloc_refund")
        seat_wallet = Wallet.objects.create(customer=seat, balance_micros=10_000_000)
        TopUpAttempt.objects.create(
            customer=seat, billing_owner_id=seat.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id="ch_alloc_refund")

        handle_charge_refunded(
            self._refund_event("ch_alloc_refund", "re_alloc_1", amount=300))

        seat_wallet.refresh_from_db()
        self.assertEqual(seat_wallet.balance_micros, 7_000_000)

    def test_refund_missing_billing_owner_id_refuses_loudly(self):
        biz, seat = self._pooled_seat("refund_null")
        Wallet.objects.create(customer=biz, balance_micros=10_000_000)
        TopUpAttempt.objects.create(
            customer=seat, amount_micros=5_000_000,  # billing_owner_id left NULL
            trigger="manual", status="succeeded", stripe_charge_id="ch_null_refund")

        with self.assertRaises(RuntimeError):
            handle_charge_refunded(
                self._refund_event("ch_null_refund", "re_null_1", amount=300))
        self.assertFalse(Wallet.objects.filter(customer=seat).exists())


class InvoicePaidTenantInvoiceTest(TestCase):
    """Phase 2 hardening: TenantInvoice update uses select_for_update."""

    def setUp(self):
        self.factory = RequestFactory()
        from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="",
        )
        self.period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start="2026-01-01",
            period_end="2026-02-01",
            status="closed",
        )
        self.tenant_invoice = TenantInvoice.objects.create(
            billing_period=self.period,
            tenant=self.tenant,
            stripe_invoice_id="in_test_tenant_1",
            total_amount_micros=5_000_000,
            status="sent",
        )

    @patch("stripe.Webhook.construct_event")
    def test_invoice_paid_tenant_invoice_locked(self, mock_construct):
        """TenantInvoice payment uses select_for_update."""
        mock_event = MagicMock()
        mock_event.id = "evt_inv_tenant_1"
        mock_event.type = "invoice.paid"
        mock_event.account = None  # Platform account, not connected
        mock_event.data.object.id = "in_test_tenant_1"
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)

        self.assertEqual(response.status_code, 200)
        self.tenant_invoice.refresh_from_db()
        self.assertEqual(self.tenant_invoice.status, "paid")
        self.assertIsNotNone(self.tenant_invoice.paid_at)

    @patch("stripe.Webhook.construct_event")
    def test_invoice_paid_tenant_invoice_idempotent(self, mock_construct):
        """Already-paid TenantInvoice skips update."""
        from django.utils import timezone as tz
        self.tenant_invoice.status = "paid"
        self.tenant_invoice.paid_at = tz.now()
        self.tenant_invoice.save()

        mock_event = MagicMock()
        mock_event.id = "evt_inv_tenant_2"
        mock_event.type = "invoice.paid"
        mock_event.account = None
        mock_event.data.object.id = "in_test_tenant_1"
        mock_construct.return_value = mock_event

        request = self.factory.post("/api/v1/webhooks/stripe/", content_type="application/json")
        response = stripe_webhook(request)
        self.assertEqual(response.status_code, 200)


class LiveReceiverFailsClosedTest(TestCase):
    """W7 preparation finding F5, ruled 2026-10-30: the LIVE receiver fails
    closed on a missing or blank STRIPE_WEBHOOK_SECRET, persisting nothing.

    Nothing is mocked: Stripe's own verifier is given a real `Stripe-Signature`
    header, so the cases say what a real delivery would get. Before the fix an
    empty secret went straight to the verifier, and an event signed with the
    empty key was accepted and recorded.
    """

    def setUp(self):
        self.factory = RequestFactory()
        self.payload = json.dumps({
            "id": "evt_w7_fail_closed", "object": "event", "type": "w7.probe",
            "livemode": True, "created": int(time.time()),
            "data": {"object": {"id": "w7", "object": "probe"}}}).encode()

    def _signed_with(self, secret):
        ts = int(time.time())
        digest = hmac.new(secret.encode(), f"{ts}.".encode() + self.payload,
                          hashlib.sha256).hexdigest()
        return f"t={ts},v1={digest}"

    def _deliver(self, signature):
        request = self.factory.post("/api/v1/webhooks/stripe", data=self.payload,
                                    content_type="application/json",
                                    HTTP_STRIPE_SIGNATURE=signature)
        return stripe_webhook(request)

    def _refused_and_nothing_persisted(self, response):
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StripeWebhookEvent.objects.exists())

    def test_an_unset_secret_refuses_even_the_empty_key_signature(self):
        with self.settings(STRIPE_WEBHOOK_SECRET=""):
            self._refused_and_nothing_persisted(self._deliver(self._signed_with("")))

    def test_a_blank_secret_refuses_even_its_own_signature(self):
        with self.settings(STRIPE_WEBHOOK_SECRET="   "):
            self._refused_and_nothing_persisted(self._deliver(self._signed_with("   ")))

    def test_a_wrong_signature_is_refused_with_a_configured_secret(self):
        with self.settings(STRIPE_WEBHOOK_SECRET="whsec_w7_configured"):
            self._refused_and_nothing_persisted(self._deliver(self._signed_with("whsec_other")))

    def test_a_correct_signature_is_accepted_with_a_configured_secret(self):
        with self.settings(STRIPE_WEBHOOK_SECRET="whsec_w7_configured"):
            response = self._deliver(self._signed_with("whsec_w7_configured"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_w7_fail_closed").exists())


class NoWalletSubjectWebhookTest(RailActivated, TestCase):
    """Stage A of the pre-Ash billing readiness (2026-11-02): an inbound
    Stripe event that would move wallet money for a tenant whose billing
    mode holds no wallet is refused by name at the wallet boundary and
    RECORDED on the event row as a non-retryable failure, acknowledged with
    200 — never the 500 Stripe would retry for three days. Two ways to get
    here on real data: an out-of-band Checkout Session for an `external +
    billing` tenant's Stripe customer (no attempt to correlate), and a
    dispute, refund or PaymentIntent on an attempt whose tenant has since
    left `prepaid`. The money stays where Stripe holds it; no wallet is
    made or moved; a redelivery is answered as already processed.
    """

    def setUp(self):
        self.factory = RequestFactory()

    def _dispatch(self, event):
        with patch("stripe.Webhook.construct_event", return_value=event):
            request = self.factory.post(
                "/api/v1/webhooks/stripe/", content_type="application/json")
            return stripe_webhook(request)

    def _recorded_not_retried(self, event):
        response = self._dispatch(event)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "failed")
        row = StripeWebhookEvent.objects.get(stripe_event_id=event.id)
        self.assertEqual(row.status, "failed")
        self.assertEqual(row.failure_reason["type"], "NoWalletSubjectError")
        self.assertIs(row.failure_reason["retryable"], False)
        self.assertIn("billing mode (external)", row.failure_reason["error"])
        # A redelivery is a duplicate of a settled failure, not a re-run.
        again = self._dispatch(event)
        self.assertEqual(json.loads(again.content)["status"], "already_processed")
        self.assertEqual(StripeWebhookEvent.objects.get(
            stripe_event_id=event.id).duplicate_count, 1)

    def _a_tenant_that_left_prepaid(self, *, charge_id):
        """A prepaid tenant with a credited wallet and a succeeded top-up,
        which then leaves `prepaid` — the one way a dispute, refund or
        PaymentIntent can name an attempt on a no-wallet tenant."""
        tenant = Tenant.objects.create(
            name="Left", products=["metering", "billing"], billing_mode="prepaid",
            stripe_connected_account_id="acct_left")
        customer = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_left")
        wallet = Wallet.objects.create(customer=customer, balance_micros=10_000_000)
        attempt = TopUpAttempt.objects.create(
            customer=customer, billing_owner_id=customer.id, amount_micros=5_000_000,
            trigger="manual", status="succeeded", stripe_charge_id=charge_id)
        tenant.billing_mode = "external"
        tenant.save()
        return tenant, customer, wallet, attempt

    def _wallet_untouched(self, wallet):
        wallet.refresh_from_db()
        self.assertEqual(wallet.balance_micros, 10_000_000)
        self.assertFalse(WalletTransaction.objects.filter(wallet=wallet).exists())

    def test_an_out_of_band_checkout_for_an_external_tenant_is_recorded_not_retried(self):
        tenant = Tenant.objects.create(
            name="X", products=["metering", "billing"], billing_mode="external",
            stripe_connected_account_id="acct_x")
        customer = Customer.objects.create(
            tenant=tenant, external_id="c1", stripe_customer_id="cus_x")
        event = MagicMock()
        event.id = "evt_oob_checkout"
        event.type = "checkout.session.completed"
        event.account = "acct_x"
        event.data.object.payment_status = "paid"
        event.data.object.customer = "cus_x"
        event.data.object.client_reference_id = ""
        event.data.object.amount_total = 100
        event.data.object.currency = "usd"
        event.data.object.id = "cs_oob_1"
        event.data.object.payment_intent = None

        self._recorded_not_retried(event)
        self.assertFalse(Wallet.all_objects.filter(customer=customer).exists())
        self.assertFalse(TopUpAttempt.objects.filter(customer=customer).exists())

    def test_a_lost_dispute_on_an_attempt_whose_tenant_left_prepaid_is_recorded_not_retried(self):
        _tenant, customer, wallet, _attempt = self._a_tenant_that_left_prepaid(
            charge_id="ch_left_dispute")
        event = MagicMock()
        event.id = "evt_left_dispute"
        event.type = "charge.dispute.closed"
        event.account = "acct_left"
        event.data.object.id = "dp_left"
        event.data.object.charge = "ch_left_dispute"
        event.data.object.status = "lost"
        event.data.object.amount = 500
        event.data.object.currency = "usd"

        self._recorded_not_retried(event)
        self._wallet_untouched(wallet)
        customer.refresh_from_db()
        self.assertEqual(customer.status, "active")

    def test_a_refund_on_an_attempt_whose_tenant_left_prepaid_is_recorded_not_retried(self):
        _tenant, _customer, wallet, _attempt = self._a_tenant_that_left_prepaid(
            charge_id="ch_left_refund")
        event = a_refund_event(
            a_charge("ch_left_refund", amount_refunded=300,
                     refunds=[a_refund_dict("re_left", 300)]),
            account="acct_left", event_id="evt_left_refund")

        self._recorded_not_retried(event)
        self._wallet_untouched(wallet)

    def test_a_settled_payment_intent_on_an_attempt_whose_tenant_left_prepaid_is_recorded_not_retried(self):
        _tenant, _customer, wallet, attempt = self._a_tenant_that_left_prepaid(
            charge_id="ch_left_pi")
        attempt.status = "pending"
        attempt.trigger = "auto_top_up"
        attempt.save(update_fields=["status", "trigger", "updated_at"])
        event = MagicMock()
        event.id = "evt_left_pi"
        event.type = "payment_intent.succeeded"
        event.account = "acct_left"
        event.data.object = MagicMock(
            id="pi_left", status="succeeded", latest_charge=MagicMock(id="ch_left_pi"),
            metadata={"topup_attempt_id": str(attempt.id)})

        self._recorded_not_retried(event)
        self._wallet_untouched(wallet)
        attempt.refresh_from_db()
        self.assertEqual(attempt.status, "pending")


class EachReceiverOwnsItsEventsTest(RailActivated, TestCase):
    """R10 Stage C1b (F-17, RULED Q1): Stripe delivers one event id to every
    endpoint subscribed to its type, and the two receivers deduplicate PER
    RECEIVER. On the C1a anchor one table keyed on the event id alone let
    whichever receiver answered first own the row: the other's delivery was
    "already_processed" — a `skipped` row from the wrong receiver buried the
    owner's processing, and a RETRYABLE failure on the owner was buried by
    the other receiver's skip. Here each receiver keeps its own row.
    """

    SUBS_SECRET = "whsec_c1b_subs_placeholder"

    def setUp(self):
        self.factory = RequestFactory()
        self.tenant = Tenant.objects.create(
            name="Both", stripe_connected_account_id="acct_both",
            products=["metering", "billing"], billing_mode="prepaid")

    def _billing(self, event):
        with patch("stripe.Webhook.construct_event", return_value=event):
            return stripe_webhook(self.factory.post(
                "/api/v1/webhooks/stripe", content_type="application/json"))

    def _subscriptions(self, event):
        from apps.subscriptions.api.endpoints import subscriptions_stripe_webhook
        with patch("stripe.Webhook.construct_event", return_value=event), \
                self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=self.SUBS_SECRET):
            return subscriptions_stripe_webhook(self.factory.post(
                "/api/v1/subscriptions/webhooks/stripe", content_type="application/json"))

    def _rows(self, event_id):
        return {r.receiver: r for r in StripeWebhookEvent.objects.filter(
            stripe_event_id=event_id)}

    def _account_updated(self, event_id):
        """A type the BILLING receiver owns and the subscriptions receiver does
        not; its effect (charges_enabled) is observable."""
        return stripe.Event.construct_from({
            "id": event_id, "object": "event", "type": "account.updated",
            "livemode": True, "created": int(time.time()), "account": "acct_both",
            "data": {"object": {"id": "acct_both", "object": "account",
                                "charges_enabled": True}}}, SK)

    def test_billing_first_then_subscriptions_each_keep_their_own_row(self):
        event = self._account_updated("evt_both_1")
        first = self._billing(event)
        second = self._subscriptions(event)
        self.assertEqual(json.loads(first.content)["status"], "ok")
        self.assertEqual(json.loads(second.content)["status"], "ok")
        rows = self._rows("evt_both_1")
        self.assertEqual({k: v.status for k, v in rows.items()},
                         {"billing": "succeeded", "subscriptions": "skipped"})
        self.assertEqual({v.duplicate_count for v in rows.values()}, {0})
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.charges_enabled)

    def test_subscriptions_first_then_billing_still_processes_on_the_owner(self):
        """The order that buried the owner on the anchor: the subscriptions
        receiver's `skipped` row no longer answers the billing receiver
        "already_processed"."""
        event = self._account_updated("evt_both_2")
        first = self._subscriptions(event)
        second = self._billing(event)
        self.assertEqual(json.loads(first.content)["status"], "ok")
        self.assertEqual(json.loads(second.content)["status"], "ok")
        rows = self._rows("evt_both_2")
        self.assertEqual({k: v.status for k, v in rows.items()},
                         {"billing": "succeeded", "subscriptions": "skipped"})
        self.tenant.refresh_from_db()
        self.assertTrue(self.tenant.charges_enabled)

    def test_a_redelivery_to_one_receiver_is_a_duplicate_there_only(self):
        event = self._account_updated("evt_both_3")
        self._billing(event)
        again = self._billing(event)
        self.assertEqual(json.loads(again.content)["status"], "already_processed")
        rows = self._rows("evt_both_3")
        self.assertEqual(list(rows), ["billing"])
        self.assertEqual(rows["billing"].duplicate_count, 1)
        # The other receiver's first delivery is still its own first delivery.
        self.assertEqual(json.loads(self._subscriptions(event).content)["status"], "ok")
        rows = self._rows("evt_both_3")
        self.assertEqual((rows["subscriptions"].status, rows["subscriptions"].duplicate_count),
                         ("skipped", 0))

    def test_a_retryable_failure_on_billing_is_not_buried_by_a_skip_on_subscriptions(self):
        """invoice.paid on UBB's own account with no TenantInvoice yet raises
        ObjectDoesNotExist — recorded retryable, 500 so Stripe retries. The
        subscriptions receiver then skips the same id; Stripe's retry to the
        billing receiver must STILL run the handler (and succeed once the row
        exists), not be answered from the subscriptions receiver's row."""
        from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice
        event = stripe.Event.construct_from({
            "id": "evt_both_retry", "object": "event", "type": "invoice.paid",
            "livemode": True, "created": int(time.time()), "account": None,
            "data": {"object": {"id": "in_both_retry", "object": "invoice",
                                "status": "paid"}}}, SK)
        first = self._billing(event)
        self.assertEqual(first.status_code, 500)
        row = self._rows("evt_both_retry")["billing"]
        self.assertEqual((row.status, row.failure_reason["retryable"]), ("failed", True))

        skipped = self._subscriptions(event)
        self.assertEqual(json.loads(skipped.content)["status"], "ok")
        self.assertEqual(self._rows("evt_both_retry")["subscriptions"].status, "skipped")

        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant, period_start="2026-01-01", period_end="2026-02-01",
            status="closed")
        invoice = TenantInvoice.objects.create(
            billing_period=period, tenant=self.tenant, stripe_invoice_id="in_both_retry",
            total_amount_micros=5_000_000, status="sent")
        retry = self._billing(event)
        self.assertEqual(json.loads(retry.content)["status"], "ok")
        rows = self._rows("evt_both_retry")
        self.assertEqual({k: v.status for k, v in rows.items()},
                         {"billing": "succeeded", "subscriptions": "skipped"})
        self.assertEqual(rows["billing"].duplicate_count, 1)
        invoice.refresh_from_db()
        self.assertEqual(invoice.status, "paid")


class _Capture(logging.Handler):
    """`caplog` cannot see `apps.*` loggers (propagate=False in settings), so
    the module's own logger gets a handler."""

    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


class ARealRefundIsClawedBackExactlyOnceTest(RailActivated, TestCase):
    """R10 Stage C1b, RULED Q15/Q19/Q20: genuinely constructed Charge/Refund
    shapes, HMAC-signed and delivered through the billing receiver, verified
    by Stripe's own ``Webhook.construct_event``. A real Charge under any API
    version since 2022-11-15 carries the CUMULATIVE ``amount_refunded`` and
    NO ``refunds`` list unless expanded. On the C1a anchor the handler keyed
    the no-list fallback on the charge id with no currency, so
    ``the_rails_currency(…, None)`` refused every real refund by name and no
    refund was ever clawed back; with a list, a second partial refund
    replayed the charge key and was dropped.
    """

    SECRET = "whsec_c1b_refund_receiver_placeholder"

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Refunds", stripe_connected_account_id="acct_refunds",
            products=["metering", "billing"], billing_mode="prepaid")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1", stripe_customer_id="cus_refunds")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=10_000_000)
        self.attempt = TopUpAttempt.objects.create(
            customer=self.customer, billing_owner_id=self.customer.id,
            amount_micros=5_000_000, trigger="manual", status="succeeded",
            stripe_charge_id="ch_real")

    def _deliver(self, event_id, obj, *, type="charge.refunded"):
        payload = json.dumps({
            "id": event_id, "object": "event", "type": type, "livemode": True,
            "created": int(time.time()), "account": "acct_refunds",
            "data": {"object": obj}}).encode()
        ts = int(time.time())
        digest = hmac.new(self.SECRET.encode(), f"{ts}.".encode() + payload,
                          hashlib.sha256).hexdigest()
        with self.settings(STRIPE_WEBHOOK_SECRET=self.SECRET):
            response = self.http_client.post(
                "/api/v1/webhooks/stripe", data=payload, content_type="application/json",
                HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
        return response

    def _refunded(self, event_id, amount_refunded, **kw):
        return self._deliver(event_id, a_charge_dict("ch_real", amount_refunded=amount_refunded, **kw))

    def _applied(self):
        from apps.billing.wallets import operations as wallet_ops
        return wallet_ops.stripe_refund_applied_micros_for(self.customer.id, self.attempt.id)

    def _refund_rows(self):
        return list(WalletTransaction.objects.filter(
            wallet=self.wallet, transaction_type="stripe_refund").order_by("created_at"))

    def _balance(self):
        self.wallet.refresh_from_db()
        return self.wallet.balance_micros

    def _ok(self, response):
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(json.loads(response.content)["status"], "ok")

    def test_one_partial_refund_with_no_refunds_list_is_clawed_back_in_usd(self):
        self._ok(self._refunded("evt_r1", 300))
        self.assertEqual(self._balance(), 7_000_000)
        rows = self._refund_rows()
        self.assertEqual([(r.amount_micros, r.idempotency_key, r.reference_id) for r in rows],
                         [(-3_000_000, "stripe_refund:ch_real:300", str(self.attempt.id))])
        self.assertEqual(self._applied(), 3_000_000)
        self.assertEqual(StripeWebhookEvent.objects.get(
            receiver="billing", stripe_event_id="evt_r1").status, "succeeded")

    def test_a_duplicate_delivery_of_the_same_event_moves_nothing(self):
        self._ok(self._refunded("evt_r2", 300))
        again = self._refunded("evt_r2", 300)
        self.assertEqual(json.loads(again.content)["status"], "already_processed")
        self.assertEqual((self._balance(), len(self._refund_rows())), (7_000_000, 1))

    def test_the_same_level_under_a_new_event_id_moves_nothing(self):
        """Stripe may re-send the Charge at the same cumulative level under a
        fresh event id: the applied-sum check (and the level key) answer it."""
        self._ok(self._refunded("evt_r3a", 300))
        self._ok(self._refunded("evt_r3b", 300))
        self.assertEqual((self._balance(), len(self._refund_rows())), (7_000_000, 1))

    def test_a_second_partial_refund_claws_back_exactly_the_increment(self):
        self._ok(self._refunded("evt_r4a", 100))
        self._ok(self._refunded("evt_r4b", 300))
        self.assertEqual(self._balance(), 7_000_000)
        self.assertEqual([(r.amount_micros, r.idempotency_key) for r in self._refund_rows()],
                         [(-1_000_000, "stripe_refund:ch_real:100"),
                          (-2_000_000, "stripe_refund:ch_real:300")])

    def test_a_full_refund_after_a_partial_applies_only_the_remainder(self):
        self._ok(self._refunded("evt_r5a", 200))
        self._ok(self._refunded("evt_r5b", 500, refunded=True))
        self.assertEqual(self._balance(), 5_000_000)
        self.assertEqual([r.amount_micros for r in self._refund_rows()],
                         [-2_000_000, -3_000_000])
        self.assertEqual(self._applied(), 5_000_000)

    def test_out_of_order_redelivery_converges_with_no_negative_movement(self):
        """The higher level arrives first, then the older lower one: the final
        applied sum is Stripe's cumulative, the older level is refused as a
        structured ERROR, and nothing moves back."""
        from apps.billing.wallets import operations as wallet_ops
        capture = _Capture()
        wallet_ops.logger.addHandler(capture)
        try:
            self._ok(self._refunded("evt_r6b", 300))
            self._ok(self._refunded("evt_r6a", 100))
        finally:
            wallet_ops.logger.removeHandler(capture)
        self.assertEqual((self._balance(), self._applied()), (7_000_000, 3_000_000))
        self.assertEqual([r.amount_micros for r in self._refund_rows()], [-3_000_000])
        errors = [r for r in capture.records
                  if r.levelno == logging.ERROR
                  and r.getMessage() == "billing.stripe_refund_total_below_applied"]
        self.assertEqual(len(errors), 1)
        self.assertEqual((errors[0].data["cumulative_refunded_micros"],
                          errors[0].data["applied_micros"]), (1_000_000, 3_000_000))

    def test_an_expanded_refunds_list_uses_refund_keys_and_a_later_cumulative_event_does_not_double_apply(self):
        self._ok(self._refunded("evt_r7a", 200, refunds=[
            a_refund_dict("re_7a", 100), a_refund_dict("re_7b", 100)]))
        self.assertEqual(self._balance(), 8_000_000)
        self.assertEqual([(r.amount_micros, r.idempotency_key) for r in self._refund_rows()],
                         [(-1_000_000, "stripe_refund:re_7a"), (-1_000_000, "stripe_refund:re_7b")])
        # The same level, unexpanded, under a new event id: nothing moves.
        self._ok(self._refunded("evt_r7b", 200))
        self.assertEqual((self._balance(), len(self._refund_rows())), (8_000_000, 2))
        # A third refund, unexpanded, then re-sent expanded: one increment only.
        self._ok(self._refunded("evt_r7c", 350))
        self._ok(self._refunded("evt_r7d", 350, refunds=[
            a_refund_dict("re_7a", 100), a_refund_dict("re_7b", 100),
            a_refund_dict("re_7c", 150)]))
        self.assertEqual((self._balance(), self._applied()), (6_500_000, 3_500_000))
        self.assertEqual([r.idempotency_key for r in self._refund_rows()][2:],
                         ["stripe_refund:ch_real:350"])

    def test_a_non_usd_charge_is_refused_by_name_and_moves_nothing(self):
        response = self._refunded("evt_r8", 300, currency="eur")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.content)["status"], "failed")
        row = StripeWebhookEvent.objects.get(receiver="billing", stripe_event_id="evt_r8")
        self.assertEqual((row.status, row.failure_reason["type"], row.failure_reason["retryable"]),
                         ("failed", "CurrencyDisagreement", False))
        self.assertIn("'eur'", row.failure_reason["error"])
        self.assertEqual((self._balance(), self._refund_rows()), (10_000_000, []))

    def test_a_refund_still_pending_at_charge_refunded_time_is_clawed_back_on_the_cumulative_increase(self):
        """RULED Q20: the money is leaving when Stripe raises the cumulative,
        so the claw-back is not deferred to a later `succeeded` update."""
        self._ok(self._refunded("evt_r9", 300, refunds=[
            a_refund_dict("re_pending", 300, status="pending")]))
        self.assertEqual((self._balance(), self._applied()), (7_000_000, 3_000_000))
        self.assertEqual([r.idempotency_key for r in self._refund_rows()],
                         ["stripe_refund:re_pending"])

    def test_a_refund_that_later_fails_raises_the_structured_alert_and_moves_nothing(self):
        """RULED Q19 (alert-only): `charge.refund.updated` with status
        failed/canceled is detected, the ERROR names the tenant, customer,
        charge, refund, status and amounts, and the wallet and the applied
        sum are unchanged — no automatic re-credit."""
        from apps.billing.connectors.stripe import webhooks as connector
        self._ok(self._refunded("evt_r10", 300, refunds=[
            a_refund_dict("re_fails", 300, status="pending")]))
        self.assertEqual(self._applied(), 3_000_000)

        for status, event_id in (("failed", "evt_r10_failed"), ("canceled", "evt_r10_canceled")):
            capture = _Capture()
            connector.logger.addHandler(capture)
            try:
                refund = a_refund_dict("re_fails", 300, status=status, charge="ch_real")
                refund["failure_reason"] = "expired_or_canceled_card"
                self._ok(self._deliver(event_id, refund, type="charge.refund.updated"))
            finally:
                connector.logger.removeHandler(capture)
            alerts = [r for r in capture.records if r.levelno == logging.ERROR
                      and getattr(r, "data", {}).get("alert") == "stripe_refund_reversed"]
            self.assertEqual(len(alerts), 1, [r.getMessage() for r in capture.records])
            data = alerts[0].data
            self.assertEqual(
                {k: data[k] for k in ("tenant_id", "customer_id", "owner_id", "attempt_id",
                                      "charge_id", "refund_id", "refund_status",
                                      "refund_amount_minor", "refund_currency",
                                      "applied_micros")},
                {"tenant_id": str(self.tenant.id), "customer_id": str(self.customer.id),
                 "owner_id": str(self.customer.id), "attempt_id": str(self.attempt.id),
                 "charge_id": "ch_real", "refund_id": "re_fails", "refund_status": status,
                 "refund_amount_minor": 300, "refund_currency": "usd",
                 "applied_micros": 3_000_000})
            self.assertNotIn("whsec", json.dumps(data))
            self.assertEqual(StripeWebhookEvent.objects.get(
                receiver="billing", stripe_event_id=event_id).status, "succeeded")
        # Unchanged: no re-credit, no new transaction type, the applied sum holds.
        self.assertEqual((self._balance(), self._applied()), (7_000_000, 3_000_000))
        self.assertEqual(len(self._refund_rows()), 1)
        self.assertFalse(WalletTransaction.objects.filter(
            wallet=self.wallet).exclude(transaction_type="stripe_refund").exists())
        # And the lowered cumulative Stripe now reports on the Charge is refused,
        # never clawed back again and never re-credited.
        self._ok(self._refunded("evt_r10_after", 0, refunded=False))
        self.assertEqual((self._balance(), self._applied()), (7_000_000, 3_000_000))

    def test_a_refund_update_with_another_status_is_nothing_to_act_on(self):
        from apps.billing.connectors.stripe import webhooks as connector
        capture = _Capture()
        connector.logger.addHandler(capture)
        try:
            self._ok(self._deliver("evt_r11", a_refund_dict(
                "re_ok", 300, status="succeeded", charge="ch_real"),
                type="charge.refund.updated"))
        finally:
            connector.logger.removeHandler(capture)
        self.assertEqual([r for r in capture.records if r.levelno >= logging.ERROR], [])
        self.assertEqual(self._balance(), 10_000_000)
