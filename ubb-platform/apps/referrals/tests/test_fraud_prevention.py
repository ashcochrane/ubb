import pytest
from unittest.mock import patch
from datetime import timedelta
from django.test import Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator


@pytest.mark.django_db
class TestVelocityLimit:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant,
            reward_type="revenue_share",
            reward_value=0.10,
            max_referrals_per_day=2,
        )
        referrer_cust = Customer.objects.create(tenant=self.tenant, external_id="referrer")
        self.referrer = Referrer.objects.create(tenant=self.tenant, customer=referrer_cust)

    def test_allows_within_limit(self):
        # First referral should succeed
        cust = Customer.objects.create(tenant=self.tenant, external_id="referred1")
        resp = self.client.post(
            "/api/v1/referrals/attribute",
            data={"customer_id": str(cust.id), "code": self.referrer.referral_code},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200

    @patch("apps.platform.events.tasks.process_single_event")
    def test_blocks_when_limit_exceeded(self, mock_task):
        # Create 2 referrals (at the limit)
        for i in range(2):
            cust = Customer.objects.create(tenant=self.tenant, external_id=f"r{i}")
            Referral.objects.create(
                tenant=self.tenant, referrer=self.referrer, referred_customer=cust,
                referral_code_used=self.referrer.referral_code,
                snapshot_reward_type="revenue_share", snapshot_reward_value=0.10,
            )
            ReferralRewardAccumulator.objects.create(
                referral=Referral.objects.get(referred_customer=cust),
            )

        # Third should be blocked
        cust3 = Customer.objects.create(tenant=self.tenant, external_id="r2")
        resp = self.client.post(
            "/api/v1/referrals/attribute",
            data={"customer_id": str(cust3.id), "code": self.referrer.referral_code},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 429


@pytest.mark.django_db
class TestCustomerAgeCheck:
    def setup_method(self):
        self.tenant = Tenant.objects.create(name="test", products=["metering", "referrals"])
        _, self.raw_key = TenantApiKey.create_key(self.tenant)
        self.client = Client()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant,
            reward_type="revenue_share",
            reward_value=0.10,
            min_customer_age_hours=24,
        )
        referrer_cust = Customer.objects.create(tenant=self.tenant, external_id="referrer")
        self.referrer = Referrer.objects.create(tenant=self.tenant, customer=referrer_cust)

    def test_blocks_new_customer(self):
        # Customer just created (age ~ 0 hours)
        cust = Customer.objects.create(tenant=self.tenant, external_id="new-cust")
        resp = self.client.post(
            "/api/v1/referrals/attribute",
            data={"customer_id": str(cust.id), "code": self.referrer.referral_code},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 400
        assert "too new" in resp.json().get("detail", "")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_allows_old_customer(self, mock_task):
        cust = Customer.objects.create(tenant=self.tenant, external_id="old-cust")
        # Manually set created_at to 25 hours ago
        Customer.objects.filter(id=cust.id).update(
            created_at=timezone.now() - timedelta(hours=25)
        )
        cust.refresh_from_db()

        resp = self.client.post(
            "/api/v1/referrals/attribute",
            data={"customer_id": str(cust.id), "code": self.referrer.referral_code},
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        assert resp.status_code == 200
