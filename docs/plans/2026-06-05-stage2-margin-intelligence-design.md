# Stage 2 — Margin Intelligence (Detailed Design)

**Date:** 2026-06-05
**Status:** Draft for review
**Parent:** `2026-06-05-ubb-repositioning-design.md`
**Depends on:** Stage 1 (provider + billed cost on `UsageEvent`, `UsageRecorded` carries both). **Blocks:** Stage 3 (prepaid billing reuses the margin/revenue substrate).

## Objective

Turn the meter into a **margin-control system**. For every customer, compute **gross margin = revenue − provider cost** in real time, attribute it across dimensions, flag unprofitable customers, surface provider-cost/repricing signals, and expose it via a **live query API + webhooks**. Together with Stage 1 this is the complete, shippable **heyotis** product. **No money movement and no spend gate** in this stage (that is Stage 3).

## The core reframe (why this stage exists)

The existing `apps/subscriptions/economics/` computes `margin = subscription_revenue − usage_cost`, where `usage_cost` is the **billed** amount. That mis-models the business twice: it treats usage **billed** (which is *revenue* to the tenant) as a cost, and it ignores **provider cost** (the actual COGS) entirely. Stage 2 adopts the program-level P&L:

```
gross_margin = revenue − provider_cost
             = (manual/stripe subscription revenue + usage_billed) − provider_cost
margin_pct   = gross_margin / revenue            (0 when revenue == 0)
```

`usage_billed = Σ billed_cost_micros`, `provider_cost = Σ provider_cost_micros` over the window — both already on `UsageEvent` after Stage 1. For a pure meter-only tenant with no subscription revenue, margin reduces to `usage_billed − provider_cost` (heyotis's markup over provider cost), which is still meaningful.

## Revenue model — manual first, Stripe optional

Most metering tenants bill their own customers on subscriptions **externally** (processors UBB never sees). So revenue is a **per-customer input**, not assumed from Stripe:

- **Manual (primary).** New `CustomerRevenueProfile` per `(tenant, customer)`: `recurring_amount_micros`, `interval` (`month`), `currency`, `effective_from`, `effective_to` (nullable). The tenant sets "customer X pays me $500/mo" once; the engine attributes the (prorated) amount to each window. Set/read via a **`metering`-gated** endpoint.
- **Stripe (secondary, automated).** The existing `StripeSubscription`/`SubscriptionInvoice` sync, **only** for tenants who run their billing on UBB's Stripe connector. Stays **`subscriptions`-gated**. `SubscriptionInvoice.amount_paid` is already seat-inclusive (it is the real invoice).

Window revenue = `manual_recurring (prorated to window)` + `Σ Stripe invoices paid in window`. For pure heyotis tenants it is just the manual number.

## Product-gating boundary (Stage-2 decision)

Because **Stages 1+2 = the heyotis product** and heyotis is **meter-only**, margin must work with zero subscription data:

| Capability | Gate |
|---|---|
| Margin read API (P&L, by-dimension, unprofitable, trend) | **`metering`** |
| Manual revenue input/read (`CustomerRevenueProfile`) | **`metering`** |
| Margin threshold config | **`metering`** |
| Stripe subscription/invoice **sync** + webhook + raw subscription/invoice reads | **`subscriptions`** |

This moves the current `/economics*` endpoints off the `subscriptions` gate onto `metering`. The margin engine code stays in `apps/subscriptions/economics/` (repositioned, not relocated — avoids churn); gating is independent of code location.

## Compute model — hybrid (live + snapshots)

- **Live (the dashboard feed).** The margin API computes **on demand for any window** (default: current month-to-date; or pass `start_date`/`end_date` for last-7/30-days, etc.) directly from `UsageEvent` aggregates + the window's revenue. Always current; nothing is gated behind a batch run. This is the "margin at any given time" capability.
- **Snapshots (the time dimension).** A periodic task writes per-customer **monthly** `CustomerEconomics` rows under the new P&L. Snapshots exist only for what a single live query cannot do: trend lines, "unprofitable last month" history, and period-over-period detection driving webhooks. They neither gate nor delay the live number.

**Proration:** the monthly snapshot uses the full month's `recurring_amount`. The live month-to-date view prorates revenue by `days_elapsed / days_in_month` so margin% stays comparable to cost-to-date. Proration is calendar-month based and documented as approximate.

## Data-model deltas

`apps/subscriptions/economics/models.py` (+ `apps/subscriptions/models.py`):

| Model | Change |
|---|---|
| `CustomerCostAccumulator` | Replace single `total_cost_micros` with **`total_provider_cost_micros`** and **`total_billed_cost_micros`** (handler increments both via atomic `F()`). Keep `event_count`, the `(tenant, customer, period_start)` unique key. |
| `CustomerEconomics` | Reframe to: `subscription_revenue_micros` (manual+stripe), `usage_billed_micros`, `provider_cost_micros`, `gross_margin_micros` (= subscription_revenue + usage_billed − provider_cost), `margin_percentage`, `is_unprofitable` (bool). Replaces the old `usage_cost_micros`/`subscription_revenue_micros` semantics (pre-prod clean replace). Total revenue = subscription + usage_billed (derived). Keep `(tenant, customer, period_start)` unique. |
| `CustomerRevenueProfile` **(new)** | `(tenant, customer)` unique; `recurring_amount_micros`, `interval` (`month`), `currency`, `effective_from`, `effective_to?`. Manual revenue source. |
| `MarginThresholdConfig` **(new)** | Per-tenant default (+ optional per-customer override): `min_margin_pct` (default `0`), `consecutive_periods` (default `1`), `provider_cost_spike_pct` (default `25`). Drives flags + webhooks. |
| `StripeSubscription` | Add `quantity` (seats) so the live current-period MRR estimate is seat-aware. (Closed-period revenue still comes from invoices.) |

## Per-dimension margin (usage-only)

A `metering`-gated `GET /margin/by-dimension` returning margin **by `tag` key / `product_id` / `provider`** = `Σ billed − Σ provider` per dimension, with `margin_micros`/`margin_pct`. This extends Stage 1's dimensional analytics (`by_tag`/`by_product`/`by_provider`) with a margin column. Subscription/manual revenue is **not** allocated across dimensions (the allocation would be arbitrary); full P&L stays at the customer/tenant level where it is attributable.

## Flags, trends & webhooks

The snapshot task, after writing each customer's period row, evaluates against `MarginThresholdConfig`:

- **Unprofitable:** `margin_pct < min_margin_pct` for ≥ `consecutive_periods` → set `is_unprofitable`, emit **`margin.customer_unprofitable`** (payload: tenant, customer, period, `gross_margin_micros`, `margin_pct`, `threshold_pct`).
- **Provider-cost spike / repricing signal:** `provider_cost` up ≥ `provider_cost_spike_pct` period-over-period while margin compresses → emit **`margin.provider_cost_spike`** (payload: tenant, customer, prev/current provider cost, prev/current margin_pct).

Both go through the **existing transactional outbox → tenant-webhook** machinery (same path as `usage.recorded`): delivery, retry, idempotency, and `HandlerCheckpoint` are already solved. New `OutboxEvent` schema dataclasses are added for the two event types.

## API surface

**`metering`-gated (margin & manual revenue):**
- `GET /margin/summary` — tenant totals for a window (revenue / provider cost / margin / margin%, unprofitable count).
- `GET /margin` — per-customer P&L list for a window.
- `GET /margin/{customer_id}` — one customer's P&L for a window.
- `GET /margin/by-dimension?tag_key=…|product|provider` — usage-only dimensional margin.
- `GET /margin/unprofitable` — flagged customers for a period.
- `GET /margin/{customer_id}/trend?periods=N` — provider-cost & margin over recent monthly snapshots.
- `GET|PUT /margin/customers/{customer_id}/revenue` — read/set the `CustomerRevenueProfile`.
- `GET|PUT /margin/threshold` (tenant default) and `GET|PUT /margin/customers/{customer_id}/threshold` (override).

All margin reads accept `start_date`/`end_date` (default current month-to-date). The old `/economics*` paths are replaced by `/margin*`; `/economics*` removed (pre-production, no compatibility shim).

**`subscriptions`-gated (unchanged owner, automated Stripe revenue):**
- `POST /sync`, the Stripe webhook, `GET /customers/{id}/subscription`, `GET /customers/{id}/invoices` — extended so sync captures `quantity`/seats.

## SDK changes (`ubb-sdk`)

Read-only margin methods + result dataclasses:
- `get_margin_summary(start_date=None, end_date=None)`, `get_customer_margin(customer_id, …)`, `get_margin_by_dimension(tag_key|product|provider, …)`, `get_unprofitable_customers(…)`, `get_margin_trend(customer_id, periods=…)`.
- `set_customer_revenue(customer_id, recurring_amount_micros, interval="month", …)` / `get_customer_revenue(...)`.
- Types: `CustomerMargin`, `DimensionMargin`, `MarginTrendPoint`, `CustomerRevenue`.
- Webhook event types (`margin.customer_unprofitable`, `margin.provider_cost_spike`) are documented, not SDK-typed (consumed by the tenant's webhook endpoint).

## Migrations summary

1. `subscriptions`: `CustomerCostAccumulator` provider/billed split (backfill: `total_provider_cost_micros = 0`, `total_billed_cost_micros = old total_cost_micros`); `CustomerEconomics` field reframe; new `CustomerRevenueProfile`; new `MarginThresholdConfig`; `StripeSubscription.quantity` (default 1).

Pre-production ⇒ backfills are trivial; still written for correctness. Migration-bearing steps are DB-validated (real `migrate` + `pytest` on Postgres) exactly as in Stage 1.

## Keep / reframe / delete

- **Reframe:** `CustomerCostAccumulator`, `CustomerEconomics`, `EconomicsService` (→ new P&L; revenue = manual+stripe; cost = provider), the `handle_usage_recorded_subscriptions` handler (accumulate both costs from the event), `apps/subscriptions/queries.py`, the economics endpoints (→ `/margin*`, `metering`-gated).
- **Keep:** `StripeSubscription`/`SubscriptionInvoice` (+`quantity`), Stripe sync + webhook mirror, outbox/webhook/checkpoint infra.
- **Delete:** nothing material — `apps/subscriptions/stripe/services.py` is already empty; subscription data is already read-only (Stage 0 removed lifecycle CRUD). Stage 2 verifies and leaves it read-only.

## Stage-2 Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Margin formula | `revenue − provider_cost` | Fixes the inverted model; provider cost is the true COGS, usage billed is revenue. |
| 2 | Revenue source | **Manual per-customer (primary) + Stripe (optional)** | Most metering tenants bill externally; UBB takes a manual revenue input and matches the P&L. |
| 3 | Compute model | **Hybrid (live window query + monthly snapshots)** | Live query = dashboard "margin at any time"; snapshots = trends/flags/webhooks. |
| 4 | Dimension margin | **Usage-only (billed − provider) per dimension** | Subscription/manual revenue is not attributable to a usage dimension; allocation would mislead. |
| 5 | Unprofitable rule | **Configurable threshold** (`min_margin_pct`, `consecutive_periods`) | Tunable, reduces noise vs. naive `<0`. |
| 6 | Interface | **Both query API + webhooks** | Dashboard pulls; alerts push (`customer_unprofitable`, `provider_cost_spike`). |
| 7 | Gating | **Margin + revenue input = `metering`; Stripe sync = `subscriptions`** | Heyotis (meter-only) must get margin with no subscription product. |
| 8 | Snapshot granularity | **Monthly** | Matches billing periods and the existing accumulator/economics period; live view is window-flexible regardless. |

## Risks & mitigations

- **Inverted-model migration.** Reframing `CustomerEconomics`/accumulator changes the meaning of stored fields. Mitigate: pre-production clean replace; assert in tests that `margin = revenue − provider_cost` and that meter-only margin = `billed − provider`.
- **Live vs. snapshot drift.** A live month-to-date number and the month-end snapshot can differ (proration, late events). Accepted and documented: live is the dashboard truth; snapshot is the archived close.
- **Manual revenue accuracy.** UBB stores what the tenant inputs; it does not verify external revenue. By design (mirrors the `provider_cost` trust posture). Note for tenant docs.
- **Double-counting revenue.** A tenant on UBB's Stripe could *also* set a manual profile. Mitigate: document that manual + Stripe are summed; recommend one source per customer; (optional later) a per-customer `revenue_source` selector.
- **Webhook noise.** Spike/unprofitable could fire repeatedly. Mitigate: `consecutive_periods` gate + only emit on state transition (not every snapshot).

## Acceptance criteria

- `makemigrations --check` clean; migrations apply on a fresh DB and on a Stage-1-seeded DB.
- A meter-only customer with usage and no revenue profile → `margin = billed − provider`, `margin_pct` correct, `revenue = usage_billed`.
- Setting a `CustomerRevenueProfile` of $500/mo → that customer's monthly snapshot revenue includes $500; live month-to-date prorates it.
- Per-dimension margin sums to the customer's usage-only margin (billed − provider).
- Threshold config drives `is_unprofitable`; crossing it emits exactly one `margin.customer_unprofitable` on transition.
- A ≥`provider_cost_spike_pct` PoP provider-cost rise emits `margin.provider_cost_spike`.
- Margin API is reachable by a `metering`-only tenant (no `subscriptions` product); Stripe sync requires `subscriptions`.
- SDK margin/revenue methods round-trip; SDK tests green.
- No reference to the old `usage_cost_micros` margin semantics or `subscriptions`-gated economics endpoints remains.
