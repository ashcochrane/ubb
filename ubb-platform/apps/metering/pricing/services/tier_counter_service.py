"""Period-cumulative unit ladders for tiered (graduated/package) price cards.

``lock_and_advance`` is THE serialization point for tiered pricing: it takes a
row lock on the (tenant, customer, lineage, period) counter so concurrent
record_usage calls rate their marginals against a consistent prior. Callers
MUST hold an open transaction — the lock (and the advance) must live exactly
as long as the caller's UsageEvent insert, committing or rolling back with it.
"""
import datetime as dt

from django.db import IntegrityError, connection, transaction

from apps.metering.pricing.models import PricingPeriodCounter


def month_bounds(as_of):
    """Calendar-month UTC bounds (DateField pair, half-open) containing as_of.

    Always normalizes to UTC before extracting the date, so callers passing a
    timezone-aware datetime with a non-UTC offset get the correct UTC month.
    """
    # Normalize aware datetimes to UTC; naive datetimes are treated as UTC.
    if hasattr(as_of, "tzinfo") and as_of.tzinfo is not None:
        as_of = as_of.astimezone(dt.timezone.utc)
    day = as_of.date()
    start = day.replace(day=1)
    if day.month == 12:
        end = day.replace(year=day.year + 1, month=1, day=1)
    else:
        end = day.replace(month=day.month + 1, day=1)
    return start, end


class TierCounterService:
    @staticmethod
    def lock_and_advance(tenant, customer, card, units, as_of):
        """Advance the period ladder for ``card.lineage_id`` by ``units``.

        Returns (prior_units, units_total_after). Must be called inside an
        open transaction so the row lock + advance roll back if the caller's
        event insert fails (e.g. a raced idempotency duplicate).
        """
        if units is not None and units < 0:
            raise ValueError(
                f"lock_and_advance: units must be >= 0, got {units}")
        if not connection.in_atomic_block:
            raise AssertionError(
                "lock_and_advance must be called inside transaction.atomic()")
        period_start, period_end = month_bounds(as_of)
        lookup = {"tenant": tenant, "customer": customer,
                  "lineage_id": card.lineage_id, "period_start": period_start}
        if not PricingPeriodCounter.objects.filter(**lookup).exists():
            try:
                # Savepoint: a raced duplicate create must not poison the
                # caller's enclosing transaction (billing/handlers.py pattern).
                with transaction.atomic():
                    PricingPeriodCounter.objects.create(
                        metric_name=card.metric_name, currency=card.currency,
                        period_end=period_end, units_total=0, **lookup)
            except IntegrityError:
                pass  # raced: another writer created it — fall through to the lock
        counter = PricingPeriodCounter.objects.select_for_update().get(**lookup)
        prior = counter.units_total
        counter.units_total = prior + (units or 0)
        counter.save(update_fields=["units_total", "updated_at"])
        return prior, counter.units_total
