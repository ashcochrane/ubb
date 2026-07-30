# Task lifecycle — the state machine, its transitions, and the idempotency guarantee

**Resolves:** [#140](https://github.com/ashcochrane/ubb/issues/140) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-30
**Decided against:** `main` @ `27efac5`
**Builds on:** `docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — only an explicit
close declaring delivery charges; the close call must carry the outcome; `failed` needs a writer;
start idempotency is a double-billing hole that no charge-level key can close
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 and #139: #154 is the single naming pass that
fixes every term once, and this document introduces two status values, one event pair and one reason
vocabulary that #154 will want to name. The ADR is owed *after* #154 and should cite all three
decision documents.

---

## The decision in one paragraph

**A job is an attempt, identified by a key its caller supplies, and it ends exactly once — in a state
that records who ended it and why.** The start call requires an idempotency key, unique per customer
and claimed permanently, so a retried start returns the original job instead of creating a second one
with a second limit and a second charge. The close call requires an outcome — `delivered`, `failed` or
`cancelled` — because that declaration *is* the charge switch; only `delivered` charges. The two paths
where nobody declared anything (UBB gave up on a silent job) converge on a **new `expired` state**
rather than borrowing `completed` or `killed`, so non-charging becomes structural rather than a rule
someone must remember, and the terminal state of a crashed job stops depending on an unrelated
spend-control flag. **Terminal is terminal**: an identical repeat of a call replays, a contradicting one
is refused loudly, and nothing ever re-opens. Two containment levels are retained — deeper nesting is a
dimension, not a third level — and how long a job may live becomes a property of the declared kind of
work, like its spend ceiling already is.

---

## 1. The state machine

### 1.1 Six states

`active` is the only non-terminal state. The three tenant-declared terminal states are reachable only
by an explicit close; the two UBB-written ones are reachable only by UBB.

| Status | Meaning | Written by | New? |
|---|---|---|---|
| `active` | running | start gate | no |
| `completed` | **the tenant declared delivery** | `close(delivered)` only | meaning narrowed |
| `failed` | the tenant declared the work could not be delivered | `close(failed)` | **gains its first writer** |
| `cancelled` | the work was deliberately stopped or withdrawn | `close(cancelled)`, or a parent's close cascade | **new** |
| `killed` | **UBB stopped it on a spend signal** | limit crossing, patrol, parent kill cascade | meaning narrowed |
| `expired` | nobody ever told UBB how it ended | both sweepers | **new** |

Today's declared set is `active / completed / failed / killed`
(`apps/platform/tasks/models.py:6-11`), of which `failed` has no writer anywhere — only `kill_task`
and `complete_task` write status (`apps/platform/tasks/services.py:150-185, 265-284`).

### 1.2 The transition table

| From → To | Trigger | Who decides | Charges (#139) | Signal emitted |
|---|---|---|---|---|
| active → `completed` | `close(delivered)` | tenant | **yes** | — |
| active → `failed` | `close(failed, reason_code[, detail])` | tenant | no | — |
| active → `cancelled` | `close(cancelled[, reason_code])` | tenant | no | — |
| active → `cancelled` | parent's close cascade, `parent_closed` | tenant's close | no | — |
| active → `killed` | limit crossing / hourly patrol | UBB | no | `task.limit_exceeded` |
| active → `killed` | parent's kill cascade, `parent_killed` | UBB | no | silent (unchanged) |
| active → `expired` | either sweeper, `stale` / `stale_max_age` | UBB | no | `task.expired` (enforcing only) |
| terminal → anything | **never** | — | — | — |

### 1.3 Two invariants this buys

**I1 — `completed` means exactly one thing: the tenant declared delivery.** Nothing else can write it.
This is what makes #139's charge switch safe to key on, and it is the property today's model cannot
offer: `close_abandoned_tasks` writes `completed` for crashed clients and stamps
`metadata["auto_closed"]` (`apps/platform/tasks/tasks.py:57`).

**I2 — `killed` means exactly one thing: UBB stopped it on a spend signal.** Nothing tenant-declared
lands there. This keeps the past-limit report (#41), `stop_context`, `announce_outbox_id` and the
console's limit story honest, and makes "how often do we blow limits" answerable without filtering on a
reason string.

---

## 2. Start: identity and the idempotency guarantee

### 2.1 Two fields with two jobs

`external_task_id` today is write-only pass-through with no uniqueness and no dedup
(`apps/platform/tasks/models.py:150`). It is **not** promoted to the key. Instead:

| Field | Role | Unique? | Required? |
|---|---|---|---|
| `idempotency_key` (**new**) | identifies **one attempt** | yes | **yes** |
| `external_task_id` | a free-text **job label**, reusable across attempts | no | no |

Promoting `external_task_id` itself was rejected: the label is the only place the relationship between
attempts can live. If the label *is* the identity, then attempt 2 of `job-42` must be called something
else, and nothing ties the attempts together in reporting.

### 2.2 The key is required, and this is the in-house pattern

**There is an exact precedent in this codebase.** `create_top_up`: *"Replay-safe: idempotency_key is
required and unique per customer — a retried call re-uses the original attempt and never starts a
second charge"* (`api/v1/billing_endpoints.py:220-222`), backed by a partial unique constraint on
`(customer, idempotency_key)` (`apps/billing/topups/models.py:80-83`). Task start is the same shape of
problem — a call that begins durable work and moves money on completion — and gets the same answer.

Optional-with-dedup-when-supplied was rejected: under #139 the hole is a real double charge, and the
callers most likely to omit the key are exactly the ones who need it. Making the field required is free
under map constraint 1 (no live integrators; one clean break available).

This applies to **subtask starts too** — a subtask start is a start.

### 2.3 Scope and lifetime

**Uniqueness: `UNIQUE(tenant, customer, idempotency_key)`** — the same constraint `UsageEvent` already
carries (`uq_usage_event_idempotency_v2`, `apps/metering/usage/models.py:76-79`). Both are the caller
reporting that something happened for a named customer, so they get the same scope, and two customers
may each have a `nightly-batch`.

**Lifetime: claimed permanently.** No release on terminal, no expiry window. This matches both
in-repo precedents (neither `UsageEvent`'s nor `TopupAttempt`'s constraint has any time bound) and it is
what closes the deliver-twice hole: a repeat of a key whose job already delivered returns that job and
its outcome, never a fresh one.

Releasing the key at terminal was rejected precisely on the case that matters — attempt 1 delivers, the
response is lost, the retry starts a second job and charges twice.

### 2.4 Replay versus conflict

| Repeat of a claimed key | Answer |
|---|---|
| every pinned field identical | `200` with the original job, `replayed: true` |
| any pinned field differs | `409 idempotency_key_conflict`, naming the conflicting field |
| label or metadata differs only | `200` replay; the original's values stand |

**Pinned fields** are those the job snapshots and cannot change: customer, parent, declared kind of
work, resolved spend limit, dimension values — and, under #139, the resolved price. A differing kind of
work is a differing *price*, so a silent replay would charge the render price for a transcode job while
the tenant's own records say otherwise.

The loud-refusal shape mirrors the existing money guard: the drawdown replay path compares the amount
and logs `ledger.usage_deduction_amount_mismatch` rather than quietly accepting a disagreement
(`apps/billing/wallets/operations.py:478-483`). Refusing here is also in keeping with the start gate's
established stance — a start-gate refusal "refuses work that hasn't happened, never a usage report"
(`apps/billing/gating/services/risk_service.py:206-208`), so the 200-always rule that
governs ingest does not apply.

### 2.5 What a replay must NOT do

A replayed start returns the existing job and **creates nothing**: no second Task row, no second
spend limit, no second set of totals, and — the #139-critical one — **no second prepaid reservation.**
This is automatic given the constraint, but it is a requirement on #141's start gate, not an accident.

### 2.6 The idempotency guarantee at every boundary

The ticket asked for this explicitly.

| Boundary | Key | Guarantee | Status |
|---|---|---|---|
| **start** | caller-supplied, `(tenant, customer, key)` | at most one job per key, forever | **new** |
| **usage** | `UsageEvent.idempotency_key`, same scope | at most one event per key | unchanged |
| **close** | the job's own identity | at most one outcome, one Charge | **new** |
| **charge** | derived from the task (#139 §4.4) | exactly once per delivered job | #139 |
| **sweepers** | winning-transition guard | one terminal flip, one announcement | unchanged |
| **kill** | winning-transition guard + `announce_outbox_id` | exactly one announcement per unit | unchanged |

---

## 3. Ending a job: the outcome declaration

### 3.1 One call, outcome required

`POST /metering/tasks/{id}/close` grows a **mandatory** `outcome`. One endpoint, one field, one call
site for the Code Builder (#157) to teach, and one code path in UBB — `complete_task`'s `transitioned`
return is the exactly-once trigger for the charge or for nothing.

Two separate endpoints (`/close` and `/fail`) was rejected as two of everything — two sets of retry,
terminal-state and cascade tests, and two call sites where #144 found no vendor in the survey emits even
one lifecycle pair.

Optional-with-a-`delivered`-default was rejected for the same class of reason #139 rejected its
neighbour: the forgiving path must never be the money-moving one. A dropped field, a stale example or an
old SDK would bill a customer for work that failed.

### 3.2 Three outcomes

`delivered` → `completed` → **Charge**. `failed` → `failed` → no charge. `cancelled` → `cancelled` → no
charge.

The third value captures a real business distinction — *attempted but could not be delivered* versus
*deliberately stopped or withdrawn* — without asking any report to infer meaning from prose. It is worth
its own terminal status rather than a code on `failed`, because "was it us or them?" is a question a task
dashboard (#152) groups by, not one it filters for.

`cancelled` explicitly does **not** map onto `killed`, which was considered and rejected: `killed` is
UBB's spend-signal state with machinery attached. `kill_and_announce` emits `task.limit_exceeded` on the
winning transition and stamps `announce_outbox_id` (`apps/platform/tasks/services.py:209-262`);
`reasons.py` states it is the single source of truth for kill metadata and that *"no stop path may invent
a reason string"* (`apps/platform/tasks/reasons.py:1-13`). A tenant cancellation landing there would
either fire a spurious limit event at the customer's workers or become the only `killed` row with no
announcement — which today means "silently cascaded by a parent".

There is no `partial` outcome, and there will not be: #139 §3.2 settled that there are no partial
charges.

### 3.3 One reason pair, from a UBB-shipped closed list

Both non-delivered outcomes use **one field pair**, not two:

```
{ "outcome": "failed",
  "reason_code": "upstream_provider_error",     # closed list, UBB-shipped
  "reason_detail": "Gemini returned HTTP 503" } # free text, display only
```

- `reason_code` — **required on `failed`**, optional on `cancelled`. A closed vocabulary UBB ships, in
  its own module, kept strictly separate from `reasons.py`. An `unspecified` member makes "required"
  cheap: the caller always has a valid answer, and the dashboard always has a bucket.
- `reason_detail` — free text, **display only, never grouped on**. This is the cardinality guard;
  `DimensionDef` caps cardinality precisely because free-text values explode.
- Neither is accepted on `delivered`.

A tenant-declared registry (like `TaskType` or `DimensionDef`) was rejected as a whole registry, admin
surface and API for a field nothing prices, rates or selects on — and it would leave a tenant who had
declared nothing unable to report a reason at all. Map constraint 5 ("tenant defines everything")
governs what a tenant sells and what it costs — providers, event types, prices — not UBB's own lifecycle
vocabulary, which `reasons.py` already ships closed.

**Illustrative starting list, to be fixed in implementation:** `upstream_provider_error`, `timeout`,
`invalid_input`, `internal_error`, `customer_cancelled`, `superseded`, `parent_closed`, `unspecified`.

### 3.4 Same declaration replays, a contradicting one is refused

| Close against a terminal job | Answer |
|---|---|
| identical declaration | `200`, `replayed: true`, no second Charge |
| any different declaration | `409` naming the real state, with `charge_created: false` |

Symmetric with §2.4 by design: **the same call replays, a different call conflicts**, at both ends of
the lifecycle. The replay half is not optional — a retried close after a lost response is exactly the
case retry-safety exists for.

The refusal half exists because today's silent `200` is, under #139, **silent revenue loss**: a job
killed on its ceiling that the tenant delivered anyway returns HTTP 200 with the killed status and no
indication that no Charge fired. The first sign would be a month-end number that is lower than expected.

Letting a late delivery override a kill or an expiry was rejected. It makes ignoring the stop signal
free, so the ceiling stops being a ceiling; and #139 releases the prepaid reservation on the kill, so the
charge would land against money that may no longer be there.

**The close response therefore carries `outcome`, `replayed` and `charge_created`.**

### 3.5 What this does not touch: the usage rail

**COGS remains entirely independent of chargeability.** A terminal state prevents the creation of a
customer Charge. It never rejects, deletes or zeroes genuine operational usage, including usage that
arrives *after* termination.

This is already how the code behaves and nothing here changes it: `accumulate_cost` "always records,
never raises on limits", a late event on a terminal unit returns the `task_not_active` **verdict** while
still landing, costing and rolling up into its parent, and `task_not_active` is documented as "a verdict,
not a refusal" (`apps/platform/tasks/services.py:56-95`, `reasons.py:21-23`). Under #139 those late
events carry real provider cost and zero revenue.

---

## 4. The paths where nobody declared anything

### 4.1 Today the same crash is recorded two different ways

Two sweepers end silent jobs, and which one wins depends on `Tenant.enforcement_mode` — a spend-control
setting with nothing to do with how the job ended:

- `close_abandoned_tasks` → `completed` + `metadata["auto_closed"]` (`tasks/tasks.py:18-63`)
- `reap_stale_tasks` → `killed` + `task.limit_exceeded` (`tasks/tasks.py:66-127`), for enforcing tenants
  whose jobs have emitted at least once — the graceful sweeper explicitly cedes those (`tasks/tasks.py:43`)

So an identical crashed worker is recorded as a *completed job* for one tenant and a *spend kill* for
another. #139 flagged this and could only work around it, by ruling that the charge may never key on
status alone.

### 4.2 Both sweepers converge on `expired`

**Decision: one new terminal status, written by both sweepers, whatever the enforcement mode.**

This removes the dependency between an unrelated flag and the recorded history. The enforcement setting
still decides whether a **tear-down signal** fires — which is precisely what enforcement buys — but no
longer changes what happened.

**Non-charging becomes structural.** #139 required that any implicit completion path be non-charging *by
construction, not by remembering to check a flag*. With `completed` reachable only through
`close(delivered)`, that requirement is satisfied by the shape of the state machine rather than by a
guard. `metadata["auto_closed"]` retires — the status carries it.

Folding expiry into `failed` was rejected: it mixes UBB's timeouts into the tenant's own failure numbers,
so "our failure rate" would need a filter to mean anything.

### 4.3 A new signal: `task.expired` / `subtask.expired`

The reaper today reuses `TaskLimitExceeded`, whose docstring already names it as a producer — *"by the
verdict-driven kill flow … and the stale-task reaper — so sibling/idle workers tear the task down"*
(`apps/platform/events/schemas.py:357-373`) — with `stale` / `stale_max_age` riding the `reason` field
(`reasons.py:26-29`). The event's real job is *tear down*; the name says *a limit was exceeded*.

**Decision: expiry gets its own event pair.** It mirrors the status decision exactly — a webhook
subscriber alerting on spend incidents stops being paged when a worker dies, and "limit breach rate"
becomes honest without parsing a reason string. The hourly patrol's re-mint path (#43/#44) must learn
them.

Still **enforcing tenants only**: off tenants expire silently, exactly as they auto-close silently today.

A single `task.stopped` replacing both was considered — the consumer's action is identical in every case
— and left to #154 as a naming question rather than taken here.

---

## 5. Long-running work

### 5.1 The ceiling becomes a property of the kind of work

No job can outlive 6 hours today, for anyone: `close_abandoned_tasks` sweeps at 6h regardless of
heartbeat (`tasks/tasks.py:30`) and `reap_stale_tasks` hardcodes the same cutoff (`:97`). The silence
window is already per-tenant (`Tenant.task_stale_seconds`, default 900s,
`apps/platform/tenants/models.py:105`).

Under this decision a job past the ceiling is `expired` — and therefore, under #139, **delivered work
that can never be charged.**

**Decision: both windows move onto the declared kind of work, on the ladder the spend ceiling already
uses** — kind of work → tenant default → 6h / 15m.

`TaskType`'s own docstring makes the argument: *"The ceiling now belongs to the KIND of work,
server-side"*, because one job that legitimately costs 20× its sibling should not force you to raise the
cap on both (`apps/platform/tasks/models.py:20-38`). How long a sold job may take is the same shape of
property, and under #139 it is a commercial one, so it belongs beside the price.

Dropping the ceiling entirely was rejected: it removes the guard the comment was written for — *"so no
tenant (incl. off, which has no reaper) ever gets an immortal task"* — and off tenants have no heartbeat
reaper at all, so their stuck jobs would live forever holding a concurrency slot and, under #139, a
prepaid reservation.

**Consequence for #139:** its reservation design leans on "the maximum reservation lifetime is ~6 hours".
That restates as **the configured maximum age for that kind of work**. The backstop sweep over terminal
jobs holding open reservations becomes more load-bearing, not less.

### 5.2 No keepalive call

Liveness is proved only by reporting usage — `last_event_at` is stamped inside `accumulate_cost`
(`tasks/services.py:122`). A job in a genuinely quiet phase (a long provider call, a queue wait, a
human approval step) is indistinguishable from a crashed one.

**Decision: no heartbeat endpoint. Silence means dead.** One less call site to teach and one less thing
to forget, and the lever is now materially better than it was: the silence window is per kind of work
(§5.1), so a kind with one slow step widens only its own window rather than every job's.

Accepted consequence: a live job that goes quiet for longer than its kind's window is expired. A
keepalive endpoint remains available as a later addition if that proves too blunt in practice — nothing
here forecloses it.

An implicit keepalive on reads was rejected outright: a read that mutates state means a console listing,
a support query or an admin inspecting a stuck job would silently resurrect it.

---

## 6. Containment

### 6.1 Two levels stay; depth is a dimension

The ticket asked whether one containment level is still right "given real workflows nest". It is.

**Decision: two altitudes — job and step. Deeper structure is expressed as a task-scoped dimension.**

- Dimensions are already inherited by every event in the tree, already cardinality-capped, and already
  serve as both grouping key and rate selector, so "cost by sub-agent" works with **no new rows**.
- Everything that makes tasks fast assumes two altitudes: one-hop rollup, one-hop cascade, and
  parent-before-child locking (`tasks/services.py:56-147`, `:188-206`, and `core/locking.py`).
- #139 puts price at job level only — a priced subtask is refused at start — so depth would buy
  reporting granularity that dimensions already provide.
- **#150 can add limit *scopes* without adding tree *depth*.** A cap scoped to a dimension is the real
  ask behind "a limit on the sub-agent", and it is a better axis than a third row level.

Unlimited depth with rollup to every ancestor was rejected on the hot path: each event write would lock
every ancestor in one transaction, so a 5-deep tree locks 5 rows per event and every event in the job
contends on the root — the ingest throughput ceiling for the whole platform — plus a new root-first lock
order and recursive cascade.

Unlimited depth with rollup only to the root was rejected as a quiet trap: an intermediate node's totals
would count only its own direct events, so a ceiling set on a middle node measures a fraction of what
runs beneath it. The tree would look right and the limits would lie.

### 6.2 Containment still cuts downward only

**A failed step does not fail its job.** A failed step is frequently recoverable — retry it, fall back to
a second provider, degrade gracefully — and only the tenant's code knows whether the job as a whole still
delivered. Under #139 the job's outcome is the money, so an automatic upward cascade would let a
step-level detail destroy the Charge for a job that actually delivered through a fallback.

This preserves the existing invariant: *"Killing a subtask kills it ALONE — the parent keeps running and
counting"* (`tasks/services.py:161-162`).

A `fails_parent` flag per kind of step was rejected: it makes the job's commercial outcome a function of
configuration set weeks earlier rather than an assertion made at the moment the answer is known.

### 6.3 Closing a job cancels its still-running steps

`_cascade` today auto-completes a closed parent's active subtasks (`tasks/services.py:188-206`, called at
`:283`), and already-terminal children keep their state.

**Decision: a tenant close cascades still-running steps to `cancelled` with `reason_code =
parent_closed`.** Not to the parent's outcome.

Same principle as §4.2: a state nobody asserted never borrows a state that means someone did. `completed`
and `failed` stay strictly tenant-declared, so "which of our steps fail most" stays answerable — whereas
inheriting the parent's outcome would record steps 1 and 2 as failed when the job failed at step 3.

Steps closed explicitly beforehand keep their real outcome; the cascade only ever touches still-running
ones, which is already how it behaves. No money implication either way (#139 refuses a price on a step at
start).

**Unchanged:** a killed parent still cascades `killed` + `parent_killed`; an expired parent cascades
`expired`. Only the tenant-close path produces `cancelled` + `parent_closed`.

Refusing to close a job with running steps was rejected: cleanup stops being one call, and a single
forgotten step would block the job's close — and therefore its Charge — until a sweeper expired the whole
thing hours later.

---

## 7. Retrying the work itself

**A task is an attempt. A job's retries are separate attempts sharing one label.**

This falls out of §2: a new attempt needs a new key, and the label is reusable. The customer's bill comes
out right in the ordinary case for free, because non-delivery never charges:

```
label "job-42":  try-1 failed     -> no charge
                 try-2 failed     -> no charge
                 try-3 delivered  -> ONE charge
```

**UBB does not enforce "at most one charge per label."** Two attempts that both declare delivery produce
two charges, and that is the recorded truth — the tenant declared delivery twice. The grouped view makes
it visible, and the existing refund rail (#139 §7) corrects it.

Enforcing it was rejected because it turns a deliberately-reusable free-text field into money identity.
A label reused for legitimately recurring work — a nightly batch keeping one name — would bill once and
then refuse forever. That is the case §2.1 chose the two-field split to support.

A per-kind `once_per_label` flag was rejected for the same reason as §6.2's `fails_parent`: it makes the
same call bill or not bill according to configuration set elsewhere.

**Reporting shape (for #152):** attempts group by `external_task_id`; each carries its own key, outcome,
`reason_code` and totals. "3 attempts, 1 delivered" is a grouping, not a new entity.

---

## 8. Async, re-attach and who may close

**Started by one worker, closed by another: already supported, and confirmed as intended.** `close_task`
takes the job id under the tenant's API key with a `WRITE` role floor
(`api/v1/metering_endpoints.py:272-292`). There is no notion of an owning process, and none is added.

**Re-attach is the idempotent start.** A replacement worker that never learned the job id calls start
again with the same key and gets the original back — live with its current status and running totals, or
terminal with its final outcome, which also tells it *"this already delivered, don't redo the work."* No
new endpoint and no second concept.

**Addition:** the job list gains filters on `idempotency_key` and `external_task_id`, so humans, the
console and #152's dashboard can find jobs the same way.

**Resume is never available.** Terminal is terminal (§3.4); a terminal job is readable, never revivable.

A dedicated `GET /tasks/by-key/{key}` was rejected as a second path to one answer that the Code Builder
would then have to teach a choice between.

---

## 9. What each existing thing becomes

| Existing | Disposition |
|---|---|
| `Task.external_task_id` (`models.py:150`) | **Kept as a free-text, reusable job label.** Gains a list filter; never unique |
| — | **New:** `Task.idempotency_key`, required at start, `UNIQUE(tenant, customer, key)`, claimed forever |
| `TASK_STATUS_CHOICES` (`models.py:6-11`) | **Gains `cancelled` and `expired`**; `failed` gains its first writer |
| `_TERMINAL_STATUSES` (`services.py:9`) | **Extends to all five** terminal values |
| `TaskService.complete_task` (`services.py:265-284`) | **Kept.** Becomes the outcome-carrying close; `transitioned` stays the exactly-once trigger |
| `TaskService.kill_task` / `kill_and_announce` (`services.py:150-185`, `:209-262`) | **Unchanged.** `killed` narrows to spend signals only |
| `TaskService._cascade` (`services.py:188-206`) | **Gains the close case:** still-running steps → `cancelled` + `parent_closed`. Kill cascade unchanged |
| `accumulate_cost` (`services.py:56-147`) | **Unchanged.** Late events on terminal units still land, cost and roll up |
| `close_abandoned_tasks` (`tasks.py:18-63`) | **Writes `expired`, not `completed`.** The `auto_closed` marker retires |
| `reap_stale_tasks` (`tasks.py:66-127`) | **Writes `expired`, not `killed`.** Emits `task.expired`, not `task.limit_exceeded` |
| The 6h hard cutoffs (`tasks.py:30`, `:97`) | **Become the fallback rung** of a per-kind-of-work ladder |
| `Tenant.task_stale_seconds` (`tenants/models.py:105`) | **Becomes the middle rung**; the kind of work may override |
| `TaskType` (`models.py:20-51`) | **Gains max age and silence window**, on the same ladder as its COGS ceiling |
| `TaskLimitExceeded` / `SubtaskLimitExceeded` | **Narrow to genuine spend signals.** The reaper stops producing them |
| — | **New events:** `task.expired`, `subtask.expired` (enforcing tenants only) |
| `POST /metering/tasks/{id}/close` | **Gains required `outcome`**, optional `reason_code` / `reason_detail`; answers `replayed` + `charge_created`; `409` on a contradicting declaration |
| `POST /api/v1/billing/pre-check` | **Gains required `idempotency_key`** when `start_task=true`; `409` on a pinned-field mismatch; answers `replayed` |
| `GET /metering/tasks` | **Gains `idempotency_key` and `external_task_id` filters** |
| `reasons.py` (`tasks/reasons.py`) | **Unchanged and untouched.** The outcome vocabulary is a separate module |
| `metadata["auto_closed"]` | **Retired** into the `expired` status |
| Subtask depth guard (`services.py:37-40`) | **Unchanged.** Two levels confirmed, not merely inherited |

---

## 10. Historical data

Both affected populations are precisely identifiable from markers already on the rows, so the rewrite is
exact rather than a guess.

| Population | Becomes |
|---|---|
| `completed` + `metadata.auto_closed` | `expired` |
| `killed` + `kill_reason ∈ {stale, stale_max_age}` | `expired` |
| `killed` + `kill_reason ∈ {task_limit, subtask_limit, parent_killed}` | **untouched** — genuine spend kills |

**Decision: backfill both.** Afterwards, invariants I1 and I2 hold across all of history, so "how many
jobs did we deliver last quarter" and "how often did we blow limits" are answerable without knowing when
the cut happened. Nothing derives money from task status today — #139 is the first thing that will — so
no historical money moves. Webhooks already sent are history and stay as sent.

---

## 11. Constraints this imposes on other tickets

- **#139 (fixed-price economics)** — its named precondition is now met. All three hard requirements are
  delivered: the close call carries the outcome, `failed` has a writer, and start idempotency closes the
  double-billing hole. Its residue item *"a retried start is two jobs and two charges"* is **closed**. One
  restatement is owed: "maximum reservation lifetime ~6 hours" becomes "the configured maximum age for
  that kind of work" (§5.1).
- **#141 (task placement / who sets limits)** — the start gate additionally owns: requiring the key,
  enforcing its uniqueness, refusing a pinned-field mismatch with `409`, and **not double-reserving on a
  replay**. This sits alongside the reservation, affordability test and subtask-price refusal #139
  already assigned there.
- **#150 (spend limits re-modelled)** — dimension-scoped caps are the answer to nesting, not a third
  containment level (§6.1). The per-kind max-age and silence-window ladder lands in the limit re-model
  beside the COGS ceiling (§5.1).
- **#152 (task dashboard)** — group attempts by `external_task_id`; bucket by `reason_code`; **never
  count `expired` or `cancelled` as failures**; surface `charge_created` per job.
- **#154 (vocabulary)** — owes names for: `expired` vs `killed`, the outcome reason vocabulary sitting
  beside (never inside) `reasons.py`, `task.expired` / `subtask.expired`, and whether a single
  `task.stopped` should replace the tear-down family (§4.3).
- **#157 (Code Builder)** — exactly **two call sites** to teach: start-with-key and close-with-outcome.
  No keepalive. This is the multi-call-site lifecycle code #144 found nobody generates, so the burden is
  on keeping it to two.
- **Webhook consumers** — anything alerting on `task.limit_exceeded` will stop seeing timeouts; that is
  the point, and it is a behaviour change to call out at release.

---

## 12. Known residue, flagged rather than buried

- **Two deliveries under one label bill twice.** Deliberate: the label is not money identity (§7).
  Corrected by refund, not prevented.
- **No keepalive.** A live job quiet for longer than its kind's silence window is expired; the lever is
  the per-kind window (§5.2). Revisit if it proves too blunt.
- **A longer configured max age means a longer-lived prepaid reservation** than #139 assumed, making its
  terminal-job sweep more load-bearing (§5.1).
- **Work delivered after a kill or an expiry can never be charged.** Now refused loudly rather than
  silently, but the revenue is still lost (§3.4).
- **The illustrative `reason_code` list is not final** — the closed set must be fixed in implementation
  and named by #154.
- **`unspecified` makes a required `reason_code` weakly binding.** Accepted: it forces a deliberate
  choice and guarantees the dashboard a bucket, which a free-text field would not.
- **Off tenants still expire silently.** They get the correct status but no `task.expired` signal, so
  their idle workers learn nothing — unchanged from today, and what enforcement buys.
- **The concurrency slot** counts `status="active"` (`risk_service.py:177-178`, patrol at
  `patrol.py:190-191`) and is unaffected by the two new statuses, since `active` remains the only
  non-terminal state. Worth an explicit test.
- **A single `task.stopped` event** replacing the tear-down family was considered and deferred to #154
  rather than decided here.
