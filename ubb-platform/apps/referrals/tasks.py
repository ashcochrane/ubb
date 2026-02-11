import logging
from datetime import date

from celery import shared_task

from apps.platform.tenants.models import Tenant

logger = logging.getLogger(__name__)


@shared_task(queue="ubb_referrals")
def reconcile_all_referrals_task():
    """Daily task: reconcile rewards and expire referrals for all referrals tenants."""
    from apps.referrals.rewards.reconciliation import (
        reconcile_all_referrals,
        expire_referrals,
    )

    tenants = Tenant.objects.filter(
        is_active=True,
        products__contains=["referrals"],
    )

    for tenant in tenants:
        today = date.today()
        period_start = today.replace(day=1)
        if today.month == 12:
            period_end = today.replace(year=today.year + 1, month=1, day=1)
        else:
            period_end = today.replace(month=today.month + 1, day=1)

        try:
            result = reconcile_all_referrals(
                tenant.id, period_start, period_end,
            )
            logger.info(
                "Referral reconciliation completed",
                extra={"data": {
                    "tenant_id": str(tenant.id),
                    **result,
                }},
            )
        except Exception:
            logger.exception(
                "Referral reconciliation failed",
                extra={"data": {"tenant_id": str(tenant.id)}},
            )

    # Expire referrals across all tenants
    expired_count = expire_referrals()
    logger.info(
        "Referral expiry completed",
        extra={"data": {"expired_count": expired_count}},
    )
