from unittest.mock import patch
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.models import UsageEvent
from apps.metering.usage.services.usage_service import UsageService


class GroupFieldTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_stored_on_event(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g1",
            idempotency_key="idem_g1",
            cost_micros=1_000_000,
            group="property_search",
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group, "property_search")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_null_by_default(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g2",
            idempotency_key="idem_g2",
            cost_micros=1_000_000,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertIsNone(event.group)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_max_length_255(self, mock_process):
        long_group = "a" * 255
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_g3",
            idempotency_key="idem_g3",
            cost_micros=1_000_000,
            group=long_group,
        )
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group, long_group)


class GroupPricingIntegrationTest(TestCase):
    """Tests that group is stored on the event and that explicit Rate costs are used.

    After Task 6/7, pricing is purely rate-based (no TenantMarkup margin resolver).
    The `group` field is stored for grouping/analytics; it no longer changes billed cost.
    Explicit dual costs (provider vs billed) are set directly on Rate.
    """

    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        from apps.metering.pricing.models import Card, Rate
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            slug="test_card",
            provider="test_provider",
        )
        Rate.objects.create(
            card=self.card,
            metric_name="requests",
            cost_per_unit_micros=2_500_000,
            provider_cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_stored_on_event_and_costs_from_rate(self, mock_process):
        """group is stored on the event; billed/provider costs come from Rate."""
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp1",
            idempotency_key="idem_gp1",
            pricing_card="test_card",
            usage_metrics={"requests": 1},
            group="premium",
        )
        # Costs come from Rate directly (no margin resolver)
        self.assertEqual(result["billed_cost_micros"], 2_500_000)
        self.assertEqual(result["provider_cost_micros"], 1_000_000)
        event = UsageEvent.objects.get(id=result["event_id"])
        self.assertEqual(event.group, "premium")

    @patch("apps.platform.events.tasks.process_single_event")
    def test_no_group_uses_rate_costs(self, mock_process):
        """Without a group, costs are still from Rate (no default margin applied)."""
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp2",
            idempotency_key="idem_gp2",
            pricing_card="test_card",
            usage_metrics={"requests": 1},
        )
        self.assertEqual(result["billed_cost_micros"], 2_500_000)
        self.assertEqual(result["provider_cost_micros"], 1_000_000)
