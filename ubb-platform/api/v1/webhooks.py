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

from apps.platform.customers.models import Customer, TopUpAttempt
from apps.metering.usage.models import Invoice
from apps.stripe_integration.models import StripeWebhookEvent
from core.exceptions import StripeFatalError
from core.locking import lock_for_billing, lock_customer, lock_invoice, lock_top_up_attempt

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


def handle_checkout_completed(event):
    """Handle checkout.session.completed — credit wallet for top-up."""
    session = event.data.object
    if session.payment_status != "paid":
        return

    connected_account = event.account
    customer = Customer.objects.filter(
        stripe_customer_id=session.customer,
        tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not customer:
        return

    # Correlate with TopUpAttempt via client_reference_id
    attempt = None
    if session.client_reference_id:
        try:
            attempt = TopUpAttempt.objects.get(id=session.client_reference_id)
        except TopUpAttempt.DoesNotExist:
            logger.warning(
                "TopUpAttempt not found for checkout session",
                extra={"data": {"client_reference_id": session.client_reference_id}},
            )

    # Handler-level idempotency: check attempt status if present
    if attempt and attempt.status != "pending":
        if not (attempt.status == "expired" and attempt.trigger == "manual"):
            return

    amount_micros = session.amount_total * 10_000

    with transaction.atomic():
        wallet, customer = lock_for_billing(customer.id)

        # Re-check attempt status under lock
        if attempt:
            attempt = lock_top_up_attempt(attempt.id)
            if attempt.status != "pending":
                if not (attempt.status == "expired" and attempt.trigger == "manual"):
                    return
            if attempt.status == "expired":
                logger.info(
                    "Recovering expired manual top-up from webhook",
                    extra={"data": {"attempt_id": str(attempt.id), "session_id": session.id}},
                )
            attempt.status = "succeeded"
            attempt.stripe_checkout_session_id = session.id
            attempt.save(update_fields=["status", "stripe_checkout_session_id", "updated_at"])

        wallet.balance_micros += amount_micros
        wallet.save(update_fields=["balance_micros", "updated_at"])

        from apps.platform.customers.models import WalletTransaction
        WalletTransaction.objects.create(
            wallet=wallet,
            transaction_type="TOP_UP",
            amount_micros=amount_micros,
            balance_after_micros=wallet.balance_micros,
            description="Stripe top-up",
            reference_id=str(attempt.id) if attempt else "",
        )

    # Generate receipt invoice (after commit)
    if attempt:
        transaction.on_commit(lambda: _dispatch_receipt(customer.id, attempt.id))


def _dispatch_receipt(customer_id, attempt_id):
    from apps.platform.customers.models import Customer, TopUpAttempt
    from apps.invoicing.services import ReceiptService
    try:
        customer = Customer.objects.select_related("tenant").get(id=customer_id)
        attempt = TopUpAttempt.objects.get(id=attempt_id)
        ReceiptService.create_topup_receipt(customer, attempt)
    except Exception:
        logger.exception(
            "Failed to generate top-up receipt",
            extra={"data": {"customer_id": str(customer_id), "attempt_id": str(attempt_id)}},
        )


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
        from apps.tenant_billing.models import TenantInvoice
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

        now = timezone.now()
        TenantInvoice.objects.filter(
            id=tenant_invoice.id,
        ).exclude(status="paid").update(
            status="paid",
            paid_at=now,
            updated_at=now,
        )


def handle_invoice_payment_failed(event):
    """Handle invoice.payment_failed — suspend customer."""
    inv = event.data.object
    connected_account = event.account
    customer = Customer.objects.filter(
        stripe_customer_id=inv.customer,
        tenant__stripe_connected_account_id=connected_account,
    ).first()
    if not customer:
        return

    # Handler-level idempotency: already suspended = skip
    if customer.status == "suspended":
        return

    with transaction.atomic():
        customer = lock_customer(customer.id)
        if customer.status == "suspended":
            return
        customer.status = "suspended"
        customer.save(update_fields=["status", "updated_at"])


WEBHOOK_HANDLERS = {
    "checkout.session.completed": handle_checkout_completed,
    "invoice.paid": handle_invoice_paid,
    "invoice.payment_failed": handle_invoice_payment_failed,
}
