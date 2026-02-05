from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.pricing.models import ProviderRate, TenantMarkup
from apps.pricing.services.pricing_service import PricingError, PricingService
from apps.platform.tenants.models import Tenant


class PricingServiceTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.rate = ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={"model": "gemini-2.0-flash"},
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        self.output_rate = ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="output_tokens",
            dimensions={"model": "gemini-2.0-flash"},
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
        self.assertEqual(billed_cost, provider_cost)

    def test_price_event_with_markup(self):
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            markup_percentage_micros=20_000_000,
            fixed_uplift_micros=0,
        )
        provider_cost, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(provider_cost, 75_000)
        # markup: (75_000 * 20_000_000 + 50_000_000) // 100_000_000 = 15_000
        self.assertEqual(billed_cost, 75_000 + 15_000)
        self.assertIn("markup", provenance)
        self.assertEqual(provenance["markup"]["percentage_micros"], 20_000_000)

    def test_no_rate_raises_pricing_error(self):
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
        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={},
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
        self.assertEqual(provider_cost, 75_000)

    def test_dimension_matching_fallback_when_no_specific(self):
        ProviderRate.objects.create(
            provider="google_gemini",
            event_type="gemini_api_call",
            metric_name="input_tokens",
            dimensions={},
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
        self.assertEqual(provider_cost, 100_000)

    def test_markup_precedence(self):
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="",
            provider="",
            markup_percentage_micros=10_000_000,
        )
        TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            markup_percentage_micros=25_000_000,
        )
        _, billed_cost, provenance = PricingService.price_event(
            tenant=self.tenant,
            event_type="gemini_api_call",
            provider="google_gemini",
            usage_metrics={"input_tokens": 1_000_000},
            properties={"model": "gemini-2.0-flash"},
        )
        self.assertEqual(provenance["markup"]["percentage_micros"], 25_000_000)

    def test_expired_rate_not_used(self):
        self.rate.valid_to = timezone.now() - timedelta(days=1)
        self.rate.save()
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
        metric_prov = provenance["metrics"]["input_tokens"]
        self.assertIn("rate_id", metric_prov)
        self.assertIn("units", metric_prov)
        self.assertIn("cost_per_unit_micros", metric_prov)
        self.assertEqual(metric_prov["units"], 500)
