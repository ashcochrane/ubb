# Fixed price on task completion — the economic specification

**Resolves:** [#139](https://github.com/ashcochrane/ubb/issues/139) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-30
**Decided against:** `main` @ `27efac5`
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — Event Type owns
costability, not cost; customer pricing lives in the versioned, customer-assignable policy book; a
fixed sell rate is an explicit override
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138: #154 is the single naming pass that fixes every
term once, and an ADR written before it would be rewritten by it. The ADR is owed *after* #154 and
should cite both this document and #138's.

---

## The decision in one paragraph

**A fixed price replaces metered revenue for one delivered job, and it is earned only by delivery.**
It is resolved from a work-level line in the customer's assigned policy book and **pinned when the job
starts**, so every event inside the job records real cost and zero revenue from the first one and
nothing is ever reversed. A customer's bill for a fixed-price job is provably always exactly the price
or nothing — no third value is reachable. The **canonical record is a first-class immutable Charge**,
projected 1:1 onto a single marked usage posting so that wallet drawdown, postpaid accrual, the Stripe
line push, budgets, the live counter and dimensional margin all keep working unchanged, without
pretending a charge was operational usage. For prepaid customers the price is **reserved against the
job at start** and tested against the tenant's own floors, so cost is never burned on work that could
not have been paid for. Non-delivery never charges; the tenant's downside is bounded by a COGS ceiling
they choose.

---

## 1. The amount has three locks, not one

The ticket asked "at what point is the amount locked". The trace shows three distinct locks with
different meanings, and conflating them is what makes this feature look ambiguous.

| Lock | When | What it fixes | Evidence |
|---|---|---|---|
| **Determination** | job start | *which* price applies | decided here; follows the existing snapshot pattern — `balance_snapshot_micros` and `provider_cost_limit_micros` are copied in at creation "so a config change never affects an in-flight task" (`apps/platform/tasks/models.py:118-128`), and `billing_owner_id` is pinned there and explicitly never re-resolved (`:130-135`) |
| **Payability** | delivery | *whether* it is owed at all | `complete_task` returns `transitioned`, true only for the winning transition (`apps/platform/tasks/services.py:265-284`) |
| **Immutability** | invoice claim | whether it can still change *in place* | freeze-at-first-claim: `line_snapshot` pins the lines at Phase 1 and every retry reuses them so a resumed invoice cannot overbill (`apps/billing/invoicing/services/postpaid_service.py:137-164`) |

After the third lock, no new event may enter the period at all: `is_usage_period_closed` treats a
non-empty `line_snapshot` as frozen — the load-bearing clause, because lines freeze *before* any Stripe
call (`apps/billing/queries.py:218-243`), and `validate_effective_at` rejects with
`billing_period_closed` (`apps/metering/usage/services/usage_service.py:78-84`).

---

## 2. What a fixed price means

### 2.1 It replaces metered revenue — it is not a fee on top, and not a floor

Events inside a fixed-price job are **cost-only**: real provider cost, zero billed revenue. The fixed
price is the sole revenue line.

Rejected alternatives, recorded so they are not re-litigated:

- **A per-job fee plus metered usage** is a different product (a setup or platform fee). It may be
  worth building; it must not be conflated with a fixed price.
- **"Charge the higher of metered or fixed"** already has a home: #138 reserved **minimum charge** as
  its own policy-line content.
- **Three tenant-selectable modes** was rejected for v1 — three charging paths means three sets of
  kill/fail/retry edge cases to build, test, document and support.

### 2.2 The cost side is entirely unchanged

The fixed price touches the **revenue** side only. Every event still records its own
`provider_cost_micros`; `accumulate_cost` still adds it into `Task.total_provider_cost_micros` and
rolls it up into the parent for a subtask (`tasks/services.py:114-126`). The spend ceiling still races
the provider total and only the provider total — "Only the provider (COGS) total races a limit"
(`tasks/services.py:77-78`).

So task-level margin is an exact subtraction: **pinned price − task provider total**.

### 2.3 Determined and pinned at job start

The price is resolved when the job starts and pinned to it. Events are revenue-zero from the first
one; nothing is ever reversed.

Two reasons this is not merely a preference:

- **Usage events are hard-immutable.** `UsageEvent.save()` raises on any update and `delete()` raises
  outright (`apps/metering/usage/models.py:104-109`). "Re-price it later" is not editing a row, it is
  writing compensating entries.
- **Reversals are visible to the customer.** Pricing events at metered rates mid-job really draws down
  a prepaid wallet and really credits it back.

**Accepted consequence:** a fixed price cannot be chosen at close. It must come from configuration
resolvable at start — the declared kind of work plus that customer's policy.

**Versioning falls out of this.** A job started before a price change is charged the old price. The
Charge records the book version, the matched line and the resolution time, so the amount is
reproducible from the record rather than by re-resolving today's config.

### 2.4 The price comes from a work-level line in the customer's policy book

The declared kind of work (`TaskType`, `apps/platform/tasks/models.py:20-51`) declares only **that**
it is priced as a whole. It never holds the amount — the same rule #138 established for Event Type,
and re-opening it for work would undo what that decision bought.

The amount is a **work-level line in the customer's assigned policy book**, which brings per-customer
pricing, set-level versioning and customer assignment for free.

**The work ladder is one step, not three.** #138's price ladder (Event Type → Event Category →
book-wide default) is about events. A fixed price keys on the kind of *work* — a different axis — so
the book grows a second kind of line, and the two ladders do not compete: **a matched work-level line
switches the whole event-level ladder off for that job.** There is no fallback tier, because "a
default fixed price for all work regardless of kind" is meaningless.

### 2.5 Markup never applies — the price is terminal

`MarkupService.apply` computes `billed = provider_cost + markup(provider_cost)`. It is a **function of
provider cost only** (`apps/metering/pricing/services/markup_service.py:28-34, 66-72`). Applying it to
a fixed price yields "£5 plus a percentage of this job's COGS", which makes the fixed price move with
cost and destroys the premise.

All four rungs are bypassed for fixed-price work — customer override, the customer's **plan**, the
tenant default, none (`markup_service.py:47-64`). This is the same direction #138 fixed: a fixed sell
rate is an explicit override of markup, never a layer under it.

**Deliberate coexistence:** a customer on a plan with markup runs two regimes at once — their loose
metered events get plan markup, their fixed-price jobs get the flat price and ignore the plan.

Also rejected: **the plan scaling the price itself** (Enterprise pays 0.8×). Coherent but redundant —
books are already per-customer, so a different price is just a different assigned book, and two ways
to express one thing means two places to look when a price is wrong.

---

## 3. What earns the charge

### 3.1 Only an explicit close declaring delivery

**The charge keys on *how* the job ended, never on the status field alone.** This is not a nicety —
`status == "completed"` is reachable without anyone asserting anything.

There are six ways a job reaches a terminal state today:

| How it ends | Ends as | Decided by | Charges? |
|---|---|---|---|
| `close_task` declaring delivery | `completed` | tenant's code | **yes** |
| `close_task` declaring failure | terminal | tenant's code | no |
| `close_abandoned_tasks` beat | `completed` + `auto_closed` | UBB, 1–6h | no |
| limit kill (`task_limit`) | `killed` | UBB | no |
| parent kill cascade (`parent_killed`) | `killed` | UBB | no |
| `reap_stale_tasks` (`stale`, `stale_max_age`) | `killed` | UBB, enforcing only | no |

The third row is why status alone cannot be the trigger. `close_abandoned_tasks` marks jobs
`completed` an hour after they go quiet, and its own docstring names the reason: "client crash, network
failure, forgotten close call" (`apps/platform/tasks/tasks.py:18-63`, stamping
`metadata["auto_closed"]` at `:57`). If status were the trigger, **a crashed client would bill the
customer an hour later.**

Worse, which sweeper wins depends on an unrelated flag. Enforcing tenants cede emitted-but-stale jobs
to the reaper, so they end `killed` (`tasks/tasks.py:43`); everyone else — and enforcement is off by
default — ends `completed`. The identical failure would charge or not charge based on a spend-control
setting.

Also rejected: **"calling close means delivered", with failure expressed by not calling close.** That
forces a tenant to deliberately abandon jobs to avoid charging, which holds their concurrency slot for
an hour and, for enforcing tenants, converts the abandonment into a reap kill that fires a spurious
`task.limit_exceeded`.

### 3.2 Non-delivery never charges; exposure is bounded by a ceiling the tenant chose

No delivery, no charge. One rule, no partial charges, no metered fallback.

The exposure this creates is **created by the replace decision** and is unique to fixed pricing: under
metered pricing one-rule means every event that reaches UBB is priced, recorded and billed even after a
kill, so a metered customer has already paid COGS+margin on everything the job burned. Zeroing event
revenue is what opens the hole.

The answer is not a recovery rule but a better ceiling. Today a COGS ceiling is an absolute number per
kind of work. With a price pinned at start there is an obviously correct ceiling available: **the price
itself, or a tenant-set fraction of it.** At 60%, a job is killed the moment it eats more than 60% of
its own revenue, and the tenant's worst case per job becomes a number they chose, expressed in the only
terms that matter for fixed-price work. Map constraint 4 explicitly opens the limit machinery for this.

**Recommended default for fixed-price work: ceiling = a tenant-set fraction of the pinned price.**

Rejected: **metered fallback on non-delivery** (either always, or only when the tenant's code declares
failure). Two reasons. It makes the customer's bill for a failed job unpredictable — the exact thing
fixed pricing sells against. And applied to a limit kill it inverts absurdly: a job stopped for burning
too much would bill the customer *more* than the price it was sold at, and a job lost to the tenant's
own crashed workers would bill them at all.

### 3.3 Whole jobs only

A fixed price attaches to top-level jobs. A fixed-price line on a subtask type is **refused at start,
loudly** — not silently ignored.

Three facts point the same way:

- **Parent completion cascades silently.** `complete_task` auto-completes active subtasks in the same
  transaction (`tasks/services.py:282-283`, `_cascade` at `:188-206`) with no outcome declared per
  child. A priced subtask would fire a fan of charges nobody asserted — exactly the auto-charge failure
  rejected in §3.1.
- **The parent is already the whole-job altitude.** Rollup is unconditional so "the parent sees
  everything underneath it" (`tasks/services.py:60-68`).
- **Subtasks are already modelled as steps, not jobs.** `list_tasks` omits them because "a listing
  counts JOBS, not steps" (`api/v1/metering_endpoints.py:300-303`).

Refusal belongs in the start gate beside the existing work-type policy refusals
(`RiskService.resolve_type_policy`, which already raises on an undeclared or retired type, a missing
required dimension, or a request above the type's ceiling).

Rejected: **allowed on both, parent wins.** The tenant would have configured something that silently
does nothing, and removing the parent's price later would spring the step price to life — a pricing
change nobody made.

---

## 4. How the money moves

### 4.1 Prepaid: the price is reserved against the job at start

The start gate already refuses work for money reasons — it reads the wallet balance and refuses on the
hard floor, the soft floor and the budget cap (`apps/billing/gating/services/risk_service.py`, the
floor/budget block before task creation). But every one of those is a **floor** test, never "can this
customer afford this specific amount". A customer with £2 and a £0 floor passes today and starts a £5
job.

**Decision: at start, record a durable reservation for the pinned price against the task.** Available
money is `balance − open reservations`, tested against **the tenant's own configured hard/soft floors**
rather than a new threshold. Short → the job never starts, so no COGS is burned on work that could not
have been paid for.

**Prepaid only, by decision.** Postpaid customers have no wallet; the budget cap remains their only
brake.

**A durable reservation row keyed on the task, not a Redis hold with a TTL.** The ingest holds carry a
documented orphan-drift problem healed only by a 62-day TTL and an hourly reconcile
(`usage_service.py:715-746`), because they are pinned to raw events that can vanish. A fixed-price
reservation is pinned to a **task**, and tasks are guaranteed to terminate: `close_abandoned_tasks`
enforces a hard 6-hour age ceiling regardless of heartbeat (`tasks/tasks.py:30`) and `reap_stale_tasks`
applies the same cutoff for enforcing tenants (`:97`). So every terminal transition is a deterministic
release point, the maximum reservation lifetime is ~6 hours, and a sweep over terminal tasks holding
open reservations is a trivial backstop.

Released on **every** terminal path: delivered (settle), failed, limit kill, parent cascade, reap,
auto-close.

Rejected: **a plain floor check.** Three £5 jobs starting at once against a £5 wallet all read £5
available and all pass; because charges are never walls in this system, all three closes still charge
and the wallet lands at −£10 with COGS burned on all three.

### 4.2 The canonical record is a first-class immutable Charge

**Every existing correction mechanism is keyed on a UsageEvent id:**

- **Refund identity** — `Refund` is a `OneToOneField(UsageEvent)` (`usage/models.py:140-153`): exactly
  one refund per event, ever. Written by the `refund.requested` handler, idempotent by swallowing the
  OneToOne IntegrityError (`apps/metering/handlers.py:10-60`, `:52-54`).
- **The amount lookup that prevents a wrong booking** — `refund_usage` refuses to accept an amount and
  looks the cost up via `get_usage_event_cost(usage_event_id)` "so no caller can book a wrong one"
  (`apps/billing/wallets/operations.py:300-315`).
- **Wallet-ledger identity** — `WalletTransaction.usage_event_id` pins the original deduction
  (`apps/billing/wallets/models.py:80`), which is how `GrantLedger.refund` restores grant-lot slices
  (`operations.py:317-325`).
- **The exactly-once money key** — `usage_deduction:{usage_event_id}`, whose replay guard compares the
  amount and logs `ledger.usage_deduction_amount_mismatch` on disagreement
  (`operations.py:478-488`).

A charge that never touches the usage rail therefore has, today, **no refund path, no reversal, no
lot-aware credit and no exactly-once money key.**

**The task's snapshotted price cannot be canonical.** It is the *determination*, not the charge. Task
rows are mutable — the `save()` guard covers only the two type fields (`tasks/models.py:194-214`) — a
Task carries no currency at all, and a determination must be able to exist and never become a charge
(the failed case). Different lifecycle, one-to-zero-or-one.

**A system-generated UsageEvent as canonical** buys the money paths free but the fiction is
load-bearing in seven places (§5), and the row can never be corrected — immutable and undeletable, so
a wrong projection would be permanent.

**Decision: a first-class immutable `Charge` is canonical**, carrying: task, amount, currency, the
resolved book version and matched line, resolution time, charge time, a task-derived idempotency key,
and the dimension snapshot.

### 4.3 Projected 1:1 onto one marked usage posting

The Charge projects to exactly **one** `UsageEvent`: `billed_cost_micros` = the amount,
`provider_cost_micros` = 0, `units` NULL, `usage_metrics` empty, dimensions inherited from the task,
plus a **`kind` discriminator** (`work_charge`).

Dimension inheritance is the reason this is nearly free: `_inherit_dimensions` already pushes
`task_type` and `dim1..dim6` from the task onto every event
(`usage_service.py:110-148`), so "margin by region" nets the price against that same job's COGS in the
same bucket with no new code. A separate entity would have to re-implement inheritance *and* re-plumb
every analytics path.

**The pattern is already in production, twice.** `RawIngestEvent → UsageEvent` is exactly this shape —
the raw row is canonical for what arrived and the projection holds the money guarantee, stated
outright: "NO unique constraint on idempotency_key ... UsageEvent's unique constraint at settle is the
exactly-once authority" (`usage/models.py:167-171`). `Refund → UsageRefunded → wallet REFUND
transaction` is the second: a first-class record whose money effect is carried by a separate posting.

**Why the distinction matters** (versus "a UsageEvent with a flag"):

1. **Re-derivability.** A wrong posting can be rebuilt from the Charge; a wrong canonical event is
   permanent.
2. **The platform-fee effect becomes an explicit property of the projection** rather than something
   inherited by accident (§6).
3. **#138 compatibility.** The Charge holds the policy provenance #138 requires of a rating record,
   while the posting is marked system-generated instead of impersonating a recognised tenant event
   type — which under #138 would otherwise be *unrecognised* and quarantined.

**The projection must preserve the money key.** The posting's id *is* the exactly-once key
(`usage_deduction:{id}`), which is sound because the chain job → Charge → posting → deduction is 1:1
at every hop, and the amount-mismatch guard still protects it.

### 4.4 Idempotency

**The Charge's idempotency key is derived from the task, never caller-supplied.** The task id is
already a unique work identity, and this codebase's stance is explicit in `refund_usage`: do not let
callers supply amounts or keys the system can derive. Belt and braces: the charge fires only on the
winning `complete_task` transition (`tasks/services.py:277-278`), and `UsageEvent`'s unique constraint
on `(tenant, customer, idempotency_key)` (`usage/models.py:76-80`) makes a duplicate posting a
database error rather than a double charge.

**Named precondition, not solvable here:** task *start* has no idempotency. `external_task_id` is
write-only pass-through with no uniqueness (`tasks/models.py:150`), so a retried start creates two
tasks and therefore **two legitimate charges**. No charge-level key can prevent that; it belongs to
#140/#141.

### 4.5 Dated at delivery

The posting is dated at close, so **delivered work is always billable**.

Dating it back to the job's start would keep cost and revenue in one period, but it can be *rejected*:
a job starting at 23:58 on the 31st and closing after the month's push has claimed the period would hit
`billing_period_closed` and become unbillable for delivered work — a failure in the worst direction.

**Accepted consequence:** for a job crossing a month boundary, cost lands in the earlier period and
revenue in the later one. The skew is tightly bounded — no task survives the hard 6-hour ceiling, so
only jobs started in a month's final 6 hours can split at all. **Task-level margin remains exact
always**, because the Charge carries the job's start time.

---

## 5. Consumers of the revenue rail, classified

The ticket's reporting question reduces to this table. Everything that consumes
`UsageEvent.billed_cost_micros` is either a pure economic posting (works unchanged) or an operational
assumption (must filter on `kind`).

**Category A — pure economic posting. Correct with no changes.**

| Consumer | Reference |
|---|---|
| prepaid wallet drawdown | `apps/billing/handlers.py:27-42` → `wallets/operations.py:464-509` |
| postpaid usage-line total | `postpaid_service.py:46-49` |
| grouped line breakdown (per dimension / per seat) | `postpaid_service.py:51-55` |
| durable total the postpaid live counter MAX-merges toward | `apps/metering/queries.py:242-256` |
| live spend counter | `apps/billing/queries.py:79-93` |
| drawdown repair reconcile | `apps/billing/wallets/tasks.py:144-153` |
| referrals reconciliation | `apps/metering/queries.py:150-167` |
| refund amount lookup | `apps/metering/queries.py:79-86` |

**Category B — assumes a genuine operational event. Must filter on `kind` or it misreports.**

| Consumer | What breaks | Reference |
|---|---|---|
| tenant period `event_count` (recomputed and **overwritten**) | count inflated | `queries.py:45-71` → `tenant_billing/services.py:176-199` |
| daily revenue analytics `event_count` | "events per day" wrong | `queries.py:123-129` |
| customer usage summary (keyed on `event_type`, `units`) | a fake metric row with no units | `queries.py:202-221` |
| usage timeseries `markup_micros` + count | charge reads as pure markup | `queries.py:287-302` |
| dimensional margin | right bucket, but a 100%-margin "event" | `queries.py:321-366` |
| `Task.event_count` | a job counts its own charge as work | `tasks/services.py:117` |
| #138 recognition/rating state | a synthetic type would be unrecognised → quarantined | #138 decision doc |

---

## 6. UBB's own platform fee applies

`_calculate_fees` computes UBB's platform fee as a **percentage of
`period.total_usage_cost_micros`** (`apps/billing/tenant_billing/services.py:99-101`, legacy fallback
`:113-121`), and `reconcile_period` recomputes that base from `Σ billed_cost_micros` over UsageEvents
and overwrites the accumulator (`:176-199`).

**Decision: the projected posting counts toward the tenant's fee base.**

This is not a re-opening of UBB→tenant pricing (out of scope per map #137). Fixed-price work does not
exist yet, so there is no status quo to preserve — the only question is whether a new posting falls
inside the existing fee base, and there is no neutral answer.

It is also the only self-consistent option. **Excluding it would require teaching both
`accumulate_usage` and `get_period_totals`**; miss the second and the hourly reconcile silently re-adds
the posting and overwrites the accumulator. And excluding it means a tenant adopting fixed pricing
removes their entire revenue line from UBB's fee base, because §2.1 already zeroed the event revenue.

**Naming debt for #154:** `total_usage_cost_micros` no longer holds only usage.

---

## 7. Corrections: what can move the amount, and what cannot

| Path | Available? | Mechanism |
|---|---|---|
| Cancel before delivery | yes | no charge exists; release the reservation |
| Refund after delivery | yes | the existing OneToOne rail against the posting; lot-aware credit restores grant slices |
| Manual credit / adjustment | yes | `WalletTransaction` type `ADJUSTMENT` with `reason_code` + `actor` (`wallets/models.py:12-15, 81-85`) |
| **Re-invoice a frozen period** | **no — does not exist anywhere** | correction is a refund or an adjustment; `PostpaidResidualLedger` carries only rounding remainders |
| **Edit the amount** | **never** | `UsageEvent.save()`/`delete()` both raise; the Charge is immutable by design |

Stated as an accepted limit rather than a gap to fill: **#139 does not invent a re-invoice path.**

---

## 8. What each existing thing becomes

| Existing | Disposition |
|---|---|
| `POST /metering/tasks/{id}/close` (`metering_endpoints.py:272-292`) | **Becomes a charging call.** Must carry a delivered/failed outcome → #140 |
| `TaskService.complete_task` (`tasks/services.py:265-284`) | **Kept.** Its `transitioned` return becomes the exactly-once charge trigger |
| `close_abandoned_tasks` (`tasks/tasks.py:18-63`) | **Kept, explicitly non-charging.** `auto_closed` must never earn revenue |
| `reap_stale_tasks`, limit kills, `_cascade` | **Kept, explicitly non-charging** |
| `Task.status = "failed"` (declared, never written) | **Needs a writer** → #140 |
| `Task.balance_snapshot_micros` / `provider_cost_limit_micros` | **Pattern reused** — the pinned price follows the same start-snapshot discipline |
| `Task.external_task_id` (`tasks/models.py:150`) | **Insufficient** — no uniqueness, so a retried start double-charges → #140/#141 |
| `TaskType` (`tasks/models.py:20-51`) | **Extended** with a declaration that this kind of work is priced as a whole. Never holds the amount |
| `TaskType.kind = "subtask"` | **May not carry a fixed price** — refused at start (§3.3) |
| Policy book (#138's re-scoped `RateCard`) | **Gains a work-level line type**, keyed on the declared kind of work; a matched work line switches the event-level ladder off for that job |
| `TenantMarkup` + the plan markup rung (`markup_service.py:47-64`) | **Bypassed entirely** for fixed-price work (§2.5) |
| `UsageEvent` | **Gains a `kind` discriminator.** Category B consumers filter on it |
| `Refund` OneToOne (`usage/models.py:140-153`) | **Reused unchanged** — the projection is what makes this work |
| `draw_down_usage` / `usage_deduction:{id}` | **Reused unchanged** — the posting id is the money key |
| `TenantBillingPeriod.total_usage_cost_micros` | **Meaning widens** to include work charges (§6) → naming to #154 |
| `RiskService` start gate | **Gains** the prepaid reservation, the affordability-vs-floor test, and the subtask-price refusal |
| — | **New:** `Charge` (canonical, immutable); a durable per-task price reservation |

---

## 9. Constraints this imposes on other tickets

- **#140 (task lifecycle)** — three hard requirements. The close call **must** carry a delivered/failed
  outcome, because that is the charge switch. `failed` **must** get a writer. Task-start idempotency
  **must** be fixed or explicitly accepted, because a retried start creates two tasks and two
  legitimate charges that no charge-level key can prevent.
- **#141 (task placement / product gating)** — the start gate is where the reservation, the
  affordability test and the subtask refusal live. Task creation being a billing-only endpoint
  (`products=["metering"]` tenants cannot create tasks at all) blocks fixed-price work for those
  tenants.
- **#142 (currency & precision)** — a Task carries no currency; the Charge does. Under CUR-1 it is the
  tenant's single currency, stamped at pin time.
- **#146 (provider-supplied cost)** — the recommended ceiling-as-a-fraction-of-price default lands in
  the limit re-model.
- **#147 (markup precedence)** — reaffirmed for work-level lines: the fixed price is terminal, all four
  markup rungs bypassed.
- **#148 (pricing versions)** — the Charge's pinned book version and matched line are what versioning
  must make reproducible.
- **#154 (vocabulary)** — `total_usage_cost_micros` is now a misnomer; the work-level line, the `kind`
  discriminator value and `Charge` itself all need naming.
- **Reporting tickets** — the seven Category B consumers in §5 must filter on `kind`.

---

## 10. Known residue, flagged rather than buried

- **No pre-flight affordability gate for postpaid fixed-price work.** Prepaid-only by decision; the
  budget cap is the only brake for postpaid.
- **A retried start is two jobs and two charges** until start idempotency exists.
- **Cross-period jobs split cost from revenue**, bounded to jobs started in a month's final 6 hours.
- **No re-invoice path** — post-freeze corrections are refunds or adjustments only.
- **Zero-event jobs charge normally.** The price is for the outcome, not the usage.
- **Per-event margin views show the charge as a 100%-margin row**, segregable via `kind`. Task-level is
  the honest altitude for fixed-price work.
- **Recording the hypothetical metered price in the posting's provenance** — so a tenant can check the
  fixed price is actually profitable — is recommended but not decided as required.
- **Reservation release on every terminal path** is specified as a requirement, but the sweep's exact
  cadence and the reservation's own schema are left to implementation.
- **Whether the ceiling-as-fraction-of-price should be mandatory** for fixed-price work, rather than a
  default, is left open for #146.
