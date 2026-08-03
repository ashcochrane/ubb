# The vocabulary lock — one word per concept, and the rules that decide the next one

**Resolves:** [#154](https://github.com/ashcochrane/ubb/issues/154) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-03
**Decided against:** `main` @ `df06cf3`
**Builds on:** all thirteen preceding decision documents, every one of which deferred its naming debt
here —
`docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — Event Type owns costability;
`card_type` deleted; "metric" retired; book naming routed here.
`docs/plans/2026-07-30-fixed-price-task-economics-decision.md` (#139) — the `Charge`, its 1:1
projection, the `kind` discriminator, `total_usage_cost_micros` flagged as a misnomer.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — six states; `expired` vs `killed`; the
`task.stopped` question left open here.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — one top-level `/tasks`;
`affordability` vs `wallet-status` left open here.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — one tenant currency; `default_currency`
becomes a lie; whether "micros" survives left open here.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — Measurement, Grouping Field,
Measurement Concept, `amount_micros`, `per_quantity`, `metadata`.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — two costing modes;
`costing_status`; `unresolved`; the third ceiling state.
`docs/plans/2026-07-31-markup-and-price-precedence-decision.md` (#147) — the Pricing Book; one method
per rule; three revenue states; markup retained as the word, forbidden from drifting to "margin".
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the receipt is authoritative; three
names for one record flagged; the Pricing Book Publish.
`docs/plans/2026-07-31-streaming-and-long-running-calls-decision.md` (#149) — one event is one
provider operation; the fast lane deleted; the declared-unit noun left open here.
`docs/plans/2026-08-01-spend-limits-decision.md` (#150) — four families; "limit" means four things;
the admission-control name left open here.
`docs/plans/2026-08-02-charging-modes-decision.md` (#151) — method/mode/structure; `pricing_model`
may not survive beside `pricing_mode`; "charging mode" retired.
`docs/plans/2026-08-03-analytics-realignment-decision.md` (#153) — the economic query; the four
measures; `recorded operations` provisional; `TenantSuppliedRevenue` owed a name.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**The ADR is no longer deferred.** Thirteen documents each recorded *"the ADR is owed after #154"*.
It is written as part of this pass: `docs/adr/0006-domain-vocabulary-and-contract-naming.md`. The
authority relationship is explicit and one-directional:

```
this document   exhaustive snapshot + implementation map   FROZEN EVIDENCE
ADR-0006        the durable rules, final authority         LIVING
```

The ADR carries a compact canonical-name summary and the rules. The full migration matrix lives
**only here**, so there is no two-document synchronisation problem. Future naming proposals are
assessed against the ADR, not against this document.

---

## The decision in one paragraph

**One concept, one word, everywhere — and the freedom to enforce that expires at the first
integrator.** Sixteen decisions fix the words; seven rules decide every word this pass did not
anticipate. The two names the ticket said could never change both dissolved: audit actions are freed
by a one-time pre-production ledger reset, and immutable `UsageEvent` rows are freed by #153's
cutover wipe — so the only genuinely frozen vocabulary in the system is **someone else's**, the
`stripe_*` mirror fields whose entire job is exact correspondence with a foreign API. Everything UBB
owns is renamed now, once. Task and Subtask survive as the domain nouns and Celery yields instead —
an infrastructure framework does not get to dictate the business domain. `_micros` means millionths
of a currency unit and nothing else. A webhook is named for the state entered, never the cause. And
because a document cannot enforce a vocabulary, every rule here lands as a test.

---

## 1. The ticket's premise, corrected

The ticket asked for *"names that cannot change, and why"* and supplied two: audit actions
(contractual, additive-only under ADR-004) and immutable `UsageEvent` rows (which keep old values
forever regardless of what anything is called). Both were sound when written. Both have since been
overtaken by decisions merged after the ticket was filed.

**`UsageEvent` rows do not survive.** #153 §13.2 removes usage and economic postings, Charges and
receipts, Tasks and steps, wallet deductions, period accumulators and analytics snapshots at cutover
— not for effort reasons but because old rows carry undeclared free-text measurement keys that #145
§2.4 forbids auto-registering. There is no row left to carry an old value forward.

**Audit actions were the real question**, and §4 answers it. With both dissolved, the "cannot change"
section is not the constraint the ticket expected — it is a single narrow rule about foreign
vocabulary (§7).

**A third premise is confirmed rather than corrected.** The ticket says the physical-vs-logical split
must be decided. It is worse than described — `Rate` sits on `ubb_rate_card` while `RateCard` sits on
`ubb_rate_card_container`, fully inverted — but the blast radius is smaller than it looks, because
both models are replaced by #138 and #148 anyway. §6 settles it with a rule rather than two renames.

---

## 2. The seven rules

These are the durable output of this pass. Each one decided more than one name below, and each one
decides names this document never saw.

### R1 — A suffix names a unit, and two units may never share one suffix

`_micros` means millionths of a currency unit. It may not also mean millionths of a percent. §3.5.

### R2 — One canonical public term per concept

No short form beside a long form. If the analytics contract says `customer_spend_pool`, the webhook
namespace says `customer_spend_pool` too. The abbreviation that saves eight characters costs a second
name for one public concept. §5.

### R3 — Method, mode and structure describe different things

Ratified verbatim from #151 §13.1:

```
method     how an amount is derived         costing_method · pricing_method
mode       which operating regime applies   pricing_mode · customer_billing_mode
structure  the mathematical shape of a rate rate_structure
```

### R4 — A derived fact is not stored independently

Two encodings of one fact can disagree, and the wrong one is always the one nobody is looking at
(#148 §5.2, which deleted the book version on exactly this reasoning). `tenant_posture` derives from
`customer_billing_mode` and is never written. §3.6.

### R5 — A webhook event is named for the state entered

Cause and mechanism live in structured payload fields, never in the event name.

```
event name      canonical state entered
reason_code     specific business cause
trigger_source  mechanism that applied the transition
control_family  canonical control-family vocabulary
```

§5.

### R6 — A configured maximum is named as a maximum

`max_task_starts_per_minute`, not `task_start_rate_per_minute` — the latter reads as telemetry
describing the current rate rather than a ceiling someone set. §3.4.

### R7 — Infrastructure terminology does not dictate domain vocabulary

Where a framework's word collides with a domain word, the framework yields: namespace the
infrastructure, qualify its uses, and keep the domain noun. §3.1.

---

## 3. The canonical names

### 3.1 The unit of work — Task and Subtask survive; Celery yields

**A Task is the top-level unit of work. A Subtask is the same record with a parent.** One model, one
table, a nullable parent:

```
Task
  parent_task_id: nullable

parent_task_id IS NULL   → a Task
parent_task_id IS NOT NULL → a Subtask
```

Subtask is a **product-facing relationship, not a second database model, not a separate pricing
entity, and not a `SubtaskType`.**

"Job" and "Step" were put and declined. The reasoning is recorded because it constrains future
proposals: *"Job" may sound like a queue execution or worker attempt; "Step" may imply a strictly
sequential workflow stage. Neither is more accurate than Task and Subtask.* Changing the entire
product language because Celery also uses the word "task" lets an infrastructure framework dictate
the business domain — R7.

**The collision is real and is fixed on the infrastructure side.** `apps.platform.tasks` (the domain
model) sits beside thirteen Celery `tasks.py` modules, and `config/settings.py:168-200` schedules them
with entries literally keyed `"task": "apps.billing.wallets.tasks.reconcile_wallet_balances"`.

The sharpest evidence is inside the domain app itself: **`apps/platform/tasks/tasks.py`** — a Celery
module whose dotted path says "task" twice, in two unrelated senses. `apps.platform.tasks.tasks` is
not a name anyone should have to disambiguate by reading the file.

| | |
|---|---|
| Domain model moves to | `apps.platform.work.models.Task` |
| Celery's sense must always be qualified | `celery_task` · `worker_task` · `scheduled_action`, or a full module path |
| Import discipline | `from apps.platform.work.models import Task` / `from apps.billing.wallets import tasks as wallet_worker_tasks` |

**No public API, SDK, Code Builder output or domain document may use Celery's meaning of "task."**

The public shape:

| Concept | Name |
|---|---|
| The unit of work | `Task` · `TaskType` · `/api/v1/tasks` |
| Caller's own identifier | `external_task_id` |
| Containment | `parent_task_id` · `/api/v1/tasks/{task_id}/subtasks` |
| Terminal signals | `task.killed` · `task.expired` · `subtask.killed` · `subtask.expired` |

**The two type columns collapse to one.** Today `Task.task_type` and `Task.subtask_type`
(`tasks/models.py:91-94`) are set exclusively — one or the other, decided by whether `parent` is set.
Since there is no `SubtaskType`, one column carries the declared kind and `parent_task_id` says which
level it sits at. `TaskType.kind ∈ {task, subtask}` survives, because it is what lets #151 §5.4 refuse
a `fixed` declaration on a subtask kind at declaration time.

### 3.2 Measurement, grouping and the Event Type

Ratified from #145 §10 without reopening — that document coined them against research and this pass
adds nothing by having a second opinion.

| Concept | Name | Rule |
|---|---|---|
| A measurable quantity | **Measurement** (`measurements`) | "metric" names the metered *entity* industry-wide; using it for the quantity inside guarantees mis-translation |
| A declared grouping axis | **Grouping Field** (`GroupingFieldDef`) | "Dimension" means *price selection* at Orb — the one job ours will never do |
| Cross-provider aggregation label | **Measurement Concept** (`concept`) | says what it is |
| The registered operational thing | **Event Type** | #138 |
| The open bag | **`metadata`** | one bag; `tags` retired with the capability it implied |
| The rate amount | **`amount_micros`** | it is an amount |
| The rate basis | **`per_quantity`** | reads as written |

### 3.3 Cost, price, and the record that explains them

**The authoritative record is a Pricing Receipt.** Today it has three names — the field is
`pricing_provenance` (`api/v1/schemas.py:177`, `:251`), the endpoint docstring calls it *"the pricing
receipt"* (`metering_endpoints.py:236`), and `apps/metering/CONTEXT.md:164` calls it *"the audit
trail"*. #148 argued in "receipt" 78 times, "provenance" 17 (always as a *section*), "audit trail"
twice — and "audit trail" already names the ADR-004 governance ledger.

`pricing_provenance` **understates** the field. The record now carries authoritative values and
statuses, not only references explaining where they came from:

```
pricing_receipt
  costing
    method: calculated
    measurements: ...
    cost_rates: ...
    provider_cost_micros: ...
  pricing
    method: margin_over_cost
    applied_percentage: ...
    billed_cost_micros: ...
  provenance
    cost_rate_ids: ...
    pricing_book_publish_id: ...
    matched_rule_id: ...
  subject_type: usage_event | charge
  subject_id: ...
  receipt_schema_version · pricing_engine_version
```

**It covers every economic path**, which is why "Charge Receipt" was declined as too narrow — most
operational events have no canonical Charge, and a fixed-price Task's events deliberately generate no
event-level Charge:

| Path | What the receipt holds |
|---|---|
| Event-priced usage | COGS and customer pricing |
| Fixed-price Task | child-event receipts hold COGS, pricing `not_applicable`; the Task Charge receipt explains the fixed price |
| Metering-only usage | COGS; customer pricing `not_applicable` or `unknown` as appropriate |
| Unresolved cost | costing status `unresolved`, amount NULL — never zero |

**One terminology qualification, documented on the name itself:** *Pricing Receipt* means the receipt
for **economic resolution**, not a guarantee that customer revenue exists. Without this, a
metering-only tenant reads "pricing receipt" as "UBB charged my customer."

```
pricing_status   known · waived · unknown · not_applicable
costing_status   known · unresolved · not_applicable
```

The rest of the cost/price vocabulary, ratified from the merged documents:

| Concept | Name | Source |
|---|---|---|
| The book of pricing rules | **Pricing Book** | #147 §4.1 — 34 uses across three documents against 2 for "Pricing Policy Set" and 1 for "Commercial Policy Set" |
| An immutable publish act | **Pricing Book Publish** | #148 §5.4 |
| The supplier amount | **CostRate** | #138 |
| One resolved price decision | **PricingRule** / **ResolvedPricingRule** | #147 |
| The rate's arithmetic shape | **`rate_structure ∈ {per_unit, fixed_component}`** | #151 §13.2 — ratified; `pricing_model` may not survive one character from `pricing_mode` |
| The cost derivation | **`costing_method ∈ {calculated, reported}`** | #146 |
| The price derivation | **`pricing_method ∈ {margin_over_cost, direct_event_price}`** | #147 |
| Whole-job pricing regime | **`pricing_mode ∈ {event_priced, fixed}`** | #151 |

**`TaskType.pricing_mode` and `Task.pricing_mode` share the word deliberately.** #151 flagged
`TaskType.task_pricing_mode` versus `Task.pricing_mode` as a naming question. Under R2 they are one
concept at two scopes — the declaration and its snapshot — and the model name already supplies the
scope. A `task_` prefix on a field of `TaskType` restates its own table.

### 3.4 Spend controls — four families, and "limit" leaves the field vocabulary

The four families keep #150's nouns. What changes is that **"limit" stops being a field word**, since
it named four different things:

| Family | Canonical term | Concrete fields |
|---|---|---|
| One unit of work | **Ceiling** | `task_cogs_ceiling_micros` · `task_silence_ceiling_seconds` · `task_duration_ceiling_seconds` |
| One customer's charges per period | **`customer_spend_pool`** | |
| The floors | **`wallet_policy`** | |
| Rate of new work | **`admission_control`** | `max_task_starts_per_minute` |

**Each ceiling field states its own basis and unit.** #150 §2.2 gives a Ceiling a declared basis of
`cost` or `time`, and both already exist in production — `provider_cost_limit_micros` bounds spend
while `Tenant.task_stale_seconds` and an absolute age bound time, all firing through the identical
`kill_and_announce` flow. A single `task_ceiling` carrying a basis value was declined on #150 §2.3's
own reasoning: a mode field that switches unit, storage and comparison simultaneously is the shape
that document refused when it rejected a universal `Limit` entity. These genuinely are separate
columns in different units, so the names say so.

**Admission control is narrowed, not just renamed.** `RiskConfig.max_requests_per_minute`
(`gating/models.py:7`) becomes **`max_task_starts_per_minute`**, scoped strictly to new top-level Task
admission. The scoping is structural, not cosmetic: #150 §1.3's one rule says reporting usage that
already happened is never refused, and a general request throttle *can* refuse a usage recording.
Narrowing the scope makes the rule hold by construction.

```
Start a new top-level Task              → may return 429 rate_limit_exceeded
Replay a start with the same key        → returns the original Task, consumes no admission
Report usage for an existing Task       → always accepted and recorded
Close / fail / cancel an existing Task  → not subject to admission control
Create or update configuration          → not subject to admission control
```

Subtasks created inside already-admitted work do **not** consume the allowance — otherwise an active
Task could be blocked because its own internal decomposition crossed the tenant's new-work rate. If
separate Subtask admission control is ever wanted it must be designed explicitly, never inherited
accidentally.

It answers one question — *how many new Tasks may this owner start in the window?* — and it is
**never described as spend protection**. It says nothing about supplier COGS and offers no monetary
overshoot guarantee. The rejection carries retry information (`Retry-After`, `window_reset_at`,
`limit`, `remaining`) and the scope key (tenant, billing owner or seat) is pinned from the commercial
contract and exposed, never silently varying between endpoints.

**The wallet question is `affordability`.** #141 left the final call between `affordability` and
`wallet-status`; `GET /billing/customers/{id}/affordability` stands. It names the question being
asked rather than the object inspected, so it stays true if a future credit line or grant becomes an
input — and "wallet" is now loaded vocabulary, since `wallet_policy` is a declared control family.

### 3.5 Money and units

**`_micros` means millionths of a currency unit, and nothing else.** Today it means two things: money
on `balance_micros`, and millionths of a *percent* on `markup_percentage_micros`. That ambiguity has
already cost defensive code — #147 §9.2 records that the `le=1_000_000_000` bound exists specifically
because a value *"is far more likely a unit error (percent passed as micros) than a real commercial
term."*

| Today | Becomes | Rule |
|---|---|---|
| `markup_percentage_micros` | **`markup_micro_percent`** | R1 — same scale, honest unit, no longer reads as money |
| `Tenant.default_currency` | **`Tenant.currency`** | #142 §3.4 — nothing can override a default that cannot vary |
| `usage_markup_margin_micros` · `markup_micros` | **`gross_margin_micros`** | #153 §14 — it is neither markup nor margin; it is `billed − provider` over a bucket |
| `total_usage_cost_micros` | **`total_customer_revenue_micros`** | it is neither only usage nor only cost (#139 §6, #153) |

"Markup" survives as the word for the configured input, per #147 §9.1 — *it is the word Stripe's
competing product uses* — and remains forbidden from drifting into "margin", which now names only the
displayed derived figure.

### 3.6 Tenant posture — one stored field, one derived reading

`Tenant.billing_mode ∈ {meter_only, prepaid, postpaid}` mixes a product name into a billing setting
and does not say what it governs. #141 §1.1 fixed what it actually decides — *mode decides who
invoices, not whether economics exist* — so the field is named for UBB's role in customer billing:

```
Tenant.customer_billing_mode
  external    the tenant handles customer billing outside UBB; UBB records
              supplier COGS and may accept tenant-supplied revenue for margin
  prepaid     UBB calculates customer Charges and settles them against a wallet
  postpaid    UBB calculates customer Charges and places them on an invoice
```

**Posture derives and is never stored** (R4):

```
customer_billing_mode = external            → tenant_posture = metering_only
customer_billing_mode = prepaid | postpaid  → tenant_posture = full_billing
```

A second writable field would permit `tenant_posture = metering_only` beside
`customer_billing_mode = postpaid`. The derived value **is** returned as a read-only API and console
field, so callers never reconstruct the mapping themselves:

```json
{ "customer_billing_mode": "external", "tenant_posture": "metering_only" }
```

**`external` must never be read as "revenue is zero".** It means exactly one thing: *UBB does not
create, invoice or collect the tenant's customer Charges.* Both metering-only workflows survive:

| Workflow | COGS | Revenue | Margin |
|---|---|---|---|
| Cost tracking only | known | unknown | unavailable |
| Tenant supplies revenue | known | known | available at the supplied revenue scope |

**Posture does not decide every pricing outcome by itself.** It determines whether UBB customer
pricing is *applicable*; the precise behaviour still depends on the pricing context:

```
metering-only, missing UBB customer price    → not applicable; work proceeds
full-billing, event-priced, price unresolved → event recorded, revenue unresolved, alert per policy
full-billing, fixed-price, price unresolved  → Task start refused
```

**Code uses named capability checks, never scattered enum comparisons**, all derived from the one
field: `tenant.is_metering_only` · `tenant.uses_ubb_billing` · `tenant.uses_prepaid_wallet` ·
`tenant.uses_postpaid_invoicing`.

### 3.7 Analytics measures, and the count that tells the truth

| Measure | Rule |
|---|---|
| **`supplier_cogs`** | says which side of the trade |
| **`customer_revenue`** | |
| **`gross_margin`** | |
| **`recorded_events`** | it counts records at the tenant's declared granularity, not units of work |

**`recorded_events`, and no "operation" noun is introduced.** #153 proposed *"recorded operations"*
and #149 asked for the declared-unit noun *"if 'operation' is not it"*. They are one question, and the
answer is that #149 §2 already ruled **one event is one provider operation** — so a second noun for
the same thing would violate R2 on the very concept the rule exists to protect. "Recorded" carries
#153's honesty point; "event" keeps the measure tied to `EventType`, `UsageEvent` and `usage.recorded`.
This closes #149's open question: **the event is the declared unit.**

The constraint travels with the name, in the docs and in the discovery contract: a raw count may never
be the headline or denominator of a comparison whose grouping does not hold Event Type — or its
rollup — constant.

**Externally-supplied revenue is `TenantSuppliedRevenue`**, replacing `CustomerRevenueProfile`
(`subscriptions/economics/models.py:52`). It names who supplied the number, so no surface can present
it as something UBB charged, and "supplied" pairs with `supplier_cogs`. `ReportedRevenue` was
considered and declined — it would have paired neatly with #146's `reported` costing method, but
"reported revenue" is standard accounting language for the figure a company publishes, failing the
same industry-collision test that killed "metric" and "dimension" in #145.

### 3.8 The `kind` discriminator — the nature of a row, and nothing else

#139 §4.3 coined `work_charge` for the synthetic posting a fixed price projects onto, and left the
ordinary row unnamed. Both values are named here:

```
metered_usage   a real usage event reported for work that occurred
task_charge     a synthetic posting projected from the canonical Charge
                created when a fixed-price Task is delivered
```

`work_charge` is retired: "work" would be the only place that word appears as a noun now that Task is
the ratified unit of work, and `task_charge` ties the posting to both the `Charge` entity and the Task.

**The discriminator identifies the nature of the `UsageEvent` row only.** It does not classify the
tenant, and it does not determine how COGS or customer price was calculated. `metered_usage` therefore
spans:

- metering-only **and** full-billing tenants
- `calculated` **and** `reported` COGS
- event-priced Tasks **and** usage inside fixed-price Tasks

`metered_usage` must **not** be interpreted as belonging to a metering-only tenant, as having
measurement-calculated COGS, or as being charged to the customer per event. Those facts are governed
independently by `customer_billing_mode`, `EventType.costing_method`, `Task.pricing_mode` and the
resolved pricing rule.

The reporting contract:

| | `metered_usage` | `task_charge` |
|---|---|---|
| Counts as recorded operational usage | yes | **no** |
| Represents a provider operation | yes | **no** |
| May carry measurements and supplier COGS | yes | no |
| Carries the fixed Task's customer revenue | no | yes |
| Appears in event / provider / measurement analytics | yes | **excluded** |
| Participates in monetary totals | yes | yes, through the posting rail |

A fixed-price Task with 400 metered calls:

```
400 metered_usage rows   400 real operational events, supplier COGS,
                         event-level customer pricing not_applicable
  1 task_charge row      the fixed customer Charge, revenue,
                         excluded from recorded event counts
```

Four tests pin the practical reason the field exists:

1. `recorded_events` counts `metered_usage` only
2. `Task.event_count` counts `metered_usage` only
3. provider and measurement analytics exclude `task_charge`
4. revenue and monetary totals may include both kinds, according to their economic fields

---

## 4. The audit registry — a one-time pre-production reset

### 4.1 The collision

ADR-004 §2 makes audit action names contractual: *"additive-only, a rename is a breaking change"*,
with names *"deliberately decoupled from routes — the ADR-002 single-API restructure renames routes;
it must never rewrite history's vocabulary"*, plus a published 1-year retention floor.

#153's cutover does **not** touch the ledger. §13.2 wipes operational and economic records; §13.3
preserves configuration. Audit records are neither, so by default a year of development-era entries
survives carrying dead vocabulary — `dimension.declared` for a concept renamed to Grouping Field, and
`revenue_mode.set` for a setting #153 deleted outright.

### 4.2 The ruling

**A one-time pre-production audit reset, scoped narrowly and stated as an exception rather than a
weakening of audit policy.**

```
At cutover:
  rename audit actions to the new domain language
  delete registrations for concepts that no longer exist
  delete pre-cutover audit entries
  open the production ledger with one explicit entry
```

The opening entry, written in the new vocabulary:

```
system.preproduction_model_cutover
  occurred_at · code/version reference · actor · summary of the reset
```

This preserves evidence that the reset happened without retaining every development-era mutation
inside the production audit product.

### 4.3 Why not additive retirement

Keeping old names registered-but-retired would leave the live codebase carrying **a second vocabulary
solely to interpret pre-launch history** — working directly against the purpose of the clean break:

```
old vocabulary  removed from models, APIs and documentation
                → should also be removed from the live audit registry
new vocabulary  the only vocabulary understood after cutover
```

Additive retirement is the correct policy *after* launch, when real customer and governance history
exists. It is the wrong burden on a pre-launch codebase. **A database backup or export may be
retained privately for engineering rollback or forensic reference, but must not remain queryable
through the live audit system and must not require obsolete action names to survive in production
code.**

Renaming the registry *without* deleting the rows was declined outright: existing entries would refer
to actions the registry no longer recognises, so the feed would show entries `record()` denies exist.

**This is a one-time pre-production exception, not the ongoing policy.** After cutover: action names
are stable and never silently renamed; entries are retained for the promised production period; and
future terminology changes are handled through additive retirement wherever real customer or
governance history exists.

### 4.4 The registry changes

Against `apps/platform/audit/actions.py` (55 names today):

| Today | Becomes | Why |
|---|---|---|
| `dimension.declared` | `grouping_field.declared` | #145 |
| `rate_card.created` / `.assigned` / `.published` | `pricing_book.created` / `.assigned` / `.published` | #147 §4.1, #148 §5.4 |
| `rate.added` / `rate.deleted` | `cost_rate.added` / `.deleted` **and** `pricing_rule.added` / `.deleted` | #138 splits the line across the COGS boundary |
| `markup.set` / `markup.deleted` | **deleted** | `TenantMarkup` deleted (#147 §4.2); markup is now a field of a pricing rule, recorded by `pricing_rule.*` |
| `revenue_mode.set` | **deleted** | `Customer.revenue_mode` deleted (#153 §3) |
| `revenue_profile.set` | `tenant_supplied_revenue.recorded` | §3.7 — a per-period record, not a profile |
| `budget.set` | `customer_spend_pool.set` | #150 |
| `task_type.declared` | unchanged | TaskType survives |
| `margin_threshold.set` | unchanged | margin alerting survives |
| — | **new:** `event_type.declared` · `measurement.declared` · `customer_pricing_override.set` | #138, #145, #147 |
| — | **new:** `system.preproduction_model_cutover` | §4.2 |

Everything else in the registry — api keys, invitations, members, tenant config, sandbox, connect,
wallet money movements, top-ups, grants, customers, plans, subscriptions, referrals, webhook configs
— is untouched: those concepts did not change.

---

## 5. The webhook catalog — one convention

### 5.1 The problem

The 35-event catalog has no convention. Some namespaces are resources (`task.*`, `customer.*`,
`referral.*`), some are products (`billing.balance_low`), and some are mechanisms (`stop.fired`,
`soft_floor.crossed`, `budget.threshold_reached`, `margin.provider_cost_spike`). Two spellings of one
concept coexist — `auto_topup.requires_action` in the catalog beside `auto_top_up.configured` in the
audit registry.

### 5.2 The rule

```
<domain owner>.<past-tense state transition>

resource lifecycle transition → the resource owns the namespace
control's own state change    → the declared control family owns the namespace
```

The namespace, `control_family` and the analytics family use the **same canonical term** (R2). But
`reason_code` stays more specific and is **not** forced to match:

```
type:            wallet_policy.floor_crossed
control_family:  wallet_policy
reason_code:     hard_floor
```

Short namespaces (`pool.*`, `ceiling.*`) are refused: the abbreviation is less self-explanatory and
creates two public names for one concept. Filing control events under the affected resource
(`customer.spend_threshold_reached`) is equally refused: it hides which control fired and crowds
unrelated customer lifecycle, billing and spend-control events into one namespace.

### 5.3 Terminal task events

**`task.killed` and `task.expired`** (with subtask twins, since Subtask is a separately-subscribable
public resource). `task.limit_exceeded` and `subtask.limit_exceeded` retire with the word "limit".

The event name answers *what durable state was entered*; structured metadata answers *why*, *what
initiated it*, and *which control was involved*:

```json
{ "type": "task.killed", "task_id": "task_123", "status": "killed",
  "reason_code": "task_cogs_ceiling", "trigger_source": "usage_ingest",
  "control_family": "ceiling", "control_id": "ceiling_456" }
```

Several legitimate causes produce the same state, and that is the point:

```
task.killed  reason_code: task_cogs_ceiling      trigger_source: usage_ingest
task.killed  reason_code: task_cogs_ceiling      trigger_source: enforcement_patrol
task.killed  reason_code: parent_killed          trigger_source: parent_cascade
task.killed  reason_code: customer_spend_pool    trigger_source: pool_crossing
task.expired reason_code: silence_window         trigger_source: stale_reaper
```

**A single `task.stopped` was declined** on #140 §4.3's own reasoning: a subscriber alerting on spend
incidents must stop being paged when a worker dies, and *"limit breach rate"* must be answerable
without parsing a reason string. One event with a reason field reintroduces exactly that parsing and
makes every consumer reimplement the classification.

**`task.ceiling_exceeded` was also declined** — it confuses cause with outcome, is inaccurate where a
patrol applied the transition or a parent cascaded it, and is doubly wrong because under #150 §10's
`>=` convention a ceiling may be **reached** rather than numerically exceeded.

**A Pool crossing and the Tasks it kills are separate events**, never one overloaded webhook:

```
customer_spend_pool.threshold_reached
task.killed  reason_code: customer_spend_pool  trigger_source: pool_crossing
```

### 5.4 The catalog, renamed

| Today | Becomes | Rule |
|---|---|---|
| `task.limit_exceeded` | `task.killed` · `task.expired` | §5.3 |
| `subtask.limit_exceeded` | `subtask.killed` · `subtask.expired` | §5.3 |
| `budget.threshold_reached` | `customer_spend_pool.threshold_reached` | control family owns it |
| `soft_floor.crossed` / `.cleared` | `wallet_policy.soft_floor_crossed` / `_cleared` | control family owns it |
| `stop.fired` / `stop.cleared` | `customer.stopped` / `customer.stop_cleared` | a customer-wide stop is a customer state |
| `billing.balance_low` / `_critical` / `_overage` | `wallet.balance_low` / `_critical` / `_overage` | the wallet owns its own levels; "billing" is a product, not an owner |
| `billing.credit_grant_expired` / `_expiring` | `credit_grant.expired` / `.expiring` | resource owns it |
| `billing.customer_suspended` | `customer.suspended` | resource owns it |
| `billing.topup_requested` | `top_up.requested` | resource owns it; matches the audit spelling |
| `billing.withdrawal_requested` | `withdrawal.requested` | resource owns it |
| `auto_topup.requires_action` | `auto_top_up.requires_action` | one spelling, matching `auto_top_up.configured` |
| `margin.customer_unprofitable` | `customer.unprofitable` | "margin" is now only the displayed derived figure (#147 §9.1) |
| `margin.provider_cost_spike` | `provider.cost_spike` | same |
| `usage.invoice_pushed` / `_failed_permanent` | `usage_invoice.pushed` / `.push_failed_permanent` | the invoice owns its own state |
| — | **new:** `admission_control.rate_limit_reached` | if genuinely needed |

`usage.recorded`, `usage.refunded`, `refund.requested`, `customer.deleted`, `invitation.*`,
`member.activated`, `referral.*`, `sandbox.reset_completed`, `tenant.api_key_*` are unchanged — each
already names a resource and a past-tense transition.

**An ordinary 429 does not need a webhook merely because it was rejected.**
`admission_control.rate_limit_reached` is registered only if a genuine subscriber need exists.

---

## 6. Physical versus logical — one tested rule

### 6.1 The ruling

For every first-party **managed, concrete** model:

```
<ModelName> → ubb_<model_name in snake_case>

CostRate                 → ubb_cost_rate
PricingBookPublish       → ubb_pricing_book_publish
CustomerSubscriptionItem → ubb_customer_subscription_item
```

**The intent, in the owner's words:** *the new tables must be an accurate reflection of what we are
adopting, not a semi-shadow of their former selves.*

### 6.2 The wart, measured

Only 4 of 58 models with an explicit `db_table` mismatch, and two are real:

| Model | Table today | Canonical |
|---|---|---|
| `Rate` | `ubb_rate_card` | `ubb_rate` |
| `RateCard` | `ubb_rate_card_container` | `ubb_rate_card` |
| `CustomerSubscriptionItem` | `ubb_customer_sub_item` | `ubb_customer_subscription_item` |
| `ConnectOAuthState` | `ubb_connect_oauth_state` | *(allowlisted — see §6.4)* |

The `Rate` / `RateCard` inversion resolves **by construction**: #138 splits `Rate` and #148 replaces
`RateCard`, so their tables are rebuilt regardless. The replacements take correct names rather than
inheriting inverted legacy ones.

### 6.3 The one real migration

`ubb_customer_sub_item` → `ubb_customer_subscription_item` must be a **genuine table rename**
preserving rows, primary keys, foreign keys, indexes, constraints and sequences. It must **not** drop
and recreate the table.

### 6.4 The gate, and its pre-flight checks

A CI test walks all applicable models and asserts
`model._meta.db_table == canonical_table_name(model.__name__)`, covering managed, concrete,
first-party tables only. Documented exceptions are allowlisted **with a reason** — unmanaged external
tables, proxy models, framework-owned tables, auto-generated through tables, or a name exceeding the
database identifier limit. Arbitrary `db_table` values are not permitted merely because Django allows
them.

Both pre-flight checks the rule requires were run against `main` @ `df06cf3` and **pass**:

```
collisions between canonical names   NONE (58 models)
longest canonical name               ubb_referral_reward_accumulator = 31 chars
                                     (PostgreSQL identifier limit: 63)
```

One allowlist entry is created at adoption: **`ConnectOAuthState` → `ubb_connect_oauth_state`**,
because mechanical snake-casing produces `ubb_connect_o_auth_state`, which is worse than the correct
name already in place. Reason recorded: *OAuth is a single acronym token.*

**Accepted consequence:** a future model rename normally carries a table-rename migration. That is
desirable — the database should not preserve obsolete terminology indefinitely.

---

## 7. What is frozen, and what "frozen" means

### 7.1 The principle

Not *"any name containing a foreign system's terminology can never change"*, but:

> **At an integration boundary, preserve the external system's canonical object names where exact
> correspondence is valuable. Everything in UBB's own domain vocabulary remains ours to rename.**

### 7.2 Provider mirrors keep the provider's nouns

The 17 `stripe_*` model fields retain Stripe's canonical object names — `stripe_payment_intent_id`,
`stripe_subscription_id`, `stripe_subscription_item_id`, `stripe_invoice_id` and the rest — because
the name communicates an exact mapping:

```
UBB field  ↕  Stripe API object and dashboard identifier
```

An engineer reconciling a payment should not have to translate an internal euphemism before searching
Stripe. Renaming `stripe_payment_intent_id` to something generic like `payment_reference` would hide
which external identifier it actually contains.

### 7.3 Scoped to the integration layer, and structurally isolated

```
Stripe adapter and mirror records  → may use Stripe's canonical nouns
UBB domain models, APIs, analytics → use UBB's own vocabulary
```

UBB still says **Customer Charge**, **Customer Spend Pool**, **Wallet Policy**, **Pricing Receipt** —
never adopting Stripe terminology merely because Stripe is one possible collection provider. Where
possible the foreign names are isolated structurally:

```
StripePaymentRecord
  stripe_payment_intent_id
  stripe_invoice_id
```

rather than scattering `stripe_*` fields through unrelated core domain models. The canonical UBB
record references the integration record without making Stripe vocabulary part of the economic model.

### 7.4 "Frozen" means stable while the correspondence holds

Not metaphysically permanent. A rename remains legitimate if the provider changes its canonical
object, the integration is redesigned, the field was incorrectly mapped, or the field moves behind a
typed adapter. Such a change is **deliberate and tested** because it affects reconciliation — not
prohibited outright.

### 7.5 Error codes are UBB-owned

They are not foreign vocabulary and are not frozen. Pre-launch and unpublished, they are renamed or
removed **now**. They become stable only when the relevant API contract is actually launched, after
which they are deprecated deliberately or versioned.

### 7.6 The published v1 spec is not frozen

Honouring the `api-v1-launch` tag was considered and declined. Map #137 constraint 1 has already
overridden it deliberately — #141 retires `POST /api/v1/billing/pre-check` outright rather than
deprecating it. Half-applying a contract we are already overriding would leave the spec carrying old
and new vocabulary side by side, which is the outcome this pass exists to prevent.

---

## 8. Retirements — words that must not survive

Each of these must return **zero hits** in first-party code, the spec, the SDK, the console and the
living docs after cutover (dated documents under `docs/plans/` and `docs/reviews/` are frozen history
and are exempt).

| Retired | Replaced by | Source |
|---|---|---|
| `metric` / `metric_name` | Measurement | #145 |
| `dimension` / `DimensionDef` | Grouping Field / `GroupingFieldDef` | #145 |
| `tags` | `metadata` | #145 |
| Cost Card / Price Card / `card_type` | CostRate · Pricing Book | #138 |
| `budget` | `customer_spend_pool` | #150 |
| `limit` *(as a field word)* | Ceiling · Pool · Wallet policy · Admission control | #150 |
| "charging mode" | the three declarations; `charging_summary` for display | #151 §13.3 |
| `pre-check` | `affordability` | #141 |
| "ingest" / "async ingest" / "fast lane" | the one recording core | #149 §6 |
| "estimate" / "hold" | the price is the price | #149, #148 §8 |
| `work_charge` | `task_charge` | §3.8 |
| `revenue_mode` | deleted; posture derives | #153 §3 |
| `pricing_provenance` *(as the record name)* | `pricing_receipt`; provenance is a section | §3.3 |
| "audit trail" *(for the receipt)* | Pricing Receipt; "audit log" stays the governance ledger | §3.3 |
| `meter_only` | `external` | §3.6 |
| `metering_async` *(product flag)* | deleted | #149 §6 |
| "job" / "step" *(as prose synonyms)* | Task / Subtask | §3.1 |
| "operation" *(as a count noun)* | `recorded_events` | §3.7 |
| `pricing_model` | `rate_structure` | #151 §13.2 |
| `flat` *(rate structure value)* | `fixed_component` | #151 §13.2 |

**"Margin" is not retired — it is narrowed.** It names only the displayed derived figure and the
`gross_margin` measure, never a stored per-event value and never the configured input (which is
markup).

---

## 9. Where each name must appear

A name is locked only if it is identical on every surface. The matrix, with the artefact that must
change and the gate that proves it:

| Surface | Artefact | Proof |
|---|---|---|
| Model | `apps/**/models.py` | the naming test (§6.4) |
| Database | `db_table`, constraint and index names | the naming test (§6.4) |
| API | `api/v1/*.py`, `schemas.py` | spec regeneration |
| OpenAPI | `openapi/v1.json` | `scripts/export_openapi.py`; oasdiff breaking gate run deliberately |
| SDK | `ubb-sdk/ubb/*.py` | regenerated from the spec; TS gate |
| Webhooks | `apps/platform/events/schemas.py` → catalog derives | catalog test |
| Audit | `apps/platform/audit/actions.py` | `record()` refuses unregistered names |
| Console | `apps/ui/src/lib/labels.ts` + call sites | `api:generate`; type-check |
| Analytics | `queries.py` measures, group-by contract | discovery-contract test |
| Errors | error codes and problem details | contract test |
| Glossaries | `CONTEXT-MAP.md`, per-product `CONTEXT.md` | forbidden-term search |
| Docs | `CLAUDE.md`, `docs/conventions/`, `docs/adr/` | forbidden-term search |

### 9.1 Console specifics

`apps/ui/src/lib/labels.ts` (337 lines) carries more retired vocabulary than any other single file:

| Export | Change |
|---|---|
| `cardTypeLabel` | **deleted** — `card_type` is gone (#138) |
| `pricingModelLabel` | → `rateStructureLabel`, values `per_unit` / `fixed_component` |
| `revenueModeLabel` | **deleted** (#153 §3) |
| `dimensionLabel` · `ANALYTICS_DIMENSIONS` · `TIMESERIES_GROUP_BY` | → grouping-field vocabulary, `field:` / `rollup:` kinds (#153 §5.3) |
| `taskStatusLabel` | gains `cancelled` and `expired` (#140 §1.1) |
| `billingModeLabel` · `billingModeDescription` | `meter_only` → `external`; add derived `tenant_posture` |
| `PRODUCTS` · `productLabel` · `productDescription` | `metering_async` deleted; "audit trail" wording corrected |
| `budgetEnforceModeLabel` | → `spendPoolEnforceModeLabel` |
| `preCheckReasonLabel` | → `affordabilityReasonLabel`; `budget_*` → `customer_spend_pool_*` |
| `stopReasonLabel` · `stopScopeLabel` · `pastLimitFamilyLabel` | → the four control families; `task_limit` → `task_cogs_ceiling` |
| `ingestModeLabel` | **deleted** (#149 §6) |
| `ingestRejectionLabel` | `pricing_error` deleted — `PricingError` has no raise sites left (#146 §6.3) |
| `WEBHOOK_EVENT_TYPES` | the full §5.4 rename |

The `humanize()` fallback and ADR-003's open-enum stance mean an unrenamed value degrades to a
humanised raw token rather than crashing — which is exactly why a forbidden-term search, not runtime
behaviour, is the gate.

### 9.2 SDK specifics

Two dead methods go with the rename rather than being carried forward:

- `ubb-sdk/ubb/metering.py:313` — `update_rate_card`, which PUTs to a path absent from
  `openapi/v1.json` (#148 §14)
- `ubb-sdk/ubb/metering.py:320` — `get_rate_card_history(lineage_id)`, calling a path that exists in
  neither `metering_endpoints.py` nor the spec; its test passes only because it mocks the HTTP call
  (#148 §5.3)

### 9.3 `CLAUDE.md` changes

The orientation file states two facts this pass invalidates:

```
Tenant billing modes (Tenant.billing_mode): meter_only · prepaid · postpaid
Tenant products: metering, billing, referrals, metering_async
```

Both must be restated: `Tenant.customer_billing_mode` with `external · prepaid · postpaid`, and
`metering_async` removed from the product list (#149 §6).

---

## 10. What each existing thing becomes

Consolidated migration map. Items already decided by a merged document are marked with their source
and are listed here only because they must appear on a surface this pass owns.

| Today | Becomes | Source |
|---|---|---|
| `apps.platform.tasks` (domain) | `apps.platform.work` | §3.1 |
| `Task.parent` | `Task.parent_task_id` | §3.1 |
| `Task.task_type` + `Task.subtask_type` | one `Task.task_type`; level from `parent_task_id` | §3.1 |
| `Task.provider_cost_limit_micros` | `task_cogs_ceiling_micros` | §3.4 |
| `TaskType.default_provider_cost_limit_micros` | `default_task_cogs_ceiling_micros` | §3.4 |
| `Tenant.task_stale_seconds` | `task_silence_ceiling_seconds` | §3.4 |
| `RiskConfig.max_requests_per_minute` | `max_task_starts_per_minute`, narrowed | §3.4 |
| `RiskConfig.max_concurrent_requests` | **deleted** | #150 §12.5 |
| `Tenant.billing_mode` | `Tenant.customer_billing_mode`; `meter_only` → `external` | §3.6 |
| `Tenant.default_currency` | `Tenant.currency` | #142 §3.4 |
| `Tenant.require_cost_card_coverage` | **deleted** | #146 §6.1 |
| `UsageEvent.usage_metrics` | `measurements` | #145 |
| `UsageEvent.tags` | **deleted**; contents to `metadata` | #145 |
| `UsageEvent.dim1..dim6` | `dim1..dim10`, analytics-only | #145 |
| `UsageEvent.pricing_provenance` | `pricing_receipt` | §3.3 |
| `UsageEvent.kind` | `metered_usage` / `task_charge` | §3.8 |
| `Rate.metric_name` | a reference to a declared Measurement | #145 |
| `Rate.rate_per_unit_micros` / `unit_quantity` | `amount_micros` / `per_quantity` | #145 |
| `Rate.pricing_model` | `rate_structure ∈ {per_unit, fixed_component}` | #151 §13.2 |
| `Rate` / `RateCard` (tables inverted) | `CostRate` + pricing rules; `PricingBook` — correct tables by construction | §6.2 |
| `RateCard.version` | `PricingBookPublish` | #148 §5.4 |
| `Rate.lineage_id`, `book_version_from/to` | **deleted** | #148 §5 |
| `DimensionDef` | `GroupingFieldDef` | #145 |
| `TenantMarkup` | **deleted** | #147 §4.2 |
| `Plan.markup_percentage_micros` / `fixed_uplift_micros` | **deleted**; Plan gains a required `pricing_book_id` | #147, #151 §7 |
| `markup_percentage_micros` (surviving sites) | `markup_micro_percent` | §3.5 |
| `CustomerRevenueProfile` | `TenantSuppliedRevenue` | §3.7 |
| `Customer.revenue_mode` | **deleted** | #153 §3 |
| `TenantBillingPeriod.total_usage_cost_micros` | `total_customer_revenue_micros` | §3.5 |
| `usage_markup_margin_micros` · `markup_micros` | `gross_margin_micros` | §3.5 |
| `event_count` (measure) | `recorded_events` | §3.7 |
| `CustomerSubscriptionItem` table | `ubb_customer_subscription_item` (true rename) | §6.3 |
| `stripe_*` mirror fields | unchanged, isolated into integration records | §7 |

---

## 11. Answers to the ticket's five questions

**1. The final name for every entity, field and API parameter, with a stated rule for each.**
§3 gives the names; §2 gives the seven rules; §10 gives the migration map. Every name in §3 carries
its rule inline rather than as a bare assertion.

**2. Where each name must appear identically.**
§9's matrix — spec, SDK, console (`labels.ts` itemised in §9.1), `CONTEXT.md` glossaries, docs, error
codes, webhook event types and audit action names — each with the gate that proves it (§12).

**3. Names that cannot change, and why.**
Nearly empty, and §1 explains why: the ticket's two examples both dissolved. What remains is §7 —
foreign vocabulary at integration boundaries, frozen only while the correspondence holds.

**4. The physical-versus-logical split.**
Corrected in the same break (§6). One tested rule, `ubb_<snake_case_model_name>`; the inverted tables
resolve by construction; one true rename; one allowlisted acronym exception.

**5. What `tags` is called, if it survives.**
It does not. `tags` folds into `metadata` — one open bag, filterable, never groupable (#145 §8), and
"tags" retires with the grouping capability it implied.

---

## 12. Enforcement — the gates that keep this

A document cannot enforce a vocabulary. Each rule lands as a mechanical check:

| Rule | Gate |
|---|---|
| R1 unit suffixes | schema test: a `_micros` field is money-typed; no other unit uses the suffix |
| R2 one canonical term | forbidden-term search across code, spec, SDK, console and living docs |
| R3 method/mode/structure | enum-name test over the declaring models |
| R4 derived not stored | absence test: no writable `tenant_posture` column |
| R5 event = state | catalog test: every event type matches `<owner>.<past_tense>`; every terminal task event maps to a status value |
| R6 maxima named as maxima | reviewed at declaration; covered by the forbidden-term search for `*_rate_per_*` |
| R7 infrastructure yields | boundary test extension: no domain import of a Celery `tasks` module without qualification |
| §6 table names | `db_table == canonical(model.__name__)`, with an allowlist carrying reasons |
| §3.8 `kind` | the four pinning tests in §3.8 |
| Whole-surface | OpenAPI regeneration + oasdiff breaking gate, run deliberately; SDK regeneration; console type-check |

The forbidden-term search is the workhorse: §8's retirement table is its input, and the dated
documents under `docs/plans/` and `docs/reviews/` are excluded as frozen history.

---

## 13. Constraints this imposes on other tickets

- **#155 (migration and cutover)** — owns the largest share. The audit reset and its single opening
  entry (§4.2); the `ubb_customer_sub_item` true rename (§6.3); the `billing_mode` →
  `customer_billing_mode` value migration; the full webhook catalog rename (§5.4); the OpenAPI regen
  and a deliberate run of the oasdiff breaking gate; SDK regeneration including the two dead-method
  deletions (§9.2); and the `CLAUDE.md` restatement (§9.3).
- **#152 (task dashboard)** — renders in this vocabulary: `task.killed` versus `task.expired` as
  distinct first-class outcomes, never both counted as failures; the four control families as the
  stop taxonomy; `recorded_events` never headlining a comparison across mixed Event Types.
- **#156 / #157 (Code Builder)** — generates in this vocabulary and nothing else. Two call sites
  (start-with-key, close-with-outcome), Task/Subtask nouns, no Celery sense of "task", no retired
  word from §8 in any generated comment or identifier.
- **#158 (end-to-end audit method)** — §12's gates are the mechanical half of proving the built system
  matches the agreed model.
- **#165 (splitting the measurement record from the economic posting)** — inherits `metered_usage` /
  `task_charge` as the discriminator the split must preserve, and `pricing_receipt` with its explicit
  `subject_type`.
- **The owed ADR** — written as part of this pass:
  `docs/adr/0006-domain-vocabulary-and-contract-naming.md`. ADR-0005 is superseded on its central
  noun (Dimension → Grouping Field) and on `Rate.SELECTORS`, which #145 already left without a
  subject. ADR-004 §2 gains the one-time exception recorded in §4, scoped and dated.

---

## 14. Residue, flagged not buried

- **The clean break expires at the first integrator.** Every freedom this document spends — the audit
  reset, the table renames, the webhook catalog rewrite, the `billing_mode` rename — is available
  exactly once. This is the same exercise of map #137 constraint 1 that #148 §11 and #153 §13.4
  already invoked, not a new one, and it must not be read as licensing another afterwards.
- **`ConnectOAuthState` is the first allowlist entry, on day one.** A rule that needs an exception
  immediately is worth watching. If a second acronym model appears, the mechanical snake-case
  algorithm should be revisited rather than the allowlist extended twice.
- **`margin.*` → `customer.unprofitable` / `provider.cost_spike` are alerts, not state transitions.**
  R5 is written for state transitions; these two are the catalog's genuine anomaly-detection events,
  and the rule is applied by naming the *subject* of the alert. If more alerting events arrive, the
  convention may need an explicit third clause rather than an analogy.
- **`admission_control.rate_limit_reached` may never be registered.** It is listed conditionally in
  §5.4 because an ordinary rejected request does not need a webhook merely because it returned 429.
- **Two `pricing_mode` fields share one word by design** (§3.3). It is correct under R2 — one concept
  at two scopes — but it is exactly the shape #151 §13.2 warned about when `pricing_model` sat one
  character from `pricing_mode`. The difference is that these two genuinely *are* the same concept;
  that reasoning must survive in the glossary or someone will "fix" it.
- **The forbidden-term search will have false positives** in vendored code, migration files carrying
  historical column names, and the frozen dated documents. The exclusion list is part of the gate's
  design, not an afterthought — and an over-broad exclusion silently disarms it.
- **"Recorded events" still counts records, not work.** Renaming the measure makes the honest reading
  available; it does not make the dishonest comparison impossible. The grouping constraint (§3.7) is
  the actual protection, and it lives in the discovery contract rather than in the name.
