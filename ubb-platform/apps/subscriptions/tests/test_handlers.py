import pytest
from django.utils import timezone
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer


@pytest.mark.django_db
class TestHandleUsageRecorded:
    def test_creates_accumulator_on_first_event(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-1", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "cost_micros": 1_500_000,
            "event_type": "api_call",
            "event_id": "evt-1",
        })

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_cost_micros == 1_500_000
        assert acc.event_count == 1

    def test_accumulates_on_subsequent_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        for i in range(3):
            handle_usage_recorded_subscriptions(f"evt-outbox-{i}", {
                "tenant_id": str(tenant.id),
                "customer_id": str(customer.id),
                "cost_micros": 1_000_000,
                "event_type": "api_call",
                "event_id": f"evt-{i}",
            })

        acc = CustomerCostAccumulator.objects.get(tenant=tenant, customer=customer)
        assert acc.total_cost_micros == 3_000_000
        assert acc.event_count == 3

    def test_skips_zero_cost_events(self):
        from apps.subscriptions.handlers import handle_usage_recorded_subscriptions
        from apps.subscriptions.economics.models import CustomerCostAccumulator

        tenant = Tenant.objects.create(name="test", products=["metering", "subscriptions"])
        customer = Customer.objects.create(tenant=tenant, external_id="cust-1")

        handle_usage_recorded_subscriptions("evt-outbox-0", {
            "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "cost_micros": 0,
            "event_type": "api_call",
            "event_id": "evt-0",
        })

        assert not CustomerCostAccumulator.objects.filter(tenant=tenant, customer=customer).exists()
