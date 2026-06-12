import datetime
import logging

from celery import shared_task
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.subscriptions.economics.services import MarginService
from apps.subscriptions.stripe.sync import sync_subscriptions

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_economics")
def calculate_all_economics_task():
    """Daily task: snapshot margin for all metering tenants."""
    today = timezone.now().date()
    period_start = today.replace(day=1)
    if today.month == 12:
        period_end = today.replace(year=today.year + 1, month=1, day=1)
    else:
        period_end = today.replace(month=today.month + 1, day=1)

    tenants = Tenant.objects.filter(
        products__contains=["metering"],
        is_active=True,
    )

    for tenant in tenants:
        try:
            results = MarginService.snapshot_all(
                tenant.id, period_start, period_end,
            )
            logger.info(
                "Margin snapshots calculated",
                extra={"data": {
                    "tenant_id": str(tenant.id),
                    "snapshots": len(results),
                }},
            )
        except Exception:
            logger.exception(
                "Margin snapshot failed",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )


@shared_task(queue="ubb_economics")
def reconcile_cost_accumulators():
    """Source-of-truth repair: recompute each open-period CustomerCostAccumulator
    from SUM(UsageEvent) by effective_at (mirrors reconcile_usage_drawdowns).

    Covers current + TWO previous calendar months: the backfill window
    (Tenant.backfill_window_days, max 60 days) can span 3 calendar months, so a
    maximally backdated event still lands inside the reconcile horizon and is
    corrected within the hour.

    # TODO: extend to aggregate business-level rollup once Stage-E2 "seats never
    # invoiced directly" semantics are confirmed stable (avoid double-counting).
    """
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.models import CustomerCostAccumulator
    from apps.subscriptions.handlers import _period_bounds_for

    today = timezone.now().date()
    cur_start, cur_end = _period_bounds_for(today)
    prev_start, prev_end = _period_bounds_for(cur_start - datetime.timedelta(days=1))
    prev2_start, prev2_end = _period_bounds_for(prev_start - datetime.timedelta(days=1))

    drift = 0
    for period_start, period_end in ((prev2_start, prev2_end),
                                     (prev_start, prev_end), (cur_start, cur_end)):
        for tenant in Tenant.objects.filter(products__contains=["metering"], is_active=True):
            ledger = {r["customer_id"]: r
                      for r in get_per_customer_cost_totals(tenant.id, period_start, period_end)}
            seen = set()
            for acc in CustomerCostAccumulator.objects.filter(
                    tenant_id=tenant.id, period_start=period_start):
                seen.add(acc.customer_id)
                r = ledger.get(acc.customer_id)
                prov = r["provider_cost_micros"] if r else 0
                bill = r["billed_cost_micros"] if r else 0
                cnt = r["event_count"] if r else 0
                if (acc.total_provider_cost_micros != prov
                        or acc.total_billed_cost_micros != bill
                        or acc.event_count != cnt):
                    drift += 1
                    CustomerCostAccumulator.objects.filter(id=acc.id).update(
                        period_end=period_end, total_provider_cost_micros=prov,
                        total_billed_cost_micros=bill, event_count=cnt)
            for cid, r in ledger.items():
                if cid in seen:
                    continue
                CustomerCostAccumulator.objects.create(
                    tenant_id=tenant.id, customer_id=cid, period_start=period_start,
                    period_end=period_end,
                    total_provider_cost_micros=r["provider_cost_micros"],
                    total_billed_cost_micros=r["billed_cost_micros"],
                    event_count=r["event_count"])
                drift += 1

    logger.info("cost_accumulator_reconcile", extra={"data": {"drift_count": drift}})


@shared_task(queue="ubb_economics")
def resnapshot_dirty_periods():
    """Refresh margin snapshots for periods dirtied by backfilled usage.

    Consumes BackfillDirtyPeriod markers via the metering read contract.
    For a marker on a PRIOR month: re-run snapshot_customer (update_or_create,
    idempotent) + evaluate_and_emit (transition-guarded + OutboxEvent-deduped,
    idempotent), then ack the marker — a crash before the ack leaves the
    marker for the next hourly run. A CURRENT-month marker is just acked: the
    nightly calculate_all_economics_task owns the current month's snapshot.

    Beat: hourly at :55, AFTER reconcile_cost_accumulators (:50) so the
    accumulator this snapshot reads has already been repaired to the ledger.
    """
    from apps.metering.queries import (
        clear_backfill_dirty_period, list_backfill_dirty_periods,
    )
    from apps.subscriptions.handlers import _period_bounds_for

    cur_start, _ = _period_bounds_for(timezone.now().date())
    resnapshots = 0
    for marker in list_backfill_dirty_periods():
        period_start = marker["period_start"]
        try:
            if period_start < cur_start:
                _, period_end = _period_bounds_for(period_start)
                econ = MarginService.snapshot_customer(
                    marker["tenant_id"], marker["customer_id"],
                    period_start, period_end)
                MarginService.evaluate_and_emit(econ)
                resnapshots += 1
            # Ack AFTER the snapshot work succeeded (or for a current-month
            # marker, immediately — nothing to do here).
            clear_backfill_dirty_period(marker["id"])
        except Exception:
            # Keep the marker: retried next hour. Other markers still run.
            logger.exception("resnapshot_dirty_period_failed", extra={"data": {
                "tenant_id": str(marker["tenant_id"]),
                "customer_id": str(marker["customer_id"]),
                "period_start": str(period_start)}})
    if resnapshots:
        logger.info("resnapshot_dirty_periods", extra={"data": {
            "resnapshots": resnapshots}})


@shared_task(queue="ubb_subscriptions")
def sync_tenant_subscriptions_task(tenant_id):
    """On-demand task: sync subscriptions for a specific tenant."""
    tenant = Tenant.objects.get(id=tenant_id)
    result = sync_subscriptions(tenant)
    logger.info(
        "Subscription sync completed",
        extra={"data": {"tenant_id": str(tenant_id), **result}},
    )
    return result
