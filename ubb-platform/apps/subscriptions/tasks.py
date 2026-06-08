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
