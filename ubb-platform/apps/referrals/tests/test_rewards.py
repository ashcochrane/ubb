import pytest
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock

from django.db import IntegrityError

from apps.referrals.rewards.models import ReferralRewardLedger
from apps.referrals.rewards.services import RewardService


class TestRewardCalculation:
    def _make_referral(self, reward_type, reward_value,
                       max_reward_micros=None, estimated_cost_pct=None):
        ref = MagicMock()
        ref.snapshot_reward_type = reward_type
        ref.snapshot_reward_value = Decimal(str(reward_value))
        ref.snapshot_max_reward_micros = max_reward_micros
        ref.snapshot_estimated_cost_percentage = (
            Decimal(str(estimated_cost_pct)) if estimated_cost_pct is not None else None
        )
        return ref

    def test_flat_fee(self):
        ref = self._make_referral("flat_fee", 5_000_000)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 5_000_000

    def test_revenue_share_10_percent(self):
        ref = self._make_referral("revenue_share", 0.10)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 100_000

    def test_revenue_share_50_percent(self):
        ref = self._make_referral("revenue_share", 0.50)
        reward = RewardService.calculate_reward(ref, cost_micros=2_000_000)
        assert reward == 1_000_000

    def test_profit_share_with_actual_cost(self):
        ref = self._make_referral("profit_share", 0.50)
        # Customer pays 1M, tenant cost is 200K, profit = 800K, reward = 400K
        reward = RewardService.calculate_reward(
            ref, cost_micros=1_000_000, raw_cost_micros=200_000
        )
        assert reward == 400_000

    def test_profit_share_with_estimated_cost(self):
        ref = self._make_referral("profit_share", 0.50, estimated_cost_pct=0.20)
        # Customer pays 1M, estimated cost = 200K, profit = 800K, reward = 400K
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 400_000

    def test_profit_share_no_cost_data_returns_zero(self):
        ref = self._make_referral("profit_share", 0.50)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 0

    def test_profit_share_negative_profit_returns_zero(self):
        ref = self._make_referral("profit_share", 0.50)
        # Cost exceeds revenue
        reward = RewardService.calculate_reward(
            ref, cost_micros=100_000, raw_cost_micros=200_000
        )
        assert reward == 0

    def test_revenue_share_zero_cost(self):
        ref = self._make_referral("revenue_share", 0.10)
        reward = RewardService.calculate_reward(ref, cost_micros=0)
        assert reward == 0

    def test_unknown_type_returns_zero(self):
        ref = self._make_referral("unknown_type", 0.10)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 0


@pytest.mark.django_db
class TestReferralRewardLedgerConstraints:
    def test_duplicate_ledger_entry_raises_integrity_error(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.referrals.models import Referral, Referrer

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        referrer_customer = Customer.objects.create(tenant=tenant, external_id="referrer")
        referred_customer = Customer.objects.create(tenant=tenant, external_id="referred")
        referrer = Referrer.objects.create(tenant=tenant, customer=referrer_customer)
        referral = Referral.objects.create(
            tenant=tenant,
            referrer=referrer,
            referred_customer=referred_customer,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type="revenue_share",
            snapshot_reward_value=Decimal("0.10"),
        )

        ReferralRewardLedger.objects.create(
            referral=referral,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            referred_spend_micros=1_000_000,
            reward_micros=100_000,
            calculation_method="actual_cost",
        )

        with pytest.raises(IntegrityError):
            ReferralRewardLedger.objects.create(
                referral=referral,
                period_start=date(2026, 1, 1),
                period_end=date(2026, 3, 1),
                referred_spend_micros=2_000_000,
                reward_micros=200_000,
                calculation_method="actual_cost",
            )
