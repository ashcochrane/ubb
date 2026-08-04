# Code Builder output — prototype notes (#157)

**Status:** revision 1 — ready to react to. A prototype: **not a specification.**
**Artifact:** [`2026-08-04-code-builder-output/`](./2026-08-04-code-builder-output/) — start at
`README.md`, then `python/ubb_integration.py`.
**Built against:** `main` @ `d60d86f`, rendering decisions #138–#156 and #165.
**Blocked by:** #156 (Code Builder inputs) — decided and merged, and this prototype inherits the
plan/renderer split (§10), per-token classification (§6.1), the three readiness states and fail-fast
helpers (§8), the verdict in the source header (§8.4), separately-copyable per-call-site blocks, and
the verify stage (§12.2).

Issue [#157](https://github.com/ashcochrane/ubb/issues/157) is a `wayfinder:prototype` ticket: *produce
a rough worked example — real generated output for one plausible tenant configuration, in Python and
in raw HTTP — and react to it. Do not build the generator.* These notes are the reading companion.

---

## 1. Three premises in the ticket that no longer hold

The ticket was charted on 2026-07-29. Eleven decisions have landed since, and three of its framings
were overtaken. None of this is a criticism of the charting — it is the same effect #156 §0 recorded,
and it has to be said before the artifact makes sense.

**1. It is not four call sites. It is three, plus a branch.**
The ticket says *"start, report, complete and handle-stop is four call sites"*. Handle-stop is not a
call site: the stop rides fields on the ack of the report call (#150 §1), so it is a branch inside
call site 2. #149 §6 collapsed reporting to one call site, #140 gave close its required outcome, and
#141 put the whole lifecycle in one ungated namespace. **The taught surface is start, record, close —
plus one branch, plus a conditional second instance of start/close for Subtasks.** That is a
materially easier thing to teach than the ticket assumed, and it changes the artifact's shape.

**2. The three value classes are not the ones the ticket names.**
The ticket asks how *"platform-known / configure-once / runtime"* are distinguished. #156 §6 decided a
different trio — `platform_known` / `runtime_bound` / `secret_reference` — and §1.4 specifically
investigated and **rejected** "configure-once": `DimensionDef.scope` reads like that axis but a
task-scoped value is bound at task start, so **both scopes are runtime**, and scope decides *which
call site a value lands at*, not what class it is. Rendering the ticket's trio would render a model
that no longer exists. The artifact renders the decided one.

**3. "Generated from `openapi/v1.json`, or hand-maintained templates?" is a false binary, and #156
already answered the architecture.** What is left for this ticket is that **drift has three axes and
the spec covers exactly one of them** — §3.7 below.

---

## 2. Seven questions, seven positions

| # | The ticket asks | Position |
|---|---|---|
| 1 | What is the artifact? | **One generated module + an empty `.env.example`**, plus per-call-site blocks that contain **zero generated values** |
| 2 | How is "why this line exists" conveyed? | **Inline comments only, in two strictly separated classes** — provenance (from the plan) and contract (a closed catalogue owned by the renderer). No third class |
| 3 | How are the three classes distinguished so they survive the clipboard? | **Structurally, not typographically.** Literal / required parameter / `os.environ[...]`. No markers, no tokens, nothing to substitute |
| 4 | How much lifecycle at once? | **All of it in the module; none of it in the call-site blocks.** And it is three call sites, not four |
| 5 | Error and stop handling | Python: `raise_on_stop=True`, **always emitted**, caught **once around the whole unit of work**. Shell: an explicit field read and a non-zero return. The two targets genuinely differ here |
| 6 | The verify stage | **Both, and they prove different things.** Only the emitted script can prove the provider-response mapping — and it is also what defends the stop branch from deletion |
| 7 | Drift | **Three mechanisms for three axes.** The spec covers one; the plan covers one; only `ubb-codegen` can cover the third |

Two more, which #156 §13 explicitly left open for this ticket:

| | | |
|---|---|---|
| 8 | The stop-branch shape | Answered in §3.5 |
| 9 | Is a webhook handler emitted? | **No.** §3.8 |

---

## 3. The positions in detail

### 3.1 The artifact is a module, and the rule that produces that answer

The four candidate shapes in the ticket are a single annotated file, a walkthrough with code per stage, a
downloadable project, and a diff to paste. The artifact is **a module you drop in and never edit**,
plus **call-site blocks that go in code you do edit**.

What decides it is not taste, it is one requirement: **regeneration must be a file replace.** Your
configuration changes far more often than your application structure does — a republished Event Type,
a new Measurement, a changed ceiling — and every one of those must be absorbable without a developer
reading a diff of their own business logic. That is only possible if the generated content is
entirely inside one file.

From which the load-bearing renderer rule falls out, and it is testable:

> **No generated value may appear in a call-site block.** No Task kind, no Event Type, no measurement
> name, no path into a provider response, no ceiling. If a value came from the plan, it lives in the
> module.

`CALL-SITES.md` holds to that: every block is imports, parameters the developer already has, and
control flow. Compare a walkthrough — which puts generated values into prose stages that are copied
once and then rot — or a diff, which is unusable the second the developer's file differs from the one
the diff was cut against.

**What this costs, stated.** The developer gets a layer of indirection they did not ask for, and one
more file in their repository. That is a real cost and it is worth paying only because the
alternative is asking them to re-integrate on every configuration change.

### 3.2 Comments are the product, and they need a grammar

The ticket is right that *"comments in emitted code are the cheapest thing to get wrong"*. The
research is right that they die at the clipboard when the console strips them (#144 finding 3, three
vendors verified). Both are true and they point the same way: **the explanation must be in the copied
text, and it must be generated rather than written.**

Two classes, and no third:

- **Provenance comments** — machine-generated from the plan, one grammatical form: *what this value
  is, which declaration it came from, and when that declaration was published.*
  `# int · tokens · declared at usage.input_tokens`
- **Contract comments** — fixed prose owned by `ubb-codegen`, versioned with it, **identical for
  every tenant**, drawn from a closed catalogue. The explanation of what `reported` costing means; the
  explanation of why the stop is not an error.

The rule that makes this testable, and it is the whole point:

> **No comment may assert a fact the plan does not carry, and no comment may be hand-written per
> template.** A renderer test asserts every emitted comment line either matches a provenance form or
> is a member of the catalogue.

That forbids the failure this is guarding against: a template author writing *"your provider returns
token counts here"*, which is provider knowledge arriving by the back door (#156 §3) in the one place
nobody checks it.

**No prose between blocks, and no collapsible explanations.** Both are console furniture and neither
survives a copy. Everything in the artifact is either code or a comment attached to code.

### 3.3 Three classes, three shapes — and the clipboard becomes irrelevant

This is the ticket's hardest question and the answer is not a marker.

| Class | Rendered as | Why it cannot be got wrong |
|---|---|---|
| `platform_known` | a literal — `"report_generation"` | It is already the value. There is nothing to substitute |
| `runtime_bound` | a **required** parameter — `customer_id` | Omit it and Python raises `TypeError` **at the call**. Never a wrong number later |
| `secret_reference` | `os.environ["UBB_API_KEY"]` | There is no literal to leak, because a literal was never emitted |

Lago and Flexprice independently converged on `__MUST_BE_DEFINED__` and `__SCREAMING_SNAKE__`, which
#144 rates as its strongest single design signal. #156 §8.3 already rejected the first for being valid
Python that fails late and vaguely. **This prototype rejects the second too, for a different reason:
a token is still something you have to find and replace, and forgetting one is silent.** A required
parameter is enforced by the language.

The per-token requirement (#156 §6.1) then costs nothing, because the classes are *shapes* rather
than *decorations*:

```python
"environment": environment
 |              |
 |              this run's value, supplied by you
 the field name you declared to UBB
```

A per-line highlight cannot express that. Two different shapes on one line can.

**The wrinkle, and it is real.** `missing_configuration` is a *state* of `platform_known`, not a
fourth class (#156 §8.1) — but it renders as a fourth shape, a `required_configuration(...)` call. A
reader of the emitted file will reasonably read four kinds of thing. Mitigated by the header legend
naming three shapes and describing the fourth as a state, but it is a genuine seam between the model
and its rendering.

**And a second, in the shell target.** `${VAR:?message}` is the right analogue — it is that language's
"you must supply this" construct — but it *exits the shell*, not the function. Sourcing the file
interactively and calling a function with a variable unset closes the terminal. Blunter than a
`TypeError`, accepted, recorded.

### 3.4 All the lifecycle, in one place, because the four call sites are not four

The ticket worries that *"a single linear snippet may misrepresent"* four call sites in different parts
of an application. Correct — and the artifact resolves it by putting **the whole lifecycle in the
module**, where it reads top to bottom as one narrative, and **none of it in the call sites**, which
are one to three lines each.

The module reads in the order the work happens: start · record · Subtask · close. Nothing is elided,
including the paths a given tenant will not use — because the alternative is a developer discovering
at 2am that closing needed an argument nobody showed them.

**One rule this forced, and it is the best thing in the prototype.** The `with` block has to decide
what to do when it exits. It closes as `failed` on an exception, and on a clean exit that declared
nothing it **raises** and leaves the Task to expire.

> **Generated code may infer the outcome that costs nothing. It may never infer the one that charges.**

That is #140's *"the forgiving path must never be the money path"* arriving at the call site. A
context manager that closed as `delivered` on a clean exit would be the obvious, friendly, idiomatic
thing to generate — and under a Task kind priced as a whole it would manufacture revenue from a
`return` statement.

### 3.5 The stop is control flow, and it is the one keyword you must not delete

The brief is exact: *"the stop instruction rides response fields, never an HTTP error — the generated
code must make that idiomatic rather than a footnote."*

**Python: `raise_on_stop=True`, always emitted, caught once around the whole unit of work.**
Not per record call, because `stop.scope` may be `customer` and no individual record call knows what
else that customer has running. `CALL-SITES.md` block 3 says so in the copied text: *"This is not
error handling. Every call in block 2 succeeded."*

**Shell: an explicit read of `.stop.requested` on a response already known to have succeeded, and a
non-zero return.** There is no exception mechanism to lean on. This is the one place the two targets
differ in **shape** rather than in syntax, and the artifact says so in both files rather than hiding it.

**The honest weakness.** `raise_on_stop=True` is one keyword and deleting it is a two-character edit
that fails nothing. The defence is not typographic — it is §3.6: the generated verify script drives a
sandbox Task past its ceiling and asserts the exception arrives. Delete the keyword and a test the
developer already runs goes red. That is the only mechanism here that actually binds.

**Failures are three different things and the artifact separates them:** transport failures (the SDK
retries, and the emitted code does not re-implement it), contract refusals (`409` on a replayed start
with different pinned fields — never retry it, and the comment says what it means), and the stop
(a 200 that means stop).

### 3.6 Verification is both halves, and only one of them can prove the mapping

The ticket asks whether the verify stage is emitted code, a console affordance, or both. **Both — and
they answer different questions, which is why neither replaces the other.**

The console stage (#156 §12.2) proves *the event landed and what UBB made of it*: cost, statuses,
ceiling. It closes the market-wide gap #144 finding 15 found.

The emitted `verify_integration.py` proves *the mapping*, and **nothing else can**. #145 §14 is
explicit that `source_path` is unvalidatable by UBB because UBB never sees the provider response, and
that the defence is code generation rather than validation. The generated script closes that by taking
a **real captured provider response** and asserting the declared paths resolve in it — including two
checks a human would not write: that no measurement reads a constant zero, and that two measurements
do not read the same field. Those two are the signature of a path pointing at the wrong number, which
is #145's canonical failure.

It also refuses to run without a `ubb_test_` key, because it deliberately drives a Task past its
ceiling.

**Not proposed, but worth a ruling.** #144 rates Lago's `POST /events/estimate_fees` — computed fees
returned **without persisting the event** — the highest-value verify surface it found anywhere, and
notes almost nobody has it. We have the compute spine (#149 §6.3: the price *is* the price). A
non-persisting "what would this cost" call would let the verify script check the *number* and not just
the plumbing. It is out of scope here, it needs a name that is not "estimate" (retired by ADR-0006),
and it is a product decision rather than a rendering one.

### 3.7 Drift has three axes and `openapi/v1.json` covers one

#144 finding 6 established that generating the builder from the spec cannot work: codegen covers
response DTOs in `ubb-sdk/ubb/_core/` only, and the call surface is ~2,425 lines of hand-written httpx.
That is right, and it is a third of the answer.

| What drifts | Held correct by | Caught how |
|---|---|---|
| **Names** — Task kinds, Event Types, measurements, paths, ceilings | the tenant's own published configuration, read at generation time | Cannot drift. There is no second copy to disagree |
| **Operations** — paths, request fields, response fields | `operation_id` in the `ResolvedCodePlan`, resolved against `openapi/v1.json` | CI, composing with #155's operation-level gate (#156 §13 assigns this to #158) |
| **Ergonomics** — SDK method names, imports, idioms, the `with`-block convention | `ubb-codegen`, versioned against the SDK major | Renderer tests that execute emitted code against a mock. **Neither the spec nor the plan can see this** — #156 §10.2 |

The fourth case is the one nobody owns: **a file already sitting in a developer's repository.** The
only mechanism available is the header, which is why the artifact's header carries plan schema
version, renderer version, target SDK major, and the publish date of every declaration it resolved.
`verify_integration.py` re-states those and can compare them. Making that comparison *fail a build* is
Segment Typewriter's move (#144 finding 5) and is a real option later; **for v1 the position is that
the header makes it possible and nothing enforces it.**

### 3.8 No webhook handler is emitted

#156 §13 left this open. The position is **no**, for three reasons:

1. **It is not a call site of this integration.** `task.killed` and `task.expired` (#154, under ADR-0006 §5)
   arrive precisely when nobody is calling — a Task expires *because* the caller stopped reporting. A
   handler is an operational listener, usually in a different service, often a different language.
2. **It would need the webhook signing secret**, which is on the withhold list (#156 §6). Emittable as
   a `secret_reference`, but it makes the artifact's readiness depend on a second, unrelated
   configuration.
3. **Which events to subscribe to is a spend-control question, not a code-generation one** — #150's
   four families, and ADR-0006 gave control events their own declared namespaces.

What the builder should do instead costs nothing: **name the events this Task kind's ceilings can
produce, and deep-link to the webhook surface.** If a webhook receiver is worth generating, it is a
second builder target with its own inputs and its own readiness — not a section of this one.

---

## 4. What building it found

Ten things, in rough order of how much they matter. Six are about code on `main`.

**F1 · The stop branch is opt-in today, and the SDK calls that an ergonomic preference.**
`record_usage(..., raise_on_stop: bool = False)` (`ubb-sdk/ubb/metering.py:91`), whose docstring says
*"this is purely an ergonomic choice between checking result.stop and catching an exception"*
(`:110-116`), and `UBBStoppedError` repeats it: *"Default record_usage behavior is NOT to raise"*
(`ubb-sdk/ubb/exceptions.py`). For hand-written code that framing is defensible. For **generated**
code it is not a preference: the default is the one that silently discards every stop UBB issues.
The builder emits `raise_on_stop=True` regardless; the question is whether v4 flips the default.

**F2 · Every one of the three call sites changes shape, so no version of this artifact runs against
`main`.** Not "needs new fields" — contradicts, at all three:
- `start_task` is a wrapper over `pre_check(start_task=True)`, calls `self._require_billing()`, returns
  a `PreCheckResult`, and takes **no idempotency key** (`ubb-sdk/ubb/client.py:166-188`). #141 makes the
  lifecycle ungated and top-level; #140 makes the key required and permanently claimed.
- `close_task(task_id)` takes **no outcome** (`ubb-sdk/ubb/metering.py:188-194`) and lives on the
  metering client, while start lives behind the facade's billing requirement — **the lifecycle cannot
  be expressed in one namespace today.**
- `record_usage` requires `request_id` *and* `idempotency_key`, and carries `tags`, `dimensions`,
  `units` and `billed_cost_micros` (`:82-91`) — all of which the re-model deletes, renames or folds.

This is #155's "prototype against a paper model" hazard at its sharpest, and it cuts both ways: the
prototype cannot be validated against anything, **and** it is a preview of how much of the SDK's
public surface slice 5 rewrites.

**F3 · `request_id` has no decision behind it.** It is a required positional parameter of
`record_usage` and appears in **no decision document in map #137**. A generated call site would ask a
developer for two identity-shaped values and be able to explain only one. Either it goes, or it
becomes optional, or something must say what it is for — "supply two ids, we will not tell you why" is
exactly the unexplained fragment this ticket exists to prevent.

**F4 · The ceiling's three public status values still spell a retired word.**
#146 §5 coined `within_limit` / `limit_reached` / `indeterminate`; #150 §4.1 restated them. ADR-0006
then retired "limit" from field vocabulary, replaced `task.limit_exceeded` with `task.killed` /
`task.expired`, and **declined `task.ceiling_exceeded` on the grounds that under `>=` a ceiling is
reached, not exceeded** — reasoning that applies to `limit_reached` word for word. Nothing revisited
the three values. They are public response fields, #155 forbids provisional public vocabulary, and
**this artifact is the first thing that would put them in a developer's source file.** Rendered here
as `within_ceiling` / `ceiling_reached` / `indeterminate`. Owed a ruling.

**F5 · A `reported` Event Type has nowhere to declare where its cost comes from.**
#156 §4 puts `source_kind` on the **Measurement**, and §5 puts `source_path` / `source_shape_id` on the
Measurement mapping. A `reported` Event Type's defining value is not a Measurement — it is the cost.
So nothing declares whether that cost is read from the provider response, computed by the caller, or
constant, and **the generator cannot know whether to emit an extraction or a parameter.** Rendered
here as caller-supplied by assumption. Small, and it blocks a whole costing method.

**F6 · The `reported` cost line and the `calculated` cost-claim line are the same shape with opposite
meanings.** #151 §9.1 keeps `claimed_provider_cost_micros` for a surplus cost on a `calculated` kind —
non-canonical, flagged, diagnostic. At a call site it looks identical to a `reported` cost, which *is*
COGS. Proposed rule: **the builder never emits any cost field for a `calculated` Event Type.** Not
because the field is wrong, but because generated code teaches habits, and this is the one habit the
cost model exists to prevent.

**F7 · JSON has no comments, so the raw HTTP target has nowhere to put the explanation.**
The sharpest constraint the second target imposes, and it is invisible until you write one. Two ways
out: emit `jq` — which has comments, and is what this prototype does, at the cost of a tool dependency
— or move every explanation into shell comments above the request, which loses the per-token adjacency
#156 §6.1 requires. A plain `curl -d '{...}'` heredoc can carry **no** explanation at all in the
copied text, which for the target most likely to be pasted into a terminal is the worst outcome.

**F8 · Readiness is per-operation before it is per-file.** #156 §8.1 defines one verdict for the
artifact. The HTTP target here is complete for two Event Types and blocked for a third, because
`anthropic-messages` declares its mapping against a Python SDK response shape and a curl target reads
JSON (#156 §5.4, §5.5). One file-level verdict either overstates or understates. As rendered:
**readiness is computed per emitted operation and the file verdict is the aggregate**, with the header
naming which operations are blocked and which are fine. This is the decided-but-never-illustrated
consequence of one-shape-per-Event-Type, and seeing it rendered is most of why it is worth rendering.

**F9 · The console's two placeholder conventions sit in one file, and one carries its rule as a
comment.** `ubb_test_YOUR_SANDBOX_KEY` inside `sandboxResetCurl`, and
`AUTH_HEADER_EXAMPLE = "Authorization: Bearer ubb_live_xxxxxxxxxxxxxxxxxxxxxxxx"` with the comment
*"Placeholder auth header for the basics card — never a real key"*
(`apps/ui/src/features/developers/lib/test-event.ts`). #156 §12.1 already records both as wrong under
its §7. Worth adding: the second is a **comment asking future maintainers to keep a rule**, which is
precisely what #156 §10.1 replaces with a renderer type that cannot hold a secret at all.

**F10 · The generated module never calls the provider, and that turned out to be load-bearing.**
It takes the response the developer already has. Written the other way — constructing the provider
client, naming `ANTHROPIC_API_KEY`, showing the call — the artifact would ship UBB's opinion about
provider clients into the money path, which is #156 §3 and map constraint 5. Refusing it also makes
the module testable with a captured response, which is what `verify_integration.py` is built on. Two
requirements satisfied by one refusal.

---

## 5. Vocabulary I had to invent, and where it is provisional

#155 forbids provisional public vocabulary, so everything here that would become a public field name
needs a ruling before slice 0. Rendered names, and their standing:

| Rendered | Standing |
|---|---|
| `task_type`, `parent_task_id`, `idempotency_key`, `outcome`, `reason_code`, `reason_detail` | Decided (#140, #154) |
| `costing_status`, `pricing_status`, `unresolved` | Decided (#146, #147, #148) |
| `grouping_fields` | Follows #154's `GroupingFieldDef` rename. Plural form is mine |
| `measurements` | Follows #145's Measurement. Field name is mine |
| `reported_cost_micros` | **Mine.** #146 deleted caller-supplied `billed_cost_micros`; nothing names the field a `reported` Event Type uses |
| `within_ceiling` / `ceiling_reached` / `indeterminate` | **Contested** — see F4 |
| `stop.requested`, `stop.scope`, `stop.reason_code` | Shape is mine; today's SDK has flat `stop`, `stop_scope`, `stop_reason` |
| `measurements_received`, `grouping_fields_received` | **Mine**, and only the verify script needs them. May not be worth existing |
| `source_kind`, `source_shape_id` | Decided (#156 §4, §5) |

Endpoints rendered as `POST /api/v1/tasks`, `POST /api/v1/tasks/{id}/close`, `POST
/api/v1/metering/usage` — the first two per #141, the third unchanged. Illustrative.

---

## 6. Deliberately not done

- **TypeScript** — map constraint 6, #156 residue 6.
- **The Resolved Contract screen** — #156 §2 owns it; this ticket is about the code.
- **Console chrome of any kind** — #152 owns rendering; this artifact is what the page *emits*.
- **A `ResolvedCodePlan` JSON example** — #156 §10.1 already sketched one, and duplicating it here
  would create the second source this map has rejected five times.
- **Batch recording** — #149 §6 makes batching a loop over the same call site.
- **Draft-preview rendering** — #156 §9.2 decided the behaviour; it changes a header line, not a shape.
- **A `scaffold` example** — #156 §12.1 already specifies the API-basics scaffold in detail. The
  `incomplete` variant is the state that needed seeing, because it is the one where correct-looking
  code and missing configuration coexist in one file.

---

## 7. Rulings requested

1. **The three ceiling status values** (F4) — do `within_limit` / `limit_reached` become
   `within_ceiling` / `ceiling_reached`? They are public, and this artifact is where they surface.
2. **`raise_on_stop`** (F1) — does the v4 SDK default flip to `True`? The builder emits it explicitly
   either way; the question is what the *non*-generated path does.
3. **`request_id`** (F3) — does it survive the re-model, and if so, what does the emitted comment say
   about it?
4. **Where a `reported` Event Type declares its cost source** (F5) — a fifth attribute alongside
   `source_kind` on the Event Type, or is caller-supplied simply the only option?
5. **The HTTP target's dependency** (F7) — emit `jq` so the explanation can live in the copied text, or
   emit plain `curl` and accept that the raw HTTP target carries no per-line explanation at all?
6. **Per-operation readiness** (F8) — is the file verdict an aggregate of per-operation verdicts, as
   rendered, or does a single blocked Event Type make the whole artifact `incomplete`?
7. **The clean exit that declares nothing** (§3.4) — raise, as rendered? Close as `cancelled`? Or leave
   the Task open silently and let it expire? All three never charge; they differ in how loudly.
8. **The non-persisting cost preview** (§3.6) — worth raising as its own ticket, or out of scope?

---

## 8. The hazard, stated on the artifact itself

This renders a **paper model**. F2 is not a caveat, it is the condition: every call in the artifact
contradicts the SDK on `main` today, so nothing here can be validated against anything, and a reader
who takes it for a specification will build the wrong thing. #155 recorded exactly this risk for #152
and #157 both.

It is still worth having before slice 0, for the reason #152's notes gave: the alternative is
discovering the shape after the contract that has to carry it is already public. Three of the ten
findings above (F3, F4, F5) are things nobody would have looked for without writing the code out, and
all three are cheaper to fix now than after `ResolvedCodePlan` ships under #155's
no-provisional-vocabulary rule.
