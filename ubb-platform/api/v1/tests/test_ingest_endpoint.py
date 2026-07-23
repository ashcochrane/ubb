import json
import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase, Client

from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.platform.tasks.models import Task
from apps.billing.wallets.models import Wallet
from apps.billing.gating.services.live_counter import Door
from apps.metering.usage.models import RawIngestEvent, UsageEvent
from apps.metering.pricing.services.pricing_service import Unpriceable


class IngestEndpointTestBase(TestCase):
    """Shared fixture: prepaid + enforcing tenant with metering_async enabled,
    one customer with a funded wallet.

    Same Redis DB-15 cleanup idiom as apps/billing/gating/tests/test_hold_lane.py
    — cache.clear() FLUSHDBs the dedicated test db, wiping every raw
    ubb:idem:*/livebal:*/stop:* key this test file writes.
    """

    def setUp(self):
        cache.clear()
        # The task-metadata L1 cache is module-level in-process state; reset it
        # so an entry cached by one test can never leak into another (#113:
        # through the seam's owned reset surface, not the private dict).
        from apps.metering.usage.services.ingest_accept import reset_task_meta_cache
        reset_task_meta_cache()
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
        self.assertNotIn("rejected", r)  # #78: the per-item boolean is gone
        self.assertIsNone(r["code"])
        self.assertIsNone(r["detail"])
        self.assertFalse(r["stop"])
        self.assertEqual(r["mode"], "async")
        self.assertEqual(r["estimated_cost_micros"], 1_500_000)

        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.estimate_micros, 1_500_000)
        self.assertEqual(raw.status, "pending")
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 1_500_000)


class FloorCrossingTest(IngestEndpointTestBase):
    def test_crossing_item_and_later_items_all_report_stop(self):
        # Same customer/owner -> one acquire() pipeline call for all three
        # items; balance 20_000_000 -> 900_000 leaves headroom, +200_000 more
        # crosses the (default 0) overdraft floor, the third item lands AFTER
        # the crossing. The hold lane applies the resulting stop verdict
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


class TaskLimitAcceptAlwaysTest(IngestEndpointTestBase):
    def test_over_limit_item_is_accepted_and_held(self):
        """One-rule (#37): the accept-time unit-cap lane is retired. An item
        that would blow straight past a tiny task provider limit is still
        ACCEPTED and held — no cost_limit_exceeded rejection reason exists;
        task-limit detection happens at settle with exact provider costs."""
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000, provider_cost_limit_micros=500_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([self._event(task_id=str(task.id),
                                       billed_cost_micros=600_000,
                                       provider_cost_micros=600_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        self.assertIsNone(r["code"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.task_id, task.id)
        # A real hold was taken; accept never kills.
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 600_000)
        task.refresh_from_db()
        self.assertEqual(task.status, "active")


class IdemReplayTest(IngestEndpointTestBase):
    def test_replay_appends_second_row_without_second_hold(self):
        event = self._event(billed_cost_micros=500_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        self.assertTrue(first.json()["results"][0]["accepted"])
        self.assertEqual(RawIngestEvent.objects.count(), 1)
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 500_000)

        second = self._post([event])  # identical customer_id + idempotency_key
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertTrue(r2["duplicate_suspect"])
        self.assertEqual(RawIngestEvent.objects.count(), 2)
        raw_rows = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertFalse(raw_rows[1].held)
        # No second hold: the balance is decremented exactly once.
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 500_000)


class UnpriceableSyncFallbackTest(IngestEndpointTestBase):
    def test_unpriceable_routes_through_sync_path(self):
        with patch(
            "apps.metering.pricing.services.pricing_service.PricingService.estimate",
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


class SyncFallbackRejectionIdemUnwindTest(IngestEndpointTestBase):
    """Final-review fix batch #4: an Unpriceable item's idem key is SET by
    the accept-time prefilter; if the inline sync fallback then REJECTS it
    (e.g. a strict-coverage PricingError), the key must not stay burned — or
    a retry misreads as an idem-hit (accepted, held=False, no hold ever
    taken) and settle would re-raise the same poison payload into a false
    "failed" incident."""

    def test_sync_fallback_rejection_unwinds_idem_key_for_genuine_retry(self):
        self.tenant.require_cost_card_coverage = True
        self.tenant.save(update_fields=["require_cost_card_coverage"])
        event = self._event(billed_cost_micros=None, usage_metrics={"tokens": 100})

        resp = self._post([event])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertFalse(r["accepted"])
        self.assertEqual(r["mode"], "sync_fallback")
        self.assertEqual(r["code"], "pricing_error")
        # sync_fallback rejections are the one lane whose verdicts carry the
        # sync error detail (#78).
        self.assertIsNotNone(r["detail"])
        self.assertEqual(UsageEvent.objects.count(), 0)
        self.assertEqual(RawIngestEvent.objects.count(), 0)

        from apps.metering.usage.services.ingest_accept import _idem_key
        key = _idem_key(self.tenant.id, self.customer.id, event["idempotency_key"])
        import redis
        from django.conf import settings
        client = redis.from_url(settings.REDIS_URL)
        self.assertFalse(client.exists(key))  # unburned

        retry = self._post([event])  # identical batch, identical idem key
        self.assertEqual(retry.status_code, 200)
        r2 = retry.json()["results"][0]
        # A genuine first attempt -- same rejection again, NOT a replay.
        self.assertFalse(r2["accepted"])
        self.assertEqual(r2["mode"], "sync_fallback")
        self.assertEqual(r2["code"], "pricing_error")
        self.assertFalse(r2["duplicate_suspect"])
        self.assertEqual(UsageEvent.objects.count(), 0)
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
        self.assertEqual(resp["Content-Type"], "application/problem+json")
        self.assertEqual(resp.json()["code"], "feature_not_enabled")


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
        self.assertEqual(Door.balance(self.customer.id), 20_000_000)


class BatchSizeBoundsTest(IngestEndpointTestBase):
    def test_empty_batch_is_422(self):
        resp = self._post([])
        self.assertEqual(resp.status_code, 422)

    def test_over_max_batch_is_422(self):
        events = [self._event(billed_cost_micros=1) for _ in range(1001)]
        resp = self._post(events)
        self.assertEqual(resp.status_code, 422)


class RejectionDoesNotBurnIdemKeyTest(IngestEndpointTestBase):
    """Local rejections (unknown task, validation) must run BEFORE the
    idempotency SETNX pipeline, or the rejected attempt burns the key: the
    client's legitimate retry after fixing the problem would then misread as
    an idem-hit — appended with held=False, i.e. accepted spend with NO hold
    ever taken (a one-event enforcement bypass on the retry path)."""

    def test_unknown_task_rejection_then_retry_is_genuine_first_accept(self):
        import uuid as _uuid
        event = self._event(task_id=str(_uuid.uuid4()),  # no such task
                            billed_cost_micros=400_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        r1 = first.json()["results"][0]
        self.assertFalse(r1["accepted"])
        self.assertEqual(r1["code"], "not_found")
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        self.assertIsNone(Door.balance(self.customer.id))

        real_task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id,
        )
        event["task_id"] = str(real_task.id)  # fixed; SAME idempotency_key
        second = self._post([event])
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        # A REAL hold this time — the rejection must not have burned the key.
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 400_000)
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)

    def test_currency_mismatch_rejection_then_retry_is_genuine_first_accept(self):
        event = self._event(currency="eur", billed_cost_micros=300_000)
        first = self._post([event])
        self.assertEqual(first.status_code, 200)
        r1 = first.json()["results"][0]
        self.assertFalse(r1["accepted"])
        self.assertEqual(r1["code"], "validation_error")
        self.assertIsNone(Door.balance(self.customer.id))

        del event["currency"]  # corrected; SAME idempotency_key
        second = self._post([event])
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 300_000)
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)


class TaskMetaCacheEvictionTest(IngestEndpointTestBase):
    def test_clear_on_full_with_mixed_cached_and_new_tasks_does_not_500(self):
        """Clear-on-full regression: with the cache at _TASK_META_MAX, a batch
        mixing an already-cached task and an uncached one triggers the clear —
        the entries fresh for THIS call must survive into the return value
        (the first cut re-read the module cache after clearing it: KeyError).
        Entries are (customer_id_str|None, expires) — existence/ownership only."""
        from apps.metering.usage.services import ingest_accept
        task_a = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id)
        task_b = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id)
        with patch.object(ingest_accept, "_TASK_META_MAX", 1):
            first = self._post([self._event(task_id=str(task_a.id), billed_cost_micros=100_000)])
            self.assertEqual(first.status_code, 200)  # caches task_a; cache now AT the max
            resp = self._post([
                self._event(task_id=str(task_a.id), billed_cost_micros=100_000),
                self._event(task_id=str(task_b.id), billed_cost_micros=100_000),
            ])
        self.assertEqual(resp.status_code, 200)
        results = resp.json()["results"]
        self.assertTrue(results[0]["accepted"])
        self.assertTrue(results[1]["accepted"])
        # The cache holds (customer_id_str|None, expires) tuples.
        entry = ingest_accept._TASK_META_CACHE.get(str(task_b.id))
        self.assertIsNotNone(entry)
        self.assertEqual(entry[0], str(self.customer.id))


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
        self.assertEqual(Door.balance(self.customer.id), 20_000_000)

        retry = self._post([event])  # identical batch, identical idem key
        self.assertEqual(retry.status_code, 200)
        r = retry.json()["results"][0]
        self.assertTrue(r["accepted"])
        self.assertFalse(r["duplicate_suspect"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        # A REAL hold on the retry — decremented exactly once overall.
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 500_000)


class KilledTaskAcceptedTest(IngestEndpointTestBase):
    def test_items_for_killed_task_are_accepted_and_held(self):
        """One-rule (#37): the accept-time dead-unit reject is retired — a
        task's STATUS never gates acceptance. Items for a killed task are
        accepted + held and their raw rows appended; the task_not_active
        verdict happens at settle. No replay probe is involved (these are
        fresh keys, not idem-hits)."""
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="killed",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id)
        resp = self._post([
            self._event(task_id=str(task.id), billed_cost_micros=400_000),
            self._event(task_id=str(task.id), billed_cost_micros=100_000),
        ])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["rejected"], 0)
        for r in body["results"]:
            self.assertTrue(r["accepted"])
            self.assertFalse(r["duplicate_suspect"])
        rows = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertEqual(len(rows), 2)
        for raw in rows:
            self.assertTrue(raw.held)
            self.assertEqual(raw.task_id, task.id)
        # Real holds were taken for both items.
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 500_000)
        task.refresh_from_db()
        self.assertEqual(task.status, "killed")  # accept never re-touches it


class EffectiveAtTest(IngestEndpointTestBase):
    def test_naive_effective_at_rejected_before_idem_no_burned_key(self):
        from datetime import timedelta
        from django.utils import timezone
        event = self._event(billed_cost_micros=200_000,
                            effective_at="2026-07-01T00:00:00")  # no tz
        resp = self._post([event])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertFalse(r["accepted"])
        self.assertEqual(r["code"], "effective_at_naive")
        self.assertIsNone(Door.balance(self.customer.id))
        # Rejection precedes the SETNX: the corrected retry (same key) is a
        # genuine first accept with a real hold. The retry must stay inside the
        # ROLLING backfill_window_days accept bound, so stamp it relative to now
        # (a hardcoded date would age out of the window and start rejecting).
        event["effective_at"] = (timezone.now() - timedelta(days=1)).isoformat()
        second = self._post([event])
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 200_000)

    def test_too_old_effective_at_rejected(self):
        from datetime import timedelta
        from django.utils import timezone
        too_old = (timezone.now() - timedelta(days=60)).isoformat()  # window default 34d
        resp = self._post([self._event(billed_cost_micros=200_000, effective_at=too_old)])
        r = resp.json()["results"][0]
        self.assertFalse(r["accepted"])
        self.assertEqual(r["code"], "effective_at_too_old")
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


class EffectiveAtReplayWinsTest(IngestEndpointTestBase):
    """Replay-wins parity for effective_at validation (mirrors the dead-run
    probe and the sync path's replay-before-validation contract): a replayed
    key whose FIRST accept already passed validation must be accepted as a
    duplicate suspect even if the billing period has since closed or the
    backfill window aged out — a whole-batch retry must never flip an
    already-accepted item into a rejection."""

    def test_idem_hit_on_closed_period_is_replay_not_rejection(self):
        from datetime import timedelta
        from django.utils import timezone
        eff = (timezone.now() - timedelta(days=1)).isoformat()
        event = self._event(billed_cost_micros=200_000, effective_at=eff)
        first = self._post([event])
        self.assertTrue(first.json()["results"][0]["accepted"])
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 200_000)

        # The period FREEZES between the first accept and the retry.
        with patch("apps.billing.queries.is_usage_period_closed", return_value=True):
            second = self._post([event])  # SAME idempotency_key
        self.assertEqual(second.status_code, 200)
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertTrue(r2["duplicate_suspect"])
        rows = list(RawIngestEvent.objects.order_by("created_at"))
        self.assertEqual(len(rows), 2)
        self.assertFalse(rows[1].held)
        # No second hold taken for the replay.
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 200_000)

    def test_fresh_key_on_closed_period_still_rejected_without_burning_key(self):
        from datetime import timedelta
        from django.utils import timezone
        eff = (timezone.now() - timedelta(days=1)).isoformat()
        event = self._event(billed_cost_micros=200_000, effective_at=eff)
        with patch("apps.billing.queries.is_usage_period_closed", return_value=True):
            resp = self._post([event])
        r = resp.json()["results"][0]
        self.assertFalse(r["accepted"])
        self.assertEqual(r["code"], "billing_period_closed")
        self.assertEqual(RawIngestEvent.objects.count(), 0)
        self.assertIsNone(Door.balance(self.customer.id))

        # The probe is read-only: the rejection must not have burned the key,
        # so the retry (period reopened) is a genuine first accept + real hold.
        second = self._post([event])
        r2 = second.json()["results"][0]
        self.assertTrue(r2["accepted"])
        self.assertFalse(r2["duplicate_suspect"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(Door.balance(self.customer.id),
                         20_000_000 - 200_000)


class MixedBatchTest(IngestEndpointTestBase):
    def test_positional_alignment_and_exactly_one_new_hold(self):
        """One request mixing all four verdict shapes: [valid held item,
        unknown-task reject, idem-hit replay, currency-mismatch reject].
        Results must align positionally and exactly ONE new hold may be
        taken."""
        replay_event = self._event(billed_cost_micros=250_000)
        pre = self._post([replay_event])  # seed the idem-hit item (takes a hold)
        self.assertTrue(pre.json()["results"][0]["accepted"])
        balance_before = Door.balance(self.customer.id)
        raw_before = RawIngestEvent.objects.count()

        resp = self._post([
            self._event(billed_cost_micros=500_000),                            # 0: held
            self._event(task_id=str(uuid.uuid4()), billed_cost_micros=600_000), # 1: unknown task
            replay_event,                                                       # 2: idem-hit
            self._event(currency="eur", billed_cost_micros=100_000),            # 3: currency
        ])
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        r0, r1, r2, r3 = body["results"]
        self.assertTrue(r0["accepted"] and not r0["duplicate_suspect"])
        self.assertEqual(r0["estimated_cost_micros"], 500_000)
        self.assertFalse(r1["accepted"])
        self.assertEqual(r1["code"], "not_found")
        self.assertTrue(r2["accepted"] and r2["duplicate_suspect"])
        self.assertFalse(r3["accepted"])
        self.assertEqual(r3["code"], "validation_error")
        self.assertEqual(body["accepted"], 2)
        self.assertEqual(body["rejected"], 2)
        # Exactly one NEW hold (the valid item); replay + rejects take none.
        self.assertEqual(Door.balance(self.customer.id),
                         balance_before - 500_000)
        # Two new raw rows: the held item + the held=False replay append.
        self.assertEqual(RawIngestEvent.objects.count(), raw_before + 2)


class TaskHeldItemTest(IngestEndpointTestBase):
    def test_task_bearing_item_is_held_with_task_attribution(self):
        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=20_000_000,
            billing_owner_id=self.customer.id,
        )
        resp = self._post([self._event(task_id=str(task.id), billed_cost_micros=400_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)
        self.assertEqual(raw.task_id, task.id)
        self.assertEqual(raw.payload["task_id"], str(task.id))
        self.assertEqual(Door.balance(self.customer.id), 20_000_000 - 400_000)


class PostpaidPriorMonthGuardTest(TestCase):
    """Final-review fix batch #2 (I9 parity): a postpaid backfill accepted
    through the ASYNC ingest path must not inflate the CURRENT month's live
    spend counter (mirrors LiveCounter.debit's sync-path guard)."""

    def setUp(self):
        cache.clear()
        from apps.metering.usage.services.ingest_accept import reset_task_meta_cache
        reset_task_meta_cache()
        self.http_client = Client()
        self.tenant = Tenant.objects.create(
            name="PostpaidAsyncIngest",
            products=["metering", "billing", "metering_async"],
            billing_mode="postpaid", enforcement_mode="enforcing",
            backfill_window_days=60,
        )
        self.key_obj, self.raw_key = TenantApiKey.create_key(self.tenant, label="test")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="pcust1")

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

    def test_prior_month_backfill_skips_livespend(self):
        from datetime import timedelta
        from django.utils import timezone

        task = Task.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            balance_snapshot_micros=0,
            billing_owner_id=self.customer.id,
        )
        now = timezone.now()
        prior_month_eff = (now.replace(day=1) - timedelta(days=1)).isoformat()

        # A backdated (prior-month) item is accepted + held, but must NOT
        # touch this month's livespend counter (I9). One-rule (#37): the
        # accept-time unit-cap lane is retired, so there is no cost-cap arm
        # here any more — task limits are detected at settle.
        resp = self._post([
            self._event(task_id=str(task.id), billed_cost_micros=4_000_000,
                        effective_at=prior_month_eff),
        ])
        self.assertEqual(resp.status_code, 200)
        r0 = resp.json()["results"][0]
        self.assertTrue(r0["accepted"])

        # The backfilled (accepted) item never touched THIS month's livespend.
        self.assertIsNone(Door.spend(self.customer.id))
        raw = RawIngestEvent.objects.get()
        self.assertTrue(raw.held)

    def test_current_month_item_unaffected_by_the_guard(self):
        resp = self._post([self._event(billed_cost_micros=2_500_000)])
        self.assertEqual(resp.status_code, 200)
        r = resp.json()["results"][0]
        self.assertTrue(r["accepted"])
        # No effective_at (== now, current month) -> livespend moves normally.
        self.assertEqual(Door.spend(self.customer.id), 2_500_000)
