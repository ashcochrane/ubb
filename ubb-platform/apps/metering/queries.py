"""
Metering query interface for cross-product reads.

Other products call these functions instead of importing metering models.
Returns plain dicts/tuples — consumers never touch ORM instances.

If metering becomes a separate service, these become HTTP/gRPC calls.
One file changes; every consumer stays untouched.
"""
from django.db.models import Sum, Count
from django.db.models.functions import Coalesce


def get_period_totals(tenant_id, period_start, period_end):
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


def get_customer_usage_for_period(tenant_id, customer_id, period_start, period_end):
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
