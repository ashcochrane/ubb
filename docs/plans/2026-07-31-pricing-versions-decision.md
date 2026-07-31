# Pricing versions — the receipt is the record, effective dating is the only axis, and the past is filled, never rewritten

**Resolves:** [#148](https://github.com/ashcochrane/ubb/issues/148) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-31
**Decided against:** `main` @ `84e53d5`
**Evidence:** `docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch
`research/pricing-model-prior-art` @ `2f0ce4c`) — **Q5** is this ticket's subject end to end: Stripe's
and Orb's immutable-price-plus-pin, Metronome's half-open effective segments with `getRates(at)`,
OpenMeter's derived-not-stored status (`PlanMeta.StatusAt(t)`), Lago as the cautionary case that
*"cannot answer 'what would this invoice have been under the price in effect on date X'"*, and the
finding that **nobody stamps the price onto the event** — addressed directly in §3.3 rather than
worked around.
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — the blocking
ticket; effective dating survives its cull, `card_type` and the wildcard/specificity engine do not.
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the fixed price is pinned at
start and the `Charge` is immutable with **no re-invoice path anywhere**, which is half of why §2
declines recalculation.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — terminal is terminal.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — **unknown revenue ≠ zero**, and
mode decides who invoices, not whether economics exist; §3.3 leans on the second half.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — the receipt records a denominated value, so
it records the currency.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — the collapsed cost key
`tenant + event_type + measurement + timestamp` is what makes `lineage_id` redundant (§5.3).
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — **replay at the original
timestamp**, named here as load-bearing for correctness; §7 resolves the fact that its remediation
loop, as written, cannot close.
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — §10's forward-dated
effectivity is the mechanism this ticket was told to supply; §13 required this ticket to reproduce
*the resolved rule, not just the resolved rate*. §6 supplies the mechanism, which does not currently
exist.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** Same reasoning as #138 through #147: #154 is the single naming pass, and
this document coins three nouns, one enum value and two published promises (§16). The ADR is owed
*after* #154 and should cite all nine decision documents.

---

## The decision in one paragraph

**The guarantee is explanation, not recalculation**, and that single choice pays for everything else.
Re-running a closed period was never going to be actionable — #139 left no re-invoice path anywhere,
#147 §10.4 refuses to move a posted number, and #146 §9.1 makes a correction an entry beside the
original — so a recalculation that disagreed with history would have had nowhere to land. What we
promise instead is that **every charge carries its own receipt, and the receipt is the truth**: not
the rules, and not both-and-reconcile, because the rules are guaranteed to move underneath it and
#147 §12 deletes the ones that priced most of history outright. The receipt therefore carries
**values, not pointers** — a pointer is only as good as the row it points at — and stops being an
untyped blob: it becomes a **validated, self-versioning domain record** with `receipt_schema_version`
and `pricing_engine_version` as separate facts, discriminated `costing` / `pricing` / `totals` /
`provenance` sections each declaring a method *and* a status, and four pricing statuses — `known`,
`unresolved`, `waived`, `not_applicable` — so that unknown revenue, free, waived and inapplicable can
never collapse into the same absent field. On the rules side the ticket's four mechanisms collapse to
**two**: **effective dating is the sole resolution axis**, and an immutable **Pricing Book Publish**
record carries audit, scheduling and provenance while never participating in resolution — the
book-version range and `lineage_id` are deleted, having been written by three paths, read by none.
Repricing becomes a **diary, not an alarm**: a future-dated change is persisted immediately with its
effective date, nothing executes at the boundary, and one shared instant closes the outgoing rule as
it opens the incoming one — which also closes the microsecond hole that `auto_now_add` opens on every
supersession today. Publishes stay **forward-only forever**; a historical gap is filled by a separate
**remediation** action scoped by construction to `unresolved` records only, which may complete COGS
and reporting but **never auto-back-bills and never rewrites posted money** — and which resolves the
fact that #146's remediation loop, as written, could not close. The accept-vs-settle gap **closes
fully**: estimation resolves at the event's own timestamp like settlement does, the rate cache becomes
time-aware because forward-dating otherwise breaks it, and `Estimate.exact` — a boolean its own
docstring concedes is asserted rather than established — is deleted. For a fixed-price task **revenue
is pinned and cost floats per event**, because the price was promised and the cost is merely observed.
Receipts live **six years as a published promise**, and the receipts written before this document
exists get a **clean break** — a one-time exercise of #137's constraint 1 that must never be cited as
a precedent.

---

## 1. The ticket's premise, corrected

The ticket asks which of four mechanisms survive, and calls the set *"a lot of machinery for one
guarantee."* That is generous in one direction and unfair in the other.

### 1.1 Three of the four are inert

| Mechanism | What it does today |
|---|---|
| `Rate.valid_from` / `valid_to` (`pricing/models.py:91-92`) | the **only** thing resolution reads |
| `Rate.book_version_from` / `book_version_to` (`:88-89`) | written; read by nothing but the tests that assert it was written |
| `Rate.lineage_id` (`:90`) | written, copied on supersession, serialized to SDK and UI — **queried nowhere** |
| `RateCard.version` (`:146`) | a publish counter feeding `__str__` and an audit blob |

Resolution is `_resolve_rate_within` (`pricing_service.py:40-43`), and it filters on `valid_from` and
`valid_to` alone. The history endpoint (`metering_endpoints.py:768-773`) filters on the same dates.
Neither consults a version. `RateOut` (`schemas.py:845-867`) does not expose the version columns at
all.

So the machinery is not four mechanisms serving one guarantee. It is **one mechanism doing the work
and three keeping it company.**

### 1.2 The version columns are also written three different ways

Worse than unread: inconsistently written, by three paths that disagree.

- `publish_book` → `BookService.publish` supersedes rates, bumps `RateCard.version`, and sets both
  `book_version_from` and `book_version_to` (`book_service.py:33`, `:48-49`, `:59-60`).
- `add_rate` stamps `book_version_from = book.version` **without bumping the version**
  (`metering_endpoints.py:809`).
- `delete_rate` soft-expires by stamping `valid_to` and **never sets `book_version_to`**
  (`metering_endpoints.py:892-896`).

An expired rate can therefore carry a NULL `book_version_to`, and two rates can share a
`book_version_from` without belonging to the same publish. Even a reader who started consulting these
columns would get wrong answers. This is the strongest argument for deletion in §5: the columns are
not merely unused, they are **already incorrect**, and nothing noticed because nothing looked.

### 1.3 Two things the ticket does not mention, both load-bearing

**`Rate.valid_from` is `auto_now_add=True`** (`models.py:91`). A rate's effective date is always the
instant its row was inserted. `BookService.publish` says so in its own docstring: *"future-dated
scheduling is not supported because the new rate's `valid_from` is auto-stamped at insert."* But #147
§10.1 **requires** forward-dating — *"a book edit takes effect from a date — now by default"*, with
`effective_from` constrained to now or later. **The mechanism #147 assumed exists does not exist.**
§6 builds it.

**`TenantMarkup` has no effective dating at all** — no `valid_from`, no `valid_to`, no lineage
(`pricing/models.py:8-30`). Markup is the *default* path: `_compute` falls to it whenever no price
rate matches (`pricing_service.py:165-167`). So the pricing engine's most-travelled path is entirely
unversioned while its least-travelled path is versioned twice. #147 §4 dissolves this by moving markup
into the Pricing Book as a `margin_over_cost` rule, which brings it under the book's effective dating
for free — a payoff #147 did not state and this document records.

### 1.4 There is no recalculation path, and there never has been

A scoped sweep of `apps/`, `api/`, `core/`, `config/` and `scripts/` for `reprice`, `recalculat*` and
`replay` returns only Stripe webhook idempotency, stop-signal replay and drawdown repair. **Nothing
re-prices a usage event.** The guarantee the ticket asks us to preserve has never been provided, which
usefully lowers the cost of §2's answer: we are not withdrawing a promise, we are declining to make
one.

---

## 2. The guarantee is explanation, not recalculation

### 2.1 The ruling

Two promises were on the table:

| | Promise |
|---|---|
| **A** | *"We can tell you why we charged you that."* |
| **B** | *"We can re-run last March and get the same numbers."* |

**We promise A. We do not offer B.**

### 2.2 Why B has nowhere to land

B is not merely expensive; under the decisions already merged its output is **inert**.

- **#139** established there is no re-invoice path anywhere, and made the `Charge` immutable.
- **#147 §10.4** refuses backdating outright, because *"a posted number never moves"*.
- **#146 §9.1** forbids overwriting a costed event; corrections are entries beside the original.

So a re-run that disagreed with history could not correct the invoice, could not amend the posting and
could not move the number. The only permitted response is a deliberate, customer-facing adjustment —
which is justified by a commercial decision, not by a recalculation. **B's answer has no consumer.**

The research says the same about the market. Stripe has *"no re-rate, replay or reprice endpoint
across the meter, meter-event, meter-event-summary or price references"*, and corrections happen at
the invoice layer: **"the invoice is the immutable record"** (**medium-high**, negative established
across the full surface read). Amberflo's corpus sweep returns `recalculat*` **0** and `replay` **0**,
with the correction path being *"cancel-and-re-ingest, not re-rate"* (**high**). Metronome offers
regeneration and it is the cautionary case, not the model — see §7.4.

### 2.3 The thing that looks like B and is not

#146 requires an unresolved-cost event to be **replayed at its original timestamp** once its cause is
fixed. That is not re-calculating something already calculated. It is calculating it **for the first
time, late**: the event was recorded with a null cost and is being priced now.

This distinction carries real weight and is easy to lose:

```
recalculation     a number exists   → compute it again → compare
remediation       no number exists  → compute it once  → fill
```

Declining B does not decline remediation. §7 gives remediation its own mechanism precisely so the two
can never be confused at the point of implementation.

---

## 3. The receipt is authoritative

### 3.1 The ruling

When someone asks why a charge is what it is, **the answer is read from the receipt stored with the
event**. Not re-derived from the rules; not derived-and-reconciled.

### 3.2 Why not the rules, and why not both

**Not the rules**, because the rules are guaranteed to move. #147 §10.1 makes a book edit move
everyone resolving through it, and §12 deletes `TenantMarkup`, both `Plan` markup fields and four
endpoints outright — so after that migration *every markup-priced event in history has no rule left to
re-derive from.* A rules-based answer is a confident, well-formatted, wrong answer with a citation,
which is worse than no answer.

**Not both**, because two sources of truth that must agree are two sources of truth that can disagree,
and nothing here says which wins. "They must agree" is also promise B wearing a different hat: it is
exactly the reproducibility guarantee §2 declined, reintroduced as an invariant.

**Lago is the live demonstration.** Its `Fee` row stores a full computed snapshot — `amount_cents`,
`amount_details`, `precise_amount_cents`, `units`, `taxes_rate` — but on a *draft* invoice the fees are
`destroy_all`'d and re-derived at the new price when the plan is edited. The research names the
consequence exactly: **"fees are a *cache*, not a snapshot"**, and *"Lago cannot answer 'what would
this invoice have been under the price in effect on date X'"* (**high**). A snapshot that is ever
re-derived is not a snapshot. §4's immutability is the guard against becoming Lago.

### 3.3 The divergence from prior art, stated plainly

The research is unambiguous and it does not support us:

> **Nobody stamps the price onto the event.** The snapshot always lives at the invoice line item, the
> subscription item, or the rate schedule — never on the usage record. … it has **zero prior art
> across all six platforms**.

That finding is accepted, not disputed. Three things make it a difference in product rather than a
mistake, and the document states them rather than letting a future reader discover the gap alone.

**The comparison is not like-for-like.** Those platforms *do* stamp the price onto the billed
artifact — Orb embeds the complete `price` discriminated union on each invoice line item, and
OpenMeter denormalises the whole rate card into the subscription item's own columns under a literal
`// RateCard Fields` comment. They snapshot one level up from the event because **the invoice line is
the smallest thing they need to explain.**

**That level does not always exist here.** #141's governing invariant is that *mode decides who
invoices, not whether revenue, margin and COGS exist*. A `meter_only` tenant produces no invoice, no
subscription item and no line item — and still has costs, prices and margin that must be explicable.
The posting is the lowest level that **always** exists, and for a third of UBB's tenants it is the
only level that exists at all.

**The grain is the product.** Orb needs to explain an invoice line. #152 and #153 need to explain
margin per event, per task and per dimension. An invoice-level snapshot cannot answer *"why is this
one call's margin negative"*, which is the question UBB is for.

And #165 narrows the divergence further: once the measurement record splits from the economic posting,
"on the event" becomes "on the posting" — which **is** Orb's line item, at a finer grain and without
requiring an invoice to exist.

### 3.4 What this buys

Once the receipt is authoritative, **effective-dated rules are no longer needed for explanation at
all.** They are needed for exactly one thing: pricing something *for the first time, late* — #146's
replay, and a backfilled event arriving with a past timestamp. That is a far smaller job than
"reconstruct any historical answer", and it is the entire reason §5 can delete three of four
mechanisms without weakening anything.

---

## 4. The receipt becomes a typed, self-versioning record

### 4.1 The ruling

`pricing_provenance` stops being a free-form dictionary and becomes a **validated, immutable,
schema-versioned domain record**. It stays JSON — the shape legitimately varies — but it acquires a
declared structure, a version, and a validator at the single point of construction.

### 4.2 The evidence that discipline is not enough

`UsageEvent.pricing_provenance` is `models.JSONField(default=dict, blank=True)`
(`usage/models.py:43`), typed on the way out as bare `dict` (`schemas.py:251`), and echoed unread by
the detail endpoint (`metering_endpoints.py:259`).

The consequence is already in the repository. `test_get_event_returns_full_receipt` — the one test
guarding the receipt endpoint — hand-builds a blob keyed `price_card_id` and asserts that key comes
back (`api/v1/tests/test_metering_endpoints.py:255-269`). Production has only ever written
`rate_card_id` (`pricing_service.py:138`, `:157`). The test passes because nothing validates anything.
**The receipt has already drifted into two spellings of one field, and the test certifying it asserts
the spelling nothing writes.**

That key also holds a **`Rate`** id, not a `RateCard` id — the naming wart the model docstring already
confesses to.

### 4.3 Two versions, because they answer two questions

```
receipt_schema_version    "How do I parse this historical record?"
pricing_engine_version    "Which calculation code produced it?"
```

Both sit at the **top level**, explicitly, never inferred from which fields happen to be present.
Today they are conflated into one hand-maintained constant, `PRICING_ENGINE_VERSION = "2.1.0"`
(`pricing_service.py:9`), which answers the second question and is silently relied on for the first.

Under §2 the engine version is a **forensic breadcrumb** — you will never re-run that code, so it is
worth exactly what it costs, which is nothing — while the schema version is what a reader in 2032
needs to parse a receipt written in 2026 under a six-year retention promise (§10). This document alone
changes the shape substantially.

### 4.4 The shape

A stable outer structure with validated, discriminated sections:

```
PricingReceipt
  receipt_schema_version: 1
  pricing_engine_version: "2.1.0"
  effective_at: ...
  currency: USD

  costing:     method + status + method-specific detail
  pricing:     method + status + method-specific detail
  totals:      the denominated outcomes
  provenance:  cross-reference ids only
```

**Costing** declares `method ∈ {calculated, reported, none}` and
`status ∈ {known, unresolved, not_applicable}` — #146's two costing modes and its third state, made
explicit rather than inferred:

```
costing:                          costing:
  method: calculated                method: reported
  status: known                     status: known
  components:                       reported_cost_micros: 30000
    - measurement: input_tokens     source: provider_event
      quantity: 100000
      rate_amount_micros: 300000
      rate_unit_quantity: 1000000
      resulting_cost_micros: 30000
  total_provider_cost_micros: 30000
```

**Pricing** declares `method ∈ {margin_over_cost, direct_event_price, fixed_task_price, none}` —
#147's two methods, plus #139's fixed task price, plus the honest absence — and
`status ∈ {known, unresolved, waived, not_applicable}`:

```
pricing:                          pricing:                      pricing:
  method: margin_over_cost          method: direct_event_price     method: none
  status: known                     status: known                  status: not_applicable
  applied_markup_percentage: 20     applied_direct_price_micros:   totals:
  billed_amount_micros: 36000         20000                          provider_cost_micros: 30000
                                    billed_amount_micros: 20000      billed_amount_micros: null
```

**This extends #147 §7.** That document gave revenue three states — known, waived, unknown. The fourth,
`not_applicable`, is the metering-only terminal #147 §8.2 described as *"the expected, silent end of
the pipeline"* but did not name. Naming it is what stops a dashboard reading silence as zero. Four
distinctions must survive the round trip and must never collapse into the same combination of absent
fields and zeroes:

```
unknown revenue          ≠  explicitly zero revenue
waived customer liability ≠  pricing not applicable
```

### 4.5 Validation, and what it refuses

Validation happens at the **single receipt-construction boundary**, before persistence:

```
compute receipt → validate against receipt_schema_version → persist immutable receipt
```

The production writer **rejects an invalid receipt rather than storing a partial explanation.** That
is the same instinct as #146's "nothing is refused" applied one layer down and inverted: an *event* is
never refused for being uncostable, but a *receipt* that cannot explain itself is not a receipt and
must not be written as one.

The construction point is `_compute` and the persistence point is `usage_service.py:422` — one seam,
one validator. The test that pins it is that **production's own writer output validates**, across
every supported costing and pricing path. That is precisely the test that would have caught
`price_card_id`, and it satisfies the repo's ratchet rule of backing a hard rule with a test.

### 4.6 Old receipts are read, never rewritten

```
receipts created under schema v1  →  remain v1  →  parsed with the v1 reader
new requirements                  →  schema v2  →  new receipts only
```

A migration rewrites historical receipts **only** where there is a specific, audited correction
requirement — never merely to make old rows resemble the newest shape. Rewriting a receipt to tidy it
is indistinguishable, after the fact, from rewriting it to change what it says.

### 4.7 Pointers may ride along; values are authoritative

Ids survive in the `provenance` section as cross-reference:

```
provenance:
  cost_rate_ids: [...]
  pricing_book_publish_id: ...
  matched_rule_id: ...
  customer_override_id: ...
  remediation_id: ...        # §7.3, present only on a remediated posting
```

They are for navigation and forensics. **Explanation never dereferences them**, because #147 §10.1
guarantees the rows they point at move. The one pointer that is safe to store is the publish id (§5.4)
— because a publish record is immutable by construction, it is the only cross-reference that means the
same thing forever.

---

## 5. Four mechanisms become two

### 5.1 The ruling

| Mechanism | Fate |
|---|---|
| `valid_from` / `valid_to` | **Survives** — the sole resolution axis |
| `book_version_from` / `book_version_to` | **Deleted** |
| `lineage_id` | **Deleted** |
| `RateCard.version` | **Promoted** to an immutable Pricing Book Publish record |

### 5.2 Why the version range goes

It is a second encoding of the fact `valid_from` / `valid_to` already carries. Two encodings of one
fact can disagree — and per §1.2 **these already do**, because three write paths maintain them three
different ways. When two encodings disagree, the wrong one is always the one nobody is looking at.

OpenMeter is the prior art for the direction: `PlanMeta.StatusAt(t)` derives draft / active / archived
/ scheduled / invalid **from the dates** — *"status is derived, not stored"* (**high**). A version is
not a second axis to resolve along; the dates already say everything the version would.

### 5.3 Why `lineage_id` goes

Its only consumer anywhere is dead code. `ubb-sdk/ubb/metering.py:320-322` ships
`get_rate_card_history(lineage_id)`, calling `/api/v1/metering/pricing/rate-cards/{lineage_id}/history`
— a path that exists in neither `metering_endpoints.py` nor `openapi/v1.json`, which ADR-002 makes the
single source of truth. Its test passes because it mocks the HTTP call. Server-side, no query has ever
touched the column.

It is also now redundant on the merits. #145 collapsed the cost key to
`tenant + event_type + measurement + timestamp`, and #147 §5.1 makes a rule target one Event Type. The
rule's **natural identity is its target**, so *"show me this price's history"* is a query on that
identity across dates. A synthetic identity adds nothing the natural key does not already give, and
costs a column that must be correctly propagated by every future write path.

### 5.4 Why the book version is promoted rather than kept or deleted

A **Pricing Book Publish** becomes a first-class immutable record: an id, an `effective_from`, the
actor, and what changed. Three things it does that an integer counter cannot.

**It names the act.** Twelve rules changing at 09:04:12 is not self-evidently one decision. *Publish
#7, effective 1 August, by Dana, 12 rules* is.

**It gives forward-dating something to schedule and cancel.** §6 requires future-dated changes. Two
publishes pending for 1 and 15 August are, without a record, rows recoverable only by grouping on a
timestamp — and a tenant who can schedule a change must be able to cancel it before it lands, which
needs an object to cancel.

**It is the one pointer worth storing.** Per §4.7, ids are demoted to cross-reference because the rows
they point at move. A publish record never moves. It is the stable cross-reference the receipt's
`provenance` section can safely carry.

**It is emphatically not a resolution axis.** Resolution reads dates and only dates. That separation
is what makes this a collapse from four mechanisms to two rather than a rename of the same four.

Prior art supports the split. OpenMeter versions plans by identity — `PlanMeta{Key, Version,
EffectivePeriod}` — while resolving status from `EffectivePeriod`. Metronome maintains
`POST /v2/contracts/getEditHistory`, *"a full history of all edits that were ever made to a
contract"*, **alongside** its effective-dated rate schedule rather than instead of it (**high**).
Identity and effectivity are two jobs, and every platform that does both well does them separately.

---

## 6. Repricing is a diary, not an alarm

### 6.1 The ruling

A future-dated change is **persisted immediately, dated forward**. Nothing executes at the moment it
takes effect.

```
Today (28 Jul), tenant schedules 20% → 25% effective 1 Aug:

  rule A  [.. , 1 Aug)   20%     ← valid_to written now
  rule B  [1 Aug, ..)    25%     ← valid_from written now, in the future

Event on 31 Jul → resolves A.  Event on 2 Aug → resolves B.  No job ran.
```

### 6.2 Why not a scheduled job

A job has a failure mode: if it is late, every event in the gap prices at the old rate — and under §3
that wrong price is now permanently on an **authoritative** receipt, in a system with no re-invoice
path. The diary has no job, so it has no failure mode. Reading a date range is already what
`_resolve_rate_within` does (`pricing_service.py:40-43`); it has simply never had future rows to find.

Metronome models a price change the same way — *"adding a new rate with a future `starting_at`"* over
half-open `[starting_at, ending_before)` segments (**high**).

### 6.3 Every change to a book is a publish

Today repricing is versioned and audited while adding and retiring a rule are immediate and
unversioned (§1.2) — which is *why* the version columns disagree. One path replaces three:

| Act | Today | Becomes |
|---|---|---|
| add a rule | immediate, unversioned | a publish |
| reprice a rule | versioned publish | a publish |
| retire a rule | immediate, unversioned | a publish |

This also gives the console one thing to show a tenant — *"your book changes on 1 August; here is the
diff"* — instead of three unrelated mutation surfaces.

### 6.4 One clock closes and opens the boundary

The outgoing rule's `valid_to` and the incoming rule's `valid_from` are both **the publish's
`effective_from`, the same value.** With the half-open range already in use, that is exactly no gap
and exactly no overlap.

**This fixes a live bug.** `BookService.publish` stamps `old.valid_to = as_of` and then inserts the
replacement, whose `valid_from` is `auto_now_add` — the instant of insert, strictly *after* `as_of`
(`book_service.py:57-61`, and the docstring says so: *"valid_from auto_now_add > T"*). Resolution
filters `valid_from <= as_of` and `valid_to > as_of`. So the interval `[as_of, insert_time)` is
covered by **neither row**:

```
old:  [.......................)          valid_to   = T
new:                           [.......  valid_from = T + ε
                              ↑
                        no rule resolves here
```

An event landing in that window resolves to no rate and falls silently through to markup pricing
(`pricing_service.py:165-167`). Microseconds wide, real, and invisible — it presents as an
inexplicably cheap invoice line with no error anywhere. Dropping `auto_now_add` is the same change
forward-dating needs, so one fix closes both.

### 6.5 Cancellation, and one pending publish per book

A publish is **cancellable strictly before its `effective_from`**, and a book has **at most one
pending publish** in v1.

Cancelling deletes rows whose `valid_from` is still in the future and reopens their predecessors'
`valid_to`. That is safe **only** because nothing has resolved against the boundary yet — which is
exactly why the deadline is the effective instant and not a minute later. After it passes, the
publish is history and §4.6's rule applies: history is read, not rewritten.

The one-pending limit is a **v1 simplification, and §17 flags it as such.** With two overlapping
pending publishes you need a rule for which wins where, and that is a scheduling calendar rather than
a pricing model. A tenant wanting a series of rises schedules them in turn. Orb's prior art is a
caution in the other direction: `POST /subscriptions/{id}/price_intervals` accepts `start_date` as a
union including past dates, guarded by a runtime latch — `allow_invoice_credit_or_void`, defaulting
to **`true`** — where *"editing an interval into the past retroactively rewrites billing"* (**high**).
A safety-critical behaviour defended by a flag that defaults to the dangerous value is precisely the
shape §7 declines.

---

## 7. Backfill: the past is filled, never rewritten

### 7.1 Which version applies to a backfilled event

**The rule live when the event happened.** This is already the behaviour — `usage_service.py:410`
passes `as_of=inp.effective_at` — and #147 §10.1 restates it. It is not really a question: pricing at
arrival time would make an event's price depend on how backed-up the tenant's queue was.

The window is bounded by `Tenant.backfill_window_days` (`usage_service.py:69`), and a backfill into an
already-frozen invoice period is refused outright (`usage_service.py:78-84`). Both stand unchanged.
Prior art agrees on bounding: Metronome runs backdating and dedupe on a **34-day** window, beyond
which re-rating is a manual operations ticket (**high/medium**), and OpenMeter pins usage quantities
with a **`StoredAtLT`** cutoff *"so late-arriving events cannot retroactively alter an already-rated
line"* (**high**).

### 7.2 The collision this ticket inherited

#146 §3.1 lists four cases its remediation loop governs. **The second is "an event whose effective time
precedes the earliest Cost Rate"**, and the stated fix is:

> when the cause is fixed, the event is **replayed at its original timestamp**, resolving against the
> Cost Rate that was effective *then*

But if the event predates every rate, **no rate was effective then** — and #147 §10.4 refuses to
create one, because `effective_from` may not be in the past. The cause gets fixed, the replay finds
nothing, and the event remains `unresolved` permanently.

**#146's remediation loop cannot close for the first case it names.** Two documents merged one day
apart, and this ticket owns the collision because it owns effective dating.

### 7.3 The ruling: remediation is not a publish

**Publishes stay forward-only, always, with no past-dating door.** A historical gap is closed by a
distinct, immutable **remediation** action: *"price these unresolved postings using this rule."*

It is scoped to `unresolved` postings **by construction**, so it cannot touch a posted number — there
is no predicate to get right and no flag to set correctly.

```
publish       forward-only     changes what everyone will pay
remediation   past-facing      fills what was never priced, and only that
```

**Remediation may complete COGS and reporting. It must never automatically back-bill a customer and
never rewrite previously posted money.** That is #147 §7.3's rule for waived revenue — *"never
automatically back-billed"* — applied to the same shape from the other direction. Recovering money
from a remediated period remains a deliberate, auditable, customer-facing adjustment.

The remediated posting **records that it was remediated**: `provenance.remediation_id`, with the
action's own timestamp and actor (§4.7). Under §3 that is exactly what an authoritative receipt should
carry, and it is invisible under any design that backdates a rule instead.

### 7.4 Why not permit backdating with a check

The obvious alternative — allow a past `effective_from`, but first verify no event in that span priced
through the position being filled — was put and rejected.

**It is a check where remediation is a construction**, which is the reasoning that has won repeatedly
across this map. Its check is also subtly wrong: an event may have priced through a customer override
while the book default was absent, so *"any priced event in the span"* refuses cases that were safe,
and refining it means modelling which rung each event used. Most importantly it **reopens
`effective_from` to past dates** and then defends the door with a predicate every future caller must
pass through correctly.

The research names the failure mode at Metronome directly: `regenerate-an-invoice` *"recalculates the
invoice based on **up-to-date rates**"*, and the past window re-resolves the same way *"unless someone
has since added a backdated rate"* — accuracy resting *"on rate-schedule discipline, not on an
immutable per-invoice price snapshot"* (**high** for the quotes). A backdated rate is the single input
that breaks historical accuracy at the most rigorous effective-dated platform surveyed. We decline to
have one.

### 7.5 What this means for onboarding

A tenant who configures pricing in August and backfills July gets July events landing `unresolved`,
then runs one remediation over them. That is more work than magic and entirely visible — and it does
not require a backdating door that #155 would inevitably come to lean on.

### 7.6 What it costs, stated plainly

Remediation is a **new surface**: an action, a queue, an authorization rule for who may run it. It is
now the **third** unbuilt recovery mechanism across this map — #146 §11's unresolved-cost queue, #147
§14's customer adjustment, and this. §17 flags that they should be one thing rather than three tickets
each inventing their own.

---

## 8. The accept-vs-settle gap closes

### 8.1 What the gap actually is

The docstring at `pricing_service.py:210-221` calls it *"rate-card config drift between the two
instants"* — implying something rare that opens when configuration changes. It is worse and different.

`CardCache.resolve` hardcodes `timezone.now()` (`card_cache.py:87`), and `estimate` has no `as_of`
parameter at all — `ingest_accept.py:573` could not pass one if it wanted to, though `item.effective_at`
is available. So for **every backfilled event**, estimation resolves against today's rules while
settlement resolves against the event's own date. That is not a drift window; it is a **systematic
mismatch on an entire class of events**, and the estimate becomes a hold — the real-time money gate.

### 8.2 It is a spend-control problem, not a historical-accuracy one

Under §2 and §3, the estimate never reaches a receipt: the receipt records the settled number. So this
gap does not threaten explanation at all. It threatens **spend control**, which is #150's subject —
and #146 §14 already assigned #150 the adjacent question of what an accept-time hold does when no
estimate can be produced.

The document says this explicitly so that #150 inherits the residue with the right label on it.

### 8.3 What this ticket must close, because this ticket breaks it

The cache is invalidated by a version counter bumped inside `BookService.publish`'s `on_commit`. Under
§6 that fires **at publish time, when nothing has changed**, and **never at the effective moment, when
everything has**. The cache key `(tenant, customer, card_type, metric, currency, selectors)` has no
time component (`card_cache.py:80-81`). After a forward-dated boundary, correctness rests entirely on
`TTL_SECONDS = 30` happening to be short (`card_cache.py:23`).

That is accidental correctness, and §6 is what introduces it. **The cache becomes time-aware.**

### 8.4 The ruling

The gap closes **fully**: `estimate` resolves at the event's own `effective_at`, exactly as `price`
does. Once the cache must become time-aware anyway, threading `effective_at` through estimation is the
cheap half of the job, and leaving it undone means knowingly shipping a systematic mis-hold across a
ticket boundary. For the overwhelmingly common case where `effective_at ≈ now`, as-of resolution and
current resolution return the same row, so the cache stays as warm as it is today.

### 8.5 `Estimate.exact` is deleted

Its own docstring concedes it is *"a claim about the compute spine, not a guarantee over every possible
caller"* (`pricing_service.py:219-221`). This map has already deleted the zero that impersonated unset
(#147 §7.1) and the zero that impersonated unknown cost (#146 §4). A boolean named `exact` that is
asserted rather than established belongs in the same bin.

---

## 9. Fixed price: revenue is pinned, cost floats

### 9.1 No new versioning machinery

#139 pins the fixed price at task start; #147 §3.1 snapshots the mode and the price at creation. The
task resolves its price through the same effective-dated mechanism at start, then pins it. **The
snapshot is the version.** One timeline, two reads, no second mechanism — which is §5's whole spirit.

Prior art is the same shape: Stripe's subscription-item pin to an immutable price, Orb's *"the version
is fixed when you schedule the change rather than resolved again"*, OpenMeter's `Subscription.PlanRef`
plus a by-value `RateCard` copy (**high** throughout).

### 9.2 The ruling for a task that spans a price change

A job starts 31 July, delivers 3 August, and carries 400 events contributing COGS only.

**Revenue is pinned at task start. Cost resolves per event, at each event's own timestamp.**

The asymmetry is principled, not a compromise: **the price is pinned because it was promised; the cost
floats because it is observed.** That is #146's spine — *cost is observed, price is decided* — applied
to a job. What a supplier charged on 3 August is a fact about 3 August; pinning it to 31 July's rate
would not preserve anything, it would invent a cost that was never incurred and then report a margin
derived from it.

It also preserves one unbroken rule on the cost side: **every event resolves at its own timestamp,
always, with no exceptions** — which is precisely what #146's replay depends on.

### 9.3 The other 399 events are `not_applicable`, not zero

#139 projects the `Charge` onto one marked posting; the rest carry COGS and no revenue. Their receipt
reads `pricing: {method: none, status: not_applicable}` (§4.4).

Without that value, a dashboard sees 400 events, one with revenue, and reports a job running at
catastrophic negative margin on 399 of its lines. This is the same class of lie as #147 §7.1's
zero-impersonating-unset, and #152 must render it distinctly.

### 9.4 The pin carries its own receipt

Which rule produced the fixed price, resolved at which instant, from which publish. #139 made the
`Charge` immutable with no re-invoice path, so *"your book says £6 — why was this job £5"* is a
question that will be asked about a number that cannot be changed. Under §3 the only acceptable answer
is a receipt.

---

## 10. Retention: six years, published

### 10.1 The ruling

A receipt is retained for **at least six years**, as a **published promise** — a floor, raisable and
never lowerable, joining ADR-0004's one-year audit floor and ADR-003's deprecation notice on the
published-floors list.

### 10.2 Why a promise is owed at all

The receipt is now the **only** authoritative explanation of money (§3). If it is pruned, promise A
expires on a date nobody told the customer about.

ADR-0004 was able to defer this for the audit trail, writing *"no pruning job in v1 — volume is
governance-scale, not telemetry-scale."* **That argument does not transfer.** A receipt is written
once per usage event; it is the highest-volume record in the system and it is JSON. Here, "no pruning
job" is a permanent storage commitment — so it should be made deliberately rather than inherited from
a sentence written about a much smaller table.

### 10.3 Why six rather than one

ADR-0004 chose one year on the reasoning that *"who changed this rate card gets asked at renewal and
dispute time, a year later"*, explicitly rejecting 90/180-day log-style retention. A receipt answers a
different question with a longer tail: **a receipt must outlive the invoice it explains.** One year
covers a renewal conversation; it does not cover a tax audit, due diligence, or a contract dispute —
which are exactly the moments someone reaches for a three-year-old receipt. Six years aligns with UK
financial record-keeping (six years from the end of the accounting period).

### 10.4 The consequence for #165

This is the strongest argument yet for splitting the measurement record from the economic posting. The
receipt rides on the **posting**; measurements are bulky and have no dispute value, so they become
prunable on a much shorter clock while postings carry the six-year floor. #147 §13 already leaned
toward the split on state-divergence grounds; retention economics may be what makes it necessary
rather than merely tidy.

---

## 11. The clean break, and why it is not a precedent

### 11.1 The ruling

Every receipt written before this document exists was written under **no schema at all**. There is no
schema v0 reader. **Version 1 is the first version**; pre-existing receipts are not carried forward.

### 11.2 Why it is legitimate here

#137's constraint 1 licenses it explicitly — *"No live integrators yet. One clean break is available
across API, SDK, UI and database."* No receipt in the database has ever explained a real customer's
money.

And a v0 reader would be a parser for a format nobody specified. Its behaviour would have to be
reverse-engineered from whatever happens to be in the rows — which, per §4.2, is **not one shape**.
That is a compatibility shim for test data, maintained forever.

### 11.3 The sentence that matters more than the ruling

**This is a one-time exercise of #137 constraint 1, not a precedent.** The constraint expires the
moment the first integrator lands, and this document will outlive the condition that justified it.
From schema v1 onward, §4.6 binds properly and no clean break is available.

Cleaned up on the way past, since nothing reads them: the `book_version_from` / `book_version_to`
columns, `lineage_id`, and the SDK's `get_rate_card_history`.

---

## 12. Answers to the ticket's six questions

**1. Which of these survive, and which are redundant?**
**One survives; one is promoted; two are deleted.** Effective dating is the sole resolution axis. The
book-version range and `lineage_id` go — written by three paths, read by none, and already mutually
inconsistent (§1.2, §5.2, §5.3). `RateCard.version` is promoted from an integer counter to an
immutable **Pricing Book Publish** record that carries audit, scheduling and provenance and never
participates in resolution (§5.4). Four mechanisms become two.

**2. What is the guarantee, precisely?**
**Explanation, not recalculation** (§2). *"We can tell you why we charged you that"* is promised;
*"re-running a past period gives the same numbers"* is not offered, because #139, #146 §9.1 and #147
§10.4 have jointly left its output nowhere to land. Remediation — a **first** calculation happening
late — is explicitly not recalculation and is preserved (§2.3, §7.3).

**3. Is the receipt or the rule the source of truth?**
**The receipt, unambiguously** (§3). Not the rules, because #147 §10.1 moves them and §12 deletes the
ones that priced most of history; not both-and-reconcile, because that is promise B wearing a
different hat. The consequence the ticket anticipated is confirmed: versioned rules are needed only
for **first-time-late** pricing, not for explanation (§3.4) — which is what pays for §5's collapse.
The receipt therefore carries **values, not pointers**, and becomes typed, validated and
self-versioning (§4).

**4. Backfill — the version live when it happened, or when it arrived?**
**When it happened** (§7.1) — already the behaviour, and arrival-time pricing would make a price
depend on queue depth. The real question underneath was what happens when *nothing* was live then,
where #146's remediation loop collides with #147's backdating refusal (§7.2). **Publishes stay
forward-only; the gap is filled by a separate remediation action scoped by construction to
`unresolved` records**, which completes COGS and reporting but never auto-back-bills and never
rewrites posted money (§7.3).

**5. Estimate/settle drift — close it or keep it?**
**Close it fully** (§8). It is not a drift window but a systematic mismatch on every backfilled event,
and §6's forward-dating makes it worse by breaking the cache's invalidation model. The cache becomes
time-aware, `estimate` resolves at `effective_at`, and `Estimate.exact` is deleted. The residual
mis-hold is labelled **spend control** and handed to #150 (§8.2), not historical accuracy.

**6. Fixed-price versioning.**
**No new machinery** (§9). The price resolves through the same effective-dated mechanism at task start
and is then pinned — the snapshot is the version. For a task spanning a change, **revenue is pinned
and cost floats per event**, because the price was promised and the cost is observed. The 399
non-charging events are `not_applicable`, never zero (§9.3), and the pin carries its own receipt
(§9.4).

---

## 13. What each existing thing becomes

| Today | Becomes |
|---|---|
| `Rate.valid_from` / `valid_to` (`pricing/models.py:91-92`) | **Kept as the sole resolution axis**; `auto_now_add` **dropped** so both sides come from the publish's clock (§6.4) |
| `Rate.book_version_from` / `book_version_to` (`:88-89`) | **Deleted** — write-only, and written three inconsistent ways (§1.2, §5.2) |
| `Rate.lineage_id` (`:90`) | **Deleted** — never queried; #145's collapsed key is the natural identity (§5.3) |
| `RateCard.version` (`:146`) | **Promoted** to an immutable Pricing Book Publish record (§5.4) |
| `RateCard.__str__` `f"RateCard({self.key} v{self.version})"` (`:160-161`) | **Re-expressed** against the publish record |
| `BookService.publish` (`book_service.py:18-65`) | **Rewritten** — one clock for both sides (§6.4); the `as_of` param becomes the publish's `effective_from` and **may be in the future** |
| `BookService.publish` docstring *"future-dated scheduling is not supported"* (`:26-29`) | **Reversed** — it is now the only way a change lands (§6.1) |
| `add_rate` direct `Rate.objects.create` (`metering_endpoints.py:798-809`) | **Routed through a publish** (§6.3) |
| `delete_rate` direct `valid_to` stamp (`:892-896`) | **Routed through a publish** (§6.3) |
| `POST /pricing/rate-cards/{book_id}/publish` (`:828`) | **Kept and generalised** — gains `effective_from`; add/retire join reprice |
| — | **New:** `GET`/`DELETE` for pending publishes — list what is scheduled, cancel before it lands (§6.5) |
| `list_book_rates` `as_of` + `include_history` (`:760-774`) | **Kept** — point-in-time reads stay first-class; must now also surface *future* rows |
| `UsageEvent.pricing_provenance` `JSONField(default=dict)` (`usage/models.py:43`) | **Re-founded** as a validated, immutable, schema-versioned receipt (§4) |
| `pricing_provenance: dict` in `UsageEventDetailOut` (`schemas.py:251`) | **Typed** against the declared receipt schema |
| `metering_endpoints.py:259` echoing `e.pricing_provenance or {}` | **Kept in role**; the `or {}` must not mean "an empty receipt is fine" — a missing receipt is an integrity failure, not an empty dict |
| `PRICING_ENGINE_VERSION = "2.1.0"` (`pricing_service.py:8`) | **Kept as a breadcrumb**, joined by a separate top-level `receipt_schema_version` (§4.3) |
| `prov["metrics"][].rate_card_id` (`:138`, `:157`) | **Re-founded** — holds a `Rate` id despite its name; becomes `provenance.cost_rate_ids`, and the applied rate is recorded **by value** (§4.4, §4.7) |
| `prov["cost_source"] ∈ {caller, rate_card}` (`:110`, `:139`) | **Re-founded** as `costing.method ∈ {calculated, reported, none}`; `caller` already deleted by #146 §8 |
| `prov["price_source"] ∈ {caller, rate_card, markup}` (`:148`, `:164`, `:167`) | **Re-founded** as `pricing.method` + `pricing.status`; the applied percentage or price is recorded, which today it is not |
| `ResolvedMarkup.source` *"carried for provenance"* (`markup_service.py:26`) | **Finally written into the receipt** — today it is resolved and discarded, which is why a markup charge is inexplicable |
| `test_get_event_returns_full_receipt` (`api/v1/tests/test_metering_endpoints.py:261-269`) | **Rewritten** — it asserts `price_card_id`, a key production has never written (§4.2) |
| — | **New test (the ratchet):** production's own writer output validates against the declared schema, across every costing and pricing path (§4.5) |
| `CardCache.resolve` → `_resolve_card(..., timezone.now())` (`card_cache.py:87`) | **Time-aware** — resolves at the event's `effective_at` (§8.3, §8.4) |
| `CardCache.invalidate` on publish `on_commit` (`book_service.py:65`) | **Re-founded** — invalidating at publish time is wrong under forward-dating (§8.3) |
| `TTL_SECONDS = 30` (`card_cache.py:23`) | **No longer load-bearing for correctness** at an effective boundary |
| `PricingService.estimate` (`:198-245`) | **Gains `as_of`**, supplied from `item.effective_at` (§8.4) |
| `Estimate.exact` (`:26`) | **Deleted** (§8.5) |
| `ingest_accept.py:573` estimate call | **Passes `item.effective_at`** |
| `usage_service.py:410` `as_of=inp.effective_at` | **Unchanged and confirmed correct** — it is the pattern everything else moves toward |
| `validate_effective_at` backfill window + closed-period guard (`usage_service.py:69`, `:78-84`) | **Unchanged** (§7.1) |
| `ubb-sdk` `get_rate_card_history(lineage_id)` (`metering.py:320-322`) | **Deleted** — calls a path in neither the router nor `openapi/v1.json` (§5.3) |
| `RateOut.lineage_id` (`schemas.py:848`, `:875`) | **Deleted** with the column |
| Existing `pricing_provenance` rows | **Clean break** — no v0 reader; #137 constraint 1, one time only (§11) |
| — | **New:** Pricing Book Publish; the remediation action + its record; `receipt_schema_version`; `pricing.status = not_applicable`; the six-year published retention floor |

---

## 14. Constraints this imposes on other tickets

- **#149 (streaming: one event or many?)** — **gains a cost dimension it did not have.** Every event
  now carries a validated receipt retained six years (§4, §10). Splitting one call into many events
  multiplies receipts, not just rows. #147 §13 already relieved #149 of the per-event-uplift hazard;
  this adds a storage one that should be weighed in the same decision.
- **#150 (spend limits re-modelled)** — inherits two things explicitly. The accept-time hold with **no
  estimate** becomes *more common* once estimation resolves at `effective_at` (§8.2) — #146 §14 had
  already assigned this. And the mis-hold on backfilled events is labelled spend-control residue, not
  historical accuracy, so it lands in the right ticket with the right framing.
- **#151 (charging modes)** — a fixed-price task's non-charging events are `not_applicable`, never
  zero (§9.3), and the revenue-pinned / cost-floating asymmetry (§9.2) is part of what a charging mode
  means. Whether a subtask may differ from its parent's `pricing_mode` remains #151's, per #147 §14.
- **#152 (task dashboard and reporting)** — must render **four** pricing statuses distinctly, not
  three: #147 §7 gave known / waived / unknown, and §4.4 adds `not_applicable`. A dashboard showing
  399 `not_applicable` events as zero-revenue reports a catastrophic false margin on every fixed-price
  job (§9.3). It should also host the **pending publish** view — *"your prices change on 1 August"* —
  beside #146's unresolved queue and #147's waived-revenue report.
- **#153 (analytics re-alignment)** — every margin surface must handle `not_applicable` as a distinct
  input from zero and from null. This is a **third** state beyond the null-revenue handling #147 §13
  already required, and `queries.py:301`'s `or 0` coalescing — already a named defect there — is
  wrong in one more way.
- **#154 (vocabulary)** — names owed for: the **Pricing Book Publish**; the **remediation** action and
  its record; `receipt_schema_version` versus `pricing_engine_version`; the value `not_applicable`;
  and the receipt itself, which is called `pricing_provenance` in the model, *"the pricing receipt"* in
  the endpoint docstring, and *"the audit trail"* in `apps/metering/CONTEXT.md:164` — three names for
  one thing, now authoritative. Also owed: the `rate_card_id`-holds-a-`Rate`-id wart (§4.2), and the
  SDK's dead `update_rate_card`, which PUTs to a path absent from `openapi/v1.json`.
- **#155 (onboarding and cutover)** — backfilled events predating a tenant's first publish land
  `unresolved` and are closed by one remediation (§7.5). **There is no backdating door**, and #155
  must not ask for one. The clean break on old receipts (§11) is also #155's to sequence.
- **#156/#157 (Code Builder)** — can now state not only a call's current price (#147 §13) but a
  **scheduled** one: *"this call costs 2p, rising to 2.5p on 1 August"* is generatable from the pending
  publish (§6.1). Generated code should also surface the receipt endpoint, since it is the supported
  answer to *"why was I charged this"*.
- **#165 (splitting the measurement record from the economic posting)** — **gains its strongest
  argument.** The six-year receipt floor rides on the posting; measurements are bulky with no dispute
  value and can be pruned on a far shorter clock (§10.4). #147 §13 leaned toward the split on
  state-divergence grounds; retention economics make it load-bearing.
- **#146 and #147, retroactively** — #146 §3.1's remediation loop is **repaired**, not merely
  extended: as written it could not close for the first case it names (§7.2). #147 §10.1's
  forward-dated effectivity is **supplied**; it depended on a mechanism that did not exist (§1.3).

---

## 15. What this fixes that was already broken

Recorded separately because these are defects on `main`, not design choices, and each needs a test
when the work lands.

1. **Every supersession opens a window in which no rule resolves.** `old.valid_to = T`, new
   `valid_from = T + ε` under `auto_now_add`, against a half-open filter — events landing between price
   at markup instead of their rate, silently (§6.4).
2. **A markup charge cannot be explained.** `ResolvedMarkup.source` is resolved and discarded; the
   receipt records the word `"markup"` and no percentage, no rung, no id (§13). This is the *default*
   pricing path.
3. **The receipt has already drifted into two spellings**, and the test guarding it asserts the one
   production never writes (§4.2).
4. **The book-version columns are written three inconsistent ways** and would give wrong answers to
   anyone who started reading them (§1.2).
5. **The SDK ships a method calling an endpoint that does not exist**, green in CI because its test
   mocks the transport (§5.3).
6. **Estimation is systematically wrong for backfilled events** — not a drift window, a whole class
   (§8.1).

---

## 16. Published promises this document adds

Both join the compatibility surface under ADR-003 §3's raisable-never-lowerable rule, alongside
ADR-0004's one-year audit floor:

- **Receipt retention: at least six years** (§10.1).
- **Receipt schema versioning: a receipt is readable under the schema it was written with** (§4.6) —
  with the one-time pre-v1 clean break called out explicitly as an exception that has expired (§11.3).

---

## 17. Residue, flagged not buried

- **Three unbuilt recovery surfaces now exist and should be one.** #146 §11's unresolved-cost queue,
  #147 §14's customer adjustment, and §7.3's remediation. Three tickets are each about to invent their
  own queue, actor model and authorization rule. #147 already called its own *"the largest unbuilt
  thing this document depends on"*; that is now true of a family, not a single mechanism. Whoever owns
  the remediation queue should own all three.
- **One pending publish per book is a v1 simplification, not a principle** (§6.5). The moment a tenant
  wants two scheduled changes in flight, the rule for which wins where has to be written, and that is
  a scheduling calendar.
- **The maximum forward-scheduling horizon is unspecified.** Nothing stops a publish dated 2099.
  Probably a bound; certainly a decision nobody has made.
- **Remediation's scope is stated coarsely.** "Unresolved postings only" is correct and safe. Whether
  a remediation may target a *subset* — one customer, one event type, one date range — rather than
  everything it matches is unstated, and it decides whether the console offers a filter or a button.
- **Nothing says who may run a remediation.** It writes money-adjacent numbers into closed periods'
  reporting. `role_floor(ADMIN)` is the obvious guess and a guess is not a decision.
- **The interaction between remediation and a closed billing period is not fully worked.** §7.1 keeps
  the closed-period refusal for *new* events; §7.3 lets remediation complete COGS for events already
  recorded in such a period. That is deliberate — the event was already accepted — but it means a
  closed period's *cost and margin* figures can still move after close, while its *revenue* cannot.
  #146 §9.4 said unresolved events bill next period; whether the reporting figures for the closed
  period restate or stay frozen is not decided here and should be, by #152 or #153.
- **`GET /metering/usage/{event_id}` is the only receipt surface, and it is per-event.** Under a
  six-year promise, someone will want to export a period's receipts. No bulk read exists and none is
  designed here.
- **The receipt's size is unmeasured.** §4 makes it strictly larger — values as well as pointers, a
  status per section — and §10 keeps it for six years. Nobody has multiplied those together against a
  realistic event volume. That number should exist before implementation starts, not after.
- **Whether an override may change a rule's *method* remains open** (#147 §14, unchanged here) — but it
  now also touches the receipt, since `pricing.method` is recorded per event and an override that
  switches method makes two events of the same type read differently.
