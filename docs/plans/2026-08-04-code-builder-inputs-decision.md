# Code Builder inputs — three questions, and everything else looked up

**Resolves:** [#156](https://github.com/ashcochrane/ubb/issues/156) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-04
**Decided against:** `main` @ `0cf00b5`
**Blocked by:** [#154](https://github.com/ashcochrane/ubb/issues/154) (the vocabulary lock) — closed;
ADR-0006 is on main and binds every name coined here.
**Blocks:** [#157](https://github.com/ashcochrane/ubb/issues/157) (Code Builder output).
**Builds on:**
`docs/plans/2026-07-29-event-type-entity-model-decision.md` (#138) — Provider and Event Type become
real entities.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — start carries an idempotency key, close
carries a required outcome.
`docs/plans/2026-07-30-task-lifecycle-placement-decision.md` (#141) — the whole lifecycle moves to
one ungated top-level `/tasks`.
`docs/plans/2026-07-30-measurement-vocabulary-decision.md` (#145) — Measurements are declared on the
Event Type; `source_path` is handed to this ticket by name.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — `costing_method` is declared on
the Event Type, never asserted per call.
`docs/plans/2026-07-31-pricing-versions-decision.md` (#148) — the Pricing Book Publish; schema
version separated from engine version.
`docs/plans/2026-07-31-streaming-and-long-running-calls-decision.md` (#149) — streaming struck, the
fast lane deleted, one reporting call site.
`docs/plans/2026-08-02-charging-modes-decision.md` (#151) — "charging mode" retired; the generator
reads exactly one of the three declarations.
`docs/adr/0006-domain-vocabulary-and-contract-naming.md` (#154) — R2 one canonical public term, R4 a
derived fact is never stored.
`docs/plans/2026-08-03-migration-and-cutover-decision.md` (#155) — eight slices; no provisional
public vocabulary; the operation-level SDK gate.
`docs/research/2026-07-29-code-builder-prior-art.md` (#144) — fifteen findings from sixteen vendors.
**Status:** decided. Planning only; implementation is out of scope for map #137.

---

## 0. The question, and the three things that moved it

The ticket asks what a tenant chooses in the Code Builder, what the platform must be able to
enumerate for them, and what mechanically decides whether a value is platform-known, configured once,
or supplied at runtime. It states a blocker: dimensions and task types are enumerable, but providers,
event types and measurable quantities are not.

**The blocker is real, and it is sharper than the ticket states.** It is not that a registry was
never built — it is that these four words are *structurally excluded* from the one registry that
exists. `RESERVED_KEYS = ("provider", "event_type", "task_type", "subtask_type")` is a module
constant (`apps/platform/dimensions/models.py:17`), and `DimensionService.declare` refuses any
attempt to declare one: *"a reserved dimension — always present, never declared"*
(`apps/platform/dimensions/services.py:23-25`). Because they never acquire a `DimensionDef` row, they
never acquire a `DimensionValue` ledger either, and the only value-enumeration contract in the system
guards on exactly that row: `GET /metering/dimensions/{key}/values` raises `not_found` unless a
`DimensionDef` exists (`api/v1/metering_endpoints.py:958-961`). **So `GET
/metering/dimensions/provider/values` returns 404 today, by construction, and always will under the
current model.** `metric_name` — the measurable quantity — is a bare `CharField(max_length=100)` on
the rate (`apps/metering/pricing/models.py:81`) with no registry of any kind.

**But every missing registry is already created by decisions this map has made.** #138 turns Provider
and Event Type into real entities. #145 declares Measurements *on* the Event Type with `value_type`,
`unit`, `required_for_costing` and `source_path`, and deletes the attribute-matching engine that made
free text load-bearing. Both land in #155's slice 2. **The blocker therefore dissolves as a
by-product of the re-model, and this ticket's real purpose is not to confirm that it does — it is to
state the read contract and find the parts the re-model does not hand us for free.** Those parts turn
out to be substantial, and §§3–5 and §10 are all of them.

**Three of the ticket's own candidate inputs are already dead.** The ticket's list asks whether a
tenant chooses "charging mode" — #151 retired both the phrase and any field that could claim to be
it, and ruled that the generator reads exactly one of the three surviving declarations, the Event
Type's costing method. It asks about "execution style (sync/async/streaming)" — #149 struck streaming
as a thing to model at all (the billable numbers arrive in the provider's final chunk, so a stream is
indistinguishable from an ordinary call at UBB's boundary) *and* deleted the asynchronous ingest lane
outright. **There is one execution style left, and no mode to choose.** A ticket charted before those
decisions cannot be answered from its own list.

**One more correction, small but load-bearing for §12.** The ticket describes the existing Developers
tab as holding "an API-basics card and a test-event console". It holds four sections and about 1,695
lines: API keys (268), sandbox (172), API basics (78), and the test-event console (328 + 135 + 146).

---

## 1. The input set — three universal questions, two conditional

**The governing rule: the builder never asks a tenant to re-enter a fact they have already
declared.** Asking again creates a second place the answer can be given, and this map has rejected
that shape four times — #148 §3.2 (two sources that must agree is promise B in a hat), #151 (no
combined `charging_mode` enum that could disagree with all three owners), #165 (the drawdown key must
not be re-keyed), #153 (five endpoints collapse because two were reimplementations).

### 1.1 The three universal questions

1. **Language / client.** Python SDK or raw HTTP/curl — map #137 constraint 6.
2. **Task kind.** Which declared kind of work this integration performs.
3. **Event Types.** Which provider operations happen inside it.

### 1.2 The two conditional questions

4. **Does this integration explicitly create Subtasks? If so, which registered Subtask kinds?**
   This is not optional politeness — it is forced by a ruling already made. #152's revision 2
   established declared Subtask kinds, *explicitly created* Subtask instances, and **observed**
   parent-kind composition, with the rule that **UBB must never infer a Subtask boundary** from event
   timing or provider calls, because *a guessed boundary would put spend enforcement on a structure
   the tenant never asserted*. The direct consequence for the generator: selecting
   `report_generation` does **not** tell it whether this integration creates `source_research` and
   `summarise` Subtasks. Nothing in the model can. So it must be asked.

   Events must remain valid attached **directly to the parent Task** — that is a first-class path,
   not a degenerate one, and the emitted code shows it as such.

5. **Where do the declared values come from in the provider response** — asked only where no mapping
   resolves. §§3–5 govern this entirely.

### 1.3 What is inferred, and from what

| Value | Inferred from |
|---|---|
| Provider | the selected Event Type owns it (#138) |
| Measurements, and which are required | declared on the Event Type (#145) |
| Costing method | declared on the Event Type (#146, #151) |
| Required Grouping Fields | `required_dimensions` on the Task kind |
| Task pricing mode | declared on the Task kind, pinned at start (#151) |
| Which call site a value lands at | the Grouping Field's declared `scope` |
| Lifecycle shape | fixed by the contract (#140, #141) |
| Spend-control response handling | fixed by the contract (#150) |

The danger this closes is concrete. If the Event Type declares `input_tokens` as required and the
builder asks *"which measurements should be sent?"*, a developer may answer `token_count` — a payload
that satisfies the builder and is silently uncostable, which is #145 §2.4's live defect arriving
through a new door.

### 1.4 What `scope` does and does not carry

Investigated and **rejected as a classification source.** `DimensionDef.scope ∈ {task, subtask,
event}` documents *"the level at which a dimension's value is CONSTANT (D6)"*
(`apps/platform/dimensions/models.py:12-13`), which reads like the configure-once/runtime axis. It is
not. A task-scoped value is constant *for one task*, bound at task start; an event-scoped one is sent
per call. **Both are runtime.** `scope` tells the generator **which call site a value is supplied
at** — `tasks.start(...)` versus `events.record(...)` — and is load-bearing for *placement*, not for
binding class. Recorded because the misreading is natural and would put runtime values into
interpolated literals.

---

## 2. The Resolved Contract — inference made visible, not silent

The objection to inferring seven facts is that inference is invisible: a developer who picks a Task
kind and receives Grouping Fields they did not expect has no way to see where they came from. **The
answer is not to ask again; it is to show where every inferred fact came from.**

Before rendering code, the builder shows a **read-only Resolved Contract**: Task kind and its pinned
pricing mode, required Grouping Fields, each selected Event Type with its provider, costing method,
declared measurements with type/unit/required flag, the declared response shape, and the inherited
COGS ceiling — **each labelled with the declaration it came from.** The emitted code carries the same
provenance in comments (`# Required because report_generation declares this Grouping Field.`).

This is the mechanism that makes a three-question builder safe. It is also the reason §9's read-only
boundary is affordable: the builder exists to *explain and reveal* the contract, and the Resolved
Contract is that purpose made concrete.

Per **ADR-0006 R4**, the Resolved Contract is **derived at read time and never stored** — the
identical treatment #151 gave `charging_summary`. If it ever acquires a stored column it has become
the second source this section exists to avoid.

---

## 3. Provider-response mapping — the tenant's declaration is authoritative; UBB may only warn

#145 §13 hands this ticket the mapping by name: *"the generator now has an enumerable contract per
Event Type, and `source_path` is its input for emitting the provider-response mapping."* Its §14
states the stakes: *"`source_path` is unvalidatable by UBB … The mapping is enforced by **code
generation, not validation** — which is an argument for … the Code Builder being the primary defence
against a correct-looking wrong mapping."*

The failure being defended against is #145's own: a developer declares `input_tokens` correctly, maps
it to the provider's **output** field, satisfies every check, and reports wrong COGS forever.

**Decision.** The tenant's declared mapping is the **sole source of truth**. UBB may hold tested
knowledge of provider response shapes and use it to **check and warn**. It may **never** generate
from its own knowledge, and may **never** silently substitute a path it believes is correct.

**Why generating from a UBB adapter was refused.** Under that model a stale UBB catalogue silently
produces incorrect COGS — the catalogue becomes commercially load-bearing. Under this one, a stale
checker can only fail to warn. **The blast radius of staleness is a missing warning, never a wrong
number.** It also keeps a UBB-shipped provider catalogue out of the money path, which map #137
constraint 5 exists to prevent.

**What a warning looks like.** Declared `usage_metadata.input_tokens` against shape
`google.genai.python.v1`, where UBB's tested shape has `usage_metadata.prompt_token_count`:

```
Measurement: input_tokens
Status: Suspect mapping — generated code may report the wrong quantity.
[Open input_tokens mapping]
```

Advisory, never blocking — UBB's catalogue may be stale, the tenant may use a wrapper, the provider
may have changed. This is the same instrument as #152's C′ dominance warning: arithmetic or
comparison over declared values, delivered at configuration time, never refusing.

A **missing required mapping is different from a disagreement**: the builder cannot produce complete
code without it, which §8 handles as a readiness state rather than a refusal.

---

## 4. `source_kind` — the mandatory rule, corrected

#145 §14 proposed making `source_path` mandatory *"on any Measurement whose Event Type has a
Provider"*. **That is too broad.** A measurement may legitimately be computed by the tenant before
reporting, taken from somewhere other than the provider response, be a constant or contextual value,
or be derived from several provider fields. A blanket rule would force a fictitious path on all of
them.

**Decision — a fifth attribute on the Measurement, beyond #145's four:**

```
source_kind ∈ { provider_response, caller_supplied, derived, constant }
```

| `source_kind` | Obligation |
|---|---|
| `provider_response` | `source_path` **required** |
| `caller_supplied` | `source_path` not applicable |
| `derived` | declared transformation, or explicit caller responsibility |
| `constant` | declared value |

This gives the generator a precise contract without assuming every measurement is a direct property
lookup, and it makes the mandatory rule state its actual precondition rather than a proxy for it.

---

## 5. `source_shape_id` and the structured path — the renderer may change syntax, never names

### 5.1 The trap

Google's REST response carries `usageMetadata.promptTokenCount`; its Python SDK object carries
`usage_metadata.prompt_token_count`. Same number, same provider, **different names**. A single
canonical path cannot be rendered into both without UBB knowing how to *rename* keys — which is
precisely the adapter §3 just refused to make load-bearing.

**The governing rule: the renderer may change access syntax, but it must never translate, rename or
guess field names.**

Within a declared shape, this is legitimate rendering:

```
segments: ["usage_metadata", "prompt_token_count"]
  → response.usage_metadata.prompt_token_count
  → response["usage_metadata"]["prompt_token_count"]
```

This is **not** rendering, and is prohibited:

```
usageMetadata.promptTokenCount  →  usage_metadata.prompt_token_count
```

That is provider/client-shape knowledge, and performing it would make UBB's catalogue commercially
load-bearing by the back door.

### 5.2 The path is structured data, not code

`source_path` stores **canonical segments** (`["usage_metadata", "prompt_token_count"]`), never an
executable, language-specific expression. A stored string like `response.usage.input_tokens` is
Python source in a database column; the builder targets more than one language, and a raw expression
is not portable across them.

### 5.3 The shape identifier

Free text was rejected: `google-python`, `Google Python SDK`, `gemini_py` and `google_genai` would
all be distinct values and the advisory checker would have nothing stable to match. A hard database
enum was also rejected: every new provider SDK or materially changed response shape would require a
schema migration.

**Decision — a stable, namespaced identifier validated against an extensible response-shape
registry**, additive rather than a closed enum:

```
google.gemini.rest.v1
google.genai.python.v1
openai.responses.python.v1
custom
```

With `custom`, the tenant supplies `source_shape_label` (e.g. `acme-gemini-wrapper-v2`); UBB
generates from the declared path and performs **no** shape validation.

**The shape is declared once, at the Event Type mapping level** — not repeated on every Measurement,
where copies could disagree. Measurements carry their own paths beneath it. Genuinely mixed sources
are already expressible through §4's `source_kind`.

### 5.4 Client mismatch refuses to claim completeness

If the declared shape is `google.genai.python.v1` and the builder target is raw curl, the builder
does **not** translate and does **not** emit plausible-looking code. It states that no compatible
mapping exists and asks for one to be added. **Emitting something that looks right is worse than
emitting nothing**, which is the research's finding 8: Paddle's copy-paste-clean, silently-wrong
token repeated 28 times on one page.

**A stated product consequence, not an objection:** this makes the language choice and the Event Type
choice capable of conflicting. A tenant integrating via curl whose Event Types are declared against a
Python SDK shape gets incomplete output everywhere, which will push tenants toward declaring against
raw REST. That is a real pressure created by this rule and is recorded so it is not later discovered
as a surprise.

### 5.5 v1 limitation, and its named extension

**One active provider-response shape per Event Type in v1.** Recorded explicitly as a simplification.
If tenants later need one Event Type through several clients, the extension is **sparse mapping
profiles** under the Event Type — only the profiles a tenant actually uses need exist — **never a
duplicated Event Type**, which would fork a money-bearing declaration to solve a rendering problem.

### 5.6 Publication

Because an incorrect mapping produces incorrect COGS, `source_shape_id` and `source_path` belong to
the **published** Event Type contract. Drafts may hold incomplete or edited mappings; publication
pins them. Changing SDK or response shape is **a revised mapping, published** — never a silent
reinterpretation of code already generated and deployed.

---

## 6. The classification rule — three ordered questions

The ticket requires a rule that is *derivable, not hand-authored per template*.

```
1. Can UBB resolve this value now, from this tenant's own published configuration?
     No  → runtime_bound.   The declared scope decides which call site it lands at.
2. Yes — is it on the central withhold list?
     Yes → secret_reference. Emit an environment / secret-manager lookup.
3. Otherwise
         → platform_known.  Interpolate the literal.
```

| Class | Members |
|---|---|
| `platform_known` | task kind key, subtask kind key, event type key, measurement names, grouping-field keys, costing method, `source_shape_id`, `source_path` segments |
| `runtime_bound` | customer id, idempotency key, grouping-field **values**, provider-response object, measurement **values**, provider-reported cost, outcome |
| `secret_reference` | UBB API credential, provider credential where the integration uses one, webhook signing secret |

### 6.1 Classification is per token, not per statement

One line of emitted code routinely contains two classes:

```python
grouping_fields={
    "environment": environment,       # key: platform_known · value: runtime_bound
}
measurements={
    "input_tokens": response.usage_metadata.prompt_token_count,
}                                     # name: platform_known · expression: runtime_bound
```

`"input_tokens"` is a declared Measurement name; the expression beside it reads runtime provider
data. **The key/value split must stay explicit**, and it is a direct constraint on how #157 renders
the three classes — a per-line highlight cannot express it.

### 6.2 Class 2 is a policy, not a derivation — and saying so is the point

**A credential is not unknown and not runtime. UBB may know it, and deliberately refuses to embed it
in generated source.** Class 2 is therefore properly understood as a **small, centrally enforced
withholding policy carved out of `platform_known`** — not a naturally derived category.

Deriving it from something like "constant for this deployment" was rejected because that blurs
security policy with binding time. The research is explicit that this is *"a security decision, not a
research finding"*: Stripe injects a shared sandbox key that works, Clerk injects your real one,
Twilio and Supabase-in-code refuse and use environment variables. Making the withheld set short,
central and named makes that decision visible and reviewable instead of smeared across templates.

**A canonical API base URL is not a secret.** It may be emitted as a default literal while remaining
overridable through client configuration. It does not join the withhold list merely because it varies
between environments.

---

## 7. No generated artifact ever contains a real secret

The builder emits the **name**, never the value:

```python
api_key = os.environ["UBB_API_KEY"]
```

and may generate `.env.example` with an empty assignment. It **does not** generate a downloadable or
copyable file containing the real credential. The console may offer a secure copy or secret-management
flow separately; the *code artifact* carries only the variable name and setup instructions.

This is deliberately **stricter than the prior art**. Supabase's Connect sheet — the pattern this
document otherwise borrows from — puts real values in its `.env` tab. For a file whose entire purpose
is to be downloaded, stricter is right.

**Five mechanical tests** are owed, and the policy is defined once rather than repeated per template:

1. no secret value appears in generated source;
2. no secret value appears in fixtures or snapshots;
3. every secret reference carries setup instructions;
4. every non-secret platform-known value renders consistently;
5. every runtime value lands at its declared scope.

---

## 8. Empty state — resolution status and artifact readiness are two different axes

A brand-new tenant has empty registries. The builder **never refuses, and never fabricates tenant
vocabulary.**

### 8.1 Two axes

An unconfigured platform-known value keeps its class and gains a status:

```
binding_class:     platform_known
resolution_status: missing_configuration
```

**It is not a fourth class.** Source and eventual resolution path are unchanged; the tenant creates
the declaration and the same token resolves normally. Keeping it a state means templates branch three
ways, not four, and §6's rule stays three questions. This is the **fifth** application of a pattern
this map has now ruled on four times: #147 §7.1 (waived versus free zero), #151 §8
(`not_applicable_reason`), #153 §3.4 (unknown versus zero revenue), #165 (`measurements_status`,
volunteered unasked).

Separately, the **artifact** carries a readiness verdict:

| Verdict | Meaning |
|---|---|
| `scaffold` | configuration is missing and some code structure cannot yet be determined |
| `incomplete` | structure is known; required mappings or values remain unresolved |
| `complete` | every required declaration and mapping resolves |

Readiness sharpens progressively: no Task/Event Type → `scaffold`; both declared but mappings missing
→ `incomplete`; all published → `complete`.

### 8.2 Never invent tenant vocabulary

A worked example built on UBB-invented values — a plausible `openai-gpt4` with `input_tokens` and
`output_tokens` — was **refused**. It is map #137 constraint 5 arriving through the back door, and it
produces the worst failure the research found: code that is copy-paste clean and silently wrong.
Plausible names survive copying and become accidental production configuration. Labels do not survive
copying: finding 6 verifies three separate products strip their own guidance on copy (Lago's
`ignoreComment: true`, Helicone's diff-free string, AWS marking replaceable values in CSS only), so
**only the tokens survive**.

### 8.3 Fail fast with a precise message, not a fatal-looking token

Lago and Flexprice independently converged on the literal `__MUST_BE_DEFINED__`, and the research
calls that convergence its strongest design signal. **It is nevertheless rejected here**, for a
reason the research did not test: it is *valid Python syntax* and yields only a generic `NameError`,
and only if execution happens to reach it.

Instead the builder emits a generated helper that fails immediately and says what is missing:

```python
def required_configuration(name: str):
    raise RuntimeError(
        f"UBB Code Builder scaffold is incomplete: configure {name}."
    )
```

with language-native equivalents — `requiredConfiguration("Event Type")` throwing in TypeScript,
`: "${UBB_EVENT_TYPE:?Configure an Event Type in UBB}"` in shell. **The aim is not malformed code. It
is valid code that fails immediately and explains exactly what is missing.**

### 8.4 The verdict travels with the code

Because console labels are lost on copy, the verdict and its remediation list are emitted **in the
source header**, not only on screen:

```python
# UBB CODE BUILDER STATUS: SCAFFOLD — NOT READY TO RUN
# Missing configuration:
# - Task Type
# - Event Type
# Complete these declarations and regenerate this code.
```

The action is labelled **"Copy scaffold"**, not "Copy integration", until the verdict is `complete`.

---

## 9. The builder reads; only the owning surface writes

**Decision: strictly read-and-generate. The Code Builder never creates, edits or publishes tenant
configuration.**

| May | May not |
|---|---|
| inspect published configuration | create Task Types |
| resolve the generated contract | create Event Types |
| detect missing or suspect mappings | declare Measurements |
| explain why code is incomplete | edit source paths |
| deep-link to the exact configuration field | revise a published Event Type |
| refresh after configuration changes | publish money-bearing configuration |

**This holds even when the current user is an admin. Permissions alone do not change the product
boundary: generating integration code must not have a hidden side effect of changing the economic
contract it exists to implement.**

**The supporting code evidence.** Reading the registries is READ-floored; declaring into them is
ADMIN-floored — `list_dimensions` (`api/v1/metering_endpoints.py:943`) and `list_task_types`
(`:1014`) against `declare_dimensions` (`:910`) and `declare_task_types` (`:968`) — and the admin
comment states the reason: *"a task type's ceiling prices usage the same way markup.set and
rate_card.* do"*. The audiences differ. A writing builder either forces ADMIN on the whole surface,
locking out the developers it exists for, or ships a screen where half the controls are dead for most
users and the core experience depends on permissions.

**The mapping carve-out was considered and declined.** Letting the builder edit only `source_path`
looks small, but §5.6 makes that field part of the published contract, so the carve-out means a
code-generation screen can trigger a publish of a money-bearing contract — #140's *"the forgiving path
must never be the money path"* arriving in a new place. It would drag publication lifecycle controls,
audit behaviour and ADMIN permissions onto the builder, making it a second, incomplete configuration
editor.

**What is kept from it costs nothing:** the builder detects and reports a suspect mapping and links
to the exact owning field. #145's *"primary defence against a correct-looking wrong mapping"* is
preserved in full, because the defence is **noticing**, not **editing**.

### 9.1 The round trip is made cheap by navigation, not by merging permissions

1. Builder detects missing or suspect configuration and names the owning object.
2. User opens the configuration surface (new tab, drawer or routed page).
3. An ADMIN edits and publishes.
4. Returning preserves language, Task kind, Event Types and Subtask selections.
5. The builder refreshes the resolved plan and regenerates automatically.

Where the developer lacks permission: *"This field must be changed by a tenant admin"*, with **Copy
configuration request** and **Copy link for an admin** — the copied request identifying the exact
Event Type, Measurement and problem rather than making the developer explain it.

### 9.2 Published by default, draft preview explicit

Production code resolves against **published** configuration. A **draft preview** may be selected
explicitly, labelled *"Draft preview — not production-ready"*, and remains **read-only from the
builder**. An admin can see how proposed configuration would render without the builder being able to
mutate or publish it.

**Governing rule:** *the Code Builder may explain and reveal the contract, but only the owning
configuration surface may change it.*

---

## 10. Architecture — the server decides meaning, the renderer decides expression

**Decision: the server resolves and issues a typed, versioned `ResolvedCodePlan`; one shared,
versioned `ubb-codegen` package renders it into Python, curl (and later other targets).**

### 10.1 The boundary

Server-authoritative — domain and security decisions that must not be reconstructed in a browser:
published Task and Subtask kinds, selected Event Types, costing methods, required Measurements,
required Grouping Fields, provider-response mappings, binding classes, secret-withholding decisions,
artifact readiness, missing configuration, warnings and diagnostics.

Renderer-owned — presentation: imports, keyword-argument formatting, `with`-block versus explicit
close, curl line breaks, comment placement, variable naming, SDK convenience-method names.

```json
{
  "schema_version": 1,
  "artifact_status": "complete",
  "target": { "language": "python", "client": "ubb-sdk", "major_version": 4 },
  "operations": [
    { "operation_id": "tasks_start",
      "arguments": [
        { "name": "task_type",   "binding_class": "platform_known",  "value": "report_generation" },
        { "name": "customer_id", "binding_class": "runtime_bound",   "identifier": "customer_id" },
        { "name": "api_key",     "binding_class": "secret_reference","environment_variable": "UBB_API_KEY" }
      ] }
  ],
  "diagnostics": []
}
```

The renderer **cannot** decide that a runtime value is a literal, that a credential may be embedded,
or that one provider field should replace another. Those decisions are already made in the
server-issued plan. Its type system accepts only a `SecretReference`, never an arbitrary string, so
**a secret literal is unrepresentable rather than merely forbidden.**

### 10.2 Why not fully server-side rendering

Rendering the final Python on the server was considered and **rejected on coupling**. It would make
`ubb-platform` depend on the hand-written SDK's evolving ergonomic surface: an SDK wrapper rename
forces platform template changes, and an independently released SDK version means the platform may
emit code for the wrong one.

**The deciding argument, which corrects an over-reliance on an existing gate:** #155's operation-level
two-way gate can prove that an SDK operation resolves to a real API operation. **It cannot prove that
a server-owned snippet uses the current SDK API, imports the right objects, or follows current
lifecycle conventions.** The gate covers reachability, not ergonomics.

Fully server-side rendering becomes appropriate later *if* code generation becomes a standalone
platform capability consumed by many thin clients — and even then as an isolated code-generation
module consuming this same plan, never as ordinary platform services importing SDK internals. For v1
it creates coupling before there is evidence the capability is needed publicly.

### 10.3 Why not browser-side resolution

Asking the browser to read raw registries and reconstruct the contract would duplicate resolution
ladders, published-versus-draft selection, source-mapping rules, readiness classification, the secret
policy and diagnostics — making the console a second implementation of business rules, and one that
cannot be reused safely elsewhere. It would also satisfy §7's *"central and mechanically tested"*
requirement for the console only.

### 10.4 One renderer package, many consumers

The weak form of this split — bespoke templates scattered through the frontend — is **rejected for
the same drift reason**. `ubb-codegen` is isolated, versioned and free of UI dependencies; the console
consumes it today, and a future CLI, documentation generator or coding-agent surface consumes the
same package and the same plan. This is the research's transfer 5: Langfuse serves docs and console
from **one function**, and Clerk is the counterexample of what happens otherwise. The package may
initially live in the console repository if that is operationally easiest.

Tests sit on **both** sides: server tests that no plan contains a secret value, that classifications
and the readiness verdict are correct; renderer tests that secret references become environment
lookups, runtime values stay runtime expressions, platform literals are escaped correctly, and
incomplete plans produce fail-fast scaffolds.

### 10.5 Two contract consequences

`ResolvedCodePlan` is a public response, so **#155's no-provisional-public-vocabulary rule binds its
field names on day one** — they ship final or they break the contract later. And `schema_version` is
the **second application of #148's split** between "which shape is this, so I can parse it" and
"which code produced it".

---

## 11. The read contracts — what exists, what is missing, what is new

| Input | Contract | State |
|---|---|---|
| Task kinds, Subtask kinds, ceilings, `required_dimensions` | `GET /metering/task-types` | **exists** (`:1013`); `kind ∈ {task, subtask}` already present |
| Grouping Fields and their scope | `GET /metering/dimensions` | **exists** (`:942`); `GroupingFieldDef` after #154's rename |
| Grouping Field values | `GET /metering/dimensions/{key}/values` | **exists** (`:951`); reserved keys 404 by construction |
| Providers | — | **missing**; created by #138 in slice 2 |
| Event Types, costing method, Measurements | — | **missing**; created by #138/#145 in slice 2 |
| `source_kind` | — | **new here** (§4); beyond #145's four attributes |
| `source_shape_id`, structured `source_path`, shape registry | — | **new here** (§5) |
| Event Type draft / published state | — | **new here** (§5.6) |
| Tenant posture | derived, served read-only | #154 |
| `ResolvedCodePlan` | — | **new here** (§10) |

**No new endpoint restates registry facts.** The plan **resolves**; it does not duplicate. That
distinction is what keeps §10 from being the second-source shape this map has rejected four times,
and it is enforced by ADR-0006 R4 — the resolution is derived at read time and never stored.

---

## 12. Placement — a dedicated route under Developers

**Decision: `/developers/code-builder`.** Not a thirteenth top-level nav item, and not a fifth inline
card.

The route is justified by the builder being a **substantial workflow**, not merely by state
preservation — though it delivers deep-linking, browser history, refresh recovery and a stable return
target after configuration changes. The page holds language and client selection, Task-kind and
Event-Type selection, optional Subtask selection, the Resolved Contract, the readiness verdict,
diagnostics, generated files and per-call-site blocks, copy/download actions, and verification.
Builder state is encoded via an opaque saved-state identifier or safe URL parameters; **secrets and
tenant-sensitive values never appear in the URL.**

Nav is ten items today (`apps/ui/src/components/shared/nav-config.ts`) and #152 already proposes two
more. A dedicated route under the existing Developers entry keeps navigation under control while
giving the capability first-class behaviour. Promoting it to top-level later is a presentation change,
not an architectural one, because it already owns a stable route. The Developers overview links to it
prominently rather than burying it.

### 12.1 API basics is absorbed as a designed onboarding state

The current API-basics card must not survive as a **second hand-written integration example** — it
would duplicate the builder and drift. The console already demonstrates the failure: two placeholder
conventions live **eight lines apart in one file**, `Bearer ubb_test_YOUR_SANDBOX_KEY`
(`apps/ui/src/features/developers/lib/test-event.ts:138`) and `Bearer
ubb_live_xxxxxxxxxxxxxxxxxxxxxxxx` (`:146`). **Under §7 both are now wrong**, so that file changes
regardless of placement.

"Absorbed" means its beginner purpose is **preserved deliberately**, not left to whatever an empty
builder happens to render. A new tenant sees an explicit API-basics scaffold teaching the minimum
lifecycle — authenticate, start a Task, record an event, complete the Task — labelled *"Scaffold — not
ready to run"* and naming exactly what must be configured. That replaces the old card with a better
single source rather than deleting introductory guidance.

### 12.2 The test-event console relocates, and stays conceptually separate

It moves onto the builder page, giving the workflow **Configure → Review resolved contract → Generate
→ Verify**. This closes a gap the research found across the entire market: finding 15 records that at
Chargebee, Paddle, Moesif, m3ter, Auth0 and Supabase alike, the snippet and the proof it worked live
on different screens. We already own both halves.

Verification stays a **distinct stage, never fused into the renderer**. It may use the builder's
current selections; it must not silently change configuration or generated code. It states whether it
is testing against sandbox, published configuration or an explicitly supported draft preview, and it
never embeds real credentials into copied artifacts.

**Final shape:**

```
Developers overview          /developers/code-builder
  API Keys                     Setup
  Sandbox                      Resolved Contract
  Code Builder card            Diagnostics
  developer settings           Generated Code
                               Verify
```

---

## 13. What this constrains

- **#157 (Code Builder output)** — inherits the plan/renderer split (§10), per-token classification
  (§6.1), the three readiness states and fail-fast helpers (§8), the verdict in the source header
  (§8.4), separately-copyable per-call-site blocks, and the verify stage's placement (§12.2). Its open
  questions on the stop-branch shape and whether the webhook handler is emitted are **not** answered
  here.
- **#158 (audit method)** — gains concrete targets: the five secret tests plus the renderer tests
  (§7, §10.4), and *"every emitted path corresponds to a real contract"* now means every
  `operation_id` in a plan resolves to a real spec operation, composing with #155's operation-level
  gate.
- **#155 (migration and cutover)** — slice 2 gains `source_kind`, `source_shape_id`, the structured
  path, the response-shape registry and Event Type draft/published. The `ResolvedCodePlan` endpoint,
  `ubb-codegen` and the builder page are **new build work with no slice assigned** (§14).
- **#152 (console)** — adds a surface its prototype did not draw, and confirms that config is
  distributed while the builder is centralised.
- **#145** — extended by `source_kind` (§4) and by structured paths (§5.2); its §14 mandatory-path
  proposal is **narrowed**, not adopted.
- **#151** — confirmed: the generator reads exactly one of the three declarations. The builder never
  shows customer prices.

---

## 14. Residue, flagged not buried

1. **#155's eight slices contain no Code Builder.** Slices 0–8 are gates+money, demolition,
   measurement & catalogue, cost, price, work, spend control, analytics, cutover. The
   `ResolvedCodePlan` endpoint, `ubb-codegen` and the builder page are real build work with **no slice
   assigned**. A gap in a merged build plan, recorded here because this is the ticket that created the
   work.
2. **A second publish mechanism now exists.** #148 created an immutable Pricing Book Publish record;
   §5.6 puts draft-versus-published on the Event Type. Whether that is the same mechanism generalised
   or a second one is **undecided**. #151's residue that Task Types have no publish equivalent is
   **narrowed, not closed** — Event Types now have one and Task Types still do not.
3. **The response-shape registry and the advisory checker have no owner and no staleness policy.**
   Both are UBB-shipped datasets. They are a **deliberate, bounded exception to map #137 constraint
   5** — a namespace and a warning, never commercially load-bearing, with `custom` as the escape hatch
   — and that reconciliation is written down here precisely so a later reader does not find a vendor
   catalogue and conclude the rule was broken. Who maintains them, and on what cadence, is open.
4. **`ubb-codegen`'s home is undecided** — it may start in the console repository if operationally
   easiest, provided it is isolated, versioned and free of UI dependencies.
5. **Draft-preview visibility is unspecified** — presumably ADMIN, but no floor is decided.
6. **TypeScript appears as a later renderer target.** Consistent with map #137 constraint 6 (Python
   SDK and raw HTTP only for v1), recorded so the renderer sketch is not read as scope creep.
7. **The saved-state identifier for builder state is undesigned** — only the constraint that secrets
   and tenant-sensitive values never appear in the URL is decided.
