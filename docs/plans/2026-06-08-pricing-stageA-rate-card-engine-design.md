# Pricing Program — Stage A: Rate-Card Pricing Engine (Detailed Design)

**Date:** 2026-06-08
**Status:** Approved (approach) — pending written-spec review
**Program:** Pricing Cards + Billing Integrity (Stages A–D)
**Depends on:** Stage 1 metering core (UsageEvent ledger), the slim `TenantMarkup` (commit `e0c8972`). **Reinstates** the dimensional pricing engine deleted in `7206dc4` / `ca5fa2c` / `29e8449`, redesigned.

## Program context (the orchestration)

The user has decided to reinstate a full rate-card / pricing-card architecture (deliberately removed in the Stage-0 repositioning), with flexibility to evolve. This is **Stage A** of a 4-stage program:

- **A — Rate-Card Pricing Engine** *(this doc)*: cost + price cards, multi-metric intake, `PricingService`, integration at the single `record_usage` choke point, provenance, CRUD + SDK.
- **B — Revenue-Source Disambiguation**: per-customer `revenue_source` selector so price-card billing + manual revenue + Stripe never double-count in the margin engine.
- **C — Money-Safety Hardening** (audit gap): `payment_intent.succeeded` backstop, reconcile-direction fix + repair, auto-top-up credit idempotency key, double-charge window.
- **D — Overage Policy + Wallet↔Ledger Reconciliation** (audit gaps): explicit bounded overage policy; reconcile the wallet against the durable `UsageEvent` ledger *with repair*; proactive before-depletion top-up.

B/C/D each get their own design+plan when reached. A is the keystone and is fully specified here.

## Objective

Let UBB **identify the cost of a unit of usage from tenant-defined rate cards** (e.g. "1,500 input tokens of gpt-4 → $X"), and optionally **derive the end-customer price** from rate cards — serving two personas:
- **Metering-only**: compute COST from a cost card (or keep sending exact cost); revenue stays manual (`CustomerRevenueProfile`); get margin visibility.
- **Integrated-billing**: compute COST from a cost card, then PRICE the end-customer via a price card (possibly on *different units* than cost) or a flat markup, then bill via prepaid drawdown (Stage 3) or postpaid Stripe push (Stage 4).

The reinstatement is **additive and backward-compatible**: with zero rate cards configured, `record_usage` behaves byte-for-byte as today (caller-provided `provider_cost_micros` + slim markup).

## The model: two card types, one resolution ladder

Cost and price are different functions (integrated-billing customers charge on different units than they cost — per-seat/per-message/flat vs per-token), so there are two **optional** card types, both resolving to the existing `UsageEvent.provider_cost_micros` / `billed_cost_micros` **before the event is written**.

```
COST  (provider_cost_micros):
    explicit caller provider_cost_micros          # trust the post-call exact COGS
  → else  CostCard.compute(usage_metrics, tags)   # caller sent units, not dollars
  → else  0                                        # free provider

PRICE (billed_cost_micros = revenue):
    explicit caller billed_cost_micros            # caller override
  → else  PriceCard.compute(usage_metrics, tags)  # charge on any units (seats/messages/flat)
  → else  MarkupService.apply(provider_cost)       # degenerate price card: cost × (1+m) + fixed
  → else  billed = provider_cost                   # meter-only, nothing configured

Card matching within a type:  per-customer card → tenant-default card → none
                              (same precedence as the existing MarkupService.resolve)
```

Markup is **kept** as the zero-config default price model (a tenant wanting "cost × 1.2" never authors a card). A price card is the override for different-units / non-linear pricing.

## 1. Data model — `RateCard`

New model in `apps/metering/pricing/models.py`, beside `TenantMarkup`. Reinstates the deleted `ProviderRate`'s proven bones + extension headroom.

| Field | Type | Notes |
|---|---|---|
| `tenant` | FK(tenants.Tenant, CASCADE) | |
| `customer` | FK(customers.Customer, CASCADE, **null=True**) | null = tenant-default; set = per-customer override |
| `card_type` | CharField(choices=`cost`\|`price`, db_index) | the discriminator |
| `provider` | CharField(100, blank, db_index) | matcher |
| `event_type` | CharField(100, blank, db_index) | matcher |
| `metric_name` | CharField(100) | which `usage_metrics` key this card prices (e.g. `input_tokens`, `seats`) |
| `dimensions` | JSONField(default=dict) | matched against event `tags`, subset / most-specific-wins; `{}` = wildcard fallback |
| `dimensions_hash` | CharField(64, db_index) | sha256 of canonical-sorted `dimensions` (computed in `save()`) — the slice key |
| `pricing_model` | CharField(choices=`per_unit`\|`flat`, default `per_unit`) | **enum-extensible** to tiered/volume/package with no migration |
| `rate_per_unit_micros` | BigIntegerField(default=0) | per-unit rate |
| `unit_quantity` | BigIntegerField(default=1_000_000) | divisor (price quoted per N units; matches token pricing) |
| `fixed_micros` | BigIntegerField(default=0) | flat / per-call component; `flat` model = rate 0 + fixed |
| `tiers` | JSONField(default=list) | **headroom**, unused at v1 |
| `currency` | CharField(3, default from tenant) | one currency per row; must equal event currency (no FX) |
| `product_id` | CharField(blank) | optional SKU alignment with `UsageEvent.product_id` |
| `valid_from` | DateTimeField(auto_now_add, db_index) | |
| `valid_to` | DateTimeField(null=True) | soft-versioning |

- **Compute** (`per_unit`): `(units * rate_per_unit_micros + unit_quantity // 2) // unit_quantity + fixed_micros` — restore the deleted round-half-up integer math verbatim. (`flat`: `rate_per_unit_micros = 0`, so just `fixed_micros`.)
- **Partial unique:** `(tenant, customer, card_type, provider, event_type, metric_name, dimensions_hash, currency) WHERE valid_to IS NULL` → exactly one **active** card per slice.
- **Versioning:** re-pricing closes the current row (`valid_to=now`) and inserts a new one. History is immutable; because analytics re-derive from the immutable `UsageEvent` ledger with stamped provenance, forward re-pricing never corrupts past numbers.

`db_table = "ubb_rate_card"`.

## 2. Intake — dual-mode `RecordUsageRequest`

- **Mode 1 (caller-cost, today):** `provider_cost_micros` — relaxed from **required → optional** (`api/v1/schemas.py:29`). `billed_cost_micros` stays an optional override.
- **Mode 2 (platform-prices, reinstated):** `usage_metrics: dict[str,int]` (e.g. `{"input_tokens":1500,"output_tokens":300,"seats":3}`), with `event_type` + `provider` required for card matching, and `tags` carrying the dimensions (e.g. `{"model":"gpt-4"}`). Values validated non-negative int (bool rejected), as the deleted engine did.
- `usage_metrics` is **persisted on `UsageEvent`** (new additive `usage_metrics` JSONField, default `{}`) for queryable re-pricing/audit. Dimensions reuse the existing GIN-indexed `tags`.

## 3. `PricingService.price(...)`

New `apps/metering/pricing/services/pricing_service.py`. Signature roughly `price(tenant, customer, event_type, provider, usage_metrics, tags, currency, caller_provider_cost, caller_billed, as_of=now) -> (provider_cost_micros, billed_cost_micros, provenance)`. Implements the ladder:
- **COST:** `caller_provider_cost` if not None; else for each `metric_name` in `usage_metrics`, resolve the most-specific active **cost** card (validity window + currency match + most-specific dimensions, with `{}` wildcard fallback) and sum `card.compute(units)`. A metric with **no** matching cost card contributes **0** to cost (not an error) — `usage_metrics` legitimately mixes cost-driving metrics like `input_tokens` with price-only metrics like `seats`. If no metric has a cost card and no caller cost was given → cost 0.
- **PRICE:** `caller_billed` if not None; else if **any** price card matches a metric, `billed = Σ price_card.compute(units)` over the metrics that have a matching price card (a metric with no price card contributes 0 to price — this is how "charge only on seats, not tokens" works); else `MarkupService.apply(provider_cost)`; else `provider_cost`.
- **Coverage visibility, not silent under-bill:** the provenance records exactly which metrics were priced by which card, so an *unintended* missing card (e.g. a forgotten gpt-4 cost card → cost 0 → 100%-margin illusion) is visible in provenance + analytics. A **per-tenant strict mode** (`require_cost_card_coverage`, default **off**) raises `PricingError` → 422 when a Mode-2 event has a metric with no cost card, for tenants who want loud failure. Default is permissive (0 contribution) because the mixed-metric model makes blanket fail-closed wrong.
- **Provenance:** build `{engine_version, metrics:[{metric, units, rate_card_id, valid_from, pricing_model, unit_price, computed_micros}], markup, provider_cost_micros, billed_cost_micros}`.
- Card resolution reuses the deleted `_dimensions_match` (subset; rate's dims must all be present-and-equal in event tags) + sort by `(len(dimensions), valid_from)` desc.

## 4. Integration — the single choke point

Insert `PricingService.price(...)` into `UsageService.record_usage` **immediately before** the existing `MarkupService.apply` call (`apps/metering/usage/services/usage_service.py:60-62`). This is the sole writer of `UsageEvent` and sole producer of `UsageRecorded`, so it is the only place that keeps every downstream consumer consistent.

**Hard invariants preserved by construction** (resolution happens *before* the event is written):
- `UsageRecorded.cost_micros == billed_cost_micros` (revenue) — unchanged producer (`usage_service.py:81-85`).
- `provider_cost_micros` is always a concrete integer (default 0, never None) — analytics distinguish None vs 0.
- `billed` still drives wallet drawdown (`handlers.py` `payload['cost_micros']`), budget caps (`budget_service`), run hard-stop (`runs/services`), postpaid Stripe lines (`postpaid_service.aggregate_lines`).
- `provider` still drives margin/economics (`MarginService`), the cost accumulator (`subscriptions/handlers`), and the provider-cost-spike webhook.

**No event-schema change, no billing-handler change, no UsageEvent cost-column migration.** Run accumulation and idempotency stay intact because computation is inside `record_usage`, not the endpoint or a handler.

## 5. Provenance + exposure

Write the provenance into the already-present-but-dormant `UsageEvent.pricing_provenance` JSON (`models.py:27`, currently always `{}`), and **expose** it in the usage `_result`/response and in a usage-event detail/analytics view so tenants can audit "which card priced this" and so the Stage-2 provider-cost-spike signal is explainable.

## 6. Authoring — CRUD + SDK

Reinstate soft-versioned CRUD `/api/v1/pricing/rate-cards` on `metering_api`:
- `GET` (active cards, filterable by `card_type`), `POST` (create), `PUT/{id}` (soft-version: close old + create new), `DELETE/{id}` (soft-expire `valid_to=now`).
- **Gating:** cost cards require `metering` (both personas); price cards require `billing` (integrated only).
- SDK: `create_rate_card`, `list_rate_cards`, `update_rate_card`, `delete_rate_card`, types.

## 7. Deferred (enum/sidecar-compatible — not rewrites)

Tiered/graduated/volume/package calculators (schema headroom via `pricing_model` + `tiers` is in place now), percentage pricing, minimums/commitments/discounts, cross-currency FX. Each is later a new enum value, a nullable column, or a sibling table.

## Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Card types | **Two** (`cost`, `price`) in one `RateCard` table via `card_type` | Integrated-billing prices on different units than cost; one table avoids duplicated matcher/versioning logic |
| 2 | Markup vs price card | **Markup kept as the zero-config default**; price card is the override | "cost × 1.2" tenants never author a card |
| 3 | Caller-cost vs cost card | **Caller `provider_cost_micros` wins** (highest precedence) | Trust the exact post-call COGS; card is the alternative for unit-only callers |
| 4 | Pricing-model richness | **`per_unit` + `flat` now**; enum + `tiers` JSON headroom | User: "per-unit now, built to extend" |
| 5 | Missing card for a metric | **Permissive: 0 contribution** (mixed cost/price metrics); **opt-in strict mode** raises 422 | Blanket fail-closed wrongly rejects "charge per-seat, no cost card on seats"; provenance makes uncosted metrics visible |
| 6 | Currency | **One per row, must equal event currency; no FX** | Stripe owns money movement |
| 7 | Versioning | **`valid_from`/`valid_to` + one-active-row** | Immutable history; analytics re-derive from the stamped ledger |
| 8 | Integration point | **Inside `record_usage`, before markup** | Sole writer/producer; preserves all downstream contracts |
| 9 | Multi-unit / different-units | **`usage_metrics` dict; card declares its `metric_name`** | "cost per-token, charge per-seat" in one event |
| 10 | Gating | **cost→metering, price→billing** | Matches the product-access model |

## Risks & mitigations

- **Cost-contract regression** (the repositioning's hardest-won invariant). Mitigated: resolution is upstream of event creation; cost-contract tests assert drawdown/margin/postpaid see the right numbers; a no-cards backward-compat test proves identical behavior.
- **Silent under-billing via a forgotten cost card** (permissive default → cost 0). Mitigated: provenance + analytics surface uncosted metrics; the opt-in `require_cost_card_coverage` strict mode gives loud failure for tenants who want it.
- **Dimension-match performance** (O(n) Python-side after DB filter). Acceptable at expected card cardinality; `dimensions_hash` enables an exact-match fast path; noted for later optimization.
- **Re-pricing of open postpaid periods.** Events are immutable and stamped at write time → frozen `billed`; a rate change applies forward only. Explicit, not accidental.

## Acceptance criteria

- A tenant authors a cost card (gpt-4 `input_tokens` @ rate); a caller sends `usage_metrics={"input_tokens":1500}` + `tags={"model":"gpt-4"}` with **no** `provider_cost_micros` → UBB computes `provider_cost_micros` correctly (round-half-up), applies markup → `billed`, stamps provenance.
- A price card on `seats` charges per-seat independent of token cost; `billed` reflects the price card, `provider_cost` the cost card.
- Caller-supplied `provider_cost_micros` still wins over a cost card; caller `billed_cost_micros` still wins over a price card.
- Most-specific-wins + wildcard-fallback + validity-window + per-customer-override all resolve correctly.
- A tenant with **no** rate cards prices identically to today (backward-compat).
- Downstream invariants hold: `UsageRecorded.cost_micros == billed`; drawdown, budget, margin, and postpaid all consume the right figures.
- A Mode-2 call naming a metric with no cost card → cost 0 for that metric by default (provenance flags it uncosted); with `require_cost_card_coverage` on → 422 `PricingError`, no event written.
- CRUD soft-versioning: `PUT` closes the old card and creates a new active one; `DELETE` soft-expires; SDK round-trips.
- Migrations apply on a fresh DB; full platform + SDK suites green.
