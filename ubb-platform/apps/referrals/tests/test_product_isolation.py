from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey


class TestReferralsProductIsolation(TestCase):
    def setUp(self):
        self.http_client = Client()

    def test_metering_only_tenant_gets_403(self):
        tenant = Tenant.objects.create(
            name="metering-only", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/referrals/program",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_billing_tenant_gets_403(self):
        tenant = Tenant.objects.create(
            name="billing-only", products=["metering", "billing"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/referrals/program",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_referrals_tenant_can_access(self):
        tenant = Tenant.objects.create(
            name="ref-tenant", products=["metering", "referrals"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/referrals/program",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        # Should be 404 (no program yet), not 403
        self.assertEqual(response.status_code, 404)

    def test_referrals_analytics_requires_product(self):
        tenant = Tenant.objects.create(
            name="no-ref", products=["metering"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/referrals/analytics/summary",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 403)

    def test_referrals_analytics_allowed_with_product(self):
        tenant = Tenant.objects.create(
            name="ref-tenant", products=["metering", "referrals"],
        )
        _, raw_key = TenantApiKey.create_key(tenant=tenant, label="test")

        response = self.http_client.get(
            "/api/v1/referrals/analytics/summary",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(response.status_code, 200)
