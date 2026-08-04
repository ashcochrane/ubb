# The renderer and the preview — a dependency that was never optional, and a capability that already exists

**Resolves:** [#180](https://github.com/ashcochrane/ubb/issues/180) (wayfinder:grilling), under map
[#137](https://github.com/ashcochrane/ubb/issues/137)
**Date:** 2026-08-04
**Decided against:** `main` @ `4beb0e3`
**Deferred from:** [#157](https://github.com/ashcochrane/ubb/issues/157) by
[#158](https://github.com/ashcochrane/ubb/issues/158) §13
**Builds on:**
`docs/prototypes/2026-08-04-code-builder-output-notes.md` (#157) — findings F7 and §3.6, the two
rulings this document owes, and §3.2's rule that the comments are the product.
`docs/plans/2026-08-04-generated-runtime-contract-decision.md` (#179) — §1's raising, `BaseException`
-derived stop and §1.5's authority rule, which this document renders into a language with no
exceptions. **Corrects its §9.**
`docs/plans/2026-08-04-end-to-end-audit-method-decision.md` (#158) — §5's execution pyramid, §6's
readiness aggregation, §13.1's deferral rule, which this discharges.
`docs/plans/2026-08-04-code-builder-inputs-decision.md` (#156) — §6.1's per-token classification,
§8's readiness states, §12.2's console verify stage.
`docs/plans/2026-07-31-streaming-and-long-running-calls-decision.md` (#149) — §6's deletion of the
async lane, and §6.3's retirement of the word "estimate".
`docs/research/2026-07-29-code-builder-prior-art.md` (#144) — findings 14 and 15, and §1.8's ranking
of verify surfaces. **Note: this document is on branch `research/code-builder-prior-art` and is not
merged to `main`.**
`docs/adr/0006-domain-vocabulary-and-contract-naming.md` — the naming authority.
`docs/adr/0008-audit-method-and-launch-gates.md` (#158) — §3's registry, §5's execution gates.
**Status:** decided. Planning only; implementation is out of scope for map #137.

**No ADR is written by this pass.** Every ruling lands inside an existing authority: ADR-0006 owns
the names, ADR-0007 §3 owns the new-public-surface rule that §4 satisfies by declining to add any,
ADR-0002 owns the spec surface §5's refusal lands on, ADR-0008 §3 owns the registry the reserved exit
status enters and §5 owns the execution gates §8 extends, and ADR-0008 §13.1 is the rule this
document exists to discharge. Nothing here is hard enough to reverse to justify a ninth ADR — which
is #179's reasoning, reached independently and by the same test.

---

## The decision in one paragraph

**Both of the ticket's questions dissolve on inspection, and what is left underneath is sharper than
what was asked.** The raw HTTP target was framed as a trade — pay a tool dependency and the
explanation lives in the copied text, or stay dependency-free and explain nothing. **That trade does
not exist.** A raw HTTP integration must read a stop instruction off a *successful* response, extract
a Task id that cannot be a literal, and encode tenant values into a request body; every one of those
needs a JSON parser, so the dependency is a cost of the integration and not of the comments. The
target is therefore **a runnable `curl` + `jq` shell client that declares and probes what it needs
before it does anything**, its jq programs arrive through a **quoted heredoc** — which deletes an
entire class of escaping defect rather than policing it — and #179's raising stop is rendered as a
**reserved exit status that inner helpers return and an outer boundary honours**, never an `exit`.
And the non-persisting cost preview is not built, because **the number was never missing**: UBB's
record acknowledgement already returns supplier COGS, customer price, provenance, unresolved
Measurements and the stop, synchronously, on the same 200 that records. The only property a preview
would add is that nothing is written down — and the sandbox already provides that, while
additionally proving persistence, idempotency, the Pricing Receipt, postings and stop handling,
which no preview can. Underneath both, two defects: an event naming an Event Type the environment
does not have is currently recorded as *uncosted* rather than refused, and a sandbox holds none of
the tenant's configuration — so the verify stage's headline check fires for a reason that has nothing
to do with the mapping it exists to prove.

---

## 0. The ticket's framing, corrected — twice

### 0.1 #157 F7 offered three options; the ticket carried two, and dropped the one that decides it

F7 states the constraint exactly: *"JSON has no comments, so the raw HTTP target has nowhere to put
the explanation."* It then names **three** ways out — emit `jq`, move every explanation into shell
comments above the request (*"which loses the per-token adjacency #156 §6.1 requires"*), or a plain
`curl -d '{...}'` heredoc that *"can carry **no** explanation at all"*.

#180 records the first and the third. The middle one — the only genuine competitor, because it is
safe, dependency-light and readable — is the one that went missing, and it is the option a careful
reader should have had to reject knowingly. It is rejected in §2.5, on adjacency.

More importantly, the surviving binary is false for a reason F7 could not see from inside the
question: **the `jq` dependency is not created by the explanation.** §1.1.

### 0.2 #179 §9 says this ticket is unaffected by it. It is not

> **#179 §9:** *"**#180** (renderer and preview) — unaffected. Its two rulings are independent."*

**Superseded by §3 of this document, 2026-08-04.** #179 §1 changed the stop from an opt-in return
flag to a raising signal outside the `Exception` family, and §1.5 bound it to *the outermost boundary
that can actually act on its scope*. Shell has no exceptions, and #157 §3.5 had already identified
this as *"the one place the two targets genuinely differ in **shape** rather than in syntax."* #180 is
the only ticket that decides what the shell does instead, so it inherits a contract that changed
after it was charted.

#179's text is frozen history and is not edited. The correction lives here.

---

## 1. The target is a runnable shell client, and the dependency was never the comments' fault

### 1.1 The argument that decides ruling 1

The prototype's shell target calls `jq` for four reasons, and **not one of them is explanation**:

| Where | Why a JSON parser is unavoidable |
|---|---|
| `ubb_start_report_generation` | the new Task id is read out of the response body; it cannot be a literal, because it does not exist until the call returns |
| `_ubb_handle_ack` | **the stop rides fields on a 200** (#150 §1), so the HTTP status tells you nothing; the branch cannot be taken without parsing the body |
| every request body | tenant values are encoded into JSON; `--arg` escapes them, string concatenation does not |
| `verify_integration.sh` | resolving a declared `source_path` against a captured provider response *is* a JSON query — and #157 §3.6 says this is the one thing only the emitted verifier can prove |

So "emit plain `curl` and accept no explanation" does not buy a dependency-free artifact. It buys an
artifact with **the same dependency and no explanation**. The ruling follows without weighing
explanation against tooling at all.

The alternative that genuinely escapes `jq` is to make the HTTP target non-runnable — an illustration
of the wire format rather than code. That is rejected on three grounds: ADR-0008 §5.2 already requires
*"at minimum one complete artifact per materially different renderer target — Python SDK, raw
HTTP/curl"*, so choosing it reopens a decision that landed three days ago; #157 §3.1 rejected the
walkthrough shape because a copied-once explanation rots; and grepping JSON out of a response is a
correctness trap that survives exactly until a value contains a brace, a newline or an escaped quote.

### 1.2 The target is named for what it is

**Not "curl".** The target is:

```
Shell / raw HTTP
Requires: curl, jq
```

Naming it `curl` misdescribes the artifact and hides a runtime requirement in a label.

### 1.3 Preflight by capability, before any side effect

Both tools are checked for **presence**, and then **probed for the exact non-baseline behaviour the
emitted file relies on**. Version strings are not parsed.

```sh
_ubb_check_jq() {
    command -v jq >/dev/null 2>&1 || {
        printf '%s\n' 'UBB generated shell integration requires jq.' >&2
        return 1
    }
    jq -n '
      # UBB-generated jq programs contain comments.
      {preflight: true}
    ' >/dev/null 2>&1 || {
        printf '%s\n' 'The installed jq cannot parse the generated jq program.' >&2
        return 1
    }
}

_ubb_check_curl() {
    command -v curl >/dev/null 2>&1 || {
        printf '%s\n' 'UBB generated shell integration requires curl.' >&2
        return 1
    }
    curl --fail-with-body --version >/dev/null 2>&1 || {
        printf '%s\n' 'The installed curl does not support --fail-with-body.' >&2
        return 1
    }
}

_ubb_preflight() { _ubb_check_jq || return $?; _ubb_check_curl || return $?; }
_ubb_preflight || exit $?
```

**Why capability rather than a version floor.** A floor such as `jq >= 1.6` is an indirect proxy for
what is actually needed, and `jq --version` has returned `jq-1.6`, `jq-1.7.1` and bare `1.6` across
builds and vendor backports. A probe answers the only question that matters — *can this installed
binary execute the construct the generated file is about to use?* — and stays coupled to the renderer
rather than to historical release trivia. It is the same instinct as ADR-0008 §5.1's argument that a
mock proves nothing: test the behaviour, not the label.

Four constraints on the probes:

- **They run before authentication, temporary work, or any API call**, so a missing tool cannot leave
  a half-created Task.
- **They contact no network and create nothing.**
- **No tenant content is injected into them.** They verify the renderer's syntax, not a configuration.
- **They are renderer-derived obligations, not policy.** The renderer starts using a new jq feature →
  the probe changes. The renderer stops using `--fail-with-body` → that probe is deleted. The
  renderer stops putting comments in jq → the comment probe goes. **No general-purpose dependency
  framework and no central catalogue of tool versions is created.** Two short generated checks and
  matching execution tests are the whole of it.

A minimum version may appear in the error text as installation guidance. The **capability result**,
not a parsed version, decides whether the file runs.

### 1.4 The request preview is documentation, and is not a renderer target

There is real value in showing the raw request without any tooling, and it costs nothing to keep:

```
Runnable artifact   →  complete Shell / raw HTTP file using curl and jq
Request preview     →  read-only display of method, URL, headers and JSON body
```

The preview is **documentation**. It is not one of the executable renderer targets, it carries no
readiness verdict of its own, and it never substitutes for the runnable artifact. It is rendered from
the same resolved plan, so it is not a second source.

---

## 2. The explanation sits beside the token, and the program comes from a quoted heredoc

### 2.1 The defect this fixes is live, not hypothetical

The prototype puts the comments inside the jq program, and the jq program inside a **single-quoted
shell string**:

```sh
jq -n --arg stage "$stage" '{
   # Grouping Field required at event scope. Declared values: research · drafting · review.
   grouping_fields: { stage: $stage }
 }'
```

Everything between those quotes is generated from tenant declarations — the Event Type name, the
provider, the response-shape id, the declared values, and **the object keys themselves**. One
apostrophe anywhere in that material ends the shell string early and the file dies at parse time,
before the §1.3 preflight ever runs.

And nothing stops a tenant producing one. `DimensionDef.key` is `CharField(max_length=64)` and
`DimensionValue.value` is `CharField(max_length=100)` (`apps/platform/dimensions/models.py:38,71`),
and the API bounds length only, with no pattern (`api/v1/schemas.py:782`). `client's_region` is a
legal declared key today.

The prototype survives only by accident: it contains **zero** apostrophes inside its jq programs and
exactly one outside them — `curl's`, at `ubb_integration.sh:121`, where it is harmless. Nothing
enforced that, and the generated material is precisely the part a renderer does not control.

### 2.2 The ruling

**The jq program is supplied through a quoted heredoc. The single-quoted inline form is not
retained.**

```sh
_ubb_body_openai_embeddings() {
  task_id="$1"
  response_file="$2"

  jq -n \
    --arg task_id "$task_id" \
    --slurpfile response "$response_file" \
    "$(cat <<'JQ'
{
  # Declared Event Type; supplier COGS is calculated from these Measurements.
  event_type: "openai-embeddings",

  measurements: {
    # Integer token quantity declared at usage.prompt_tokens.
    prompt_tokens: $response[0].usage.prompt_tokens
  },

  task_id: $task_id
}
JQ
)"
}
```

Because the delimiter is quoted, the shell expands nothing inside the program — apostrophes,
`$variables`, `$(commands)`, backticks and backslashes are all literal. **That removes the failure
class rather than relying on a renderer rule every future edit must remember**, which is the same
move #179 §2.2 made when it let the `Exception` hierarchy classify exits structurally instead of
maintaining an exclusion list.

### 2.3 What the heredoc does *not* fix

**It removes shell-escaping exposure only.** jq-string encoding is a separate layer and still applies:

| Material | Rule |
|---|---|
| Runtime values | always `--arg`, `--argjson`, or a file argument |
| Tenant-defined values embedded as jq strings | emitted through a real JSON/jq string encoder |
| Tenant-defined object keys | **quoted, or constructed from an argument** — never assumed to be a valid bare jq identifier |
| Free-text tenant descriptions | never placed directly into jq comments (§2.4) |

So this is wrong for an arbitrary declared key:

```
my-custom-key: $value
```

and this is right:

```
"my-custom-key": $value
```

### 2.4 Comments carry canonical metadata, never tenant prose

Comments are generated from **UBB-controlled canonical metadata** — the Measurement name, the source
path, requirement status, the costing method, publish dates. **Unrestricted tenant prose never enters
a comment.**

This is required by #157 §3.2's own rule (*no comment may assert a fact the plan does not carry, and
no comment may be hand-written per template*), and it has a second effect that matters here: because
the heredoc's contents are drawn from controlled generated text, **a delimiter collision cannot arise
from arbitrary tenant input.** The renderer does not have to defend a terminator against a
tenant-supplied string, because no tenant-supplied string reaches it.

### 2.5 Two altitudes of comment, one source — and why the shell-comments-only option loses

Adjacent comments stay short and specific to the token they sit on:

```
# Required Measurement; source path: usage.prompt_tokens.
prompt_tokens: $response[0].usage.prompt_tokens
```

Wider explanation — why reported costing differs from calculated, how the stop works, how to
configure an Event Type — lives **above the function and in the file header**. The jq program is not
turned into a documentation page.

```
Adjacent comment     →  explains this exact generated token
File-level comment   →  explains the broader integration behaviour
```

This is not the two-source problem the map has rejected repeatedly, because both are generated from
the same resolved plan and have distinct purposes.

**And this is what rejects F7's missing third option.** Moving *every* explanation above the request
is safe and readable, and it can still say everything the header says. What it cannot do is put
`# Integer token quantity declared at usage.prompt_tokens.` on the line of the field it describes —
and per-token adjacency is exactly what #156 §6.1 requires and what #157 §3.3 argued shapes beat
markers *for*. Rejected on adjacency, not on safety.

---

## 3. The stop returns a reserved status; the boundary honours what it can

### 3.1 What it has to render

#179 §1 flipped the SDK stop to raise by default and moved it outside the `Exception` family, so a
tenant's own catch-all cannot swallow it. §1.5 then bound the handling to *the outermost boundary that
can actually act on its scope*, **never inside a per-call helper**, because `stop_scope` may be
`customer` and a helper that knows about one call has neither the authority nor the context to halt
everything for that customer.

Shell has no exceptions. The rule survives anyway, because **#179 §1.5 is about authority, not
syntax**, and authority is language-independent.

### 3.2 The ruling

**The record helper returns a distinguished stop status. A generated outer boundary interprets its
scope and reason, stops the work it controls, and returns the same status to the process.**

```
record helper
  → event recorded successfully
  → response requests a stop
  → set stop metadata
  → return 20

unit-of-work boundary
  → observe 20
  → stop new local dispatch
  → log scope and reason
  → return 20

process / supervisor
  → observe 20
  → apply any wider Task or customer action
```

**Inner helpers never call `exit` for this condition.** They return, so the outermost generated
boundary capable of acting on the scope gets the decision. `exit` from a helper collapses every scope
into "kill this process", makes a `task` stop and a `customer` stop indistinguishable in effect, and
kills the terminal of anyone who sourced the file — a rough edge #157 §3.3 had already flagged for
`${VAR:?}`.

**The boundary never converts the status to success after logging it.** If it cannot fully honour the
scope itself — particularly a customer-wide stop — it returns 20 so a calling worker or supervisor can
take the broader action. This is #179 §1.5's *"if nobody handles it, letting it escape is safer than
silently continuing to spend"*, in a language where escaping means an exit status.

The literal is never scattered through generated code:

```sh
UBB_EXIT_STOP_REQUESTED=20
...
return "$UBB_EXIT_STOP_REQUESTED"
```

**20 is public contract.** It avoids success, ordinary failure (`1`, `2`), the shell's
command-not-found and signal-derived range, and the 64–78 `sysexits.h` block the prototype already
draws `78` from for missing configuration. Once published it is part of the shell renderer's
compatibility surface, and it enters ADR-0008 §3's registry as a named concept with a value:

```
spending_stop_requested
  shell_exit_code: 20
```

### 3.3 `set -e` is not the mechanism

Propagation is **explicit**. Every non-zero status is inspected or deliberately passed on:

```sh
#!/usr/bin/env sh
set -u

UBB_EXIT_STOP_REQUESTED=20

_ubb_do_work() {
    _ubb_record_usage
    status=$?
    if [ "$status" -ne 0 ]; then
        return "$status"
    fi
    # Start further work only after the acknowledgement was handled.
    return 0
}

_ubb_run_unit_of_work() {
    _ubb_do_work "$@"
    status=$?
    case "$status" in
        0) return 0 ;;
        "$UBB_EXIT_STOP_REQUESTED")
            printf 'UBB requested a spending stop: scope=%s reason=%s\n' \
                "${UBB_STOP_SCOPE:-unknown}" "${UBB_STOP_REASON:-unknown}" >&2
            # Stop any work this process controls.
            # Preserve the status for the external supervisor.
            return "$UBB_EXIT_STOP_REQUESTED"
            ;;
        *) return "$status" ;;
    esac
}
```

`set -e` behaves differently around functions, conditionals, `||` chains and command substitution, and
across shells. Relying on it produces either a **swallowed stop** or an unrelated command aborting
before the boundary can interpret anything. Neither failure is acceptable for the branch that exists
to stop spending, and neither is visible in a passing test.

### 3.4 The stop-producing path is never called through command substitution

```sh
ack="$(_ubb_record_usage)"        # forbidden on this path
```

Command substitution runs in a subshell in common shells, so `UBB_STOP_SCOPE` and `UBB_STOP_REASON`
may never reach the boundary that has to log and act on them, and it makes non-zero status handling
easy to neutralise by accident.

The helper is called **directly**. Response bodies travel through a temporary file, a supplied output
path, or carefully separated file descriptors.

**This invalidates the prototype's shape**, which is command-substitution throughout —
`ubb_integration.sh:165` and `verify_integration.sh:91`. Recorded as D3 in §9.

### 3.5 The boundary acts only within its authority

```
Task scope       → stop the current Task's remaining dispatch
Customer scope   → stop all customer work controlled by this process
                 → return 20 so an external supervisor can stop work elsewhere
```

A single generated shell process cannot guarantee that every other worker serving the same customer
has stopped, and **must not claim otherwise**. The retained exit status is how it escalates the
instruction rather than pretending to have executed it.

Task-scoped and customer-scoped stops produce the same process status and stay distinguishable
through the structured metadata. The status says *a stop happened*; the metadata says *how far it
reaches*.

---

## 4. The cost preview is not built, because the number is not missing

### 4.1 UBB is not in Lago's position

#144 finding 14 rates Lago's `POST /events/estimate_fees` — computed fees returned without persisting
the event — *"the highest-value verify surface that exists"* for a metering platform, and notes almost
nobody has it. #157 §3.6 carried that forward as the one thing that would let the emitted verifier
check *the number* rather than the plumbing.

**Lago needs that endpoint because Lago cannot tell you a fee at ingestion time.** Its events are
ingested asynchronously and fees are computed against an invoice period; there is no acknowledgement
to read a number off, so a separate non-persisting call is the only way to see one.

**UBB already returns the number on the record call.** `RecordUsageResponse`
(`api/v1/schemas.py:139-180`) carries `provider_cost_micros`, `billed_cost_micros`,
`pricing_provenance` and `uncosted_metrics`, synchronously, on the same 200 that records the event.
That is not incidental: #149 §6 **deleted** the async lane specifically so there is one path and it
returns a settled number rather than an estimate, and ADR-0003 deleted tiered pricing, so a single
event's price has no dependence on period aggregates — #149 §6.3's *the price is the price*.

| | What a preview adds over today's acknowledgement |
|---|---|
| The computed supplier COGS | nothing — already on the ack |
| The computed customer price | nothing — already on the ack |
| Which rate matched | nothing — `pricing_provenance` is already on the ack |
| Which Measurements failed to cost | nothing — `uncosted_metrics` is already on the ack |
| **No event is persisted** | **this, and only this** |

So ruling 2 is not *"should UBB be able to tell you what an event costs"*. It is the much narrower
*"is non-persistence worth new public surface"*.

### 4.2 The ruling

**No public non-persisting cost preview in v1.** Code Builder verification records a genuine event in
the sandbox and inspects the acknowledgement.

That is not a compromise, it is the stronger check. Recording proves, together:

```
payload accepted
Measurements extracted correctly
supplier COGS resolved
customer price resolved
Pricing Receipt created
posting persisted
spend-control acknowledgement returned
idempotency works
```

A preview would prove only the calculation. **It would omit most of what the verify stage exists to
verify** — which inverts #157 §3.6's own argument for it.

The console verify stage renders that acknowledgement plainly, and names the environment:

```
Verification succeeded

Supplier COGS:       £0.00123
Customer price:      £0.00148
Costing status:      resolved
Pricing status:      known
Pricing Receipt:     pr_...
Stop requested:      false

Sandbox verification — creates sandbox records only and cannot affect production billing.
```

If sandbox test data is later judged undesirable, that is solved through sandbox isolation or explicit
test-data filtering, **never by adding a second economic call**.

### 4.3 Why "run the calculation but skip the insert" is not free

Four reasons, and they compound:

- **It is not authoritative.** #148 made the persisted Pricing Receipt authoritative. A non-persisted
  answer has no durable receipt and cannot explain what was ultimately billed. Between preview and
  recording a pricing publish may become effective, a customer override may change, an unresolved
  rate may be repaired, the effective time may differ, or spend-control state may move — so the
  recorded answer may legitimately differ from the preview, and nothing would record why.
- **It cannot honestly reproduce every economic effect.** Customer spend Pool state, wallet drawdown,
  invoice totals, fixed-price Task delivery, concurrent events, stop decisions, taxes and
  period-level calculation are not properties of an isolated event. On a fixed-price Task in
  particular an event may carry supplier COGS and no event-level customer revenue at all, so a generic
  *"what would this event cost?"* is read as answering more than it does.
- **It risks a second pricing path.** Unless it invokes precisely the same kernel it will eventually
  disagree, and even sharing the kernel it needs its own contract, permissions, SDK method, Code
  Builder output, tests, status semantics and documentation.
- **It is new public surface**, so ADR-0007 §3 applies in full — for a capability whose central
  result is already returned after recording.

### 4.4 Deferred, not adopted — the constraints, and deliberately no names

Recorded so a later reader knows the shape was seen and set aside, not missed. **Nothing here reserves
a name.**

Any future non-persisting evaluation must:

- use the **exact recording calculation kernel**;
- accept an explicit effective time and a configuration revision;
- create **no** event, posting, Pricing Receipt or Charge;
- change **no** Pool, wallet or spend-control state;
- return an explicitly **provisional** result;
- **name everything it does not simulate**;
- never promise that the later recorded result will match.

And it must not be conflated with a different product:

```
Event evaluation      →  how would the published rules evaluate this exact payload,
                         at this effective time, persisting nothing?

Financial simulation  →  what would this activity do to an invoice, wallet, Pool,
                         tax total or customer affordability?
```

A single endpoint must not quietly claim to answer both.

**Two naming constraints, and no name chosen:**

1. **"Estimate" stays retired in this context**, and for a stronger reason than style. ADR-0006
   retired the word; #149 §6.3 retired it *substantively* — *"The word 'estimate' is now a
   misnomer"* — because the compute spine is the same one that charges, so nothing about the number
   is estimated.
2. **"Evaluate" is already spoken for.** #158 §12 uses evaluation throughout for **ceiling**
   assessment: `within_ceiling` is defined as *"every applicable cost needed for the evaluation is
   resolved"*, and `indeterminate` means *"we tried and could not tell, never there was nothing to
   evaluate"* (§12.2, §12.4). Reusing it for pricing computation would put one public word on two
   unrelated things in the same product — the collision class #179 §8 caught with `outcome`.

Any concrete route or response shape that appears in discussion of this capability is **illustrative
only — unapproved, non-normative, and not name-reserving.** The public vocabulary is left undecided,
and is decided if and when a real customer workflow requires a pre-commit answer.

---

## 5. Two failures that must never be one

A defect found while deciding §4, and it is a category error rather than a bug in any one line.

An event naming an Event Type that does not exist in the receiving environment is **not an event with
unresolved costing. It is an invalid reference.**

```
Unknown Event Type
  → UBB cannot know what the event means
  → refuse the request; persist nothing

Known Event Type, cost cannot resolve
  → UBB understands the event
  → record it with the appropriate unresolved costing state
```

Today the second swallows the first. `require_cost_card_coverage` defaults to `False`
(`apps/platform/tenants/models.py:71`), and with it off a Measurement with no matching cost rate does
not error — it lands in `uncosted_metrics`, contributes 0, and the event records successfully
(`apps/metering/pricing/services/pricing_service.py:130-143`).

**The ruling: an event referencing an Event Type unavailable in the target environment is refused at
validation and never persisted as an uncosted event.**

```
422 event_type_not_available

Event Type `openai-embeddings` is not available in this sandbox
configuration. No event was recorded.
```

That gives a developer a truthful diagnosis instead of telling them a declared Measurement or source
mapping is wrong. **This is established now regardless of how sandbox configuration is ultimately
supplied**, because it is a correctness rule about what UBB accepts, not a verification convenience.

---

## 6. The sandbox cannot verify what it does not have

### 6.1 The gap

§4.2 routes verification through the sandbox. The sandbox does not carry the tenant's configuration.

- `get_or_create_sandbox` creates a **sibling Tenant row** and copies exactly four fields — `products`,
  `billing_mode`, `default_currency`, `require_cost_card_coverage`
  (`apps/platform/tenants/services/sandbox_service.py:38-48`). No Task kinds, no Event Types, no
  Measurements, no Grouping Fields, no Cost Rates, no pricing configuration, no ceilings.
- Its own docstring says why that is total: *"every domain model is tenant-scoped, [so] a sandbox
  tenant gets isolation… automatically."*
- **Nothing anywhere reads `parent_tenant` to fall back to the live catalogue.** The only references in
  `apps/` are the model, its constraint, and the provisioning service.
- `reset_sandbox_tenant_sync` defaults to `keep_config=True` (`apps/platform/tenants/tasks.py`), which
  only makes sense if sandbox configuration is expected to be sandbox-resident and tenant-maintained.

**The consequence is worse than an empty environment.** The artifact is generated from the *live*
published configuration and refuses to run without a *sandbox* key, so the two are guaranteed to be
different tenants — and §5's defect means the mismatch surfaces as unresolved costing rather than a
refusal. The prototype's verify script asserts `costing_status == resolved` and tells the developer, in
the copied text, that anything else *"means a required measurement did not arrive under its declared
name"* (`verify_integration.sh:92-93`). **An unconfigured sandbox produces exactly the symptom the
verifier exists to detect.** The one check #157 §3.6 says only the emitted verifier can perform is also
the check most likely to fire for an unrelated reason.

### 6.2 The ruling — an immutable, disposable verification snapshot

**This is an owned dependency, blocking the verification portion of the Code Builder build work under
ADR-0008 §13.1. It is not optional cleanup.** The verification flow cannot be called complete while a
tenant would have to rebuild their catalogue by hand before it means anything.

The invariant to satisfy is narrow:

> **The generated artifact and its verification run must use exactly the same resolved configuration.**

The mechanism is a **verification snapshot** derived from the Code Builder's Resolved Contract:

```
Resolved verification snapshot
  Task and Subtask kinds used
  Event Types and Measurements used
  required Grouping Fields
  relevant Cost Rates
  applicable pricing rules
  applicable ceilings
  source mappings
  content hash / snapshot id
```

```
1. Code Builder resolves the selected contract
2. it creates an immutable verification snapshot
3. generated code is stamped with that snapshot id or hash
4. the ephemeral sandbox materialises that exact snapshot
5. verification runs against it
6. the sandbox data and the materialisation are discarded
```

Verification checks the snapshot resolves **before creating a Task or any other side effect**, and
refuses with an explanation if it does not. That also closes a race the gap would otherwise leave
open: the builder generating against one configuration and the sandbox evaluating against another.

### 6.3 What the snapshot is not

```
not editable
not independently published
not continuously copied
not a competing source of truth
not retained as tenant configuration
```

It is a **derived test fixture** representing precisely what the builder resolved at that moment. This
matters because a copy-on-publish mirror would create a second, drifting copy of the configuration —
and #157 §3.7 published a table asserting that names *cannot* drift precisely because *"there is no
second copy to disagree."* The snapshot is read-only, non-authoritative and discarded, so that table
survives.

**And it must not be oversold.** The snapshot guarantees one thing: *this generated artifact was
verified against this exact resolved configuration.* It does not give Task Types and Event Types a
durable user-facing publication history.

### 6.4 The second dependency, separately owned and not blocking

Whether **Pricing Book Publish**, **Event Type publishing** and any future **Task Type** lifecycle
should become one catalogue-wide immutable publication mechanism is a real question and is **not**
blocking.

It is already recorded twice. #156 residue 2: *"A second publish mechanism now exists… Whether that is
the same mechanism generalised or a second one is **undecided**."* And #151's residue, *"narrowed, not
closed"* — Event Types gained a publish concept and Task Types still have none. #148 §4.7 supplies the
direction if it is ever taken up: the publish record is *"the only cross-reference that means the same
thing forever… because a publish record is immutable by construction."*

**It is deliberately not forced here.** Answering it inside a sandbox ticket would make verification
responsible for settling the platform's whole publication architecture, and would reopen publishing
for Task Types, Event Types, pricing, ceilings, Measurements and Grouping Fields at once. The snapshot
leaves the path open: if a unified publication record later exists, the snapshot derives from it
instead of from individually resolved objects.

---

## 7. What the Shell / raw HTTP target looks like after all four rulings

| | Before (#157 prototype) | After |
|---|---|---|
| Target name | "http / curl" | **Shell / raw HTTP · requires curl, jq** |
| Dependency | a cost attributed to comments | a cost of parsing responses at all; comments ride along free |
| Dependency check | none | presence **+ capability probe**, before any side effect |
| jq program | single-quoted inline; one tenant apostrophe breaks the file | **quoted heredoc**; shell expands nothing |
| Tenant keys/values | interpolated into program text | `--arg` / encoder / quoted keys |
| Comments | tenant-derived text inline | **canonical metadata only**, two altitudes, one source |
| Stop | `return 3` from the record helper, no boundary | reserved `20`, returned to a **generated boundary** that logs scope and escalates |
| Stop propagation | `ack="$(...)" \|\| return $?` | explicit status checks; **no command substitution on this path** |
| Response reading | `jq` ad hoc | structural only — `--fail-with-body`, `jq -er`, never grep/sed |
| Cost preview | proposed as the missing verify surface | **not built** — the number is already on the ack |

The net effect is that the shell target stops being the weaker sibling of the Python one. Python gets
its guarantees from the language — a required parameter, a `BaseException` that a catch-all cannot
eat. Shell gets them from **structure**: a preflight that runs before anything, a quoting construct
that cannot be broken by data, and a status that survives to the process.

---

## 8. The tests that pin this

On ADR-0006's *prefer backing any hard rule with a test* footing, extending ADR-0008 §5's pyramid.

**Renderer — escaping and structure**
1. declarations containing an apostrophe (`customer's`) render and execute unchanged
2. …a dollar sign (`$value`) — no shell expansion occurs inside the heredoc
3. …command-like text (`$(touch file)`) — nothing is executed
4. …backticks, backslashes, Unicode, hyphenated keys and permitted spaces
5. dynamic values are supplied **only** through jq arguments
6. generated object keys are valid jq — quoted where not bare identifiers
7. the heredoc delimiter cannot be produced by generated comment text
8. every emitted comment line matches a provenance form or the closed catalogue (#157 §3.2), in both
   comment altitudes
9. the emitted script passes shell parsing and runs against the CI server

**Preflight**
10. jq absent → refusal before any request, Task or temporary work
11. curl absent → same
12. jq present but cannot parse the generated program shape → refusal, with the installation hint
13. curl present without `--fail-with-body` → refusal
14. the probes contact no network and create nothing
15. minimal-image fixtures for missing **and** incompatible tools

**The stop**
16. record helper returns 20 → the outer boundary observes it
17. the boundary logs scope and reason and returns 20 — **never 0**
18. an ordinary API or parsing failure preserves its own non-zero status
19. command substitution is not used on the stop-producing path
20. Task-scoped and customer-scoped stops produce the same process status and stay distinguishable
    through structured metadata
21. the deliberate ceiling-crossing scenario in CI **expects exit 20**, not an unexplained failure

**Response handling**
22. malformed JSON → clear failure, no partial workflow
23. a missing required response field → clear failure
24. non-2xx → `--fail-with-body` surfaces the body
25. a stop inside a successful 200 is acted on

**Configuration and verification**
26. unknown Event Type → validation refusal, **no event persisted**
27. known Event Type, missing required Measurement → payload validation refusal
28. known Event Type, valid payload, missing Cost Rate → unresolved **or** refused per the declared
    cost-coverage policy
29. verification snapshot unavailable in the sandbox → refusal **before** starting a Task
30. matching snapshot → the event records and the real acknowledgement is checked

Test 28 exists because fixing the unknown-Event-Type case alone would still leave the other failures
reported as mapping errors.

---

## 9. Live defects found while deciding

**D1 · An unknown Event Type records as uncosted instead of being refused.** §5. A category error, not
a bug in one line: `require_cost_card_coverage` defaults `False`
(`apps/platform/tenants/models.py:71`) and the uncosted path is the fallback
(`pricing_service.py:130-143`). It makes an invalid reference indistinguishable from a real costing
gap.

**D2 · A sandbox holds none of the tenant's configuration, and the verify stage reads that as a mapping
bug.** §6.1. `sandbox_service.py:38-48` copies four tenant-level fields; nothing reads `parent_tenant`
for configuration. The artifact is generated from live and run against sandbox by construction.

**D3 · The prototype's stop path runs through command substitution.** §3.4.
`ubb_integration.sh:165` and `verify_integration.sh:91`. Under §3.2's variable-carried metadata the
subshell loses `UBB_STOP_SCOPE` and `UBB_STOP_REASON` before the boundary can act on them.

**D4 · The prototype's inline jq program is apostrophe-fragile against unvalidated tenant names.**
§2.1. Tenant keys and values are length-bounded only (`apps/platform/dimensions/models.py:38,71`;
`api/v1/schemas.py:782`). The file survives by containing zero apostrophes inside its jq programs and
one outside (`ubb_integration.sh:121`).

**D5 · #157 F7's binary was false.** §0.1. The `jq` dependency is a cost of reading responses, not of
explaining lines — so the trade the ruling was framed around never existed. Recorded because the same
inversion is easy to repeat for a future TypeScript target.

**D6 · #144's research document is not on `main`.** It lives on branch
`research/code-builder-prior-art` @ `cf3232c`. Eight decision documents in this map cite it as a
source, including this one. Not a code defect; a provenance one, and cheap to fix.

---

## 10. Vocabulary owed

| Name | Standing |
|---|---|
| `spending_stop_requested` + `shell_exit_code: 20` | **new.** Public contract for the Shell / raw HTTP target; enters ADR-0008 §3's registry under ADR-0006's authority |
| `UBB_EXIT_STOP_REQUESTED` | the emitted symbolic constant carrying the value above |
| `event_type_not_available` | **new** refusal code (§5) |
| A non-persisting evaluation | **deliberately unnamed** (§4.4). "Estimate" stays retired; "evaluate" collides with ceiling evaluation; nothing is reserved |
| the verification snapshot | **owed** — its public identity, if it has one, belongs to the dependency in §6.2 |

The forbidden-term sweep ADR-0006 §*Consequences* already runs was applied to this document before
posting, which is #157's method note and #179 §8's practice.

---

## 11. Constraints this imposes on other tickets

- **Code Builder build work** (still unassigned — #156 residue 1, #158 §16) — inherits all of §1–§3
  as renderer requirements, §8's thirty tests, and §6.2 as a **blocking dependency for the
  verification portion specifically**. The rest of the builder is not blocked by it.
- **Slice 2 (measurement & catalogue)** — §5's refusal is a model and API rule: an Event Type
  reference that does not resolve in the environment is refused, never recorded as uncosted. Tests 26
  and 27.
- **Slice 3 (cost)** — test 28's boundary between *refused* and *unresolved* is set by the declared
  cost-coverage policy, and `require_cost_card_coverage`'s default is now load-bearing for a
  diagnosis, not only for strictness.
- **Slice 6 (spend control)** — the stop's shell rendering is public contract. Exit status 20 ships
  with the renderer and is versioned with it.
- **ADR-0008 §5** — the execution matrix gains the Shell / raw HTTP target's minimal-image fixtures
  (tests 15, 21). The CI image pins tool versions, so **capability skew is structurally invisible to
  CI** — which is exactly why §1.3's probe is generated into the artifact rather than asserted in the
  suite.
- **#179 §9** — its "#180 unaffected" line is superseded by §3 (§0.2).
- **#156 residue 2 / #151 residue** — restated as a named, separately owned, **non-blocking**
  dependency (§6.4) rather than left as residue.
- **The console** — gains the verify-stage rendering of §4.2 and the environment banner; gains the
  read-only request preview of §1.4.

---

## 12. Residue, flagged not buried

1. **The heredoc incantation has not been executed.** `jq` is not installed on the machine this was
   decided on. `jq -n "$(cat <<'JQ' … JQ)"` and the alternative `jq -n -f /dev/stdin <<'JQ'` both need
   running once against the supported shell and container matrix before either is emitted. The
   *ruling* — quoted heredoc, not single-quoted inline — does not depend on which form wins.
2. **No claim is recorded about jq version behaviour.** A suspicion that jq changed comment lexing
   between releases could not be verified here and is **deliberately not written down as fact**. §1.3's
   probe makes the question moot by testing the property instead of the version.
3. **Sandbox catalogue population is unresolved** (§6.2) and blocks verification only. Owner needed.
4. **Catalogue-wide publish identity is unresolved** (§6.4) and blocks nothing. Owner needed
   eventually.
5. **The verification snapshot's lifecycle is undesigned** — how it materialises into an ephemeral
   sandbox, how the existing `reset_sandbox_tenant` machinery relates to it, and how it is discarded.
   That belongs to the dependency in §6.2, not here.
6. **`derived` source kinds and the shell target.** #179 §3.3 permits `derived` as *"a named,
   declarative transformation"* with no vocabulary designed. Whether such a transformation is
   renderable in jq at all is unknown, and could make an Event Type Python-only in the way #157 F8
   already showed for response shapes.
7. **The TypeScript target will re-pose §0.1's question and must not re-inherit its false binary.**
   Ask first what the *runtime* needs, then whether the explanation costs anything on top.
8. **Test data in the sandbox is accepted, not solved.** §4.2 routes verification through real
   records. If that is later judged undesirable, the answer is isolation or filtering — a second
   economic call is ruled out here.
