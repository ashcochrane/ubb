from datetime import date
from django.test import TestCase, Client
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.billing.tenant_billing.models import TenantBillingPeriod, TenantInvoice


class TenantBillingPeriodsEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=1.00,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=50_000_000_000,
            event_count=1000,
            platform_fee_micros=500_000_000,
        )

    def test_list_billing_periods(self):
        response = self.http_client.get(
            "/api/v1/tenant/billing-periods",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_usage_cost_micros"], 50_000_000_000)

    def test_unauthenticated_returns_401(self):
        response = self.http_client.get("/api/v1/tenant/billing-periods")
        self.assertEqual(response.status_code, 401)


class TenantInvoicesEndpointTest(TestCase):
    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="invoiced",
            total_usage_cost_micros=50_000_000_000,
            platform_fee_micros=500_000_000,
        )
        TenantInvoice.objects.create(
            tenant=self.tenant,
            billing_period=period,
            total_amount_micros=500_000_000,
            status="paid",
        )

    def test_list_invoices(self):
        response = self.http_client.get(
            "/api/v1/tenant/invoices",
            HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(len(body["data"]), 1)
        self.assertEqual(body["data"][0]["total_amount_micros"], 500_000_000)
