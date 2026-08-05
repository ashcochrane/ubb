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
missing oracle.

## Status: seeded, not complete

Issue #198 landed the registry as a **tracer bullet** — data, compiler, gate and
CI in one complete path — carrying a representative concept of each of the four
kinds and nothing more. The complete reconciled end-state vocabulary lands with
**#202**, and the generated consumers with **#200**, **#207** and **#208**.

## What is in here

| File | What it is |
|---|---|
| `schema.yaml` | The registry's own schema — the four kinds, and the fields each one requires or forbids. **Data, not documentation**: the compiler reads it, so it cannot drift away from what is enforced. |
| `consumers.yaml` | The surfaces a concept may name as a consumer, each with the subtree it lives in. |
| `concepts/*.yaml` | The vocabulary itself, split by domain. CI treats the directory as **one registry**: a term defined twice across files, or defined differently in two, is a failure. |

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

Validate before you commit — the same verdict CI reaches, without waiting for a
workflow:

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
4. Name its consumers, or write `consumers: []` and let it be visibly unconsumed.
5. Run `python -m tools.vocabulary`.

### Retired terms

`retired_aliases` is registry data, not a list somebody maintains by memory —
it is the declared input the forbidden-term sweep (#206) consumes. A term
retired by one concept while live in another is refused: the sweep works over
text, so it cannot both forbid and require one word.

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
