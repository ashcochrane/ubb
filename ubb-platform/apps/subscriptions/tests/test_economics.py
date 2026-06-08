import datetime
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import CustomerCostAccumulator, CustomerRevenueProfile
from apps.subscriptions.economics.revenue import RevenueService
from apps.subscriptions.economics.services import MarginService


class MarginServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.ps = datetime.date(2026, 6, 1)
        self.pe = datetime.date(2026, 7, 1)

    def test_meter_only_margin_is_billed_minus_provider(self):
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.subscription_revenue_micros == 0
        assert econ.usage_billed_micros == 1_000_000
        assert econ.provider_cost_micros == 800_000
        assert econ.gross_margin_micros == 200_000
        assert float(econ.margin_percentage) == 20.0

    def test_manual_revenue_full_month(self):
        amt = RevenueService.manual_revenue_for_window(
            self.tenant.id, self.customer.id, self.ps, self.pe)
        assert amt == 0
        CustomerRevenueProfile.objects.create(
            tenant=self.tenant, customer=self.customer,
            recurring_amount_micros=500_000_000, effective_from=datetime.date(2026, 1, 1))
        amt = RevenueService.manual_revenue_for_window(
            self.tenant.id, self.customer.id, self.ps, self.pe)
        assert amt == 500_000_000

    def test_margin_includes_manual_revenue(self):
        CustomerRevenueProfile.objects.create(
            tenant=self.tenant, customer=self.customer,
            recurring_amount_micros=500_000_000, effective_from=datetime.date(2026, 1, 1))
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=800_000, total_billed_cost_micros=1_000_000, event_count=2)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        assert econ.subscription_revenue_micros == 500_000_000
        assert econ.gross_margin_micros == 500_200_000

    def test_compute_live_matches(self):
        from apps.metering.usage.services.usage_service import UsageService
        from unittest.mock import patch
        with patch("apps.platform.events.tasks.process_single_event"):
            UsageService.record_usage(
                tenant=self.tenant, customer=self.customer, request_id="r1",
                idempotency_key="i1", provider_cost_micros=800_000, billed_cost_micros=1_000_000)
        # live window covering today; just assert the shape + margin math
        data = MarginService.compute_live(
            self.tenant.id, self.customer.id, datetime.date(2026, 1, 1), datetime.date(2100, 1, 1))
        assert data["provider_cost_micros"] == 800_000
        assert data["usage_billed_micros"] == 1_000_000
        assert data["gross_margin_micros"] == 200_000
