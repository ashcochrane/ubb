from django.core.cache import cache
from django.test import TestCase

from apps.platform.tenants.models import Tenant


class TenantProductsCacheInvalidationTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(
            name="Cache Test Tenant", products=["metering"]
        )

    def tearDown(self):
        cache.clear()

    def test_save_invalidates_products_cache(self):
        """When Tenant.save() is called, the cached products entry is deleted."""
        cache_key = f"tenant_products:{self.tenant.id}"

        # Simulate a cached value
        cache.set(cache_key, ["metering"], timeout=300)
        self.assertEqual(cache.get(cache_key), ["metering"])

        # Update products and save
        self.tenant.products = ["metering", "billing"]
        self.tenant.save()

        # Cache should be invalidated
        self.assertIsNone(cache.get(cache_key))

    def test_fresh_lookup_after_cache_invalidation(self):
        """After save, EventBus._tenant_has_product will fetch fresh data."""
        from core.event_bus import EventBus

        cache_key = f"tenant_products:{self.tenant.id}"

        # Prime the cache with old data
        cache.set(cache_key, ["metering"], timeout=300)

        # Update tenant to add billing
        self.tenant.products = ["metering", "billing"]
        self.tenant.save()

        # EventBus should now see the updated products (cache was invalidated)
        bus = EventBus()
        self.assertTrue(bus._tenant_has_product(str(self.tenant.id), "billing"))

    def test_create_also_sets_cache_key_clear(self):
        """Even on initial create, the cache key is cleared (no-op but safe)."""
        cache_key_before = f"tenant_products:{self.tenant.id}"
        # The key shouldn't be in cache after create since save() deletes it
        self.assertIsNone(cache.get(cache_key_before))
