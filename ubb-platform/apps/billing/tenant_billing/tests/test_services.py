import pytest
from decimal import Decimal
from datetime import date
from apps.platform.tenants.models import Tenant
from apps.billing.tenant_billing.models import TenantBillingPeriod, ProductFeeConfig
from apps.billing.tenant_billing.services import TenantBillingService


@pytest.mark.django_db
class TestProductFeeCalculation:
    def test_flat_fee_for_product(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        ProductFeeConfig.objects.create(
            tenant=tenant,
            product="metering",
            fee_type="flat",
            config={"amount_micros": 50_000_000},  # $50
        )
        period = TenantBillingPeriod.objects.create(
            tenant=tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="open",
            total_usage_cost_micros=100_000_000,  # $100 usage
            event_count=1,  # Prevents reconcile from zeroing cost (no UsageEvents in test DB)
        )

        TenantBillingService.close_period(period)
        period.refresh_from_db()

        assert period.platform_fee_micros == 50_000_000

    def test_percentage_fee_for_product(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        ProductFeeConfig.objects.create(
            tenant=tenant,
            product="billing",
            fee_type="percentage",
            config={"percentage": "2.0"},
        )
        period = TenantBillingPeriod.objects.create(
            tenant=tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="open",
            total_usage_cost_micros=100_000_000,  # $100 usage
            event_count=1,  # Prevents reconcile from zeroing cost (no UsageEvents in test DB)
        )

        TenantBillingService.close_period(period)
        period.refresh_from_db()

        # 2% of $100 = $2 = 2_000_000 micros
        assert period.platform_fee_micros == 2_000_000

    def test_multiple_products_sum_fees(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
        )
        ProductFeeConfig.objects.create(
            tenant=tenant, product="metering",
            fee_type="flat", config={"amount_micros": 30_000_000},
        )
        ProductFeeConfig.objects.create(
            tenant=tenant, product="billing",
            fee_type="percentage", config={"percentage": "1.0"},
        )
        period = TenantBillingPeriod.objects.create(
            tenant=tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="open",
            total_usage_cost_micros=200_000_000,  # $200 usage
            event_count=1,  # Prevents reconcile from zeroing cost (no UsageEvents in test DB)
        )

        TenantBillingService.close_period(period)
        period.refresh_from_db()

        # $30 flat + 1% of $200 = $2 = $32 total
        assert period.platform_fee_micros == 32_000_000

    def test_falls_back_to_legacy_percentage_when_no_configs(self):
        tenant = Tenant.objects.create(
            name="Test", products=["metering"],
            platform_fee_percentage=Decimal("1.5"),
        )
        period = TenantBillingPeriod.objects.create(
            tenant=tenant,
            period_start=date(2026, 1, 1),
            period_end=date(2026, 2, 1),
            status="open",
            total_usage_cost_micros=100_000_000,
            event_count=1,  # Prevents reconcile from zeroing cost (no UsageEvents in test DB)
        )

        TenantBillingService.close_period(period)
        period.refresh_from_db()

        # 1.5% of $100 = $1.50 = 1_500_000, floored to cent = 1_500_000
        assert period.platform_fee_micros == 1_500_000
