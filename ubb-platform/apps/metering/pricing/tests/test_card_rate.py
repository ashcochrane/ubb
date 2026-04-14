import hashlib
import json

from django.db import IntegrityError
from django.test import TestCase

from apps.metering.pricing.models import Card, Rate
from apps.platform.tenants.models import Tenant


class CardModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_create_card(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
        )
        card.refresh_from_db()
        self.assertEqual(card.name, "GPT-4o Pricing")
        self.assertEqual(card.provider, "openai")
        self.assertEqual(card.event_type, "llm_call")
        self.assertEqual(card.dimensions, {"model": "gpt-4o"})
        self.assertEqual(card.status, "active")
        self.assertTrue(len(card.dimensions_hash) > 0)

    def test_dimensions_hash_computed_on_save(self):
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
        )
        expected = hashlib.sha256(
            json.dumps({"model": "gpt-4o"}, sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(card.dimensions_hash, expected)

    def test_unique_active_card(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
        )
        with self.assertRaises(IntegrityError):
            Card.objects.create(
                tenant=self.tenant,
                name="GPT-4o Pricing Duplicate",
                provider="openai",
                event_type="llm_call",
                dimensions={"model": "gpt-4o"},
            )

    def test_archived_card_does_not_conflict(self):
        Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing Old",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
            status="archived",
        )
        # Should NOT raise — archived cards are excluded from unique constraint
        card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing New",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
        )
        self.assertEqual(card.status, "active")


class RateModelTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")
        self.card = Card.objects.create(
            tenant=self.tenant,
            name="GPT-4o Pricing",
            provider="openai",
            event_type="llm_call",
            dimensions={"model": "gpt-4o"},
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
