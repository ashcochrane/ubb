import logging

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.referrals.rewards.services import RewardService

logger = logging.getLogger("ubb.events")


def handle_usage_recorded_referrals(event_id, payload):
    """Accumulate referral rewards when a referred customer records usage.

    Registered as outbox handler with requires_product="referrals".
    Called by the outbox dispatcher with (event_id, payload) signature.
    """
    from apps.referrals.models import Referral
    from apps.referrals.rewards.models import ReferralRewardAccumulator

    cost_micros = payload.get("cost_micros", 0)
    if cost_micros <= 0:
        return

    customer_id = payload["customer_id"]
    tenant_id = payload["tenant_id"]

    # Find active referral for this customer
    try:
        referral = Referral.objects.select_related("reward_accumulator").get(
            tenant_id=tenant_id,
            referred_customer_id=customer_id,
            status="active",
        )
    except Referral.DoesNotExist:
        return  # Customer was not referred

    # Check reward window
    if referral.reward_window_ends_at and timezone.now() > referral.reward_window_ends_at:
        referral.status = "expired"
        referral.save(update_fields=["status", "updated_at"])
        return

    # Skip if flat fee already paid
    if referral.snapshot_reward_type == "flat_fee" and referral.flat_fee_paid:
        return

    # Calculate reward
    raw_cost_micros = payload.get("provider_cost_micros")
    reward_micros = RewardService.calculate_reward(
        referral, cost_micros, raw_cost_micros=raw_cost_micros
    )

    if reward_micros <= 0:
        return

    # Check cap and accumulate under lock to prevent over-cap payouts
    from django.db import IntegrityError

    if referral.snapshot_max_reward_micros is not None:
        with transaction.atomic():
            acc = ReferralRewardAccumulator.objects.select_for_update().filter(
                referral=referral,
            ).first()
            if acc is None:
                try:
                    acc = ReferralRewardAccumulator.objects.create(referral=referral)
                except IntegrityError:
                    acc = ReferralRewardAccumulator.objects.select_for_update().get(
                        referral=referral,
                    )

            remaining = referral.snapshot_max_reward_micros - acc.total_earned_micros
            if remaining <= 0:
                return
            reward_micros = min(reward_micros, remaining)

            acc.total_earned_micros += reward_micros
            acc.total_referred_spend_micros += cost_micros
            acc.event_count += 1
            acc.save(update_fields=[
                "total_earned_micros", "total_referred_spend_micros",
                "event_count", "updated_at",
            ])
    else:
        # No cap — use atomic F() increment (no lock needed)
        rows = ReferralRewardAccumulator.objects.filter(
            referral=referral,
        ).update(
            total_earned_micros=F("total_earned_micros") + reward_micros,
            total_referred_spend_micros=F("total_referred_spend_micros") + cost_micros,
            event_count=F("event_count") + 1,
        )

        if rows == 0:
            try:
                ReferralRewardAccumulator.objects.create(
                    referral=referral,
                    total_earned_micros=reward_micros,
                    total_referred_spend_micros=cost_micros,
                    event_count=1,
                )
            except IntegrityError:
                ReferralRewardAccumulator.objects.filter(
                    referral=referral,
                ).update(
                    total_earned_micros=F("total_earned_micros") + reward_micros,
                    total_referred_spend_micros=F("total_referred_spend_micros") + cost_micros,
                    event_count=F("event_count") + 1,
                )

    # Mark flat fee as paid
    if referral.snapshot_reward_type == "flat_fee":
        referral.flat_fee_paid = True
        referral.save(update_fields=["flat_fee_paid", "updated_at"])

    # Write downstream event to outbox
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import ReferralRewardEarned

    write_event(ReferralRewardEarned(
        tenant_id=tenant_id,
        referral_id=str(referral.id),
        referrer_id=str(referral.referrer_id),
        referred_customer_id=str(referral.referred_customer_id),
        reward_micros=reward_micros,
    ))
