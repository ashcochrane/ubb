from datetime import date
from decimal import Decimal
from django.test import TestCase
from django.utils import timezone
from apps.tenants.models import Tenant
from apps.customers.models import Customer
from apps.tenant_billing.models import TenantBillingPeriod
from apps.tenant_billing.services import TenantBillingService


class AccumulateUsageTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("1.00"),
        )

    def test_accumulate_creates_period_if_none(self):
        TenantBillingService.accumulate_usage(self.tenant, 1_000_000)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant, status="open")
        self.assertEqual(period.total_usage_cost_micros, 1_000_000)
        self.assertEqual(period.event_count, 1)

    def test_accumulate_increments_existing_period(self):
        TenantBillingService.accumulate_usage(self.tenant, 1_000_000)
        TenantBillingService.accumulate_usage(self.tenant, 2_000_000)
        period = TenantBillingPeriod.objects.get(tenant=self.tenant, status="open")
        self.assertEqual(period.total_usage_cost_micros, 3_000_000)
        self.assertEqual(period.event_count, 2)


class CloseBillingPeriodTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("2.50"),
        )

    def test_close_period_calculates_fee_with_decimal(self):
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            total_usage_cost_micros=100_000_000_000,  # $100k
            event_count=5000,
        )
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        self.assertEqual(period.status, "closed")
        # 2.5% of $100k = $2,500 = 2_500_000_000 micros
        self.assertEqual(period.platform_fee_micros, 2_500_000_000)

    def test_close_period_decimal_precision(self):
        """Verify no floating-point precision loss."""
        self.tenant.platform_fee_percentage = Decimal("0.33")
        self.tenant.save()
        period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            total_usage_cost_micros=100_000_000,  # $100
            event_count=10,
        )
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        # 0.33% of $100 = $0.33 = 330_000 micros (exact with Decimal)
        self.assertEqual(period.platform_fee_micros, 330_000)
