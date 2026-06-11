"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, referrals) to read metering data. Functions return
plain dicts, never ORM instances.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- api/v1/billing_endpoints.py → get_revenue_analytics()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
"""
from datetime import date
from typing import TypedDict

from django.db.models import Sum, Count
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import TruncDate

from core.time_windows import utc_day_start, utc_next_day_start


class PeriodTotals(TypedDict):
    total_cost_micros: int
    event_count: int


class UsageEventCost(TypedDict):
    billed_cost_micros: int
    provider_cost_micros: int


def get_period_totals(tenant_id: str, period_start: date, period_end: date) -> PeriodTotals:
    """Get aggregate usage totals for a tenant's billing period.

    Returns dict with 'total_cost_micros' and 'event_count'.
    """
    from apps.metering.usage.models import UsageEvent

    totals = UsageEvent.objects.filter(
        tenant_id=tenant_id,
        effective_at__gte=utc_day_start(period_start),
        effective_at__lt=utc_day_start(period_end),
    ).aggregate(
        total_cost=Sum("billed_cost_micros"),
        event_count=Count("id"),
    )

    return {
        "total_cost_micros": totals["total_cost"] or 0,
        "event_count": totals["event_count"] or 0,
    }


def get_usage_event_cost(usage_event_id: str, tenant_id: str | None = None) -> int | None:
    """Get the billed cost of a usage event. Returns int or None.

    If tenant_id is provided, only returns cost for events belonging to that tenant.
    """
    from apps.metering.usage.models import UsageEvent

    qs = UsageEvent.objects.filter(id=usage_event_id)
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    event = qs.values_list("billed_cost_micros", flat=True).first()
    return event


class RevenueAnalytics(TypedDict):
    total_provider_cost_micros: int
    total_billed_cost_micros: int
    total_markup_micros: int
    daily: list[dict]


def get_revenue_analytics(
    tenant_id: str, start_date: date = None, end_date: date = None,
) -> RevenueAnalytics:
    """Get revenue analytics with totals and daily breakdown.

    Returns dict with total provider/billed/markup costs and a daily
    list of dicts with day, provider_cost_micros, billed_cost_micros,
    event_count.
    """
    from apps.metering.usage.models import UsageEvent

    qs = UsageEvent.objects.filter(tenant_id=tenant_id)

    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        # Inclusive date end == strict bound at the NEXT UTC midnight.
        qs = qs.filter(effective_at__lt=utc_next_day_start(end_date))

    totals = qs.aggregate(
        total_provider_cost_micros=Sum("provider_cost_micros"),
        total_billed_cost_micros=Sum("billed_cost_micros"),
    )

    provider_cost = totals["total_provider_cost_micros"] or 0
    billed_cost = totals["total_billed_cost_micros"] or 0

    daily = list(
        qs.annotate(day=TruncDate("effective_at")).values("day").annotate(
            provider_cost_micros=Sum("provider_cost_micros"),
            billed_cost_micros=Sum("billed_cost_micros"),
            event_count=Count("id"),
        ).order_by("day")
    )

    for entry in daily:
        if entry.get("day"):
            entry["day"] = entry["day"].isoformat()

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


def get_customer_usage_for_period(
    tenant_id: str, customer_id: str, period_start: date, period_end: date,
) -> list[UsageEventCost]:
    """Get per-event usage data for a customer in a period.

    Returns list of dicts with billed_cost_micros, provider_cost_micros.
    Used by referrals reconciliation.
    """
    from apps.metering.usage.models import UsageEvent

    events = UsageEvent.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        effective_at__gte=period_start,
        effective_at__lt=period_end,
    ).values("billed_cost_micros", "provider_cost_micros")

    return list(events)


def get_customer_cost_totals(tenant_id, customer_id, start_date, end_date) -> dict:
    """Provider + billed cost totals for one customer over [start, end)."""
    from apps.metering.usage.models import UsageEvent
    agg = UsageEvent.objects.filter(
        tenant_id=tenant_id, customer_id=customer_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).aggregate(
        provider=Sum("provider_cost_micros"), billed=Sum("billed_cost_micros"),
        count=Count("id"),
    )
    return {
        "provider_cost_micros": agg["provider"] or 0,
        "billed_cost_micros": agg["billed"] or 0,
        "event_count": agg["count"] or 0,
    }


def get_usage_timeseries(tenant_id, *, granularity="day", customer_id=None,
                         group_by=None, start_date=None, end_date=None) -> list[dict]:
    """Time-series spend rollup: daily or hourly COGS per tenant, optionally per customer/dimension.

    Returns list of dicts with bucket (ISO string), provider_cost_micros, billed_cost_micros,
    markup_micros, event_count, and optionally dimension (when group_by is set).
    """
    from django.db.models.functions import TruncHour
    from apps.metering.usage.models import UsageEvent

    trunc = TruncHour if granularity == "hour" else TruncDate
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    valid_group_by = ("provider", "event_type", "product_id", "service_id", "agent_id")
    cols = ["bucket"]
    if group_by in valid_group_by:
        cols.append(group_by)

    rows = (qs.annotate(bucket=trunc("effective_at")).values(*cols).annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id")).order_by("bucket"))

    out = []
    for r in rows:
        d = dict(r)
        d["bucket"] = d["bucket"].isoformat() if d.get("bucket") else None
        if group_by and group_by in d:
            raw_dim = d.pop(group_by)
            # Map empty string or None to the unattributed sentinel so no events
            # are silently dropped and every timeseries bucket reconciles to the total.
            d["dimension"] = raw_dim if raw_dim else "(unattributed)"
        d["markup_micros"] = (d["billed_cost_micros"] or 0) - (d["provider_cost_micros"] or 0)
        out.append(d)
    return out


def get_per_customer_cost_totals(tenant_id, start_date, end_date) -> list[dict]:
    """Per-customer provider + billed totals over [start, end)."""
    from apps.metering.usage.models import UsageEvent
    rows = (UsageEvent.objects.filter(
        tenant_id=tenant_id,
        effective_at__gte=utc_day_start(start_date),
        effective_at__lt=utc_day_start(end_date),
    ).values("customer_id").annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id"),
    ).order_by("-billed_cost_micros"))
    return [dict(r) for r in rows]


def get_dimensional_margin(tenant_id, *, group_by=None, tag_key=None,
                           start_date=None, end_date=None) -> list[dict]:
    """Usage-only margin (billed - provider) grouped by a column or a tag key.

    group_by in {"provider", "event_type", "product_id"}; OR tag_key for tags->>key.
    Each row: {dimension, provider_cost_micros, billed_cost_micros, margin_micros, event_count}.
    """
    from apps.metering.usage.models import UsageEvent
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if start_date:
        qs = qs.filter(effective_at__gte=utc_day_start(start_date))
    if end_date:
        qs = qs.filter(effective_at__lt=utc_day_start(end_date))

    def _row(dim, provider, billed, count):
        return {"dimension": dim, "provider_cost_micros": provider or 0,
                "billed_cost_micros": billed or 0,
                "margin_micros": (billed or 0) - (provider or 0), "event_count": count}

    if tag_key:
        grouped = (
            qs.filter(tags__has_key=tag_key)
            .annotate(dimension=KeyTextTransform(tag_key, "tags"))
            .values("dimension")
            .annotate(
                prov_sum=Sum("provider_cost_micros"),
                billed_sum=Sum("billed_cost_micros"),
                cnt=Count("id"),
            )
            .order_by()
        )
        rows = [_row(g["dimension"], g["prov_sum"], g["billed_sum"], g["cnt"]) for g in grouped]
        return sorted(rows, key=lambda r: -r["margin_micros"])

    if group_by not in ("provider", "event_type", "product_id"):
        raise ValueError("group_by must be provider, event_type, or product_id")
    grouped = (qs.exclude(**{group_by: ""}).values(group_by).annotate(
        prov_sum=Sum("provider_cost_micros"), billed_sum=Sum("billed_cost_micros"),
        cnt=Count("id")).order_by())
    rows = [_row(g[group_by], g["prov_sum"], g["billed_sum"], g["cnt"]) for g in grouped]
    return sorted(rows, key=lambda r: -r["margin_micros"])
