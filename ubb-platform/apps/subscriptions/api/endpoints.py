import logging

import stripe
from stripe import SignatureVerificationError as StripeSignatureError
from datetime import date
from decimal import Decimal

from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from ninja import NinjaAPI

from api.v1.pagination import apply_cursor_filter, encode_cursor
from apps.platform.customers.models import Customer
from apps.subscriptions.api.schemas import (
    SyncResponse,
    StripeSubscriptionOut,
    CustomerEconomicsOut,
    EconomicsListResponse,
    EconomicsSummaryResponse,
    PaginatedInvoicesResponse,
    SubscriptionInvoiceOut,
)
from apps.subscriptions.economics.services import EconomicsService
from apps.subscriptions.models import StripeSubscription, SubscriptionInvoice
from core.auth import ApiKeyAuth, ProductAccess

subscriptions_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_subscriptions_v1")

_product_check = ProductAccess("subscriptions")


def _current_period():
    """Return (period_start, period_end) for the current calendar month."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    if today.month == 12:
        first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_of_next_month = today.replace(month=today.month + 1, day=1)
    return first_of_month, first_of_next_month


# ---------- Sync ----------


@subscriptions_api.post("/sync", response=SyncResponse)
def trigger_sync(request):
    _product_check(request)
    from apps.subscriptions.stripe.sync import sync_subscriptions

    result = sync_subscriptions(request.auth.tenant)
    return result


# ---------- Unit Economics ----------

# IMPORTANT: /economics/summary MUST be registered before /economics/{customer_id}
# so that django-ninja does not interpret "summary" as a customer_id parameter.


@subscriptions_api.get("/economics/summary")
def get_economics_summary(request, period_start: date = None, period_end: date = None):
    _product_check(request)
    tenant = request.auth.tenant

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    results = EconomicsService.calculate_all_economics(
        tenant.id, period_start, period_end,
    )

    total_revenue = sum(r.subscription_revenue_micros for r in results)
    total_cost = sum(r.usage_cost_micros for r in results)
    total_margin = total_revenue - total_cost
    avg_margin = (
        float(Decimal(total_margin) / Decimal(total_revenue) * 100)
        if total_revenue > 0
        else 0.0
    )
    unprofitable = sum(1 for r in results if r.gross_margin_micros < 0)

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "total_revenue_micros": total_revenue,
        "total_cost_micros": total_cost,
        "total_margin_micros": total_margin,
        "avg_margin_percentage": round(avg_margin, 2),
        "unprofitable_customers": unprofitable,
        "total_customers": len(results),
    }


@subscriptions_api.get("/economics")
def list_economics(request, period_start: date = None, period_end: date = None):
    _product_check(request)
    tenant = request.auth.tenant

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    results = EconomicsService.calculate_all_economics(
        tenant.id, period_start, period_end,
    )

    customers_out = []
    for econ in results:
        customer = Customer.objects.get(id=econ.customer_id)
        sub = StripeSubscription.objects.filter(
            tenant=tenant, customer=customer, status="active",
        ).first()
        plan_name = sub.stripe_product_name if sub else "Unknown"

        customers_out.append(
            {
                "customer_id": str(customer.id),
                "external_id": customer.external_id,
                "plan": plan_name,
                "subscription_revenue_micros": econ.subscription_revenue_micros,
                "usage_cost_micros": econ.usage_cost_micros,
                "gross_margin_micros": econ.gross_margin_micros,
                "margin_percentage": float(econ.margin_percentage),
            }
        )

    total_revenue = sum(c["subscription_revenue_micros"] for c in customers_out)
    total_cost = sum(c["usage_cost_micros"] for c in customers_out)
    total_margin = total_revenue - total_cost
    avg_margin = (
        float(Decimal(total_margin) / Decimal(total_revenue) * 100)
        if total_revenue > 0
        else 0.0
    )
    unprofitable = sum(1 for c in customers_out if c["gross_margin_micros"] < 0)

    return {
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "customers": customers_out,
        "summary": {
            "total_revenue_micros": total_revenue,
            "total_cost_micros": total_cost,
            "total_margin_micros": total_margin,
            "avg_margin_percentage": round(avg_margin, 2),
            "unprofitable_customers": unprofitable,
        },
    }


@subscriptions_api.get("/economics/{customer_id}")
def get_customer_economics(
    request,
    customer_id: str,
    period_start: date = None,
    period_end: date = None,
):
    _product_check(request)
    tenant = request.auth.tenant
    customer = get_object_or_404(Customer, id=customer_id, tenant=tenant)

    if period_start is None or period_end is None:
        period_start, period_end = _current_period()

    econ = EconomicsService.calculate_customer_economics(
        tenant.id, customer.id, period_start, period_end,
    )

    sub = StripeSubscription.objects.filter(
        tenant=tenant, customer=customer, status="active",
    ).first()
    plan_name = sub.stripe_product_name if sub else "Unknown"

    return {
        "customer_id": str(customer.id),
        "external_id": customer.external_id,
        "plan": plan_name,
        "period": {"start": period_start.isoformat(), "end": period_end.isoformat()},
        "subscription_revenue_micros": econ.subscription_revenue_micros,
        "usage_cost_micros": econ.usage_cost_micros,
        "gross_margin_micros": econ.gross_margin_micros,
        "margin_percentage": float(econ.margin_percentage),
    }


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
