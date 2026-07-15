# One-rule enforcement — spec (ready to hand off)

**Date:** 2026-07-15 · **Origin:** map [#9](https://github.com/ashcochrane/ubb/issues/9), tickets
[#18](https://github.com/ashcochrane/ubb/issues/18) (one-rule contract) +
[#28](https://github.com/ashcochrane/ubb/issues/28) (two floors + task/subtask model) ·
**Status:** decisions locked with the user; implementation not started.

**Re-issued 2026-07-15** (ticket [#31](https://github.com/ashcochrane/ubb/issues/31), per #28
decisions 6+7): this spec now speaks the **final task/subtask vocabulary** throughout and folds in
#28's seven decisions where they touch the same surfaces, so implementation builds every endpoint,
event, and reason code exactly once under its final name. The run-vocabulary draft survives only in
this file's git history; **no surface below is ever built under a pre-rename name.** All file:line
anchors verified against main on 2026-07-15 (re-verified during the re-issue).

The one-rule model (decided in [#10](https://github.com/ashcochrane/ubb/issues/10)): **every usage
event that reaches UBB is priced, recorded, and billed immediately — no refusals of usage reports,
no parking states, anywhere.** The balance always shows reality, including negative. Limits and the
wallet floors are **signal points** (stop + resume), never billing walls. Refusing *new task
starts* at the start-gate stays — refusing work that hasn't happened is consistent; refusing to
record work that has is not.

## The clean cut — final vocabulary

One rename, all surfaces at once, no aliases, no dual-emit window (#28 decision 6): **run → task**;
today's label-"task" machinery retires, freeing the word; the new child object is **subtask**.

| Surface | Today (dies at the cut) | Final |
| --- | --- | --- |
| Unit of work | `Run` model (`apps/platform/runs/models.py:14`, `db_table="ubb_run"`) | `Task` model, app dir `apps/platform/tasks/`, `db_table="ubb_task"` |
| Child unit | — (label counter only, no object) | **Subtask** = a `Task` row with `parent` set (§A) |
| Service | `RunService` (`apps/platform/runs/services.py:33`): `create_run` / `accumulate_cost` + `accumulate_cost_settled` / `kill_run` / `complete_run` | `TaskService`: `create_task` / one `accumulate_cost` primitive (§B) / `kill_task` / `complete_task` |
| Limit field | `Run.cost_limit_micros` — billed (`models.py:40`) | `Task.provider_cost_limit_micros` — COGS (§A) |
| Running totals | `Run.total_cost_micros` — billed only (`models.py:34`) | `Task.total_billed_cost_micros` + `Task.total_provider_cost_micros` (§A) |
| Floor snapshot | `Run.hard_stop_balance_micros` (`models.py:41`) | `Task.floor_snapshot_micros` — "hard stop" vocabulary retired with the 429 |
| Unit identity on events | `UsageEvent.run` FK (`apps/metering/usage/models.py:35-38`) + label `Run.task_id` (`models.py:54`) + tag fallback (`usage_service.py:201-207`) | `UsageEvent.task` FK naming the exact unit (task or subtask); label column deleted; tags analytics-only (§A) |
| API request fields | `run_id` (record/batch/ingest items); `start_run` / `run_metadata` / `external_run_id` (pre-check) | `task_id`; `start_task` / `task_metadata` / `external_task_id` + `parent_task_id` + `provider_cost_limit_micros` (§A) |
| Routes | `POST /api/v1/metering/runs/{run_id}/close` (`metering_endpoints.py:849-850`) | `POST /api/v1/metering/tasks/{task_id}/close` |
| Response fields | `run_id`, `run_total_cost_micros`, `hard_stop` (`api/v1/schemas.py:98-100`) | `task_id` + `parent_task_id`, `task_total_billed_cost_micros` + `task_total_provider_cost_micros`; `hard_stop` retired (§J) |
| Events | `run.limit_exceeded` / `RunLimitExceeded(scope="run"\|"task")` (`catalog.py:39`, `events/schemas.py:292`) | `task.limit_exceeded` / `TaskLimitExceeded` and `subtask.limit_exceeded` / `SubtaskLimitExceeded` — two types, ids explicit; the scope field dies with the split (§B) |
| Reason vocabulary | 429 `hard_stop_exceeded` with reasons `cost_limit_exceeded` / `balance_floor_exceeded` / `task_limit_exceeded`; 409 `run_not_active` | HTTP 200 family — `stop_reason` / `stop_context.limit` ∈ `task_limit` \| `subtask_limit` \| `customer_floor` \| `suspended` \| `task_not_active` (§H) |
| `stop_scope` | `run` \| `task` \| `customer` | `task` \| `subtask` \| `customer` |
| Redis keys | `ubb:runcost:{run_id}` (`hold_service.py:147`) · `ubb:taskcost:{tenant}:{owner}:{task_id}:{YYYY-MM}` (`live_ledger_service.py:173`) | **both retired unreplaced** (§B/§C) — after the cut no task-named Redis key exists |
| Config | `RiskConfig.max_cost_per_task_micros` (`apps/billing/gating/models.py:14`) | deleted; `RiskConfig.default_task_provider_cost_limit_micros` + `default_subtask_provider_cost_limit_micros` (§A); soft floor `soft_min_balance_micros` on `CustomerBillingProfile` + `BillingTenantConfig` (§F) |
| SDK | `start_run` / `close_run` / `record_usage(run_id=)` (`ubb-sdk/ubb/client.py:143,206,158`) | `start_task(..., parent_task_id=None, provider_cost_limit_micros=None)` / `close_task` / `record_usage(task_id=)` (§J) |
| Exceptions on the wire | `HardStopExceeded` / `RunNotActive` (`runs/services.py:10,24`) | nothing — crossings are verdicts, not exceptions (§B) |

**Why one cut is safe, and the referent-hygiene check** (#28 decision 6): no tenant is live, no
environment exists beyond docker-compose, and the SDK ships from this repo — the contracts are
pinned by nobody, so this is the cheapest the cut will ever be. No name spans eras with two
meanings: the old 429 reason string `task_limit_exceeded` (label cap) retires with the 429 itself
and is deliberately **not** reused — the new family says `task_limit` / `subtask_limit`. The
`ubb:taskcost:*` and `ubb:runcost:*` key families retire with no task-named successor, so lingering
TTL'd keys (62-day TTL, `live_ledger_service.py:52`) can never be misread by new code. The
re-issued `stop_scope` value `task` refers only to the renamed unit — the label machinery that once
answered to "task" is deleted in the same change, and its old spellings appear nowhere.

## Decisions locked in this spec's grilling (2026-07-15, ticket #18)

1. **Wire contract — success + stop signal.** Every recorded event returns a normal success
   response; the stop instruction rides response fields. HTTP 429 `hard_stop_exceeded` and
   409 `run_not_active` are retired for usage reports. Errors remain only for requests that
   genuinely didn't record (auth, malformed payload, unknown customer).
2. **Task lifecycle — keep `killed`, keep counting.** The task still flips to `killed` the moment
   its limit trips (the flip is the durable record that the signal fired). Events arriving
   afterwards land, bill, and keep adding to its totals. No status rename; the glossary redefines
   *killed* as "stop signal fired; late events still land and count."
3. **Modes — `advisory` is dropped entirely.** `Tenant.enforcement_mode` becomes two-position:
   `off` / `enforcing`. The whole signal suite (stop/resume signals, stop-context tagging, task
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

## Decisions folded from the two-floor / task-subtask ticket (#28, 2026-07-15)

7. **Soft floor — refuse new starts + webhook pair; never a billing wall** (→ §F). A tenant-chosen
   line on each end customer's wallet past which running tasks may complete but new ones must not
   start. Durable lane only; no second Redis threshold; **no ack changes**. The hard floor needs no
   build — today's `min_balance` floor + stop flag under the one-rule model *is* it (#26).
8. **Subtask = real child object; two levels, built to deepen** (→ §A). Registered like a task:
   explicit start/end, its own record, its own per-instance limit, its own kill/close story. Spend
   rolls up into the parent's limit; a subtask crossing its limit is killed **alone**. The
   month-scoped, owner-global label counter retires; monthly-budget needs stay covered by
   `BudgetConfig` (`apps/billing/gating/models.py:30`).
9. **Limits are passed at start, tenant default as fallback** (→ §A). Absent both, the unit is
   uncapped and no signal ever fires. Named/registered task types deliberately deferred.
10. **Task/subtask limits are COGS-denominated; wallet floors stay billed** (→ §A). Starting a
    unit with a limit is coverage-gated on `Tenant.require_cost_card_coverage`. Records and
    responses carry **both** running totals, denominationally explicit; only the provider total
    races the limit. Async counting stays settle-time exact (#12) — which retires the accept-time
    cap lane wholesale (§C).
11. **The tag fallback dies — explicit only** (→ §A). Limits attach only to registered
    tasks/subtasks; an event references one explicitly or belongs to none.
12. **Rename = one clean cut** (→ the vocabulary table above).
13. **Sequencing — spec first.** This re-issue (ticket #31) precedes implementation; the
    delivery/auto-repair spec (#23) is written against this document.

## Inherited inputs (decided upstream; folded in, not re-opened)

- Estimate/hold machinery **kept** as arrival-time crossing detection for the wallet floor,
  per-tenant opt-in/out (flag shape + repair spec → #23; evidence in #21). Its accept-time
  *reject* branch is removed here (§C).
- Task/subtask limits count **at settle with exact costs** — no accept-time estimate feed
  (#12, reaffirmed by #28's COGS denomination).
- Signals are **durable at-least-once**: Postgres is the guaranteed lane, Redis the fast lane;
  catch-up after a blind window is bottom-line only (#11). Delivery rails → #23.
- Durable floor-crossing detection at the **configured** floor; reconcile gains the power to SET
  stop state; fast-lane/durable-lane dedup so a crossing never double-fires (#11 riders, §D).
- ADR-002 (floor is an application invariant, never a DB CHECK) test pin + "Min balance" glossary
  re-word (#13 riders, §K/§L).

## Change list

### A. The object model — task, subtask, limits

One model. `Run` is renamed to **`Task`** (RenameModel + RenameField migrations, `ubb_run` →
`ubb_task`; app dir `apps/platform/runs/` → `apps/platform/tasks/`, `reasons.py`/`tasks.py`/tests
ride along; FK `related_name` `runs` → `tasks`). A **subtask is a `Task` row with a `parent`
self-FK set**. Launch validation permits exactly one level of containment (the parent must itself
be parentless); the generic parent column makes deepening later a validation change, not a remodel
(#28 decision 8). No live tenant exists, so these are plain rename migrations with no data
concerns.

- **Fields**: `total_cost_micros` (billed-only, `models.py:34`) splits into
  `total_billed_cost_micros` + `total_provider_cost_micros` — both maintained on every accumulate,
  denominationally explicit. `cost_limit_micros` (`models.py:40`) becomes
  **`provider_cost_limit_micros`**: a task/subtask limit measures **provider cost** (what the job
  burns), full stop; only the provider total races it. `hard_stop_balance_micros` (`models.py:41`)
  → `floor_snapshot_micros`. The label column `Run.task_id` (`models.py:54`) is **deleted**.
  `UsageEvent.run` (`apps/metering/usage/models.py:35-38`) → `UsageEvent.task`, naming the exact
  unit the event belongs to (task or subtask).
- **Registration**: `POST /api/v1/billing/pre-check` (`api/v1/billing_endpoints.py:292-302`) with
  `start_task=True` starts a task; adding **`parent_task_id`** registers a subtask under it.
  Registering under a non-active parent or under a subtask (at launch) is refused —
  `parent_task_not_active` / `subtask_depth_exceeded`. Start-gate refusals are legitimate: they
  refuse work that hasn't happened, never a usage report.
- **Limits at start** (#28 decision 9): the start call may pass `provider_cost_limit_micros`;
  absent that, the tenant default applies — `RiskConfig.default_task_provider_cost_limit_micros` /
  `default_subtask_provider_cost_limit_micros` (new, null = no default), replacing the deleted
  `max_cost_per_task_micros` (`apps/billing/gating/models.py:14`). Absent both, the unit is
  uncapped and no signal ever fires. (Today's copy-from-tenant-config-at-creation shape,
  `runs/models.py:37-41`, survives — only the source fields and denomination change.)
- **Coverage gate** (#28 decision 10): starting a unit whose limit resolves non-null (explicit
  *or* default) is **refused** with reason `cost_coverage_required` unless
  `Tenant.require_cost_card_coverage` is on (`apps/platform/tenants/models.py:69`) — a COGS limit
  over uncovered events would silently count 0, and refusing a start is not a usage report.
- **Rollup** (#28 decision 8): an event attributed to a subtask accumulates into the subtask's
  totals **and** its parent's (containment: the parent sees everything). The parent's limit races
  the rolled-up provider total.
- **Kill semantics**: a subtask crossing its own limit fires `subtask.limit_exceeded` scoped to
  that subtask and flips **it alone** to `killed` — the parent keeps running and counting. A
  parent crossing its limit fires `task.limit_exceeded`, flips the parent to `killed`, and
  cascades the flip to its active subtasks (containment cuts downward, never upward). Killed is a
  signal point, not a wall (decision 2). Today's kill-the-whole-run-on-label-cap behavior dies
  with the label machinery.
- **Close**: `complete_task` (today `complete_run`, `runs/services.py:164`) via
  `POST /api/v1/metering/tasks/{task_id}/close`; closing a parent auto-completes its active
  subtasks.
- **The tag fallback dies** (#28 decision 11): the `task → service → agent` inference
  (`apps/metering/usage/services/usage_service.py:201-207`) is deleted. The `task_id` request
  field is the only unit attribution; `tags` remain free-form analytics labels
  (`usage/models.py:34`) and never silently become a limited thing.

### B. Sync ingest path — limits become signals

Today the tipping event is rolled back and never billed: `record_usage` wraps pricing + task
accumulate + label-cap check in a savepoint (`usage_service.py:212`); `accumulate_cost` raises
`HardStopExceeded` before saving on unit-limit or floor-snapshot breach
(`apps/platform/runs/services.py:89-103`) and `RunNotActive` on a non-active unit
(`services.py:82`); the endpoint answers 429/409 and kills the unit
(`api/v1/metering_endpoints.py:75-107`, batch parity 170-203).

- `accumulate_cost` **never raises on limits**: it always persists both true totals (billed +
  provider, §A) and returns crossing verdicts — `crossed_task_limit`, `crossed_subtask_limit`,
  `crossed_floor_snapshot`, `task_not_active` — alongside the unit. Merge its semantics with
  `accumulate_cost_settled` (`services.py:115-138`), which already tolerates non-active units and
  carries no limit checks — **one accumulate primitive**, always-record, rollup to the parent
  inside it, verdicts out. `RunNotActive` is retired as an exception; a non-active unit is a
  verdict, not a refusal.
- **The label-cap check retires wholesale** (superseding the earlier draft's always-increment
  conversion — the counter's object is gone): the `check_task_cost_cap` call
  (`usage_service.py:234-236`), `check_task_cost`
  (`apps/billing/gating/services/live_ledger_service.py:408-441`), the `_TASK_CHECK_INCR` Lua
  (`live_ledger_service.py:122-130`), and the `ubb:taskcost:*` key family
  (`live_ledger_service.py:173`) are deleted. Subtask limit detection is the accumulate primitive
  on the subtask's own row — no Redis counter, no new store (#26).
- Endpoint: the `except HardStopExceeded` / `except RunNotActive` handlers
  (`metering_endpoints.py:75-107`) are deleted. On a crossing verdict, the existing kill flow runs
  unchanged (`kill_task` in its own transaction — today `kill_run`, `services.py:140`, already
  idempotent on the winning transition — emitting `task.limit_exceeded` or
  `subtask.limit_exceeded` per §A), and the response is **HTTP 200** with `stop=True`,
  `stop_reason` (`task_limit` / `subtask_limit` / `task_not_active` / customer reasons),
  `stop_scope` (`task` / `subtask` / `customer`), and `stop_context` (§H). Batch parity mirrors
  this per item.
- Event types: `run.limit_exceeded` (`catalog.py:39`, `RunLimitExceeded` at
  `events/schemas.py:292` with its `scope` field) is replaced by **two** catalog-registered types:
  `TaskLimitExceeded` (`task.limit_exceeded`: tenant/customer/billing-owner ids, `task_id`,
  `external_task_id`, `reason`, both totals, `provider_cost_limit_micros`) and
  `SubtaskLimitExceeded` (`subtask.limit_exceeded`: the same plus `subtask_id` +
  `parent_task_id`).
- `HardStopExceeded` (`services.py:10`) survives only as an internal type if useful; nothing
  user-facing throws it.
- The customer-wide live debit (`usage_service.py:270-272`) is now reached on every event —
  previously skipped when a cap raised. This is correct under one-rule (the spend is real) and
  removes the old "capped events invisible to the live counter" skew. It still passes
  `billed_cost_micros` — wallet-shaped things stay billed (#28 decision 10).

### C. Async ingest path — the last accept-time door closes

Today the only async hard reject is the per-unit cap inside the `_ACQUIRE` Lua
(`apps/billing/gating/services/hold_service.py:106-109`, reason wired at 157-159, endpoint
664-668), counting **billed estimates** into `ubb:runcost:{run_id}` (`hold_service.py:147`), plus
the accept-time refusal for dead units (`api/v1/metering_endpoints.py:561-569`).

- **The accept-time unit-cap lane retires unreplaced** (this supersedes the earlier draft's
  crossing-flag conversion): task/subtask limits are provider-cost-denominated (#28 decision 10),
  and exact provider cost exists only at settle — an accept-time compare of a billed estimate
  against a COGS limit would be denominationally dishonest. The `_ACQUIRE` Lua drops KEYS[2]; the
  `ubb:runcost:*` key family and its `_NO_RUN_SENTINEL` (`hold_service.py:66`) are deleted.
  `_ACQUIRE` **always holds**, against the wallet only. No `RawIngestEvent` is ever skipped for
  limit reasons.
- **Unit-limit detection moves to settle**: settle runs the one accumulate primitive (§B) with
  exact costs → the same verdicts, kill flow, and events as the sync path. The async kill parity
  block moves from accept (`metering_endpoints.py:704-718`) to settle. Signal latency for async
  unit limits is settle latency — accepted (#12: settle-time exact); the wallet floor keeps its
  arrival-time fast trigger (below).
- The dead-unit accept-time reject goes: events for a non-active unit are accepted, held, and
  tagged (`stop_reason=task_not_active` verdict + stop-context at settle). Settle already
  tolerates dead units — accept now matches settle.
- The floor-crossing detection in `HoldService.acquire` (threshold compare + `_set_stop`,
  `hold_service.py:232-253`) is unchanged in shape — it was already cooperative (never rejects,
  I3) — and is now formally the **arrival-time fast trigger** of the signal suite. Per-tenant
  opt-in/out flag and live-balance auto-repair are #23's spec; this spec only requires that with
  the machinery off, the durable lane (§D) still produces the stop/resume signals, later.
- Poison-path unchanged: repeated settle failure still dead-letters to `failed` + hold release
  (`apps/metering/usage/tasks.py:78-92`) — that's a pipeline fault, not a billing wall, and
  `reconcile_usage_drawdowns` remains its repair.

### D. Floor crossing — durable lane detects at the configured floor; both lanes dedup

Today the Redis fast lane sets `ubb:stop:{owner}` when the live balance crosses `-min_balance`
(`live_ledger_service.py:244-246, 274-291`), but the durable lane watches the wrong line:
`billing.balance_overage` fires on the zero crossing (`apps/billing/handlers.py:104-108`), and
suspension fires at the floor (`handlers.py:109-115`) with no tie to the stop-signal family.
`reconcile_prepaid` can only *clear* a stop (`live_ledger_service.py:499-501`), never set one.

- **New durable signal ledger** — the dedup bookkeeping both #11 riders point at: a Postgres row
  per owner **per signal family** (`StopSignalState`: owner, `family`, current state stop/clear,
  `episode_seq`, reason, transitioned_at; unique on (owner, family)) written with the same
  winning-insert/transition-guard pattern as `balance_overage`. Families at launch: `floor_stop`
  (this section + §E) and `soft_floor` (§F) — each with its own episode sequence, per #28
  decision 7. **Every** stop/resume emission — fast lane (`_set_stop`,
  `live_ledger_service.py:293-361`), durable drawdown handler, reconcile — routes through a
  transition on this row; only the winning transition emits the outbox event. A crossing observed
  by both lanes fires exactly one signal; the row's `episode_seq` is the stop-episode id the
  report (§I) and stop-context (§H) key on.
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

### E. Resume signal — new, paired with stop

No resume exists today: `_clear_stop` silently deletes the Redis key
(`live_ledger_service.py:363-365`) at three sites — credit lifting balance over the floor (462),
prepaid reconcile recovery (500), postpaid recovery/rollover (530).

- New outbox event type **`stop.cleared`** (`StopCleared`), webhook-deliverable, catalog-registered
  beside `StopFired` (`catalog.py:40`), carrying owner, reason, `episode_seq` of the stop it
  closes, and the balance at clearance. Emitted at all three `_clear_stop` sites **through the §D
  transition guard** (a clear that didn't win the transition emits nothing).
- Fires **the moment** the balance re-crosses the floor (decision 4) — the `credit()` path
  (`live_ledger_service.py:450-462`, fed by Stripe top-up webhooks and prepaid over-hold settles)
  is the fast lane; reconcile and the durable handler are the guaranteed lane.
- `read_stop` (`live_ledger_service.py:391-405`) and ack verdicts are unchanged in shape — resume
  is observable as `stop=False` on the next response, plus the pushed event.
- Delivery guarantees (best-effort → guaranteed, the orphaned-`StopFired` fix) are #23's spec;
  `stop.cleared` rides whatever rails #23 lands, same as `stop.fired`.

### F. Soft floor — refuse new starts + webhook pair, never a billing wall

New (#28 decision 7). The soft floor is a tenant-chosen line on each end customer's wallet: past
it, running tasks may complete but new ones must not start. It is **not** a stop signal on events
and changes **no ack** — the ack's `stop` keeps meaning exactly "stop sending" (hard-floor family
only, decision 1).

- **Config mirrors `min_balance` resolution**: new nullable `soft_min_balance_micros` on
  `CustomerBillingProfile` (beside `min_balance_micros`, `apps/billing/wallets/models.py:81`) and
  `BillingTenantConfig` (beside `apps/billing/tenant_billing/models.py:130`); customer override →
  tenant default, null/absent = no soft floor — a `get_customer_soft_min_balance` sibling of
  `get_customer_min_balance` (`apps/billing/queries.py:28-40`). Same orientation as
  `min_balance_micros`; must resolve to a line at or above the hard floor's. Set via the existing
  billing-profile API/SDK surfaces.
- **Start-gate refusal**: `RiskService.check` (`risk_service.py:7`) gains the soft-line compare
  beside the affordability check (`risk_service.py:55`); crossing refuses **new top-level task
  starts** with new reason **`soft_floor_reached`**, beside `insufficient_funds`. Subtask starts
  under a still-active parent pass — a contained child is a running task completing, which the
  soft floor explicitly permits.
- **Webhook pair from the durable lane**: `handle_usage_recorded_billing` gains a soft-line
  crossing branch (beside §D's) driving a transition on the `soft_floor` family of
  `StopSignalState` — the winning transition emits **`soft_floor.crossed`** (`SoftFloorCrossed`:
  tenant/customer/owner ids, balance, resolved soft-floor line, `episode_seq`); credit and
  reconcile paths drive the clearing transition, emitting **`soft_floor.cleared`**
  (`SoftFloorCleared`). **No second Redis threshold** — no fast lane; signal latency is outbox
  latency, accepted by #28. Both types are catalog-registered and ride #23's guaranteed rails
  beside `stop.fired`/`stop.cleared`.
- **Never a billing wall**: if work slips past the gate anyway (tenant bug, race), it lands and
  bills — the wallet is the truth of what happened. Soft-floor crossings tag no events (§H): work
  completing past the soft line is permitted by design, not "past limit".
- **The hard floor needs no build**: today's `min_balance` floor + stop flag under the one-rule
  model *is* the hard floor (#26); §D/§E are its hardening, not a new mechanism.

### G. Modes — two positions

`Tenant.enforcement_mode` (`apps/platform/tenants/models.py:80-82`, choices at 41-45) drops
`advisory`. Migration maps any existing `advisory` tenant to `off` (advisory promised "never
act"; `off` is the honest nearest state — and no advisory tenant exists in prod).

- `apps/platform/tenants/flags.py`: `enforcement_on` and `enforcing` collapse into one predicate
  (keep one name, alias or delete the other; every call site listed in flags.py's readers —
  `live_ledger_service.py:218,396,450,480,510`, `hold_service.py:193,313,329`,
  `usage_service.py:159`, `risk_service.py:22,77`, `handlers.py:45`, `gating/tasks.py:49`, and
  the task-app tasks (today `runs/tasks.py:42,85,94`) — simplifies to it).
- In `enforcing`: full signal suite + state changes (task flips, start-gate refusals, soft-floor
  gate + pair, suspension, reapers). In `off`: no counters, no signals, no tagging — Tier-1
  byte-for-byte.
- Docs/glossary updates in §K. The guarantee artifact's precondition line ("enforcement_mode ships
  off by default") stays true.

### H. Stop-context tagging — the past-limit schema

New **system-owned** nullable JSONField `stop_context` on `UsageEvent`
(`apps/metering/usage/models.py:9-72`) — not tenant `tags` (validated tenant namespace,
`usage_service.py:77-94`, collision risk) and not free-form `metadata`. GIN-index it (or a partial
index on non-null) for the report query. Set at creation time — record (sync) / settle (async) —
and immutable with the event (save guard at models.py:66-69 already enforces this).

Schema (all fields required when present):

```json
{
  "limit": "task_limit | subtask_limit | customer_floor | suspended | task_not_active",
  "stop_scope": "task | subtask | customer",
  "tripped_at": "<ISO8601 — when the limit tripped>",
  "episode_seq": "<int — §D episode id; null for task/subtask scopes>",
  "task_id": "<uuid|null>", "subtask_id": "<uuid|null — set when the unit is a subtask>",
  "arrived_after": true
}
```

An event that *is* the tipping event carries `arrived_after: false` (it tripped the limit); every
later event in the episode carries `true`. Multiple simultaneous limits (task limit + customer
floor) → array or the most specific scope wins: **spec choice: array of contexts**, so nothing is
lost. Soft-floor crossings never tag events (§F).

### I. Report + query surfaces

- **Event/analytics queries** (`metering_endpoints.py` events listing + analytics filters around
  771-772, 1002-1014) gain `stop_context` in responses and a filter (`past_limit=true`,
  `stop_scope=`, `episode_seq=`).
- **New endpoint** `GET /api/v1/customers/{customer_id}/past-limit-report?since=&until=`:
  episodes (from `StopSignalState` history + task/subtask trips), each with the tripping limit,
  `tripped_at`, resume time (if any), itemized events (id, effective_at, billed_cost_micros,
  provider_cost_micros, arrived_after), and totals per limit **in both denominations** — "exactly
  what was spent past the limit and why" in one call. Soft-floor episodes appear as
  crossed/cleared marker rows from the `soft_floor` signal family (no itemized events — nothing
  is "past limit" under a soft floor). SDK helper to match.
- **Balance surface**: `GET /customers/{id}/balance` (`api/v1/billing_endpoints.py:40-52`) gains
  `negative_since` (null when ≥ 0; set from the wallet's last ≥0→<0 transition, which
  `handle_usage_recorded_billing` already detects at `handlers.py:104`). Ops metric: count +
  max-age of negative balances, on the existing ops/ingest-health surface.

### J. Response schema + SDK

- `RecordUsageResponse` (`api/v1/schemas.py:91-112`) and per-item `IngestBatchResponse` verdicts
  (80-88): **`hard_stop` is retired** (nothing is hard anymore); `stop`/`stop_reason`/`stop_scope`
  stay and gain `stop_context`. `suspended` stays. `run_id` → `task_id` plus `parent_task_id`
  (null for a top-level task); `run_total_cost_micros` → `task_total_billed_cost_micros` +
  `task_total_provider_cost_micros` — the named unit's totals, both denominations (#28
  decision 10). HTTP 200 on every recorded event.
- `PreCheckResponse` (`schemas.py:16-22`): `run_id` → `task_id`, `cost_limit_micros` →
  `provider_cost_limit_micros`, `hard_stop_balance_micros` → `floor_snapshot_micros`; the
  `reason` vocabulary gains `soft_floor_reached`, `cost_coverage_required`,
  `parent_task_not_active`, `subtask_depth_exceeded` (§A/§F).
  `CloseRunResponse` (`schemas.py:320-324`) → `CloseTaskResponse` with both totals.
- SDK (`ubb-sdk/ubb/`): the sync client's 429/409 handling goes; the documented contract becomes
  "check `stop` on every ack and stop the named scope" (the cooperative model, unchanged in
  spirit). Renames per the vocabulary table: `start_task` (gains `parent_task_id`,
  `provider_cost_limit_micros`), `close_task`, `record_usage(task_id=)`,
  `pre_check(start_task=)`. The launch stop-propagation contract stays webhook push + ack-verdict
  + `pre_check` (#12).

### K. Doc + glossary updates (ride along in the implementing PR)

- `apps/billing/CONTEXT.md:40-42` **Min balance (wallet floor)**: re-word from "before its owner is
  suspended" to signal-point semantics — the predetermined line whose crossing fires stop (and
  whose re-crossing fires resume); events past it still land and bill (#13 rider). Note it is the
  **hard** floor of the two-floor pair.
- New glossary entries (via `/domain-modeling`): **Task** (renamed from Run — the registered unit
  of agent work), **Subtask** (parent-linked child unit; rollup; killed alone), **Soft floor**
  (refuse-starts line; webhook pair; never a billing wall). The **Run** entry and the label-era
  **task** sense are retired — the glossary must carry no trace of the old referents.
- **Killed (task)** glossary entry: redefine per decision 2. **Enforcement mode** entry
  (`CONTEXT.md:59-61`): two positions. **Customer-wide stop flag** (55-57): still accurate
  ("blocks new task starts until recovery"), add the resume pairing.
- ADR-002 cross-reference: this spec is the enforcement-side implementation of the
  ledger-records/policy-reacts doctrine.

### L. Test pins (the spec's definition of done)

1. Tipping event lands and bills — sync task limit, sync subtask limit, async task limit (at
   settle).
2. Events on a killed task land, bill, count into both totals, and carry stop-context.
3. Below-floor event lands and bills; `Wallet` carries no floor CHECK (ADR-002 pin, #13).
4. Durable lane fires the stop at the **configured** floor with Redis down; fast lane and durable
   lane together fire **exactly one** stop per crossing (episode dedup).
5. `reconcile_prepaid` SETs a missed stop (not just clears a stale one).
6. Resume fires at the exact re-cross via credit, reconcile, and durable paths — once per episode.
7. Every recorded event answers 200; no code path returns 429/409 for a usage report.
8. `advisory` migration → `off`; two-position choices enforced; `off` is Tier-1 byte-for-byte.
9. Past-limit report reconstructs an episode end-to-end (stop → itemized events → totals in both
   denominations → resume).
10. `negative_since` set on ≥0→<0, cleared on recovery; ops metric counts aged negatives.
11. Zero-crossing `balance_overage` still fires at zero (early warning unaffected).
12. Soft floor: crossing refuses a new top-level task start (`soft_floor_reached`) while a subtask
    start under an active parent passes and usage events keep landing and billing;
    `soft_floor.crossed`/`soft_floor.cleared` fire exactly once per crossing through the
    transition guard; acks never change on a soft-floor crossing.
13. Subtask killed **alone**: its limit trip flips only the subtask; the parent keeps running and
    counting. Subtask spend rolls up into the parent's provider total; the parent's limit trip
    kills the parent and cascades to active subtasks.
14. Denomination: only the provider total races a task/subtask limit — a billed total past the
    limit with the provider total under it fires nothing; both totals appear on the record and
    the response.
15. Coverage gate: a start whose limit resolves non-null (explicit or tenant default) is refused
    `cost_coverage_required` with coverage off, and passes with it on.
16. Tag fallback removed: an event carrying `tags={"task": ...}` and no `task_id` field gets no
    unit attribution, no limit, no kill — tags are analytics only.
17. The clean cut holds: no `run.limit_exceeded` in the catalog, no `ubb:taskcost:*` or
    `ubb:runcost:*` key ever written, `max_cost_per_task_micros` dropped by migration, and no
    API/SDK/event surface answers to a `run_*` name.

## Consequences routed to other tickets

- **#15 (proof plan):** evidence bar is now **three legs** — load, chaos, live Stripe money test.
  The soak leg is dropped with advisory mode (user-confirmed 2026-07-15). Load-test assertions
  from #10 unchanged: zero lost/mis-tagged events (hard), signal-latency p99 (threshold #15's).
- **#23 (delivery + repair):** written against this re-issued spec (#28 decision 13). Inherits
  `stop.cleared` **and the soft-floor pair** (`soft_floor.crossed`/`soft_floor.cleared`, own
  episode family) as guaranteed event types; the §D transition guard as the emission choke point
  for both families; resume-at-re-cross semantics; task/subtask-scoped stop signals riding the
  existing ack/webhook contract; the two-mode model (no advisory rail to spec); and the fact that
  async unit-limit signals are settle-time — there is no accept-time lane left to harden.
- **#16 (guarantee artifact):** headline unchanged; preconditions line stays true; the guarantee's
  surface list gains the soft floor and the subtask limit; vocabulary swaps run→task,
  label-task→subtask; soak-leg references, if any, need the three-leg wording.

## Out of scope here

Delivery rails, orphan-hold auto-repair, machinery opt-in/out flag shape (#23) · proof-plan
thresholds, environment shape, poller (#15) · named/registered task types (deferred by #28
decision 9) · nesting deeper than one level of containment (a later validation change, #28
decision 8) · executing any of this (past the map's destination).
