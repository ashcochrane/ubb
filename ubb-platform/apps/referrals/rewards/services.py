from decimal import Decimal, ROUND_HALF_UP


class RewardService:
    """Calculate reward amounts based on referral configuration."""

    @staticmethod
    def calculate_reward(referral, cost_micros, raw_cost_micros=None):
        """Calculate the reward for a single usage event.

        Args:
            referral: Referral instance with snapshotted reward config.
            cost_micros: What the referred customer paid (revenue to tenant).
            raw_cost_micros: Tenant's actual cost (optional, for profit-share).

        Returns:
            int: Reward amount in micros (always >= 0).
        """
        reward_type = referral.snapshot_reward_type
        reward_value = Decimal(str(referral.snapshot_reward_value))

        if reward_type == "flat_fee":
            return int(reward_value)

        if reward_type == "revenue_share":
            reward = Decimal(cost_micros) * reward_value
            return max(0, int(reward.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))

        if reward_type == "profit_share":
            if raw_cost_micros is not None:
                profit = cost_micros - raw_cost_micros
            elif referral.snapshot_estimated_cost_percentage is not None:
                estimated_cost = Decimal(cost_micros) * Decimal(
                    str(referral.snapshot_estimated_cost_percentage)
                )
                profit = Decimal(cost_micros) - estimated_cost
                profit = int(profit.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            else:
                return 0  # Cannot calculate profit, defer to batch

            if profit <= 0:
                return 0

            reward = Decimal(profit) * reward_value
            return max(0, int(reward.quantize(Decimal("1"), rounding=ROUND_HALF_UP)))

        return 0
