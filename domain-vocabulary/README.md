# The domain vocabulary registry

`domain-vocabulary/` is the checked-in, machine-readable statement of what every
UBB-owned concept is **called** and what values it may take (ADR-0008 §2). It
sits at the git root beside `openapi/` because that is the only level the
platform, the SDK and the console all reach — the same reason
`openapi/error-codes.json` lives there and already serves all three.

It exists because **prose is not an oracle**. Twenty-two decision documents fixed
this vocabulary and nothing in the repository knew about any of it, so "the
console and the API agree about what things are called" was a check nobody could
run: `openapi/v1.json` declares an allowed value list in 3 of its 165 component
schemas, by design under ADR-0003's open-enum stance. The registry is the
missing oracle — and it stays the oracle, which is why #208 gave the contract
*documentation metadata* rather than turning those 3 into 165.

## Status: complete, and deliberately at odds with the code

Issue #198 landed the registry as a **tracer bullet** — data, compiler, gate and
CI in one complete path — carrying a representative concept of each of the four
kinds and nothing more. Issue #200 added the first generated consumer, the
backend constants. Issue **#202** filled it in: the complete reconciled
end-state vocabulary, from ADR-0006 and the decision records. Issue **#207**
added the other two consumers, in the two other languages. Issue **#208** added
the published contract's known-value metadata — and, because nothing in the
tree serves a concept yet, advertised none of it: the spec states a value only
where the backend already serves it, so all twenty-nine concepts the registry
gives an `openapi` consumer are migration-ledger entries instead.

**On the day it filled in, the registry disagreed with almost the entire
codebase. That is the design** (#191 decision 1). Every value here is the one
that was decided, not the one the tree carries — because every value is already
frozen in ADR-0006 and the decision records, ADR-0007 §3 forbids parking a
public value under a temporary name, and #158 §12.1 had already applied exactly
this reasoning to the ceiling statuses. The disagreement is the migration, and
every later slice is measured by how much of it that slice deletes.

## What is in here

| File | What it is |
|---|---|
| `schema.yaml` | The registry's own schema — the four kinds, and the fields each one requires or forbids. **Data, not documentation**: the compiler reads it, so it cannot drift away from what is enforced. |
| `consumers.yaml` | The surfaces a concept may name as a consumer, each with the subtree it lives in. |
| `concepts/*.yaml` | The vocabulary itself, split by domain. CI treats the directory as **one registry**: a term defined twice across files, or defined differently in two, is a failure. |

The domains are economics, tasks, spend controls, webhooks, payment rails, and
`retired.yaml` — which holds the **surviving** names whose replacement is a
tenant-owned set or a caller's own prose, and so has no value set to sit beside.
Nothing in that file is retired; read its header before adding to it.

## What is generated from it

A canonical token is authored **here, once**; every other appearance is
generated or verified (ADR-0008 §3).

| Artifact | Consumer | Landed |
|---|---|---|
| `ubb-platform/core/vocabulary.py` | the Django platform, which **imports** the constants | #200 |
| `apps/ui/src/lib/vocabulary.ts` | the React console — value lists, union types and stable label **keys** | #207 |
| `ubb-sdk/ubb/vocabulary.py` | the Python SDK, so a value the API can return is a value the SDK can name | #207 |
| `openapi/known-values.json` | the committed tenant contract, which the spec export applies at render time | #208 |

Consumer code is never scanned for matching string literals. Each consumer
imports its generated artifact, so agreement is **structural rather than
textual** — the difference between a check a coincidence can satisfy and one it
cannot.

**The contract is the exception, and it proves the rule.** A JSON document
cannot import anything, so it holds no value by reference and the census
refuses to answer `serves(concept, "openapi")` at all. What the fourth artifact
carries is therefore not values but a **decision**: what the spec would say for
each concept, by its kind, and whether it may say it yet. A schema field names
its concept and the export supplies the values, so the platform's source still
spells nothing the registry owns. `openapi/README.md` has the rules and the
order they force on a slice.

The two Python artifacts bind the same values from one authored source and
differ only in the account each gives of itself. That is not duplication to be
tidied away: the platform and the SDK are separately installable and cannot
import each other, so each needs its own copy, and ADR-0008 §3's whole point is
that a *generated* copy is the answer and a second hand-written one is the
problem. What is forbidden is a second renderer, and there is one.

The console's artifact carries **keys, never words**, and one thing the other
two do not: `satisfies Record<…, string>` on each label map, so the console's
own compiler proves the map covers every value of its concept at the moment a
value is added here. An `open` concept's map is declared total over its KNOWN
values, never over the concept's type — that type admits any string (ADR-0003),
and a map total over `string` would be total over nothing.

Every generated artifact rides a **zero-diff regeneration check**: the committed
bytes must be exactly what the registry produces, so a hand edit or a stale
generation turns CI red instead of rotting. That is the ratchet the generated
SDK core and its registry-derived exception hierarchy already ride.

### If the SDK is ever split out of this repository

Recorded now, while it costs nothing, because the invariant is easy to lose in
the move and expensive to notice afterwards. Today the SDK is a package in this
monorepo, so its artifact is regenerated from this registry by this
repository's own CI and the check is direct. After a split there is no single
checkout holding both, and "regenerate and compare" stops being answerable in
one job.

What replaces it is two things, and **neither alone is sufficient**: the SDK's
own CI validates its artifact against a *pinned, versioned* registry artifact,
so its build is reproducible and its release is self-describing; and a
**required cross-repository compatibility job** supplies the overall verdict,
because a pin proves only that the SDK agrees with the registry it pinned — not
that the pin is current. A split that ships the first and skips the second
converts a gate into a version stamp.

Editing the registry alone is therefore never enough — regenerate in the same
commit, or CI is red:

```
python -m tools.vocabulary --write
```

## The four kinds

Not every string is a closed enum, and pretending otherwise is how a registry
becomes a catalogue of somebody else's business.

| Kind | What it obliges a consumer to do |
|---|---|
| `closed` | Exactly these values, no more. |
| `open` | UBB records the values it knows; consumers accept future and external ones. |
| `tenant_defined` | The tenant owns the values. UBB defines the field and its validation contract and **never enumerates the set**. |
| `free_text` | Not vocabulary. Recorded so the question is answered once. |

Checking an `open` concept is deliberately **asymmetric**:

```
registry-known value missing from a UBB-owned consumer   → defect
runtime value unknown to the registry                    → legal
```

That is what keeps ADR-0003 true — UBB learning about a new value is not a
breaking schema change, and an open concept keeps `type: string` in the spec with
its recognised values as documentation metadata, never as a closed `enum` array.

`tenant_defined` and `free_text` carry no values *by construction*: the schema
forbids the fields. That is map #137 constraint 5 as a schema rule — UBB cannot
quietly acquire the vendor catalogue that constraint forbids it to ship.

## Declared consumers

Every concept names the places its values actually appear, as `{surface, path}`
pairs. The compiler refuses a pair whose surface is undeclared, whose path does
not exist, or whose path sits outside its surface's root.

`consumers: []` is **legal** — the registry is normative before the code catches
up — but the key is required and the compiler reports empty ones by name. A
concept that simply omitted the key would be silently exempt from every consumer
check, which is exactly what the declared-consumer list exists to prevent.

**A declared consumer is an END-STATE consumer.** On the day this registry
landed it disagreed with almost the whole codebase, and that is the design: the
disagreement becomes the migration ledger (#201), and each later slice is
measured by how much of it that slice deletes. Proving a consumer *agrees* is a
later, deeper check — generated artifacts ride a zero-diff regeneration gate.

## Working on it

Check before you commit — the same verdict CI reaches, without waiting for a
workflow. One command answers both questions: is the registry valid, and is
every artifact generated from it current?

```
python -m tools.vocabulary
```

It exits 1 and names every reason, by code, that the registry is invalid:

```
concepts/spend-controls.yaml:plan_name: defined differently in
concepts/economics.yaml — two definitions of one term means the registry is
not an oracle
```

The gate itself is `tests/contracts/test_vocabulary_registry.py`:

```
python -m pytest tests/contracts
```

### Adding a concept

1. Put it in the domain file it belongs to, or add one. The names track the
   decision records: economics, tasks, spend controls, webhooks, payment rails,
   retired.
2. Declare its `kind` first. If you cannot say which of the four it is, that is
   the design question — answer it before writing values (ADR-0007 §3 forbids
   provisional public vocabulary, so a value cannot be parked under a temporary
   name and corrected later).
3. Write a `summary` a human would recognise. Every concept says what it means.
   It is rendered into the generated artifacts, so write it in **end-state**
   language: a summary that names a retired term plants that word in a file
   nobody may hand-edit, and the gate says so.
4. Name its consumers, or write `consumers: []` and let it be visibly unconsumed.
5. Run `python -m tools.vocabulary --write` and commit what it regenerates.

### Retired terms, and the two lists

`retired_aliases` is registry data, not a list somebody maintains by memory —
it is the declared input the forbidden-term sweep (#206) consumes. A term
retired by one concept while live in another is refused: the sweep works over
text, so it cannot both forbid and require one word.

Every entry is matched as a **whole term on identifier and word boundaries**,
never as a substring. `hold` does not forbid `threshold`; `metric` does not
forbid `usage_metrics`, which is retired in its own right. A sweep matching
substrings would have to exempt half the tree, and #154 §14 is explicit that an
over-broad exclusion silently disarms the gate.

Most terms are one snake_case token. Two concepts retire **dotted** ones — the
webhook catalogue's `<owner>.<past-tense>` names and the audit ledger's
`noun.verb` actions — and each declares the `token_pattern` that admits them, so
the form a term takes is data rather than something the sweep has to guess.

Some words are retired **in one sense only**, and those go in `retired_senses`
instead — with the sense that went, and the sense that survives:

```
limit      retired as a spend-control field word
           survives in the admission-control rejection's retry information
operation  retired as a count noun for metered work
           survives as an OpenAPI operation
job, step  retired as prose synonyms for Task and Subtask
           survive as a CI job and a CI step
ingest     retired as a selectable recording lane
           survives in `usage_ingest`, the trigger source
```

Putting those in `retired_aliases` would state something false in a normative
file, and would force the sweep into exactly the exclusions above. They are not
sweep input. They are carried, visibly and with an owner, for the one owned
acceptance audit — ADR-0008 §1: a question needing judgement about meaning
rather than comparison against an oracle stays human-judged, and an obligation
that is not a gate is recorded rather than dropped.

The compiler refuses a word that appears in both lists, and a word claimed by
two concepts in either.

### Decision rules

A few concepts carry a `value_semantics` block: the rule that decides which of
their values applies, as **data**, over named boolean inputs.

It exists because of one case. #158 §12.3 calls `ceiling_status`'s lower-bound
rule *"a spend-control safety invariant, not a naming detail"* and says it
belongs in the registry **beside the values**. A sentence in a summary is not
beside the values; it is above them, and nothing can check it.

The compiler proves each rule is **total** — every combination of its inputs
reaches an answer — and **unambiguous** — no combination reaches two. So a rule
that answers three of four cases fails here, rather than being settled by
whichever consumer meets the fourth first. `any` is how a rule says an input
does not affect the answer, and it has to be written: an omitted input is a case
nobody decided.

The generated backend module renders the rule as a comment rather than as an
importable table. The rule lives here, where the compiler already proved it;
half-importing it would invite a caller to consult two rows and infer the third.

## What is deliberately absent

Three things a reader may go looking for, and why they are not here.

- **A value set the decision records left open.** #140 §3.3's list of reasons a
  Task did not deliver is recorded there as *"illustrative, to be fixed in
  implementation"*, so it is not a decided set and ADR-0007 §3 forbids parking
  one under a provisional name. `admission_control.rate_limit_reached` and
  `indeterminate_reason` are conditional in the same way — #154 §14 records that
  the first may never be registered, and #158 §12.4 introduces the second with
  *"where useful"*. The slice that builds each one decides it.
- **A migration-ledger entry per disagreeing consumer.** #202 asks for one, and
  this is a conflict between two tickets of the same slice rather than an
  oversight — it is recorded here so the owner can reverse it rather than
  discover it. #191 §5 rule 2 asks only that an entry name a real gate and a
  real slice, which would admit these entries. #201 deliberately went further
  (its README, *"Beyond what #201 asked for"*, item 1): an entry may only name
  an **installed** gate, because a debt against a check that cannot fail
  anything is a note nothing will ever prove, clear or notice. When #202
  landed, the four gates that compare a consumer against the registry — G2, G3,
  G4, G6 — were all still owned, so the entries were inadmissible under the
  stricter rule.

  The stricter rule is kept, on its own merits and because loosening it to admit
  ~40 hand-typed entries against checks nothing runs is exactly what it was
  written to prevent. Nor is the disagreement measurable another way: #191
  decision 3 rules out scanning backend modules for matching string literals,
  because they are meant to *import* the generated module. So the entries are
  seeded by the pull request that installs each gate, per `gates/README.md` —
  which is what has since happened: **#227 installed G2 and G3 and recorded 54
  disagreeing consumers; #208 installed G4 and recorded the 29 concepts the
  contract may not advertise yet.** Only G6 is still owed, to #210, and
  `tests/contracts/test_gate_manifest.py` is what holds that last row to naming
  this registry as its input and a slice that has not landed.
- **Anything the tenant owns.** No Event Type key, Task or Subtask kind,
  Grouping Field value, instance display name, provider outcome or free-text
  description is enumerated anywhere, by construction (the schema forbids the
  fields) and by assertion over the shipped registry.

## What the registry is not

- **A copy deck.** The registry generates value sets and stable label *keys*; the
  English lives in the console's own catalogue (ADR-0008 §4). Wording changes far
  more often than the token underneath, and a vocabulary file that becomes the
  copy deck either turns into an i18n database or privileges English inside the
  domain model. Tooltips, empty-state prose, validation explanations and
  onboarding copy are never registry content.
- **Proof that the names are right.** Every gate over this directory is a
  *consistency* check, and consistency with a wrong declaration is still green.
  Whether the declarations remain meaningful, complete and commercially
  appropriate is the one owned acceptance audit's question (ADR-0008 §1).
