# Tier-2 Real-Time Spend Control — Implementation Plan

**Date:** 2026-06-19
**Design:** `2026-06-19-tier2-realtime-spend-control-design.md` (read first; this plan references its decisions `D1`–`D20` and invariants `I1`–`I10`).
**Rule for the executor:** every cross-cutting choice is already made in the design's §6. If you find yourself making a design decision, stop — it should already be a `Dn`. Phases are ordered so the tree is never in a half-built unsafe state. **No tenant is flipped past `off` until P3 is merged.**

Queues in use: `ubb_billing`, `ubb_invoicing` (existing). Beat lives in `config/settings.py` `CELERY_BEAT_SCHEDULE`.

---

## Phase ordering & gates (read once)

```
P0 Foundations (additive, zero behavior change)         ── must land ALONE, first
P1 Monotonic reconcile fix (flag-independent bugfix)    ── can land anytime ≥P0
P2 Live counter + synchronous decrement (write-only)    ── needs P0
P3 Synchronous stop verdict + kill flag (READS counter) ── needs P0,P2 ; first flag flip allowed AFTER this
P4 Per-run hardening + per-task cap + 429 taxonomy      ── needs P0
P5 Concurrency cap + run heartbeat/reaper               ── needs P0 (P5 release hooks + reaper land together)
P6 Webhook fan-out + single suspend emitter             ── needs P0 (canonical event), P5 (reaper emits)
P7 SDK + integration contract + observability           ── needs P3,P4,P5,P6 wire contract
P8 Rollout: advisory canary → enforcing                 ── needs all
```

**Hard gate:** do not enable any tenant (`advisory` or `enforcing`) until **P0+P2+P3** are merged, or a flipped tenant pays Redis writes with no consumer / a half-wired verdict (review sequencing finding).

---

## P0 — Foundations (additive, zero behavior change)

Everything here is inert until later phases or gated by `enforcement_on`. After P0, `migrate` runs clean and all existing tests pass unchanged.

### P0.1 — The one flag (D1, I1)
- `apps/platform/tenants/models.py`: add `enforcement_mode = models.CharField(max_length=10, choices=[("off","Off"),("advisory","Advisory"),("enforcing","Enforcing")], default="off", db_index=True)`. No `clean()`/`save()` change.
- New `apps/platform/tenants/flags.py`:
  ```python
  def enforcement_mode(tenant) -> str: return getattr(tenant, "enforcement_mode", "off") or "off"
  def enforcement_on(tenant) -> bool: return enforcement_mode(tenant) != "off"
  def enforcing(tenant) -> bool: return enforcement_mode(tenant) == "enforcing"
  ```
- Migration: `tenants/` next number (`makemigrations` assigns — it is **0016+**, *not* 0007; 0007 already exists). `AddField` only.
- Expose read-only in `GET /tenant/config` (additive field).

### P0.2 — Canonical event + reason enum (D6)
- New `apps/platform/runs/reasons.py`: a frozen set of constants `COST_LIMIT_EXCEEDED`, `TASK_LIMIT_EXCEEDED`, `BALANCE_FLOOR_EXCEEDED`, `CUSTOMER_WIDE_STOP`, `STALE`, `STALE_MAX_AGE`.
- `apps/platform/events/schemas.py`: add **one** frozen dataclass (additive-only):
  ```python
  @dataclass(frozen=True)
  class RunLimitExceeded:
      EVENT_TYPE = "run.limit_exceeded"
      tenant_id: str
      customer_id: str = ""          # the SEAT that owns the run
      billing_owner_id: str = ""     # resolve_billing_owner — the kill scope
      run_id: str = ""
      external_run_id: str = ""
      task_id: str = ""
      reason: str = ""               # from runs/reasons.py
      scope: str = "run"             # "run" | "customer"
      total_cost_micros: int = 0
      limit_micros: int = 0
  ```
- `apps/platform/events/apps.py` `ready()`: register `run.limit_exceeded` exactly once so the outbox dispatches it. **Schema + registration + first emit (P6) ship together** — never register without an emitter or vice-versa.
- No emit sites yet (P4/P5/P6 emit). Forbid any other module from redefining this class.

### P0.3 — One `_result()` signature (D5, I4)
- `apps/metering/usage/services/usage_service.py:97-110`: change to
  ```python
  def _result(event, run_total, *, stop=False, stop_reason=None, stop_scope=None,
              suspended=False, new_balance_micros=None):
  ```
  Keep all existing keys; add `stop`, `stop_reason`, `stop_scope`. Defaults reproduce today's behavior exactly.
- Update **all three** call sites to pass through (still defaulting in P0): happy path `:221`, replay `:128`, replay `:197`. (P3 fills real values.)
- `api/v1/schemas.py` `RecordUsageResponse`: add `stop: bool = False`, `stop_reason: Optional[str] = None`, `stop_scope: Optional[str] = None` (D14). `suspended` already exists and is always populated.
- **Test (acceptance gate):** `test_result_signature_populates_on_all_three_paths` — asserts the new keys are present on happy path **and both replay returns** (the hardcoded-False bug is trivially half-fixed; this guards it).

### P0.4 — Pin the billing owner + run heartbeat columns (D4, D10, I6)
- `apps/platform/runs/models.py`: add `billing_owner_id = models.UUIDField(null=True, blank=True, db_index=True)`, `last_event_at = models.DateTimeField(null=True, blank=True)`, `task_id = models.CharField(max_length=255, blank=True, default="")`. Add index `idx_run_status_heartbeat` on `(status, last_event_at)`.
- `apps/platform/runs/services.py` `create_run` (`:35-52`): accept and store `billing_owner_id`; `RiskService.check` passes `resolve_billing_owner(customer).id`. (Back-compat: nullable, so pre-existing runs have `None`.)
- `accumulate_cost` (`:55-106`): stamp `last_event_at = timezone.now()` in the same `save(update_fields=...)`. (Single edit; no other phase touches this stamp — D10.)
- **One** migration `runs/0002_run_heartbeat_owner` adds all three fields + the index. (Not two — D10 collision fix.)

### P0.5 — `LiveLedgerService` skeleton (no callers) (D9)
- New `apps/billing/gating/services/live_ledger_service.py` with the raw client + Lua scripts defined but **no caller** yet (P2 wires it). Confirm `CACHES` `KEY_PREFIX`/`VERSION` (D9) and document the exact key strings. New keys use a `ubb:` prefix (`ubb:livebal:{owner}`, etc.) to avoid django-redis namespace collision.

**Definition of done (P0):** `migrate` clean; full existing suite green; new fields/flag default to inert; `enforcement_mode="off"` for all tenants; zero runtime behavior change.

---

## P1 — Monotonic reconcile fix (flag-independent bugfix) (D8/I7, WS7)

Fixes a live correctness bug for **all** postpaid tenants regardless of the flag, and is a prerequisite for honest `/allowed` reporting (P7).

- `apps/billing/gating/services/budget_service.py` `reconcile_customer` (`:113-124`): replace the absolute `cache.set(total)` with a **MAX-merge** via a Lua script through `django_redis.get_redis_connection()` on the **prefixed** key (D9): `SET key = max(current, durable_total)`; never lower an in-month counter (lowering is legitimate only at month rollover, where the key label changes anyway).
- Hold `lock_for_billing(owner)` around the durable read + merge so a concurrent `record_spend`/credit cannot be erased (D8).
- **Tests:** `test_reconcile_never_lowers_inmonth_counter`; `test_reconcile_concurrent_with_record_spend_no_lost_update`; `test_reconcile_raises_to_durable_when_counter_drifted_low`.

**DoD:** the time-travel re-allow window is closed; postpaid budget cap can no longer be transiently bypassed by a mid-burst reconcile.

---

## P2 — Live counter + synchronous decrement (write-only) (WS1; D3, D7, D9, D20, I2, I9)

The counter is **written** here but **not yet read** for a verdict (P3 reads it). Gated by `enforcement_on`; `off` ⇒ the hook is a no-op (counter untouched).

### P2.1 — `LiveLedgerService` API
- `record_usage_debit(owner_id, tenant, billed_cost_micros, *, effective_at, now) -> dict|None`: no-op (return None) if `not enforcement_on(tenant)` or `billed_cost_micros <= 0` **or the event is backdated to a prior month** (I9 — mirror `handlers.py:115-129`). Prepaid: `SEED_AND_DECR` Lua (seed = durable balance − recorded-but-undebited usage via the Stage D anti-join, then DECRBY — D7/I2, atomic). Postpaid: INCRBY the owner-aggregated `budget:{owner}:{month}` for **pooled** topology, the seat key for **allocated** (D3). Returns `{mode, remaining|spend, threshold, key}` for P3 to consume.
- `credit(owner_id, tenant, amount_micros)`: `CREDIT_IF_PRESENT` Lua (INCRBY only if the key exists; an unseeded credit is dropped because first-use seeds from the post-credit durable balance). Negative `amount` = DECRBY (grant expiry).
- `seed_prepaid`, `read_prepaid`, `reconcile_prepaid` (MIN-merge under `lock_for_billing` — D8/I7), `cleanup_keys(tenant)` (D17).

### P2.2 — Wire the synchronous decrement (the choke point)
- `usage_service.py` `record_usage`: **inside the inner savepoint, after `event = UsageEvent.objects.create(...)` and after `accumulate_cost`** (so a replay/IntegrityError never reaches it — exactly-once per real insert), call `live = LiveLedgerService.record_usage_debit(owner_id, tenant, billed_cost_micros, effective_at=effective_at, now=now)`. Store `live` locally; **P2 ignores the return** (do not change `_result` values yet). Document the rollback asymmetry: the breaching-event path (P3) is **200 + commit** (D2/I3), so the event always persists and the Redis decrement always matches a committed event — there is no "decrement-then-rollback" case.

### P2.3 — Credit hooks (D20) — all `transaction.on_commit`, gated by `enforcement_on`
- `connectors/stripe/webhooks.py:127` (checkout/manual top-up) and STRIPE_REFUND credit → `LiveLedgerService.credit(wallet.customer_id, tenant, +amount)`.
- `topups/services.py:90` (`AutoTopUpService.apply_topup_credit`, winning branch only) → `credit(+amount)`.
- `api/v1/billing_endpoints.py:94` (POST /credit, the **endpoint** — not a `wallets/tasks.py` task) → `credit(+amount)`.
- `apps/billing/wallets/grants.py` `GrantLedger.expire_due` (winning expiry branch) → `credit(-expired)`. (Optional per D8 — reconcile MIN-merge also lowers; if kept, add `test_expiry_no_double_decrement_with_reconcile`.)

### P2.4 — Reconcile beat
- New `reconcile_live_ledgers` task (queue `ubb_billing`), iterates **every `Wallet` row** (a wallet ⇒ a billing owner — D9 fix: do not filter by `account_type`, which misses allocated seats), MIN-merges prepaid `livebal`. Postpaid owner-aggregation reconcile for pooled businesses. Beat at **`:25`** (D16).
- **Tests:** `test_seed_excludes_undebited_usage`; `test_concurrent_first_use_debits_seed_once`; `test_backdated_event_does_not_move_live_counter`; `test_reconcile_min_merge_under_concurrent_credit`; `test_pooled_postpaid_counter_aggregates_seats_at_owner`; `test_flag_off_hook_is_noop`.

**DoD:** for a flagged tenant the live counter tracks the durable wallet/budget within one outbox-drain window; no verdict yet surfaced; `off` tenants unaffected.

---

## P3 — Synchronous stop verdict + customer-wide kill flag (WS2; D2, D5, D13, D15, I3, I4, I5)

This is the headline. **After this lands, the first tenant may be flipped to `advisory`.**

### P3.1 — Kill flag
- `StopFlagService` (in `live_ledger_service.py` or a sibling): `ubb:stop:{owner}` carrying `reason` + `scope`. **Set** synchronously when `record_usage_debit` reports the counter crossed the threshold (prepaid floor / postpaid cap), but only when `enforcement_on`. In `advisory` mode the flag is **still set and read** (so the verdict is computed and emitted) — `advisory` differs from `enforcing` only in that the tenant's gates/SDK treat `stop` as informational; UBB never *itself* blocks/kills/suspends in advisory. (D1.)
- **Read** on every `record_usage` — happy path **and both replay returns** — and populate `_result(..., stop=..., stop_reason=..., stop_scope=..., suspended=...)` (D5/I4). The read short-circuits on `mode == "off"` before touching Redis (D17).
- Owner-keyed; for a pooled business the flag is on the owner and stops all seats; an allocated-seat budget breach sets a seat-scoped flag (D3).

### P3.2 — Cooperative, never rollback (D2/I3)
- The breaching event is **recorded and charged** (the durable async debit follows as today). The 200 response carries `stop=True`. **No 429**, **no `SpendStopExceeded`**, **no savepoint rollback** for the customer-wide stop. (The per-run/per-task hard cap in P4 is the only rollback/429 path.)

### P3.3 — Single suspend emitter + un-suspend (D13/I5, D15)
- The sync path sets the Redis flag and populates `_result` only — it emits **neither** `customer.suspended` nor `RunLimitExceeded`.
- `customer.suspended` stays emitted **only** by `handle_usage_recorded_billing` on the winning `active → suspended` transition (`handlers.py:85-90`), now for **both** modes — add the **postpaid** suspend branch (today `handlers.py:36-37` is `pass`) under the same `lock_for_billing` + `active→suspended` guard.
- Programmatic un-suspend on top-up (`StopFlagService.clear` + `status="active"`): take `lock_for_billing(owner)`, only when `new_balance >= -min_balance` **and** the suspension reason was monetary (D15 — add `Customer.suspension_reason`); never un-suspend an admin/fraud suspension.
- **Tests:** `test_crossing_returns_200_stop_true_event_persists_and_charges`; `test_stop_populated_on_both_replay_paths`; `test_sync_crossing_does_not_emit_customer_suspended`; `test_postpaid_suspend_emits_customer_suspended_once`; `test_topup_clears_flag_and_unsuspends_only_for_money_reason`; `test_topup_does_not_unsuspend_admin_suspended_owner`; `test_advisory_mode_sets_flag_but_ubb_never_blocks`.

**DoD:** a flagged tenant's crossing event returns `stop=True` synchronously; sibling runs see it on their next event; suspend webhook fires exactly once from the async handler; start-gate (durable status) is the backstop.

---

## P4 — Per-run hardening + per-task cap + 429 taxonomy (WS3; D12, I7)

- **Per-run cap:** confirm `accumulate_cost` (`runs/services.py:85`) is billing-mode-agnostic (it is — no change needed beyond a regression test `test_per_run_cap_fires_in_postpaid`).
- **Per-task cap (new):** `taskcost:{tenant}:{owner}:{task_id}:{YYYY-MM}` (raw client, `ubb:` prefix). `task_id` per D12. Synchronous INCR + check inside the same savepoint as the event; on breach raise `HardStopExceeded(reason=TASK_LIMIT_EXCEEDED)`. Cap value from `RiskConfig` (new `max_cost_per_task_micros`, tenant-global — D11 honesty). Reconcile = **absolute SET from the UsageEvent ledger sum** for that task/period (I7 — NOT MAX-merge; the over-count drift is upward and only an absolute set heals it).
- **Per-task rate limit:** extend the existing per-customer RPM pattern (`risk_service.py:22-33`) to a `taskrpm:{...}` token bucket (fail-open, like the existing one).
- **429 reason taxonomy:** `metering_endpoints.py:77-83` already returns `{hard_stop:true, reason, run_id, total_cost_micros}`. Map `HardStopExceeded.reason ∈ {cost_limit_exceeded, task_limit_exceeded, balance_floor_exceeded}` (from `runs/reasons.py`).
- **Run-less task breach:** when `run_id is None`, a `task_limit_exceeded` breach returns **429 only** (no `kill_run`, no `RunLimitExceeded` — there is no run to scope it to). Keep the existing `if payload.run_id is not None` guard around `kill_run` at `:75` and `:158`.
- **Tests:** `test_per_run_cap_fires_in_postpaid`; `test_per_task_cap_kills_task`; `test_per_task_reconcile_absolute_from_ledger_heals_overcount`; `test_task_cap_null_run_id_429_only_no_emit`; `test_429_reason_taxonomy`.

**DoD:** runaway agents are bounded per-run and per-task, in both billing modes; reasons are a closed set.

---

## P5 — Concurrency cap + run heartbeat/reaper (WS4+WS5 merged; D10, D11, I6)

WS4 and WS5 are **one** workstream (they share `Run.billing_owner_id`, the slot lease, and the reaper).

- **Slot acquire (D11):** `runslots:{owner}` (raw client). Acquire in `transaction.on_commit` *after* the Run row commits (accept bounded over-admit on rollback rather than leak a synchronously-reserved slot). Reject a new run at the start-gate when the counter ≥ `RiskConfig.max_concurrent_requests` (tenant-global value, per-owner counter). Lease TTL = **15 min**. Delete any dead `on_commit(lambda: nothing)`.
- **Slot release:** `complete_run`, `kill_run`, and `reap_stale_runs` all release, reading `Run.billing_owner_id` (D4/I6 — never re-resolve). Lease-gated so double-release is a no-op.
- **Reaper (D10):** `reap_stale_runs` (beat, every 5 min): `active` runs with `last_event_at` stale >15 min ⇒ `killed(reason=STALE)`; age >6 h ⇒ `killed(reason=STALE_MAX_AGE)`; release slot; emit `RunLimitExceeded(scope="run")` (P6). Gate the 15-min heartbeat path behind `enforcement_on` so `off` tenants keep pure-`close_abandoned_runs` semantics (don't kill slow legit runs of un-enrolled tenants).
- **`close_abandoned_runs`** (existing, `runs/tasks.py`, every 15 min): keep as the graceful >1 h **completer**, but **skip runs with a recent heartbeat** (`last_event_at` within 15 min) so it never races the reaper.
- **`reconcile_run_slots`** (beat, every 10 min, `:35` — D16): re-base `runslots:{owner}` from the actual count of `active` runs per owner.
- **Tests:** `test_concurrency_cap_blocks_new_run_at_limit`; `test_pooled_business_shares_tenant_cap_counted_per_owner`; `test_slot_released_on_complete_kill_and_reap`; `test_slot_reconcile_rebases_after_rollback_leak`; `test_reaper_kills_stale_run_releases_slot_emits`; `test_close_and_reaper_do_not_double_handle`; `test_reaper_does_not_kill_slow_legit_run_when_flag_off`.

**DoD:** `max_concurrent_requests` is enforced per owner (bounding overshoot K); crashed/silent runs are reaped and their slots freed; no double-handling with the existing completer.

---

## P6 — Webhook fan-out + single suspend emitter (WS6; D6, D13)

- Emit the canonical `RunLimitExceeded` (P0.2) from: the per-run/per-task `kill_run` path (`scope="run"`, run-scoped fields) and the reaper (P5). For a **customer-wide** stop, emit **one** owner-scoped `RunLimitExceeded(scope="customer", billing_owner_id=owner)` — consumers fan out to their own runs — **not** one event per killed run (review cardinality fix).
- `customer.suspended` remains single-emitter in `handle_usage_recorded_billing` (D13).
- `empty event_types = deliver-all`: document in release notes that all-event subscribers begin receiving `run.limit_exceeded`; rate-bound the fan-out on a mass stop.
- **Tests:** `test_run_kill_emits_run_scoped_event`; `test_customer_wide_stop_emits_single_owner_scoped_event`; `test_run_limit_exceeded_registered_and_dispatched`; `test_webhook_v2_signature_covers_new_event`.

**DoD:** sibling/idle runs are reachable by webhook; suspend fires once; event cardinality is bounded.

---

## P7 — SDK + integration contract + observability (WS8; D14, D17, D18)

- **SDK (`ubb-sdk`):** `pre_check(start_run=True)` returns `run_id` + caps; `record_usage` returns `stop`/`stop_reason`/`stop_scope`/`suspended` (D14 names, identical server↔client); add `UBBCustomerStoppedError` raised on `200 + stop=True` **only in opt-in raise-mode** (D18); keep `UBBHardStopError` for 429. Add a `GET /me/allowed` (or reuse `pre_check` without `create_run`) pull endpoint reading `max(cache_value, fresh Postgres total)` for an honest `budget_pct` (depends on P1).
- **Low-touch contract + paved paths:** document the 4 tenant integration points and the **per-step failure-mode table** (skip the stop-check ⇒ start-gate+caps only; skip `run_id` threading ⇒ no per-run/task cap; no webhook handler ⇒ no sibling stop). Recipes: Inngest `cancelOn`, Temporal cancel + heartbeat, Vercel AI SDK `stopWhen`, LangGraph node-boundary check, OpenAI Agents SDK `result.cancel()`.
- **Observability:** metrics for stop-set rate, overshoot per run, reconcile repairs, concurrency rejections, reaper kills; **a live-vs-durable drift alert** (analog of Stage D's repair-rate spike) so the under-charge/flap class of bug is observable; a loud log + alert when Redis is down (fail-open silently disables synchronous enforcement — I2 backstop is the durable start-gate).
- **Flag-off cleanup (D17):** `cleanup_enforcement_keys(tenant)` deletes stale `livebal/stop/runslots/taskcost` keys on disable; all read paths already short-circuit on `mode=="off"`.
- **Tests:** `test_sdk_record_usage_surfaces_stop_fields`; `test_sdk_raise_mode_raises_customer_stopped`; `test_allowed_endpoint_never_reports_stale_low`; `test_cleanup_keys_on_disable`.

**DoD:** a tenant can integrate enforcement with ≤4 changes and no gateway; operators can see drift and Redis-down.

---

## P8 — Rollout

1. **Full-pipeline seam test (mandatory before any flip):** `test_e2e_enforcement_seam` — seed counter (P2) → cross floor → kill flag set (P3) → 200 carries `stop` → start-gate blocks new run (P5/RiskService) → `run.limit_exceeded` fans to sibling (P6) → top-up clears flag + un-suspends (P3) → next event allowed. This is the test that would have caught the divergent-flag bug.
2. **Load/SLO check:** measure the added synchronous Redis Lua round-trip on the `record_usage` hot path; set a p99 budget; confirm fail-open under Redis latency.
3. **Canary:** flip one internal/sandbox tenant to **`advisory`** — counters + flags + webhooks compute and emit, UBB never blocks. Watch the drift alert and overshoot metric for a week.
4. **Enforce:** flip the canary to **`enforcing`**; then roll tenants forward individually. Back-out = set `enforcement_mode="off"` (instant, no deploy) + `cleanup_enforcement_keys`.

---

## Migrations (all additive, `makemigrations`-numbered — never hardcode)
- `tenants/00NN_tenant_enforcement_mode` — `enforcement_mode` (P0.1).
- `tenants/00NN_customer_suspension_reason` — `Customer.suspension_reason` (P3.3). *(or fold into the tenants/customers migration set as appropriate)*
- `runs/0002_run_heartbeat_owner` — `billing_owner_id` + `last_event_at` + `task_id` + `idx_run_status_heartbeat` (P0.4) — **one** migration (D10).
- `gating/00NN_riskconfig_task_caps` — `RiskConfig.max_cost_per_task_micros` (+ per-task RPM field) (P4).

## Cross-cutting test gates (must all pass before P8)
`test_single_flag_gates_everything` · `test_no_behavior_change_when_off` · `test_stop_populated_on_both_replay_paths` · `test_pooled_postpaid_owner_aggregates_seats` · `test_breaching_event_committed_and_charged` (I3) · `test_run_billing_owner_pinned_immune_to_reparent` (I6) · `test_e2e_enforcement_seam` (P8).

## Known limitations (documented, not bugs)
- Residual overshoot = in-flight calls dispatched before the crossing event was reported (bounded by per-run cap + concurrency; not zero — Tier-3 pre-auth needed for zero). (I10)
- A runaway that **stops reporting** cannot be cost-capped synchronously; the heartbeat reaper catches it within 15 min. (D10)
- Mid-period re-parenting / topology change is out of scope; old-owner counters retain prior spend until month rollover. (D19)
- `RiskConfig` caps are tenant-global values counted per owner; per-business cap *values* are a follow-up. (D11)
- **Concurrency cap is best-effort (P5).** Implemented as `COUNT(active runs WHERE billing_owner_id=owner)` at the start-gate (not a Redis slot counter — platform can't release a billing-owned slot). The read-then-create has no lock, so over-admit ≤ the number of *simultaneously-starting* runs for that owner; the reaper reconverges below cap. Enabling `enforcing` activates the cap at `RiskConfig.max_concurrent_requests` (default 10) for any tenant that already has a `RiskConfig` row — review that value before flipping; `0`/negative = no cap.
- **Reaper stale window is tunable (P5).** `Tenant.run_stale_seconds` (default 900s) sets how long an enforcing run may go without a metered event before the heartbeat reaper kills it — widen it for workloads with long *uninstrumented* steps (the heartbeat is stamped only by metered events). `0` disables the heartbeat reaper; the 6h max-age ceiling always applies. A never-emitted run holds its concurrency slot up to 1h (until `close_abandoned_runs`).
