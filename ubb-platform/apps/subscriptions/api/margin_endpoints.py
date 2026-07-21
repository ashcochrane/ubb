from datetime import date, timedelta
from uuid import UUID

from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router

from core.auth import ApiKeyAuth, ProductAccess
from core.problems import Problem, ProblemOut
from core.time_windows import REPORT_WINDOW_MAX_DAYS
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.api.margin_schemas import (
    RevenueProfileIn, RevenueProfileOut, MarginThresholdIn, MarginThresholdOut,
    RevenueModeIn, RevenueModeOut)

margin_router = Router(auth=ApiKeyAuth())
_product_check = ProductAccess("metering")


def _current_month():
    today = timezone.now().date()
    start = today.replace(day=1)
    end = (start.replace(year=start.year + 1, month=1, day=1)
           if start.month == 12 else start.replace(month=start.month + 1, day=1))
    return start, end


def _window(start_date, end_date):
    if start_date and end_date:
        if end_date < start_date:
            raise Problem(
                "validation_error", "end_date must not precede start_date"
            )
        if (end_date - start_date).days > REPORT_WINDOW_MAX_DAYS:
            raise Problem(
                "validation_error", "date window must not exceed 366 days"
            )
        return start_date, end_date
    s, _ = _current_month()
    today = timezone.now().date()
    return s, today + timedelta(days=1)  # month-to-date (inclusive of today)


@margin_router.get("/summary")
def margin_summary(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    tenant = request.auth.tenant
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    rows = get_per_customer_cost_totals(tenant.id, s, e)
    cust = {c.id: c for c in Customer.objects.filter(
        id__in=[r["customer_id"] for r in rows], tenant=tenant)}
    total_provider = total_billed = total_sub = total_usage_rev = 0
    for r in rows:
        total_provider += r["provider_cost_micros"]
        total_billed += r["billed_cost_micros"]
        total_sub += RevenueService.accrued_subscription_revenue(tenant.id, r["customer_id"], s, e)
        if RevenueService.resolve_revenue_mode(tenant, cust[r["customer_id"]]) == "billed":
            total_usage_rev += r["billed_cost_micros"]
    total_revenue = total_sub + total_usage_rev
    margin = total_revenue - total_provider
    return {
        "period": {"start": s.isoformat(), "end": e.isoformat()},
        "subscription_revenue_micros": total_sub,
        "usage_billed_micros": total_billed,
        "usage_revenue_micros": total_usage_rev,
        "provider_cost_micros": total_provider,
        "total_revenue_micros": total_revenue,
        "gross_margin_micros": margin,
        "margin_percentage": round(margin / total_revenue * 100, 2) if total_revenue else 0.0,
        "customer_count": len(rows),
    }


@margin_router.get("/by-dimension")
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


@margin_router.get("/unprofitable")
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


@margin_router.get("/threshold", response=MarginThresholdOut)
def get_threshold(request):
    _product_check(request)
    cfg = MarginThresholdConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"min_margin_pct": 0.0, "consecutive_periods": 1, "provider_cost_spike_pct": 25.0}
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_router.put("/threshold", response=MarginThresholdOut)
def put_threshold(request, payload: MarginThresholdIn):
    _product_check(request)
    cfg, _ = MarginThresholdConfig.objects.update_or_create(
        tenant=request.auth.tenant, customer=None,
        defaults={"min_margin_pct": payload.min_margin_pct,
                  "consecutive_periods": payload.consecutive_periods,
                  "provider_cost_spike_pct": payload.provider_cost_spike_pct})
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_router.get("/customers/{customer_id}/revenue", response=RevenueProfileOut)
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


@margin_router.put(
    "/customers/{customer_id}/revenue",
    response={200: RevenueProfileOut, 404: ProblemOut, 422: ProblemOut},
)
def put_revenue(request, customer_id: UUID, payload: RevenueProfileIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    try:
        eff_from = date.fromisoformat(payload.effective_from) if payload.effective_from else timezone.now().date()
        eff_to = date.fromisoformat(payload.effective_to) if payload.effective_to else None
    except ValueError as e:
        raise Problem("validation_error", f"invalid effective date: {e}")
    p, _ = CustomerRevenueProfile.objects.update_or_create(
        tenant=request.auth.tenant, customer=customer,
        defaults={"recurring_amount_micros": payload.recurring_amount_micros,
                  "interval": payload.interval, "currency": payload.currency,
                  "effective_from": eff_from, "effective_to": eff_to})
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


_VALID_MODES = {"", "billed", "metered_only"}


@margin_router.get("/customers/{customer_id}/revenue-mode", response=RevenueModeOut)
def get_revenue_mode(request, customer_id: UUID):
    _product_check(request)
    from apps.subscriptions.economics.revenue import RevenueService
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    return {"revenue_mode": customer.revenue_mode,
            "resolved": RevenueService.resolve_revenue_mode(request.auth.tenant, customer)}


@margin_router.put(
    "/customers/{customer_id}/revenue-mode",
    response={200: RevenueModeOut, 404: ProblemOut, 422: ProblemOut},
)
def put_revenue_mode(request, customer_id: UUID, payload: RevenueModeIn):
    _product_check(request)
    from apps.subscriptions.economics.revenue import RevenueService
    if payload.revenue_mode not in _VALID_MODES:
        raise Problem(
            "invalid_revenue_mode",
            "revenue_mode must be one of '', 'billed', 'metered_only'; "
            f"got '{payload.revenue_mode}'",
        )
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    customer.revenue_mode = payload.revenue_mode
    customer.save(update_fields=["revenue_mode", "updated_at"])
    return {"revenue_mode": customer.revenue_mode,
            "resolved": RevenueService.resolve_revenue_mode(request.auth.tenant, customer)}


@margin_router.get("/business/{external_id}")
def business_margin(request, external_id: str, start_date: date = None, end_date: date = None):
    _product_check(request)
    biz = get_object_or_404(Customer, tenant=request.auth.tenant,
                            external_id=external_id, account_type="business")
    s, e = _window(start_date, end_date)
    return MarginService.compute_business(request.auth.tenant.id, biz, s, e)


@margin_router.get("/{customer_id}/trend")
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


@margin_router.get("/{customer_id}")
def customer_margin(request, customer_id: UUID, start_date: date = None, end_date: date = None):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    s, e = _window(start_date, end_date)
    data = MarginService.compute_live(request.auth.tenant.id, customer.id, s, e)
    data["external_id"] = customer.external_id
    data["period"] = {"start": s.isoformat(), "end": e.isoformat()}
    return data


@margin_router.get("")
def list_margin(request, start_date: date = None, end_date: date = None):
    _product_check(request)
    s, e = _window(start_date, end_date)
    tenant = request.auth.tenant
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.revenue import RevenueService
    rows = get_per_customer_cost_totals(tenant.id, s, e)
    cust = {c.id: c for c in Customer.objects.filter(
        id__in=[r["customer_id"] for r in rows], tenant=tenant)}
    out = []
    for r in rows:
        customer_obj = cust[r["customer_id"]]
        sub = RevenueService.accrued_subscription_revenue(tenant.id, r["customer_id"], s, e)
        usage_rev = (r["billed_cost_micros"]
                     if RevenueService.resolve_revenue_mode(tenant, customer_obj) == "billed"
                     else 0)
        revenue = sub + usage_rev
        margin = revenue - r["provider_cost_micros"]
        out.append({"customer_id": str(r["customer_id"]),
                    "subscription_revenue_micros": sub,
                    "usage_billed_micros": r["billed_cost_micros"],
                    "usage_revenue_micros": usage_rev,
                    "provider_cost_micros": r["provider_cost_micros"],
                    "gross_margin_micros": margin,
                    "margin_percentage": round(margin / revenue * 100, 2) if revenue else 0.0})
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "customers": out}
