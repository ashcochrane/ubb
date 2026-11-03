import logging

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import transaction
from django.http import HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.gating.services.live_counter import LiveCounter
from apps.billing.invoicing.models import Invoice
from apps.billing.stripe.models import WEBHOOK_RECEIVER_BILLING
from apps.billing.stripe.receiver import receive_stripe_event
from apps.subscriptions.stripe.items import paid_amounts
from apps.billing.locking import lock_invoice

from apps.billing.connectors.stripe.webhooks import (
    handle_checkout_completed,
    handle_charge_dispute_created,
    handle_charge_dispute_closed,
    handle_charge_refund_updated,
    handle_charge_refunded,
    handle_invoice_payment_failed,
    handle_payment_intent_succeeded,
    handle_payment_intent_payment_failed,
)
from apps.billing.connectors.stripe.invoice_routing import (  # noqa: F401
    _invoice_subscription_id,
    _refresh_urls,
    AR_ALLOWED,
    ar_transition_allowed,
    event_livemode,
    livemode_filter,
    reject_for_mode,
    settle_failure_stamp,
)
from core.vocabulary import (
    TENANT_INVOICE_STATUS_PAID,
)

logger = logging.getLogger(__name__)


@csrf_exempt
@require_POST
def stripe_webhook(request):
    """Stripe LIVE-mode webhook endpoint — the BILLING receiver.

    Fails closed, exactly as the test endpoint below does, when
    STRIPE_WEBHOOK_SECRET is unset or blank: an empty secret must never
    verify. It used to be handed straight to Stripe's verifier, which then
    accepted any event signed with the empty key — a deployment that uses no
    Stripe (an `external` tenant's) would have left the live receiver open
    (W7 preparation finding F5, ruled 2026-10-30). Refused before anything is
    verified or persisted.

    The body is the shared receiver core (`apps/billing/stripe/receiver.py`,
    C1b): deduplicated per receiver, so an event id the subscriptions
    receiver also receives is this receiver's own row here.
    """
    if not (settings.STRIPE_WEBHOOK_SECRET or "").strip():
        return HttpResponse(status=400)
    return _stripe_webhook(
        request, secret=settings.STRIPE_WEBHOOK_SECRET, is_test_endpoint=False)


@csrf_exempt
@require_POST
def stripe_webhook_test(request):
    """Stripe TEST-mode webhook endpoint (F4.4) — sandbox tenants' events.

    Verified with STRIPE_TEST_WEBHOOK_SECRET; 400 when that secret is unset
    (an empty secret must never verify) or when the event is livemode=True.
    Handlers are shared: the livemode filters inside them bind every lookup
    to sandbox tenants.
    """
    if not (settings.STRIPE_TEST_WEBHOOK_SECRET or "").strip():
        return HttpResponse(status=400)
    return _stripe_webhook(
        request, secret=settings.STRIPE_TEST_WEBHOOK_SECRET, is_test_endpoint=True)


def _stripe_webhook(request, *, secret, is_test_endpoint):
    return receive_stripe_event(
        request, receiver=WEBHOOK_RECEIVER_BILLING, handlers=WEBHOOK_HANDLERS,
        secret=secret, is_test_endpoint=is_test_endpoint,
        # This receiver moves wallet money, so the wallet boundary's refusal
        # is one of its named, non-retryable outcomes.
        refuses_without_a_wallet_subject=True)


# --- AR payment-status reconcile (Wave-5a) ---------------------------------
# ALL invoice.* reconcile lives here; the subscriptions endpoint handles
# customer.subscription.* only. Since C1b (F-17) each receiver deduplicates
# its own deliveries, so a type registered on both would be processed by
# both — keep every type on exactly one receiver's map.
#
# AR_ALLOWED, ar_transition_allowed, _refresh_urls, and _invoice_subscription_id
# are billing-domain logic; they live in
# apps/billing/connectors/stripe/invoice_routing.py and are re-exported above
# so existing call-sites (tests, etc.) can still reach them via this module.


def _unix(ts):
    from datetime import datetime, timezone as _tz
    return datetime.fromtimestamp(ts, tz=_tz.utc) if ts else None


def _reconcile_customer_invoice(event, *, new_status):
    """Reconcile a customer invoice's payment status (status only — no money movement).

    Routes by subscription presence: subscription invoices reconcile onto
    SubscriptionInvoice, standalone usage invoices onto CustomerUsageInvoice.
    Every match is account-checked (C-2): the matched row's tenant
    stripe_connected_account_id must equal event.account. Status follows the
    Stripe-legal transition table (AR_ALLOWED): paid/void are final, but
    uncollectible remains payable and voidable — a late invoice.paid applies.
    """
    from apps.billing.invoicing.models import CustomerUsageInvoice
    from apps.subscriptions.models import SubscriptionInvoice, StripeSubscription

    inv = event.data.object
    acct = event.account
    if not acct:
        return
    sub_id = _invoice_subscription_id(inv)
    if sub_id:
        sub = StripeSubscription.objects.filter(
            stripe_subscription_id=sub_id,
            tenant__stripe_connected_account_id=acct,
            **livemode_filter(event),
        ).first()
        if not sub:
            return
        # What Stripe sent, kept exactly — its integer and its currency — and
        # an amount in UBB's one currency only where the policy admits it
        # (#564). A connected account may hold a subscription in a currency UBB
        # never admitted: that invoice is QUARANTINED, never scaled by the
        # tenant's minor unit and never relabelled. Keyed on the Stripe id, so
        # a retried event and the poller's repair both meet this one row.
        currency, paid_minor, paid_micros = paid_amounts(inv)
        with transaction.atomic():
            row, _created = SubscriptionInvoice.objects.select_for_update().get_or_create(
                stripe_invoice_id=inv.id,
                defaults={
                    "tenant": sub.tenant,
                    "customer": sub.customer,
                    # THE HISTORICAL BILLING OWNER (R10 Stage C2, PLAN §7 item
                    # 27): resolved ONCE, here, as the invoice first enters UBB
                    # — a callable, so only a row actually being created asks
                    # — and never again: a replay, the sync, a settlement or a
                    # topology change leaves an existing row's owner as it was.
                    "billing_owner": lambda: sub.customer.resolve_billing_owner(),
                    "stripe_subscription": sub,
                    "amount_paid_micros": paid_micros,
                    "source_amount_paid_minor": paid_minor,
                    "currency": currency,
                    "status": new_status,
                    "period_start": _unix(getattr(inv, "period_start", None)),
                    "period_end": _unix(getattr(inv, "period_end", None)),
                },
            )
            if ar_transition_allowed(row.status, new_status):
                row.status = new_status
            elif not _created and new_status != row.status:
                logger.warning("ar.transition_ignored", extra={"data": {
                    "subscription_invoice_id": str(row.id),
                    "stripe_invoice_id": inv.id,
                    "old_status": row.status, "new_status": new_status}})
            # Money fields gate on the APPLIED state (not the event), so a
            # refused transition (e.g. void + late invoice.paid) never leaves
            # paid_at on a non-paid row; the born-paid get_or_create row
            # (row.status == "paid", paid_at unset) is still covered.
            if row.status == "paid" and not row.paid_at:
                st = getattr(inv, "status_transitions", None)
                row.paid_at = _unix(getattr(st, "paid_at", None)) or timezone.now()
                row.currency = currency
                row.amount_paid_micros = paid_micros
                row.source_amount_paid_minor = paid_minor
            # R10 Stage C2 (F-6, §7 items 26-27): a paid or voided subscription
            # invoice clears ITS failure stamp, and billing re-decides its
            # HISTORICAL owner — never one re-derived from today's topology.
            settled_owner_id = (row.billing_owner_id
                                if settle_failure_stamp(row, row.status) else None)
            _refresh_urls(row, inv)
            row.save()
        if settled_owner_id is not None:
            LiveCounter.clear_payment_failed_suspension(settled_owner_id)
        # F5.5: a CONSOLIDATED usage rec rides this subscription invoice — its
        # payment status follows the same event along the same table. Only a
        # recorded ('pushed') row is repaired: a mid-split push may still
        # repoint its stripe_invoice_id to the remainder invoice it actually
        # bills on, so an unrecorded pointer is not yet authoritative.
        consolidated_row = CustomerUsageInvoice.objects.filter(
            stripe_invoice_id=inv.id, invoice_kind="consolidated", status="pushed",
            tenant__stripe_connected_account_id=acct,
            **livemode_filter(event),
        ).first()
        if consolidated_row:
            _apply_usage_invoice_status(consolidated_row.id, inv, new_status)
    else:
        existing = CustomerUsageInvoice.objects.filter(
            stripe_invoice_id=inv.id,
            tenant__stripe_connected_account_id=acct,
            **livemode_filter(event),
        ).first()
        if not existing:
            return
        _apply_usage_invoice_status(existing.id, inv, new_status)


def _apply_usage_invoice_status(row_id, inv, new_status):
    """Apply a Stripe-reported payment status to one CustomerUsageInvoice along
    the Stripe-legal transition table. Shared by the standalone usage branch and
    the F5.5 consolidated extension so the two can never diverge."""
    from apps.billing.invoicing.models import CustomerUsageInvoice

    with transaction.atomic():
        row = CustomerUsageInvoice.objects.select_for_update().get(id=row_id)
        if ar_transition_allowed(row.payment_status, new_status):
            row.payment_status = new_status
        elif new_status != row.payment_status:
            logger.warning("ar.transition_ignored", extra={"data": {
                "usage_invoice_id": str(row.id),
                "stripe_invoice_id": inv.id,
                "old_status": row.payment_status, "new_status": new_status}})
        # Money fields gate on the APPLIED state (see subscription branch).
        if row.payment_status == "paid" and not row.paid_at:
            row.paid_at = timezone.now()
        # R10 Stage C2 (F-6, §7 items 26-27): a paid or voided invoice clears
        # ITS failure stamp, and billing re-decides its HISTORICAL owner — a
        # usage invoice's own `customer`, the owner it was issued to (I5).
        settled_owner_id = (row.customer_id
                            if settle_failure_stamp(row, row.payment_status) else None)
        _refresh_urls(row, inv)
        row.save()
    if settled_owner_id is not None:
        LiveCounter.clear_payment_failed_suspension(settled_owner_id)


def handle_invoice_finalized(event):
    """invoice.finalized — mark the customer invoice open + store hosted url/pdf."""
    _reconcile_customer_invoice(event, new_status="open")


def handle_invoice_voided(event):
    """invoice.voided — mark the customer invoice void. A voided invoice that
    carried a payment-failure stamp is a resolved AR condition (R10 Stage C2,
    PLAN §7 item 26 — not economically paid): its stamp is settled and billing
    re-decides the owner's `payment_failed` suspension, exactly as on paid."""
    _reconcile_customer_invoice(event, new_status="void")


def handle_invoice_uncollectible(event):
    """invoice.marked_uncollectible — mark the customer invoice uncollectible."""
    _reconcile_customer_invoice(event, new_status="uncollectible")


def handle_invoice_paid(event):
    """Handle invoice.paid — mark local invoice as paid.

    Handles three things:
    - Customer-invoice AR reconcile (usage/subscription payment_status -> paid)
    - End-user top-up receipt invoices (on connected account): matched via event.account
    - Platform fee invoices (on UBB's own account): matched when no connected account
    """
    inv = event.data.object
    connected_account = event.account

    # Customer-invoice AR reconcile runs first and always for connected-account
    # events; it targets CustomerUsageInvoice / SubscriptionInvoice — a different
    # table from the top-up Invoice / TenantInvoice reconcile below, so both run.
    if connected_account:
        _reconcile_customer_invoice(event, new_status="paid")

    if connected_account:
        # End-user invoice on tenant's Connected Account
        invoice = Invoice.objects.filter(
            stripe_invoice_id=inv.id,
            tenant__stripe_connected_account_id=connected_account,
            **livemode_filter(event),
        ).first()
        if not invoice:
            return

        if invoice.status == "paid":
            return

        with transaction.atomic():
            invoice = lock_invoice(invoice.id)
            if invoice.status == "paid":
                return
            invoice.status = "paid"
            invoice.paid_at = timezone.now()
            invoice.save(update_fields=["status", "paid_at", "updated_at"])
    else:
        # Platform fee invoice on UBB's own Stripe account. Sandbox tenants are
        # never platform-invoiced, but the livemode bind costs nothing and keeps
        # a test-mode invoice id from ever matching a live TenantInvoice.
        from apps.billing.tenant_billing.models import TenantInvoice
        tenant_invoice = TenantInvoice.objects.filter(
            stripe_invoice_id=inv.id,
            **livemode_filter(event),
        ).first()
        if not tenant_invoice:
            # TenantInvoice may not be persisted yet — raise to trigger Stripe retry
            raise ObjectDoesNotExist(
                f"TenantInvoice not found for stripe_invoice_id={inv.id}"
            )

        if tenant_invoice.status == "paid":
            return

        with transaction.atomic():
            tenant_invoice = TenantInvoice.objects.select_for_update().get(
                id=tenant_invoice.id,
            )
            if tenant_invoice.status == TENANT_INVOICE_STATUS_PAID:
                return
            tenant_invoice.status = TENANT_INVOICE_STATUS_PAID
            tenant_invoice.paid_at = timezone.now()
            tenant_invoice.save(update_fields=["status", "paid_at", "updated_at"])


def handle_account_updated(event):
    """Handle account.updated — sync the connected account's charges_enabled.

    The Connect account arrives in event.data.object (with .id + .charges_enabled).
    """
    from apps.platform.tenants.models import Tenant
    acct = event.data.object
    # F4.4: the SAME acct_ id exists in test and live mode — livemode picks
    # which sibling (live tenant vs sandbox) this event may touch.
    t = Tenant.objects.filter(
        stripe_connected_account_id=acct.id,
        **livemode_filter(event, tenant_path=""),
    ).first()
    if t:
        t.charges_enabled = bool(getattr(acct, "charges_enabled", False))
        t.save(update_fields=["charges_enabled", "updated_at"])


def handle_account_deauthorized(event):
    """Handle account.application.deauthorized — clear the connected account.

    The deauthorized connected account is carried in event.account.
    """
    from apps.platform.tenants.models import Tenant
    t = Tenant.objects.filter(
        stripe_connected_account_id=event.account,
        **livemode_filter(event, tenant_path=""),
    ).first()
    if t:
        t.stripe_connected_account_id = ""
        t.charges_enabled = False
        t.save(update_fields=["stripe_connected_account_id", "charges_enabled", "updated_at"])


WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "account.updated": handle_account_updated,
    "account.application.deauthorized": handle_account_deauthorized,
    "invoice.paid": handle_invoice_paid,
    "invoice.finalized": handle_invoice_finalized,
    "invoice.voided": handle_invoice_voided,
    "invoice.marked_uncollectible": handle_invoice_uncollectible,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "charge.dispute.created": handle_charge_dispute_created,
    "charge.dispute.closed": handle_charge_dispute_closed,
    "charge.refunded": handle_charge_refunded,
    # Alert-only (C1b, RULED Q19): a refund that later fails or is cancelled
    # is detected and reported; the wallet is never moved by it.
    "charge.refund.updated": handle_charge_refund_updated,
    "payment_intent.succeeded": handle_payment_intent_succeeded,
    "payment_intent.payment_failed": handle_payment_intent_payment_failed,
}
