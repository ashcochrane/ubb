# Historical reporting and analytics — one economic query, and the honesty rules it enforces

**Resolves:** [#153](https://github.com/ashcochrane/ubb/issues/153) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-03
**Decided against:** `main` @ `d584974`
**Builds on:** its three blockers —
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — only declared measurements may
move money; `tags` folds into a never-groupable `metadata`; Grouping Field replaces Dimension;
Measurement Concept restores cross-provider aggregation.
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the receipt is authoritative and carries
values not pointers; a fourth pricing status `not_applicable`; remediation completes COGS inside closed
periods.
`docs/plans/2026-08-02-charging-modes-decision.md` (#151) — three independent declarations at three
levels; every COGS surface must say which derivation produced a figure; no aggregate may sum a NULL as
zero.
and on five more it inherits work from: #139 (the Charge and its 1:1 projection), #141 (mode decides
who invoices, not whether revenue exists), #142 (foreign-currency quarantine), #146 (cost is never
zero when unknown), #147 (revenue has three states), #149 (declared granularity), #150 (four limit
families).
**Status:** decided. Planning only; implementation is out of scope for map #137.

**This document answers one question merged #148 left open and extends another.** §6 settles
#148 §17's *"whether the reporting figures for the closed period restate or stay frozen … should be
decided by #152 or #153"*. §12 places a **new content obligation on the receipt** that #148 did not
carry: a receipt must outlive the measurements it explains, so it must contain enough to explain *and
remediate* an amount after measurement detail has been pruned. Neither is a defect in #148; both are
consequences of decisions taken here that it could not have anticipated.

**No ADR yet, deliberately.** Same reasoning as #138 through #151: #154 is the single naming pass, and
this document coins or retires eleven names. The ADR is owed *after* #154.

---

## The decision in one paragraph

**Margin is a subtraction between two quantities that no longer share a grain, so it is computed once
per bucket and never per row.** Cost is naturally per event; revenue is naturally per Charge — which is
per event for metered work, per job for fixed-price work, and per customer-period for revenue the
tenant supplies from outside UBB. A margin figure is therefore published **only where every revenue
component in that bucket is attributable at that bucket's grain**; where it is not, the surface reports
cost, reports the revenue it can attribute, names what it could not, and prints no margin. The one
exception is **time**, along which period revenue may be distributed as labelled recognition, because a
period record declares its own span while it never declares a provider. The per-customer `revenue_mode`
switch — which converts *"we do not invoice this"* into *revenue zero*, and is why every metering-only
tenant currently reads exactly 0.00% margin — is **deleted**, and tenant-supplied revenue is promoted
from a recurring profile to a first-class record at its own scope. Grouping collapses to **two kinds of
thing**: a field on the posting, and a declared rollup of one (Event Category over Event Type,
Measurement Concept over Measurement), reached through one namespaced parameter and one discovery
contract that declares, per axis, **which measures it supports** — so *"revenue by provider is
unavailable"* is data rather than each chart's private guess. Five overlapping endpoints collapse into
**one economic analytics query surface** whose engine aggregates each measure from its own canonical
fact source and combines them only where scopes are compatible, returning a **status per measure**
(`known` · `incomplete` · `unavailable_at_requested_grain` · `not_applicable`) so that unknown, zero and
inapplicable stop being the same integer. Nothing derived is stored: closed-period **figures restate**
when facts resolve while **money never moves**. History does not survive the vocabulary change — old
rows carry undeclared measurement keys that #145 forbids auto-registering, so the cutover is a **clean
operational reset**, not a migration. And "historical" is finally given a length: **two published
retention clocks**, six years for money and its explanation, a shorter declared horizon for bulky
measurement detail, with the query surface stating its own horizons rather than silently returning a
short answer to a long question.

---

## 1. The ticket's premise, corrected in three places

Three of the ticket's framing statements are wrong against `main`, and each correction changes what the
ticket is for.

### 1.1 "Margin is computed on read and never stored"

It is stored. `CustomerEconomics` (`apps/subscriptions/economics/models.py:26-49`) persists
`gross_margin_micros`, `total_revenue_micros`, `margin_percentage`, `revenue_mode` and
`is_unprofitable` per customer per month, written by `MarginService.snapshot_customer`
(`economics/services.py:62-90`) from `CustomerCostAccumulator` — a *different* aggregate maintained by
event handlers, not from `UsageEvent`.

So there are two margin answers for one customer-month, from three storage layers:

| Surface | Source | Freshness |
|---|---|---|
| `/margin/summary`, `/margin/customers`, `/margin/customers/{id}` | live over `UsageEvent` | request time |
| `/margin/customers/{id}/trend`, `/margin/unprofitable` | `CustomerEconomics` snapshot | month-end, never revisited |

Nothing reconciles them, nothing labels which is which, and §6 shows the case where they are guaranteed
to disagree forever.

### 1.2 "with three live `tag_key` exceptions … does the re-model close those, or bless them?"

**#145 already closed them**, four days before this ticket was reached: `tags` is retired as a concept,
its contents belong to `metadata`, and `metadata` is *"filterable and readable but never groupable"*
(#145 §8.2). What is genuinely open — and what §5 and §9 decide — is not *whether* the hatches close but
**what the three surfaces become**, which is a different question with a customer-facing edge the
grouping ruling does not reach.

### 1.3 "Does the past-limit report change if limits gain a second denomination (#150)?"

**They did not.** #150 §3 kept ceilings COGS-only in v1 on the argument that *customer price is not an
invariant of the work*, explicitly declining #141 §8's revenue-denominated ceiling. The premise is
false, and the real change is structural rather than dimensional: one "limit" became **four families**,
and the existing report knows two of them (§10).

---

## 2. Margin is a bucket-level subtraction, never a row-level one

### 2.1 The ruling

**A margin figure is produced by aggregating each side to a bucket and subtracting once.** Per-row
margin on an individual posting ceases to be a concept — for metered work as well as fixed.

The two sides have genuinely different natural grains:

```
cost     → one provider operation          (always per event)
revenue  → one Charge
             metered work   → per event
             fixed-price    → per delivered job
             tenant-supplied→ per customer-period
```

Per-event margin was never a general fact. It was an artefact of metered pricing making both sides
accidentally per-event, and it silently stops being true the moment any other pricing shape exists.

### 2.2 The distortion this removes

A tenant sells `research-report` at a flat £5. One run makes 400 provider calls costing £2.40. Under
#139 §4.3 the £5 lands as one synthetic posting inside the job, `provider_cost_micros = 0`,
`usage_metrics` empty, dimensions inherited from the Task, `provider` unset.

Today's `by_provider` breakdown (`api/v1/metering_endpoints.py:562-568`) therefore shows:

| Row | Cost | Revenue | Reads as |
|---|---|---|---|
| `openai` | £1.60 | £0.00 | catastrophic loss |
| `gemini` | £0.80 | £0.00 | catastrophic loss |
| `(unattributed)` | £0.00 | £5.00 | infinite margin |

Every row is wrong; only the total is right. #139 §5 anticipated exactly this, classifying dimensional
margin as *"right bucket, but a 100%-margin 'event'"* — and this document is where that flagged
consequence is discharged rather than merely noted.

### 2.3 What analytics reads, and what it does not

**Analytics keeps reading revenue off the projected posting, not off the `Charge` record.** The
projection is 1:1 at every hop and its exactly-once key is the posting id (#139 §4.3), so summing
postings *is* summing Charges. Introducing a second aggregation path over `Charge` rows would create
two totals that can disagree — the shape #148 §3.2 refused outright.

What changes is the **presentation grain**, not the storage. The fixed-price posting is excluded from
operational breakdowns (§7) and its revenue is attributed at job scope (§4), while the money rails —
wallet drawdown, postpaid accrual, the Stripe line push, the live counter — continue to read it exactly
as #139 designed.

---

## 3. Revenue: one switch deleted, one record promoted

### 3.1 `Customer.revenue_mode` is deleted

`revenue_mode ∈ {"", "billed", "metered_only"}` resolves from the tenant's billing mode
(`economics/revenue.py:39-44`) and is consumed in one place:

```python
usage_revenue = usage_billed if revenue_mode == "billed" else 0   # economics/services.py:8
```

It is a coarse, customer-level answer to a question #147 §7 already answers precisely per posting, and
it answers it wrongly: it converts *"UBB does not invoice this customer"* into *"this customer produced
no revenue"*. #141 §1.1's governing invariant says the opposite — **mode decides who invoices, not
whether revenue, margin and COGS exist.**

Deleted: `Customer.revenue_mode`, `GET`/`PUT /margin/customers/{id}/revenue-mode`
(`margin_endpoints.py:212-247`), `RevenueService.resolve_revenue_mode`, `CustomerEconomics.revenue_mode`,
and the `_compose` branch.

### 3.2 The workflow the deletion must not remove

A metering-only tenant may legitimately operate either way, and both must survive:

```
cost-tracking only                    cost tracking + tenant-supplied revenue
  operational usage                     operational usage
  → calculated supplier COGS            → calculated supplier COGS
  → revenue unknown                     + tenant supplies external revenue
  → margin unavailable                  → revenue known at the supplied scope
                                        → margin available at that scope
```

The switch was carrying the second workflow badly. Removing it requires making that workflow explicit
rather than implicit.

### 3.3 Tenant-supplied revenue becomes a first-class record

`CustomerRevenueProfile` (`economics/models.py:52-64`) and its endpoints
(`margin_endpoints.py:162-206`) are **replaced**, not extended. Their limitations are structural: one
recurring amount per customer with no per-period rows, no source reference, and — decisively — the
amount is summed into `subscription_revenue_micros` alongside Stripe subscriptions
(`revenue.py:65-68`), so its provenance is destroyed on arrival and no surface can say where a revenue
number came from.

The replacement carries at minimum:

```
ExternalRevenueRecord
  tenant · customer
  amount_micros · currency
  period_start · period_end   (or an effective date, for point-in-time revenue)
  recognition_method          (§4.3)
  source_reference
  created_at
```

**It must never impersonate a Charge.** UBB neither created nor invoiced it; it is externally supplied
revenue admitted for analytics, and every surface that consumes it must be able to say so. Naming and
the write surface's authorization model are owed to #154 and #155 respectively (§19).

### 3.4 The four revenue states, and what "zero" means

| State | Amount | Meaning |
|---|---|---|
| **known** | a number, possibly `0` | a Charge resolved, or the tenant supplied a record. A deliberate `0` is a genuine commercial decision — a free service — and produces a real negative margin against known COGS |
| **waived** | `0` | #147 §7.3: a margin rule resolved but its cost input could not. No customer liability, and a tenant-visible loss |
| **unknown** | `null` | no Charge exists and no record was supplied. **Margin unavailable, never zero** |
| **not_applicable** | — | #148 §4.4 + #151 §8.1: this posting was never going to carry revenue, e.g. a call inside a fixed-price job |

**"Explicitly zero" needs no new state.** #147 §7.1 already covers it: `known` *"including a deliberate
`0` — a free service"*, distinguished from a waived `0` by `pricing_status` and not by the integer. This
document adds no fifth state; it adds a second legitimate *source* of `known`.

---

## 4. The scope rule, and the one axis it exempts

### 4.1 The ruling

**Margin is defined at a bucket only when every revenue component in that bucket is attributable at that
bucket's grain.** Where it is not, the surface reports the cost, reports the revenue it *can* attribute,
names what it could not, and publishes no margin.

Worked, at two grains, for one customer-month with £1,000 of tenant-supplied revenue and £250 of COGS:

```
customer-month grain                    provider grain
  revenue  $1,000  known                  supplier_cogs   gemini $150 · openai $100  known
  cogs       $250  known                  customer_revenue          unavailable_at_requested_grain
  margin     $750  known                  gross_margin              unavailable_at_requested_grain
                                          (context: $1,000 exists at customer-month)
```

Three prohibitions, all load-bearing:

- **Never distribute.** Allocating the $1,000 across providers pro-rata by cost produces a hypothetical,
  not an observation. #151 §12 already declined counterfactual revenue for a different question; the same
  answer holds here.
- **Never bucket as unattributed.** The coarse revenue must not land in the `(unattributed)` row
  alongside genuinely-missing values — that row means *"we do not know which provider"*, and this is
  *"the question does not apply"*. Two different facts, and today's sentinel
  (`queries.py:298-300`, `metering_endpoints.py:624-627`) conflates them.
- **Never silently drop.** The coarse revenue is presented as **context** on the finer chart, so the
  tenant can see that $1,000 exists and understand why no margin is drawn.

### 4.2 This is a fix, not a new capability

The mismatch already ships and nothing labels it. `/margin/summary` (`margin_endpoints.py:52-82`)
includes accrued subscription revenue. `/margin/by-dimension` calls `get_dimensional_margin`, whose
docstring is explicit — *"Usage-only margin (billed - provider)"* (`apps/metering/queries.py:321-323`) —
and silently omits it.

A tenant with a £10k/month subscription and £2k of usage gets **two margin figures for the same period,
differing by £10k, from two links on the same page**, neither of which states its revenue basis. The
scope rule is what makes that impossible to reintroduce.

### 4.3 Time is the sole exception, and it is explicit

Revenue supplied for a period may be **distributed across time within that period**, because the record
*declares its own span*. It never declares a provider, an Event Type or an event — so spreading along
time is interpolation inside a stated boundary, while spreading along any operational axis invents a
boundary the record never asserted. That asymmetry is the whole justification and must be recorded, or a
future reader will reasonably ask why one allocation is honest and the others are not.

```
recognition_method:  point_in_time | straight_line_daily

July revenue $1,000 · 31 days · straight_line_daily
  → ~$32.26/day of recognised revenue, chartable against daily COGS
```

Two views, both offered, always labelled:

- **Recorded** — revenue appears on its recorded or receipt date.
- **Recognised** — period revenue distributed by its configured recognition method, labelled
  *"revenue basis: evenly recognised over month"*.

**Recognition policy is per revenue kind, not one blanket smoothing rule:**

| Revenue kind | Natural recognition |
|---|---|
| Monthly subscription | may recognise evenly through the month |
| Tenant-supplied period revenue | tenant's declared `recognition_method` |
| Fixed Task Charge | on Task delivery |
| Event-priced Charge | on the event / Charge date |

Note this is not new behaviour so much as *newly honest* behaviour: `manual_revenue_for_window`
(`revenue.py:20-37`) and `subscription_nominal_for_window` (`revenue.py:47-63`) already prorate by day.
They do it unlabelled, unconditionally, and with no way to ask for the recorded view — so today
"recognised" is the only behaviour UBB has, and "recorded" is the one that is missing.

---

## 5. What may be grouped by: two kinds, one contract

### 5.1 The ruling

**Exactly two kinds of groupable thing exist, and their difference stays visible to the caller.**

| Kind | Definition | Examples |
|---|---|---|
| **Direct grouping field** | a value materially attached to the posting, or inherited from its Task | `customer`, `task_type`, `event_type`, and the tenant's declared fields — `region`, `environment`, `agent`, `workflow` |
| **Declared semantic rollup** | a controlled mapping from an existing identity to a broader analytical classification | Event Type → **Event Category**; Measurement → **Measurement Concept** |

Both are **analytics-only**. Neither may ever select a Cost Rate or a customer-pricing rule — #145 §5
removed that role and #147 §2 removed Event Category from pricing specifically; this document must not
readmit either through a reporting door.

### 5.2 Why rollups are not just more grouping fields

Requiring tenants to reproduce semantic relationships as ordinary grouping fields is the failure mode.
#145 §6.1 sends operational variants to separate Event Types, and §6.3 hands the consequence here:

```
gemini-flash-standard  ┐
gemini-flash-batch     ├── Event Category ──→  gemini-flash
gemini-flash-negotiated┘
```

The Event Types stay operationally and economically distinct — which is what makes their costing
correct — while the rollup gives one analytical view of combined activity. That **discharges #145 §6.3's
handoff by declared grouping**, exactly as it required, and without reintroducing rate selection from
event attributes.

Measurement Concept works the same way one level down (#145 §4), and carries one restriction: it groups
*measurement records*, not events, so it may appear only on surfaces that have component-level
quantities or component COGS. **It must never duplicate a whole event's cost across every measurement
that event contains.**

### 5.3 One query vocabulary, kinds visible

```
group_by=field:region
group_by=rollup:event_category
group_by=rollup:measurement_concept
```

Retired: `dimensions=`, `tag_key=`, `usage_line_item_group_by=`, and any future per-surface parameter.
Four bespoke doors is how three tag hatches happened.

The namespace is deliberate. A flat, untyped list would hide materially different query and attribution
behaviour behind identical-looking strings — a field is a column and a rollup is a join, with different
cardinality and cost characteristics, and hiding that is how a chart times out in production.

### 5.4 The discovery contract declares capability, not just availability

```
Grouping option
  key · label
  kind: field | rollup
  source grain
  supported surfaces
  supported economic measures
```

This is the load-bearing part. **Being groupable for COGS does not make revenue or margin attributable
at that grain**, and each chart must not independently invent its own answer:

```
field:region
  supports: supplier_cogs · customer_revenue where attributable · gross_margin where both attributable

rollup:event_category
  supports: event_count · supplier_cogs · revenue only where attributable · margin only where scopes match

rollup:measurement_concept
  supports: measurement quantities · component COGS
```

The console, SDK and Code Builder all read this one contract — the same enumerability argument that
carried #145 §2 and §8.3.

### 5.5 Changing a rollup reclassifies history

**v1 rule:** rollup membership is analytical taxonomy. Changing an Event Type's Event Category, or a
Measurement's Measurement Concept, **may reclassify historical charts**. It never alters original events,
COGS, Charges, receipts, or any historical monetary amount.

This is a deliberate departure from ADR-0005's slot-immutability instinct, and the reason it is safe is
precisely that rollups touch no money — the property ADR-0005 invariants 1 and 2 exist to protect. The
UI must state the behaviour at the point of change. If immutable historical classification later becomes
a requirement, rollup membership can be effective-dated or snapshotted as an explicit feature rather
than silently assumed now.

---

## 6. Derive, don't store: closed periods restate, money never moves

### 6.1 The ruling

**Margin is always derived at read time from postings, Charges and revenue records. A closed period's
reported COGS and margin move when its facts resolve; its invoices and Charges do not.**

This settles the question #148 §17 handed here explicitly:

> whether the reporting figures for the closed period restate or stay frozen is not decided here and
> should be, by #152 or #153.

### 6.2 Why freezing is not available

The case is not hypothetical, and today it is permanent. `CustomerCostAccumulator` is a cache over
`UsageEvent` repaired hourly by `reconcile_cost_accumulators` (`apps/subscriptions/tasks.py:49-104`) —
but the repair covers **only the current calendar month and the two before it**, sized for
`Tenant.backfill_window_days`. Beyond that horizon it is frozen and never checked again.

Now compose it with two merged decisions:

- #146 §3.1 resolves a supplier cost long after the fact and **replays it at its original timestamp**.
- #148 §7.3 lets a **remediation complete COGS inside a closed period**.

```
March event, cost unresolvable
August       remediation resolves it, replayed at its March timestamp
             → accumulator is outside the 3-month repair horizon → never moves
             → CustomerEconomics snapshot → never moves
             → /trend and /unprofitable report a March margin UBB knows is wrong, forever
```

A stored margin is a fourth thing that can be wrong, with no way to tell which of the four is right —
the two-sources-that-disagree shape #148 §3.2 refused. And the freeze-at-close alternative requires UBB
to keep publishing a figure it has already established is false.

### 6.3 Caches survive; authorities do not

Caching stays permitted. The rule is that a cache must be **invalidatable by anything that can change
its inputs, at any age**. Today's three-month horizon is what quietly promoted a cache into an
authority, and after #146 and #148 it is a correctness bug rather than a tuning choice.

### 6.4 What `CustomerEconomics` becomes

It survives **only as the alerting state machine**. `MarginService.evaluate_and_emit`
(`economics/services.py:115-167`) needs memory of what it last alerted on, so a
`margin.customer_unprofitable` webhook fires once per transition and a `consecutive_periods` rule can
look back. That is an alerting record, not a margin record, and no reporting surface may read a margin
figure from it. `/margin/unprofitable` and `/margin/threshold` therefore keep their own endpoints (§8.3)
as state-and-workflow surfaces.

---

## 7. What is counted, and what may be compared

### 7.1 Three failure modes wearing one word

"This number cannot be shown" has been used for three unrelated situations, which is why surfaces
disagree about what to do. They separate cleanly:

| Failure | Example | Treatment |
|---|---|---|
| **Not attributable** | revenue at a finer grain than supplied | `unavailable_at_requested_grain`, reason named (§4) |
| **Not addable** | token quantities summed with search quantities | unavailable — enforced by §5.4's capability declaration, needing no new machinery |
| **Addable but not workload** | event counts across differently-granular Event Types | **shown**, with constraints (§7.2) |

### 7.2 Counts survive, renamed and constrained

#149 §3.1 made granularity a tenant declaration: one tenant records one event per provider call, another
one event per minute of the same call. Same work, counts 60× apart. #149 handed this ticket the
consequence — *"charts must aggregate on measurements, never on event counts, unless the unit is held
constant"* — but measurements are not universally addable either, so the instruction cannot be followed
literally.

The resolution: 5 + 3 genuinely is 8 **recorded operations**. It is not 8 units of work.

- The measure is renamed to say what it counts (**recorded operations**; final name → #154).
- **Synthetic charge postings are excluded everywhere**, discharging #139 §5's Category B: a job must not
  count its own invoice as a unit of work (`tasks/services.py:117`), and "events per day"
  (`queries.py:123-129`) must not include them.
- A raw count may never be the **headline or denominator** of a comparison whose grouping does not hold
  Event Type — or its rollup — constant.

---

## 8. One economic analytics query surface

### 8.1 The ruling

Five overlapping endpoints collapse into **one parameterised economic analytics query**:

```
filters · group_by · bucket · measures

measures:  event_count · supplier_cogs · customer_revenue · gross_margin
group_by:  field:customer · field:task_type
bucket:    month
```

**It is an *economic* query, not a posting-grain one.** That distinction is the whole design: the
measures no longer share an origin, so the engine aggregates each from its own canonical fact source and
combines them only where their scopes are compatible.

| Measure | Canonical source |
|---|---|
| `event_count` | operational usage records |
| `supplier_cogs` | supplier-cost postings |
| `customer_revenue` (UBB-created) | canonical Charge postings |
| `customer_revenue` (tenant-supplied) | external revenue records |
| `gross_margin` | revenue − COGS, **only after both are aggregated to a compatible bucket** |

### 8.2 The parity matrix

Every capability that exists today, and where it lands. Nothing is banked without a destination.

| Capability (live) | Where it lives now | After |
|---|---|---|
| Totals: events, billed, provider, margin | `/analytics/usage` (`metering_endpoints.py:554-560`) | measures on the one query |
| Fixed `by_provider` / `by_event_type` / `by_customer` / `by_task_type` blocks | `/analytics/usage:562-589`, unconditional | `group_by=field:…` — four **presets**, not four response keys |
| `by_tag` | `/analytics/usage?tag_key=` (`:591-603`) | **gone** (#145 §8.2) |
| Up to 6 ad-hoc breakdowns in one response | `?dimensions=` (`:605-628`, capped at `:607`) | multi-axis `group_by` on the one query |
| Day/hour bucketing | `/analytics/usage/timeseries` (`:644-670`) | `bucket=day\|hour` on the one query |
| Single-axis group_by + bucket | `timeseries?group_by=` | same query, both axes |
| Stop-context filters (`past_limit`, `stop_scope`, `episode_seq`) | `/analytics/usage:527` | filters on the one query, and Spend Controls (§10) |
| Task / subtask filter, `include_subtasks` | `/analytics/usage:526` | filter on the one query |
| Usage-only margin by one axis | `/margin/by-dimension` + `tag_key` (`margin_endpoints.py:85-112`) | **duplicate** — same rows, same maths, different endpoint, different revenue basis |
| Daily provider / billed / markup + totals | `/billing/analytics/revenue` (`billing_endpoints.py:486-497` → `queries.py:96-147`) | **duplicate** of timeseries, tenant-wide |
| Per-customer margin list | `/margin/customers` (`margin_endpoints.py:289-316`) | `group_by=field:customer` + revenue measures |
| One customer's margin | `/margin/customers/{id}` (`:277-286`) | same query, filtered |
| Margin trend over N periods | `/margin/customers/{id}/trend` (`:260-274`) | `bucket=month`; stops reading the snapshot (§6.4) |
| Customer usage summary (per Event Type) | `me_endpoints.py:357-362` → `queries.py:177-221` | same query, customer-scoped |
| p95 / distribution per kind of work | `/analytics/tasks` (`metering_endpoints.py:333-358`) | **keeps its own endpoint** — one observation per Task, not per posting (§11) |
| Business rollup with per-seat detail | `/margin/business/{id}` (`:250-257`) | **keeps its own endpoint** — a tree, not a group-by table |
| Unprofitable list, thresholds | `/margin/unprofitable`, `/threshold` (`:115-159`) | **keep** — stored alerting state and workflow (§6.4) |
| Past-limit episodes | `/customers/{id}/past-limit-report` | **keeps its own endpoint**, reshaped (§10) |

**Three rows are the finding.** `/margin/by-dimension` and `/billing/analytics/revenue` are already
reimplementations of `/analytics/usage` and `/analytics/usage/timeseries`, with different null handling
and — in by-dimension's case — a silently different revenue basis. That is *how* the same period gets
two margin figures.

### 8.3 What stays separate, and why

One surface does not mean one universal row model. These answer structurally different questions and
keep their own contracts:

- **Task COGS distribution** — one observation per Task, including percentiles (§11).
- **Business / seat hierarchy** — a tree, not a group-by table.
- **Spend Control breaches** — chronological enforcement episodes (§10).
- **Spend Control utilisation** — control-specific analytics (§10).
- **Unprofitable alerts and thresholds** — stored alerting state and workflow.

### 8.4 Named reports become presets, not contracts

The console keeps its familiar experiences — *Revenue overview*, *Margin by customer*, *COGS by
provider*, *Monthly margin trend* — as **saved query presets over the one contract**:

```
"COGS by provider"        measures=supplier_cogs
                          group_by=field:provider

"Monthly customer margin" measures=supplier_cogs,customer_revenue,gross_margin
                          group_by=field:customer
                          bucket=month
```

A simple tenant experience without maintaining five backend definitions of revenue and margin.

### 8.5 The response carries a state per measure

Because unknown, unavailable, inapplicable and zero are now deliberately different facts, each requested
measure carries its own status:

```
supplier_cogs:
  amount: 4200000
  status: incomplete
  unresolved_event_count: 1
customer_revenue:
  amount: 5000000
  status: known
gross_margin:
  amount: null
  status: incomplete
```

`known` · `incomplete` · `unavailable_at_requested_grain` · `not_applicable`.

**No query may coerce an unresolved value to zero, and no query may compute a confident margin from an
incomplete cost total.** This is #151 §10.3's rule made structural rather than advisory.

### 8.6 A controlled language, not SQL over HTTP

The query surface **rejects invalid combinations** rather than returning subtly misleading data,
validating the request against §5.4's discovery contract — supported measures, supported surfaces,
cardinality constraints. A caveat a client may ignore is a caveat that will be ignored, and that is how
the tag hatches survived ADR-0005 in the first place.

---

## 9. Invoice lines: one vocabulary, money-only lines

### 9.1 The customer-facing hatch

`usage_line_item_group_by` (`apps/billing/invoicing/models.py:148`) accepts `"tag:<key>"` or `"dim1"` and
drives the labels on postpaid invoice usage lines (`apps/metering/queries.py:424-455`). #145 §8.2 named
it the sharpest of the three tag surfaces — *"an unbounded free-text key driving invoice line labels is
how a 5,000-line invoice happens"* — and it is the only one a paying customer reads.

### 9.2 The ruling

**One vocabulary, and a line exists only where customer money exists.**

- Invoice grouping accepts `field:` and `rollup:` from the same discovery contract as analytics
  (§5.3). **Rollups are actively preferred** — they produce fewer, more meaningful lines.
- A **fixed-price job is one line**, labelled by the job. Its 400 constituent calls produce **none**:
  they are `not_applicable`, and #148 §9.3's warning about rendering them as zero-revenue is worse on an
  invoice than on a dashboard — it is 400 lines of £0.00 sent to a customer.
- A **waived** event produces **no invoice line** (there is no liability) but must appear on the tenant's
  exposure report, which #147 §7.3 already requires be highly visible.
- Cardinality gets a real guard: UBB warns at **configuration time** when the chosen axis could exceed a
  line budget. A declared cap of 100 distinct values still permits a 100-line invoice.

### 9.3 The rule underneath

**A customer's invoice depends on revenue state only. Cost state never delays, blocks or alters a
customer-facing line.**

The apparent exception — a `margin_over_cost` rule whose cost cannot resolve — is not one: #147 §7.3
already converts that into a *revenue* state (`waived`) before it reaches an invoice. So the rule holds
without exception, and an unresolved supplier cost can never hold up a customer's bill.

---

## 10. Spend Controls: two contracts in one product area

### 10.1 The ruling

One product area, two report contracts, distinct datasets and response schemas:

```
Spend Controls
  ├── Stops and breaches        chronological enforcement episodes
  └── Utilisation and headroom  continuous and aggregate control analytics
```

They may share filters — customer, Task Type, period, control family — but they answer different
questions and must not share one stretched row shape.

### 10.2 Stops and breaches

Episodic. Each row is a control that **actually fired and had an enforcement consequence**.

```
family: task_ceiling                    family: customer_spend_pool
  Task: research-report-123               Customer: Acme · Period: July
  Control: supplier COGS ceiling          Pool: £100
  Ceiling: £5.00                          Charge that crossed it: £4.00
  Known COGS when crossed: £5.08          Period spend after Charge: £102
  Final COGS: £5.31                       Outcome: active Tasks signalled to stop
  Triggered by: usage event …                      new Task starts blocked
  Outcome: Task stopped
```

Families: `task_ceiling` · `customer_spend_pool` · `wallet_policy`.

- **The Pool is new** and is what today's report is missing entirely. #150 §7.1 made Pool enforcement
  payment-mode independent and blocking, so a Pool crossing now stops work and produces exactly the
  "spend past a stop" this report exists to itemise. **A Pool row is explained through its canonical
  Charge and that Charge's posting**, never through an arbitrary usage event — the money path #151 §6
  pinned.
- **Wallet-floor episodes stay.** They are genuine affordability interventions and today's report already
  reconstructs them from the `stop.fired` / `stop.cleared` pair plus the durable ledger row
  (`api/v1/past_limit.py:88-116`).
- **An indeterminate ceiling is never a breach.** #146 §5 and #150 §4.2 keep enforcement silent when a
  cost cannot be evaluated, and it must not appear here merely because unresolved COGS existed.
- **A Task appears only if its known lower bound independently reached the ceiling** — #150 §4.2's
  known-over-always-fires rule, which makes the report a set of true statements rather than suspicions.

### 10.3 Utilisation and headroom

Analytical. Describes how controls were used **even when nothing went wrong**.

```
per Task                              aggregate
  Task COGS: £3.20                      Average final Task utilisation: 61%
  Task ceiling: £5.00                   Tasks reaching their ceiling: 3.2%
  Final utilisation: 64%                Tasks with indeterminate evaluation: 0.7%
  Unused headroom: £1.80                Average unused headroom: £1.45
  Ceiling reached: no
  Cost state: complete
```

- **Averages are computed per Task and then aggregated**, never over event acknowledgements — #150 §9.3's
  rule, and without it Tasks that emit many events are weighted disproportionately.
- Pool utilisation carries period spend, configured amount, percentage used, remaining headroom, highest
  threshold reached, and whether blocking occurred.
- The **indeterminate count or rate** lives here. *"My ceiling could not evaluate 400 times last month"*
  is urgent tenant information that produces no episode by construction, so without this report it is
  invisible.
- `limit_hit_count` **moves here** from `/analytics/tasks` (`apps/platform/tasks/queries.py:86-88`),
  where it is a third independent implementation of a ceiling comparison (§17.7).

### 10.4 What belongs to neither

Expiry and admission control answer operational questions, not spend questions:

- **Task expiry** → lifecycle and worker-health reporting. #140 §11 and #149 §5.4 already forbid counting
  `expired` as a failure; counting it as an overrun would be worse.
- **Request throttle** (#150 §13.1's renamed admission control) → API admission and capacity reporting.
  Nothing was overspent; work was never admitted.

### 10.5 Honest unknowns, before either ships

Where a contributing amount is unresolved:

```
Known COGS: at least £4.20
Unresolved events: 1
State: incomplete
```

Never coerce NULL to zero. Never compute a confident utilisation percentage. Never describe a ceiling as
safely below its threshold on incomplete data. This is #151 §10's *"at least £4.20"* presentation applied
to spend control, and §17.6 records why it is urgent.

---

## 11. The COGS distribution per kind of work

### 11.1 What it is for

#151 §12 declined to manufacture counterfactual event prices for fixed-price work and named the
replacement, handing it here: *"Is £5 the right price for this kind of work?"* becomes **a distribution
of COGS per kind of work**.

It answers one question — *what does this kind of Task tend to cost us?* It does **not** answer *what
should we charge?* or *what would event pricing have billed?*, and it must not become a price
recommendation engine.

### 11.2 The problem a distribution has that a sum does not

A tenant reads p95 = £4.80 and concludes £5 is a sound price. Meanwhile 0.7% of runs contain an event
whose supplier cost could not be resolved — and those are not a random 0.7%. An unusual, expensive,
badly-mapped call is exactly the kind that fails to cost.

For a *sum*, #151 §10 solved this: "at least £4.20". For a *percentile*, dropping the unknowns does not
give a lower bound — it gives a number that could be wrong in either direction, computed over the subset
that behaved, and it will be used to set a price. Today `task_rollup_by_type`
(`apps/platform/tasks/queries.py:85`) computes p95 over whatever happens to be in the column.

### 11.3 The ruling: distribute over known lower bounds

Each Task contributes the supplier COGS **currently known** for it:

```
Task A                          Task B
  known COGS: £2.00               known COGS: £4.80
  unresolved: none                unresolved events: 1
  lower bound: £2.00              lower bound: £4.80
                                  final COGS: unknown, but cannot be lower
```

Every Task stays in the sample, nothing is guessed, and no unresolved amount becomes zero. Because
quantiles preserve ordering, **every percentile of the floors is itself an honest floor of the true
percentile**, and the number can only ever move up as costs resolve.

Presentation depends on completeness:

```
complete population                    incomplete population
  Median Task COGS: £2.70                Known-cost p95: £4.80
  p95 Task COGS:    £4.80                Interpretation: lower bound
  Cost completeness: 100%                Tasks with incomplete COGS: 0.7%
  (exact)
```

The UI states it plainly — *"95th percentile of currently known Task COGS: £4.80. 0.7% of Tasks contain
unresolved supplier cost, so the final p95 may be higher"* — and never *"£5 is definitely a safe fixed
price"*.

**One distribution, not two.** A resolved-only series beside a lower-bound series gives tenants two
competing numbers without resolving which should guide them.

The tenant compares the chosen fixed Task price, the known-cost distribution, and the cost completeness,
and makes their own commercial decision.

---

## 12. Retention: two clocks, both published

### 12.1 Why one clock does not work

The map has published a six-year receipt floor (#148 §10.1, §16), and §6.1 has just promised that a
closed period's figures restate whenever its facts resolve — **at any age**. That promise is only true
while the rows are still there.

Against that, #148 §10.4 and #165 both lean toward pruning measurements on a far shorter clock: they are
bulky, high-volume and carry no dispute value. #148 §17 records that nobody has multiplied receipt size
by realistic event volume.

The two pressures are reconcilable only if the money and the bulk are on different clocks — which is
exactly the seam #165 exists to cut, now load-bearing for a third reason.

### 12.2 The ruling

**One platform-wide economic horizon and one platform-wide measurement horizon. Both published. No
per-tenant retention policies, no per-measurement clocks, no archival tiers, no per-chart horizons.**

| Clock | Covers | Horizon |
|---|---|---|
| **Economic** | Charges · economic postings · tenant-supplied revenue records · immutable pricing and costing receipts · costing and pricing statuses · applied monetary values · currency · customer/Task/Event Type attribution · Cost Rate provenance | **six years** — the horizon already promised for receipts |
| **Detailed measurement** | raw measurement records · measurement quantities · component drill-down · Measurement Concept rollups · fine-grained quantity time series | one shorter platform horizon, explicitly documented and returned by the API |

After the shorter horizon, UBB still answers *"what was Acme's COGS in July 2027?"*, *"what revenue and
margin did this Task produce?"*, *"what did this historical event cost?"* — and no longer answers *"how
many input tokens were used that month?"* or *"break six-year-old COGS down by Measurement Concept."*
That is an honest and useful degradation boundary.

The shorter horizon's **number is not set here** (§19). It should start conservative and be adjusted once
real volume is known, but it must be public and mechanically enforced.

### 12.3 Never truncate silently

The query surface exposes its own horizons per measure and grouping capability:

```
economic_data_available_from
measurement_data_available_from

measure: input_tokens
  status: unavailable_outside_retention_horizon
  available_from: 2024-08-01
```

It must not return a shorter series without saying so, and must not present partial measurement totals as
totals for the requested period. Same honesty rule as every other unavailable number in this document.

### 12.4 The obligation this places on the receipt — extending #148

**A record cannot promise six-year economic restatement while deleting the only inputs capable of
producing that economic result.** Two consequences, and the first is a new content requirement on #148's
receipt:

1. **The receipt must retain enough snapshotted input to explain its amount after detailed measurement
   rows expire** — for calculated COGS, the quantities, rates, denominators and resulting components
   actually used. #148 §4 already made the receipt carry *values, not pointers*; this makes measurement
   quantities specifically non-optional, and adds a second reason for it that #148 did not have.
2. **Unresolved records must retain their remediation inputs.** Either the immutable unresolved receipt
   carries the original measurements needed to resolve the cost later, or the required source payload is
   **exempt from measurement pruning until the event resolves or reaches the economic horizon**.
   Otherwise #146's remediation and #148 §7.3's completion silently stop working at the measurement
   horizon — and would do so quietly, on exactly the records that most need fixing.

---

## 13. The clean operational reset

### 13.1 Migration is not available, and the reason is a merged decision

The ticket says the data *can* be migrated because there are no live integrators. It cannot, for a reason
stronger than effort.

Existing `UsageEvent` rows carry free-text `usage_metrics` keys (`apps/metering/usage/models.py:44`) that
were never declared against an Event Type. #145 §2.1 requires measurement keys to validate against
declarations, and §2.4 explicitly refuses auto-registration — *"a typo becomes permanent billing
vocabulary"*. Confronted with:

```
input_token
input_tokens
in_tokens
```

no automatic translation can decide whether those are equivalent, erroneous or intentionally distinct.
That leaves two options, both bad: auto-register every observed key (forbidden), or carry old rows
forward permanently `unresolved` and ungroupable — a two-vocabulary branch in every query, forever, to
serve pre-launch dev and demo data.

Old rows were created under materially different rules on both sides:

| Old model | New model |
|---|---|
| free-text Event Types | registered Event Types |
| undeclared measurement keys | declared measurements |
| mutable or incomplete pricing provenance | immutable, schema-versioned receipts |
| revenue zero when unknown | explicit revenue states |
| — | explicit costing methods; versioned Cost Rates and Pricing Books |

Automatically translating them would imply a confidence the source data does not support.

### 13.2 What is removed at cutover

Operational and economic records created under the old semantics:

- usage and economic postings
- Charges and receipts
- Tasks and steps
- wallet deductions and derived ledger state
- period accumulators and live counters
- analytics snapshots and cached totals
- remediation and reconciliation state tied to those rows

### 13.3 What may survive, and under what test

Configuration may survive **only where it has an unambiguous representation in the new model** — tenant
configuration, customer configuration, Plans, Providers, Event Types, declared measurements, Cost Rates,
Pricing Books, customer overrides, Task Types.

"Keep configuration" is not "copy every row". The rule:

```
maps cleanly and validates              → migrate it
requires inference or obsolete meaning  → recreate or discard it
```

Event Types and measurements in particular should be **explicitly re-declared under the new contracts**
rather than inferred from historical traffic.

### 13.4 The break this uses

This is the **same** exercise of #137 constraint 1 that #148 §11 already invoked, executed at #155's
cutover — not a second break. #148 §11.3 is precise that the constraint *"expires the moment the first
integrator lands"*; it has not, and this document must not be read as licensing another one afterwards.

### 13.5 Before and after

Take a **one-time database snapshot or export for engineering rollback and forensic reference**. That
backup is explicitly **not a supported product data source** and must not influence the new application
model.

The cutover regenerates all derived state from zero, with tests confirming:

1. no old posting contributes to a balance or a report
2. no undeclared measurement survives
3. no legacy pricing provenance is read
4. every new event validates against its Event Type
5. every new monetary record uses the new receipt shape

**No legacy operational data and no dual-read behaviour enters the new system.** Specifically not built:
legacy query branches, two-vocabulary analytics, unresolved historical placeholders, or a permanent
archive reporting surface.

---

## 14. Names

#154 locks these; this document coins or retires them.

| Concept | Today | Proposed | Rule |
|---|---|---|---|
| The one query surface | five endpoints | **economic analytics query** | it is not posting-grain; the noun must not imply it (§8.1) |
| The measures | `total_billed_cost_micros`, `total_provider_cost_micros` | **`supplier_cogs`** · **`customer_revenue`** · **`gross_margin`** · **`event_count`** | say which side of the trade, not which column |
| Measure state | — | `known` · `incomplete` · `unavailable_at_requested_grain` · `not_applicable` | four facts that were one integer (§8.5) |
| Group-by axis kinds | `dimensions`, `tag_key`, `usage_line_item_group_by` | **`field:`** / **`rollup:`** | kind stays visible (§5.3) |
| Count of operations | `event_count` | **recorded operations** | it counts records, not work (§7.2) |
| Tenant-supplied revenue | `CustomerRevenueProfile` | a record of externally-supplied revenue — **must not read as a Charge** | UBB neither created nor invoiced it (§3.3) |
| Revenue recognition | — | `recognition_method ∈ {point_in_time, straight_line_daily}` | (§4.3) |
| Spend Control reports | `past-limit-report` | **stops and breaches** · **utilisation and headroom** | (§10) |
| Control families | `stop_scope`, `family`, `limit` | `task_ceiling` · `customer_spend_pool` · `wallet_policy` | reconcile with #150's own naming debt |
| Retention horizons | — | `economic_data_available_from` · `measurement_data_available_from` | (§12.3) |

**Two retirements owed:**

- **`usage_markup_margin_micros`** (`metering_endpoints.py:634`) and `markup_micros`
  (`queries.py:301`, `:264`). #147 §9.1 retained "markup" deliberately — *"it is the word Stripe's
  competing product uses"* — and forbade it drifting into "margin", which now names only the displayed
  derived figure. This field fuses both words into one identifier and is neither: it is
  `billed − provider` over a bucket, which after §2 is `gross_margin`.
- **`total_usage_cost_micros`** — #139 §6 already flagged that it no longer holds only usage. Compounded
  here: after §8 it is neither only usage nor only cost.

---

## 15. Answers to the ticket's six questions

**1. What can be grouped by, once the vocabulary changes? Do the three `tag_key` exceptions close or get
blessed?**
**Closed — by #145, before this ticket was reached** (§1.2). What this document decides is what replaces
them: **two kinds of groupable thing**, a field on the posting and a declared rollup of one, reached
through one namespaced parameter and one discovery contract that declares each axis's supported measures
as well as its availability (§5). The three surfaces' destinations: `?tag_key=` and `by_tag` are deleted
with the collapse into the one query (§8.2); `usage_line_item_group_by` accepts `field:`/`rollup:` with
rollups preferred (§9).

**2. Does margin still mean `billed − provider` when a fixed price per task exists?**
It still means revenue minus cost — but **only as a bucket-level subtraction, never a row-level one**
(§2). Per-event margin was an artefact of metered pricing making both sides accidentally per-event; it
ceases to be a concept for metered work too. And it is published only where every revenue component is
attributable at the bucket's grain (§4).

**3. What is the reporting unit for fixed-price work — the task, or its events?**
**The binary dissolves.** Cost is always reported per event; revenue is always reported per Charge, which
for fixed-price work is per delivered job. Neither is the universal unit, and the pair is what makes §4's
scope rule necessary rather than fussy.

**4. How do historical rows survive a vocabulary change?**
**They do not, and cannot** (§13). Old rows carry undeclared measurement keys, and #145 §2.4 forbids
auto-registering them — so migration would require either a forbidden auto-registration or a permanent
legacy class of row. The cutover is a clean operational reset: operational and economic history removed,
configuration kept only where it validates, ambiguous configuration explicitly re-declared, with an
engineering-only backup and five cutover assertions.

**5. Which surfaces are contract-breaking to change, and does that matter given the clean break?**
**Effectively all of them, and no** (§8.2). Five endpoints are retired outright, two endpoint pairs are
deleted (`/revenue-mode`, `/customers/{id}/revenue`), the past-limit report is reshaped into two
contracts, and every remaining response gains a per-measure status. All of it lands inside the one break;
#155 owns the OpenAPI regen and the deliberate run of the oasdiff breaking gate.

**6. Does the past-limit report change if limits gain a second denomination (#150)?**
**#150 declined the second denomination** (§1.3) — ceilings stay COGS-only in v1. The report changes for
a different reason: one limit became four families and it knows two of them. It becomes **two contracts**
in one Spend Controls area — episodic stops and breaches, gaining `customer_spend_pool` as a family
explained through its canonical Charge, and a separate utilisation and headroom report carrying #150's
peak, headroom, reached flag and the indeterminate rate (§10).

---

## 16. What this narrows, extends and answers in merged decisions

| Decision | Effect |
|---|---|
| **#148 §17** | **Answered.** Closed-period reporting figures **restate**; money never moves (§6.1) |
| **#148 §4** | **Extended.** The receipt gains a content obligation: it must outlive the measurements it explains, retaining quantities, rates, denominators and components sufficient to explain *and remediate* an amount after measurement detail is pruned (§12.4) |
| **#148 §4.4 / #151 §8.1** | **Consumed.** `not_applicable` becomes a first-class measure state on every surface, distinct from zero and from null (§8.5) |
| **#147 §7** | **Confirmed and extended.** `known` already covered a deliberate zero; this adds a second legitimate source of `known` — the tenant-supplied revenue record (§3.3, §3.4) |
| **#147 §13** | **Discharged.** `queries.py:301`'s `or 0` and its eight siblings are named with evidence and removed by §8.5's structural rule (§17.5) |
| **#146 §4, §7.4 / #151 §10.2-10.3** | **Consumed.** No aggregate sums a NULL as zero; every COGS figure can say which derivation produced it, via the measure state and its `cost_sources` drill-down |
| **#145 §6.3** | **Repaired.** Reporting fragmentation from operational-variant Event Types is reassembled by the Event Category rollup — *"by declared grouping, never by reintroducing rate selection"*, exactly as required (§5.2) |
| **#145 §8.2** | **Completed.** The three tag surfaces get destinations (§8.2, §9) |
| **#142 §4.3** | **Implemented as a measure state.** Foreign-currency subscriptions are excluded and **counted** — `not_applicable` with a count, never zeroed, never silently omitted (§17.4) |
| **#141 §1.1** | **Enforced.** Mode decides who invoices, not whether revenue exists — the switch that violated it is deleted (§3.1) |
| **#141's handoff** | **Satisfied.** *"Period-level margin for metering-only tenants is a first-class reporting shape, not a degraded per-event one"* — §3.3 and §4 make it exactly that |
| **#139 §5 Category B** | **Discharged.** Counts exclude charge postings; dimensional margin stops being per-row; the customer usage summary stops manufacturing a metric row with no units (§7.2, §2.3) |
| **#150 §9** | **Housed.** Peak utilisation, headroom at completion and the ceiling-reached flag land in a named utilisation contract, with the per-Task-then-average rule preserved (§10.3) |
| **#150 §6.4** | **Honoured.** No dimension-scoped cap affordance is built |
| **#149 §9's handoff** | **Answered, with a correction.** Charts cannot simply "aggregate on measurements" — measurements are not addable across units either. Three failure modes get three answers (§7.1) |
| **ADR-0005 consequence 1** | **Retired.** *"'never grouped' was never quite true"* stops being true of anything |
| **ADR-0005's under-counting warning** | **Made moot** by §13 rather than mitigated forever |

---

## 17. What this fixes that was already broken

Defects on `main`, not design choices. Each needs a test when the work lands.

1. **Every metering-only tenant reads exactly 0.00% margin.** `revenue_mode` resolves to `metered_only`
   for `billing_mode == "meter_only"` (`revenue.py:39-44`), which zeroes usage revenue
   (`economics/services.py:8`), and the percentage guard prints `0` when revenue is `0`
   (`services.py:11-12`, `margin_endpoints.py:80`, `:315`). Cost £2,400, revenue £0, margin −£2,400,
   **margin 0.00%** — and 0% is what you print for break-even. Three numbers, three kinds of wrong.
2. **Two margin figures for one period, from two links on the same page.** `/margin/summary`
   (`margin_endpoints.py:52-82`) includes accrued subscription revenue; `/margin/by-dimension` →
   `get_dimensional_margin` (`queries.py:321-323`) is usage-only and silently omits it. Neither states its
   revenue basis (§4.2).
3. **The accumulator's repair horizon makes old periods permanently wrong.**
   `reconcile_cost_accumulators` covers the current month and two prior (`apps/subscriptions/tasks.py:49-104`).
   #146's replay-at-original-timestamp and #148 §7.3's remediation both write outside it, and the
   `CustomerEconomics` snapshot never revisits. A tuning choice becomes a correctness bug (§6.2).
4. **Foreign-currency subscriptions are summed straight into margin revenue.**
   `subscription_nominal_for_window` (`revenue.py:47-63`) aggregates `StripeSubscription.amount_micros`
   with **no currency filter**, while the model carries `currency` (`apps/subscriptions/models.py:29`). A
   EUR subscription's number is added to a USD margin. #142 §4.3 requires it be **excluded and counted**;
   #145 §7 makes USD-only the rule while keeping the Stripe mirror legitimately foreign.
5. **`or 0` coalescing across the read contract.** `apps/metering/queries.py:70-71`, `:120-121`,
   `:136-140`, `:212-213`, `:236-238`, `:256`, `:301`, `:339-341`, `:421`, `:453-454`. Correct while both
   money columns are non-nullable; wrong on the day #146 nulls `provider_cost_micros` and #147 nulls
   `billed_cost_micros`. #147 §13 and #150 §7.6 named the class; this is the full inventory for the
   analytics rail.
6. **The past-limit report will 500, not merely mislead.** `api/v1/past_limit.py:131-134` sums
   `billed_cost_micros` and `provider_cost_micros` with no null handling. The moment either goes nullable
   this is a `TypeError` inside a report endpoint. Loud is better than wrong, but neither is shippable.
7. **A third independent implementation of the ceiling comparison.** `limit_hit_count` recomputes
   `total_provider_cost_micros >= provider_cost_limit_micros` at read time
   (`apps/platform/tasks/queries.py:86-88`), alongside the ingest check and the patrol that #150 §17
   already found disagreeing on `>` versus `>=`. Three implementations, two known to differ.
8. **p95 is computed over whatever resolved.** `task_rollup_by_type` (`apps/platform/tasks/queries.py:85`)
   percentiles the column as it stands, so unresolved-cost Tasks — disproportionately the unusual and
   expensive ones — silently leave the sample that sets a price (§11.2).
9. **Two grouping semantics on one column.** `get_customer_billed_breakdown` collapses a missing key,
   NULL, JSON-null and empty string into `"(other)"` for invoice labels, while the analytics contract
   keeps `""` a distinct dimension — documented in the docstring itself
   (`queries.py:424-435`) and therefore known, not accidental. One column, two meanings, depending on who
   is asking.
10. **`Task.event_count` counts a job's own invoice as work** (`tasks/services.py:117`), as does the
    tenant period `event_count` that `reconcile_period` recomputes and overwrites. Flagged by #139 §5 and
    unfixed (§7.2).

---

## 18. Constraints this imposes on other tickets

- **#152 (task dashboard)** — the boundary is **contracts here, rendering there**. This document
  specifies the query surface, the four measure states, the grouping and discovery contract, the two Spend
  Control report shapes, the COGS distribution and the retention horizons. #152 decides how a task
  dashboard renders them, and inherits the rule that **it may not invent a number this contract cannot
  express**. Its existing obligations survive unchanged: render four pricing statuses distinctly, never
  show `indeterminate` as under-limit, never present a period-level margin as if it were per-task.
- **#148** — gains a receipt-content obligation (§12.4): the receipt must be sufficient to explain and
  remediate after measurement pruning. Its §17 open question on closed-period restatement is answered here
  and can be struck.
- **#150** — its three utilisation shapes have a named home (§10.3); `limit_hit_count` moves into it; its
  `provider_cost_limit_micros` naming debt is compounded by the family vocabulary in §14.
- **#151** — `charging_summary` remains derived and display-only; §8.5's measure state is where its
  *"which derivation produced this figure"* requirement lands structurally rather than per-surface.
- **#154 (vocabulary lock)** — eleven names owed (§14), plus two retirements: `usage_markup_margin_micros`
  / `markup_micros`, and `total_usage_cost_micros`. Also owed: whether "past-limit report" survives as a
  phrase at all now that it is two contracts, and the noun for the externally-supplied revenue record —
  which must not read as a Charge.
- **#155 (migration and cutover)** — owes the largest single item in this document: §13's clean
  operational reset, its config-validation rule, the engineering-only backup, and the five cutover
  assertions. Plus the OpenAPI regen and a deliberate run of the oasdiff breaking gate for five retired
  endpoints, two deleted endpoint pairs and one reshaped report. Also owes the write surface and
  authorization model for the externally-supplied revenue record.
- **#156 / #157 (Code Builder)** — the generator reads §5.4's discovery contract for grouping axes and
  their supported measures. Generated reporting code must carry the measure states rather than
  `or 0`-ing them, since the states are the whole point.
- **#165 (splitting the measurement record from the economic posting)** — **strengthened again, from a
  fourth direction.** §12's two clocks require the money and the bulk to be separable by retention;
  §5.4's component-COGS grouping needs a component-grain row that neither current record provides
  (§19). #148 argued the split on retention economics; this makes it a precondition of a published
  promise rather than an optimisation.
- **#137 (the map)** — constraint 1 is exercised here at the same cutover as #148 §11, not separately
  (§13.4).

---

## 19. Residue, flagged not buried

- **Component-grain COGS has no home.** Grouping COGS by Measurement Concept (§5.4) requires
  per-measurement cost lines to sum. #148 put those values inside the receipt, and querying a JSON receipt
  per event to draw a chart does not scale. That implies a **component-grain row** — a third grain that
  neither #148's receipt nor #165's posting/measurement split currently owns. Whoever implements §5.4
  must resolve this before the Measurement Concept axis can ship, or the axis ships against the receipt
  and is quietly unusable at volume.
- **The measurement retention horizon has no number** (§12.2). "Conservative, then adjusted once real
  volume is known" is a policy, not a value, and it must be public before it is enforced. The same
  unmeasured-size problem #148 §17 flagged for receipts blocks picking it honestly.
- **Where query presets live is unspecified** (§8.4). Whether they are tenant-owned rows, shipped
  defaults, or both — and whether a tenant may save their own — decides whether this is a console feature
  or an API concept. Nobody has said.
- **The externally-supplied revenue record's authorization is unstated.** It writes numbers that appear in
  margin reporting. `role_floor(ADMIN)` is the obvious guess and a guess is not a decision — the same gap
  #148 §17 recorded for remediation, now present in a second place. This strengthens its point that the
  three unbuilt recovery surfaces should have one owner; make it four.
- **Rollups and the business/seat tree have not been reconciled.** `/margin/business/{id}` composes
  per-seat margin (`economics/services.py:44-60`); nothing says whether a rollup axis is available inside
  that composition or only alongside it.
- **Retiring `CustomerRevenueProfile` loses pro-rata mid-period start and end dates.** Its
  `effective_from` / `effective_to` semantics (`revenue.py:20-37`) express "this recurring revenue began
  on the 14th". The replacement's per-period rows can express it by construction, but only if the tenant
  enters the partial period correctly — which is a data-entry burden the profile absorbed automatically.
  Worth a UI affordance; not worth keeping two records for.
- **`REPORT_WINDOW_MAX_DAYS = 366` is unexamined against the six-year promise** (`core/time_windows.py:15`).
  A tenant promised six years of economic history can request at most 366 days per call, and no pagination
  or export exists above that bound. #148 §17 raised the same gap for receipts — *"someone will want to
  export a period's receipts"* — and it is now true of every measure in this document.
- **The two-clock model assumes measurement pruning is safe for closed-but-unremediated records.** §12.4
  states the exemption; nobody has designed the mechanism that tracks which payloads are still exempt, and
  it is the kind of bookkeeping that silently stops working.
