# Spend-Control Guarantees — the proof, for a skeptical engineer

> **Accepted 2026-07-15 — wayfinder [#16](https://github.com/ashcochrane/ubb/issues/16).
> Live since 2026-07-17 — program close-out
> [#47](https://github.com/ashcochrane/ubb/issues/47).**
> Structure accepted and revised the same day into the final task/subtask vocabulary with both
> handed-off specs folded in — the
> [one-rule enforcement spec](https://github.com/ashcochrane/ubb/pull/27) and the
> [guaranteed-delivery + auto-repair spec](https://github.com/ashcochrane/ubb/pull/32). The
> build landed as the [#34](https://github.com/ashcochrane/ubb/issues/34) execution program
> (tickets #35–#46); the close-out verified all 29 spec pins green and removed every
> launch-gated marking from this document.

You are about to put UBB between your agents and your Stripe account. This document is the
case for trusting it with that position: exactly what we guarantee, the mechanism behind each
guarantee, what enforces it (a database constraint, application code plus a reconcile, or a
test pin), and what happens when our infrastructure fails. The companion
[integration guide](spend-control-integration.md) tells you how to wire it up; this document
tells you why the wiring holds.

Every statement below is **Live**: on `main` today, enforced as described — by a database
constraint, application code plus a reconcile, or a named test pin. The two implementation
specs' 29 pins (17 one-rule + 12 delivery) are all green in CI; §9 maps every pin to its
named test.

---

## 1. The claim

**Your customer's spend is never invisible and never surprising.** Every event your agents
emit is on the ledger the moment it reaches us — including past any limit, itemized with which
limit was active and why. The instant a limit or balance floor trips, we signal you to stop —
and signal again when it's safe to resume. Work in flight when the signal fires will land and
be billed; that overage is expected and visible. What we cannot do is reach into your
infrastructure and stop your agents for you — so the guarantee is: **you will always know,
immediately and exactly, and nothing your agent does will ever be off the books.**

Notice what the claim does *not* say. It does not say "your agent cannot physically
overspend," and it does not offer a dollar-denominated overshoot bound. We retired both
(decision: [#10](https://github.com/ashcochrane/ubb/issues/10)) — not because the enforcement
machinery is weak, but because any such promise is dishonest for report-after-the-fact
metering: UBB is not in your inference path and cannot un-spend a call already dispatched to
your provider. A vendor that quotes you a bound is quoting a number it will one day be held
to and cannot control, because the overshoot depends on *your* concurrency and *your*
reporting cadence. We promise the two things we fully control instead: **a complete ledger
and immediate signals.**

## 2. The one-rule model

Everything below follows from one rule and a small set of signal points.

**The rule: every event that reaches UBB is priced, recorded, and billed immediately.** No
doors, no parking states, no refusals of usage reports — on any path, in any failure mode, in
any enforcement mode. Every recorded event answers HTTP 200; errors exist only for requests
that genuinely didn't record (auth, malformed payload, unknown customer) — no code path
returns 429/409 for a usage report *(pin 7,
`api/v1/tests/test_one_rule_pins.py`)*. The balance always shows
reality, including negative: if your customer's floor is $0 and $2 of in-flight work lands
after the stop signal, the balance reads −$2 and a $20 top-up nets to $18. The one refusal
that survives is the **start-gate** declining to start a *new* task — refusing work that
hasn't happened yet is consistent with the rule; refusing to record work that has is not.

**The signal points:**

- **Task and subtask limits are signals, never billing walls.** A *task* is the unit of work
  you register (a workflow between two points, possibly spanning providers); a *subtask* is a
  child task with its own limit, whose spend also rolls up into its parent's. Limits are
  denominated in **provider cost (COGS)** — what the work costs, not what you bill for it.
  The tipping event lands and bills; the kill is a signal to you; events arriving on a killed
  task still land, bill, count into its totals, and carry stop context. A subtask crossing
  its limit is killed alone — its parent keeps running. *(Pins 1–2 and 13–14:
  `api/v1/tests/test_one_rule_pins.py`, `test_subtask_pins.py`.)*
- **The hard floor is a predetermined signal point, not a wall.** A tenant-set line on each
  customer's wallet: crossing it fires customer-scoped stop signals; a top-up re-crossing it
  fires **resume** (`stop.cleared`) the moment it happens — no smoothing, no headroom margin.
  *(Pins 4–6: `apps/billing/gating/tests/test_stop_resume_pins.py` — durable lane at the
  configured floor with Redis down, reconcile SETs a missed stop, resume once per episode on
  every path.)*
- **The soft floor refuses new starts, and that is all it does.** A second, higher tenant-set
  line per customer wallet: past it, running tasks may complete but new top-level tasks are
  refused at the start-gate, and a `soft_floor.crossed`/`soft_floor.cleared` webhook pair
  tells you which side of the line the customer is on. It never touches event acks and never
  tags events — work completing past the soft line is permitted by design. *(Pin 12:
  `apps/billing/gating/tests/test_soft_floor_pins.py`.)*

**Past-limit accounting.** Every event that lands after a trip carries stop context — which
limit, tripped when, arrived after — and a dedicated report returns the itemized "exactly
what was spent past the limit and why" per customer, grouped by stop episode, totalled in
both denominations. *(Pins 2, 9, 10: `api/v1/tests/test_past_limit_pins.py` — stop-context
schema, the end-to-end episode report, `negative_since` set and cleared.)*

**The worst case, accepted knowingly.** If every signal fails on a broken client, we keep
accepting, billing, and showing the truth — an unboundedly negative balance, visible with a
`negative_since` timestamp and an aged-negatives ops metric. The protection is a robust
signal suite plus total visibility, not a wall. We state this because you should hear the
worst case from us, with the mitigations, rather than discover an unstated one.

### How you receive the signals

The launch stop-propagation contract is a triad
(decision: [#12](https://github.com/ashcochrane/ubb/issues/12)):

1. **Every `record_usage`/ingest response** carries `stop` / `stop_reason` / `stop_scope`
   (plus `stop_context`) — for workers posting continuously, this is push-equivalent latency
   on a channel that cannot disconnect.
2. **Webhook push** covers idle and sibling workers — stop *and* resume events, for the hard
   floor, the soft floor, and task/subtask kills. Delivery is **at-least-once: late, never
   lost** — every emission rides an atomic transition guard, and an hourly patrol re-mints a
   fresh current-state announcement for any signal that never reached you, so an endpoint
   that was down for a day gets the current bottom line within the hour of recovery, not a
   replay of every intermediate flap. *(Delivery pins 3–5:
   `apps/billing/gating/tests/test_patrol_pins.py`.)*
3. **`pre_check`** is the poll and the start-gate.

The delivery fine print, in one place: signals are **at-least-once — late, never lost**; an
unreachable endpoint gets the **current bottom line** on recovery, never a replay of
intermediate flaps; the worst-case crash corner is **one patrol interval plus delivery
retries** (§6); and the ≤5s signal p99 presumes **arrival signals ON** — OFF is the
documented settle-latency posture (§8).

Signal latency is not asserted in this document — it is **measured**. The locked launch SLOs
(recorded in [the proof plan](https://github.com/ashcochrane/ubb/issues/15)): ingest-accept
p99 ≤ 200ms and stop-signal p99 ≤ 5s, under a 1-hour storm at 500 events/s (~5× the first
tenant's peak) with limit and floor crossings mid-storm — plus a hard pass/fail of **zero**
events lost or mis-tagged. The ≤5s number presumes arrival signals ON (the default posture —
see §8). Executing that proof (load, chaos drills, live Stripe money test — three legs) is
deferred to the testing stage that follows this map.

## 3. What the database itself refuses to break — and what it deliberately doesn't

The wallet's database-level rules protect the books being **true**, and nothing else
(doctrine: [ADR-002](adr/0002-db-constraints-enforce-facts-not-policy.md), decided in
[#13](https://github.com/ashcochrane/ubb/issues/13)):

- **No event is ever billed twice.** Every credit and debit carries an idempotency key under
  a unique constraint (`uq_wallet_txn_idempotency`; usage debits keyed
  `usage_deduction:{usage_event_id}`, top-ups keyed `auto_topup:{payment_intent_id}`).
  Replays, retries, and race losers become silent no-ops — the database, not application
  discipline, is the guarantee.
- **Granted credit is conserved.** A credit grant's remaining balance can never go below zero
  or above what was granted (`ck_grant_remaining_bounds`), and allocations can never exceed
  or double-refund their grant — CHECK-enforced.

**Spending limits are deliberately not database rules.** The wallet floors and the
task/subtask limits are *signal points*: their job is to trigger an immediate reaction to
spending — stop signals, and resume when a top-up re-crosses the floor — never to block the
record of spending that already happened. A database rule enforcing the floor would do the
opposite of this product's core promise: when real work arrived past the floor, the database
would reject the write and the books would lie. This is the same design as a bank ledger: an
overdraft is recorded, never refused.

The floor's integrity therefore rests on: crossing detection firing the signal suite, hourly
reconciles that repair any missed or dead-lettered debit exactly-once, and test pins holding
the behavior in CI. And "the balance shows the truth" is itself **measured, not asserted**:
the proof requires every touched wallet's running total to exactly equal the sum of its
transaction ledger after the load storm — any drift, even one micro-unit, is a hard fail.

## 4. The invariants table

Every guarantee below is classified by its *strongest* enforcement: a **database constraint**
(violations are impossible, not just detected), **application code + a reconcile** (violations
are possible in a window and then repaired or alarmed), or a **test pin** (behavior held in CI).
All pointers are to `ubb-platform/`; constraint names are the real ones in the schema, so you
can check them against a live database.

### Enforced by the database — cannot be violated

| Invariant | Constraint | Where |
|---|---|---|
| A usage event is never debited twice | `uq_wallet_txn_idempotency` — partial unique on `(wallet, idempotency_key)` | `apps/billing/wallets/models.py:97` |
| A top-up PaymentIntent is never credited twice | same constraint, key `auto_topup:{payment_intent_id}` | `apps/billing/topups/services.py:76` |
| A grant's remaining balance stays within `[0, granted]` | `ck_grant_remaining_bounds` | `apps/billing/wallets/models.py:190` |
| A grant allocation is positive and never refunds more than it allocated | `ck_grant_allocation_positive`, `ck_grant_alloc_refund_bounds` | `apps/billing/wallets/models.py:233-238` |
| A usage report is deduplicated per `(tenant, customer, idempotency_key)` | `uq_usage_event_idempotency_v2` | `apps/metering/usage/models.py:69` |
| An outbox event is handled at most once per handler | `uq_checkpoint_event_handler` | `apps/platform/events/models.py:56` |
| A Stripe webhook event is processed once | unique `stripe_event_id` | `apps/billing/stripe/models.py:21` |
| One usage invoice per customer per period | `uq_usage_invoice_customer_period` | `apps/billing/invoicing/models.py:107` |
| At most one pending auto-top-up per customer (no double charge) | `uq_one_pending_auto_topup_per_customer` | `apps/billing/topups/models.py:62` |

### Enforced by application code + a self-healing reconcile

| Invariant | Detection / repair | Where |
|---|---|---|
| `Wallet.balance_micros` == Σ ledger (it's a cached running total; the DB does not force them equal) | hourly auditor `reconcile_wallet_balances` logs any drift loud; the proof asserts exact equality as a hard pass/fail after the load storm (assertion recorded in [the proof plan](https://github.com/ashcochrane/ubb/issues/15); the proof stage itself is deferred to the testing phase) | `apps/billing/wallets/tasks.py:11` |
| Full grant-conservation equation (spans parent + child rows, so not expressible as one CHECK) | same hourly auditor; randomized fuzz pin in CI | `apps/billing/wallets/tasks.py:11-45` |
| Every settled usage event on a prepaid wallet has its debit, even if the async pipeline died mid-flight | `reconcile_usage_drawdowns` repairs exactly-once (see §7) | `apps/billing/wallets/tasks.py:105` |
| Every succeeded top-up charge is credited, even if our webhook never arrived | `reconcile_topups_with_stripe` repairs from Stripe's ledger (see §7) | `apps/billing/connectors/stripe/tasks.py:118` |
| The fast-lane (Redis) balance tracks the durable one | `reconcile_prepaid` MIN-merges hourly + drift alarm; the upward auto-repair rides the same pass for orphaned holds (see §7) | `apps/billing/gating/services/live_ledger_service.py:530`, `apps/billing/gating/repair.py` |
| A true crossing always eventually produces exactly one signal, and that signal always eventually reaches you | the durable signal ledger (`StopSignalState`, one row per owner per family) + atomic transition-and-emit through one winning-transition guard (`drive_stop`/`drive_clear`) + the hourly patrol | `apps/billing/gating/models.py:38`, `apps/billing/gating/services/stop_signal_service.py:79`, `apps/billing/gating/patrol.py:51` |
| The floors and limits fire their signals | application signal suite by design — never a DB rule ([ADR-002](adr/0002-db-constraints-enforce-facts-not-policy.md)) | `apps/billing/gating/services/` |

### Pinned by tests in CI

| Behavior | Representative pins |
|---|---|
| A below-floor event still lands, bills, and persists; the stop is a separate signal | `apps/billing/gating/tests/test_live_ledger.py` (`test_record_usage_crossing_returns_stop_event_persists_and_replays`), `test_e2e_seam.py` (`test_full_customer_wide_stop_pipeline`); the explicit ADR-002 pin is `api/v1/tests/test_one_rule_pins.py::Pin3BelowFloorLandsTest` (`test_wallet_carries_no_floor_check`) |
| Concurrent replays of the same debit/credit produce exactly one transaction | `apps/billing/tests/test_concurrency_races.py` (`test_two_concurrent_drawdowns_same_event_one_debit`, `test_two_concurrent_topup_credits_same_pi_one_credit`) |
| Reconcile repair is itself exactly-once | `apps/billing/wallets/tests/test_reconcile_drawdowns.py` (`test_repairs_missing_debit_exactly_once`, `test_does_not_redebit_already_debited_via_column`) |
| Grant conservation survives randomized grant/spend/void/dispute/refund sequences | `apps/billing/wallets/tests/test_grant_invariant_fuzz.py` (`test_random_sequence_holds_invariants`) |
| Limit trip → scoped kill signal; the tipping event lands and bills; killed units keep counting; the start-gate refuses new starts on a set stop flag | the 29-pin suite (§9): `api/v1/tests/test_one_rule_pins.py`, `test_subtask_pins.py`, `test_past_limit_pins.py`, `test_delivery_pins.py`; `apps/billing/gating/tests/test_stop_resume_pins.py`, `test_soft_floor_pins.py`, `test_mode_pins.py`, `test_patrol_pins.py`, `test_repair_pins.py`, `test_switch_pins.py`; plus `test_p6_fanout.py` (kill fan-out under the 200-always contract) |
| A negative balance is allowed and does not block recording | `apps/billing/gating/tests/test_risk_service.py` (`test_postpaid_negative_balance_still_allowed`) |

## 5. The idempotency story: keys that never expire

Exactly-once billing rests on idempotency keys under `uq_wallet_txn_idempotency` — and on the
fact that **the keys are never deleted**. There is no TTL, no cleanup task, and no code path
that deletes a `WalletTransaction`: the scheduled cleanup jobs touch only processed Stripe
webhook events, processed outbox rows, and webhook delivery attempts — never the wallet
ledger. This is load-bearing, not housekeeping neglect: the reconciles in §7 re-derive intent
from durable state hours or days after the fact, and a replay arriving at *any* distance —
a Celery redelivery seconds later, a reconcile repair six hours later, a Stripe webhook
retried three days later — collapses into a silent no-op against the same key. Expiring keys
would convert every late replay into a double charge.

The key namespace, so you can audit the ledger yourself:

| Key format | Written by | Where |
|---|---|---|
| `usage_deduction:{usage_event_id}` | live drawdown on settle, and the reconcile repair — deliberately the **same key**, so live and repair can race and one wins | `apps/billing/handlers.py:54`, `apps/billing/wallets/tasks.py:136` |
| `auto_topup:{payment_intent_id}` | the charge task, the `payment_intent.succeeded` webhook, and the Stripe reconcile — three paths, one key, one credit | `apps/billing/topups/services.py:76` |
| `topup:{checkout_session_id}` | Stripe Checkout top-up webhook | `apps/billing/connectors/stripe/webhooks.py:95` |
| `expiry:{grant_id}` | grant expiry | `apps/billing/wallets/grants.py:94` |
| `dispute:{dispute_id}` | dispute deduction | `apps/billing/connectors/stripe/webhooks.py:305` |

One deliberate asymmetry on the async path: the raw ingest table (`RawIngestEvent`) has **no**
uniqueness constraint at all. It is an at-least-once append log — accepting your events must
never wait on a dedup check. Exactly-once is enforced downstream, where it counts: settle
writes the `UsageEvent` under `uq_usage_event_idempotency_v2`, and the debit under
`usage_deduction:{usage_event_id}`. Duplicates die at the money boundary, not the front door
(`apps/metering/usage/models.py:156`).

## 6. When our infrastructure fails

The design direction (decision: [#11](https://github.com/ashcochrane/ubb/issues/11)): the
**Postgres ledger is the guaranteed signal lane; Redis is the fast lane**. Signals are durable
at-least-once — a crossing that happens while we're blind signals late, never gets lost.
Catch-up after any blind window is bottom-line only: at most one net stop-or-resume per
customer per signal family, judged against what you were last told (the durable signal
ledger's job); the blow-by-blow history stays in the itemized ledger. Money is never in the
failure equation, because of the one rule: there is no door to fail open or closed.

One structural fact first, because every cell below follows from it: **a single Redis
instance is simultaneously the live-counter store, the Django cache, and the Celery broker**
(`ubb-platform/config/settings.py:107-118`). "Redis down" therefore means crossing detection
goes blind *and* all async work (outbox drain, webhook delivery, wallet drawdown, settle,
every reconcile) pauses — all of it Postgres-durable, all of it drains on recovery. And on
both ingest paths, **the durable write is Postgres and it commits before anything else
matters**: the sync path writes the `UsageEvent` in-request; the async path bulk-inserts
`RawIngestEvent` rows and only acks after that commit. The wallet drawdown is *never*
synchronous — it rides the outbox to a worker on both paths.

| Failure | Sync path (`record_usage`) | Async path (`ingest`) | What accumulates → how it heals |
|---|---|---|---|
| **Redis down** | Every enforcement Redis touch fails open with a log warning — limit checks, live debit, stop publish (`live_ledger_service.py:187-380`). The `UsageEvent` still commits, and the post-commit dispatch (the "doorbell") carries a broker-down guard: the response stays **200**, the durable row is the queue, and delivery resumes within a minute of broker recovery *(delivery pin 12, `api/v1/tests/test_delivery_pins.py`)*. | Same shape: idempotency pre-filter and holds fail open (`hold_service.py:209-218`), the `RawIngestEvent` batch still commits, and the same guarded doorbell keeps the accept a 200. | Signals are what's lost *in the moment*: no crossing detection, no stop flags fire while blind (the durable start-gate on task start still works — it reads Postgres). Outbox rows and raw events pile up Postgres-durable. On recovery the 1-min sweep drains the outbox, the 10s sweeper settles raws, hourly reconciles re-merge counters — and the durable lane fires **at most one net stop/resume per customer per family** for anything crossed while blind: the reconcile has SET power and the hourly patrol re-aligns the fast flag to durable truth *(pin 5, `test_stop_resume_pins.py`; delivery pin 1, `test_patrol_pins.py`)*. |
| **Celery workers dead** (broker up) | Clean 200s. Pricing, the durable `UsageEvent`, and the live Redis counter + stop flag are all in-request, so **stop verdicts stay accurate and immediate**. What stalls: the wallet drawdown, durable suspend, and webhook delivery — all worker-side. | Clean 2xx accepts with accurate hold/stop verdicts (holds are synchronous Redis). Nothing settles. | Pending outbox rows, broker queues, unsettled raws, and unsettled estimate holds accumulate. Note the drift direction: unsettled holds leave the live balance *over-restrictive* (pessimistic), and durable wallets read stale-*high* — the fast lane errs toward stopping you early, never toward hiding spend. Workers return → backlogs drain, reconciles run; the 6h drawdown grace is sized above the outbox retry horizon so repair never races live delivery. |
| **Postgres down** | Immediate 5xx, **before any money state changes**: the first statement is a Postgres read, and the Redis debit sits after the durable write, so it is never reached. Nothing acked, nothing mutated. | The 2xx only exists after the `RawIngestEvent` commit. If Postgres dies mid-request, every hold taken is released and fresh idempotency keys are unwound before the 5xx (`api/v1/metering_endpoints.py:308`, `_ingest_idem_unwind`). **Nothing can be acked-then-lost, and no money state is stranded.** | Redis live counters and stop flags freeze untouched (they can't be reconciled without Postgres, and can't drift without new events). Recovery: reconciles re-merge; nothing to repair because nothing was accepted. |

The direction of every degradation is the same, and it is the decided one
([#11](https://github.com/ashcochrane/ubb/issues/11)): **failure degrades toward
accepting-and-recording with late signals — never toward losing events, refusing usage
reports, or double-billing.** The one drift that runs the other way (unsettled holds
over-restricting the fast lane) errs pessimistic and is repaired by the upward
auto-repair (§7). The fine print on "late": the worst crash corner — a signal's triggering
transaction torn down at the exact moment of detection — is re-detected by the next landing
event or by the hourly patrol, then delivered on the retry schedule; **one patrol interval
plus delivery retries** is the bound, and a crossing is never lost, because it is recomputed
from the Postgres ledger, which never stopped being written.

## 7. Self-healing: the reconciles

Application-enforced invariants hold because scheduled jobs continuously re-derive the truth
from durable state and repair drift — each repair exactly-once via the same idempotency keys
as the live path, so a reconcile can never double-apply what the live path already did. The
schedule is `CELERY_BEAT_SCHEDULE` in `ubb-platform/config/settings.py:150-272`. Window
sizing is not arbitrary: each grace/lookback is sized *above* the retry horizon of the
mechanism it backstops, so a reconcile never races something that would have succeeded on
its own.

| Job | Schedule | Repairs / detects | Exactly-once & windows |
|---|---|---|---|
| `sweep_outbox` | every 1 min | re-dispatches outbox events due for retry; reclaims rows stuck `processing` > 5 min; alerts on dead-letter | backoff 30s → 2m → 10m → 30m → 2h, max 5 attempts (`apps/platform/events/tasks.py:23,85`); per-handler dedup via `uq_checkpoint_event_handler`. The post-commit dispatch "doorbell" carries a broker-down guard — the row is the queue, the doorbell is a latency optimization *(delivery pin 12, `api/v1/tests/test_delivery_pins.py`)* |
| `reconcile_usage_drawdowns` | hourly at :40 | any settled usage event on a prepaid wallet whose debit never landed (e.g. outbox dead-lettered) — repairs the debit | anti-join on `WalletTransaction.usage_event_id` + key `usage_deduction:{id}`; **6h grace, deliberately > the ~2h43m outbox retry horizon** so live delivery always gets to finish first; 7-day lookback; repair-rate spike alarm (`apps/billing/wallets/tasks.py:105-171`) |
| `reconcile_topups_with_stripe` | hourly at :20 | any *succeeded* Stripe PaymentIntent with no local wallet credit — credits it from Stripe's ledger (Stripe is the source of truth for money movement); secondary amount/refund audit | key `auto_topup:{pi_id}`; **4-day lookback, > Stripe's ~3-day webhook retry horizon**; 48h audit window (`apps/billing/connectors/stripe/tasks.py:118-208`) |
| `reconcile_wallet_balances` | hourly at :00 | **auditor, not repairer**: checks `balance == Σ ledger` and grant conservation on every wallet; any drift logs loud | detect-and-alarm by design — an automated "fix" would hide the bug that caused the drift (`apps/billing/wallets/tasks.py:11-96`) |
| `reconcile_live_ledgers` → `reconcile_prepaid` | hourly at :25 | MIN-merges the fast-lane (Redis) prepaid balance toward the durable wallet balance; alarms on drift spikes; both **clears** stale stop flags for recovered customers and **sets** missed ones — the crossed-while-blind-then-went-quiet hole is closed (decision: [#11](https://github.com/ashcochrane/ubb/issues/11)) | conservative merge direction — the fast lane may only be *more* cautious than durable truth, never less (`apps/billing/gating/services/live_ledger_service.py:530`); *(pin 5, `test_stop_resume_pins.py`)* |
| the hourly patrol | rides the :25 pass | the signal suite's backstop, traffic-independent: drives missed stop/soft-floor transitions (both directions), re-aligns the fast `ubb:stop` flag to durable truth, **re-mints a fresh current-state announcement** for any signal that never reached you, sweeps active tasks sitting at-or-past their provider-cost limit and kills them idempotently | `apps/billing/gating/patrol.py:51`; announcement bookkeeping via `announce_outbox_id` stamps, re-mints marked `re_announcement: true`, at most one in-flight announcement per signal row; `PatrolOutcome` counters surface as `patrol_*_7d` on ops ingest-health *(delivery pins 1–6, `test_patrol_pins.py`)* |
| live-balance upward repair | rides the :25 pass | orphaned arrival-time holds (a hold acquired, the ingest row rolled back with a crashed request) leave the live counter wedged low — the stingy direction, false stops. Expected = durable − Σ(pending held estimates), exact prices post-ADR-0003; a deficit must persist across **two consecutive hourly passes** and repairs by **min(first, second)** as a relative increment, never an absolute set; every repair audited (`LiveBalanceRepair`), repair-rate spike alerts, and a repair that lifts a wedged stop fires `stop.cleared` through the same guard as every other clearing | `apps/billing/gating/repair.py`, `apps/billing/gating/models.py:130`; principle, verbatim ([#12](https://github.com/ashcochrane/ubb/issues/12)): "we CANNOT have a wallet balance that does not show reality" *(delivery pins 7–8/10–11, `test_repair_pins.py`)* |
| `expire_credit_grants` | hourly at :10 | expires past-due credit grants | key `expiry:{grant_id}`; clamped so expiry never takes back spent credit (`apps/billing/wallets/tasks.py:178-256`) |
| `settle_raw_events` | every 10s | straggler sweeper: settles async raw events the inline settle missed | settle itself is exactly-once via `uq_usage_event_idempotency_v2` + the debit key (`apps/metering/usage/tasks.py:19-96`) |
| `monitor_ingest_health` | every 5 min | alerting only: ingest lag/queue-depth/failed-count thresholds | *known weakness, acknowledged: it is itself a Celery task, i.e. in-band with the failure it reports. The decided fix ([#11](https://github.com/ashcochrane/ubb/issues/11)) — a pull-based health endpoint with a Redis probe, watched by an outside poller — is deferred to the testing/ops stage along with the rest of the environment work* |

Two properties worth stating explicitly, because they're where reconcile designs usually go
wrong:

- **Repairs never re-fire side effects.** A back-corrected debit does not re-trigger suspend
  or overage events; signal state transitions fire only on true state changes — every
  emission, from either lane or any repair, routes through one winning-transition guard per
  owner per signal family, so a crossing observed twice still signals once.
- **Every repair path shares its idempotency key with the live path.** There is no
  "reconcile namespace" — repair and live delivery race safely for the *same* row, so the
  question "did the live path or the reconcile do this?" can never become "did both?"

## 8. What the rest of the market does

You should know the convention you're comparing us against
(survey of 7 vendors' official docs, 2026-07-14:
[#21](https://github.com/ashcochrane/ubb/issues/21)). Metronome, Orb, OpenMeter, Lago, Stripe
native usage billing, m3ter, and Amberflo all converge on the same shape: **minutes-latency
alerts against an eventually-consistent balance, overrun tolerated and settled financially
afterwards, stopping delegated to the tenant's app.** Metronome documents 3-minute threshold
evaluation and 5-minute webhook delivery; Orb caps the *invoice* rather than stopping usage;
OpenAI's own prepaid platform bills overrun as a negative balance. No surveyed vendor
documents arrival-time cost estimation or balance holds. UBB's arrival-time crossing
detection is (as far as vendor docs show) unique — and since the MVP dropped tiered pricing
(ADR-0003), the arrival-time price is **exact**, not an estimate: per-unit and flat pricing
compute the same number at accept and at settle. It is also an honest per-tenant choice
(`Tenant.arrival_signals_enabled`, read only through `flags.arrival_signals_on` —
*delivery pin 9, `test_switch_pins.py`*): arrival
signals **ON** (the default) buys stop-signal latency that is independent of settle-pipeline
health; **OFF** is the documented competitor-normal posture — detection at settle, where the
alarm slows down exactly when a runaway spender floods the queue. Same contract, same events,
two latency profiles. The industry default is not a truer balance; it is slower signals
against a staler one.

## 9. The pin ledger — every promise's named test

The two implementation specs each shipped with a numbered definition of done. All 29 pins
are live tests on `main`, verified green by the program close-out
([#47](https://github.com/ashcochrane/ubb/issues/47), 2026-07-17) on a fully green suite.
This table is the acceptance gate made auditable: run any row yourself.

**One-rule enforcement spec** ([PR #27](https://github.com/ashcochrane/ubb/pull/27),
`docs/plans/2026-07-15-one-rule-enforcement-spec.md` §L). Paths under `ubb-platform/`;
`api/v1/tests/` and `apps/billing/gating/tests/` abbreviated after first use.

| Pin | Holds | Named test |
|---|---|---|
| 1 | The tipping event lands and bills — sync task, sync subtask, async at settle | `api/v1/tests/test_one_rule_pins.py::Pin1SyncTippingEventTest`, `::Pin1AsyncSettleTest`; `test_subtask_pins.py::Pin1SubtaskTippingEventTest` |
| 2 | Events on a killed task land, bill, count into both totals, carry stop-context | `test_one_rule_pins.py::Pin2KilledTaskStillCountsTest`; `test_past_limit_pins.py::Pin2StopContextOnKilledTaskTest` |
| 3 | A below-floor event lands and bills; `Wallet` carries no floor CHECK (ADR-002) | `test_one_rule_pins.py::Pin3BelowFloorLandsTest` |
| 4 | Durable lane fires at the **configured** floor with Redis down; exactly one stop per crossing | `apps/billing/gating/tests/test_stop_resume_pins.py::TestPin4DurableLane` |
| 5 | `reconcile_prepaid` SETs a missed stop, not just clears a stale one | `test_stop_resume_pins.py::TestPin5ReconcileSetsAMissedStop` |
| 6 | Resume fires at the exact re-cross — once per episode, via credit, reconcile, and durable paths | `test_stop_resume_pins.py::TestPin6ResumeOncePerEpisode` |
| 7 | Every recorded event answers 200; no 429/409 for a usage report | `test_one_rule_pins.py::Pin7TwoHundredAlwaysTest` |
| 8 | `advisory` migrated to `off`; two-position mode; `off` is Tier-1 byte-for-byte | `apps/billing/gating/tests/test_mode_pins.py` (all six tests) |
| 9 | The past-limit report reconstructs an episode end-to-end | `test_past_limit_pins.py::Pin9PastLimitReportTest` |
| 10 | `negative_since` set on ≥0→<0, cleared on recovery; aged-negatives ops metric | `test_past_limit_pins.py::Pin10NegativeSinceTest` |
| 11 | Zero-crossing `balance_overage` early warning unaffected | `test_stop_resume_pins.py::TestPin11EarlyWarningUnaffected` |
| 12 | Soft floor refuses new top-level starts only; subtask pass-through; crossed/cleared exactly once; acks never change | `apps/billing/gating/tests/test_soft_floor_pins.py::TestPin12StartGate`, `::TestPin12PairExactlyOnce` |
| 13 | Subtask killed alone — parent keeps running; parent trip cascades | `api/v1/tests/test_subtask_pins.py::Pin13ContainmentTest` |
| 14 | Only the provider (COGS) total races a limit; both totals on record and response | `test_one_rule_pins.py::Pin14DenominationTest`; `test_subtask_pins.py::Pin14SubtaskDenominationTest` |
| 15 | Coverage gate: a resolvable limit without cost coverage is refused `cost_coverage_required` | `test_one_rule_pins.py::Pin15CoverageGateTest` |
| 16 | Tag fallback removed — tags are analytics only | `test_one_rule_pins.py::Pin16TagFallbackRemovedTest` |
| 17 | The clean cut holds: no run-era name on any surface | `test_one_rule_pins.py::Pin17CleanCutSweepTest` |

**Guaranteed-delivery + auto-repair spec**
([PR #32](https://github.com/ashcochrane/ubb/pull/32),
`docs/plans/2026-07-15-guaranteed-delivery-autorepair-spec.md`):

| Pin | Holds | Named test |
|---|---|---|
| 1 | Ambient-rollback corner: orphaned flag re-aligned, signal fired by the next patrol pass | `apps/billing/gating/tests/test_patrol_pins.py::TestPin1AmbientRollback` |
| 2 | Emit-failure corner: savepoint rolls the transition back with the failed insert; the event still lands; the patrol fires within one interval | `test_live_ledger.py::test_pin2_failed_event_insert_rolls_the_transition_back`; `test_patrol_pins.py::TestPin2EmitFailureCompletes` |
| 3 | Dead-lettered `stop.fired` re-minted as a fresh current-state announcement, same episode | `test_patrol_pins.py::TestPin3RemintUnannounced` |
| 4 | Stop + clear during a blind window → recovery delivers the current bottom line only | `test_patrol_pins.py::TestPin4BottomLineOnly` |
| 5 | The soft pair rides the same rails; families stay independent | `test_patrol_pins.py::TestPin5SoftFamilyRidesTheSameRails` |
| 6 | A crashed kill is swept and announced within one interval; a subtask alone | `test_patrol_pins.py::TestPin6TaskSweep` |
| 7 | Two-pass repair: candidate on pass one, `min(d1,d2)` relative increment + full audit on pass two; a lifting repair fires `stop.cleared` once | `test_repair_pins.py::TestPin7TwoPassRepair` |
| 8 | A transient deficit lapses; sub-de-minimis never candidates | `test_repair_pins.py::TestPin8TransientAndDeMinimis` |
| 9 | Switch OFF: no Redis writes on accept, identical ack schema, verdicts from the durable flag, a floor crossing signals at settle latency, OFF→ON re-seeds, flag read only through `flags.py`, default ON | `apps/billing/gating/tests/test_switch_pins.py` (20 tests incl. the AST doctrine scan) |
| 10 | MIN-merge downward behavior byte-identical; pending holds are never a deficit | `test_repair_pins.py::TestPin10DownwardNeighborsUntouched` |
| 11 | The repair-rate spike alert fires past its threshold | `test_repair_pins.py::TestPin11RepairSpikeAlert` |
| 12 | Broker down at accept: durable row written, response 200, delivery within a minute of recovery | `api/v1/tests/test_delivery_pins.py::BrokerDownAtAcceptTest` |

**What still stands between here and launch** — outside this document's guarantees, stated
so nothing is blurred: **the proof stage**, deferred to the testing phase — three legs: load
(the §2 SLOs: accept p99 ≤ 200ms, signal p99 ≤ 5s, zero lost/mis-tagged events under a
1h/500eps storm), chaos drills (the §6 failure modes, observed live), and the operator-run
real-money Stripe test — plus the balance ≡ Σ ledger hard assertion. The soak leg was
dropped with advisory mode. [The proof plan](https://github.com/ashcochrane/ubb/issues/15)
records the locked numbers and the descope.

---

*Supersedes the "honest guarantee (and its bound)" section of the
[integration guide](spend-control-integration.md) — the bound formula is retired
([#10](https://github.com/ashcochrane/ubb/issues/10)). The guide now speaks the shipped
contract: the task/subtask vocabulary and the 200-always wire contract.*
