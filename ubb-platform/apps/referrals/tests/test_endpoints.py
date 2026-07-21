import json
from datetime import timedelta

from django.test import TestCase, Client
from django.utils import timezone

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.referrals.models import ReferralProgram, Referrer, Referral
from apps.referrals.rewards.models import ReferralRewardAccumulator, ReferralRewardLedger
from apps.referrals.tests._helpers import assert_problem


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
        assert_problem(resp, "not_found", 404)

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
        assert_problem(resp, "conflict", 409)


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
        assert_problem(resp, "conflict", 409)

    def test_register_without_program_422(self):
        self.program.status = "deactivated"
        self.program.save(update_fields=["status", "updated_at"])
        resp = self.http_client.post(
            "/api/v1/referrals/referrers",
            data=json.dumps({"customer_id": str(self.customer.id)}),
            content_type="application/json",
            **self.headers,
        )
        assert_problem(resp, "validation_error", 422)

    def test_list_referrers_invalid_cursor(self):
        resp = self.http_client.get(
            "/api/v1/referrals/referrers?cursor=not-a-cursor", **self.headers,
        )
        assert_problem(resp, "invalid_cursor", 400)

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
        assert_problem(resp, "validation_error", 422)

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
        assert_problem(resp, "validation_error", 422)

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
        assert_problem(resp, "conflict", 409)


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

    def test_get_referrals_invalid_cursor(self):
        resp = self.http_client.get(
            f"/api/v1/referrals/referrers/{self.referrer_customer.id}/referrals"
            "?cursor=not-a-cursor",
            **self.headers,
        )
        assert_problem(resp, "invalid_cursor", 400)

    def test_get_ledger_invalid_cursor(self):
        resp = self.http_client.get(
            f"/api/v1/referrals/referrals/{self.referral.id}/ledger"
            "?cursor=not-a-cursor",
            **self.headers,
        )
        assert_problem(resp, "invalid_cursor", 400)


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
        assert_problem(resp, "conflict", 409)


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


class TestAnalyticsEarningsWindow(ReferralsEndpointTestBase):
    """The period_start/period_end params are applied, not echoed: windowed
    earnings come from the reconciliation ledger."""

    def setUp(self):
        super().setUp()
        self.program = ReferralProgram.objects.create(
            tenant=self.tenant, reward_type="revenue_share", reward_value=0.10,
        )
        referrer_cust = Customer.objects.create(
            tenant=self.tenant, external_id="referrer",
        )
        self.referrer = Referrer.objects.create(
            tenant=self.tenant, customer=referrer_cust,
        )
        referred = Customer.objects.create(
            tenant=self.tenant, external_id="referred",
        )
        self.referral = Referral.objects.create(
            tenant=self.tenant, referrer=self.referrer,
            referred_customer=referred,
            referral_code_used=self.referrer.referral_code,
            snapshot_reward_type="revenue_share",
            snapshot_reward_value=0.10,
        )
        # All-time accumulator total deliberately disagrees with every window
        # to prove windowed earnings are ledger-sourced.
        ReferralRewardAccumulator.objects.create(
            referral=self.referral,
            total_earned_micros=999_999_999,
            total_referred_spend_micros=9_999_999_999,
        )

        self.today = timezone.now().date()
        self.month_start = self.today.replace(day=1)
        self.old_start = self.today - timedelta(days=200)
        self.old_end = self.old_start + timedelta(days=27)

        ReferralRewardLedger.objects.create(
            referral=self.referral,
            period_start=self.month_start,
            period_end=self.today,
            referred_spend_micros=3_000_000,
            reward_micros=300_000,
            calculation_method="actual_cost",
        )
        ReferralRewardLedger.objects.create(
            referral=self.referral,
            period_start=self.old_start,
            period_end=self.old_end,
            referred_spend_micros=7_000_000,
            reward_micros=700_000,
            calculation_method="actual_cost",
        )

    def _get(self, query=""):
        return self.http_client.get(
            f"/api/v1/referrals/analytics/earnings{query}", **self.headers,
        )

    def test_default_window_is_utc_month_to_date(self):
        resp = self._get()
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["period_start"], self.month_start.isoformat())
        self.assertEqual(body["period_end"], self.today.isoformat())
        self.assertEqual(body["total_earned_micros"], 300_000)
        self.assertEqual(
            body["referrers"][0]["total_earned_micros"], 300_000,
        )

    def test_explicit_window_filters_earnings(self):
        resp = self._get(
            f"?period_start={self.old_start.isoformat()}"
            f"&period_end={self.old_end.isoformat()}"
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["period_start"], self.old_start.isoformat())
        self.assertEqual(body["period_end"], self.old_end.isoformat())
        self.assertEqual(body["total_earned_micros"], 700_000)

    def test_window_covering_both_periods_sums_both(self):
        resp = self._get(
            f"?period_start={self.old_start.isoformat()}"
            f"&period_end={self.today.isoformat()}"
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["total_earned_micros"], 1_000_000)

    def test_window_longer_than_366_days_refused(self):
        start = self.today - timedelta(days=400)
        resp = self._get(
            f"?period_start={start.isoformat()}"
            f"&period_end={self.today.isoformat()}"
        )
        assert_problem(resp, "validation_error", 422)

    def test_window_of_exactly_366_days_allowed(self):
        start = self.today - timedelta(days=366)
        resp = self._get(
            f"?period_start={start.isoformat()}"
            f"&period_end={self.today.isoformat()}"
        )
        self.assertEqual(resp.status_code, 200)

    def test_inverted_window_refused(self):
        resp = self._get(
            f"?period_start={self.today.isoformat()}"
            f"&period_end={(self.today - timedelta(days=1)).isoformat()}"
        )
        assert_problem(resp, "validation_error", 422)

    def test_malformed_date_is_a_400_problem(self):
        resp = self._get("?period_start=not-a-date")
        assert_problem(resp, "bad_request", 400)
