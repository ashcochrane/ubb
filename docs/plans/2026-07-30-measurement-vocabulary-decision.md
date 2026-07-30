# Measurements and Grouping Fields — what may move money, and what may only slice a chart

**Resolves:** [#145](https://github.com/ashcochrane/ubb/issues/145) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-30
**Decided against:** `main` @ `b828304`
**Evidence:** `docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch
`research/pricing-model-prior-art` @ `2f0ce4c`) — Q2 (quantities are free-form everywhere; one metric
aggregates one quantity), Q3 (the grouping/pricing vocabulary split, and Metronome's role model).
**Builds on:** `docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — Event Type owns
costability, not cost; Cost Rates are effective-dated per component; unknown event types are
quarantined and replayed at their original timestamp.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — money is exact whole micros; the minor unit
is reached once on the way out; this ticket owns the noun `unit_quantity` becomes and the wording of
the sub-micro warning.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**This document narrows two decisions that are already merged.** §5 and §7 state exactly what of
#138 and #142 no longer holds. Neither is a discovered defect in those documents — both are the
consequence of a rule decided here that neither could have anticipated. They must be read together,
and #154 should carry the reconciliation into the ADR.

**No ADR yet, deliberately.** Same reasoning as #138 through #142: #154 is the single naming pass,
and this document renames the central noun of ADR-0005. The ADR is owed *after* #154 and should cite
all six decision documents.

---

## The decision in one paragraph

**Only declared measurements may move money. Everything else on an event may only slice a chart.**
An Event Type declares the measurable quantities it produces — each with a value type, a unit and a
provider mapping — and those declarations are the *only* inputs to supplier cost and customer price.
Grouping fields, metadata, region, processing mode and provider account lose every monetary role
they had: no rate selection, no rate variation, no wildcards, no specificity ranking. The ticket
asked whether one vocabulary should serve both grouping and pricing or split into two; the answer is
**neither** — the second job is deleted, so one vocabulary remains and it now has exactly one duty.
Measurements are **Event-Type-local and independently authoritative**, because a matching name has
never been evidence of a matching meaning and a correct mapping matters more than a consistent
spelling; an optional tenant-level **Measurement Concept** restores cross-provider aggregation for
tenants who want it, without making costing depend on naming discipline. The cost key collapses to
`tenant + event_type + measurement + event timestamp`. v1 is **USD-only**, enforced at both the API
and database boundary, and every row that owns an amount carries its own denomination rather than
inheriting one. The three overlapping descriptive bags become two: `tags` folds into `metadata`,
which is filterable and readable but **never groupable**, and the declared vocabulary — renamed
**Grouping Field** — grows from six slots to ten to absorb the ad-hoc grouping this removes.

---

## 1. The ticket's premise, corrected

The ticket frames the problem as a naming and unification failure:

> ADR-0005 deliberately made dimensions do double duty: the same declared vocabulary serves analytics
> grouping *and* rate selection. … the working model suspects that unification is what makes
> "dimensions" confusing.

That diagnosis is wrong in an instructive way, and the correction is the spine of this document.

**Unification was not the defect.** The genuine sharp edges in ADR-0005 all came from the *matching
engine* built on top of the unified vocabulary, not from the vocabulary itself:

- `""` meant "not set" on a `UsageEvent` and "matches anything" on a `Rate`
  (`apps/metering/usage/models.py:24-28`, `apps/metering/pricing/models.py:64-69`) — one token, two
  opposed meanings, on two sides of the same comparison.
- Two independent ranking layers could disagree, producing ADR-0005 §8's documented shadowing: a
  narrowly-pinned rate in the `""` book is silently beaten by a broadly-pinned rate in a provider
  book, because the book walk short-circuits before specificity is ever consulted.

**#138 already deleted all of that** — the wildcard, the specificity ranking, and the three-tier book
walk. So by the time this ticket was asked, most of the confusion it names had already been removed
by a different decision. What remained was one word doing three jobs in prose.

The consequence is that the ticket's binary — *one vocabulary or two?* — was the wrong question. Both
of its answers preserve the thing worth removing: **that a field whose declared purpose is grouping
can silently determine how much money changes hands.** Splitting the registry makes that harder to do
by accident; it does not make it impossible, and it costs a rename Lago has already shown us the
price of (two renames, a ~6-month deprecation window, vestigial tables still on `main`, and an
input/output asymmetry where you configure `pricing_group_keys` and read back `grouped_by` —
`docs/research/2026-07-29-pricing-model-prior-art.md` Q3).

**The decision is to remove the second job instead of duplicating the vocabulary that carries it.**

---

## 2. Declared measurements

### 2.1 The ruling

An Event Type declares the measurable quantities it can produce. Each declaration carries:

| Field | Purpose |
|---|---|
| `code` | the name the caller sends (`input_tokens`) |
| `display_name` | human label for console and invoice |
| `value_type` | `integer` \| `decimal` |
| `unit` | `token`, `search`, `call`, `second`, `byte` |
| `required_for_costing` | whether absence blocks a complete cost |
| `source_path` | the provider response field this maps from |
| `concept` | optional cross-provider Measurement Concept (§4) |

```
EventType  gemini-api-call-flash-4.0
  Measurement  input_tokens       integer  token   ← usageMetadata.promptTokenCount
  Measurement  output_tokens      integer  token   ← usageMetadata.candidatesTokenCount
  Measurement  grounded_searches  integer  search  ← grounding usage
  Measurement  completed_calls    integer  call    ← (constant 1)
```

**Only declared measurements may participate in monetary calculation.** A Cost Rate references a
declared measurement; nothing else is a monetary input.

### 2.2 Why declare, when no comparable platform does

The prior art is unanimously against pre-declaration. All six platforms surveyed in #143 leave the
event payload free-form, and Orb says so outright: *"The schema of this dictionary need not be
pre-declared, and properties can be added at any time."*

Two reasons override it.

**First, the Code Builder is a hard blocker.** Every one of those six is a billing engine whose
consumer is an engineer reading documentation. Map #137's driver is a builder that must *generate*
correct, self-explaining integration code, and nothing can generate a typed call against a
schemaless bag. That is a requirement none of the six shared, so their choice is not evidence
against ours.

**Second — and this one stands alone — undeclared money keys are a live correctness defect, not an
ergonomics gap.** Today `usage_metrics` is a bare `JSONField` (`apps/metering/usage/models.py:44`)
whose only validation anywhere is that values are non-negative (`api/v1/schemas.py:74-82`). A
misspelled quantity is **silently free**:

- On the price side, a quantity with no matching rate hits `continue` and contributes nothing, with
  no signal to anyone (`apps/metering/pricing/services/pricing_service.py:151-158`).
- On the cost side it is appended to `uncosted_metrics` and skipped, raising only if the tenant
  enabled `require_cost_card_coverage` (`pricing_service.py:130-140`) — **off by default**.
- The mirror-image typo is equally silent: `Rate.metric_name` is free text
  (`apps/metering/pricing/models.py:80`), so a rate whose name never matches simply never fires.

The asymmetry that made this ticket necessary is therefore sharper than "two things are confusable":
**the values that determine how much money changes hands were undeclared, and the values that only
slice a chart were strictly governed** — declared, cardinality-capped, slot-frozen, with reserved and
forbidden key lists (`apps/platform/dimensions/models.py:16-21`).

### 2.3 Metadata stays open

Declaration is required only of *economic* measurements. Everything else travels in an open
`metadata` bag that needs no registration and may never move money:

```
measurements:  input_tokens 100000   output_tokens 5000
metadata:      provider_request_id abc123   latency_ms 840   finish_reason stop
```

Metadata is available for diagnostics, filtering and future product work. It cannot affect a charge
unless a tenant deliberately promotes it into a declared measurement.

### 2.4 Unknown measurements: quarantine, never zero

An unknown measurement key follows #138's precedent for unknown event types, for the same reason —
the supplier may already have charged us, so discarding the value hides real COGS.

| Arrival | Treatment |
|---|---|
| Unknown **metadata** key | accept and preserve normally |
| Unknown **measurement** key | accept and preserve the event; mark the measurement unresolved; **do not** auto-register; **do not** silently ignore; the event is not *fully costed* until resolved |

Remediation is explicit and tenant-driven: **map** `input_toknes` → `input_tokens`, **register** a new
measurement, or **dismiss** as non-economic metadata. On resolution the event is **replayed from its
original timestamp**, never the repair date, so the historically correct Cost Rate applies.

This preserves #138's rule at the level below it: auto-registration is refused because it lets a typo
become permanent billing vocabulary, and a period containing unresolved economic values cannot close
silently.

---

## 3. Measurements are Event-Type-local and independently authoritative

### 3.1 The ruling

`input_tokens` on `gemini-api-call-flash-4.0` and `input_tokens` on `openai-chat-gpt5` are **two
independent measurement records that happen to share a spelling**. Each is separately declared,
separately mapped, and separately costed. Neither needs the other to exist, agree, or be spelled
alike.

A Cost Rate references a **measurement record**, not a free-text name.

### 3.2 Why locality beats a mandatory shared vocabulary

The obvious alternative — one tenant-level vocabulary that Event Types draw from, with per-Event-Type
role assignment (Metronome's `group_keys` + `pricing_group_key` shape, which #143 identifies as the
strongest prior art) — was considered and rejected. The argument that defeats it:

> A tenant-level vocabulary enforces that two measurements share a **name**. It cannot enforce that
> they share a **meaning**.

A developer can declare `input_tokens (integer, token)` correctly and map it to the provider's
*output* token field. The vocabulary is satisfied, the declaration looks consistent, every
cross-provider chart aggregates cleanly — and the COGS is wrong. Conversely a developer can name a
measurement `gemini_prompt_usage`, map it correctly, and be exactly right while looking untidy.

So name-equality was never the correctness boundary. **The boundary is whether a declared measurement
has a validated mapping to the specific provider value it is supposed to represent.** Costing must not
depend on a developer naming things consistently across Event Types, because consistent naming is
neither necessary nor sufficient for a correct cost.

The two questions are genuinely separate, and only one of them is essential:

- *Can this Gemini event be costed correctly?* — essential; answered entirely within the Event Type.
- *Can Gemini and OpenAI input tokens be added together?* — useful; optional; answered in §4.

### 3.3 The asymmetry with Grouping Fields is deliberate

Measurements are Event-Type-local. Grouping Fields are tenant-level. That will read as an
inconsistency, so the reason is recorded here: **a Grouping Field can be task-scoped** — set once on a
Task and inherited by every event beneath it, across many Event Types (`DimensionDef.scope`, ADR-0005
D6). A vocabulary that is inherited down a task tree spanning several Event Types cannot be
Event-Type-local by construction. A measurement is produced by one operation and priced by one Cost
Rate, so it can be. Each is scoped to the job it does.

---

## 4. Measurement Concept — optional, for aggregation only

A tenant who *wants* cross-provider aggregation declares it explicitly. A **Measurement Concept** is a
tenant-level label that measurement records may be assigned to:

```
Concept  input_tokens
   ├── gemini-api-call-flash-4.0 / input_tokens
   └── openai-chat-gpt5 / model_input
```

Two rules, both load-bearing:

- **A matching name never automatically proves equivalence.** Two measurements called `input_tokens`
  are aggregated only if the tenant assigns them the same concept.
- **A differing name never prevents aggregation.** `model_input` and `input_tokens` aggregate freely
  once assigned to one concept.

The concept is **analytics and reporting only** in v1. It is not a costing input, and it is not a
prerequisite for recording, costing or charging an event. It groups *measurement records*, not
events — which is why it is not a role on the Grouping Field vocabulary; folding it in would conflate
two different kinds of thing.

---

## 5. Nothing but a measurement may move money

### 5.1 The ruling

Contextual attributes, grouping fields, metadata and event properties **may never select or vary a
Cost Rate or a price**. The costing key is:

```
tenant + event_type + measurement + event timestamp
    → the effective Cost Rate
    → quantity × rate
    → COGS
```

There is no lookup on `region`, `processing_mode`, `environment`, `provider_account`, `customer_tier`,
`workflow`, or any other event field. One rung, no matching engine, no defaults tier, no ranking.

### 5.2 What this narrows in merged #138

#138 kept a reduced form of dimensional cost selection: the Event Type declared *which properties may
vary its supplier cost*, and the cost ladder walked exact-variant → explicit-default → blocked. That
is now removed. Stated precisely, so the reconciliation is not left to inference:

| #138 as merged | After this decision |
|---|---|
| Cost key = `event type + measurement + provider account + declared cost dimensions + timestamp` | `tenant + event type + measurement + timestamp` |
| Cost ladder: exact declared variant → explicitly marked default → blocked | one rung: an effective rate exists → cost; otherwise uncosted |
| EventType owns "its declared **cost dimensions** — which properties may vary its supplier cost" | **deleted** |
| CostRate carries "one cost-dimension variant" or an explicit `default` marker | neither exists |
| `task_type`, `subtask_type`, `dim1..dim6` survive as exact-match cost-dimension variant values | survive as **analytics axes only** |
| **"Variants are not identities … `…-flash-4.0-batch-eu` as a separate Event Type is wrong"** | **reversed for operational variants** (§6) |
| `ProviderAccount` — "a distinct purchasing arrangement that pays different rates" | **removed from the model** (§6.2) |

ADR-0005's invariant 7 — *"Every `Rate.SELECTORS` name exists as a `UsageEvent` column — one
vocabulary, both sides"* — loses its subject entirely: the ten selector columns on `Rate` are deleted,
so there is no second side to agree with. `test_dimension_invariants.py` needs a corresponding rewrite.

### 5.3 Why remove rather than restrict

The alternative was to keep a small, disciplined set of cost-varying properties. It was rejected
because it preserves the property this decision exists to eliminate: **that a tenant configuring a
field for reporting reasons can change what their supplier costs resolve to.** A restricted matching
engine is still a matching engine — it still needs ranking rules, still needs a default rung, still
needs a story for two rates that both match, and still leaves "why did this event cost that?"
answerable only by simulating the engine. Either the separation is real or it is not.

### 5.4 A justification collapses with it

ADR-0005 justified the cardinality cap as a cache-safety measure, and `CardCache`'s docstring states
it directly:

> *"Dimensions are declared and cardinality-capped (design D4), so the selector tuple is a bounded,
> safe cache key"* — `apps/metering/pricing/services/card_cache.py`

With no rate selection, the resolved-rate cache key collapses to
`(tenant, customer, event_type, measurement)` and **the cap's stated reason ceases to exist.** The cap
survives, but on a different and weaker footing — group-by legibility, per §8.3. This must be written
down: a future reader who checks the cap against ADR-0005's reasoning will find the reasoning false
and may conclude the cap is vestigial.

---

## 6. Cost variants: which ones may become Event Types

Removing attribute-based rate selection raises an obvious question — what happens when supplier cost
genuinely *does* differ for what looks like the same operation? The answer differs by *why* it
differs.

### 6.1 Operational variants — a separate Event Type is correct

Standard versus batch execution is a **different operation**, and the integration knows which one it
performed *before* it emits the event:

```
EventType  gemini-api-call-flash-4.0-standard
EventType  gemini-api-call-flash-4.0-batch
```

Each is a complete, independent contract with its own measurements and Cost Rates. Duplication is
reduced by a **creation-time affordance** — *register this Event Type by copying that one's
measurement contract* — following #138's precedent of solving grouping and revision problems with
usability affordances rather than new entities. The resulting records are fully independent: **no
inheritance, no template hierarchy, no parent pointer.**

### 6.2 Commercial variants — never an Event Type

A negotiated agreement does **not** change what operation occurred or what measurements it produced.
These are forbidden:

```
gemini-api-call-flash-4.0-list-rate        ✗
gemini-api-call-flash-4.0-negotiated-rate  ✗
```

A tenant on a negotiated deal enters **the Cost Rates they actually pay**. That is the whole
mechanism, and it is sufficient for every tenant with one commercial arrangement per operation.

**A tenant using several differently-priced provider accounts *concurrently* for the same operation is
explicitly unsupported in v1.** That is a real limitation, stated rather than simulated: encoding it
in Event Type identity would make the identity lie about what happened, which is precisely the
failure #138's "variants are not identities" rule was protecting against.

**`ProviderAccount` is therefore removed from the target model.** Its sole stated purpose in #138 was
*"a distinct purchasing arrangement … that pays different rates"* — a cost selector. Keeping it as an
inert entity that can no longer do its job is the kind of confusing abstraction map #137's standing
preferences direct us away from. Future support arrives as an explicit cost-profile mechanism, not by
reopening arbitrary attribute-based pricing.

### 6.3 The cost, recorded

Operational variants fragment reporting: *"all Gemini Flash 4.0 spend"* stops being one filter and
becomes several codes. Reassembly is available through #138's **Event Category** for commercial
policy and through §4's **Measurement Concept** per quantity — but neither is automatic, and a tenant
who declares neither will find their reporting split by a decision they made for costing reasons.
**#153 inherits this explicitly.** It must be repaired by declared grouping, never by reintroducing
rate selection from event attributes.

---

## 7. Currency: USD-only, explicit, database-constrained

### 7.1 The ruling

**v1 is USD-only.** Every amount participating in supplier costing, customer charging, wallets,
refunds, invoicing and margin reporting is USD, enforced at **both** boundaries:

```sql
currency NOT NULL DEFAULT 'USD'
CHECK (currency = 'USD')
```

Non-USD monetary input is **rejected, never converted**. A tenant may convert a supplier rate
externally and enter the USD result — that is a documented tenant-maintained approximation, not
native-currency reconciliation.

This deliberately avoids building half an FX engine. Credible FX requires effective-dated rate
sources, conversion timing rules, rounding, historical replay, refund and reconciliation semantics,
and treatment of FX gain and loss. Until those are explicit and auditable, a non-USD cost must not
reach a USD wallet.

### 7.2 Currency is stored, not inferred

Every persisted row that **independently owns a monetary amount stores its own currency.** Rows that
merely reference or inherit an amount do not duplicate it.

The benefit is that a monetary record is self-describing wherever it is read — database, API, export,
support tooling, audit — with no need to trace a denomination back through a tenant, a policy book or
a wallet.

### 7.3 What this reverses in merged #142

#142 deleted eight currency columns on the grounds that each was a copy of a frozen tenant choice
that *"can never legitimately differ."* Applying §7.2's rule reverses seven of them:

| # | Column | #142 | Now | Owns |
|---|---|---|---|---|
| 1 | `UsageEvent.currency` | deleted | **restored** | `provider_cost_micros`, `billed_cost_micros` (`usage/models.py:41-42`) |
| 2 | `Rate.currency` → `CostRate` | deleted | **restored** | the monetary rate (`pricing/models.py:82-84`) |
| 3 | `RateCard.currency` → policy book | deleted | **restored** | the single-currency invariant for its lines |
| 4 | `RateCardAssignment.currency` | deleted | **stays deleted** | nothing — pure reference |
| 5 | `Wallet.currency` | deleted | **restored** | `balance_micros` (`wallets/models.py:22-26`) |
| 6 | `CreditGrant.currency` | deleted | **restored** | `granted_micros` (`wallets/models.py:143`) |
| 7 | `CustomerUsageInvoice.currency` | deleted | **restored** | `total_billed_micros` (`invoicing/models.py:61`) |
| 8 | `CustomerRevenueProfile.currency` | deleted | **restored** | `recurring_amount_micros` (`subscriptions/economics/models.py:52`) |
| 9–10 | Stripe mirrors | survive | **survive unchanged** | what Stripe reported |

Currency lives at the **book** level for policy books and is inherited by their lines — not duplicated
onto both. The Stripe mirrors keep #142 §4's quarantine rule intact: they record an observed external
fact and can legitimately differ.

**That a value is derived does not exempt it.** `Wallet.balance_micros` is a cache over the
`CreditGrant` ledger, and it still stores its currency: the point is inspection-time
self-description, and the database CHECK makes disagreement impossible anyway.

### 7.4 What this simplifies in #142

The reversal is not all cost. #142 imposed a **hard prerequisite on #155** — *"currency selection must
exist in onboarding before the `currency_not_set` gate ships."* Under USD-only there is no currency
selection to build, and that prerequisite is **removed**. `Tenant.default_currency` survives as the
tenant's reporting and presentation default, constrained to USD.

### 7.5 ADR-0002 compatibility

ADR-0002 bars database constraints that encode **mutable spend policy** — its worked example being a
wallet floor, which would "refuse to record work that already happened." `CHECK (currency = 'USD')`
passes that test: non-USD input is rejected at the API door, so **no real posting is ever blocked by
the constraint**, and "every amount is USD" is an invariant no business situation can make false while
v1's rule holds. When multi-currency ships, the constraint is dropped deliberately as part of that
feature.

**Future multi-currency must not be implemented by removing the CHECK.** It requires reviewing
monetary ownership, conversion timing, rounding, historical FX snapshots, native-plus-reporting
amounts, and records such as `UsageEvent` that presently hold supplier cost and customer revenue
under a single denomination (§10).

---

## 8. Three descriptive bags become two

### 8.1 The state this decision inherits

After §5, a usage event carries three places for descriptive strings and **none of them can touch
money**:

| | declared | bounded | groupable | inherited from the task tree |
|---|---|---|---|---|
| `dim1..dim6` (`usage/models.py:35-40`) | yes | yes, cardinality cap | yes — indexed columns | **yes**, task/subtask scope |
| `tags` (`usage/models.py:45`) | no | no | yes, in three live places | no |
| `metadata` (`usage/models.py:19`) | no | no | no — echoed on read only (`metering_endpoints.py:261`) | no |

Once pricing is out of all three, the distinction between the first two collapses to indexing
strategy.

### 8.2 The ruling: `tags` folds into `metadata`

**One declared vocabulary that may be grouped, and one open bag that may not.** `tags` is retired as a
concept and its contents belong to `metadata`, which is **filterable and readable but never
groupable.**

The three live grouping surfaces migrate to declared Grouping Fields:

- `?tag_key=` on `/analytics/usage` (`apps/metering/queries.py:328,345-346`)
- `tag_key` on `/margin/by-dimension` (`api/v1/metering_endpoints.py:594-595`)
- `usage_line_item_group_by="tag:<key>"` driving postpaid invoice line labels
  (`apps/metering/queries.py:430,444`)

ADR-0005's Consequences already concede the gap this closes: *"'never grouped' was never quite true;
'never priced' is the invariant that actually holds."* This makes the stronger claim true rather than
continuing to document the exception.

**Filtering survives; grouping does not.** A filter is bounded by the result set; a group-by is bounded
by *cardinality*, which is unbounded on an open bag. The sharpest live case is the invoice-label
path — an unbounded free-text key driving invoice line labels is how a 5,000-line invoice happens, and
it is the only one of the three a paying customer sees.

**The name goes too.** Keeping "tags" as an alias for a bag that can no longer be grouped would
preserve exactly the wrong expectation. Worth noting that this field has already been renamed once:
migration `0017_rename_group_keys_to_tags` renamed it *from* `group_keys`, and
`0022_swap_tags_gin_to_jsonb_ops` rebuilt its GIN index — UBB has already run Lago's rename dance on
this exact column.

### 8.3 Grouping Fields keep their registry, on restated grounds

The declared vocabulary survives, justified by what remains true after §5:

- **Task-tree inheritance is structural and an open bag cannot do it.** A Grouping Field can be set
  once on a Task and inherited by every event beneath it. There is no metadata equivalent, and
  building one would be re-creating Grouping Fields under another name.
- **The Code Builder needs an enumerable vocabulary** — the same argument that carried §2.
- **Only a declared field can have a column** (§9), and only a column makes group-by cheap.
- **The cardinality cap survives with a new justification** — group-by legibility, not cache
  safety (§5.4). A chart with 50,000 series is not a chart.

---

## 9. Ten slots, analytics-only, with an index cleanup

### 9.1 Why columns at all, now that the original reasons are gone

ADR-0005 moved this vocabulary *from* JSONB *to* physical columns for two reasons — cache keying and a
single matching semantic. §5 deleted both. The columns survive on a third reason ADR-0005 did not
lean on:

**A GIN index does not accelerate `GROUP BY` on a JSONB key.** GIN serves containment lookups.
Grouping by `metadata->>'region'` is a sequential scan plus per-row expression evaluation unless a
separate expression index exists per key. Physical columns are the only shape that makes analytics
group-by cheap — which is now the entire job, and which retroactively explains why only declared
fields may be grouped: **declaration is what earns a column.**

### 9.2 Six becomes ten

**Ten slots, justified as v1 product headroom now that ad-hoc grouping has been removed.** §8.2 closes
the `tag_key` escape hatch, so demand that previously landed on free-form tags now lands on declared
fields. Six was sized when the hatch was open.

This is *not* justified by migration cost. Adding a nullable column in modern Postgres is a
catalog-only operation, so ADR-0005's *"adding columns later is the expensive move"* overstates it.
The reason is product headroom, and that reason will still be true when someone reads it later.

**There is no empirical evidence for either number.** There are no live integrators, so ten is a
judgment about headroom after a capability was removed, not a measured requirement.

### 9.3 The index cleanup

Today all six slots are individually indexed (`db_index=True` on each, `usage/models.py:35-40`) *plus*
a composite `idx_usage_dim_attribution` on `(tenant, dim1, dim2, -effective_at)` — seven index writes
per event on the hottest insert path in the system.

**The six single-column indexes should go.** A cardinality-capped column (default 100 distinct values,
`dimensions/models.py:43`) has roughly 1% selectivity, at which Postgres will prefer a sequential scan
or the composite anyway. Widening to ten slots *without* this cleanup would tax every insert for
capacity nobody is yet using. Ten columns behind two or three composites matching real query shapes
is strictly better than six columns behind seven indexes.

---

## 10. The names

#154 locks these across every surface; this ticket coins them.

| Concept | Today | **Decided** | Rule |
|---|---|---|---|
| A measurable quantity | `usage_metrics` keys, `Rate.metric_name` | **Measurement** (`measurements`) | `metric` is unavailable — it names the metered *entity* industry-wide (`billable_metric` in Lago and Metronome). "Measurement" leaves "quantity" free for the number: a Measurement is `input_tokens`, its quantity is `100000` |
| A declared grouping axis | `Dimension` / `DimensionDef` | **Grouping Field** | "Dimension" is a minority industry term, and Orb uses it specifically for *price selection* — the one job ours will never do. A developer arriving from Orb would guess exactly wrong |
| Cross-provider aggregation label | — | **Measurement Concept** (`concept`) | Says what it is; "semantic" carries no information |
| The rate amount | `rate_per_unit_micros` | **`amount_micros`** | It is an amount |
| The rate basis | `unit_quantity` (`pricing/models.py:83`) | **`per_quantity`** | Reads as written: `amount_micros: 300000, per_quantity: 1000000, unit: token` = $0.30 per 1,000,000 tokens |
| The open bag | `metadata` + `tags` | **`metadata`** | One bag; "tags" retired with the capability it implied |

**The sub-micro warning** (#142 §6.3's handoff, raised when `amount_micros × 2 < per_quantity`):

> **`rate_below_minimum_precision`** — *"$0.0000003 per 1 token charges nothing until an event reports
> at least 2 tokens. Events reporting fewer will record zero."*

The load-bearing part is naming **the quantity at which the line first becomes chargeable**, which is
what makes the warning actionable rather than merely alarming. It stays a warning, not an error: a
genuinely cheap per-call price is legitimate when calls arrive in batches.

**Deliberately not coined here:** a replacement for "Cost Card / Price Card". #138 already deleted
`card_type` and routed book naming to #154; a third opinion would not help.

---

## 11. Answers to the ticket's five questions

**1. Do quantities get a declared registry, and do they belong to an Event Type or stand alone?**
Yes — declared, and owned by the Event Type. Economic measurements only; non-economic fields stay in
an open `metadata` bag. Declarations are **Event-Type-local and independently authoritative for
costing** (§3), with an optional tenant-level **Measurement Concept** for aggregation (§4).

**2. Does the unified grouping/selection vocabulary survive, or split into two concepts?**
Neither. **The selection role is deleted.** One vocabulary survives with exactly one job — analytics
grouping. The question assumed the second job had to live somewhere; it does not (§5).

**3. Final names for each.**
Measurement · Grouping Field · Measurement Concept · `amount_micros` + `per_quantity` · `metadata`
(§10).

**4. What happens to `tags`?**
Folded into `metadata`, and the word retired. The open bag is filterable and readable but **never
groupable**; the three live tag-grouping surfaces migrate to declared Grouping Fields (§8.2).

**5. Six slots — still the right bound?**
No. **Ten**, as v1 product headroom replacing the ad-hoc grouping removed in §8.2, with the six
per-slot single-column indexes dropped in favour of composites (§9).

---

## 12. What each existing thing becomes

| Today | Becomes |
|---|---|
| `UsageEvent.usage_metrics` (`usage/models.py:44`) | **`measurements`** — keys validated against the Event Type's declarations |
| `UsageEvent.tags` (`usage/models.py:45`) | **deleted**; contents belong to `metadata` |
| `UsageEvent.metadata` (`usage/models.py:19`) | **kept and widened** — the one open bag; filterable, never groupable |
| `UsageEvent.dim1..dim6` (`usage/models.py:35-40`) | **`dim1..dim10`**, analytics-only; per-column indexes dropped |
| `UsageEvent.currency` | **restored** (§7.3) |
| `Rate.metric_name` (`pricing/models.py:80`) | **a reference to a declared Measurement record**, not a name |
| `Rate.rate_per_unit_micros` / `unit_quantity` (`:82-83`) | **`amount_micros`** / **`per_quantity`** |
| `Rate`'s ten selector columns (`:70-79`, `SELECTORS` `:109-110`) | **deleted** — no selectors on a rate |
| `Rate.specificity` (`:116-121`) | **deleted** — nothing ranks |
| `DimensionDef` (`dimensions/models.py:24`) | **`GroupingFieldDef`** — same registry, ten slots, analytics-only, cap restated |
| `DimensionValue` (`:61`) | kept — the distinct-value ledger behind the cap |
| `RESERVED_KEYS` (`:16`) | narrowed — `provider` and `event_type` are entity references after #138 |
| `FORBIDDEN_KEYS` (`:20`) | unchanged — correlation identifiers still may never be grouping axes |
| `CardCache` selector-tuple key (`card_cache.py`) | key collapses to `(tenant, customer, event_type, measurement)` |
| `ProviderAccount` (#138) | **removed from the model**; deferred to an explicit cost-profile feature |
| ADR-0005 invariant 7 (`Rate.SELECTORS` ↔ `UsageEvent` columns) | **loses its subject**; `test_dimension_invariants.py` rewritten |
| ADR-0005 §8 (book tier dominates specificity) | already dissolved by #138; nothing left to shadow |

---

## 13. Constraints this imposes on other tickets

- **#146 (provider-supplied cost)** — caller-supplied cost now arrives alongside *declared*
  measurements, so `require_cost_card_coverage`'s "every metric must have a card" check
  (`pricing_service.py:114-122`) is restated against declarations rather than free text. Unresolved
  measurements are a new blocking state it must handle.
- **#147 (markup and price precedence)** — its parked question from #138, *"may a policy line
  additionally condition on a declared dimension?"*, is **answered: no, not in v1.** Grouping Fields
  have no price role. #147 still owns precedence and target-margin arithmetic.
- **#148 (pricing versions)** — Cost Rates key on `(event_type, measurement)` with no variant
  dimension, so the effective-dating story simplifies. Measurement declarations themselves need a
  change story: altering a `unit` retroactively changes the meaning of historical quantities, which is
  ADR-0005's slot-immutability argument one level down.
- **#149 (streaming: one event or many?)** — **partial reporting is now expressible**, because an event
  carries named declared quantities rather than an opaque bag. Whether it *should* be is #149's. It
  also inherits #142's warning that splitting one call into many events multiplies sub-micro roundings
  (§10's warning is phrased in this ticket's vocabulary).
- **#150 (spend limits)** — limits race COGS computed from measurements only; no attribute can alter
  the rate a limit is racing.
- **#152 (task dashboard) / #153 (analytics re-alignment)** — #153 inherits the most: three
  tag-grouping surfaces to migrate (§8.2), reporting fragmentation from operational variant Event
  Types (§6.3), the Measurement Concept as the cross-provider aggregation path, and the rule that
  only declared Grouping Fields may be grouped.
- **#154 (vocabulary lock)** — six names to lock (§10), `DimensionDef` → `GroupingFieldDef` across
  API/SDK/console/`labels.ts`/`CONTEXT.md`, the retirement of "tags" and "metric", and the
  reconciliation of this document with #138 §5.2 and #142 §7.3 in the owed ADR.
- **#155 (migration and cutover)** — **loses** #142's onboarding-currency prerequisite (§7.4); **gains**
  seven currency-column restorations, the USD CHECK constraints, the `tags` → `metadata` fold, four
  new slot columns, six index drops, and the `usage_metrics` → `measurements` wire rename.
- **#156/#157 (Code Builder)** — the generator now has an enumerable contract per Event Type, and
  `source_path` is its input for emitting the provider-response mapping.

---

## 14. Residue, flagged not buried

- **`UsageEvent` does two jobs.** It records *what happened* (measurements — not monetary) and *what it
  cost and earned* (`provider_cost_micros`, `billed_cost_micros` — monetary). §7.2's rule exposes the
  seam: the currency belongs to the economic posting, not to the measurement record. #139 already
  created a first-class `Charge` projected onto a marked usage posting, so half the seam exists.
  **Splitting measurement-record from economic-posting is a larger structural move than #145 should
  decide, and it needs its own ticket.** Until it exists, `UsageEvent` owns money and therefore stores
  its currency.
- **FX is deferred, not designed.** A tenant whose supplier bills in a foreign currency maintains
  converted rates by hand, and recorded COGS drifts from actual as rates move. The future feature
  needs native *and* reporting amounts plus a snapshotted conversion — not a currency column on every
  table.
- **Concurrent multi-account cost variants are unsupported** (§6.2), awaiting an explicit cost-profile
  mechanism.
- **`source_path` is unvalidatable by UBB.** UBB never sees the provider response, so it can check
  *declared / typed / non-negative / required-and-present* but never that a number came from the right
  provider field. The mapping is enforced by **code generation, not validation** — which is an argument
  for `source_path` being mandatory on any Measurement whose Event Type has a Provider, and for the
  Code Builder being the primary defence against a correct-looking wrong mapping.
- **The cardinality cap's justification changed** (§5.4). ADR-0005's stated reason is now false. If the
  restatement in §8.3 is not carried into the ADR, a future reader will find the reasoning broken and
  may delete the cap.
- **Ten slots has no empirical backing** (§9.2). It is headroom sizing after a capability removal.
- **Measurement declaration change semantics are unspecified** — retire-never-delete is the obvious
  inheritance from #138 and ADR-0005, but which fields are immutable (`unit` certainly; `value_type`
  probably) is left to #148.
