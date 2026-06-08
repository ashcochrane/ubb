from datetime import date, timedelta
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import NinjaAPI

from core.auth import ApiKeyAuth, ProductAccess
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.api.margin_schemas import (
    RevenueProfileIn, RevenueProfileOut, MarginThresholdIn, MarginThresholdOut)

margin_api = NinjaAPI(auth=ApiKeyAuth(), urls_namespace="ubb_margin_v1")
_product_check = ProductAccess("metering")


def _current_month():
    today = timezone.now().date()
    start = today.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1)
           if start.month == 12 else start.replace(month=start.month + 1, day=1))
    return start, end


def _window(start_date, end_date):
    if start_date and end_date:
        return start_date, end_date
    s, _ = _current_month()
    today = timezone.now().date()
    return s, today + timedelta(days=1)  # month-to-date (inclusive of today)


@margin_api.get("/summary")
def margin_summary(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    rows = get_per_customer_cost_totals(request.auth.tenant.id, s, e)
    total_provider = total_billed = total_sub = 0
    for r in rows:
        total_provider += r["provider_cost_micros"]
        total_billed += r["billed_cost_micros"]
        total_sub += RevenueService.revenue_for_window(
            request.auth.tenant.id, r["customer_id"], s, e)
    total_revenue = total_sub + total_billed
    margin = total_revenue - total_provider
    return {
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "subscription_revenue_micros": total_sub,
        "usage_billed_micros": total_billed,
        "provider_cost_micros": total_provider,
        "total_revenue_micros": total_revenue,
        "gross_margin_micros": margin,
        "margin_percentage": round(margin / total_revenue * 100, 2) if total_revenue else 0.0,
        "customer_count": len(rows),
    }


@margin_api.get("/by-dimension")
def margin_by_dimension(request, provider: int = None, product: int = None,
                        tag_key: str = None, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_dimensional_margin
    if tag_key:
        rows = get_dimensional_margin(request.auth.tenant.id, tag_key=tag_key, start_date=s, end_date=e)
    elif product:
        rows = get_dimensional_margin(request.auth.tenant.id, group_by="product_id", start_date=s, end_date=e)
    else:
        rows = get_dimensional_margin(request.auth.tenant.id, group_by="provider", start_date=s, end_date=e)
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "rows": rows}


@margin_api.get("/unprofitable")
def margin_unprofitable(request, period_start: date = None):
    _product_check(request)
    ps = period_start or _current_month()[0]
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, period_start=ps, is_unprofitable=True
    ).select_related("customer")
    return {"period_start": ps.isoformat(), "customers": [{
        "customer_id": str(r.customer_id), "external_id": r.customer.external_id,
        "gross_margin_micros": r.gross_margin_micros,
        "margin_percentage": float(r.margin_percentage),
    } for r in rows]}


@margin_api.get("/threshold", response=MarginThresholdOut)
def get_threshold(request):
    _product_check(request)
    cfg = MarginThresholdConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"min_margin_pct": 0.0, "consecutive_periods": 1, "provider_cost_spike_pct": 25.0}
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_api.put("/threshold", response=MarginThresholdOut)
def put_threshold(request, payload: MarginThresholdIn):
    _product_check(request)
    cfg, _ = MarginThresholdConfig.objects.update_or_create(
        tenant=request.auth.tenant, customer=None,
        defaults={"min_margin_pct": payload.min_margin_pct,
                  "consecutive_periods": payload.consecutive_periods,
                  "provider_cost_spike_pct": payload.provider_cost_spike_pct})
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_api.get("/customers/{customer_id}/revenue", response=RevenueProfileOut)
def get_revenue(request, customer_id: UUID):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    p = CustomerRevenueProfile.objects.filter(tenant=request.auth.tenant, customer=customer).first()
    if not p:
        return {"recurring_amount_micros": 0, "interval": "month", "currency": "usd",
                "effective_from": timezone.now().date().isoformat(), "effective_to": None}
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


@margin_api.put("/customers/{customer_id}/revenue", response=RevenueProfileOut)
def put_revenue(request, customer_id: UUID, payload: RevenueProfileIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    eff_from = date.fromisoformat(payload.effective_from) if payload.effective_from else timezone.now().date()
    eff_to = date.fromisoformat(payload.effective_to) if payload.effective_to else None
    p, _ = CustomerRevenueProfile.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer,
        defaults={"recurring_amount_micros": payload.recurring_amount_micros,
                  "interval": payload.interval, "currency": payload.currency,
                  "effective_from": eff_from, "effective_to": eff_to})
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


@margin_api.get("/{customer_id}/trend")
def margin_trend(request, customer_id: UUID, periods: int = 6):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, customer=customer).order_by("-period_start")[:max(1, min(periods, 36))]
    return {"customer_id": str(customer.id), "points": [{
        "period_start": r.period_start.isoformat(),
        "provider_cost_micros": r.provider_cost_micros,
        "usage_billed_micros": r.usage_billed_micros,
        "subscription_revenue_micros": r.subscription_revenue_micros,
        "gross_margin_micros": r.gross_margin_micros,
        "margin_percentage": float(r.margin_percentage),
    } for r in reversed(list(rows))]}


@margin_api.get("/{customer_id}")
def customer_margin(request, customer_id: UUID, start_date: date = None, end_date: date = None):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    s, e = _window(start_date, end_date)
    data = MarginService.compute_live(request.auth.tenant.id, customer.id, s, e)
    data["external_id"] = customer.external_id
    data["period"] = {"start": s.isoformat(), "end": e.isoformat()}
    return data


@margin_api.get("")
def list_margin(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    out = []
    for r in get_per_customer_cost_totals(request.auth.tenant.id, s, e):
        sub = RevenueService.revenue_for_window(request.auth.tenant.id, r["customer_id"], s, e)
        revenue = sub + r["billed_cost_micros"]
        margin = revenue - r["provider_cost_micros"]
        out.append({"customer_id": str(r["customer_id"]),
                    "subscription_revenue_micros": sub,
                    "usage_billed_micros": r["billed_cost_micros"],
                    "provider_cost_micros": r["provider_cost_micros"],
                    "gross_margin_micros": margin,
                    "margin_percentage": round(margin / revenue * 100, 2) if revenue else 0.0})
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "customers": out}
