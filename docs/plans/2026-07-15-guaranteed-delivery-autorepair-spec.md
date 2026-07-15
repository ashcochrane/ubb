# Guaranteed signal delivery + live-balance auto-repair — spec (ready to hand off)

**Date:** 2026-07-15 · **Origin:** map [#9](https://github.com/ashcochrane/ubb/issues/9), ticket
[#23](https://github.com/ashcochrane/ubb/issues/23) · **Status:** decisions locked with the user;
implementation not started.

Written against the re-issued one-rule enforcement spec
(`docs/plans/2026-07-15-one-rule-enforcement-spec.md`, draft PR
[#27](https://github.com/ashcochrane/ubb/pull/27)) — this document hardens the signal rails that
spec defines (`StopSignalState` §D, `stop.cleared` §E, the soft-floor pair §F,
`task.limit_exceeded`/`subtask.limit_exceeded` §A/§B) and must land with or after that build.
File:line anchors are against main, 2026-07-15.

**What this spec delivers.** The one-rule model made every limit a *signal point*: events always
land and bill; the stop/resume signal is the product. This spec makes that signal trustworthy,
end to end:

1. **Emission guarantee** — a real crossing always eventually produces the outbox event, even
   when the moment of detection is torn down by a crash.
2. **Delivery guarantee** — an emitted signal always eventually reaches the tenant, even when
   their webhook endpoint is down past the retry horizon.
3. **The honesty repair** — the fast live-balance counter converges back to reality when orphaned
   holds wedge it low (user principle, #12: *"we CANNOT have a wallet balance that does not show
   reality"*).
4. **The switch** — the whole arrival-time fast-trigger lane becomes a per-tenant choice with two
   honest postures; the guaranteed durable lane never switches off.

## Decisions locked in this spec's grilling (2026-07-15, ticket #23)

1. **Guarantee by re-detection, not by saving the original notification.** The signal-ledger
   transition and its outbox write stay inside the triggering transaction (atomically, §A); if
   that transaction dies, both vanish together — the system simply hasn't signalled yet. The
   guarantee comes from the layers behind: the durable lane re-notices the crossing on the next
   event that lands, and the hourly patrol (§C) — which already holds reconcile-SET power from
   the one-rule spec — is the traffic-independent backstop. Late, never lost (#11). An autonomous
   commit that survives the rollback was considered and rejected: it can announce a stop whose
   triggering spend never landed, and durable truth wins. (May be hardened later if evidence
   demands; re-detection ships first.)
2. **The patrol is the delivery guarantee; shared outbox retries stay untouched.** Today's rails
   retry a webhook 5 times over ~2h43m (`BACKOFF_SCHEDULE`,
   `apps/platform/events/tasks.py:20`; `OutboxEvent.max_retries`,
   `apps/platform/events/models.py:24`) then dead-letter with an ops alert — unchanged, for every
   product. For signal events, the hourly patrol re-mints a *fresh* event announcing the
   **current** state for as long as the state persists unannounced (§C.3). An endpoint down for a
   day gets the current bottom line within the hour of recovery — not a replay of every
   intermediate flap — matching #11's bottom-line-only catch-up (at most one net signal per owner
   per family). Queue stays bounded: at most one live announcement per signal row at a time.
3. **Full-writ patrol.** Task/subtask limit signals get the same guarantee as the floor families
   ("no new rail — one more scope", #28): the patrol sweeps active tasks sitting at-or-past their
   provider-cost limit and drives the idempotent kill flow, and re-mints dead-lettered
   kill events. The guarantee never depends on the tenant's traffic continuing.
4. **Upward repair with a two-pass grace window.** Expected live balance = durable balance −
   Σ(holds of genuinely pending ingest rows) — exact prices, no estimation slop, post ADR-0003.
   A deficit repairs only after persisting across **two consecutive hourly passes**, and only the
   amount both measurements agree on (§D). In-flight races live for seconds; an orphaned hold is
   a constant offset — an hour separates them essentially perfectly, and a false *upward* repair
   is the unsafe direction (it delays real stops). A repair that lifts a wedged stop fires
   `stop.cleared` through the same transition guard as any other clearing. Every repair writes an
   audit row; a repair-rate spike alerts (Stage D pattern). The existing downward MIN-merge is
   untouched.
5. **One switch, two postures.** A boolean on `Tenant` beside `enforcement_mode`, read through
   the flags module, governs the **whole arrival-time fast lane as one unit** (§E): estimate
   holds at accept, live Redis counters, arrival-moment floor detection, and the upward repair.
   The durable lane — settle-time detection, the signal ledger, the patrol, webhook delivery,
   ack verdicts — never switches off, and the tenant-facing contract (event types, ack schema) is
   identical in both postures; only the latency profile changes. **ON** (default, incl. tenant
   one): crossings detected at arrival; stop latency bounded, independent of settle-queue depth
   (the ≤5s p99 launch number presumes this). **OFF**: the competitor-normal posture (#21) —
   detection at settle, latency degrades exactly when a runaway spender floods the queue; the
   honest degraded mode. Flipping either way triggers an immediate per-tenant reconcile.

## Change list

### A. Atomic emission at the choke point

Today `_set_stop` writes `StopFired` in a savepoint and **swallows** a failed insert
(`apps/billing/gating/services/live_ledger_service.py:359-361`) — signalled internally, never
queued; and the documented orphan corner (`apps/platform/events/schemas.py:332-343`) leaves the
Redis flag set while the event row rolls back with the outer transaction, after which the NX
detector suppresses every re-emission until the flag clears.

- **The transition and the emit become one atomic unit.** Every signal emission — the
  `StopSignalState` winning transition (both families) and its `write_event`, the task/subtask
  kill flip and its `TaskLimitExceeded`/`SubtaskLimitExceeded` — executes inside a single
  savepoint nested in the ambient transaction. If the event insert fails, the savepoint rolls the
  transition back with it: **"transitioned but never queued" becomes impossible by
  construction.** The ambient work (the usage landing and billing) commits regardless — a signal
  hiccup must never block the one rule. The swallow `try/except` is deleted; the regression test
  at `apps/billing/gating/tests/test_live_ledger.py:237-279` is rewritten to the new contract
  (usage lands; state untransitioned; patrol catches it).
- **Ambient rollback is now clean, not a corner.** If the outer transaction dies, transition and
  event vanish together — a well-defined "not yet signalled" state. The fast-lane Redis flag
  (`client.set`, outside the DB transaction, `live_ledger_service.py:342`) may survive such a
  rollback; the patrol re-aligns it to durable truth (§C.2). Re-detection is guaranteed by the
  durable lane on the next landing event and by the patrol within the hour (§C.1).

### B. Announcement bookkeeping

"Guaranteed" must be checkable, so every signal-bearing row records what it last told the world:

- `StopSignalState` gains **`announce_outbox_id`** (nullable), stamped inside the §A atomic unit
  each time a transition or re-mint emits. `Task` gains the same stamp for its kill event.
- **Announced** = the stamped `OutboxEvent` reached terminal success — `processed`, or `skipped`
  (a tenant with no webhook config has chosen no push channel; that is vacuous success, never
  re-minted). **Unannounced** = stamp null while the state is non-initial, or the stamped row is
  terminally `failed`. A stamped row still `pending`/`processing` is in flight — the patrol
  leaves it alone.
- Re-minted events are ordinary events of the same catalog types carrying the current state and
  current `episode_seq`, plus **`re_announcement: true`** so consumers and ops can tell a fresh
  crossing from a repaired delivery. Consumers dedup on `episode_seq` as ever.

### C. The hourly patrol

All jobs join the existing hourly reconcile pass (`reconcile_live_ledgers`,
`apps/billing/gating/tasks.py:30-73`, beat `crontab(minute=25)`, `config/settings.py:227-230`,
enforcing tenants only) — no new scheduled task. Per owner:

1. **Drive missed transitions** (the one-rule spec's reconcile-SET power, §D there, restated as
   the emission backstop): durable balance past the configured floor / soft line with no
   corresponding stop/crossed state → drive the SET transition; recovered balance with a stale
   state → drive the CLEAR. Both families; each transition emits through §A.
2. **Re-align the fast flag**: make `ubb:stop:{owner}` match the `floor_stop` family's durable
   state (set or clear). The flag is the verdict cache read by acks (`read_stop`,
   `live_ledger_service.py:391-405`); durable truth owns it (§E makes durable transitions
   maintain it in both postures).
3. **Re-mint unannounced state** (§B): any signal row unannounced → mint a fresh current-state
   event, update the stamp. At most one in-flight announcement per row.
4. **Task sweep**: `Task` rows `status=active` with a non-null `provider_cost_limit_micros` and
   `total_provider_cost_micros` at-or-past it → `kill_task` (idempotent winning transition) →
   emits per §A. Killed-but-unannounced tasks → re-mint. Backed by a partial index on active
   limited tasks.
5. **Upward repair** (§D).

Worst-case emission latency after a crash: the next landing event (durable lane) or one patrol
interval (~1h), plus the delivery retry schedule — the "late, never lost" bound, documented in
the guarantee artifact's fine print (#16).

### D. Upward live-balance repair (prepaid wallet lane)

Orphaned holds — a Redis hold acquired, the `RawIngestEvent` row rolled back with a crashed
request — leave the prepaid live counter (`ubb:livebal:{owner}`) permanently below reality: the
stingy direction, false stops when it drifts far enough. The existing MIN-merge
(`_RECONCILE_MIN`, `live_ledger_service.py:93-106`) can only lower; this is its grace-gated
upward sibling.

- **Expected** = durable balance − Σ(`estimate_micros` of the owner's `RawIngestEvent` rows with
  `status="pending"`, `held=True` — `apps/metering/usage/models.py:146-150`), computed from one
  consistent DB snapshot; then the live counter is read. Post ADR-0003 those holds are exact
  prices (`estimate_exact` always true). **Deficit** = expected − live, when past a de-minimis
  constant (`REPAIR_DE_MINIMIS_MICROS`, default $1 — below it, drift is noise, not dishonesty).
- **Two-pass grace**: the first pass observing a deficit writes a **candidate** row and changes
  nothing. If the immediately-next pass (staleness-guarded: within <2.5h) still measures a
  deficit, the repair applies **min(first, second)** — the amount proven stable across a full
  hour — as a **relative `INCRBY`** on the live counter (never an absolute SET; safe under
  concurrent traffic). A vanished deficit lapses the candidate.
- **Audit + alert**: candidate and repair live in one model (`LiveBalanceRepair`: owner, status
  candidate/repaired/lapsed, both measurements, amount applied, live before/after, durable
  balance, pending sum, timestamps). Repair-rate spike (count and total amount per tenant per
  24h past a threshold) alerts CRITICAL — the Stage D reconciler pattern, beside the existing
  $50 `drift_spike` (`DRIFT_ALERT_MICROS`, `live_ledger_service.py:58`).
- **Resume on repair**: after applying, re-check the `floor_stop` family against the repaired
  balance; if the wedge lifted, drive the clear transition → `stop.cleared`, exactly once,
  through the same guard as every other clearing.
- **Interplay, explicitly**: the MIN-merge stays byte-identical (immediate, downward, target =
  durable). Accepted residual: live may transiently sit *above* expected by up to Σ(pending
  holds) — the generous direction, draining at settle within seconds. The postpaid spend counter
  (`ubb:livespend`, MAX-merge) is **not** in this repair's scope — its drift lane is owned by the
  MAX-merge + `reconcile_budget_counters` (`gating/tasks.py:8-27`), and the first tenant is
  prepaid.
- The repair exists only where holds exist: it is part of the fast lane and switches off with it
  (§E) — with the lane off no new orphans can accrue and the MIN-merge alone converges the
  counter.

### E. The switch — `arrival_signals_enabled`

- **Column**: `Tenant.arrival_signals_enabled = BooleanField(default=True)`, beside
  `enforcement_mode` (`apps/platform/tenants/models.py:80-82`). Not a `products` entry —
  `products` gates *access* to surfaces (403s); this flag selects a *behavior posture*, which is
  what `enforcement_mode` models. Meaningful only when enforcing.
- **Single read point**: `apps/platform/tenants/flags.py` gains
  `arrival_signals_on(tenant)` = `enforcing(tenant) and tenant.arrival_signals_enabled`, per the
  module's single-source-of-truth doctrine.
- **OFF disables, as one unit**: the accept-time Redis hold + arrival floor detection
  (`HoldService.acquire`, `apps/billing/gating/services/hold_service.py:232-253` — accept does no
  Redis work at all), the sync-path live debit + crossing check
  (`live_ledger_service.py:244-246`), the reconcile's counter jobs (seed/MIN-merge) for the
  tenant, and the §D repair.
- **Never off** (in enforcing): durable-lane detection at settle (one-rule §D), the signal
  ledger and its transitions, patrol jobs C.1–C.4, webhook delivery, ack verdicts. **The verdict
  cache is maintained by durable transitions in both postures** — the winning `floor_stop`
  transition sets/clears `ubb:stop:{owner}` — so `read_stop` and the ack schema are identical
  either way; only the latency profile changes.
- **Default ON**, including tenant one (prepaid, 100+ events/s, async — the exact profile the
  fast trigger was built for; the ≤5s p99 signal SLO presumes ON).
- **Toggle choreography**: flipping either way enqueues an immediate per-tenant reconcile pass —
  OFF→ON re-seeds honest counters from durable within minutes; ON→OFF needs nothing (outstanding
  holds drain naturally at settle).

### F. Ops surface

Patrol outcomes — re-mints, flag re-alignments, sweep kills, repairs (count + amount), lapsed
candidates — join the existing ops/ingest-health surface as counters. The dead-letter CRITICAL
alert (`alert_dead_letter`, `apps/platform/events/tasks.py:29-43`) stays exactly as is: a dead
tenant endpoint is worth a page even though the patrol guarantees eventual delivery.

### G. Docs + glossary (ride along in the implementing PR)

- New glossary entries via `/domain-modeling`: **Arrival signals (fast lane)** — the per-tenant
  posture and its two honest latency profiles; **Patrol** (or fold into the existing reconcile
  entry) — the hourly pass that guarantees emission, delivery, and counter honesty.
- The billing `CONTEXT.md` reconcile/stop-flag entries gain the re-mint + repair sentences.
- Guarantee-artifact wording changes are routed to #16, not made here.

## Test pins (the spec's definition of done)

1. Ambient-rollback corner: outer transaction dies after transition+emit → both vanish; the
   orphaned Redis flag is re-aligned and the signal fired by the next patrol pass; delivered
   late, never lost.
2. Emit-failure corner: the event insert fails → savepoint rolls the transition back; the usage
   event still lands and bills; the patrol fires the signal within one interval. (Rewrites
   `test_live_ledger.py:237-279`.)
3. Dead-lettered `stop.fired` → the patrol mints a fresh current-state announcement
   (`re_announcement: true`, same `episode_seq`, stamp updated); no mint while an announcement
   is in flight; announced-by-`skipped` (no webhook config) never re-mints.
4. Stop and clear both occurring while the endpoint is down → recovery delivers the current
   bottom line only (one cleared announcement), never the stale intermediate stop.
5. The soft pair rides the same rails: a dead-lettered `soft_floor.crossed` re-mints; soft and
   hard episodes stay independent families.
6. A task whose kill transaction crashed and that receives no further traffic is killed and
   announced by the patrol sweep within one interval; a subtask likewise, alone, parent
   unaffected.
7. Repair: an injected orphan deficit produces a candidate (no counter change) on pass one and a
   `min(d1,d2)` relative-increment repair with a complete audit row on pass two, correct under
   concurrent traffic; a repair that lifts a wedged stop fires `stop.cleared` exactly once.
8. A transient deficit (settle backlog) that resolves between passes lapses — no repair. A
   sub-de-minimis deficit never candidates.
9. Switch OFF: accept writes no Redis keys; acks keep the identical schema with verdicts from
   the durable-maintained flag; a floor crossing signals at settle latency; OFF→ON re-seeds via
   the immediate reconcile; the flag is read only through `flags.py`; default is ON.
10. MIN-merge regression pin: downward behavior byte-identical to today.
11. The repair-rate spike alert fires past its threshold.

## Consequences routed to other tickets

- **#16 (guarantee artifact):** the delivery promise is now speakable — *signals are
  at-least-once: late, never lost; an unreachable endpoint gets the current bottom line on
  recovery* — and the fine print gains the two-posture line: the ≤5s p99 presumes arrival
  signals ON; OFF is the documented settle-latency posture. Worst-case crash-corner latency:
  one patrol interval + delivery retries.
- **Proof stage (deferred, was #15):** this spec implies the chaos-drill shapes for whenever
  that stage runs — kill the process between flag-set and commit; endpoint dead >3h then
  recovering; orphan-hold injection with wedged-stop repair + resume. Recorded here so the
  deferred stage inherits them.
- **Implementation:** past the map's destination; not spawned here.

## Out of scope here

SSE / SDK background push (deferred beyond launch, #12) · infinite-retry outbox policy for any
event family (rejected — decision 2) · retargeting the MIN-merge at expected-minus-holds
(deliberately untouched) · postpaid spend-counter repair (owned by MAX-merge + budget reconcile)
· anything advisory (retired by the one-rule spec).
