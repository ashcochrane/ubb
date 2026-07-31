# Provider-supplied cost — a second way to reach COGS, and one rule for what UBB cannot know

**Resolves:** [#146](https://github.com/ashcochrane/ubb/issues/146) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-31
**Decided against:** `main` @ `82a3a53`
**Evidence:** `docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch
`research/pricing-model-prior-art` @ `2f0ce4c`) — **Q4** (only two of six platforms accept a cost
through the metering pipeline; Lago's `dynamic` charge model; the silent-precedence failure mode;
OpenMeter's cost plane that never touches invoicing) and **§5** of its recommendations.
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — the Event Type
owns costability, not cost; missing cost is never zero; unknown event types are quarantined and
replayed at their original timestamp; `require_cost_card_coverage` is "structural now → #146".
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the Charge is terminal and
immutable; there is no re-invoice path anywhere; the ceiling-as-a-fraction-of-price question is
parked here.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — terminal is terminal; `killed` is
narrowed to genuine spend signals.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — the COGS ceiling is universal
and wallet-free; **unknown revenue ≠ zero**; the coverage gate moves to the kernel and "its
*semantics* are #146's collision to resolve".
`docs/plans/2026-07-30-money-model-decision.md` (#142) — the caller-cost cap asymmetry is "unexplained
and belongs to #146".
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — only declared measurements may
move money; "unresolved measurements are a new blocking state it must handle".
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 through #145: #154 is the single naming pass, and
this document coins three nouns (§12). The ADR is owed *after* #154 and should cite all seven decision
documents.

---

## The decision in one paragraph

**A supplier-reported cost is not a fourth cost source. It is a second, cheaper way to reach the one
COGS number** — and once COGS exists the two derivations are indistinguishable to everything
downstream: the same margin, the same price ladder, the same ceiling, the same reports. Which
derivation applies is **declared once per kind of event**, never asserted per call: an Event Type
either has its cost computed from declared measurements and Cost Rates, or has it reported by the
caller, never both. Quantities are still recorded on reported-cost events — they simply do not derive
the money — which is precisely the breakdown the current collision destroys. Everything UBB cannot
compute is governed by **one rule: preserve, flag, remediate.** Nothing is refused: an event whose
cost cannot be resolved is recorded with `costing_status = unresolved` and a **null** cost that is
never zero, the tenant is alerted once per *cause* rather than once per event, and the event replays
at its original timestamp when the gap is fixed. A spend ceiling therefore gains a **third state** —
`within_limit`, `limit_reached`, **`indeterminate`** — because a ceiling standing over an unresolved
event cannot honestly be called safe; and one misconfigured call never kills a job of a thousand good
ones. The `require_cost_card_coverage` flag, the `cost_coverage_required` start refusal, and — a
consequence the ticket did not anticipate — the entire `Unpriceable` sync-fallback path that exists
only to serve them are **all deleted**, because #138 and #145 already made costability structural and
there is nothing left for a tenant to promise. On the revenue side the mirror hole is **closed
outright**: caller-supplied *billed* cost is deleted, giving the model its governing asymmetry —
**cost is observed, price is decided.** Corrections are new entries beside the original, never
overwrites, and a period closes on time with unresolved events billing next period, still dated to
when they happened.

---

## 1. The ticket's premise, corrected

The ticket presents two problems: an undocumented **fourth cost source**, and a **hard collision**
between provider-supplied cost and task spend limits. Both descriptions are accurate about the code
and wrong about the shape of the fix.

### 1.1 There is no fourth source, because "source" is the wrong axis

The map's ground truth records "two axes (cost, price) × three sources each — not three exclusive
modes", and the ticket inherits that framing. It counts *provenance* and concludes there are more
kinds of thing than the working model knew about.

But provenance is not a kind of thing. **A supplier-reported cost and a rate-card-computed cost are
the same fact obtained two ways.** The owner's framing during grilling is the correct one, and it is
worth quoting because it is the spine of everything below:

> costs are produced (i.e. our COGS are known per event) for any event prior to any margin added.
> This is essentially another way of calculating our COGS. In fact it's an easier way because a
> provider or a supplier gives it to us. … We then apply the same logic afterwards to this type of
> event for a margin as we do an event that we calculated our supplier costs using our measurements
> and prices for those measurements.

So the two paths converge at COGS and **share every step after it**. That is what makes the whole
ticket tractable: there is no second plane to keep consistent, no parallel margin arithmetic, no
second ceiling. There is one COGS number with two derivations, and the only design question is *which
derivation applies, and how UBB knows in advance.*

This also explains why the current code is confusing without being wrong. `_compute`
(`pricing_service.py:94-171`) already treats caller cost as a branch of the cost step, not as a
separate mode — the confusion is that the branch is chosen by *the presence of a field in the
payload*, which nobody can predict, rather than by configuration, which everybody can read.

### 1.2 The collision is not between two features

The ticket describes the collision correctly:

- a limited task is refused with `cost_coverage_required` unless the tenant sets
  `require_cost_card_coverage` (`risk_service.py:209-212`);
- strict coverage demands a cost card **for every metric even when the caller supplied the aggregate
  cost** (`pricing_service.py:114-119`);
- so the two coexist only if the caller sends no quantities at all.

Read as a conflict between "provider-supplied cost" and "task limits", the fix would be a special
case: teach the coverage check to accept caller cost. That fix is available, small, and wrong.

**The collision is a symptom.** The flag exists because of a real invariant — *a COGS ceiling standing
over an event of unknown cost would silently count zero, and a ceiling that silently counts zero is
not a ceiling.* The defect is that this invariant was implemented as **a promise the tenant makes**
rather than **a property the system has**. A promise cannot distinguish "the caller told us the cost"
from "nobody knows the cost", because it was never about the caller at all.

#138 already began dismantling it — *"`require_cost_card_coverage` … Structural now — cost-plus
requires resolvable COGS by construction, so the opt-in flag has no job on that path → #146"* — and
#145 finished the job by making every money-moving quantity a declared thing. What remains for this
document is not to resolve the collision but to **notice that it has already dissolved**, and to say
what replaces the invariant the flag was protecting. §6 does that; §5 supplies the replacement.

### 1.3 What the ticket got right, and this document keeps

The ticket's instinct that caller-supplied **billed** cost is "a hole to close" is correct, and §8
closes it — though for a reason the ticket does not give, and by deletion rather than by discipline.

---

## 2. Two costing modes, declared on the Event Type

### 2.1 The ruling

Every Event Type declares exactly one **costing mode**:

| Mode | Meaning | Where COGS comes from |
|---|---|---|
| **calculated** | UBB works the cost out | declared measurements × Cost Rates (#138, #145) |
| **reported** | the supplier tells us | a cost carried on the event |

The mode is **a property of the Event Type, not of the event**, and it is **exclusive** — no Event
Type is both. The mode is declared when the Event Type is registered, exactly like its measurements,
and is readable by anything that needs to know what an event of that kind will cost *before one
arrives*.

Everything downstream of COGS is **identical between the two modes**: margin, the price ladder, the
task ceiling, margin reporting, the platform fee, invoicing. A `reported` Event Type is not a
"pass-through" event and does not bypass pricing — it bypasses **cost derivation only**.

### 2.2 Why declaration, and not the payload

Three arguments, in decreasing order of force.

**(a) It is the only option under which a spend ceiling can promise anything.** A ceiling accepted at
task start is a promise about events that have not happened yet. If any event may or may not carry its
own cost, the start gate cannot know whether the events it is about to govern will be costable — which
is exactly why today's code has to ask the tenant to promise it (§1.2). Once the mode is declared, the
question "is every event this task can attribute costable?" is answerable **from configuration, at
start time, with no promise from anyone**.

**(b) The one working analogue in the prior art does it this way.** Lago's `precise_total_amount_cents`
is read by exactly one *charge model* (`dynamic`), i.e. by configuration, not by payload inspection —
and Lago's docs frame it as a property of the thing being priced: *"Select the dynamic charge model if
you calculate the price manually or if prices fluctuate during a billing period (e.g., for SMS APIs,
AI models, etc.)"* (research Q4, **high** confidence, read in source). The research's own
recommendation §5 names the configuration shape as the part worth copying.

**(c) The Code Builder cannot generate a call it cannot predict.** Map #137's destination is
"correct, self-explaining integration code". A field that *may* be sent on *any* event, and whose
presence silently changes where money comes from, cannot be generated correctly — the generator would
have to emit both branches and let the developer choose, which is the opposite of self-explaining.
A declared mode generates one call shape per Event Type. This is the same argument #145 used to
justify declaring measurements at all, and it applies with more force to money.

### 2.3 Exclusive per kind — and where the "both" case actually goes

A tempting third option was rejected: let a kind be `calculated` normally, but let a reported cost win
when it happens to arrive. It is rejected for two reasons.

**It reintroduces exactly the failure the research warns about.** Lago resolves supplied-vs-calculated
by silent precedence: send both and whichever the configured charge model reads wins, with no error
anywhere. The research's verdict is blunt — *"A misconfigured charge model turns provider-supplied
cost into a no-op, with no error anywhere. Lago validates the shape of the configuration, not the
coherence of the data against it. If we adopt this pattern, that is the failure mode to design
against."*

**It makes two events of the same kind incomparable.** Under a per-event race, a margin report
covering one Event Type mixes two derivations with no way to tell which produced which figure, and a
ceiling's guarantee weakens from "will bind" to "will probably bind".

The genuine need behind "both" — *the supplier tells us the real number later* — is real and is
served properly by **corrections** (§9), which is where a late-arriving authoritative number belongs
anyway. A number that arrives after the fact is a correction whether or not the event's mode allowed
it at the time.

In practice the choice is per-kind regardless: a supplier's API either returns a cost on that call or
it never does. #145 already established that operational variants of the same work may legitimately be
separate Event Types, which covers the case of one provider exposing both a cost-bearing and a
cost-less endpoint.

### 2.4 Quantities survive on reported-cost events

**A `reported` Event Type still declares measurements, and its events still carry them.** They are
recorded, filterable, groupable and reportable exactly as on a `calculated` kind — cost per token,
tokens per job, volume trends, all of it. They simply never derive the money, because the supplier
already did.

This is the ticket's headline damage, repaired. The current code forces the choice — caller cost plus
strict coverage plus any `usage_metrics` at all is a `PricingError` — so a tenant who reports cost
must send no quantities, "losing the very breakdown that makes the event useful".

It does not strain #145's rule that *only declared measurements may move money*. Nothing here moves
money: the reported cost **is** the money, arriving as an assertion rather than being derived. #145's
rule forbids undeclared things from *becoming* money through a rate; it does not require that all
money be derived.

Two consequences worth stating plainly:

- On a `reported` kind, no measurement is a costing input, so `required_for_costing` (#145) has no
  meaning there and Cost Rates for that Event Type are not merely unnecessary but **meaningless** —
  configuring one is a tenant error worth surfacing.
- Unit economics remain computable on reported-cost kinds by division (reported cost ÷ recorded
  quantity), which is how a tenant sanity-checks a supplier's own arithmetic. That is a *reporting*
  capability, deliberately not a *validation* one (§7.1).

---

## 3. One rule for everything UBB cannot compute: preserve, flag, remediate

### 3.1 The ruling

**No event is ever refused because UBB cannot work out what it cost.** In every such case:

1. the event is **recorded**, with its measurements, dimensions, attribution and timestamp intact;
2. its cost is recorded as **unknown** — `costing_status = unresolved`, cost **null**, never zero;
3. the **cause** is raised to the tenant once (§11), with the event queued for remediation;
4. when the cause is fixed, the event is **replayed at its original timestamp**, resolving against the
   Cost Rate that was effective *then* (#138's effective-dating), and every total it belongs to is
   corrected.

This governs all of: a missing Cost Rate for a required measurement; an event whose effective time
precedes the earliest Cost Rate; a malformed or unmappable measurement; and — per the owner's ruling —
a `reported` event that arrives **without** its cost.

### 3.2 Nothing is refused, including the contradiction cases

The rule was tested in grilling against both directions of payload/configuration contradiction, and it
held in both:

| Case | Verdict |
|---|---|
| `reported` kind, event arrives with **no** cost | recorded `unresolved`, alerted, remediable |
| `calculated` kind, event arrives **with** a cost | recorded, costed the declared way; the sent number is stored as **the caller's claim** and flagged |
| `calculated` kind, a required measurement has **no Cost Rate** | recorded `unresolved`, alerted, remediable |
| event of an **undeclared Event Type** | **quarantined** — unchanged from #138, see §3.4 |

The owner's reasoning for the first row, which overrode an earlier "refuse loudly" answer, is the
governing principle of this section: a preserved-and-flagged event beats a lost one, and the failure a
caller cannot fix mid-run must not destroy a usage record.

### 3.3 Why preservation beats refusal

The decisive case, in the owner's words:

> a job may contain 1,000 provider calls and only one incorrectly configured event: 999 events →
> costed normally; 1 event → accepted → `costing_status: unresolved` → COGS unknown, never zero; job →
> continues running.

Refusal fails this case three ways. The refused event's *usage* is lost even though nothing was wrong
with it — the measurements, the attribution and the timing were all fine, only the price list was
incomplete. The caller who receives the error is typically an agent mid-run that cannot fix a tenant's
Cost Rate configuration and can only retry into the same wall. And the loss is silent in the way that
matters most: a refused event leaves *no* record, so the tenant's COGS is understated with nothing
anywhere indicating that it is.

Preservation inverts all three: the usage survives, the money is explicitly marked unknown rather than
implicitly counted as zero, and the gap is visible and countable. **The record is complete about what
happened and honest about what is not yet known** — which is the strongest available position, and one
no platform in the research achieves.

### 3.4 `unresolved` is not `quarantined` — the line matters

#138 established quarantine for unknown event types, and it would be easy to reach for it here. The
two are complementary, not competing, and the line between them is:

| | Quarantine (#138) | Unresolved (this document) |
|---|---|---|
| What is missing | UBB cannot **place** the event — no declared Event Type | UBB can place it but cannot **price** it |
| Is it recorded as a usage event? | **No** — held outside the record until registered | **Yes** — a first-class event with a null cost |
| Does it appear in usage reports? | No | Yes, with cost unknown |
| Does it count toward a task's ceiling? | No | It makes the ceiling `indeterminate` (§5) |
| Resolution | register the type, replay at original timestamp | fix the rate/mapping, replay at original timestamp |

An event whose Event Type is unknown has no attribution, no validated measurements and no declared
meaning — there is nothing to record it *as*. An event whose type is known has all of that, and only
its money is missing. Recording the second as though it were the first would throw away everything UBB
does know.

### 3.5 The caller's claim: beating Lago's failure honestly

When a `calculated` kind receives a cost anyway, the recorded COGS is **UBB's own figure** — that is
what the Event Type declares, and the declaration wins. The sent number is not discarded: it is stored
beside the event as **the caller's claim**, and the disagreement is surfaced.

This is the point where the design departs from Lago on purpose. Lago drops the number silently; the
research names this the failure mode to design against, and notes that *"validating coherence at the
door — rejecting an event that carries both a supplied cost and quantities the configuration would
price — has no prior art, which makes it an opportunity rather than a risk."* This document takes the
opportunity but **not** by rejecting: it keeps the number and shows the disagreement, which is
strictly more useful than an error. Two independent COGS figures for the same event is exactly the
evidence a tenant needs to find a mis-set Cost Rate — the error tells them something is wrong, the
stored pair tells them *what*.

The owner's caveat — *"the provided number is therefore the bonus to be taken, flagged and recorded if
it's easy to do and implement"* — is satisfied cheaply: with one request shape carrying one optional
cost field, a surplus cost is a null-check on a value already in the payload. There is nothing to go
hunting for. **If the implementation ever finds this expensive, the claim record is the part to drop,
never the declared-mode costing.**

---

## 4. Unknown cost is never zero — the column must become nullable

`UsageEvent.provider_cost_micros` is `BigIntegerField(default=0)` (`usage/models.py:41`). Under this
document it must become **nullable**, with null meaning *not yet known* and `0` meaning *this
genuinely cost nothing* (a cached response, a free-tier call). Both are real states and they must not
share a representation.

This is the same defect #141 identified on the revenue side and handed to #147:

> `billed_cost_micros` non-nullability (`usage/models.py:41-42`) — the "unknown vs zero" defect (§1.2)
> belongs to #147.

**The two halves are now split cleanly: #146 owns the cost column, #147 owns the revenue column**, and
the fix is the same shape on both. #138's "missing cost is never zero" becomes enforceable rather than
aspirational — today it cannot be enforced, because the column has no way to say "unknown".

Every consumer that sums `provider_cost_micros` must therefore handle null explicitly rather than
inherit SQL's `SUM` semantics by accident. That is not a burden to be minimised — it is the point.
A sum over a set containing an unknown is itself unknown, and §5 is what that means for the one
consumer where it changes behaviour rather than presentation.

---

## 5. Spend ceilings gain a third state

### 5.1 The ruling

A task's ceiling state is one of three, not two:

| State | Meaning |
|---|---|
| `within_limit` | every relevant event is costed, and known COGS is below the ceiling |
| `limit_reached` | known COGS has reached the ceiling |
| **`indeterminate`** | one or more events have unresolved COGS, so the ceiling **cannot currently be guaranteed** |

The owner's worked example is the specification:

```
known COGS:        $4.20
unresolved events: 1
cap:               $5.00
cap status:        indeterminate
```

`indeterminate` is **not** a variety of "within limit". Under the old model this task reports as
comfortably under its ceiling, and that report is a lie of exactly the kind the deleted flag existed
to prevent — the difference being that the lie now has a name, a count, and a queue of work that
clears it.

### 5.2 One bad event never kills a good job

Enforcement does **not** fire on `indeterminate`. A job continues running with unresolved events in
it, per §3.3's 999-of-1000 case. The alternative — stopping a job because one call out of a thousand
hit a configuration gap — converts a reporting problem into an outage, and would make a single
mis-registered measurement a tenant-wide kill switch.

This is a deliberate, named trade: **UBB will not stop a job it cannot fully cost, and will not
pretend it can.** The protection is honesty plus urgency (§11), not enforcement. A tenant who wants
enforcement over unknown cost has the tools to get it — the alert, the count, and the ability to stop
their own work — and UBB does not make that choice for them.

### 5.3 Replay: the running case and the ended case

When a fix lands and held events replay:

- **Job still running** — the corrected total is added, and if it now reaches the ceiling,
  **enforcement may stop it at that point**. This needs no new mechanism: it is the existing crossing
  race inside `TaskService.accumulate_cost` (`apps/platform/tasks/services.py:56`, `_crossed_limit` at
  `:128-146`), reached by a replayed event instead of a live one.
- **Job already ended** — the retrospective over-ceiling fact is **recorded for reporting**, and the
  job's historical lifecycle is **not rewritten**. It is not retroactively `killed`; no stop signal
  fires; no event is re-dated.

The second rule follows from #140's *terminal is terminal* and from #139's finding that no re-invoice
path exists. A terminal state records what the system did at the time, and the system did not stop
that job. Rewriting it would forge an enforcement action that never happened, and would silently
contradict any `task.completed` webhook already delivered. The honest record is: this job ended
normally, and we later learned it exceeded its ceiling.

---

## 6. The coverage collision, dissolved

### 6.1 What is deleted

| Thing | Where | Why it goes |
|---|---|---|
| `Tenant.require_cost_card_coverage` | `tenants/models.py:71` | nothing left for a tenant to promise (§6.2) |
| `cost_coverage_required` start refusal | `risk_service.py:209-212` | the condition it tests is now structurally true |
| the strict-coverage check on the caller-cost path | `pricing_service.py:114-119` | the ticket's collision, at its source |
| the `units > 0` + no-metrics strict check | `pricing_service.py:126-129` | subsumed by declared Event Types (§6.2) |
| the strict-coverage raise on the computed path | `pricing_service.py:142-143` | replaced by `unresolved` (§3) |
| `PricingError` | `pricing_service.py:11` | **all three raise sites are the above** |
| `Unpriceable` + the estimate wrapper | `pricing_service.py:15-20`, `:243-244` | raised "exactly where `price` raises `PricingError`" — nowhere now |
| the async sync-fallback branch + its per-item idem unwind | `ingest_accept.py:580-598` | its only trigger is `Unpriceable` (§6.3) |
| the enable-time "no cost cards" guard | `tenant_endpoints.py:541-546` | guards a flag that no longer exists |
| the flag on the tenant settings read/write surface | `tenant_endpoints.py:456`, `:584-585`; `schemas.py:961`, `:989` | ditto |
| the flag's sandbox copy | `sandbox_service.py:45` | ditto |
| `cost_coverage_required` from the refusal vocabulary | `schemas.py:50-51`; `ubb-sdk/ubb/client.py:143` | ditto |

### 6.2 Why the flag has no job left

The invariant the flag protects is *a ceiling must never stand over an event of unknown cost while
silently counting it as zero.* Under #138, #145 and this document, that invariant is now delivered by
construction, in three parts:

1. **Every event has a declared Event Type**, or it is quarantined and never reaches a task total at
   all (#138). This alone kills the `units > 0` + no-`usage_metrics` check, which exists precisely
   because a free-text event with no metric name had nothing to resolve a rate against — a state that
   can no longer occur.
2. **Every declared Event Type has a declared costing mode** (§2), so a task's costability is knowable
   at start time from configuration.
3. **Where cost is nonetheless unknown, it is recorded as unknown and the ceiling says
   `indeterminate`** (§4, §5) — the silent-zero the flag was preventing cannot happen, whether or not
   any tenant opted in.

A tenant-facing switch that promises a property the system now guarantees is a switch that can only
ever be wrong. Worse, this one is *load-bearing in the wrong direction*: because it gates task
creation, a tenant reporting supplier costs must enable a flag about **cost cards they deliberately do
not have**, and today enabling it is itself refused unless they first create at least one cost rate
card (`tenant_endpoints.py:541-546`). The flag does not merely fail to help such a tenant — it stands
between them and the feature.

### 6.3 A whole failure path goes with it, not just a check

The three `PricingError` raise sites are the *only* three in the codebase, and they are all
strict-coverage. `Unpriceable` exists solely to mirror them into the async path — its docstring says
so: *"Raised by `PricingService.estimate` exactly where `price` raises `PricingError` (they share one
compute spine, #112), so the sync fallback surfaces the real pricing error to the caller."* And its
only consumer is `ingest_accept.py:580`, whose fallback re-runs the item synchronously and then, on
rejection, unwinds that item's idempotency key through `_ingest_idem_unwind` to avoid burning it
(`:583-598`).

So deleting the flag deletes: three checks, one exception class, one exception wrapper, one
accept-time fallback branch, one per-item idempotency unwind path, and the reasoning burden of keeping
accept-time estimation and settle-time pricing agreeing about *failure* as well as about amounts.

**This was not visible from the ticket and is a material simplification.** It is also a correctness
gain: the sync-fallback path is one of the subtlest pieces of the ingest pipeline — its own comment
runs thirteen lines explaining why a burned idempotency key would cause "a money-gate bypass" and "a
false incident alert" — and it exists only to serve a flag that should never have existed. Under this
document, an unpriceable event is not an error at all, so **the async and sync paths converge**: both
record the event, both mark it `unresolved`, and neither needs an escape hatch.

The estimate path keeps its job: it still returns an estimate for the hold. An event whose cost cannot
be resolved yields **no** estimate rather than a zero one — the same unknown-is-not-zero rule (§4)
applied at accept time, and a question for the hold mechanism (#150) rather than for this document.

### 6.4 The residual risk, named

Deleting the flag does not make unknown cost impossible; it makes it **visible**. A tenant with a
misconfigured Cost Rate still has a ceiling that does not bind. The difference is that the ceiling now
says so, in a named state, with a count and an alert, instead of reporting a comfortable number.

That is a genuine reduction in enforcement strength compared to the *intent* of strict coverage, and
it is accepted deliberately. The comparison that matters is not against the intent but against the
behaviour: today a tenant either opts in and cannot use supplier-reported cost at all, or opts out and
gets a ceiling that silently counts unknown costs as zero with no indication anywhere. Both are worse
than an honest `indeterminate`.

---

## 7. Validation: what UBB can check, and what it must not pretend to

### 7.1 Shape, not plausibility

A reported cost is validated for **shape and coherence only**: it is an integer, non-negative,
denominated in the tenant's currency (#145: USD-only in v1), within the shared bound (§7.2), and
arriving on an Event Type declared `reported`.

**No plausibility check gates a reported cost.** Comparing it against the tenant's own rates was
considered and rejected: on a `reported` Event Type there are no Cost Rates to compare against — that
is the entire point of the mode — so any band would have to be inferred from the Event Type's own
history, which is anomaly detection wearing validation's clothes.

The decisive argument is the consequence of a false positive. A validation rule that rejects a
surprising cost either destroys a real usage record (§3.3) or, worse, refuses the genuinely unusual
event — the retried job, the outsized batch, the price change the tenant has not configured yet — which
is precisely the event whose cost most needs recording. **A rule that fails hardest exactly when it
matters most is not a safety feature.** Anomaly detection over recorded costs remains available later,
as reporting, where a false positive costs a second look instead of a lost record.

### 7.2 One bound for every cost figure

#142 parked this here: caller-supplied cost is capped at `le=999_999_999_999`
(`api/v1/schemas.py:69-70`) — about 1,000,000 currency units — while a rate-card-computed cost is
bounded only by `BigIntegerField` (~9.2 × 10¹² currency units). The asymmetry is unexplained and
indefensible: the same $2,000,000 cost is accepted if UBB computes it and refused if a supplier
reports it.

**One bound applies to every cost figure in the system, set by what the storage can hold, regardless
of derivation.** A hard-coded per-event ceiling is the wrong instrument for typo protection: it is
UBB's guess at what is plausible for every tenant, currency and workload at once, and UBB already
offers the right instrument — a spend ceiling the tenant chose, on the job, which catches the extra
zero by stopping the work rather than by discarding the record of it.

### 7.3 Zero is legal; unknown is not zero

An explicitly reported `0` is valid and meaningful — a cached response, a free-tier call, an included
request. It is unambiguous **because** unknown has its own representation (§4). Under the current
model these are the same value, which is why "missing cost is never zero" could be stated by #138 but
not enforced.

### 7.4 What UBB fundamentally cannot check

**UBB never sees the supplier's invoice.** No amount of validation makes a reported cost *true*; it
can only make it well-formed. This is the same limit #145 recorded for `source_path` — *"UBB never
sees the provider response, so it can check declared / typed / non-negative / required-and-present but
never that a number came from the right provider field"* — and the same conclusion follows: the
defence against a plausible wrong number is **code generation, not validation** (the Code Builder),
plus the reporting that makes a wrong number visible (unit economics per §2.4, the claim record per
§3.5, and margin that moves when it should not).

The honest consequence is that **a reported cost is a tenant assertion and every surface that reports
COGS must be able to say so.** The derivation is not provenance trivia — it is the difference between
a number UBB computed from configuration it can show you and a number it was handed. Both are
legitimate COGS; only one is auditable by UBB.

---

## 8. Caller-supplied billed cost is deleted

### 8.1 The ruling

`RecordUsageRequest.billed_cost_micros` (`api/v1/schemas.py:70`) and its handling
(`pricing_service.py:146-148`, `prov["price_source"] = "caller"`) are **removed**. There is **no
caller rung on the price ladder**, and no per-event mechanism for asserting revenue. The field remains
on *responses*, where it reports what UBB determined.

Revenue comes from UBB alone: a margin over cost, an explicit sell rate, or #139's fixed price for a
whole job.

### 8.2 Cost is observed, price is decided

The asymmetry with §2 is deliberate and is the cleanest principle in this document.

**A cost is an observation of a fact owned by someone else.** The supplier decided it; the tenant is
relaying it; UBB could in principle have derived the same number from rates and is accepting a shortcut
to a fact that already exists in the world.

**A price is a decision owned by the tenant, which they have asked UBB to hold.** The plan catalog,
the policy book, the markup, the fixed price — that is what a tenant configures UBB *for*. Asserting a
price per call does not relay a fact; it bypasses the decision the tenant asked UBB to make, per call,
invisibly, and leaves UBB's configured answer and the tenant's asserted answer permanently in
disagreement with no way to tell which is authoritative.

So the two are not symmetrical, and the model should not pretend they are. Relaying an observation is
legitimate; overriding your own decision one call at a time is not a feature, it is a bypass.

### 8.3 What a tenant who prices elsewhere does instead

Three paths remain, and they cover the cases:

- **A sell rate on the Event Type's policy line** — the tenant's own price, configured once rather
  than repeated per call.
- **#139's fixed price for a whole job** — for work sold as a unit, which is where "I priced this
  myself" usually really means "I sold this job for £X".
- **Margin over cost** — including over a *reported* cost, which is the combination this document
  makes work and which serves the resale case directly.

The cost of deletion is real and worth naming: a tenant whose per-event prices are genuinely computed
by an external system, and which cannot be expressed as a rate or a job price, must now configure
something in UBB. That is a deliberate trade of flexibility for one source of revenue truth.

### 8.4 What #147 inherits

#147 owns markup and price precedence. It inherits a **closed** ladder: every rung is UBB-configured,
and it does not need to decide where a caller-supplied price ranks, because there is no such thing.
Combined with #145's answer to its parked question (no price-side conditioning on Grouping Fields) and
#139's terminal fixed price, the price side is now bounded on three sides.

---

## 9. Corrections

### 9.1 A correction is a new entry, never an overwrite

When a supplier later publishes a different cost for an event already costed, the original event is
**never modified**. A linked **cost correction** records the difference, dated when the correction
arrived and attributed to the original event, and downstream consumers read the pair.

Three independent reasons, any one sufficient:

- `UsageEvent` is declared *"Immutable usage event record"* (`usage/models.py:9`), and the past-limit
  stop context is already documented as *"written once … immutable with the event"*.
- **The period may be closed and the invoice sent.** #139 established that *"no re-invoice path exists
  anywhere — post-freeze correction is a refund or a manual adjustment."* A rewritten past event would
  put the record permanently at odds with an invoice already delivered, with nothing recording that it
  had ever said otherwise.
- **#142's reproducibility.** A recompute must apply the same rounding to be byte-comparable; that is
  impossible if the inputs are mutable.

### 9.2 Completing a blank is not a correction

Resolving an `unresolved` event (§3.1) writes a cost where there was none. That is **not** a mutation
in the sense §9.1 forbids, and the distinction is load-bearing:

- An `unresolved` event **asserted nothing** about its cost. Writing the resolved value **completes**
  the record.
- A costed event **asserted a number**, and that number may already have been invoiced, reported and
  reconciled. Changing it **contradicts** the record.

Completing a blank cannot contradict anything downstream, because nothing downstream was ever given a
number to rely on — which is exactly why null-not-zero (§4) and `indeterminate` (§5) had to exist
first. **The nullable column is what buys the in-place resolution.** Without it, resolution would be a
correction, and every configuration gap would generate a correction pair forever.

### 9.3 A correction never rewrites a terminal job's lifecycle

Per §5.3, and by the same reasoning: corrections change what the record *says*, never what the system
*did*.

### 9.4 Period close: on time, billed next period

A period **closes on time** with what is known. Unresolved events are **excluded from the invoice**,
counted and reported so the gap is visible, and once resolved they appear on the **next** invoice,
still attributed to when they actually happened.

This matters more than it first appears, because of an interaction the ticket does not raise. Under
#147's direction, **margin over cost becomes the default price mechanism** — so on a markup-priced
Event Type an unknown cost means an unknown *price*, and an unresolved event is not merely
unmeasurable, it is **unbillable**. Period close is therefore the point where §3's tolerance meets real
money leaving the building.

The rule holds anyway, for the reason #139 supplies: there is no re-invoice path, so blocking the
close to wait for completeness buys nothing — it converts one tenant's configuration gap into every
invoice for that tenant being late, and puts maximum pressure on an override at exactly the wrong
moment. Deferring to the next period needs no new machinery, is how late-arriving usage is handled
everywhere, and keeps the governing rule intact: **a configuration gap delays money; it never destroys
it and never holds everything else hostage.**

The excluded amount must be **reported at close**, not merely omitted — #142's precedent, where a
foreign-currency Stripe mirror is *"flagged and excluded, with the excluded count reported"*, rather
than silently dropped.

---

## 10. Fixed-price ceilings stay optional

#139 parked this here: *"Whether the ceiling-as-fraction-of-price should be mandatory for fixed-price
work, rather than a default, is left open for #146."*

**Decided: optional, as for any other job.** A ceiling is offered, defaults to a tenant-set fraction of
the price per #139, and may be cleared or omitted.

The argument for making it compulsory was put and rejected. It is worth recording, because the risk is
real and the decision accepts it knowingly: on a metered job, cost and revenue move together, so a cost
overrun usually implies a revenue overrun. On a fixed-price job **revenue is frozen at the start and
cost is the only thing that can move — in one direction.** It is the one case where "uncapped" means
"unbounded loss".

The owner's ruling is that this is the tenant's commercial risk to take, and that fixed-price jobs
should not be a special case in the limit model. The mitigations are the ones this document already
requires: the ceiling is defaulted rather than absent, margin per job is reportable, and `indeterminate`
(§5) means a fixed-price job with unresolved costs cannot silently report a healthy margin — which is
where an unnoticed loss on frozen revenue would otherwise hide.

---

## 11. Alerting: the condition, not the occurrence

**One notification per distinct cause, not per affected event.** The cause is the tuple that must be
fixed — tenant + Event Type + measurement + missing thing — raised the first time it occurs and
suppressed thereafter until it clears. Alongside it, two standing surfaces:

- a **live count** of unresolved events and of open causes;
- a **remediation queue** — the causes, each with its affected-event count, that a tenant works
  through.

A misconfigured Cost Rate can produce a thousand unresolved events in an hour, and a thousand
notifications for one fixable cause is how alerting gets muted — after which the design's entire
safety story is hollow, because "preserve and flag" degrades to "preserve". The tenant has **one**
thing to fix; they should receive one thing to read.

Alerting on the cause also gives remediation a natural completion: the cause clears, its held events
replay, the count returns to zero, and affected ceilings leave `indeterminate`. That closed loop is a
requirement of this decision, not a nicety — it is the whole of what replaces the deleted flag.

The delivery mechanism (outbox event, webhook, console surface, or all three) belongs to the webhook
catalog work; what is decided here is the **granularity** and the **closed loop**.

---

## 12. Answers to the ticket's six questions

**1. How is provider-supplied cost represented?**
As a **declared costing mode on the Event Type** — `calculated` or `reported` — never a source flag on
the event, a distinct event shape, or a property of a pricing rule. The cost still travels on the
event; what changes is that its presence is *declared in advance* rather than discovered in the
payload (§2).

**2. Is it mutually exclusive with calculated pricing, and enforced at which level?**
**Yes, exclusive, at the Event Type level.** Not the event (unpredictable), not the task (an unrelated
grouping), not the tenant (too coarse — one tenant legitimately has both kinds). The "both" case is
served by corrections (§2.3, §9).

**3. What makes a submitted cost trustworthy?**
**Shape and coherence, and nothing more.** Non-negative, integer, tenant currency, one shared bound
(§7.2), on a `reported` Event Type. No range check against the tenant's own rates, because a
`reported` type has none and a false positive destroys a record (§7.1). UBB never sees the supplier's
invoice, so the real defences are code generation and reporting, not validation — and every COGS
surface must be able to say which derivation produced a figure (§7.4).

**4. Does caller-supplied billed cost survive?**
**No. Deleted** — it is a hole, and it is closed rather than disciplined. Cost is observed, price is
decided (§8).

**5. Resolve the coverage collision.**
**The flag, the refusal and their entire failure path are deleted**, because #138 and #145 already
made costability structural — a tenant-facing promise about a system guarantee can only ever be wrong,
and this one actively blocked the combination it was asked about. A ceiling trusts a reported cost
exactly as it trusts a computed one; where cost is genuinely unknown, the ceiling reports
`indeterminate` rather than a comfortable lie (§5, §6).

**6. Reconciliation.**
**A correction entry beside the original, never an overwrite** (§9.1) — with the deliberate exception
that *completing* an unresolved blank is not a correction (§9.2). Corrections never rewrite a terminal
job's lifecycle (§5.3, §9.3); a still-running job may be stopped by a replay; periods close on time and
unresolved events bill next period, dated to when they happened (§9.4).

---

## 13. What each existing thing becomes

| Today | Becomes |
|---|---|
| `RecordUsageRequest.provider_cost_micros` (`schemas.py:69`) | **Kept**, meaningful only on a `reported` Event Type; on a `calculated` one it is recorded as the caller's claim and flagged (§3.5) |
| `RecordUsageRequest.billed_cost_micros` (`schemas.py:70`) | **Deleted** from the request (§8) |
| `le=999_999_999_999` on both (`schemas.py:69-70`) | **Replaced** by one shared bound over every cost figure (§7.2) |
| `prov["cost_source"] = "caller"` (`pricing_service.py:110`) | **Kept in substance, re-founded** — provenance of a *declared mode*, not of a payload branch; naming → #154 |
| `prov["price_source"] = "caller"` (`pricing_service.py:148`) | **Deleted** with the field (§8) |
| `_compute`'s caller-cost branch (`pricing_service.py:108-119`) | **Re-founded** as the `reported` mode; the strict-coverage check inside it is deleted (§6.1) |
| `_compute`'s strict checks (`:126-129`, `:142-143`) | **Deleted** — replaced by `costing_status = unresolved` (§3) |
| `PricingError`, `Unpriceable` (`pricing_service.py:11`, `:15-20`, `:243-244`) | **Deleted** — no raise sites remain (§6.3) |
| `ingest_accept.py:580-598` sync fallback + idem unwind | **Deleted** — its only trigger is gone; accept and settle converge (§6.3) |
| `Tenant.require_cost_card_coverage` (`tenants/models.py:71`) and its full surface | **Deleted** (§6.1) |
| `cost_coverage_required` (`risk_service.py:211`, `schemas.py:50-51`, SDK docstring) | **Deleted** from the refusal vocabulary (§6.1) |
| `UsageEvent.provider_cost_micros` (`usage/models.py:41`) | **Nullable** — null is unknown, `0` is free (§4) |
| `UsageEvent.billed_cost_micros` (`usage/models.py:42`) | **Unchanged here** — the revenue half of the same defect stays with #147 (§4) |
| Task ceiling state (two-valued, implicit) | **Three-valued**: `within_limit` / `limit_reached` / `indeterminate` (§5) |
| — | **New:** costing mode on the Event Type; `costing_status`; the caller's-claim record; the cost correction entry; the cause-level alert + remediation queue |

---

## 14. Constraints this imposes on other tickets

- **#147 (markup and price precedence)** — inherits a **closed** price ladder with no caller rung
  (§8.4), and keeps the revenue half of the unknown-vs-zero defect (§4) — now with a decided shape to
  mirror on the cost side. It must also answer what a markup over an **unresolved** cost yields: this
  document says unbillable-until-resolved and bills next period (§9.4), and #147 owns whether that
  produces a null price, no line, or a deferred line.
- **#150 (spend limits re-modelled)** — must carry the **third state** as a first-class concept, not a
  display nicety, and decide what an accept-time **hold** does when no estimate can be produced
  (§6.3). #139's ceiling-as-fraction-of-price is **optional**, decided here (§10).
- **#148 (pricing versions)** — replay-at-original-timestamp (§3.1) makes historically accurate rate
  resolution **load-bearing for correctness**, not only for reporting: an event resolved late must
  resolve against the rate effective when it happened, or the fix silently mis-costs it. Cost
  corrections (§9.1) are also a new thing versioning must reproduce.
- **#152 (task dashboard and reporting)** — must show `indeterminate` distinctly from `within_limit`,
  surface the unresolved count per job, and host the remediation queue (§11). A dashboard that renders
  `indeterminate` as "under limit" reintroduces the exact lie this document removes.
- **#151 (charging modes)** and **#153 (analytics re-alignment)** — every COGS surface must distinguish
  **computed / reported / unresolved**, and must never sum a null as zero (§4, §7.4).
- **#154 (vocabulary)** — names owed for: the two costing modes; `costing_status` and the value
  `unresolved`; the third ceiling state; the caller's-claim record; the cost correction entry. Note
  `cost_source` predates all of this and should be reconciled with the mode noun rather than kept
  beside it.
- **#165 (splitting UsageEvent's measurement record from its economic posting)** — strengthened. §2.4
  (measurements recorded but non-monetary on a `reported` kind) and §4 (a measurement record that is
  complete while its posting is unknown) are the seam #165 names, arriving from a second direction.
- **#155 (onboarding)** — a tenant registering an Event Type must choose a costing mode; there is no
  defensible default, since guessing wrong silently mis-costs every event of that kind.
- **#156/#157 (Code Builder)** — generates one call shape per Event Type from its declared mode (§2.2),
  and is the primary defence against a well-formed wrong cost (§7.4).

---

## 15. Residue, flagged not buried

- **No time limit on `unresolved` is decided.** An event can in principle stay unresolved forever if
  nobody fixes the cause, and its COGS never lands. §9.4 keeps the books moving regardless, but a
  tenant that ignores the queue accumulates permanently unknown cost. Whether an ageing threshold
  should force a decision — write off, estimate, or escalate — is deliberately left open; it is a
  policy question with no evident right answer, and inventing one here would bind #150 and #152
  unnecessarily.
- **`indeterminate` has no decided precedence against other ceiling states.** A job can be both
  `limit_reached` on known COGS and `indeterminate` on unresolved events. Known-and-over should
  dominate for *enforcement* (the ceiling has demonstrably been reached), but the *reported* state
  needs a rule → #150.
- **The claim record's schema is unspecified** (§3.5), and the owner explicitly rated it
  implement-if-cheap. It is the one piece of this decision that may be dropped without damaging the
  rest — everything else is load-bearing.
- **A `reported` Event Type with Cost Rates configured is a tenant error nobody currently catches**
  (§2.4). It should be surfaced at configuration time, but the mechanism is #148's or #155's, not
  decided here.
- **Deleting `PricingError` and the sync fallback (§6.3) removes machinery that guards a subtle
  money-gate bypass.** The reasoning is sound — the trigger is gone, so the guard is unreachable — but
  the implementation must confirm that no *other* accept-time rejection reaches that unwind path, or a
  burned idempotency key returns as a live defect. This is the highest-risk deletion in the document
  and should be its own implementation step with a test that survives the deletion.
- **The estimate path's behaviour on an unresolvable event is stated but not designed** (§6.3): no
  estimate, not a zero one. What the hold does with no estimate is #150's.
- **Migration for `require_cost_card_coverage` is not specified.** Tenants with it on today lose a
  guarantee they opted into; per map #137's clean-break constraint there is no deprecation dance owed,
  but they are exactly the tenants who cared, and they deserve telling.
