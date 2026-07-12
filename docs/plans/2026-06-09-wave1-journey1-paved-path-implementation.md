# Wave 1 — Journey 1 Paved Path Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the cost-attribution journey (Journey 1) reachable and correct through the official SDK + analytics — so a Type-1 tenant can configure cost rate-cards, record multi-metric events, and read true per-customer COGS by dimension without dropping to raw HTTP.

**Architecture:** The server engine already supports everything (provider_cost optional + computed from cost cards via `PricingService.price`; `usage_metrics` accepted; `uncosted_metrics` captured in provenance). Wave 1 fixes the *client surface + two small server touches*: SDK rate-card URL 404, SDK `record_usage` can't send `usage_metrics`, analytics breakdowns report billed-not-provider cost, rate-card create accepts invalid `card_type`, miscosted metrics are silent, dead SDK methods 404, onboarding misleads. A capstone live-server integration test proves the whole J1 path works end-to-end through the SDK.

**Tech Stack:** Django 6, django-ninja, pytest-django, the `ubb` Python SDK (httpx).

**Review ref:** `docs/plans/2026-06-09-phase2-journey-review.md` (Wave 1).

---

## ⚠️ Caveats / facts (verified against the code)
- **Server is ready.** `RecordUsageRequest.provider_cost_micros: Optional[int] = None` + `usage_metrics: Optional[dict[str,int]]` (api/v1/schemas.py:29,31); `UsageService.record_usage(..., provider_cost_micros=None, usage_metrics=None)` calls `PricingService.price(..., usage_metrics=..., caller_provider_cost=provider_cost_micros)` which computes COGS from cost cards (usage_service.py:54-67). So omitting cost + sending metrics ALREADY works server-side — Task 3 is SDK-only.
- `card_type ∈ {cost, price}`, `pricing_model ∈ {per_unit, flat}` (pricing/models.py:38-39). `RateCardIn.card_type: str` (no validation, schemas.py:221-227).
- `uncosted_metrics` is written to provenance + `require_cost_card_coverage` is an opt-in per-tenant hard-fail, default off (pricing_service.py:50-65). **Do NOT flip that default** — surface the warning in the response instead (non-breaking).
- Dead SDK methods: `get_economics` / `get_customer_economics` / `get_economics_summary` (ubb-sdk/ubb/subscriptions.py:66-97) hit `/api/v1/subscriptions/economics*` which is NOT mounted → 404.

## Conventions
- Platform: run from `ubb-platform/`, `$DJ` = `DJANGO_SETTINGS_MODULE=config.settings <venv python>` (`.venv/Scripts/python.exe`). Baseline **745 platform green**.
- SDK: run from `ubb-sdk/` with NO `DJANGO_SETTINGS_MODULE` (unset it); `<venv python> -m pytest -q`. Baseline **152 SDK green**.
- Commit per task; end messages with `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. No PR/merge.

---

### Task 1: Analytics breakdowns report provider cost (COGS), not just billed

**Files:** Modify `api/v1/metering_endpoints.py` (`usage_analytics` ~239-282), `api/v1/schemas.py` (the `UsageAnalyticsResponse` row schemas ~160-175); Test `api/v1/tests/test_metering_endpoints.py`.

- [ ] **Step 1 — Failing test** (append; mirror the file's auth/client setup — tenant + `TenantApiKey.create_key` + Bearer + `django.test.Client`): create a tenant + customer; create a `UsageEvent` with `provider_cost_micros=300_000, billed_cost_micros=500_000, product_id="search"`; GET the metering API `/analytics/usage?customer_id=<id>` with the Bearer key; assert each `by_customer` and `by_product` row has `total_provider_cost_micros == 300_000` (today it only has `total_cost_micros == 500_000`).
- [ ] **Step 2 — Run** → FAIL (KeyError / missing field).
- [ ] **Step 3 — Implement.** In `usage_analytics`, add `total_provider_cost_micros=Sum("provider_cost_micros")` to EACH breakdown annotate (`by_provider`, `by_event_type`, `by_customer`, `by_product`) and to the `by_tag` manual aggregation (accumulate a `provider` sum alongside `billed`). For example `by_customer`:
```python
    by_customer = list(
        qs.values("customer__external_id").annotate(
            event_count=Count("id"),
            total_cost_micros=Sum("billed_cost_micros"),
            total_provider_cost_micros=Sum("provider_cost_micros"),
        ).order_by("-total_cost_micros")
    )
```
and in `by_tag`'s defaultdict track `{"event_count":0, "total_cost_micros":0, "total_provider_cost_micros":0}`, summing `provider_cost_micros` per row, and emit `total_provider_cost_micros` in each tag dict. Then in `api/v1/schemas.py`, add `total_provider_cost_micros: int = 0` to each breakdown-row schema used by `UsageAnalyticsResponse` (read the row schema class names there and add the field to each).
- [ ] **Step 4 — Verify:** `$DJ -m pytest api/v1/tests/test_metering_endpoints.py -q` → green. **Commit:** `fix(analytics): report provider cost (COGS) in every usage breakdown row`.

---

### Task 2: Rate-card create validates card_type/pricing_model; miscosted metrics surface loudly

**Files:** Modify `api/v1/metering_endpoints.py` (the `@metering_api.post("/pricing/rate-cards")` create ~326-349 + the record-usage endpoint response), `api/v1/schemas.py` (`RecordUsageResponse`); Test `api/v1/tests/test_metering_endpoints.py`.

- [ ] **Step 1 — Failing tests** (append): (a) POST the metering API `/pricing/rate-cards` with `card_type="costs"` (invalid) → expect **422** with an error (today it 200s + silently never prices); also `pricing_model="graduated"` → 422. (b) record a usage event whose `usage_metrics` has a metric with NO matching cost card → the record-usage response includes `uncosted_metrics` listing that metric (today the caller gets no signal).
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3a — Validate** in the rate-card create endpoint, before `RateCard.objects.create(...)`:
```python
    from apps.metering.pricing.models import CARD_TYPE_CHOICES, PRICING_MODEL_CHOICES
    valid_types = {c[0] for c in CARD_TYPE_CHOICES}
    valid_models = {c[0] for c in PRICING_MODEL_CHOICES}
    if payload.card_type not in valid_types:
        return 422, {"error": f"card_type must be one of {sorted(valid_types)}"}
    if payload.pricing_model not in valid_models:
        return 422, {"error": f"pricing_model must be one of {sorted(valid_models)}"}
```
(Add `422: dict` to the endpoint's `response=` map. Match the existing return-shape style of the file.)
- [ ] **Step 3b — Surface uncosted metrics.** In `RecordUsageResponse` (api/v1/schemas.py) add `uncosted_metrics: list[str] = []`. In the record-usage endpoint, after `record_usage(...)` returns, populate it from the event's provenance: read `result`/the event's `pricing_provenance.get("uncosted_metrics", [])` and include it in the response dict. (Read how the endpoint builds `RecordUsageResponse` today and add the field; `pricing_provenance` is on the `UsageEvent` and in the `_result` dict from `usage_service.py:39-46`.)
- [ ] **Step 4 — Verify:** `$DJ -m pytest api/v1/tests/test_metering_endpoints.py apps/metering -q` → green. **Commit:** `feat(pricing): validate rate-card enums + surface uncosted_metrics in record-usage response`.

---

### Task 3: SDK `record_usage` can send `usage_metrics` + omit cost; rate-card URLs fixed; analytics wrapper

**Files:** Modify `ubb-sdk/ubb/metering.py`; Test `ubb-sdk/tests/test_metering_client.py`.

- [ ] **Step 1 — Failing tests** (`ubb-sdk/tests/test_metering_client.py`, mock the httpx client per the file's existing pattern): (a) `create_rate_card(card_type="cost", metric_name="input_tokens")` POSTs to **`/api/v1/metering/pricing/rate-cards`** (today it's `/api/v1/pricing/rate-cards`); same for `list_rate_cards` (GET) + `delete_rate_card`. (b) `record_usage(customer_id="c", request_id="r", idempotency_key="i", usage_metrics={"input_tokens": 1000})` with NO `provider_cost_micros` succeeds and the POST body contains `usage_metrics={"input_tokens":1000}` and does NOT require/contain `provider_cost_micros`. (c) `usage_analytics(customer_id="c", tag_key="agent")` GETs `/api/v1/metering/analytics/usage` with those params. (There is an existing test asserting `usage_metrics` is ABSENT from the record_usage body — find it and flip it.)
- [ ] **Step 2 — Run** → FAIL.
- [ ] **Step 3 — Implement** in `ubb-sdk/ubb/metering.py`:
  - `record_usage`: change `provider_cost_micros: int` → `provider_cost_micros: int | None = None`; add `usage_metrics: dict | None = None` to the signature. Build the body WITHOUT unconditionally setting `provider_cost_micros`; instead:
```python
        body: dict = {
            "customer_id": customer_id, "request_id": request_id,
            "idempotency_key": idempotency_key, "metadata": metadata or {},
        }
        if provider_cost_micros is not None:
            body["provider_cost_micros"] = provider_cost_micros
        if usage_metrics is not None:
            body["usage_metrics"] = usage_metrics
```
(keep the existing `if billed_cost_micros is not None: ...` etc. blocks unchanged.)
  - `create_rate_card` / `list_rate_cards` / `delete_rate_card`: change the three paths from `/api/v1/pricing/rate-cards...` to **`/api/v1/metering/pricing/rate-cards...`**.
  - Add a `usage_analytics` method:
```python
    def usage_analytics(self, *, start_date=None, end_date=None, customer_id=None, tag_key=None):
        """Cost + margin analytics with customer/product/tag breakdowns via
        GET /api/v1/metering/analytics/usage."""
        params = {k: v for k, v in {
            "start_date": start_date, "end_date": end_date,
            "customer_id": customer_id, "tag_key": tag_key}.items() if v}
        r = self._request("get", "/api/v1/metering/analytics/usage", params=params)
        return r.json()
```
- [ ] **Step 4 — Verify (from `ubb-sdk/`, unset DJANGO_SETTINGS_MODULE):** `<venv python> -m pytest -q` → green. **Commit (repo root):** `fix(sdk): correct rate-card URLs + record_usage usage_metrics/optional cost + usage_analytics wrapper`.

---

### Task 4: Remove the dead `get_economics*` SDK methods (they 404)

**Files:** Modify `ubb-sdk/ubb/subscriptions.py` (remove `get_economics`/`get_customer_economics`/`get_economics_summary` ~66-97); Test `ubb-sdk/tests/` (remove/adjust any test referencing them).

- [ ] **Step 1 — Confirm they're dead.** `git grep -n "subscriptions/economics" ../ubb-platform` → no server route. (The live economics surface is `/api/v1/margin/*`, already wrapped by `get_customer_margin` etc.)
- [ ] **Step 2 — Failing/grep check:** `git grep -n "get_economics\|get_customer_economics\|get_economics_summary" ubb-sdk/` to find all references (methods + tests).
- [ ] **Step 3 — Remove** the three methods from `subscriptions.py`. Delete or repoint any test in `ubb-sdk/tests/` that calls them (if a test asserts the old `/subscriptions/economics` path, delete that test — the route is gone; do NOT weaken it to pass).
- [ ] **Step 4 — Verify (from `ubb-sdk/`):** `<venv python> -m pytest -q` → green. **Commit (repo root):** `fix(sdk): remove dead get_economics methods (route removed; use margin API)`.

---

### Task 5: Capstone — Journey-1 happy-path live-server integration test (catches the 404 class for good)

**Files:** Create `api/v1/tests/test_journey1_sdk_integration.py` (platform-side; uses pytest-django `live_server` + the `ubb` SDK).

- [ ] **Step 1 — Ensure the SDK is importable in the platform venv:** `<platform venv python> -c "import ubb"` ; if ImportError, `<platform venv python> -m pip install -e ../ubb-sdk`. (Note this in the report.)
- [ ] **Step 2 — Write the integration test.** Uses the real HTTP stack (so URL routing is exercised — this is what mocked tests missed). Create tenant + API key + customer + a **cost** rate-card and a customer all via the ORM (committed so the live-server thread sees them — `live_server` runs against the test DB), then drive the SDK against `live_server.url`:
```python
import pytest
from apps.platform.tenants.models import Tenant, TenantApiKey
from apps.platform.customers.models import Customer
from apps.metering.pricing.models import RateCard


@pytest.mark.django_db(transaction=True)
def test_journey1_cost_attribution_end_to_end_via_sdk(live_server):
    from ubb.metering import MeteringClient
    tenant = Tenant.objects.create(name="J1", products=["metering"])
    _, raw_key = TenantApiKey.create_key(tenant)
    customer = Customer.objects.create(tenant=tenant, external_id="acme")
    # A cost card: 2 micros per input token (per_unit, unit_quantity=1 token).
    RateCard.objects.create(tenant=tenant, card_type="cost", metric_name="input_tokens",
                            pricing_model="per_unit", rate_per_unit_micros=2, unit_quantity=1,
                            currency="usd")
    client = MeteringClient(api_key=raw_key, base_url=live_server.url)
    try:
        # (a) rate-card create reaches the real route (would 404 before Task 3)
        client.create_rate_card(card_type="cost", metric_name="output_tokens",
                                pricing_model="per_unit", rate_per_unit_micros=5, unit_quantity=1)
        # (b) record usage with usage_metrics and NO caller cost -> engine computes COGS
        res = client.record_usage(customer_id=str(customer.id), request_id="r1",
                                  idempotency_key="i1", product_id="search",
                                  usage_metrics={"input_tokens": 1000})
        # 1000 tokens * 2 micros = 2000 micros COGS, computed server-side from the cost card
        assert res.provider_cost_micros == 2000
        # (c) analytics returns per-customer + per-product PROVIDER cost (COGS)
        rep = client.usage_analytics(customer_id=str(customer.id))
        assert rep["total_provider_cost_micros"] == 2000
        assert any(row["customer__external_id"] == "acme"
                   and row["total_provider_cost_micros"] == 2000 for row in rep["by_customer"])
        assert any(row["product_id"] == "search"
                   and row["total_provider_cost_micros"] == 2000 for row in rep["by_product"])
    finally:
        client.close()
```
(VERIFY field names against the real `RecordUsageResult` type + the analytics row keys — adapt `res.provider_cost_micros` / `row[...]` to the actual shapes. If `live_server` + cross-package import proves environment-fiddly, fall back to a deterministic CONTRACT test: drive each SDK method through an `httpx.MockTransport` that records the path, and assert `django.urls.resolve(path)` succeeds for each — this still catches the 404 class. Prefer the live_server e2e; report which you shipped.)
- [ ] **Step 3 — Run** → it must FAIL on a checkout of the code BEFORE Tasks 1-3 (404 on rate-cards / no usage_metrics / no provider columns) and PASS now. Run a couple of times to confirm stability.
- [ ] **Step 4 — Verify:** `$DJ -m pytest api/v1/tests/test_journey1_sdk_integration.py -q` → green. **Commit:** `test(journey1): live-server SDK integration proving the cost-attribution path end-to-end`.

---

### Task 6: Honest onboarding — fix `seed_dev_data` + ship an SDK README

**Files:** Modify the management command that prints curl examples (`git grep -ln "seed_dev_data"` → the command under `apps/*/management/commands/seed_dev_data.py`); Create `ubb-sdk/README.md`.

- [ ] **Step 1 — Fix `seed_dev_data`:** find the printed curl/example block (it points at deleted endpoints on the wrong port). Update the URLs to real, current paths (`/api/v1/metering/...`, correct port) OR replace the curl block with the SDK happy-path snippet from the README below. Verify by running the command output mentions only routes that resolve.
- [ ] **Step 2 — Create `ubb-sdk/README.md`** with the Journey-1 happy path (install, construct `MeteringClient`, `create_rate_card(card_type="cost", ...)`, `record_usage(..., usage_metrics={...})` without caller cost, `usage_analytics(customer_id=...)` to read per-customer COGS by product/tag). Keep it copy-pasteable + correct against the Task-3 SDK signatures. Mention `uncosted_metrics` in the response as the "did every metric match a cost card?" signal.
- [ ] **Step 3 — Verify:** `$DJ manage.py <seed command> --help` (or a dry run) shows no dead URLs; README paths match the SDK. **Commit:** `docs(sdk): J1 happy-path README + fix seed_dev_data example URLs`.

---

### Task 7: Final verification
- [ ] `$DJ manage.py check`; `$DJ manage.py makemigrations --check --dry-run` → "No changes detected" (Wave 1 adds NO migration).
- [ ] Full platform suite `$DJ -m pytest -q` → green (report count; expect 745 + the new tests).
- [ ] SDK suite from `ubb-sdk/` → green (report count; 152 + new, minus removed dead-method tests).
- [ ] Confirm the capstone integration test (Task 5) passes; clean tree.

---

## Self-Review
**Spec coverage (Wave 1 items):** analytics provider columns (T1) ✓; SDK usage_metrics + optional cost (T3, server already ready) ✓; SDK rate-card URL 404 (T3) ✓; SDK analytics wrapper (T3) ✓; dead get_economics* removed (T4) ✓; rate-card enum validation + loud uncosted_metrics (T2) ✓; honest onboarding seed+README (T6) ✓; live-server integration capstone (T5) ✓.
**Placeholder scan:** every code step has concrete code; T1/T2 schema edits say "read the row schema + add the field" with the exact field/type; T5 gives the full test + a named fallback. No TBD/TODO.
**Type consistency:** `usage_metrics: dict|None` (T3) matches server `Optional[dict[str,int]]`; `total_provider_cost_micros` added in both the query (T1) and row schema (T1); `uncosted_metrics: list[str]` added to `RecordUsageResponse` (T2) and surfaced (T2) + documented (T6); SDK `usage_analytics` (T3) is what the capstone (T5) calls; rate-card URL `/api/v1/metering/pricing/rate-cards` consistent T3↔T5.
**No migration** (T7 guards it).
