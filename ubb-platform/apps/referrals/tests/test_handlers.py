import pytest
from dataclasses import asdict
from unittest.mock import patch
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import UsageRecorded
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator
from apps.referrals.handlers import handle_usage_recorded_referrals


@pytest.mark.django_db
class TestUsageRecordedHandler:
    def _setup(self, reward_type="revenue_share", reward_value=0.10, **kwargs):
        tenant = Tenant.objects.create(
            name="test", products=["metering", "referrals"],
        )
        referrer_cust = Customer.objects.create(tenant=tenant, external_id="referrer")
        referred_cust = Customer.objects.create(tenant=tenant, external_id="referred")
        referrer = Referrer.objects.create(tenant=tenant, customer=referrer_cust)

        referral = Referral.objects.create(
            tenant=tenant, referrer=referrer, referred_customer=referred_cust,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type=reward_type,
            snapshot_reward_value=reward_value,
            **kwargs,
        )
        ReferralRewardAccumulator.objects.create(referral=referral)

        return tenant, referrer_cust, referred_cust, referral

    @patch("apps.platform.events.tasks.process_single_event")
    def test_accumulates_revenue_share(self, mock_task):
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 100_000
        assert acc.total_referred_spend_micros == 1_000_000
        assert acc.event_count == 1

    @patch("apps.platform.events.tasks.process_single_event")
    def test_accumulates_multiple_events(self, mock_task):
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        for i in range(3):
            handle_usage_recorded_referrals(f"evt-outbox-{i}", asdict(UsageRecorded(pricing_status_reason=None,
                tenant_id=tenant.id,
                customer_id=referred.id,
                cost_micros=500_000,
                event_type="api_call",
                event_id=f"evt-{i}",
            )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 150_000  # 3 * 50K
        assert acc.event_count == 3

    @patch("apps.platform.events.tasks.process_single_event")
    def test_flat_fee_paid_once(self, mock_task):
        tenant, _, referred, referral = self._setup("flat_fee", 5_000_000)

        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 5_000_000

        # Second event should not add more
        handle_usage_recorded_referrals("evt-outbox-2", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-2",
        )))

        acc.refresh_from_db()
        assert acc.total_earned_micros == 5_000_000  # Still 5M

    def test_skips_non_referred_customer(self):
        tenant = Tenant.objects.create(
            name="test", products=["metering", "referrals"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="nobody")

        # Should not raise
        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-1",
        )))

    def test_skips_zero_cost(self):
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=0,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0

    @patch("apps.platform.events.tasks.process_single_event")
    def test_respects_max_reward_cap(self, mock_task):
        tenant, _, referred, referral = self._setup(
            "revenue_share", 0.10,
            snapshot_max_reward_micros=150_000,
        )

        # First event: 100K reward (within cap)
        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 100_000

        # Second event: would be 100K but cap allows only 50K more
        handle_usage_recorded_referrals("evt-outbox-2", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-2",
        )))

        acc.refresh_from_db()
        assert acc.total_earned_micros == 150_000  # Capped

    @patch("apps.platform.events.tasks.process_single_event")
    def test_cap_enforcement_under_lock(self, mock_task):
        """Cap check uses select_for_update to prevent over-cap payouts."""
        tenant, _, referred, referral = self._setup(
            "revenue_share", 0.10,
            snapshot_max_reward_micros=120_000,
        )

        # First event: 10% of 1M = 100K (within 120K cap)
        handle_usage_recorded_referrals("evt-outbox-cap-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-cap-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 100_000

        # Second event: would be 100K but only 20K remaining under cap
        handle_usage_recorded_referrals("evt-outbox-cap-2", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-cap-2",
        )))

        acc.refresh_from_db()
        assert acc.total_earned_micros == 120_000  # Capped at 120K, not 200K

    @patch("apps.platform.events.tasks.process_single_event")
    def test_profit_share_with_raw_cost(self, mock_task):
        tenant, _, referred, referral = self._setup("profit_share", 0.50)

        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            provider_cost_micros=200_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        # Profit = 800K, reward = 400K
        assert acc.total_earned_micros == 400_000

    def test_expired_referral_skipped(self):
        tenant, _, referred, referral = self._setup(
            "revenue_share", 0.10,
            reward_window_ends_at=timezone.now() - timezone.timedelta(days=1),
        )

        handle_usage_recorded_referrals("evt-outbox-1", asdict(UsageRecorded(pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=1_000_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        # Referral should be marked expired
        referral.refresh_from_db()
        assert referral.status == "expired"

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0

    def test_an_unpriced_posting_is_no_referred_spend_and_raises_nothing(self):
        """Folded into #603: `None <= 0` was a `TypeError` in this outbox
        handler for every posting whose price UBB did not resolve — the
        defect #351 fixed in billing's handler and never here."""
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        handle_usage_recorded_referrals("evt-outbox-u", asdict(UsageRecorded(
            pricing_status_reason=None,
            tenant_id=tenant.id,
            customer_id=referred.id,
            cost_micros=None,
            billed_cost_micros=None,
            pricing_status="unknown",
            event_type="api_call",
            event_id="evt-u",
        )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0
        assert acc.total_referred_spend_micros == 0
        assert acc.event_count == 0

    def test_a_negative_known_price_is_refused_by_name_and_rewards_nothing(self):
        """UBB never writes one (a negative calculated price is `unknown`
        with its reason); rewarding it would reverse a referrer's reward,
        negative money v1 does not carry (ADR-0020 §5)."""
        from core.money import NegativeKnownPriceRefused
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        with pytest.raises(NegativeKnownPriceRefused, match="below zero"):
            handle_usage_recorded_referrals("evt-outbox-n", asdict(UsageRecorded(
                pricing_status_reason=None,
                tenant_id=tenant.id,
                customer_id=referred.id,
                cost_micros=-1_000_000,
                billed_cost_micros=-1_000_000,
                event_type="api_call",
                event_id="evt-n",
            )))

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0
        assert acc.total_referred_spend_micros == 0
        assert acc.event_count == 0
