# ADR-0016: Generated integration code is a module and value-free call sites, and the names in it are a contract

**Status:** accepted
**Date:** 2026-10-02
**Decision records:** the consolidated Code Builder specification on #184 (four comments,
2026-09-25) — §1 the three components, §5 the renderer package, §6 the artifact, §7 the classes as
shapes, §9 the runtime contract, §10 the catalogue's home — and the owner's rulings of the same day
(item 9: the catalogue's symbols are the renderer's and are not registry concepts) ·
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156 §6, §7, §10)
**Companion:** ADR-0015 is the document this renders and §3 there is the token convention §3 here
reads; ADR-0008 §5 names the gates (G23 to G26) the suite here is the first half of; ADR-0007 §3 is
why a name a tenant's code depends on is final on the day it ships

## Context

ADR-0015 recorded what the server answers. This ADR records the second of #184's three components
as built (#577): `ubb-codegen`, which turns that answer into files, and its Python target.

The specification settled most of it. Four things were left to the build, and each is expensive to
change once a tenant has a generated file in their repository: what a tenant's own code is allowed
to depend on, how a token becomes an argument without the renderer knowing what a field means,
where the Blueprints a renderer is tested against come from, and what a renderer does with a
document it cannot read.

## Decision

### 1. One pure function, in a package that cannot reach anything

`render(blueprint)` returns the files of an artifact. It lives in `apps/codegen`, a workspace
package beside the console, and imports nothing but its own modules. Its source is compiled with no
DOM and no Node types in scope and linted against a non-relative import, a clock, a network call
and randomness, so purity is a property of the build and not of care.

The Blueprint's type is generated from the committed contract on every typecheck and is never
committed. A hand-written type would be a second place the document's shape is written down.

A token is read into one of four types, and a secret reference's type carries the name of a
variable and nothing else. Whatever a document puts in the `value` of a secret token is never
copied out of it, so past the reader there is no type through which a secret token's value could
reach a file. The document itself arrives as the contract types it — a token's `value` is untyped
JSON — so the secret is unrepresentable from the reader onward and ignored at it. That a Blueprint
carries no secret anywhere is the server's test to hold (ADR-0015).

### 2. The module holds every value; a call site holds none, and its names are final

An artifact is one module, the call-site blocks, an `.env.example` and a verify script. Every value
the Blueprint resolved that running code needs is in the module; the verify script holds the
declared paths again, to check them. Regenerating replaces those two files and touches no
call-site block.

A call-site block is written from the names of functions the module exports, the names of
parameters, and fixed text. No type holds a literal out of one — a block is lines of text — so the
suite does: Python's parser is asked for every string, number and bytes literal in every block of
every branch, and there must be none. `...`, where the tenant's own code goes, is the one constant
a block contains.

Which work an event belongs to is the tenant's to say, so a record block asks for `task_id` by
name and reads it off nothing. A Subtask's parent is the work the block sits inside, so that one
id is read off the handle.

**What a block does contain is therefore a contract with code UBB never sees:**

- `start_task` and `unit_of_work`, fixed;
- `start_subtask_<name>`, `record_<name>` and `backfill_<name>`, where `<name>` is the declared key
  with every character outside ASCII letters and digits written as an underscore;
- each `runtime_bound` token's `parameter_name`, exactly as the Blueprint gives it.

Naming a function for a key is this renderer's naming. It is not a second spelling of the key,
which is only ever written as a literal.

**What "no generated value" means, as ruled (§9).** #184 §6 says no generated value may appear in
a call-site block, "that excludes kinds of work, Event Types, Measurement names". The rule is about
VALUES: a block never supplies a tenant-declared Event Type, Measurement name, grouping value or
any other argument as a literal, so nothing in a block can go stale when configuration moves. A
function named for the declared object it is about is a SYMBOL derived from the selected contract,
and is not a value in that sense. The alternative, a name by position, would silently change what
a call means when the selection changes.

**Two keys that would share a function name both take a suffix that is a function of the key.**
Neither keeps the plain name. So selecting a second Event Type can make an existing function's
name disappear, which a call site notices at import, and can never hand that name to the other
Event Type, which would record one supplier's usage as another's and say nothing. **That is the
invariant: a generated function is never silently reattributed to another declared object.** A
collision may change a symbol loudly; it is deliberately no more elaborate than that.

The module's own names are chosen so that no parameter is spelled like one, so a declared name can
never stand in front of the client, the conversion or the SDK keywords.

### 3. A token is placed by its name and its position, and never by what its field means

`src/tokens.ts` is the only reader of ADR-0015 §3's convention, and it never decodes a key:

1. `api_key` is the credential, read from the environment by the name the Blueprint gives.
2. A one-segment name is a field the request publishes, and is passed under exactly that name.
3. For the two fields that hold an object of declared keys, each one-segment token is a key; the
   tokens named under it follow it directly, share one `<field>.<segment>` prefix read off the
   first of them, and the one named exactly that prefix is the value.
4. Every other token is a declared fact: stated in a comment beside the value it is about, never
   sent, never asked for.

Three facts change how a value is written, and the list is closed: `source_path`,
`response_shape_representation` and `amount_representation`. A path is written segment by segment
as declared. A segment Python cannot spell as an attribute is reached with `getattr`, which changes
the syntax and not the name. A fourth, `pricing_mode`, chooses a sentence of comment.

Since renderer contract 2 (#583, 2026-10-08; ADR-0015 §3), `source_path` may also stand under a
field's own value — a supplier's cost, or the currency beside it — and that value is then read off
`response` at its path, as a value under a key is. The list stays closed: a currency read off the
response is the runtime `currency` with the existing `currency.source_path` fact, and no new fact.

A call that is not ready raises before it sends anything, naming every token with no configured
value, and is still written beneath the guard so the file shows the lifecycle's shape.

### 4. The stop is caught once, and the conversion is the platform's

`UBBStopRequested` is caught in exactly one place, `unit_of_work`, which logs the acknowledgement
as it stands and raises again. No function that records has a handler. The path for work that has
already happened passes `stop_behavior="return"`; the live path passes `"raise"`.

What is logged today is the key the event was sent under and the acknowledgement's own `repr`.
**That is a fallback and is temporary (§9).** The SDK's models cannot be turned back into a
dictionary yet (#596), and the stop's contracted explanation — the reason, the mechanism that
applied it, the scope, the limit and the spend measured against it — is not all published yet
(#569). When that lands, the boundary states those fields by name. It never relies on an SDK
object's `repr` as its structured account of a stop.

A cost a supplier reports is converted to whole micros in the tenant's process, by a helper written
into the module. Its definition is the platform's `to_micros` and `pin_currency`, and it is held to
them case for case: the platform writes a table of its own answers, and the suite runs the
generated helper over that table.

Since #583 (2026-10-08) that includes a cost read off the supplier's response. It is read at its
declared path as the response holds it — an integer, a decimal string, or a `Decimal` where the
JSON was parsed with `parse_float=Decimal` — and a binary float is refused, in words of its own
that send the reader to the response's integer or its decimal text. It is sent as
`provider_response_cost_micros` and never as `provider_cost_micros`, which is the caller's. The
platform's table carries rows read off a response too, answered by `json.loads` and `to_micros`,
and the generated read is held to them case for case. A row whose response `json` cannot read is
refused as a response: the tenant's own parse fails before the module is handed anything, and the
shell file, which is handed the text, refuses it to match (ADR-0017 §6).

A currency that disagrees with the declared one is refused by that helper, and here that is proved
by calling the helper: for a cost the caller supplies, generated code has no supplier currency to
pass. **It is not the end-to-end proof (§9).** The ticket that carries a cost read off a
supplier's response (#583) passes the response's currency and owes the real case, through the
generated artifact: a response reporting a currency other than the contract's is refused.

*Ruled on #583 (2026-10-08, decision D1): the refusal reaches the integration from the server.* A
mapping either pins a currency or declares a `currency_path`, and generated code passes the helper
the one it has and never both, so the helper's own disagreement case is never reached by a
generated call. Where the currency is read, generated code refuses locally only a value the
helper's table does not recognise, and sends a recognised one as the event's `currency`. It holds
no copy of the tenant's currency to compare. A recognised currency that is not the tenant's
reaches UBB and is refused there by the one shared check — 422, "currency mismatch", nothing
recorded — and the SDK's error carries that refusal out of the integration. The end-to-end proof
is Seam C's `response-currency-refused` scenario, on both targets.

### 5. Fixtures are what the platform answered

Every Blueprint the suite renders is a committed file that a platform test produces through the
tenant's own routes and holds equal to the route's answer. A Blueprint added by hand beside them
fails that test. Where a test needs a document the routes cannot produce, it derives one from a
committed fixture inside the test and says what it changed.

### 6. Comments are provenance or catalogue, and the catalogue is the renderer's

A comment is either one statement generated from the Blueprint, in the single form
`<name> = <json>[ · <qualifier> <json>]...`, or a line of the renderer catalogue. There are no
docstrings. The catalogue is closed and versioned, and holds a sentence for every diagnostic code
and every verdict. Its symbols are the renderer's own and are not registry concepts.

**The catalogue restates five registry value sets, and that is an exception recorded here.** The
verdicts, the diagnostic codes, the pricing modes, the amount representations and the response
representations are spelled in it as keys, where the coding standards ask for a generated name.
The registry generates no artifact for this package. Each set is instead held equal to the
registry's by a test, against the SDK's generated vocabulary, and the sets the contract marks are
exhaustive by type as well. A generated target for this package would retire the exception.

The version is a convention with a tripwire, not a refusal: the whole catalogue is pinned in a file
named for its version, so a change under an unchanged number is a diff of that file.

### 7. A document the renderer cannot read is refused, not guessed at

`render` throws `BlueprintNotRenderable` for:

- a `schema_version` or `renderer_contract_version` outside the set it reads;
- a target with no renderer, an SDK major it is not written against, or an operation it has no
  call for;
- no start of the work itself, or more than one;
- a secret with no setup instructions in the catalogue, a second secret on one call, or two calls
  naming different credentials;
- a token the convention cannot place: a fact named under a field the call does not carry, a fact
  or a keyed value of the wrong class, a path that is not a list of segments;
- a parameter Python cannot bind, or one spelled like a name the boundary must be able to say;
- a number too large to carry exactly.

A Blueprint that is merely not ready is never refused.

### 8. Where the API is, is not the renderer's to say

`UBB_BASE_URL` is read from the environment and is **required**. A generated file holds no host:
with the variable unset or empty it refuses to build a client, naming the variable, before anything
is sent.

#184 §4 and #156 §7 describe a default, "the canonical host". No operational hostname is ratified
by the platform's contract, and the only one written down was quoted by a dated decision from a
prototype. A renderer that wrote it into tenants' files would make it a public contract by
accident, so it does not (§9). The SDK's own default is a developer's localhost and is not
inherited either: a file that fell back to it would send production usage nowhere.

**The rule for every target:** the renderer never holds its own copy of the platform's service
location. If the SDK comes to own a canonical production base URL, generated Python inherits the
SDK's default and does not restate it; until then the variable is required. The shell target
follows the same source and holds no host of its own.

### 9. The owner's rulings on this record

The owner reviewed these decisions on PR #597 on 2026-10-02 and approved §1 to §7 as built, with
five rulings:

1. **Generated function names stand** (§2): symbolic identifiers derived from the selected
   contract are not the values §6 prohibits, semantic names are preferred to positional ones, and
   the collision rule stays as it is.
2. **The fixed-price fixture is route-built**, not synthetic as the ticket's criterion said: a
   real route-built Blueprint is stronger evidence. A missing agreed price stays #586's.
3. **The currency-disagreement proof here is the helper's**, accepted for this ticket; #583 owes
   the generated-artifact case (§4). *2026-10-08:* #583 met it as the owner ruled there (D1): the
   refusal is the server's, and the integration surfaces it (§4).
4. **The default host is removed** (§8). This is the one thing the review changed.
5. **#596 does not block this, and `repr` is temporary** (§4).

### 10. What this ADR does not decide

The shell target (#578), which is ADR-0017's. The page that calls `render` (#579). Execution against the real
application (#582). How a constant's value or a missing agreed price is rendered (#584, #586):
each arrives as tokens under §3 and needs no new rule. A cost read off a supplier's response
(#583) arrived that way too, and needed only renderer contract 2 (§3).

## What proves it

| Rule | Test |
|---|---|
| §1 — the suite runs unconditionally in CI, in a job of its own, and can fail it | `tests/contracts/test_the_renderer_suite_is_enforced.py` — `test_ci_runs_the_renderers_suite_and_can_fail_on_it`, `test_no_renderer_test_is_skipped_or_run_alone`, `test_the_package_defines_the_scripts_the_steps_run` |
| §1 — a secret token's value changes nothing | `apps/codegen/tests/snapshots.test.ts` — "writes the same files whatever a secret token carries as a value" |
| §2 — no generated value in a call-site block; its names are exports, parameters and handles | `apps/codegen/tests/artifact.test.ts` — "puts no generated value in a call-site block", "names nothing in a call-site block but exports, parameters and the handles" |
| §2 — a shared name is taken by neither key | `apps/codegen/tests/execution.test.ts` — "name each function for its declared key, and never share a name" |
| §2 — a declared name cannot stand in front of the module's own | same module — "can never stand in front of one of the module's own names" |
| §3 — every runtime value is a required parameter at its own call; every literal reads back unchanged | `apps/codegen/tests/artifact.test.ts` — "asks for every runtime value as a required parameter, at the call it is declared for", "writes every platform-known argument as the literal Python reads back unchanged" |
| §3 — declared names reach the wire as declared, and cannot end a line | `apps/codegen/tests/execution.test.ts` — "reach the wire exactly as they were declared", "cannot end a line or start a statement, whatever they hold" |
| §3 — a call that is not ready raises, naming what is missing | same module — "raises from every call that is not ready, naming what is missing" |
| §4 — one catch, by name, raised again | same module — "is caught in exactly one place, by name, and raised again", "passes through a tenant's own except Exception and out of the boundary" |
| §4 — the conversion is the platform's, case for case | same module — "is converted exactly as the platform converts it, case for case"; `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` — `test_the_reported_cost_cases_carry_this_platforms_answers`, `test_the_currency_table_is_this_platforms` |
| §4 — a cost read off the response is read as the platform answers it, row for row, on its own field; a currency UBB holds and the tenant does not is the server's refusal, surfaced (#583) | `apps/codegen/tests/execution.test.ts` — "is read and converted exactly as the platform answers, row for row", "goes on the wire as provider_response_cost_micros, never as provider_cost_micros", "surfaces UBB's refusal of a currency it holds and the tenant does not, as the SDK's error"; `ubb-platform/api/v1/tests/test_the_renderers_fixtures_are_what_the_platform_answers.py` — `test_a_cost_read_off_a_response_is_answered_as_ruled` |
| §5 — every committed Blueprint is what the route answers, and none is added by hand | same platform module — `test_a_committed_blueprint_is_what_the_route_answers`, `test_every_committed_blueprint_is_one_this_module_produces`; `tests/contracts/test_the_renderer_suite_is_enforced.py` — `test_every_blueprint_the_suite_renders_is_one_the_platform_holds` |
| §6 — every comment is provenance or a catalogue member, and states only what the Blueprint carries | `apps/codegen/tests/artifact.test.ts` — "carries only comments that are provenance or a catalogue member", "states in a provenance comment only what the Blueprint carries" |
| §6 — a sentence for every code and verdict, and no other; each restated set equal to the registry's | `apps/codegen/tests/catalogue.test.ts` — "has remediation for every diagnostic code, and for no other", "says what every verdict means, and no other", "converts every amount representation, and no other", "says what delivering means under every pricing mode, and no other", "reads every response shape representation, and no other" |
| §8 — no file holds a host; unset or empty refuses, naming the variable, and sends nothing | `apps/codegen/tests/artifact.test.ts` — "writes no host into any file: where the API is, is read from the environment"; `apps/codegen/tests/execution.test.ts` — "holds no host of its own: with the variable unset or empty it refuses, naming it"; `apps/codegen/tests/catalogue.test.ts` — "hold no host: where the API is, is not the renderer's to say" |
| §7 — what is refused | `apps/codegen/tests/artifact.test.ts` — "refuses %s rather than writing a file that is wrong" |

## Consequences

- **Renaming a generated function, or changing how a key becomes a name, breaks tenant code.** It
  is a new renderer contract and is announced as one.
- **A second Event Type whose key differs from a selected one only in punctuation renames the
  first one's functions.** That is loud by design, and it is the price of never recording under
  the wrong Event Type.
- **Every fact the Blueprint carries is in the file as a comment.** A module is long. What it buys
  is that the provenance survives the copy that strips the console's labels.
- **The suite needs a Python interpreter.** There is no skip: a renderer whose output nobody
  compiled has not been tested.
- **A new diagnostic code, verdict, amount representation or pricing mode reddens the catalogue's
  tests** until the renderer says something about it. A new document shape is refused until the
  renderer is taught to read it.
- **A generated file does not run until `UBB_BASE_URL` is set.** One more line of setup, in
  exchange for no tenant ever sending usage to an address nobody chose.
- **The module converts money in a process UBB never sees.** The table of cases is the only thing
  that holds it to the platform, so a change to `to_micros` is a change to that table and to every
  module already generated.
