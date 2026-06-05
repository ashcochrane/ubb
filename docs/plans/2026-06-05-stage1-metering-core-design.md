# Stage 1 — Metering Core (heyotis) (Detailed Design)

**Date:** 2026-06-05
**Status:** Draft for review
**Parent:** `2026-06-05-ubb-repositioning-design.md`
**Depends on:** Stage 0. **Blocks:** Stage 2.

## Objective

Make `UsageEvent` the **hardened, durable source of truth** for usage, cost, and dimensional attribution, with a clean caller-provided-cost contract and a rich analytics surface. This is the complete metering product for **heyotis**: record usage with provider + billed cost and dimensional tags, query it every way that matters, with exact idempotency. **No money, no gate** in this stage.

## The new `record_usage` contract

Caller passes the **exact provider cost** (known after the AI provider call). UBB derives billed cost via a slim markup unless the caller overrides it. Target SDK call:

```python
ubb.record_usage(
    customer_id="cus_123",
    request_id="req_…",            # caller's trace id
    idempotency_key="…",
    run_id="run_456",               # optional
    units=1,                        # optional scalar quantity
    provider="openai",
    event_type="chat_completion",
    provider_cost_micros=12000,     # exact provider COGS
    billed_cost_micros=30000,       # optional override; else provider × (1+markup)
    currency="usd",                 # optional; defaults to tenant default
    tags={"model": "gpt-4.1", "feature": "property_search", "agent": "research_agent"},
    metadata={...},
)
```

`billed_cost` resolution order: explicit `billed_cost_micros` → else `MarkupService` (per-customer override → tenant default) → else `billed = provider` (meter-only, no markup configured).

## Scope

**In scope**
1. `UsageEvent` schema hardening: collapse cost model, add `currency`, `units`, `product_id`; rename `group_keys`→`tags` and relax limits; drop the now-unused `usage_metrics`/`properties` columns.
2. New `record_usage` service contract + `RecordUsageRequest`/`RecordUsageResponse` schemas.
3. Slim `MarkupService` + reworked `TenantMarkup` (per-tenant default + per-customer override; drop dimensional precedence) + simplified markup CRUD.
4. Cross-product read contract (`queries.py`) and analytics endpoint updated for the new cost model + dimensional grouping.
5. SDK metering client + types.
6. Idempotency preserved and tested.

**Out of scope (deferred)**
- Real-time gate / budget / credit drawdown → **Stage 3** (`record_usage` still emits `UsageRecorded`; the billing handler stays product-gated and dormant for meter-only).
- Full customer P&L margin (subscription + seat revenue) → **Stage 2**. Stage 1 exposes *usage markup margin* only (`billed − provider`).
- Per-run hard-stop evolution to Redis → **Stage 3** (the existing synchronous `RunService.accumulate_cost` path is left intact).

## `UsageEvent` model — target shape

`apps/metering/usage/models.py`:

| Field | Change | Notes |
|---|---|---|
| `provider_cost_micros` | **non-null, default 0** | Caller-provided exact COGS. 0 = free provider. |
| `billed_cost_micros` | **non-null** | Resolved billed amount (override / markup / =provider). Authoritative for revenue + drawdown. |
| `cost_micros` | **removed** | Collapsed into `billed_cost_micros`. See migration + call-site updates below. |
| `tags` | **renamed from `group_keys`**, `JSONField(default=dict)` | Dimensional attribution. |
| `units` | **new**, `BigIntegerField(null=True)` | Optional scalar quantity for analytics/Stripe aggregation. |
| `currency` | **new**, `CharField(3, default="usd")` | Per-event currency; defaults to tenant default. |
| `product_id` | **new**, `CharField(100, blank=True, db_index=True)` | Tenant's own product/SKU identifier (distinct from UBB `products`). |
| `usage_metrics`, `properties` | **removed** | Dead after Stage 0's pricing removal. |
| `event_type`, `provider` | keep (indexed) | Descriptive dimensions. |
| `balance_after_micros` | keep, nullable | Set by billing handler in Stage 3; null for meter-only. |
| `request_id`, `idempotency_key`, `metadata`, `run`, `effective_at` | keep | Idempotency unchanged. |

Immutability (`save`/`delete` guards) retained.

### Tags (was `group_keys`)
- Rename field and its GIN index (migration `0011` created `…group_keys_gin_index` → recreate as `…tags_gin_index`).
- Validation relaxed: key regex stays sane (`^[a-z][a-z0-9_]{1,63}$`), values are strings ≤256 chars, **cap raised 10 → 50**. Rationale: the brief's dimensional analysis (model/feature/agent/region/provider/workflow/…) needs headroom; 10 is too tight.
- Query filter `tags__contains={k: v}` (GIN-backed).

### Indexes (dimensional + period queries)
Keep `(customer, -effective_at)`, `(tenant, -effective_at)`. Add:
- `(tenant, event_type, -effective_at)` and `(tenant, provider, -effective_at)` for provider/event rollups.
- GIN on `tags`.
- Consider `(tenant, product_id, -effective_at)`.

### Cost-model collapse — call sites to update
Removing `cost_micros` touches (from blast-radius scan):
- `apps/metering/queries.py` — `get_period_totals` (`Coalesce("billed_cost_micros","cost_micros")` → `billed_cost_micros`), `get_usage_event_cost` (same), `get_customer_usage_for_period` (drop `cost_micros` key). Also fix `get_customer_usage_for_period` to filter on `effective_at` not `created_at` (current latent bug).
- `api/v1/metering_endpoints.py` — `usage_analytics` Coalesce → `billed_cost_micros`; `get_usage` serializer (`cost_micros` → `billed_cost_micros`).
- `apps/platform/events/schemas.py` — `UsageRecorded.cost_micros` is the drawdown amount consumed by billing (Stage 3). Keep the **schema field** named `cost_micros` = billed amount (avoid churning the event contract), but populate it from `billed_cost_micros`. Document that the event's `cost_micros` == billed.
- `api/v1/schemas.py` — `UsageEventOut.cost_micros` → `billed_cost_micros` (+ add `provider_cost_micros` already present).

## Markup — slim model + service

Rework `apps/metering/pricing/`:
- `TenantMarkup`: **drop** `event_type`, `provider`, and the validity-window precedence machinery. **Add** nullable `customer` FK. Keep `markup_percentage_micros` (1_000_000 = 1%) and `fixed_uplift_micros`. Unique: one active default per tenant (`customer IS NULL`) + one per `(tenant, customer)`.
- New `MarkupService.resolve(tenant, customer) -> (percentage_micros, fixed_uplift_micros)`: customer override → tenant default → `(0, 0)`.
- `MarkupService.apply(provider_cost_micros, tenant, customer) -> billed_cost_micros`: `provider + round_half_up(provider × pct) + fixed`. Reuse the existing round-half-up formula.
- CRUD: replace dimensional markup endpoints with `GET/PUT /pricing/markup` (tenant default) and `GET/PUT /customers/{id}/markup` (override). Simplify `TenantMarkupIn/Out` (no `event_type`/`provider`).

> **Markup placement note:** `pricing` lives under `apps/metering/`. Markup is arguably a billing concern, but it must run inside `record_usage` (metering) to populate `billed_cost_micros` for meter-only tenants too (heyotis wants margin). Keeping a *slim* markup in metering is the pragmatic choice and avoids a cross-product call on the hot path. Revisit if it grows.

## `record_usage` service — new signature

`apps/metering/usage/services/usage_service.py`:
```python
record_usage(tenant, customer, request_id, idempotency_key, *,
             provider_cost_micros, billed_cost_micros=None, units=None,
             provider="", event_type="", currency=None, tags=None,
             metadata=None, run_id=None) -> dict
```
Flow: validate tags → idempotency fast-path → resolve `billed_cost_micros` (override else `MarkupService.apply`) → run hard-stop check (unchanged `RunService.accumulate_cost`, now on `billed_cost`) → create `UsageEvent` (IntegrityError race fallback) → `write_event(UsageRecorded(... cost_micros=billed ...))` → return `{event_id, provider_cost_micros, billed_cost_micros, units, run_id, run_total_cost_micros, hard_stop}`.

`currency` defaults to a new `Tenant.default_currency` (`CharField(3, default="usd")`, added this stage).

## Analytics API (dimensional)

Extend `GET /api/v1/metering/analytics/usage` and add grouping. Deliver the brief's "cost by …" set using only metering data:
- Totals: events, `total_provider_cost_micros`, `total_billed_cost_micros`, `usage_markup_margin_micros` (= billed − provider).
- Breakdowns: `by_provider`, `by_event_type`, `by_customer`, `by_product`, and **`by_tag?key=model`** (group by a chosen tag key, GIN-filtered). Each row: count, provider/billed cost, markup margin.
- Date range + optional `customer_id` filter; reuse cursor pagination patterns where lists are large.

> Full **customer P&L** margin (incl. subscription + seat revenue) is **Stage 2**. Stage 1's "margin" is strictly usage markup (billed − provider), clearly labelled as such.

## SDK changes (`ubb-sdk`)
- `MeteringClient.record_usage(...)`: new kwargs (`provider_cost_micros`, `billed_cost_micros`, `units`, `tags`, `currency`); remove `usage_metrics`/`event_type`-as-pricing. Map `tags` → request `tags`.
- `types.RecordUsageResult`: add `units`, drop pricing-mode fields no longer returned; keep `provider_cost_micros`, `billed_cost_micros`.
- `UBBClient.record_usage(...)`: thread new params.
- Update SDK tests (`test_metering_client.py`, `test_client.py`, `test_orchestration.py`).

## Idempotency
Unchanged and re-asserted by tests: unique `(tenant, customer, idempotency_key)`; fast-path return + `IntegrityError` race fallback. The fast-path/return dicts updated to the new field set.

## Migrations summary
1. `usage`: rename `group_keys`→`tags` (+ GIN index rename); add `units`, `currency`, `product_id`; make `provider_cost_micros`/`billed_cost_micros` non-null (backfill `billed = cost_micros`, `provider = provider_cost_micros or 0`); drop `cost_micros`, `usage_metrics`, `properties`; add new indexes.
2. `pricing`: alter `TenantMarkup` (drop `event_type`/`provider`, add `customer` FK, new constraints).
3. `tenants`: add `default_currency`.

Pre-production ⇒ backfills are trivial; still written for correctness.

## Risks & mitigations
- **Renaming `group_keys`→`tags`** touches the GIN index and the `get_usage` filter params (`group_key`/`group_value` → `tag_key`/`tag_value`) and the `me`/SDK surfaces. Mitigate: single migration + grep sweep (scan already enumerated sites); update SDK in lockstep.
- **Dropping `cost_micros`** could silently break a consumer. Mitigate: the blast-radius list above is the authoritative checklist; add a test asserting `queries.get_period_totals` matches summed `billed_cost_micros`.
- **Markup in metering** may feel misplaced. Accepted trade-off (hot-path, meter-only needs it); documented for revisit.
- **`provider_cost` trust.** UBB stores what the caller sends; it does not verify against providers. This is by design (the brief). Note for tenant docs.

## Acceptance criteria
- `makemigrations --check` clean; migrations apply on a fresh DB and on a DB seeded with Stage-0 data.
- Record usage with `provider_cost_micros` only → `billed = provider × (1+markup)`; with `billed_cost_micros` override → stored verbatim; meter-only tenant with no markup → `billed = provider`.
- Duplicate `idempotency_key` returns the original event, no double-write.
- `tags` accepts ≥10 keys; `tags__contains` filter works via GIN.
- Analytics returns correct totals and every breakdown (provider/event_type/customer/product/tag) with markup margin = billed − provider.
- `queries.py` totals equal summed `billed_cost_micros`.
- SDK `record_usage` round-trips the new contract; SDK tests green.
- No reference to `cost_micros`, `usage_metrics`, `properties`, or `group_keys` remains.
