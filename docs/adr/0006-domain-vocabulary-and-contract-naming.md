# ADR-0006: Domain vocabulary and contract naming

**Status:** accepted
**Date:** 2026-08-03
**Decision record:** `docs/plans/2026-08-03-vocabulary-lock-decision.md` (#154) — the exhaustive
snapshot, the full name table, and the migration matrix
**Supersedes:** ADR-0005 on its central noun (Dimension → Grouping Field) and on `Rate.SELECTORS`
**Amends:** ADR-004 §2, with one scoped, dated, pre-production exception (§7)
**Cutover:** [#155](https://github.com/ashcochrane/ubb/issues/155)

## Context

Four products on a shared kernel had accumulated several words for one concept and one word for
several concepts. `RateCard.card_type` made cost and price one entity. "Dimension" meant both a
grouping axis and a rate selector. The record explaining a price was called `pricing_provenance` in
the model, "the pricing receipt" in an endpoint docstring, and "the audit trail" in a glossary — where
"audit trail" already named the ADR-004 governance ledger. `_micros` meant millionths of a currency
unit on one field and millionths of a percent on another, an ambiguity that had already forced a
defensive bound. `Rate` sat on the table `ubb_rate_card` while `RateCard` sat on
`ubb_rate_card_container`.

Thirteen decision documents (#138–#153) re-modelled the domain between 2026-07-29 and 2026-08-03.
Each deferred its naming debt to a single pass so that nothing would be renamed twice, and each
recorded that this ADR was owed afterwards. Map #137 constraint 1 — **no live integrators** — makes
one clean break available instead of an additive alias layer plus a 90-day sunset (ADR-003 §4). That
freedom expires the moment someone integrates.

## Decision

**One concept, one word, on every surface — enforced by tests, not by convention.**

Names are fixed by the decision record. This ADR fixes the **rules**, which outlive the pass and
against which future naming proposals are assessed.

### 1. A suffix names a unit, and two units may never share one suffix

`_micros` means millionths of a currency unit and nothing else. A percentage scaled by a million is
`_micro_percent`. A duration is `_seconds`.

### 2. One canonical public term per concept

No short form beside a long form. If the analytics contract says `customer_spend_pool`, the webhook
namespace and the `control_family` field say `customer_spend_pool` too. An abbreviation that saves
eight characters costs a second public name for one concept.

### 3. Method, mode and structure describe different things

```
method     how an amount is derived         costing_method · pricing_method
mode       which operating regime applies   pricing_mode · customer_billing_mode
structure  the mathematical shape of a rate rate_structure
```

Two fields whose names differ by one character but whose meanings are unrelated (`pricing_model`
beside `pricing_mode`) are a defect, not a coincidence.

### 4. A derived fact is not stored independently

Two encodings of one fact can disagree, and the wrong one is always the one nobody is looking at. A
derived value may be *served* read-only so callers need not reconstruct it; it is never *written*.

### 5. A webhook event is named for the state entered

Cause and mechanism belong in structured payload fields, never in the event name.

```
<domain owner>.<past-tense state transition>

resource lifecycle transition → the resource owns the namespace
control's own state change    → the declared control family owns the namespace

event name      canonical state entered
reason_code     specific business cause      (more specific; not forced to match)
trigger_source  mechanism that applied it
control_family  canonical control-family vocabulary
```

One overloaded event carrying a discriminating reason string makes every consumer reimplement the
classification. Distinct states get distinct events.

### 6. A configured maximum is named as a maximum

`max_task_starts_per_minute`, not `task_start_rate_per_minute` — the latter reads as telemetry
describing the current rate rather than a bound someone configured.

### 7. Infrastructure terminology does not dictate domain vocabulary

Where a framework's word collides with a domain word, **the framework yields**: namespace the
infrastructure, qualify its uses, keep the domain noun. Celery's `task` does not get to rename the
tenant's unit of work.

### 8. Foreign vocabulary survives only at integration boundaries

> At an integration boundary, preserve the external system's canonical object names where exact
> correspondence is valuable. Everything in UBB's own domain vocabulary remains ours to rename.

`stripe_payment_intent_id` keeps Stripe's noun so an engineer can search Stripe's dashboard with it.
UBB still says Customer Charge, Customer Spend Pool, Wallet Policy, Pricing Receipt. Foreign names are
isolated into integration records rather than scattered through core domain models.

**"Frozen" means stable while the correspondence holds**, not permanent. A rename stays legitimate if
the provider changes its canonical object, the integration is redesigned, the mapping was wrong, or
the field moves behind a typed adapter — deliberate and tested, because it affects reconciliation.

### 9. Physical table names track model names

`ubb_<snake_case_model_name>` for first-party managed concrete models. Exceptions are allowlisted with
a stated reason. A model rename normally carries a table-rename migration; the database does not
preserve obsolete terminology.

## The canonical vocabulary, in brief

The full table, every rule-per-name, and the migration matrix live in the decision record. This is the
orientation summary.

| Concept | Canonical name |
|---|---|
| Unit of work / contained unit | **Task** / **Subtask** (one model, nullable `parent_task_id`) |
| Registered metered thing | **Event Type** |
| A measurable quantity | **Measurement** |
| A declared grouping axis | **Grouping Field** |
| Supplier amount | **CostRate** |
| Home of pricing rules | **Pricing Book**; publishes are **Pricing Book Publish** |
| The record explaining an amount | **Pricing Receipt** (`provenance` is a section of it) |
| Spend controls | **Ceiling** · **`customer_spend_pool`** · **`wallet_policy`** · **`admission_control`** |
| Analytics measures | `supplier_cogs` · `customer_revenue` · `gross_margin` · `recorded_events` |
| Externally supplied revenue | **TenantSuppliedRevenue** |
| UBB's role in customer billing | `Tenant.customer_billing_mode ∈ {external, prepaid, postpaid}` |
| Derived posture | `tenant_posture ∈ {metering_only, full_billing}` — never stored |
| Usage row nature | `kind ∈ {metered_usage, task_charge}` |

Retired and not to reappear: `metric`, `dimension`, `tags`, Cost Card / Price Card, `budget`, `limit`
as a field word, "charging mode", `pre-check`, "ingest" / "fast lane" / "estimate" / "hold",
`revenue_mode`, `meter_only`, `metering_async`, "job" / "step" as prose synonyms, and "operation" as a
count noun.

Two qualifications that must survive in the glossary, because both names are otherwise misread:

- **Pricing Receipt** means the receipt for *economic resolution*, not a guarantee that customer
  revenue exists. A metering-only tenant has receipts.
- **`kind`** identifies the nature of a `UsageEvent` row only. It does not classify the tenant, the
  costing method, or how customer price was calculated.

## Consequences

- **Every rule above lands as a test.** A forbidden-term search over code, spec, SDK, console and
  living docs; a `db_table == canonical(model_name)` walker; a webhook catalog shape test; an absence
  test for derived-but-stored fields; and the four pinning tests for the `kind` discriminator. This is
  the house pattern — ADR-001's boundary walker made import discipline a gate, and this does the same
  for vocabulary. **Prefer backing any hard rule with a test.**
- **One-time, scoped amendment to ADR-004.** At #155's cutover the pre-production audit ledger is
  reset: surviving actions are renamed, actions for deleted concepts are removed, pre-cutover rows are
  deleted, and the production ledger opens with `system.preproduction_model_cutover`. The alternative
  — keeping retired names registered forever — would make the live codebase carry a second vocabulary
  solely to interpret pre-launch history. **After cutover, ADR-004's additive-only rule and retention
  floor apply unchanged**, and later terminology changes use additive retirement.
- **The v1 contract breaks deliberately, once.** OpenAPI is regenerated and the oasdiff breaking gate
  is run knowingly rather than suppressed. The SDK regenerates; two dead methods go with it.
- **ADR-0005 is superseded on its central noun.** Its `Rate.SELECTORS` ↔ `UsageEvent` invariant had
  already lost its subject under #145.
- **This freedom is spent.** The clean break is available exactly once; every rule here must hold on
  its own merits afterwards, when a rename costs a deprecation cycle.
- **Future naming proposals are assessed against this ADR**, not against the decision record — which
  is frozen evidence of one pass, not a living specification.
