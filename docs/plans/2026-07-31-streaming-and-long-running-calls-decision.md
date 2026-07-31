# Streaming and long-running calls — one event is one operation, and the fast lane goes

**Resolves:** [#149](https://github.com/ashcochrane/ubb/issues/149) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-31
**Decided against:** `main` @ `b1af9dd`
**Evidence:** `ubb-platform/docs/plans/2026-07-03-async-ingestion-hard-stop-design.md` — the design
that built the fast lane, quoted here for its own goal statement, its own throughput ceiling, and its
own admission that the lane widens the enforcement bound.
`docs/spend-control-guarantees.md` — the published claim, the signal triad, and the locked launch
SLOs.
`docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch `research/pricing-model-prior-art`
@ `2f0ce4c`) and `docs/research/2026-07-29-code-builder-prior-art.md` (#144, branch
`research/code-builder-prior-art` @ `cf3232c`) — **thin on this subject and said so** (§1.4). #144's
finding that no surveyed vendor generates multi-call-site integration code is the one load-bearing
input.
**Builds on:** `docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — silence means dead, no
keepalive, *"available as a later addition if that proves too blunt in practice"*; both time windows
move onto the declared kind of work; exactly two call sites for the Code Builder to teach.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — *"event granularity is a pricing-accuracy
decision"*; more events means more roundings and sub-micro lines charging zero.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — partial reporting became
*expressible*, and *"whether it should be is #149's"*; attribute-based rate selection is deleted.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — cost is observed, price is
decided; an unresolvable cost yields **no** estimate rather than a zero one; the sync-fallback branch
is already deleted.
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — the per-event fixed uplift is
deleted **because this ticket was open**; `direct_event_price` is kept.
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the accept-versus-settle gap closes;
`Estimate.exact` is deleted; every event gains a receipt retained six years.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**This document repairs one merged decision and dissolves part of another.** §7 states exactly what of
#147 no longer stands unqualified and what of #148 loses its subject. Neither is a discovered defect —
both are consequences of a rule decided here that neither could have taken for itself, because both
named this ticket as the open question. They must be read together, and #154 should carry the
reconciliation into the ADR.

**No ADR yet, deliberately.** Same reasoning as #138 through #148: #154 is the single naming pass, and
this document retires one product flag, one endpoint family and one noun (§10). The ADR is owed
*after* #154 and should cite all nine decision documents.

---

## The decision in one paragraph

**A streamed call is not a metering concept, a long call is not a new kind of hole, and one event is
one provider operation.** The billable numbers arrive from every major provider in the final chunk, so
streaming never reaches UBB at all and is **struck as a thing to model**; what the ticket was really
pointing at is money spent while we are blind, and that is caused by reporting-after-the-fact — which
is universal — not by duration. So no new before-the-call mechanism is built; the blindness is written
down honestly and handed to #150 framed as **concurrent unreported work**, because ten workers each
ninety seconds into a call is the real exposure and elapsed time is not. The ticket's headline
question dissolves once the unit is defined: **an event records one complete operation, a fragment is
not a cheaper event but not an event at all**, which repairs #147 — it deleted a per-event fee partly
because nobody had said what one event was, then kept a per-event price with the identical exposure.
Granularity is therefore **declared, never improvised**: the tenant fixes the unit when they declare
the Event Type, so a voice session may be sold per session or per minute and both are honest, and the
same declaration that buys spend visibility during long work also buys liveness — which is why **no
keepalive is added**, with a silence window every usage event resets and an absolute maximum that
fires regardless. Finally, the **fire-and-forget ingest lane is deleted outright**. Its accuracy
advantage evaporated when #145 removed attribute rate-matching and #148 made estimation resolve at the
event's own date — the estimate *is* the price now — and what remains is a lane that protects wallets
identically and enforces job ceilings **later**, because its accept-time unit-cap was retired
unreplaced. Spend control loses nothing: hard floor, soft floor, job ceilings, stop verdicts, webhooks
and the patrol all live in the recording core or the start-gate, never in the lane. What is genuinely
given up is throughput headroom and one locked launch SLO, and that is stated rather than glossed.

---

## 1. The ticket's premise, corrected

### 1.1 Two problems wearing one name

The ticket is titled *"Streaming and long-running calls"* and treats them as one subject. They are two
subjects, and only one of them is UBB's.

**Streaming** means the developer's code receives the answer in pieces. But the values UBB bills on —
token counts — arrive from every major provider in one lump in the final chunk. From UBB's side a
stream therefore ends exactly like an ordinary call: there is one moment at which the quantities become
known, and it is at the end. The streaming-ness is a property of how the integration reads bytes, and
it never crosses the API boundary.

**Long-running** means the call takes a long time. That one is real, and it is the complaint underneath
the ticket: money is spent for ninety seconds while UBB is blind, and by the time it is reported it is
already gone.

These point at incompatible answers. If the subject were streaming, the design would be a way to report
one call in pieces. If the subject is long-running work, reporting in pieces buys nothing whatsoever,
because the numbers do not exist until the end either way — and the design question becomes one about
spend control, which is a different mechanism in a different ticket.

**Decision: streaming is struck as a thing to model.** UBB has no representation of a streamed call, no
lane for one, and nothing in the Code Builder that teaches one. The ticket is about long-running work.

### 1.2 Duration is not the cause of the overshoot

The second correction is sharper and it removes an entire class of candidate answers.

A 200-millisecond call and a 90-second call are **structurally identical**: both spend the money first
and report it second. A single expensive fast call blows a ceiling exactly as effectively as a slow
one. Duration introduces no new kind of hole, because report-after-the-fact is universal — it is the
property `docs/spend-control-guarantees.md` §1 already refuses to promise around:

> *"any such promise is dishonest for report-after-the-fact metering: UBB is not in your inference path
> and cannot un-spend a call already dispatched to your provider … the overshoot depends on **your**
> concurrency and **your** reporting cadence."*

That sentence already contains this ticket's answer. What long duration changes is **how much
accumulates in the dark**: during 90 seconds other workers begin their own calls, and none of them can
see each other's spend because none has reported. Ten workers at 90 seconds each, and every ceiling in
the system honestly reads zero for a minute and a half.

**The exposure is concurrent unreported work, not elapsed time.** That reframing is what §4 hands to
#150, and it matters because a mitigation aimed at duration would be aimed at the wrong variable.

### 1.3 What this rules out before it is proposed

Both obvious fixes fail against §1.1 and §1.2, and it is worth recording why so neither is reopened
without new information.

- **Report the call in pieces.** Impossible for the dominant case — the integration cannot report a
  token count the provider has not yet produced. #145 made partial reporting *expressible*; it did not
  make the numbers exist earlier.
- **Extend the fast lane's estimate-and-hold to cover it.** The ticket asks this directly. The hold
  fires when the *event arrives*, which for a long call is still the end. It exists so the caller is
  not blocked while UBB prices — a throughput device, not a latency one. Moving it before the call
  would require estimating output tokens before the model has produced them, i.e. holding against a
  guess about the half that actually costs money.

### 1.4 The prior art is thin here, and that is recorded rather than dressed up

Neither research document has meaningful coverage of this subject. #143's only streaming reference is
Metronome's *internal* pipeline restricting which aggregation types its streaming path supports —
about their architecture, not about modelling a streamed provider call. #144 has nothing on it at all.

That is itself informative in the same way #145 §2.2 found the prior art unanimous against
pre-declaration: all six surveyed platforms are billing engines fed by a customer's own event pipeline,
so *when* a provider call finishes is simply not their problem. It becomes a problem only because map
#137's destination generates the integration code that sits directly against the provider.

**The one load-bearing input is #144's finding that no surveyed vendor generates multi-call-site
integration code.** It is cited three times below (§3.3, §5.2, §6.7) and it is the reason every answer
here spends call sites reluctantly.

---

## 2. One event is one provider operation

### 2.1 The ruling

**An event records one complete provider operation. A fragment of an operation is not a smaller event;
it is not an event.**

This is the answer to the ticket's headline question — *one event, or many?* — and it arrives not as a
preference between two workable options but as a consequence of defining the unit. Half a call is not
an instance of the thing the tenant declared, so there is nothing for it to be an event *of*.

### 2.2 Why the question could not be left open

#147 §6.2 deleted `TenantMarkup.fixed_uplift_micros` and `Plan.fixed_uplift_micros`, giving three
reasons. The first, verbatim:

> **"'Per event' is not a stable unit.** #149 is open on whether one streamed provider call becomes one
> event or many. Under splitting, a per-event fee bills once per fragment — a rule whose output changes
> because an unrelated ticket changed the event granularity is not a priced term."

The same document keeps `direct_event_price` — *"$0.02 per event"* (#147 §2.1) — as one of the two
methods a pricing rule may declare. **A per-event price has exactly the property the per-event fee was
deleted for.** A tenant selling a call at 2p whose integration reports that call as five fragments has
charged their customer 10p, and no warning UBB could write makes that safe, because the tenant who
typed 2p is the person least likely to go looking for the reason it became 10p.

#147's deletion still stands — its second and third reasons (an uplift charges on genuinely free calls,
and it is a second number in a box that should hold one) apply to the uplift alone and are sufficient.
But its **first reason proves too much**, and #147 could not have resolved it, because it was waiting on
this document. §7.1 states the repair precisely.

### 2.3 Why defining the unit beats governing the splitting

The alternative was to permit splitting and manage its consequences with warnings. Three warnings were
already queued for that approach and none of them addresses the real injury:

- #142 §6.3 — more events means more half-up roundings and a real risk of sub-micro lines charging
  zero.
- #148 §14 — every event carries a validated receipt retained six years, so splitting multiplies
  receipts, not merely rows.
- #147 §13 — splitting no longer multiplies a flat fee, since the fee is gone.

All three describe *cost of splitting*. None describes *the tenant's own selling price silently
multiplying*, which is the consequence that actually reaches a customer's invoice. A warning regime
that omits the worst outcome is not a warning regime.

Defining the unit removes the failure instead of pricing it, and it is the definition a developer
already assumes: an Event Type named `gemini-api-call-flash-4.0` describes **a call**.

### 2.4 What this does not touch

**A failed or aborted operation is still one operation, and it is still reported.** A stream that dies
sixty seconds in has usually incurred real provider cost, and #146's rule governs it unchanged:
preserve, flag, remediate. Where the provider returns no usage block for an aborted stream, the event
is recorded with an `unresolved` cost — NULL, never zero, alerted once per cause, replayed at its
original timestamp. Nothing here creates an exception to that, and nothing here makes a failed
operation unreportable.

---

## 3. Granularity is declared, never improvised

### 3.1 The ruling

**The tenant fixes the unit when they declare the Event Type. The integration then reports exactly one
event per instance of that unit, and has no discretion.**

§2 says a fragment of an operation is not an event. This says which operation, and it is what makes §2
livable rather than restrictive.

### 3.2 The mechanism already exists

Work that accrues money continuously — a thirty-minute live voice session billed per second of audio, a
long transcription billed per minute — appeared at first to be the price of §2, reportable only once at
the end. It is not, because #145 already put the choice in the tenant's hands.

#145 §6.1 established that operational variants are **separate Event Types**, not modes on one type:

> *"Standard versus batch execution is a **different operation**, and the integration knows which one it
> performed *before* it emits the event."*

The same machinery answers this. A tenant may declare either:

```
EventType  realtime-voice-session      → one event when the session ends
EventType  realtime-voice-minute       → one event per minute, sixty per hour
```

Both are honest. Both make a per-event price mean exactly what it says, because the price attaches to
the **declared** unit. Neither requires a new entity, a new field or a new call site — it is the
declaration #145 already requires, used for its stated purpose.

### 3.3 Why the choice sits at declaration and not at reporting

This is the load-bearing half of the rule.

If the integration chose granularity at reporting time, "per event" would remain unstable no matter how
carefully §2 were worded — a deploy that changed a loop would change what a customer pays. Fixing the
unit at declaration makes the price a property of a **declared, versioned, enumerable** thing, which is
the same property #145 §2.2 required for the Code Builder to be able to generate a typed call at all.

It also keeps the generated code honest. #144 found no surveyed vendor generating multi-call-site
integration code; a builder that had to decide *how finely to chop* a call would be generating a policy
decision, not an integration. Under this rule it generates one report per declared operation, which is
a mechanical fact it can read off the declaration.

### 3.4 The tenant chooses their own blindness window

A consequence worth naming, because it partially mitigates §4 at no cost.

A tenant who declares a finer unit gets events **during** long work. Sixty per-minute events across an
hour-long session means the wallet counter, the job's COGS ceiling and the stop verdict all move
sixty times rather than once. A tenant who declares a per-session unit accepts a one-hour blind
window in exchange for one invoice line.

**Neither is wrong, and UBB does not pick.** The tenant is choosing between reporting granularity,
invoice legibility and spend visibility, and those trade against each other differently for different
businesses. What matters is that the trade is now *visible and declared* rather than an accident of how
someone wrote a loop.

The cost is equally real and stated in §12: a finer unit multiplies roundings (#142 §6.3) and receipts
(#148 §14). Under §2 that multiplication is now the consequence of a deliberate priced decision rather
than of accidental fragmentation, which is the whole difference.

---

## 4. Long-running work and spend control

### 4.1 The ruling

**No new before-the-call mechanism is built. The blindness is documented and handed to #150 framed as
concurrent unreported work.**

### 4.2 Why nothing new is built here

Three candidates were considered and all fail on grounds already established:

| Candidate | Why not |
|---|---|
| Report the call in pieces | The numbers do not exist yet (§1.3) |
| Declare intent and hold before the call | Requires estimating output tokens before the model produces them; adds a third call site per provider call against #144's finding (§1.3, §3.3) |
| Cap concurrent in-flight calls | Bounds calls, not money; a cap denominated in "calls" does not convert to a COGS ceiling, and #142 §10 already settled that limits are denominated in the tenant's one currency |

The honest position is the one the published guarantee already takes: UBB is not in the inference path
and cannot un-spend a dispatched call. Adding a mechanism that *appears* to bound in-flight spend while
holding against a guess would weaken the claim in §1.2 rather than strengthen it.

### 4.3 What #150 inherits, and with which label

#150 receives this as **concurrent unreported work**, not as *long calls*. The distinction is the whole
value of the handoff:

- A limit aimed at duration would bound the wrong variable — §1.2 shows duration is not the cause.
- The exposure scales with **how many operations are simultaneously unreported**, which is a function
  of the tenant's concurrency and their declared unit (§3.4), both of which the tenant controls.
- A tenant can already reduce it themselves by declaring a finer unit. That is a genuine mitigation,
  and #150 should know it exists before designing a mechanism to replace it.

This follows the pattern #148 §8.2 established — label the residue accurately so it lands in the right
ticket with the right framing, rather than being solved in the wrong one.

### 4.4 What does not change

The ceiling still bites when the event lands, the tipping event still lands and bills, killed units
still count, and the stop verdict still rides the ack. #140 §3.5's rule is untouched: a terminal state
prevents a *charge*, never a *recording*.

---

## 5. Liveness: no keepalive, two declared deadlines

### 5.1 The collision this resolves

#140 §5.2 ruled that liveness is proved only by reporting usage — *"silence means dead"* — with no
heartbeat endpoint, and named the exact case:

> *"A job in a genuinely quiet phase (**a long provider call**, a queue wait, a human approval step) is
> indistinguishable from a crashed one."*

and deferred the question explicitly:

> *"A keepalive endpoint remains available as a later addition **if that proves too blunt in
> practice**."*

**This is the ticket where it proves too blunt or does not.** A job whose substance is one thirty-minute
provider call goes silent for thirty minutes against a default fifteen-minute window
(`Tenant.task_stale_seconds`, 900s). It is expired while still running and still spending — and under
#139 that is delivered work that can never be charged, because only a live job can be closed as
delivered.

### 5.2 The ruling: no keepalive in v1

**A worker-generated heartbeat proves only that the local process is alive. It does not prove the
provider call is progressing** — and provider progress is the thing that would need proving. For the
primary workload, provider usage is known only when the call completes; during one atomic provider
call neither UBB nor the tenant necessarily has any meaningful progress signal to send.

A keepalive would therefore buy a weaker guarantee than it appears to, at a real price: a third SDK call
path, background renewal behaviour, and — decisively — **an additional absolute timeout anyway**, to
stop a live-but-hung worker renewing indefinitely. Once that absolute deadline exists it is doing the
substantive work, and the renewal mechanism is decoration on top of it.

Against #144's finding on multi-call-site generation and #140's hard-won two-call-site lifecycle, that
is not a trade worth making for v1.

### 5.3 Two deadlines, both declared per kind of work

```
usage event                       → resets the silence window
no usage before silence deadline  → task expires
absolute task deadline reached    → task expires regardless
```

Both windows already move onto the declared kind of work under #140 §5.1, on the ladder the COGS
ceiling uses (kind of work → tenant default → 6h / 15m fallback). This document makes two things
explicit that #140 left implicit:

- **Every usage event resets the silence window.** Already true mechanically — `last_event_at` is
  stamped inside `accumulate_cost` (`apps/platform/tasks/services.py:122`) — and now load-bearing, since
  §3.4's finer-unit tenants rely on it.
- **The absolute maximum fires regardless of activity.** It is not a silence window with a longer
  fuse; it is an independent deadline, and it is what makes the absence of a keepalive safe rather than
  merely convenient.

A kind of work should declare a silence window long enough to cover its **longest legitimate atomic
provider call**.

### 5.4 The limitation, stated rather than buried

**Crash detection for genuinely atomic long-running work is delayed to the configured window.** A kind
of work that declares a forty-minute silence window to accommodate a forty-minute render will not
notice a *crashed* worker of that kind for forty minutes — during which it holds its concurrency slot
and, under #139, its prepaid reservation.

This is an explicit v1 limitation, not an oversight. **Lease renewal can be added later** if real
integrations require tighter worker-failure detection; nothing here forecloses it, and §5.2's
reasoning would then be revisited with evidence rather than in the abstract.

§3.4's mitigation applies where it can: work that *can* declare a finer unit emits events, resets the
window, and never relies on the long fuse. The limitation binds only genuinely atomic work.

---

## 6. The fire-and-forget lane is deleted

### 6.1 The ruling

**`POST /metering/usage/ingest`, the `RawIngestEvent` log, the settle sweep, the estimate-and-hold path
and the `metering_async` product flag are removed. There is one way to report usage.** Batching
survives as an efficiency the generated code may use, not as a concept the Code Builder teaches.

### 6.2 What the lane was for, in its own words

The design that built it is unambiguous about its purpose and its position:

> **"Goal:** async-class ingestion throughput **while keeping the hard-stop guarantee at (effectively)
> today's strength."**

> *"The **synchronous endpoint is unchanged** — callers who want the exact priced result in-response
> keep it. **The async path is additive**, gated per-tenant via the existing `products` flag pattern."*

The hold apparatus was never the source of spend control. It existed so a throughput lane could
**approximate** a guarantee the synchronous path already had inline. The same document concedes the
approximation is lossy: *"the bound widens from ~1 event to ~1 batch + tier-boundary estimate error."*

### 6.3 Its accuracy advantage has already evaporated

The word "estimate" is now a misnomer. `PricingService.estimate` runs over `item.usage_metrics` — the
measurements the caller has already reported — through the *same* compute spine as `price`, and says so
(`pricing_service.py:198-245`):

> *"the SAME compute spine as `price` … every estimate therefore equals what `price()` will charge by
> construction, MODULO that config-drift window and the caller keeping selectors in sync."*

Both modulos are gone, killed by decisions already merged:

| Divergence source | Closed by |
|---|---|
| Estimation resolved *current* cards, settlement resolved *as-of* cards (`card_cache.py:87` hardcodes `timezone.now()`) | **#148 §8.4** — estimation resolves at the event's own `effective_at`; `Estimate.exact` deleted as an unearned claim |
| Accept and settle could match different rates via selector inheritance | **#145 §5.1** — attribute-based rate selection deleted outright; there is no matching engine left to disagree |

So the lane's pitch reduces from *"fast but approximate"* to *"fast"*. Accuracy is no longer a
differentiator in either direction.

### 6.4 It makes job ceilings later, not sooner

This is the finding that decides the ticket, and it is stated in the code:

> *"the acquire ALWAYS holds, **against the wallet only** — the accept-time unit-cap lane is **retired
> unreplaced** (task limits are COGS-denominated and exact provider cost exists only at settle; an
> accept-time compare of a billed estimate against a COGS limit would be denominationally dishonest).
> **No item is ever rejected for limit reasons**."* (`ingest_accept.py`, hold acquisition)

So per limit type:

- **Job / step COGS ceilings — worse on the fast lane.** The synchronous path rolls the job's totals up
  inline and the kill has already fired by the time the caller reads the response
  (`metering_endpoints.py`: *"the kills have already fired by the time this returns"*). The fast lane
  touches no job counter at accept; the total does not move until settle.
- **Wallet floor — identical.** A hold goes against the wallet at accept and the verdict rides the
  response.

**And the retirement is correct.** Comparing a billed-price estimate against a COGS-denominated ceiling
compares two different quantities — exactly the denominational discipline #142 §10 and #141 insist on.
That is why it cannot be quietly repaired: fixing it means either estimating *provider* cost at accept
or making ceilings price-denominated, and both are larger decisions than this lane deserves.

The honest sentence for the documentation would read: *"use this lane and your spend ceilings bite
later."* No tenant should be asked to opt into that.

### 6.5 Spend control survives intact — it stops having two implementations

Both limits are enforced in the **recording core**, which every event passes through on either lane.
The fast lane does not bypass it; it arrives later.

| Guarantee | Where it lives | Survives? |
|---|---|---|
| Job / step COGS ceilings, kills, cascades | `usage_service.py:437` → `TaskService.accumulate_cost` | **Yes** — and trips *sooner* without the lane |
| Hard floor (wallet) / budget cap, stop flag | `usage_service.py:453` → `record_live_usage_debit` → `LiveCounter.debit` | **Yes** — same call, unchanged |
| Soft floor refusing new top-level starts | the start-gate (`RiskService`) | **Yes** — never touched acks or lanes |
| Stop verdict on every response | the ack schema | **Yes**, and improves — a settled number, not an estimate |
| Stop / resume webhooks, at-least-once | outbox + `StopSignalState` transition guards | **Yes** — durable-driven |
| Hourly patrol, re-mint, wedged-stop clearing | `apps/billing/gating/patrol.py` | **Yes** — traffic-independent by design |
| Past-limit accounting, `stop_context` | written inside the recording transaction | **Yes** |

**The arrival-signals switch survives too.** It is not the fast lane's switch: it gates `LiveCounter.debit`
(the *synchronous* live-counter write) and both reconcile paths, not only `hold`. Its meaning narrows
from "the whole fast lane is off as one unit" to "real-time counter maintenance is off; detection
happens at the durable lane" — which remains a genuine, documented posture.

### 6.6 What genuinely dies, and why

- **The hold trio** — `LiveCounter.hold` / `release` / `settle` and the three `apps/billing/queries.py`
  operations over them. No caller remains.
- **`PricingService.estimate` and the `Estimate` record.** Exactly one non-test caller exists
  (`ingest_accept.py:573`). `Unpriceable` and the sync-fallback branch were already deleted by #146.
- **The upward live-balance repair patrol (#45).** It dies **with its cause**, by its own docstring:
  *"An orphaned hold — acquired on the fast lane, its `RawIngestEvent` row rolled back with a crashed
  request — leaves the prepaid live counter permanently below reality"*, and *"the repair exists only
  where holds exist … part of the fast lane and switches off with it."* No holds, no orphans, no
  repair.
  **One check is owed before removal, not assumed here:** whether the synchronous `debit` path can
  produce the same class of drift (a counter written, its event row rolled back). If it can, the repair
  survives on a narrowed footing and its docstring's stated cause is incomplete. This is flagged in §12.

### 6.7 What is genuinely given up

Stated plainly, because the case for deletion does not need it hidden.

**Throughput headroom.** The design doc's own numbers: *"Ceiling: ~100–300 events/sec per instance;
**batching does not help** because items run sequentially in-request."* Batching amortises HTTP round
trips, not database work — it is not a substitute, and any argument for deletion that leans on it is
wrong.

**One locked launch SLO.** `docs/spend-control-guarantees.md` §2 fixes *"ingest-accept p99 ≤ 200ms and
stop-signal p99 ≤ 5s, under a 1-hour storm at 500 events/s"*. The first of those is an SLO on the lane
being deleted and **must be restated** against the surviving path.

**What softens it:** the same sentence documents 500 events/s as *"~5× the first tenant's peak"* — so
real expected load is around 100/s, inside a single instance's stated ceiling. The loss is stress
margin, not day-one capacity, and the surviving path scales horizontally except where contention
concentrates on one billing owner or one job — which the fast lane deferred rather than removed, since
settle takes the same row locks in the same order, later.

**Real prior investment.** This reverses part of a shipped program: the accept-seam extraction (#113),
the arrival-signals work (#46) in the portion that served holds, and the upward repair (#45). Deleting
working, tested, spend-control-integrated code is a genuine cost and is not free because it is
justified.

### 6.8 Why now rather than later

- **Its one advantage is gone** (§6.3), so what remains is throughput for a load nobody has yet.
- **It weakens the guarantee it was built to preserve** (§6.4), in the direction no tenant would choose.
- **It is the most intricate machinery in the system and keeps needing repair** — dimension admission
  at accept, selector inheritance parity between accept and settle, the extraction refactor, and
  #146's deletion of its sync-fallback branch. That is sustained correctness risk for unused capacity.
- **Map constraint 1 gives one clean break and there are no live integrators to break.** #145 §6.2 and
  #147 §6.2 both took the same licence for smaller deletions.

If volume arrives, the lane returns as a deliberate feature with a measured requirement — and can then
be built to hold against **COGS** ceilings, which is the thing today's version structurally cannot do.

---

## 7. What this repairs and dissolves in merged decisions

### 7.1 #147 — the first reason for deleting the per-event uplift, repaired

| #147 as merged | After this decision |
|---|---|
| *"'Per event' is not a stable unit. #149 is open on whether one streamed provider call becomes one event or many"* (§6.2, reason 1) | **"Per event" is now a stable unit.** An event is one declared provider operation (§2.1); granularity is declared, never improvised (§3.1) |
| `fixed_uplift_micros` deleted on three reasons | **Deletion stands** on reasons 2 and 3, which are specific to an uplift. Reason 1 is superseded, not withdrawn |
| `direct_event_price` kept, carrying the same per-event exposure unexamined | **Kept and now sound.** The exposure is closed by defining the unit, not by deleting the method |
| #147 §13: *"#149 relieved of a hazard"* | Correct, and reciprocal — #149 relieves #147 of the instability its own first reason implied |

**Nothing in #147 is reversed.** Its conclusion is upheld; one of its stated reasons is discharged.

### 7.2 #148 — the accept-versus-settle gap loses its subject

#148 §8 closed a real defect: estimation resolved against today's rules while settlement resolved
against the event's date, *"a systematic mismatch on an entire class of events"*. With the lane deleted
there is **no accept instant left to disagree with settle**, and the two work items it assigned lose
their targets:

| #148 §9 line item | Disposition |
|---|---|
| `PricingService.estimate` **gains `as_of`** | **Moot** — `estimate` is deleted (§6.6) |
| `ingest_accept.py:573` **passes `item.effective_at`** | **Moot** — the call site is deleted |
| `Estimate.exact` **deleted** | **Already correct**, and now deleted with its record |

**#148 §8.3 survives unchanged and must not be discarded with the rest.** The requirement that
`CardCache` become **time-aware** stands on its own footing: it exists because §6's forward-dated
publishes break a cache whose key has no time component, which affects `price` at settle regardless of
which lane fed it. That is not an artefact of estimation.

This is a dissolution, not a contradiction: #148 solved the problem correctly, and this document removes
the surface on which half of it occurred.

---

## 8. Handoffs this answers

| From | The handoff | Answer |
|---|---|---|
| #145 §13 | *"Partial reporting is now expressible … whether it should be is #149's"* | **No.** Expressible is not the same as available: granularity is declared, never improvised (§3) |
| #142 §10 | *"Event granularity is a pricing-accuracy decision … more, smaller events means more R1 roundings and a real risk of sub-micro lines charging zero"* | Accepted and rehoused. Multiplication now follows only from a **deliberately declared** finer unit (§3.4), never from accidental fragmentation. The rate-set-time warning #142 §6.3 specifies is the right surface and is unchanged |
| #148 §14 | *"Splitting one call into many events multiplies receipts, not just rows"* | Same disposition: a declared per-minute unit multiplies receipts by design and by the tenant's choice. Retention economics belong with the declaration UI, not with a splitting rule |
| #147 §13 | *"Relieved of a hazard"* — the per-event uplift no longer multiplies on split | Acknowledged, and reciprocated (§7.1) |
| #140 §5.2 | *"A keepalive endpoint remains available as a later addition if that proves too blunt in practice"* | **Not added in v1** (§5.2), with the two-deadline shape made explicit (§5.3) and the residual limitation stated (§5.4) |
| #146 §6.3 | An unresolvable event yields **no** estimate rather than a zero one; *"what the hold does with no estimate is #150's"* | **Dissolved** — there is no hold and no estimate (§6.6). #150 loses this question entirely |

---

## 9. Answers to the ticket's five questions

**1. Does a streaming call need first-class modelling, or is "one event at completion" the honest and
sufficient answer?**
Neither, quite. *"One event at completion"* is the right behaviour but the wrong justification — it
sounds like a concession. **Streaming is struck as a concept** (§1.1): the billable numbers arrive in
the final chunk, so a stream is not a distinguishable kind of call from UBB's side at all. One event
because it is one operation (§2), not because we gave up on splitting it.

**2. If incremental reporting is wanted: is that many events, or one event updated?**
**Neither, and the dichotomy is false.** "One event updated" is refused — `UsageEvent` is immutable by
construction and #148 made the receipt immutable too, so it would be a new concept. "Many events" is
refused *as a way of splitting one operation*. Incremental reporting is available only by **declaring a
finer unit**, in which case each report is a whole event of a smaller declared operation (§3.2), which
is not splitting at all.

**3. How does a long-running call interact with spend limits?**
It does not interact differently from a short one — duration is not the cause of the overshoot (§1.2).
**Nothing new is built**; the exposure is documented and handed to #150 as **concurrent unreported
work** (§4). A tenant may reduce it themselves by declaring a finer unit (§3.4). Separately, long calls
force the liveness question, answered in §5: no keepalive, a silence window every event resets, and an
absolute maximum that fires regardless.

**4. Does the async lane's estimate-and-hold shape extend to streaming, or is streaming a third lane?**
**Neither — the async lane is deleted** (§6). Its hold fires when the event *arrives*, which for a long
call is still the end, so it never addressed this problem; and its remaining advantages are gone (§6.3)
while it enforces job ceilings later than the path it was meant to match (§6.4).

**5. What does the developer write in each of the three cases, and are the differences large enough to
warrant three distinct code paths in the Code Builder?**
**There is one case and one code path.** Streaming is struck (§1.1); fire-and-forget is deleted (§6);
batching is a loop over the single path — already true in the code, where `record_sync_item` is *"one
batch item == one independent POST /usage"* and the single↔batch field map is deliberately written
once — so it is an efficiency the generated code may use, never a concept it teaches. The developer
writes: **report one event per declared operation.** Exact code shape is #157's.

---

## 10. What each existing thing becomes

| Existing | Disposition |
|---|---|
| `POST /metering/usage` | **The one way to report usage.** Unchanged in shape |
| `POST /metering/usage/batch` | **Kept as an efficiency**, not a taught concept. Semantics already identical per item |
| `POST /metering/usage/ingest` | **Deleted** |
| `GET /metering/ops/ingest-health` | **Deleted** (operator-facing, already schema-excluded) |
| `RawIngestEvent` (`usage/models.py:168-195`) + its migration | **Deleted** |
| `ingest_accept.py` (the accept pipeline) | **Deleted** |
| `ingest_health.py` | **Deleted** |
| The settle sweep + poison path (`usage/tasks.py`) | **Deleted** |
| Settle branches in `usage_service.py` (`:622`, `:699`) | **Deleted** |
| `IngestEventIn` / `IngestBatchRequest` / `IngestBatchResponse` (`schemas.py`) | **Deleted** |
| `PricingService.estimate` (`pricing_service.py:198-245`) + `Estimate` | **Deleted** — one non-test caller, itself deleted |
| `LiveCounter.hold` / `release` / `settle` (`live_counter.py:315`, `:507`, `:446`) | **Deleted** |
| `acquire_ingest_holds` / `release_ingest_hold` / `settle_ingest_hold` (`billing/queries.py`) | **Deleted** |
| Upward live-balance repair (`billing/gating/repair.py`, #45) | **Deleted with its cause** — subject to the §6.6 check |
| `arrival_signals_on` + the switch (`tenants/flags.py:35`, `tenants/models.py:97`) | **Kept.** Gates the synchronous `debit` and both reconciles; meaning narrows (§6.5) |
| `LiveCounter.debit` (`:248`) | **Unchanged** — the surviving real-time counter write |
| `TaskService.accumulate_cost` (`tasks/services.py:56`) | **Unchanged.** Still the one COGS-ceiling choke point |
| `metering_async` in `Tenant.products` (`tenants/models.py`) | **Retired.** One fewer product flag |
| `Tenant.task_stale_seconds` (`tenants/models.py:105`) | **Unchanged as the middle rung**; per #140 §5.1 the kind of work may override |
| The 6h absolute cutoff (`tasks/tasks.py:30`, `:97`) | **Confirmed as an independent deadline** (§5.3), not a long silence window |
| `EventType` declarations (#145) | **Gain the granularity role explicitly** — the declared operation *is* the event unit (§3.1) |
| `direct_event_price` (#147 §2.1) | **Unchanged and now sound** (§7.1) |
| Async ingest design + hardening docs (`ubb-platform/docs/plans/2026-07-03-*`, `2026-07-10-*`) | **Frozen history.** Never edited as current truth; this document supersedes them |
| `docs/spend-control-guarantees.md` §2 SLOs, §8 | **Owed an edit** — the ingest-accept SLO must be restated (§6.7) |

---

## 11. Constraints this imposes on other tickets

- **#150 (spend limits re-modelled)** — inherits in-flight blindness labelled **concurrent unreported
  work**, not "long calls" (§4.3); **loses** #146 §14's question of what an accept-time hold does with
  no estimate, since neither survives (§8); and gains #140 §5.1's per-kind silence window **and** the
  independent absolute maximum (§5.3) beside the COGS ceiling.
- **#151 (charging modes)** — a per-event price is now stable because the unit is declared (§2, §3);
  the mode question is unaffected, but a charging mode's interaction with a *finer declared unit* is
  worth an explicit sentence, since sixty per-minute events under a fixed-price task are sixty
  `not_applicable` postings (#148 §9.3), not sixty zero-revenue ones.
- **#152 (task dashboard)** — must show that expiry can strike a *live* job doing atomic long work
  (§5.4), which is not a failure and must not be counted as one (#140 §11 already forbids counting
  `expired` as a failure). Attempts still group by `external_task_id`.
- **#153 (analytics re-alignment)** — a tenant who declares a finer unit produces far more events for
  the same work; per-event counts stop being comparable across Event Types with different declared
  granularities. Charts must aggregate on **measurements**, never on event counts, unless the unit is
  held constant.
- **#154 (vocabulary lock)** — owes: the retirement of "ingest" / "async ingest" / "fast lane" /
  "estimate" / "hold" as product vocabulary; the noun for the declared unit (§3.1) if "operation" is
  not it; the narrowed meaning of the arrival-signals switch (§6.5); and the §7 reconciliation of this
  document with #147 §6.2 and #148 §8 in the owed ADR.
- **#155 (migration and cutover)** — **gains** the largest deletion in the map: an endpoint family, a
  durable table and its migration, a Celery sweep, a patrol job, three billing operations, three live
  counter methods, a pricing method, a product flag, and their pin tests across both products. Also
  owes the §6.6 drift check before the repair job is removed. **Loses** nothing.
- **#156/#157 (Code Builder)** — **one** reporting call site, not three (§9.5). §3.1 gives the
  generator its granularity input directly from the Event Type declaration; there is no policy decision
  for it to make and no lane for it to choose between. Combined with #140's two lifecycle call sites,
  the total taught surface is three calls.
- **#158 (end-to-end audit method)** — the SLO restatement (§6.7) is an audit input: the proof stage's
  three SLOs on #15 are reduced to two plus a restated throughput target against the surviving path.
- **The proof plan (#15)** — the *"ingest-accept p99 ≤ 200ms"* SLO loses its subject and must be
  restated **before** load testing is designed, not discovered during it.

---

## 12. Residue, flagged not buried

- **The 500 events/s storm SLO must be restated** (§6.7). Real expected load is ~100/s and inside a
  single instance's stated ceiling, but the locked number is a published commitment and someone must
  own changing it. This is the single largest consequence of §6 and it is a launch-stage item.
- **Batching does not relieve the throughput ceiling.** Items run sequentially in-request by design.
  Any future argument that "batch covers it" is wrong and the design doc says so.
- **Whether the upward repair truly dies is one check away** (§6.6). Its docstring names orphaned holds
  as the cause, but whether a synchronous `debit` whose event row rolls back produces the same drift
  was not established here. If it does, the repair survives narrowed and its docstring is incomplete.
- **Crash detection for atomic long-running work is delayed to the declared silence window** (§5.4).
  A forty-minute window means a crashed worker holds a concurrency slot and a prepaid reservation for
  forty minutes. Lease renewal is the named later remedy.
- **Concurrent unreported work remains genuinely unbounded**, and #150 inherits it rather than solving
  it here (§4.3). The published guarantee already refuses to quote a bound, so this changes nothing
  about what is promised — but it is the honest state of affairs and should not be discovered in a
  sales conversation.
- **A tenant who declares a coarse unit accepts a long blind window** (§3.4). That is their choice and
  UBB does not override it, but the console should show the consequence at declaration time — the
  declared unit is the moment a tenant is deciding their own spend visibility, and probably does not
  know it.
- **A finer declared unit multiplies roundings and receipts** (§3.4, §8). Under #142 §6.3 the
  sub-micro warning fires at rate-set time, which is the right surface, but nothing warns at
  *declaration* time that choosing a per-minute unit multiplies six-year receipt retention by sixty.
  Worth considering with #157's declaration UI.
- **Reversing shipped work has a morale and trust cost that is not technical.** #45, #46 and #113 were
  built deliberately and reviewed. This document argues they served a lane that should not exist, not
  that they were wrongly built — and the distinction should survive into the changelog.
- **Nothing here decides what happens if a provider genuinely offers mid-call usage.** Some providers
  emit incremental usage on long streams. Under §3 a tenant could declare a finer unit and use it; the
  question of whether UBB should *encourage* that, or model provider-side incremental usage
  explicitly, is left open rather than pre-empted.
