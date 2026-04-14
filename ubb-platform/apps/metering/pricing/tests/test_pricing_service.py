from datetime import timedelta
from decimal import Decimal

from django.test import TestCase
from django.utils import timezone

from apps.metering.pricing.models import Card, Rate, TenantMarkup
from apps.metering.pricing.services.pricing_service import PricingError, PricingService
from apps.platform.tenants.models import Tenant


class PricingServiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.card = Card.objects.create(
            tenant=self.tenant,
            provider="google_gemini",
            event_type="gemini_api_call",
            name="Gemini Flash",
            dimensions={"model": "gemini-2.0-flash"},
        )
        self.input_rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        self.output_rate = Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            cost_per_unit_micros=300_000,
            unit_quantity=1_000_000,
        )

    def test_price_event_single_metric(self):
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(provider_cost, 75_000)
        # No margin configured -> passthrough
        self.assertEqual(billed_cost, 75_000)
        self.assertIn("input_tokens", provenance["metrics"])

    def test_price_event_multi_metric(self):
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
            properties={"model": "gemini-2.0-flash"},
        )
        # input: 75_000, output: (500_000 * 300_000 + 500_000) // 1_000_000 = 150_000
        self.assertEqual(provider_cost, 75_000 + 150_000)
        # No margin -> passthrough
        self.assertEqual(billed_cost, provider_cost)

    def test_price_event_with_margin(self):
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            margin_pct=20,
        )
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(provider_cost, 75_000)
        # margin 20%: 75_000 / (1 - 0.20) = 75_000 / 0.80 = 93_750
        expected_billed = int(Decimal("75000") / Decimal("0.80"))
        self.assertEqual(billed_cost, expected_billed)
        self.assertIn("margin", provenance)
        self.assertEqual(provenance["margin"]["margin_pct"], 20.0)

    def test_no_card_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="unknown",
                provider="unknown",
                usage_metrics={"tokens": 100},
            )

    def test_empty_metrics_returns_zero(self):
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={},
        )
        self.assertEqual(provider_cost, 0)
        self.assertEqual(billed_cost, 0)

    def test_dimension_matching_most_specific_wins(self):
        # Create a fallback card with no dimensions (less specific)
        fallback_card = Card.objects.create(
            tenant=self.tenant,
            provider="google_gemini",
            event_type="gemini_api_call",
            name="Gemini Fallback",
            dimensions={},
        )
        Rate.objects.create(
            card=fallback_card,
            metric_name="input_tokens",
            cost_per_unit_micros=100_000,
            unit_quantity=1_000_000,
        )
        provider_cost, _, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        # The more specific card (with model dimension) should win -> 75_000
        self.assertEqual(provider_cost, 75_000)

    def test_dimension_matching_fallback_when_no_specific(self):
        # Create a fallback card with no dimensions
        fallback_card = Card.objects.create(
            tenant=self.tenant,
            provider="google_gemini",
            event_type="gemini_api_call",
            name="Gemini Fallback",
            dimensions={},
        )
        Rate.objects.create(
            card=fallback_card,
            metric_name="input_tokens",
            cost_per_unit_micros=100_000,
            unit_quantity=1_000_000,
        )
        provider_cost, _, _ = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "unknown-model"},
        )
        # The specific card dimensions don't match, fallback wins -> 100_000
        self.assertEqual(provider_cost, 100_000)

    def test_margin_precedence(self):
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="",
            provider="",
            margin_pct=10,
        )
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            margin_pct=25,
        )
        _, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        # Most specific markup (event_type + provider) wins
        self.assertEqual(provenance["margin"]["margin_pct"], 25.0)

    def test_expired_rate_not_used(self):
        self.input_rate.valid_to = timezone.now() - timedelta(days=1)
        self.input_rate.save()
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="gemini_api_call",
                provider="google_gemini",
                usage_metrics={"input_tokens": 1_000},
                properties={"model": "gemini-2.0-flash"},
            )

    def test_negative_units_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="gemini_api_call",
                provider="google_gemini",
                usage_metrics={"input_tokens": -100},
                properties={"model": "gemini-2.0-flash"},
            )

    def test_non_integer_units_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="gemini_api_call",
                provider="google_gemini",
                usage_metrics={"input_tokens": 1.5},
                properties={"model": "gemini-2.0-flash"},
            )

    def test_string_units_raises_pricing_error(self):
        with self.assertRaises(PricingError):
            PricingService.price_event(
                tenant=self.tenant,
                event_type="gemini_api_call",
                provider="google_gemini",
                usage_metrics={"input_tokens": "many"},
                properties={"model": "gemini-2.0-flash"},
            )

    def test_provenance_structure(self):
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 500},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertIn("engine_version", provenance)
        self.assertIn("calculated_at", provenance)
        self.assertIn("metrics", provenance)
        self.assertIn("card_id", provenance)
        self.assertIn("card_name", provenance)
        self.assertIn("margin", provenance)
        metric_prov = provenance["metrics"]["input_tokens"]
        self.assertIn("rate_id", metric_prov)
        self.assertIn("card_id", metric_prov)
        self.assertIn("units", metric_prov)
        self.assertIn("cost_per_unit_micros", metric_prov)
        self.assertEqual(metric_prov["units"], 500)
