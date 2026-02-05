import hashlib
import json

from django.test import TestCase

from apps.pricing.models import ProviderRate, TenantMarkup
from apps.platform.tenants.models import Tenant


class ProviderRateTests(TestCase):
    def setUp(self):
        self.rate = ProviderRate.objects.create(
            provider="openai",
            event_type="llm_call",
            metric_name="input_tokens",
            dimensions={"model": "gpt-4o"},
            cost_per_unit_micros=5_000,
            unit_quantity=1_000_000,
        )

    def test_calculate_cost_micros_known_values(self):
        """1,000 units at 5,000 micros per 1M units = 5 micros (truncated)."""
        result = self.rate.calculate_cost_micros(1_000)
        # (1_000 * 5_000 + 500_000) // 1_000_000 = 5_500_000 // 1_000_000 = 5
        self.assertEqual(result, 5)

    def test_calculate_cost_micros_round_half_up(self):
        """Verify round-half-up: exact midpoint rounds up."""
        rate = ProviderRate.objects.create(
            provider="openai",
            event_type="llm_call",
            metric_name="output_tokens",
            dimensions={},
            cost_per_unit_micros=1,
            unit_quantity=2,
        )
        # units=1: (1 * 1 + 1) // 2 = 1  (midpoint rounds up)
        self.assertEqual(rate.calculate_cost_micros(1), 1)
        # units=0: (0 * 1 + 1) // 2 = 0
        self.assertEqual(rate.calculate_cost_micros(0), 0)

    def test_dimensions_hash_computed_on_save(self):
        """save() should compute SHA-256 of sorted JSON dimensions."""
        expected = hashlib.sha256(
            json.dumps({"model": "gpt-4o"}, sort_keys=True).encode()
        ).hexdigest()
        self.assertEqual(self.rate.dimensions_hash, expected)

    def test_dimensions_hash_empty_dict(self):
        """Empty dimensions should still produce a valid hash."""
        rate = ProviderRate.objects.create(
            provider="anthropic",
            event_type="llm_call",
            metric_name="input_tokens",
            dimensions={},
            cost_per_unit_micros=3_000,
        )
        expected = hashlib.sha256(b"{}").hexdigest()
        self.assertEqual(rate.dimensions_hash, expected)


class TenantMarkupTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_percentage_only(self):
        """50% markup on 1,000,000 micros = 500,000 micros."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            markup_percentage_micros=50_000_000,  # 50%
            fixed_uplift_micros=0,
        )
        result = markup.calculate_markup_micros(1_000_000)
        # (1_000_000 * 50_000_000 + 50_000_000) // 100_000_000 + 0
        # = 50_050_000_000 // 100_000_000 = 500
        # Wait: let's recalculate properly.
        # (1_000_000 * 50_000_000 + 50_000_000) // 100_000_000
        # = (50_000_000_000_000 + 50_000_000) // 100_000_000
        # = 50_000_050_000_000 // 100_000_000
        # = 500_000
        self.assertEqual(result, 500_000)

    def test_percentage_plus_fixed_uplift(self):
        """50% markup + 100 fixed uplift on 1,000,000 micros = 500,100 micros."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            markup_percentage_micros=50_000_000,  # 50%
            fixed_uplift_micros=100,
        )
        result = markup.calculate_markup_micros(1_000_000)
        self.assertEqual(result, 500_100)

    def test_zero_markup(self):
        """Zero markup should return only the fixed uplift."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            markup_percentage_micros=0,
            fixed_uplift_micros=250,
        )
        result = markup.calculate_markup_micros(1_000_000)
        # (1_000_000 * 0 + 50_000_000) // 100_000_000 + 250 = 0 + 250 = 250
        self.assertEqual(result, 250)
