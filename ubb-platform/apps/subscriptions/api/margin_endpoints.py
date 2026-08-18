from datetime import date, timedelta
from uuid import UUID

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from ninja import Router

from core.auth import ADMIN, ApiKeyAuth, ProductAccess, READ, role_floor
from core.cost_totals import UNPRICED_EVENT_COUNT_KEY, UNRESOLVED_EVENT_COUNT_KEY
from core.problems import Problem, ProblemOut
from core.time_windows import REPORT_WINDOW_MAX_DAYS
from apps.platform.audit.ledger import record as audit_record
from apps.platform.audit.marker import records_audit
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerEconomics, CustomerRevenueProfile, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.api.margin_schemas import (
    RevenueProfileIn, RevenueProfileOut, MarginThresholdIn, MarginThresholdOut,
    RevenueModeIn, RevenueModeOut,
    MarginSummaryOut, MarginByGroupingFieldOut, UnprofitableOut, MarginListOut,
    CustomerMarginOut, MarginTrendOut, BusinessMarginOut)

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


@margin_router.get("/summary", response=MarginSummaryOut)
@role_floor(READ)
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
    # WHAT THE TENANT-WIDE COST TOTAL LEFT OUT, ADDED UP LIKE THE COST (#328).
    # Each row the read contract returns carries its own count, and a loop that
    # took the money and dropped the caveat would publish a floor as a figure —
    # the same defect as an `or 0`, one product further out. This is the one
    # place the count could go missing on this route, because the loop is where
    # the rows stop being rows.
    total_unresolved = 0
    # AND WHAT THE BILLED TOTALS LEFT OUT (#351), on the same terms and for the
    # same reason: the read contract's rows each carry their own count, and a
    # loop that took the money and dropped the caveat would publish a floor as a
    # figure. Two accumulators because the two counts are about different
    # postings and bound the margin below in opposite directions.
    total_unpriced = 0
    for r in rows:
        total_provider += r["provider_cost_micros"]
        total_unresolved += r[UNRESOLVED_EVENT_COUNT_KEY]
        total_billed += r["billed_cost_micros"]
        total_unpriced += r[UNPRICED_EVENT_COUNT_KEY]
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
        UNRESOLVED_EVENT_COUNT_KEY: total_unresolved,
        UNPRICED_EVENT_COUNT_KEY: total_unpriced,
        "total_revenue_micros": total_revenue,
        "gross_margin_micros": margin,
        "margin_percentage": round(margin / total_revenue * 100, 2) if total_revenue else 0.0,
        "customer_count": len(rows),
    }


@margin_router.get("/by-grouping-field",
                   response={200: MarginByGroupingFieldOut, 422: ProblemOut})
@role_floor(READ)
def margin_by_grouping_field(request, group_by: str = "provider",
                             tag_key: str = None,
                             start_date: date = None, end_date: date = None):
    """Margin by any Grouping Field the tenant has declared.

    Replaces the old `provider: int` / `product: int` pseudo-flags, which could
    not reach event_type at all despite get_dimensional_margin supporting it."""
    _product_check(request)
    s, e = _window(start_date, end_date)
    from apps.metering.queries import get_dimensional_margin
    if tag_key:
        rows = get_dimensional_margin(request.auth.tenant.id, tag_key=tag_key, start_date=s, end_date=e)
    else:
        from apps.platform.grouping_fields.queries import slot_map

        col = group_by
        if group_by not in ("provider", "event_type", "task_type", "subtask_type"):
            col = slot_map(request.auth.tenant.id).get(group_by)
            if col is None:
                raise Problem("validation_error",
                              f"{group_by!r} is not a declared grouping field")
        try:
            rows = get_dimensional_margin(request.auth.tenant.id, group_by=col,
                                          start_date=s, end_date=e)
        except ValueError as exc:
            raise Problem("validation_error", str(exc))
    return 200, {"period": {"start": s.isoformat(), "end": e.isoformat()}, "rows": rows}


@margin_router.get("/unprofitable", response=UnprofitableOut)
@role_floor(READ)
def margin_unprofitable(request, period_start: date = None):
    _product_check(request)
    ps = period_start or _current_month()[0]
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, period_start=ps, is_unprofitable=True
    ).select_related("customer")
    return {"period_start": ps.isoformat(), "customers": [{
        "customer_id": str(r.customer_id), "external_id": r.customer.external_id,
        "gross_margin_micros": r.gross_margin_micros,
        # A CEILING ON A MARGIN CAN ONLY GET WORSE, WHICH IS WHY THIS LIST OF
        # ALL PLACES CARRIES THE COUNT (#328). The customers here are named as
        # unprofitable on a margin computed from a cost total that excluded
        # events — the true margin is lower still, so a non-zero count never
        # means "maybe they are fine".
        UNRESOLVED_EVENT_COUNT_KEY: r.unresolved_event_count,
        # ⚠ AND THIS COUNT POINTS THE OTHER WAY, WHICH IS WHY IT IS HERE (#351).
        # An excluded PRICE means revenue was left out, so the true margin is
        # HIGHER than the one that named this customer unprofitable — a non-zero
        # count here really can mean "maybe they are fine", and a list of
        # unprofitable customers that showed only the count which cannot say
        # that would be the more misleading of the two.
        UNPRICED_EVENT_COUNT_KEY: r.unpriced_event_count,
        "margin_percentage": float(r.margin_percentage),
    } for r in rows]}


@margin_router.get("/threshold", response=MarginThresholdOut)
@role_floor(READ)
def get_threshold(request):
    _product_check(request)
    cfg = MarginThresholdConfig.objects.filter(tenant=request.auth.tenant, customer__isnull=True).first()
    if not cfg:
        return {"min_margin_pct": 0.0, "consecutive_periods": 1, "provider_cost_spike_pct": 25.0}
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_router.put("/threshold", response=MarginThresholdOut)
@role_floor(ADMIN)
@records_audit("margin_threshold.set")
def put_threshold(request, payload: MarginThresholdIn):
    _product_check(request)
    with transaction.atomic():
        cfg, _ = MarginThresholdConfig.objects.update_or_create(
            tenant=request.auth.tenant, customer=None,
            defaults={"min_margin_pct": payload.min_margin_pct,
                      "consecutive_periods": payload.consecutive_periods,
                      "provider_cost_spike_pct": payload.provider_cost_spike_pct})
        audit_record(
            action="margin_threshold.set", tenant_id=request.auth.tenant.id,
            resource_type="margin_threshold", resource_id=cfg.id,
            metadata={"min_margin_pct": float(cfg.min_margin_pct),
                      "consecutive_periods": cfg.consecutive_periods,
                      "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)})
    return {"min_margin_pct": float(cfg.min_margin_pct), "consecutive_periods": cfg.consecutive_periods,
            "provider_cost_spike_pct": float(cfg.provider_cost_spike_pct)}


@margin_router.get("/customers/{customer_id}/revenue", response=RevenueProfileOut)
@role_floor(READ)
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
@role_floor(ADMIN)
@records_audit("revenue_profile.set")
def put_revenue(request, customer_id: UUID, payload: RevenueProfileIn):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    try:
        eff_from = date.fromisoformat(payload.effective_from) if payload.effective_from else timezone.now().date()
        eff_to = date.fromisoformat(payload.effective_to) if payload.effective_to else None
    except ValueError as e:
        raise Problem("validation_error", f"invalid effective date: {e}")
    with transaction.atomic():
        p, _ = CustomerRevenueProfile.objects.update_or_create(
            tenant=request.auth.tenant, customer=customer,
            defaults={"recurring_amount_micros": payload.recurring_amount_micros,
                      "interval": payload.interval, "currency": payload.currency,
                      "effective_from": eff_from, "effective_to": eff_to})
        audit_record(
            action="revenue_profile.set", tenant_id=request.auth.tenant.id,
            resource_type="revenue_profile", resource_id=p.id,
            metadata={"customer_id": str(customer.id),
                      "recurring_amount_micros": p.recurring_amount_micros,
                      "interval": p.interval, "currency": p.currency,
                      "effective_from": p.effective_from.isoformat(),
                      "effective_to": p.effective_to.isoformat() if p.effective_to else None})
    return {"recurring_amount_micros": p.recurring_amount_micros, "interval": p.interval,
            "currency": p.currency, "effective_from": p.effective_from.isoformat(),
            "effective_to": p.effective_to.isoformat() if p.effective_to else None}


_VALID_MODES = {"", "billed", "metered_only"}


@margin_router.get("/customers/{customer_id}/revenue-mode", response=RevenueModeOut)
@role_floor(READ)
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
@role_floor(ADMIN)
@records_audit("revenue_mode.set")
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
    with transaction.atomic():
        customer.revenue_mode = payload.revenue_mode
        customer.save(update_fields=["revenue_mode", "updated_at"])
        audit_record(
            action="revenue_mode.set", tenant_id=request.auth.tenant.id,
            resource_type="customer", resource_id=customer.id,
            metadata={"customer_id": str(customer.id),
                      "revenue_mode": customer.revenue_mode})
    return {"revenue_mode": customer.revenue_mode,
            "resolved": RevenueService.resolve_revenue_mode(request.auth.tenant, customer)}


@margin_router.get("/business/{external_id}", response=BusinessMarginOut)
@role_floor(READ)
def business_margin(request, external_id: str, start_date: date = None, end_date: date = None):
    _product_check(request)
    biz = get_object_or_404(Customer, tenant=request.auth.tenant,
                            external_id=external_id, account_type="business")
    s, e = _window(start_date, end_date)
    return MarginService.compute_business(request.auth.tenant.id, biz, s, e)


@margin_router.get("/customers/{customer_id}/trend", response=MarginTrendOut)
@role_floor(READ)
def margin_trend(request, customer_id: UUID, periods: int = 6):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    rows = CustomerEconomics.objects.filter(
        tenant=request.auth.tenant, customer=customer).order_by("-period_start")[:max(1, min(periods, 36))]
    return {"customer_id": str(customer.id), "points": [{
        "period_start": r.period_start.isoformat(),
        "provider_cost_micros": r.provider_cost_micros,
        # Per POINT: a trend whose completeness varied month to month and said
        # so once at the top would be answering about the wrong months (#328).
        UNRESOLVED_EVENT_COUNT_KEY: r.unresolved_event_count,
        UNPRICED_EVENT_COUNT_KEY: r.unpriced_event_count,
        "usage_billed_micros": r.usage_billed_micros,
        "subscription_revenue_micros": r.subscription_revenue_micros,
        "gross_margin_micros": r.gross_margin_micros,
        "margin_percentage": float(r.margin_percentage),
    } for r in reversed(list(rows))]}


@margin_router.get("/customers/{customer_id}", response=CustomerMarginOut)
@role_floor(READ)
def customer_margin(request, customer_id: UUID, start_date: date = None, end_date: date = None):
    _product_check(request)
    customer = get_object_or_404(Customer, id=customer_id, tenant=request.auth.tenant)
    s, e = _window(start_date, end_date)
    data = MarginService.compute_live(request.auth.tenant.id, customer.id, s, e)
    data["external_id"] = customer.external_id
    data["period"] = {"start": s.isoformat(), "end": e.isoformat()}
    return data


@margin_router.get("/customers", response=MarginListOut)
@role_floor(READ)
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
                    # Per row, because one customer's unresolved cost says
                    # nothing about another's (#327's shape, carried out to the
                    # wire here). The margin beside it is a ceiling wherever
                    # this is non-zero.
                    UNRESOLVED_EVENT_COUNT_KEY: r[UNRESOLVED_EVENT_COUNT_KEY],
                    # And per row for the revenue half (#351), which bounds the
                    # margin the other way: an excluded price makes it a floor.
                    UNPRICED_EVENT_COUNT_KEY: r[UNPRICED_EVENT_COUNT_KEY],
                    "gross_margin_micros": margin,
                    "margin_percentage": round(margin / revenue * 100, 2) if revenue else 0.0})
    return {"period": {"start": s.isoformat(), "end": e.isoformat()}, "customers": out}
