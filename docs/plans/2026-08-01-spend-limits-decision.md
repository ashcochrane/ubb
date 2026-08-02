# Spend limits re-modelled — four families, one denomination, and a promise that survives contact with unknown cost

**Resolves:** [#150](https://github.com/ashcochrane/ubb/issues/150) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-01
**Decided against:** `main` @ `e009c1b`
**Builds on:** `docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — six states, `killed` narrowed
to spend signals, close carries a required outcome, and terminal is terminal;
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — a fixed price replaces metered
revenue for one delivered job, pinned at start, and only an explicit delivered-close charges;
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — the COGS ceiling is universal,
wallet affordability is billing-only, and mode decides who invoices, not whether economics exist;
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — preserve, flag, remediate; unknown
cost is never zero; ceilings gain `indeterminate`;
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — revenue has three states and
`billed_cost_micros` becomes nullable;
`docs/plans/2026-07-31-streaming-and-long-running-calls-decision.md` (#149) — one event is one provider
operation; the hold/estimate lane is deleted; concurrent unreported work is handed here
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 through #149: #154 is the single naming pass, and
this document introduces four family names, one field rename and one deletion that #154 will want to
fix. The ADR is owed *after* #154 and should cite every decision document in the map.

---

## The decision in one paragraph

**A spend limit is one of four things, and conflating them is what made the old machinery
un-answerable.** A **Ceiling** bounds one unit of work: it starts at zero, dies with the job, races
supplier COGS or wall-clock time, and stops that unit. A **Pool** bounds one customer's charges over a
repeating period: it resets, kills nothing, refuses new starts and signals stop. **Wallet policy** — the
hard and soft floors — is a property of the money and never was a limit. **Admission control** is one
renamed request throttle that bounds how fast new work may enter and says nothing about money. Ceilings
stay **COGS-denominated in v1**, because a customer's price is not an invariant of the work: the same
job at the same supplier cost carries a different price under a different plan, markup or negotiated
override, and for three legitimate paths carries no computable price at all. Customer-charge control
therefore lives entirely in the Pool, which becomes **payment-mode independent** — the same alerts, the
same mid-flight stop, the same start blocking for prepaid and postpaid, because mode decides who
invoices, not whether a spending policy is enforced. Unknown cost never becomes zero and never disables
enforcement: **known-over always fires**, because the known total is a true lower bound, and
`indeterminate` describes only whether a total sitting *below* the line can be trusted. The one rule
survives, restated honestly as a **recording** promise rather than a pricing one. And two mechanisms
that pretended to bound money are removed rather than improved: the per-owner concurrency cap is
**deleted outright**, and the blind window it never actually closed is documented instead.

---

## 1. The one rule, restated

### 1.1 The promise no longer described the system

`docs/spend-control-guarantees.md` §2 states the rule as:

> **Every event that reaches UBB is priced, recorded, and billed immediately.**

Three merged decisions have since made the first verb false:

- **#146 §4** — an event whose cost cannot be resolved is recorded `unresolved` with a **NULL** cost that
  is never zero.
- **#139 §2.1** — every event inside a fixed-price job records real cost and **zero revenue**.
- **#147 §7** and **#148 §4.4** — revenue has four states: `known`, `waived`, `unknown`,
  `not_applicable`.

A published guarantee that promises universal pricing, beside three merged documents that deliberately
decline to price in named cases, is a contradiction a skeptical reader finds in five minutes. It is also
the wrong promise: the load-bearing commitment was never that UBB can always compute a number, it is
that UBB never *loses the evidence*.

### 1.2 The ruling

> **Every structurally valid, authenticated and idempotently consistent event report that reaches UBB is
> durably recorded and acknowledged. Spend limits never reject evidence of work that has already
> happened.**

Costing, pricing and billing are **separate outcomes** that follow recording, and may legitimately
remain unresolved or not apply. The acknowledgement therefore distinguishes successful *recording* from
successful *economic resolution*:

```json
{
  "recorded": true,
  "costing_status": "unresolved",
  "pricing_status": "unknown"
}
```

| Axis | States |
|---|---|
| `costing_status` | `known` · `unresolved` · `not_applicable` |
| `pricing_status` | `known` · `waived` · `unknown` · `not_applicable` |

Worked cases, so the two axes are unambiguous:

| Case | Recorded | Costing | Pricing |
|---|---|---|---|
| Metering-only tenant, ordinary event | yes | `known` | `not_applicable` — margin unavailable, not zero |
| Missing Cost Rate | yes | `unresolved` | `unknown` or `waived` (#147 §7.2 decides which by method) |
| Event inside a fixed-price job | yes | `known` | `not_applicable` — delivery creates the Charge |
| Ordinary event-priced usage | yes | `known` | `known` — customer billed |

### 1.3 Where a refusal is still legitimate

The rule constrains one boundary, not all of them. Refusals survive where they always belonged:

| Boundary | Behaviour |
|---|---|
| Malformed or unauthenticated submission | reject |
| Conflicting reuse of an idempotency key | reject (`409`, per #140 §2.4 / §3.4) |
| Starting **new** work that affordability or policy forbids | refuse at the start gate |
| Reporting usage that already happened | **record it**, even past a limit |
| Closing or failing an existing job | **never** blocked by a spend control |

Known usage that crosses a limit still triggers enforcement *after* it lands. An indeterminate ceiling
may make the cap unguaranteeable, but it never causes a usage report to be discarded.

### 1.4 Why not simply keep the old wording

Rejected: leaving the published sentence alone. The wording is not decorative — it is the sentence the
spend-control guarantees document is built to prove, cited by the integration guide and reproduced in
the console. Leaving a knowingly false verb inside a document whose entire purpose is to earn trust from
a skeptical reader costs more than the edit.

Rejected: **weakening the rule to permit refusals under limit pressure.** That reverses the whole
one-rule programme (#35–#47, 29 green pins), contradicts ADR-0002's ledger-not-wall doctrine, and makes
the books lie exactly when they matter most.

---

## 2. Four families, not one Limit and not five bespoke mechanisms

### 2.1 The problem the model had to solve

Ten distinct mechanisms exist today, each with its own hard-coded scope, denomination, storage and trip
action. Every question this ticket asks — denomination, thresholds, alert-versus-stop, unknown handling
— had to be answered ten times or not at all. The §14 parity matrix records all ten.

### 2.2 The ruling

**Four families.**

| Family | What it bounds | Reset | On trip |
|---|---|---|---|
| **Ceiling** | one unit of work | never — dies with the job | stops that unit |
| **Pool** | one customer's charges over a period | each period | refuses new starts + customer-wide stop signal |
| **Wallet policy** | available funds | n/a | signals; refuses starts |
| **Admission control** | the rate new work may enter | per window | refuses the start |

A ceiling carries a **declared basis**: `cost` or `time`. That is not a switch bolted on for
generality — it is what the system already does. `reap_stale_tasks` kills on silence
(`Tenant.task_stale_seconds`) and on absolute age, riding the **identical** `kill_and_announce` flow
and emitting the **identical** `task.limit_exceeded` event as a COGS crossing
(`apps/platform/tasks/tasks.py:88-127`). Time was already a ceiling denomination in production; the
model now says so, and #140 §5.3's per-kind silence window and absolute maximum land here as declared
ceilings rather than as a fifth concept.

### 2.3 Why not one universal `Limit` entity

A single record with `scope + basis + amount + period + action` would need a mode field that switches
storage, reset semantics and trip behaviour simultaneously. `period=none + action=stop_unit` and
`period=month + action=refuse_starts` share no code, no storage and no meaning — only a table. That is
an abstraction that hides five things rather than unifying them.

### 2.4 Why not leave the ten bespoke

Because the shared parts are genuinely shared, and leaving them un-named is what produced the defects in
§10 and §11: two comparison conventions that disagree, and a master switch that governs some mechanisms
and not others, with nobody able to say which by design.

### 2.5 What the families already get right, and keep

Two existing behaviours are load-bearing and are preserved verbatim rather than re-derived.

**"Stops the whole job" versus "stops only that step" is not a switch.** It falls out of the tree in
`reasons.kill_plan` (`apps/platform/tasks/reasons.py:69-92`): a subtask's own crossing targets the
subtask; a rolled-up crossing targets the parent, whose kill cascades downward. The scope *is* the row
the ceiling is attached to. One implementation, no mode field, already pinned by 17 tests in
`api/v1/tests/test_subtask_pins.py`.

**Alert-only is the absence of a line, not a flag the compare inspects.**
`crossing.budget_stop_threshold` returns `None` for a non-blocking config, so every lane that compares
receives `None` and structurally cannot cross. Alerts are level-based and deliberately separate. This is
the pattern the Pool keeps, and the one a new family should copy if it ever needs the same distinction.

---

## 3. Ceilings are COGS-denominated, and price is not an invariant of the work

### 3.1 The ruling

**A Task ceiling races supplier COGS only. There is no customer-price ceiling on a unit of work in v1.**

```
Task
  supplier COGS ceiling: 5.00

races: Task.total_provider_cost_micros
```

The counter for the alternative was free — `Task.total_billed_cost_micros` is already maintained on
every accumulate (`tasks/services.py:114-127`) and raced by nothing — so this is not a cost argument.

### 3.2 Why: the same work has many prices

**Supplier cost is a property of the job. Customer price is a property of the relationship.** The same
Task, burning the same supplier cost, carries:

| Relationship | Price |
|---|---|
| Individual plan | markup 50% |
| Business plan | markup 20% |
| Negotiated customer | direct event prices or customer overrides |

A ceiling denominated in price would therefore mean a different thing per customer for identical work,
and a tenant reading "this kind of job stops at $5" would be reading a number that is only true for some
of their customers.

### 3.3 Four paths where price is unavailable or unsuitable

| Path | Why a price ceiling cannot work |
|---|---|
| Metering-only tenant | no UBB-calculated customer price exists at all (#141 §1.1) |
| Fixed-price Task | child events carry no event revenue; revenue appears once, at delivery |
| Unresolvable `margin_over_cost` event | the customer price cannot be calculated (#147 §7.2) |
| `direct_event_price` event | price is independent of supplier cost, so it bounds a different thing |

The fixed-price case is the sharpest, because it shows the mechanism failing rather than merely being
unavailable:

```
while the Task runs:     event revenue = 0.00
when the Task delivers:  fixed Charge  = 5.00
```

A price-denominated counter would sit at zero for the entire life of the work and then jump once, after
the work is finished. It cannot control anything while supplier cost is accumulating — which is the only
window in which control is possible.

### 3.4 What this declines, explicitly

#141 §8 recorded *"a customer-charge (revenue-denominated) ceiling ... as a separate requirement for
#150"*. **This document declines it for v1** and rehomes the need: customer-charge protection is the
Pool's job (§7). A price-denominated ceiling may return later as a deliberate feature with its own
evidence — it is not a slot in a generic abstraction that should be filled because the abstraction has
room.

### 3.5 What survives on the ceiling

- COGS ceiling, per unit of work, declared per kind of work.
- Time ceilings — silence window and absolute maximum age (#140 §5.3).
- Nothing else.

---

## 4. Unknown cost: known-over always fires

### 4.1 The residue this closes

#146 §5 ruled that a ceiling standing over an unresolved event reports `indeterminate` and that
enforcement does not fire on it — *"one bad event never kills a good job"*. Its own residue section then
recorded the gap:

> *"`indeterminate` has no decided precedence against other ceiling states. A job can be both
> `limit_reached` on known COGS and `indeterminate` on unresolved events."*

That is this ticket's to settle, and the same question decides what a Pool does when unknown charges sit
inside it.

### 4.2 The ruling

**Known-over always fires. `indeterminate` describes only a total sitting below the line.**

```
ceiling 5.00   known 6.00   + 1 unresolved event
  -> limit_reached      job stops
  -> ALSO reported indeterminate: "true total is at least 6.00"

ceiling 5.00   known 4.00   + 1 unresolved event
  -> indeterminate      job continues, enforcement does not fire
```

The same rule in the Pool:

```
known period charges >= threshold   -> Pool reached, blocks
known below + unknowns present      -> alerts, never blocks
```

### 4.3 Why this is not a reversal of #146

The known total is a **true lower bound**. Once it has crossed, the crossing is a *fact*, and the
unresolved event contributed nothing to that conclusion. #146's actual intent is therefore preserved
exactly: a bad event never *kills* a good job, because a bad event never *contributes* to a crossing.
What is removed is only the reading under which one permanently-unresolvable event type silently
disables ceiling enforcement on every job that touches it — a bypass whose failure mode is invisible
precisely because nothing happens.

Rejected: **any unresolved event suspends enforcement.** It converts a data-quality problem into a
silent, unbounded spend problem, and the tenant has no signal that enforcement is off.

Rejected: **a per-tenant switch between the two.** A third enforcement posture to document, teach and
test, whose safe-sounding default is the one containing the bypass.

### 4.4 The other two states are not zero

| State | Treatment in a Pool basis |
|---|---|
| `unknown` | excluded from the total; reported as unknown; never summed as zero |
| `not_applicable` | excluded from the basis entirely and **reported as excluded** |
| `waived` | genuinely zero — a decision, not a gap. The one state where zero is honest. Still visible in the breakdown |

---

## 5. Fixed price: an absolute ceiling, and a cliff worth naming

### 5.1 The ruling

**A fixed-price kind of work declares its COGS ceiling in absolute micros, exactly like any other kind of
work.** One declaration form across the whole product.

```
TaskType
  cogs_ceiling_micros: 3_000_000

runtime: total_provider_cost_micros >= 3_000_000  -> stop
```

### 5.2 This reverses #139 §3.2

#139 recommended *"ceiling = a tenant-set fraction of the pinned price"*, expressed *"in the only terms
that matter for fixed-price work"*. That recommendation is **not adopted.** Following §3, price does not
belong in the ceiling machinery in any role — not as the thing measured, and not as the thing the
measured number is derived from. A percentage form would reintroduce price into a mechanism this
document just removed it from, in exchange for a convenience, and would require a second resolution
moment, a second pinned field and a second explanation of what happens when a price book changes
mid-job.

### 5.3 The cliff, stated because it is severe

#140 §3.4 decided that a job killed on its ceiling and then closed as delivered receives a `409` with
`charge_created: false` — deliberately, so ignoring the stop signal is not free, and because #139
releases the prepaid reservation on the kill. Combined with #139, this means:

**For a fixed-price job, crossing the ceiling converts a possible profit into a certain total loss.**
Below the line the tenant may still earn the whole price; the instant it crosses, they earn nothing and
keep the supplier cost.

This is worth stating plainly because the intuition it violates is a common one. At the moment of
crossing, the cost already burned is gone under either choice — the only live question is whether the
*remaining* work is worth the *remaining* cost. A job that has consumed 60% of its price but is nearly
finished is still worth completing. **A fraction-of-price ceiling is a runaway detector, not a
profitability calculation**, and treating it as the latter is what makes a tight fraction look prudent
when it is destructive.

The absolute form does not resolve that tension — nothing can, because UBB cannot see how close a job is
to delivering. It declines to *encode* a false answer to it.

### 5.4 The accepted residue

A tenant who raises a price and leaves the ceiling alone has silently tightened it in relative terms: a
$3.00 ceiling under a $5.00 price is 60%, and under a later $8.00 price is 37%, with no signal. This is
accepted, and rehomed as a **console surface** concern for #152 — showing ceiling against price for
fixed-price kinds of work — rather than as a coupling in the data model.

---

## 6. Scopes: task and subtask, and #140 §6.1 is revoked

### 6.1 The ruling

**Ceilings attach to a task or a subtask. The Pool is keyed on a customer. No new scope is added in
v1.**

### 6.2 #140's dimension-scoped cap does not survive contact with the mechanism

#140 §6.1 made this ticket a promise:

> *"#150 can add limit scopes without adding tree depth. A cap scoped to a dimension is the real ask
> behind 'a limit on the sub-agent', and it is a better axis than a third row level."*

**It is revoked, with the reason recorded so it does not resurface as folklore.**

A grouping-field-scoped limit is **Pool-shaped, not Ceiling-shaped**, and fails as both:

- **There is no unit to stop.** A ceiling works because a row accumulates and a unit can be terminated.
  "All work in `region=eu`" has neither. On crossing, the only available actions are a fan-out kill
  across every unrelated active job carrying that value — a cross-job kill that exists nowhere in the
  system — or refusing new starts and signalling, which is what a Pool already does.
- **There is no period.** Every Pool needs one, and nobody has said what period "all work in
  `region=eu`" resets on.
- **It makes cardinality a spend-control setting.** #145 stripped Grouping Fields of every monetary role
  and made them analytics-only. Giving them an enforcement role means raising a field's
  `max_cardinality` (default 100, raise-only, ten slots) silently becomes a change to spend control.

### 6.3 What a tenant does instead

**The ask is already served.** "A limit on the sub-agent" means making the sub-agent a subtask: its own
ceiling covers it, and its spend rolls up into the parent's ceiling one hop. The only unserved case is a
tenant who wants *both* a tree deeper than one level *and* a ceiling on each node — which #140 rejected
on hot-path grounds (every event would lock every ancestor; the platform's ingest ceiling is the root
row).

### 6.4 What #152 and #153 must not build

A console affordance for dimension-scoped caps. It was never built, and now never will be in v1.

---

## 7. The Pool

### 7.1 Enforcement is payment-mode independent

**The ruling: a blocking Pool enforces identically for prepaid and postpaid.**

Payment mode determines how Charges are funded or collected. It must not determine whether a spending
policy is enforced — which is #141 §1.1's governing invariant applied one level down.

Today it does. For postpaid, the live lane races month-to-date spend against the budget line
(`live_counter.debit`, `_threshold`), so the cap stops work mid-flight. For prepaid and meter_only the
live lane races the **wallet balance** against the floor instead, so the budget crossing has no prepaid
lane at all: a prepaid customer receives threshold **alerts** (those fire in every mode via
`BudgetService.record_usage_spend`) but **no stop signal** until the next start gate. The cause is
structural rather than considered — and the seat-keyed month counter is already incremented for every
tenant, so only the compare-and-signal is missing.

The two controls answer different questions and both may hold at once:

| Control | Question |
|---|---|
| Customer spend Pool | *"How much may this customer be charged during this period?"* |
| Wallet policy | *"Can this customer's prepaid balance safely fund more work?"* |

A customer with a **$5,000 wallet** and a **$100 monthly Pool** is a coherent configuration. The large
balance does not invalidate the separate promise that monthly charges stop at $100.

### 7.2 What a blocking Pool does on crossing

```
Customer Charges accumulate
  -> threshold alerts fire
  -> known period spend >= stop threshold
  -> the triggering Charge is RECORDED and COUNTED
  -> active Tasks receive the customer-wide stop signal
  -> new Task starts are refused
```

The Charge that reached the boundary is never rejected or reversed — it represents activity that already
happened (§1). `enforce_mode` keeps its existing meaning, expressed as the presence or absence of a stop
line (§2.5):

| `enforce_mode` | Behaviour |
|---|---|
| `alert_only` | alerts fire; work continues |
| `blocking` | alerts fire; active Tasks receive a stop signal; new starts refused |

A Pool becomes available again when the accounting period rolls over, or when an authorised change
raises or disables the threshold.

### 7.3 Two declared levels, and the tenant default belongs to seats

**The ruling: a Pool is declared on a customer — seat or business, both are `Customer` rows — and a
job's charges count toward its seat's Pool AND its billing owner's Pool where each exists. The tenant
default applies to seats only.**

Today the resolution level depends on **which lane is asking**, which is pinned and described as
deliberate in `apps/billing/gating/tests/test_seat_owner_budget_scopes.py`:

| Counter | Key | Drives | Config resolution |
|---|---|---|---|
| `ubb:budget:{seat}:{YYYY-MM}` | seat | start gate + threshold alerts | seat's own row, then tenant default |
| `ubb:livespend:{owner}:{YYYY-MM}` | billing owner | postpaid live crossing | owner's own row, then tenant default |

For a standalone customer these coincide. For a pooled business they diverge on purpose — *"per-seat
start caps plus one owner-aggregate stop line"*. Once §7.1 makes both counters drive alerts **and**
stops **and** start refusals, "which level" stops being a lane detail and becomes a declaration.

The tenant default is restricted to seats because inheriting it at both levels means **one configured
number silently becomes two separate lines** at different altitudes with different counters — the exact
class of invisible configuration this map keeps deleting.

```
acme (business, holds the wallet)
  pool: 5000.00/month        <- declared explicitly
  seat alice   pool:  500.00/month
  seat bob     pool:  (tenant default)

one job by alice counts toward BOTH alice's pool and acme's pool
```

Rejected: **one Pool at the billing owner.** Loses per-seat caps entirely, and one seat consuming the
whole company Pool with nothing able to declare otherwise is a common, reasonable thing to want to
prevent.

Rejected: **one Pool per seat.** Ten seats at $500 bounds the company at $5,000 only if every seat
spends to the maximum; there is no way to cap the business directly.

### 7.4 The reason must name which control fired

A consequence of §7.1 that today's vocabulary cannot express. `reasons.CUSTOMER_WIDE_STOP`
(`apps/platform/tasks/reasons.py:25`) is documented as *"the owner crossed the wallet floor / budget
cap"* — **one string for two different controls** — and `STOP_SIGNAL_FAMILIES`
(`apps/billing/gating/models.py:34`) offers only `floor_stop` and `soft_floor`.

**The Pool needs its own reason and its own signal family**, so that:

| Reached | Means |
|---|---|
| Pool | the customer's **spending policy** was reached |
| Wallet hard or soft floor | the customer's **available funds** policy was reached |

Either may stop work. The recorded reason, the stop context, the past-limit report and the webhook must
say which. Naming is #154's; the split is decided here.

### 7.5 The fixed-price limitation, stated rather than discovered

A Pool cannot provide meaningful mid-flight enforcement against a price that has not been posted:

```
Task runs        -> event revenue is not_applicable
Task delivered   -> one fixed Task Charge enters the Pool
```

If the completion Charge is itself the crossing, it is recorded, the Pool becomes reached, and
subsequent work is blocked. **Reserving known fixed Task prices against the Pool is a separate future
feature**, not assumed here.

Note the deliberate asymmetry with the wallet: #139 §4.1 already reserves the fixed price against the
**wallet** at start for prepaid customers, so affordability sees the price early while the Pool does
not. Both are correct for what they measure — a reservation is about funds being available, and a Pool
is about charges having been made.

### 7.6 Two live defects that §4 turns from latent into urgent

Both are pre-existing and both bite the moment #147 makes `billed_cost_micros` nullable:

| Defect | Where | Effect |
|---|---|---|
| `Sum("billed_cost_micros")` coalesced with `or 0` | `apps/metering/queries.py:232-237` (and `:256`) | `Sum` silently skips NULLs, so a Pool holding unknown revenue reads **lower than reality** and stops blocking — the precise failure §4 forbids |
| `if billed_cost_micros > 0` | `apps/billing/handlers.py:31` | becomes `None > 0` — a `TypeError` **inside the drawdown handler**, dead-lettering an event that may already have been drawn down |

---

## 8. Uncapped is legal, but never silent

### 8.1 The ruling

**A declared kind of work must state either a ceiling or `uncapped: true`. Declaring neither is refused
at declaration time.**

```
TaskType
  cogs_ceiling_micros: 3_000_000
    -- or --
  uncapped: true                 <- explicit

declaring neither  ->  422
```

The resolved ceiling — or an explicit null meaning uncapped — continues to ride the start response and
to be pinned on the task, as it already does (`risk_service.py:234`).

### 8.2 Why the silent fallback has to go

Today a nullable `TaskType.default_provider_cost_limit_micros` falls back to a nullable
`RiskConfig.default_task_provider_cost_limit_micros` and then to **uncapped, with no signal ever
firing**. The only thing that previously forced the question — the coverage gate refusing a *limited*
start unless `require_cost_card_coverage` (`risk_service.py:203-212`) — is **deleted by #146 §6.1**. So
nothing now stands between "I configured nothing" and "this job has no spend control", in a product
whose core promise is spend control. "I thought limits were on" should be falsifiable from the API.

Rejected: **every job must have a ceiling.** A start-gate refusal for a whole class of tenants, and
there are legitimate uncapped cases — an internal tenant, or work whose cost genuinely cannot be bounded
in advance. Uncapped is a real choice; it just has to be a choice.

### 8.3 The ceiling stays server-side on the declared kind of work

**Unchanged and reaffirmed: a start call may request lower, never higher**
(`risk_service.resolve_type_policy`, `apps/billing/gating/services/risk_service.py:44-54`).

The ticket asked whether this still holds once tenants configure limits at task-definition time. It
does, and the reason is worth recording because "the caller holds the tenant's own API key" makes it
look like protection from nobody. The two parties are different in practice: the **kind of work** is
declared by the tenant's platform team, deliberately, once; the **start call** is made by agent code
that may be generated, buggy, or prompt-injected. The ceiling is protection from your own agent asking
for a bigger allowance than your platform team authorised.

---

## 9. Utilisation is information, not a lifecycle signal

### 9.1 The ruling

**v1 adds no warning event, no outbox message, no configurable warning threshold and no
`ceiling_warning` state.** Enforcement stays binary:

```
below ceiling            -> Task continues
at or above ceiling      -> triggering event accepted and costed -> Task stops
```

### 9.2 What is exposed

For every accepted cost-bearing event, the acknowledgement or receipt may expose:

| Field | Derivation |
|---|---|
| `task_total_provider_cost_micros` | authoritative running total (already shipped) |
| `provider_cost_limit_micros` | the task's snapshotted ceiling (already shipped) |
| `ceiling_used_percentage` | `task_total_provider_cost / provider_cost_limit` |
| `ceiling_remaining_micros` | `max(provider_cost_limit - task_total_provider_cost, 0)` |

Observational only: no event is omitted or rejected, and no worker is required to act.

### 9.3 What analytics retains

Per Task: final ceiling utilisation, **peak** ceiling utilisation, remaining headroom at completion, and
whether the ceiling was reached. That supports tenant reporting such as *"average peak utilisation 64%;
3.2% of Tasks reached their ceiling; average unused headroom $1.40"*.

**Averaging rule, stated because getting it wrong is easy and invisible:** utilisation is averaged **per
Task and then across Tasks**. Averaging every acknowledgement would overweight Tasks that happen to emit
more events.

### 9.4 Why not copy the Pool's threshold alerts

Pools are per-customer-per-period, so four events each is nothing. Ceilings are per-job — four extra
outbox events on **every job**, on the hottest path in the system, and #148 already flagged storage
growth from per-event receipts. The fan-out also buys less: idle sibling workers cannot act on another
job's ceiling the way they can on a customer-wide stop.

---

## 10. One boundary convention, and a defect it closes

### 10.1 The ruling

**At or above the line stops. Everywhere.**

```
ceiling 5.00   total 5.00      -> stops
ceiling 5.00   total 4.99      -> continues
```

### 10.2 The defect

Two comparison conventions exist today and they disagree:

| Path | Compare | Where |
|---|---|---|
| live ingest | `total > limit` | `apps/platform/tasks/services.py:128-130` |
| hourly patrol sweep | `total >= limit` | `apps/billing/gating/patrol.py:193` |

A job landing **exactly** on its ceiling survives the event that landed it, and is then killed by the
patrol within the hour — with reason `task_limit` and **no tipping event to attribute it to**, so the
past-limit report has a kill it cannot itemise and the stop-context array has no `arrived_after=false`
entry for that episode.

### 10.3 Why at-or-above wins

It is the safer reading of "this is the most this job may spend", it matches the Pool's existing
`past_budget_stop` (`spend >= threshold`), and it aligns the patrol *up* rather than aligning the live
path *down* — so the patrol stops being able to kill jobs the live path decided were fine. One
convention across ceiling, Pool and patrol.

**Consequence:** `tasks/services.py:130` changes, and Pin 1's boundary arithmetic changes with it
(`api/v1/tests/test_one_rule_pins.py`). Both deliberate.

---

## 11. What `enforcement_mode` actually governs

### 11.1 The contradiction

`apps/platform/tenants/flags.py` documents `off` as *"byte-for-byte pre-enforcement behavior"*, and the
mode pins assert *"no counters, no signals, no tagging"*
(`apps/billing/gating/tests/test_mode_pins.py`). That is not what happens.

**Job ceilings fire regardless of the switch.** `apps/platform/tasks/services.py` contains **zero**
references to `enforcing`, and `OneRulePinTestBase` creates its tenant at the `off` default while Pin 1
asserts the tipping event kills the task and emits `task.limit_exceeded`
(`api/v1/tests/test_one_rule_pins.py:88-127`). Meanwhile the hourly sweep that retries a **crashed**
ceiling kill runs only for enforcing tenants (`apps/billing/gating/tasks.py:98`), and the same split runs
through the deadlines: the 6h auto-**complete** safety net is universal while the kill-on-silence reaper
is enforcing-only.

### 11.2 The ruling

**Declaring a ceiling is itself the opt-in.**

| Always on, if declared | Governed by `enforcement_mode` |
|---|---|
| task + subtask COGS ceilings | wallet hard floor |
| silence window, absolute maximum age | wallet soft floor |
| **their hourly repair sweep** — newly universal | customer spend Pool |
| | customer-wide stop flag |

`off` is restated as **"no customer-wide enforcement"**, not "nothing happens". A tenant who set a $5
ceiling asked for it; an unrelated switch should not silently disable it. Nothing any individual job
asked for is switched by the mode — the floors, the Pool and the customer stop flag are properties of
the customer relationship, which is exactly what the switch should govern.

Making the repair sweep universal closes the remaining gap: today an `off` tenant whose kill transaction
crashes keeps a runaway job running with no sweep to catch it.

Rejected: **ceilings obey the switch.** The documented meaning becomes true at the cost of a deliberate,
explicit ceiling being silently disabled by an unrelated setting — and Pin 1 would have to assert the
opposite of what it asserts today.

---

## 12. The blind window: documented, not mitigated

### 12.1 What #149 handed over

Concurrent unreported work — **not** long calls. #149 §1.2 established that duration is not the cause: a
200ms call and a 90-second call both report after they finish. The exposure scales with how many
operations are simultaneously unreported.

```
Provider operation starts
  -> supplier cost not yet known to UBB
Provider operation completes
  -> usage event arrives
  -> COGS recorded
  -> Task ceiling can be evaluated
```

### 12.2 The ruling

**The blind window is documented honestly. No per-kind concurrency field, and no artificial headroom on
the ceiling.**

The guarantee is stated as:

> **The COGS ceiling is enforced against supplier cost reported to UBB. Operations already dispatched
> before the ceiling is observed may still complete, report usage, and increase final COGS beyond the
> configured ceiling.**

Those later events remain accepted and costed, marked as arriving after the Task was stopped — which is
the existing `arrived_after` stop-context machinery (#41), unchanged.

### 12.3 Why concurrency does not convert to money

Because it does not:

```
10 simultaneous lightweight calls  -> may cost very little
1  simultaneous deep-research call -> may cost substantially more
```

A `TaskType.max_concurrent` field would bound outstanding **operations** and still provide no dependable
dollar-denominated overshoot bound. It would also require tenants to maintain another operational
setting that likely duplicates limits already present in their own workers, queues, provider accounts or
orchestration systems.

Rejected: **headroom** — a trip factor that stops at 80% of the ceiling "leaving room" for in-flight
work. The right factor depends on concurrency and per-call cost, neither of which UBB can see, and it
reintroduces exactly the class of dollar-denominated promise retired by decision
[#10](https://github.com/ashcochrane/ubb/issues/10) as dishonest for report-after-the-fact metering.

### 12.4 The tenant's own controls, named as theirs

Smaller operational units (#149 §3.4's declared granularity), lower worker concurrency, provider request
timeouts, queue controls, and avoiding unnecessary parallel calls. These are legitimate and effective.
**UBB should not pretend that one generic concurrency number converts them into a precise cost
guarantee.**

### 12.5 `max_concurrent_requests` is deleted

Not narrowed, not moved — **deleted.** It was a weak attempt to bound unknown COGS, and keeping it
active in the codebase invites confusion about functionality the product does not have and does not
want.

What goes with it:

| Item | Where |
|---|---|
| `RiskConfig.max_concurrent_requests` + admin display | `apps/billing/gating/models.py:8`, `admin.py:7` |
| the cap block and its `concurrency_limit` refusal | `apps/billing/gating/services/risk_service.py:172-181` |
| `concurrency_limit` from the reason vocabulary | `api/v1/schemas.py:50` — a **docstring comment**, since `reason` is `Optional[str]` and not an enum, so this is **not** a breaking spec change |
| the concurrency half of `test_concurrency_reaper.py` | `TestConcurrencyCap` (3) + 2 in `TestP5ReviewFixes` = **5 tests**; the reaper and abandoned-close halves stay |
| one setup line | `apps/billing/gating/tests/test_risk_service.py:15` |
| `Task.idx_task_owner_status` | `apps/platform/tasks/models.py:169-172` — exists solely for the cap's COUNT; joins #145's index drops |

What **survives**: the stale reaper. Its concurrency-slot rationale was secondary
(`apps/platform/tasks/tasks.py:38`); its real job is a deterministic terminal state for crashed jobs.
The comment needs correcting, the logic does not.

**A trap for whoever implements this.** `apps/billing/tests/test_concurrency_races.py`,
`test_concurrency_races_grants.py`, `apps/billing/invoicing/tests/test_concurrency_postpaid.py`,
`test_hold_lane.py` and `live_counter.py` all say "concurrency" about **transactional races on money
invariants**. They are entirely unrelated to the cap. A grep-and-delete would tear out the exactly-once
money proofs.

### 12.6 A residue this deletion resolves

#141 §9 flagged that `max_requests_per_minute` staying in billing while the concurrency cap moved to the
kernel was *"slightly arbitrary — worth revisiting in #150"*. With the cap deleted, nothing moves and
the anomaly disappears.

---

## 13. Admission control

### 13.1 The ruling

**One mechanism survives, renamed and scoped to new-work admission.** It is retained as Admission
Control — never as a financial limit and never as a mitigation for unreported COGS.

Its name should describe exactly what it gates: `task_start_rate_limit_per_minute` if it governs task
creation, or `request_throttle_per_minute` more generally. #154 makes the final call.

### 13.2 Its contract

| It does | It does not |
|---|---|
| bound the rate at which new work may enter | participate in COGS calculation |
| protect API capacity and plan entitlements | estimate concurrent unreported cost |
| refuse a start with `rate_limit_exceeded` | alter a Task ceiling |
| | get presented as spend protection |

### 13.3 It may only apply at an admission boundary

| Call | Behaviour |
|---|---|
| Start a new Task | may be refused, `rate_limit_exceeded` |
| Report usage that already occurred | **must** be accepted and recorded |
| Close or fail an existing Task | **must not** be prevented by the throttle |

This preserves §1: evidence of completed work is never discarded because a control fired.

### 13.4 Today's implementation already satisfies this — confirmed, not assumed

`RiskService.check` has exactly **one** non-test call site — `api/v1/billing_endpoints.py:277`, the
start gate. The throttle therefore structurally cannot reach ingest or close today. Pin 7
(`test_no_usage_report_path_answers_429_or_409`, `api/v1/tests/test_one_rule_pins.py:216`) already holds
the ingest half. **The close half is unpinned and should gain a pin**, since the guarantee is now
explicit.

The work is therefore rename, rehome and restate — not narrowing behaviour that is currently too wide.

### 13.5 Where it belongs

If it is a tenant-facing plan entitlement it may stay in the billing domain. If it is merely an internal
infrastructure safeguard, it belongs in platform configuration. Flagged for #154 / #155; the behaviour
is valid either way.

---

## 14. The parity matrix

Every mechanism on `main` @ `e009c1b`, with its deliberate home. Nothing is permitted to have no home.

**Enforcement gate:** *universal* = runs regardless of `enforcement_mode`; *enforcing-only* = no-op
unless `enforcement_mode = "enforcing"`.

| # | Mechanism | Owner / scope | Denomination | Reset | Thresholds | Trip action | Alerts | Unknown-value | Gate today | Current tests | Becomes |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | Task ceiling | one top-level Task row | COGS (`total_provider_cost_micros`) | never | none | kill + cascade down | `task.limit_exceeded`; `stop`/`stop_reason`/`stop_scope` on every ack; stop-context on late events | `indeterminate` (§4) | universal | `test_one_rule_pins.py` pins 1/2/13/14; `test_only_the_provider_total_races_the_limit`; `test_patrol_pins.py` | **Ceiling** (task, basis `cost`) |
| 2 | Subtask ceiling | one Task row with a parent | COGS, own total + rolls up one hop | never | none | killed **alone**; parent keeps counting | `subtask.limit_exceeded`; parent trip wins the scalar ack slot | `indeterminate` (§4) | universal | `test_subtask_pins.py` (17) | **Ceiling** (subtask, basis `cost`) |
| 3 | Silence window | one task | time since `last_event_at` (`Tenant.task_stale_seconds`, 900s) | every event re-stamps | none | kill + cascade, reason `stale` | same events as a COGS crossing | n/a | enforcing-only | reaper tests; `test_concurrency_reaper.py` | **Ceiling** (task, basis `time`) — #140 §5.3 |
| 4 | Absolute age | one task | wall clock since `created_at`, 6h | never | none | kill + cascade, `stale_max_age`; a **separate universal** beat auto-*completes* at 6h | same events | n/a | kill enforcing-only; auto-complete universal | as above | **Ceiling** (task, basis `time`) — #140 §5.3 |
| 5 | Budget cap | **two keys**: seat (start gate + alerts) and owner (postpaid live crossing) | customer charge (`billed_cost_micros`) | calendar month, **effective**-month basis | `alert_levels` `[50,80,100,110]`; stop at `cap * hard_stop_pct / 100` | refuses new starts; postpaid **only** sets the mid-flight stop flag | `budget.threshold_reached` per level, deduped | **broken** — §7.6 | live crossing enforcing-only; start-gate check universal | `test_budget_service.py`, `test_budget_e2e.py`, `test_budget_effective_at.py`, `test_seat_owner_budget_scopes.py`, `test_budget_endpoints.py` | **Pool** — mode-independent (§7.1), two declared levels (§7.3), own reason + family (§7.4) |
| 6 | Hard floor | billing owner's wallet | balance vs `min_balance_micros` — inspected, never accumulated | n/a | none | customer-wide stop + resume; refuses starts | `stop.triggered` / `stop.cleared` via `StopSignalState` | n/a | signals enforcing-only; start refusal universal | `test_stop_resume_pins.py` (4–6), `test_crossing.py`, `test_stop_signal_ledger.py` | **Wallet policy** — outside the limit vocabulary |
| 7 | Soft floor | billing owner's wallet | balance vs `soft_min_balance_micros`, clamped ≥ hard line | n/a | none | refuses **new top-level** starts only | `soft_floor.crossed` / `.cleared`; never tags events | n/a | enforcing-only; none for postpaid | `test_soft_floor_pins.py` (12) | **Wallet policy** |
| 8 | Concurrency cap | billing owner | count of active tasks | n/a — live COUNT | none | refuses start, `concurrency_limit` | none | n/a | enforcing-only | `test_concurrency_reaper.py`, `test_concurrency_webhooks.py` | **DELETED** (§12.5) |
| 9 | Rate limit | seat | requests/minute, Redis fixed window | per minute | none | refuses start, `rate_limit_exceeded` | none | n/a | universal | `test_risk_service.py` | **Admission control** — renamed, scoped (§13) |
| 10 | Coverage gate | the start call | n/a | n/a | n/a | refuses a limited start, `cost_coverage_required` | none | n/a | universal | `test_one_rule_pins.py:291-333` (4) | **DELETED** by #146 §6.1 — its pins retire rather than rehome |

---

## 15. What each existing thing becomes

| Existing | Disposition |
|---|---|
| `Task.provider_cost_limit_micros` | **Kept.** The COGS ceiling, unchanged in denomination and in being pinned at start |
| `Task.total_billed_cost_micros` | **Kept and still raced by nothing** on the unit. It feeds analytics and the Pool's durable basis |
| `_crossed_limit` (`tasks/services.py:128-130`) | **Compare changes to `>=`** (§10) and **moves to `core/`** (§17) |
| `TaskType.default_provider_cost_limit_micros` | **Must be explicit**: a ceiling or `uncapped: true`; nullable-means-maybe is no longer a valid declaration (§8) |
| `RiskConfig.default_task_provider_cost_limit_micros` / `default_subtask_...` | **Kept** as the tenant fallback; moves to the kernel per #141 §7 |
| `RiskConfig.max_concurrent_requests` | **Deleted** (§12.5) |
| `RiskConfig.max_requests_per_minute` | **Kept, renamed, rescoped** as Admission Control (§13) |
| `RiskConfig.gate_fail_closed` | **Unchanged** — it governs the budget read, which is now a Pool read |
| `Tenant.require_cost_card_coverage` + the coverage gate | **Deleted** by #146 §6.1; its four pins retire |
| `BudgetConfig` | **Becomes the Pool.** Gains an explicit level; the tenant default applies to seats only |
| `reasons.CUSTOMER_WIDE_STOP` | **Splits** — the Pool gets its own reason (§7.4) |
| `STOP_SIGNAL_FAMILIES` | **Gains a Pool family** beside `floor_stop` and `soft_floor` |
| `crossing.past_budget_stop` / `budget_stop_threshold` | **Unchanged in semantics**; joins the relocated ceiling predicates in `core/` |
| `sweep_over_limit_tasks` (`patrol.py:177`) | **Unchanged in behaviour**, now runs for **every** tenant (§11) |
| `reap_stale_tasks` | **Kept.** Writes `expired` per #140; its concurrency-slot comment is corrected |
| `close_stale_tasks` | **Kept** as the universal 6h auto-complete safety net |
| `LiveCounter.hold` / `release` / `settle`, `PricingService.estimate` | **Already deleted by #149 §6.6** — this ticket inherits nothing from them |
| Ack fields | **Gain** `ceiling_used_percentage`, `ceiling_remaining_micros`, `recorded`, `costing_status`, `pricing_status` (§1, §9) |

---

## 16. Narrowings and reversals of merged decisions

Recorded explicitly, because this map's convention is that a later document may narrow an earlier one
but may never do it silently.

| Document | What changes |
|---|---|
| **#139 §3.2** | **Reversed.** The recommended fixed-price ceiling as a fraction of the pinned price is not adopted; ceilings are absolute micros (§5.2) |
| **#140 §6.1** | **Revoked.** Dimension-scoped caps are not the answer to nesting — they are Pool-shaped with no unit, no period, and would make cardinality a spend-control setting (§6.2) |
| **#141 §8** | **Declined for v1.** The revenue-denominated task ceiling recorded there as a separate requirement is not built; the need is rehomed to the Pool (§3.4) |
| **#146 §5** | **Completed, not reversed.** Its named residue — the precedence of `indeterminate` against a known crossing — is settled as known-over-fires (§4.2), which preserves its intent exactly |
| **#149 §4.2** | **Narrowed.** Its rejection of a call-denominated cap is upheld *and extended*: the existing per-owner cap is deleted rather than kept as a partial mitigation (§12.5) |
| **`spend-control-guarantees.md` §2** | **Restated.** The one rule becomes a recording promise (§1); the ceiling/patrol boundary convention unifies (§10); `enforcement_mode`'s scope is corrected (§11); the blind window gains an explicit paragraph (§12.2) |

---

## 17. Constraints this imposes on other tickets

- **#146** — its `indeterminate` state survives intact and gains the precedence rule it left open (§4.2).
  Its deletion of the coverage gate is depended upon by §8.2: without it, uncapped-by-default would have
  a second, unrelated guard.
- **#147** — `billed_cost_micros` becoming nullable **breaks two live call sites** the moment it lands
  (§7.6). Neither is this ticket's to fix, but both are now on a clock, and `queries.py:232-237` is the
  same `or 0` class of defect #147 §13 and #153 already name.
- **#148** — the two residues it handed here are **dissolved, not inherited**: #149 §6.6 deleted the hold
  and the estimate, so "what an accept-time hold does with no estimate" and "the mis-hold on backfilled
  events" have no subject. Its receipt work is unaffected; §9's utilisation fields are derived, never
  stored on a receipt as independent values.
- **#151 (charging modes)** — must carry §7.5: a Pool cannot enforce mid-flight against a price that has
  not been posted, and the fixed-price completion Charge may itself be the crossing. Also owes the pin
  that #139's 1:1 projection is what keeps a fixed Charge counted **exactly once** in the Pool — a
  Charge that additionally incremented a Pool directly would double-count, and nothing structurally
  prevents that today.
- **#152 (task dashboard)** — must render the ceiling's **three** states (`within_limit`,
  `limit_reached`, `indeterminate`) and never show `indeterminate` as "under limit". Must surface
  utilisation per §9.3 with the per-Task-then-average rule. Must show ceiling against price for
  fixed-price kinds of work, which is where §5.4's relative-tightening residue is caught. Must **not**
  build a dimension-scoped cap affordance (§6.4).
- **#153 (analytics re-alignment)** — inherits peak utilisation, headroom at completion and the
  ceiling-reached flag as first-class reporting shapes, plus the rule that unknown revenue is excluded
  from a Pool basis and reported, never summed as zero.
- **#154 (vocabulary)** — owes names for: the four families themselves; `Ceiling` versus the existing
  "limit"; `Pool` versus "budget"; the Pool's stop reason and signal family (§7.4); the renamed
  admission control (§13.1); `uncapped` as a declaration keyword; and whether
  `provider_cost_limit_micros` survives as a field name now that "limit" means four things.
- **#155 (migration and cutover)** — owes: the `max_concurrent_requests` deletion and its index drop
  (§12.5, **not** a breaking spec change — the reason field is a free string); the ceiling compare
  moving to `core/`; the `>=` change and Pin 1's arithmetic; the Pool's level declaration and the
  seats-only tenant default; the four retiring coverage-gate pins; and the universal repair sweep.
- **#156 / #157 (Code Builder)** — the generated integration story gains **nothing new to call**. There
  is no keepalive, no hold, no warning acknowledgement to handle and no concurrency setting to teach.
  The ack simply carries more fields, and `stop` is still the one thing a worker must react to.

---

## 18. Residue, flagged rather than buried

- **The blind window is real and unbounded.** Work already dispatched will land and bill past any
  ceiling. v1 documents it and hands the tenant nothing new; the mitigations are theirs (§12.4). This is
  the second ticket in a row to decline a mechanism here, and that consistency is deliberate — but it is
  still an exposure a customer will eventually ask about with a number attached.
- **A fixed-price job killed on its ceiling earns nothing** (§5.3). The tenant holds real supplier cost
  against zero revenue, and UBB cannot tell a runaway job from one that was nearly finished. The
  absolute ceiling declines to encode a false answer; it does not provide a true one.
- **Relative tightening of fixed-price ceilings is silent** (§5.4). Raising a price does not move the
  ceiling, and only a console surface catches it.
- **The Pool is blind to a fixed price until delivery** (§7.5), while the wallet reservation sees it at
  start. Two different answers to "how much has this customer committed to" that are each correct for
  their own question, and will read as an inconsistency to anyone comparing them.
- **`indeterminate` still has no per-event remediation SLA.** #146 §3.1's replay closes the loop, but a
  ceiling can sit indeterminate indefinitely if nobody remediates, and §4 deliberately lets the job keep
  running in that state when known spend is below the line.
- **Deleting the concurrency cap removes a real, if crude, guard.** A tenant using it today as a rough
  parallelism bound loses it and gains nothing in return. Justified by §12.3, but it is a working
  feature being removed because its name implies a promise it never kept.
- **Two Pool counters remain, seat and owner.** §7.3 makes their levels explicit rather than
  lane-dependent, but it does not merge them, so a pooled business still has two month keys and two
  reconcile paths.
- **Admission control has one member.** A family named for a single mechanism invites someone to add a
  second one to justify it. The family exists to keep a request throttle from being mistaken for spend
  protection — that is its whole job, and it should stay empty otherwise.
- **The ceiling predicates must move to `core/`.** #110 named `apps/billing/gating/crossing.py` the one
  owner of the crossing decision, but the kernel may not import a product (ADR-001 rule 2), which is why
  `_crossed_limit` is an inline compare outside that owner. With #141 moving ceiling config to the
  kernel and §10 unifying the convention, the pure predicates belong in `core/` where both sides may
  import them. Recorded here as a derived consequence rather than a decision; it needs its own review in
  the implementation ticket.
