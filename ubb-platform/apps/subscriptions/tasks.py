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

    Covers current + previous calendar month so cross-month-boundary late events
    and end-of-month retries are corrected within 24 hours.

    # TODO: extend to aggregate business-level rollup once Stage-E2 "seats never
    # invoiced directly" semantics are confirmed stable (avoid double-counting).
    """
    from apps.metering.queries import get_per_customer_cost_totals
    from apps.subscriptions.economics.models import CustomerCostAccumulator
    from apps.subscriptions.handlers import _period_bounds_for

    today = timezone.now().date()
    cur_start, cur_end = _period_bounds_for(today)
    prev_start, prev_end = _period_bounds_for(cur_start - datetime.timedelta(days=1))

    drift = 0
    for period_start, period_end in ((prev_start, prev_end), (cur_start, cur_end)):
        for tenant in Tenant.objects.filter(
            products__contains=["metering"],
            is_active=True,
        ):
            for r in get_per_customer_cost_totals(tenant.id, period_start, period_end):
                acc, _ = CustomerCostAccumulator.objects.get_or_create(
                    tenant_id=tenant.id,
                    customer_id=r["customer_id"],
                    period_start=period_start,
                    defaults={"period_end": period_end},
                )
                if (
                    acc.total_provider_cost_micros != r["provider_cost_micros"]
                    or acc.total_billed_cost_micros != r["billed_cost_micros"]
                    or acc.event_count != r["event_count"]
                ):
                    drift += 1
                    CustomerCostAccumulator.objects.filter(id=acc.id).update(
                        period_end=period_end,
                        total_provider_cost_micros=r["provider_cost_micros"],
                        total_billed_cost_micros=r["billed_cost_micros"],
                        event_count=r["event_count"],
                    )

    logger.info("cost_accumulator_reconcile", extra={"data": {"drift_count": drift}})


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
