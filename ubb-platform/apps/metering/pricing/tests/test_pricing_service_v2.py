from decimal import Decimal
from django.test import TestCase
from apps.platform.tenants.models import Tenant
from apps.platform.groups.models import Group
from apps.metering.pricing.models import Card, Rate, TenantMarkup
from apps.metering.pricing.services.pricing_service import PricingService, PricingError


class PricingServiceCardTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini Flash",
            provider="google_gemini",
            event_type="llm_call",
            dimensions={"model": "gemini-2.0-flash"},
        )
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            cost_per_unit_micros=300_000,
            unit_quantity=1_000_000,
        )
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=40)

    def test_price_event_with_card(self):
        provider_cost, billed_cost, prov = PricingService.price_event(
            tenant=self.tenant,
            event_type="llm_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(provider_cost, 75_000 + 150_000)
        expected_billed = int(Decimal("225000") / Decimal("0.60"))
        self.assertEqual(billed_cost, expected_billed)

    def test_no_card_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="unknown",
                provider="unknown",
                usage_metrics={"tokens": 100},
            )

    def test_empty_metrics_returns_zero(self):
        p, b, prov = PricingService.price_event(
            tenant=self.tenant,
            event_type="llm_call",
            provider="google_gemini",
            usage_metrics={},
        )
        self.assertEqual(p, 0)
        self.assertEqual(b, 0)


class MarginResolutionTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Test", stripe_connected_account_id="acct_test"
        )
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="Test Card",
            provider="test_provider",
            event_type="test_event",
            dimensions={},
        )
        Rate.objects.create(
            card=self.card,
            metric_name="requests",
            cost_per_unit_micros=1_000_000,
            unit_quantity=1,
        )
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=30)

    def test_default_margin_when_no_group(self):
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_group_margin_overrides_default(self):
        Group.objects.create(
            tenant=self.tenant, name="Premium", slug="premium", margin_pct=60,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        self.assertEqual(billed, 2_500_000)

    def test_group_null_margin_inherits_default(self):
        Group.objects.create(
            tenant=self.tenant, name="Basic", slug="basic", margin_pct=None,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="basic",
        )
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_card_level_markup_takes_precedence_over_group(self):
        Group.objects.create(
            tenant=self.tenant, name="Premium", slug="premium", margin_pct=60,
        )
        TenantMarkup.objects.create(
            tenant=self.tenant, event_type="test_event",
            provider="test_provider", margin_pct=80,
        )
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="premium",
        )
        self.assertEqual(billed, 5_000_000)

    def test_unmatched_group_slug_uses_default(self):
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
            group="nonexistent_group",
        )
        expected = int(Decimal("1000000") / Decimal("0.70"))
        self.assertEqual(billed, expected)

    def test_zero_margin_passthrough(self):
        TenantMarkup.objects.all().delete()
        TenantMarkup.objects.create(tenant=self.tenant, margin_pct=0)
        _, billed, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="test_event",
            provider="test_provider",
            usage_metrics={"requests": 1},
        )
        self.assertEqual(billed, 1_000_000)
