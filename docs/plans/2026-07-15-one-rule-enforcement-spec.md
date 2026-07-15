# One-rule enforcement — spec (ready to hand off)

**Date:** 2026-07-15 · **Origin:** map [#9](https://github.com/ashcochrane/ubb/issues/9), ticket
[#18](https://github.com/ashcochrane/ubb/issues/18) · **Status:** decisions locked with the user;
implementation not started. All file:line anchors verified against main on 2026-07-15.

The one-rule model (decided in [#10](https://github.com/ashcochrane/ubb/issues/10)): **every usage
event that reaches UBB is priced, recorded, and billed immediately — no refusals of usage reports,
no parking states, anywhere.** The balance always shows reality, including negative. Caps and the
wallet floor are **signal points** (stop + resume), never billing walls. Refusing *new runs* at the
start-gate stays — refusing work that hasn't happened is consistent; refusing to record work that
has is not.

## Decisions locked in this spec's grilling (2026-07-15)

1. **Wire contract — success + stop signal.** Every recorded event returns a normal success
   response; the stop instruction rides response fields. HTTP 429 `hard_stop_exceeded` and
   409 `run_not_active` are retired for usage reports. Errors remain only for requests that
   genuinely didn't record (auth, malformed payload, unknown customer).
2. **Run lifecycle — keep `killed`, keep counting.** The run still flips to `killed` the moment its
   cap trips (the flip is the durable record that the signal fired). Events arriving afterwards
   land, bill, and keep adding to `run.total_cost_micros`. No status rename; the glossary redefines
   *killed* as "stop signal fired; new runs refused; late events still land and count."
3. **Modes — `advisory` is dropped entirely.** `Tenant.enforcement_mode` becomes two-position:
   `off` / `enforcing`. The whole signal suite (stop/resume signals, stop-context tagging, run
   flips, start-gate refusals, suspension) exists only in `enforcing`; `off` is byte-for-byte
   Tier-1 behavior. **Corollary (user-confirmed):** the ≥1-week advisory soak leg of the proof
   plan is dropped — the evidence bar becomes **three legs** (load, chaos drills, live Stripe
   money test). Flagged to the proof-plan ticket (#15).
4. **Resume — fires the moment the balance re-crosses the floor.** No headroom margin, no ack
   latch. Every signal reflects a real crossing; flapping driven by real payments and real spend is
   the tenant's economics, not ours to smooth.
5. **Negative balances — nothing automatic, full visibility.** A never-topped-up balance stays
   negative indefinitely. The balance API gains `negative_since`; ops gains an aged-negatives
   metric. Collections belong to the tenant (Stripe owns dunning in our split). No reminder
   events, no auto-close.
6. **Past-limit report — both surfaces.** Per-event stop-context is exposed and filterable on the
   existing event/analytics queries, AND a dedicated report endpoint returns the itemized
   past-limit story per customer, grouped by stop episode with totals per limit.

## Inherited inputs (decided upstream; folded in, not re-opened)

- Estimate/hold machinery **kept** as arrival-time crossing detection, per-tenant opt-in/out
  (flag shape + repair spec → #23; evidence in #21). Its accept-time *reject* branch is removed
  here (§B).
- Per-task cap counts **at settle with exact costs** — no accept-time estimate feed (#12).
- Signals are **durable at-least-once**: Postgres is the guaranteed lane, Redis the fast lane;
  catch-up after a blind window is bottom-line only (#11). Delivery rails → #23.
- Durable floor-crossing detection at the **configured** floor; reconcile gains the power to SET
  stop state; fast-lane/durable-lane dedup so a crossing never double-fires (#11 riders, §C).
- ADR-002 (floor is an application invariant, never a DB CHECK) test pin + "Min balance" glossary
  re-word (#13 riders, §I/§J).

## Change list

### A. Sync ingest path — caps become signals

Today the tipping event is rolled back and never billed: `record_usage` wraps pricing + run
accumulate + task check in a savepoint (`apps/metering/usage/services/usage_service.py:212`);
`RunService.accumulate_cost` raises `HardStopExceeded` before saving on run-cap or floor-snapshot
breach (`apps/platform/runs/services.py:88-103`) and `RunNotActive` on a non-active run
(`services.py:81-82`); the endpoint answers 429/409 and kills the run
(`api/v1/metering_endpoints.py:75-107`, batch parity 170-203).

- `accumulate_cost` **never raises on limits**: it always persists the true total and returns
  crossing verdicts (`crossed_run_cap`, `crossed_floor_snapshot`) alongside the run. Merge its
  semantics with `accumulate_cost_settled` (`services.py:116-138`), which already tolerates
  non-active runs and carries no limit checks — one accumulate primitive, always-record, verdicts
  out. `RunNotActive` is retired as an exception; a non-active run is a verdict
  (`run_not_active=True`), not a refusal.
- `check_task_cost` (`apps/billing/gating/services/live_ledger_service.py:408-441`): the
  `_TASK_CHECK_INCR` Lua (122-130) **always increments** — the "return `-new`, touch nothing"
  reject branch goes. Crossing returns a verdict; the `HardStopExceeded` raise (437-441) goes.
  The rejected-events-don't-count property is deliberately inverted: every event counts, including
  the tipping one (its cost is real).
- Endpoint: the `except HardStopExceeded` / `except RunNotActive` handlers
  (`metering_endpoints.py:75-107`) are deleted. On a crossing verdict, the existing kill flow runs
  unchanged (`RunService.kill_run` in its own transaction + `RunLimitExceeded(scope="run")` on the
  winning transition — same shape as `metering_endpoints.py:82-94`), and the response is **HTTP 200**
  with `stop=True`, `stop_reason` (`run_cost_cap` / `task_cost_cap` / `run_not_active` / customer
  reasons), `stop_scope` (`run` / `task` / `customer`), and `stop_context` (§F). Batch parity
  mirrors this per item.
- `HardStopExceeded` survives only as an internal type if useful; nothing user-facing throws it.
- The customer-wide live debit (`usage_service.py:270-272`) is now reached on every event —
  previously skipped when a cap raised. This is correct under one-rule (the spend is real) and
  removes the old "capped events invisible to the live counter" skew.

### B. Async ingest path — the last accept-time door closes

Today the only async hard reject is the per-run cap inside the `_ACQUIRE` Lua
(`apps/billing/gating/services/hold_service.py:106-109`, reason wired at 157-159, endpoint
664-668), plus the accept-time `run_not_active` refusal for dead runs
(`api/v1/metering_endpoints.py:561-569`).

- `_ACQUIRE` **always holds**: the `newrun > cap` reject branch becomes a crossing flag returned
  with the hold. The crossing item is held, appended, settled, and billed like any other; the flag
  routes to the existing async run-kill parity block (`metering_endpoints.py:704-718`), which is
  unchanged. No `RawIngestEvent` is ever skipped for limit reasons.
- The dead-run accept-time reject goes: events for a non-active run are accepted, held, and tagged
  (`stop_reason=run_not_active` verdict + stop-context at settle). Settle already tolerates dead
  runs (`accumulate_cost_settled`) — accept now matches settle.
- The floor-crossing detection in `HoldService.acquire` (threshold compare + `_set_stop`,
  `hold_service.py:232-253`) is unchanged in shape — it was already cooperative
  (never rejects, I3) — and is now formally the **arrival-time fast trigger** of the signal suite.
  Per-tenant opt-in/out flag and live-balance auto-repair are #23's spec; this spec only requires
  that with the machinery off, the durable lane (§C) still produces the stop/resume signals, later.
- Poison-path unchanged: repeated settle failure still dead-letters to `failed` + hold release
  (`apps/metering/usage/tasks.py:78-92`) — that's a pipeline fault, not a billing wall, and
  `reconcile_usage_drawdowns` remains its repair.

### C. Floor crossing — durable lane detects at the configured floor; both lanes dedup

Today the Redis fast lane sets `ubb:stop:{owner}` when the live balance crosses `-min_balance`
(`live_ledger_service.py:244-246, 274-291`), but the durable lane watches the wrong line:
`billing.balance_overage` fires on the zero crossing (`apps/billing/handlers.py:104-108`), and
suspension fires at the floor (`handlers.py:109-115`) with no tie to the stop-signal family.
`reconcile_prepaid` can only *clear* a stop (`live_ledger_service.py:499-501`), never set one.

- **New durable signal ledger** — the dedup bookkeeping both #11 riders point at: a per-owner
  Postgres row (e.g. `StopSignalState`: owner, current state stop/clear, `episode_seq`, reason,
  transitioned_at) written with the same winning-insert/transition-guard pattern as
  `balance_overage`. **Every** stop/resume emission — fast lane (`_set_stop`,
  `live_ledger_service.py:293-361`), durable drawdown handler, reconcile — routes through a
  transition on this row; only the winning transition emits the outbox event. A crossing observed
  by both lanes fires exactly one signal; the row's `episode_seq` is the stop-episode id the
  report (§G) and stop-context (§F) key on.
- **Durable handler detects the configured floor**: `handle_usage_recorded_billing` gains a
  floor-crossing branch (`old >= -limit and new < -limit`) that drives the stop transition —
  the guaranteed lane for the stop signal, independent of Redis health (#11: a crossing while
  blind signals late, never lost). The zero-crossing `balance_overage` event **stays** as the
  early warning it was built to be (Stage D); it is not part of the stop/resume pair.
- **Suspension folds into the stop family**: the `< -limit` suspend branch is the durable stop
  state — `CustomerSuspended(reason="min_balance_exceeded")` keeps its name and its start-gate
  effect, but its emission rides the same transition guard, so floor-stop and suspension can never
  disagree or double-fire.
- **Reconcile gains SET power**: `reconcile_prepaid` / `reconcile_postpaid`
  (`live_ledger_service.py:474-531`) get the missing `else`: when the reconciled balance IS past
  the floor, drive the stop transition (bottom-line catch-up — at most one net stop/resume per
  owner per #11). Today's clear-only recovery keeps working through the same guard.

### D. Resume signal — new, paired with stop

No resume exists today: `_clear_stop` silently deletes the Redis key
(`live_ledger_service.py:363-365`) at three sites — credit lifting balance over the floor (462),
prepaid reconcile recovery (500), postpaid recovery/rollover (530).

- New outbox event type **`stop.cleared`** (`StopCleared`), webhook-deliverable, catalog-registered
  beside `StopFired` (`catalog.py:37`), carrying owner, reason, `episode_seq` of the stop it
  closes, and the balance at clearance. Emitted at all three `_clear_stop` sites **through the §C
  transition guard** (a clear that didn't win the transition emits nothing).
- Fires **the moment** the balance re-crosses the floor (decision 4) — the `credit()` path
  (`live_ledger_service.py:450-462`, fed by Stripe top-up webhooks and prepaid over-hold settles)
  is the fast lane; reconcile and the durable handler are the guaranteed lane.
- `read_stop` (`live_ledger_service.py:391-405`) and ack verdicts are unchanged in shape — resume
  is observable as `stop=False` on the next response, plus the pushed event.
- Delivery guarantees (best-effort → guaranteed, the orphaned-`StopFired` fix) are #23's spec;
  `stop.cleared` rides whatever rails #23 lands, same as `stop.fired`.

### E. Modes — two positions

`Tenant.enforcement_mode` (`apps/platform/tenants/models.py:80-82`, choices at 41-45) drops
`advisory`. Migration maps any existing `advisory` tenant to `off` (advisory promised "never
act"; `off` is the honest nearest state — and no advisory tenant exists in prod).

- `apps/platform/tenants/flags.py`: `enforcement_on` and `enforcing` collapse into one predicate
  (keep one name, alias or delete the other; every call site listed in flags.py's readers —
  `live_ledger_service.py:218,396,450,480,510`, `hold_service.py:193,313,329`,
  `usage_service.py:159`, `risk_service.py:22,77`, `handlers.py:45`, `gating/tasks.py:49`,
  `runs/tasks.py:42,85,94` — simplifies to it).
- In `enforcing`: full signal suite + state changes (run flips, start-gate refusals, suspension,
  reapers). In `off`: no counters, no signals, no tagging — Tier-1 byte-for-byte.
- Docs/glossary updates in §I. The guarantee artifact's precondition line ("enforcement_mode ships
  off by default") stays true.

### F. Stop-context tagging — the past-limit schema

New **system-owned** nullable JSONField `stop_context` on `UsageEvent`
(`apps/metering/usage/models.py:9-72`) — not tenant `tags` (validated tenant namespace,
`usage_service.py:77-94`, collision risk) and not free-form `metadata`. GIN-index it (or a partial
index on non-null) for the report query. Set at creation time — record (sync) / settle (async) —
and immutable with the event (save guard at models.py:66-69 already enforces this).

Schema (all fields required when present):

```json
{
  "limit": "run_cost_cap | task_cost_cap | customer_floor | suspended | run_not_active",
  "stop_scope": "run | task | customer",
  "tripped_at": "<ISO8601 — when the limit tripped>",
  "episode_seq": "<int — §C episode id; null for run/task scopes>",
  "run_id": "<uuid|null>", "task_id": "<string|null>",
  "arrived_after": true
}
```

An event that *is* the tipping event carries `arrived_after: false` (it tripped the limit); every
later event in the episode carries `true`. Multiple simultaneous limits (run cap + customer floor)
→ array or the most specific scope wins: **spec choice: array of contexts**, so nothing is lost.

### G. Report + query surfaces

- **Event/analytics queries** (`metering_endpoints.py` events listing + analytics filters around
  771-772, 1002-1014) gain `stop_context` in responses and a filter (`past_limit=true`,
  `stop_scope=`, `episode_seq=`).
- **New endpoint** `GET /api/v1/customers/{customer_id}/past-limit-report?since=&until=`:
  episodes (from `StopSignalState` history + run/task trips), each with the tripping limit,
  `tripped_at`, resume time (if any), itemized events (id, effective_at, billed_cost_micros,
  arrived_after), and totals per limit — "exactly what was spent past the limit and why" in one
  call. SDK helper to match.
- **Balance surface**: `GET /customers/{id}/balance` (`api/v1/billing_endpoints.py:40-52`) gains
  `negative_since` (null when ≥ 0; set from the wallet's last ≥0→<0 transition, which
  `handle_usage_recorded_billing` already detects at `handlers.py:104`). Ops metric: count +
  max-age of negative balances, on the existing ops/ingest-health surface.

### H. Response schema + SDK

- `RecordUsageResponse` (`api/v1/schemas.py:91-112`) and per-item `IngestBatchResponse` verdicts
  (80-88): **`hard_stop` is retired** (nothing is hard anymore); `stop`/`stop_reason`/`stop_scope`
  stay and gain `stop_context`. `suspended` stays. HTTP 200 on every recorded event.
- SDK: the sync client's 429/409 handling goes; the documented contract becomes "check `stop` on
  every ack and stop the named scope" (the cooperative model, unchanged in spirit). The launch
  stop-propagation contract stays webhook push + ack-verdict + `pre_check` (#12).

### I. Doc + glossary updates (ride along in the implementing PR)

- `apps/billing/CONTEXT.md:40-42` **Min balance (wallet floor)**: re-word from "before its owner is
  suspended" to signal-point semantics — the predetermined line whose crossing fires stop (and
  whose re-crossing fires resume); events past it still land and bill (#13 rider).
- **Killed (run)** glossary entry: redefine per decision 2. **Enforcement mode** entry
  (`CONTEXT.md:59-61`): two positions. **Customer-wide stop flag** (55-57): still accurate
  ("blocks new runs until recovery"), add the resume pairing.
- ADR-002 cross-reference: this spec is the enforcement-side implementation of the
  ledger-records/policy-reacts doctrine.

### J. Test pins (the spec's definition of done)

1. Tipping event lands and bills — sync run cap, sync task cap (run-less too), async run cap.
2. Events on a killed run land, bill, count into `run.total_cost_micros`, and carry stop-context.
3. Below-floor event lands and bills; `Wallet` carries no floor CHECK (ADR-002 pin, #13).
4. Durable lane fires the stop at the **configured** floor with Redis down; fast lane and durable
   lane together fire **exactly one** stop per crossing (episode dedup).
5. `reconcile_prepaid` SETs a missed stop (not just clears a stale one).
6. Resume fires at the exact re-cross via credit, reconcile, and durable paths — once per episode.
7. Every recorded event answers 200; no code path returns 429/409 for a usage report.
8. `advisory` migration → `off`; two-position choices enforced; `off` is Tier-1 byte-for-byte.
9. Past-limit report reconstructs an episode end-to-end (stop → itemized events → totals → resume).
10. `negative_since` set on ≥0→<0, cleared on recovery; ops metric counts aged negatives.
11. Zero-crossing `balance_overage` still fires at zero (early warning unaffected).

## Consequences routed to other tickets

- **#15 (proof plan):** evidence bar is now **three legs** — load, chaos, live Stripe money test.
  The soak leg is dropped with advisory mode (user-confirmed 2026-07-15). Load-test assertions
  from #10 unchanged: zero lost/mis-tagged events (hard), signal-latency p99 (threshold #15's).
- **#23 (delivery + repair):** inherits `stop.cleared` as a second guaranteed event type, the §C
  transition guard as the emission choke point, resume-at-re-cross semantics, and the two-mode
  model (no advisory rail to spec).
- **#22/#26 (machinery walkthrough / gap analysis):** §B formalizes the machinery as the
  arrival-time fast trigger; walkthrough proceeds against this spec's shape.
- **#16 (guarantee artifact):** headline unchanged; preconditions line stays true; soak-leg
  references, if any, need the three-leg wording.

## Out of scope here

Delivery rails, orphan-hold auto-repair, machinery opt-in/out flag shape (#23) · machinery
walkthrough (#22, gap analysis #26) · proof-plan thresholds, environment shape, poller (#15) ·
executing any of this (past the map's destination).
