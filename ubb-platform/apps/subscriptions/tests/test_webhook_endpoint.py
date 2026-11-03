import hashlib
import hmac
import json
import time
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from apps.subscriptions.tests._helpers import (
    a_licensed_item, a_mirrored_subscription, a_stripe_subscription,
    a_subscription_dict)

# A placeholder, not a secret: the subscriptions receiver verifies with ITS
# OWN setting (C1b, F-17), so every test that reaches the verifier configures
# one explicitly rather than depending on the shell's throwaway.
SUBS_SECRET = "whsec_c1b_subs_receiver_placeholder"
BILLING_SECRET = "whsec_c1b_billing_receiver_placeholder"


@override_settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=SUBS_SECRET)
class TestSubscriptionsWebhookEndpoint(TestCase):
    def setUp(self):
        self.http_client = Client()

    @patch("stripe.Webhook.construct_event")
    def test_returns_400_on_bad_signature(self, mock_construct):
        mock_construct.side_effect = ValueError("bad sig")

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="bad",
        )
        self.assertEqual(response.status_code, 400)

    @patch("stripe.Webhook.construct_event")
    def test_dispatches_subscription_created(self, mock_construct):
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

        mock_construct.return_value = mock_event

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

    @patch("stripe.Webhook.construct_event")
    def test_returns_200_for_unhandled_event_type(self, mock_construct):
        mock_event = MagicMock()
        mock_event.id = "evt_unknown_1"
        mock_event.type = "charge.succeeded"
        mock_construct.return_value = mock_event

        response = self.http_client.post(
            "/api/v1/subscriptions/webhooks/stripe",
            data=b"{}",
            content_type="application/json",
            HTTP_STRIPE_SIGNATURE="valid",
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["status"], "ok")

    @patch("stripe.Webhook.construct_event")
    def test_returns_500_on_handler_exception(self, mock_construct):
        mock_event = MagicMock()
        mock_event.id = "evt_err_1"
        mock_event.type = "customer.subscription.created"
        mock_event.account = "acct_nonexistent"
        mock_event.data.object.id = "sub_err_1"
        mock_event.data.object.customer = "cus_nonexistent"
        mock_construct.return_value = mock_event

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
    @patch("stripe.Webhook.construct_event")
    def test_duplicate_event_processed_at_most_once(self, mock_construct, mock_handlers):
        from apps.billing.stripe.models import StripeWebhookEvent

        handler = MagicMock()
        mock_handlers.get.return_value = handler

        mock_event = MagicMock()
        mock_event.id = "evt_dup_1"
        mock_event.type = "customer.subscription.updated"
        mock_construct.return_value = mock_event

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

        # Exactly one dedup row exists — THIS receiver's — and it recorded
        # the duplicate.
        evt = StripeWebhookEvent.objects.get(
            receiver="subscriptions", stripe_event_id="evt_dup_1")
        self.assertEqual(evt.status, "succeeded")
        self.assertEqual(evt.duplicate_count, 1)
        self.assertEqual(StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_dup_1").count(), 1)


def _signed(secret, payload):
    ts = int(time.time())
    digest = hmac.new(secret.encode(), f"{ts}.".encode() + payload,
                      hashlib.sha256).hexdigest()
    return f"t={ts},v1={digest}"


class TestTheSubscriptionsReceiverVerifiesWithItsOwnSecret(TestCase):
    """R10 Stage C1b (F-17, RULED Q1): the subscriptions receiver is verified
    by STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET — a real, independent setting —
    and FAILS CLOSED when it is blank or missing. There is no fallback to the
    billing receiver's STRIPE_WEBHOOK_SECRET: on the C1a anchor the setting
    did not exist (`hasattr(settings, …)` was always False), so the
    subscriptions endpoint silently verified with the billing secret.
    Stripe's own verifier judges real signatures here — nothing is mocked.
    """

    def setUp(self):
        self.http_client = Client()
        self.payload = json.dumps({
            "id": "evt_c1b_subs_secret", "object": "event", "type": "c1b.probe",
            "livemode": True, "created": int(time.time()),
            "data": {"object": {"id": "c1b", "object": "probe"}}}).encode()

    def _deliver(self, signature):
        return self.http_client.post("/api/v1/subscriptions/webhooks/stripe",
                                     data=self.payload, content_type="application/json",
                                     HTTP_STRIPE_SIGNATURE=signature)

    def _refused_and_nothing_persisted(self, response):
        from apps.billing.stripe.models import StripeWebhookEvent
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StripeWebhookEvent.objects.exists())

    def test_a_blank_subscriptions_secret_fails_closed_even_with_the_billing_secret_set(self):
        """The billing secret is configured and the delivery is signed with
        it — and the subscriptions receiver still refuses: its own secret is
        blank, and it never borrows another receiver's."""
        with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET,
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=""):
            self._refused_and_nothing_persisted(
                self._deliver(_signed(BILLING_SECRET, self.payload)))
        with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET,
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET="   "):
            self._refused_and_nothing_persisted(
                self._deliver(_signed("   ", self.payload)))

    def test_a_missing_subscriptions_secret_setting_fails_closed(self):
        """The setting ABSENT from settings — the C1a anchor's own state,
        where `hasattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET")` was
        False and the receiver fell back to the billing secret — is refused
        exactly like a blank one, never answered "use the other one".
        `override_settings` cannot make a setting absent (it CREATES the
        attribute, which on the anchor was precisely what the fallback
        tested for), so the attribute is removed from the live settings
        object for the duration and put back after."""
        from django.conf import settings as django_settings
        holder = django_settings._wrapped
        name = "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET"
        had = hasattr(holder, name)
        saved = getattr(holder, name, None)
        if had:
            delattr(holder, name)
        try:
            with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET):
                self.assertFalse(hasattr(django_settings, name))
                self._refused_and_nothing_persisted(
                    self._deliver(_signed(BILLING_SECRET, self.payload)))
        finally:
            if had:
                setattr(holder, name, saved)

    def test_an_unset_subscriptions_secret_fails_closed(self):
        """Unset (None) reads as absent too: refused, nothing recorded."""
        with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET,
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=None):
            self._refused_and_nothing_persisted(
                self._deliver(_signed(BILLING_SECRET, self.payload)))

    def test_the_dedicated_secret_verifies(self):
        from apps.billing.stripe.models import StripeWebhookEvent
        with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET,
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=SUBS_SECRET):
            response = self._deliver(_signed(SUBS_SECRET, self.payload))
        self.assertEqual(response.status_code, 200)
        row = StripeWebhookEvent.objects.get(stripe_event_id="evt_c1b_subs_secret")
        self.assertEqual((row.receiver, row.status), ("subscriptions", "skipped"))

    def test_the_billing_secret_does_not_verify_the_subscriptions_receiver(self):
        with self.settings(STRIPE_WEBHOOK_SECRET=BILLING_SECRET,
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=SUBS_SECRET):
            self._refused_and_nothing_persisted(
                self._deliver(_signed(BILLING_SECRET, self.payload)))

    def test_the_test_endpoint_uses_its_own_test_secret_and_fails_closed_without_it(self):
        from apps.billing.stripe.models import StripeWebhookEvent
        test_payload = json.dumps({
            "id": "evt_c1b_subs_test_secret", "object": "event", "type": "c1b.probe",
            "livemode": False, "created": int(time.time()),
            "data": {"object": {"id": "c1b", "object": "probe"}}}).encode()

        def deliver(signature):
            return self.http_client.post(
                "/api/v1/subscriptions/webhooks/stripe/test", data=test_payload,
                content_type="application/json", HTTP_STRIPE_SIGNATURE=signature)

        test_secret = "whsec_c1b_subs_test_placeholder"
        # Blank own test secret: fails closed even though the billing test
        # secret and the live subscriptions secret are both configured.
        with self.settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_c1b_billing_test_placeholder",
                           STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=SUBS_SECRET,
                           STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET=""):
            self._refused_and_nothing_persisted(
                deliver(_signed("whsec_c1b_billing_test_placeholder", test_payload)))
            self._refused_and_nothing_persisted(deliver(_signed(SUBS_SECRET, test_payload)))
        with self.settings(STRIPE_TEST_WEBHOOK_SECRET="whsec_c1b_billing_test_placeholder",
                           STRIPE_SUBSCRIPTIONS_TEST_WEBHOOK_SECRET=test_secret):
            self.assertEqual(deliver(_signed(test_secret, test_payload)).status_code, 200)
        self.assertEqual(StripeWebhookEvent.objects.get(
            stripe_event_id="evt_c1b_subs_test_secret").receiver, "subscriptions")


class TestLiveSubscriptionsReceiverFailsClosed(TestCase):
    """W7 preparation finding F5, ruled 2026-10-30, for the subscriptions
    LIVE receiver: a missing or blank signing secret refuses the delivery
    before anything is verified or persisted. Since C1b the secret in
    question is the receiver's OWN, STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET.
    Stripe's own verifier judges real signatures here — nothing is mocked."""

    def setUp(self):
        self.http_client = Client()
        self.payload = json.dumps({
            "id": "evt_w7_subs_fail_closed", "object": "event", "type": "w7.probe",
            "livemode": True, "created": int(time.time()),
            "data": {"object": {"id": "w7", "object": "probe"}}}).encode()
        self.signed_with = lambda secret: _signed(secret, self.payload)

    def _deliver(self, signature):
        return self.http_client.post("/api/v1/subscriptions/webhooks/stripe",
                                     data=self.payload, content_type="application/json",
                                     HTTP_STRIPE_SIGNATURE=signature)

    def _refused_and_nothing_persisted(self, response):
        from apps.billing.stripe.models import StripeWebhookEvent
        self.assertEqual(response.status_code, 400)
        self.assertFalse(StripeWebhookEvent.objects.exists())

    def test_an_unset_secret_refuses_even_the_empty_key_signature(self):
        with self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=""):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("")))

    def test_a_blank_secret_refuses_even_its_own_signature(self):
        with self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET="   "):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("   ")))

    def test_a_wrong_signature_is_refused_with_a_configured_secret(self):
        with self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET="whsec_w7_configured"):
            self._refused_and_nothing_persisted(self._deliver(self.signed_with("whsec_other")))

    def test_a_correct_signature_is_accepted_with_a_configured_secret(self):
        from apps.billing.stripe.models import StripeWebhookEvent
        with self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET="whsec_w7_configured"):
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
        with self.settings(STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET=self.SECRET):
            return self.http_client.post(
                "/api/v1/subscriptions/webhooks/stripe", data=payload,
                content_type="application/json",
                HTTP_STRIPE_SIGNATURE=_signed(self.SECRET, payload))

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
