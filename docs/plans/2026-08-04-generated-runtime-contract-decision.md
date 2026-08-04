# The generated runtime contract — what happens when nobody decided

**Resolves:** [#179](https://github.com/ashcochrane/ubb/issues/179) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-04
**Decided against:** `main` @ `0451423`
**Deferred from:** [#157](https://github.com/ashcochrane/ubb/issues/157) by
[#158](https://github.com/ashcochrane/ubb/issues/158) §13
**Builds on:**
`docs/prototypes/2026-08-04-code-builder-output-notes.md` (#157) — findings F1, F3, F5 and §3.4, the
four rulings this document owes.
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156) — §4's `source_kind`, §5's
`source_shape_id` and structured paths, §6's three value classes.
`docs/plans/2026-07-30-task-lifecycle-decision.md` (#140) — the six states, the required outcome, and
*the forgiving path must never be the money path*.
`docs/plans/2026-07-31-provider-supplied-cost-decision.md` (#146) — `reported` as a costing method.
`docs/plans/2026-07-30-money-model-decision.md` (#142) — no float ever enters money arithmetic.
`docs/adr/0006-domain-vocabulary-and-contract-naming.md` — the naming authority these names answer to.
`docs/adr/0008-audit-method-and-launch-gates.md` (#158) — §13.1's deferral rule, which this discharges.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR is written by this pass.** Every ruling here lands inside an existing authority: ADR-0006
owns the names, ADR-0007 §3 owns the no-provisional-vocabulary rule these names satisfy, and ADR-0008
§13.1 is the rule this document exists to discharge. Nothing here is hard enough to reverse to justify
a ninth ADR.

---

## The decision in one paragraph

**Four unexplained behaviours, and the same cause under all of them: nobody ever decided.** The SDK's
stop signal is off by default and its own docstring calls that *"purely an ergonomic choice"*; the
generated wrapper had no rule for a clean exit that declared nothing; a `reported` Event Type — whose
defining value *is* the cost — has nowhere to say where that cost comes from; and `record_usage`
demands a second identity-shaped string that no code in the platform reads. Each gap would be filled
by whichever engineer reached it first, and generated code makes that choice for every tenant at once.
So: **the stop raises by default and leaves the `Exception` family entirely**, becoming a control
signal a developer's own catch-all cannot swallow. **The wrapper declares a terminal outcome only where
control flow is itself evidence for one** — an ordinary exception is evidence of failure, a clean exit
is evidence of nothing, and a stop is evidence only of a stop. **A `reported` Event Type declares its
cost source** through the same structured-path machinery Measurements use, with an explicit amount
representation and a pinned currency, so the one number that *is* COGS is generated and tested rather
than hand-extracted. And **`request_id` is deleted**, taking an unexplained required parameter, an
index write on the hottest path, and a live bound defect with it.

---

## 0. The ticket's framing, corrected

#179 states that the four rulings *"share one contract: what the generated integration actually does at
runtime."* Three of them do. **F5 does not**, and the difference decides how it is answered.

F1, R7 and F3 are behaviours: what the SDK does on a stop, what the wrapper does on an exit, what the
caller is asked to supply. F5 is a **gap in what a tenant can declare**. Its runtime consequence — the
generator cannot know whether to emit an extraction or a parameter — is downstream of a missing
attribute on the Event Type, not a missing decision about behaviour. It therefore cannot be settled by
whatever principle settles the other three; it needs a model change, which §3 makes.

Recorded because the shared framing invites a single governing rule, and a single rule applied to F5
would produce a behavioural convention papering over a declaration gap.

**What the four genuinely share** is narrower and more useful: each is a place where the *absence* of a
decision already has a default, and the default is the dangerous one. A stop that is off. An exit that
would helpfully close. A cost that is assumed caller-supplied. A parameter that is required for no
reason. #140's rule — *the forgiving path must never be the money path* — is the same observation one
level up, and #157's sharpening of it (*generated code may infer the outcome that costs nothing, never
the one that charges*) is the same observation at the call site.

---

## 1. The stop signal — raises by default, and leaves the `Exception` family

### 1.1 The default flips

`record_usage(..., raise_on_stop: bool = False)` (`ubb-sdk/ubb/metering.py:91`), whose docstring calls
the choice *"purely an ergonomic choice between checking result.stop and catching an exception"*
(`:112-115`), and whose exception class repeats it: *"Default record_usage behavior is NOT to raise"*
(`ubb-sdk/ubb/exceptions.py`). The facade default matches (`ubb-sdk/ubb/client.py:199`), a parity test
keeps them together (`tests/test_sdk_delegation.py:187-194`), and `test_default_does_not_raise_on_stop`
(`tests/test_stop_verdict.py:49`) pins the current behaviour.

**For v4 the default raises.**

The framing is defensible for hand-written code and indefensible for generated code, but that is not
the reason it changes — the builder emits its choice explicitly either way. The reason is that the
sequence a real integration runs is:

```
provider call completes → tenant reports usage → UBB records the event
                        → UBB says spending should stop
                        → SDK interrupts the workflow before another call starts
```

and a returned flag is too easy to omit:

```python
client.record_usage(...)      # developer forgets to inspect the acknowledgement
run_another_expensive_call()
```

**The argument #157 did not make, and it is the one that decides.** #157 recorded an honest weakness:
`raise_on_stop=True` is one keyword, deleting it is a two-character edit, and nothing fails. That
weakness exists *only because the default is `False`*. Flip the default and the safe behaviour stops
depending on a token surviving every future edit of a generated file — continued spending now requires
an **act of commission**, which is greppable and visible in review. The generated live integration
therefore stops emitting the keyword at all.

### 1.2 A named behaviour, not a negative boolean

`raise_on_stop=False` is replaced by:

```
stop_behavior ∈ { "raise", "return" }        default: "raise"
```

An enum makes the exceptional choice legible at the call site and leaves room for future behaviours,
where a negative boolean forces a reader to compute the meaning of `False`. The `"return"` path returns
the identical stop metadata without raising.

**`"return"` has exactly one legitimate use, and it is a money reason.** When recording a backlog of
work that has already happened, raising part-way through the loop means the remaining events are never
recorded and UBB permanently loses real COGS. That case is backfill, and it is why §1.6 exists. The
docstring names it and stops calling the choice ergonomic.

### 1.3 It is a control signal, and the write already succeeded

The exception must mean **the event was successfully recorded, and no further work should start.** It
must never read as a failed submission — a caller who mistakes it for one retries a completed event.

Ordering is part of the contract:

```
event transaction commits
    ↓
successful acknowledgement is constructed
    ↓
the stop signal is raised, carrying that acknowledgement
```

The signal carries the acknowledgement so nothing is lost by catching it:

| Field | Why it is on the signal |
|---|---|
| `recorded_event_id` | proves the write landed; the handler needs no second call to confirm |
| `idempotency_key` | lets a handler reconcile against its own records without re-sending |
| `stop_scope` | decides what the handler must stop — this Task, or everything for the customer |
| `reason_code` | which control produced it |
| `trigger_source` | which configured control fired, for the operator asking *why now* |
| `current_cogs` | what has been spent |
| `configured_ceiling` | what it was measured against |

`current_cogs` and `configured_ceiling` together make the signal self-explaining: a handler can log
what happened without a follow-up read.

### 1.4 It sits outside `Exception`

Today `UBBStoppedError` derives from `UBBError`, which derives from `Exception`
(`ubb-sdk/ubb/exceptions.py:4-36`). That makes this pattern silently defeat the entire mechanism:

```python
try:
    record_usage(...)
except Exception:
    logger.exception("Usage reporting failed")
    continue_doing_work()          # the event recorded fine; the stop was eaten; spending continues
```

Excluding the signal *by name inside UBB's own wrapper* does nothing about this, because the swallowing
happens in the tenant's code. **The stop signal therefore derives from `BaseException`.**

Python already draws exactly this line: `KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError`
sit outside `Exception` because they are control signals that generic application error handling must
not consume. A stop-spending instruction is closer to cancellation than to an API failure.

Two qualifications on this, both deliberate:

- **One narrowly defined type, not the start of a parallel hierarchy.** It does not inherit from
  `UBBError`. Every ordinary SDK failure — auth, validation, transport, API error — stays an
  `Exception` under `UBBError`, unchanged.
- **It does not make interception impossible.** `except BaseException:` and a bare `except:` still
  catch it. That is accepted: *the objective is to protect against the common accidental failure mode,
  not to make interception technically impossible.* The generated examples and linting avoid bare
  catches around provider loops, and the documentation states that a `BaseException` must normally be
  re-raised unless the code is handling a specific named control signal.

### 1.5 Caught where the scope can be honoured

Generated code catches it **explicitly, at the outermost boundary that can actually act on its scope**:

```python
try:
    run_customer_work()
except <StopSignal> as stop:
    logger.info("UBB requested a spending stop", extra={
        "scope": stop.stop_scope,
        "reason": stop.reason_code,
        "event_id": stop.recorded_event_id,
    })
    stop_dispatching_new_work(stop.stop_scope)
```

**It is never caught inside a single provider-call helper.** `stop_scope` may be `customer`, and a
helper that knows about one call has neither the authority nor the context to halt everything for that
customer. This is #157 §3.5's *caught once around the whole unit of work*, restated as a rule about
authority rather than about convenience.

For a worker system the normal integration boundary catches it by name, stops dispatching affected
work, and ends the current execution cleanly. **If nobody handles it, letting it escape is safer than
silently continuing to spend.**

### 1.6 Batch never raises

`record_batch` (`ubb-sdk/ubb/metering.py:152`) has no raising path today and gains none. It:

- records every valid independent item;
- **never aborts part-way** because one acknowledgement requests a stop;
- returns per-item results;
- returns an aggregate stop indication;
- identifies the **earliest** item that triggered it.

A stop cannot prevent work that already completed. It remains useful information and is never a reason
to discard later history. #149 §7 already keeps the batch path *"as an efficiency, not a taught
concept"*, and semantics are identical per item — this adds the one field that makes the non-raising
posture safe.

The documentation carries the split explicitly:

| | |
|---|---|
| **Live, sequential recording** | raises by default, to prevent *future* work |
| **Historical or independent batch recording** | records the full batch and reports the stop condition |

**Generated code must never quietly adopt the backfill posture for a live workflow.** A generated live
integration relies on the raising default; a generated backfill example uses the batch path or
explicitly selects `stop_behavior="return"`, and says which it is.

### 1.7 The names owed

The exception is public vocabulary, so ADR-0007 §3 binds it and ADR-0008 §3's registry records it.
The token goes through ADR-0006; **three constraints are decided here**:

1. **Not an `Error`.** Today's `UBBStoppedError` says in its own name the thing §1.3 forbids it to say.
2. **Not Task-scoped.** `TaskStopRequested` is wrong whenever `stop_scope` is `customer`, which is
   precisely the case no per-call handler can honour.
3. **Describes a requested control action**, not a state that has already been reached.

`UBBStopRequested` and `SpendingStopRequested` both satisfy all three and are the candidates carried
forward. `trigger_source` is likewise a new public field name and enters the registry with them.

---

## 2. The wrapper declares an outcome only where control flow is evidence

### 2.1 The rule

> **The generated wrapper may declare a terminal outcome only where the control flow is itself evidence
> for that outcome.**

An ordinary unhandled exception is reasonable evidence that the Task's execution failed. A clean return
proves only that the Python block ended — it does not prove the Task was delivered, cancelled or
failed. A stop is evidence of a stop, and of nothing about whether the work delivered.

This is #157's *generated code may infer the outcome that costs nothing, never the one that charges*,
made both stricter and simpler: stricter because a non-charging inference is still a fabricated
statement, simpler because "is this evidence?" is answerable at the exit rather than requiring the
renderer to reason about which Task kinds charge.

### 2.2 The five exits

| Exit | Wrapper behaviour |
|---|---|
| Clean, explicit terminal call made | preserve the declared outcome; do nothing |
| Clean, Task still open | **declare nothing**; raise `TaskOutcomeRequired`; the Task stays open |
| Ordinary `Exception` | mark `failed` (`reason_code="execution_failed"`) if still open; **re-raise the original** |
| Stop signal | never mark failed; propagate unchanged |
| `KeyboardInterrupt` / cancellation / other `BaseException` | invent no outcome; propagate unchanged |

Because §1.4 moved the stop out of `Exception`, the classification is **structural** and carries no
exclusion list:

```python
def __exit__(self, exc_type, exc, traceback):
    if exc_type is None:
        if self.task.is_open:
            raise TaskOutcomeRequired(self.task.id)
        return False
    if issubclass(exc_type, Exception):
        if self.task.is_open:
            self.task.fail(reason_code="execution_failed")
        return False
    # Stop signals, cancellation, interrupts and process termination
    # are not evidence of business failure.
    return False
```

This is why §1.4 and §2 are one decision rather than two. Under any arrangement that leaves the stop
inside `Exception`, the wrapper needs a maintained list of things not to treat as failure, and its
correctness depends on every future control-flow type being remembered and added.

**The wrapper is documented as surrounding the entire Task run, not one stage within it.** The
`failed`-on-exception inference is only sound under that reading.

### 2.3 The original exception survives

If reporting the failure to UBB *also* fails, that secondary error is chained or logged and **never
replaces the exception that actually broke the work.** A developer debugging a broken workflow must not
be handed a UBB transport error in place of their own stack trace.

### 2.4 `TaskOutcomeRequired`

Raised on a clean exit with the Task still open, carrying at least:

- `task_id` · `task_type` · `current_state` · expiry time · the terminal declarations it will accept

with a message that says what to do:

```
Task task_123 left the execution block without a terminal outcome.
The Task remains open. Call complete(), fail() or cancel() explicitly.
```

**The Task is deliberately left open**, which is what makes this recoverable: a later explicit terminal
declaration still lands correctly. The exception reports a missing declaration; it does not destroy the
thing that is missing one.

### 2.5 Why not the two quiet options

**Close as `cancelled`** invents an outcome. Under #140 `cancelled` is *tenant-declared*, so this puts a
statement nobody made onto the record — and on a Task kind priced as a whole, a Task that genuinely
delivered is silently stripped of a Charge that was legitimately due. It costs nothing to UBB and can
cost the tenant real revenue.

**Leave it open silently** hides the integration defect, holds the #139 prepaid reservation and a
concurrency slot until the configured max age (default six hours), and — because #140 emits
`task.expired` for **enforcing tenants only** — may produce no signal at all. It is the quietest option
with the highest resource cost.

Raising while leaving the Task open is the only one that is simultaneously truthful about the unknown
outcome, immediately visible to the developer, recoverable by a later explicit declaration, and
incapable of either fabricating or destroying revenue.

**The missing-outcome exception is wanted in production, not only in development.** It exposes an
integration defect at once rather than silently holding resources until expiry or manufacturing a
commercial outcome.

### 2.6 Interruption is not business failure

`KeyboardInterrupt`, `SystemExit` and `asyncio.CancelledError` all sit outside `Exception`, so §2.2's
structural test already covers them: no declaration is made and the signal propagates. A Ctrl-C during
a Task that had in fact delivered must not write `failed` onto it.

This closes the policy #179's owner flagged as owed rather than leaving `except BaseException` to
classify interruption as ordinary business failure by accident.

---

## 3. A `reported` Event Type declares where its cost comes from

### 3.1 The gap

#146 made costing method a declaration on the Event Type — `calculated` or `reported`, exclusive per
kind. #156 §4 put `source_kind` on the **Measurement** and §5 put `source_shape_id` and structured
`source_path` on the Event Type's mapping. A `reported` Event Type's defining value is not a
Measurement — **it is the cost** — and #146 §2.4 is explicit that on such a kind no measurement is a
costing input at all.

So nothing declares whether that cost is read from the provider response, computed by the caller, or
fixed. The generator cannot know whether to emit an extraction or a parameter, and #157 rendered it as
caller-supplied by assumption.

**The argument that decides it.** #146 introduced reported costing as *"a second, cheaper way to reach
the one COGS number."* Leaving the cost caller-supplied by rule makes `reported` **more** work than
`calculated`, inverting its purpose: the supposedly easier method has its most important field
hand-written by every integrator. Worse, #145 §14 is explicit that `source_path` is unvalidatable by
UBB and *"the defence is code generation, not validation"* — so under caller-supplied-only, the Code
Builder's central defence covers every token count and misses the actual COGS value.

### 3.2 `reported_cost_mapping` — a sibling of the Measurements, not one of them

The Event Type's costing configuration gains a mapping:

```
EventType
  costing_method: reported
  reported_cost_mapping:
    source_kind
    source_path
    amount_representation
    currency treatment
```

It **shares** the Measurement machinery: `source_kind`, the inherited `source_shape_id`, structured
path segments, mapping validation, Code Builder rendering, and the published-contract lifecycle.

It is **not** a Measurement, and is not modelled as one:

| | |
|---|---|
| Measurements | quantities with **units** |
| Reported supplier cost | money with a **currency** |

Forcing the cost into the Measurement entity would make `unit` meaningless or force it to mean
"currency", give `value_type` a money shape, and put a value governed by #146 §7.2's single shared cost
bound under a caller-set unbounded integer. Sharing the *source-declaration vocabulary* is the reuse
worth having; sharing the entity is not.

### 3.3 Which source kinds are valid, and which are not

The four `source_kind` values are not inherited wholesale — reported costing constrains them:

| `source_kind` | On a `reported` Event Type |
|---|---|
| `provider_response` | **valid.** `source_path` required; the inherited `source_shape_id` identifies the response shape; the Code Builder extracts and converts |
| `caller_supplied` | **valid.** The Code Builder emits a required runtime parameter; obtaining the value stays the tenant's responsibility |
| `derived` | **only** as a named, declarative transformation — never arbitrary tenant code hidden in configuration |
| `constant` | **rejected.** Nothing is being reported per event |

The `constant` rejection is the sharpest of the four and was volunteered against my own proposal: a
fixed per-call supplier cost is a **configured cost rule**, and representing it as a reported cost would
let `reported` mean "a number that arrives" and "a number that never arrives" at once. Keeping it out
prevents the shared source vocabulary from blurring the meaning of the costing method it is attached
to.

### 3.4 The amount says what it is, and the conversion is exact

The declaration states what the extracted number represents:

```
amount_representation ∈ {
  micros                  integer, already denominated in currency micros
  minor_units             integer, in the currency's minor unit
  major_units_decimal     decimal amount such as 0.00123 dollars
}
```

The Code Builder then emits the conversion **once**, in decimal arithmetic:

```python
provider_cost_micros = int(
    Decimal(str(response.cost)) * Decimal("1000000")
)
```

**This is what protects #142.** *No float ever enters money arithmetic* survived because quantities are
integers on both paths — but a provider hands us `0.00123`, and somebody has to convert it. If the
source is declared, the generator writes that conversion once, exactly, and tests it. If it is not, the
developer writes `cost * 1e6` in code UBB never sees, and #142's invariant dies silently in tenant
repositories. **The conversion happens either way; the only question is whether it is generated and
tested or invisible.** Where the response shape offers an integer or a decimal string, that is
preferred over a binary float.

**Over-precision is refused, not rounded.** If the amount cannot be represented exactly in micros, the
generated integration rejects it unless an explicit rounding policy has been declared. No rounding mode
is chosen silently. This is a genuinely new case: #142's four rounding rules govern amounts UBB
*computes*, and a reported cost is one it *observes* — and #146's governing asymmetry is that **cost is
observed, price is decided**, which makes silently reshaping an observation the wrong move.

### 3.5 Currency is pinned, and disagreement fails loudly

The mapping declares an unambiguous currency source: either a **fixed currency** declared on the Event
Type or the cost mapping, or a **provider-returned currency** with its own structured source path.

If the provider returns a currency that disagrees with the configured one, **the generated integration
fails clearly rather than converting the amount under the wrong currency assumption.** #145 made v1
USD-only, enforced at the API and in the database, with no FX — so there is no correct conversion to
perform, and a silent reinterpretation would be the worst available outcome.

### 3.6 The wire stays normalised

The declaration governs **code generation**. The event that reaches UBB carries:

- `provider_cost_micros` — integer
- `currency` — canonical currency code

**UBB never receives the provider's raw float and never repeats the conversion server-side.** The
generated integration performs the declared extraction and conversion; the Pricing Receipt records that
the cost was reported, along with the applicable source provenance.

### 3.7 Publication and readiness

Because this mapping directly determines COGS, it is part of the published Event Type contract on
#156 §5.6's footing:

- **missing mandatory reported-cost mapping** → the Event Type may remain a draft; the generated
  artifact is `incomplete`
- **published mapping** → pinned as part of the Event Type contract
- **mapping changed** → a revised publish; **never a silent reinterpretation** of integrations already
  generated and deployed

UBB's response-shape checker may **warn** when a path looks inconsistent with a known provider shape,
and must **never substitute its own path** — #156 §3's rule, unchanged, arriving at the cost field.

### 3.8 This resolves #157 F6 without a special case

F6 recorded that the `reported` cost line and #151's `claimed_provider_cost_micros` line are the same
shape at a call site with opposite meanings, and proposed the rule *the builder never emits any cost
field for a `calculated` Event Type.*

Routing the reported cost onto **`provider_cost_micros`** — the authoritative COGS column, nullable
since #146 — settles it by construction. `provider_cost_micros` is accepted only on `reported` kinds
and *is* the cost; `claimed_provider_cost_micros` is unambiguously diagnostic and lives only on
`calculated` kinds. F6's proposed rule holds, and needs no special case to state it.

**Owed to slice 3, not decided here:** whether the two are distinct wire fields or one field routed by
the Event Type's costing method at the door. Today `provider_cost_micros` is accepted on any event
(`api/v1/schemas.py:69`), so something must change either way.

---

## 4. `request_id` is deleted

### 4.1 It does nothing

`record_usage(customer_id, request_id, idempotency_key, ...)` requires it positionally
(`ubb-sdk/ubb/metering.py:82`). In the platform it is:

- stored on `UsageEvent` (`apps/metering/usage/models.py:16`) with `db_index=True`
- threaded through `UsageService.gather` and `record_usage` as a pass-through
  (`usage_service.py:282,312,503,547`) — one site already defaults it to `""`
- echoed back in responses (`api/v1/metering_endpoints.py:247`, `api/v1/schemas.py:205,222,239`)
- searchable in Django admin (`apps/metering/usage/admin.py:17`)
- displayed once in the console (`features/events/components/event-detail-page.tsx:114`)
- listed in `FORBIDDEN_KEYS` so nobody can declare a Grouping Field with that name

It has **no uniqueness constraint, no lookup, no filter, and no read that changes any behaviour
anywhere.** It supports zero product query paths. It appears in **no decision document in map #137**.

And it carries `db_index=True` — an index write on every event, on the hottest path in the system,
serving only Django admin search.

### 4.2 The live defect it carries

`RecordUsageRequest.request_id` accepts up to **500** characters (`api/v1/schemas.py:66`). The column
is **`varchar(255)`** (`apps/metering/usage/models.py:16`). A 300-character value passes validation and
`DataError`s at insert.

What makes this a finding rather than a triviality is one field below it. `idempotency_key` is 500 in
both places, and `RawIngestEvent` carries an explicit comment recording why:

> `# 500, matching IngestEventIn/RecordUsageRequest's schema max_length and`
> `# UsageEvent.idempotency_key: a 256-500 char caller key must not DataError`
> `# the whole batch's bulk_create …`

The identical hazard was spotted, reasoned about, and fixed for one field — and left in place for the
field directly above it, because nothing reads that field and so nothing ever exercised it.

### 4.3 Why deletion rather than repair

Under #156 §6 `request_id` classifies as `runtime_bound`, so #157 §3.3 renders it as a **required
parameter** in every generated integration. That is the forcing consideration: the builder would demand
a value on every call and be able to explain only the other one. *"Supply two ids, we will not tell you
why"* is precisely the unexplained fragment the Code Builder exists to eliminate — and generated code
teaches habits at tenant scale.

Identity is `idempotency_key`. Correlation is what `metadata` is for — filterable and readable under
#145 §9, which folded `tags` into it for this reason. A tenant who wants to correlate a UBB event to
their own provider call puts the value in `metadata` deliberately, rather than being made to invent one.

Map constraint 1 makes the break free: there are no live integrators, and ADR-0003 §4's 90-day
deprecation does not apply. The v4 SDK re-cut and #155's cutover are where it lands.

**A better version of this field was considered and not adopted.** It could have been re-founded as the
*provider's* request id — a declared value with `source_kind: provider_response` and a `source_path`,
extracted by the generator, giving UBB a real link from a cost back to the exact supplier call that
produced it. That is the only reading under which requiring it makes sense, and it is new product
inside a runtime-contract ruling. Recorded so a later reader knows the shape was seen and deferred, not
missed.

### 4.4 What goes with it

- the required positional parameter, from `record_usage` and `record_batch` items
- the column, its index, and the 255/500 defect
- the field from `RecordUsageRequest` and from three response schemas
- four occurrences in `openapi/v1.json`
- the admin search field, and the console's **Request ID** row

The console row's replacement is residue (§8): a `metadata` key has no fixed name, so the event detail
page shows whatever the tenant chose rather than a labelled field.

---

## 5. What the Code Builder emits, after all four

| | Before | After |
|---|---|---|
| Stop | `raise_on_stop=True` emitted at every record call | nothing emitted — the default raises; the signal is caught by name at the workflow boundary |
| Clean exit | context manager raises | unchanged, and now the *only* branch that declares nothing on a clean path |
| Exception exit | closes `failed` | unchanged, but scoped structurally to `Exception` |
| Stop exit | would have closed `failed` | propagates untouched |
| Reported cost | required parameter, by assumption | extraction **or** parameter, per the declared `source_kind`, with a generated exact conversion |
| `request_id` | required parameter with no explanation | gone |

The net effect on the emitted call site is that **it gets shorter and says more**: one fewer required
parameter, one fewer keyword argument, and the two behaviours that matter — the stop and the outcome —
become things the language enforces rather than things a comment asks for.

§1.1 removes #157 §3.5's stated weakness rather than mitigating it. The generated verify script still
drives a sandbox Task past its ceiling and asserts the signal arrives, but it is no longer *the only
mechanism that binds* — it now proves a default rather than defending a keyword.

---

## 6. The tests that pin this

Every rule above is owed a test, on ADR-0006's *prefer backing any hard rule with a test* footing.
Collected from all four rulings:

**Stop delivery**
1. a stop response → the event **exists** before the signal is raised
2. the typed signal carries the complete successful acknowledgement
3. `except Exception:` does **not** catch the stop signal
4. catching by name receives the full acknowledgement
5. retry after the signal → idempotency prevents duplication
6. `stop_behavior="return"` → identical stop metadata, no raise
7. an ordinary UBB API failure **remains** an `Exception` under `UBBError`
8. `record_batch` never raises the stop signal mid-batch; records all valid items; reports the
   aggregate condition and the earliest triggering item; never truncates

**Wrapper exits**
9. explicit completion → no exception
10. clean exit without an outcome → `TaskOutcomeRequired`, and the Task remains **open**
11. ordinary body exception → Task marked `failed` **once**, original exception re-raised
12. the wrapper receives a stop signal → Task **not** marked failed, signal propagated unchanged
13. `KeyboardInterrupt` and `CancelledError` propagate with **no** fabricated outcome
14. failure-reporting call also fails → the original body exception remains primary

**Reported cost**
15. `provider_response` mapping → generated extraction resolves against a captured response
16. `major_units_decimal` → conversion is exact and no binary float participates
17. an over-precise amount → refused, with no rounding mode chosen silently
18. a provider currency disagreeing with the configured one → clear failure, no conversion
19. `constant` on a `reported` Event Type → rejected at declaration
20. missing mandatory mapping → Event Type stays draft; artifact readiness is `incomplete`

**`request_id`**
21. the field is absent from the request schema, the model, the spec and the SDK signature — the
    forbidden-term sweep ADR-0006 §*Consequences* already runs, extended by one name

---

## 7. Live defects found while deciding

**D1 · `request_id`'s bound mismatch** — §4.2. Schema 500, column 255, and the adjacent field carries a
comment proving the hazard was understood. Dies with the field; **worth a regression test on
`idempotency_key`'s bound regardless**, since that is the one that survives.

**D2 · `UBBStoppedError` is swallowable by a catch-all** — §1.4. Not a bug in the class; a consequence
of its base, which nothing had reason to question while the raising path was opt-in.

**D3 · `docs/spend-control-integration.md:52` teaches the retired shape.** It reads *"Or pass
`raise_on_stop=True` and catch `UBBStoppedError`"*, presenting the safe behaviour as the alternative.
The surrounding paragraph is otherwise correct and says the right thing — *"the stop is an instruction,
not an error"* — which is the sentence §1.3 turns into a type. The line changes with v4, and it
**narrows** the map's open "generated code and the docs site" item (§9): the hand-written guide is now
known to contain at least one instruction the ruling invalidates.

**D4 · The parity test pins the wrong default.** `tests/test_sdk_delegation.py:187-194` and
`tests/test_stop_verdict.py:49` both encode `raise_on_stop=False` as correct. They are correct today;
noted so slice 5 changes them deliberately rather than discovering them red.

---

## 8. Vocabulary owed

Public names introduced or removed here, for ADR-0008 §3's registry under ADR-0006's authority:

| Name | Standing |
|---|---|
| the stop signal type | **owed.** Constraints decided (§1.6): not an `Error`, not Task-scoped, describes a requested action. `UBBStopRequested` / `SpendingStopRequested` |
| `stop_behavior` + `"raise"` / `"return"` | **new**, closed value set |
| `trigger_source` | **new** field on the signal payload |
| `TaskOutcomeRequired` | **new.** Task-scoped and correctly so |
| `reported_cost_mapping`, `amount_representation` + its three values | **new** |
| `execution_failed` | **owed** — whether it is a member of #140's UBB-shipped closed reason list, or an addition to it |
| `request_id` | **retired** — joins ADR-0006's retirement list and the forbidden-term sweep |

**Two collisions found, both owed a resolution before the names ship:**

- **`outcome` is carrying two meanings.** #140 pinned it as the **required close field** ∈
  delivered/failed/cancelled. A `task.complete(outcome={"report_id": ...})` shape uses it for business
  payload. One public word, two meanings, in the same call. The three-method shape
  (`complete()`/`fail()`/`cancel()`) is **retained and preferred** over `close(outcome=...)` — it maps
  onto #140's single endpoint and has no default to forget, which is #140's own requirement satisfied
  more strongly by ergonomics than by validation. It is the **payload** that needs a different word.
- **"permitted terminal operations"** on `TaskOutcomeRequired` uses "operation" as a count noun, which
  ADR-0006 retired. Rendered here as *the terminal declarations it will accept*. Caught by running the
  forbidden-term sweep over this document before posting, which is #157's method note applied.

---

## 9. Constraints this imposes on other tickets

- **Slice 3 (cost)** — unblocked. `reported_cost_mapping`, its constrained source kinds,
  `amount_representation`, the Decimal conversion rule, the over-precision refusal and the currency
  pin all land here. Also owed: whether reported cost and `claimed_provider_cost_micros` are one wire
  field routed by costing method or two (§3.8).
- **Slice 5 (work)** — unblocked. The v4 SDK re-cut carries: the flipped default, `stop_behavior`, the
  `BaseException`-derived signal and its payload, the non-interrupting batch contract, the wrapper's
  five exits, `TaskOutcomeRequired`, and the removal of `request_id` from the signature. D4's two tests
  change deliberately.
- **Slice 2 (measurement)** — `request_id` leaves the model, the schema, three response schemas and
  the spec in this slice's migration matrix.
- **Code Builder build work** (still unassigned — #156 residue 1, #158 §16) — all four rulings are
  inputs. The emitted artifact loses one required parameter and one keyword argument, and gains a
  generated cost extraction.
- **#180** (renderer and preview) — unaffected. Its two rulings are independent.
- **ADR-0006 / the vocabulary registry** — seven names in §8, two collisions, one retirement.
- **`docs/spend-control-integration.md`** — D3. At minimum line 52 changes; whether the guide survives
  the Code Builder is the map's still-open item.

---

## 10. Residue, flagged not buried

1. **The exception tokens are not chosen**, only constrained. Two candidates carried; ADR-0006 picks.
2. **`execution_failed`'s membership** of #140's closed reason list is unresolved.
3. **The `outcome` word collision** has a diagnosis and no chosen replacement.
4. **The SDK namespace shape is undesigned.** `client.events.record(...)` / `client.tasks.run(...)`
   appeared throughout this grilling as illustration. Today it is `client.record_usage(...)`; #141 put
   the *API* lifecycle in one namespace but nothing has decided the client's shape. **Read as
   illustrative, not ruled** — it belongs to slice 5, and #157 F2 already records that all three call
   sites contradict `main`.
5. **The console's Request ID row has no replacement.** A `metadata` key has no fixed name, so the
   event detail page either drops the row or shows a tenant-chosen key.
6. **`derived` is permitted but undefined.** "A named, declarative transformation" is the constraint;
   what the transformation vocabulary *is* has no design, and no ticket owns it. It is the one
   `source_kind` a tenant cannot use until somebody specifies it — which is acceptable for v1 only
   because `provider_response` and `caller_supplied` cover the real cases.
7. **The over-precision rounding policy has no declaration shape.** §3.4 rules that an explicit policy
   is required before rounding may occur; where that policy is declared, and what values it takes, is
   undesigned.
8. **Nothing prevents a deliberate `except BaseException:`** from swallowing the stop. Accepted in
   §1.4, mitigated by generated examples and linting, and stated here so it is not later discovered as
   a gap in the guarantee.
