from datetime import date
from typing import Optional

from django.db.models import Sum, Count
from django.db.models.functions import TruncDate, Coalesce
from ninja import NinjaAPI, Schema

from api.v1.pagination import apply_cursor_filter, encode_cursor
from core.auth import ApiKeyAuth
from apps.tenant_billing.models import TenantBillingPeriod, TenantInvoice
from apps.metering.usage.models import UsageEvent

tenant_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_tenant_v1")


class TenantBillingPeriodOut(Schema):
    id: str
    period_start: str
    period_end: str
    status: str
    total_usage_cost_micros: int
    event_count: int
    platform_fee_micros: int


class TenantBillingPeriodListResponse(Schema):
    data: list[TenantBillingPeriodOut]
    next_cursor: Optional[str] = None
    has_more: bool


class TenantInvoiceOut(Schema):
    id: str
    billing_period_id: str
    stripe_invoice_id: str
    total_amount_micros: int
    status: str
    created_at: str


class TenantInvoiceListResponse(Schema):
    data: list[TenantInvoiceOut]
    next_cursor: Optional[str] = None
    has_more: bool


class UsageAnalyticsResponse(Schema):
    total_events: int
    total_billed_cost_micros: int
    total_provider_cost_micros: int
    by_provider: list[dict]
    by_event_type: list[dict]


class RevenueAnalyticsResponse(Schema):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


@tenant_api.get("/billing-periods", response=TenantBillingPeriodListResponse)
def list_billing_periods(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantBillingPeriod.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return tenant_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    periods = list(qs[:limit + 1])
    has_more = len(periods) > limit
    periods = periods[:limit]

    next_cursor = None
    if has_more and periods:
        last = periods[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(p.id),
                "period_start": p.period_start.isoformat(),
                "period_end": p.period_end.isoformat(),
                "status": p.status,
                "total_usage_cost_micros": p.total_usage_cost_micros,
                "event_count": p.event_count,
                "platform_fee_micros": p.platform_fee_micros,
            }
            for p in periods
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@tenant_api.get("/invoices", response=TenantInvoiceListResponse)
def list_invoices(request, cursor: str = None, limit: int = 50):
    tenant = request.auth.tenant
    limit = min(max(limit, 1), 100)

    qs = TenantInvoice.objects.filter(tenant=tenant).order_by("-created_at", "-id")

    if cursor:
        try:
            qs = apply_cursor_filter(qs, cursor, time_field="created_at")
        except ValueError:
            return tenant_api.create_response(request, {"error": "Invalid cursor"}, status=400)

    invoices = list(qs[:limit + 1])
    has_more = len(invoices) > limit
    invoices = invoices[:limit]

    next_cursor = None
    if has_more and invoices:
        last = invoices[-1]
        next_cursor = encode_cursor(last.created_at, last.id)

    return {
        "data": [
            {
                "id": str(inv.id),
                "billing_period_id": str(inv.billing_period_id),
                "stripe_invoice_id": inv.stripe_invoice_id,
                "total_amount_micros": inv.total_amount_micros,
                "status": inv.status,
                "created_at": inv.created_at.isoformat(),
            }
            for inv in invoices
        ],
        "next_cursor": next_cursor,
        "has_more": has_more,
    }


@tenant_api.get("/analytics/usage", response=UsageAnalyticsResponse)
def usage_analytics(request, start_date: date = None, end_date: date = None):
    """Usage analytics. Uses billed_cost_micros (falls back to cost_micros via Coalesce)
    to correctly aggregate both pricing modes."""
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    # Coalesce: use billed_cost_micros if set (metric pricing), else cost_micros (legacy)
    effective_cost = Coalesce("billed_cost_micros", "cost_micros")

    totals = qs.aggregate(
        total_events=Count("id"),
        total_billed_cost_micros=Sum(effective_cost),
        total_provider_cost_micros=Sum("provider_cost_micros"),
    )

    by_provider = list(
        qs.exclude(provider="").values("provider").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    by_event_type = list(
        qs.exclude(event_type="").values("event_type").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum(effective_cost),
        ).order_by("-total_cost_micros")
    )

    return {
        "total_events": totals["total_events"] or 0,
        "total_billed_cost_micros": totals["total_billed_cost_micros"] or 0,
        "total_provider_cost_micros": totals["total_provider_cost_micros"] or 0,
        "by_provider": by_provider,
        "by_event_type": by_event_type,
    }


@tenant_api.get("/analytics/revenue", response=RevenueAnalyticsResponse)
def revenue_analytics(request, start_date: date = None, end_date: date = None):
    tenant = request.auth.tenant
    qs = UsageEvent.objects.filter(tenant=tenant)

    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lte=end_date)

    totals = qs.aggregate(
        total_provider_cost_micros=Sum("provider_cost_micros"),
        total_billed_cost_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
    )

    provider_cost = totals["total_provider_cost_micros"] or 0
    billed_cost = totals["total_billed_cost_micros"] or 0

    daily = list(
        qs.annotate(day=TruncDate("effective_at")).values("day").annotate(
            provider_cost_micros=Sum("provider_cost_micros"),
            billed_cost_micros=Sum(Coalesce("billed_cost_micros", "cost_micros")),
            event_count=Count("id"),
        ).order_by("day")
    )

    for entry in daily:
        if entry.get("day"):
            entry["day"] = entry["day"].isoformat()

    # Compute markup when provider_cost is known (is not None from DB).
    # provider_cost == 0 is valid (free provider); None means no provider cost data.
    raw_provider = totals["total_provider_cost_micros"]
    if raw_provider is not None:
        markup = billed_cost - provider_cost
    else:
        markup = 0

    return {
        "total_provider_cost_micros": provider_cost,
        "total_billed_cost_micros": billed_cost,
        "total_markup_micros": markup,
        "daily": daily,
    }
