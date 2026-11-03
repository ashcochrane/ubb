import hashlib
import hmac
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.utils import timezone
from apps.subscriptions.tests._helpers import (
    a_licensed_item, a_mirrored_subscription, a_stripe_subscription,
    a_subscription_dict)


class TestSubscriptionsWebhookEndpoint(TestCase):
    def setUp(self):
        self.http_client = Client()

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_returns_400_on_bad_signature(self, mock_stripe):
        mock_stripe.Webhook.construct_event.side_effect = ValueError("bad sig")

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="bad",
        )
        self.assertEqual(response.status_code, 400)

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_dispatches_subscription_created(self, mock_stripe):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer

        tenant = Tenant.objects.create(
            name="test",
            products=["metering", "billing"],
            stripe_connected_account_id="acct_wh_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_wh",
        )

        mock_event = MagicMock()
        mock_event.id = "evt_wh_1"
        mock_event.type = "customer.subscription.created"
        mock_event.account = "acct_wh_test"
        mock_event.data.object = a_stripe_subscription(
            "sub_wh_1", "cus_wh", "active",
            items=[a_licensed_item(4900, qty=1, product_name="Pro")])

        mock_stripe.Webhook.construct_event.return_value = mock_event

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(response.status_code, 200)

        from apps.subscriptions.models import StripeSubscription
        self.assertTrue(
            StripeSubscription.objects.filter(stripe_subscription_id="sub_wh_1").exists()
        )

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_returns_200_for_unhandled_event_type(self, mock_stripe):
        mock_event = MagicMock()
        mock_event.id = "evt_unknown_1"
        mock_event.type = "charge.succeeded"
        mock_stripe.Webhook.construct_event.return_value = mock_event

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")

    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_returns_500_on_handler_exception(self, mock_stripe):
        mock_event = MagicMock()
        mock_event.id = "evt_err_1"
        mock_event.type = "customer.subscription.created"
        mock_event.account = "acct_nonexistent"
        mock_event.data.object.id = "sub_err_1"
        mock_event.data.object.customer = "cus_nonexistent"
        mock_stripe.Webhook.construct_event.return_value = mock_event

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(response.status_code, 500)

    def test_rejects_get_method(self):
        response = self.http_client.get(
            "/api/v1/subscriptions/webhooks/stripe",
        )
        self.assertEqual(response.status_code, 405)

    @patch("apps.subscriptions.api.endpoints.SUBSCRIPTIONS_WEBHOOK_HANDLERS")
    @patch("apps.subscriptions.api.endpoints.stripe")
    def test_duplicate_event_processed_at_most_once(self, mock_stripe, mock_handlers):
        from apps.billing.stripe.models import StripeWebhookEvent

        handler = MagicMock()
        mock_handlers.get.return_value = handler

        mock_event = MagicMock()
        mock_event.id = "evt_dup_1"
        mock_event.type = "customer.subscription.updated"
        mock_stripe.Webhook.construct_event.return_value = mock_event

        first = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(first.status_code, 200)

        second = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(second.status_code, 200)

        # Handler ran exactly once despite the duplicate delivery.
        self.assertEqual(handler.call_count, 1)

        # Exactly one dedup row exists and it recorded the duplicate.
        evt = StripeWebhookEvent.objects.get(stripe_event_id="evt_dup_1")
        self.assertEqual(evt.status, "succeeded")
        self.assertEqual(evt.duplicate_count, 1)


class TestLiveSubscriptionsReceiverFailsClosed(TestCase):
    """W7 preparation finding F5, ruled 2026-10-30, for the subscriptions
    LIVE receiver: a missing or blank STRIPE_WEBHOOK_SECRET refuses the
    delivery before anything is verified or persisted. Stripe's own verifier
    judges real signatures here — nothing is mocked."""

    def setUp(self):
        import hashlib, hmac, time
        self.http_client = Client()
        self.payload = json.dumps({
            "id": "evt_w7_subs_fail_closed", "object": "event", "type": "w7.probe",
            "livemode": True, "created": int(time.time()),
            "data": {"object": {"id": "w7", "object": "probe"}}}).encode()

        def signed_with(secret):
            ts = int(time.time())
            digest = hmac.new(secret.encode(), f"{ts}.".encode() + self.payload,
                              hashlib.sha256).hexdigest()
            return f"t={ts},v1={digest}"
        self.signed_with = signed_with

    def _deliver(self, signature):
        return self.http_client.post("/api/v1/subscriptions/webhooks/stripe",
                                     data=self.payload, content_type="application/json",
                                     HTTP_STRIPE_SIGNATURE=signature)

    def _refused_and_nothing_persisted(self, response):
        from apps.billing.stripe.models import StripeWebhookEvent
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StripeWebhookEvent.objects.exists())

    def test_an_unset_secret_refuses_even_the_empty_key_signature(self):
        with self.settings(STRIPE_WEBHOOK_SECRET=""):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("")))

    def test_a_blank_secret_refuses_even_its_own_signature(self):
        with self.settings(STRIPE_WEBHOOK_SECRET="   "):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("   ")))

    def test_a_wrong_signature_is_refused_with_a_configured_secret(self):
        with self.settings(STRIPE_WEBHOOK_SECRET="whsec_w7_configured"):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("whsec_other")))

    def test_a_correct_signature_is_accepted_with_a_configured_secret(self):
        from apps.billing.stripe.models import StripeWebhookEvent
        with self.settings(STRIPE_WEBHOOK_SECRET="whsec_w7_configured"):
            response = self._deliver(self.signed_with("whsec_w7_configured"))
        self.assertEqual(response.status_code, 200)
        self.assertTrue(StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_w7_subs_fail_closed").exists())


class TestARealSignedSubscriptionEventOverTheSubscriptionsReceiver(TestCase):
    """Stage C1a (F-3b): a genuinely signed ``customer.subscription.created``
    and ``updated`` posted to the subscriptions receiver, verified by Stripe's
    own ``Webhook.construct_event`` — the handler gets the real
    ``stripe.Subscription`` (no ``.get``; ``pause_collection`` a StripeObject;
    ``price.product`` an id string unless expanded). On the anchor both
    answered 500 ``{"type": "AttributeError", "error": "get"}`` over the wire
    (``R10-BILLING-READINESS/evidence/07-plans-subscriptions.txt``)."""

    SECRET = "whsec_c1a_subs_receiver"

    def setUp(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="signed", products=["metering", "billing"],
            stripe_connected_account_id="acct_signed_subs")
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1", stripe_customer_id="cus_signed")

    def _deliver(self, event_id, kind, sub_dict):
        payload = json.dumps({
            "id": event_id, "object": "event", "type": kind, "livemode": True,
            "created": int(time.time()), "account": "acct_signed_subs",
            "data": {"object": sub_dict}}).encode()
        ts = int(time.time())
        digest = hmac.new(self.SECRET.encode(), f"{ts}.".encode() + payload,
                          hashlib.sha256).hexdigest()
        with self.settings(STRIPE_WEBHOOK_SECRET=self.SECRET):
            return self.http_client.post(
                "/api/v1/subscriptions/webhooks/stripe", data=payload,
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")

    def test_a_signed_created_event_mirrors_the_subscription_and_answers_200(self):
        from apps.billing.stripe.models import StripeWebhookEvent
        from apps.subscriptions.models import StripeSubscription
        response = self._deliver(
            "evt_signed_created", "customer.subscription.created",
            a_subscription_dict("sub_signed", "cus_signed", "active", items=[
                a_licensed_item(4900, qty=1, product_name="Pro"),
                a_licensed_item(1000, qty=3)]))
        self.assertEqual(response.status_code, 200, response.content)
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_signed")
        self.assertEqual((mirror.stripe_product_name, mirror.amount_micros, mirror.quantity),
                         ("Pro", (4900 + 3 * 1000) * 10_000, 3))
        self.assertEqual(StripeWebhookEvent.objects.get(
            stripe_event_id="evt_signed_created").status, "succeeded")

    def test_a_signed_updated_event_with_pause_and_pending_cancel_answers_200(self):
        from apps.subscriptions.models import StripeSubscription
        now = timezone.now()
        a_mirrored_subscription(
            tenant=self.tenant, customer=self.customer, stripe_subscription_id="sub_signed_u",
            stripe_product_name="Pro", status="active", amount_micros=49_000_000,
            currency="usd", interval="month", current_period_start=now,
            current_period_end=now, last_synced_at=now)
        response = self._deliver(
            "evt_signed_updated", "customer.subscription.updated",
            a_subscription_dict("sub_signed_u", "cus_signed", "active",
                                cancel_at_period_end=True,
                                pause_collection={"behavior": "void", "resumes_at": None},
                                items=[a_licensed_item(4900, qty=1)]))
        self.assertEqual(response.status_code, 200, response.content)
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_signed_u")
        self.assertEqual((mirror.cancel_at_period_end, mirror.paused, mirror.status),
                         (True, True, "active"))
