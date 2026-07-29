# Event Type as a real entity — the target entity set

**Resolves:** [#138](https://github.com/ashcochrane/ubb/issues/138) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-07-29
**Decided against:** `main` @ `27efac5`
**Evidence:** `docs/research/2026-07-29-pricing-model-prior-art.md` (#143, branch
`research/pricing-model-prior-art` @ `2f0ce4c`) — six platforms against primary sources
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR yet, deliberately.** This is a hard-to-reverse decision and the ratchet would normally ask
for one. #154 is the single naming pass that fixes every term once, and an ADR written before it
would be rewritten by it. The ADR is owed *after* #154, and should cite this document.

---

## The decision in one paragraph

**Event Type owns costability, not cost.** It is the registered operational thing a tenant meters —
what happened, which measurements a completed event produces, which of those drive cost, their units
and calculation rules, and which properties may vary its supplier cost. It never holds a single
timeless cost amount, because supplier cost changes with date, processing mode, region, and
purchasing arrangement. It never holds the customer price, because price is contextual to plan,
customer, assigned book and time — the cardinality wall that zero of six surveyed platforms cross.
**Cost amounts live on independently effective-dated Cost Rates**, one per measurement per variant.
**Customer pricing lives in a versioned, customer-assignable Pricing Policy Book** whose default job
is to turn COGS into a sell price. Provider and Event Category are real entities: Provider supplies
the cost context, Event Category carries commercial policy across providers.

---

## Target entity set

```
Provider ──────has many (optional)─────> ProviderAccount
   │                                          │
   │ has many                                 │ optional cost selector
   ▼                                          │
EventType ────declares────> Measurement       │
   │  │                          │            │
   │  │                          ▼            │
   │  │                     CostRate <────────┘
   │  │                  (effective-dated,
   │  │                   one per variant)
   │  └────declares────> cost dimensions
   │                     (which properties may vary cost)
   ▼
EventCategory  (one primary, optional, cross-provider)


UsageEvent ──references──> EventType
     │
     ▼
  Measurements + declared cost-dimension values + occurred_at
     │
     ▼
  CostRate effective at the event timestamp
     │
     ▼
  Calculated COGS
     │
     ▼
  PricingPolicy   (EventType → EventCategory → book-wide default)
   in an assigned PricingPolicyBook
     │
     ▼
  Customer charge
```

### Provider — *new*

The external party supplying the underlying service and creating the cost. A real entity rather than
a label because it needs stable identity for supplier accounts, currency defaults, and navigation.

- **Owns:** supplier identity; the cost context; optional provider accounts; the catalog view of its
  Event Types (`Provider has_many EventType` **is** the catalog — no separate catalog entity unless
  curation, enablement, ordering or subsets are later needed).
- **Does not own:** customer pricing. Provider is never a substitute for commercial category.
- **Per-tenant only** (constraint 5 — no UBB-shipped catalog). **Retire, never delete.**
- **Optional on an Event Type.** Internal work with no external supplier gets no Provider; a fake
  Provider must never be created to satisfy the schema.
- Cost resolution keys on **provider identity**, never on parsing a readable provider name out of an
  event-type code.

### ProviderAccount — *new, optional*

A distinct purchasing arrangement or credential under one Provider that pays different rates
(`gemini-production` at list, `gemini-negotiated` at a discount). **Created only when a tenant
genuinely pays different rates through different arrangements** — nullable everywhere, and no tenant
is forced to create one to enter simple public rates.

### EventType — *new*

The registered operational thing our code records (`gemini-api-call-flash-4.0`). A stable identifier
and, per the research, "a stable API contract between your application and your billing
configuration".

- **Owns:** identity/code; what happened; its declared Measurements; which Measurements are cost
  drivers; units and calculation rules for those measurements; its declared **cost dimensions** —
  which properties may vary its supplier cost; exactly one Provider when provider-backed; one
  optional primary Event Category.
- **Does not own:** any cost amount; any customer price.
- **Per-tenant only. Retire, never delete** — historical events reference it permanently.
- **Variants are not identities.** Batch vs standard, us vs eu, one account vs another are
  cost-selection dimensions. `…-flash-4.0-batch-eu` as a separate Event Type is wrong: it is the same
  operational event with the same measurement schema. A separate Event Type is warranted only when
  the operation itself or its measurement contract changes.

### Measurement — *new*

One declared measurable quantity a completed Event Type produces (`input_tokens`, `output_tokens`,
`completed_calls`). Carries its unit and calculation rule, and whether it is a cost driver. Owned by
its Event Type.

> The noun is provisional. `metric` is **not** available: the research establishes that "metric"
> names the *metered entity* industry-wide (`billable_metric` in both Lago and Metronome), so using
> it for the quantity inside guarantees mis-translation. Final word → #154; whether the vocabulary is
> shared with grouping fields → #145.

### CostRate — *new*

The effective-dated supplier amount for exactly one (Event Type, Measurement) and one cost-dimension
variant.

- **Independently effective-dated per component.** A tenant's job is only: *for this Event Type, this
  measurement costs this amount, in this currency and unit, from this date onward.* When one amount
  changes, they add one new rate for that component; everything else keeps its dates.
- **No mandatory container.** There is deliberately **no Supplier Cost Schedule / agreement /
  versioned supplier price-sheet entity**. Presenting all of a Provider's current rates together, and
  letting several changes land as one revision, is a **usability and audit affordance** — not a
  required object and not a rule that rates must be versioned as a set.
- Carries: amount, currency, unit basis, `effective_from`, and either an exact cost-dimension variant
  or the explicit `default` marker.
- Historical events resolve against the rate effective at **their own** timestamp.

### EventCategory — *new*

What broader **kind of commercial work** an operation represents (`llm-inference`), independent of
which supplier performs it. Exists because customer pricing policy usually follows the kind of work,
not the vendor — and a Provider-level policy is not a substitute: it would group unrelated work
merely for sharing a supplier, and could never express "all LLM inference regardless of vendor".

Deliberately constrained for v1: tenant-defined, **optional**, **one primary category per Event
Type**, **no hierarchy**, **no arbitrary multi-tag monetary matching**. Analytics tags may exist
alongside but never participate in monetary resolution. **Membership must be historically
reproducible** — effective-dated, or preserved in the rating record — so replaying an old event never
applies today's category.

### PricingPolicyBook — *kept, re-scoped, renamed from `RateCard`*

The versioned, customer-assignable container of commercial policy. It survives because it does the
one job nothing else does: **give this customer that coherent set of commercial rules, versioned as a
unit.**

- **It does not file Event Types.** Event Types belong to Providers.
- Its lines reference **registered Event Types or Event Categories**, never free-text selectors.
- Line content: markup on cost, target gross margin, minimum charge, rounding rule, included
  allowance, or an explicit **fixed sell-rate override**.
- **A fixed sell rate is an explicit override, not the default meaning of a line.**
- If "book" now reads as *fixed prices*, rename to **Pricing Policy Set** / **Commercial Policy
  Set** (#154). The set-level versioning and customer assignment behaviour stays either way.

---

## Resolution: two deterministic ladders, no wildcards

### Cost

Conceptual key: `event type + measurement + provider account + declared cost dimensions + event timestamp`.

1. **Exact declared variant.**
2. **Explicitly marked default rate.**
3. **Neither → leave the event uncosted and require resolution.**

**Blank-field wildcard matching is rejected outright**, along with "most specific row wins". The
reason is a genuine ambiguity, not a preference: given rate A pinning `provider_account` and leaving
`region` open, and rate B pinning `region` and leaving `provider_account` open, an event from that
account in that region matches both and **neither is inherently more correct**. No accidental rate
may be selected merely because some fields were blank.

### Price

1. **Exact Event Type policy.**
2. **Event Category policy.**
3. **Book-wide default.**
4. **Otherwise unresolved** — never a silent zero.

An exact Event Type override wins over its category's policy.

### Cost-first, and what "no cost" means

Cost-plus policies **require resolvable COGS**. A tenant may still charge for usage with no supplier
cost, but **only through an explicitly configured direct-pricing policy**. Two hard rules:

- **Missing cost must never be interpreted as zero.**
- **Direct-priced usage with unknown cost reports margin as *unavailable*** — a first-class value,
  distinct from zero margin.

---

## Unrecognised events: accept, quarantine, replay

An unknown event type is an **operational configuration error, not invalid historical data**. The
provider may already have charged us; rejecting would hide real COGS, and deployment ordering or
config drift must not cause permanent data loss.

```
received → unrecognised → recognised → costed → priced → invoiced
```

On a valid envelope carrying an unregistered event type: **store the event immutably**, preserving
the raw submitted code, the raw measurements and the original `occurred_at`; mark recognition
unrecognised and rating/pricing blocked; calculate no COGS, no price, and do not invoice; alert the
tenant and surface remediation.

**Never auto-register.** Auto-registration lets a typo become permanent billing vocabulary and can
silently distort COGS or lose revenue (the research documents exactly this failure mode at the one
platform that does it).

Remediation is explicit: **map to an existing Event Type**, **register as a new Event Type**, or
**classify as non-economic usage**. On resolution, **replay from the original event timestamp** — the
occurrence time, never the repair date, selects both the Cost Rate and the policy version.

**Period-close safeguard:** a billing period containing unresolved economic events cannot close
silently. The tenant must register/map, explicitly classify as non-economic, or deliberately waive
with an auditable reason.

**Still rejected at the door:** malformed, unauthenticated, duplicate or structurally invalid
envelopes. The distinction is *invalid envelope → reject*; *valid envelope with an unknown event type
→ accept, quarantine, require resolution*.

---

## What each existing entity becomes

| Existing | Disposition |
|---|---|
| `UsageEvent.event_type` free text (`usage/models.py:29`) | **Kept, re-typed** — a reference to a registered Event Type, plus the raw submitted code preserved for the quarantine path |
| `UsageEvent.provider` free text (`usage/models.py:31`) | **Absorbed into Event Type** — derived from the Event Type's Provider, system-written, never caller-supplied. Survives physically only as a denormalised analytics read column |
| `UsageEvent` recognition/rating/pricing state | **New** — `recognition_status`, `rating_status`, `pricing_status`, plus preserved raw measurements for replay |
| `Rate` — the line (`pricing/models.py:59`, table `ubb_rate_card`) | **Split, then deleted** — its cost half becomes `CostRate`; its price half becomes a policy line in the book |
| `Rate.card_type` + `RateCard.card_type` (`:63`, `:139`) | **Deleted** — cost and price are two entities on opposite sides of COGS; this flag was one table impersonating both |
| `Rate.metric_name` (`:80`) | **Promoted and renamed** — a reference to a declared Measurement. The word "metric" is retired (→ #154) |
| `Rate.provider`, `Rate.event_type` selectors (`:70-71`) | **Absorbed** — entity references, not text selectors |
| `Rate.task_type`, `subtask_type`, `dim1..dim6` selectors (`:72-79`) | **Kept on the cost side only**, as exact-match cost-dimension variant values. The `""` wildcard and specificity ranking are **deleted** |
| `Rate.customer` (`:61`) | **Deleted** — never read in resolution today (`_assigned_book` is price-only, `pricing_service.py:53-59`); cost is customer-invariant by construction |
| `Rate.valid_from` / `valid_to` (`:91-92`) | **Kept in substance** as per-component `effective_from` on `CostRate`; mechanism inventory → #148 |
| `Rate.book_version_from` / `_to` (`:88-89`), `RateCard.version` (`:146`) | **No remaining job on the cost side** — cost rates are independently dated, not book-versioned. Set-level versioning survives on the policy book → #148 |
| `Rate.lineage_id` (`:90`) | → #148 |
| `Rate.pricing_model ∈ {per_unit, flat}` (`:81`) | **Kept in substance** — unit basis and calculation rule, declared per Measurement |
| `Rate.currency` (`:85`) | **Kept** on `CostRate` ("this currency and unit") → #142 |
| `RateCard` — the book (`:130`, table `ubb_rate_card_container`) | **Kept, re-scoped, renamed** — the Pricing Policy Book. Never a container for Event Types |
| `RateCard.provider_key` (`:142`) | **Deleted** — provider-scoped books were a cost-side device, and cost has no books |
| `RateCard.is_default` (`:147`) | **Repurposed** — the book-wide default policy, step 3 of price resolution |
| `RateCardAssignment` (`:164`) | **Kept, renamed** — assigns a Pricing Policy Book to a customer |
| `TenantMarkup` (`:8`) | **Absorbed** into policy-line content. Markup stops being a parallel mechanism and becomes the *default* meaning of a line; precedence → #147 |
| `PricingService._resolve_card` three-tier book walk (`pricing_service.py:67-92`) | **Deleted** — two deterministic ladders replace it |
| `PricingService._resolve_rate_within` wildcard + specificity (`pricing_service.py:31-50`) | **Deleted** |
| ADR-0005 §8 "book tier dominates rate specificity" sharp edge | **Dissolves** — no two independent ranking layers remain to disagree |
| `DimensionDef` / `DimensionValue` registry (`platform/dimensions/models.py`) | **Kept.** `provider` and `event_type` stop being pricing selectors (they are entity references now) while remaining analytics axes. Whether declared cost dimensions draw from this registry or from a separate per-Event-Type declaration → #145 |
| `CardCache` | **Kept in role, re-keyed** — no ten-selector tuple; keyed on (event type, measurement, account, cost-dimension variant, as-of) |
| `require_cost_card_coverage` tenant flag | **Structural now** — cost-plus requires resolvable COGS by construction, so the opt-in flag has no job on that path → #146 |
| — | **New:** Provider, ProviderAccount (optional), EventType, Measurement, CostRate, EventCategory, PricingPolicy |

---

## Constraints this imposes on the tickets #138 was blocking

- **#145 (quantities vs grouping fields)** — must coin the quantity noun, and `metric` is unavailable.
  Also decides whether declared cost dimensions reuse the `DimensionDef` registry or are a separate
  per-Event-Type declaration. Already fixed here: the Event Type carries a **role assignment** over
  whatever that vocabulary is — *which properties may vary this operation's cost* — which is
  Metronome's `group_keys` / `pricing_group_key` shape from the research.
- **#146 (provider-supplied cost)** — fixed here: missing cost is never zero; direct-priced usage
  reports margin *unavailable*. `require_cost_card_coverage` loses its opt-in job on the cost-plus
  path. The task-limit collision remains #146's to resolve.
- **#147 (markup: layer or fallback)** — direction is now fixed and it is the **reversal of today's
  behaviour**: markup/margin is the *default* content of a policy line and a fixed sell rate is the
  *explicit override*. Today a matched price line prices directly and markup never runs at all
  (`pricing_service.py:150-167`). #147 still owns precedence (plan vs customer vs book-wide) and the
  target-margin arithmetic.
- **#148 (pricing versions)** — fixed here: cost amounts are independently effective-dated per
  component, so a book-version window has no job on the cost side; policy books stay set-versioned;
  category membership must be historically reproducible. #148 decides which of `lineage_id` /
  effective dating / book version / provenance receipt survive.
- **#154 (vocabulary)** — "book" may become Pricing Policy Set or Commercial Policy Set; "metric" is
  retired; Cost Card / Price Card stop being one word for two sides.

## Known residue, flagged rather than buried

- **No dimension conditioning on the price side.** The decided price ladder has exactly three targets
  (Event Type → Event Category → book default). Whether a policy line may *additionally* condition
  on a declared dimension — a different margin for `region=eu`, say — is deliberately unanswered
  here. #147 should confirm or extend.
- **Category hierarchy** is out for v1 by decision, not by accident. One primary category, no
  nesting. Revisit only with evidence.
- **Batch revision** of several cost rates as one auditable change is called for as a UI/audit
  affordance, but no revision entity is specified. Whoever builds the cost catalog owns that gap.
- **Cost dimensions are declared per Event Type**, so two Event Types may declare the same property
  independently. That interacts with the cardinality guard in #145.
