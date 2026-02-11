import json

from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator


class ReferralsEndpointTestBase(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="test-tenant", products=["metering", "referrals"],
        )
        _, self.api_key = TenantApiKey.create_key(tenant=self.tenant, label="test")
        self.headers = {"HTTP_AUTHORIZATION": f"Bearer {self.api_key}"}


class TestProgramEndpoints(ReferralsEndpointTestBase):
    def test_create_program(self):
        resp = self.http_client.post(
            "/api/v1/referrals/program",
            data=json.dumps({
                "reward_type": "revenue_share",
                "reward_value": 0.10,
                "attribution_window_days": 30,
                "reward_window_days": 365,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["reward_type"], "revenue_share")
        self.assertEqual(body["status"], "active")

    def test_get_program(self):
        ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="flat_fee", reward_value=5_000_000,
        )
        resp = self.http_client.get(
            "/api/v1/referrals/program", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["reward_type"], "flat_fee")

    def test_get_program_404_when_none(self):
        resp = self.http_client.get(
            "/api/v1/referrals/program", **self.headers,
        )
        self.assertEqual(resp.status_code, 404)

    def test_update_program(self):
        ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="revenue_share", reward_value=0.10,
        )
        resp = self.http_client.patch(
            "/api/v1/referrals/program",
            data=json.dumps({"reward_value": 0.20}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertAlmostEqual(resp.json()["reward_value"], 0.20)

    def test_deactivate_program(self):
        ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="flat_fee", reward_value=1_000_000,
        )
        resp = self.http_client.delete(
            "/api/v1/referrals/program", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "deactivated")

    def test_reactivate_program(self):
        program = ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="flat_fee", reward_value=1_000_000,
            status="deactivated",
        )
        resp = self.http_client.post(
            "/api/v1/referrals/program/reactivate", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "active")

    def test_duplicate_program_409(self):
        ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="flat_fee", reward_value=1_000_000,
        )
        resp = self.http_client.post(
            "/api/v1/referrals/program",
            data=json.dumps({
                "reward_type": "revenue_share",
                "reward_value": 0.10,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)


class TestReferrerEndpoints(ReferralsEndpointTestBase):
    def setUp(self):
        super().setUp()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="revenue_share", reward_value=0.10,
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="cust-1",
        )

    def test_register_referrer(self):
        resp = self.http_client.post(
            "/api/v1/referrals/referrers",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["referral_code"].startswith("REF-"))
        self.assertTrue(body["is_active"])

    def test_register_duplicate_409(self):
        Referrer.objects.create(tenant=self.tenant, customer=self.customer)
        resp = self.http_client.post(
            "/api/v1/referrals/referrers",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)

    def test_get_referrer(self):
        Referrer.objects.create(tenant=self.tenant, customer=self.customer)
        resp = self.http_client.get(
            f"/api/v1/referrals/referrers/{self.customer.id}",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["customer_id"], str(self.customer.id))

    def test_list_referrers(self):
        Referrer.objects.create(tenant=self.tenant, customer=self.customer)
        resp = self.http_client.get(
            "/api/v1/referrals/referrers", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 1)


class TestAttributionEndpoint(ReferralsEndpointTestBase):
    def setUp(self):
        super().setUp()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="revenue_share", reward_value=0.10,
            reward_window_days=365,
        )
        self.referrer_customer = Customer.objects.create(
            tenant=self.tenant, external_id="referrer",
        )
        self.referrer = Referrer.objects.create(
            tenant=self.tenant, customer=self.referrer_customer,
        )
        self.referred_customer = Customer.objects.create(
            tenant=self.tenant, external_id="referred",
        )

    def test_attribute_with_code(self):
        resp = self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referred_customer.id),
                "code": self.referrer.referral_code,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "active")
        self.assertEqual(body["referred_customer_id"], str(self.referred_customer.id))

    def test_attribute_with_link_token(self):
        resp = self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referred_customer.id),
                "link_token": self.referrer.referral_link_token,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)

    def test_attribute_missing_code_and_token(self):
        resp = self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referred_customer.id),
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 400)

    def test_self_referral_rejected(self):
        resp = self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referrer_customer.id),
                "code": self.referrer.referral_code,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 400)

    def test_duplicate_referral_409(self):
        self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referred_customer.id),
                "code": self.referrer.referral_code,
            }),
            content_type="application/json",
            **self.headers,
        )
        resp = self.http_client.post(
            "/api/v1/referrals/attribute",
            data=json.dumps({
                "customer_id": str(self.referred_customer.id),
                "code": self.referrer.referral_code,
            }),
            content_type="application/json",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)


class TestRewardEndpoints(ReferralsEndpointTestBase):
    def setUp(self):
        super().setUp()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="revenue_share", reward_value=0.10,
        )
        self.referrer_customer = Customer.objects.create(
            tenant=self.tenant, external_id="referrer",
        )
        self.referrer = Referrer.objects.create(
            tenant=self.tenant, customer=self.referrer_customer,
        )
        self.referred = Customer.objects.create(
            tenant=self.tenant, external_id="referred",
        )
        self.referral = Referral.objects.create(
            tenant=self.tenant, referrer=self.referrer,
            referred_customer=self.referred,
            referral_code_used=self.referrer.referral_code,
            snapshot_reward_type="revenue_share",
            snapshot_reward_value=0.10,
        )
        ReferralRewardAccumulator.objects.create(
            referral=self.referral,
            total_earned_micros=500_000,
            total_referred_spend_micros=5_000_000,
            event_count=10,
        )

    def test_get_earnings(self):
        resp = self.http_client.get(
            f"/api/v1/referrals/referrers/{self.referrer_customer.id}/earnings",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_earned_micros"], 500_000)
        self.assertEqual(body["total_referrals"], 1)

    def test_get_referrals(self):
        resp = self.http_client.get(
            f"/api/v1/referrals/referrers/{self.referrer_customer.id}/referrals",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        data = resp.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["total_earned_micros"], 500_000)

    def test_get_ledger_empty(self):
        resp = self.http_client.get(
            f"/api/v1/referrals/referrals/{self.referral.id}/ledger",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["data"]), 0)


class TestRevocationEndpoint(ReferralsEndpointTestBase):
    def test_revoke_referral(self):
        referrer_cust = Customer.objects.create(
            tenant=self.tenant, external_id="r",
        )
        referred_cust = Customer.objects.create(
            tenant=self.tenant, external_id="ref",
        )
        referrer = Referrer.objects.create(
            tenant=self.tenant, customer=referrer_cust,
        )
        referral = Referral.objects.create(
            tenant=self.tenant, referrer=referrer,
            referred_customer=referred_cust,
            referral_code_used="REF-X",
            snapshot_reward_type="flat_fee", snapshot_reward_value=1000,
        )

        resp = self.http_client.delete(
            f"/api/v1/referrals/referrals/{referral.id}",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "revoked")

        # Double revoke = 409
        resp = self.http_client.delete(
            f"/api/v1/referrals/referrals/{referral.id}",
            **self.headers,
        )
        self.assertEqual(resp.status_code, 409)


class TestAnalyticsEndpoints(ReferralsEndpointTestBase):
    def test_analytics_summary_empty(self):
        resp = self.http_client.get(
            "/api/v1/referrals/analytics/summary", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["total_referrers"], 0)
        self.assertEqual(body["total_referrals"], 0)

    def test_analytics_earnings_empty(self):
        resp = self.http_client.get(
            "/api/v1/referrals/analytics/earnings", **self.headers,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.json()["referrers"]), 0)
