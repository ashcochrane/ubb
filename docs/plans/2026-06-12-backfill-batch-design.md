# F4.2 — Caller Timestamps, Bounded Backfill, Batch Ingestion

**Status:** Implemented (2026-06-12)

## Problem

`UsageEvent.effective_at` was `auto_now_add` — callers could not timestamp events, so one bad
integration day was unrecoverable (UsageEvent is INSERT-ONLY). This task makes `effective_at`
caller-suppliable with hard bounds, adds `POST /usage/batch` for replays, and — the actual
point — walks EVERY downstream consumer of usage timestamps and assigns it an explicit basis.

## The contract

- `effective_at` = when the usage economically **happened** (caller-suppliable).
- `created_at` = when the event **arrived** (server clock, immutable).
- Validation at the `record_usage` choke point (`EffectiveAtError`, typed 422 codes):
  - `effective_at_naive` — no tz offset;
  - `effective_at_in_future` — > now + 5 min skew;
  - `effective_at_too_old` — < now − `Tenant.backfill_window_days` (default 34, bounds 0..60,
    0 = no backfill at all);
  - `billing_period_closed` — the billing OWNER's `CustomerUsageInvoice` for the EFFECTIVE
    month has touched Stripe (status `pushing`/`pushed`/`skipped`/`failed_permanent`, OR
    `push_phase != ""`, OR `stripe_invoice_id != ""`). Under F0.1 resume semantics such a row
    has items pinned at the frozen `line_snapshot`; a backfill would diverge recorded totals
    from the finalized invoice. A truly-untouched `pending` row re-aggregates safely and does
    NOT block. Guard goes through the billing read contract
    (`apps.billing.queries.is_usage_period_closed`, promoted to the ADR-001 shared list).
- Pricing: `as_of=effective_at` — historical rate-card versions + the EFFECTIVE month's
  tier-counter ladder (`month_bounds(as_of)`, F4.1).
- Replay-before-validate: the idempotency replay check runs BEFORE effective_at validation, so
  a whole-batch retry returns original event ids even if the window has since aged past the
  timestamp or the period closed.
- A backfill into a PRIOR calendar month writes a `BackfillDirtyPeriod(tenant, customer,
  period_start)` marker in the same transaction (savepoint-IntegrityError-swallow).
- `UsageRecorded` outbox payload gains `effective_at: str = ""` (UTC-normalized ISO);
  legacy queued payloads without it keep working via consumer fallbacks.

## Per-consumer recompute map

| Consumer | Basis | Mechanism |
|---|---|---|
| Cost accumulators (`apps/subscriptions/handlers.py`) | **effective** | Buckets into the effective month — fast path `payload["effective_at"]`, fallback to the `get_usage_event_effective_at` contract getter. `reconcile_cost_accumulators` widened to current + 2 previous months (a 60-day max window spans 3 calendar months). |
| Margin snapshots (`CustomerEconomics`) | **effective** | NEW hourly `resnapshot_dirty_periods` (beat :55, after the :50 accumulator reconcile): each prior-month `BackfillDirtyPeriod` → `snapshot_customer` (update_or_create, idempotent) + `evaluate_and_emit` (transition-guarded + outbox-deduped, idempotent) → delete marker AFTER success (crash ⇒ retried). Current-month markers just deleted — the nightly snapshot owns the current month. |
| Budget live counters (`apps/billing/handlers.py`) | **effective-month budgets; live counter is current-month-only** | The Redis spend counter increments ONLY when the effective month == current wall-clock month (absent payload field ⇒ legacy behavior). Hourly rebuild (already effective_at-filtered via `get_customer_cost_totals`) is the source of truth. |
| Drawdown repair (`reconcile_usage_drawdowns`) | **arrival** | `iter_billable_usage_events(..., basis="created")` — the DLQ horizon is an arrival-time concept. A backfilled event is INSERTED now, so it is repair-eligible now regardless of effective age (kills "backdated >7d invisible to repair forever" with zero window widening). Supported by the new `(tenant, created_at)` index. |
| Tenant platform fee (`TenantBillingService.reconcile_period`) | **arrival** | `get_period_totals(..., basis="arrival")` — platform fees accrue in the ARRIVAL period, matching the wall-clock live `accumulate_usage` counter; kills the accumulate-vs-reconcile drift asymmetry for backdated events. |

### Naturally correct (verified, document-only)

- **Postpaid aggregation** — re-queries by effective_at at close; closed periods are guarded by
  the `billing_period_closed` 422, and a `pending` row that re-aggregates on push picks the
  backfilled events up by construction.
- **Analytics / timeseries / margin reads** — pure effective_at range queries; backfilled events
  appear in the right buckets automatically.
- **Referrals reconciliation** — windows on effective_at via the read contract; the daily
  reconcile re-derives from the ledger.
- **Wallet debits + gates + run hard-stop** — intentionally arrival-time: balance is a "now"
  scalar; a backdated event still costs money now.
- **Pagination cursor skip** — a backfilled event can sort behind an already-consumed cursor
  position; accepted, standard cursor-pagination behavior.

## Known races / accepted gaps

- **Close-vs-backfill race:** the guard reads the owner's invoice row without locking it, so a
  backfill validated a few milliseconds before the monthly close claims the row can commit an
  event the frozen snapshot misses. The window is milliseconds wide, occurs once a month at
  the close instant, and the residual is bounded by one event. Documented, not fixed —
  closed-period **adjustment lines** (post-close corrections as next-invoice line items) are
  the future-work fix and are explicitly out of scope here.
- **Budget enforcement bypass:** an enforcing-capped seat can backdate usage into the PRIOR
  month to evade the live cap (the prior month's budget already evaluated). Bounded by
  `backfill_window_days`; tenants needing airtight caps set it low — **0 = no backfill**.
- **Tier counters for closed-but-unpushed months:** a backfill into a prior month advances that
  month's `PricingPeriodCounter` (month from `as_of`) — correct marginal pricing; the
  `verify_tier_rerate` tripwire re-rates from the ladder, so totals stay telescoping-exact.

## Out of scope

- Closed-period adjustments (credit notes / next-invoice adjustment lines).
- Bulk import beyond 100 items per call (loop `record_batch`; per-item idempotency makes the
  loop resumable).
