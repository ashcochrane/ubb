# ADR-003 — Versioning and deprecation: the v1 compatibility contract

**Date:** 2026-07-20 · **Status:** accepted · **Decided in:**
[#67](https://github.com/ashcochrane/ubb/issues/67) (grilling session)

## Context

Today versioning is the `/v1/` path prefix and nothing else: no policy for what may change, no
deprecation mechanics, and an SDK versioned independently of the API (SDK v2.0.0 against an API
called v1). ADR-002 supplies the machinery — a committed `openapi/v1.json`, a drift gate, and an
`oasdiff breaking` gate with a suppression file — but machinery without a policy: nothing says
what the suppression file may be used for once real customers integrate, or what the public API
actually promises them. Pre-launch there is unusual freedom (house precedent: the one clean cut);
the self-serve launch (map [#60](https://github.com/ashcochrane/ubb/issues/60)) ends it. This ADR
is the policy the ADR-002 gates enforce.

## Decision

### 1. Additive-only, with deprecate-then-remove — no v2

Day to day the API only gains things. Removing or changing anything a client could depend on is
allowed, but only through the deprecation process in §4 — never silently. `/v1/` is the surface
indefinitely; a `/v2/` path is reserved for a wholesale redesign and is expected never to exist.
Pinned per-tenant versioning (Stripe-style) is rejected as machinery disproportionate to our size.

Non-breaking, may appear at any time with no notice:

- new endpoints;
- new **optional** request parameters and fields (with safe defaults);
- new response fields;
- new webhook event types;
- new values in existing status-like (enum) fields — see §2.

Breaking, requires the §4 process:

- removing or renaming anything;
- a new **required** request field, or tightening validation on an existing one;
- making a required response field optional or absent — see §3;
- changing the meaning or type of an existing field.

### 2. Unknown values are the client's job to tolerate

The published contract obliges clients to handle unknown response fields **and unknown values in
existing status-like fields** gracefully (treat as "other"). All enums are open-world; there is no
list of fields promised complete. Our own generated SDK is built to not crash on unknowns
(string-backed enums / fallback members, never strict deserialization).

Consequence for the gate: the `oasdiff` configuration must be aligned with this stance — a new
value appearing in a response enum is **not** breaking under our contract, even where the tool's
defaults flag it.

### 3. Required-where-true response typing

Any response field that is in fact always sent is marked `required` in the spec, so generated
clients (the SDK core, the UI types) type it as guaranteed-present with no null-checks. Each such
marking is a promise: walking it back is a breaking change caught by the gate. This discipline is
what makes the typed SDK worth having; the cost is a moment's thought per new field.

### 4. Deprecation mechanics: 90-day floor, docs + headers

Every deprecation gets, from announcement day:

- `deprecated: true` in the spec (visible in the docs UI and the generated SDK);
- a dated changelog entry and an email announcement;
- a runtime **`Sunset` header** (RFC 8594) carrying the shutoff date on every response from the
  deprecated endpoint — the one channel a machine notices. Implementation: a small middleware
  plus a registry of deprecated routes.

Minimum notice is **90 days**, published explicitly as a floor we may later raise but will never
lower. Usage-targeted outreach (scanning request logs to contact tenants still calling a
deprecated route) is a nice-to-have per deprecation, not a promised mechanic.

### 5. The contract binds at self-serve launch, after one final sweep

Until the first self-serve customer, breaking changes continue to land freely through the CI
suppression file, hand-coordinated with the one known tenant — the already-planned pre-launch
breaks (the [#63](https://github.com/ashcochrane/ubb/issues/63) error-model big-bang, the
[#65](https://github.com/ashcochrane/ubb/issues/65) SDK v3.0 cut) ride this lane. Immediately
before launch, one planned **final sweep** of the whole surface — names, shapes, anything we
would regret freezing — lands as the last free break, and the spec is tagged. From that tag
onward, every suppression-file entry requires the §4 process.

### 6. SDK: own semver, spec-pinned

The SDK keeps its own version line (v3.x at launch, per #65) with honest semver semantics for its
users: API additions arrive as SDK minors, SDK-only fixes as patches, SDK majors only when the
SDK's own surface breaks — which §1 should make rare. Every SDK release records the exact
committed spec revision (`openapi/v1.json` git commit) it was generated from, so any SDK build can
be tied to a contract state. The API carries no second customer-facing version number; the git
history of the committed spec is the change record.

## Consequences

- The suppression file changes meaning at launch: before, a coordination record; after, evidence
  of a §4 deprecation in flight. The launch tag is the boundary.
- Execution items implied (tickets in the execution program, not this ADR): the Sunset-header
  middleware + deprecated-route registry, `oasdiff` configuration aligned to the open-enum
  stance, the pre-launch final-sweep ticket, SDK release tooling that stamps the spec revision,
  and the public compatibility page in the docs stating §1–§4 in customer-facing words.
- Generated-client discipline cuts both ways: required-where-true (§3) is only safe because the
  breaking-change gate enforces it mechanically.
- Raising the notice floor later is free; shortening it, or breaking without the process, is a
  trust breach with a billing API — the kind of decision this ADR exists to make expensive.
