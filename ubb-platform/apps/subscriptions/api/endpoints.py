import logging
from datetime import timedelta

import stripe
from stripe import SignatureVerificationError as StripeSignatureError

from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist
from django.db import IntegrityError, transaction
from django.db.models import F
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ninja import NinjaAPI

from apps.billing.stripe.models import StripeWebhookEvent
from core.exceptions import StripeFatalError

from core.pagination import apply_cursor_filter, encode_cursor
from apps.platform.customers.models import Customer
from apps.subscriptions.api.schemas import (
    SyncResponse,
    StripeSubscriptionOut,
    PaginatedInvoicesResponse,
    SubscriptionInvoiceOut,
)
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from core.auth import ApiKeyAuth, ProductAccess

subscriptions_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_subscriptions_v1")

_product_check = ProductAccess("subscriptions")


# ---------- Sync ----------


@subscriptions_api.post("/sync", response=SyncResponse)
def trigger_sync(request):
    _product_check(request)
    from apps.subscriptions.stripe.sync import sync_subscriptions

    result = sync_subscriptions(request.auth.tenant)
    return result


# ---------- Subscription Data (read-only) ----------


@subscriptions_api.get("/customers/{customer_id}/subscription")
def get_subscription(request, customer_id: str):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    sub = StripeSubscription.objects.filter(
        tenant=tenant, customer=customer,
    ).order_by("-created_at").first()

    if not sub:
        return subscriptions_api.create_response(
            request, {"error": "No subscription found"}, status=404
        )

    return {
        "id": str(sub.id),
        "stripe_subscription_id": sub.stripe_subscription_id,
        "stripe_product_name": sub.stripe_product_name,
        "status": sub.status,
        "amount_micros": sub.amount_micros,
        "currency": sub.currency,
        "interval": sub.interval,
        "current_period_start": sub.current_period_start.isoformat(),
        "current_period_end": sub.current_period_end.isoformat(),
        "last_synced_at": sub.last_synced_at.isoformat(),
    }


@subscriptions_api.get("/customers/{customer_id}/invoices")
def get_invoices(request, customer_id: str, cursor: str = None, limit: int = 50):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)
    limit = min(max(limit, 1), 100)

    # Only paid invoices surface here (this is the revenue listing). Since the AR
    # reconcile now also persists open/void/uncollectible rows with a NULL paid_at,
    # exclude them — they have no paid_at to order/serialize on.
    qs = SubscriptionInvoice.objects.filter(
        tenant=tenant, customer=customer, paid_at__isnull=False,
    ).order_by("-paid_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="paid_at")
        except ValueError:
            from ninja.errors import HttpError

            raise HttpError(400, "Invalid cursor")

    invoices = list(qs[: limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.paid_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "amount_paid_micros": inv.amount_paid_micros,
                "currency": inv.currency,
                "period_start": inv.period_start.isoformat(),
                "period_end": inv.period_end.isoformat(),
                "paid_at": inv.paid_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


# ---------- Stripe Webhook ----------

logger = logging.getLogger(__name__)

from apps.subscriptions.api.webhooks import (
    handle_subscription_created,
    handle_subscription_updated,
    handle_subscription_deleted,
)

# This endpoint handles customer.subscription.* ONLY. ALL invoice.* reconcile
# (including subscription-invoice status) lives on api/v1 — see api/v1/webhooks.py.
# Never register an invoice.* type here: both endpoints share the
# StripeWebhookEvent dedup table, so the first to handle an event wins the dedup
# row and the second silently skips (C-1).
SUBSCRIPTIONS_WEBHOOK_HANDLERS = {
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
}

PROCESSING_TTL_MINUTES = 30


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook(request):
    """Stripe webhook endpoint for subscription events.

    This is the authoritative seat-quantity confirm path for Wave-4 orchestration,
    so it must process each Stripe event at most once. Deduplication mirrors the
    api/v1 webhook: StripeWebhookEvent get_or_create + IntegrityError fallback +
    CAS-guarded retry of retryable failures / stale processing.
    """
    secret = (
        settings.STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET
        if hasattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET")
        else settings.STRIPE_WEBHOOK_SECRET
    )
    return _subscriptions_stripe_webhook(request, secret=secret, is_test_endpoint=False)


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook_test(request):
    """Stripe TEST-mode subscriptions webhook (F4.4) — sandbox tenants' events.

    Verified with STRIPE_TEST_WEBHOOK_SECRET; 400 when that secret is unset or
    the event is livemode=True. Same handlers — the livemode filters inside
    them bind every lookup to sandbox tenants.
    """
    if not settings.STRIPE_TEST_WEBHOOK_SECRET:
        return HttpResponse(status=400)
    return _subscriptions_stripe_webhook(
        request, secret=settings.STRIPE_TEST_WEBHOOK_SECRET, is_test_endpoint=True)


def _subscriptions_stripe_webhook(request, *, secret, is_test_endpoint):
    from apps.billing.connectors.stripe.invoice_routing import reject_for_mode

    # 1. Verify signature
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, secret)
    except (ValueError, StripeSignatureError):
        return HttpResponse(status=400)

    # 1b. Mode gate (F4.4) — same policy as the api/v1 endpoint.
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
    handler = SUBSCRIPTIONS_WEBHOOK_HANDLERS.get(event.type)
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
            "Subscriptions webhook handler ObjectDoesNotExist (likely out-of-order)",
            extra={"data": {"event_id": event.id, "event_type": event.type, "error": str(e)}},
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
            "Subscriptions webhook handler fatal error",
            extra={"data": {"event_id": event.id, "event_type": event.type, "error": str(e)}},
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
            "Subscriptions webhook handler failed",
            extra={"data": {"event_id": event.id, "event_type": event.type}},
        )
        webhook_event.status = "failed"
        webhook_event.failure_reason = {
            "error": str(e), "type": type(e).__name__, "retryable": True
        }
        webhook_event.processed_at = timezone.now()
        webhook_event.save(update_fields=["status", "failure_reason", "processed_at", "updated_at"])
        return HttpResponse(status=500)  # Stripe retries

    return JsonResponse({"status": "ok"})
