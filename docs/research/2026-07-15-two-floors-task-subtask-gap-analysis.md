# Gap analysis: two wallet floors, task/subtask renaming, fast-reaction layer

**Wayfinder research ticket #26 (map #9).** Verified against code at `b739fc6` (== `origin/main`).
All paths relative to the repo root. Classification: **built** (exists and matches the ask) /
**needs adjustment** (exists, semantics or naming differ) / **missing** (no concept in code).

---

## Area 1 — Two wallet floors per prepaid end customer

### 1a. What exists

| Item | Status | Evidence |
|---|---|---|
| Tenant-set per-customer wallet floor, customer override → tenant default → 0 | built | `CustomerBillingProfile.min_balance_micros` `ubb-platform/apps/billing/wallets/models.py:81`; tenant default `BillingTenantConfig.min_balance_micros` `ubb-platform/apps/billing/tenant_billing/models.py:130`; resolution `get_customer_min_balance` `ubb-platform/apps/billing/queries.py:28-40`; set via `PUT /billing/customers/{id}/billing-profile` `ubb-platform/api/v1/billing_endpoints.py:814-831` |
| HARD floor as a "stop emitting" signal measured on the customer's wallet | built (as the single floor) | Prepaid threshold = `-min_balance`: `LiveLedgerService._threshold` `ubb-platform/apps/billing/gating/services/live_ledger_service.py:274-275`; crossing on the sync path sets `ubb:stop:{owner}` `live_ledger_service.py:244-246` (key `:164-167`); async hold path crossing `ubb-platform/apps/billing/gating/services/hold_service.py:229-248` |
| Hard-floor signal channels | built (3 of 4) | Ack verdict `stop`/`stop_reason`/`stop_scope` on every 200 `ubb-platform/apps/metering/usage/services/usage_service.py:296-298`, `ubb-platform/api/v1/schemas.py:98-104`; `stop.fired` webhook on the unset→set transition `live_ledger_service.py:294-361`, catalog `ubb-platform/apps/platform/events/catalog.py:37`; Redis pub/sub `ubb:stopchan:{owner}` `live_ledger_service.py:347` — published but **no consumer endpoint** (SSE deferred per #12); `pre_check` poll refuses `customer_stopped` `ubb-platform/apps/billing/gating/services/risk_service.py:22-26` |
| In-flight events still land and get priced into the wallet (accepted overage) | built | Stop is cooperative, never rolls back the crossing event (I3): `live_ledger_service.py:214-217`; `record_usage` has no status/stop refusal — events price, record, debit regardless (`usage_service.py:167-298`; no suspension check in `ubb-platform/api/v1/metering_endpoints.py:45-114`) |
| Recovery when balance re-crosses the floor | built (flag clear), missing (resume event) | Credit clears the stop flag + durably un-suspends `live_ledger_service.py:443-468`, `:371-389`; hourly reconcile backstop `:499-501`; **no "safe to resume" event exists** — decided to build in #12, spec'd by #23 |
| Durable enforcement behind the fast flag | built | Async drawdown suspends owner at `new_balance < -limit`, emits `billing.customer_suspended` `ubb-platform/apps/billing/handlers.py:103-115`; start-gate refuses suspended/closed `risk_service.py:12-16` |
| SOFT floor: second, higher, tenant-set threshold gating only NEW task starts | **missing** | Exactly one prepaid threshold exists; `get_customer_min_balance` feeds both the start-gate (`risk_service.py:52-55`) and the stop-flag crossing (`live_ledger_service.py:274-275`) — same number, no second field anywhere |

### 1b. Candidate second-threshold concepts examined (none fits as-is)

| Candidate | Verdict | Evidence |
|---|---|---|
| `BudgetConfig` (cap, `hard_stop_pct`, `alert_levels`) | not a wallet floor | Monthly billed-SPEND cap per seat, % thresholds of `cap_micros` — spend-vs-cap, not balance-vs-floor `ubb-platform/apps/billing/gating/models.py:30-48` |
| `AutoTopUpConfig.trigger_threshold_micros` → `billing.balance_low` | closest in shape, gates nothing | Per-customer balance threshold, but coupled to auto-top-up config, fires only an async webhook after the drawdown lands `handlers.py:116-125`, schema `ubb-platform/apps/platform/events/schemas.py:117-124` |
| `BalanceCritical` schema | dead schema | Defined `schemas.py:127-133`, **never emitted anywhere in production code** |
| Per-run `hard_stop_balance_micros` | run-scoped, snapshot-based | Floor on `balance_snapshot − run_total`, tenant-level config snapshotted at run creation `ubb-platform/apps/platform/runs/models.py:39-41`, checked in `accumulate_cost` `ubb-platform/apps/platform/runs/services.py:96-103` — not a live wallet measure, not per-customer |

### 1c. What adding the soft floor concretely requires

| Piece | Size | Where |
|---|---|---|
| Config field(s): `soft_floor_micros` (or similar) on `CustomerBillingProfile` + tenant default on `BillingTenantConfig` + billing-profile API/SDK | additive | `wallets/models.py:76-91`, `tenant_billing/models.py:122-138`, `billing_endpoints.py:802-831` |
| Second comparison in the start-gate (durable wallet read already there) with a new refusal/advice reason | small | `risk_service.py:52-55` (add `soft_floor` branch beside `insufficient_funds`) |
| Optionally: a second live-ledger threshold + scoped flag (e.g. `ubb:softstop:{owner}`) + crossing/resume signal pair, if the soft verdict must also ride acks/webhooks | medium — rides #23's delivery rails | `live_ledger_service.py:256-291` resolves ONE threshold per (mode, owner); `_crossed`/`_set_stop`/`read_stop` and `HoldService.acquire`'s single-threshold batch check (`hold_service.py:229-248`) all assume one bound and one binary flag |

---

## Area 2 — Task/subtask renaming (away from "run") + cap basis

### 2a. Structural mapping: user's TASK ⊇ SUBTASK vs today's run ⊇ task-tag

| Item | Status | Evidence |
|---|---|---|
| User's TASK = "tenant-defined set of events between two points" | built as **Run** | Created via `POST /billing/pre-check` (`start_run`) `ubb-platform/api/v1/billing_endpoints.py:292-302` → `RiskService.check(create_run=True)` `risk_service.py:66-102`; per-instance cap `Run.cost_limit_micros` `runs/models.py:40`; accumulate+ceiling `runs/services.py:58-113`; heartbeat `runs/models.py:49-51`; reaper `ubb-platform/apps/platform/runs/tasks.py:68-129`; kill + fan-out `metering_endpoints.py:75-101`; close endpoint `metering_endpoints.py:849`; SDK `start_run`/`close_run` `ubb-sdk/ubb/client.py:143-155,206-208` |
| User's SUBTASK = a task within a task | **needs adjustment** — today's "task" is NOT run-scoped | Task identity = `tags['task']` falling back to `service`/`agent` `usage_service.py:207`; counter key `ubb:taskcost:{tenant}:{owner}:{task_id}:{YYYY-MM}` `live_ledger_service.py:170-173` — **month-scoped, per billing owner, summed ACROSS runs**. A "task" spans runs, outlives any one run, resets monthly. Not contained in a run |
| Subtask's "own limiting mechanism" | needs adjustment | Per-task cap exists but is ONE tenant-wide value for ALL task_ids: `RiskConfig.max_cost_per_task_micros` `ubb-platform/apps/billing/gating/models.py:14` (exposed `api/v1/schemas.py:518-519,539-540`). Enforced sync-only, enforcing-mode-only, reject-not-count `live_ledger_service.py:407-441`; breach kills the **whole run** (`metering_endpoints.py:78-94`), not just the "subtask" |
| Two-level hierarchy in the data model | **missing** | `Run` has no parent FK (`runs/models.py:14-84`); `UsageEvent` has `run` FK + free tags only (`ubb-platform/apps/metering/usage/models.py:35`); `RawIngestEvent.run_id` (`usage/models.py:139`). No nesting anywhere; renaming alone does not produce containment |
| Run↔task linkage today | broken/vestigial | `Run.task_id` (`runs/models.py:54`) is **never assigned in production code** — the only assignment of `task_id` is the local variable `usage_service.py:207`; `Run.task_id` is only read when emitting `RunLimitExceeded` (`metering_endpoints.py:92,188,312`, `runs/tasks.py:123`), so the event's `task_id` field is always `""` |
| Task-cap breach with no run_id | signal gap | `HardStopExceeded` can fire run-less; endpoint guards `kill_run` on `run_id` (`metering_endpoints.py:77-78`) — a run-less task-cap 429 emits **no fan-out event at all** (429 body only, `metering_endpoints.py:95-101`) |

### 2b. "run" naming blast radius (rename inventory)

| Surface | Items | Evidence |
|---|---|---|
| DB tables/columns | `ubb_run` table; `Run.*`; `UsageEvent.run_id` FK; `RawIngestEvent.run_id` | `runs/models.py:61`; `usage/models.py:35,139` |
| Models/services/exceptions | `apps/platform/runs/` app: `Run`, `RunService`, `RunNotActive`, `HardStopExceeded(run_id=…)`, `close_abandoned_runs`, `reap_stale_runs`, `reasons.py` | `runs/models.py`, `runs/services.py:10-31,33-177`, `runs/tasks.py:18,68` |
| API request/response fields | `pre-check`: `start_run`, `run_metadata`, `external_run_id` (`api/v1/schemas.py:11-13`), response `run_id`+`cost_limit_micros` (`:20`); usage payload `run_id` (`:47`); usage response `run_id`, `run_total_cost_micros` (`:98-99`); `POST /metering/runs/{run_id}/close` + `CloseRunResponse` (`metering_endpoints.py:849`, `schemas.py:320-324`); tenant config `run_cost_limit_micros` (`schemas.py:516,537`); error codes `run_not_active` (`metering_endpoints.py:102-107`) | as cited |
| Event types (wire contracts) | `run.limit_exceeded` (`schemas.py:304`) in the webhook catalog (`events/catalog.py:36`); `RunLimitExceeded.run_id/external_run_id/scope="run"` | `schemas.py:292-315` |
| Redis keys | `ubb:runcost:{run_id}` (`hold_service.py:146-147`); reason string `customer_wide_stop` etc. in `ubb:stop:{owner}` values | as cited |
| SDK | `pre_check(start_run=…)`, `start_run`, `close_run` (`ubb-sdk/ubb/client.py:113-155,206-208`, `metering.py:251-253`, `billing.py:153-162`); `PreCheckResult.run_id/cost_limit_micros`, `RecordUsageResult.run_id/run_total_cost_micros`, `CloseRunResult` (`ubb-sdk/ubb/types.py:8-15,26-27,60-64`); exceptions carrying `run_id` (`ubb-sdk/ubb/exceptions.py:34-61`); README | as cited |
| Config / ops | `Tenant.run_stale_seconds` (`ubb-platform/apps/platform/tenants/models.py:89`); `BillingTenantConfig.run_cost_limit_micros` (`tenant_billing/models.py:131`); Celery beat entries `close_abandoned_runs`/`reap_stale_runs` (`ubb-platform/config/settings.py:208-215`) | as cited |
| Reason vocabulary | `cost_limit_exceeded` (run cap), `task_limit_exceeded` (task cap), `balance_floor_exceeded`, `customer_wide_stop`, `stale`, `stale_max_age` — closed set consumed by 429 bodies, kill reasons, and webhooks | `runs/reasons.py:10-30` |
| Living docs | `apps/platform/CONTEXT.md` (13 "run" mentions), `apps/billing/CONTEXT.md` (4), `docs/spend-control-integration.md` (14). Dated plans are frozen history (not renamed) | grep counts at `b739fc6` |

### 2c. Cap basis — what every counter counts today

| Counter / gate | Basis today | Evidence |
|---|---|---|
| Two-card pricing model produces both numbers per event | built | `RateCard.card_type` `cost`/`price` `ubb-platform/apps/metering/pricing/models.py:51,141`; `PricingService.price` returns `(provider_cost_micros, billed_cost_micros, provenance)` `pricing/services/pricing_service.py:108-140`; `UsageEvent` stores **both** `usage/models.py:30-31` |
| Per-run cap accumulate | **billed (customer price)** | `RunService.accumulate_cost(run_id, billed_cost_micros)` `usage_service.py:224-228` (sync), `:375-378` (settle) |
| Per-task cap counter (`ubb:taskcost:*`) | **billed (customer price)** | `check_task_cost_cap(owner_id, tenant, task_id, billed_cost_micros)` `usage_service.py:234-236` → `queries.py:71-80` → `live_ledger_service.py:409-441` ("month-to-date billed spend"); `RiskConfig` comment `gating/models.py:10-11` |
| Live wallet counter (`ubb:livebal`) / postpaid spend | **billed** | `record_live_usage_debit(owner_id, tenant, billed_cost_micros)` `usage_service.py:270-272`, `queries.py:54-68` |
| Async accept-time hold estimate | **estimated billed** | `EstimationService.estimate` returns `caller_billed` directly (`estimation_service.py:28-29`) else resolves **price** cards (`:44-46`); wired at `metering_endpoints.py:656-678` |
| Budget counter / monthly cap | **billed** | `get_customer_cost_totals(...)["billed_cost_micros"]` `budget_service.py:92,111,167-168` |
| Wallet drawdown | **billed** | `WalletTransaction` amount `-billed_cost_micros` `handlers.py:86-99` |
| Switching task cap to COGS | needs adjustment (small at the sync/settle choke points) | `provider_cost_micros` is in hand at both call sites (`usage_service.py:218-223` sync, `:351-357` settle) — pass it instead of billed. Caveats: `provider_cost` defaults to **0** when no cost card matches and the caller sent none (`pricing_service.py:130-140`), so a COGS cap is only meaningful with `Tenant.require_cost_card_coverage` on (`pricing_service.py:122,136`); accept-time COGS **estimation does not exist** (`EstimationService` prices only price cards) — moot if async task counting is settle-time exact per #12; cost cards are `per_unit`/`flat` only (no tiers) `pricing/models.py:88-90`, so a COGS estimate would be arithmetically exact if ever needed |

---

## Area 3 — Fast-reaction layer

| Item | Status | Evidence |
|---|---|---|
| Fast database tracking the wallet | built (Redis, raw client + Lua) | Prepaid `ubb:livebal:{owner}` = credits − recorded usage (conservative, MIN-merge reconcile), postpaid `ubb:livespend:{owner}:{YYYY-MM}` (MAX-merge) `live_ledger_service.py:1-58,151-182`; seeded from durable wallet balance with one bounded over-permissive drain window (`:29-37`); hourly reconcile beat `config/settings.py:228-231`; drift alert at $50 `live_ledger_service.py:52-58` |
| Customer-wide floor signal (hard floor) | built | Crossing → `ubb:stop:{owner}` + ack verdict + `stop.fired` + pub/sub (Area 1); read on every replay/ack `usage_service.py:154-162,180` |
| Per-task "task hit its limit" fast signal | needs adjustment | Sync path only: atomic check-then-increment Lua `_TASK_CHECK_INCR` `live_ledger_service.py:122-130,407-441`; today it **rejects (429) + kills the run** rather than signaling stop (pre-one-rule semantics, being re-spec'd by #18). Async: `HoldService.acquire`/`settle_raw` never touch `ubb:taskcost:*` — confirmed: `hold_service.py:99-127` (run cap + owner counter only), `usage_service.py:300-445` (no `check_task_cost_cap`); #12 decided settle-time exact counting closes this |
| Per-run (→ per-TASK after rename) limit signal | built | Sync: `accumulate_cost` ceiling → 429 + kill + `run.limit_exceeded` (`services.py:87-94`, `metering_endpoints.py:75-101`); async: run-cap check inside the hold Lua (`hold_service.py:99-111`) + kill parity `_kill_capped_run` `metering_endpoints.py:290-325,704-718`; per-run counter `ubb:runcost:{run_id}` settled by exact deltas `hold_service.py:265-343` |
| Signal only "if tenant defines tasks" | built (analogous) | Task cap no-ops without `task_id` and without a positive cap (`live_ledger_service.py:420-426`); run machinery only engages when the tenant starts runs / passes `run_id` |
| Soft-floor signal from the fast layer | **missing** | Single threshold per (mode, owner) — `_threshold` `live_ledger_service.py:256-275`; binary `ubb:stop` flag with one reason |
| Resume ("safe to allow new events") signal | missing (decided, spec #23) | Flag clear exists (`:462,:500,:530`) but emits nothing |
| Failure semantics of the fast layer | built (documented) | Fail-open everywhere, durable gates as backstop: `live_ledger_service.py:216-217,249-252`, `hold_service.py:186-192,254-263` (one-batch stop-flag delay), task-cap Redis error fails open `live_ledger_service.py:433-436`; enforcement gated per tenant `off/advisory/enforcing` `ubb-platform/apps/platform/tenants/flags.py:17-33` |
| Known orphan-hold drift (over-restrictive, unrepaired) | known gap (decided, spec #23) | Documented at `usage_service.py:426-443`; auto-repair decided in #12, spec'd by #23 |

---

## Tensions & questions for the decision session

1. **Hard floor is already built and already decided.** Today's `min_balance` floor + stop flag + "every event lands and bills" IS the user's hard floor under the one-rule model (#10). The gap is purely that there is only one floor. The soft floor is genuinely new config + a second comparison — but note the two *mechanisms* the user wants (gate new starts vs stop emitting) already exist separately (start-gate vs stop flag); today they just fire at the same threshold. The minimal build is "split the threshold", not "build a gate".
2. **Where must the soft-floor verdict travel?** If only `pre_check` (new-task starts), it is a ~10-line durable check. If it must also ride event acks and webhooks (a `soft_stop`/resume pair), it becomes a second live-ledger threshold + second flag + catalog event, and lands squarely on #23's delivery rails — worth deciding as one package with #23.
3. **The rename is asymmetric.** User's TASK → today's Run is clean (same shape: two endpoints bound a set of events, own cap, kill/close lifecycle). User's SUBTASK → today's "task" is NOT clean: today's task-tag is month-scoped, spans runs, is owner-global, has a single tenant-wide cap, and has no containment relation to the run. A faithful subtask needs either (a) re-scoping the counter key to `{run_id}:{subtask_id}` with a lifecycle, or (b) a real child entity. Decide which before renaming, or the new names will lie about the semantics exactly the way "run" does now.
4. **Silent fallback surprise:** task identity falls back `task → service → agent` (`usage_service.py:207`), so tenants tagging `service`/`agent` get per-"task" caps without ever defining tasks. Under the new "if and only if the tenant defines tasks" framing this fallback probably has to go.
5. **Reason/event vocabulary collision mid-rename:** after run→task, `task_limit_exceeded` (today: the tag cap) and `cost_limit_exceeded` (today: the run cap) swap referents, and `run.limit_exceeded` is a wire contract in the webhook catalog that tenants pin. Decide big-bang rename vs alias/dual-emit window. Note `RunLimitExceeded.task_id` is already always `""` (vestigial `Run.task_id`), so nothing real is lost by redesigning that field.
6. **COGS cap vs everything else billed:** all money surfaces (wallet, live ledger, budget, margin, responses like `run_total_cost_micros`) are customer-price denominated; a COGS-denominated task cap introduces a second denomination into the same run/task records and responses. Cheap to compute (both numbers exist per event), but decide the display/API story — and note a COGS cap is only trustworthy with `require_cost_card_coverage` on (otherwise unmatched events count 0 toward the cap).
7. **Per-task-definition caps need a config home.** Today's cap is one tenant-wide number on `RiskConfig`. Tenant-defined tasks with individual caps need a per-task-definition config surface (nothing like it exists; `BudgetConfig` is per-seat monthly, wrong shape).
8. **The fast layer needs no new store.** Redis live ledger + Lua one-round-trip patterns already cover customer/run/task scopes; the user's ask is new thresholds and re-scoped signals on the same substrate. The async task-cap wiring is already a decided work item (#12 → #18: settle-time exact), so the subtask-limit signal for async tenants should be spec'd there rather than duplicated.
9. **One-rule rework (#18) will rewrite the very semantics being renamed** (caps land the tipping event; killed runs keep accepting events; `run_not_active` refusal goes away). Sequencing question: rename before or with #18's spec? Doing the rename first would churn the same surfaces twice.
