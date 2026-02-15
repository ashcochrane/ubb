import pytest
from decimal import Decimal

from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.referrals.models import Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator


def _create_referral_with_accumulator(tenant, earned_micros, last_payout_micros=0):
    """Helper: creates a referral chain and accumulator with given amounts."""
    referrer_cust = Customer.objects.create(
        tenant=tenant, external_id=f"referrer-{earned_micros}-{last_payout_micros}"
    )
    referred_cust = Customer.objects.create(
        tenant=tenant, external_id=f"referred-{earned_micros}-{last_payout_micros}"
    )
    referrer = Referrer.objects.create(tenant=tenant, customer=referrer_cust)
    referral = Referral.objects.create(
        tenant=tenant,
        referrer=referrer,
        referred_customer=referred_cust,
        referral_code_used=referrer.referral_code,
        snapshot_reward_type="revenue_share",
        snapshot_reward_value=Decimal("0.10"),
    )
    acc = ReferralRewardAccumulator.objects.create(
        referral=referral,
        total_earned_micros=earned_micros,
        last_payout_amount_micros=last_payout_micros,
    )
    return referral, acc


@pytest.mark.django_db
class TestEmitReferralPayoutsTask:
    def test_emits_payout_event_above_threshold(self):
        """Accumulator with >$1 unpaid earnings should emit a payout event."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="Payout", products=["metering", "referrals"])
        referral, acc = _create_referral_with_accumulator(
            tenant, earned_micros=5_000_000, last_payout_micros=0
        )

        emit_referral_payouts_task()

        events = OutboxEvent.objects.filter(event_type="referral.payout_due")
        assert events.count() == 1
        evt = events.first()
        assert evt.payload["referral_id"] == str(referral.id)
        assert evt.payload["payout_amount_micros"] == 5_000_000
        assert evt.payload["referrer_customer_id"] == str(referral.referrer.customer_id)

    def test_updates_accumulator_after_emission(self):
        """After emitting, last_payout_amount_micros should match total_earned_micros."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="Payout2", products=["metering", "referrals"])
        referral, acc = _create_referral_with_accumulator(
            tenant, earned_micros=3_000_000, last_payout_micros=0
        )

        emit_referral_payouts_task()

        acc.refresh_from_db()
        assert acc.last_payout_amount_micros == 3_000_000
        assert acc.last_payout_at is not None

    def test_skips_below_threshold(self):
        """Accumulator with <$1 unpaid earnings should NOT emit a payout event."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="BelowThreshold", products=["metering", "referrals"])
        _create_referral_with_accumulator(
            tenant, earned_micros=500_000, last_payout_micros=0  # $0.50 < $1
        )

        emit_referral_payouts_task()

        events = OutboxEvent.objects.filter(event_type="referral.payout_due")
        assert events.count() == 0

    def test_skips_already_paid(self):
        """Accumulator with all earnings already paid should NOT emit."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="AlreadyPaid", products=["metering", "referrals"])
        _create_referral_with_accumulator(
            tenant, earned_micros=5_000_000, last_payout_micros=5_000_000
        )

        emit_referral_payouts_task()

        events = OutboxEvent.objects.filter(event_type="referral.payout_due")
        assert events.count() == 0

    def test_idempotent_double_call(self):
        """Calling the task twice should only emit one event."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="Idempotent", products=["metering", "referrals"])
        _create_referral_with_accumulator(
            tenant, earned_micros=2_000_000, last_payout_micros=0
        )

        emit_referral_payouts_task()
        emit_referral_payouts_task()

        events = OutboxEvent.objects.filter(event_type="referral.payout_due")
        assert events.count() == 1

    def test_partial_payout_delta(self):
        """Only the delta since last payout should be emitted."""
        from apps.referrals.tasks import emit_referral_payouts_task

        tenant = Tenant.objects.create(name="Delta", products=["metering", "referrals"])
        referral, acc = _create_referral_with_accumulator(
            tenant, earned_micros=5_000_000, last_payout_micros=2_000_000
        )

        emit_referral_payouts_task()

        events = OutboxEvent.objects.filter(event_type="referral.payout_due")
        assert events.count() == 1
        assert events.first().payload["payout_amount_micros"] == 3_000_000

        acc.refresh_from_db()
        assert acc.last_payout_amount_micros == 5_000_000
