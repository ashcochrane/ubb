import json
import pytest
from unittest.mock import patch, MagicMock
from django.test import TestCase, Client
from django.utils import timezone


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
            products=["metering", "subscriptions"],
            stripe_connected_account_id="acct_wh_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="cust-1", stripe_customer_id="cus_wh",
        )

        mock_event = MagicMock()
        mock_event.id = "evt_wh_1"
        mock_event.type = "customer.subscription.created"
        mock_event.account = "acct_wh_test"
        mock_event.data.object.id = "sub_wh_1"
        mock_event.data.object.customer = "cus_wh"
        mock_event.data.object.status = "active"
        mock_event.data.object.current_period_start = 1738368000
        mock_event.data.object.current_period_end = 1740960000
        mock_event.data.object.plan.product.name = "Pro"
        mock_event.data.object.plan.amount = 4900
        mock_event.data.object.plan.currency = "usd"
        mock_event.data.object.plan.interval = "month"
        mock_event.data.object.quantity = 1

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
