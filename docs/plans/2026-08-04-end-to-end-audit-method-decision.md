# The end-to-end audit — what a machine proves forever, and what a human judges once

**Resolves:** [#158](https://github.com/ashcochrane/ubb/issues/158) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-04
**Decided against:** `main` @ `cfb89fd`
**Blocked by:** [#154](https://github.com/ashcochrane/ubb/issues/154), merged — the vocabulary lock
**Builds on:**
`docs/plans/2026-08-03-vocabulary-lock-decision.md` (#154) — §12's gate table is the mechanical half
of this audit; §8's retirement list is the forbidden-term input.
`docs/plans/2026-08-03-migration-and-cutover-decision.md` (#155) — §11.3's five assertions, §11.4's
end-to-end proof obligation and the `conformance/` promotion question, both handed here.
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156) — §7's five secret tests, §10.4's
renderer tests, and §13's assignment of *"every emitted path corresponds to a real contract"*.
`docs/prototypes/2026-08-04-code-builder-output-notes.md` (#157) — §3.7's three drift axes, and eight
requested rulings this document inherits by being the last ticket standing.
`docs/adr/0006-domain-vocabulary-and-contract-naming.md` — the rules whose enforcement this designs.
`docs/adr/0007-schema-and-contract-change-rules.md` — §5 gates admission on this audit passing.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**The ADR is written as part of this pass:** `docs/adr/0008-audit-method-and-launch-gates.md`. The
authority relationship follows #154's precedent exactly:

```
this document   exhaustive gate inventory + registry design   FROZEN EVIDENCE
ADR-0008        the durable rules, final authority            LIVING
```

**This document amends two merged documents.** ADR-0007 §5 and #155 §11.4 are both changed, not
restated — §10 and §11 say precisely how.

---

## The decision in one paragraph

**Humans inspect meaning once; machines enforce every provable rule forever.** The agreed model stops
being prose and becomes a checked-in vocabulary registry — the normative source for every UBB-owned
name — because the artifact the ticket assumed could hold it, `openapi/v1.json`, declares a value list
in three of its one hundred and sixty-five schemas and is *designed* not to hold vocabulary. A check
becomes a permanent gate when an authoritative oracle holds the expected answer, the comparison is
deterministic, and it needs no human interpretation; everything else is judgement and belongs to a
single owned pre-launch acceptance audit that is never repeated on a schedule. The Code Builder's
output is testable, and the only test that proves all three of its drift axes is running the emitted
file **unmodified** against a real ephemeral server — CI may supply runtime inputs, never repair the
code. That suite gets its own permanently-gating home, because the folder already named `conformance/`
is wired to never fail a pull request. And the single admission act ADR-0007 imagined becomes two,
because a tenant who bills their own customers elsewhere should not wait on a Stripe account they will
never use.

---

## 1. The ticket's premise, corrected — the spec cannot be the oracle

The ticket proposes four candidate checks, and names one of them as the frontend/backend consistency
question: *"no name appears in the console that is not in the spec."*

**That check cannot be built.** Measured against `main` @ `cfb89fd`:

```
paths in openapi/v1.json                 105
component schemas                        165
schemas declaring an allowed value list    3
```

All three are on request bodies:

| Schema | Property | Values |
|---|---|---|
| `BudgetConfigIn` | `enforce_mode` | `alert_only` · `blocking` |
| `PlanIn` | `interval` | `month` · `year` |
| `ProgramCreateRequest` | `reward_type` | `flat_fee` · `revenue_share` · `profit_share` |

Every response status, kind, mode, reason and family in the entire tenant surface is an open string.
This is not an oversight — ADR-0003's open-enum stance is deliberate, and `apps/ui/src/lib/labels.ts`
states it in its own header comment: *"The contract deliberately has NO closed enums… every
status/kind/mode is an open string, and new values may appear without a schema change."*

So the console hand-writes roughly fifty value maps, and the document it would be checked against
knows seven of the values in them. **The spec is not a weak oracle for vocabulary; it is not an oracle
at all**, and making it one would require reversing ADR-0003 and turning every new status into a
breaking-gate event.

This moves the ticket's fourth question — *what does "the agreed model" exist as at audit time* — from
last to first. It is not one question among five. It is the dependency the other four hang from, and
the ticket says so itself: *"The answer determines whether an audit can be automated at all."*

### 1.1 The precedent is already in the repository

One vocabulary in UBB is already machine-checkable, and it works exactly the way the rest must:

```
openapi/error-codes.json          29 problem codes, checked in
  ├── core/problems.py            the app renders from it
  ├── ubb-sdk/codegen/            generates _exceptions_generated.py;
  │     generate_exceptions.py    CI fails on any diff
  ├── conformance/dialect.py      derives the sweep's notion of "contract"
  ├── api/v1/tests/               test_problem_contract.py pins it
  └── docs/conventions/           api-contract.md, sdk-wrap.md cite it
```

One declared file; the application, a generated SDK artifact, a test suite and the documentation all
derive from or are verified against it. Nothing about that pattern is specific to error codes.

---

## 2. The rule that assigns every check

This matters more than either list of checks, because it is what a future engineer applies to an item
neither this document nor its reviewers anticipated.

### 2.1 The rule

**Machine-proved versus human-judged.** A check becomes a permanent machine gate when **all three**
hold:

```
1. An authoritative source contains the expected answer.
2. The answer can be compared deterministically.
3. The check runs repeatedly without human interpretation.
```

**Being technically automatable is not sufficient**, and that clause is the load-bearing one. Almost
any subjective judgement can be encoded as a brittle assertion once somebody has hard-coded an answer.
`assert heading == "Pricing Receipt"` proves the heading is consistent. It does not prove the term is
still the right one for the concept, and calling that question "automated" overstates what the test
established.

A question stays human when the answer requires judgement about **meaning, adequacy or acceptable
risk** rather than comparison against an existing oracle.

### 2.2 The seam, drawn on one example

```
Machine proves    the receipt carries every required field
                  the worked example reconciles arithmetically
                  no retired name appears on any surface
                  "pricing_receipt" is spelled that way everywhere

Human judges      the receipt is understandable, and actually explains
                  the figure it carries
```

A machine may **assemble the evidence** for a judged question. It cannot manufacture the judgement.

### 2.3 What every human item must carry

Five lines, and no review ceremony for anything machine-verifiable:

```
Question being judged
Evidence presented
Why no existing machine oracle settles it
Owner of the decision
Recorded conclusion
```

The third line is what stops the human list quietly growing. An item that cannot state why no oracle
settles it is an unbuilt test, not an audit item.

### 2.4 The sentence the audit must contain

> **A green CI board proves the declared invariants passed. It does not prove that the declarations
> themselves remain meaningful, complete or commercially appropriate.**

This is written into the acceptance record verbatim. Without it, a fully green board is read as
evidence the model is right — and every gate in §8 is a *consistency* check. Consistency with a wrong
declaration is still green.

### 2.5 The conversion rule, and its limit

**Whenever the human audit finds a concrete defect that could recur mechanically, it becomes a test
and leaves human review permanently.**

```
Human finds pricing_provenance still in the console
  → add the forbidden-token gate
  → no human ever searches for it again
```

**The limit is explicit.** The broader semantic question — whether *Pricing Receipt* remains the right
concept — must **not** be converted into a spelling test and declared settled forever. Converting the
finding is right; converting the question is the failure §2.1's third clause exists to prevent.

---

## 3. The agreed model exists as a vocabulary registry

### 3.1 The ruling

**A checked-in, machine-readable domain-vocabulary registry is the normative source for UBB-owned
canonical names and values.** It sits beside the ADRs rather than replacing them:

```
ADR-0006             the naming principles and architectural rules
vocabulary registry  the exact machine-checkable vocabulary
code · OpenAPI ·     generated from, or validated against, the registry
console · SDK · docs
```

### 3.2 Four kinds — and why every string is not a closed enum

The registry's central design constraint is that it must **not** turn deliberately open or
tenant-defined fields into closed enumerations. That would reverse ADR-0003 and make a new
`reason_code` a breaking API change merely because the registry learned about it.

| Kind | Meaning | Consumer obligation |
|---|---|---|
| `closed` | UBB owns the complete value set | exactly these values, no more |
| `open` | UBB records known values and namespace rules | accept future and external values |
| `tenant_defined` | the tenant owns the values; UBB defines the field and its validation contract | never enumerated by UBB |
| `free_text` | not vocabulary | not registry content |

```yaml
customer_billing_mode:
  kind: closed
  values: [external, prepaid, postpaid]

ceiling_status:
  kind: closed
  values: [within_ceiling, ceiling_reached, indeterminate]

reason_code:
  kind: open
  known_values: [task_cogs_ceiling, customer_spend_pool, parent_killed]
  allow_unknown: true

grouping_field_value:
  kind: tenant_defined
```

### 3.3 The asymmetric check for open concepts

```
registry-known value missing from a UBB-owned consumer   → defect, fail
runtime value not known to the registry                  → legal, where the concept is open
```

This is what preserves forward compatibility while still catching the case that actually bites: UBB
declaring a value on one surface and forgetting it on another.

### 3.4 What the registry holds — and what it must not

**Holds** (UBB-owned public vocabulary): canonical concept names · closed value sets · webhook event
names · status values · control-family names · method, mode and structure values · canonical label
keys · retired terms and forbidden aliases · open namespaces with their known built-in values.

**Never enumerates**: tenant-created Event Type keys · tenant-created Task and Subtask kinds ·
Grouping Field values · instance display names · arbitrary provider outcomes · free-form descriptions.

The second list is map #137 constraint 5 restated as a schema rule — *UBB ships no catalogue* — so the
registry cannot become the vendor catalogue that constraint forbids.

### 3.5 Generation is preferred; verification is the fallback

> **A canonical token is authored once. Every other appearance is generated or verified.**

Generate where practical — backend constants, frontend constants and label keys, the webhook catalogue,
SDK constants, documentation vocabulary tables. Where generation is impractical, CI compares the
consumer against the registry. What is forbidden is the third option: a fourth hand-maintained
vocabulary sitting beside the backend, the console and the docs.

### 3.6 OpenAPI treatment — the open-enum stance is not reversed

An open concept keeps `type: string`. Recognised values are exposed as documentation metadata, never
as a closed `enum` array:

```yaml
ceiling_status:
  type: string
  x-ubb-known-values: [within_ceiling, ceiling_reached, indeterminate]
```

The registry stays normative; the OpenAPI representation is **generated from it** according to the
concept's kind. A closed concept may render a real `enum`; an open one never does.

### 3.7 File shape and location

"One checked-in file" means **one logical source of truth, not one enormous document.** A schema plus
domain-separated files reviews far better:

```
domain-vocabulary/
  schema.json
  economics.yaml
  tasks.yaml
  spend-controls.yaml
  webhooks.yaml
  retired.yaml
```

CI treats the directory as a single registry and **rejects duplicate canonical terms and conflicting
definitions across files.**

**Location: `domain-vocabulary/` at the git root, beside `openapi/`.** It is consumed by
`ubb-platform/`, `ubb-sdk/` and `apps/ui/`, and the root is the only level all three reach — which is
exactly why `openapi/error-codes.json` already lives there and already serves all three.

---

## 4. The console — the registry owns identity, localisation owns expression

### 4.1 The ruling

Generation stops at the boundary where vocabulary becomes copy.

```
registry            which canonical concepts and values exist
console / i18n      how those concepts are described to users
```

The registry generates the **value sets** and **stable label keys**; it does not carry the English.
"External billing" versus "Metering only", capitalisation, explanatory wording and future localisation
are presentation decisions that will change far more often than the token underneath.

```ts
// generated from the registry
export const CUSTOMER_BILLING_MODES = ["external", "prepaid", "postpaid"] as const;
export type CustomerBillingMode = (typeof CUSTOMER_BILLING_MODES)[number];
```

```json
// owned by the console / localisation layer
{
  "customer_billing_mode.external": "External billing",
  "customer_billing_mode.prepaid":  "Prepaid",
  "customer_billing_mode.postpaid": "Postpaid"
}
```

### 4.2 What CI proves

1. every required registry value has a label;
2. every console label refers to a valid registry value;
3. no retired token remains labelled or used;
4. every supported locale carries the required key;
5. generated value lists are current.

### 4.3 `humanize()` stops being a fallback — reversing #154 §9.1

#154 §9.1 treated the `humanize()` fallback as a safe soft-landing: *"an unrenamed value degrades to a
humanised raw token rather than crashing."* **That is now the defect, not the mitigation.**

Automatic humanisation turns an implementation token into accidental user-facing terminology. A system
that has just spent thirteen documents deciding what things are called must not then let
`meter_only → "Meter only"` manufacture a name nobody chose. A missing label **fails CI**; at runtime a
missing label renders an explicit development error rather than invented copy.

### 4.4 Coverage by kind

| Kind | Rule |
|---|---|
| `closed` | every value labelled; no additional platform value permitted |
| `open` | every UBB-known built-in labelled; an unfamiliar runtime value is legal, rendered in a deliberate generic form — never title-cased as though UBB authored the wording |
| `tenant_defined` | render the tenant's declared display name or key per that object's contract; the platform catalogue never enumerates them |
| `free_text` | rendered as supplied, subject to ordinary escaping |

### 4.5 The registry does not absorb copy

Out of scope, permanently: tooltips, empty-state prose, validation explanations, onboarding
instructions, marketing language. At most the registry generates a stable semantic key the console
attaches copy to:

```
registry owns    pricing_status.not_applicable
console owns     "Not applicable"
                 "This Task is sold for a fixed price, so its events do not
                  generate separate customer revenue."
```

### 4.6 The cost, measured

There is **no localisation layer in the console today.** `apps/ui/src/lib/labels.ts` *is* the layer:
337 lines, ~50 exported maps, 35 `humanize` call sites, imported by 52 files, and no i18n dependency
in either `package.json`. §4.1's split therefore creates real build work — introducing a keyed label
catalogue — which **no slice in #155's plan owns.** Recorded in §16 rather than buried, alongside
#156 §14.1's identical finding about the builder itself.

---

## 5. The Code Builder's output is testable, and how far

### 5.1 Why execution is not optional

#157 §3.7 established three ways generated code can drift, and only one of them is visible to any
static artifact:

| Axis | Held correct by | Visible to |
|---|---|---|
| **Names** | the tenant's own published configuration, read at generation time | cannot drift — no second copy exists |
| **Operations** | `operation_id` resolved against `openapi/v1.json` | static check |
| **Ergonomics** — SDK method names, imports, the `with`-block idiom | `ubb-codegen`, versioned against the SDK major | **execution only** |

**Mock execution does not close the third axis**, and the repository has already proved it: three SDK
methods called routes that exist in no spec and no router, stayed green in CI for months, and were
only ever exercised against a patched `httpx.Client` (#155 §13.2). A mock can faithfully reproduce the
generator's mistake rather than contradict it.

### 5.2 The pyramid

**Layer 1 — static, on every generated case.** Parse or compile; type-check where supported; every
`operation_id` resolves to a real spec operation; no real secret appears; declared names are preserved;
the rendered readiness verdict matches the plan.

**Layer 2 — renderer tests, per generation branch.** Calculated cost · provider-reported cost · direct
Task events · explicit Subtasks · fixed-price Task · unknown or incomplete configuration · secret
references. Cheap, and they cover the branch matrix that execution cannot afford to.

**Layer 3 — execution, on a small representative matrix.** At minimum one complete artifact per
materially different renderer target — Python SDK, raw HTTP/curl, and a future TypeScript target. A
further execution scenario is added only when it exercises a genuinely different runtime path, such as
calculated versus provider-reported COGS.

**The matrix is deliberately not** language × provider × costing method × pricing method × Task mode.

### 5.3 The execution test, step by step

1. seed a deterministic tenant configuration;
2. resolve a complete Code Builder plan;
3. render the artifact;
4. write it to disk **without patching its source**;
5. set only documented environment variables;
6. execute it as a customer would;
7. assert the resulting API and economic records.

A representative lifecycle covers: start a Task · optionally start a Subtask · record direct and
Subtask usage · resolve supplier COGS · receive and act on acknowledgements · complete the Subtask and
Task · verify the resulting postings and totals. **One dedicated scenario** crosses a ceiling and
proves the emitted stop branch behaves; not every smoke test deliberately breaches one.

### 5.4 "Unmodified" has a precise definition

| Allowed setup | Forbidden |
|---|---|
| `UBB_BASE_URL` | rewriting an import after generation |
| `UBB_API_KEY` | changing an SDK method name |
| runtime example values | patching a URL |
| temporary tenant / customer identifiers | injecting a transport mock |
| | editing an incorrect source path |

> **CI may supply the code's external runtime inputs. It may not repair the code.**

**This needs no change to the SDK or the artifact.** The prototype already reads its host from the
environment — `base_url=os.environ.get("UBB_BASE_URL", "https://api.ubb.dev")`
(`docs/prototypes/2026-08-04-code-builder-output/python/ubb_integration.py:94`) — so CI sets one
variable and runs the file exactly as shipped. That matters, because the SDK has **no transport
injection seam**: `httpx.Client(...)` is constructed independently in `billing.py:27`,
`metering.py:50`, `referrals.py:17` and `subscriptions.py:17`. Any approach needing an injected
transport would have required an SDK change *and* would have re-created the mock trap in §5.1.

### 5.5 "Real server" means ephemeral and internal

The actual UBB application, router, database and economic services, started in an isolated CI
environment. **Not** a shared deployed sandbox — nothing is deployed, and a shared one would make the
gate depend on somebody else's state.

**No real external providers.** The objective is UBB's integration contract, not the availability of
Google, OpenAI or Stripe. Provider responses come from deterministic local fixtures of realistic
shape, and the generated code still executes the tenant-declared `source_path` against them — which is
the line that actually needs proving, per #145 §14. Wallet and invoice behaviour runs through UBB's
real internal services with **test payment adapters**, never the live Stripe network.

### 5.6 Only complete artifacts execute

Binding on #156 §8's readiness axis:

```
scaffold     parse + fail-fast behaviour tested; never run as an integration
incomplete   diagnostics and placeholders tested; not expected to complete a lifecycle
complete     executed unmodified against the real CI server
```

This stops CI pretending a deliberately incomplete scaffold ought to behave like production code.

---

## 6. Readiness aggregation — the first ruling inherited from #157

#157 asked whether the file verdict is an aggregate of per-operation verdicts, or whether one blocked
Event Type makes the whole artifact `incomplete`. It must be answered here because §5.6 keys CI
behaviour on the verdict.

**Artifact readiness is the least-ready state of every required component in the selected
integration.**

```
scaffold     a structural declaration is missing — the Task Type or Event Type selection
incomplete   the structure is known, but at least one selected Event Type has a
             missing required mapping or declaration
complete     every selected Task Type, Event Type, Measurement, source mapping and
             required Grouping Field resolves
```

```
Selected Event Types
  gemini_generation      complete
  external_search        complete
  document_extraction    missing source_path

Artifact                 incomplete
```

The builder **may still render the valid blocks and clearly identify the blocked one** — it must not
label the combined integration complete.

**An advisory warning does not make an artifact incomplete.** #156 §3 makes the tenant's declaration
authoritative and the shape checker advisory; a suspect mapping is a warning. A **missing mandatory**
mapping is `incomplete`. The distinction is exactly #156 §3's, applied to the verdict.

---

## 7. The home — and why not `conformance/`

### 7.1 The ruling

**A dedicated, deterministic, permanently gating Code Builder test suite.** The existing sweep stays
where it is, best-effort and non-gating.

```
resolution   the resolved plan and its completeness verdict
renderers    language/client branches and snapshots
static       parsing, typing, operation IDs, forbidden secrets
execution    complete artifacts run unmodified against the ephemeral real server
```

### 7.2 Why the existing folder is the wrong home

`ubb-platform/conformance/` is defined by two properties that are precisely wrong for a gate:

```
pytest.ini      norecursedirs = ... conformance    excluded from the default suite
ci.yml:160      continue-on-error: true            can never turn a PR red
```

Plus a pinned extra dependency installed in-job. A must-pass invariant placed there would report into
a job summary and be ignored. The execution suite must inherit **none** of it: no
`continue-on-error: true`, no default-suite exclusion without an equivalent required job, no
best-effort semantics.

The deciding factor is **execution policy, not whether both things can loosely be called
"conformance."** A test's location should make its enforcement expectations unsurprising.

### 7.3 CI treatment

Fast layers — resolution, renderers, static — run in the normal test job. The real-server execution
tests may take a dedicated required job if startup cost makes them too heavy for the unit suite:

```
code-builder-execution
  required: true
  continue-on-error: false
```

Path filtering is a permitted optimisation, but the filter **must** include every input that can
change generation: the Code Builder itself, OpenAPI, the SDK, Task/Event Type schemas, the costing and
pricing contracts, and **the vocabulary registry**. A scheduled full run may supplement the required
PR gate; it may never replace it.

### 7.4 The fuzzer is not promoted, and its name is wrong

#155 §11.4 handed this ticket the question of whether the schemathesis sweep becomes a gate. **It does
not.** The sweep is stochastic and unseeded by design — `max_examples=10` per operation, and its own
module docstring says *"no findings means this run found nothing, not a proof of conformance."*
Promoting it would make a deliberately best-effort probe release-critical, which is a separate project
about determinism, reproducibility and failure triage. The Code Builder must not depend on that
cleanup completing.

**Separately: the folder is misnamed.** A process whose own documentation states it cannot establish
conformance should not be the thing called `conformance/`. It should later become `api_fuzzing/` or
equivalent. That rename does not block anything here; for this decision it is enough not to extend an
already-misleading directory.

---

## 8. The standing gates — the machine half, in full

Every row satisfies §2.1's three conditions. Rows marked ▲ are new work this document creates; the
rest are inherited from merged documents and listed so the inventory is complete in one place.

| # | Gate | Oracle | Source |
|---|---|---|---|
| G1 ▲ | Registry is internally valid — no duplicate canonical term, no conflicting definition across files | the registry schema | §3.7 |
| G2 ▲ | Every closed value set matches backend, console and SDK consumers | the registry | §3.2 |
| G3 ▲ | Every registry-known open value is present in UBB-owned consumers | the registry | §3.3 |
| G4 ▲ | No open concept has been silently converted to a closed schema enum | the registry | §3.6 |
| G5 ▲ | Generated artifacts are current — zero diff on regeneration | the registry | §3.5 |
| G6 ▲ | Every required registry value has a label; every label maps to a valid value; every locale carries the key | the registry | §4.2 |
| G7 | Forbidden-term search — no retired word on any living surface | #154 §8's table | #154 §12 |
| G8 | Webhook catalogue shape — `<owner>.<past_tense>`; every terminal Task event maps to a status | ADR-0006 §5 | #154 §12 |
| G9 | `db_table == canonical(model_name)`, allowlist entries carry reasons | ADR-0006 §9 | #154 §6.4 |
| G10 | No writable `tenant_posture` column | ADR-0006 §4 | #154 §12 |
| G11 | `_micros` is money-typed; no other unit uses the suffix | ADR-0006 §1 | #154 §12 |
| G12 | Enum-name test over declaring models — method/mode/structure | ADR-0006 §3 | #154 §12 |
| G13 | No unqualified domain import of a Celery `tasks` module | ADR-0006 §7 | #154 §12 |
| G14 | The four `kind` discriminator pins | #154 §3.8 | #154 §12 |
| G15 | OpenAPI drift, oasdiff breaking, TS smoke, UI contract snapshot, UI typecheck | `openapi/v1.json` | ADR-002, ci.yml |
| G16 | SDK core + exception regeneration — zero diff | spec, error registry | ci.yml |
| G17 | Every hand-written SDK call targets a real operation (method + path, or `operationId`) | the spec | ADR-0007 §4 |
| G18 | Every published operation carries an explicit SDK disposition; an increase in unwrapped is a reviewed change | the generated manifest | ADR-0007 §4 |
| G19 | Field transition classes enforced in the database across `save()`, `QuerySet.update()` and raw SQL | ADR-0007 §2 | ADR-0007 §2 |
| G20 | Migrations carry their data — rename, not add+remove | ADR-0007 §1 | ADR-0007 §1 |
| G21 | The five cutover assertions | #153 §13.5 | #155 §11.3 |
| G22 | Every seeded allowlist at zero; SDK invalid-call list at zero; no unexplained oasdiff difference | #155 | #155 §11.3 |
| G23 ▲ | Code Builder static layer — operation IDs resolve, no secrets, names preserved, verdict matches plan | spec + plan + registry | §5.2 |
| G24 ▲ | Code Builder renderer branches | snapshots | §5.2 |
| G25 ▲ | Code Builder execution — complete artifacts run unmodified | the running app | §5.3 |
| G26 | The five secret tests | #156 §7 | #156 §13 |
| G27 ▲ | Payment-rail activation invariant — `prepaid`/`postpaid` cannot be enabled without a matching activation record | the activation record | §10.3 |

**G26 restated, because #156 §7 defined the policy once rather than per template:** no secret value in
generated source; none in fixtures or snapshots; every secret reference carries setup instructions;
every non-secret platform-known value renders consistently; every runtime value lands at its declared
scope.

---

## 9. The one-time acceptance audit — the human half

### 9.1 What it covers

Only what §2.1 leaves to judgement:

- Does real economic value travel correctly end to end?
- Does a real or representative payment-provider flow reconcile?
- Do Task, Subtask, Event Type, costing and pricing still **mean** what the decision documents say?
- Are `unknown`, `waived`, `not_applicable` and `incomplete` states displayed **honestly**?
- Does the Code Builder produce a coherent integration from the final model?
- Are permissions and administrative boundaries correct?
- Have all old terms and temporary compatibility paths been removed?
- Are the migration, audit reset and API-baseline rotation complete?

### 9.2 What it records

```
audit date
auditor / owner
commit and API baseline
decision documents and ADRs reviewed
standing CI gates relied upon
manual scenarios exercised
known accepted limitations
```

Plus §2.4's sentence, verbatim.

**Roles, not individuals.** The record names the accountable role and the commit; no personnel data is
checked into the repository.

### 9.3 It does not recur

**No periodic full-audit process is established.** A focused human review repeats only on an explicit
architectural trigger:

- a new major API or economic-model version;
- a new payment or settlement provider;
- a substantial pricing or posting redesign;
- a new data-retention model;
- an incident demonstrating the existing gates missed a class of failure.

Scheduling an audit because time has passed creates governance bureaucracy without evidence that
anything changed. **Standing gates are ordinary tests** — no meetings, no sign-off, no periodic manual
review. Developers experience them as CI.

That is the payoff of doing one large audit properly: wherever it finds a mechanically detectable
problem, §2.5 converts it into a test and no human audits that issue again.

---

## 10. Two gates, not one — amending ADR-0007 §5

### 10.1 What ADR-0007 assumed

> *"Admitting the first integrator is a deliberate act, gated on the end-to-end audit (#158)
> passing."*

One act, one gate. That was right about the act and wrong about its scope, because it predates the
observation that **a tenant in `external` billing mode never touches Stripe at all.** Under #154 §3.6
such a tenant records supplier COGS and may supply their own revenue for margin, while billing their
customers entirely outside UBB. Blocking them on a Stripe account is blocking them on infrastructure
they will never use.

### 10.2 The ruling — platform admission, then billing-capability activation

The second gate is **not** a second integrator admission. It is a capability activation, and naming it
correctly is what keeps the model clean.

**Gate 1 — Platform admission.** Required before the first external integrator:

```
pre-launch acceptance audit passed
permanent CI gates green
API and SDK baseline established
Code Builder execution tests passed
cost recording and analytics verified
known launch limitations recorded

→ customer_billing_mode = external may be enabled
```

No Stripe account and no live-money test are required, because Stripe is outside this path.

**Gate 2 — Billing-capability activation.** Required before the first tenant uses
`customer_billing_mode ∈ {prepaid, postpaid}`:

```
automated payment-rail test-mode round trip passed
live credentials and webhook configuration verified
one controlled live-mode transaction completed
Charge → posting → invoice/wallet reconciliation confirmed
idempotency and duplicate-webhook handling confirmed
failure, refund and operational runbooks owned
named approver records the activation

→ UBB-managed billing enabled for an explicitly approved tenant or environment
```

### 10.3 Both a record and a flag — and the invariant between them

A capability flag alone is not a governance decision, and a governance record alone does not prevent
anything:

```
activation record   proves why and when billing was approved
capability flag     technically prevents premature use
```

**Enforced centrally, never as an advisory console convention** (G27):

> `prepaid` or `postpaid` may not be enabled unless the relevant payment-rail activation exists.

### 10.4 Scoped per payment rail, not named after Stripe

```
PaymentRailActivation
  rail            stripe · <future rail>
  environment     test · live
  activated_at
  approved_by
  evidence
```

One successful Stripe transaction must never be read as proof that a future collection mechanism is
ready. Each rail carries its own readiness evidence.

**`PaymentRailActivation` and `rail` are new public vocabulary** and enter the registry as `closed`
concepts under §3 — including the `environment` values — before anything is built on them
(ADR-0007 §3).

### 10.5 The governing rule

> **Admit tenants when the capabilities they will use are ready. Activate money movement separately,
> per payment rail, before anyone depends on it.**

---

## 11. The money test — amending #155 §11.4

### 11.1 What #155 required

> *"Slice 8 is not complete until a live Stripe money test has actually been run, in whatever form
> #158 specifies."*

The form is specified here, and the **timing is amended**: a live-money transaction is no longer a
slice 8 completion condition.

### 11.2 Why the timing changes

**No Stripe account or live payment operation exists.** Making one a precondition for finishing the
platform model turns an external commercial dependency into an artificial blocker on internal
engineering, and invites the worse outcome — a Stripe account created to satisfy a ticket's wording.

There are three distinct milestones, and #155 collapsed them into one:

```
1. Platform implementation complete   internal economic invariants and adapters tested
2. Payment integration ready          automated test-mode round trip passes
3. Real-money billing ready           one controlled live-mode transaction charged,
                                      received by webhook, reconciled and recorded
```

### 11.3 What slice 8 requires instead

The strongest tests executable **without a production payment account**:

- deterministic internal payment-adapter tests;
- webhook parsing and idempotency tests;
- Charge → posting → wallet/invoice reconciliation;
- refund and correction behaviour;
- failure and retry handling;
- no duplicated money movement;
- generated integration and contract tests (§5).

### 11.4 The automated test-mode round trip

Required before the payment integration is declared ready. Repeatable, no real money, and it covers
the **complete economic path** rather than payload shape:

```
create or finalise the customer liability
send the payment-rail request
receive the webhook
apply it idempotently
reconcile the result into UBB
verify the expected wallet, invoice and posting state
```

**This is materially wider than what exists.** `apps/billing/invoicing/tests/test_live_stripe_ar.py`
is gated on `UBB_STRIPE_LIVE_TEST`, runs against Stripe **test mode**, asserts the invoice **field
paths** the reconcile handlers read — and its own docstring records that it ships unrun. It proves
payload shape. It does not prove money moved.

### 11.5 The live-mode transaction

One controlled, low-value live transaction under an owned runbook, before enabling the first tenant to
bill or collect in live mode. It confirms live credentials work, live webhook delivery works, the
expected object is created, UBB reconciles it **exactly once**, fees and settlement fields are
represented correctly, and the resulting customer and tenant records are correct. The account,
environment, commit, operator, transaction reference and reconciliation result are recorded, and the
transaction is refunded or otherwise closed.

**It is an operational launch-readiness act — not a permanent CI test**, and not a prerequisite for
completing a platform that has no payment account.

### 11.6 How it is carried until then

Recorded explicitly, so it can neither be silently passed nor quietly lost:

```
Deferred prerequisite   required before the first live payment-rail billing customer
Reason                  no payment account or live operation currently exists
Owner                   named commercial / operations role
Evidence required       documented successful live-mode reconciliation
```

This obligation previously lived in a single line of a dated document (`scripts/integration_test.py`,
untouched since `5c9bcdf` on 2026-02-15, in no CI job, still calling a retired endpoint — dead for six
months before #155 §1.3 found it). §10.3's activation record and G27's invariant are what make the
same outcome impossible a second time: the flag cannot be turned on without the record existing.

---

## 12. Ceiling statuses — the second ruling inherited from #157

### 12.1 Why it is decided here

#157 F4 found that the three public ceiling statuses still spell a retired word. `within_limit` /
`limit_reached` / `indeterminate` were coined by #146 §5 and restated by #150 §4.1; ADR-0006 then
retired "limit" from field vocabulary and **declined `task.ceiling_exceeded` on the grounds that under
a `>=` comparison a ceiling is reached, not exceeded** — reasoning that endorses `ceiling_reached` word
for word. Nothing revisited the values.

They must be settled before the registry is committed, because the registry is normative and
ADR-0007 §3 forbids provisional public vocabulary. A later change would break the chain the registry
exists to protect:

```
registry value → backend constant → API-known value → console label key
               → SDK constant → analytics filter
```

They cost nothing to fix now: `within_limit` and `limit_reached` appear **zero times** in first-party
code, the spec, the SDK or the console on `main` @ `cfb89fd`. They exist only in decision documents
and #157's prototype. This is naming a thing not yet built, not renaming a shipped one.

### 12.2 The ruling

```
ceiling_status ∈ { within_ceiling, ceiling_reached, indeterminate }
```

**`indeterminate` is kept, and is not folded into `unresolved`.** The two name different things and
the distinction is worth a word:

```
unresolved      a cost value is missing
indeterminate   the resulting inability to evaluate the ceiling
```

Precise definitions:

| Value | Meaning |
|---|---|
| `within_ceiling` | every applicable cost needed for the evaluation is resolved, and accumulated COGS is below the ceiling |
| `ceiling_reached` | known accumulated COGS is at or above the ceiling |
| `indeterminate` | known accumulated COGS is below the ceiling, but one or more applicable costs remain unresolved, so UBB cannot prove the Task is within it |

### 12.3 The lower-bound rule

**Once the known portion has crossed the ceiling, missing costs cannot reverse the result.**

```
known COGS >= ceiling  → ceiling_reached
                         even when additional unresolved costs exist
```

`indeterminate` applies **only** while the known lower bound is still below the ceiling.

```
Ceiling £5.00 · known COGS £6.00 · one event unresolved  → ceiling_reached
Ceiling £5.00 · known COGS £4.00 · one event unresolved  → indeterminate
```

This is a spend-control safety invariant, not a naming detail, and it belongs in the registry beside
the values. It is the same principle #157 applied to generated code — *infer the outcome that costs
nothing, never the one that charges* — pointed at the enforcement side: unresolved cost may never
argue a Task back under a ceiling it has already reached.

### 12.4 No ceiling is not `indeterminate`

Where no ceiling applies, use the established applicability treatment — `not_applicable`, or omit the
ceiling evaluation at the enclosing contract level. `indeterminate` means *we tried and could not
tell*, never *there was nothing to evaluate*.

Where useful, the cause travels separately rather than being inferred:

```json
{ "ceiling_status": "indeterminate", "indeterminate_reason": "unresolved_cost" }
```

---

## 13. Six decisions deferred, with owners

#157 closed with eight requested rulings and no owner; #158 is the last open ticket in map #137. §6 and
§12 settle the two that block this document's own normative outputs. **The remaining six are deferred
to owned decision tickets — not left for implementation to improvise.**

Grouped by the contract they affect, rather than as one grab bag:

| Ticket | Rulings | Depends on |
|---|---|---|
| **[#179](https://github.com/ashcochrane/ubb/issues/179)** — generated integration runtime contract | SDK stop-raising default (#157 F1/R2) · `request_id` treatment (F3/R3) · where a `reported` Event Type declares its cost source (F5/R4) · the clean-exit-that-declares-nothing shape (§3.4/R7) | slice 3 (cost) and slice 5 (work) |
| **[#180](https://github.com/ashcochrane/ubb/issues/180)** — renderer and preview behaviour | `jq` versus plain `curl` for the HTTP target (R5) · the non-persisting cost preview (R8) | Code Builder build work (unassigned — §16) |

Each ticket states: owner · decision deadline · the slice that depends on it · public-contract impact ·
whether the vocabulary registry is affected. **The deadline is before the first slice that needs the
answer**, not "whenever implementation reaches it."

### 13.1 The deferral rule

> **The map may close with an owned decision dependency. A dependent implementation slice may not
> begin with that dependency unresolved.**

This is what keeps §12's principle general: implementation may not invent provisional public names or
behaviours while a decision remains open, and a decision discovered late gets a ticket of its own
rather than a hurried paragraph inside an audit document.

---

## 14. Answers to the ticket's five questions

**1. What must be mechanically checkable, and what can only be reviewed by a human?**
§2 gives the rule that decides it — an authoritative oracle, a deterministic comparison, no human
interpretation — and §8 gives the resulting inventory of 27 standing gates. §9 gives the human half,
which is eight judgement questions asked once. The ticket's four candidates: *one vocabulary on both
sides of pricing* is G2/G7; *a mode is never ambiguous* is G12 plus ADR-0006 §3; *every emitted Code
Builder path corresponds to a real contract* is G23 (and #156 §13's sharpening: every `operation_id`
resolves to a real spec operation, composing with ADR-0007 §4's operation-level gate); *no name appears
in the console that is not in the spec* is **replaced** by G6 against the registry, for the reason in
§1.

**2. Should the vocabulary lock be test-enforced across labels, spec and glossaries?**
Yes — §3 and §4. But not as three artifacts checked against each other, which has no oracle. One
registry is normative; labels, spec, SDK, backend and glossaries are generated from it or verified
against it. The console keeps the English (§4.1), and `humanize()` stops silently manufacturing it
(§4.3).

**3. Is the Code Builder's output testable, and is `conformance/` the right home?**
Testable, and only execution proves all three drift axes (§5.1). A three-layer pyramid, complete
artifacts run **unmodified** against an ephemeral real server with no live external providers (§5.3–§5.5).
`conformance/` is **not** the right home (§7.2) — it is excluded from the default suite and wired
`continue-on-error: true`. The new suite is permanently gating; the fuzzer stays best-effort, is not
promoted (§7.4), and is misnamed.

**4. What does "the agreed model" exist as at audit time?**
A checked-in machine-readable vocabulary registry (§3), normative for UBB-owned names, sitting beside
ADR-0006 rather than replacing it. Not the spec, which declares values in 3 of 165 schemas by design
(§1). Not the Django models, which describe what the backend currently accepts rather than what was
agreed. Not prose, which has no oracle.

**5. Who audits, and when?**
Both, split by §2's rule. One owned pre-launch acceptance audit against a named commit and baseline
(§9), and 27 standing gates that run forever (§8). The audit does not recur on a schedule (§9.3). And
the act it gates is now **two** acts — platform admission, then billing-capability activation (§10).

---

## 15. Constraints this imposes on other tickets

- **ADR-0007 §5 is amended** by §10: one admission act becomes platform admission plus payment-rail
  billing activation. The dated note in `docs/api-compatibility.md` is deleted at **platform
  admission**, since that is the act after which ADR-0003 §4 governs the contract.
- **#155 §11.4 is amended** by §11: the live money test is no longer a slice 8 completion condition.
  Slice 8 requires §11.3's list; the automated round trip gates payment-integration readiness; the
  live transaction gates billing activation. #155's deletion of `scripts/integration_test.py` in
  slice 1 stands unchanged.
- **#155 §11.3's five assertions** are inherited verbatim as G21 and are not restated or redesigned.
- **#154 §9.1 is reversed on one point** by §4.3: the `humanize()` fallback is a defect for canonical
  concepts, not a safe degradation. #154's conclusion — that a forbidden-term search rather than
  runtime behaviour is the gate — is unaffected and becomes G7.
- **#154 §12's gate table** is absorbed into §8 as G7–G14, with the registry supplying the oracle each
  row previously left implicit.
- **#156 §7's five secret tests and §10.4's renderer tests** land as G26 and G24 in the suite of §7.1.
- **#157's eight rulings** — two answered (§6, §12), six deferred with owners (§13).
- **Slice 0 gains G1–G6 and G27**; the registry must exist before any slice renames anything, or the
  rename has no oracle. **Slice 8's completion criteria change** per §11.3.
- **ADR-0005's `Rate.SELECTORS` invariant** (`apps/platform/tests/test_dimension_invariants.py:60`) is
  the closest existing thing to a registry check and #145 already removed its subject. It is
  **replaced** by G2/G3 against the registry, not merely deleted — the invariant it encodes ("a rate
  selector must exist as an event column") survives as a registry-backed check.

---

## 16. Residue, flagged not buried

- **The console has no localisation layer, and no slice owns building one.** §4.1 splits identity from
  expression; `apps/ui/src/lib/labels.ts` is currently both, at 337 lines with 35 `humanize` call
  sites across 52 importing files. This is real build work sitting in the same unassigned gap as
  #156 §14.1's `ResolvedCodePlan` endpoint, `ubb-codegen` and the builder page. Three pieces of
  unassigned work is a pattern, not an oversight, and the build plan should absorb them explicitly
  rather than discovering them at slice 5.
- **The registry has no owner and no maintenance cadence.** It is the same gap #156 §14.3 recorded for
  the response-shape registry and the advisory checker. A normative artifact that nobody owns drifts
  from normative to descriptive without anyone noticing, and the failure is silent because every gate
  still passes — against the stale declaration.
- **Every gate in §8 is a consistency check.** Not one of them can tell that a *correct* declaration is
  a *wrong* one. §2.4's sentence is the entire defence, and it lives in a document rather than in a
  gate, because by construction it cannot live in a gate.
- **`ubb-codegen`'s home is undecided** (#156 §14.4), which means §7.1's `renderers` layer has no
  settled location. If the renderer starts in the console repository, its tests either follow it out of
  this repository or test it across a boundary. Neither is decided.
- **Path filtering on the execution job is a correctness risk, not just an optimisation.** §7.3 lists
  six inputs the filter must include. A seventh input nobody thought of produces a gate that silently
  stops running — the same failure mode as `.gitignore`'s unanchored `lib/` dropping 22 modules for
  weeks (#135), and as the conformance job's `continue-on-error` making findings invisible. Prefer
  running it always until measurement proves the cost.
- **The acceptance audit has no named owner in this document**, only a role, because the repository
  holds no personnel data. Naming the accountable person is an act outside the repository, and
  ADR-0007 §5's whole point was that admission is *"a decision with a name on it."* The name has to
  land somewhere.
- **`indeterminate` survives one more round of scrutiny than its neighbours got.** §12.2 keeps it
  against ADR-0006 rule 2's pressure toward a single word for "not known". If a third
  evaluation-blocked state ever appears elsewhere in the system, the pair `unresolved` /
  `indeterminate` should be revisited as a general convention rather than extended by analogy.
- **The fuzzer's rename is recorded and unscheduled.** §7.4 establishes that `conformance/` cannot
  establish conformance. Leaving a misleading name in place while writing a document that depends on
  the distinction is a small debt, taken deliberately to avoid coupling this work to a rename.
