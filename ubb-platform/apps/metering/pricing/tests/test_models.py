from django.test import TestCase

from apps.metering.pricing.models import TenantMarkup
from apps.platform.tenants.models import Tenant


class TenantMarkupTests(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Test Tenant")

    def test_percentage_only(self):
        """50% markup on 1,000,000 micros = 500,000 micros."""
        markup = TenantMarkup.objects.create(
            tenant=self.tenant,
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
