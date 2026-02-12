from datetime import timedelta
from unittest.mock import patch, MagicMock

from django.test import TestCase
from django.utils import timezone

from apps.billing.stripe.models import StripeWebhookEvent
from apps.billing.stripe.tasks import cleanup_webhook_events, _batched_delete
from apps.billing.connectors.stripe.tasks import reconcile_topups_with_stripe
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.topups.models import TopUpAttempt


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


class ReconcileTopupsWithStripeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1",
        )

    def _create_attempt(self, charge_id, amount_micros=5_000_000):
        return TopUpAttempt.objects.create(
            customer=self.customer,
            amount_micros=amount_micros,
            trigger="manual",
            status="succeeded",
            stripe_charge_id=charge_id,
        )

    @patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve")
    @patch("apps.billing.connectors.stripe.tasks.time.sleep")
    def test_no_mismatch_for_matching_charge(self, mock_sleep, mock_retrieve):
        self._create_attempt("ch_ok", amount_micros=5_000_000)
        mock_charge = MagicMock()
        mock_charge.status = "succeeded"
        mock_charge.amount = 500  # 500 cents = 5_000_000 micros
        mock_charge.refunded = False
        mock_retrieve.return_value = mock_charge

        reconcile_topups_with_stripe()

        mock_retrieve.assert_called_once_with(
            "ch_ok", stripe_account="acct_test",
        )

    @patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve")
    @patch("apps.billing.connectors.stripe.tasks.time.sleep")
    def test_flags_amount_mismatch(self, mock_sleep, mock_retrieve):
        self._create_attempt("ch_bad", amount_micros=5_000_000)
        mock_charge = MagicMock()
        mock_charge.status = "succeeded"
        mock_charge.amount = 999  # Wrong amount
        mock_charge.refunded = False
        mock_retrieve.return_value = mock_charge

        with self.assertLogs("apps.billing.connectors.stripe.tasks", level="ERROR") as cm:
            reconcile_topups_with_stripe()
        self.assertTrue(any("reconciliation mismatch" in msg for msg in cm.output))

    @patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve")
    @patch("apps.billing.connectors.stripe.tasks.time.sleep")
    def test_flags_refunded_charge(self, mock_sleep, mock_retrieve):
        self._create_attempt("ch_refunded", amount_micros=5_000_000)
        mock_charge = MagicMock()
        mock_charge.status = "succeeded"
        mock_charge.amount = 500
        mock_charge.refunded = True
        mock_retrieve.return_value = mock_charge

        with self.assertLogs("apps.billing.connectors.stripe.tasks", level="ERROR") as cm:
            reconcile_topups_with_stripe()
        self.assertTrue(any("reconciliation mismatch" in msg for msg in cm.output))

    @patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve")
    @patch("apps.billing.connectors.stripe.tasks.time.sleep")
    def test_skips_old_attempts(self, mock_sleep, mock_retrieve):
        attempt = self._create_attempt("ch_old")
        # Make attempt older than 48 hours
        TopUpAttempt.objects.filter(pk=attempt.pk).update(
            updated_at=timezone.now() - timedelta(hours=49),
        )

        reconcile_topups_with_stripe()

        mock_retrieve.assert_not_called()

    @patch("apps.billing.connectors.stripe.tasks.stripe.Charge.retrieve")
    @patch("apps.billing.connectors.stripe.tasks.time.sleep")
    def test_handles_stripe_error_gracefully(self, mock_sleep, mock_retrieve):
        import stripe as stripe_lib
        self._create_attempt("ch_error")
        mock_retrieve.side_effect = stripe_lib.error.StripeError("API down")

        # Should not raise
        reconcile_topups_with_stripe()

    def test_skips_attempts_without_charge_id(self):
        TopUpAttempt.objects.create(
            customer=self.customer, amount_micros=5_000_000,
            trigger="manual", status="succeeded",
            stripe_charge_id=None,
        )
        # No Stripe API call should be attempted — no mock needed
        reconcile_topups_with_stripe()
