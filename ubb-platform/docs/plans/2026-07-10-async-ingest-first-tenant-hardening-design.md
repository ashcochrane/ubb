# Async-Ingest First-Tenant Hardening — Design

**Date:** 2026-07-10
**Branch:** feat/rate-card-container (stacked; PR #5 grows — decided over merge-first)
**Goal:** a real tenant can switch on `metering_async` safely. Four items ship:
run-kill parity, markup rate cache, ops visibility (endpoint + log alerts),
RawIngestEvent retention. Everything else stays deferred (see Non-goals).

The standard every call below is held to, restated from the product thesis:
the platform itself enforces spend — never leak money past a cap, fail in the
safe (over-restrictive) direction, keep the guarantee legible and testable.

## 1. Run-kill parity on the async path

**Gap.** Sync: `HardStopExceeded` → endpoint kills the run
(`RunService.kill_run`, idempotent, `select_for_update`) + writes a
`RunLimitExceeded` outbox event (scope="run", P6 webhook fan-out to sibling
workers) inside one `transaction.atomic()` → 429. Async:
`HoldService.acquire`'s Lua rejects the item (`reason:
"cost_limit_exceeded"`) and nothing else — the run stays `running`, sibling
workers learn nothing, and every later batch re-rejects against a run that
should be dead.

**Design.** In `ingest_usage_batch` (api/v1/metering_endpoints.py), after the
acquire loop and after the raw-append durability boundary:

1. Collect distinct `run_id`s whose verdict reason is `cost_limit_exceeded`
   (dedupe — many items in one batch can share a run).
2. For each, in its own `transaction.atomic()`: `kill_run(run_id,
   reason="cost_limit_exceeded", tenant_id=…, customer_id=…)` + `write_event(
   RunLimitExceeded(scope="run", …))` — the same pairing, same atomic scope,
   as the sync handler. `total_cost_micros` = the killed run's durable
   `total_cost_micros` as read under the row lock (the live counter may be
   slightly ahead; the field documents best-known total at kill time — noted
   in the event schema docstring).
3. Ordering vs the append boundary: kills run only after the append block
   completes. On the 503 append-failure path the endpoint raises before the
   kill — the client's retry re-derives the same rejections and kills then,
   so kills only happen for batches that landed. A fully-rejected batch has
   no raws to append and proceeds straight to the kill step. If the client
   never retries a failed append, the next batch on that run re-rejects and
   kills — convergent either way.

**Exactly-once event emission.** `kill_run` no-ops if the run is already
terminal, but the caller can't tell whether *it* performed the transition.
Unlike sync (where `RunNotActive` fires before `HardStopExceeded` on
retries), an async batch racing a stale run-meta cache re-enters this branch.
Change: `kill_run` returns `(run, transitioned)`; all existing call sites
updated; the outbox event is written only when `transitioned` is True. The
sync handler adopts the same guard (harmless there, consistent everywhere).

**Run-meta cache.** On a performed kill, `_RUN_META_CACHE.pop(run_id)` in the
local process so the next batch rejects `run_not_active` immediately. Other
web processes converge within `_RUN_META_TTL_SECONDS` (bounded staleness;
duplicate kill attempts in that window are no-ops and emit nothing, per the
transition guard). The replay-wins idem probe (retries beat
`run_not_active`) is untouched.

**Deliberately different from sync:** no HTTP 429 (batch semantics keep
per-item verdicts — the posting worker sees `rejected: cost_limit_exceeded`
in its item result); run-cap rejection still sets no owner-level stop flag
(run caps are exact-reject; the stop flag belongs to the wallet floor).

**Tests.** (a) Race: two concurrent batches hit the same run's cap → exactly
one kill, one outbox event, both get correct rejection verdicts
(`transaction=True`, threaded, per the Lua-race test idiom). (b) Kill flips
subsequent batches to `run_not_active` (cache invalidated). (c) Mixed
sync-then-async and async-then-sync sequences end in the same terminal state
+ single event. (d) 503 append-failure path performs no kill; retry does.
(e) `kill_run` transition flag: True exactly once across repeated calls.

## 2. Markup rate cache

**Gap.** `MarkupService.resolve` runs up to two ORM queries (customer
override → tenant default) per event. `EstimationService` calls it for every
cost-provided, non-caller-billed item — the accept path's "no ORM per event"
property is false precisely for markup tenants.

**Design.** New `apps/metering/pricing/services/markup_cache.py`, mirroring
`card_cache.py` as-built (the reviewed pattern: per-tenant version key in
Redis, request-pinned via `contextvars`, bounded L1 dict, L2 Redis):

- L1 key `(tenant_id, customer_id|"")` → resolved `TenantMarkup` instance or
  `None` (negative cache — "no markup configured" is the common case and must
  also be one dict hit), validated against the Redis version key
  `ubb:markupver:{tenant_id}`. No L2 value store: `card_cache.py` as-built
  holds values in L1 only (Redis carries just the version), and an L2 adds
  nothing here — an L1 miss repopulates with one ORM resolve per (tenant,
  customer) per 30s TTL per worker. *(Corrected from an earlier draft that
  described an L2 value key, to match the pattern actually being mirrored.)*
- Version bump on `TenantMarkup.save()` and `.delete()` overrides — at the
  model layer so no service path can bypass it (same reasoning as
  UsageEvent's model-layer immutability).
- Resolution order preserved exactly: customer entry → default entry → none.
- **Fallback direction (the money rule):** a missing markup would
  *under-estimate* and therefore under-hold. On L2 miss → ORM resolve +
  populate. On Redis failure → ORM resolve directly (degraded to today's
  behavior, loud log; never "assume none"). The settle path keeps live-ORM
  exact pricing, unchanged — estimate/settle drift from a mid-flight markup
  edit nets out at settlement like every other estimate error.

**Tests.** (a) Property: cached resolve ≡ ORM resolve across
override/default/none shapes. (b) Bump-on-save/delete invalidates (stale
version unreadable). (c) Redis-down falls back to ORM (estimate unchanged,
log emitted). (d) Accept-path query count for a markup tenant's batch is
O(1), not O(n) — pinned with `assertNumQueries`-style assertion, the
discriminating test for the whole item.

## 3. Ops visibility: ingest health endpoint + alert task

**Gap.** Spec'd rollout monitoring ("settle lag, raw-log queue depth") was
never built; there is no metrics infra at all (no Prometheus/statsd/Sentry —
alerting today is loud log lines, e.g. `DRIFT_ALERT_MICROS`).

**Design.** One source of truth, two consumers:

- `ingest_health()` in `apps/metering/usage/services/` returns:
  `pending_count`, `oldest_pending_age_seconds` (settle lag — `now -
  min(created_at)` over status=pending), `retrying_count` (pending with
  attempts > 0), `failed_count`. All served by the existing
  `idx_rawingest_claim (status, created_at)` index. Optional `tenant_id`
  filter param.
- **Endpoint:** `GET /api/v1/metering/ops/ingest-health`. Operator-facing,
  not tenant-facing, so tenant API keys must NOT grant it: guarded by a
  dedicated `UBB_OPS_TOKEN` setting compared with `hmac.compare_digest`
  against an `X-Ops-Token` header; when the setting is unset the endpoint
  returns 404 (fail closed, invisible). No new dependency, curl-able,
  dashboard-ready later.
- **Alert task:** `monitor_ingest_health` beat task every 5 minutes (matches
  existing cadence convention). Logs ONE structured line per run with all
  metrics; level = worst threshold breached: WARNING at
  `UBB_INGEST_SETTLE_LAG_WARN_SECONDS` (default 120) or
  `UBB_INGEST_QUEUE_DEPTH_WARN` (default 10_000); ERROR at 5× either
  threshold or any `failed_count > 0` (poison events are never auto-cleared,
  so they must stay loud until an operator acts — accepted noise, noted).

**Tests.** (a) Metrics correct against seeded raw rows in every status.
(b) Threshold matrix → log level (caplog). (c) Endpoint: 404 when token
unset, 401 wrong token, 200 + shape with token. (d) Tenant filter scopes
counts.

## 4. RawIngestEvent retention

**Gap.** Settled/duplicate raws accumulate forever — unbounded table growth
at exactly the volumes the async path exists for.

**Design.** `purge_raw_ingest_events` beat task, daily 03:20 UTC (offset from
the existing 3 AM `cleanup_webhook_events` slot; same shape as
`cleanup_outbox`, the established purge precedent):

- Deletes `status IN (settled, duplicate)` with `created_at <` now −
  `UBB_RAW_INGEST_RETENTION_DAYS` (default **90**; > the 62-day idem-key TTL
  so raw evidence always outlives any replay window it could be correlated
  against — UsageEvent, not the raw row, is the exactly-once authority, so
  purging settled raws can never affect idempotency).
- **Never** deletes `pending` (that's the queue) or `failed` (poison rows
  are operator evidence — matches `cleanup_outbox`'s "failed events are
  never auto-deleted").
- Chunked deletes (pk-sliced batches of 10_000) — at target volume a
  one-shot `DELETE` would hold locks too long. Logs a summary count line.

**Tests.** (a) Age/status matrix: only old settled+duplicate rows die.
(b) Chunking: >1 batch drains fully. (c) Boundary: rows exactly at the
cutoff survive (strict `<`).

## Settings added

| Setting | Default |
|---|---|
| `UBB_OPS_TOKEN` | unset (endpoint 404s) |
| `UBB_INGEST_SETTLE_LAG_WARN_SECONDS` | 120 |
| `UBB_INGEST_QUEUE_DEPTH_WARN` | 10_000 |
| `UBB_RAW_INGEST_RETENTION_DAYS` | 90 |

## Task order (for the implementation plan)

1. Run-kill parity (money gate — reviewed hardest, freshest attention)
2. Markup rate cache (money-adjacent: pricing correctness + hot path)
3. Ops endpoint + alert task
4. Retention purge

Full-suite expectation unchanged: 27 pre-existing failures in
invoicing/subscriptions remain outside this work's baseline.

## Non-goals (deferred, with reasons)

- **Orphan-hold repair** — fails safe (over-restrictive), surfaced by drift
  alerts; watch-and-wait per scoping decision.
- **caller_billed strict-coverage alignment** — safe direction, flag-gated;
  only matters for caller-priced tenants.
- **SSE stop endpoint + SDK batching + local stop flag** (Plan 2) — SDK
  session owns this; webhook + ack-flag stop propagation is the v1 story.
- **Load test** (paper numbers → measured) — after Plan 2, before quoting
  throughput publicly.
- **event_ref / error-taxonomy decisions** — pre-GA API-freeze work, owned
  by the SDK session that consumes them.
- **Redpanda log swap** (Plan 3 / Rung B) and everything behind the Rung C
  seams — pulled by tenant volume, not pushed.
