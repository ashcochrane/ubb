import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.runs.models import Run
from apps.billing.wallets.models import Wallet
from apps.billing.gating.services.live_ledger_service import LiveLedgerService
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.metering.pricing.services.estimation_service import Unpriceable


class IngestEndpointTestBase(TestCase):
    """Shared fixture: prepaid + enforcing tenant with metering_async enabled,
    one customer with a funded wallet.

    Same Redis DB-15 cleanup idiom as apps/billing/gating/tests/test_hold_service.py
    — cache.clear() FLUSHDBs the dedicated test db, wiping every raw
    ubb:idem:*/livebal:*/runcost:*/stop:* key this test file writes.
    """

    def setUp(self):
        cache.clear()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="AsyncIngest", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)

    def tearDown(self):
        cache.clear()

    def _auth(self):
        return {"HTTP_AUTHORIZATION": f"Bearer {self.raw_key}"}

    def _post(self, events):
        return self.http_client.post(
            "/api/v1/metering/usage/ingest",
            data=json.dumps({"events": events}),
            content_type="application/json",
            **self._auth(),
        )

    def _event(self, **overrides):
        base = {
            "customer_id": str(self.customer.id),
            "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
            "billed_cost_micros": 1_000_000,
        }
        base.update(overrides)
        return base


class HappyPathTest(IngestEndpointTestBase):
    def test_happy_path_verdict_and_raw_row(self):
        resp = self._post([self._event(billed_cost_micros=1_500_000)])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 1)
        self.assertEqual(body["rejected"], 0)
        r = body["results"][0]
        self.assertTrue(r["accepted"])
        self.assertFalse(r["rejected"])
        self.assertFalse(r["stop"])
        self.assertEqual(r["mode"], "async")
        self.assertEqual(r["estimated_cost_micros"], 1_500_000)

        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.estimate_micros, 1_500_000)
        self.assertEqual(raw.status, "pending")
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000 - 1_500_000)


class FloorCrossingTest(IngestEndpointTestBase):
    def test_crossing_item_and_later_items_all_report_stop(self):
        # Same customer/owner -> one acquire() pipeline call for all three
        # items; balance 20_000_000 -> 900_000 leaves headroom, +200_000 more
        # crosses the (default 0) overdraft floor, the third item lands AFTER
        # the crossing. HoldService applies the resulting stop verdict
        # uniformly to every HELD item in that one acquire() call (I3:
        # cooperative — never rejects the crossing hold itself).
        self.wallet.balance_micros = 1_000_000
        self.wallet.save(update_fields=["balance_micros"])
        events = [
            self._event(billed_cost_micros=900_000),
            self._event(billed_cost_micros=200_000),
            self._event(billed_cost_micros=50_000),
        ]
        resp = self._post(events)
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(all(r["accepted"] for r in results))  # cooperative: never rejected
        self.assertTrue(results[1]["stop"])  # the crossing item
        self.assertTrue(results[2]["stop"])  # a later item in the same batch
        self.assertEqual(results[1]["stop_scope"], "customer")
        self.assertEqual(RawIngestEvent.objects.count(), 3)


class RunCapRejectTest(IngestEndpointTestBase):
    def test_run_cap_rejects_without_hold(self):
        run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=500_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([self._event(run_id=str(run.id), billed_cost_micros=600_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertFalse(r["accepted"])
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "cost_limit_exceeded")
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        # Rejection must touch NOTHING on the balance key (no partial hold).
        self.assertIsNone(LiveLedgerService.read_prepaid(self.customer.id))


class IdemReplayTest(IngestEndpointTestBase):
    def test_replay_appends_second_row_without_second_hold(self):
        event = self._event(billed_cost_micros=500_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["results"][0]["accepted"])
        self.assertEqual(RawIngestEvent.objects.count(), 1)
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000 - 500_000)

        second = self._post([event])  # identical customer_id + idempotency_key
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertTrue(r2["duplicate_suspect"])
        self.assertEqual(RawIngestEvent.objects.count(), 2)
        raw_rows = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertFalse(raw_rows[1].held)
        # No second hold: the balance is decremented exactly once.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000 - 500_000)


class UnpriceableSyncFallbackTest(IngestEndpointTestBase):
    def test_unpriceable_routes_through_sync_path(self):
        with patch(
            "apps.metering.pricing.services.estimation_service.EstimationService.estimate",
            side_effect=Unpriceable("forced for test"),
        ):
            resp = self._post([self._event(
                billed_cost_micros=750_000, provider_cost_micros=600_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        self.assertEqual(r["mode"], "sync_fallback")
        self.assertTrue(UsageEvent.objects.filter(billed_cost_micros=750_000).exists())
        # Unpriceable items never produce a RawIngestEvent row (nothing to
        # settle later — the real UsageEvent already exists).
        self.assertEqual(RawIngestEvent.objects.count(), 0)


class MissingProductFlagTest(IngestEndpointTestBase):
    def test_tenant_without_metering_async_gets_403(self):
        plain_tenant = Tenant.objects.create(
            name="NoAsync", products=["metering", "billing"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        key_obj, raw_key = TenantApiKey.create_key(plain_tenant, label="test")
        customer = Customer.objects.create(tenant=plain_tenant, external_id="c2")
        Wallet.objects.create(customer=customer, balance_micros=5_000_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage/ingest",
            data=json.dumps({"events": [{
                "customer_id": str(customer.id), "request_id": "r1",
                "idempotency_key": "k1", "billed_cost_micros": 100_000,
            }]}),
            content_type="application/json",
            HTTP_AUTHORIZATION=f"Bearer {raw_key}",
        )
        self.assertEqual(resp.status_code, 403)
        self.assertEqual(resp.json()["error"], "feature_not_enabled")


class AppendFailureReleasesHoldsTest(IngestEndpointTestBase):
    def test_bulk_create_failure_releases_holds_and_5xxs(self):
        with patch(
            "apps.metering.usage.models.RawIngestEvent.objects.bulk_create",
            side_effect=RuntimeError("db down"),
        ):
            resp = self._post([self._event(billed_cost_micros=500_000)])
        self.assertGreaterEqual(resp.status_code, 500)
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        # The hold taken before the failed append must be fully released.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000)


class BatchSizeBoundsTest(IngestEndpointTestBase):
    def test_empty_batch_is_422(self):
        resp = self._post([])
        self.assertEqual(resp.status_code, 422)

    def test_over_max_batch_is_422(self):
        events = [self._event(billed_cost_micros=1) for _ in range(1001)]
        resp = self._post(events)
        self.assertEqual(resp.status_code, 422)


class RunHeldItemTest(IngestEndpointTestBase):
    def test_run_bearing_item_under_cap_is_held_with_run_id_in_payload(self):
        run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([self._event(run_id=str(run.id), billed_cost_micros=400_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.run_id, run.id)
        self.assertEqual(raw.payload["run_id"], str(run.id))
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000 - 400_000)
