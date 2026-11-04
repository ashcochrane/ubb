"""A subscription invoice that arrives before its mirror is retried, never
acknowledged and lost (R10 Stage C4, PLAN §7 items 30 and 36).

At ``cf46154f`` the billing receiver's invoice reconcile returned quietly when
the subscription had no mirror (``if not sub: return``), so the receiver
recorded the event ``succeeded`` and no ``SubscriptionInvoice`` was ever
created. And the ``reprocess_webhook`` command only reset a row to
``processing``, which made every Stripe redelivery answer
``already_processing`` for the next 30 minutes and ran nothing.

Two routes now recover the same durable record with the same receiver
semantics: Stripe's own redelivery (12), and the operator's
``reprocess_webhook`` (13, 14). Every delivery here is signed and verified by
Stripe's own verifier; the operator command retrieves a genuine
``stripe.Event`` (``Event.retrieve`` is the one thing faked: no network).
Test (2) is the subscription UBB itself opened: its explicit owner is bound,
the hourly sync cannot move it, and its invoice freezes that same owner.
"""
import hashlib
import hmac
import json
import time
from unittest.mock import patch

import stripe
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import RequestFactory, TestCase
from django.utils import timezone

from apps.billing.stripe.models import StripeWebhookEvent
from apps.platform.customers.models import Customer
from apps.platform.plans.tests._helpers import a_plan
from apps.platform.tenants.models import Tenant
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from apps.subscriptions.tests._helpers import (
    SK, a_licensed_item, a_stripe_subscription, a_subscription_dict,
    clear_stripe_customer_id_in_the_admin)

ACCT = "acct_c4_invoice"
WIRE_SECRET = "whsec_c4_billing_receiver_test_only"


def _invoice_event(event_id, invoice_id, sub_id, *, event_type="invoice.finalized",
                   account=ACCT, livemode=True):
    """The JSON of a subscription invoice event, as Stripe sends it."""
    return {
        "id": event_id, "object": "event", "type": event_type, "livemode": livemode,
        "created": int(time.time()), "account": account,
        "data": {"object": {
            "id": invoice_id, "object": "invoice", "customer": "cus_shared",
            "subscription": sub_id, "parent": None, "amount_paid": 4900,
            "currency": "usd", "hosted_invoice_url": "https://pay/1",
            "invoice_pdf": "https://pdf/1", "status_transitions": {"paid_at": None},
            "period_start": 1738368000, "period_end": 1740960000}}}


class _InvoiceBeforeMirror(TestCase):
    """A pooled seat holds the Stripe customer id its subscription charges,
    and so does another customer: the new mirror is ambiguous until the
    other customer's id is cleared. The C2 historical owner of the seat's
    invoice is its business."""

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id=ACCT, charges_enabled=True)
        self.business = Customer.objects.create(
            tenant=self.tenant, external_id="biz", account_type="business",
            billing_topology="pooled", metadata={"crm": "biz"})
        self.seat = Customer.objects.create(
            tenant=self.tenant, external_id="seat", account_type="seat",
            parent=self.business, stripe_customer_id="cus_shared",
            metadata={"crm": "seat"})
        self.other = Customer.objects.create(
            tenant=self.tenant, external_id="other", stripe_customer_id="cus_shared",
            metadata={"crm": "other"})

    # -- the routes ------------------------------------------------------------

    def deliver(self, event):
        """One signed delivery through the billing receiver."""
        from api.v1.webhooks import stripe_webhook
        payload = json.dumps(event).encode()
        ts = int(time.time())
        digest = hmac.new(WIRE_SECRET.encode(), f"{ts}.".encode() + payload,
                          hashlib.sha256).hexdigest()
        request = RequestFactory().post(
            "/api/v1/webhooks/stripe", data=payload, content_type="application/json",
            HTTP_STRIPE_SIGNATURE=f"t={ts},v1={digest}")
        with self.settings(STRIPE_WEBHOOK_SECRET=WIRE_SECRET, STRIPE_TEST_WEBHOOK_SECRET=""):
            return stripe_webhook(request)

    def reprocess(self, event_id, tenant=None, *, retrieved=None, **retrieve):
        """The operator command, with Stripe answering ``retrieved`` (a genuine
        ``stripe.Event`` built from its JSON) or the ``retrieve`` patch kwargs."""
        if retrieved is not None:
            retrieve.setdefault("return_value", stripe.Event.construct_from(retrieved, SK))
        with patch("stripe.Event.retrieve", **retrieve) as retrieved_call:
            call_command("reprocess_webhook", event_id, receiver="billing",
                         tenant=str((tenant or self.tenant).id))
        return retrieved_call

    def sync(self):
        """The hourly sync, listing the subscription under the shared id."""
        from apps.subscriptions.stripe.sync import sync_subscriptions
        page = stripe.ListObject.construct_from(
            {"object": "list", "has_more": False, "url": "/v1/subscriptions",
             "data": [a_subscription_dict("sub_late", "cus_shared", "active",
                                          items=[a_licensed_item(4900, product_name="Pro")])]},
            SK)
        with patch("apps.subscriptions.stripe.sync.stripe.Subscription.list", return_value=page):
            return sync_subscriptions(self.tenant)

    # -- what the tests read ---------------------------------------------------

    def row(self, event_id):
        return StripeWebhookEvent.objects.get(receiver="billing", stripe_event_id=event_id)

    def invoices(self):
        return SubscriptionInvoice.objects.filter(stripe_invoice_id="in_late")

    def assert_failed_retryably_with_no_invoice(self, event_id):
        row = self.row(event_id)
        self.assertEqual(row.status, "failed")
        self.assertIs(row.failure_reason["retryable"], True)
        self.assertEqual(row.failure_reason["type"], "DoesNotExist")
        self.assertFalse(self.invoices().exists())

    def an_invoice_recorded_before_its_mirror(self, event_id="evt_late"):
        """The invoice arrives; the mirror is ambiguous, then stays so through
        a sync and a redelivery; then the ambiguity is removed and the sync
        binds the mirror exactly once, to the seat."""
        event = _invoice_event(event_id, "in_late", "sub_late")
        self.assertEqual(self.deliver(event).status_code, 500)
        self.assert_failed_retryably_with_no_invoice(event_id)

        self.assertEqual(self.sync()["skipped"], 1)            # still ambiguous
        self.assertEqual(self.deliver(event).status_code, 500)  # still retryable
        self.assert_failed_retryably_with_no_invoice(event_id)

        clear_stripe_customer_id_in_the_admin(self.other)
        self.assertEqual(self.sync(), {"synced": 1, "skipped": 0, "errors": 0})
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_late")
        self.assertEqual((mirror.customer_id, mirror.tenant_id), (self.seat.id, self.tenant.id))
        return event

    def assert_one_invoice_owned_by_the_business(self):
        invoice = self.invoices().get()
        # C2's frozen historical owner: the seat's billing owner, its business.
        self.assertEqual((invoice.customer_id, invoice.billing_owner_id),
                         (self.seat.id, self.business.id))
        self.assertEqual(invoice.status, "open")
        return invoice


class StripeRedeliveryRecoversTheInvoiceTest(_InvoiceBeforeMirror):
    """(12) The invoice is recovered by Stripe redelivering the original event."""

    def test_the_redelivery_after_the_binding_creates_the_invoice_exactly_once(self):
        event = self.an_invoice_recorded_before_its_mirror()

        response = self.deliver(event)
        self.assertEqual((response.status_code, json.loads(response.content)),
                         (200, {"status": "ok"}))
        self.assertEqual(self.row("evt_late").status, "succeeded")
        self.assert_one_invoice_owned_by_the_business()

        response = self.deliver(event)
        self.assertEqual(json.loads(response.content), {"status": "already_processed"})
        self.assertEqual(self.invoices().count(), 1)
        self.assertEqual(StripeWebhookEvent.objects.filter(stripe_event_id="evt_late").count(), 1)

    def test_a_paid_invoice_before_its_mirror_strands_none_of_its_other_effects(self):
        """invoice.paid reconciles before its top-up/platform work, so the raise
        leaves nothing half done: the redelivery does the whole of it once."""
        event = _invoice_event("evt_paid_late", "in_late", "sub_late", event_type="invoice.paid")
        self.assertEqual(self.deliver(event).status_code, 500)
        self.assertFalse(self.invoices().exists())
        clear_stripe_customer_id_in_the_admin(self.other)
        self.sync()
        self.assertEqual(self.deliver(event).status_code, 200)
        invoice = self.invoices().get()
        self.assertEqual((invoice.status, invoice.billing_owner_id), ("paid", self.business.id))
        self.assertIsNotNone(invoice.paid_at)


class TheOperatorReprocessRecoversTheInvoiceTest(_InvoiceBeforeMirror):
    """(13) The same record, recovered by the existing operator command: no
    further Stripe delivery and no wait for the processing TTL."""

    def test_reprocess_after_the_binding_creates_the_invoice_exactly_once(self):
        event = self.an_invoice_recorded_before_its_mirror()
        before = self.row("evt_late").updated_at

        retrieved = self.reprocess("evt_late", retrieved=event)

        # Run now, on the recorded row: it was refreshed moments ago, well
        # inside the 30-minute processing TTL, and nothing was redelivered.
        self.assertLess(timezone.now() - before, timezone.timedelta(minutes=1))
        retrieved.assert_called_once()
        self.assertEqual(self.row("evt_late").status, "succeeded")
        self.assert_one_invoice_owned_by_the_business()

        # Another reprocess is refused, and another delivery is a duplicate.
        with self.assertRaisesMessage(CommandError, "not 'failed'"):
            self.reprocess("evt_late", retrieved=event)
        self.assertEqual(json.loads(self.deliver(event).content),
                         {"status": "already_processed"})
        self.assertEqual(self.invoices().count(), 1)
        self.assertEqual(StripeWebhookEvent.objects.filter(stripe_event_id="evt_late").count(), 1)


class TheReprocessRepairTest(_InvoiceBeforeMirror):
    """(14) The narrow repair: the authoritative Event is retrieved through the
    guarded transport under the tenant's own context, checked against the row
    and the tenant, and run through the receiver's own core on the same row."""

    def bound_and_recorded(self):
        return self.an_invoice_recorded_before_its_mirror()

    def assert_untouched(self):
        self.assert_failed_retryably_with_no_invoice("evt_late")
        self.assertEqual(StripeWebhookEvent.objects.filter(stripe_event_id="evt_late").count(), 1)

    def test_the_event_is_retrieved_through_stripe_call_under_the_tenants_context(self):
        from apps.billing.stripe.services.stripe_service import stripe_call
        event = self.bound_and_recorded()
        command = "apps.billing.stripe.management.commands.reprocess_webhook"
        with patch(f"{command}.stripe_call", wraps=stripe_call) as guarded:
            retrieved = self.reprocess("evt_late", retrieved=event)
        guarded.assert_called_once()
        self.assertIs(guarded.call_args.args[0], retrieved)   # the (patched) Event.retrieve
        self.assertEqual(retrieved.call_args.kwargs, {
            "api_key": "sk_test_sentinel", "id": "evt_late", "stripe_account": ACCT})
        self.assert_one_invoice_owned_by_the_business()
        self.assertEqual(StripeWebhookEvent.objects.filter(stripe_event_id="evt_late").count(), 1)

    def test_a_redelivery_winning_the_race_leaves_the_reprocess_nothing_to_do(self):
        event = self.bound_and_recorded()
        stripe_event = stripe.Event.construct_from(event, SK)

        def the_delivery_lands_first(**_kwargs):
            self.assertEqual(self.deliver(event).status_code, 200)
            return stripe_event

        self.reprocess("evt_late", side_effect=the_delivery_lands_first)
        self.assertEqual(self.row("evt_late").status, "succeeded")
        self.assertEqual(self.invoices().count(), 1)

    def test_a_redelivery_arriving_mid_reprocess_runs_nothing(self):
        """The reprocess holds the row ``processing``; a delivery meeting it
        is answered as a duplicate by the receiver's existing semantics (a
        fresh ``processing`` row is not re-claimable) and runs no handler."""
        import api.v1.webhooks as billing_webhooks
        event = self.bound_and_recorded()
        reconcile = billing_webhooks._reconcile_customer_invoice
        answers = []

        def a_delivery_arrives_while_the_handler_runs(*args, **kwargs):
            if not answers:
                answers.append(json.loads(self.deliver(event).content))
            return reconcile(*args, **kwargs)

        with patch.object(billing_webhooks, "_reconcile_customer_invoice",
                          side_effect=a_delivery_arrives_while_the_handler_runs):
            self.reprocess("evt_late", retrieved=event)
        self.assertEqual(answers, [{"status": "already_processed"}])
        self.assertEqual(self.row("evt_late").status, "succeeded")
        self.assertEqual(self.invoices().count(), 1)

    def test_a_tenant_on_another_account_is_refused_without_processing(self):
        event = self.bound_and_recorded()
        elsewhere = Tenant.objects.create(
            name="Elsewhere", products=["metering", "billing"],
            stripe_connected_account_id="acct_elsewhere", charges_enabled=True)
        with self.assertRaisesMessage(CommandError, "disagrees"):
            self.reprocess("evt_late", elsewhere, retrieved=event)
        self.assert_untouched()

    def test_a_tenant_in_the_other_mode_is_refused_without_processing(self):
        from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
        event = self.bound_and_recorded()
        sandbox = get_or_create_sandbox(self.tenant)
        Tenant.objects.filter(id=sandbox.id).update(stripe_connected_account_id=ACCT)
        sandbox.refresh_from_db()
        with self.settings(STRIPE_TEST_SECRET_KEY="sk_test_sentinel"), \
                self.assertRaisesMessage(CommandError, "livemode"):
            self.reprocess("evt_late", sandbox, retrieved=event)
        self.assert_untouched()

    def test_an_event_of_another_type_or_id_is_refused(self):
        event = self.bound_and_recorded()
        for name, wrong in (("type", {**event, "type": "invoice.voided"}),
                            ("id", {**event, "id": "evt_somebody_else"})):
            with self.subTest(name), self.assertRaisesMessage(CommandError, name):
                self.reprocess("evt_late", retrieved=wrong)
        self.assert_untouched()

    def test_a_missing_stripe_key_is_refused_before_transport(self):
        self.bound_and_recorded()
        with self.settings(STRIPE_SECRET_KEY=""), patch("stripe.Event.retrieve") as retrieved, \
                self.assertRaisesMessage(CommandError, "refused before any request"):
            call_command("reprocess_webhook", "evt_late", receiver="billing",
                         tenant=str(self.tenant.id))
        retrieved.assert_not_called()
        self.assert_untouched()

    def test_an_event_stripe_cannot_return_invents_nothing(self):
        self.bound_and_recorded()
        for error in (stripe.error.InvalidRequestError("No such event: 'evt_late'", "id"),
                      stripe.error.APIConnectionError("network down")):
            with self.subTest(type(error).__name__), \
                    patch("apps.billing.stripe.services.stripe_service._backoff"), \
                    self.assertRaisesMessage(CommandError, "Stripe did not return event"):
                self.reprocess("evt_late", side_effect=error)
        self.assert_untouched()

    def test_a_non_retryable_failure_is_not_run_again(self):
        self.bound_and_recorded()
        StripeWebhookEvent.objects.filter(stripe_event_id="evt_late").update(
            failure_reason={"error": "refused", "type": "StripeFatalError", "retryable": False})
        with patch("stripe.Event.retrieve") as retrieved, \
                self.assertRaisesMessage(CommandError, "NON-retryably"):
            call_command("reprocess_webhook", "evt_late", receiver="billing",
                         tenant=str(self.tenant.id))
        retrieved.assert_not_called()
        self.assertFalse(self.invoices().exists())


class AUbbCreatedSubscriptionKeepsItsOwnerTest(TestCase):
    """(2) UBB opens a subscription for ``biz``; ``other`` holds the same
    Stripe customer id and is the holder the anchor's sync chose (created
    later, larger external id). The binding stays ``biz`` through the hourly
    sync, and the invoice freezes ``biz`` as its owner (probes D1-D3)."""

    def test_the_explicit_owner_is_bound_kept_and_frozen_on_the_invoice(self):
        from apps.subscriptions.orchestration.service import SubscriptionOrchestrator
        from apps.subscriptions.stripe.sync import sync_subscriptions

        tenant = Tenant.objects.create(
            name="T", products=["metering", "billing"],
            stripe_connected_account_id=ACCT, charges_enabled=True)
        biz = Customer.objects.create(tenant=tenant, external_id="biz",
                                      stripe_customer_id="cus_shared")
        Customer.objects.create(tenant=tenant, external_id="other",
                                stripe_customer_id="cus_shared")
        plan = a_plan(tenant=tenant, key="pro", name="Pro", access_fee_micros=49_000_000,
                      interval="month", stripe_access_price_id="price_4900",
                      provisioned_at=timezone.now())
        opened = a_stripe_subscription("sub_ubb", "cus_shared", "active",
                                       items=[a_licensed_item(4900, item_id="si_ubb")])
        with patch("apps.subscriptions.orchestration.service.stripe.Subscription.create",
                   return_value=opened):
            SubscriptionOrchestrator.subscribe(biz, plan, 1)
        mirror = StripeSubscription.objects.get(stripe_subscription_id="sub_ubb")
        self.assertEqual((mirror.customer_id, mirror.tenant_id), (biz.id, tenant.id))

        page = stripe.ListObject.construct_from(
            {"object": "list", "has_more": False, "url": "/v1/subscriptions",
             "data": [a_subscription_dict("sub_ubb", "cus_shared", "active",
                                          items=[a_licensed_item(4900, product_name="Pro")])]},
            SK)
        with patch("apps.subscriptions.stripe.sync.stripe.Subscription.list", return_value=page):
            self.assertEqual(sync_subscriptions(tenant)["synced"], 1)
        mirror.refresh_from_db()
        self.assertEqual(mirror.customer_id, biz.id)

        from api.v1.webhooks import handle_invoice_finalized
        handle_invoice_finalized(stripe.Event.construct_from(
            _invoice_event("evt_ubb", "in_ubb", "sub_ubb"), SK))
        invoice = SubscriptionInvoice.objects.get(stripe_invoice_id="in_ubb")
        self.assertEqual((invoice.customer_id, invoice.billing_owner_id), (biz.id, biz.id))
