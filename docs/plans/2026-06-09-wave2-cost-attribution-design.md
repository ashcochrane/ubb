# Wave 2 — Make Journey-1 Cost Attribution Best-in-Class (Design)

**Date:** 2026-06-09 · **Method:** 8-agent code-grounded design analysis (map the current pricing/dimensions/analytics pipeline → evaluate each Wave-2 item with options + recommendation → competitor bar → synthesis). Goal: J1 cost-attribution genuinely best-in-class (fast/easy/risk-free) for the Type-1 buyer.

## 1. The architectural crux — service/agent modeling

**Recommendation: HYBRID.** Add `service_id` + `agent_id` as **indexed columns** on `UsageEvent` (for attribution + scalable analytics), **derived from tags** (single source of truth — never a separate request field, so they can't drift). Keep cost-card **matching** in the existing `dimensions`-subset-of-`tags` mechanism (frozen — don't touch the high-risk pricing code). Add **opt-in reserved-key value validation** to close the silent-$0 hole.

**Why not "make everything first-class":** matching already handles service/agent — a card with `dimensions={"agent":"x"}` already fires on an event with `tags={"agent":"x"}` (`pricing_service.py:15-20`). The real defects are two *separate* things: (i) the axes are unindexed JSONB, so analytics aggregate them in app memory (doesn't scale) → fixed by **columns**; (ii) a tag-value typo silently misses the dimension and prices to **$0** → fixed by **validation**. Promoting columns into the matcher fixes neither and *adds* risk (drop/recreate the `RateCard` partial-unique constraints, hard-code exactly two axes, run three matching mechanisms where one suffices).

**Consequences:** one additive migration (`UsageEvent.service_id`, `agent_id` `CharField(100, blank, db_index)` + composite `Index(['tenant','product_id','service_id','agent_id','-effective_at'])`); `RateCard` untouched; columns write-once (immutability-safe); `record_usage` derives `service_id=tags.get("service","")`, `agent_id=tags.get("agent","")`, and `product_id ← tags.get("product")` when the request's `product_id` is empty (unifies product/service/agent under one reserved-key model). **SDK `record_usage` signature is unchanged** — service/agent still arrive as tags → zero wire break. `RESERVED_DIM_KEYS = {"product","service","agent"}`.

**Silent-$0 fix:** tenant flag `validate_reserved_dimensions` (sibling of `require_cost_card_coverage`) + an opt-in `ReservedDimensionValue(tenant,key,value)` registry; when ON, an event whose reserved value isn't registered returns **422** instead of pricing to $0. Also **extend the coverage check to the caller-cost path** (today `caller_provider_cost` bypasses all validation — `pricing_service.py:45-47`).

**Honest caveat:** Metronome/Orb/m3ter declare dimensions as typed schema objects → typo-proof *by construction*. The hybrid is operationally equivalent **only if the tenant turns validation on**; with the default fail-open posture a typo still silently zeroes. That's a deliberate back-compat trade (see Decision 1), not an oversight.

## 2. The Wave-2 design, item by item

**2a. Multi-key breakdown in one call (S).** Extend the existing `GET /api/v1/metering/analytics/usage` (no new route) with `dimensions: list[str]` from `{provider, event_type, product_id, customer, service_id, agent_id, tag:<key>}` (cap 6, 422 on unknown/over-cap). Each runs the existing `.values(col).annotate(Sum(provider), Sum(billed), Count)`; for `tag:<key>` replace the in-memory `defaultdict` with `KeyTextTransform` → pushes tag aggregation into Postgres. Additive response `breakdowns: dict[str, list[row]]`. SDK: `usage_analytics(..., dimensions=[...])`. **This is parallel single-dimension breakdowns, not a cross-product cube** (the cube — one row per `(product×service×agent)` tuple — is the strictly-richer Wave-3 follow-on needing pagination + a GIN index).

**2b. Time-series spend rollup (M).** New `GET /api/v1/metering/analytics/usage/timeseries` — on-the-fly `TruncHour`/`TruncDate` over `UsageEvent` (no new table; mirrors `get_revenue_analytics` at `queries.py:101-107`). Params: `granularity` (hour|day), `start_date`/`end_date` (default 30d), `customer_id` (UUID PK), `group_by` (one dim, mutually exclusive with `tag_key`), `tag_key`, `tz` (IANA, validated), `fill_gaps`. Rides existing `(tenant,-effective_at)`/`(customer,-effective_at)` indexes → zero hot-path migration. Guardrail: cap hourly windows (~92d). SDK: `usage_timeseries(...)`. Optionally surface `uncosted_event_count` per bucket so a missing-cost-card hole shows up instead of a misleadingly clean COGS line.

**2c. Bulk create + SDK update + readable history (M).** Add a stable lineage handle `RateCard.lineage_id = UUIDField(default=uuid4, db_index)` (additive migration + backfill grouping existing rows on the natural key). `POST /pricing/rate-cards/batch` (`cards: list[RateCardIn]`, 1–100, atomic, all-or-nothing). Make `PUT /pricing/rate-cards/{id}` lineage-aware (copy `lineage_id` to the new version, stamp `old.valid_to` before create in one atomic block). `GET /rate-cards?include_history&as_of=` + `GET /rate-cards/{lineage_id}/history` (newest-first). SDK: `update_rate_card`, `bulk_create_rate_cards`, `list_rate_cards(include_history, as_of)`, `get_rate_card_history(lineage_id)`; add `lineage_id` to the `RateCard` dataclass + `RateCardOut`. Footgun documented: update returns a *new* id; the stable handle is `lineage_id`.

## 3. Dashboard — DEFER

UBB is deliberately headless (`TEMPLATES.DIRS=[]`, no SPA, no browser session/CSRF auth, Bearer-only). A "thin dashboard" isn't thin — it bootstraps templates, a static pipeline, a new browser-auth model, and XSS-escaping of tenant tag values; it would consume the Wave-2 budget and leave the real J1 gaps (multi-dim, time-series) unaddressed. **Ship the analytics API/SDK; treat any UI as a separate effort** with its own auth/frontend design. Interim operator view at ~zero engineering cost: **Metabase/Superset embed over the platform DB.** Honest competitive cost: this is where UBB most visibly trails Amberflo (React UI Kit) / Metronome (signed-iframe embeds) on demo optics.

## 4. Competitiveness check (after Wave 2)

| Bar item | After Wave 2 | Notes |
|---|---|---|
| First-class dims, no silent-$0 | **Partial** | indexed columns; validation **opt-in** (default fail-open still allows typo→$0) |
| Cost-card matching uses declared dims | **Gap** | `product_id`-not-in-matching (claim b) NOT fixed by these items — per-product *pricing* still tag-encoded (Decision 2) |
| Multi-dimension in one call | **Met (parallel) / Partial (cube)** | the compound cube is Wave-3 unless promoted |
| Time-series, daily/hourly | **Met** | at/above Orb parity |
| Soft-versioned card history via SDK | **Met / leads** | `lineage_id` + point-in-time `as_of` is genuinely strong |
| Operator dashboard / customer embed | **Deferred** | met only via BI-embed; trails on optics |
| Spend alerts in the event path | **Not in scope** | leaders all have it |

**Verdict: best-in-class on the data/API axis, still trailing on UI/last-mile.** For a buyer who values data ownership + cost + auditability over a polished embed, items 1–5 are enough to win the Type-1 wedge.

## 5. Open owner decisions
1. **[LEAD] Validation posture — fail-open vs fail-closed by default.** Fail-open (opt-in strict, loud surfacing) = back-compat + zero onboarding friction but keeps silent-$0 on by default; fail-closed = typo-proof like Metronome but forces every tenant to pre-register their taxonomy. *Lean: fail-open + loud.*
2. **[high stakes] Fix `product_id`-not-in-matching in Wave 2?** Behavior-changing (gated behind a flag). Matters for per-product *pricing*; J1 cost *attribution* breakdowns are already correct without it. *Lean: defer (revisit when a tenant needs per-product rates).*
3. **[scope] Multi-dimension CUBE in Wave 2 or Wave 3?** Parallel (S) ships now + satisfies the literal item; the cube is L. *Lean: parallel now, cube → Wave 3 unless the headline demo is a pivot table.*
4. **[optics] Dashboard required in Wave 2?** *Lean: defer; Metabase-embed interim; UI is a separate effort.*

## 6. Build sequence + capstone
1. service/agent columns + composite index + derivation + response echo (S–M). 2. reserved-key validation + caller-cost-path coverage (S). 3. multi-key breakdown + `KeyTextTransform` (S). 4. time-series endpoint (M). 5. `lineage_id` + bulk/update/history + SDK (M). 6. *(owner-gated)* product_id-in-matching behind a flag (M, last).

**Capstone (proves J1 best-in-class via the SDK alone):** one SDK script — bulk-create two cost cards differing by a `service` dimension; record ~50 events across 2 customers × 2 products × 2 services × 2 agents over 3 days (some with a mis-typed `agent`); `usage_analytics(dimensions=[product_id,service_id,agent_id,provider])` and assert the four breakdowns sum to the same COGS and the typo'd agent surfaces as its own row; `usage_timeseries(granularity=day, group_by=service_id)` and assert 3 day-buckets reconcile to the breakdown totals; `update_rate_card` + `get_rate_card_history(lineage_id)` and assert two non-overlapping versions + an `as_of` before the change returns the old rate; with `validate_reserved_dimensions` ON, assert the mis-typed event is rejected 422 (the silent-$0 footgun closed). Passes with no raw SQL and no client-side joins.
