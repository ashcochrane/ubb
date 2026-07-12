import pytest
from unittest.mock import patch
from apps.platform.tenants.models import Tenant


@pytest.mark.django_db
class TestCalculateAllEconomicsTask:
    def test_runs_for_metering_tenants(self):
        from apps.subscriptions.tasks import calculate_all_economics_task
        t = Tenant.objects.create(name="metering-only", products=["metering"])
        with patch("apps.subscriptions.tasks.MarginService.snapshot_all") as mock_calc:
            mock_calc.return_value = []
            calculate_all_economics_task()
            assert mock_calc.call_count == 1
            assert mock_calc.call_args[0][0] == t.id


import datetime
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.subscriptions.economics.models import (
    CustomerCostAccumulator, CustomerEconomics, MarginThresholdConfig)
from apps.subscriptions.economics.services import MarginService
from apps.platform.events.models import OutboxEvent


class MarginFlaggingTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="c1")
        self.ps = datetime.date(2026, 6, 1)
        self.pe = datetime.date(2026, 7, 1)

    def test_unprofitable_flag_and_webhook_on_transition(self):
        MarginThresholdConfig.objects.create(tenant=self.tenant, min_margin_pct=10)
        # margin% = 50k/1000k = 5% < 10% -> unprofitable
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=950_000, total_billed_cost_micros=1_000_000, event_count=1)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        MarginService.evaluate_and_emit(econ)
        econ.refresh_from_db()
        assert econ.is_unprofitable is True
        assert OutboxEvent.objects.filter(
            event_type="margin.customer_unprofitable").count() == 1
        # Re-running must NOT emit again (transition-only)
        econ2 = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        MarginService.evaluate_and_emit(econ2)
        assert OutboxEvent.objects.filter(
            event_type="margin.customer_unprofitable").count() == 1

    def test_provider_cost_spike_webhook(self):
        # previous month snapshot with low provider cost
        CustomerEconomics.objects.create(
            tenant=self.tenant, customer=self.customer,
            period_start=datetime.date(2026, 5, 1), period_end=self.ps,
            subscription_revenue_micros=0, usage_billed_micros=1_000_000,
            provider_cost_micros=100_000, gross_margin_micros=900_000, margin_percentage=90)
        # current month with >25% provider-cost rise
        CustomerCostAccumulator.objects.create(
            tenant=self.tenant, customer=self.customer, period_start=self.ps, period_end=self.pe,
            total_provider_cost_micros=200_000, total_billed_cost_micros=1_000_000, event_count=1)
        econ = MarginService.snapshot_customer(self.tenant.id, self.customer.id, self.ps, self.pe)
        MarginService.evaluate_and_emit(econ)
        assert OutboxEvent.objects.filter(
            event_type="margin.provider_cost_spike").count() == 1
        # idempotent — no duplicate for the same period
        MarginService.evaluate_and_emit(econ)
        assert OutboxEvent.objects.filter(
            event_type="margin.provider_cost_spike").count() == 1
