# Async Ingestion with Accept-Time Hard Stop (Rung A core) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A batch `POST /api/v1/metering/usage/ingest` endpoint that enforces the prepaid/postpaid hard stop atomically at accept time using cost *estimates*, persists raw events durably, returns 202-style per-event verdicts in ~2 I/O calls per batch, and settles to exact pricing in Celery workers.

**Architecture:** Estimate-hold-settle. The accept path computes a conservative cost estimate from cached rate cards, takes an atomic Redis hold against the existing Tier-2 live ledger (plus a new Redis per-run cap), bulk-inserts raw events, and responds. Settle workers run the real `PricingService`, insert `UsageEvent` rows (unique constraint = exactly-once), emit the existing outbox event, and adjust the live counter by `estimate − exact`. See spec: `docs/plans/2026-07-03-async-ingestion-hard-stop-design.md`.

**Tech Stack:** Django 6 + django-ninja, Redis (raw client + Lua, same pattern as `live_ledger_service.py`), Celery, Postgres, pytest.

## Global Constraints

- Run tests: `cd ubb-platform && DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest --tb=short -q <path>`
- All new models inherit `core.models.BaseModel` (UUID pk, timestamps).
- Metering must not import billing internals — cross-product calls go through `apps/billing/queries.py` (add ports there; pattern: `record_live_usage_debit`).
- Redis `ubb:*` keys use the RAW client (`redis.from_url(settings.REDIS_URL)` + Lua EVAL), never django-redis `cache.*` (D9 in live_ledger_service.py).
- **Never under-hold**: every estimate must be ≥ the exact price wherever tier state is involved. Take `max(marginal at mirror prior, marginal at 0)` AND, for graduated cards, additionally floor the estimate at the worst (max) per-unit rate among the tiers not fully below the mirror prior plus their flat fees — the two anchors alone under-hold on increasing-rate ladders because the mirror lags the true position downward only (spec: "estimate at the max applicable rate").
- **Never ack before durable append**; on append failure, release holds in the same request and return 503.
- Idempotency: Redis SETNX is a fast filter only; idem-hit **skips the hold but still appends**; the `UsageEvent` unique constraint at settle is the exactly-once authority; duplicate settle releases the hold.
- Cooperative stop semantics (I3): the crossing event is still accepted/recorded; the verdict flips on its ack; the flag stops subsequent events.
- Redis failure on the gate = fail-open with loud log (matches `record_usage_debit`).
- v1 limitations (documented, deliberate): per-task cost cap (P4) enforced on the sync path only; auth/tenant resolve uses existing request auth (optimize later); SSE + SDK batching are the follow-up plan.

---

### Task 1: RawIngestEvent model

**Files:**
- Modify: `ubb-platform/apps/metering/usage/models.py` (append)
- Create: migration via `makemigrations metering_usage` (app label: check `apps/metering/usage/apps.py`)
- Test: `ubb-platform/apps/metering/usage/tests/test_raw_ingest_model.py`

**Interfaces:**
- Produces: `RawIngestEvent` model — fields used by later tasks: `tenant`, `customer`, `billing_owner_id: UUID`, `run_id: UUID|None`, `idempotency_key: str`, `payload: dict` (the full request item), `estimate_micros: int`, `estimate_exact: bool`, `held: bool` (False when idem-hit skipped the hold), `status: pending|settled|duplicate|failed`, `attempts: int`, `last_error: str`.
- **No unique constraint on idempotency_key** (retries append duplicates by design; settle dedups).

- [ ] **Step 1: Write the failing test**

```python
# apps/metering/usage/tests/test_raw_ingest_model.py
import pytest
from apps.metering.usage.models import RawIngestEvent

pytestmark = pytest.mark.django_db


def test_raw_ingest_defaults(tenant, customer):
    raw = RawIngestEvent.objects.create(
        tenant=tenant, customer=customer, billing_owner_id=customer.id,
        idempotency_key="k1", payload={"event_type": "llm_call"},
        estimate_micros=120_000)
    assert raw.status == "pending"
    assert raw.attempts == 0
    assert raw.held is True
    assert raw.estimate_exact is False
    assert raw.run_id is None


def test_duplicate_idempotency_keys_allowed(tenant, customer):
    for _ in range(2):  # retry-append is by design; settle dedups
        RawIngestEvent.objects.create(
            tenant=tenant, customer=customer, billing_owner_id=customer.id,
            idempotency_key="same", payload={}, estimate_micros=1)
    assert RawIngestEvent.objects.filter(idempotency_key="same").count() == 2
```

(Reuse the existing `tenant`/`customer` fixtures — find them with `grep -rn "def tenant" apps/*/tests/conftest.py conftest.py`; import/replicate the same pattern used by `apps/metering/usage/tests/` neighbors.)

- [ ] **Step 2: Run test to verify it fails**

Run: `DJANGO_SETTINGS_MODULE=config.settings .venv/bin/python -m pytest apps/metering/usage/tests/test_raw_ingest_model.py -q`
Expected: FAIL — `ImportError: cannot import name 'RawIngestEvent'`

- [ ] **Step 3: Implement the model**

```python
# append to apps/metering/usage/models.py
RAW_INGEST_STATUS = [("pending", "Pending"), ("settled", "Settled"),
                     ("duplicate", "Duplicate"), ("failed", "Failed")]


class RawIngestEvent(BaseModel):
    """Durable raw event accepted by the async ingest path, awaiting exact
    settlement. NO unique constraint on idempotency_key: a retried batch
    appends again (at-least-once log); UsageEvent's unique constraint at
    settle is the exactly-once authority."""
    tenant = models.ForeignKey("tenants.Tenant", on_delete=models.CASCADE)
    customer = models.ForeignKey("customers.Customer", on_delete=models.CASCADE)
    billing_owner_id = models.UUIDField(db_index=True)
    run_id = models.UUIDField(null=True, blank=True)
    idempotency_key = models.CharField(max_length=255)
    payload = models.JSONField(default=dict)
    estimate_micros = models.BigIntegerField(default=0)
    estimate_exact = models.BooleanField(default=False)
    held = models.BooleanField(default=True)
    status = models.CharField(max_length=12, choices=RAW_INGEST_STATUS,
                              default="pending", db_index=True)
    attempts = models.IntegerField(default=0)
    last_error = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ubb_raw_ingest_event"
        indexes = [models.Index(fields=["status", "created_at"],
                                name="idx_rawingest_claim")]
```

Then: `.venv/bin/python manage.py makemigrations` (with `DJANGO_SETTINGS_MODULE=config.settings`) and `migrate`.

- [ ] **Step 4: Run test to verify it passes**

Run: same pytest command. Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add apps/metering/usage/models.py apps/metering/usage/migrations/ apps/metering/usage/tests/test_raw_ingest_model.py
git commit -m "feat(metering): RawIngestEvent durable raw log for async ingest"
```

---

### Task 2: Card cache + tier mirror

**Files:**
- Create: `ubb-platform/apps/metering/pricing/services/card_cache.py`
- Test: `ubb-platform/apps/metering/pricing/tests/test_card_cache.py`

**Interfaces:**
- Produces:
  - `CardCache.resolve(tenant, customer, card_type, provider, event_type, metric, tags, currency) -> Rate | None` — same resolution semantics as `PricingService._resolve_card` (assigned book first, then default book, dimension-specificity sort) but candidates come from a 30s in-process cache, dimension matching done per call.
  - `CardCache.invalidate(tenant_id)` — bumps Redis `ubb:cardver:{tenant_id}`; caches check the version at most once per request via `CardCache.begin_request(tenant_id)`.
  - `TierMirror.read(tenant_id, customer_id, lineage_id, now) -> int` (0 if absent) and `TierMirror.write(tenant_id, customer_id, lineage_id, units_total, now)` — key `ubb:tiermirror:{tenant}:{customer}:{lineage}:{YYYY-MM}`, SET (authoritative, written at settle from the durable ladder), TTL 62 days (reuse `LEDGER_TTL_SECONDS`).

- [ ] **Step 1: Write the failing tests** — cover: (a) resolve returns the same Rate as `PricingService._resolve_card` for an assigned-book + default-book fixture, (b) second resolve within 30s does **zero** queries (`django.test.utils.CaptureQueriesContext`), (c) `invalidate()` + `begin_request()` forces a re-read, (d) `TierMirror.write` then `read` round-trips and an absent key reads 0.

```python
# apps/metering/pricing/tests/test_card_cache.py  (representative core)
import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from apps.metering.pricing.services.card_cache import CardCache, TierMirror
from apps.metering.pricing.services.pricing_service import PricingService

pytestmark = pytest.mark.django_db


def test_resolve_matches_pricing_service(tenant, customer, price_card_fixture):
    now = timezone.now()
    expected = PricingService._resolve_card(
        tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd", now)
    CardCache.begin_request(tenant.id)
    got = CardCache.resolve(tenant, customer, "price", "openai", "llm_call",
                            "tokens", {}, "usd")
    assert got is not None and got.id == expected.id


def test_second_resolve_hits_cache(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    assert len(ctx.captured_queries) == 0


def test_invalidate_forces_reread(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    CardCache.invalidate(tenant.id)
    CardCache.begin_request(tenant.id)   # new request observes the bump
    with CaptureQueriesContext(connection) as ctx:
        CardCache.resolve(tenant, customer, "price", "openai", "llm_call", "tokens", {}, "usd")
    assert len(ctx.captured_queries) > 0


def test_tier_mirror_roundtrip(tenant, customer):
    now = timezone.now()
    assert TierMirror.read(tenant.id, customer.id, "lin1", now) == 0
    TierMirror.write(tenant.id, customer.id, "lin1", 900_000, now)
    assert TierMirror.read(tenant.id, customer.id, "lin1", now) == 900_000
```

(`price_card_fixture`: create a `RateCard(card_type="price", currency="usd", is_default=True)` + `Rate(metric_name="tokens", event_type="llm_call", provider="openai", pricing_model="per_unit", rate_per_unit_micros=10_000_000, unit_quantity=1_000_000)` — copy the construction idiom from existing pricing tests.)

- [ ] **Step 2: Run to verify failure** — Expected: `ModuleNotFoundError: card_cache`.

- [ ] **Step 3: Implement**

```python
# apps/metering/pricing/services/card_cache.py
"""In-process (L1) rate-card candidate cache + Redis tier-position mirror.

L1 caches the CANDIDATE Rate rows per resolution key for TTL_SECONDS;
dimension matching runs per call (tags vary per event). Version key
ubb:cardver:{tenant} is read at most once per request: begin_request stores
the observed version in a contextvars.ContextVar — request/context-scoped, so
a stale concurrent request can never clobber the version a fresher request
observed — and resolve compares cached entries against it. A publish-time
invalidation therefore propagates within one request boundary + TTL.
"""
import contextvars
import time

from django.conf import settings

TTL_SECONDS = 30
MIRROR_TTL_SECONDS = 62 * 24 * 3600  # month + buffer; do NOT import billing internals here
_L1_MAX = 4096    # crude bound: clear-on-full (not an LRU) caps worker memory
_l1 = {}          # key -> (version, expires_monotonic, Rate | None)
# Request-scoped {tenant_id: version} observed by begin_request. Copy-on-write:
# set() replaces the whole dict so no context ever mutates another's view.
_ctx_versions = contextvars.ContextVar("card_cache_versions")

_redis = None  # lazy singleton; bound to settings.REDIS_URL at first use


def _client():
    global _redis
    if _redis is None:
        import redis
        _redis = redis.from_url(settings.REDIS_URL)
    return _redis


def _ver_key(tenant_id):
    return f"ubb:cardver:{tenant_id}"


class CardCache:
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
    def resolve(tenant, customer, card_type, provider, event_type, metric, tags, currency):
        """Resolve with PricingService._resolve_card semantics, via the L1
        cache when tags are empty. Returned Rate instances are shared cache
        objects — callers must NOT mutate them."""
        from django.utils import timezone
        from apps.metering.pricing.services.pricing_service import PricingService
        if tags:
            # Dimension-bearing resolutions vary per tag set; caching the
            # tag-influenced result under a tag-less key would wrongly
            # negative/positive-cache for other tag sets. Bypass L1.
            return PricingService._resolve_card(
                tenant, customer, card_type, provider, event_type, metric,
                tags, currency, timezone.now())
        ver = _ctx_versions.get({}).get(str(tenant.id), 0)
        key = (str(tenant.id), str(customer.id) if customer else "",
               card_type, provider or "", event_type or "", metric, currency)
        hit = _l1.get(key)
        if hit and hit[0] == ver and hit[1] > time.monotonic():
            return hit[2]
        rate = PricingService._resolve_card(
            tenant, customer, card_type, provider, event_type, metric,
            tags, currency, timezone.now())
        if len(_l1) >= _L1_MAX:
            _l1.clear()  # crude bound; entries repopulate within one TTL
        _l1[key] = (ver, time.monotonic() + TTL_SECONDS, rate)
        return rate


class TierMirror:
    @staticmethod
    def _key(tenant_id, customer_id, lineage_id, now):
        return f"ubb:tiermirror:{tenant_id}:{customer_id}:{lineage_id}:{now:%Y-%m}"

    @staticmethod
    def read(tenant_id, customer_id, lineage_id, now):
        try:
            v = _client().get(TierMirror._key(tenant_id, customer_id, lineage_id, now))
            return int(v) if v is not None else 0
        except Exception:
            return 0  # conservative: prior=0 estimates at the FIRST tier

    @staticmethod
    def write(tenant_id, customer_id, lineage_id, units_total, now):
        try:
            _client().set(TierMirror._key(tenant_id, customer_id, lineage_id, now),
                          int(units_total), ex=MIRROR_TTL_SECONDS)
        except Exception:
            pass
```

Note for implementer: caching the single resolved Rate keyed WITHOUT tags is only valid because dimension-bearing cards re-match per call; if `_resolve_card` returned `None` *because* tags didn't match a dimensioned card, the cached empty list could wrongly negative-cache for other tags. Guard: only cache when `tags` is empty/None at resolve time; otherwise bypass L1 (call `_resolve_card` directly). Add a test for a dimensioned card with two different tag sets.

- [ ] **Step 4: Run to verify pass** — all tests in the file green.

- [ ] **Step 5: Hook invalidation into publish** — in `apps/metering/pricing/services/book_service.py`, at the end of `BookService.publish` (inside the success path, after commit via `transaction.on_commit`):

```python
from apps.metering.pricing.services.card_cache import CardCache
transaction.on_commit(lambda: CardCache.invalidate(tenant.id))
```

Add a test asserting `publish` bumps `ubb:cardver:{tenant}` (mock or read the key).

- [ ] **Step 6: Commit**

```bash
git add apps/metering/pricing/services/card_cache.py apps/metering/pricing/services/book_service.py apps/metering/pricing/tests/test_card_cache.py
git commit -m "feat(pricing): L1 card cache + Redis tier mirror for accept-time estimation"
```

---

### Task 3: EstimationService

**Files:**
- Create: `ubb-platform/apps/metering/pricing/services/estimation_service.py`
- Test: `ubb-platform/apps/metering/pricing/tests/test_estimation_service.py`

**Interfaces:**
- Consumes: `CardCache.resolve`, `TierMirror.read`, `Rate.compute`, `Rate.compute_marginal`, `MarkupService.apply`.
- Produces:
  - `class Unpriceable(Exception)` — endpoint routes the item down the sync path.
  - `EstimationService.estimate(tenant, customer, *, event_type, provider, usage_metrics, tags, currency, caller_billed, caller_provider_cost, units, now) -> Estimate` where `Estimate = namedtuple("Estimate", "micros exact")`.
- Estimation rules (mirror of `PricingService.price`, read-only):
  1. `caller_billed is not None` → `Estimate(caller_billed, exact=True)`.
  2. Per metric with a price card: non-tiered → `card.compute(units)` (exact); tiered/graduated → `max(card.compute_marginal(prior_mirror, units), card.compute_marginal(0, units))`, and for graduated cards additionally floored at the max applicable band rate over the tiers not fully below the mirror plus their flat fees (never-under-hold on increasing-rate ladders too; package cards have `tiers == []` and are covered by the `marginal(0)` anchor), `exact=False`.
  3. No price card matched any metric → markup path mirrors the pricer exactly: provider cost from `caller_provider_cost` or cost cards via `card.compute` (0 when nothing matches, non-strict tenants never fail here); then `MarkupService.apply(provider_cost, tenant=tenant, customer=customer)`. Cost cards are never tiered (enforced by `validate_tiers`), so this is exact.
  4. `Unpriceable` is raised only where the real pricer raises `PricingError` — strict-coverage tenants (`require_cost_card_coverage`) with uncosted metrics (checked even when price cards match), or strict tenants with `units > 0`, no `usage_metrics`, and no caller cost.

- [ ] **Step 1: Write the failing tests** — the load-bearing one is the **property test** against the real pricer:

```python
# apps/metering/pricing/tests/test_estimation_service.py (core cases)
import pytest
from django.utils import timezone
from apps.metering.pricing.services.estimation_service import (
    EstimationService, Unpriceable)
from apps.metering.pricing.services.pricing_service import PricingService
from apps.metering.pricing.services.card_cache import CardCache, TierMirror

pytestmark = pytest.mark.django_db


def test_caller_billed_is_exact(tenant, customer):
    e = EstimationService.estimate(
        tenant, customer, event_type="x", provider="", usage_metrics=None,
        tags=None, currency="usd", caller_billed=777, caller_provider_cost=None,
        units=None, now=timezone.now())
    assert (e.micros, e.exact) == (777, True)


def test_linear_estimate_equals_exact_price(tenant, customer, price_card_fixture):
    CardCache.begin_request(tenant.id)
    now = timezone.now()
    e = EstimationService.estimate(
        tenant, customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None, now=now)
    _, exact_billed, _ = PricingService.price(
        tenant=tenant, customer=customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": 12_000}, tags={}, currency="usd",
        caller_provider_cost=None, caller_billed=None)
    assert e.micros == exact_billed and e.exact is True


@pytest.mark.parametrize("prior_mirror,units", [(0, 50), (900_000, 250_000), (2_000_000, 10)])
def test_tiered_never_under_holds(tenant, customer, graduated_card_fixture, prior_mirror, units):
    """PROPERTY: estimate >= exact marginal price at ANY true ladder position
    <= mirror (mirror lags truth only when settles are pending, and pending
    settles only RAISE the true position; estimate at max(prior,0) covers it)."""
    now = timezone.now()
    card = graduated_card_fixture
    TierMirror.write(tenant.id, customer.id, str(card.lineage_id), prior_mirror, now)
    CardCache.begin_request(tenant.id)
    e = EstimationService.estimate(
        tenant, customer, event_type="llm_call", provider="openai",
        usage_metrics={"tokens": units}, tags={}, currency="usd",
        caller_billed=None, caller_provider_cost=None, units=None, now=now)
    for true_prior in (0, prior_mirror // 2, prior_mirror):
        assert e.micros >= card.compute_marginal(true_prior, units)


def test_unpriceable_raises(tenant, customer):
    # Unpriceable mirrors the pricer's PricingError: strict coverage only.
    tenant.require_cost_card_coverage = True
    tenant.save(update_fields=["require_cost_card_coverage"])
    CardCache.begin_request(tenant.id)
    with pytest.raises(Unpriceable):
        EstimationService.estimate(
            tenant, customer, event_type="unknown", provider="",
            usage_metrics={"mystery": 5}, tags={}, currency="usd",
            caller_billed=None, caller_provider_cost=None, units=None,
            now=timezone.now())
```

(`graduated_card_fixture`: `pricing_model="graduated"`, tiers `[{"up_to": 1_000_000, "rate_per_unit_micros": 10_000_000}, {"up_to": None, "rate_per_unit_micros": 8_000_000}]` — decreasing ladder.)

- [ ] **Step 2: Run to verify failure** — `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

```python
# apps/metering/pricing/services/estimation_service.py
from collections import namedtuple
from apps.metering.pricing.models import TIERED_PRICING_MODELS
from apps.metering.pricing.services.card_cache import CardCache, TierMirror

Estimate = namedtuple("Estimate", "micros exact")


class Unpriceable(Exception):
    """No cached card, no caller cost — route this item down the sync path."""


class EstimationService:
    @staticmethod
    def estimate(tenant, customer, *, event_type, provider, usage_metrics,
                 tags, currency, caller_billed, caller_provider_cost, units, now):
        if caller_billed is not None:
            return Estimate(caller_billed, True)
        usage_metrics = usage_metrics or {}
        # Strict cost coverage mirrors the pricer's PricingError risk exactly:
        # it checks coverage BEFORE pricing, even when price cards match and
        # even when the caller supplies the aggregate cost.
        if getattr(tenant, "require_cost_card_coverage", False):
            if caller_provider_cost is None and (units or 0) > 0 and not usage_metrics:
                raise Unpriceable(
                    "strict cost coverage: units > 0 with no usage_metrics")
            uncosted = [m for m in usage_metrics
                        if CardCache.resolve(tenant, customer, "cost", provider,
                                             event_type, m, tags, currency) is None]
            if uncosted:
                raise Unpriceable(f"no cost rate card for metrics: {uncosted}")
        total, matched, exact = 0, False, True
        for metric, units_val in sorted(usage_metrics.items()):
            card = CardCache.resolve(tenant, customer, "price", provider,
                                     event_type, metric, tags, currency)
            if card is None:
                continue
            matched = True
            if card.pricing_model in TIERED_PRICING_MODELS:
                prior = TierMirror.read(tenant.id, customer.id,
                                        str(card.lineage_id), now)
                # never-under-hold: anchor at the mirror and at 0...
                est = max(card.compute_marginal(prior, units_val),
                          card.compute_marginal(0, units_val))
                # ...but on INCREASING-rate ladders the marginal grows with
                # prior, so those anchors under-hold. graduated: guard with
                # the spec's "estimate at the max applicable rate" over the
                # tiers not fully below the mirror. (package cards have
                # tiers == [] and are covered by the marginal(0) anchor.)
                if card.tiers:
                    remaining = [t for t in card.tiers
                                 if t["up_to"] is None or t["up_to"] > prior]
                    if remaining:
                        worst_rate = max(
                            (units_val * t["rate_per_unit_micros"]
                             + t.get("unit_quantity", 1_000_000) // 2)
                            // t.get("unit_quantity", 1_000_000)
                            for t in remaining)
                        est = max(est, worst_rate + sum(
                            t.get("flat_micros", 0) for t in remaining))
                total += est
                exact = False
            else:
                total += card.compute(units_val)
        if matched:
            return Estimate(total, exact)
        # Markup fallback mirrors PricingService exactly: billed is
        # markup(provider cost); a non-strict tenant with no matching cost
        # cards simply bills markup(0) — never a failure.
        if caller_provider_cost is not None:
            provider_cost = caller_provider_cost
        else:
            provider_cost = 0
            for metric, units_val in usage_metrics.items():
                card = CardCache.resolve(tenant, customer, "cost", provider,
                                         event_type, metric, tags, currency)
                if card is not None:
                    provider_cost += card.compute(units_val)
        from apps.metering.pricing.services.markup_service import MarkupService
        return Estimate(MarkupService.apply(provider_cost, tenant=tenant,
                                            customer=customer), True)
```

- [ ] **Step 4: Run to verify pass.**

- [ ] **Step 5: Commit**

```bash
git add apps/metering/pricing/services/estimation_service.py apps/metering/pricing/tests/test_estimation_service.py
git commit -m "feat(pricing): conservative accept-time cost estimation (never under-hold)"
```

---

### Task 4: HoldService — atomic batch gate

**Files:**
- Create: `ubb-platform/apps/billing/gating/services/hold_service.py`
- Modify: `ubb-platform/apps/billing/queries.py` (add ports)
- Test: `ubb-platform/apps/billing/gating/tests/test_hold_service.py`

**Interfaces:**
- Consumes: key helpers + `_client()` + flags pattern from `live_ledger_service.py`; `get_customer_balance`, `get_customer_min_balance` (queries.py).
- Produces (also exported via `apps/billing/queries.py` as `acquire_ingest_holds`, `settle_ingest_hold`, `release_ingest_hold`):
  - `HoldService.acquire(owner_id, tenant, items) -> list[dict]` — `items: [{"estimate_micros": int, "run_id": str|None, "run_cap_micros": int|None, "run_seed_micros": int}]`; returns per-item `{"held": bool, "rejected": bool, "reason": str|None, "stop": bool, "stop_reason": str|None, "stop_scope": str|None}`. Semantics per item, in one Lua eval each (pipelined): run-cap check-then-incr FIRST (reject leaves livebal untouched); then livebal seed+DECRBY; floor crossing sets the stop flag (cooperative — item still held). Prepaid path only for the balance; postpaid mirrors `_SPEND_INCR` on livespend.
  - `HoldService.settle(owner_id, tenant, run_id, delta_micros)` — `delta = estimate − exact`; prepaid: positive credits livebal back (reuses `LiveLedgerService.credit`), negative debits further; postpaid: adjusts the current month's livespend key directly by `−delta` (credit() no-ops for postpaid and the reconcile MAX-merge can never lower an inflated counter); adjusts `ubb:runcost:{run}` by `−delta` in both modes.
  - `HoldService.release(owner_id, tenant, run_id, estimate_micros)` — full credit-back (duplicate/failed/append-failure), i.e. `settle(..., delta_micros=estimate_micros)`.

- [ ] **Step 1: Write the failing tests** — must include the race test:

```python
# apps/billing/gating/tests/test_hold_service.py (core cases)
import threading
import pytest
from apps.billing.gating.services.hold_service import HoldService
from apps.billing.gating.services.live_ledger_service import LiveLedgerService

pytestmark = pytest.mark.django_db


def _item(est, run_id=None, cap=None, seed=0):
    return {"estimate_micros": est, "run_id": run_id,
            "run_cap_micros": cap, "run_seed_micros": seed}


def test_hold_decrements_live_balance(enforced_prepaid_tenant, funded_owner):
    # funded_owner fixture: wallet balance 20_000_000, floor 0
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(2_920_000)])
    assert out[0]["held"] and not out[0]["stop"]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_080_000


def test_floor_crossing_sets_stop_but_holds(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(19_600_000)])
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(500_000)])
    assert out[0]["held"] is True          # cooperative (I3)
    assert out[0]["stop"] is True
    assert out[0]["stop_scope"] == "customer"


def test_run_cap_rejects_without_touching_balance(enforced_prepaid_tenant, funded_owner):
    out = HoldService.acquire(funded_owner.id, enforced_prepaid_tenant,
                              [_item(600_000, run_id="r1", cap=500_000)])
    assert out[0]["rejected"] and out[0]["reason"] == "cost_limit_exceeded"
    assert LiveLedgerService.read_prepaid(funded_owner.id) in (None, 20_000_000)


def test_settle_delta_credits_overhold(enforced_prepaid_tenant, funded_owner):
    HoldService.acquire(funded_owner.id, enforced_prepaid_tenant, [_item(2_500_000)])
    HoldService.settle(funded_owner.id, enforced_prepaid_tenant, None,
                       delta_micros=300_000)   # exact was 2_200_000
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 17_800_000


def test_concurrent_holds_at_floor_race(enforced_prepaid_tenant, funded_owner):
    """20 threads x 1_500_000 against a 20_000_000 balance: every hold is
    atomic, final balance is exactly 20_000_000 - 20*1_500_000, and the stop
    flag is set (crossing detected exactly, no lost updates)."""
    results = []
    def go():
        results.extend(HoldService.acquire(
            funded_owner.id, enforced_prepaid_tenant, [_item(1_500_000)]))
    ts = [threading.Thread(target=go) for _ in range(20)]
    [t.start() for t in ts]; [t.join() for t in ts]
    assert LiveLedgerService.read_prepaid(funded_owner.id) == 20_000_000 - 30_000_000
    assert any(r["stop"] for r in results)
```

(Fixtures: `enforced_prepaid_tenant` = tenant with `billing_mode="prepaid"` and enforcement flags on — copy from the existing live-ledger tests, `grep -rn "enforcement" apps/billing/gating/tests/`; `funded_owner` = customer + Wallet with `balance_micros=20_000_000`. Flush the `ubb:*` keys in fixture teardown the same way existing Tier-2 tests do.)

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement** — one Lua script; per-item eval pipelined:

```python
# apps/billing/gating/services/hold_service.py
"""Accept-time atomic gate for the async ingest path (estimate-hold-settle).

Per item, ONE Lua eval:
  1. run cap check-then-increment (reject => balance untouched)  [if run item]
  2. prepaid: livebal seed-if-absent + DECRBY estimate
     postpaid: livespend INCRBY estimate
  3. threshold-crossing detection -> caller sets the stop flag
Reuses live_ledger_service keys/semantics; settle/release route through
LiveLedgerService.credit (MIN-merge-safe).
"""
import logging
from django.conf import settings
from apps.platform.tenants.flags import enforcement_on
from apps.billing.gating.services.live_ledger_service import (
    LiveLedgerService, LEDGER_TTL_SECONDS, _livebal_key, _livespend_key,
    _month_label_bounds, _client)

logger = logging.getLogger("ubb.billing")

# KEYS[1]=livebal  KEYS[2]=runcost ('' sentinel key unused when no run)
# ARGV: 1=seed 2=estimate 3=ttl 4=run_cap (-1 none) 5=run_seed
# Returns {held(0/1), rejected(0/1), post_balance}
_ACQUIRE = """
local cap = tonumber(ARGV[4])
if cap >= 0 then
    if redis.call('EXISTS', KEYS[2]) == 0 then
        redis.call('SET', KEYS[2], ARGV[5], 'EX', ARGV[3])
    end
    local newrun = tonumber(redis.call('GET', KEYS[2])) + tonumber(ARGV[2])
    if newrun > cap then
        return {0, 1, 0}
    end
    redis.call('SET', KEYS[2], newrun, 'EX', ARGV[3])
end
if redis.call('EXISTS', KEYS[1]) == 0 then
    redis.call('SET', KEYS[1], ARGV[1], 'EX', ARGV[3])
end
local v = redis.call('DECRBY', KEYS[1], ARGV[2])
redis.call('EXPIRE', KEYS[1], ARGV[3])
return {1, 0, v}
"""


def _runcost_key(run_id):
    return f"ubb:runcost:{run_id}"


class HoldService:
    @staticmethod
    def acquire(owner_id, tenant, items):
        if not enforcement_on(tenant):
            # gate disabled: everything held, no stop — durable start-gate backstop
            return [{"held": True, "rejected": False, "reason": None,
                     "stop": False, "stop_reason": None, "stop_scope": None}
                    for _ in items]
        from django.utils import timezone
        from apps.billing.queries import get_customer_balance, get_customer_min_balance
        now = timezone.now()
        postpaid = tenant.billing_mode == "postpaid"
        if postpaid:
            label, _, _ = _month_label_bounds(now)
            bal_key = _livespend_key(owner_id, label)
            seed = 0
        else:
            bal_key = _livebal_key(owner_id)
            seed = int(get_customer_balance(owner_id))
        out, crossed = [], False
        try:
            client = _client()
            pipe = client.pipeline()
            for it in items:
                run_id = it.get("run_id")
                cap = it.get("run_cap_micros")
                pipe.eval(_ACQUIRE, 2, bal_key,
                          _runcost_key(run_id) if run_id else "ubb:runcost:_none",
                          seed if not postpaid else 0,
                          # postpaid: INCR is modeled as DECRBY of negative
                          int(it["estimate_micros"]) if not postpaid
                          else -int(it["estimate_micros"]),
                          LEDGER_TTL_SECONDS,
                          int(cap) if (run_id and cap is not None) else -1,
                          int(it.get("run_seed_micros") or 0))
            for it, (held, rejected, post) in zip(items, pipe.execute()):
                if rejected:
                    out.append({"held": False, "rejected": True,
                                "reason": "cost_limit_exceeded", "stop": False,
                                "stop_reason": None, "stop_scope": None})
                    continue
                # post is the post-op counter value in BOTH modes: prepaid
                # balance (after DECRBY estimate) or postpaid month-to-date
                # spend (DECRBY of a negative == INCRBY estimate). _crossed
                # expects exactly these (balance vs floor / spend vs cap).
                value = int(post)
                if LiveLedgerService._crossed(
                        "postpaid" if postpaid else "prepaid", value, owner_id, tenant):
                    crossed = True
                out.append({"held": True, "rejected": False, "reason": None})
            if crossed:
                from apps.platform.runs.reasons import CUSTOMER_WIDE_STOP
                LiveLedgerService._set_stop(owner_id, CUSTOMER_WIDE_STOP)
            verdict = LiveLedgerService.read_stop(owner_id, tenant)
            for o in out:
                if o["held"]:
                    o.update(verdict)
            return out
        except Exception:
            logger.warning("hold_service.acquire_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
            return [{"held": True, "rejected": False, "reason": None,
                     "stop": False, "stop_reason": None, "stop_scope": None}
                    for _ in items]  # fail-open, matches record_usage_debit

    @staticmethod
    def settle(owner_id, tenant, run_id, delta_micros):
        """delta = estimate - exact. Positive => credit back the over-hold.

        PREPAID routes through LiveLedgerService.credit (MIN-merge-safe).
        POSTPAID: credit() no-ops for postpaid, so settle adjusts the CURRENT
        month's livespend key directly (INCRBY -delta) — otherwise every
        over-estimate would permanently inflate the counter (the reconcile
        MAX-merge only raises, never lowers) and budget caps would fire
        increasingly early. Month-rollover window: a hold acquired in month M
        settling in M+1 adjusts M+1's key; bounded to the seconds of ingest
        latency around rollover and re-corrected for both months by the
        MAX-merge reconcile toward each month's durable total within one
        cycle. Never clears stop flags (recovery stays with reconcile/credit).
        The runcost adjustment is mode-independent and exists-guarded
        (Lua _RUNCOST_CREDIT_IF_PRESENT, TTL-refreshing) so an uncapped run
        never grows a stray TTL-less counter."""
        delta_micros = int(delta_micros)
        if delta_micros:
            if tenant.billing_mode == "postpaid":
                if enforcement_on(tenant):
                    from django.utils import timezone
                    try:
                        label, _, _ = _month_label_bounds(timezone.now())
                        key = _livespend_key(owner_id, label)
                        pipe = _client().pipeline()
                        pipe.incrby(key, -delta_micros)
                        pipe.expire(key, LEDGER_TTL_SECONDS)
                        pipe.execute()
                    except Exception:
                        logger.warning("hold_service.settle_failed",
                                       extra={"data": {"owner_id": str(owner_id)}})
            else:
                LiveLedgerService.credit(owner_id, tenant, delta_micros)
        if run_id and delta_micros and enforcement_on(tenant):
            try:
                _client().eval(_RUNCOST_CREDIT_IF_PRESENT, 1,
                               _runcost_key(run_id), -delta_micros, LEDGER_TTL_SECONDS)
            except Exception:
                logger.warning("hold_service.run_settle_failed",
                               extra={"data": {"run_id": str(run_id)}})

    @staticmethod
    def release(owner_id, tenant, run_id, estimate_micros):
        HoldService.settle(owner_id, tenant, run_id, estimate_micros)
```

NOTE for implementer: the postpaid DECRBY-of-negative trick keeps one script for both modes; verify sign handling in tests (`livespend` must INCREASE by the estimate). If it reads confusingly, split into two scripts — clarity beats cleverness here.

- [ ] **Step 4: Add ports in `apps/billing/queries.py`** (docstring pattern mirrors `record_live_usage_debit`):

```python
def acquire_ingest_holds(owner_id, tenant, items):
    from apps.billing.gating.services.hold_service import HoldService
    return HoldService.acquire(owner_id, tenant, items)


def settle_ingest_hold(owner_id, tenant, run_id, delta_micros):
    from apps.billing.gating.services.hold_service import HoldService
    HoldService.settle(owner_id, tenant, run_id, delta_micros)


def release_ingest_hold(owner_id, tenant, run_id, estimate_micros):
    from apps.billing.gating.services.hold_service import HoldService
    HoldService.release(owner_id, tenant, run_id, estimate_micros)
```

- [ ] **Step 5: Run all tests, verify pass; run the full gating suite** (`pytest apps/billing/gating -q`) to check no regression.

- [ ] **Step 6: Commit**

```bash
git add apps/billing/gating/services/hold_service.py apps/billing/queries.py apps/billing/gating/tests/test_hold_service.py
git commit -m "feat(billing): atomic estimate holds + Redis per-run cap for async ingest"
```

---

### Task 5: Ingest endpoint

**Files:**
- Modify: `ubb-platform/api/v1/schemas.py` (add `IngestEventIn`, `IngestBatchRequest`, `IngestBatchResponse`)
- Modify: `ubb-platform/api/v1/metering_endpoints.py` (add `POST /usage/ingest`)
- Test: `ubb-platform/api/v1/tests/test_ingest_endpoint.py`

**Interfaces:**
- Consumes: `EstimationService.estimate` / `Unpriceable`, `CardCache.begin_request`, `acquire_ingest_holds` (queries port), `RawIngestEvent`, `UsageService.record_usage` (sync fallback), existing `_product_check` / auth / `UsageBatchRequest` idioms in `metering_endpoints.py`.
- Produces: `POST /api/v1/metering/usage/ingest` accepting `{"events": [1..1000 items]}` where each item carries the SAME fields as the existing batch item schema (event_type, provider, units, usage_metrics, tags, idempotency_key, run_id, metadata, product_id, effective_at, provider_cost_micros, billed_cost_micros, customer_id/external ref — copy the existing item schema fields exactly). Response 200: positionally aligned `results[]`, each `{accepted, estimated_cost_micros, stop, stop_reason, stop_scope, rejected, reason, mode}` where `mode` is `"async" | "sync_fallback"`.
- Endpoint algorithm (the hot path — no ORM per event beyond what is listed). AS-BUILT ordering note: every LOCAL rejection (customer/currency validation, `run_not_active`) runs BEFORE the idempotency SETNX, so a rejected item never burns its idem key — otherwise the client's legitimate retry (after fixing the problem / against an active run) would misread as an idem-hit and be appended `held=False`: accepted spend with no hold ever taken. Estimation stays AFTER the idem check (an idem-hit takes no hold so needs no estimate; an `Unpriceable` replay is already idempotent through `record_usage`'s own replay path):
  1. `_product_check`; resolve tenant; gate on `"metering_async" in (tenant.products or [])` else 403 `feature_not_enabled`.
  2. Group items by customer (resolve customers once per batch, same memo-dict idiom as `record_usage_batch`); resolve billing owner once per customer; per-item currency validation (mismatch → rejected `validation_error`, no idem write, no hold); per-item `validate_effective_at(tenant, owner_id, effective_at, now)` for effective_at-bearing items ONLY (the sanctioned per-event ORM exception; `EffectiveAtError` → rejected with `reason=e.code`, no idem write, no hold). effective_at survives into the raw payload as an ISO string (`model_dump(mode="json")`) so settlement prices `as_of` it; estimation stays on the current-month tier mirror (conservative; settle is exact).
  3. Run metadata for run items from a 30s L1 cache (`{run_id: (cap, seed_total, status, customer_id)}`, single `Run.objects.values()` read on miss; the return dict is built from LOCAL captures so the clear-on-full size bound can never KeyError entries fresh for the current call). Killed/completed/unknown/foreign-customer runs: replay-wins first — a read-only pipelined `EXISTS` probe (never SETNX) on the item's idem key; present → treated as an idem-hit replay (accepted, `duplicate_suspect`, held=False append, current stop verdict — parity with `record_usage`'s replay-before-validation contract); absent → rejected `run_not_active` WITHOUT writing the key. The probe fails CLOSED to "absent" (reject rather than accept unheld spend on an unverifiable replay claim).
  4. `CardCache.begin_request(tenant.id)`; for the still-viable subset only: idem-check `SETNX ubb:idem:{tenant}:{customer}:{key}` (pipelined, TTL 7 days), remembering which keys THIS request freshly set; then per item estimate (`Unpriceable` → run item through `UsageService.record_usage` inline, mark `mode="sync_fallback"`).
  5. `acquire_ingest_holds(owner_id, tenant, items)` — idem-hit items excluded (held=False, still appended).
  6. `RawIngestEvent.objects.bulk_create([...])` — the durability boundary. On DB failure: `release_ingest_hold` for every held item AND pipeline-DELETE the freshly-set idem keys (best-effort, ERROR-logged on failure — a stranded key means the batch retry would misread as all idem-hits and bypass the estimate+hold gate), then re-raise (500/503).
  7. `transaction.on_commit(lambda: settle_raw_events.delay())` then return verdicts. (As-built: the enqueue lands with the settlement change — the task does not exist yet at Task 5 time.)

- [ ] **Step 1: Write the failing endpoint tests** — accepted+verdict happy path; floor-crossing batch returns `stop: true` on the crossing item AND all later items; run-cap item rejected with `reason="cost_limit_exceeded"`; idem replay appends a second raw row but takes no second hold (assert live balance decremented once); `Unpriceable` item falls back to sync (a `UsageEvent` exists immediately, `mode == "sync_fallback"`); tenant without the `metering_async` product gets 403. Use the existing endpoint-test client idiom from `api/v1/tests/test_billing_endpoints.py` / metering tests (auth headers, tenant fixtures).

- [ ] **Step 2: Run to verify failure** (404 route not found).

- [ ] **Step 3: Implement schemas + endpoint** following the algorithm above. Key code shape for the verdict assembly:

```python
@metering_api.post("/usage/ingest", response={200: IngestBatchResponse})
def ingest_usage_batch(request, payload: IngestBatchRequest):
    """Async accept path: estimate -> atomic hold -> durable raw append -> 202-style
    verdicts. Exact pricing settles in workers (estimate-hold-settle; see
    docs/plans/2026-07-03-async-ingestion-hard-stop-design.md)."""
    ...
```

- [ ] **Step 4: Run tests; run the whole `api/v1/tests` suite for regressions.**

- [ ] **Step 5: Commit**

```bash
git add api/v1/schemas.py api/v1/metering_endpoints.py api/v1/tests/test_ingest_endpoint.py
git commit -m "feat(api): POST /metering/usage/ingest async accept path with accept-time hard stop"
```

---

### Task 6: Settlement

**Files:**
- Modify: `ubb-platform/apps/metering/usage/services/usage_service.py` (add `settle_raw`)
- Modify: `ubb-platform/apps/platform/runs/services.py` (add `accumulate_cost_settled`)
- Create: `ubb-platform/apps/metering/usage/tasks.py` additions (or create file if absent): `settle_raw_events` Celery task
- Test: `ubb-platform/apps/metering/usage/tests/test_settlement.py`

**Interfaces:**
- Consumes: `RawIngestEvent`, `PricingService.price`, `TierMirror.write`, `settle_ingest_hold`/`release_ingest_hold` (queries ports), `write_event`/`UsageRecorded`, `RunService`.
- Produces:
  - `UsageService.settle_raw(raw: RawIngestEvent) -> "settled" | "duplicate"` — inside `@transaction.atomic`: exact pricing (tier ladders lock here, worker-only contention), `UsageEvent` insert (IntegrityError → duplicate), `RunService.accumulate_cost_settled` (accumulates true cost, **never raises** — enforcement already happened at accept; stamps heartbeat), outbox `write_event(UsageRecorded(...))`, then post-commit: `settle_ingest_hold(delta=estimate−exact)` (or `release_ingest_hold(estimate)` for duplicate) and `TierMirror.write(units_total_after)` from the provenance `tier_breakdown`.
  - `accumulate_cost_settled(run_id, cost_micros)` — same row lock + heartbeat as `accumulate_cost` but no limit checks and tolerates non-active runs (a settle after kill must still record cost).
  - `settle_raw_events(batch_size=200)` — `@shared_task(queue="ubb_metering")`: claims `status="pending"` rows `select_for_update(skip_locked=True).order_by("created_at")[:batch_size]`, settles each in its own transaction, increments `attempts`, marks `failed` + releases hold + `logger.error` after 5 attempts, re-enqueues itself if it drained a full batch. Register in the same beat schedule file the outbox drain uses (find with `grep -rn "beat_schedule" config/`) at a 10s cadence as the straggler sweeper.

- [ ] **Step 1: Write failing tests**: (a) settle nets to exact — accept-style raw with estimate 2_500_000 whose exact price is 2_200_000 → after settle, live balance reflects exactly the exact price (property: hold+settle ≡ sync debit); (b) duplicate → second raw with same idempotency_key settles as `"duplicate"`, hold released, no second `UsageEvent`, no second outbox row; (c) settle after run kill still records cost, run total updated, no exception; (d) poison payload → after 5 attempts marked `failed`, hold released, error logged; (e) tier mirror written to `units_total_after` from provenance.

- [ ] **Step 2: Run to verify failure.**

- [ ] **Step 3: Implement `settle_raw`** — core shape:

```python
@staticmethod
def settle_raw(raw):
    """Exact-settle one accepted raw event. Enforcement already happened at
    accept; this path NEVER rejects — it prices exactly, records durably,
    and adjusts the live counter by (estimate - exact)."""
    from apps.billing.queries import settle_ingest_hold, release_ingest_hold
    tenant, customer = raw.tenant, raw.customer
    try:
        with transaction.atomic():
            # AS-BUILT: the claim in settle_raw_events only COLLECTS ids (it
            # never marks rows), so two overlapping invocations can claim the
            # same still-"pending" id. Re-locking the specific row and
            # re-checking status here is the exactly-once guarantee for every
            # Redis hold adjustment below.
            raw = RawIngestEvent.objects.select_for_update().get(id=raw.id)
            if raw.status != "pending":
                return raw.status
            p = raw.payload
            provider_cost, billed, provenance = PricingService.price(
                tenant=tenant, customer=customer,
                event_type=p.get("event_type", ""), provider=p.get("provider", ""),
                usage_metrics=p.get("usage_metrics"), tags=p.get("tags"),
                currency=(tenant.default_currency or "usd").lower(),
                caller_provider_cost=p.get("provider_cost_micros"),
                caller_billed=p.get("billed_cost_micros"), units=p.get("units"),
                as_of=_parse_effective_at(p))
            event = UsageEvent.objects.create(
                tenant=tenant, customer=customer,
                request_id=p.get("request_id", ""),
                idempotency_key=raw.idempotency_key,
                billing_owner_id=raw.billing_owner_id, run_id=raw.run_id,
                provider_cost_micros=provider_cost, billed_cost_micros=billed,
                # ... same field mapping as record_usage's create() ...
            )
            if raw.run_id:
                RunService.accumulate_cost_settled(
                    raw.run_id, billed, tenant_id=tenant.id, customer_id=customer.id)
            write_event(UsageRecorded(...))  # same construction as record_usage
            raw.status = "settled"
            raw.save(update_fields=["status", "updated_at"])
    except IntegrityError:
        # AS-BUILT: the IntegrityError rolled the atomic back, RELEASING the
        # row lock while DB status is still "pending" — a racing worker can be
        # right here too. Resolve under a FRESH lock; only the winner of the
        # pending -> duplicate flip releases the hold (post-commit), so the
        # release is exactly-once (a double release over-credits the live
        # gate — over-permissive, the worst direction).
        with transaction.atomic():
            locked = RawIngestEvent.objects.select_for_update().get(id=raw.id)
            if locked.status != "pending":
                return locked.status  # racer already resolved (and released)
            locked.status = "duplicate"
            locked.save(update_fields=["status", "updated_at"])
        if locked.held:
            release_ingest_hold(locked.billing_owner_id, tenant, raw.run_id,
                                locked.estimate_micros)
        return "duplicate"
    if raw.held:
        settle_ingest_hold(raw.billing_owner_id, tenant, raw.run_id,
                           raw.estimate_micros - billed)
    else:
        # idem-hit at accept took NO hold; apply the full exact debit so the
        # live counter still converges (matches record_live_usage_debit).
        settle_ingest_hold(raw.billing_owner_id, tenant, raw.run_id, -billed)
    _write_tier_mirrors(tenant, customer, provenance)  # SET units_total_after per metric
    return "settled"
```

AS-BUILT NOTE (poison bookkeeping, same lock discipline): `settle_raw_events`'s
exception handler mirrors the duplicate path — it re-locks the raw
(`select_for_update`), re-checks `status == "pending"` under the lock,
increments `attempts` atomically (an unlocked read-modify-write would lose
increments between racing invocations), flips to `"failed"` inside the lock at
the 5-attempt ceiling, and only the flip WINNER releases the hold post-commit.

IMPLEMENTER NOTE (subtle, load-bearing): the un-held branch (`raw.held is False`) covers the retry-append case. If the FIRST append settled already, this settle hits IntegrityError → duplicate → no double debit. If the first append was LOST (crash between hold and append), this row is the only survivor and carries `held=False` while the orphaned hold decremented the counter — the full `-billed` debit here would double-count against the orphan; the hourly `reconcile_prepaid` MIN-merge is the documented corrector (spec invariant 7). Do not "fix" this locally; write the test to pin the reconcile behavior instead.

- [ ] **Step 4: Implement `accumulate_cost_settled` + the Celery task; wire the beat entry.**

- [ ] **Step 5: Run tests + full metering suite.**

- [ ] **Step 6: Commit**

```bash
git add apps/metering/usage/services/usage_service.py apps/metering/usage/tasks.py apps/platform/runs/services.py config/ apps/metering/usage/tests/test_settlement.py
git commit -m "feat(metering): exact settlement workers for async ingest (estimate-delta, dedup, tier mirror)"
```

---

### Task 7: Stop propagation (pub/sub + webhook event)

**Files:**
- Modify: `ubb-platform/apps/billing/gating/services/live_ledger_service.py` (`_set_stop`)
- Modify: `ubb-platform/apps/platform/events/schemas.py` (add `StopFired`)
- Test: extend `ubb-platform/apps/billing/gating/tests/test_hold_service.py`

**Interfaces:**
- Produces: setting the stop flag additionally (a) PUBLISHes `ubb:stopchan:{owner_id}` with the reason (consumed by the future SSE endpoint — Plan 2), and (b) writes a `StopFired{tenant_id, owner_id, reason, scope}` outbox event so the existing outgoing-webhook system delivers `stop.fired` to tenant endpoints. Both best-effort; must never raise into the accept path.

- [ ] **Step 1: Failing test** — crossing the floor via `HoldService.acquire` publishes on `ubb:stopchan:{owner}` (subscribe with a raw client in the test) and creates one outbox row of type `StopFired`; a second crossing while the flag is already set does NOT emit again (flag-transition-only, no spam).

- [ ] **Step 2: Verify failure.**

- [ ] **Step 3: Implement** — in `_set_stop`, detect the transition with `SET ... NX` on a companion marker or `SETNX`-style return, then:

```python
@staticmethod
def _set_stop(owner_id, reason, tenant_id=None):
    client = _client()
    was_new = client.set(_stop_key(owner_id), reason, ex=LEDGER_TTL_SECONDS, nx=True)
    if not was_new:
        client.expire(_stop_key(owner_id), LEDGER_TTL_SECONDS)
        return
    try:
        client.publish(f"ubb:stopchan:{owner_id}", reason)
    except Exception:
        logger.warning("live_ledger.stop_publish_failed",
                       extra={"data": {"owner_id": str(owner_id)}})
    if tenant_id:
        try:
            from apps.platform.events.outbox import write_event
            from apps.platform.events.schemas import StopFired
            write_event(StopFired(tenant_id=str(tenant_id),
                                  owner_id=str(owner_id), reason=reason,
                                  scope="customer"))
        except Exception:
            logger.warning("live_ledger.stop_event_failed",
                           extra={"data": {"owner_id": str(owner_id)}})
```

Thread `tenant_id` through from the two `_set_stop` call sites (`record_usage_debit`, `HoldService.acquire`). CAUTION: `_clear_stop` must also delete the NX transition marker if you used a companion key — with the `nx=True`-on-the-flag-itself approach above there is no companion key, and recovery (`credit`/reconcile `_clear_stop`) naturally re-arms the transition. Check every `_set_stop` caller compiles with the new signature (`grep -rn "_set_stop" apps/`).

- [ ] **Step 4: Verify pass; run the full gating + events suites.**

- [ ] **Step 5: Commit**

```bash
git add apps/billing/gating/services/live_ledger_service.py apps/platform/events/schemas.py apps/billing/gating/tests/test_hold_service.py
git commit -m "feat(billing): stop-flag transitions publish pub/sub + stop.fired outbox event"
```

---

### Task 8: End-to-end burn-to-floor + docs

**Files:**
- Test: `ubb-platform/api/v1/tests/test_ingest_e2e.py`
- Modify: `ubb-platform/docs/plans/2026-07-03-async-ingestion-hard-stop-design.md` (status → implemented for Rung A core; record measured numbers)

- [ ] **Step 1: Write the E2E test** — tenant (prepaid, enforcement on, `metering_async` product), owner funded $20, linear $10/1M-token card. Drive batches through the ingest endpoint until the floor crosses; then run `settle_raw_events` eagerly (CELERY_TASK_ALWAYS_EAGER or call the task function). Assert: (a) the crossing item's verdict has `stop: true`; (b) every subsequent item's verdict has `stop: true`; (c) overage = `|live balance at flag-set|` ≤ the crossing batch's estimate sum (the spec's bound); (d) after settlement, `sum(UsageEvent.billed_cost_micros)` equals the durable wallet drawdown total and the live counter matches durable balance after `reconcile_prepaid`; (e) a whole-batch replay creates zero new `UsageEvent` rows and leaves balances unchanged.

- [ ] **Step 2–4: Run, fix anything it flushes out, get green, run the FULL platform suite** (`pytest --tb=short -q`) — zero regressions allowed, sync-path tests must be untouched.

- [ ] **Step 5: Commit**

```bash
git add api/v1/tests/test_ingest_e2e.py docs/plans/2026-07-03-async-ingestion-hard-stop-design.md
git commit -m "test(metering): E2E async-ingest burn-to-floor with bounded overage assertion"
```

---

## Follow-up plans (not in this plan — deliberate)

1. **Plan 2 — SSE endpoint + SDK batching** (`ubb-sdk`): background flush buffer, SSE subscription, local `stopped` flag, `on_stop`, at-least-once retry.
2. **Plan 3 — Rung B**: swap `RawIngestEvent.bulk_create` seam for Redpanda produce + consumer-group settlers; ASGI deployment of the ingest route; load test.
3. Per-task cap (P4) on the async path; per-tenant fail-closed knob; auth cache.
