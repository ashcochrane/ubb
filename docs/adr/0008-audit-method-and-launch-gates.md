# ADR-0008: How the system is proved — machine gates, human judgement, and the acts that admit a tenant

**Status:** accepted
**Date:** 2026-08-04
**Decision record:** `docs/plans/2026-08-04-end-to-end-audit-method-decision.md` (#158) — the frozen
evidence, the full 27-gate inventory, the registry design and the Code Builder test pyramid
**Amends:** ADR-0007 §5, by splitting one admission act into two (§6); and #155 §11.4, by moving the
live-money test off the slice 8 completion gate (§6)
**Reverses:** #154 §9.1 on one point — the console's `humanize()` fallback (§4)
**Companion:** ADR-0006 owns *what things are called*; ADR-0007 owns *how they may change*; this ADR
owns *how we prove any of it is true*

## Context

ADR-0006 ends with a promise: *"Every rule above lands as a test."* ADR-0007 §5 ends with a gate:
*"Admitting the first integrator is a deliberate act, gated on the end-to-end audit passing."* Neither
says what that audit is, what it can prove, or what artifact it compares the system against.

The obvious candidate for that artifact does not work. `openapi/v1.json` declares an allowed value list
in **3 of its 165 component schemas** — deliberately, under ADR-0003's open-enum stance, which
`apps/ui/src/lib/labels.ts` restates in its own header. The console hand-writes roughly fifty value
maps. So the check the originating ticket proposed — *no name appears in the console that is not in the
spec* — has no oracle, and the repository's four documented enforcement precedents all rest on one.

The repository had also demonstrated what happens without this ADR:

- The only end-to-end money test sat in no CI job and was dead for six months, still calling a retired
  endpoint.
- Three SDK methods called routes existing in no spec and no router, green for months, because their
  tests patched the HTTP client — a mock reproduced the mistake instead of contradicting it.
- A folder named `conformance/` is excluded from the default suite and wired `continue-on-error: true`,
  so its findings can never fail a pull request.
- One vocabulary — error codes — is already machine-checkable, from a checked-in registry that the
  app, a generated SDK artifact, a test suite and the documentation all derive from.

## Decision

**Humans inspect meaning once; machines enforce every provable rule forever.**

---

### 1. A check is a machine gate only when an oracle exists

All three must hold:

```
1. An authoritative source contains the expected answer.
2. The answer can be compared deterministically.
3. The check runs repeatedly without human interpretation.
```

**Technically automatable is not sufficient.** Any subjective judgement can be encoded as a brittle
assertion once somebody hard-codes an answer, and calling that "automated" overstates what it
established. A question stays human when the answer requires judgement about **meaning, adequacy or
acceptable risk** rather than comparison against an oracle.

A machine may assemble the evidence for a judged question. It cannot manufacture the judgement.

Every human item states: the question judged, the evidence, **why no existing machine oracle settles
it**, the owner, and the conclusion. An item that cannot state the third is an unbuilt test.

### 2. The agreed model exists as a checked-in vocabulary registry

Prose is not an oracle and the spec is not the vocabulary. A machine-readable registry is **normative
for UBB-owned canonical names and values**, and sits beside this ADR rather than inside it — the ADR
carries principles, the registry carries the exact tokens.

**Four kinds, because not every string is a closed enum:**

| Kind | Consumer obligation |
|---|---|
| `closed` | exactly these values, no more |
| `open` | UBB records known values; consumers accept future and external ones |
| `tenant_defined` | the tenant owns the values; UBB defines only the field and its validation contract |
| `free_text` | not vocabulary, not registry content |

This preserves ADR-0003: a new recognised open value is not a breaking schema change merely because the
registry learned about it. An open concept keeps `type: string` in the spec and exposes recognised
values as documentation metadata (`x-ubb-known-values`) — never as a closed `enum` array. The spec
representation is generated from the registry according to the concept's kind.

**Checking open concepts is asymmetric:**

```
registry-known value missing from a UBB-owned consumer   → defect
runtime value unknown to the registry                    → legal, where the concept is open
```

The registry never enumerates tenant-created Event Types, Task kinds, Grouping Field values, provider
outcomes or free text — map #137 constraint 5 as a schema rule, so the registry cannot become the
vendor catalogue that constraint forbids.

### 3. A canonical token is authored once; every other appearance is generated or verified

Generate where practical — backend constants, frontend constants and label keys, the webhook catalogue,
SDK constants, documentation tables. Where generation is impractical, CI compares the consumer against
the registry. What is forbidden is a further hand-maintained vocabulary beside the backend, the console
and the docs.

### 4. The registry owns identity; the localisation layer owns expression

The registry generates value sets and **stable label keys**; it does not carry user-facing English.
Wording, capitalisation and translation change far more often than the token underneath, and a
vocabulary file that becomes the copy deck either turns into an i18n database or privileges English
inside the domain model. Tooltips, empty-state prose, validation explanations and onboarding copy are
never registry content.

CI proves coverage in both directions: every required registry value has a label, every label refers to
a valid registry value, no retired token remains labelled, and every supported locale carries the key.

**Silent humanisation of a canonical concept is a defect.** A missing label fails CI, and at runtime
renders an explicit development error. Deriving `"Meter only"` from `meter_only` manufactures
user-facing terminology from an implementation token — which is exactly the authority ADR-0006 spent
thirteen documents establishing. An unknown *open* value renders in a deliberate generic form, never
title-cased as though UBB authored the wording. **This reverses #154 §9.1**, which treated the fallback
as a safe degradation.

### 5. Generated code is proved by running it, unmodified

Static analysis sees names and operations. Only execution sees ergonomics — method names, imports,
idioms — and a mock can faithfully reproduce a generator's mistake rather than contradict it.

Complete artifacts are written to disk and executed against a **real ephemeral application** — router,
database and economic services — with deterministic local fixtures standing in for external providers.

> **CI may supply the code's external runtime inputs. It may not repair the code.**

Environment variables, example values and temporary identifiers are setup. Rewriting an import,
changing a method name, patching a URL, injecting a transport mock or editing a declared source path
are all repairs, and any of them voids the proof.

**Readiness is the least-ready state of every required component**, and only `complete` artifacts
execute; `incomplete` and `scaffold` artifacts are tested for diagnostics and fail-fast behaviour, never
for completion. An advisory warning does not make an artifact incomplete; a missing mandatory
declaration does.

### 6. Admission and money movement are separate acts

ADR-0007 §5 assumed one act. A tenant in `customer_billing_mode: external` bills their own customers
elsewhere and never touches a payment rail, so gating them on payment infrastructure blocks them on
something they will never use.

```
Platform admission            → customer_billing_mode = external may be enabled
  the acceptance audit passed, CI green, API and SDK baseline established,
  Code Builder execution tests passed, limitations recorded

Billing-capability activation → prepaid | postpaid may be enabled
  automated test-mode round trip, live credentials and webhooks verified,
  one controlled live-mode transaction, reconciliation and idempotency
  confirmed, runbooks owned, named approver
```

**Activation is scoped per payment rail** — `PaymentRailActivation { rail, environment, activated_at,
approved_by, evidence }` — so one successful transaction on one rail is never read as readiness for
another.

**Both a record and a flag, with an invariant between them.** The record proves why and when billing
was approved; the flag technically prevents premature use; and the invariant — *`prepaid` or `postpaid`
may not be enabled without the relevant rail activation* — is **enforced centrally, never as an
advisory console convention.**

Consequently **a live-money transaction is not a platform-completion condition.** Requiring one to
finish internal engineering turns an external commercial dependency into an artificial blocker, and
invites a payment account created to satisfy a ticket's wording. The obligation is carried as an
explicit deferred prerequisite with a reason, an owner and required evidence — never silently marked
passed.

> **Admit tenants when the capabilities they will use are ready. Activate money movement separately,
> per payment rail, before anyone depends on it.**

### 7. Test location predicts enforcement

A must-pass invariant does not live under an umbrella whose contract is informational. A suite that
gates is not excluded from the default run, is not `continue-on-error`, and does not share a directory
with best-effort probes under per-suite flags — because a reader must be able to tell from where a test
lives whether its failure is a bug or a note.

A stochastic, unseeded probe is not promoted to a gate merely because it is useful. Making one
release-critical is a separate project about determinism, reproducibility and failure triage.

### 8. Human review does not recur on a schedule

One owned acceptance audit, recorded against a named commit and API baseline, with its owner,
scenarios, evidence, the gates it relied on, and its accepted limitations. Afterwards, a focused human
review repeats **only on an explicit trigger** — a new major contract or economic model, a new payment
rail, a substantial pricing or posting redesign, a new retention model, or an incident showing the
gates missed a class of failure. Standing gates are ordinary tests: no meetings, no sign-off, no
periodic manual review.

**Whenever a human audit finds a concrete defect that could recur mechanically, it becomes a test and
leaves human review permanently.** The limit is explicit: a *semantic* question must never be converted
into a spelling test and declared settled. Converting the finding is right; converting the question is
the failure §1's third clause exists to prevent.

### 9. The sentence every acceptance record carries

> **A green CI board proves the declared invariants passed. It does not prove that the declarations
> themselves remain meaningful, complete or commercially appropriate.**

Every gate this ADR establishes is a **consistency** check. Consistency with a wrong declaration is
still green, and without this stated plainly a green board is read as evidence the model is right.

## Consequences

- **The registry becomes a build-order dependency.** It must exist before any slice renames anything,
  or the rename has no oracle. ADR-0006's rules stop being enforced by a forbidden-term search over
  prose and start being enforced against a declared source.
- **Adding a public value now means declaring its kind**, the same cost ADR-0007 §2 accepted for field
  transition classes, and for the same reason: answering "what is this, exactly?" before it ships.
- **The console gains a localisation layer it does not have today.** `labels.ts` is currently both
  identity and expression; §4 splits them, and no slice of the #155 build plan owns the split.
- **ADR-0005's `Rate.SELECTORS` invariant is replaced, not deleted.** #145 removed its subject; the
  rule it encoded survives as a registry-backed check.
- **`conformance/` is misnamed** and should later become `api_fuzzing/` or equivalent. A process whose
  own documentation states it cannot establish conformance should not hold that word.
- **The acceptance audit needs a named human**, which is an act outside this repository. ADR-0007 §5's
  point was that admission is a decision with a name on it; the repository records the role, and the
  name has to land somewhere.
- **Every gate here is a consistency check, and none can tell a correct declaration from a wrong one.**
  §9 is the entire defence, and it lives in a document rather than a gate because by construction it
  cannot live in a gate.
