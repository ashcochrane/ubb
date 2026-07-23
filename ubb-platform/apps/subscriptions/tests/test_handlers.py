import pytest
from dataclasses import asdict
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.schemas import UsageRecorded


@pytest.mark.django_db
class TestHandleUsageRecorded:
    def test_creates_accumulator_on_first_event(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-1", asdict(UsageRecorded(
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=1_500_000,
            provider_cost_micros=1_200_000,
            billed_cost_micros=1_500_000,
            event_type="api_call",
            event_id="evt-1",
        )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 1_200_000
        assert acc.total_billed_cost_micros == 1_500_000
        assert acc.event_count == 1

    def test_accumulates_on_subsequent_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        for i in range(3):
            handle_usage_recorded_subscriptions(f"evt-outbox-{i}", asdict(UsageRecorded(
                tenant_id=tenant.id,
                customer_id=customer.id,
                cost_micros=1_000_000,
                provider_cost_micros=800_000,
                billed_cost_micros=1_000_000,
                event_type="api_call",
                event_id=f"evt-{i}",
            )))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 2_400_000
        assert acc.total_billed_cost_micros == 3_000_000
        assert acc.event_count == 3

    def test_skips_zero_cost_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-0", asdict(UsageRecorded(
            tenant_id=tenant.id,
            customer_id=customer.id,
            cost_micros=0,
            provider_cost_micros=0,
            billed_cost_micros=0,
            event_type="api_call",
            event_id="evt-0",
        )))

        assert not CustomerCostAccumulator.objects.filter(tenant=tenant, customer=customer).exists()

    def test_handler_accumulates_provider_and_billed(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test2", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-2")

        handle_usage_recorded_subscriptions("evt1", asdict(UsageRecorded(
            tenant_id=tenant.id, customer_id=customer.id,
            event_id="evt-1", cost_micros=1_000_000,
            provider_cost_micros=800_000, billed_cost_micros=1_000_000)))
        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 800_000
        assert acc.total_billed_cost_micros == 1_000_000
        assert acc.event_count == 1

    def test_handler_accumulates_twice(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test3", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-3")

        for _ in range(2):
            handle_usage_recorded_subscriptions("evt2", asdict(UsageRecorded(
                tenant_id=tenant.id, customer_id=customer.id,
                event_id="evt-2", cost_micros=1_000_000,
                provider_cost_micros=800_000, billed_cost_micros=1_000_000)))

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_provider_cost_micros == 1_600_000
        assert acc.total_billed_cost_micros == 2_000_000
        assert acc.event_count == 2
