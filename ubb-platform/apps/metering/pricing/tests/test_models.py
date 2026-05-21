from django.test import TestCase

from apps.metering.pricing.models import Card, Rate
from apps.platform.tenants.models import Tenant


class RateProviderCostTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="T", products=["metering"])
        self.card = Card.objects.create(
            tenant=self.tenant, name="C", slug="c",
            provider="openai",
        )

    def test_provider_cost_defaults_to_null(self):
        rate = Rate.objects.create(
            card=self.card, metric_name="input_tokens",
            cost_per_unit_micros=1_000, unit_quantity=1_000_000,
        )
        self.assertIsNone(rate.provider_cost_per_unit_micros)

    def test_provider_cost_can_be_set(self):
        rate = Rate.objects.create(
            card=self.card, metric_name="output_tokens",
            cost_per_unit_micros=1_500, provider_cost_per_unit_micros=1_000,
            unit_quantity=1_000_000,
        )
        rate.refresh_from_db()
        self.assertEqual(rate.provider_cost_per_unit_micros, 1_000)
        self.assertEqual(rate.cost_per_unit_micros, 1_500)
