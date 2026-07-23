from django.db import connection
from django.test.utils import CaptureQueriesContext

from api.v1.tests.test_ingest_endpoint import IngestEndpointTestBase
from apps.metering.pricing.models import TenantMarkup
from apps.metering.pricing.services import markup_cache


class IngestMarkupQueryCountTest(IngestEndpointTestBase):
    """THE discriminating test for spec §2: markup resolution on the accept
    path is O(1) per batch, not O(n) per event."""

    def setUp(self):
        super().setUp()
        markup_cache._l1.clear()
        markup_cache._ctx_versions.set({})
        TenantMarkup.objects.create(tenant=self.tenant, customer=None,
                                    markup_percentage_micros=10_000_000)

    def test_markup_table_queried_at_most_once_per_batch(self):
        # provider_cost_micros (not billed) forces the markup branch in
        # PricingService.estimate (caller_provider_cost path) for every item.
        events = [self._event(provider_cost_micros=100_000) for _ in range(10)]
        for e in events:
            del e["billed_cost_micros"]
        with CaptureQueriesContext(connection) as ctx:
            resp = self._post(events)
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["accepted"], 10)
        markup_queries = [q for q in ctx.captured_queries
                          if "ubb_tenant_markup" in q["sql"]]
        # One resolve populates the L1 (MarkupService.resolve = up to 2
        # queries: override probe + default); every later item is a dict hit.
        self.assertLessEqual(len(markup_queries), 2)
