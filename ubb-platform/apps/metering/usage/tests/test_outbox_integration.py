import pytest
from unittest.mock import patch

from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent


@pytest.mark.django_db
class TestUsageServiceOutbox:
    def test_record_usage_creates_outbox_event(self):
        from apps.metering.usage.services.usage_service import UsageService

        tenant = Tenant.objects.create(
            name="Test", products=["metering", "billing"],
            stripe_connected_account_id="acct_test",
        )
        customer = Customer.objects.create(
            tenant=tenant, external_id="ext1",
        )
        customer.wallet.balance_micros = 100_000_000
        customer.wallet.save(update_fields=["balance_micros"])

        with patch("apps.platform.events.tasks.process_single_event"):
            result = UsageService.record_usage(
                tenant=tenant,
                customer=customer,
                request_id="req1",
                idempotency_key="idem1",
                cost_micros=5_000_000,
            )

        assert OutboxEvent.objects.filter(event_type="usage.recorded").count() == 1
        event = OutboxEvent.objects.get(event_type="usage.recorded")
        assert event.payload["customer_id"] == str(customer.id)
        assert event.payload["cost_micros"] == 5_000_000
        assert event.payload["event_id"] == result["event_id"]
