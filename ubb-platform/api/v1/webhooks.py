import logging
from datetime import timedelta

import stripe
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse, HttpResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from apps.billing.invoicing.models import Invoice
from apps.billing.stripe.models import StripeWebhookEvent
from core.exceptions import StripeFatalError
from apps.billing.locking import lock_invoice

from apps.billing.connectors.stripe.webhooks import (
    handle_checkout_completed,
    handle_charge_dispute_created,
    handle_charge_dispute_closed,
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
)

logger = logging.getLogger(__name__)

PROCESSING_TTL_MINUTES = 30


@csrf_exempt
@require_POST
def stripe_webhook(request):
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
    if not settings.STRIPE_TEST_WEBHOOK_SECRET:
        return HttpResponse(status=400)
    return _stripe_webhook(
        request, secret=settings.STRIPE_TEST_WEBHOOK_SECRET, is_test_endpoint=True)


def _stripe_webhook(request, *, secret, is_test_endpoint):
    # 1. Verify signature
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)

    # 1b. Mode gate (F4.4): test endpoint = test events only; live endpoint
    # rejects test events once the test secret (= sandbox infra) exists.
    if reject_for_mode(event, is_test_endpoint=is_test_endpoint):
        return HttpResponse(status=400)

    # 2. Event-level dedup with IntegrityError handling
    try:
        with transaction.atomic():
            webhook_event, created = StripeWebhookEvent.objects.get_or_create(
                stripe_event_id=event.id,
                defaults={"event_type": event.type, "status": "processing"},
            )
    except IntegrityError:
        StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
            duplicate_count=F("duplicate_count") + 1,
            last_seen_at=timezone.now(),
            updated_at=timezone.now(),
        )
        return JsonResponse({"status": "already_received"})

    if not created:
        processing_ttl = timezone.now() - timedelta(minutes=PROCESSING_TTL_MINUTES)

        # CAS: allow retry of retryable failures or stale processing
        if (
            (webhook_event.status == "failed"
             and webhook_event.failure_reason
             and webhook_event.failure_reason.get("retryable") is True)
            or (webhook_event.status == "processing"
                and webhook_event.updated_at < processing_ttl)
        ):
            rows_updated = StripeWebhookEvent.objects.filter(
                id=webhook_event.id,
                status=webhook_event.status,
                updated_at=webhook_event.updated_at,
            ).update(
                status="processing",
                failure_reason=None,
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            if rows_updated == 0:
                return JsonResponse({"status": "already_processing"})
            # Won CAS — fall through to handler
        else:
            StripeWebhookEvent.objects.filter(stripe_event_id=event.id).update(
                duplicate_count=F("duplicate_count") + 1,
                last_seen_at=timezone.now(),
                updated_at=timezone.now(),
            )
            return JsonResponse({"status": "already_processed"})

    # 3. Dispatch
    handler = WEBHOOK_HANDLERS.get(event.type)
    if not handler:
        webhook_event.status = "skipped"
        webhook_event.save(update_fields=["status", "updated_at"])
        return JsonResponse({"status": "ok"})

    # 4. Execute with error classification
    try:
        handler(event)
        webhook_event.status = "succeeded"
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "processed_at", "updated_at"])
    except ObjectDoesNotExist as e:
        logger.warning(
            "Webhook handler ObjectDoesNotExist (likely out-of-order)",
            extra={"data": {"event_id": event.id, "error": str(e)}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries
    except StripeFatalError as e:
        logger.error(
            "Webhook handler fatal error",
            extra={"data": {"event_id": event.id, "error": str(e)}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": False
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return JsonResponse({"status": "failed"})  # 200 — no Stripe retry
    except Exception as e:
        logger.exception(
            "Webhook handler transient error",
            extra={"data": {"event_id": event.id}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries

    return JsonResponse({"status": "ok"})


# --- AR payment-status reconcile (Wave-5a) ---------------------------------
# ALL invoice.* reconcile lives here; the subscriptions endpoint handles
# customer.subscription.* only — never register an invoice.* type on both
# (they share the StripeWebhookEvent dedup table, so a double-registration would
# let the first endpoint win the dedup row and the second silently skip).
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
        with transaction.atomic():
            row, _created = SubscriptionInvoice.objects.select_for_update().get_or_create(
                stripe_invoice_id=inv.id,
                defaults={
                    "tenant": sub.tenant,
                    "customer": sub.customer,
                    "stripe_subscription": sub,
                    "amount_paid_micros": (getattr(inv, "amount_paid", 0) or 0) * 10_000,
                    "currency": getattr(inv, "currency", "usd"),
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
                row.amount_paid_micros = (getattr(inv, "amount_paid", 0) or 0) * 10_000
            _refresh_urls(row, inv)
            row.save()
    else:
        existing = CustomerUsageInvoice.objects.filter(
            stripe_invoice_id=inv.id,
            tenant__stripe_connected_account_id=acct,
            **livemode_filter(event),
        ).first()
        if not existing:
            return
        with transaction.atomic():
            row = CustomerUsageInvoice.objects.select_for_update().get(id=existing.id)
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
            _refresh_urls(row, inv)
            row.save()


def handle_invoice_finalized(event):
    """invoice.finalized — mark the customer invoice open + store hosted url/pdf."""
    _reconcile_customer_invoice(event, new_status="open")


def handle_invoice_voided(event):
    """invoice.voided — mark the customer invoice void."""
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
            if tenant_invoice.status == "paid":
                return
            tenant_invoice.status = "paid"
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
    "payment_intent.succeeded": handle_payment_intent_succeeded,
    "payment_intent.payment_failed": handle_payment_intent_payment_failed,
}
