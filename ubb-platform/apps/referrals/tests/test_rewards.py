import pytest
from datetime import date
from unittest.mock import MagicMock, patch

from django.db import IntegrityError

from apps.referrals.rewards.models import ReferralRewardLedger
from apps.referrals.rewards.services import RewardService


class TestRewardCalculation:
    def _make_referral(self, reward_type, amount_micros=None, share_bp=None,
                       max_reward_micros=None, estimated_cost_bp=None):
        ref = MagicMock()
        ref.snapshot_reward_type = reward_type
        ref.snapshot_reward_amount_micros = amount_micros
        ref.snapshot_reward_share_basis_points = share_bp
        ref.snapshot_max_reward_micros = max_reward_micros
        ref.snapshot_estimated_cost_basis_points = estimated_cost_bp
        return ref

    def test_flat_fee(self):
        ref = self._make_referral("flat_fee", amount_micros=5_000_000)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 5_000_000

    def test_revenue_share_10_percent(self):
        ref = self._make_referral("revenue_share", share_bp=1000)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 100_000

    def test_revenue_share_50_percent(self):
        ref = self._make_referral("revenue_share", share_bp=5000)
        reward = RewardService.calculate_reward(ref, cost_micros=2_000_000)
        assert reward == 1_000_000

    def test_profit_share_with_actual_cost(self):
        ref = self._make_referral("profit_share", share_bp=5000)
        # Customer pays 1M, tenant cost is 200K, profit = 800K, reward = 400K
        reward = RewardService.calculate_reward(
            ref, cost_micros=1_000_000, raw_cost_micros=200_000
        )
        assert reward == 400_000

    def test_profit_share_with_estimated_cost(self):
        ref = self._make_referral("profit_share", share_bp=5000,
                                  estimated_cost_bp=2000)
        # Customer pays 1M, estimated cost = 200K, profit = 800K, reward = 400K
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 400_000

    def test_profit_share_no_cost_data_returns_zero(self):
        ref = self._make_referral("profit_share", share_bp=5000)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 0

    def test_profit_share_negative_profit_returns_zero(self):
        ref = self._make_referral("profit_share", share_bp=5000)
        # Cost exceeds revenue
        reward = RewardService.calculate_reward(
            ref, cost_micros=100_000, raw_cost_micros=200_000
        )
        assert reward == 0

    def test_revenue_share_zero_cost(self):
        ref = self._make_referral("revenue_share", share_bp=1000)
        reward = RewardService.calculate_reward(ref, cost_micros=0)
        assert reward == 0

    def test_unknown_type_returns_zero(self):
        ref = self._make_referral("unknown_type", share_bp=1000)
        reward = RewardService.calculate_reward(ref, cost_micros=1_000_000)
        assert reward == 0

    def test_ten_percent_entered_as_basis_points_pays_ten_percent(self):
        ten = self._make_referral("revenue_share", share_bp=1000)
        assert RewardService.calculate_reward(ten, cost_micros=1_000_000) == 100_000
        half = self._make_referral("revenue_share", share_bp=5000)
        assert RewardService.calculate_reward(half, cost_micros=1_000_000) == 500_000
        whole = self._make_referral("revenue_share", share_bp=10000)
        assert RewardService.calculate_reward(whole, cost_micros=1_000_000) == 1_000_000

    def test_a_share_divides_by_ten_thousand_exactly(self):
        odd = self._make_referral("revenue_share", share_bp=3333)
        assert RewardService.calculate_reward(odd, cost_micros=1_000_000) == 333_300
        one = self._make_referral("revenue_share", share_bp=1)
        assert RewardService.calculate_reward(one, cost_micros=1_000_000) == 100
        # 0.0001 of one micro rounds half-up to a whole micro: 0.
        assert RewardService.calculate_reward(one, cost_micros=1) == 0


@pytest.mark.django_db
class TestFlatFeeReconciledOnce:
    def _event(self):
        return {"billed_cost_micros": 1_000_000, "pricing_status": "known",
                "provider_cost_micros": None, "costing_status": "not_applicable"}

    def test_a_flat_fee_is_reconciled_once_over_three_events(self):
        from apps.platform.tenants.models import Tenant
        from apps.platform.customers.models import Customer
        from apps.referrals.models import Referral, Referrer
        from apps.referrals.rewards.reconciliation import reconcile_referral

        tenant = Tenant.objects.create(name="Test", products=["metering"])
        referrer_customer = Customer.objects.create(tenant=tenant, external_id="referrer")
        referred_customer = Customer.objects.create(tenant=tenant, external_id="referred")
        referrer = Referrer.objects.create(tenant=tenant, customer=referrer_customer)
        referral = Referral.objects.create(
            tenant=tenant, referrer=referrer, referred_customer=referred_customer,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type="flat_fee",
            snapshot_reward_amount_micros=5_000_000,
        )

        target = "apps.metering.queries.get_customer_postings_for_period"
        with patch(target, return_value=[self._event(), self._event(), self._event()]):
            first = reconcile_referral(referral, date(2026, 1, 1), date(2026, 2, 1))

        assert first.reward_micros == 5_000_000
        assert ReferralRewardLedger.objects.filter(referral=referral).count() == 1
        referral.refresh_from_db()
        assert referral.flat_fee_paid is True

        with patch(target, return_value=[self._event()]):
            second = reconcile_referral(referral, date(2026, 2, 1), date(2026, 3, 1))

        assert second.reward_micros == 0
        assert ReferralRewardLedger.objects.filter(referral=referral).count() == 2


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
            snapshot_reward_share_basis_points=1000,
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
