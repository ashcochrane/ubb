import logging
from datetime import date

from celery import shared_task
from django.db import models, transaction
from django.utils import timezone

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


@shared_task(queue="ubb_referrals")
def emit_referral_payouts_task():
    """Emit payout_due webhook events for referrals with unpaid earnings.

    Idempotency: tracks last_payout_amount_micros per accumulator.
    Atomicity: update + outbox write in same transaction.
    """
    from apps.referrals.rewards.models import ReferralRewardAccumulator
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import ReferralPayoutDue

    min_payout_micros = 1_000_000  # $1 minimum payout threshold

    accumulators = ReferralRewardAccumulator.objects.filter(
        total_earned_micros__gt=models.F("last_payout_amount_micros") + min_payout_micros,
    ).select_related("referral__tenant", "referral__referrer__customer")

    emitted = 0
    for acc in accumulators.iterator():
        with transaction.atomic():
            # Re-fetch with lock to prevent concurrent emission
            locked_acc = ReferralRewardAccumulator.objects.select_for_update().get(id=acc.id)
            actual_payout = locked_acc.total_earned_micros - locked_acc.last_payout_amount_micros
            if actual_payout < min_payout_micros:
                continue  # Another worker already emitted

            locked_acc.last_payout_amount_micros = locked_acc.total_earned_micros
            locked_acc.last_payout_at = timezone.now()
            locked_acc.save(update_fields=["last_payout_amount_micros", "last_payout_at", "updated_at"])

            write_event(ReferralPayoutDue(
                tenant_id=str(acc.referral.tenant_id),
                referral_id=str(acc.referral_id),
                referrer_customer_id=str(acc.referral.referrer.customer_id),
                payout_amount_micros=actual_payout,
            ))
            emitted += 1

    if emitted:
        logger.info(
            "Referral payouts emitted",
            extra={"data": {"emitted_count": emitted}},
        )
