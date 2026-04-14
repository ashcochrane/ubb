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
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test",
            products=["metering", "billing"],
        )
        self.customer = Customer.objects.create(
            tenant=self.tenant, external_id="c1"
        )
        from apps.metering.pricing.models import Card, Rate, TenantMarkup
        card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=card,
            metric_name="requests",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=30)
        from apps.platform.groups.models import Group
        Group.objects.create(
            tenant=self.tenant, name="Premium", slug="premium", margin_pct=60,
        )

    @patch("apps.platform.events.tasks.process_single_event")
    def test_group_affects_billed_cost(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp1",
            idempotency_key="idem_gp1",
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        # 60% margin: $1.00 / 0.40 = $2.50
        self.assertEqual(result["billed_cost_micros"], 2_500_000)
        self.assertEqual(result["provider_cost_micros"], 1_000_000)

    @patch("apps.platform.events.tasks.process_single_event")
    def test_no_group_uses_default_margin(self, mock_process):
        result = UsageService.record_usage(
            tenant=self.tenant,
            customer=self.customer,
            request_id="req_gp2",
            idempotency_key="idem_gp2",
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        from decimal import Decimal
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(result["billed_cost_micros"], expected)
