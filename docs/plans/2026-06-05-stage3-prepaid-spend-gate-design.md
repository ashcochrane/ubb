# Stage 3 — Prepaid Credit Billing & Real-Time Spend Gate (Detailed Design)

**Date:** 2026-06-05
**Status:** Draft for review
**Parent:** `2026-06-05-ubb-repositioning-design.md`
**Depends on:** Stage 1 (durable `UsageEvent` ledger with exact `billed_cost_micros`), the existing `billing` product substrate. **Blocks:** Stage 4 (postpaid).

## Objective

Give prepaid (localscouta-style) tenants **real-time spend control**: stop a runaway agent before the next billable provider call, with multi-threshold visibility, while never letting the control plane corrupt the money ledger. This is the program's **highest-risk** stage; the risk is contained by one decision — **Postgres remains the sole money authority; Redis holds only a derived, reconstructable spend counter** for a soft budget cap.

## What already exists (and stays unchanged)

The prepaid substrate is already built as the `billing` product. Stage 3 **keeps it as-is** and layers one new control on top:

- **Credit ledger:** `Wallet` (`balance_micros`) + idempotent `WalletTransaction`. The authoritative prepaid balance.
- **Async drawdown:** `handle_usage_recorded_billing` (outbox handler, `requires_product="billing"`) deducts the wallet on `usage.recorded`, suspends on min-balance breach (`CustomerSuspended`), and emits `BalanceLow` for auto-top-up.
- **Auto-top-up:** `AutoTopUpConfig` + `TopUpAttempt` (idempotent) + the Stripe connector (`handle_balance_low_stripe`) charging the saved card and crediting the wallet.
- **Credit-balance gate:** `RiskService.check` — rejects suspended/closed, applies a Redis fixed-window rate limit (already fail-open), and does the **Postgres affordability check** (`balance < -min_balance → insufficient_funds`), optionally creating a `Run`.
- **Per-run hard-stops:** `RunService.accumulate_cost` — snapshot-based per-run cost ceiling + balance floor. Unchanged.
- **Access fee + seats:** a Stripe Subscription that Stripe bills; UBB reads it for margin (Stage 2). No new work here.

**Stage 3 adds exactly one thing:** a per-period **budget overlay** (soft spend cap + 50/80/100/110% alerts) backed by a reconstructable Redis counter, wired into the existing gate (pre-call) and drawdown (post-call).

## The single risk-containing principle

```
Money correctness  = Postgres (Wallet ledger). Synchronous, locked, exact. UNCHANGED.
Spend visibility/cap = Redis counter. Approximate, fast, FAIL-OPEN, always recomputable
                       from the durable UsageEvent ledger. NEW.
```

Redis is **never** the source of truth for a balance. If Redis is wiped, the worst case is that some customers temporarily skip their *soft* budget cap (fail-open) until the hourly reconciliation rebuilds the counter from Postgres — the prepaid credit balance still gates the money the whole time. *(Documented future escalation, out of scope now: if the hard credit-balance gate ever becomes latency-bound, introduce **reservations over a durable journal** — never an authoritative Redis balance.)*

## Budget overlay — data model

`apps/billing/gating/models.py` (alongside `RiskConfig`):

| Model | Fields |
|---|---|
| `BudgetConfig` **(new)** | `tenant` FK; `customer` FK (nullable → per-tenant default row); `cap_micros` (per-period ceiling); `period` (`CharField`, default `"month"`); `enforce_mode` (`advisory` \| `enforcing`, **default `advisory`**); `hard_stop_pct` (`IntegerField`, default `100`; set `110` for a grace band); `alert_levels` (`JSONField`, default `[50, 80, 100, 110]`); `fail_closed` (`BooleanField`, default `False` — per-customer override of the tenant fail-mode). Partial-unique: one default per tenant (`customer IS NULL`) + one per `(tenant, customer)` (same pattern as `TenantMarkup`/`MarginThresholdConfig`). |
| `RiskConfig` | Add `gate_fail_closed` (`BooleanField`, default `False`) — the tenant-level fail-mode (fail-open by default). |

Resolution: a customer's effective `BudgetConfig` is its own row → else the tenant default → else none (no budget overlay; gate behaves exactly as today). Fail-mode: `BudgetConfig.fail_closed` (if a config exists) → else `RiskConfig.gate_fail_closed` → else open.

## The Redis counter (derived, reconstructable)

- **Key:** `budget:{customer_id}:{YYYY-MM}` → integer micros of spend-so-far this **calendar month** (aligned with the existing monthly drawdown/billing cycle). **TTL** = end of next month (so a late reconciliation still finds it; expiry is harmless — it rebuilds on miss).
- `BudgetService` (`apps/billing/gating/services/budget_service.py`):
  - `record_spend(customer_id, period, amount_micros) -> (old, new)` — `cache.incr` by `amount_micros` (init via `cache.add` then `incr` on the race). Returns the pre/post totals for threshold detection.
  - `current_spend(customer_id, period) -> int` — `cache.get`; **on miss, rebuild** from Postgres (`Σ UsageEvent.billed_cost_micros` for the customer in the period) and `cache.set`.
  - `check(customer) -> {allowed, reason, spend, cap}` — resolve config; **if none, or `cap_micros <= 0` → `allowed=True` (overlay inactive)**. Read counter; in `enforcing` mode deny (`budget_exceeded`) when `spend ≥ cap × hard_stop_pct / 100`. **Any Redis exception → fail-open** (allow) unless the resolved fail-mode is closed (then deny `budget_unavailable`). `advisory` mode never denies.

`cap_micros <= 0` is the explicit "no cap" sentinel — the overlay is inert (no gating, no alerts), so a default `BudgetConfig` with cap `0` is a safe no-op until a real cap is set.

The period helper is the existing calendar-month `_current_period_bounds()` (factor it to a shared util if convenient).

## Gate wiring (advisory → enforcing)

- **Pre-call** — in `RiskService.check`, after the existing credit-balance affordability check passes, call `BudgetService.check(customer)`. Deny if **either** gate fails. New denial `reason="budget_exceeded"`. The pre-check endpoint/SDK surface this reason.
- **Post-call** — in `handle_usage_recorded_billing`, after the wallet deduction commits, call `BudgetService.record_spend(customer_id, period, billed_cost_micros)` and run threshold detection (next section). This reuses the handler's idempotency: the handler already runs once per event (checkpointed), so the counter increments once per event.

**Why advisory-first is safe to ship:** launch every `BudgetConfig` at `enforce_mode=advisory` — alerts fire and the dashboard shows spend-vs-cap, but nothing is blocked. After one cycle of watching alerts + reconciliation agree, flip a customer to `enforcing` via the config API — **no code change**. Enforcement and observation share one code path.

## Threshold alerts (transition-safe, exactly-once)

On `record_spend(old, new)` (only when `cap_micros > 0`), for each `L` in `alert_levels`: if `old < cap × L/100 ≤ new`, the level was crossed this increment → emit **`budget.threshold_reached`** (payload: `tenant_id, customer_id, period, level, spend_micros, cap_micros, enforce_mode`). **Dedup via outbox existence** (same guard as Stage 2's `provider_cost_spike`): skip if a `budget.threshold_reached` OutboxEvent already exists for `(customer_id, period, level)`. This makes a counter rebuild or a reconciliation pass unable to double-fire. Delivered through the existing transactional outbox → tenant webhook (`handle_webhook_delivery` registered for the new type). The 110% level is just another alert; the *blocking* is the gate's job in enforcing mode.

## Fail-open & reconciliation

- **Fail-open** is the default everywhere Redis is touched on the hot path (`check`, `record_spend`): a Redis error is swallowed and the request proceeds (money still guarded by the Postgres credit gate). `record_spend` failing just means a missed increment — corrected by reconciliation. Fail-closed is per-tenant/customer opt-in and only affects the *budget* gate.
- **Reconciliation task** (`reconcile-budget-counters`, hourly Celery beat): for each customer with an effective `BudgetConfig`, recompute the current-period counter from Postgres (`Σ billed_cost_micros`) and overwrite Redis. Idempotent; corrects drift from missed increments or a Redis flush. It may also fire any *missed* threshold alerts (same outbox-existence dedup) so a Redis outage doesn't silently swallow a crossing. This task is the safety net that makes the approximate counter trustworthy enough to enforce.

## API surface (all `billing`-gated)

- `GET|PUT /api/v1/billing/customers/{customer_id}/budget` — per-customer config.
- `GET|PUT /api/v1/billing/budget` — tenant default config.
- `GET /api/v1/billing/customers/{customer_id}/budget/status` — `{spend_micros, cap_micros, pct, enforce_mode, period}` for a live dashboard (reads the counter; rebuilds on miss).
- `/pre-check` response: `reason` may now be `budget_exceeded` (enforcing) — additive, no breaking change.

## SDK (`ubb-sdk`)

- `set_budget(customer_id, cap_micros, enforce_mode="advisory", hard_stop_pct=100, alert_levels=None)`, `get_budget(customer_id)`, `get_budget_status(customer_id)` + a `BudgetStatus` dataclass.
- `pre_check`/`check_budget` already returns allow/deny; surface the `budget_exceeded` reason.
- New webhook event `budget.threshold_reached` documented (consumed by the tenant's webhook endpoint).

## Keep / reframe / new

- **Keep unchanged:** wallet ledger, drawdown handler (extended by one `record_spend` call + threshold detection), auto-top-up + Stripe charge, the Postgres credit-balance gate, run hard-stops, Stripe subscription/seat revenue read.
- **New:** `BudgetConfig` + `RiskConfig.gate_fail_closed`; `BudgetService` (+ Redis counter); threshold detection + `budget.threshold_reached` contract & registration; budget API; reconciliation task; SDK budget methods.
- **Delete:** nothing.

## Sequencing (additive; DB-validated; **Redis-integration-tested**)

1. `BudgetConfig` + `RiskConfig.gate_fail_closed` (migration) · 2. `budget.threshold_reached` contract + delivery registration · 3. `BudgetService` (counter, reconstruct, check) — unit-tested against **real Redis** · 4. threshold-crossing detection + alert emission (transition-safe) · 5. wire `record_spend` into `handle_usage_recorded_billing` · 6. wire `BudgetService.check` into `RiskService.check` (+ `budget_exceeded` reason) · 7. budget API · 8. reconciliation task + beat schedule · 9. SDK · 10. final verification.

## Stage-3 Decision Log

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Redis role | **Budget counter only; Postgres authoritative for money** | Redis failure can never corrupt the ledger; counter is reconstructable from `UsageEvent`. |
| 2 | Budget cap | **Enforces (hard ceiling) at `hard_stop_pct`** | Alert-only fails the runaway-agent case the feature exists for. |
| 3 | Rollout | **`enforce_mode` default `advisory`; flip to `enforcing` per-customer** | Validate alerts + reconciliation before blocking; same code path, config-only flip. |
| 4 | Thresholds | **% of the per-period cap** (`[50,80,100,110]`) | Independent of credit balance; distinct from the existing `BalanceLow`. |
| 5 | Fail-mode | **Fail-open default; fail-closed opt-in (tenant + per-customer)** | Tenant app keeps working; money still guarded by the Postgres credit gate. |
| 6 | Period | **Calendar month, aligned with the billing/drawdown cycle** | Reuses `_current_period_bounds`; matches the monthly accumulator + tenant billing. |
| 7 | Alert dedup | **Outbox-existence guard on `(customer, period, level)`** | Rebuild/reconciliation can never double-fire; durable, not Redis-state-dependent. |
| 8 | Run hard-stop | **Unchanged (snapshot-based, per-run)** | Orthogonal to the per-period budget cap; the gate catches budget at each pre-check. |

## Risks & mitigations

- **Approximate counter under-counts and lets spend slip past the cap.** Bounded by: the durable ledger is exact; reconciliation overwrites drift hourly; the cap is a *soft* control and the credit balance is the hard money gate. Acceptable by design.
- **Threshold alert spam / double-fire.** Outbox-existence dedup per `(customer, period, level)`; transition-only emission on the crossing increment.
- **Redis outage.** Fail-open: budget gate skips, money gate unaffected; reconciliation repairs the counter when Redis returns.
- **Enforcing too early.** Mitigated by advisory-first default; flip per-customer only after reconciliation is observed to agree.
- **Test fidelity.** Budget tests MUST run against the real Dockerized Redis (not Django's dummy cache) — `cache.incr`/TTL semantics matter. Reconciliation tests assert counter == `Σ billed_cost_micros`.

## Acceptance criteria

- A customer with no `BudgetConfig` → gate behaves exactly as today (no regression).
- `advisory` config: crossing 50/80/100% emits one `budget.threshold_reached` each (no duplicates on replay); the gate never denies.
- `enforcing` config with `hard_stop_pct=100`: once `spend ≥ cap`, `pre-check` returns `allowed=False, reason="budget_exceeded"`; under the cap it allows.
- Redis made unavailable: gate still allows (fail-open) and the credit-balance check still functions; with `fail_closed=True` the budget gate denies `budget_unavailable`.
- `record_spend` increments the counter; `budget/status` reflects spend/cap/pct; after a manual `cache.delete`, `current_spend` rebuilds from Postgres to the same value.
- Reconciliation overwrites a drifted counter to `Σ billed_cost_micros` and fires only not-yet-sent threshold alerts.
- SDK budget methods round-trip; full platform suite + SDK suite green; migrations apply on a fresh DB.
