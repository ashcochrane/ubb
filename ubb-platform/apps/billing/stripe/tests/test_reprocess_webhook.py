"""The ``reprocess_webhook`` operator command's refusals (R10 Stage C4, PLAN §7
item 36). The command now re-runs a failed retryable event on its own row,
with the Event retrieved from Stripe under the tenant's context; its whole
recovery path, with real invoices, is
``api/v1/tests/test_an_invoice_waits_for_its_mirror.py``. Until C4 it only
reset the row to ``processing`` and waited for a redelivery that the
receiver then answered ``already_processing`` for 30 minutes; that pin
(``test_resets_failed_event_to_processing``) is replaced below by its
opposite.
"""
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.tenants.models import Tenant

RETRYABLE = {"error": "timeout", "type": "DoesNotExist", "retryable": True}


class ReprocessWebhookCommandTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id="acct_reprocess", charges_enabled=True)
        # Every case here is refused before Stripe is asked anything.
        self.retrieve = patch("stripe.Event.retrieve").start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.retrieve.assert_not_called()

    def _reprocess(self, event_id, **options):
        options.setdefault("tenant", str(self.tenant.id))
        call_command("reprocess_webhook", event_id, **options)

    def test_raises_for_nonexistent_event(self):
        with self.assertRaises(CommandError) as ctx:
            self._reprocess("evt_nonexistent", receiver="billing")

        self.assertIn("No webhook event found", str(ctx.exception))

    def test_raises_for_succeeded_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_ok",
            event_type="invoice.paid",
            status="succeeded",
        )

        with self.assertRaises(CommandError) as ctx:
            self._reprocess("evt_ok", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_processing_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_proc",
            event_type="invoice.paid",
            status="processing",
        )

        with self.assertRaises(CommandError) as ctx:
            self._reprocess("evt_proc", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_raises_for_skipped_event(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_skip",
            event_type="invoice.paid",
            status="skipped",
        )

        with self.assertRaises(CommandError) as ctx:
            self._reprocess("evt_skip", receiver="billing")

        self.assertIn("not 'failed'", str(ctx.exception))

    def test_a_failed_row_is_never_reset_to_wait_for_a_redelivery(self):
        """The old command's whole behaviour, refused: a row it cannot re-run
        now (here: the tenant has no connected account to retrieve the event
        from) is left exactly as it was, failed and retryable, so Stripe's
        own redelivery still re-runs it at once."""
        event = StripeWebhookEvent.objects.create(
            stripe_event_id="evt_reprocess_1", event_type="invoice.paid",
            status="failed", failure_reason=RETRYABLE)
        unconnected = Tenant.objects.create(name="U", products=["metering", "billing"])

        with self.assertRaisesMessage(CommandError, "no connected Stripe account"):
            self._reprocess("evt_reprocess_1", receiver="billing",
                            tenant=str(unconnected.id))

        event.refresh_from_db()
        self.assertEqual((event.status, event.failure_reason), ("failed", RETRYABLE))

    def test_a_non_retryable_failure_is_refused(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_final", event_type="invoice.paid", status="failed",
            failure_reason={"error": "refused", "type": "StripeFatalError", "retryable": False})
        with self.assertRaisesMessage(CommandError, "NON-retryably"):
            self._reprocess("evt_final", receiver="billing")

    def test_the_receiver_is_part_of_the_identity(self):
        """C1b (F-17): the same event id is a different row per receiver, so
        the command acts on only the named receiver's row and refuses a
        receiver outside the closed set."""
        StripeWebhookEvent.objects.create(
            receiver="billing", stripe_event_id="evt_both", event_type="invoice.paid",
            status="failed", failure_reason=RETRYABLE)
        StripeWebhookEvent.objects.create(
            receiver="subscriptions", stripe_event_id="evt_both",
            event_type="invoice.paid", status="skipped")

        with self.assertRaises(CommandError) as ctx:
            self._reprocess("evt_both", receiver="subscriptions")
        self.assertIn("not 'failed'", str(ctx.exception))

        # The billing row is the one acted on: with no Stripe key it is
        # refused before any request, and neither row moves.
        with self.settings(STRIPE_SECRET_KEY=""), \
                self.assertRaisesMessage(CommandError, "refused before any request"):
            self._reprocess("evt_both", receiver="billing")
        rows = {r.receiver: r.status for r in StripeWebhookEvent.objects.filter(
            stripe_event_id="evt_both")}
        self.assertEqual(rows, {"billing": "failed", "subscriptions": "skipped"})

        with self.assertRaises(CommandError):
            self._reprocess("evt_both", receiver="metering")

    def test_the_receiver_is_required(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_req", event_type="invoice.paid", status="failed",
            failure_reason=RETRYABLE)
        with self.assertRaises(CommandError):
            call_command("reprocess_webhook", "evt_req", tenant=str(self.tenant.id))

    def test_the_tenant_is_required_and_must_exist(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_ten", event_type="invoice.paid", status="failed",
            failure_reason=RETRYABLE)
        with self.assertRaises(CommandError):
            call_command("reprocess_webhook", "evt_ten", receiver="billing")
        for value, message in (("not-a-uuid", "not a tenant id"),
                               ("00000000-0000-0000-0000-000000000000", "no tenant")):
            with self.subTest(value), self.assertRaisesMessage(CommandError, message):
                self._reprocess("evt_ten", receiver="billing", tenant=value)

    def test_a_type_the_receiver_does_not_handle_is_refused_before_any_request(self):
        StripeWebhookEvent.objects.create(
            stripe_event_id="evt_alien", event_type="customer.subscription.created",
            status="failed", failure_reason=RETRYABLE)
        with self.assertRaisesMessage(CommandError, "does not handle"):
            self._reprocess("evt_alien", receiver="billing")
