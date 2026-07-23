"""#113: the async accept pipeline behind the metering seam — accept_batch
exercised BELOW HTTP.

The endpoint keeps only HTTP shape (auth/product gates, envelope counters,
problem mapping); everything the pipeline decides — verdicts, holds, raw
durability, idempotency routing, the sync fallback — is asserted here against
the service interface directly. Wire-shape parity for the same flows stays
pinned by api/v1/tests/test_ingest_endpoint.py.

Items are built as real IngestEventIn schema objects: the seam's items are
request-item SHAPED (duck-typed — the service never imports api.*), and using
the real schema keeps this suite honest about that shape.

Same Redis DB-15 cleanup idiom as the endpoint suite — cache.clear()
FLUSHDBs the dedicated test db.
"""
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from api.v1.schemas import IngestEventIn
from apps.billing.gating.services.live_counter import Door
from apps.billing.wallets.models import Wallet
from apps.metering.pricing.services.pricing_service import Unpriceable
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.metering.usage.services import ingest_accept
from apps.metering.usage.services.ingest_accept import (
    IngestAppendFailed, accept_batch, reset_task_meta_cache)
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.platform.tenants.models import Tenant


class AcceptBatchTestBase(TestCase):
    """Prepaid + enforcing tenant with metering_async, one funded customer —
    the endpoint suite's fixture, minus the HTTP client."""

    def setUp(self):
        cache.clear()
        reset_task_meta_cache()
        self.tenant = Tenant.objects.create(
            name="AcceptSeam", products=["metering", "billing", "metering_async"],
            billing_mode="prepaid", enforcement_mode="enforcing",
        )
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="cust1")
        self.wallet = Wallet.objects.create(customer=self.customer, balance_micros=20_000_000)

    def tearDown(self):
        cache.clear()

    def _item(self, **overrides):
        base = {
            "customer_id": str(self.customer.id),
            "request_id": f"req-{uuid.uuid4()}",
            "idempotency_key": f"idem-{uuid.uuid4()}",
            "billed_cost_micros": 1_000_000,
        }
        base.update(overrides)
        return IngestEventIn(**base)


class AcceptBatchVerdictsTest(AcceptBatchTestBase):
    def test_happy_path_verdict_hold_and_raw_row(self):
        results = accept_batch(self.tenant, [self._item(billed_cost_micros=1_500_000)])
        self.assertEqual(len(results), 1)
        r = results[0]
        self.assertTrue(r["accepted"])
        self.assertIsNone(r["code"])
        self.assertEqual(r["mode"], "async")
        self.assertEqual(r["estimated_cost_micros"], 1_500_000)
        self.assertFalse(r["stop"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.estimate_micros, 1_500_000)
        self.assertEqual(raw.status, "pending")
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 1_500_000)

    def test_unknown_customer_rejected_not_found(self):
        results = accept_batch(self.tenant, [self._item(customer_id=str(uuid.uuid4()))])
        r = results[0]
        self.assertFalse(r["accepted"])
        self.assertEqual(r["code"], "not_found")
        self.assertEqual(r["mode"], "async")
        self.assertEqual(RawIngestEvent.objects.count(), 0)

    def test_replay_is_duplicate_suspect_without_second_hold(self):
        item = self._item(billed_cost_micros=500_000)
        first = accept_batch(self.tenant, [item])
        self.assertTrue(first[0]["accepted"])
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 500_000)

        second = accept_batch(self.tenant, [item])  # same idempotency_key
        r2 = second[0]
        self.assertTrue(r2["accepted"])
        self.assertTrue(r2["duplicate_suspect"])
        self.assertEqual(RawIngestEvent.objects.count(), 2)
        self.assertFalse(RawIngestEvent.objects.order_by("created_at").last().held)
        # No second hold: decremented exactly once.
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 500_000)

    def test_unpriceable_routes_through_sync_fallback(self):
        with patch(
            "apps.metering.pricing.services.pricing_service.PricingService.estimate",
            side_effect=Unpriceable("forced for test"),
        ):
            results = accept_batch(self.tenant, [self._item(
                billed_cost_micros=750_000, provider_cost_micros=600_000)])
        r = results[0]
        self.assertTrue(r["accepted"])
        self.assertEqual(r["mode"], "sync_fallback")
        self.assertIsNotNone(r["event_id"])
        # The real UsageEvent already exists — nothing to settle later.
        self.assertTrue(UsageEvent.objects.filter(billed_cost_micros=750_000).exists())
        self.assertEqual(RawIngestEvent.objects.count(), 0)


class AcceptBatchAppendFailureTest(AcceptBatchTestBase):
    def test_append_failure_releases_holds_and_raises_typed(self):
        """The durability boundary surfaces as the seam's TYPED failure —
        holds released and fresh idem keys unwound BEFORE the raise, so the
        endpoint's problem mapping (service_unavailable) stays a pure
        translation with no compensation logic of its own."""
        item = self._item(billed_cost_micros=500_000)
        with patch(
            "apps.metering.usage.models.RawIngestEvent.objects.bulk_create",
            side_effect=RuntimeError("db down"),
        ):
            with self.assertRaises(IngestAppendFailed):
                accept_batch(self.tenant, [item])
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        self.assertEqual(Door.balance(self.customer.id), 20_000_000)

        # The retry is a genuine first accept with a REAL hold (idem unwound).
        retry = accept_batch(self.tenant, [item])
        self.assertTrue(retry[0]["accepted"])
        self.assertFalse(retry[0]["duplicate_suspect"])
        self.assertTrue(RawIngestEvent.objects.get().held)
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 500_000)


class TaskMetaCacheResetSurfaceTest(AcceptBatchTestBase):
    def test_reset_surface_clears_the_module_cache(self):
        """#113 win: the task-metadata L1 cache gets an OWNED reset — callers
        (test fixtures included) stop clearing the private dict."""
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id)
        accept_batch(self.tenant, [self._item(task_id=str(task.id))])
        self.assertIn(str(task.id), ingest_accept._TASK_META_CACHE)
        reset_task_meta_cache()
        self.assertEqual(ingest_accept._TASK_META_CACHE, {})
