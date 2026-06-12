"""F4.4: sandbox tenants never accrue or get invoiced platform fees."""
from datetime import date
from decimal import Decimal

import pytest
from django.test import TestCase

from apps.billing.tenant_billing.models import ProductFeeConfig, TenantBillingPeriod
from apps.billing.tenant_billing.services import TenantBillingService
from apps.billing.stripe.services.stripe_service import StripeService
from apps.platform.tenants.models import Tenant
from apps.platform.tenants.services.sandbox_service import get_or_create_sandbox
from core.exceptions import StripeFatalError


class SandboxFeeExclusionTest(TestCase):
    def setUp(self):
        self.live = Tenant.objects.create(
            name="Live Co", products=["metering", "billing"],
            platform_fee_percentage=Decimal("1.00"))
        self.sandbox = get_or_create_sandbox(self.live)

    def _period(self, tenant, usage_micros=50_000_000_000):
        return TenantBillingPeriod.objects.create(
            tenant=tenant,
            period_start=date(2026, 5, 1), period_end=date(2026, 6, 1),
            status="open", total_usage_cost_micros=usage_micros, event_count=10)

    def test_calculate_fees_zero_for_sandbox_with_product_fee_configs(self):
        ProductFeeConfig.objects.create(
            tenant=self.sandbox, product="metering", fee_type="percentage",
            config={"percentage": "2.0"})
        period = self._period(self.sandbox)
        fee, items = TenantBillingService._calculate_fees(self.sandbox, period)
        self.assertEqual(fee, 0)
        self.assertEqual(items, [])

    def test_calculate_fees_zero_for_sandbox_legacy_percentage(self):
        period = self._period(self.sandbox)
        fee, items = TenantBillingService._calculate_fees(self.sandbox, period)
        self.assertEqual(fee, 0)
        self.assertEqual(items, [])

    def test_live_tenant_fee_unchanged(self):
        ProductFeeConfig.objects.create(
            tenant=self.live, product="metering", fee_type="percentage",
            config={"percentage": "2.0"})
        period = self._period(self.live)
        fee, items = TenantBillingService._calculate_fees(self.live, period)
        self.assertGreater(fee, 0)
        self.assertTrue(items)

    def test_close_period_on_sandbox_closes_at_zero_fee(self):
        period = self._period(self.sandbox, usage_micros=0)
        TenantBillingService.close_period(period)
        period.refresh_from_db()
        self.assertEqual(period.status, "closed")
        self.assertEqual(period.platform_fee_micros, 0)

    def test_create_tenant_platform_invoice_belt_raise_for_sandbox(self):
        period = self._period(self.sandbox)
        period.platform_fee_micros = 500_000_000  # forged: must STILL refuse
        with pytest.raises(StripeFatalError, match="never be platform-fee invoiced"):
            StripeService.create_tenant_platform_invoice(self.sandbox, period)
