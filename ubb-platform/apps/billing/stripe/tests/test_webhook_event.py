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
        """Unique per RECEIVER (C1b, F-17): a second row for the same event id
        on the same receiver is refused by the database."""
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

    def test_the_same_event_id_is_a_row_per_receiver(self):
        """The dedup identity is (receiver, stripe_event_id): the billing and
        subscriptions receivers each record the one Stripe event id Stripe
        delivered to both, and the default receiver is `billing`."""
        billing = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_both", event_type="invoice.paid", status="succeeded")
        subs = StripeWebhookEvent.objects.create(
            receiver="subscriptions", stripe_event_id="evt_both",
            event_type="invoice.paid", status="skipped")
        self.assertEqual(billing.receiver, "billing")
        self.assertEqual(
            sorted(StripeWebhookEvent.objects.filter(stripe_event_id="evt_both")
                   .values_list("receiver", "status")),
            [("billing", "succeeded"), ("subscriptions", "skipped")])
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StripeWebhookEvent.objects.create(
                    receiver="subscriptions", stripe_event_id="evt_both",
                    event_type="invoice.paid", status="processing")

    def test_a_receiver_outside_the_closed_set_is_refused_by_the_database(self):
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                StripeWebhookEvent.objects.create(
                    receiver="metering", stripe_event_id="evt_third",
                    event_type="invoice.paid", status="processing")

    def test_failure_reason_json(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_fail",
            event_type="invoice.paid",
            status="failed",
            failure_reason={"error": "test", "retryable": True},
        )
        event.refresh_from_db()
        self.assertTrue(event.failure_reason["retryable"])
