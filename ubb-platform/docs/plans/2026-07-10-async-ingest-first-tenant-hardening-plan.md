# Async-Ingest First-Tenant Hardening Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four gaps blocking the first real `metering_async` tenant: run-kill parity on the async path, markup rate cache, ops ingest-health visibility, and RawIngestEvent retention.

**Architecture:** All four items bolt onto the shipped estimate-hold-settle async path (design: `docs/plans/2026-07-03-async-ingestion-hard-stop-design.md`; this work's spec: `docs/plans/2026-07-10-async-ingest-first-tenant-hardening-design.md`). Task 1 wires the sync path's kill+fan-out semantics into `ingest_usage_batch`; Task 2 clones the reviewed `card_cache.py` L1+version pattern for markups; Tasks 3–4 are a read-only health service with two consumers and a chunked purge task following the `cleanup_outbox` precedent.

**Tech Stack:** Django 6.0, django-ninja, Celery beat, Redis (redis-py), PostgreSQL, pytest.

## Global Constraints

- Branch: `feat/rate-card-container` (stacked on open PR #5). Work in the MAIN checkout at `/Users/ashtoncochrane/Git/localscouta/ubb` — before ANY file op run `git branch --show-current` and confirm `feat/rate-card-container`.
- Test command: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q <path>`
- Full-suite baseline: 1621 passed / **27 pre-existing failures confined to `apps/billing/invoicing` + `apps/subscriptions`** — those 27 are OUTSIDE this work's baseline; 0 new failures allowed anywhere else.
- Money rule (spec): never leak past a cap; every fallback fails in the over-restrictive/safe direction; a missing markup under-holds so markup fallbacks go to the ORM, never "assume none".
- Test idiom: NO shared conftest fixtures — every test file builds tenant/customer inline (subclassing an existing TestBase in the same app is fine, e.g. `IngestEndpointTestBase`).
- New settings follow the existing `os.environ.get("UBB_*", default)` pattern at `config/settings.py:276-286`; beat entries go in `CELERY_BEAT_SCHEDULE` (`config/settings.py:150+`).
- Reason strings come from `apps/platform/runs/reasons.py` (closed set) — never inline string literals.

---

### Task 1: Run-kill parity on the async ingest path

**Files:**
- Modify: `apps/platform/runs/services.py:141-159` (`kill_run` returns `(run, transitioned)`)
- Modify: `api/v1/metering_endpoints.py:82-92` (single-sync handler), `:178-186` (batch-sync handler), new `_kill_capped_run` helper near `_run_meta_for` (~line 246), kill loop in `ingest_usage_batch` after the append boundary (~line 663)
- Modify: `apps/platform/runs/tests/test_services.py:177,187,195` (unpack new tuple)
- Test: `api/v1/tests/test_ingest_run_kill.py` (create), `apps/platform/runs/tests/test_services.py` (extend)

**Interfaces:**
- Consumes: `RunService.kill_run(run_id, reason="", *, tenant_id=None, customer_id=None)`; `write_event(RunLimitExceeded(...))` from `apps.platform.events.outbox` / `.schemas`; `reasons.COST_LIMIT_EXCEEDED`; module state `_RUN_META_CACHE` in `api/v1/metering_endpoints.py`.
- Produces: `kill_run(...) -> tuple[Run, bool]` (run, transitioned — True iff THIS call performed the active→terminal transition). `_kill_capped_run(tenant, run_id, customer) -> None` (module-private, endpoint file only).

- [ ] **Step 1: Write the failing unit test for the `kill_run` transition flag**

Append to `apps/platform/runs/tests/test_services.py` (match the file's existing class style; `run` fixtures in this file are created via `Run.objects.create(tenant=..., customer=..., status="active", ...)`):

```python
class KillRunTransitionFlagTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="KillFlag")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="kf1")
        self.run = Run.objects.create(
            tenant=self.tenant, customer=self.customer, status="active",
            billing_owner_id=self.customer.id,
        )

    def test_transitioned_true_exactly_once(self):
        with transaction.atomic():
            run, transitioned = RunService.kill_run(self.run.id)
        self.assertTrue(transitioned)
        self.assertEqual(run.status, "killed")
        with transaction.atomic():
            run, transitioned = RunService.kill_run(self.run.id)
        self.assertFalse(transitioned)
        self.assertEqual(run.status, "killed")

    def test_transitioned_false_on_completed_run(self):
        with transaction.atomic():
            RunService.complete_run(self.run.id)
        with transaction.atomic():
            run, transitioned = RunService.kill_run(self.run.id)
        self.assertFalse(transitioned)
        self.assertEqual(run.status, "completed")  # kill never demotes completed
```

(Use the imports already present in the file; add `from django.db import transaction` if absent.)

- [ ] **Step 2: Run the test — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/runs/tests/test_services.py -q`
Expected: the two new tests FAIL with `TypeError: cannot unpack non-sequence Run` (kill_run still returns a bare Run).

- [ ] **Step 3: Change `kill_run` to return `(run, transitioned)`**

In `apps/platform/runs/services.py`, replace the body of `kill_run`:

```python
    @staticmethod
    def kill_run(run_id, reason="", *, tenant_id=None, customer_id=None):
        """Mark a run as killed. Idempotent — no-op if already in a terminal
        state. Returns (run, transitioned): transitioned is True iff THIS
        call performed the active->killed transition, so callers can emit
        fan-out events (RunLimitExceeded) exactly once even when racing.

        Must be called inside @transaction.atomic.
        """
        qs = Run.objects.select_for_update()
        if tenant_id is not None:
            qs = qs.filter(tenant_id=tenant_id)
        if customer_id is not None:
            qs = qs.filter(customer_id=customer_id)
        run = qs.get(id=run_id)
        if run.status in ("killed", "completed", "failed"):
            return run, False
        run.status = "killed"
        run.completed_at = timezone.now()
        if reason:
            run.metadata = {**run.metadata, "kill_reason": reason}
        run.save(update_fields=["status", "completed_at", "metadata", "updated_at"])
        return run, True
```

Update every call site that uses the return value (bare `RunService.kill_run(run.id)` calls that discard it are unaffected):

1. `api/v1/metering_endpoints.py:82` (single-sync): `killed, transitioned = RunService.kill_run(...)` and wrap the existing `write_event(RunLimitExceeded(...))` in `if transitioned:` (indent the block).
2. `api/v1/metering_endpoints.py:178` (batch-sync): same change.
3. `apps/platform/runs/tests/test_services.py:177`: `killed, _ = RunService.kill_run(run.id, reason="cost_limit_exceeded")`
4. `apps/platform/runs/tests/test_services.py:187`: `killed, _ = RunService.kill_run(run.id)  # second call = no-op`
5. `apps/platform/runs/tests/test_services.py:195`: `result, _ = RunService.kill_run(run.id)`

- [ ] **Step 4: Run runs + sync-endpoint suites — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/platform/runs/ api/v1/tests/test_metering_endpoints.py apps/billing/gating/tests/test_task_cap.py -q`
Expected: all pass (new tests green; the guarded `write_event` changes nothing observable on the sync path because `RunNotActive` pre-empts repeat breaches).

- [ ] **Step 5: Write the failing endpoint tests for async kill**

Create `api/v1/tests/test_ingest_run_kill.py`:

```python
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
```

(`OutboxEvent.event_type` and `.payload` are the verified field names — `apps/platform/events/models.py:16-17`.)

Also add the mixed-path parity test (spec §1 test (c)) to `IngestRunKillTest`:

```python
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
```

- [ ] **Step 6: Run the new file — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ingest_run_kill.py -q`
Expected: FAIL — kill assertions (`status == "killed"`, event counts) fail; the run stays `active` because the ingest path never kills.

- [ ] **Step 7: Implement `_kill_capped_run` + the kill loop**

In `api/v1/metering_endpoints.py`, add after `_run_meta_for` (below line ~284):

```python
def _kill_capped_run(tenant, run_id, customer):
    """Kill a run whose per-run cap rejected async items — parity with the
    sync path's HardStopExceeded handler (kill + RunLimitExceeded fan-out,
    one atomic). Emits the event ONLY when this call performed the
    active->killed transition, so batches racing a stale _RUN_META_CACHE
    entry can never double-emit. A kill failure must never 500 the batch
    (the verdicts are already correct) — loud log, same contract as
    _record_batch_item's kill."""
    from apps.platform.events.outbox import write_event
    from apps.platform.events.schemas import RunLimitExceeded
    from apps.platform.runs import reasons
    from apps.platform.runs.services import RunService
    try:
        with transaction.atomic():
            killed, transitioned = RunService.kill_run(
                run_id, reason=reasons.COST_LIMIT_EXCEEDED,
                tenant_id=tenant.id, customer_id=customer.id)
            if transitioned:
                write_event(RunLimitExceeded(
                    tenant_id=str(tenant.id), customer_id=str(customer.id),
                    billing_owner_id=str(killed.billing_owner_id or ""),
                    run_id=str(killed.id), external_run_id=killed.external_run_id,
                    task_id=killed.task_id, reason=reasons.COST_LIMIT_EXCEEDED,
                    scope="run",
                    # Durable total as read under the row lock; the live Redis
                    # counter may be slightly ahead (estimate holds).
                    total_cost_micros=killed.total_cost_micros,
                    limit_micros=killed.cost_limit_micros or 0))
        # Local-process cache: next batch rejects run_not_active immediately.
        # Other processes converge within _RUN_META_TTL_SECONDS.
        _RUN_META_CACHE.pop(run_id, None)
    except Exception:
        logger.exception("run.kill_failed", extra={"data": {
            "run_id": run_id, "tenant_id": str(tenant.id),
            "customer_id": str(customer.id),
            "reason": reasons.COST_LIMIT_EXCEEDED}})
```

In `ingest_usage_batch`, immediately after the `if raw_objs:` append block (after the `transaction.on_commit(...)` line, before `accepted = sum(...)`):

```python
    # ---- run-kill parity (spec §1). A cost_limit_exceeded verdict means the
    # run's cap is provably hit — kill it so sibling workers stop, exactly
    # like the sync path's HardStopExceeded handler. Placed AFTER the append
    # boundary: the 503 path above raises first, so kills only happen for
    # batches that landed (the client's retry re-derives the same rejections
    # and kills then). A fully-rejected batch has no raws and reaches here
    # directly. ----
    capped = {}
    for i in range(n):
        r = results[i]
        if (r is not None and r.get("reason") == "cost_limit_exceeded"
                and items[i].run_id is not None):
            capped[str(items[i].run_id)] = item_customer[i]
    for rid, run_customer in capped.items():
        _kill_capped_run(tenant, rid, run_customer)
```

- [ ] **Step 8: Run the new file — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ingest_run_kill.py -q`
Expected: PASS (all 7 tests).

- [ ] **Step 9: Run the affected suites**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/ apps/platform/runs/ apps/billing/gating/ apps/metering/ -q`
Expected: PASS, 0 new failures.

- [ ] **Step 10: Commit**

```bash
git add apps/platform/runs/services.py apps/platform/runs/tests/test_services.py \
        api/v1/metering_endpoints.py api/v1/tests/test_ingest_run_kill.py
git commit -m "feat(metering): async run-kill parity — cap breach kills run + RunLimitExceeded fan-out

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 2: Markup rate cache

**Files:**
- Create: `apps/metering/pricing/services/markup_cache.py`
- Modify: `apps/metering/pricing/models.py:10-36` (TenantMarkup save/delete bump), `apps/metering/pricing/services/estimation_service.py:100-101` (use cache), `api/v1/metering_endpoints.py:427` (begin_request)
- Test: `apps/metering/pricing/tests/test_markup_cache.py` (create), `api/v1/tests/test_ingest_markup_queries.py` (create)

**Interfaces:**
- Consumes: `MarkupService.resolve(tenant, customer) -> TenantMarkup | None` and `TenantMarkup.calculate_markup_micros(provider_cost_micros) -> int` (both unchanged); `settings.REDIS_URL`.
- Produces: `MarkupCache.begin_request(tenant_id)`, `MarkupCache.invalidate(tenant_id)`, `MarkupCache.resolve(tenant, customer) -> TenantMarkup | None`, `MarkupCache.apply(provider_cost_micros, *, tenant, customer) -> int` (same semantics as `MarkupService.apply`).

- [ ] **Step 1: Write the failing cache tests**

Create `apps/metering/pricing/tests/test_markup_cache.py`:

```python
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
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_markup_cache.py -q`
Expected: FAIL with `ModuleNotFoundError: ... markup_cache`.

- [ ] **Step 3: Implement `markup_cache.py`**

Create `apps/metering/pricing/services/markup_cache.py`:

```python
"""In-process (L1) resolved-markup cache, mirroring card_cache.py as-built.

L1 caches the single RESOLVED ``TenantMarkup`` instance (or ``None``, a
negative cache — "no markup configured" is the common case and must also be
one dict hit) per (tenant, customer) key for TTL_SECONDS. Version key
ubb:markupver:{tenant} is read at most once per request: begin_request pins
the observed version in a contextvars.ContextVar (request-scoped — a stale
concurrent request can never clobber a fresher request's view) and resolve
compares cached entries against it. TenantMarkup.save()/.delete() bump the
version at the MODEL layer so no write path can bypass invalidation; a bump
therefore propagates within one request boundary + TTL.

Money rule (never-under-hold): a missing markup would under-ESTIMATE and
therefore under-hold, so every fallback — L1 miss, stale version, Redis
failure — is a live ORM resolve via MarkupService.resolve, never "assume no
markup". The settle path does not use this cache at all (exact live-ORM
pricing via PricingService, unchanged).
"""
import contextvars
import time

from django.conf import settings

TTL_SECONDS = 30
_L1_MAX = 4096   # crude bound: clear-on-full (not an LRU), mirrors CardCache
_l1 = {}         # (tenant_id, customer_id) -> (version, expires_monotonic, TenantMarkup | None)
_ctx_versions = contextvars.ContextVar("markup_cache_versions")

_redis = None  # lazy singleton; bound to settings.REDIS_URL at first use


def _client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(settings.REDIS_URL)
    return _redis


def _ver_key(tenant_id):
    return f"ubb:markupver:{tenant_id}"


class MarkupCache:
    @staticmethod
    def begin_request(tenant_id):
        try:
            v = _client().get(_ver_key(tenant_id))
            ver = int(v) if v else 0
        except Exception:
            ver = 0  # fail-open: TTL still bounds staleness
        _ctx_versions.set({**_ctx_versions.get({}), str(tenant_id): ver})

    @staticmethod
    def invalidate(tenant_id):
        try:
            _client().incr(_ver_key(tenant_id))
        except Exception:
            pass  # TTL bounds staleness

    @staticmethod
    def resolve(tenant, customer):
        """MarkupService.resolve via the L1 cache. Returned TenantMarkup
        instances are shared cache objects — callers must NOT mutate them."""
        from apps.metering.pricing.services.markup_service import MarkupService
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "")
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        markup = MarkupService.resolve(tenant, customer)
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, markup)
        return markup

    @staticmethod
    def apply(provider_cost_micros, *, tenant, customer):
        """MarkupService.apply semantics via the cache (estimation hot path)."""
        markup = MarkupCache.resolve(tenant, customer)
        if markup is None:
            return provider_cost_micros
        return provider_cost_micros + markup.calculate_markup_micros(provider_cost_micros)
```

In `apps/metering/pricing/models.py`, add to `TenantMarkup` (after `calculate_markup_micros`):

```python
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(self.tenant_id)

    def delete(self, *args, **kwargs):
        tenant_id = self.tenant_id
        result = super().delete(*args, **kwargs)
        from apps.metering.pricing.services.markup_cache import MarkupCache
        MarkupCache.invalidate(tenant_id)
        return result
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/pricing/tests/test_markup_cache.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing hot-path query-count test**

Create `api/v1/tests/test_ingest_markup_queries.py`:

```python
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
        # EstimationService (caller_provider_cost path) for every item.
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
```

- [ ] **Step 6: Run — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ingest_markup_queries.py -q`
Expected: FAIL — ~20 markup queries captured (2 per event × 10), because estimation still calls `MarkupService.apply` per event.

- [ ] **Step 7: Wire the cache into estimation + the endpoint**

In `apps/metering/pricing/services/estimation_service.py`, replace lines 100-101:

```python
        from apps.metering.pricing.services.markup_cache import MarkupCache
        return Estimate(MarkupCache.apply(provider_cost, tenant=tenant,
                                          customer=customer), True)
```

In `api/v1/metering_endpoints.py` line 427, directly under `CardCache.begin_request(tenant.id)`:

```python
    from apps.metering.pricing.services.markup_cache import MarkupCache
    MarkupCache.begin_request(tenant.id)
```

(Put the import with the other locals at the top of `ingest_usage_batch`, next to the `CardCache` import.)

- [ ] **Step 8: Run — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ingest_markup_queries.py apps/metering/pricing/ -q`
Expected: PASS.

- [ ] **Step 9: Run the affected suites**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/ api/v1/ -q`
Expected: PASS, 0 new failures (settlement/pricing property tests unaffected — settle path untouched).

- [ ] **Step 10: Commit**

```bash
git add apps/metering/pricing/services/markup_cache.py apps/metering/pricing/models.py \
        apps/metering/pricing/services/estimation_service.py api/v1/metering_endpoints.py \
        apps/metering/pricing/tests/test_markup_cache.py api/v1/tests/test_ingest_markup_queries.py
git commit -m "feat(metering): markup rate cache — accept-path markup resolution is O(1) per batch

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 3: Ops ingest-health endpoint + alert beat task

**Files:**
- Create: `apps/metering/usage/services/ingest_health.py`
- Modify: `apps/metering/usage/tasks.py` (add `monitor_ingest_health`), `api/v1/metering_endpoints.py` (add ops endpoint), `config/settings.py` (3 settings + 1 beat entry)
- Test: `apps/metering/usage/tests/test_ingest_health.py` (create), `api/v1/tests/test_ops_endpoints.py` (create)

**Interfaces:**
- Consumes: `RawIngestEvent` (statuses: pending/settled/duplicate/failed; `attempts` int; index `idx_rawingest_claim (status, created_at)`).
- Produces: `ingest_health(tenant_id=None) -> dict` with keys `pending_count`, `oldest_pending_age_seconds`, `retrying_count`, `failed_count`, `generated_at`; task `apps.metering.usage.tasks.monitor_ingest_health`; endpoint `GET /api/v1/metering/ops/ingest-health`; settings `UBB_OPS_TOKEN`, `UBB_INGEST_SETTLE_LAG_WARN_SECONDS` (120), `UBB_INGEST_QUEUE_DEPTH_WARN` (10000).

- [ ] **Step 1: Write the failing service + task tests**

Create `apps/metering/usage/tests/test_ingest_health.py`:

```python
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import RawIngestEvent


def _mk_raw(tenant, customer, status="pending", age_seconds=0, attempts=0):
    raw = RawIngestEvent.objects.create(
        tenant=tenant, customer=customer, billing_owner_id=customer.id,
        idempotency_key=f"k-{status}-{age_seconds}-{attempts}",
        payload={}, status=status, attempts=attempts,
    )
    if age_seconds:
        RawIngestEvent.objects.filter(id=raw.id).update(
            created_at=timezone.now() - timedelta(seconds=age_seconds))
    return raw


class IngestHealthServiceTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Health")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="h1")

    def test_metrics_across_statuses(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=300)
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=60, attempts=2)
        _mk_raw(self.tenant, self.customer, "settled")
        _mk_raw(self.tenant, self.customer, "duplicate")
        _mk_raw(self.tenant, self.customer, "failed")
        h = ingest_health()
        self.assertEqual(h["pending_count"], 2)
        self.assertEqual(h["retrying_count"], 1)
        self.assertEqual(h["failed_count"], 1)
        self.assertGreaterEqual(h["oldest_pending_age_seconds"], 300)
        self.assertLess(h["oldest_pending_age_seconds"], 330)

    def test_empty_pipeline_zeroes(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        h = ingest_health()
        self.assertEqual(h["pending_count"], 0)
        self.assertEqual(h["oldest_pending_age_seconds"], 0.0)

    def test_tenant_filter(self):
        from apps.metering.usage.services.ingest_health import ingest_health
        other_t = Tenant.objects.create(name="Other")
        other_c = Customer.objects.create(tenant=other_t, external_id="o1")
        _mk_raw(self.tenant, self.customer, "pending")
        _mk_raw(other_t, other_c, "pending")
        self.assertEqual(ingest_health(tenant_id=self.tenant.id)["pending_count"], 1)
        self.assertEqual(ingest_health()["pending_count"], 2)


@override_settings(UBB_INGEST_SETTLE_LAG_WARN_SECONDS=120,
                   UBB_INGEST_QUEUE_DEPTH_WARN=3)
class MonitorIngestHealthTaskTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="HealthMon")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="hm1")

    def _run(self):
        from apps.metering.usage.tasks import monitor_ingest_health
        return monitor_ingest_health()

    def test_healthy_logs_info(self):
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=5)
        with self.assertLogs("ubb.metering", level="INFO") as logs:
            self._run()
        self.assertTrue(any("ingest.health" in m for m in logs.output))
        self.assertFalse(any(m.startswith(("WARNING", "ERROR")) for m in logs.output))

    def test_lag_breach_warns(self):
        _mk_raw(self.tenant, self.customer, "pending", age_seconds=200)
        with self.assertLogs("ubb.metering", level="WARNING") as logs:
            self._run()
        self.assertTrue(any(m.startswith("WARNING") for m in logs.output))

    def test_depth_5x_breach_errors(self):
        for i in range(16):  # depth warn 3, 5x = 15
            _mk_raw(self.tenant, self.customer, "pending", age_seconds=i + 1)
        with self.assertLogs("ubb.metering", level="ERROR") as logs:
            self._run()
        self.assertTrue(any(m.startswith("ERROR") for m in logs.output))

    def test_any_failed_errors_every_cycle(self):
        _mk_raw(self.tenant, self.customer, "failed")
        for _ in range(2):  # stays loud on repeat runs — deliberate
            with self.assertLogs("ubb.metering", level="ERROR") as logs:
                self._run()
            self.assertTrue(any(m.startswith("ERROR") for m in logs.output))
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_ingest_health.py -q`
Expected: FAIL with `ModuleNotFoundError: ... ingest_health` / `ImportError: monitor_ingest_health`.

- [ ] **Step 3: Implement the service, task, and settings**

Create `apps/metering/usage/services/ingest_health.py`:

```python
"""Ingest-pipeline health metrics — the ONE source of truth for both the ops
endpoint (GET /api/v1/metering/ops/ingest-health) and the
monitor_ingest_health alert task (spec §3). Read-only; every query rides
idx_rawingest_claim (status, created_at)."""
from django.utils import timezone


def ingest_health(tenant_id=None):
    from apps.metering.usage.models import RawIngestEvent
    qs = RawIngestEvent.objects.all()
    if tenant_id is not None:
        qs = qs.filter(tenant_id=tenant_id)
    pending = qs.filter(status="pending")
    oldest = (pending.order_by("created_at")
              .values_list("created_at", flat=True).first())
    now = timezone.now()
    return {
        "pending_count": pending.count(),
        "oldest_pending_age_seconds": (
            (now - oldest).total_seconds() if oldest else 0.0),
        "retrying_count": pending.filter(attempts__gt=0).count(),
        "failed_count": qs.filter(status="failed").count(),
        "generated_at": now.isoformat(),
    }
```

Append to `apps/metering/usage/tasks.py`:

```python
@shared_task(queue="ubb_metering")
def monitor_ingest_health():
    """Beat (5 min): ONE structured ingest.health line per run; level = worst
    threshold breached. WARNING at the configured lag/depth thresholds,
    ERROR at 5x either — or at ANY failed (poison) raws: those are never
    auto-cleared, so alerting EVERY cycle until an operator acts is
    deliberate noise, not a bug."""
    from django.conf import settings
    from apps.metering.usage.services.ingest_health import ingest_health

    h = ingest_health()
    lag_warn = settings.UBB_INGEST_SETTLE_LAG_WARN_SECONDS
    depth_warn = settings.UBB_INGEST_QUEUE_DEPTH_WARN
    level = logging.INFO
    if (h["oldest_pending_age_seconds"] > lag_warn
            or h["pending_count"] > depth_warn):
        level = logging.WARNING
    if (h["failed_count"] > 0
            or h["oldest_pending_age_seconds"] > 5 * lag_warn
            or h["pending_count"] > 5 * depth_warn):
        level = logging.ERROR
    logger.log(level, "ingest.health", extra={"data": h})
    return h
```

In `config/settings.py`, next to the other `UBB_*` env settings (~line 286):

```python
# Async-ingest ops (first-tenant hardening spec §3).
UBB_OPS_TOKEN = os.environ.get("UBB_OPS_TOKEN", "")  # unset => ops endpoint 404s
UBB_INGEST_SETTLE_LAG_WARN_SECONDS = int(
    os.environ.get("UBB_INGEST_SETTLE_LAG_WARN_SECONDS", "120"))
UBB_INGEST_QUEUE_DEPTH_WARN = int(
    os.environ.get("UBB_INGEST_QUEUE_DEPTH_WARN", "10000"))
```

In `CELERY_BEAT_SCHEDULE`:

```python
    "monitor-ingest-health": {
        "task": "apps.metering.usage.tasks.monitor_ingest_health",
        "schedule": crontab(minute="*/5"),  # Every 5 minutes
    },
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_ingest_health.py -q`
Expected: PASS.

- [ ] **Step 5: Write the failing endpoint tests**

Create `api/v1/tests/test_ops_endpoints.py`:

```python
from django.test import Client, TestCase, override_settings

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import RawIngestEvent


class OpsIngestHealthEndpointTest(TestCase):
    """Operator-facing: gated on UBB_OPS_TOKEN, NOT tenant API keys.
    Unset token -> 404 (fail closed, invisible)."""

    def setUp(self):
        self.http_client = Client()
        self.tenant = Tenant.objects.create(name="Ops")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="op1")
        RawIngestEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            billing_owner_id=self.customer.id, idempotency_key="op-k1",
            payload={}, status="pending")

    def _get(self, token=None, query=""):
        headers = {"HTTP_X_OPS_TOKEN": token} if token is not None else {}
        return self.http_client.get(
            f"/api/v1/metering/ops/ingest-health{query}", **headers)

    def test_unset_token_404s(self):
        # UBB_OPS_TOKEN defaults to "" in tests (no env var set).
        self.assertEqual(self._get(token="anything").status_code, 404)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_wrong_or_missing_token_401s(self):
        self.assertEqual(self._get(token="wrong").status_code, 401)
        self.assertEqual(self._get().status_code, 401)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_correct_token_returns_metrics(self):
        resp = self._get(token="s3cret")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["pending_count"], 1)
        for key in ("oldest_pending_age_seconds", "retrying_count",
                    "failed_count", "generated_at"):
            self.assertIn(key, body)

    @override_settings(UBB_OPS_TOKEN="s3cret")
    def test_tenant_filter(self):
        other_t = Tenant.objects.create(name="OpsOther")
        other_c = Customer.objects.create(tenant=other_t, external_id="op2")
        RawIngestEvent.objects.create(
            tenant=other_t, customer=other_c, billing_owner_id=other_c.id,
            idempotency_key="op-k2", payload={}, status="pending")
        resp = self._get(token="s3cret", query=f"?tenant_id={self.tenant.id}")
        self.assertEqual(resp.json()["pending_count"], 1)
        resp = self._get(token="s3cret")
        self.assertEqual(resp.json()["pending_count"], 2)
```

- [ ] **Step 6: Run — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ops_endpoints.py -q`
Expected: FAIL — 404s everywhere EXCEPT the `@override_settings` tests, which fail because the route doesn't exist (ninja returns 404 with a different body; the 200 test fails).

- [ ] **Step 7: Implement the endpoint**

In `api/v1/metering_endpoints.py`, add (near the other GET endpoints, after `ingest_usage_batch`):

```python
@metering_api.get("/ops/ingest-health", auth=None)
def ops_ingest_health(request, tenant_id: str = None):
    """Operator-facing pipeline health (spec §3) — deliberately NOT behind
    ApiKeyAuth: tenant keys must not grant ops visibility. Gated on the
    deployment-level UBB_OPS_TOKEN via constant-time compare; when the
    setting is unset the endpoint 404s (fail closed, invisible)."""
    import hmac
    from django.conf import settings as dj_settings
    token = getattr(dj_settings, "UBB_OPS_TOKEN", "")
    if not token:
        return metering_api.create_response(
            request, {"error": "not_found"}, status=404)
    supplied = request.headers.get("X-Ops-Token", "")
    if not hmac.compare_digest(supplied.encode(), token.encode()):
        return metering_api.create_response(
            request, {"error": "unauthorized"}, status=401)
    from apps.metering.usage.services.ingest_health import ingest_health
    return ingest_health(tenant_id=tenant_id)
```

- [ ] **Step 8: Run — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest api/v1/tests/test_ops_endpoints.py apps/metering/usage/tests/test_ingest_health.py -q`
Expected: PASS.

- [ ] **Step 9: Commit**

```bash
git add apps/metering/usage/services/ingest_health.py apps/metering/usage/tasks.py \
        api/v1/metering_endpoints.py config/settings.py \
        apps/metering/usage/tests/test_ingest_health.py api/v1/tests/test_ops_endpoints.py
git commit -m "feat(metering): ingest-health ops endpoint + 5-min alert beat task

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```

---

### Task 4: RawIngestEvent retention purge

**Files:**
- Modify: `apps/metering/usage/tasks.py` (add `purge_raw_ingest_events`), `config/settings.py` (1 setting + 1 beat entry)
- Test: `apps/metering/usage/tests/test_raw_ingest_purge.py` (create)

**Interfaces:**
- Consumes: `RawIngestEvent` statuses; `settings.UBB_RAW_INGEST_RETENTION_DAYS`.
- Produces: task `apps.metering.usage.tasks.purge_raw_ingest_events(chunk_size=10000) -> int` (rows deleted); setting `UBB_RAW_INGEST_RETENTION_DAYS` (default 90).

- [ ] **Step 1: Write the failing tests**

Create `apps/metering/usage/tests/test_raw_ingest_purge.py`:

```python
from datetime import timedelta

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.platform.customers.models import Customer
from apps.platform.tenants.models import Tenant
from apps.metering.usage.models import RawIngestEvent


def _mk_raw(tenant, customer, status, age_days, key):
    raw = RawIngestEvent.objects.create(
        tenant=tenant, customer=customer, billing_owner_id=customer.id,
        idempotency_key=key, payload={}, status=status)
    RawIngestEvent.objects.filter(id=raw.id).update(
        created_at=timezone.now() - timedelta(days=age_days))
    return raw


@override_settings(UBB_RAW_INGEST_RETENTION_DAYS=90)
class PurgeRawIngestEventsTest(TestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(name="Purge")
        self.customer = Customer.objects.create(tenant=self.tenant, external_id="p1")

    def _purge(self, **kw):
        from apps.metering.usage.tasks import purge_raw_ingest_events
        return purge_raw_ingest_events(**kw)

    def test_age_status_matrix(self):
        keep = [
            _mk_raw(self.tenant, self.customer, "settled", 89, "young-settled"),
            _mk_raw(self.tenant, self.customer, "duplicate", 1, "young-dup"),
            _mk_raw(self.tenant, self.customer, "pending", 200, "old-pending"),
            _mk_raw(self.tenant, self.customer, "failed", 200, "old-failed"),
        ]
        _mk_raw(self.tenant, self.customer, "settled", 91, "old-settled")
        _mk_raw(self.tenant, self.customer, "duplicate", 91, "old-dup")
        deleted = self._purge()
        self.assertEqual(deleted, 2)
        alive = set(RawIngestEvent.objects.values_list("idempotency_key", flat=True))
        self.assertEqual(alive, {r.idempotency_key for r in keep})

    def test_boundary_row_at_cutoff_survives(self):
        # created_at exactly == cutoff is NOT < cutoff: survives (strict <).
        raw = RawIngestEvent.objects.create(
            tenant=self.tenant, customer=self.customer,
            billing_owner_id=self.customer.id, idempotency_key="edge",
            payload={}, status="settled")
        from django.conf import settings
        cutoff_age = timedelta(days=settings.UBB_RAW_INGEST_RETENTION_DAYS)
        RawIngestEvent.objects.filter(id=raw.id).update(
            created_at=timezone.now() - cutoff_age + timedelta(seconds=5))
        self.assertEqual(self._purge(), 0)
        self.assertTrue(RawIngestEvent.objects.filter(id=raw.id).exists())

    def test_chunked_delete_drains_fully(self):
        for i in range(5):
            _mk_raw(self.tenant, self.customer, "settled", 100, f"bulk-{i}")
        self.assertEqual(self._purge(chunk_size=2), 5)
        self.assertEqual(RawIngestEvent.objects.count(), 0)
```

- [ ] **Step 2: Run — expect FAIL**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_raw_ingest_purge.py -q`
Expected: FAIL with `ImportError: purge_raw_ingest_events`.

- [ ] **Step 3: Implement the task + settings**

Append to `apps/metering/usage/tasks.py`:

```python
@shared_task(queue="ubb_metering")
def purge_raw_ingest_events(chunk_size=10_000):
    """Delete settled/duplicate raws older than UBB_RAW_INGEST_RETENTION_DAYS
    (spec §4). NEVER pending (that's the queue) or failed (poison rows are
    operator evidence — same contract as cleanup_outbox's never-delete-failed).
    Chunked pk-batch deletes so the table never locks long at target volume.
    Retention (90d default) deliberately exceeds the 62-day idem-key TTL so
    raw evidence outlives any replay window it could be correlated against;
    UsageEvent's unique constraint — not the raw row — is the exactly-once
    authority, so this purge can never affect idempotency."""
    from datetime import timedelta

    from django.conf import settings
    from django.utils import timezone

    from apps.metering.usage.models import RawIngestEvent

    cutoff = timezone.now() - timedelta(days=settings.UBB_RAW_INGEST_RETENTION_DAYS)
    total = 0
    while True:
        ids = list(RawIngestEvent.objects.filter(
            status__in=("settled", "duplicate"), created_at__lt=cutoff,
        ).values_list("id", flat=True)[:chunk_size])
        if not ids:
            break
        deleted, _ = RawIngestEvent.objects.filter(id__in=ids).delete()
        total += deleted
    if total:
        logger.info("raw_ingest.purged", extra={"data": {
            "deleted": total,
            "retention_days": settings.UBB_RAW_INGEST_RETENTION_DAYS}})
    return total
```

In `config/settings.py`, next to the Task 3 settings:

```python
UBB_RAW_INGEST_RETENTION_DAYS = int(
    os.environ.get("UBB_RAW_INGEST_RETENTION_DAYS", "90"))
```

In `CELERY_BEAT_SCHEDULE`:

```python
    "purge-raw-ingest-events": {
        "task": "apps.metering.usage.tasks.purge_raw_ingest_events",
        "schedule": crontab(minute=20, hour=3),  # Daily 03:20 UTC (offset from 3 AM cleanup slot)
    },
```

- [ ] **Step 4: Run — expect PASS**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_raw_ingest_purge.py -q`
Expected: PASS (3 tests).

- [ ] **Step 5: Full-suite regression check**

Run: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q`
Expected: everything green EXCEPT the 27 pre-existing failures confined to `apps/billing/invoicing` + `apps/subscriptions`. Any other failure = regression, fix before commit.

- [ ] **Step 6: Commit**

```bash
git add apps/metering/usage/tasks.py config/settings.py \
        apps/metering/usage/tests/test_raw_ingest_purge.py
git commit -m "feat(metering): daily chunked purge of settled/duplicate raw ingest events

Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>"
```
