import pytest
from django.test import Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator


@pytest.mark.django_db
class TestPayoutExport:
    def setup_method(self):
        self.tenant = Tenant.objects.create(
            name="test", products=["metering", "referrals"],
        )
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()

    def test_payout_export_returns_referrers_with_earnings(self):
        referrer_cust = Customer.objects.create(tenant=self.tenant, external_id="referrer1")
        referred_cust = Customer.objects.create(tenant=self.tenant, external_id="referred1")
        referrer = Referrer.objects.create(tenant=self.tenant, customer=referrer_cust)
        referral = Referral.objects.create(
            tenant=self.tenant, referrer=referrer, referred_customer=referred_cust,
            referral_code_used=referrer.referral_code,
            snapshot_reward_type="revenue_share", snapshot_reward_value=0.10,
        )
        ReferralRewardAccumulator.objects.create(
            referral=referral, total_earned_micros=500_000, total_referred_spend_micros=5_000_000, event_count=10,
        )

        resp = self.client.get(
            "/api/v1/referrals/payouts/export",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referrer_count"] == 1
        assert data["total_payout_micros"] == 500_000
        assert len(data["data"]) == 1
        assert data["data"][0]["external_id"] == "referrer1"
        assert data["data"][0]["referral_code"] == referrer.referral_code
        assert data["data"][0]["total_earned_micros"] == 500_000
        assert data["data"][0]["total_referred_spend_micros"] == 5_000_000
        assert data["data"][0]["referral_count"] == 1
        assert data["data"][0]["active_referral_count"] == 1
        assert "exported_at" in data

    def test_payout_export_excludes_zero_earnings(self):
        referrer_cust = Customer.objects.create(tenant=self.tenant, external_id="referrer1")
        Referrer.objects.create(tenant=self.tenant, customer=referrer_cust)
        # No referrals/earnings

        resp = self.client.get(
            "/api/v1/referrals/payouts/export",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referrer_count"] == 0
        assert data["total_payout_micros"] == 0
        assert len(data["data"]) == 0

    def test_payout_export_multiple_referrers(self):
        """Multiple referrers with earnings are all included."""
        referrer_cust1 = Customer.objects.create(tenant=self.tenant, external_id="referrer1")
        referrer_cust2 = Customer.objects.create(tenant=self.tenant, external_id="referrer2")
        referred_cust1 = Customer.objects.create(tenant=self.tenant, external_id="referred1")
        referred_cust2 = Customer.objects.create(tenant=self.tenant, external_id="referred2")

        referrer1 = Referrer.objects.create(tenant=self.tenant, customer=referrer_cust1)
        referrer2 = Referrer.objects.create(tenant=self.tenant, customer=referrer_cust2)

        referral1 = Referral.objects.create(
            tenant=self.tenant, referrer=referrer1, referred_customer=referred_cust1,
            referral_code_used=referrer1.referral_code,
            snapshot_reward_type="revenue_share", snapshot_reward_value=0.10,
        )
        referral2 = Referral.objects.create(
            tenant=self.tenant, referrer=referrer2, referred_customer=referred_cust2,
            referral_code_used=referrer2.referral_code,
            snapshot_reward_type="revenue_share", snapshot_reward_value=0.10,
        )

        ReferralRewardAccumulator.objects.create(
            referral=referral1, total_earned_micros=300_000,
            total_referred_spend_micros=3_000_000, event_count=5,
        )
        ReferralRewardAccumulator.objects.create(
            referral=referral2, total_earned_micros=700_000,
            total_referred_spend_micros=7_000_000, event_count=15,
        )

        resp = self.client.get(
            "/api/v1/referrals/payouts/export",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referrer_count"] == 2
        assert data["total_payout_micros"] == 1_000_000
        assert len(data["data"]) == 2

    def test_payout_export_tenant_isolation(self):
        """Referrers from other tenants are not included."""
        other_tenant = Tenant.objects.create(
            name="other", products=["metering", "referrals"],
        )
        other_cust = Customer.objects.create(tenant=other_tenant, external_id="other-ref")
        other_referrer = Referrer.objects.create(tenant=other_tenant, customer=other_cust)
        other_referred = Customer.objects.create(tenant=other_tenant, external_id="other-referred")
        other_referral = Referral.objects.create(
            tenant=other_tenant, referrer=other_referrer, referred_customer=other_referred,
            referral_code_used=other_referrer.referral_code,
            snapshot_reward_type="revenue_share", snapshot_reward_value=0.10,
        )
        ReferralRewardAccumulator.objects.create(
            referral=other_referral, total_earned_micros=999_000,
            total_referred_spend_micros=9_990_000, event_count=50,
        )

        resp = self.client.get(
            "/api/v1/referrals/payouts/export",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["referrer_count"] == 0
        assert data["total_payout_micros"] == 0
