import logging

from celery import shared_task
from django.db.models import Q
from django.utils import timezone

from core.time_windows import utc_day_start

logger = logging.getLogger(__name__)


def _previous_month_start(today):
    first_of_this_month = today.replace(day=1)
    if first_of_this_month.month == 1:
        return first_of_this_month.replace(year=first_of_this_month.year - 1, month=12)
    return first_of_this_month.replace(month=first_of_this_month.month - 1)


@shared_task(queue="ubb_invoicing")
def verify_tier_rerate(period_start_iso=None):
    """Tripwire: re-verify every tiered-pricing period ladder for the just-closed
    month against the immutable event stream. ALERT ONLY — never mutates.

    Per PricingPeriodCounter of the period:
      (a) counter.units_total == sum of event units billed against the lineage
          (from tier_breakdown provenance entries);
      (b) chain continuity: events ordered by created_at satisfy
          prior_units[i+1] == units_total_after[i], starting from 0;
      (c) single-card-version periods: sum(micros) == compute_cumulative(total)
          — the telescoping invariant re-checked against the closed form.

    ``period_start_iso`` overrides the default just-closed month (manual re-runs
    and tests).
    """
    from datetime import date, timedelta

    from apps.metering.pricing.models import (
        PricingPeriodCounter, Rate, TIERED_PRICING_MODELS,
    )
    from apps.metering.usage.models import UsageEvent

    if period_start_iso:
        period_start = date.fromisoformat(period_start_iso)
    else:
        period_start = _previous_month_start(timezone.now().date())

    checked = drifted = 0
    for counter in PricingPeriodCounter.objects.filter(
            period_start=period_start).iterator():
        # Scan one day past each period edge: an event priced microseconds
        # before month rollover can carry an effective_at in the neighboring
        # month. Membership is decided by the provenance period below — the
        # effective_at window is only a pre-filter.
        start_dt = utc_day_start(counter.period_start) - timedelta(days=1)
        end_dt = utc_day_start(counter.period_end) + timedelta(days=1)
        lineage = str(counter.lineage_id)
        period_iso = counter.period_start.isoformat()

        entries = []
        events = UsageEvent.objects.filter(
            tenant_id=counter.tenant_id, customer_id=counter.customer_id,
            effective_at__gte=start_dt, effective_at__lt=end_dt,
        ).order_by("created_at", "id")
        for ev in events.iterator():
            for m in (ev.pricing_provenance or {}).get("metrics", []):
                breakdown = m.get("tier_breakdown") or {}
                if (breakdown.get("lineage_id") == lineage
                        and breakdown.get("period_start") == period_iso):
                    entries.append({
                        "event_id": str(ev.id),
                        "units": m.get("units") or 0,
                        "micros": m.get("micros") or 0,
                        "prior_units": breakdown.get("prior_units"),
                        "units_total_after": breakdown.get("units_total_after"),
                    })

        # Sort by prior_units (clock-skew-immune) so chain-continuity check is
        # independent of wall-clock ordering.  Two events with equal prior_units
        # indicate a real ladder collision and will trigger the chain-break alert.
        entries.sort(key=lambda e: (e["prior_units"] is None, e["prior_units"]))

        problems = []
        total_units = sum(e["units"] for e in entries)
        if total_units != counter.units_total:  # (a)
            problems.append(
                f"units_total mismatch: counter={counter.units_total} "
                f"events={total_units}")
        expected_prior = 0
        for e in entries:  # (b)
            if e["prior_units"] != expected_prior:
                problems.append(
                    f"chain break at event {e['event_id']}: "
                    f"prior_units={e['prior_units']} expected={expected_prior}")
                break
            expected_prior = e["units_total_after"]
        versions = list(Rate.objects.filter(
            tenant_id=counter.tenant_id, lineage_id=counter.lineage_id,
            valid_from__lt=utc_day_start(counter.period_end),
        ).filter(Q(valid_to__isnull=True)
                 | Q(valid_to__gt=utc_day_start(counter.period_start))))
        if len(versions) == 1 and versions[0].pricing_model in TIERED_PRICING_MODELS:  # (c)
            total_micros = sum(e["micros"] for e in entries)
            expected_micros = versions[0].compute_cumulative(total_units)
            if total_micros != expected_micros:
                problems.append(
                    f"re-rate mismatch: sum(micros)={total_micros} "
                    f"compute_cumulative({total_units})={expected_micros}")

        checked += 1
        if problems:
            drifted += 1
            logger.error("pricing.tier_rerate_drift", extra={"data": {
                "counter_id": str(counter.id),
                "tenant_id": str(counter.tenant_id),
                "customer_id": str(counter.customer_id),
                "lineage_id": lineage,
                "period_start": period_iso,
                "event_entry_count": len(entries),
                "problems": problems,
            }})

    logger.info("pricing.tier_rerate_complete", extra={"data": {
        "period_start": period_start.isoformat(),
        "counters_checked": checked, "counters_drifted": drifted,
    }})
