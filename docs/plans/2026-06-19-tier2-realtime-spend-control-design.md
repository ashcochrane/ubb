# Tier-2 Real-Time Spend Control — Design

**Date:** 2026-06-19
**Status:** Approved design, ready for implementation
**Companion:** `2026-06-19-tier2-realtime-spend-control-implementation.md`
**Provenance:** Designed and adversarially reviewed via multi-agent workflow (8 workstream specs + 3 independent review lenses: distributed-systems correctness, execution-safety/sequencing, code-fidelity/ambiguity). Every cross-cutting conflict the review surfaced is resolved here as a single canonical decision (see §6).

---

## 1. The problem we are solving

UBB's tenants (e.g. "Local Scouta") run AI agent workflows for *their* end-customers. End-customers hold a **prepaid wallet** (or are billed **postpaid**). UBB meters spend **report-after-the-fact**: the tenant makes the LLM/tool call first, then POSTs a priced usage event to UBB.

The tenant wants to **stop overspend** without UBB sitting in the inference path (no gateway, no added latency). Concretely, four capabilities:

1. **Start-gate** — block a *new* run when the customer is out of money / suspended.
2. **Mid-flight customer-wide stop** — when incoming events cross the floor (prepaid) or budget cap (postpaid), stop **all** of that customer's concurrent runs.
3. **Per-run and per-task hard cost cap** — kill a runaway agent that loops forever.
4. **Per-task rate limit.**

### Why today's code cannot deliver this (verified)

- **The stop verdict is asynchronous.** Wallet drawdown, the `min_balance → suspend` transition, the `BalanceOverage` event, and the budget-counter increment **all run in the async outbox handler** `handle_usage_recorded_billing` (Celery, `transaction.on_commit`) — *after* `record_usage` commits. The synchronous response builder `_result()` (`apps/metering/usage/services/usage_service.py:97-110`) **hardcodes `suspended=False, hard_stop=False`**. So the POST that tips a customer over the line still returns "all clear"; suspension lands seconds later.
- **In-flight runs of a suspended customer keep metering.** `record_usage` never reads `owner.status`; only the start-gate `RiskService.check` does (`apps/billing/gating/services/risk_service.py:12-16`). Suspension only blocks the *next run's* start.
- **The per-run cap already works** synchronously (`RunService.accumulate_cost`, `apps/platform/runs/services.py:55-106`) and is **billing-mode-agnostic** — but there is no per-*task* cap.
- **`RiskConfig.max_concurrent_requests` is defined but enforced nowhere** (`apps/billing/gating/models.py:8`).
- **No run heartbeat / stale-run reaper** — a crashed or silent runaway leaks an `active` Run forever and is never cost-capped.
- **The budget reconcile can time-travel backward.** `BudgetService.reconcile_customer` does an absolute `cache.set` (`budget_service.py:113-124`), which mid-burst can lower the live counter below in-flight increments and re-allow over-cap spend.

### What stays out of scope (stated honestly)

- **Tier-3 pre-authorization** (reserve/settle/refund for near-zero overshoot) — a separate future design. This plan is best-effort enforcement with **bounded, honest overshoot**.
- **Killing in-flight provider calls.** UBB is not in the inference path; it can only stop the *next* unit of work. Residual overshoot = the calls already dispatched to the provider when the floor was crossed. This is deterministic (bounded by the per-run cap + enforced concurrency), **never absorbed by a guessed buffer** (no estimation).
- **Per-owner / per-task *configurable* cap values.** `RiskConfig` is per-tenant (one number), enforced against a per-owner counter. Per-business cap *values* are a follow-up.

---

## 2. Target state (one paragraph)

`record_usage` becomes the **synchronous control point**. After pricing, it decrements a **shared, owner-keyed Redis live counter** (prepaid: remaining balance; postpaid: month-to-date spend) and, if that crosses the threshold, sets a **customer-wide Redis kill flag** keyed on the billing owner. Every `record_usage` response — *including the idempotent-replay paths* — carries a `stop` verdict read from that flag. The durable wallet debit stays async (source of truth); the Redis counter is the fast read, kept honest by a **monotonic** hourly reconcile. The kill flag stops the *posting* run immediately; a **`run.limit_exceeded`** webhook and the existing **`customer.suspended`** webhook reach *sibling/idle* runs. The per-run cap is hardened, a **per-task** cost cap and rate limit are added, `max_concurrent_requests` is finally enforced (bounding overshoot), and a **heartbeat + stale-run reaper** catches crashed/silent runaways. Everything is gated by **one** per-tenant flag, `enforcement_mode ∈ {off, advisory, enforcing}`, default `off`.

---

## 3. The unified prepaid / postpaid model

The same mechanism serves both modes; only the *threshold source* differs:

| | Prepaid | Postpaid |
|---|---|---|
| Shared live counter | `livebal:{owner}` — micros remaining above floor; DECRBY on usage, INCRBY on credit | `budget:{owner|seat}:{YYYY-MM}` — month-to-date billed spend; INCRBY on usage |
| Threshold | wallet floor (`-min_balance`) | budget cap (`cap × hard_stop_pct / 100`) |
| Counter scope | **owner** (`resolve_billing_owner`) | **owner** for pooled topology, **seat** for allocated |
| Per-run / per-task cap | identical (`cost_limit_micros`, synchronous, mode-agnostic) | identical |
| Start-gate affordability | wallet balance vs floor | budget cap (wallet check skipped — `risk_service.py:44`) |

> **Critical resolution (review finding):** for a **pooled** postpaid business, spend must aggregate at the **owner** (`budget:{owner}:{month}` summing seats), not the per-seat budget counter — otherwise the highest-value consolidated-billing customers can *never* trip a business-wide stop. See D3.

Everything keys on `resolve_billing_owner` so **pooled money** (wallet/floor/suspend at the business) and **per-seat control** (per-seat budget caps when allocated) both work — mirroring the Stage D/E billing-owner pinning.

---

## 4. Invariants (the plan must preserve all of these)

- **I1 — One kill switch.** Exactly one field, `Tenant.enforcement_mode`, gates all behavior. `off` ⇒ byte-for-byte unchanged. `advisory` ⇒ compute + emit, never block/kill/suspend. `enforcing` ⇒ block/kill/suspend.
- **I2 — Conservative-or-honest live counter.** The live counter is never *more permissive* than the durable ledger **except** for one bounded outbox-drain / re-seed window, and that window is backstopped by the durable start-gate (`RiskService` reads the real wallet/status). (Reworded from the naive "absolute" claim per review.)
- **I3 — The breaching event is always recorded and charged.** The customer-wide spend stop is **cooperative** (200 + `stop=True`); it never rolls back the event that crossed the line. Only the per-run/per-task **hard cap** rejects+rolls-back the current event (429) and that path records/charges nothing (the run is killed).
- **I4 — Stop verdict on every path.** `_result()` populates the stop fields on the happy path **and both idempotent-replay returns** (`usage_service.py:128` and `:197`). A replayed event for a stopped owner must not report "all clear."
- **I5 — Single suspend emitter.** `customer.suspended` is emitted **only** by the async handler `handle_usage_recorded_billing`, on the winning `active → suspended` transition, for **both** prepaid and postpaid. The synchronous path only sets the Redis flag + populates `_result`.
- **I6 — Symmetric owner keying.** `Run.billing_owner_id` is pinned at create time; slot acquire/release/reconcile and both reapers read it — never re-resolve `resolve_billing_owner` (re-parenting must not split counters or leak slots).
- **I7 — Reconcile monotonicity is per-key and directional.** Prepaid `livebal` = **MIN-merge** (only lowers toward durable). Postpaid `budget` = **MAX-merge** (only raises). Per-task `taskcost` = **absolute SET from ledger**. Never apply two disciplines to one key. Read-and-merge is serialized under `lock_for_billing(owner)` so a concurrent credit cannot be erased.
- **I8 — One Redis access path per key.** A key written via Django `cache.*` is read/merged via the same django-redis connection (prefix-aware); a key written via the raw Lua client is only ever touched by the raw client. No cross-client reads.
- **I9 — Backdated events do not move the live counter.** A prior-month `effective_at` event must not INCRBY/DECRBY the current-month live/budget counter (mirrors `handlers.py:115-129`); the effective-month ledger + reconcile remain the source of truth.
- **I10 — No estimation.** Only deterministic limits (floor, cap, per-run/per-task ceiling, concurrency cap). Overshoot is bounded and stated, never buffered by a guess.

---

## 5. Honest guarantee & overshoot

When `enforcing` is on for a tenant:

- **Start-gate:** deterministic — a new run for an out-of-money/suspended owner is refused.
- **Per-run / per-task cap:** deterministic ceiling on what one run/task can be charged; overshoot ≤ one in-flight call per run.
- **Customer-wide stop:** every run is stopped on its **next event** (200 `stop=True`) and idle/sibling runs by webhook.
- **Residual overshoot** = Σ(cost of calls already dispatched to the provider but not yet reported at the crossing instant) ≈ (concurrent in-flight calls) × (per-call cost). Bounded by the per-run cap and the now-enforced `max_concurrent_requests`. **Not zero** (that needs Tier-3 pre-auth), and **not estimated**.

Marketing-safe claim: *"The moment a customer crosses their floor, every not-yet-started call across all their concurrent runs is blocked — on the next event and by webhook — with zero inference-path latency. Overshoot is bounded by your per-run cap and concurrency limit, never a guess."*

---

## 6. Resolved cross-cutting decisions (these eliminate the "room for error")

The review found the parallel specs diverged on these. Each is now **one** decision; the implementation plan references them by number.

- **D1 — Feature flag.** `Tenant.enforcement_mode = CharField(choices=off|advisory|enforcing, default="off", db_index=True)`. One accessor module `apps/platform/tenants/flags.py`: `enforcement_mode(tenant) -> str`, `enforcement_on(tenant) -> bool` (`mode != "off"`), `enforcing(tenant) -> bool` (`mode == "enforcing"`). Hard-stop/kill/suspend paths gate on `enforcing`; counter writes + event emission run in `advisory` too. **Every** workstream imports this; no other flag, no other migration. (Kills the 5-name collision.)
- **D2 — Stop delivery model.** Customer-wide spend stop = **HTTP 200 + `stop=True`** (cooperative; event commits and is charged). The per-run/per-task hard cap is the **only** 429 path (kills run, rolls back event). The "raise `SpendStopExceeded` inside the `record_usage` savepoint" variant is **deleted** (it rolls back the breaching event while keeping the Redis decrement → under-charge + stop-flap).
- **D3 — Postpaid pooled scope.** Pooled business ⇒ owner-aggregated counter `budget:{owner}:{YYYY-MM}`; allocated seat ⇒ seat-keyed. `BudgetService.record_spend` is **not** reused verbatim for pooled; an owner-keyed variant is added.
- **D4 — Pin `Run.billing_owner_id`** at `create_run` (set from `resolve_billing_owner`), exactly like `UsageEvent.billing_owner_id`. All slot/reaper logic reads it. (I6.)
- **D5 — One `_result()` signature** (flat kwargs): `_result(event, run_total, *, stop=False, stop_reason=None, stop_scope=None, suspended=False, new_balance_micros=None)`. One WS owns it; populated on `:128`, `:197`, `:221`. (I4.)
- **D6 — One canonical `RunLimitExceeded`** frozen dataclass (superset, all non-`tenant_id` fields defaulted): `tenant_id` (req), `customer_id=""` (the **seat**), `billing_owner_id=""` (the **owner / kill scope**), `run_id=""`, `external_run_id=""`, `task_id=""`, `reason=""`, `scope="run"`, `total_cost_micros=0`, `limit_micros=0`. Registered once in `apps/platform/events/apps.py`. Reasons come from one closed enum module `apps/platform/runs/reasons.py`: `{cost_limit_exceeded, task_limit_exceeded, balance_floor_exceeded, customer_wide_stop, stale, stale_max_age}`.
- **D7 — Seeding race.** Seed `livebal` = durable wallet balance **minus recorded-but-undebited usage** (the Stage D anti-join: `UsageEvent` rows with no matching `WalletTransaction.usage_event_id`). Done atomically via Lua `SEED_AND_DECR` so two concurrent first-use debits cannot both seed. (I2.)
- **D8 — Reconcile direction & atomicity.** Per I7. Reconcile holds `lock_for_billing(owner)` so credits cannot interleave a MIN-merge.
- **D9 — Redis client/key path.** Confirm `CACHES` `KEY_PREFIX`/`VERSION` at build start. The budget counter (written by `cache.incr`) is merged via `django_redis.get_redis_connection()` with the prefix-applied key. The new `livebal`/`runslots`/`taskcost` keys are raw-client-only and use a `ubb:` prefix that cannot collide with django-redis's namespace. (I8.)
- **D10 — Run lifecycle, one owner.** One migration adds `Run.last_event_at` + `Run.task_id` + index `idx_run_status_heartbeat (status, last_event_at)`. `accumulate_cost` stamps `last_event_at`. `close_abandoned_runs` stays the graceful >1h completer **but skips runs with a recent heartbeat**. `reap_stale_runs` (new) is the crash-killer: `last_event_at` stale >15 min ⇒ `killed(reason=stale)`, age >6 h ⇒ `killed(reason=stale_max_age)`. Both release the lease-gated concurrency slot. (No double-handling.)
- **D11 — Concurrency slot.** Acquire in `transaction.on_commit` *after* the Run row commits (accept a bounded over-admit on rollback rather than leak a synchronously-reserved slot). Lease TTL = 15 min (tracks the heartbeat-stale window); `reconcile_run_slots` every 10 min re-bases from actual active runs. Cap value is tenant-global, counted per owner. Delete the dead `on_commit(lambda: nothing)`.
- **D12 — Task identity.** `task_id = tags.get("task")` with fallback to `tags.get("service") or tags.get("agent")`; absent ⇒ no per-task cap (safe default). Documented as caller-controlled/evadable; the per-run + wallet caps are the hard backstop. `Run.task_id` is populated from the same source.
- **D13 — `customer.suspended` single emitter** = `handle_usage_recorded_billing` only (I5). Add the postpaid suspend branch there (today `handlers.py:36-37` is `pass`), under the same `lock_for_billing` + `active → suspended` guard. The sync path emits **neither** `customer.suspended` nor `RunLimitExceeded`.
- **D14 — 200-body field names** standardized once across server `RecordUsageResponse` and SDK `RecordUsageResult`: `stop: bool=False`, `stop_reason: str|None=None`, `stop_scope: str|None=None`, `suspended: bool` (already exists, always populated). `reason` stays only on the 429 body. `suspended` implies `stop`.
- **D15 — Un-suspend guard.** Programmatic un-suspend (on top-up) only fires when the suspension reason was monetary. Add `Customer.suspension_reason` (or read the latest `CustomerSuspended`); never auto-un-suspend an admin/fraud suspension.
- **D16 — Beat schedule** uses genuinely-free minutes: `reconcile-live-ledgers` at `:25`, `reconcile-run-slots` at `:35` (`:15/:40/:45/:50/:55` are taken).
- **D17 — Flag-off semantics.** Every Redis read path short-circuits on `mode == "off"` **before** touching Redis. A `cleanup_enforcement_keys(tenant)` management action deletes stale `livebal/stop/runslots/taskcost` keys when a tenant is disabled. (No stale flag re-read on re-enable.)
- **D18 — SDK exception.** One cooperative-stop exception `UBBCustomerStoppedError` (raised on 200 + `stop=True` *only if the caller opts into raise-mode*); `UBBHardStopError` stays for 429. Document the distinction once.
- **D19 — Topology change.** Re-parenting / pooled↔allocated mid-period is **explicitly out of scope** for v1 enforcement; documented as a known limitation (old-owner counter retains prior spend until month rollover). No silent retarget claim.
- **D20 — Correct credit hook sites.** Top-up credit: `connectors/stripe/webhooks.py:127` and `topups/services.py:90`. Manual credit: the **endpoint** `api/v1/billing_endpoints.py:94` (POST /credit) — *not* a `wallets/tasks.py` task (that line is a drawdown-repair debit). Grant expiry: `grants.py` `GrantLedger.expire_due` (negative credit). All via `on_commit`, all gated by `enforcement_on`.

---

## 7. Discarded

The workflow produced a second, monolithic decomposition alongside WS1–WS8. It is **discarded** in favor of the finer-grained, independently-shippable workstreams below; only its two good ideas are harvested: the **`advisory` enforcement mode** (D1) and the **"never roll back the breaching event"** correction (D2/I3).
