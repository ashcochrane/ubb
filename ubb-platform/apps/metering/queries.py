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
from django.db.models.functions import Coalesce, TruncDate


class PeriodTotals(TypedDict):
    total_cost_micros: int
    event_count: int


class UsageEventCost(TypedDict):
    billed_cost_micros: int
    provider_cost_micros: int
    cost_micros: int


def get_period_totals(tenant_id: str, period_start: date, period_end: date) -> PeriodTotals:
    """Get aggregate usage totals for a tenant's billing period.

    Returns dict with 'total_cost_micros' and 'event_count'.
    Cost uses billed_cost_micros if available, falls back to cost_micros.
    """
    from apps.metering.usage.models import UsageEvent

    totals = UsageEvent.objects.filter(
        tenant_id=tenant_id,
        effective_at__date__gte=period_start,
        effective_at__date__lt=period_end,
    ).aggregate(
        total_cost=Sum(Coalesce("billed_cost_micros", "cost_micros")),
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
    event = qs.values_list(
        Coalesce("billed_cost_micros", "cost_micros"), flat=True
    ).first()
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

    Returns list of dicts with billed_cost_micros, provider_cost_micros,
    and cost_micros. Used by referrals reconciliation.
    """
    from apps.metering.usage.models import UsageEvent

    events = UsageEvent.objects.filter(
        tenant_id=tenant_id,
        customer_id=customer_id,
        created_at__gte=period_start,
        created_at__lt=period_end,
    ).values("billed_cost_micros", "provider_cost_micros", "cost_micros")

    return list(events)
