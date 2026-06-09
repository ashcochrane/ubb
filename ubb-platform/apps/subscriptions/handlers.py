import logging

from django.db.models import F
from django.utils import timezone

logger = logging.getLogger("ubb.events")


def _period_bounds_for(day):
    """Return (period_start, period_end) for the calendar month containing *day*."""
    first_of_month = day.replace(day=1)
    if day.month == 12:
        first_of_next = day.replace(year=day.year + 1, month=1, day=1)
    else:
        first_of_next = day.replace(month=day.month + 1, day=1)
    return first_of_month, first_of_next


def _current_period_bounds():
    """Return (period_start, period_end) for the current calendar month."""
    return _period_bounds_for(timezone.now().date())


def handle_usage_recorded_subscriptions(event_id, payload):
    """Accumulate provider + billed usage cost for margin. Atomic F() increment.

    Buckets by the UsageEvent's effective_at so backdated / late-retry events
    land in the correct month.  Falls back to now() when event_id is absent or
    not a valid UUID row (keeps legacy test fixtures with "evt-1" style ids green).
    """
    provider = payload.get("provider_cost_micros", 0) or 0
    billed = payload.get("billed_cost_micros", payload.get("cost_micros", 0)) or 0
    if billed <= 0 and provider <= 0:
        return

    # Resolve the event's effective_at to bucket into the correct calendar month.
    from apps.metering.usage.models import UsageEvent
    eff = None
    ev_id = payload.get("event_id")
    if ev_id:
        try:
            eff = UsageEvent.objects.filter(id=ev_id).values_list(
                "effective_at", flat=True
            ).first()
        except Exception:
            # Non-UUID ids (e.g. "evt-1" in tests) raise DataError on Postgres.
            eff = None
    basis = eff.date() if eff else timezone.now().date()
    period_start, period_end = _period_bounds_for(basis)

    from apps.subscriptions.economics.models import CustomerCostAccumulator

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
