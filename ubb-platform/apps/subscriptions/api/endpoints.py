import logging

import stripe
from stripe import SignatureVerificationError as StripeSignatureError

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ninja import NinjaAPI

from api.v1.pagination import apply_cursor_filter, encode_cursor
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

    qs = SubscriptionInvoice.objects.filter(
        tenant=tenant, customer=customer,
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
    handle_invoice_paid,
)

SUBSCRIPTIONS_WEBHOOK_HANDLERS = {
    "customer.subscription.created": handle_subscription_created,
    "customer.subscription.updated": handle_subscription_updated,
    "customer.subscription.deleted": handle_subscription_deleted,
    "invoice.paid": handle_invoice_paid,
}


@csrf_exempt
@require_POST
def subscriptions_stripe_webhook(request):
    """Stripe webhook endpoint for subscription events."""
    payload = request.body
    sig_header = request.META.get("HTTP_STRIPE_SIGNATURE", "")

    try:
        event = stripe.Webhook.construct_event(
            payload,
            sig_header,
            settings.STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET
            if hasattr(settings, "STRIPE_SUBSCRIPTIONS_WEBHOOK_SECRET")
            else settings.STRIPE_WEBHOOK_SECRET,
        )
    except (ValueError, StripeSignatureError):
        return HttpResponse(status=400)

    handler = SUBSCRIPTIONS_WEBHOOK_HANDLERS.get(event.type)
    if not handler:
        return JsonResponse({"status": "ok"})

    try:
        handler(event)
    except Exception:
        logger.exception(
            "Subscriptions webhook handler failed",
            extra={"data": {"event_id": event.id, "event_type": event.type}},
        )
        return HttpResponse(status=500)

    return JsonResponse({"status": "ok"})
