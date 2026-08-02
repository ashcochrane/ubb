# Charging modes — three declarations at three levels, and no field that names them all

**Resolves:** [#151](https://github.com/ashcochrane/ubb/issues/151) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-02
**Decided against:** `main` @ `d614f3e`
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — Event Type owns
costability, not cost.
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — a fixed price replaces
metered revenue for one delivered job, pinned at start; the Charge is canonical and projects 1:1 onto
one marked posting; a fixed price on a step is refused; §10 parked the counterfactual-price question
here.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — a subtask **is** a Task row; two
containment levels; the declared kind of work is a pinned field.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — **mode decides who invoices,
not whether revenue, margin or COGS exists**; unknown revenue ≠ zero; §8 handed the mode vocabulary
here.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — only declared measurements may
move money; operational variants are separate Event Types.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — a supplier-reported cost is a
second derivation of the one COGS number, declared per Event Type; preserve, flag, remediate; caller
-supplied *billed* cost deleted; §14 handed the COGS-derivation reporting rule here.
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — one rule resolves per event
declaring one of two methods; the Pricing Book is the only home; overrides replace; `Task.pricing_mode`
introduced; §14 handed **three** residues here — override-may-change-method, subtask interaction, and
`Plan` with no book.
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the receipt is authoritative and carries
values not pointers; four pricing statuses including `not_applicable`; §14 handed the fixed-price
`not_applicable` rule and the revenue-pinned/cost-floating asymmetry here.
`docs/plans/2026-07-31-streaming-and-long-running-calls-decision.md` (#149) — one event is one
declared provider operation; granularity is declared; §11 asked for an explicit sentence on a finer
unit under a fixed-price task.
`docs/plans/2026-08-01-spend-limits-decision.md` (#150) — the one rule is a **recording** promise;
known-over always fires; §17 handed the Pool's fixed-price limitation and the one-money-path pin here.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 through #150: #154 is the single naming pass, and
this document coins two enum values, forces one rename and retires one phrase (§13). The ADR is owed
*after* #154 and should cite every decision document in the map.

---

## The decision in one paragraph

**"Charging mode" is not one thing, and no field should ever claim to be it.** The working model's
three modes are a category error: they merge one *cost-side* declaration, one *price-side* declaration
and one *scope* declaration into a single enum, and the middle one — "tenant-supplied provider cost
with markup" — is not a mode at all but the ordinary combination of a reported cost with a margin rule,
which #146 already settled. What actually exists is **three independent declarations at three levels,
each already decided and each declared rather than inferred**: how supplier COGS is obtained
(`EventType.costing_method`), how one event's customer price is determined
(`ResolvedPricingRule.pricing_method`), and whether event-level revenue arises at all
(`Task.pricing_mode`). A fourth declaration — the tenant's own posture — never charges anything but
**decides what an absence means** at every level: for a metering-only tenant a missing price is the
expected end of the pipeline, and for a full-billing tenant it is either an alert or a refusal
depending on whether the money has already been spent. That asymmetry is the spine: a missing *event*
price records and alerts, because the call already happened; a missing *job* price **refuses the
start**, because nothing has been spent yet and #150's one rule constrains recording, never admission.
Steps get no say — a step and a job are literally the same table row, so there is **one immutable
`pricing_mode` column**, resolved from the kind of work on a parent and copied from the parent on a
child. Customer overrides **replace whole rules including their method**, because an override that may
change only the number forces a tenant to hand-compute a flat price from an estimated cost — the
caller-supplied price #146 deleted, arriving through a different door. Every plan must **name a
Pricing Book**, because "usage is free" is a rule someone wrote and a blank is not, and a nullable book
would fire the product's most important alert forever at the tenant who meant it. Zero revenue gains a
**reason** — `fixed_task_pricing` or `tenant_not_billing`, posture winning when both apply — because
#148's single `not_applicable` stamp was carrying two facts with opposite consequences. A cost total
mixing computed and reported figures is **complete, not qualified**; only an unresolved figure makes it
incomplete, and then it reads *"at least £4.20"*. And a fixed Charge reaches every money total by
**exactly one path** — the Charge explains money, only its unique projected posting moves it — which is
the invariant #139 built and nothing yet guarded.

---

## 1. The ticket's premise, corrected

### 1.1 The three modes are not three of a kind

The ticket inherits the map's working model:

> The working model proposes three charging modes: calculated metered cost, tenant-supplied provider
> cost with markup, and fixed price on task completion.

Each of those three is real. They are not, however, three values of one thing, and the list cannot be
made into an enum without breaking. Read them again as questions:

| Working-model "mode" | The question it actually answers |
|---|---|
| calculated metered cost | *How did we find out what this call cost us?* |
| tenant-supplied provider cost with markup | *How did we find out what this call cost us* **and** *how does the customer pay?* |
| fixed price on task completion | *Does the customer pay per call at all?* |

The middle row answers two questions at once, which is why it looks like a mode and is not one. #146
settled its cost half in as many words — a supplier-reported cost is *"not a fourth cost source … a
second, cheaper way to reach the one COGS number"*, and *"everything downstream of COGS is **identical
between the two modes**"*. Its price half is #147's `margin_over_cost`, which is available over a
reported cost and a calculated one alike (#147 §9.4, confirming rather than reopening #146 §2.1).

So "tenant-supplied provider cost with markup" is the pair *(reported, margin_over_cost)*. It is a
combination, not a member.

### 1.2 The ticket's diagnosis of today's code is exact

> Nothing declares a mode; the mode is *inferred* per event from which fields happen to be present
> (`pricing_service.py:94-171`). Two callers on the same event type can be in different modes.

That reading is correct and worth preserving as the record of what is being replaced.
`PricingService._compute` branches on `caller_provider_cost is not None` (`pricing_service.py:108`) and
again on `caller_billed is not None` (`:146`), then falls through `matched` to markup (`:162-167`).
Every branch is chosen by payload inspection. Nothing anywhere reads a declaration, because there is
none to read.

Three merged decisions have already dismantled the individual branches — #146 §2 made costing a
declared Event Type property, #146 §8 deleted `caller_billed` outright, #147 §2 replaced the
matched/fallback structure with one resolved rule declaring one method. What was left for this ticket
is not to fix the branches but to say **what the resulting model is called and where each part of it
lives**, and to close the residues the other tickets could not.

### 1.3 What this document actually decides

Six of the ticket's questions were substantially answered elsewhere and are confirmed here in one
vocabulary (§14). The genuinely open work is five residues explicitly handed here plus two consequences
nobody had noticed:

| Open item | From |
|---|---|
| Where `Task.pricing_mode` comes from, and what an unresolvable job price does | never stated; #147 §3.1 said only "snapshotted" |
| Whether an override may change a rule's **method** | #147 §14, #148 §17 |
| Whether a subtask may differ from its parent's pricing mode | #147 §14, map "Not yet specified" |
| Whether a `Plan`'s Pricing Book reference may be null | #147 §14, map "Not yet specified" |
| The pin that a fixed Charge counts exactly once | #150 §17 |
| **`not_applicable` carries two different facts** | discovered here (§8) |
| **A step and a job are one table row** | discovered here (§5.3) |

---

## 2. Three declarations, and no fourth field naming them

### 2.1 The ruling

**There is no `charging_mode` field, and there must never be one.** Charging behaviour is the
combination of three declarations, each owned at its natural level:

| Declaration | Values | Declared on | Decided by |
|---|---|---|---|
| **`costing_method`** | `calculated` · `reported` | **Event Type** | #146 §2.1 |
| **`pricing_method`** | `margin_over_cost` · `direct_event_price` | **the resolved pricing rule** | #147 §2.1 |
| **`pricing_mode`** | `event_priced` · `fixed` | **the Task** | #147 §3.1, §4 below |

```
costing_method    calculated   UBB derives COGS from measurements × effective Cost Rates
                  reported     the event supplies its known supplier COGS

pricing_method    margin_over_cost      customer charge derived from resolved COGS
                  direct_event_price    customer charge is the configured amount per event

pricing_mode      event_priced   events follow their resolved customer-pricing rules
                  fixed          events contribute COGS only; one Task Charge on delivery
```

None of the three is inferred from a payload, from the presence of a field, or from what configuration
happens to exist. That is the property today's `_compute` lacks and the whole of what this re-model
buys.

### 2.2 The combinations are legitimate, not exclusive

```
calculated + margin_over_cost + event_priced
  measurements × Cost Rates → markup applied → event creates a customer Charge

reported + margin_over_cost + event_priced
  supplier supplies the cost → markup applied → event creates a customer Charge

calculated + direct_event_price + event_priced
  COGS calculated for margin reporting → configured event price charged outright
  → no additional margin applied

calculated or reported + fixed
  events record supplier COGS → event-level pricing suppressed
  → one fixed Task Charge on delivery
```

The fourth row is why one enum would mislead. Those events still **have** a costing method — it runs,
it produces a real number, it feeds the ceiling — while their pricing method is not applied at all,
because the Task owns the revenue outcome. A single field would have to say two things about one event
and would be wrong about one of them.

### 2.3 Why not one enum

A combined field would need values resembling:

```
calculated_cost_margin_event
reported_cost_margin_event
calculated_cost_direct_event
reported_cost_direct_event
calculated_cost_fixed_task
reported_cost_fixed_task
…
```

Three objections, any one sufficient.

**It duplicates facts declared elsewhere**, so the combined field can disagree with the Event Type, the
Pricing Book or the Task snapshot — and when two encodings of one fact disagree, the wrong one is
always the one nobody is looking at. That is #148 §5.2's argument for deleting the book-version range,
arriving before the column is created rather than after.

**It multiplies whenever any axis gains a value.** A third costing method would double the enum.

**It has no owner.** Costing is the Event Type's, pricing is the rule's, scope is the Task's. A field
combining all three belongs to nothing and would have to be maintained by whichever write happened
last.

### 2.4 A derived summary is fine; a second source of truth is not

For usability the API or console may expose a one-line rendering:

```
charging_summary: "event priced using margin over calculated cost"
charging_summary: "fixed Task price; events contribute COGS only"
```

**`charging_summary` is derived at read time from the three canonical declarations and is never
stored, never written, and never read back as input.** It exists because a tenant reasonably wants one
sentence, and the failure mode it must avoid is becoming the thing someone updates.

### 2.5 The receipt snapshots the combination actually used

#148 made the receipt authoritative and gave it a `costing.method` and a `pricing.method`. It has
**nothing about the Task**, so the third axis is unrecoverable from the receipt alone — and #148 §4.7
is explicit that explanation must never dereference a pointer, which a live task lookup is.

**The receipt gains the Task's pricing mode**, so all three declarations are readable by value from one
immutable record. This is the mechanism behind §8, and it is what makes historical money explicable
after a Task row has been archived, a Task Type retired, or a Pricing Book republished.

---

## 3. The fourth declaration: posture decides what absence means

### 3.1 It charges nothing and governs everything

The tenant's declared operating posture — metering-only versus full billing — is **not** a charging
mode. It never determines a cost, a price or a scope. #141 §1.1 fixed what it does:

> **Mode decides who invoices — not whether economics exist.**

This document adds the corollary #147 §8.3 began and §4 below completes: **posture decides what a
missing price means, at every level.**

| | Metering-only tenant | Full-billing tenant |
|---|---|---|
| Missing **event** pricing rule | expected — the pipeline ends at COGS | recorded, revenue `unknown`, **alert** (#147 §8) |
| Missing **job** price on a `fixed` kind of work | expected — no Charge exists at all | **refuse the start** (§4.2) |

The representation is identical in both columns; the *reaction* differs. That is the whole of the
distinction, and it is why one set of columns serves both.

### 3.2 The asymmetry inside the full-billing column is deliberate

A missing event price **records and alerts**. A missing job price **refuses**. The two look
inconsistent and are not: they sit on opposite sides of the line #150 §1.3 drew.

```
reporting usage that already happened   → never refused; record it, even past a limit
starting NEW work that policy forbids   → refuse at the start gate
```

The event's provider call has already been made and already cost real money; refusing it destroys
evidence and understates COGS with nothing anywhere saying so (#146 §3.3). The job has not started;
refusing it costs nobody anything and prevents a job from running with no revenue story.

---

## 4. Where a job learns its pricing mode

### 4.1 The ruling

**The declared kind of work owns the durable declaration. The caller does not choose it and UBB never
infers it.**

```
TaskType
  code: video-transcode
  task_pricing_mode: fixed
```

```
POST /tasks
  task_type: video-transcode
  customer: acme
```

For a full-billing tenant, starting a `fixed` kind of work resolves that customer's applicable job
price and pins it:

```
Task Type declares: fixed
        ↓
Resolve customer override or Pricing Book work-level rule,
effective at Task start
        ↓
Snapshot onto the Task:
  pricing_mode          fixed
  fixed_price_micros    5_000_000
  currency              USD
  pricing_effective_at  task.started_at
  matched_rule_id       …
  pricing_book_publish_id …
        ↓
Task may start
```

Later Pricing Book changes must not alter a running or completed Task's price. That is #139's
determination lock and #148 §9.1's *the snapshot is the version* — no new machinery, one timeline read
twice.

### 4.2 Unresolvable job price: refuse the start (full-billing only)

```
Task Type declares fixed
+ no applicable customer price resolves
    → 422 fixed_task_price_unresolved
```

**Silently falling back to event pricing is refused.** Two reasons.

It would be **inferring commercial behaviour from missing configuration**, which #147 §8.3 forbids in
as many words for the event case — *"the system must not decide a billing tenant is 'metering-only for
this event' because pricing configuration is missing"*. The identical argument holds one level up, and
the consequence is worse: every child event of a job the tenant meant to sell once would be charged
individually.

And the boundary is the right one (§3.2). The work has not happened.

### 4.3 An explicit zero is a price; an absence is not

```
fixed_task_price: $0.00   → known, intentional, free job → start allowed
no matching rule          → refused
```

This is #147 §4.3's move applied to work: **the distinction between "absent" and "zero" is carried by
the presence of a rule, never by the value of a number.** It is the same shape as #146 §7.3 for cost
and #150 §8.1's `uncapped: true` for ceilings — three tickets now, one convention.

### 4.4 Why not the caller, and why not inference

**Caller declares it per start call.** The caller *already* chooses the mode, by choosing the
`task_type` — and #140 §2.4 makes the kind of work a **pinned** field precisely because *"a differing
kind of work is a differing price"*. A second, independent mode field on the same call could contradict
the type, and something would then have to win. #139 §2.4 had already placed the declaration on
`TaskType` and the amount in the customer's book, for the reason #138 established: the kind of thing
never holds the amount.

**UBB infers it from a price existing.** Rejected by #147 §3.3 for exactly this case: *"an economic
behaviour that is inferred from the presence of a field is a behaviour nobody declared and everybody
must reverse-engineer."*

### 4.5 For a metering-only tenant the declaration is inert, and that is honest

A metering-only tenant runs the same job with no price and no refusal (§3.1):

```
Metering-only tenant
  → Task starts normally
  → child events produce supplier COGS
  → customer pricing: not applicable
  → no UBB Charge
```

The consequence, stated so it is not discovered later: **for a metering-only tenant `fixed` and
`event_priced` are behaviourally identical.** Both produce no Charge and events whose pricing is
`not_applicable`. The declaration is recorded because it describes how the tenant sells and because
posture can change; it simply has no effect while UBB is not invoicing.

Forbidding a metering-only tenant from declaring `fixed` was considered and rejected — it is a gate
with no benefit that would have to be unwound the day they enable billing.

---

## 5. Containment: one column, no step may differ

### 5.1 The ruling

**A step has no independent customer-pricing mode and cannot override its Task's.** The Task is the
unit being sold.

```
Task
  pricing_mode: fixed
  fixed_price: £5.00

  events attached directly to the Task
    → record supplier COGS
    → no event-level customer Charge

  Step
    events attached to the step
      → record supplier COGS
      → no event-level customer Charge

Task delivered
  → one £5.00 Charge
```

```
Task revenue  = one fixed Task Charge
Task COGS     = all cost-bearing events belonging to the Task, including via steps
Task margin   = fixed Task Charge − total Task COGS
```

A step therefore carries no independently configurable `pricing_mode`, fixed price, margin policy or
direct-price override, and the caller cannot switch step pricing at runtime.

### 5.2 Why a step may not bill separately

If a step's events priced normally while the job was fixed, the customer would pay £5 **plus** metered
charges for part of the same job. #139 §2.1 is explicit that a fixed price *replaces* metered revenue
and is *"not a fee on top, and not a floor"*. Since step COGS already rolls into the parent
unconditionally — *"the parent sees everything underneath it"* (`tasks/services.py:60-68`) — the job's
Charge is meant to be the sole revenue line for everything beneath it.

The opposite direction is already impossible: #139 §3.3 refuses a fixed price on a step outright, whole
jobs only.

Under `event_priced`, step events price exactly as any other event does — both methods available, one
rule resolved per event. Under `fixed`, **both** methods are suppressed (#147 §3.2), and the events
still receive full cost receipts.

### 5.3 A step and a job are one table row — so one column, not two

`apps/platform/tasks/models.py:74-76` states it:

> *"Subtask containment (#38): a subtask **IS** a Task row with `parent` set — one model, one
> containment level at launch."*

So a per-step `task_pricing_mode_snapshot` beside a per-job `pricing_mode` would be **two columns on
one table**, only ever one populated per row, with two names for one invariant.

**Decision: one immutable `pricing_mode` column on every Task row.**

```
Parent Task creation
  → resolve pricing_mode from the Task Type
  → persist immutable snapshot

Child Task creation
  → copy pricing_mode from the parent
  → reject or prevent disagreement

After creation
  → pricing_mode never changes
```

Both are snapshots — one from configuration, one from the row above — and neither is caller-supplied.
The value is system-derived on every row, and `child.pricing_mode == parent.pricing_mode` always.

**Enforcement note:** the equality rule compares two rows, so it belongs in the creation service rather
than a simple column `CHECK`. It must be backed by tests and, where practical, a database trigger or
equivalent. This is the one invariant in this document that the schema cannot carry alone.

Reading the mode through the parent instead of copying it was rejected: the pricing decision runs on
every event, and a parent lookup on that path is a join the codebase already avoids by pushing task
fields down (`_inherit_dimensions`, `usage_service.py:110-148`).

### 5.4 A step kind may not declare `fixed` — refused at declaration

#139 §3.3 put this refusal in the start gate. **It moves to declaration time**, and that is a
deliberate narrowing.

```
TaskType
  kind: subtask
  task_pricing_mode: fixed   →  422 at declaration
```

#150 §8.1 established the better pattern one ticket ago — a kind of work declaring neither a ceiling
nor `uncapped: true` is refused when it is declared, not when a job starts. Catching an incoherent
declaration once at configuration beats catching it on every start, and it means the start gate has one
fewer thing to check on the hot path. Under map constraint 1 there are no existing rows to migrate.

### 5.5 The premium add-on, deferred rather than smuggled in

A step that bills separately inside a fixed-price job is **not** introduced as an exception in v1. It
would be a distinct additive-pricing feature and should be designed explicitly — or represented as a
separate Task — rather than by letting selected steps bypass the Task's revenue contract. This is the
same disposition #139 §2.1 gave "a per-job fee plus metered usage": possibly worth building, never
worth conflating.

---

## 6. Customer overrides replace whole rules, method included

### 6.1 The ruling

**A customer override is a complete, independently interpretable pricing rule.** There is no
field-level merging between a Pricing Book rule and an override.

```
Book rule                        Customer override        Resolved
  direct_event_price $0.02   →     direct_event_price $0.015    $0.015
  direct_event_price $0.02   →     margin_over_cost 10%         cost + 10%
```

The resolution contract is unchanged from #147 §5.1:

```
applicable customer override  → use the override as the complete rule
no applicable override        → use the Pricing Book rule
```

### 6.2 Why half a rule is not a replacement

#147 §4.1 already ruled that an override *replaces, never adds*. A replacement that must keep the
method it replaced is an amendment wearing a replacement's name, and "override" would need a second
meaning — which is the exact drift #147 §4.1 guarded against when it refused additive adjustments in
v1.

It also protects the deal. Under complete replacement, a later Pricing Book method change cannot
silently change the meaning of an existing negotiated arrangement; under partial merge, editing the
book's method would reinterpret every override that inherited it.

### 6.3 The hole a number-only override would reopen

If Acme genuinely negotiated cost-plus-10% and the book rule is a flat price, a number-only override
leaves the tenant one workaround: estimate Acme's typical cost, do the arithmetic by hand, and enter a
flat number that *approximates* cost-plus-10%.

That is a per-customer price computed outside UBB and pasted in — precisely the caller-supplied price
#146 §8 deleted, arriving through the configuration door instead of the payload door, and going stale
the moment the supplier moves. #146's governing asymmetry is *cost is observed, price is decided*; a
model that forces tenants to hand-compute prices from remembered costs breaks the second half.

### 6.4 What it costs, and how the console absorbs it

**The override editor is a rule editor, not a number field** (#148 §17 flagged this consequence). The
convenience belongs in the UI, not in the domain model:

```
Create override from inherited rule
    ↓
Method preselected, current value shown
    ↓
Tenant changes the price or percentage
```

Changing the method stays possible but explicit, because it changes the shape of the negotiated deal.

**Two events of the same Event Type may legitimately read differently in their receipts** — one
`margin_over_cost`, one `direct_event_price`, for two customers. #148 §17 raised this as a worry; it
resolves itself, because #148 §4.4 already records `pricing.method` and the applied value **per event,
by value**. The receipt was built for exactly this.

The four-rung ladder is untouched: #147 §5.1 ranks by specificity, and nothing about ranking depends on
rules at different rungs sharing a method.

---

## 7. A Plan must name a Pricing Book

### 7.1 The ruling

**`Plan.pricing_book_id` is required, not nullable.** This closes the map's *"Not yet specified"* item
and #147 §14's *"`Plan` with no book is undefined."*

A tenant whose plan includes usage in the access fee writes one rule:

```
Pricing Book "Individual"
  default: direct_event_price $0.00      ← usage is included
```

That is honest and it is a *statement*. The event genuinely earns nothing; the money arrives as the
access fee, which #141 §1.2 forbids smearing back across events. Margin per event reads as negative
COGS, which is the truth for an all-you-can-eat plan.

### 7.2 Why not nullable: the alert that would get muted

#147 §8's *"you are not charging for this"* is the single most important alert in the product. Under a
nullable book reference, the tenant who **deliberately** charges nothing for usage would be alerted on
every event, forever, for a decision they made on purpose.

That is how an important alert gets muted, and a muted alert protects nobody — including the tenant who
later genuinely misconfigures something. Requiring one written rule converts a permanent alarm into a
one-time declaration.

This is the third application of one convention (§4.3): #150 §8's `uncapped: true`, #147 §4.3's
presence-of-a-rule, and now this. **Uncapped is legal but never silent; free is legal but never blank.**

Plans are billing-only — `plan_router` carries `ProductAccess("billing")` with the reason stated
inline: *"a plan is a commercial offer, and charging for one is what the billing product is"*
(`api/v1/plan_endpoints.py:8-9`, `:26`) — so requiring a book never touches a metering-only tenant.

### 7.3 The case this does not fix, and should not

A full-billing tenant with a customer on **no plan at all** still has no book, and no requirement on
`Plan` can change that. That is correctly the #147 §8 alert path: they genuinely have not said how to
charge that customer. It is a real onboarding state and an alert is the right response — actionable,
and it clears.

**Cost, named:** creating a first plan now requires creating a book first. That is console sequencing —
offer a starter book, or mint one alongside the plan — not a model problem. **Bonus:** requiring the
book also guarantees #139's work-level job prices a home, since a book carries both event rules and
work-level lines.

---

## 8. Zero revenue has two causes, and the record says which

### 8.1 The problem #148 left

#148 §4.4 stamps an event that earns no revenue as:

```
pricing:
  method: none
  status: not_applicable
```

That exact stamp is used for **two different facts with opposite consequences**, and after §4 there is
a third case where both are true:

| Situation | What it means | Where the revenue is |
|---|---|---|
| a call inside a fixed-price job (#148 §9.3) | the job owns the revenue | on the Task Charge |
| any call from a metering-only tenant (#150 §1.2) | UBB was never asked to price | **nowhere** |
| a metering-only tenant running a `fixed` kind of work (§4.5) | both descriptions apply | nowhere |

One stamp, three stories. This is the same collapse this map has deleted three times already —
unknown-versus-zero cost (#146 §4), unknown-versus-zero revenue (#147 §7.1), waived-versus-genuinely
-free (#147 §7.1) — and it is the reason a dashboard would render a fixed-price job's 399 cost-only
calls exactly as it renders a metering-only tenant's entire life.

### 8.2 The ruling

**`not_applicable` carries a reason from a closed list, and posture wins when both apply.**

```
pricing_status:        not_applicable
not_applicable_reason: fixed_task_pricing     | tenant_not_billing
```

| Both true? | Recorded reason |
|---|---|
| metering-only tenant, `event_priced` job | `tenant_not_billing` |
| full-billing tenant, `fixed` job | `fixed_task_pricing` |
| **metering-only tenant, `fixed` job** | **`tenant_not_billing`** |

**Posture wins because it is the honest one.** For a metering-only tenant no Charge is created
anywhere, so `fixed_task_pricing` would imply revenue sits on a Charge that does not exist — sending a
reader to look for a number nobody wrote.

### 8.3 Why a reason and not a fifth status

The status is already right: the event genuinely has no customer price, and that is correct rather than
a gap. What was missing is which of two mutually exclusive causes produced it, and the two have
different consequences — one means *look at the job's Charge*, the other means *there is nothing to
look at, by design*.

This **extends** #148 §4.4 the way #148 extended #147 §7: adding a distinction inside a value, never
reversing one. #147's three statuses became four; the fourth now carries a reason.

### 8.4 What the receipt gains

Two additions, both by value (§2.5):

- the Task's `pricing_mode`, so the third axis is recoverable without a live lookup;
- `not_applicable_reason` where the status is `not_applicable`.

Together these make the charging combination fully explicable from one immutable record — which is
#148 §3's whole premise applied to a dimension #148 did not have.

---

## 9. Contradiction: cost may disagree, price cannot

### 9.1 The cost side — confirmed, not reopened

#146 §3.2 governs and nothing here changes it. **No otherwise-valid event is ever refused.**

```
reported Event Type, no cost supplied
  event accepted and preserved
  provider_cost_micros: null
  costing_status:       unresolved
  unresolved_reason:    reported_cost_missing
```

The missing amount is never interpreted as zero, and the tenant receives a visible, **deduplicated**
diagnostic — one per cause, not one per event (#146 §11) — because the integration has failed to
deliver part of a declared contract.

```
calculated Event Type, a cost supplied anyway
  UBB-calculated COGS          → remains authoritative
  claimed_provider_cost_micros → retained as diagnostic source data
                               → never overrides or supplements calculated COGS
                               → never double-counts
```

The retained value is named `claimed_provider_cost_micros` precisely so it cannot be mistaken for
canonical COGS. This is #146 §3.5's caller's-claim record, given a name that carries its own warning.

### 9.2 The price side is contradiction-proof by construction

**A caller cannot submit or override a customer price on an event**, because #146 §8 deleted
`RecordUsageRequest.billed_cost_micros`. Customer pricing is resolved only from the Pricing Book, a
customer override, and the Task's pricing mode. **No event payload can disagree with the configured
pricing method or amount, because there is nothing in the payload to disagree with.**

This is recorded as a deliberate invariant rather than left as a happy accident:

> **Supplier cost may be an observed value reported by the caller. Customer price is a commercial
> decision resolved and held by UBB.**

**Do not reintroduce an optional per-event price field for convenience.** The reason to write that
sentence down is that it will be re-proposed — it is small, it looks helpful, and the argument against
it lives three documents away.

### 9.3 The overlap that is not a contradiction

An Event Type with a configured price of 2p, used inside a fixed-price job, earns nothing.

```
event_priced Task  → event pricing rule applies
fixed Task         → event contributes COGS only
                   → pricing_status: not_applicable
                   → not_applicable_reason: fixed_task_pricing
                   → one Task Charge on delivery
```

**This is expected configuration reuse, and it is reported, never alerted.** Two reasons.

A tenant running both fixed-price and metered jobs over the same Event Types is legitimate and likely
common, so alerting would fire constantly on a correct setup — the muting failure §7.2 already
identified.

And it **cannot be caught at configuration time even in principle**: there is no declared relationship
between a kind of work and the Event Types used inside it, so UBB cannot know in advance which prices a
fixed job will suppress. A warning would have to be invented from data that does not exist.

The three cases, distinguished:

| Case | Disposition |
|---|---|
| reported cost missing | declared contract unfulfilled → `unresolved`, **alertable** |
| unexpected cost on a `calculated` kind | payload contradicts the declaration → economically ignored, **diagnosable** |
| event price suppressed inside a fixed Task | rules working as intended → **reported for explanation, never alerted** |

---

## 10. Mixed derivation is complete; unresolved is incomplete

### 10.1 The ruling

**A Task may freely combine calculated and reported COGS.** When every contributing event has a known
cost, their sum is the **complete** Task COGS regardless of how each amount was derived. Cost
derivation is *provenance*, not a warning condition.

```
Task COGS: £4.20
Status:    complete

Breakdown:
  calculated COGS: £3.10
  reported COGS:   £1.10
```

The ticket asked whether a single task can mix modes. Two axes mix freely and one cannot, which
dissolves the question:

- **`costing_method` mixes freely** and always did — it is declared per Event Type and a job calls many
  Event Types. The ticket's own example (*"a workflow calling three providers may plausibly meter two
  and take a supplied cost for the third"*) is the **ordinary case**, not an exception needing
  permission. #146 §2.3 rejected a tenant-level costing declaration for exactly this reason: *"too
  coarse — one tenant legitimately has both kinds."*
- **`pricing_method` mixes freely** inside an `event_priced` job — each event resolves its own rule, so
  one call at a flat 2p and the next at cost+20% is normal.
- **`pricing_mode` does not mix** — one value for the whole job including its steps (§5).

### 10.2 Provenance is a breakdown, not a caveat

Both derivations produce the same downstream economic fact, which #146 §2.1 already ruled:

```
calculated  measurements × effective Cost Rates  ┐
                                                 ├→ canonical event COGS → Task COGS
reported    supplier amount supplied with event ┘   → ceilings → margin reporting
```

The total must **not** display a warning merely because it combines the two. Tasks spanning several
providers and Event Types will commonly do so, and a footnote on every such total is a footnote on
almost every total.

But the derivation must remain **available** in receipts, exports and drill-downs, because the two have
different audit characteristics (#146 §7.4):

```
calculated  UBB can reproduce the amount from quantities and rates
reported    UBB preserves the supplied amount and its provenance
            but cannot independently derive it
```

Informational metadata, not a health state:

```
cost_sources:
  calculated_event_count: 8
  calculated_cost_micros: 3_100_000
  reported_event_count:   2
  reported_cost_micros:   1_100_000
```

### 10.3 Unresolved is a caveat, and states its meaning

If any cost-bearing event remains unresolved, the displayed amount is only the **known portion**:

```
Known Task COGS:  £4.20
Status:           incomplete
Unresolved events: 1
True Task COGS:   at least £4.20
```

*"At least £4.20"* is the required wording — it states the economic meaning, where a symbol such as
`+?` states only that something is missing. It is also exactly #150 §4.2's reasoning made visible: the
known total is a **true lower bound**.

Downstream consequences, unchanged from the decisions that own them:

```
Task COGS → incomplete
Margin    → unavailable or incomplete
Ceiling   → known total at or above ceiling  → limit_reached  (#150 §4.2)
          → known below with unresolved cost → indeterminate  (#146 §5)
```

**Unknown cost is never treated as zero** (#146 §4), and no aggregate may coalesce a NULL — the `or 0`
sites #147 §13, #150 §7.6 and #153 already name are in scope of this rule, not exempt from it.

---

## 11. One money path

### 11.1 The ruling

**A `Charge` is canonical for the customer liability that was decided. Its exactly-one projected
economic posting is the sole path into every monetary total.**

```
Fixed-price Task delivered
    ↓
Charge created exactly once
    ↓
One economic posting projected exactly once
    ↓
customer monthly spend Pool · wallet drawdown · invoice totals ·
live spend counters · revenue and margin reporting
```

> **A Charge may explain money, but only its projected posting moves, counts or bills that money.**

```
Charge            owns task, amount, currency, pricing provenance,
                  idempotency and lifecycle

Projected posting owns the amount as represented on the shared money rail

All totals        read projected postings only
```

Nothing may independently do this:

```
on Charge creation:
  increment Pool
  increment wallet spend
  increment invoice total
```

Those updates would create a second accounting path and would double-count the moment the posting is
also consumed.

### 11.2 Why it needs saying, and what enforces it

This is not new machinery — it is the invariant #139 §4.2–4.3 built and #150 §17 noticed was
unguarded. The Pool's basis is `Sum("billed_cost_micros")` over `UsageEvent`
(`apps/metering/queries.py:232-237`, `:256`), so a fixed Charge reaches it **only** through the
projection. Nothing states that, and "when a Charge is created, add it to the Pool" is a reasonable
-sounding change that would silently double-bill every fixed-price job.

Structural enforcement:

```
Charge   has exactly zero or one posting while being created
         has exactly one posting once successfully committed

Posting  belongs to exactly one Charge
         has a unique charge_id
```

Charge creation and posting projection occur **atomically**, or through an exactly-once outbox workflow
whose incomplete state is detectable and repairable. **A Charge must not appear successfully posted
while lacking its economic projection.**

Pinned by tests, per the repo's ratchet:

| Case | Assertion |
|---|---|
| fixed Task Charge of $5 | Pool, wallet and invoice each increase by exactly $5 — never $10 |
| idempotent delivery retry | same Charge, same posting, no second increment |
| posting replay | no duplicate financial effect |
| refund or adjustment | its own canonical record, projected onto the same rail, never a direct total mutation |

### 11.3 Two limitations that are correctly separate

Carried from #150 §7.5 and confirmed rather than reopened:

```
Fixed-price Task while running   no Charge exists yet
                                 → the Pool cannot observe or stop it on that future price

Prepaid start affordability      → answered by Wallet policy (#139 §4.1 reserves at start)

Period spend after Charges exist → answered by the customer spend Pool
```

#150 §18 flagged these as *"two different answers to how much has this customer committed to"* that
would read as an inconsistency. **They are not competing readings of one number.** Wallet policy asks
whether funds permit *starting* work; the Pool asks how much has actually been *charged* during the
period. The charging model says which is which so the console can label them; reserving fixed job
prices against the Pool remains a separate future feature, as #150 decided.

---

## 12. The counterfactual metered price is declined

#139 §10 parked this here:

> *"Recording the hypothetical metered price in the posting's provenance — so a tenant can check the
> fixed price is actually profitable — is recommended but not decided as required."*

**Decided: no. Declined, so the residue closes rather than drifting.**

**It puts a number that was never charged inside the record that is now authoritative.** #148 made the
receipt the single source of truth for money precisely so there is nothing to reconcile against. A
counterfactual price beside the real one is a second number in an authoritative record, and someone
will eventually reconcile against it — the *"two sources of truth that can disagree"* #148 §3.2 refused
outright.

**It doubles pricing work on the hottest path, permanently.** Every event of every fixed-price job
would run the full four-rung ladder purely for reporting, and #148 retains receipts for **six years**,
so it inflates storage across that whole window. #148 §17 already flags that the receipt's size is
unmeasured.

**The question it answers is answered better elsewhere.** *"Did this job make money?"* is exact today:
pinned price − job COGS (#139 §2.2). *"Is £5 the right price for this kind of work?"* is a question
about the **distribution** of COGS across many past jobs of that type — a reporting view over data that
already exists, and a materially more useful answer than a per-event counterfactual. It belongs to
#152/#153.

The migration case was put fairly and does not survive: a tenant moving a job type from metered to
fixed wants *"what would we have billed?"*, but that is a historical comparison over the metered period
they already have — it does not require manufacturing counterfactual prices forever afterwards.

---

## 13. Naming

### 13.1 One word per job

Five things in this neighbourhood are called "mode" and two are called "method". The rule:

```
method     how an amount is derived        costing_method · pricing_method
mode       which operating regime applies  pricing_mode · billing_mode
structure  the mathematical shape of a rate rate_structure
```

### 13.2 `Rate.pricing_model` must be renamed

`apps/metering/pricing/models.py:81` — `pricing_model ∈ {per_unit, flat}` — describes the arithmetic
shape of one rate. `Task.pricing_mode ∈ {event_priced, fixed}` describes whether a whole job is sold at
once. **They differ by one character and are unrelated.** A human, an autocomplete or a code generator
will conflate them, and the failure is silent in both directions.

**Recommended: `Rate.rate_structure`, with values `per_unit` and `fixed_component`.**

`fixed_component` rather than `flat` because **"fixed" now means a whole Task is sold for one price**;
here it means a fixed component within one rate's calculation. Keeping `flat` would leave two unrelated
senses of "fixed" one field apart.

The rename is nearly free: #145 §10 is already renaming that model's neighbours
(`rate_per_unit_micros` → `amount_micros`, `unit_quantity` → `per_quantity`), and ADR-0003 deleted
tiered pricing, so the field is down to two values on a record being rewritten anyway. #154 makes the
final call; what is decided here is that **`pricing_model` may not survive alongside `pricing_mode`.**

### 13.3 The retired phrase

**No canonical `charging_mode` field, and no individual thing is called a "charging mode."** The three
declarations together are *the charging model*; `charging_summary` is its derived, display-only
rendering (§2.4).

Retiring the phrase is part of the fix. "Charging mode" is what made this area read as one setting with
three values, and every question in the ticket follows from that reading.

---

## 14. Answers to the ticket's six questions

**1. What are the legal modes, named? Is "tenant-supplied provider cost with markup" genuinely a
mode?**
**There are no modes in that sense — the list is a category error** (§1.1). Three independent
declarations exist at three levels: `EventType.costing_method`, `ResolvedPricingRule.pricing_method`,
`Task.pricing_mode` (§2.1). **"Tenant-supplied provider cost with markup" is not a mode**; it is the
combination *(reported, margin_over_cost)*, and #146 §2.1 already ruled that everything downstream of
COGS is identical between the two derivations. The combinations are legitimate, not exclusive (§2.2).

**2. Where is a mode selected?**
**At three different levels, and never per call.** Costing on the **Event Type** (#146). Pricing method
on the **resolved rule** — book rule or customer override (#147 §5.1), where an override replaces the
whole rule including its method (§6). Revenue scope on the **Task**, resolved from the declared kind of
work at start and pinned (§4.1). A fourth declaration — the tenant's posture — charges nothing but
decides what an absence means (§3).

**3. Are modes mutually exclusive, and what enforces that?**
**Within each axis, yes; across axes, the question does not arise.** `costing_method` is exclusive per
Event Type (#146 §2.3); `pricing_method` is exclusive per rule (#147 §2.1); `pricing_mode` is exclusive
per Task and uniform across its steps (§5). Enforcement is by construction rather than by validation:
each is a single declared field on a single owner, the caller can set none of them, and the receipt
records all three by value (§2.5).

**4. What happens when a call contradicts its declared mode?**
**Nothing is refused, and on the price side no contradiction is possible** (§9). Cost-side mismatches
are preserved and diagnosable — a missing reported cost is `unresolved` with
`unresolved_reason: reported_cost_missing` and a deduplicated alert; an unexpected cost on a
`calculated` kind is retained as `claimed_provider_cost_micros` and never affects COGS. The price side
is contradiction-proof **by construction**, because #146 §8 deleted the caller price field — recorded
as a deliberate invariant so it is not reintroduced for convenience (§9.2).

**5. Can a single task mix modes across its events?**
**Two axes mix freely, one does not** (§10.1). Costing mixes per event type — the ticket's
three-provider example is the ordinary case, not an exception. Pricing method mixes per event inside an
`event_priced` job. `pricing_mode` is one value for the whole job including steps. A mixed-derivation
cost total is **complete**, with provenance available as a breakdown; only an **unresolved** cost makes
it incomplete, and then it reads *"at least £4.20"* (§10.3).

**6. Does a fixed-price task suppress event-level charging, and is that a fourth mode or a property of
the task?**
**It suppresses both pricing methods, and it is a property of the task** (§5) — reaffirming #147 §3.
Not a fourth mode: it is the third axis, and the events retain full cost receipts. Suppressed events
are `not_applicable`, never zero (#148 §9.3) — and now carry
`not_applicable_reason: fixed_task_pricing`, distinguishing them from a metering-only tenant's events,
which carry `tenant_not_billing` (§8).

---

## 15. What each existing thing becomes

| Today | Becomes |
|---|---|
| `PricingService._compute` payload branches (`pricing_service.py:108`, `:146`, `:162-167`) | **Deleted** — already required by #146 §13 and #147 §12; §1.2 records what replaces them |
| `Rate.pricing_model ∈ {per_unit, flat}` (`pricing/models.py:81`) | **Renamed** — recommended `rate_structure ∈ {per_unit, fixed_component}`; may not survive beside `pricing_mode` (§13.2) |
| `EventType` costing declaration (#146 §2) | **Named `costing_method`** — "mode" reserved for operating regimes (§13.1) |
| Pricing rule method (#147 §2.1) | **Named `pricing_method`**, resolved per event, recorded per event by value |
| `Task.pricing_mode` (#147 §3.1) | **Kept, and sourced** — resolved from `TaskType.task_pricing_mode` at start, pinned, immutable (§4.1) |
| — | **New:** `TaskType.task_pricing_mode ∈ {event_priced, fixed}`; a step kind may not declare `fixed` (§5.4) |
| `Task.pricing_mode` on a child row | **One column, system-derived copy of the parent's**, never caller-set, `child == parent` enforced in the creation service (§5.3) |
| `Task` fixed-price snapshot (#139 §2.3) | **Extended** — `fixed_price_micros`, `currency`, `pricing_effective_at`, `matched_rule_id`, `pricing_book_publish_id` (§4.1) |
| #139 §3.3's start-gate refusal of a priced step | **Moves to declaration time** — a narrowing (§5.4) |
| `Plan.pricing_book_id` (#147 §4.1) | **Required, not nullable** (§7.1) |
| `Plan.markup_percentage_micros` / `fixed_uplift_micros` (`plans/models.py:33-34`) | **Deleted** — unchanged from #147 §4.2 |
| `RateCardAssignment` (`pricing/models.py:164`) | **Superseded** by Plan → book + customer overrides (#147 §4.1); no direct customer→book assignment survives |
| `CustomerPricingOverride` (#147 §4.1) | **A complete replacement rule**, method included (§6.1) |
| `RecordUsageRequest.provider_cost_micros` | **Kept** — meaningful on a `reported` kind; on a `calculated` kind retained as `claimed_provider_cost_micros` (§9.1) |
| `RecordUsageRequest.billed_cost_micros` | **Deleted** — #146 §8; §9.2 states the resulting invariant so it is not reintroduced |
| `pricing_status = not_applicable` (#148 §4.4) | **Gains `not_applicable_reason ∈ {fixed_task_pricing, tenant_not_billing}`**, posture winning (§8.2) |
| `costing_status = unresolved` (#146 §3.1) | **Gains `unresolved_reason`**, starting with `reported_cost_missing` (§9.1) |
| The receipt (#148 §4.4) | **Gains the Task's `pricing_mode`** and `not_applicable_reason`, both by value (§8.4, §2.5) |
| `Charge` → posting projection (#139 §4.3) | **Pinned as the one money path**; posting carries a unique `charge_id`; atomic or exactly-once creation (§11) |
| `Sum("billed_cost_micros")` Pool basis (`queries.py:232-237`, `:256`) | **Confirmed as the only Charge-aware total**; the `or 0` coalescing is in scope of §10.3 |
| Task COGS total (`tasks/models.py`, `services.py:114-127`) | **Complete when all costs known**, regardless of derivation; `cost_sources` breakdown available; marked incomplete only on unresolved (§10) |
| — | **New (display only):** `charging_summary`, derived at read time, never stored (§2.4) |
| The phrase "charging mode" | **Retired.** The three declarations are *the charging model* (§13.3) |

---

## 16. Narrowings and extensions of merged decisions

Recorded explicitly, because this map's convention is that a later document may narrow an earlier one
but may never do it silently.

| Document | What changes |
|---|---|
| **#139 §3.3** | **Narrowed.** The refusal of a fixed price on a step moves from the start gate to **declaration time**, on #150 §8.1's precedent (§5.4) |
| **#139 §10** | **Residue closed.** The counterfactual metered price on a fixed job's postings is **declined** (§12) |
| **#147 §14** | **Three residues closed.** An override may change a rule's method (§6); a subtask may **not** differ from its parent's pricing mode (§5); `Plan`'s book reference is **required** (§7) |
| **#148 §4.4** | **Extended, not reversed.** `not_applicable` gains a reason, and the receipt gains the Task's pricing mode — a distinction added inside a value, the same move #148 made on #147 §7 (§8) |
| **#148 §17** | **Answered.** The override-changes-method question is decided yes; its receipt consequence resolves itself because `pricing.method` is already recorded per event by value (§6.4) |
| **#146 §2.1** | **Renamed only.** "Costing mode" becomes `costing_method`; the substance is untouched (§13.1) |
| **#150 §7.5** | **Confirmed, not reopened.** Pool reservation of fixed job prices stays a future feature; §11.3 states which question each control answers |
| **Map #137 "Not yet specified"** | **Both items closed** — `Plan`'s book reference (§7) and `Task.pricing_mode`'s subtask interaction (§5) |

Nothing is reversed.

---

## 17. Constraints this imposes on other tickets

- **#152 (task dashboard and reporting)** — inherits the most. Must render `not_applicable_reason`
  distinctly, or a fixed-price job's cost-only calls read exactly like a metering-only tenant's entire
  life (§8.1). Must show a mixed-derivation Task total as **complete** with a `cost_sources`
  drill-down, and mark it incomplete **only** on unresolved, using *"at least £4.20"* (§10). Must
  surface `charging_summary` as derived, never as an editable field (§2.4). Must label wallet
  affordability and the Pool as answering different questions (§11.3).
- **#153 (analytics re-alignment)** — every COGS surface must be able to say which derivation produced
  a figure (§10.2), and no aggregate may sum a NULL as zero (§10.3). "Is £5 the right price for this
  kind of work?" becomes a **distribution of COGS per kind of work** — the reporting shape that
  replaces the declined counterfactual (§12).
- **#154 (vocabulary lock)** — owes: the forced rename of `Rate.pricing_model`, recommended
  `rate_structure ∈ {per_unit, fixed_component}` (§13.2); the method/mode/structure rule (§13.1);
  `not_applicable_reason` and its two values; `unresolved_reason` and `reported_cost_missing`;
  `claimed_provider_cost_micros`; `charging_summary`; `TaskType.task_pricing_mode` versus
  `Task.pricing_mode`; and the retirement of the phrase **"charging mode"** (§13.3), which should not
  survive in the map, the console or the docs.
- **#155 (onboarding and cutover)** — a tenant registering an Event Type must choose a
  `costing_method` (already #146 §14); a tenant declaring a kind of work must now also choose a
  `task_pricing_mode`, and there is **no defensible default** for a full-billing tenant, since `fixed`
  without a resolvable price refuses starts (§4.2). Plan creation must sequence book creation first
  (§7.2). Migration owes the `Rate.pricing_model` rename and the `RateCardAssignment` → Plan-book
  cutover.
- **#156 / #157 (Code Builder)** — the generator reads **one** of the three declarations: the Event
  Type's `costing_method`, which decides whether the generated call sends a cost. It reads neither of
  the other two, because the caller cannot express a price (§9.2) and the job's mode is server-resolved
  (§4.1). It may state a job's fixed price from configuration, and must generate handling for
  `422 fixed_task_price_unresolved` on start.
- **#165 (splitting the measurement record from the economic posting)** — **strengthened again.** §8
  puts two more fields on the economic side (`not_applicable_reason`, the Task's pricing mode on the
  receipt) while the measurement record gains nothing, and §11's unique `charge_id` belongs
  unambiguously to the posting. That is the seam, arriving from a third direction after #147 §13 and
  #148 §10.4.
- **#149 (declared granularity)** — its handoff is answered in §18: a finer declared unit multiplies
  `not_applicable` postings, not zero-revenue ones.
- **#158 (end-to-end audit method)** — §11's four pinned cases and §5.3's cross-row equality invariant
  are audit inputs; both are enforced outside the schema and therefore need explicit tests rather than
  a constraint to inspect.

---

## 18. Residue, flagged rather than buried

- **The parent/child `pricing_mode` equality is not enforceable by a column constraint.** It compares
  two rows, so it lives in the creation service (§5.3). A database trigger is recommended where
  practical, but the invariant is code-enforced and therefore only as good as its tests. This is the
  weakest enforcement in the document and it guards a money-shaped rule.
- **A finer declared unit multiplies `not_applicable` postings, not zero-revenue ones** (#149 §11's
  request, answered). Sixty per-minute events under a fixed-price job are sixty cost-only postings,
  sixty receipts and sixty six-year retention obligations — and for a fine-grained tenant
  `not_applicable` becomes the *most common* pricing status in the system. #148 §17's unmeasured
  receipt-size concern applies here with a multiplier.
- **For a fixed job spanning a price change, revenue is pinned and cost floats** (#148 §9.2, confirmed
  as part of what the mode means). Cost resolves at each event's own timestamp; revenue was pinned at
  start. The asymmetry is principled — the price was promised, the cost is observed — but it means a
  job's revenue and its COGS resolve against different instants, which will look wrong to someone
  reading a single receipt without this document.
- **For a metering-only tenant `fixed` and `event_priced` are behaviourally identical** (§4.5). The
  declaration is recorded and inert. It becomes live the day they enable billing, at which point a
  `fixed` kind of work with no configured price starts **refusing starts** — a posture change that
  silently converts an inert declaration into a start-gate refusal. #155 must surface this at cutover.
- **A fixed-price job for a full-billing tenant can be blocked by a pricing gap on a customer nobody
  looked at.** §4.2 is deliberate and refuses at the cheapest moment, but the failure lands on the
  tenant's *end customer's* work, not on the tenant's console. The alert must be pre-emptive — "these
  customers cannot start `video-transcode`" — rather than discovered on the first refusal. No mechanism
  is designed here; it is #152's surface and #146 §11's queue is the obvious host.
- **Nothing decides how a Task Type's `task_pricing_mode` may change over time.** Retire-never-delete
  is the obvious inheritance from #138, and existing Tasks are immune because the mode is snapshotted —
  but flipping a live kind of work from `event_priced` to `fixed` changes the revenue shape of every
  future job of that kind with no effective-dating and no publish record. #148 gave pricing rules a
  publish; this declaration has nothing equivalent. Left open deliberately, and it should be answered
  beside the Task Type's other declarations rather than here.
- **The premium add-on inside a fixed-price job has no answer** (§5.5). It is a real commercial shape —
  a fixed job with one chargeable extra — and the current answer is "make it a separate Task", which
  loses the containment relationship. Deferred, not solved.
- **`charging_summary` will be asked to become writable.** It is exactly the field a tenant will want
  to set in a CSV import or a bulk configuration screen. The rule in §2.4 is one sentence and the
  pressure against it will be recurring.
