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
specs numbered 29 pins (17 one-rule + 12 delivery); **28 are live tests green in CI and one
(one-rule pin 15) was retired by deletion** — §9 maps every pin to its named test and says at
that row what was removed and why.

Spend control was re-modelled after those specs were written: it is now **four families**,
each named on every stop, refusal and event, and each living where its subject lives
([ADR-0014](adr/0014-spend-control-is-four-families-and-the-ceiling-is-a-kernel-concept.md)).
The guarantees are unchanged by that re-model — what changed is which control a signal names,
and §2 below says so family by family.

---

## 1. The claim

**Your customer's spend is never invisible and never surprising.** Every event your agents
emit is on the ledger the moment it reaches us — including past any control's line, itemized
with which control was in force and why. The instant a control's line is reached, we signal
you to stop — and signal again when it's safe to resume. Work in flight when the signal fires
will land and be billed; that overage is expected and visible. What we cannot do is reach
into your infrastructure and stop your agents for you — so the guarantee is: **you will
always know, immediately and exactly, and nothing your agent does will ever be off the
books.**

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

Everything below follows from one rule and four families of control.

**The rule is a promise about recording, and only about recording: every structurally valid,
authenticated, idempotently consistent usage report that reaches UBB is durably recorded and
acknowledged.** No doors, no parking states, no refusals of usage reports — on any path, in
any failure mode, in any enforcement mode. Every recorded event answers HTTP 200; errors
exist only for requests that genuinely didn't record (auth, malformed payload, unknown
customer) — no code path returns 429/409 for a usage report *(pin 7,
`ubb-platform/api/v1/tests/test_one_rule_pins.py`)*.

**Costing, pricing and billing are separate outcomes** that may stay unresolved or may not
apply, and none of them is a condition of the acknowledgement: an event UBB cannot cost yet
is recorded with its cost unresolved and the gaps counted, rather than counted as zero. The
promise is that the evidence is kept, not that every number beside it is final in the same
instant. **Spend control never rejects evidence of work that already happened.**

The balance always shows reality, including negative: if your customer's floor is $0 and $2
of in-flight work lands after the stop signal, the balance reads −$2 and a $20 top-up nets to
$18. The one refusal that survives is the **start-gate** declining to start *new* work —
refusing work that hasn't happened yet is consistent with the rule; refusing to record work
that has is not.

### The four families, and where each lives

Every stop, refusal and terminal event names its family in a `control_family` field and the
row that carried it in a `control_id`, so you never parse a name to learn what stopped you
([ADR-0014](adr/0014-spend-control-is-four-families-and-the-ceiling-is-a-kernel-concept.md)).
The kernel's two apply to **every** tenant, including one that does not bill through UBB; the
billing product's two apply where there is a wallet to apply them to.

- **Ceiling** (`ceiling`, kernel) — **a bound on one unit of work, and it is a signal, never
  a billing wall.** A *task* is the unit of work you register (a workflow between two points,
  possibly spanning providers); a *subtask* is contained work with its own ceiling, whose
  spend also rolls up into its parent's. Its cost form is denominated in **provider cost
  (COGS)** — what the work burns, not what you bill for it; its two time forms are the
  silence window and the absolute deadline. **At or above the line stops**, in every lane:
  the recording lane, the hourly patrol and the utilisation report all compare through one
  predicate, so a known total landing exactly on the ceiling is `ceiling_reached` and is
  stopped. The tipping event lands and bills; the kill is a signal to you; events arriving on
  a killed unit still land, bill, count into its totals, and carry stop context. Contained
  work reaching its own ceiling is killed alone — its parent keeps running. **Declaring a
  ceiling is itself the opt-in**, so this family runs whatever the enforcement switch says.
  *(Pins 1–2 and 13–14, and the boundary is pin 1's own arithmetic.)*
- **Customer spend pool** (`customer_spend_pool`, billing) — a bound on one customer's charges
  over a period, at two levels (the seat's and the billing owner's) with a counter each. A
  `blocking` pool stops a prepaid customer exactly as it stops a postpaid one; an
  `alert_only` pool announces its levels and never stops. Known-over fires on a **pair** —
  the resolved period charges beside the count of postings UBB could not price — so nothing
  sums an unknown as zero.
  *(`ubb-platform/apps/billing/gating/tests/test_a_blocking_pool_stops_prepaid_work_as_it_stops_postpaid.py`.)*
- **Wallet policy** (`wallet_policy`, billing) — policy on the wallet rather than on any one
  unit of work: the **hard floor**, a tenant-set line whose crossing fires customer-scoped
  stop signals and whose re-crossing fires **resume** (`customer.stop_cleared`) the moment it
  happens, with no smoothing and no headroom margin *(pins 4–6)*; the **soft floor**, a
  second, higher line past which running work may complete but new top-level starts are
  refused, announced by the `wallet_policy.soft_floor_crossed` /
  `wallet_policy.soft_floor_cleared` pair — it never touches event acks and never marks
  events with stop context *(pin 12; the stop-context half is
  `ubb-platform/apps/metering/usage/services/stop_context.py`, which writes no soft-floor
  entry)*; and the
  **reservation** a prepaid start takes against an agreed price, which makes affordability
  `balance − open reservations` and is released on every terminal path.
- **Admission control** (`admission_control`, kernel) — a bound on how fast new top-level work
  may enter, per seat, in a fixed window of one minute. It says nothing about supplier cost
  and **is never spend protection**: a replay, contained work, a usage report, a close and
  configuration are all outside it. Its refusal is an ordinary `429` carrying retry
  information, it opens no episode, and it has no webhook.

**Past-a-stop accounting.** Every event that lands after a stop carries stop context — which
stop, reached when, arrived after — and Stops and breaches (`GET /api/v1/spend-controls/
stops-and-breaches`, #465) returns the itemized "exactly what was spent past a stop and why",
tenant-wide or per customer, grouped by stop episode under its family, totalled in both
denominations. The per-customer report that first answered it retired in #466. *(Pins 2, 9, 10:
`ubb-platform/api/v1/tests/test_past_limit_pins.py` — stop-context schema, the two episode cases
the successor's own module does not drive, `negative_since` set and cleared;
`ubb-platform/api/v1/tests/test_spend_control_reports.py` — the end-to-end reconstruction.)*

**The blind window is documented, not mitigated** (#150 §12). Work already dispatched to your
provider before a ceiling is observed may complete, report, and raise the final cost past that
ceiling. Those events are accepted, costed and marked as having arrived after the stop — the
stop-context machinery, unchanged — and nothing pretends the window is closed. There is no
per-kind concurrency field and no artificial headroom. UBB **had** a per-owner cap on how much
work could be running at once and **deleted it by name**: a count of work already running
converts to no amount of money, and its existence invited the belief that UBB closes a window
it cannot see into.

**The worst case, accepted knowingly.** If every signal fails on a broken client, we keep
accepting, billing, and showing the truth — an unboundedly negative balance, visible with a
`negative_since` timestamp and an aged-negatives count on the ops surface. The protection is a
robust signal suite plus total visibility, not a wall. We state this because you should hear the
worst case from us, with the mitigations, rather than discover an unstated one.

### How you receive the signals

The launch stop-propagation contract is a triad
(decision: [#12](https://github.com/ashcochrane/ubb/issues/12)):

1. **Every `record_usage` response** carries `stop` / `stop_reason` / `stop_scope`
   (plus `stop_context`) — for workers posting continuously, this is push-equivalent latency
   on a channel that cannot disconnect.
2. **Webhook push** covers idle and sibling workers — stop *and* resume events, for the hard
   floor, the soft floor, the spend pool's levels, and task/subtask kills. Delivery is
   **at-least-once: late, never lost** — every emission rides an atomic transition guard, and
   an hourly patrol re-mints a fresh current-state announcement for any signal that never
   reached you, so an endpoint that was down for a day gets the current bottom line within the
   hour of recovery, not a replay of every intermediate flap. *(Delivery pins 3–5:
   `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py`.)*
3. **The affordability question** is the poll:
   `GET /api/v1/billing/customers/{customer_id}/affordability`, at the Read role floor, for a
   tenant with the billing product. It answers `200` with `allowed` and, on a denial, a
   `reason` from the open `affordability_reason` vocabulary, beside the balance, the amount
   available once open reservations are taken out, and the two resolved floors. **It registers
   nothing and consumes no admission allowance**, so polling it can never be the thing that
   makes the next real start answer `429` — and it is advisory, never authoritative: the
   start-gate is `POST /api/v1/tasks`, which re-runs every one of those checks under its own
   locks before it registers anything.
   *(`ubb-platform/api/v1/tests/test_the_affordability_question.py`.)*

The delivery fine print, in one place: signals are **at-least-once — late, never lost**; an
unreachable endpoint gets the **current bottom line** on recovery, never a replay of
intermediate flaps; the worst-case crash corner is **one patrol interval plus delivery
retries** (§6); and the ≤5s signal p99 presumes **live counter maintenance ON** — OFF is the
documented durable-lane-latency posture (§8).

Signal latency is not asserted in this document — it is **measured**. The locked launch SLOs
(recorded in [the proof plan](https://github.com/ashcochrane/ubb/issues/15)): recording
p99 ≤ 200ms and stop-signal p99 ≤ 5s, under a 1-hour storm at 500 events/s (~5× the first
tenant's peak) with ceiling and floor crossings mid-storm — plus a hard pass/fail of **zero**
events lost or mis-tagged. The ≤5s number presumes live counter maintenance ON (the default —
see §8). The 200ms number was locked against the async accept route, which slice 1 deleted;
it is carried over unchanged onto the one recording route, not re-derived — #15 owns any
change to the value itself. Executing that proof (load, chaos drills, live Stripe money test — three legs) is
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

**No spend control is a database rule.** All four families are *signal points*: their job is
to trigger an immediate reaction to spending — stop signals, and resume when a top-up
re-crosses the floor — never to block the record of spending that already happened. A
database rule enforcing the floor would do the
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
| Every recorded usage event on a prepaid wallet has its debit, even if outbox delivery died mid-flight | `reconcile_usage_drawdowns` repairs exactly-once (see §7) | `apps/billing/wallets/tasks.py:110` |
| Every succeeded top-up charge is credited, even if our webhook never arrived | `reconcile_topups_with_stripe` repairs from Stripe's ledger (see §7) | `apps/billing/connectors/stripe/tasks.py:118` |
| The fast-lane (Redis) balance tracks the durable one | `reconcile_prepaid` MIN-merges hourly + drift alarm; the upward auto-repair rides the same pass for a debit stranded by a crashed recording request (see §7) | `apps/billing/gating/services/live_counter.py`, `apps/billing/gating/repair.py` |
| A true crossing always eventually produces exactly one signal, and that signal always eventually reaches you | the durable signal ledger (`StopSignalState`, keyed one row per owner per family per **line** since #458 — the pool and the hard floor are two lines of two families and each keeps its own episode sequence) + atomic transition-and-emit through one winning-transition guard (`drive_stop`/`drive_clear`) + the hourly patrol | `apps/billing/gating/models.py`, `apps/billing/gating/services/stop_signal_service.py`, `apps/billing/gating/patrol.py` |
| Every family fires its own signals | application signal suite by design — never a DB rule ([ADR-002](adr/0002-db-constraints-enforce-facts-not-policy.md)) | `apps/billing/gating/services/` for the two billing families; `apps/platform/work/` for the Ceiling and Admission control |

### Pinned by tests in CI

| Behavior | Representative pins |
|---|---|
| A below-floor event still lands, bills, and persists; the stop is a separate signal | `apps/billing/gating/tests/test_live_counter.py::TestStopFlag::test_record_usage_crossing_returns_stop_event_persists_and_replays`, and the whole seam end to end in `apps/billing/gating/tests/test_e2e_seam.py::TestEnforcementSeam`. The explicit ADR-002 pin is `api/v1/tests/test_one_rule_pins.py::Pin3WalletNoFloorCheckTest::test_wallet_carries_no_floor_check` — **which asserts only the constraint half** (no `Wallet` constraint names a balance, and a wallet saved deeply negative round-trips); "lands and bills" is the first citation's, not this one's |
| Concurrent replays of the same debit/credit produce exactly one transaction | `apps/billing/tests/test_concurrency_races.py` (`test_two_concurrent_drawdowns_same_event_one_debit`, `test_two_concurrent_topup_credits_same_pi_one_credit`) |
| Reconcile repair is itself exactly-once | `apps/billing/wallets/tests/test_reconcile_drawdowns.py` (`test_repairs_missing_debit_exactly_once`, `test_does_not_redebit_already_debited_via_column`) |
| Grant conservation survives randomized grant/spend/void/dispute/refund sequences | `apps/billing/wallets/tests/test_grant_invariant_fuzz.py` (`test_random_sequence_holds_invariants`) |
| A ceiling reached → scoped kill signal; the tipping event lands and bills; killed units keep counting | the pin suite (§9): `api/v1/tests/test_one_rule_pins.py`, `api/v1/tests/test_subtask_pins.py`, `api/v1/tests/test_past_limit_pins.py`, `api/v1/tests/test_delivery_pins.py`; `apps/billing/gating/tests/test_stop_resume_pins.py`, `test_soft_floor_pins.py`, `test_mode_pins.py`, `test_patrol_pins.py`, `test_repair_pins.py`, `test_switch_pins.py`; plus `apps/billing/gating/tests/test_p6_fanout.py::TestTaskLimitFanout` (kill fan-out under the 200-always contract) |
| The start-gate refuses a new start while a customer-wide stop flag is set, and admits again once it clears | `apps/billing/gating/tests/test_p6_fanout.py::TestStartGateHonorsStopFlag::test_blocks_new_task_when_flag_set_enforcing` (the verdict's `reason` is `customer_stopped`), `::test_allowed_again_after_flag_cleared`. Since #410 the gate is a **verdict** (`RiskService.check`) rather than a creation call, so what these hold is the refusal, not the absence of a row |
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
| `usage_deduction:{usage_event_id}` | the live drawdown handler, and the reconcile repair — deliberately the **same key**, and literally the same line, so live and repair can race and one wins | `apps/billing/wallets/operations.py:478`, reached from `apps/billing/handlers.py:48` and `wallets/tasks.py:144` |
| `auto_topup:{payment_intent_id}` | the charge task, the `payment_intent.succeeded` webhook, and the Stripe reconcile — three paths, one key, one credit | `apps/billing/topups/services.py:76` |
| `topup:{checkout_session_id}` | Stripe Checkout top-up webhook | `apps/billing/connectors/stripe/webhooks.py:95` |
| `expiry:{grant_id}` | grant expiry | `apps/billing/wallets/grants.py:94` |
| `dispute:{dispute_id}` | dispute deduction | `apps/billing/connectors/stripe/webhooks.py:305` |

There used to be a deliberate asymmetry here: the async path's staging table carried **no**
uniqueness constraint at all, because accepting your events must never wait on a dedup check,
and exactly-once was enforced downstream instead. **That table and the sweep that drained it
were deleted in slice 1**, the last of the async path to go. Nothing is lost by it: the
downstream enforcement was always the real one, and it is untouched — the `UsageEvent` is
written under `uq_usage_event_idempotency_v2` and its debit under
`usage_deduction:{usage_event_id}`. Duplicates still die at the money boundary.

## 6. When our infrastructure fails

The design direction (decision: [#11](https://github.com/ashcochrane/ubb/issues/11)): the
**Postgres ledger is the guaranteed signal lane; Redis is the fast lane**. Signals are durable
at-least-once — a crossing that happens while we're blind signals late, never gets lost.
Catch-up after any blind window is bottom-line only: at most one net stop-or-resume per
customer per signal line, judged against what you were last told (the durable signal
ledger's job); the blow-by-blow history stays in the itemized ledger. Money is never in the
failure equation, because of the one rule: there is no door to fail open or closed.

One structural fact first, because every cell below follows from it: **a single Redis
instance is simultaneously the live-counter store, the Django cache, and the Celery broker**
(`ubb-platform/config/settings.py:107-118`). "Redis down" therefore means crossing detection
goes blind *and* all async work (outbox drain, webhook delivery, wallet drawdown, every
reconcile) pauses — all of it Postgres-durable, all of it drains on recovery. And on the
recording path, **the durable write is Postgres and it commits before anything else
matters**: the `UsageEvent` is written in-request. The wallet drawdown is *never*
synchronous — it rides the outbox to a worker.

| Failure | The recording path (`record_usage`) | What accumulates → how it heals |
|---|---|---|
| **Redis down** | Every enforcement Redis touch fails open with a log warning — the customer-wide checks, the live debit and the stop publish (`apps/billing/gating/services/live_counter.py`). The `UsageEvent` still commits, and the post-commit dispatch (the "doorbell") carries a broker-down guard: the response stays **200**, the durable row is the queue, and delivery resumes within a minute of broker recovery *(delivery pin 12, `api/v1/tests/test_delivery_pins.py`)*. The Ceiling is untouched by this: it is compared against columns on the unit's own Postgres row, so a ceiling still stops work while Redis is away. | Signals are what's lost *in the moment*: no customer-wide crossing detection, no stop flags fire while blind (the durable start-gate on a start still works — it reads Postgres, and Admission control fails OPEN and loudly when its store is away, leaving the money checks that follow to guard the money). Outbox rows pile up Postgres-durable. On recovery the 1-min sweep drains the outbox, hourly reconciles re-merge counters — and the durable lane fires **at most one net stop/resume per customer per line** for anything crossed while blind: the reconcile has SET power and the hourly patrol re-aligns the fast flag to durable truth *(pin 5, `test_stop_resume_pins.py`; delivery pin 1, `test_patrol_pins.py`)*. |
| **Celery workers dead** (broker up) | Clean 200s. Pricing, the durable `UsageEvent`, and the live Redis counter + stop flag are all in-request, so **stop verdicts stay accurate and immediate**. What stalls: the wallet drawdown, durable suspend, and webhook delivery — all worker-side. | Pending outbox rows and broker queues accumulate. Note the drift direction: durable wallets read stale-*high* while the live counter is already debited — the fast lane errs toward stopping you early, never toward hiding spend. Workers return → backlogs drain, reconciles run; the 6h drawdown grace is sized above the outbox retry horizon so repair never races live delivery. |
| **Postgres down** | Immediate 5xx, **before any money state changes**: the first statement is a Postgres read, and the Redis debit sits after the durable write, so it is never reached. Nothing acked, nothing mutated. | Redis live counters and stop flags freeze untouched (they can't be reconciled without Postgres, and can't drift without new events). Recovery: reconciles re-merge; nothing to repair because nothing was recorded. |

The direction of every degradation is the same, and it is the decided one
([#11](https://github.com/ashcochrane/ubb/issues/11)): **failure degrades toward
accepting-and-recording with late signals — never toward losing events, refusing usage
reports, or double-billing.** The one drift that runs the other way (a live-counter debit
whose recording transaction then rolled back, over-restricting the fast lane) errs
pessimistic and is repaired by the upward auto-repair (§7). The fine print on "late": the
worst crash corner — a signal's triggering
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
| `reconcile_usage_drawdowns` | hourly at :40 | any recorded usage event on a prepaid wallet whose debit never landed (e.g. outbox dead-lettered) — repairs the debit | anti-join on `WalletTransaction.usage_event_id` + key `usage_deduction:{id}`; **6h grace, deliberately > the ~2h43m outbox retry horizon** so live delivery always gets to finish first; 7-day lookback; repair-rate spike alarm (`apps/billing/wallets/tasks.py:110-158`) |
| `reconcile_topups_with_stripe` | hourly at :20 | any *succeeded* Stripe PaymentIntent with no local wallet credit — credits it from Stripe's ledger (Stripe is the source of truth for money movement); secondary amount/refund audit | key `auto_topup:{pi_id}`; **4-day lookback, > Stripe's ~3-day webhook retry horizon**; 48h audit window (`apps/billing/connectors/stripe/tasks.py:118-208`) |
| `reconcile_wallet_balances` | hourly at :00 | **auditor, not repairer**: checks `balance == Σ ledger` and grant conservation on every wallet; any drift logs loud | detect-and-alarm by design — an automated "fix" would hide the bug that caused the drift (`apps/billing/wallets/tasks.py:11-96`) |
| `reconcile_live_ledgers` → `reconcile_prepaid` | hourly at :25 | MIN-merges the fast-lane (Redis) prepaid balance toward the durable wallet balance; alarms on drift spikes; both **clears** stale stop flags for recovered customers and **sets** missed ones — the crossed-while-blind-then-went-quiet hole is closed (decision: [#11](https://github.com/ashcochrane/ubb/issues/11)) | conservative merge direction — the fast lane may only be *more* cautious than durable truth, never less (`apps/billing/gating/services/live_counter.py`); *(pin 5, `test_stop_resume_pins.py`)* |
| the hourly patrol | rides the :25 pass | the signal suite's backstop, traffic-independent: drives missed stop/soft-floor transitions (both directions), re-aligns the fast `ubb:stop` flag to durable truth, **re-mints a fresh current-state announcement** for any signal that never reached you, sweeps any work still active at or above its COGS Ceiling and kills it idempotently — that last leg running for **every** tenant, because declaring a ceiling is the opt-in and the switch does not govern it | `apps/billing/gating/patrol.py:51`; announcement bookkeeping via `announce_outbox_id` stamps, re-mints marked `re_announcement: true` and NAMED FOR THE STATE THE ROW CARRIES NOW — a piece of work that expired re-announces the expiry and never the spend stop, the patrol having no memory of which event it first sent (`test_patrol_pins.py::TestTheRemintNamesTheStateTheRowCarries`, #420) — at most one in-flight announcement per signal row; `PatrolOutcome` counters surface as `patrol_*_7d` through `apps.billing.queries.get_patrol_stats` *(delivery pins 1–6, `test_patrol_pins.py`)* |
| live-balance upward repair | rides the :25 pass | a crashed **synchronous** recording request leaves the live counter wedged low — the debit is issued after the event row's savepoint but inside the still-open recording transaction, so a failure before the commit rolls the row back and leaves the debit standing (Ruling A2, [#233](https://github.com/ashcochrane/ubb/issues/233), pinned by `api/v1/tests/test_recording_drift_pins.py`). The stingy direction, false stops. Expected = the durable balance; a deficit must persist across **two consecutive hourly passes** and repairs by **min(first, second)** as a relative increment, never an absolute set; every repair audited (`LiveBalanceRepair`), repair-rate spike alerts, and a repair that lifts a wedged stop fires `customer.stop_cleared` through the same guard as every other clearing | `apps/billing/gating/repair.py`, `apps/billing/gating/models.py:130`; principle, verbatim ([#12](https://github.com/ashcochrane/ubb/issues/12)): "we CANNOT have a wallet balance that does not show reality" *(delivery pins 7–8/10–11, `test_repair_pins.py`)* |
| `expire_credit_grants` | hourly at :10 | expires past-due credit grants | key `expiry:{grant_id}`; clamped so expiry never takes back spent credit (`apps/billing/wallets/tasks.py:178-256`) |

Every `CELERY_BEAT_SCHEDULE` entry above is checked against real, importable code by
`apps/platform/tests/test_beat_schedule.py` — a schedule naming a task that no longer resolves is a
red build, not a job that silently stops running. (The patrol and the upward repair are not beat
entries of their own — both ride the :25 pass.)

**Two jobs left this table in slice 1**, with the two-step intake path they served: the sweep that
drained the staging table, and the health monitor that watched the queue behind it. Exactly-once
never depended on either — `uq_usage_event_idempotency_v2` and the `usage_deduction:{id}` key are
where it is enforced, and both are untouched. The monitor also carried a known weakness, retired
with it: it was itself a Celery task, in-band with the failure it reported. If a health probe of
that kind is ever wanted again, [#11](https://github.com/ashcochrane/ubb/issues/11)'s decided shape
— pull-based, a Redis probe watched by an outside poller — is the one to build.

Two properties worth stating explicitly, because they're where reconcile designs usually go
wrong:

- **Repairs never re-fire side effects.** A back-corrected debit does not re-trigger suspend
  or overage events; signal state transitions fire only on true state changes — every
  emission, from either lane or any repair, routes through one winning-transition guard per
  owner per signal line, so a crossing observed twice still signals once — and a customer
  stopped by their pool and by their wallet floor at once has two episodes, one per line,
  with the stop flag lifting only when both have cleared.
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
documents arrival-time cost estimation or balance reservations — and neither does UBB any
longer: it had both, and slice 1 deleted them, because since the MVP dropped tiered pricing
(ADR-0003) the price is **exact** rather than estimated — per-unit and flat pricing compute
one number, once, when the event is recorded — so there is nothing to estimate and nothing
to reserve against. What survives them, and is (as far as vendor docs show) unique, is the
record-time crossing detection itself. It is also an honest per-tenant choice
(`Tenant.live_counter_maintenance_enabled`, read only through
`flags.live_counter_maintenance_on` — *delivery pin 9, `test_switch_pins.py`*): live counter
maintenance **ON** (the default) buys stop-signal latency that is independent of how deep the
drawdown queue is; **OFF** is the documented competitor-normal posture — detection at
durable-lane latency, where the alarm slows down exactly when a runaway spender floods the
queue. Same contract, same events, two latency profiles. The industry default is not a truer
balance; it is slower signals against a staler one.

## 9. The pin ledger — every promise's named test

The two implementation specs each shipped with a numbered definition of done. The program
close-out ([#47](https://github.com/ashcochrane/ubb/issues/47), 2026-07-17) verified all 29
green on a fully green suite; **28 are live tests on `main` today and pin 15 was retired by
deletion**, at its own row below. This table is the acceptance gate made auditable: run any
row yourself.

**Every path is written in full, from the git root**, so a citation can be pasted into
`pytest` without reconstructing a prefix — the abbreviation this table used to carry is what
let three citations go stale unnoticed while the suites stayed green. They are checked:
`tests/contracts/test_the_pin_ledger_names_tests_that_exist.py` walks this section and
reddens on a path that does not resolve or a case no cited module defines.

**Where a pin's test asserts less than its promise, the row says so** and names what holds
the rest. A row that claimed more than its test would be the same defect as a stale path,
one level down.

**One-rule enforcement spec** ([PR #27](https://github.com/ashcochrane/ubb/pull/27),
`docs/plans/2026-07-15-one-rule-enforcement-spec.md` §L).

| Pin | Holds | Named test |
|---|---|---|
| 1 | The tipping event lands and bills — whole and contained work, on the one recording path, with nothing deferred to a later sweep (#192). **The boundary is this pin's own arithmetic**: the case drives a known provider total landing *exactly on* the ceiling and asserts the kill, because at or above the line stops (#452). Its neighbour drives one micro under and asserts `within_ceiling`, no stop, and a patrol sweep that finds nothing | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin1SyncTippingEventTest::test_tipping_event_lands_bills_and_kills`, `::test_one_micro_under_the_ceiling_is_not_a_crossing`, `Pin1NothingDeferredTest::test_task_limit_bites_at_record_time_with_nothing_deferred`; `ubb-platform/api/v1/tests/test_subtask_pins.py::Pin1SubtaskTippingEventTest::test_subtask_tipping_event_lands_bills_and_kills_alone`. The same arithmetic at the service seam, inverted at its own address by #452: `ubb-platform/apps/platform/work/tests/test_services.py::TaskServiceAccumulateTest::test_accumulate_cost_exactly_on_the_ceiling_is_a_crossing`, `::test_accumulate_cost_one_under_the_ceiling_is_not_a_crossing` |
| 2 | Events on a killed unit land, bill, count into both totals, carry stop context | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin2KilledTaskStillCountsTest::test_events_on_killed_task_land_bill_and_count`; `ubb-platform/api/v1/tests/test_past_limit_pins.py::Pin2StopContextOnKilledTaskTest::test_tipping_and_late_events_carry_schema_contexts`, `::test_the_stored_row_carries_the_context_not_just_the_ack`, `::test_replay_returns_the_original_context` |
| 3 | `Wallet` carries no floor CHECK (ADR-002) — **and that is all this pin asserts.** It checks that no wallet constraint names a balance and that a deeply negative wallet round-trips; the "a below-floor event still lands and bills" half is the first citation beside it, not this one | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin3WalletNoFloorCheckTest::test_wallet_carries_no_floor_check`; the landing half is `ubb-platform/apps/billing/gating/tests/test_live_counter.py::TestStopFlag::test_record_usage_crossing_returns_stop_event_persists_and_replays` |
| 4 | Durable lane fires at the **configured** floor with Redis down; exactly one stop per crossing | `ubb-platform/apps/billing/gating/tests/test_stop_resume_pins.py::TestPin4DurableLane::test_durable_lane_fires_at_configured_floor_with_redis_down`, `::test_durable_lane_watches_the_configured_floor_not_zero`, `::test_fast_and_durable_lanes_fire_exactly_one_stop_and_one_suspend` |
| 5 | `reconcile_prepaid` SETs a missed stop, not just clears a stale one | `ubb-platform/apps/billing/gating/tests/test_stop_resume_pins.py::TestPin5ReconcileSetsAMissedStop::test_reconcile_sets_a_missed_stop`, `::test_reconcile_sets_the_missed_stop_even_with_redis_down`, `::test_reconcile_is_idempotent_per_position` |
| 6 | Resume fires at the exact re-cross — once per episode, via credit, reconcile, and durable paths | `ubb-platform/apps/billing/gating/tests/test_stop_resume_pins.py::TestPin6ResumeOncePerEpisode::test_credit_path_clears_at_the_exact_recross_once`, `::test_reconcile_path_clears_once`, `::test_durable_path_clears_when_redis_is_blind`, `::test_episodes_pair_up_across_a_full_cycle` |
| 7 | Every recorded event answers 200 for a usage report. **This pin asserts the 200 and never drives a 409 path**, so "no 429/409" is held as "every one of these answers 200". The obligation's other half — **a close is never subject to the rate bound** — is admission control's, built in #462, and is asserted for a tenant with a wallet regime and for one that does not bill through UBB | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin7TwoHundredAlwaysTest::test_no_usage_report_path_answers_429_or_409`; `ubb-platform/api/v1/tests/test_admission_control_runs_for_every_start.py::ATenantWithAWalletRegimeTest::test_a_close_is_never_subject_to_it`, `ATenantThatDoesNotBillThroughUbbTest::test_a_close_is_never_subject_to_it`, `::test_a_usage_report_is_always_accepted` |
| 8 | `advisory` migrated to `off`; two-position mode; `off` leaves no customer-wide enforcement trace. **The scope is the customer-wide families**: what the cases drive is a wallet-floor crossing, and a declared Ceiling is outside the switch by design (§2) | `ubb-platform/apps/billing/gating/tests/test_mode_pins.py::TestAdvisoryRetired::test_migration_maps_advisory_to_off`, `::test_migration_leaves_both_live_positions_alone`, `::test_choices_are_two_position`, `::test_patch_advisory_refused_422`; `TestOffIsByteForBytePreEnforcement::test_floor_crossing_leaves_no_enforcement_trace`, `::test_tier1_baseline_survives_untouched` |
| 9 | Stops and breaches reconstructs an episode end-to-end, per family | `ubb-platform/api/v1/tests/test_spend_control_reports.py::ACeilingEpisodeTest::test_a_ceiling_row_is_explained_by_its_unit_and_the_events_after_the_stop`, `AWalletPolicyEpisodeTest::test_a_hard_floor_row_itemises_its_events_and_a_soft_floor_row_is_a_marker`; `ubb-platform/api/v1/tests/test_past_limit_pins.py::Pin9StopsAndBreachesTest::test_a_historical_customer_scope_tag_still_lands_in_itemization`, `::test_suspended_tag_stays_excluded_from_itemization` (the two cases the successor's own module does not drive) |
| 10 | `negative_since` set on ≥0→<0, cleared on recovery; the aged-negatives count beside it. **The ops surface moved**: it is the `get_negative_balance_stats` read contract, the route that used to serve it having gone with the ingest pipeline it watched | `ubb-platform/api/v1/tests/test_past_limit_pins.py::Pin10NegativeSinceTest::test_negative_since_set_on_crossing_cleared_on_recovery` |
| 11 | Zero-crossing `wallet.balance_overage` early warning unaffected | `ubb-platform/apps/billing/gating/tests/test_stop_resume_pins.py::TestPin11EarlyWarningUnaffected::test_zero_crossing_fires_overage_without_a_stop`, `::test_enforcement_off_is_tier1_byte_for_byte` |
| 12 | Soft floor refuses new top-level starts only; contained work passes under a running parent; crossed/cleared exactly once; acks never change. **Since #410 the gate is a verdict rather than a creation call**, so what is asserted is the refusal word `soft_floor_reached`, not the absence of a row | `ubb-platform/apps/billing/gating/tests/test_soft_floor_pins.py::TestPin12StartGate::test_crossing_refuses_a_new_top_level_task_start`, `::test_subtask_start_under_an_active_parent_passes`, `::test_hard_floor_wins_below_both_lines`, `::test_enforcement_off_never_refuses`, `::test_postpaid_has_no_soft_floor`; `TestPin12PairExactlyOnce::test_durable_crossing_emits_soft_floor_crossed_once`, `::test_acks_never_change_on_a_soft_crossing`, `::test_credit_clears_at_the_exact_recross_once`, `::test_hard_and_soft_families_fire_independently_on_one_event` |
| 13 | Contained work killed alone — parent keeps running; a parent's own crossing cascades | `ubb-platform/api/v1/tests/test_subtask_pins.py::Pin13ContainmentTest::test_subtask_killed_alone_parent_keeps_running_and_counting`, `::test_parent_trip_kills_parent_and_cascades_to_active_subtasks`, `::test_both_limits_tripping_on_one_event_announce_both` |
| 14 | Only the provider (COGS) total races a Ceiling; both totals on the record and the response | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin14DenominationTest::test_only_the_provider_total_races_the_limit`; `ubb-platform/api/v1/tests/test_subtask_pins.py::Pin14SubtaskDenominationTest::test_only_the_provider_total_races_a_subtask_limit` |
| 15 | **Retired by #321 — this is no longer guaranteed, and by deletion rather than rehoming.** A start with a resolvable ceiling used to be refused `cost_coverage_required` unless the tenant had promised full cost coverage. #320 removed the premise: an event UBB cannot cost is now recorded with its cost unresolved rather than counted as zero, so a ceiling races a floor, and the gate was refusing work on a promise nothing keeps. Such a start is now admitted whatever a tenant has declared. | — the ceiling-resolution half survives as `ubb-platform/api/v1/tests/test_one_rule_pins.py::CeilingResolutionAtStartTest::test_a_lower_request_wins_over_the_tenant_default`, `::test_a_request_above_the_tenant_default_is_refused`, `::test_a_declared_kind_ignores_the_tenant_default_entirely`, `::test_a_start_with_no_ceiling_anywhere_pins_none` |
| 16 | Label fallback removed — a `metadata` label never attaches a Ceiling | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin16LabelFallbackRemovedTest::test_a_task_label_gets_no_attribution_no_limit_no_kill` |
| 17 | The clean cut holds: no run-era name on any surface. One case was **inverted at its own address by #453** — it now asserts the two default ceiling rungs are *off* billing's risk row and *on* the tenant, which is the opposite direction from the one it was written in | `ubb-platform/api/v1/tests/test_one_rule_pins.py::Pin17CleanCutSweepTest::test_no_run_era_event_type_in_catalog`, `::test_retired_config_fields_are_gone`, `::test_neither_retired_redis_key_family_is_ever_written`, `::test_no_surface_answers_to_a_run_era_name`, `::test_task_routes_replaced_run_routes` |

**Guaranteed-delivery + auto-repair spec**
([PR #32](https://github.com/ashcochrane/ubb/pull/32),
`docs/plans/2026-07-15-guaranteed-delivery-autorepair-spec.md`):

| Pin | Holds | Named test |
|---|---|---|
| 1 | Ambient-rollback corner: orphaned flag re-aligned, signal fired by the next patrol pass | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin1AmbientRollback::test_orphan_flag_against_recovered_durable_truth_is_realigned`, `::test_durably_crossed_position_signals_on_the_next_pass`, `::test_missing_flag_for_a_durably_stopped_owner_is_realigned` |
| 2 | Emit-failure corner: savepoint rolls the transition back with the failed insert; the event still lands; the patrol fires within one interval | `ubb-platform/apps/billing/gating/tests/test_live_counter.py::TestStopFlag::test_pin2_failed_event_insert_rolls_the_transition_back`; `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin2EmitFailureCompletes::test_patrol_fires_the_signal_within_one_interval` |
| 3 | A dead-lettered `customer.stopped` is re-minted as a fresh current-state announcement, same episode, carrying the family and the control read off the row | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin3RemintUnannounced::test_dead_lettered_stop_fired_is_reminted_with_the_same_episode`, `::test_a_signal_remint_reads_the_family_and_the_control_off_the_row`, `::test_no_mint_while_an_announcement_is_in_flight`, `::test_announced_by_skipped_never_remints` |
| 4 | Stop + clear during a blind window → recovery delivers the current bottom line only | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin4BottomLineOnly::test_recovery_delivers_the_current_bottom_line_only` |
| 5 | The soft pair rides the same rails; lines stay independent | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin5SoftFamilyRidesTheSameRails::test_dead_lettered_soft_crossed_remints`, `::test_families_remint_independently` |
| 6 | A crashed kill is swept and announced within one interval; contained work alone. The sweep's case drives a unit sitting **exactly on** its ceiling, the same at-or-above rule as one-rule pin 1. The listener case asserts that the patrol's kill notifies the kernel's terminal-transition registry **exactly once, with the transition and its cause** — it installs its own listener in place of the real ones, so what it holds is the notification, not what any listener then does; that a prepaid reservation is actually released on this path is the last citation's | `ubb-platform/apps/billing/gating/tests/test_patrol_pins.py::TestPin6TaskSweep::test_crashed_kill_is_swept_and_announced_within_one_interval`, `::test_subtask_is_swept_alone_parent_unaffected`, `::test_the_patrols_kill_reaches_the_kernels_terminal_listeners`, `::test_a_remint_carries_the_control_the_stopping_lane_recorded`, `::test_under_limit_and_unlimited_tasks_are_left_alone`; `ubb-platform/api/v1/tests/test_every_terminal_path_releases_the_reservation.py::UbbsOwnStopsReleaseTest::test_the_patrols_kill` |
| 7 | Two-pass repair of a strand left by the recording path: candidate on pass one, `min(d1,d2)` relative increment + full audit on pass two; a lifting repair fires `customer.stop_cleared` once | `ubb-platform/apps/billing/gating/tests/test_repair_pins.py::TestPin7TwoPassRepair::test_pass_one_candidates_pass_two_repairs_with_full_audit`, `::test_min_takes_the_second_measurement_when_the_deficit_shrank`, `::test_min_takes_the_first_measurement_when_the_deficit_grew`, `::test_repair_that_lifts_a_wedged_stop_fires_stop_cleared_exactly_once` |
| 8 | A transient deficit lapses; sub-de-minimis never candidates; a stale candidate lapses and the observation starts over | `ubb-platform/apps/billing/gating/tests/test_repair_pins.py::TestPin8TransientAndDeMinimis::test_transient_deficit_lapses_without_repair`, `::test_sub_de_minimis_deficit_never_candidates`, `::test_stale_candidate_lapses_and_the_observation_starts_over` |
| 9 | Switch OFF: no Redis writes on the recording path, identical ack schema, verdicts from the durable flag, a floor crossing signals at durable-lane latency, OFF→ON re-seeds, flag read only through `flags.py`, default ON | `ubb-platform/apps/billing/gating/tests/test_switch_pins.py::TestDefaultAndAccessor`, `TestPin9RecordingWritesNoRedisKeys`, `TestPin9AckContractIdentical`, `TestPin9CrossingSignalsAtDurableLaneLatency`, `TestPin9ToggleChoreography`, and the AST doctrine scan `TestFlagReadOnlyThroughFlagsModule::test_no_attribute_access_outside_the_allowlist` |
| 10 | MIN-merge downward behavior byte-identical; a drift-*high* counter is never a deficit; the measurement is the durable balance alone — **now held as module doctrine rather than arithmetic**: the case is an AST scan asserting the repair module imports nothing from metering, and its neighbour holds that an open reservation is recorded beside the measurement and never subtracted from it | `ubb-platform/apps/billing/gating/tests/test_repair_pins.py::TestPin10DownwardNeighborsUntouched::test_the_measurement_is_the_durable_balance_alone`, `::test_an_open_reservation_is_recorded_beside_the_measurement_and_never_subtracted`, `::test_drift_high_counter_is_the_min_merges_lane_never_a_candidate`, `::test_absent_counter_is_never_repaired` |
| 11 | The repair-rate spike alert fires past its threshold, on the count and on the amount | `ubb-platform/apps/billing/gating/tests/test_repair_pins.py::TestPin11RepairSpikeAlert::test_spike_past_the_count_threshold_alerts_critical`, `::test_spike_past_the_amount_threshold_alerts_critical`, `::test_below_threshold_stays_quiet` |
| 12 | Broker down at accept: durable row written, response 200, the sweep re-dispatches it. **No timing is asserted** — "within a minute" is the one-minute beat in `CELERY_BEAT_SCHEDULE`, not something this case measures | `ubb-platform/api/v1/tests/test_delivery_pins.py::BrokerDownAtAcceptTest::test_sync_record_with_broker_down_is_200_and_sweep_delivers` |

**What still stands between here and launch** — outside this document's guarantees, stated
so nothing is blurred: **the proof stage**, deferred to the testing phase — three legs: load
(the §2 SLOs: recording p99 ≤ 200ms, signal p99 ≤ 5s, zero lost/mis-tagged events under a
1h/500eps storm), chaos drills (the §6 failure modes, observed live), and the operator-run
real-money Stripe test — plus the balance ≡ Σ ledger hard assertion. The soak leg was
dropped with advisory mode. [The proof plan](https://github.com/ashcochrane/ubb/issues/15)
records the locked numbers and the descope.

---

*Supersedes the "honest guarantee (and its bound)" section of the
[integration guide](spend-control-integration.md) — the bound formula is retired
([#10](https://github.com/ashcochrane/ubb/issues/10)). The guide now speaks the shipped
contract: the task/subtask vocabulary and the 200-always wire contract.*
