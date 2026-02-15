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
)

logger = logging.getLogger(__name__)

PROCESSING_TTL_MINUTES = 30


@csrf_exempt
@require_POST
def stripe_webhook(request):
    # 1. Verify signature
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    try:
        event = stripe.Webhook.construct_event(payload, sig_header, settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
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


def handle_invoice_paid(event):
    """Handle invoice.paid — mark local invoice as paid.

    Handles both:
    - End-user invoices (on connected account): matched via event.account
    - Platform fee invoices (on UBB's own account): matched when no connected account
    """
    inv = event.data.object
    connected_account = event.account

    if connected_account:
        # End-user invoice on tenant's Connected Account
        invoice = Invoice.objects.filter(
            stripe_invoice_id=inv.id,
            tenant__stripe_connected_account_id=connected_account,
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
        # Platform fee invoice on UBB's own Stripe account
        from apps.billing.tenant_billing.models import TenantInvoice
        tenant_invoice = TenantInvoice.objects.filter(
            stripe_invoice_id=inv.id,
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


WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
    "charge.dispute.created": handle_charge_dispute_created,
    "charge.dispute.closed": handle_charge_dispute_closed,
    "charge.refunded": handle_charge_refunded,
}
