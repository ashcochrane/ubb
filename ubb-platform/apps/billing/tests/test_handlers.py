from unittest.mock import patch
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.billing.handlers import handle_usage_recorded


class HandleUsageRecordedTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test Tenant", stripe_connected_account_id="acct_test"
        )

    @patch("apps.billing.handlers.TenantBillingService")
    def test_accumulates_usage_for_positive_cost(self, mock_billing_service):
        handle_usage_recorded({
            "tenant_id": str(self.tenant.id),
            "customer_id": "cust-123",
            "cost_micros": 500_000,
            "event_type": "api_call",
            "event_id": "evt-123",
        })
        mock_billing_service.accumulate_usage.assert_called_once_with(
            self.tenant, 500_000
        )

    @patch("apps.billing.handlers.TenantBillingService")
    def test_skips_accumulation_for_zero_cost(self, mock_billing_service):
        handle_usage_recorded({
            "tenant_id": str(self.tenant.id),
            "customer_id": "cust-123",
            "cost_micros": 0,
            "event_type": "api_call",
            "event_id": "evt-456",
        })
        mock_billing_service.accumulate_usage.assert_not_called()

    @patch("apps.billing.handlers.TenantBillingService")
    def test_skips_accumulation_when_cost_missing(self, mock_billing_service):
        handle_usage_recorded({
            "tenant_id": str(self.tenant.id),
            "customer_id": "cust-123",
            "event_type": "api_call",
            "event_id": "evt-789",
        })
        mock_billing_service.accumulate_usage.assert_not_called()
