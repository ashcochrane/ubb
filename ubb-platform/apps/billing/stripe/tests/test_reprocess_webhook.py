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

        call_command("reprocess_webhook", "evt_reprocess_1", receiver="billing")

        event.refresh_from_db()
        self.assertEqual(event.status, "processing")
        self.assertIsNone(event.failure_reason)

    def test_raises_for_nonexistent_event(self):
        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_nonexistent", receiver="billing")

        self.assertIn("No webhook event found", str(ctx.exception))

    def test_raises_for_succeeded_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_ok",
            event_type="invoice.paid",
            status="succeeded",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_ok", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_processing_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_proc",
            event_type="invoice.paid",
            status="processing",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_proc", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_skipped_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_skip",
            event_type="invoice.paid",
            status="skipped",
        )

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_skip", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_the_receiver_is_part_of_the_identity(self):
        """C1b (F-17): the same event id is a different row per receiver, so
        the command resets only the named receiver's row and refuses a
        receiver outside the closed set."""
        StripeWebhookEvent.objects.create(
            receiver="billing", stripe_event_id="evt_both", event_type="invoice.paid",
            status="failed", failure_reason={"error": "timeout"})
        StripeWebhookEvent.objects.create(
            receiver="subscriptions", stripe_event_id="evt_both",
            event_type="invoice.paid", status="skipped")

        with self.assertRaises(CommandError) as ctx:
            call_command("reprocess_webhook", "evt_both", receiver="subscriptions")
        self.assertIn("not 'failed'", str(ctx.exception))

        call_command("reprocess_webhook", "evt_both", receiver="billing")
        rows = {r.receiver: r.status for r in StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_both")}
        self.assertEqual(rows, {"billing": "processing", "subscriptions": "skipped"})

        with self.assertRaises(CommandError):
            call_command("reprocess_webhook", "evt_both", receiver="metering")

    def test_the_receiver_is_required(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_req", event_type="invoice.paid", status="failed",
            failure_reason={"error": "timeout"})
        with self.assertRaises(CommandError):
            call_command("reprocess_webhook", "evt_req")
