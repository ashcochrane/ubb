import pytest
from unittest.mock import patch
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
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

        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 100_000
        assert acc.total_referred_spend_micros == 1_000_000
        assert acc.event_count == 1

    @patch("apps.platform.events.tasks.process_single_event")
    def test_accumulates_multiple_events(self, mock_task):
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        for i in range(3):
            handle_usage_recorded_referrals(f"evt-outbox-{i}", {
                "tenant_id": str(tenant.id),
                "customer_id": str(referred.id),
                "cost_micros": 500_000,
                "event_type": "api_call",
                "event_id": f"evt-{i}",
            })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 150_000  # 3 * 50K
        assert acc.event_count == 3

    @patch("apps.platform.events.tasks.process_single_event")
    def test_flat_fee_paid_once(self, mock_task):
        tenant, _, referred, referral = self._setup("flat_fee", 5_000_000)

        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 5_000_000

        # Second event should not add more
        handle_usage_recorded_referrals("evt-outbox-2", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-2",
        })

        acc.refresh_from_db()
        assert acc.total_earned_micros == 5_000_000  # Still 5M

    def test_skips_non_referred_customer(self):
        tenant = Tenant.objects.create(
            name="test", products=["metering", "referrals"],
        )
        customer = Customer.objects.create(tenant=tenant, external_id="nobody")

        # Should not raise
        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

    def test_skips_zero_cost(self):
        tenant, _, referred, referral = self._setup("revenue_share", 0.10)

        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 0,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0

    @patch("apps.platform.events.tasks.process_single_event")
    def test_respects_max_reward_cap(self, mock_task):
        tenant, _, referred, referral = self._setup(
            "revenue_share", 0.10,
            snapshot_max_reward_micros=150_000,
        )

        # First event: 100K reward (within cap)
        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 100_000

        # Second event: would be 100K but cap allows only 50K more
        handle_usage_recorded_referrals("evt-outbox-2", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-2",
        })

        acc.refresh_from_db()
        assert acc.total_earned_micros == 150_000  # Capped

    @patch("apps.platform.events.tasks.process_single_event")
    def test_profit_share_with_raw_cost(self, mock_task):
        tenant, _, referred, referral = self._setup("profit_share", 0.50)

        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "raw_cost_micros": 200_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        # Profit = 800K, reward = 400K
        assert acc.total_earned_micros == 400_000

    def test_expired_referral_skipped(self):
        tenant, _, referred, referral = self._setup(
            "revenue_share", 0.10,
            reward_window_ends_at=timezone.now() - timezone.timedelta(days=1),
        )

        handle_usage_recorded_referrals("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(referred.id),
            "cost_micros": 1_000_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        # Referral should be marked expired
        referral.refresh_from_db()
        assert referral.status == "expired"

        acc = ReferralRewardAccumulator.objects.get(referral=referral)
        assert acc.total_earned_micros == 0
