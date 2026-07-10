from unittest.mock import patch

from django.test import TestCase

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services import markup_cache
from apps.metering.pricing.services.markup_cache import MarkupCache
from apps.metering.pricing.services.markup_service import MarkupService


class MarkupCacheTestBase(TestCase):
    def setUp(self):
        # Module-level L1 + contextvar are in-process state: reset per test.
        markup_cache._l1.clear()
        markup_cache._ctx_versions.set({})
        self.tenant = Tenant.objects.create(name="MkCache")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="mc1")


class ResolveParityTest(MarkupCacheTestBase):
    def test_no_markup_configured_negative_cache(self):
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant, self.customer))
        self.assertEqual(MarkupCache.apply(1_000_000, tenant=self.tenant,
                                           customer=self.customer), 1_000_000)

    def test_parity_default_and_override(self):
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=10_000_000)  # 10%
        TenantMarkup.objects.create(tenant=self.tenant, customer=self.customer,
                                    fixed_uplift_micros=7)
        MarkupCache.begin_request(self.tenant.id)
        for cust in (self.customer, None):
            self.assertEqual(
                MarkupCache.apply(1_000_000, tenant=self.tenant, customer=cust),
                MarkupService.apply(1_000_000, tenant=self.tenant, customer=cust))

    def test_l1_hit_skips_orm(self):
        MarkupCache.begin_request(self.tenant.id)
        MarkupCache.resolve(self.tenant, self.customer)  # populate (negative)
        with self.assertNumQueries(0):
            MarkupCache.resolve(self.tenant, self.customer)


class InvalidationTest(MarkupCacheTestBase):
    def test_save_bumps_version_and_next_request_sees_change(self):
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant, self.customer))
        m = TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                        fixed_uplift_micros=5)  # save() bumps
        MarkupCache.begin_request(self.tenant.id)  # next request re-pins
        got = MarkupCache.resolve(self.tenant, self.customer)
        self.assertIsNotNone(got)
        self.assertEqual(got.fixed_uplift_micros, 5)
        m.delete()  # delete() bumps too
        MarkupCache.begin_request(self.tenant.id)
        self.assertIsNone(MarkupCache.resolve(self.tenant, self.customer))


class RedisDownTest(MarkupCacheTestBase):
    def test_redis_failure_falls_back_to_orm(self):
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    fixed_uplift_micros=3)
        with patch.object(markup_cache, "_client", side_effect=Exception("down")):
            MarkupCache.begin_request(self.tenant.id)   # swallows, ver=0
            MarkupCache.invalidate(self.tenant.id)      # swallows
            self.assertEqual(
                MarkupCache.apply(100, tenant=self.tenant, customer=self.customer),
                103)  # ORM resolve still correct — never "assume none"
