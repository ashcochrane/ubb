> ⚠️ SUPERSEDED (pricing-engine removal only): the decision to decommission the dimensional rate-card pricing engine was REVERSED. `ProviderRate` was deleted but a redesigned two-card cost+price engine (`RateCard` + `PricingService`) was REINSTATED and is now central — see `2026-06-08-pricing-stageA-rate-card-engine-design.md`. The `Tenant.billing_mode` introduction + boundary-cleanup parts remain current. Master truth: `2026-06-10-program-current-state.md`.

# Stage 0 — Reposition & Boundary Cleanup (Detailed Design)

**Date:** 2026-06-05
**Status:** Draft for review
**Parent:** `2026-06-05-ubb-repositioning-design.md`
**Depends on:** nothing. **Blocks:** Stage 1.

## Objective

Establish the new positioning on a clean base **without** rewriting the metering record contract (Stage 1) or the billing layer (Stage 3). Stage 0 is *positioning + subtraction only* — it removes what we have decided not to build (the dimensional pricing engine), introduces the `billing_mode` vocabulary, and marks the billing-overlap apps for their later reframe. After Stage 0 the test suite is green and the system runs; some markup config is temporarily inert until Stage 1 wires it.

## Scope

**In scope**
1. Add `Tenant.billing_mode`.
2. Decommission the dimensional rate-card pricing engine (`ProviderRate`, `PricingService.price_event`, the `usage_metrics` intake mode, `/pricing/rates` CRUD).
3. Reposition docs/README; add deprecation/repositioning notes to billing-overlap modules.
4. Confirm and document that `subscriptions` is retained (read-only revenue mirror for Stage 2).

**Explicitly out of scope (deferred)**
- New `record_usage` contract (`provider_cost_micros`, `units`, `currency`, `tags`) → **Stage 1**.
- Slim markup model rework + application (`TenantMarkup` → per-tenant/per-customer) → **Stage 1**.
- Removing `cost_micros`, hardening `UsageEvent` → **Stage 1**.
- Reframing `wallets`/`topups`, deleting `invoicing`/`ReceiptService` → **Stage 3** (entangled with the billing rewrite; doing it here would mean editing code Stage 3 rewrites).

### Correction to the program-level doc
The program doc listed "delete subscription lifecycle/sync CRUD" and "delete native invoicing" under Stage 0. Reading the code:
- **`subscriptions` has no lifecycle management** — it is already a read-only Stripe mirror (`StripeSubscription`, `SubscriptionInvoice.amount_paid_micros`) plus `economics/`. It is exactly the revenue ingestion Stage 2 needs. **Retained, not deleted.**
- **`invoicing` is entangled with the top-up/webhook flow** (`ReceiptService`, `handle_invoice_paid`, `me /invoices`, `lock_invoice`) — all of which Stage 3 rewrites. Its deletion **moves to Stage 3**.

## Design

### 1. `Tenant.billing_mode`

New field on `apps/platform/tenants/models.py:Tenant`:

```python
BILLING_MODE_CHOICES = [
    ("meter_only", "Meter only"),   # heyotis: track usage, no money, no gate
    ("prepaid", "Prepaid credits"), # localscouta: credit ledger + real-time gate
    ("postpaid", "Postpaid"),       # future: period-close Stripe invoice push
]
billing_mode = models.CharField(max_length=20, choices=BILLING_MODE_CHOICES, default="meter_only", db_index=True)
```

**Validation** (extend `Tenant.clean()`): `meter_only` requires `products == {"metering"}`-compatible (no `"billing"`); `prepaid`/`postpaid` require `"billing"` in `products`. This keeps `products` and `billing_mode` consistent.

**Migration:** add field (default `meter_only`) + data migration to backfill existing tenants: `prepaid` if `"billing" in products` else `meter_only`. Pre-production, so few/no rows.

**Why now (not Stage 3):** it is foundational vocabulary referenced by the gate and handlers later; harmless to introduce early; lets Stage 1 record-path and Stage 2 margin reason about mode. Behaviour is not yet branched on it in Stage 0.

### 2. Decommission the dimensional pricing engine

**Rationale:** the engine exists only to *compute* provider cost from `usage_metrics × ProviderRate` rate-cards. The new model has the caller pass `provider_cost_micros` directly (Stage 1). Dimensional rate-cards, tiered/graduated pricing, and rate versioning are exactly what the brief says to leave to Stripe/Metronome. Remove the whole engine; keep only a markup concept (reworked in Stage 1).

**Delete:**
- `apps/metering/pricing/models.py` → remove `ProviderRate` (keep `TenantMarkup` for now; Stage 1 reworks it). Add a migration that drops the `ubb_provider_rate` table.
- `apps/metering/pricing/services/pricing_service.py` → delete entirely (`price_event`, `_find_rate`, `_dimensions_match`, `_find_markup`, `validate_usage_metrics`, `PricingError`). Stage 1 introduces a small `MarkupService` in its place.
- `apps/metering/pricing/admin.py` → drop `ProviderRate` registration.
- `apps/metering/pricing/tests/test_pricing_service.py` → delete. `test_models.py` → drop `ProviderRate` tests, keep `TenantMarkup` model tests.
- Verify and remove any duplicate `pricing_service` module under `apps/metering/usage/services/` if present (flagged by blast-radius scan; confirm at implementation).

**`record_usage` intake (interim):** remove the `usage_metrics`/`properties` metrics-pricing branch from `apps/metering/usage/services/usage_service.py` (lines 72–88) and the `PricingService` import. After Stage 0, `record_usage` accepts caller-provided `cost_micros` only. (Stage 1 replaces this with the `provider_cost_micros` contract.) `usage_metrics`/`properties` columns remain on `UsageEvent` for now; Stage 1 decides their fate.

**API surface:**
- `api/v1/metering_endpoints.py` → delete `/pricing/rates` GET/POST/PUT/DELETE (`list_rates`, `create_rate`, `update_rate`, `delete_rate`, `_rate_to_out`). Keep `/pricing/markups` endpoints **as-is for now** (they operate on `TenantMarkup`, reworked in Stage 1). Remove the `PricingError` import + `except PricingError` arm in `record_usage`.
- `api/v1/schemas.py` → delete `ProviderRateIn`, `ProviderRateOut`. Update `RecordUsageRequest`: remove `usage_metrics`, `properties`, the `usage_metrics` validator, and rewrite `validate_intake_mode` so `cost_micros` is simply required (no dual-mode). `event_type`/`provider` remain (they're descriptive dimensions, not pricing inputs).

**Tests to update:** `apps/metering/usage/tests/test_usage_service.py` and `api/v1/tests/test_metering_endpoints.py` — drop the metric-pricing test cases and `ProviderRate`/`TenantMarkup`-driven pricing assertions; keep caller-cost cases. (Stage 1 adds the new contract's tests.)

### 3. Documentation & deprecation markers

- Rewrite `README.md` and add a short `docs/architecture/positioning.md` capturing the UBB/Stripe boundary and three tenant modes (from the program doc).
- Add module-level docstring notes to `apps/billing/wallets/`, `apps/billing/topups/`, `apps/billing/invoicing/` stating their Stage-3 disposition (reframe / delete), so no one extends them in the interim.
- Note in `apps/subscriptions/` that it is the retained read-only revenue source for margin (Stage 2).

## Migrations summary
1. `tenants`: add `billing_mode` + data backfill.
2. `pricing`: drop `ProviderRate` (`ubb_provider_rate` table). `TenantMarkup` untouched.

## Blast radius handled (from scan)
- `ProviderRate`: 10 imports / 16 usages / migrations — all in pricing app, metering_endpoints, and tests. All addressed by the deletions above.
- `PricingService`/`price_event`/`PricingError`: usage_service, metering_endpoints, pricing tests — all addressed.
- `usage_metrics`/`properties`: schema, usage_service, pricing_service, tests — addressed.
- `subscriptions` cross-app refs: only `config/urls.py` — untouched (retained).
- `billing_mode`: confirmed absent — safe to introduce.

## Risks
- **Inert markup between Stage 0 and Stage 1.** `TenantMarkup` + `/pricing/markups` exist but nothing applies them until Stage 1. Acceptable (pre-production); documented.
- **`usage_metrics` columns linger** on `UsageEvent` until Stage 1. Harmless; avoids a throwaway migration.

## Acceptance criteria
- `python manage.py makemigrations --check` clean; migrations apply on a fresh DB.
- Full test suite green (with pricing-engine tests removed/rewritten).
- No remaining import of `ProviderRate`, `PricingService`, `price_event`, or `usage_metrics` intake anywhere.
- `Tenant.billing_mode` present, validated against `products`, backfilled.
- `record_usage` works with caller-provided `cost_micros`; `/pricing/rates` gone; `/pricing/markups` still responds.
