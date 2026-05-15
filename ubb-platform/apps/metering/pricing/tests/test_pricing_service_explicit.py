"""Explicit-rate pricing: no runtime margin resolution."""
from decimal import Decimal

import pytest
from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import Card, Rate
from apps.metering.pricing.services.pricing_service import PricingService, PricingError


class PriceEventBySlugTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.card = Card.objects.create(
            tenant=self.tenant, name="GPT-4o", slug="gpt_4o",
            provider="openai", status="active",
        )
        Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=2_500,
            unit_quantity=1_000_000,
        )
        Rate.objects.create(
            card=self.card, metric_name="output_tokens",
            cost_per_unit_micros=15_000,
            provider_cost_per_unit_micros=10_000,
            unit_quantity=1_000_000,
        )

    def test_prices_via_stored_costs_no_margin_resolution(self):
        provider_cost, billed_cost, provenance, card = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="gpt_4o",
            usage_metrics={"input_tokens": 1_000_000, "output_tokens": 500_000},
        )
        # provider: 1M * 2500/1M + 500k * 10000/1M = 2500 + 5000 = 7500
        self.assertEqual(provider_cost, 7_500)
        # billed: 1M * 3000/1M + 500k * 15000/1M = 3000 + 7500 = 10_500
        self.assertEqual(billed_cost, 10_500)
        self.assertEqual(card, self.card)
        self.assertNotIn("margin", provenance)
        self.assertIn("metrics", provenance)
        self.assertIn("input_tokens", provenance["metrics"])

    def test_null_provider_cost_treated_as_passthrough(self):
        card2 = Card.objects.create(
            tenant=self.tenant, name="Claude", slug="claude_sonnet",
            provider="anthropic", status="active",
        )
        Rate.objects.create(
            card=card2, metric_name="input_tokens",
            cost_per_unit_micros=3_000,
            provider_cost_per_unit_micros=None,  # unknown
            unit_quantity=1_000_000,
        )
        provider_cost, billed_cost, _, _ = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="claude_sonnet",
            usage_metrics={"input_tokens": 1_000_000},
        )
        # provider cost falls back to billed cost
        self.assertEqual(provider_cost, 3_000)
        self.assertEqual(billed_cost, 3_000)

    def test_unknown_slug_raises(self):
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="nope",
                usage_metrics={"input_tokens": 1},
            )

    def test_unknown_metric_raises(self):
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="gpt_4o",
                usage_metrics={"bogus_metric": 1},
            )

    def test_empty_metrics_returns_zero(self):
        provider_cost, billed_cost, _, card = PricingService.price_event_by_slug(
            tenant=self.tenant, card_slug="gpt_4o", usage_metrics={},
        )
        self.assertEqual(provider_cost, 0)
        self.assertEqual(billed_cost, 0)
        self.assertIsNone(card)

    def test_draft_card_cannot_be_used_for_live_pricing(self):
        draft = Card.objects.create(
            tenant=self.tenant, name="Draft", slug="draft_card",
            provider="openai", status="draft",
        )
        Rate.objects.create(
            card=draft, metric_name="input_tokens",
            cost_per_unit_micros=1_000, unit_quantity=1_000_000,
        )
        with pytest.raises(PricingError):
            PricingService.price_event_by_slug(
                tenant=self.tenant, card_slug="draft_card",
                usage_metrics={"input_tokens": 1_000_000},
            )
