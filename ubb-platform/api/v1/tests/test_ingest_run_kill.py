import json
import time
import threading
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import Client, TransactionTestCase

from api.v1.tests.test_ingest_endpoint import IngestEndpointTestBase
from apps.platform.customers.models import Customer
from apps.platform.events.models import OutboxEvent
from apps.platform.runs.models import Run
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.billing.wallets.models import Wallet


def _stale_active_meta(run, customer):
    """A run-meta cache entry claiming the run is still active — simulates a
    second web process whose cache hasn't observed the kill yet."""
    return (run.cost_limit_micros, 0, "active", str(customer.id),
            time.monotonic() + 30)


class IngestRunKillTest(IngestEndpointTestBase):
    def _run(self, cap=500_000):
        return Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=cap,
            billing_owner_id=self.customer.id,
        )

    def test_cap_rejection_kills_run_and_emits_event(self):
        run = self._run(cap=500_000)
        resp = self._post([self._event(billed_cost_micros=1_000_000,
                                       run_id=str(run.id))])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "cost_limit_exceeded")
        run.refresh_from_db()
        self.assertEqual(run.status, "killed")
        self.assertEqual(run.metadata.get("kill_reason"), "cost_limit_exceeded")
        events = OutboxEvent.objects.filter(event_type="run.limit_exceeded")
        self.assertEqual(events.count(), 1)
        payload = events.get().payload
        self.assertEqual(payload["run_id"], str(run.id))
        self.assertEqual(payload["scope"], "run")

    def test_next_batch_rejects_run_not_active(self):
        run = self._run(cap=500_000)
        self._post([self._event(billed_cost_micros=1_000_000, run_id=str(run.id))])
        resp = self._post([self._event(billed_cost_micros=100_000, run_id=str(run.id))])
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        # Cache was invalidated by the kill: rejection is run_not_active
        # (dead-run prefilter), NOT another cost_limit_exceeded round trip.
        self.assertEqual(r["reason"], "run_not_active")
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 1)

    def test_stale_cache_rekill_emits_no_second_event(self):
        run = self._run(cap=500_000)
        self._post([self._event(billed_cost_micros=1_000_000, run_id=str(run.id))])
        # Simulate another process's stale cache: re-seed "active".
        from api.v1 import metering_endpoints
        metering_endpoints._RUN_META_CACHE[str(run.id)] = _stale_active_meta(
            run, self.customer)
        resp = self._post([self._event(billed_cost_micros=1_000_000,
                                       run_id=str(run.id))])
        r = resp.json()["results"][0]
        self.assertTrue(r["rejected"])
        self.assertEqual(r["reason"], "cost_limit_exceeded")  # Lua still caps
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 1)

    def test_append_failure_skips_kill_retry_kills(self):
        run = self._run(cap=500_000)
        # Mixed batch: one plain accept (forces a bulk_create) + one over-cap.
        batch = [self._event(billed_cost_micros=100_000),
                 self._event(billed_cost_micros=1_000_000, run_id=str(run.id))]
        with patch("apps.metering.usage.models.RawIngestEvent.objects.bulk_create",
                   side_effect=Exception("db down")):
            resp = self._post(batch)
        self.assertEqual(resp.status_code, 503)
        run.refresh_from_db()
        self.assertEqual(run.status, "active")  # no kill on the 503 path
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 0)
        resp = self._post(batch)  # client retry (idem keys were unwound)
        self.assertEqual(resp.status_code, 200)
        run.refresh_from_db()
        self.assertEqual(run.status, "killed")
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 1)

    def test_kill_failure_never_500s_batch(self):
        run = self._run(cap=500_000)
        with patch("apps.platform.runs.services.RunService.kill_run",
                   side_effect=Exception("lock timeout")):
            resp = self._post([self._event(billed_cost_micros=1_000_000,
                                           run_id=str(run.id))])
        self.assertEqual(resp.status_code, 200)  # verdicts already correct
        self.assertEqual(resp.json()["results"][0]["reason"], "cost_limit_exceeded")

    def test_sync_then_async_and_async_then_sync_parity(self):
        # async kills; sync single on the same run -> 409 run_not_active.
        run = self._run(cap=500_000)
        self._post([self._event(billed_cost_micros=1_000_000, run_id=str(run.id))])
        resp = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(self._event(billed_cost_micros=100_000,
                                        run_id=str(run.id))),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 409)
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 1)
        # sync kills; async batch on the same run -> run_not_active, no 2nd event.
        run2 = self._run(cap=500_000)
        resp = self.http_client.post(
            "/api/v1/metering/usage",
            data=json.dumps(self._event(billed_cost_micros=1_000_000,
                                        run_id=str(run2.id))),
            content_type="application/json", **self._auth())
        self.assertEqual(resp.status_code, 429)
        resp = self._post([self._event(billed_cost_micros=100_000,
                                       run_id=str(run2.id))])
        self.assertEqual(resp.json()["results"][0]["reason"], "run_not_active")
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 2)


class ConcurrentKillRaceTest(TransactionTestCase):
    """Two batches racing the same capped run -> exactly one transition,
    exactly one RunLimitExceeded. TransactionTestCase (not TestCase): threads
    need their own DB connections to SEE each other's committed rows — under
    TestCase's wrapping transaction the race never actually happens."""

    def setUp(self):
        cache.clear()
        from api.v1 import metering_endpoints
        metering_endpoints._RUN_META_CACHE.clear()
        self.tenant = Tenant.objects.create(
            name="KillRace", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="t")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="race1")
        Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)
        self.run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, cost_limit_micros=500_000,
            billing_owner_id=self.customer.id,
        )

    def tearDown(self):
        cache.clear()

    def _post(self, client):
        from django.db import connection
        try:
            return client.post(
                "/api/v1/metering/usage/ingest",
                data=json.dumps({"events": [{
                    "customer_id": str(self.customer.id),
                    "request_id": f"req-{uuid.uuid4()}",
                    "idempotency_key": f"idem-{uuid.uuid4()}",
                    "billed_cost_micros": 1_000_000,
                    "run_id": str(self.run.id),
                }]}),
                content_type="application/json",
                HTTP_AUTHORIZATION=f"Bearer {self.raw_key}",
            )
        finally:
            connection.close()

    def test_concurrent_cap_breaches_single_kill_single_event(self):
        results = [None, None]

        def worker(idx):
            results[idx] = self._post(Client())

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        for r in results:
            self.assertEqual(r.status_code, 200)
            body = r.json()["results"][0]
            self.assertTrue(body["rejected"])
            self.assertIn(body["reason"], ("cost_limit_exceeded", "run_not_active"))
        self.run.refresh_from_db()
        self.assertEqual(self.run.status, "killed")
        self.assertEqual(
            OutboxEvent.objects.filter(event_type="run.limit_exceeded").count(), 1)
