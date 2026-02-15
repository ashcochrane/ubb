from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.billing.stripe.models import StripeWebhookEvent


class ReprocessWebhookCommandTest(TestCase):
    def test_resets_failed_event_to_processing(self):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_reprocess_1",
            event_type="invoice.paid",
            status="failed",
            failure_reason={"error": "timeout"},
        )

        call_command("reprocess_webhook", "evt_reprocess_1")

        event.refresh_from_db()
        self.assertEqual(event.status, "processing")
        self.assertIsNone(event.failure_reason)

    def test_raises_for_nonexistent_event(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_nonexistent")

        self.assertIn("No webhook event found", str(ctx.exception))

    def test_raises_for_succeeded_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_ok",
            event_type="invoice.paid",
            status="succeeded",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_ok")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_processing_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_proc",
            event_type="invoice.paid",
            status="processing",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_proc")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_skipped_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_skip",
            event_type="invoice.paid",
            status="skipped",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_skip")

        self.assertIn("not 'failed'", str(ctx.exception))
