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


def handle_usage_recorded(data):
    """Accumulate usage cost for unit economics calculation.

    Called by event bus when usage.recorded fires for subscriptions tenants.
    Uses atomic F() increment — no SELECT needed for the hot path.
    """
    cost_micros = data.get("cost_micros", 0)
    if cost_micros <= 0:
        return

    from apps.subscriptions.economics.models import CustomerCostAccumulator

    period_start, period_end = _current_period_bounds()

    # Try atomic increment first (fast path — row already exists)
    rows = CustomerCostAccumulator.objects.filter(
        tenant_id=data["tenant_id"],
        customer_id=data["customer_id"],
        period_start=period_start,
    ).update(
        total_cost_micros=F("total_cost_micros") + cost_micros,
        event_count=F("event_count") + 1,
    )

    if rows == 0:
        # Row doesn't exist yet — create it
        from django.db import IntegrityError
        try:
            CustomerCostAccumulator.objects.create(
                tenant_id=data["tenant_id"],
                customer_id=data["customer_id"],
                period_start=period_start,
                period_end=period_end,
                total_cost_micros=cost_micros,
                event_count=1,
            )
        except IntegrityError:
            # Lost race — retry the update
            CustomerCostAccumulator.objects.filter(
                tenant_id=data["tenant_id"],
                customer_id=data["customer_id"],
                period_start=period_start,
            ).update(
                total_cost_micros=F("total_cost_micros") + cost_micros,
                event_count=F("event_count") + 1,
            )
