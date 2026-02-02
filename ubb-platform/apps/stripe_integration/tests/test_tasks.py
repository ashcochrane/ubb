from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.stripe_integration.models import StripeWebhookEvent
from apps.stripe_integration.tasks import cleanup_webhook_events, _batched_delete


class CleanupWebhookEventsTest(TestCase):
    def _create_event(self, stripe_event_id, status, days_ago):
        event = StripeWebhookEvent.objects.create(
            stripe_event_id=stripe_event_id,
            event_type="test.event",
            status=status,
        )
        # Override auto_now_add by using update()
        StripeWebhookEvent.objects.filter(pk=event.pk).update(
            created_at=timezone.now() - timedelta(days=days_ago)
        )
        return event

    def test_deletes_succeeded_events_older_than_90_days(self):
        old = self._create_event("evt_old_ok", "succeeded", days_ago=91)
        recent = self._create_event("evt_new_ok", "succeeded", days_ago=30)

        cleanup_webhook_events()

        self.assertFalse(StripeWebhookEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(StripeWebhookEvent.objects.filter(pk=recent.pk).exists())

    def test_deletes_skipped_events_older_than_90_days(self):
        old = self._create_event("evt_old_skip", "skipped", days_ago=91)

        cleanup_webhook_events()

        self.assertFalse(StripeWebhookEvent.objects.filter(pk=old.pk).exists())

    def test_deletes_failed_events_older_than_180_days(self):
        old = self._create_event("evt_old_fail", "failed", days_ago=181)
        recent_fail = self._create_event("evt_recent_fail", "failed", days_ago=100)

        cleanup_webhook_events()

        self.assertFalse(StripeWebhookEvent.objects.filter(pk=old.pk).exists())
        self.assertTrue(StripeWebhookEvent.objects.filter(pk=recent_fail.pk).exists())

    def test_does_not_delete_processing_events(self):
        old_processing = self._create_event("evt_old_proc", "processing", days_ago=200)

        cleanup_webhook_events()

        self.assertTrue(StripeWebhookEvent.objects.filter(pk=old_processing.pk).exists())

    def test_no_events_to_delete(self):
        """Runs without error when there are no events to clean up."""
        cleanup_webhook_events()


class BatchedDeleteTest(TestCase):
    def test_batched_delete_with_small_batch_size(self):
        for i in range(5):
            event = StripeWebhookEvent.objects.create(
                stripe_event_id=f"evt_batch_{i}",
                event_type="test.event",
                status="succeeded",
            )
            StripeWebhookEvent.objects.filter(pk=event.pk).update(
                created_at=timezone.now() - timedelta(days=100)
            )

        qs = StripeWebhookEvent.objects.filter(status="succeeded")
        _batched_delete(qs, batch_size=2)

        self.assertEqual(StripeWebhookEvent.objects.count(), 0)
