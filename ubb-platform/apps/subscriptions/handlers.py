import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("ubb.events")


def _current_period_bounds():
    """Return (period_start, period_end) for the current calendar month."""
    today = timezone.now().date()
    first_of_month = today.replace(day=1)
    if today.month == 12:
        first_of_next_month = today.replace(year=today.year + 1, month=1, day=1)
    else:
        first_of_next_month = today.replace(month=today.month + 1, day=1)
    return first_of_month, first_of_next_month


def handle_usage_recorded_subscriptions(event_id, payload):
    """Accumulate provider + billed usage cost for margin. Atomic F() increment."""
    provider = payload.get("provider_cost_micros", 0) or 0
    billed = payload.get("billed_cost_micros", payload.get("cost_micros", 0)) or 0
    if billed <= 0 and provider <= 0:
        return

    from apps.subscriptions.economics.models import CustomerCostAccumulator

    period_start, period_end = _current_period_bounds()

    rows = CustomerCostAccumulator.objects.filter(
        tenant_id=payload["tenant_id"],
        customer_id=payload["customer_id"],
        period_start=period_start,
    ).update(
        total_provider_cost_micros=F("total_provider_cost_micros") + provider,
        total_billed_cost_micros=F("total_billed_cost_micros") + billed,
        event_count=F("event_count") + 1,
    )

    if rows == 0:
        from django.db import IntegrityError
        try:
            CustomerCostAccumulator.objects.create(
                tenant_id=payload["tenant_id"],
                customer_id=payload["customer_id"],
                period_start=period_start,
                period_end=period_end,
                total_provider_cost_micros=provider,
                total_billed_cost_micros=billed,
                event_count=1,
            )
        except IntegrityError:
            CustomerCostAccumulator.objects.filter(
                tenant_id=payload["tenant_id"],
                customer_id=payload["customer_id"],
                period_start=period_start,
            ).update(
                total_provider_cost_micros=F("total_provider_cost_micros") + provider,
                total_billed_cost_micros=F("total_billed_cost_micros") + billed,
                event_count=F("event_count") + 1,
            )
