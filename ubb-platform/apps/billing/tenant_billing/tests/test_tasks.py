from datetime import date
from decimal import Decimal
from unittest.mock import patch
from django.db.utils import OperationalError
from django.test import TestCase
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.billing.tenant_billing.models import TenantBillingPeriod
from apps.billing.tenant_billing.services import TenantBillingService


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


class AccumulateUsageRaceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("1.00"),
        )

    def test_accumulate_usage_retries_when_period_closed(self):
        """When period is closed between get_or_create and update, retry with fresh period."""
        from datetime import date as date_cls

        # Create a past-month period (January) and a current-month period (February)
        jan_period = TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="closed",
            total_usage_cost_micros=500_000,
            event_count=1,
        )

        today = timezone.now().date()
        first_of_month = today.replace(day=1)

        # Simulate: first call returns stale (closed) Jan period,
        # retry returns a new (open) current-month period
        call_count = [0]
        original_get_or_create = TenantBillingService.get_or_create_current_period

        def mock_get_or_create(tenant):
            call_count[0] += 1
            if call_count[0] == 1:
                return jan_period  # Stale period (just closed by close_periods task)
            return original_get_or_create(tenant)  # Fresh current period

        with patch.object(
            TenantBillingService, "get_or_create_current_period",
            side_effect=mock_get_or_create,
        ):
            TenantBillingService.accumulate_usage(self.tenant, 1_000_000)

        # The closed Jan period should be untouched
        jan_period.refresh_from_db()
        self.assertEqual(jan_period.total_usage_cost_micros, 500_000)

        # A new open period should exist with the retried amount
        new_period = TenantBillingPeriod.objects.get(tenant=self.tenant, status="open")
        self.assertEqual(new_period.total_usage_cost_micros, 1_000_000)
        self.assertEqual(new_period.event_count, 1)


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


class ClosePeriodsTaskErrorHandlingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            platform_fee_percentage=Decimal("1.00"),
        )

    @patch("apps.billing.tenant_billing.tasks.TenantBillingService.close_period")
    def test_close_periods_propagates_db_error(self, mock_close):
        from apps.billing.tenant_billing.tasks import close_tenant_billing_periods

        today = timezone.now().date()
        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2025, 12, 1),
            period_end=date(2026, 1, 1),
            status="open",
        )

        mock_close.side_effect = OperationalError("connection reset")
        with self.assertRaises(OperationalError):
            close_tenant_billing_periods()

    @patch("apps.billing.tenant_billing.tasks.TenantBillingService.close_period")
    def test_close_periods_continues_on_data_error(self, mock_close):
        from apps.billing.tenant_billing.tasks import close_tenant_billing_periods

        TenantBillingPeriod.objects.create(
            tenant=self.tenant,
            period_start=date(2025, 12, 1),
            period_end=date(2026, 1, 1),
            status="open",
        )

        mock_close.side_effect = ValueError("bad data")
        # Should NOT raise — ValueError is caught and logged
        close_tenant_billing_periods()
