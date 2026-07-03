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
        # The run-metadata L1 cache is module-level in-process state; clear it
        # so a status cached by one test can never leak into another.
        from api.v1 import metering_endpoints
        metering_endpoints._RUN_META_CACHE.clear()
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


class RejectionDoesNotBurnIdemKeyTest(IngestEndpointTestBase):
    """Local rejections (run_not_active, validation) must run BEFORE the
    idempotency SETNX pipeline, or the rejected attempt burns the key: the
    client's legitimate retry after fixing the problem would then misread as
    an idem-hit — appended with held=False, i.e. accepted spend with NO hold
    ever taken (a one-event enforcement bypass on the retry path)."""

    def test_run_not_active_rejection_then_retry_is_genuine_first_accept(self):
        killed_run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="killed",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id,
        )
        event = self._event(run_id=str(killed_run.id), billed_cost_micros=400_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        r1 = first.json()["results"][0]
        self.assertTrue(r1["rejected"])
        self.assertEqual(r1["reason"], "run_not_active")
        self.assertIsNone(LiveLedgerService.read_prepaid(self.customer.id))

        active_run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id,
        )
        event["run_id"] = str(active_run.id)  # SAME idempotency_key
        second = self._post([event])
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        # A REAL hold this time — the rejection must not have burned the key.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         20_000_000 - 400_000)
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)

    def test_currency_mismatch_rejection_then_retry_is_genuine_first_accept(self):
        event = self._event(currency="eur", billed_cost_micros=300_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        r1 = first.json()["results"][0]
        self.assertTrue(r1["rejected"])
        self.assertEqual(r1["reason"], "validation_error")
        self.assertIsNone(LiveLedgerService.read_prepaid(self.customer.id))

        del event["currency"]  # corrected; SAME idempotency_key
        second = self._post([event])
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         20_000_000 - 300_000)
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)


class RunMetaCacheEvictionTest(IngestEndpointTestBase):
    def test_clear_on_full_with_mixed_cached_and_new_runs_does_not_500(self):
        """Clear-on-full regression: with the cache at _RUN_META_MAX, a batch
        mixing an already-cached run and an uncached one triggers the clear —
        the entries fresh for THIS call must survive into the return value
        (the first cut re-read the module cache after clearing it: KeyError)."""
        from api.v1 import metering_endpoints
        run_a = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id)
        run_b = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id)
        with patch.object(metering_endpoints, "_RUN_META_MAX", 1):
            first = self._post([self._event(run_id=str(run_a.id), billed_cost_micros=100_000)])
            self.assertEqual(first.status_code, 200)  # caches run_a; cache now AT the max
            resp = self._post([
                self._event(run_id=str(run_a.id), billed_cost_micros=100_000),
                self._event(run_id=str(run_b.id), billed_cost_micros=100_000),
            ])
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(results[0]["accepted"])
        self.assertTrue(results[1]["accepted"])


class AppendFailureIdemUnwindTest(IngestEndpointTestBase):
    def test_retry_after_append_failure_takes_real_holds(self):
        """The append-failure 503 is the DESIGNED recovery path: the client
        retries the same batch. The failed attempt must unwind the idem keys
        it freshly set, or the retry reads as all idem-hits — appended
        held=False with no hold ever taken (money-gate bypass)."""
        event = self._event(billed_cost_micros=500_000)
        with patch(
            "apps.metering.usage.models.RawIngestEvent.objects.bulk_create",
            side_effect=RuntimeError("db down"),
        ):
            first = self._post([event])
        self.assertGreaterEqual(first.status_code, 500)
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id), 20_000_000)

        retry = self._post([event])  # identical batch, identical idem key
        self.assertEqual(retry.status_code, 200)
        r = retry.json()["results"][0]
        self.assertTrue(r["accepted"])
        self.assertFalse(r["duplicate_suspect"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        # A REAL hold on the retry — decremented exactly once overall.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         20_000_000 - 500_000)


class DeadRunReplayWinsTest(IngestEndpointTestBase):
    def test_idem_hit_on_killed_run_is_replay_not_rejection(self):
        """Replay-wins parity with the sync path (record_usage returns the
        existing event BEFORE any validation): a replayed key whose run has
        since been killed must be accepted as a duplicate suspect (held=False
        append, no hold), not rejected run_not_active."""
        from api.v1 import metering_endpoints
        run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id)
        event = self._event(run_id=str(run.id), billed_cost_micros=400_000)
        first = self._post([event])
        self.assertTrue(first.json()["results"][0]["accepted"])

        Run.objects.filter(id=run.id).update(status="killed")
        metering_endpoints._RUN_META_CACHE.clear()  # the 30s cache would mask the kill

        second = self._post([event])  # SAME idempotency_key
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertTrue(r2["duplicate_suspect"])
        self.assertFalse(r2["rejected"])
        rows = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[1].held)
        # No second hold taken for the replay.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         20_000_000 - 400_000)

    def test_fresh_key_on_killed_run_still_rejected_without_burning_key(self):
        run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="killed",
            balance_snapshot_micros=20_000_000, cost_limit_micros=5_000_000,
            billing_owner_id=self.customer.id)
        event = self._event(run_id=str(run.id), billed_cost_micros=400_000)
        resp = self._post([event])
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "run_not_active")
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        self.assertIsNone(LiveLedgerService.read_prepaid(self.customer.id))


class EffectiveAtTest(IngestEndpointTestBase):
    def test_naive_effective_at_rejected_before_idem_no_burned_key(self):
        event = self._event(billed_cost_micros=200_000,
                            effective_at="2026-07-01T00:00:00")  # no tz
        resp = self._post([event])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "effective_at_naive")
        self.assertIsNone(LiveLedgerService.read_prepaid(self.customer.id))
        # Rejection precedes the SETNX: the corrected retry (same key) is a
        # genuine first accept with a real hold.
        event["effective_at"] = "2026-07-01T00:00:00Z"
        second = self._post([event])
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         20_000_000 - 200_000)

    def test_too_old_effective_at_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        too_old = (timezone.now() - timedelta(days=60)).isoformat()  # window default 34d
        resp = self._post([self._event(billed_cost_micros=200_000, effective_at=too_old)])
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "effective_at_too_old")
        self.assertEqual(RawIngestEvent.objects.count(), 0)

    def test_valid_effective_at_accepted_and_preserved_in_payload(self):
        from datetime import datetime, timedelta
        from django.utils import timezone
        eff = timezone.now() - timedelta(days=1)
        resp = self._post([self._event(billed_cost_micros=200_000,
                                       effective_at=eff.isoformat())])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        # Round-trip: settlement must be able to price as_of the ORIGINAL
        # effective instant from the stored payload.
        stored = datetime.fromisoformat(raw.payload["effective_at"])
        self.assertEqual(stored, eff)


class MixedBatchTest(IngestEndpointTestBase):
    def test_positional_alignment_and_exactly_one_new_hold(self):
        """One request mixing all four verdict shapes: [valid held item,
        run-cap reject, idem-hit replay, currency-mismatch reject]. Results
        must align positionally and exactly ONE new hold may be taken."""
        capped_run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=100_000,
            billing_owner_id=self.customer.id)
        replay_event = self._event(billed_cost_micros=250_000)
        pre = self._post([replay_event])  # seed the idem-hit item (takes a hold)
        self.assertTrue(pre.json()["results"][0]["accepted"])
        balance_before = LiveLedgerService.read_prepaid(self.customer.id)
        raw_before = RawIngestEvent.objects.count()

        resp = self._post([
            self._event(billed_cost_micros=500_000),                             # 0: held
            self._event(run_id=str(capped_run.id), billed_cost_micros=600_000),  # 1: run-cap
            replay_event,                                                        # 2: idem-hit
            self._event(currency="eur", billed_cost_micros=100_000),             # 3: currency
        ])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        r0, r1, r2, r3 = body["results"]
        self.assertTrue(r0["accepted"] and not r0["duplicate_suspect"])
        self.assertEqual(r0["estimated_cost_micros"], 500_000)
        self.assertTrue(r1["rejected"])
        self.assertEqual(r1["reason"], "cost_limit_exceeded")
        self.assertTrue(r2["accepted"] and r2["duplicate_suspect"])
        self.assertTrue(r3["rejected"])
        self.assertEqual(r3["reason"], "validation_error")
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["rejected"], 2)
        # Exactly one NEW hold (the valid item); replay + rejects take none.
        self.assertEqual(LiveLedgerService.read_prepaid(self.customer.id),
                         balance_before - 500_000)
        # Two new raw rows: the held item + the held=False replay append.
        self.assertEqual(RawIngestEvent.objects.count(), raw_before + 2)


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
