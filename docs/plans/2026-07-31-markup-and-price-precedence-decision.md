# Markup — one method per rule, one home for the rules, and three states for revenue

**Resolves:** [#147](https://github.com/ashcochrane/ubb/issues/147) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-31
**Decided against:** `main` @ `15f157d`
**Evidence:** `docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch
`research/pricing-model-prior-art` @ `2f0ce4c`) — **Q4** (Stripe's competing token-billing product
sets *"your markup percentage"* over a synced price list; no platform of six models cost and margin
as a first-class plane feeding invoicing), **Q5** (Metronome's Multiplier-vs-Overwrite distinction,
and its backdated-rate hazard), and OpenMeter's `UnitConfig` *"Cost + 20% margin"* mechanic.
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — `TenantMarkup` is
absorbed into policy-line content, markup stops being a parallel mechanism, and the direction of this
ticket is *"the reversal of today's behaviour"*; precedence and target-margin arithmetic were left
here.
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the fixed price is terminal
and bypasses all four markup rungs; the Charge is immutable and no re-invoice path exists.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — terminal is terminal; a close carries a
required outcome.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — **unknown revenue ≠ zero**, and
*"nothing configured → billed == provider"* must stop meaning zero margin; the `billed_cost_micros`
non-nullability defect was handed here explicitly.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — markup's rounding is R4's `round_charge`;
the fixed uplift is a denominated value; the caller-cost bound asymmetry set the precedent applied in
§9.2.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — Grouping Fields have **no** price
role, answering #138's parked question before this document opened.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — cost is observed, price is
decided; the price ladder arrives here **closed**, with no caller rung; ceilings gained
`indeterminate`; §9.4's deferral rule is **narrowed to nothing on the revenue side** by §7 below.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 through #146: #154 is the single naming pass,
and this document coins four nouns and one enum (§13). The ADR is owed *after* #154 and should cite
all eight decision documents.

---

## The decision in one paragraph

**Markup is neither a layer nor a fallback, because "layer or fallback" presumes two mechanisms and
there is only one.** A customer's price comes from exactly one **pricing rule**, resolved once per
event, and that rule declares one of two methods: **margin over cost**, or a **direct event price**.
A configured 2p is 2p — margin is not added on top of it, and a direct price does not shadow a
fallback that would otherwise have run. Every rule lives in **one place**: a versioned **Pricing
Book**, which a Plan selects and a customer inherits, with **customer overrides that replace an
inherited rule rather than adding to it**. Resolution is four rungs and **specificity beats source**
— the customer's exact rule, then the book's exact rule, then the customer's blanket rule, then the
book's default — so negotiating a blanket discount never silently deletes the specific prices a
tenant set. **Event Category leaves the pricing ladder entirely** and survives as analytics, because
reclassifying an operation for reporting must never move money. The arithmetic is **one number**:
markup on cost, with the gross margin it implies *displayed* rather than stored, and the per-event
fixed uplift **deleted** — it multiplied unpredictably whenever an event split and charged on
genuinely free calls. Revenue then gains the representation #141 said it needed and #146 built on the
cost side: **three states, not two.** Where a supplier cost cannot be resolved, a direct price still
bills — 2p is owed whether or not we know what it cost us — while a margin rule cannot produce a
number at all and the event is **waived**: no customer charge, **never automatically back-billed**,
the resolved cost landing later as a reported loss the tenant can act on. Where no rule resolves at
all, the answer depends on the tenant's **declared** mode and never on what configuration happens to
exist: for a metering-only tenant that is the expected, silent end of the pipeline, and for a
full-billing tenant it is a configuration error that alerts. Finally, a book edit **moves everyone
resolving through it**, from now or a future date — negotiated overrides are the grandfathering
mechanism, so none is built — and **backdating is refused**, because a posted number never moves.

---

## 1. The ticket's premise, corrected

The ticket opens by naming the working model false, and it is right:

> The working model assumes markup is a universal final step: *base cost → plan markup → final
> charge*. **That is false today.** In `pricing_service.py:150-167`, if any `price` rate matches, the
> billed cost is the price total and markup **never runs**. Markup is the fallback, not a layer.

That reading of the code is exact. What needs correcting is the question it leads to.

### 1.1 "Layer or fallback" is a false binary

Both readings presume **two mechanisms** — a price mechanism and a markup mechanism — and ask how
they compose. Today's code answers "by precedence"; the working model answers "by stacking". Both
answers are wrong because the premise is.

There is **one** mechanism: a rule that says what a customer pays for a kind of event. That rule
declares its **method**, and the two methods are alternatives:

| Method | Customer charge |
|---|---|
| **margin over cost** | calculated COGS + configured margin |
| **direct event price** | the configured sell price |

The owner's framing during grilling is the spine of this section:

> A direct sell price and margin-over-cost are two alternative ways of pricing an event, not two
> layers that are automatically combined. … Adding margin on top would mean that "sell this event for
> 2p" did not actually produce a 2p selling price and could double-charge by construction.

So today's *behaviour* — a matched price wins outright — is largely correct, and today's *model* is
what is wrong. Markup is not "the fallback"; it is the other method, and it loses not because it
ranks lower but because it was not the method this rule declared. #138 already fixed this direction:

> markup/margin is the *default* content of a policy line and a fixed sell rate is the *explicit
> override*. Today a matched price line prices directly and markup never runs at all.

This document keeps that and states the consequence #138 did not: since the two are alternatives on
one rule, **there is no precedence question between them at all.** Precedence exists only between
*rules* (§5), never between *methods*.

### 1.2 The third option, and why it was rejected

Metronome distinguishes **Multiplier** (*"As the list rate on the rate card changes, the effective
rate after the multiplier is applied also changes"*) from **Overwrite** (*"remains at $3.23
regardless of changes to the list price"*) — genuine prior art for letting each rule declare whether
it is final or a base to be marked up (research Q5, **medium**).

It was put and rejected. Under it, a tenant who writes "sell Gemini calls at 2p" cannot know what a
customer pays without also knowing every markup that might apply, and two rules that both apply can
disagree about which is the base. The value Metronome gets from the distinction comes from a *list
rate* that moves underneath a negotiated multiplier — a rate-card-versioning affordance, not a
margin model. Under §10 a book edit already moves everyone resolving through it, which serves the
same need without making any single rule's output conditional on another's.

### 1.3 What the ticket got right and this document keeps

The ticket's instinct that the plan rung's zero-shadowing deserves scrutiny is correct, and §4.3
resolves it — though by dissolving the rung rather than by fixing its precedence.

---

## 2. One method per rule

### 2.1 The ruling

A **pricing rule** targets one Event Type (or is the book's default), and declares exactly one
method:

```
EventType
  code: gemini-api-call-flash-4.0

PricingRule
  method: direct_event_price
  amount: $0.02 per event
```

```
Direct event price:   $0.02
Additional margin:    not applied
Customer charge:      $0.02
```

The methods are **exclusive per rule**. Nothing is layered onto a direct price — not a margin, and
(per §6.2) not a per-event fee either.

### 2.2 Why exclusivity, and not composition

**A configured price must mean what it says.** This is the whole of it. A model in which "sell this
for 2p" produces something other than 2p has broken the one promise a price is for, and no amount of
UI can repair it, because the tenant who typed 2p is the person least likely to go looking for a
second number that silently modified it.

The secondary argument is #146's, arriving from the cost side: **cost is observed, price is
decided.** A decision that composes with other decisions is not one decision; it is a formula whose
result nobody stated. Every rung of the ladder in §5 yields a *stated* answer.

The third is the Code Builder's (map #137's destination). A generator can emit "this call will be
charged at $0.02" from a declared rule. It cannot emit anything truthful about a price whose final
value depends on how many other rules happened to match.

---

## 3. Task pricing is a separate scope

### 3.1 The ruling

There are two revenue scopes, and they do not compose either:

| Scope | When revenue arises |
|---|---|
| **Event pricing** | a charge for each qualifying event occurrence |
| **Fixed task pricing** | one charge when the task is successfully delivered (#139) |

A task therefore carries an explicit **pricing mode**:

```
Task.pricing_mode
  event_priced   events follow their normal customer-pricing rules
  fixed          events contribute COGS only; one Charge on delivery
```

The mode and the fixed price are **snapshotted when the task is created**, so a later policy change
cannot alter whether a running task's events are independently charged.

### 3.2 Belonging to a task is not a reason to suppress event pricing

This is the correction #139 did not make explicit, and it matters. The decision when an event
arrives is:

```
Does the event belong to a task?
  ├── No  → apply normal event pricing
  └── Yes → what is the task's snapshotted pricing mode?
        ├── event_priced → apply normal event pricing
        └── fixed        → record event COGS
                         → suppress event-level customer pricing
                         → create one task Charge on delivery
```

Suppression under `fixed` applies to **both** methods — `margin_over_cost` and
`direct_event_price` alike. Neither creates event-level revenue inside a fixed-price task.

The economics of a fixed-price task are then exactly #139's, stated in this document's vocabulary:

```
Task revenue = the fixed task Charge
Task COGS    = sum of the task's cost-bearing events
Task margin  = task Charge − task COGS
```

### 3.3 Why an explicit mode rather than an inferred one

A task with a fixed price could in principle be recognised by *having* a fixed price, and event
suppression inferred from that. It is rejected for the same reason #146 rejected payload-inspected
costing modes and §8 rejects mode-inferred-from-configuration: **an economic behaviour that is
inferred from the presence of a field is a behaviour nobody declared and everybody must reverse-
engineer.** The snapshot requirement then follows directly from #140's *terminal is terminal* — a
task that started as `event_priced` must not become `fixed` under it.

---

## 4. Where pricing rules live

### 4.1 The ruling

The **Pricing Book** is the canonical and only home of customer-pricing rules:

```
PricingBook
  default pricing rule
  per-Event-Type pricing rules
  version and effective dates

Plan
  pricing_book_id

Customer subscription
  plan_id

CustomerPricingOverride
  optional replacements for selected inherited rules
```

A worked example, from grilling:

```
PricingBook: Individual          PricingBook: Business
  default: margin_over_cost 50%    default: margin_over_cost 20%

Plan: Individual                 Plan: Business
  pricing_book: Individual         pricing_book: Business

Customer: Acme  (on Business)
  override: default margin 15%
```

**An override replaces, never adds:**

```
Business Plan markup:  20%
Customer override:     15%
Resolved markup:       15%     (not 35%)
```

Additive adjustments are not in v1. If a future feature wants them, it must introduce them
explicitly, because "override" has to keep meaning one thing.

### 4.2 What must not remain

Parallel markup fields on Tenant, Plan, Customer *and* the book would be four competing answers to
one question. The ruling is explicit:

| Object | Job |
|---|---|
| **Pricing Book** | owns pricing rules |
| **Plan** | selects a Pricing Book |
| **Customer** | inherits through the Plan; may hold explicit override records |

So `TenantMarkup` is deleted outright, and `Plan.markup_percentage_micros` /
`Plan.fixed_uplift_micros` are deleted from the Plan. This completes what #138 began — *"markup stops
being a parallel mechanism"* — and it is a deletion, not a move: the numbers do not reappear
somewhere else under a new name, because the book already holds a default rule that says the same
thing better.

### 4.3 The zero-shadowing question, dissolved

The ticket asks about a real behaviour:

> A plan with explicit zero markup *shadows* the tenant default rather than falling through.

It is not an accident. It is deliberate and pinned by a test whose name says so —
`test_zero_markup_plan_shadows_tenant_default_and_pins_provider_cost`
(`test_markup_service.py:91-100`), asserting that a fee-only plan *"pins the customer at provider
cost and must NOT fall through to a non-zero tenant default"*.

But it sits on a contradiction inside one model. `Plan.access_fee_micros` carries the comment *"0
means 'this axis is absent', not 'free'"* (`plans/models.py:26-28`); five lines below,
`Plan.markup_percentage_micros` means a deliberate zero. **Two conventions for `0` on the same
model, three fields apart** — and `get_plan_markup_for_customer` (`plans/queries.py:9-26`) returns a
populated dict for *any* assignment, so an access-fee-only plan with no markup axis at all silently
pins that customer at cost.

Under §4.1 the question loses its subject. Plans carry no markup number, so there is no zero to be
ambiguous. A book whose default rule says *margin 0%* means exactly that, visibly, as a rule someone
wrote; a book with no default rule at all resolves to `unresolved` (§5), which §8 then interprets by
mode. **The distinction between "absent" and "zero" is carried by the presence of a rule, not by the
value of a number** — the same move #146 made when it made cost nullable, and the same move §7 makes
for revenue.

---

## 5. Resolution: four rungs, specificity before source

### 5.1 The ruling

For an event eligible for event pricing (§3.2), resolve exactly one final rule:

```
1. Customer override for this exact Event Type
2. Pricing Book rule for this exact Event Type
3. Customer blanket override
4. Pricing Book default
5. Otherwise unresolved            → §8
```

Worked:

```
Pricing Book "Business"
  default:                    margin_over_cost 20%
  gemini-api-call-flash-4.0:  direct_event_price $0.02

Acme (Business, blanket override 15%)
  gemini call  -> $0.02        rung 2 — the book's exact rule
  openai call  -> cost + 15%   rung 3 — Acme's blanket override
```

### 5.2 Why specificity outranks source

The alternative — the customer's own contract answering first, at every level — was the ladder as
first stated, and it was rejected on its consequence. Under it, Acme's blanket 15% **shadows the
$0.02 Gemini rule entirely**, so agreeing a small blanket discount silently deletes every specific
price the tenant configured, with nothing anywhere reporting that it had. The tenant's only defence
would be to restate every specific rule inside every override.

This is ADR-0005 §8's *"book tier dominates rate specificity"* sharp edge — the one #138 declared
dissolved because *"no two independent ranking layers remain to disagree"*. It very nearly came back,
because a customer override *is* a second ranking layer. Specificity-major ordering is what actually
dissolves it: there is one ranking (how specifically a rule names the event) and source is only the
tie-break within a level. That yields one sentence anybody can hold in their head — **most specific
wins; at equal specificity, the customer's own answer wins** — and it makes "override" mean *replace
the rule at the level you are overriding*, which is what §4.1's replacement rule already said.

### 5.3 No fallthrough between books

One book is selected — via the customer's Plan — and resolution happens within it plus the
customer's overrides. There is no walk to another book. This deletes the three-tier
assigned → default → wildcard walk in `PricingService._resolve_card` (`pricing_service.py:67-92`),
as #138 already required, and it is why the ladder is four rungs rather than an open-ended search.

---

## 6. What leaves the pricing model

### 6.1 Event Category leaves the ladder — a narrowing of #138

#138 created `EventCategory` **specifically to be a pricing target**:

> Exists because customer pricing policy usually follows the kind of work, not the vendor … price
> resolution: 1. Exact Event Type policy. 2. Event Category policy. 3. Book-wide default.

**That rationale is reversed here.** Event Category survives as an *optional analytics
classification* — group COGS by category, filter to all `llm-inference` operations, compare provider
costs within a category — and is **not** a pricing selector or a pricing-policy target in v1.

The owner's argument is decisive and is about blast radius, not expressiveness:

> Moving an Event Type from one reporting category to another should not unexpectedly change what
> customers are charged. … It should not be inherited accidentally from an analytics field.

Two consequences worth stating.

**It retires an obligation #138 placed on #148.** #138 required category membership to be
*"historically reproducible — effective-dated, or preserved in the rating record — so replaying an
old event never applies today's category."* That requirement existed **only** because categories
priced things. With the pricing role gone, an analytics classification may simply be current, and
#148's surface shrinks accordingly.

**It costs something real, and the cost is named.** A tenant onboarding their eighth LLM provider
writes eight rules rather than one. That is accepted as the price of keeping a reporting field
economically inert. A future category-pricing feature remains available, but the owner's conditions
on it are recorded here as binding on whoever builds it: **effective-dated category membership,
deterministic precedence, and explicit warnings that changing a classification changes money.**

### 6.2 The per-event fixed uplift is deleted

`TenantMarkup.fixed_uplift_micros` (`pricing/models.py:17`), `Plan.fixed_uplift_micros`
(`plans/models.py:34`) and the API fields that carry them (`schemas.py:515`, `:520`, `:1024`,
`:1051`) are **removed**. A margin rule is one percentage.

Three reasons, in the order they bite:

1. **"Per event" is not a stable unit.** #149 is open on whether one streamed provider call becomes
   one event or many. Under splitting, a per-event fee bills once per fragment — a rule whose output
   changes because an unrelated ticket changed the event granularity is not a priced term.
2. **It charges on genuinely free calls.** `MarkupService.apply` returns `provider_cost + markup(...)`
   and the uplift is unconditional (`markup_service.py:28-34, 66-72`), so a cached or free-tier
   response with `provider_cost = 0` still bills the uplift.
3. **It is a second number in a box that should hold one.** §9.1 already rejected offering two
   plausible-looking percentages; the same argument applies to a percentage and an amount.

A tenant with genuine per-call overhead raises the percentage or sells at a direct price. This also
removes one more denominated value from #142's inventory (`money-model-decision.md:78`), and under
map #137's clean-break constraint the deletion is free.

---

## 7. Revenue has three states

### 7.1 The ruling

`UsageEvent.billed_cost_micros` is `BigIntegerField(default=0)` (`usage/models.py:42`). It becomes
**nullable**, exactly as #146 §4 did to `provider_cost_micros` one field above it, and it now carries
three distinguishable outcomes rather than one:

| State | `billed` | Meaning |
|---|---|---|
| **known** | a number | a rule resolved and produced this amount (including a deliberate `0` — a free service) |
| **waived** | `0` | a rule resolved, but its input could not be — no customer liability (§7.3) |
| **unknown** | `null` | no rule resolved — UBB was never told what this is sold for (§8) |

A `pricing_status` on the event carries *which*, because the amount alone cannot: a waived `0` and a
deliberately-free `0` are the same integer and are not the same fact. Naming → #154.

This closes the defect #141 handed here explicitly:

> `billed_cost_micros` non-nullability (`usage/models.py:41-42`) — the "unknown vs zero" defect (§1.2)
> belongs to #147.

and retires the behaviour it named — `MarkupService.apply`'s *"nothing configured → billed ==
provider"* (`markup_service.py:68`), which made a metering-only tenant's every event report **exactly
zero margin, indistinguishable from a genuine zero-margin deal**. That fallback (`markup_service.py:71`)
is deleted, not adjusted.

### 7.2 An unresolvable cost splits by method

#146 records an event whose supplier cost cannot be worked out as `costing_status = unresolved`, cost
**null**, never zero. What the customer owes for such an event **depends on which method the resolved
rule declared**, because the two methods depend on cost differently:

```
rule: direct_event_price $0.02        rule: margin_over_cost 20%
  COGS      unresolved                  COGS      unresolved
  revenue   $0.02   -> bills now        revenue   none
  margin    unavailable                 margin    unavailable
```

**A direct price does not depend on supplier cost, so it bills immediately.** 2p is contractually
owed whether or not UBB yet knows what the call cost. When the COGS later resolves, **only cost and
margin reporting change** — the customer charge does not move:

```
Customer revenue:  $0.02
Resolved COGS:     $0.03
Gross profit:     -$0.01
```

That is #146 §9.2's *completing a blank is not a correction* applied on the revenue side: the
revenue was never blank, so nothing about it is contradicted.

### 7.3 A margin rule over an unresolvable cost is waived, not deferred

**This narrows #146 §9.4, which is four days old, and the narrowing is deliberate.** #146 ruled that
a period closes on time and unresolved events *"appear on the **next** invoice, still attributed to
when they actually happened"*, and it named this exact case in doing so — *"on a markup-priced Event
Type an unknown cost means an unknown price, and an unresolved event is not merely unmeasurable, it
is **unbillable**"*.

The ruling here is that it is never automatically billed at all:

```
costing_status:        unresolved
pricing_status:        waived_unresolved_cost
provider_cost_micros:  null
billed_amount_micros:  0
```

and when the cost later resolves:

```
Resolved COGS:     $0.03
Customer revenue:  $0.00
Gross profit:     -$0.03
```

The owner's rule, verbatim: **no resolvable cost → no automatic customer liability.**

Three things make this the right narrowing rather than a regression.

**It is a fail-safe, and it fails toward the party who owns the mistake.** The unresolved cost is the
tenant's configuration gap. Deferring the charge pushes the consequence onto *their customer*, who
receives a surprise line on a later invoice for work done in a period they have already paid for and
closed. Waiving pushes it onto the tenant, who can fix it.

**A silently deferred charge is worse than a visible loss.** #146's deferral was designed for facts
that arrive late; this is a fact that was never determined. Automatically resurrecting a charge weeks
later, for an event nobody priced at the time, is exactly the kind of quiet money movement #139's
terminal Charge and #146's never-overwrite rule exist to prevent.

**The tenant is not left without a remedy — only without an automatic one.** A later manual recovery
is explicitly available: *"an authorised tenant operator [may] create an explicit adjustment or
supplemental charge, but that must be deliberate, auditable, and customer-facing."*

The exposure must be **highly visible**, not merely recorded:

```
Unresolved-cost events:          4
Unbilled revenue exposure:       unknown
Resolved COGS on waived events:  $12.40
```

This is the same closed loop #146 §11 requires for costs — one alert per *cause*, a live count, a
remediation queue — and it exists so the tenant corrects the Cost Rates or the integration and
*future* events price correctly. That is the whole point: **the loss is the signal, and burying it in
a deferred invoice would remove the signal without removing the loss.**

Note what does **not** change: #146 §9.4's *period close* rule stands. A period still closes on time,
still excludes what it cannot bill, and still reports the excluded amount rather than silently
dropping it (#142's precedent). What changes is only what happens after resolution.

---

## 8. A missing rule means two different things, and mode decides which

### 8.1 The ruling

Rung 5 — *unresolved* — is not one outcome. Its meaning depends on the tenant's **declared operating
mode**, never on what configuration happens to exist:

| | Metering-only tenant | Full-billing tenant |
|---|---|---|
| Expected? | **Yes** — this is the end of the pipeline | **No** — a configuration problem |
| Event | recorded, COGS calculated | recorded, COGS calculated |
| Revenue | **unknown** (null) | **unknown** (null) |
| Margin | unavailable | unavailable |
| Charge | none | none |
| Alert | **no** | **yes** |

The *representation* is identical; the *reaction* differs. That is the whole of the distinction, and
it is why one nullable column serves both.

### 8.2 The metering-only pipeline ends at COGS

```
Operational usage → Supplier Cost Rates → Calculated COGS → stop

optionally: tenant-provided revenue at an appropriate scope → margin analytics
```

> That is the complete and correct result. The system should not manufacture a revenue number merely
> to populate a margin report.

Many such tenants bill their customers through subscriptions managed entirely outside UBB, where
revenue is only meaningful at customer-and-period level:

```
July subscription revenue:  $1,000
July supplier COGS:            $250
July gross profit:             $750
```

UBB must **not** allocate that across individual events. This restates #141's rule — *"any
allocation … is an **explicit analytical policy**, never part of the canonical billing or cost
record"* — and #147 adds nothing to it beyond confirming that the absence of per-event revenue is a
correct terminal state, not a gap to be filled.

### 8.3 Mode is declared, never inferred

**A full-billing tenant with no applicable pricing rule is not equivalent to a metering-only
tenant.** The system must not decide a billing tenant is "metering-only for this event" because
pricing configuration is missing.

This is #146 §2.2's argument arriving from the revenue side. There, a costing mode inferred from a
payload field made a spend ceiling unable to promise anything; here, a pricing posture inferred from
configuration absence would make the single most important alert in the product — *you are not
charging for this* — fire only for tenants who had already configured enough for UBB to notice. The
one tenant who most needs telling is the one who configured nothing.

The mode already exists on the model (`Tenant.billing_mode`, `Tenant.products`) and #141 already
ruled on what it governs — *mode decides who invoices, not whether revenue/margin/COGS exists*. This
document adds the corollary: **mode also decides whether silence is an answer or an incident.**

---

## 9. Arithmetic, bounds and rounding

### 9.1 One percentage, and it is markup on cost

A margin rule stores **markup on cost**. The gross margin it implies is **displayed, never stored**:

```
cost    $1.00
input   30%          (markup on cost)
charge  $1.30
shown   "you keep 23.1% of the sale"
```

Target gross margin — `charge = cost / (1 − m)` — was put and rejected. It is the number a finance
team reports, but as an *input* it is a division that is undefined at 100% and violent just below it:
90% turns $1.00 into $10.00 and 99% into $100.00, so a fat-fingered digit becomes a hundredfold
overcharge. Markup is a multiply and is well-defined at every value.

Offering **both**, each rule declaring which it means, was also rejected. It is structurally cheap —
a rule already declares a method — and that is exactly the trap: it puts two plausible-looking `30%`
inputs in the same UI, producing $1.30 or $1.43 with nothing on the surface to distinguish them.
This is the confusion the deleted uplift also created, in a second form.

The prior art supports the choice without settling it: Stripe's directly competing token-billing
product tells the user to *"set your **markup percentage**"* (research Q4, **medium**), and
OpenMeter's `UnitConfig` docstring illustrates the same operation as *"Cost + 20% margin:
operation=multiply, conversionFactor=1.2"* (**high**) — note that OpenMeter's own example calls a
multiply-by-1.2 a "margin", which is precisely the ambiguity a single stored input removes.

### 9.2 One bound for every markup figure

Today the same number carries two different limits:

| Where | Bound |
|---|---|
| `PlanIn.markup_percentage_micros` (`schemas.py:1023`) | `le=1_000_000_000` — 1000% |
| `TenantMarkupIn.markup_percentage_micros` (`schemas.py:514`) | `ge=0` only — **no upper bound** |

The plan cap carries a reasoned comment — *"a higher value is far more likely a unit error (percent
passed as micros) than a real commercial term"* — and that reasoning is sound. It simply is not
applied to the same number when it arrives through the other door.

**One bound applies to every markup figure, wherever configured**, on #146 §7.2's precedent, which
resolved the identical asymmetry on cost four days ago and for the same reason: *the same value is
accepted if it arrives one way and refused if it arrives another*. The plan cap's typo-protection
rationale is the better of the two and is the one that generalises.

### 9.3 Rounding is #142's, unchanged

The ticket asks whether rounding happens before or after markup. #142 already answered, and the
answer survives intact: markup arithmetic stays **in micros**, half-up on the micro
(`markup_service.py:31-33`), expressed through R4's `round_charge`; the minor unit is reached **once,
on the way out**, with the remainder always carried.

Two of #142's parked notes resolve as a side effect. Its observation that *"a fixed price and a
markup can never both apply"* is now structural rather than circumstantial (§2.1, §3.2). And its
warning that markup *"does not stack on a matched price line … so cost-then-markup-then-price never
composes"* stops being a caveat about today's code and becomes the model.

### 9.4 Markup over a supplier-reported cost is identical

The ticket asks whether markup applies to provider-supplied cost. **Yes, and it is not a #147
question** — #146 §2.1 decided it: *"Everything downstream of COGS is **identical between the two
modes**: margin, the price ladder, the task ceiling, margin reporting, the platform fee,
invoicing."* A `reported` Event Type bypasses cost *derivation* only.

Confirmed here rather than re-opened, with one consequence added: because §7.2 makes an unresolvable
cost waive a margin rule, and because a `reported` kind's cost is unresolvable exactly when the
supplier did not send one, **the `reported` path's failure mode is now a revenue waiver rather than a
mis-costed event.** That is the correct pressure — it lands on the tenant whose integration omitted
the number.

---

## 10. Repricing: forward-dated, and overrides are the grandfathering

### 10.1 The ruling

A book edit takes effect **from a date — now by default — and everyone resolving through that book
moves.** Rating resolves the rule effective at the **event's own timestamp**:

```
Book "Business": 20% -> 25%, effective 1 Aug

Acme  (override 15%)  -> 15%   unchanged
Beta  (no override)   -> 25%   from 1 Aug
Event on 31 Jul       -> 20%   resolves at its own date
```

**Backdating is refused.** `effective_from` must be now or later.

### 10.2 The ticket's question, answered

> Markup edits are live today while fee edits are grandfathered because Stripe Prices are immutable.
> Does live-markup survive when pricing becomes versioned?

**It survives, and the asymmetry it sits on is now explained rather than merely deliberate.** The
comment at `plans/models.py:44-45` states the fact — *"Markup has no Stripe object and is therefore
always live — the asymmetry is deliberate"* — without saying why that is acceptable. It is
acceptable because the two axes are different **kinds** of object: a Stripe Price is a foreign,
immutable record with a subscriber pinned to it, and grandfathering is the only thing immutability
permits; a pricing rule is UBB's own effective-dated record, and forward-dating is strictly more
expressive than immutability plus migration.

What changes is that "live" now means **effective-from-an-instant** rather than *whatever the row
currently says*. For future events the behaviour is identical. For late-arriving and replayed events
it is the difference between correct and wrong — and #146 made that load-bearing:

> replay-at-original-timestamp makes historically accurate rate resolution **load-bearing for
> correctness**, not only for reporting: an event resolved late must resolve against the rate
> effective when it happened, or the fix silently mis-costs it.

### 10.3 Negotiated deals are already insulated — so no version-pinning is built

Per-customer version pinning was put and rejected. It would make the two plan axes symmetric, but it
needs a pin, a migration action, a way to see who is on what, and a policy for what happens to
customers nobody migrates.

It is unnecessary because **the override rung already is the grandfathering mechanism.** A customer
whose price was negotiated has an override, and an override outranks the book at its own specificity
level (§5.1) — so a book edit cannot touch them. A customer with no override never negotiated
anything and is on the tenant's standard terms, which is what a standard-terms change is for.

This is worth stating plainly because it is the payoff of §5.2's ordering: choosing
specificity-major bought a repricing model for free.

### 10.4 Why backdating is refused

The routine case is real — *"we agreed 25% from the 1st, but I'm only configuring it on the 3rd"* —
and it is still refused, because permitting it re-prices events that were **already priced**.

- On the cost side, #146 §9.1 forbids overwriting a costed event; the same reasoning applies with
  more force to revenue, which may already have been invoiced.
- #139 established that **no re-invoice path exists anywhere**, so a backdated edit crossing a period
  boundary produces a correction with nowhere to land.
- The research names this exact failure at Metronome, where regeneration *"recalculates the invoice
  based on **up-to-date rates**"* and the caveat is explicit: the past window re-resolves the same way
  *"unless someone has since added a backdated rate"* (**high** for the quote).

The two-to-three-day shortfall is instead **one explicit adjustment, on the record** — the same
deliberate, auditable, customer-facing mechanism §7.3 requires for recovering a waived event. One
mechanism, used twice, both times leaving a trace.

---

## 11. Answers to the ticket's six questions

**1. Is markup a layer or a fallback? Should a matched price rule be markup-able?**
**Neither — the binary is false.** One rule resolves per event and declares one of two alternative
methods (§1.1, §2). A configured price means what it says: **no**, a direct price is not
markup-able. Today's behaviour is broadly right and today's *model* is wrong; precedence exists
between *rules*, never between *methods*.

**2. Does markup apply to provider-supplied cost?**
**Yes — decided by #146 §2.1, confirmed not re-opened** (§9.4). Everything downstream of COGS is
identical between calculated and reported costing. The new consequence is that a `reported` kind
whose supplier sent no cost now waives revenue (§7.3).

**3. Does markup apply to a fixed price per task?**
**No** — reaffirming #139, and sharpened: it is not the fixed price that suppresses event pricing but
the task's declared `pricing_mode = fixed`, snapshotted at creation, which suppresses **both**
methods. Belonging to a task is not itself a reason to suppress anything (§3).

**4. Where does markup live once Event Type owns pricing?**
**In the Pricing Book, and nowhere else** (§4). Plan selects a book; customers inherit and may hold
replacement overrides. `TenantMarkup` and the Plan's two markup fields are deleted. Resolution is
four rungs with **specificity before source** (§5), and **Event Category is not a rung** (§6.1).

**5. Is percentage-plus-fixed-uplift still the right shape, and does rounding happen before or
after?**
**Percentage yes, uplift no.** One number — markup on cost, implied margin displayed not stored
(§9.1) — with one bound wherever it is configured (§9.2). The per-event uplift is deleted (§6.2).
Rounding is unchanged from #142: micros throughout, half-up on the micro, minor unit reached once on
the way out (§9.3).

**6. Repricing semantics — does live-markup survive versioning?**
**Yes, re-founded as forward-dated effectivity** (§10). Edits move everyone resolving through the
book from an effective date; rating resolves at the event's own timestamp, which is what makes
#146's replay correct rather than merely tidy. Negotiated overrides *are* the grandfathering
mechanism, so none is built. Backdating is refused (§10.4).

---

## 12. What each existing thing becomes

| Today | Becomes |
|---|---|
| `TenantMarkup` (`pricing/models.py:8`) | **Deleted** — absorbed into Pricing Book rules (§4.2) |
| `TenantMarkup.fixed_uplift_micros` (`:17`) | **Deleted** (§6.2) |
| `TenantMarkup.calculate_markup_micros` (`:32-34`) | **Kept in substance** as the margin method's arithmetic; expressed via #142's `round_charge` (§9.3) |
| `MarkupService.resolve` four-rung chain (`markup_service.py:47-64`) | **Replaced** by the four-rung *rule* ladder (§5.1) — same depth, different subject |
| `MarkupService.apply` fallback `return provider_cost_micros` (`:71`) | **Deleted** — no rule now means revenue **unknown**, not revenue == cost (§7.1) |
| `ResolvedMarkup.source ∈ {customer, plan, tenant_default}` (`:20`) | **Re-founded** as which rung of §5.1 resolved; `plan` disappears as a source (a plan selects a book, it is not a rule) |
| `Plan.markup_percentage_micros`, `Plan.fixed_uplift_micros` (`plans/models.py:33-34`) | **Deleted**; Plan gains a Pricing Book reference (§4.1) |
| `Plan.access_fee_micros` / `per_seat_micros` (`:28-29`) | **Unchanged** — Stripe-realized, still grandfathered on edit (§10.2) |
| `Plan.pricing_version` (`:46`) | **Narrowed** — tracks only the Stripe-realized axes now; policy effectivity is the book's (§10.1) |
| `Plan.has_stripe_axes` (`:60-66`) | **Kept**; its "markup-only plan" example becomes "a plan that names a book and charges no fee" — still no Stripe presence |
| `get_plan_markup_for_customer` (`plans/queries.py:9-26`) | **Deleted** — replaced by a read contract returning the customer's resolved *rule*, not a markup pair |
| `_invalidate_markup_cache` on Plan save/delete (`plans/models.py:68-76`, `:104-126`) | **Kept in role, re-keyed** — a plan edit still changes which book applies |
| `MarkupCache` / `CardCache` | **Kept in role, re-keyed** to the §5.1 ladder; #145 already collapsed the card key |
| `PricingService._compute`'s price branch (`pricing_service.py:145-167`) | **Rewritten** — resolve one rule, apply its method; the `matched`/fallback structure is deleted (§2) |
| `PricingService._resolve_card` three-tier book walk (`:67-92`) | **Deleted** — already required by #138; §5.3 confirms no cross-book fallthrough |
| `prov["price_source"] ∈ {caller, rate_card, markup}` (`:148`, `:164`, `:167`) | **Re-founded** — `caller` already deleted by #146 §8; the remaining two become "which rung, which method" |
| `UsageEvent.billed_cost_micros` (`usage/models.py:42`) | **Nullable** — null is unknown, `0` is free-or-waived, `pricing_status` says which (§7.1) |
| `Task.total_billed_cost_micros` (`tasks/models.py:114`) | **Must not sum null as zero** — same treatment #146 §4 required of the cost rollup |
| `queries.py:301` `markup_micros = (billed or 0) - (provider or 0)` | **Broken by §7.1 and must change** — the `or 0` coalescing is exactly the silent-zero #146 §4 forbids |
| `total_markup_micros` / `usage_markup_margin_micros` (`queries.py:92`, `schemas.py:581`, `:593`) | **Must gain an unavailable state** — a markup total over any unknown revenue is itself unknown |
| `GET`/`PUT /metering/pricing/markup` (`metering_endpoints.py:364`, `:376`) | **Deleted** — a tenant default markup is a book default rule |
| `GET`/`PUT`/`DELETE /metering/pricing/customers/{id}/markup` (`:406`, `:419`, `:451`) | **Deleted** — a customer markup is a customer override rule |
| `TenantMarkupIn` / `TenantMarkupOut` (`schemas.py:513-520`) | **Deleted** with their endpoints; note both return `0/0` when nothing is configured — the same zero-impersonating-unset defect §7.1 removes |
| `PlanIn`/`PlanUpdateIn` markup + uplift fields (`schemas.py:1023-1024`, `:1050-1051`) | **Deleted**; `PlanIn` gains a book reference |
| `le=1_000_000_000` on plan markup only (`schemas.py:1023`) | **Generalised** — one bound on every markup figure (§9.2) |
| `test_zero_markup_plan_shadows_tenant_default_and_pins_provider_cost` (`test_markup_service.py:91-100`) | **Loses its subject** — plans carry no markup; the invariant it protects is re-expressed as "a book default rule of 0% is a written rule, and no rule at all is `unresolved`" (§4.3) |
| `test_plan_markup_beats_tenant_default` ("THE REVENUE LEAK, PINNED", `:51-59`) | **Re-expressed against the new ladder** — the leak it guards (a customer silently priced at a broader default) is now guarded by §5.1 rung 3 and must keep a test |
| `EventCategory` (#138) | **Kept as analytics only** — removed from price resolution; its effective-dating requirement retires with it (§6.1) |
| — | **New:** Pricing Book rule with a declared method; `CustomerPricingOverride`; `Task.pricing_mode` + its snapshot; `pricing_status` incl. `waived_unresolved_cost`; the waived-revenue exposure report |

---

## 13. Constraints this imposes on other tickets

- **#148 (pricing versions)** — **gains** book/rule effective-dating as the mechanism behind §10, and
  the hard rule that `effective_from` may not be in the past (§10.4). **Loses** #138's requirement
  that Event Category membership be effective-dated (§6.1). Must also reproduce the resolved *rule*,
  not just the resolved rate, since the method is part of what was applied.
- **#150 (spend limits re-modelled)** — unaffected in substance: ceilings race COGS, and §7 changes
  revenue only. But a waived event (§7.3) is a task with real COGS and no revenue, so a *margin*
  guard — if one is ever wanted — cannot be built on the same footing as a COGS ceiling.
- **#151 (charging modes)** — inherits the two methods and `Task.pricing_mode` as the charging
  vocabulary, plus the rule that no rule resolving is mode-dependent (§8) rather than an error
  everywhere.
- **#152 (task dashboard and reporting)** — must show **margin unavailable** distinctly from margin
  zero, and must host the waived-revenue exposure report (§7.3) beside #146's unresolved-cost queue.
  A dashboard that renders unavailable margin as 0% reintroduces exactly the lie §7.1 removes.
- **#153 (analytics re-alignment)** — inherits the most. Every margin and markup surface must handle
  null revenue explicitly; `queries.py:301`'s `or 0` coalescing is a named defect. Event Category
  becomes a *reporting* axis with no monetary meaning, which is a repositioning #153 owns.
- **#154 (vocabulary)** — names owed for: the rule and its two methods; the Pricing Book (already
  contested between "book"/"policy set" in #138); the customer override; `pricing_status` and the
  value `waived_unresolved_cost`; `Task.pricing_mode`. Note "markup" is retained deliberately — it is
  the word Stripe's competing product uses — and must not drift into "margin", which now names only
  the *displayed* derived figure (§9.1).
- **#155 (onboarding and cutover)** — a tenant must choose an operating mode explicitly (§8.3), and
  migration must carry existing `TenantMarkup` rows and `Plan` markup values into book default rules
  and customer overrides. The mapping is mechanical **except** where a plan's `0` markup was
  "axis absent" rather than "zero" (§4.3) — those cannot be distinguished from the data and need a
  tenant decision.
- **#156/#157 (Code Builder)** — can now state a call's price from configuration alone when the rule
  is a direct price, and must state "cost + N%" honestly when it is not. Both are generatable
  precisely because §2 made the output of one rule independent of every other.
- **#165 (splitting `UsageEvent`'s measurement record from its economic posting)** — **unblocked, and
  the answer leans toward the split.** #145 blocked it on this ticket *"since what a posting must say
  about unknown revenue determines whether a separate record is needed at all"*. The answer: a
  posting must carry three revenue states plus a `pricing_status`, alongside #146's three cost
  states — so the economic posting now has substantially more state than the measurement record, and
  they change at different times (a measurement is complete at ingest; a posting may resolve, waive,
  or stay unknown for weeks). That is the seam.
- **#149 (streaming: one event or many?)** — **relieved of a hazard.** With the per-event uplift
  deleted (§6.2), splitting one call into many events no longer multiplies a flat fee. #142's
  sub-micro rounding warning still applies.

---

## 14. Residue, flagged not buried

- **Nothing decides when a waived event stops mattering.** §7.3 reports the loss and leaves it
  reported. #146 left the same gap for unresolved costs and named it deliberately; the two should be
  answered together, by whoever owns the remediation queue, not separately.
- **Manual recovery is endorsed but unspecified.** §7.3 and §10.4 both route to *"an explicit
  adjustment or supplemental charge — deliberate, auditable, customer-facing"*, and no such mechanism
  exists today. #139 established there is no re-invoice path, so this is a **new** surface with two
  callers already. It is the largest unbuilt thing this document depends on.
- **A blanket customer override still shadows a book default the tenant may have thought specific.**
  §5.2 fixes the sharp case (exact rules survive), but a tenant whose book default *is* their
  considered pricing still loses it to any customer override. That is correct, and it is the kind of
  thing the console must show — "this customer does not use your default" — rather than the model
  fix further.
- **Whether an override may change a rule's *method*, not just its number, is unstated.** Can Acme's
  override turn a book's `direct_event_price $0.02` into `margin_over_cost 15%` for that event type?
  Nothing here forbids it and nothing requires it. It should be answered before the console is
  designed, since it decides whether the override editor is a number field or a rule editor.
- **`Plan` with no book is undefined.** §4.1 has Plan select a book, but a fee-only plan for a
  full-billing tenant who prices usage nowhere is representable and lands on §8's error path. Whether
  the book reference is required or nullable is a small decision with a visible consequence.
- **The migration cannot distinguish a plan's "absent" markup from a deliberate zero** (§4.3, and
  #155 above). Both are `0` in the column today. Every affected tenant needs asking, and the number
  of them is knowable from the data — that count should be produced before cutover, not after.
- **`Task.pricing_mode`'s snapshot has no stated interaction with subtasks.** #140 settled one
  containment level with depth as a dimension; whether a subtask may differ from its parent's pricing
  mode is not decided here and should be, by #151.
