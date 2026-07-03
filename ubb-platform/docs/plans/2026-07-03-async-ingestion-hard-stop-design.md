# Async Ingestion with Accept-Time Hard Stop (Rung A → B)

**Date:** 2026-07-03
**Status:** Implemented (Rung A core) — 2026-07-03; SSE/SDK batching and Redpanda log swap are follow-up plans
**Related:** 2026-06-19-prepaid-hard-stop-design.md (Tier-2 live ledger), 2026-07-03-rate-card-container-plan.md (BookService.publish — invalidation hook)

## Problem

`UsageService.record_usage` prices every event synchronously inside one
Postgres transaction (9–13 round trips, row locks on tier ladders / runs /
wallets). Ceiling: ~100–300 events/sec per instance; batching does not help
because items run sequentially in-request. Competitors ingest asynchronously
(Metronome 100k/s headline, Lago/Orb async pipelines) but **none of them
enforce spend caps** — they notify via webhooks/alerts and the customer builds
the kill-switch. UBB's differentiator is the platform-enforced hard stop.

**Goal:** async-class ingestion throughput while keeping the hard-stop
guarantee at (effectively) today's strength.

## Key insight

The hard stop does not require synchronous *pricing* — it requires a
synchronous *atomic check-and-count* per billing owner. The Tier-2 live
ledger (`apps/billing/gating/services/live_ledger_service.py`) already
provides that primitive in Redis Lua (`_SEED_AND_DECR`, `_TASK_CHECK_INCR`,
stop flag, hourly MIN/MAX reconcile). The only coupling to the slow path is
that the counter needs a cost, and cost currently comes from full pricing.

**Fix: feed the gate an *estimate* at accept; settle to exact in workers.**
(Auth/capture semantics — same design family as the Tier-2 "bounded,
reconcile-corrected window" contract.)

Today's wallet-floor stop is already cooperative (I3: the breaching event
lands; the *next* event sees the flag). The async path preserves that class
of guarantee; the bound widens from ~1 event to ~1 batch + tier-boundary
estimate error. Per-run/per-task caps stay exact-reject.

## Architecture

```
SDK (batches 100ms/500 ev, SSE stop subscription, local stop flag)
  │  POST /api/v1/metering/usage/ingest  (batch)
  ▼
Accept path (ASGI, separate deployment of same Django project)
  1. auth from in-process cache            (0 I/O)
  2. validate + ESTIMATE from L1 card cache (pure CPU)
  3. ONE pipelined Redis call: idem SETNX + HOLD (atomic decr+floor)
     + per-run cap (check-then-incr) + stop-flag readback
  4. ONE durable append (RawIngestEvent table v1; Redpanda v2 — seam)
  5. 202 with per-event verdicts {accepted, estimated_cost_micros, stop,…}
  ▼
Settle workers (Celery, SKIP LOCKED batch claim)
  exact PricingService.price (tier-ladder locks contended only by workers)
  → UsageEvent insert (unique constraint = exactly-once authority)
  → outbox UsageRecorded (existing) → async wallet drawdown (existing)
  → settle delta (INCRBY estimate−exact), update tier mirror
  ▼
Stop propagation: _set_stop → Redis pub/sub → SSE push (~ms) + stop.fired
HMAC webhook (existing infra) + verdict on every ack. SDK flips local flag,
on_stop callback, run kill; RiskService start-gate refuses new runs.
```

The **synchronous endpoint is unchanged** — callers who want the exact priced
result in-response keep it. The async path is additive, gated per-tenant via
the existing `products` flag pattern.

## Components

### 1. Estimation layer (`apps/metering/pricing/estimation.py` or similar)
- **L1** in-process cache of active rate cards per (tenant, event_type);
  **L2** Redis mirror; source of truth Postgres. Invalidation published by
  `BookService.publish` (version-key bump on Redis pub/sub).
- Four cases: caller-supplied cost (exact, no work); linear rate (exact,
  `units × rate`); tiered (estimate at *current* tier from a Redis tier-
  position mirror maintained at settle time); unpriceable (route that event
  down the sync path — never silently fail open).
- **Invariant: never knowingly under-hold.** Estimates err toward over-
  holding (current-tier pricing over-holds on decreasing-price ladders; for
  increasing-price ladders estimate at the max applicable rate).

### 2. Hold engine (`apps/billing/gating/holds.py` — the named seam)
- Narrow interface: `acquire(owner, estimates, run_id) -> verdict`,
  `settle(ref, exact)`, `release(ref)`, `void(ref)`. Nothing outside the
  module knows it is Redis. (Documented growth path: TigerBeetle pending
  transfers behind the same four functions.)
- New Lua: batch hold (seed-if-absent + DECRBY sum + floor check, per owner)
  and per-run cap as check-then-increment (ports `RunService.accumulate_cost`
  off `select_for_update` for this path; mirrors `_TASK_CHECK_INCR`).
- Existing scripts, stop flag, credit hooks, reconcile: reused unchanged.

### 3. Accept endpoint
- `POST /api/v1/metering/usage/ingest` — batch, django-ninja async view,
  deployed as its own ASGI process pool (uvicorn) behind the LB. Hot path
  touches ONLY: auth cache, L1 cards, Redis, raw append. No ORM per event.
- Response 202, per-event `{accepted, estimated_cost_micros, stop,
  stop_reason, stop_scope, event_ref}`.

### 4. Durable raw log
- v1 (**Rung A**): `RawIngestEvent` Postgres table (tenant, customer,
  idempotency_key, payload JSONB, estimate_micros, hold ref, status
  pending/settled/duplicate/failed) written with one multi-row INSERT per
  batch. Append hidden behind a `raw_log.append(batch)` seam.
- v2 (**Rung B**): swap seam to Redpanda topic `usage.raw` when sustained
  volume approaches the Postgres COPY ceiling (~20–30k/s). Only new
  operational system in Rung B.

### 5. Settle workers
- Celery consumers claim pending raws (SKIP LOCKED batches). Per event:
  exact pricing → UsageEvent insert → outbox → `holds.settle(delta)` →
  tier-mirror update. Duplicate (unique-constraint hit) → `holds.release`,
  mark `duplicate`. Permanent failure → release hold, mark `failed`, loud
  alert (a billable event that cannot settle is an incident, not a log line).

### 6. Stop propagation
- `_set_stop` additionally publishes `ubb:stopchan:{owner}`; new SSE endpoint
  (`GET /api/v1/billing/stops/stream`); `stop.fired` event through the
  existing HMAC-signed webhook system. Push is best-effort; the accept-path
  verdict is the enforcement backstop.

### 7. SDK
- Client-side batching (flush at 100ms or 500 events), background SSE
  subscription, local `stopped` flag, `on_stop` callback, run-kill helper.
  At-least-once retry of unacked batches.

## Contracts and invariants

1. **Never under-hold** (estimation invariant, tested by property test).
2. **Never ack before durable append**; on append failure, void the hold in
   the same request and return 503 (SDK retries).
3. **Idempotency across the boundary**: Redis `SETNX` is a fast filter only.
   Idem-hit ⇒ *skip the hold, still append* (at-least-once log); the
   `UsageEvent` unique constraint at settle is the exactly-once authority;
   duplicate settle releases the hold.
4. **Enforcement happens at accept.** Settle lag delays exactness and
   invoicing freshness, never enforcement.
5. **Cooperative stop semantics preserved** (I3): the crossing event is
   recorded (the spend already happened; refusing to record loses billing
   data); the verdict flips on its ack; subsequent work is refused by SDK
   flag + start-gate.
6. **Redis failure = fail-open** (current philosophy: loud log, durable
   start-gate backstop). Optional future per-tenant fail-closed knob.
7. **Orphaned holds** (crash between hold and append) are NOT auto-corrected
   by the hourly reconcile. An orphan pushes the live counter LOWER than the
   durable balance (over-restrictive, fails safe); the MIN-merge only ever
   LOWERS toward the durable balance, so an already-lower value is a FIXED
   POINT it leaves untouched (pinned by
   `test_settlement.py::OrphanHoldUnheldBranchTest`). The drift persists as
   bounded over-restrictive drift — surfaced by the existing
   `DRIFT_ALERT_MICROS` spike alert — and heals only via a credit/top-up
   (which raises the counter through `LiveLedgerService.credit`),
   `cleanup_keys` (an enforcement-mode transition), or the 62-day key TTL. An
   automatic repair mechanism (e.g. a reconcile variant that can raise a
   live counter back toward the durable value when it is HELD-orphan-caused
   rather than a genuine in-flight decrement) is a named follow-up, not yet
   built.

## Guarantee accounting

| | today (sync) | Rung A/B (async) | competitors |
|---|---|---|---|
| wallet-floor overage bound | ~1 event (cooperative) | ~1 batch estimate + tier-boundary error | burn-rate × pipeline lag (unbounded under backlog) |
| per-run / per-task caps | exact-reject | exact-reject (Redis check-then-incr)* | n/a |
| enforcement built by | platform | platform | customer (webhook DIY) |
| throughput | ~100–300/s | A: ~10–50k/s; B: ~100k+/s aggregate | 100k/s (Metronome headline) |

`*` Per-run caps are exact-reject on both paths (`HoldService.acquire`'s
run-cap check-then-increment mirrors `RunService.accumulate_cost`). Per-TASK
caps (P4, `RiskConfig.max_cost_per_task_micros`) are **sync-path-only** in
Rung A v1: `check_task_cost_cap` is called from `UsageService.record_usage`
but neither `HoldService.acquire` nor `UsageService.settle_raw` ever call it,
so async-settled spend never feeds `ubb:taskcost:*`. A tenant that mixes
synchronous and async ingestion for the same task gets an under-enforced
task cap (the async share of that task's spend is invisible to it). Wiring
per-task caps into the async accept/settle path is future work, not yet
scheduled.

## Testing strategy

- **Property test**: for arbitrary cards/volumes, estimate-then-settle nets
  exactly to `PricingService.price`, and estimate ≥ exact wherever the
  conservatism rule claims it.
- **Race tests** in the style of the existing Lua tests (concurrent holds at
  the floor, concurrent idem SETNX, crossing sets flag exactly once).
- **Failure-mode tests**: crash between hold and append (retry path), append
  failure voids hold, duplicate settle releases hold, poison event releases
  hold + alerts.
- **E2E**: burn an owner to the floor through the async path; assert the
  crossing ack carries `stop: true`, the SSE push arrives, leakage ≤ one
  batch estimate, top-up recovery lifts the flag.
- **Load test** to replace paper numbers with measured ones.

## Rollout

Per-tenant opt-in flag (existing `products` JSONField pattern). Monitoring:
settle lag, raw-log queue depth, existing `DRIFT_ALERT_MICROS` drift alerts,
hold-leak counter. Sync endpoint untouched throughout.

## Non-goals (documented future — Rung C)

Escrow/local-lease gate in the gateway, TigerBeetle as hold engine
(self-voiding pending transfers, `debits_must_not_exceed_credits` floor as a
DB invariant), Rust/Go gateway, ClickHouse settlement/analytics, gRPC
streaming ingest, flag-only "throughput mode" tenant knob. Each sits behind
a seam named above; none blocks Rung A/B.

## Implementation record (2026-07-03)

Rung A core landed end-to-end on `feat/async-ingest-hard-stop`: `RawIngestEvent`
model, the card/tier-mirror cache, `EstimationService` (never-under-hold,
exact on non-tiered cards), `HoldService`'s atomic Redis batch gate, the
`POST /api/v1/metering/usage/ingest` accept endpoint, `settle_raw_events`
settlement, and stop-flag pub/sub + `stop.fired` outbox propagation — closed
out by `api/v1/tests/test_ingest_e2e.py`, a single burn-to-floor test driving
the REAL endpoint, the REAL settlement task, and the REAL outbox wallet-
drawdown handler (no mocks) for a prepaid/enforcing owner funded $20 against
a non-tiered $10/1,000,000-token price card.

**Measured numbers (from the E2E test, deterministic across repeated runs):**
- Crossing batch (3 events, $6/$5/$2 estimated): the second item crosses the
  wallet floor; both it and every later item in that same pipelined batch
  report `stop: true` (HoldService.acquire applies one uniform verdict per
  acquire() call, not per positional crossing point — a deliberate
  batch-granularity cooperative behavior, now pinned by a test).
- **Overage bound observed:** live balance at flag-set = **-$3.00**
  (-3,000,000 micros) against a crossing-batch estimate sum of **$13.00**
  (13,000,000 micros) — i.e. actual overage was ~23% of the "≤ one batch"
  bound the design commits to, confirming the bound holds with headroom on
  this fixture (not merely non-negative).
- Exact convergence: `sum(UsageEvent.billed_cost_micros)` == $23.00 ==
  $20.00 − durable wallet balance (-$3.00); live counter equals the durable
  balance both before AND after `reconcile_prepaid` (the non-tiered card's
  estimate is exact, so estimate-then-settle nets to equality, not just an
  inequality).
- Whole-batch replay of the final batch produced zero new `UsageEvent` rows
  and zero new holds, exercised through BOTH the accept-layer idempotency
  prefilter (duplicate_suspect) and the settle-layer `UsageEvent` unique
  constraint (verified exactly-once at both boundaries).
- Exactly one `ubb:stopchan:{owner_id}` pub/sub message and exactly one
  `stop.fired` outbox row for the crossing (transition-only, no spam).

**Full-suite regression gate:** `1611 passed, 27 failed, 3 skipped` — the 27
failures are entirely in `apps/billing/invoicing` and `apps/subscriptions`
(files untouched by this branch; pre-existing baseline carried from
`feat/rate-card-container`). Zero failures in metering, gating, wallets,
topups, runs, platform/events, or api/v1.

The Task 1–7 per-task reviews (opus, money-path scrutiny throughout)
surfaced and closed several CRITICAL/Important defects along the way
(under-hold on increasing-rate ladders, postpaid settle sign trap, hold-leak
races, StopFired transaction-poisoning). A residual list of deliberately
deferred MINOR items (documentation/comment-only items, no behavior risk)
accumulated task-by-task is carried in `.superpowers/sdd/progress.md` for the
whole-branch final review — none block this "Rung A core: implemented"
status.
