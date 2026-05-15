from django.db import IntegrityError
from django.test import TestCase

from apps.metering.pricing.models import Card, Rate
from apps.platform.groups.models import Group
from apps.platform.tenants.models import Tenant


class CardModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_create_card(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o",
            provider="openai",
        )
        card.refresh_from_db()
        self.assertEqual(card.name, "GPT-4o Pricing")
        self.assertEqual(card.slug, "gpt_4o")
        self.assertEqual(card.provider, "openai")
        self.assertEqual(card.status, "active")

    def test_unique_active_card(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_unique1",
            provider="openai",
        )
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                tenant=self.tenant,
                name="GPT-4o Pricing Duplicate",
                slug="gpt_4o_unique1",
                provider="openai",
            )

    def test_archived_card_does_not_conflict(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing Old",
            slug="gpt_4o_archived",
            provider="openai",
            status="archived",
        )
        # Should NOT raise — archived cards are excluded from unique constraint
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing New",
            slug="gpt_4o_archived",
            provider="openai",
        )
        self.assertEqual(card.status, "active")


class CardSlugTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Slug Test Tenant")

    def test_create_card_with_slug(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Gemini 2 Flash",
            slug="gemini_2_flash",
            provider="google",
        )
        card.refresh_from_db()
        self.assertEqual(card.slug, "gemini_2_flash")

    def test_slug_unique_per_tenant_active(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o",
            provider="openai",
        )
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                tenant=self.tenant,
                name="GPT-4o Pricing Dup",
                slug="gpt_4o",
                provider="openai",
            )

    def test_slug_unique_allows_archived_duplicate(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing Old",
            slug="gpt_4o_dup",
            provider="openai",
            status="archived",
        )
        # Should NOT raise — archived cards are excluded from slug unique constraint
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing New",
            slug="gpt_4o_dup",
            provider="openai",
        )
        self.assertEqual(card.slug, "gpt_4o_dup")
        self.assertEqual(card.status, "active")

    def test_draft_status(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="Draft Card",
            slug="draft_card",
            provider="openai",
            status="draft",
        )
        card.refresh_from_db()
        self.assertEqual(card.status, "draft")

    def test_card_with_group(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="LLM Models",
            slug="llm_models",
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_grouped",
            provider="openai",
            group=group,
        )
        card.refresh_from_db()
        self.assertEqual(card.group, group)
        self.assertIn(card, group.pricing_cards.all())

    def test_card_group_set_null_on_delete(self):
        group = Group.objects.create(
            tenant=self.tenant,
            name="Temp Group",
            slug="temp_group",
        )
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_null_group",
            provider="openai",
            group=group,
        )
        group.delete()
        card.refresh_from_db()
        self.assertIsNone(card.group)

    def test_pricing_source_url(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_url",
            provider="openai",
            pricing_source_url="https://openai.com/pricing",
        )
        card.refresh_from_db()
        self.assertEqual(card.pricing_source_url, "https://openai.com/pricing")


class RateModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_rate",
            provider="openai",
        )

    def test_create_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.metric_name, "input_tokens")
        self.assertEqual(rate.cost_per_unit_micros, 75_000)
        self.assertIsNone(rate.valid_to)

    def test_calculate_cost_micros(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        # 1M tokens at 75,000 micros/1M = 75,000 micros
        self.assertEqual(rate.calculate_cost_micros(1_000_000), 75_000)
        # 1,000 tokens at 75,000 micros/1M = 75 micros (round-half-up)
        self.assertEqual(rate.calculate_cost_micros(1_000), 75)

    def test_unique_active_rate_per_card_metric(self):
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
        )
        with self.assertRaises(IntegrityError):
            Rate.objects.create(
                card=self.card,
                metric_name="input_tokens",
                cost_per_unit_micros=80_000,
            )

    def test_rates_via_card_relationship(self):
        Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            cost_per_unit_micros=75_000,
        )
        Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            cost_per_unit_micros=300_000,
        )
        self.assertEqual(self.card.rates.count(), 2)


class RatePricingTypeTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Rate Type Tenant")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            slug="gpt_4o_pricing_type",
            provider="openai",
        )

    def test_per_unit_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="input_tokens",
            pricing_type="per_unit",
            label="Input Tokens",
            unit="per 1M tokens",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.pricing_type, "per_unit")
        self.assertEqual(rate.label, "Input Tokens")
        self.assertEqual(rate.unit, "per 1M tokens")

    def test_flat_rate(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="api_call",
            pricing_type="flat",
            label="API Call",
            unit="per call",
            cost_per_unit_micros=500_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.pricing_type, "flat")
        self.assertEqual(rate.label, "API Call")
        self.assertEqual(rate.unit, "per call")

    def test_flat_calculate_cost_ignores_quantity(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="api_call_flat",
            pricing_type="flat",
            cost_per_unit_micros=500_000,
        )
        # Flat rate should return cost_per_unit_micros regardless of units
        self.assertEqual(rate.calculate_cost_micros(1), 500_000)
        self.assertEqual(rate.calculate_cost_micros(100), 500_000)
        self.assertEqual(rate.calculate_cost_micros(1_000_000), 500_000)

    def test_per_unit_calculate_cost_unchanged(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="output_tokens",
            pricing_type="per_unit",
            cost_per_unit_micros=75_000,
            unit_quantity=1_000_000,
        )
        # Same as existing calculation
        self.assertEqual(rate.calculate_cost_micros(1_000_000), 75_000)
        self.assertEqual(rate.calculate_cost_micros(1_000), 75)

    def test_default_pricing_type_is_per_unit(self):
        rate = Rate.objects.create(
            card=self.card,
            metric_name="default_type",
            cost_per_unit_micros=75_000,
        )
        self.assertEqual(rate.pricing_type, "per_unit")
