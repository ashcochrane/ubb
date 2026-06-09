# Wave 2 — Journey-1 Cost Attribution Best-in-Class: Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make per-customer cost attribution best-in-class on the data/API axis: first-class indexed `service`/`agent` attribution (derived from tags), one-call multi-dimension COGS breakdowns, a native time-series spend rollup, and bulk-create + updatable rate cards with readable version history — all reachable through the SDK.

**Architecture:** `service_id`/`agent_id` become **indexed columns derived from `tags`** (single source of truth, no wire change); cost-card matching stays in the existing `dimensions`-subset-of-`tags` mechanism (frozen). Analytics gains a `dimensions=[...]` multi-breakdown + a `/timeseries` rollup over `TruncHour`/`TruncDate`. Rate cards gain a stable `lineage_id` enabling bulk-create, lineage-aware update (soft-versioning), and point-in-time history.

**Tech Stack:** Django 6, django-ninja, Postgres (JSONB, `KeyTextTransform`, partial unique constraints), pytest-django, the `ubb` SDK (httpx).

**Design ref:** `docs/plans/2026-06-09-wave2-cost-attribution-design.md`. **Owner decisions locked:** validation fail-open + loud (opt-in strict = the existing `require_cost_card_coverage` flag); **no** product_id-in-matching; parallel breakdowns (no cube); **no** UI.

---

## ⚠️ Caveats / facts (verified against code)
- `UsageEvent` is **immutable** (`save()` raises on update — usage/models.py:54-57). Backfills MUST use raw SQL / `.update()`, never per-row `.save()`.
- Cost-card matching: `_resolve_card` keys on tenant/card_type/provider/event_type/metric_name/currency + customer-specific-then-default + `dimensions ⊆ tags` (pricing_service.py:15-35). `service`/`agent` already match via `dimensions={"service":...}`. **Do not touch the matcher.**
- The opt-in strict/typo-proof mode already exists: `require_cost_card_coverage` 422s on uncosted metrics (pricing_service.py:62-65); a dimension typo → no matching cost card → uncosted → 422 when the flag is on. Wave 1 already surfaces `uncosted_metrics` in the record-usage response (the loud default). **So Wave 2 builds NO new validation model.**
- usage migration head = `0020_usageevent_billing_owner_id`. Find pricing head: `git ls-files ubb-platform/apps/metering/pricing/migrations | grep -v __init__ | tail -1`.
- Time-series pattern: `get_revenue_analytics` uses `TruncDate("effective_at")` (queries.py:101-107). Breakdown machinery: `get_dimensional_margin` (queries.py:179-216).

## Conventions
- Platform from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>`. Baseline **750 platform green**. SDK from `ubb-sdk/` (unset DJANGO_SETTINGS_MODULE), **156 green**. Commit per task; `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR.

---

### Task 1: `service_id` / `agent_id` attribution columns (derived from tags)

**Files:** Modify `apps/metering/usage/models.py`, `apps/metering/usage/services/usage_service.py`, `api/v1/schemas.py` (`RecordUsageResponse`), `api/v1/metering_endpoints.py` (record-usage response); migration `usage/0021_*` (+ raw-SQL backfill); Test `apps/metering/usage/tests/test_attribution_columns.py`.

- [ ] **Step 1 — Failing test:**
```python
import pytest
from apps.platform.tenants.models import Tenant
from apps.platform.customers.models import Customer
from apps.metering.usage.services.usage_service import UsageService
from apps.metering.usage.models import UsageEvent


@pytest.mark.django_db
def test_service_agent_product_derived_from_tags():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  tags={"service": "search", "agent": "planner", "product": "p1"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.service_id == "search"
    assert e.agent_id == "planner"
    assert e.product_id == "p1"  # fell back from tags when request product_id empty

@pytest.mark.django_db
def test_explicit_product_id_wins_over_tag():
    t = Tenant.objects.create(name="T")
    c = Customer.objects.create(tenant=t, external_id="c1")
    r = UsageService.record_usage(t, c, "r1", "i1", provider_cost_micros=1000,
                                  product_id="explicit", tags={"product": "fromtag", "service": "s"})
    e = UsageEvent.objects.get(id=r["event_id"])
    assert e.product_id == "explicit"
    assert e.service_id == "s"
```

- [ ] **Step 2 — Run** → FAIL.

- [ ] **Step 3 — Fields** in `apps/metering/usage/models.py` on `UsageEvent` (after `product_id`):
```python
    service_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
    agent_id = models.CharField(max_length=100, blank=True, default="", db_index=True)
```
Add a composite index to `Meta.indexes`:
```python
            models.Index(fields=["tenant", "product_id", "service_id", "agent_id", "-effective_at"],
                         name="idx_usage_attribution"),
```
Add the reserved-keys constant at module top:
```python
RESERVED_DIM_KEYS = ("product", "service", "agent")
```

- [ ] **Step 4 — Derive** in `apps/metering/usage/services/usage_service.py` `record_usage`, just before the `UsageEvent.objects.create(...)` (alongside the existing `owner_id` line):
```python
        _tags = tags or {}
        service_id = _tags.get("service", "")
        agent_id = _tags.get("agent", "")
        if not product_id:
            product_id = _tags.get("product", "") or ""
```
Add `service_id=service_id, agent_id=agent_id` to the `UsageEvent.objects.create(...)` kwargs (product_id is already a kwarg — it now carries the fallback).

- [ ] **Step 5 — Echo** in `RecordUsageResponse` (api/v1/schemas.py) add `service_id: str = ""` and `agent_id: str = ""`; in the record-usage endpoint include them in the response dict from the created event (the `_result`/event has them). (The SDK `RecordUsageResult` is tolerant from Wave 1; add `service_id`/`agent_id` to its dataclass in Task 6's SDK pass, or they pass through harmlessly.)

- [ ] **Step 6 — Migration + backfill:** `$DJ manage.py makemigrations usage` (`0021`); then EDIT it to append a Postgres raw-SQL backfill `RunPython` (derive from tags for existing rows; bypasses the immutability guard):
```python
def _backfill(apps, schema_editor):
    schema_editor.execute(
        "UPDATE ubb_usage_event SET service_id = COALESCE(tags->>'service','') "
        "WHERE tags IS NOT NULL AND tags ? 'service'")
    schema_editor.execute(
        "UPDATE ubb_usage_event SET agent_id = COALESCE(tags->>'agent','') "
        "WHERE tags IS NOT NULL AND tags ? 'agent'")
    schema_editor.execute(
        "UPDATE ubb_usage_event SET product_id = COALESCE(tags->>'product','') "
        "WHERE product_id = '' AND tags IS NOT NULL AND tags ? 'product'")
```
append `migrations.RunPython(_backfill, migrations.RunPython.noop)`. Then `$DJ manage.py makemigrations --check --dry-run` → "No changes detected"; `$DJ manage.py migrate`.

- [ ] **Step 7 — Verify:** `$DJ manage.py check`; `$DJ -m pytest apps/metering/usage api/v1/tests/test_metering_endpoints.py -q` → green. **Commit:** `feat(metering): derive indexed service_id/agent_id attribution columns from tags`.

---

### Task 2: Multi-dimension COGS breakdown in one call

**Files:** Modify `api/v1/metering_endpoints.py` (`usage_analytics`), `api/v1/schemas.py` (`UsageAnalyticsResponse`), `ubb-sdk/ubb/metering.py` (`usage_analytics`); Test `api/v1/tests/test_metering_endpoints.py`, `ubb-sdk/tests/test_metering_client.py`.

- [ ] **Step 1 — Failing test** (platform): with a tenant/customer + a couple of events carrying `product_id`/`tags`, GET `/api/v1/metering/analytics/usage?customer_id=<id>&dimensions=product_id&dimensions=service_id&dimensions=tag:agent` → 200 with a `breakdowns` dict whose keys are `product_id`, `service_id`, `tag:agent`, each a list of rows `{dimension, event_count, total_provider_cost_micros, total_billed_cost_micros}`.
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Implement.** In `usage_analytics`, add `dimensions: list[str] = Query(None)`. Validate each against allowed `{"provider","event_type","product_id","customer","service_id","agent_id"}` or `tag:<key>` where `<key>` matches `^[a-z][a-z0-9_]{1,63}$`; cap at 6; 422 on unknown/over-cap. Build `breakdowns: dict[str, list]`:
```python
    breakdowns = {}
    for dim in (dimensions or []):
        if dim.startswith("tag:"):
            from django.db.models.functions import Cast
            from django.contrib.postgres.fields.jsonb import KeyTextTransform  # or django.db.models.functions
            key = dim[4:]
            rows = list(qs.exclude(**{f"tags__{key}__isnull": True})
                        .annotate(dimension=KeyTextTransform(key, "tags"))
                        .values("dimension").annotate(
                            event_count=Count("id"),
                            total_provider_cost_micros=Sum("provider_cost_micros"),
                            total_billed_cost_micros=Sum("billed_cost_micros"))
                        .order_by("-total_billed_cost_micros"))
        else:
            col = "customer__external_id" if dim == "customer" else dim
            rows = list(qs.exclude(**{col: ""}) if dim != "customer" else qs)
            rows = list((qs if dim == "customer" else qs.exclude(**{col: ""}))
                        .values(col).annotate(
                            event_count=Count("id"),
                            total_provider_cost_micros=Sum("provider_cost_micros"),
                            total_billed_cost_micros=Sum("billed_cost_micros"))
                        .order_by("-total_billed_cost_micros"))
            for r in rows:
                r["dimension"] = r.pop(col)
        breakdowns[dim] = rows
    # include in the response dict; keep the legacy by_* keys when dimensions is None
```
(VERIFY the correct `KeyTextTransform` import for this Django/Postgres — `from django.db.models.functions import ...` or `django.contrib.postgres.fields.jsonb` — and simplify the column branch to one clean queryset; the above shows intent. Add `breakdowns: dict = {}` to `UsageAnalyticsResponse`. When `dimensions` is omitted, behave exactly as today.)
- [ ] **Step 4 — SDK:** extend `MeteringClient.usage_analytics(..., dimensions=None)` — pass `dimensions` as a repeated query param (`params["dimensions"] = dimensions` list). SDK test asserts the list is sent.
- [ ] **Step 5 — Verify:** `$DJ -m pytest api/v1 apps/metering -q`; SDK `<venv> -m pytest -q`. **Commit:** `feat(analytics): one-call multi-dimension COGS breakdown (+ SDK)`.

---

### Task 3: Native time-series spend rollup

**Files:** Create `get_usage_timeseries` in `apps/metering/queries.py`; Modify `api/v1/metering_endpoints.py` (+ new endpoint), `api/v1/schemas.py` (`UsageTimeseriesResponse`), `ubb-sdk/ubb/metering.py`; Test `api/v1/tests/test_metering_endpoints.py`, SDK test.

- [ ] **Step 1 — Failing test** (platform): create a customer + 3 events on 3 distinct `effective_at` days (force via `UsageEvent.objects.filter(id=...).update(effective_at=...)` — immutable); GET `/api/v1/metering/analytics/usage/timeseries?customer_id=<id>&granularity=day` → 200 with a `series` of 3 buckets each `{bucket, provider_cost_micros, billed_cost_micros, event_count}`; assert the bucket provider sums reconcile to the total. Also `granularity=hour` works, and an invalid granularity → 422.
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Query** in `apps/metering/queries.py`:
```python
def get_usage_timeseries(tenant_id, *, granularity="day", customer_id=None,
                         group_by=None, tag_key=None, start_date=None, end_date=None):
    from django.db.models import Sum, Count
    from django.db.models.functions import TruncHour, TruncDate
    from apps.metering.usage.models import UsageEvent
    trunc = TruncHour if granularity == "hour" else TruncDate
    qs = UsageEvent.objects.filter(tenant_id=tenant_id)
    if customer_id:
        qs = qs.filter(customer_id=customer_id)
    if start_date:
        qs = qs.filter(effective_at__date__gte=start_date)
    if end_date:
        qs = qs.filter(effective_at__date__lt=end_date)
    group_cols = ["bucket"]
    if group_by in ("provider", "event_type", "product_id", "service_id", "agent_id"):
        group_cols.append(group_by)
    rows = (qs.annotate(bucket=trunc("effective_at")).values(*group_cols).annotate(
        provider_cost_micros=Sum("provider_cost_micros"),
        billed_cost_micros=Sum("billed_cost_micros"),
        event_count=Count("id")).order_by("bucket"))
    out = []
    for r in rows:
        d = dict(r)
        d["bucket"] = d["bucket"].isoformat() if d.get("bucket") else None
        if group_by and group_by in d:
            d["dimension"] = d.pop(group_by)
        d["markup_micros"] = (d["billed_cost_micros"] or 0) - (d["provider_cost_micros"] or 0)
        out.append(d)
    return out
```
- [ ] **Step 4 — Endpoint** `GET /api/v1/metering/analytics/usage/timeseries`: params `granularity: str = "day"` (validate ∈ {hour,day} else 422), `start_date`/`end_date`/`customer_id`/`group_by`/`tag_key`; guardrail: reject hourly windows > 92 days (422). Return `UsageTimeseriesResponse {granularity, group_by, tag_key, series: [...]}` (add the schema). (For v1, UTC buckets; `tag_key` time-series may be deferred — if included, aggregate in Python like `get_dimensional_margin`; otherwise reject `tag_key` with 422 and note it as a follow-on.)
- [ ] **Step 5 — SDK:** `MeteringClient.usage_timeseries(*, granularity="day", start_date=None, end_date=None, customer_id=None, group_by=None, tag_key=None)` → GET the endpoint, return the dict. SDK test.
- [ ] **Step 6 — Verify:** `$DJ -m pytest api/v1 apps/metering -q`; SDK green. **Commit:** `feat(analytics): time-series spend rollup endpoint (+ SDK)`.

---

### Task 4: Rate-card `lineage_id` + lineage-aware update + readable history

**Files:** Modify `apps/metering/pricing/models.py` (`RateCard.lineage_id`), `api/v1/metering_endpoints.py` (PUT + history GET), `api/v1/schemas.py` (`RateCardOut` + history), `ubb-sdk/ubb/metering.py` + `ubb-sdk/ubb/types.py` (`RateCard.lineage_id`); migration `pricing/000X_*` (+ backfill); Tests.

- [ ] **Step 1 — Failing test** (platform): create a cost card; PUT `/api/v1/metering/pricing/rate-cards/{id}` changing `rate_per_unit_micros` → returns a NEW card with the SAME `lineage_id`, the old one's `valid_to` set; GET `/api/v1/metering/pricing/rate-cards/{lineage_id}/history` → both versions newest-first with non-overlapping validity; GET `/api/v1/metering/pricing/rate-cards?include_history=true&as_of=<before change>` returns the OLD rate.
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Field + migration.** Add `lineage_id = models.UUIDField(default=uuid.uuid4, editable=False, db_index=True)` to `RateCard` (`import uuid`). `$DJ manage.py makemigrations pricing`; EDIT it to backfill existing rows — group by the natural key and assign one lineage per group (RunPython):
```python
def _backfill_lineage(apps, schema_editor):
    import uuid
    RateCard = apps.get_model("pricing", "RateCard")
    groups = {}
    for c in RateCard.objects.all().order_by("valid_from"):
        key = (c.tenant_id, c.customer_id, c.card_type, c.provider, c.event_type,
               c.metric_name, c.dimensions_hash, c.currency)
        lid = groups.setdefault(key, uuid.uuid4())
        RateCard.objects.filter(id=c.id).update(lineage_id=lid)
```
append `migrations.RunPython(_backfill_lineage, migrations.RunPython.noop)`. `makemigrations --check` clean; `migrate`.
- [ ] **Step 4 — Lineage-aware PUT** (the existing soft-versioning PUT): resolve the target by `id` (fallback `lineage_id + valid_to IS NULL`); within ONE `transaction.atomic()`: set `old.valid_to = now()` (save), then create the new version copying `old.lineage_id`. Add `RateCardOut.lineage_id` + the `valid_from`/`valid_to` fields if absent.
- [ ] **Step 5 — History endpoints:** `GET /pricing/rate-cards/{lineage_id}/history` → all versions for that lineage, `order_by("-valid_from")`. Extend `GET /pricing/rate-cards` with `include_history: bool = False` + `as_of: datetime = None` (when `as_of`, filter `valid_from <= as_of AND (valid_to IS NULL OR valid_to > as_of)`; default = active only as today).
- [ ] **Step 6 — SDK:** `update_rate_card(card_id, **fields)` (PUT), `get_rate_card_history(lineage_id)` (GET history), `list_rate_cards(..., include_history=False, as_of=None)`; add `lineage_id` to the `RateCard` dataclass (`ubb-sdk/ubb/types.py`). Tests.
- [ ] **Step 7 — Verify:** `$DJ manage.py check`; `$DJ -m pytest api/v1 apps/metering -q`; SDK green. **Commit:** `feat(pricing): rate-card lineage_id + lineage-aware update + readable history (+ SDK)`.

---

### Task 5: Bulk rate-card create

**Files:** Modify `api/v1/metering_endpoints.py` (+ batch endpoint), `ubb-sdk/ubb/metering.py`; Tests.

- [ ] **Step 1 — Failing test** (platform): POST `/api/v1/metering/pricing/rate-cards/batch` with `{"cards": [<two valid RateCardIn>]}` → 201 `{created: [...], count: 2}` and both exist; a batch where ONE card has an invalid `card_type` → 422 and **zero** cards created (atomic).
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Implement** `POST /pricing/rate-cards/batch` (response `{201: dict, 422: dict}`): body `cards: list[RateCardIn]` (reject empty or >100 → 422). In a single `transaction.atomic()`: first validate EVERY card's `card_type`/`pricing_model` (reuse the Wave-1 enum check) + any product-gating; if any invalid, return 422 before creating; then create all. Return the created ids + count.
- [ ] **Step 4 — SDK:** `bulk_create_rate_cards(cards: list[dict])` → POST the batch endpoint; SDK test.
- [ ] **Step 5 — Verify:** `$DJ -m pytest api/v1 apps/metering -q`; SDK green. **Commit:** `feat(pricing): bulk rate-card create (atomic, +SDK)`.

---

### Task 6: Capstone — Journey-1 best-in-class live-server SDK integration test

**Files:** Create `api/v1/tests/test_journey1_best_in_class.py`; finalize SDK `RecordUsageResult` (`service_id`/`agent_id`) in `ubb-sdk/ubb/types.py` if not already.

- [ ] **Step 1 — Ensure SDK importable** (editable install from Wave 1 should persist): `<platform venv> -c "import ubb"`.
- [ ] **Step 2 — Write the capstone** (`live_server` + the `_no_outbox_dispatch` fixture pattern from `test_journey1_sdk_integration.py` — patch `apps.platform.events.tasks.process_single_event.delay` to neutralize the broker). The script, via the SDK only:
  1. `bulk_create_rate_cards` two cost cards differing only by a `service` dimension (`dimensions={"service":"a"}` vs `{"service":"b"}`) for metric `tokens`.
  2. Record ~8 events across **2 customers × 2 products × 2 services × 2 agents** over **3 days** (force `effective_at` via `.update()`), some with a mis-typed `agent` tag.
  3. `usage_analytics(customer_id=C1, dimensions=["product_id","service_id","agent_id","provider"])` → assert all breakdowns sum to the same total COGS and the typo'd agent surfaces as its own row.
  4. `usage_timeseries(customer_id=C1, granularity="day", group_by="service_id")` → assert 3 day-buckets whose per-service COGS reconcile to the breakdown totals.
  5. `update_rate_card` to change one rate; record one more event; `get_rate_card_history(lineage_id)` → assert two non-overlapping versions; `list_rate_cards(as_of=<before change>)` → old rate.
  6. With the tenant's `require_cost_card_coverage` flipped ON, assert an event whose metric has no matching cost card (the typo path) is rejected **422** (the opt-in strict mode).
- [ ] **Step 3 — Run** 2-3x for stability → green.
- [ ] **Step 4 — Verify + commit:** `test(journey1): best-in-class cost-attribution capstone via SDK (multi-dim + timeseries + history + strict)`.

---

### Task 7: Final verification
- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected".
- [ ] **Fresh-DB:** drop/recreate `ubb`; `$DJ manage.py migrate` applies `usage/0021` + the pricing `lineage_id` migration (with backfills) cleanly; `$DJ -m pytest -q` whole platform suite green (report count); `cd ../ubb-sdk && <venv> -m pytest -q` green.
- [ ] Capstone passes; clean tree.

---

## Self-Review
**Spec coverage:** service/agent indexed columns derived from tags (T1) ✓; multi-key one-call breakdown, parallel not cube (T2) ✓; time-series rollup (T3) ✓; lineage_id + update + history (T4) ✓; bulk create (T5) ✓; SDK methods folded per-task (T2/T3/T4/T5) ✓; opt-in strict = existing `require_cost_card_coverage` (capstone T6 step 6; no new model — per locked decision) ✓; matching frozen / no product_id-in-matching ✓; no UI ✓; capstone (T6) ✓.
**Placeholder scan:** T2's `KeyTextTransform` branch is marked "verify the import + simplify" with the concrete intent; backfills are concrete raw SQL / RunPython. No TBD.
**Type consistency:** `service_id`/`agent_id` (T1) read by analytics (T2), timeseries (T3), capstone (T6); `lineage_id` (T4) used by history + SDK (T4) + capstone (T6); `dimensions=[...]` (T2) + `usage_timeseries` (T3) + `bulk_create_rate_cards` (T5) are the SDK methods the capstone calls.
**Migrations:** `usage/0021` (cols + backfill) + pricing `lineage_id` (+ backfill); DB-validated T1/T4 + fresh-DB T7.
