import logging
from datetime import date

from django.db.models import Sum
from django.utils import timezone

from apps.referrals.models import Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator, ReferralRewardLedger
from apps.referrals.rewards.services import RewardService

logger = logging.getLogger(__name__)


def reconcile_referral(referral, period_start, period_end):
    """Reconcile a single referral's rewards for a given period.

    Recalculates from source usage data and writes a ledger entry.
    Returns the ledger entry or None if no activity.
    """
    from apps.metering.usage.models import UsageEvent

    events = UsageEvent.objects.filter(
        tenant_id=referral.tenant_id,
        customer_id=referral.referred_customer_id,
        created_at__gte=period_start,
        created_at__lt=period_end,
    )

    total_spend = 0
    total_raw_cost = 0
    total_reward = 0
    has_actual_cost = False

    for event in events:
        cost = event.billed_cost_micros or event.cost_micros or 0
        raw_cost = getattr(event, "raw_cost_micros", None)

        total_spend += cost
        if raw_cost is not None:
            total_raw_cost += raw_cost
            has_actual_cost = True

        reward = RewardService.calculate_reward(
            referral, cost, raw_cost_micros=raw_cost
        )
        total_reward += reward

    if total_spend == 0:
        return None

    # Apply cap
    if referral.snapshot_max_reward_micros is not None:
        # Get total earned from other periods
        other_earned = ReferralRewardLedger.objects.filter(
            referral=referral,
        ).exclude(
            period_start=period_start,
        ).aggregate(total=Sum("reward_micros"))["total"] or 0

        remaining = referral.snapshot_max_reward_micros - other_earned
        total_reward = min(total_reward, max(0, remaining))

    if has_actual_cost:
        calc_method = "actual_cost"
    elif referral.snapshot_reward_type == "flat_fee":
        calc_method = "flat_fee"
    else:
        calc_method = "estimated_cost"

    ledger_entry, _ = ReferralRewardLedger.objects.update_or_create(
        referral=referral,
        period_start=period_start,
        defaults={
            "period_end": period_end,
            "referred_spend_micros": total_spend,
            "raw_cost_micros": total_raw_cost,
            "reward_micros": total_reward,
            "calculation_method": calc_method,
        },
    )

    return ledger_entry


def reconcile_all_referrals(tenant_id, period_start, period_end):
    """Reconcile all active referrals for a tenant."""
    referrals = Referral.objects.filter(
        tenant_id=tenant_id,
        status="active",
    )

    results = {"reconciled": 0, "skipped": 0, "errors": 0}

    for referral in referrals:
        try:
            entry = reconcile_referral(referral, period_start, period_end)
            if entry:
                # Correct accumulator drift
                total_earned = ReferralRewardLedger.objects.filter(
                    referral=referral,
                ).aggregate(total=Sum("reward_micros"))["total"] or 0

                total_spend = ReferralRewardLedger.objects.filter(
                    referral=referral,
                ).aggregate(total=Sum("referred_spend_micros"))["total"] or 0

                ReferralRewardAccumulator.objects.filter(
                    referral=referral,
                ).update(
                    total_earned_micros=total_earned,
                    total_referred_spend_micros=total_spend,
                )

                results["reconciled"] += 1
            else:
                results["skipped"] += 1
        except Exception:
            logger.exception(
                "Reconciliation failed for referral",
                extra={"data": {"referral_id": str(referral.id)}},
            )
            results["errors"] += 1

    return results


def expire_referrals():
    """Mark referrals past their reward window as expired."""
    from django.db import transaction

    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import ReferralExpired

    now = timezone.now()
    expired_referrals = Referral.objects.filter(
        status="active",
        reward_window_ends_at__isnull=False,
        reward_window_ends_at__lt=now,
    )

    count = 0
    for referral in expired_referrals:
        with transaction.atomic():
            referral.status = "expired"
            referral.save(update_fields=["status", "updated_at"])

            try:
                acc = referral.reward_accumulator
                total_earned = acc.total_earned_micros
            except ReferralRewardAccumulator.DoesNotExist:
                total_earned = 0

            write_event(ReferralExpired(
                tenant_id=str(referral.tenant_id),
                referral_id=str(referral.id),
                referrer_id=str(referral.referrer_id),
                total_earned_micros=total_earned,
            ))
        count += 1

    return count
