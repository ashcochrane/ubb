from django.test import TestCase

from apps.metering.pricing.models import TenantMarkup
from apps.platform.tenants.models import Tenant


class TenantMarkupMarginTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_margin_pct_default_zero(self):
        """Default margin_pct should be 0."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
        )
        self.assertEqual(markup.margin_pct, 0)

    def test_apply_margin_zero_passthrough(self):
        """0% margin means pass-through: $1.00 -> $1.00."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            margin_pct=0,
        )
        # $1.00 = 1_000_000 micros
        result = markup.apply_margin(1_000_000)
        self.assertEqual(result, 1_000_000)

    def test_apply_margin_fifty_percent(self):
        """50% margin: $1.00 / 0.50 = $2.00."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            margin_pct=50,
        )
        result = markup.apply_margin(1_000_000)
        self.assertEqual(result, 2_000_000)

    def test_apply_margin_sixty_percent(self):
        """60% margin: $1.00 / 0.40 = $2.50."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            margin_pct=60,
        )
        result = markup.apply_margin(1_000_000)
        self.assertEqual(result, 2_500_000)

    def test_apply_margin_eighty_percent(self):
        """80% margin: $1.00 / 0.20 = $5.00."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
            event_type="llm_call",
            margin_pct=80,
        )
        result = markup.apply_margin(1_000_000)
        self.assertEqual(result, 5_000_000)
