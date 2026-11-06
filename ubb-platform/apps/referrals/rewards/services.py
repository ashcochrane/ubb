from decimal import Decimal, ROUND_HALF_UP
from core.vocabulary import (
    REWARD_TYPE_FLAT_FEE,
    REWARD_TYPE_PROFIT_SHARE,
    REWARD_TYPE_REVENUE_SHARE,
)

#: A share is stated in basis points: 10,000 of them make the whole (R10
#: Stage C5, A-3, RULED Q9). Applied by dividing by this exactly, in Decimal,
#: and rounding the result to a whole micro half-up — never through a float,
#: never through a fraction or a percentage stored anywhere.
BASIS_POINTS_PER_WHOLE = Decimal(10_000)

#: The bounds the API admits (`apps/referrals/api/schemas.py`): a reward share
#: of 1..10000 (a share of nothing is not a reward scheme), an estimated cost
#: share of 0..10000.
REWARD_SHARE_BASIS_POINTS_MIN = 1
ESTIMATED_COST_BASIS_POINTS_MIN = 0
BASIS_POINTS_MAX = 10_000


def share_of(amount_micros, basis_points):
    """``amount_micros × basis_points / 10,000``, exactly, as whole micros
    (half-up on the last micro)."""
    share = Decimal(int(amount_micros)) * Decimal(int(basis_points)) / BASIS_POINTS_PER_WHOLE
    return int(share.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


class RewardService:
    """Calculate reward amounts based on referral configuration."""

    @staticmethod
    def flat_fee_micros(referral):
        """The flat fee a ``flat_fee`` referral pays — ONCE per referral, by
        the caller's invariant (the real-time handler's ``flat_fee_paid``, the
        reconciler's one ledger row carrying it)."""
        return int(referral.snapshot_reward_amount_micros or 0)

    @staticmethod
    def calculate_reward(referral, cost_micros, raw_cost_micros=None):
        """Calculate the reward for a single usage event.

        Args:
            referral: Referral instance with snapshotted reward config —
                ``snapshot_reward_amount_micros`` for a flat fee,
                ``snapshot_reward_share_basis_points`` (1..10000) for a share,
                ``snapshot_estimated_cost_basis_points`` (0..10000) as a profit
                share's fallback cost estimate.
            cost_micros: What the referred customer paid (revenue to tenant).
            raw_cost_micros: Tenant's actual cost (optional, for profit-share).

        Returns:
            int: Reward amount in micros (always >= 0).
        """
        reward_type = referral.snapshot_reward_type

        if reward_type == REWARD_TYPE_FLAT_FEE:
            return RewardService.flat_fee_micros(referral)

        share_bp = referral.snapshot_reward_share_basis_points
        if share_bp is None:
            return 0

        if reward_type == REWARD_TYPE_REVENUE_SHARE:
            return max(0, share_of(cost_micros, share_bp))

        if reward_type == REWARD_TYPE_PROFIT_SHARE:
            if raw_cost_micros is not None:
                profit = int(cost_micros) - int(raw_cost_micros)
            elif referral.snapshot_estimated_cost_basis_points is not None:
                estimated_cost = share_of(
                    cost_micros, referral.snapshot_estimated_cost_basis_points)
                profit = int(cost_micros) - estimated_cost
            else:
                return 0  # Cannot calculate profit, defer to batch

            if profit <= 0:
                return 0

            return max(0, share_of(profit, share_bp))

        return 0
