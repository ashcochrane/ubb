"""Metering Query Interface — Cross-Product Read Contract.

This module provides the ONLY approved way for other products
(billing, referrals) to read metering data. Functions return
plain dicts, never ORM instances.

If metering becomes a separate service, these functions become
HTTP calls. All callers remain untouched.

Consumers:
- apps/billing/tenant_billing/services.py → get_period_totals()
- apps/referrals/rewards/reconciliation.py → get_customer_usage_for_period()
"""
from datetime import date
from typing import TypedDict

from django.db.models import Sum, Count
from django.db.models.functions import Coalesce


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
