from django.test import TestCase
from django.db import IntegrityError, transaction
from django.utils import timezone
from apps.billing.stripe.models import StripeWebhookEvent


class StripeWebhookEventModelTest(TestCase):
    def test_create_event(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_test_123",
            event_type="checkout.session.completed",
            status="processing",
        )
        self.assertEqual(event.stripe_event_id, "evt_test_123")
        self.assertEqual(event.status, "processing")
        self.assertEqual(event.duplicate_count, 0)
        self.assertIsNotNone(event.last_seen_at)

    def test_unique_stripe_event_id(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_dup",
            event_type="invoice.paid",
            status="succeeded",
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StripeWebhookEvent.objects.create(
                    stripe_event_id="evt_dup",
                    event_type="invoice.paid",
                    status="processing",
                )

    def test_failure_reason_json(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_fail",
            event_type="invoice.paid",
            status="failed",
            failure_reason={"error": "test", "retryable": True},
        )
        event.refresh_from_db()
        self.assertTrue(event.failure_reason["retryable"])
