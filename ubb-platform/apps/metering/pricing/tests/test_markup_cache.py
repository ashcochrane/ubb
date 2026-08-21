from unittest.mock import patch

from django.test import TestCase

from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import TenantDefaultMarkup
from apps.metering.pricing.services import markup_cache
from apps.metering.pricing.services.markup_cache import MarkupCache
from apps.metering.pricing.services.markup_service import MarkupService


class MarkupCacheTestBase(TestCase):
    def setUp(self):
        # Module-level L1 + contextvar are in-process state: reset per test.
        markup_cache._l1.clear()
        markup_cache._ctx_versions.set({})
        self.tenant = Tenant.objects.create(name="MkCache")


class ResolveParityTest(MarkupCacheTestBase):
    def test_no_markup_configured_negative_cache(self):
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant))
        self.assertIsNone(MarkupService.resolve(self.tenant))

    def test_parity_with_a_declared_rung(self):
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=10_000_000)  # 10%
        MarkupCache.begin_request(self.tenant.id)
        # PARITY IS OVER THE WHOLE RESOLVED VALUE, not over a price built from
        # it: the source is half of what a rung answers, and comparing two
        # figures would let the cache lose it silently.
        self.assertEqual(MarkupCache.resolve(self.tenant),
                         MarkupService.resolve(self.tenant))

    def test_l1_hit_skips_orm(self):
        MarkupCache.begin_request(self.tenant.id)
        MarkupCache.resolve(self.tenant)  # populate (negative)
        with self.assertNumQueries(0):
            MarkupCache.resolve(self.tenant)

    def test_one_tenants_entry_is_not_another_tenants(self):
        """⚠ THE KEY LOST ITS CUSTOMER HALF (#369) AND MUST KEEP THE OTHER.

        A key that dropped the tenant too would serve one tenant's rung to
        every other one, and every case above uses a single tenant, so nothing
        else here would notice.
        """
        other = Tenant.objects.create(name="Other")
        TenantDefaultMarkup.objects.create(tenant=other,
                                           markup_micro_percent=42_000_000)
        MarkupCache.begin_request(self.tenant.id)
        MarkupCache.begin_request(other.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant))
        self.assertEqual(MarkupCache.resolve(other).markup_micro_percent,
                         42_000_000)


class InvalidationTest(MarkupCacheTestBase):
    def test_save_bumps_version_and_next_request_sees_change(self):
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant))
        m = TenantDefaultMarkup.objects.create(  # save() bumps
            tenant=self.tenant, markup_micro_percent=5_000_000)
        MarkupCache.begin_request(self.tenant.id)  # next request re-pins
        got = MarkupCache.resolve(self.tenant)
        self.assertIsNotNone(got)
        self.assertEqual(got.markup_micro_percent, 5_000_000)
        m.delete()  # delete() bumps too
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant))


class RedisDownTest(MarkupCacheTestBase):
    def test_redis_failure_falls_back_to_orm(self):
        # 3% of 100 micros is 3, so the fallback answers 103 — a figure the
        # negative cache's own answer could not produce.
        TenantDefaultMarkup.objects.create(tenant=self.tenant,
                                           markup_micro_percent=3_000_000)
        with patch.object(markup_cache, "_client", side_effect=Exception("down")):
            MarkupCache.begin_request(self.tenant.id)   # swallows, ver=0
            MarkupCache.invalidate(self.tenant.id)      # swallows
            resolved = MarkupCache.resolve(self.tenant)
            # ORM resolve still correct — never "assume none"
            self.assertEqual(resolved.applied_to(100), 103)
