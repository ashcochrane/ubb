import pytest
from django.db import IntegrityError
from django.utils import timezone

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator, ReferralRewardLedger


@pytest.mark.django_db
class TestReferralProgram:
    def test_create_program(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        program = ReferralProgram.objects.create(
            tenant=tenant,
            reward_type="revenue_share",
            reward_value=0.10,
        )
        program.refresh_from_db()
        assert program.reward_type == "revenue_share"
        assert program.status == "active"
        assert program.attribution_window_days == 30

    def test_one_program_per_tenant(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        ReferralProgram.objects.create(
            tenant=tenant, reward_type="flat_fee", reward_value=1_000_000,
        )
        with pytest.raises(IntegrityError):
            ReferralProgram.objects.create(
                tenant=tenant, reward_type="revenue_share", reward_value=0.10,
            )


@pytest.mark.django_db
class TestReferrer:
    def test_create_referrer(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        referrer = Referrer.objects.create(tenant=tenant, customer=customer)
        referrer.refresh_from_db()
        assert referrer.referral_code.startswith("REF-")
        assert len(referrer.referral_link_token) > 10
        assert referrer.is_active is True

    def test_one_referrer_per_customer(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")
        Referrer.objects.create(tenant=tenant, customer=customer)
        with pytest.raises(IntegrityError):
            Referrer.objects.create(tenant=tenant, customer=customer)

    def test_unique_referral_codes(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        c1 = Customer.objects.create(tenant=tenant, external_id="cust-1")
        c2 = Customer.objects.create(tenant=tenant, external_id="cust-2")
        r1 = Referrer.objects.create(tenant=tenant, customer=c1)
        r2 = Referrer.objects.create(tenant=tenant, customer=c2)
        assert r1.referral_code != r2.referral_code


@pytest.mark.django_db
class TestReferral:
    def _setup(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        referrer_customer = Customer.objects.create(tenant=tenant, external_id="referrer")
        referred_customer = Customer.objects.create(tenant=tenant, external_id="referred")
        referrer = Referrer.objects.create(tenant=tenant, customer=referrer_customer)
        return tenant, referrer, referred_customer

    def test_create_referral(self):
        tenant, referrer, referred = self._setup()
        referral = Referral.objects.create(
            tenant=tenant,
            referrer=referrer,
            referred_customer=referred,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type="revenue_share",
            snapshot_reward_value=0.10,
        )
        referral.refresh_from_db()
        assert referral.status == "active"
        assert referral.flat_fee_paid is False

    def test_unique_referred_customer_per_tenant(self):
        tenant, referrer, referred = self._setup()
        Referral.objects.create(
            tenant=tenant, referrer=referrer, referred_customer=referred,
            referral_code_used="REF-X",
            snapshot_reward_type="flat_fee", snapshot_reward_value=1000,
        )
        # Another referrer in same tenant can't refer the same customer
        c3 = Customer.objects.create(tenant=tenant, external_id="referrer2")
        referrer2 = Referrer.objects.create(tenant=tenant, customer=c3)
        with pytest.raises(IntegrityError):
            Referral.objects.create(
                tenant=tenant, referrer=referrer2, referred_customer=referred,
                referral_code_used="REF-Y",
                snapshot_reward_type="flat_fee", snapshot_reward_value=1000,
            )

    def test_snapshot_preserves_config(self):
        tenant, referrer, referred = self._setup()
        referral = Referral.objects.create(
            tenant=tenant, referrer=referrer, referred_customer=referred,
            referral_code_used="REF-X",
            snapshot_reward_type="profit_share",
            snapshot_reward_value=0.50,
            snapshot_max_reward_micros=100_000_000,
            snapshot_estimated_cost_percentage=0.20,
        )
        referral.refresh_from_db()
        assert referral.snapshot_reward_type == "profit_share"
        assert float(referral.snapshot_reward_value) == 0.50
        assert referral.snapshot_max_reward_micros == 100_000_000
        assert float(referral.snapshot_estimated_cost_percentage) == 0.20


@pytest.mark.django_db
class TestRewardAccumulator:
    def test_create_accumulator(self):
        tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        c1 = Customer.objects.create(tenant=tenant, external_id="r")
        c2 = Customer.objects.create(tenant=tenant, external_id="ref")
        referrer = Referrer.objects.create(tenant=tenant, customer=c1)
        referral = Referral.objects.create(
            tenant=tenant, referrer=referrer, referred_customer=c2,
            referral_code_used="REF-X",
            snapshot_reward_type="flat_fee", snapshot_reward_value=1000,
        )
        acc = ReferralRewardAccumulator.objects.create(referral=referral)
        assert acc.total_earned_micros == 0
        assert acc.event_count == 0
