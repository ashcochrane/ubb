# ADR-002 — The OpenAPI spec is the single source of truth

**Date:** 2026-07-20 · **Status:** accepted · **Decided in:** [#64](https://github.com/ashcochrane/ubb/issues/64)
(grilling session), on the evidence of the toolchain research
([#61](https://github.com/ashcochrane/ubb/issues/61) →
`docs/research/2026-07-20-spec-as-truth-toolchain.md` on `research/spec-as-truth-toolchain`).

## Context

The self-serve launch surface (map [#60](https://github.com/ashcochrane/ubb/issues/60)) requires a
versioned REST API whose contract the typed SDK and the UI types are generated from, never
hand-maintained. Today Django Ninja generates an OpenAPI document per mount at runtime — twelve of
them, none checked in, none enforced. The hand-written Python SDK and the UI's hand-written TS
types drift silently; error responses are largely undocumented (`4xx: dict`); webhook payload
shapes have no machine-readable contract at all, and their two internal registries
(`apps/platform/events/catalog.py` + `schemas.py`) have drifted once already.

## Decision

### 1. Code-first, with a ratchet

The code generates the spec. A copy is checked in at **`openapi/v1.json`** (git root; sorted,
indented). The generator is the file's only writer — hand edits are refused in review, as
Stripe/GitHub practice. When code and document disagree, CI fails: the PR must carry the
regenerated spec, and **the spec diff in the PR is the API review**.

Spec-first (hand-authoring the contract and forcing code to conform) was rejected: ~114 routes to
hand-write, permanent dual maintenance, and it fights the framework — Ninja's design is
generation from code.

### 2. One spec via restructure — no merge script, ever

The twelve `NinjaAPI` mounts become **routers on one versioned `NinjaAPI`** (Ninja ≥1.6
idempotent routers). Per-router `auth=` preserves the current split (eleven `ApiKeyAuth`, one
`WidgetJWTAuth` on `/me`); external URLs do not change. The interim merge-twelve-documents script
the research offered as step 1 is skipped outright — the structural end-state lands first.

Prerequisites inside the restructure:

- rename the **seven Schema class names defined twice** across API modules (Ninja silently
  overwrites duplicate component schemas — the document would quietly lie about one of each pair);
- sweep `reverse()` call sites: twelve `urls_namespace`s collapse to one, with `url_name_prefix`
  per router to prevent same-named URL shadowing.

ADR-001 is respected, not amended: products expose **routers**; the composition layer
(`api/v1`, `config/urls.py`) imports and mounts them. Imports still flow composition → product,
never product → `api.*`.

### 3. Sequencing: restructure first, then the error-model conversion

The restructure is mechanical and behaviour-preserving, so it lands first; the spec is checked in
and the ratchet switches on. **Then** the [#63](https://github.com/ashcochrane/ubb/issues/63)
problem+json big-bang — the most contract-changing PR of the program — lands as a reviewable spec
diff *under the gate*, exactly when the gate matters most.

### 4. The CI ratchet — two gates at switch-on, conformance tests next

- **Drift gate:** CI regenerates the document offline (`manage.py export_openapi_schema
  --sorted`, no dev server) and fails on any diff from the committed file.
- **Breaking-change gate:** `oasdiff breaking` (official GitHub Action; OpenAPI 3.1 GA) fails the
  PR on breaking changes. A committed **suppression file** records intentional pre-launch breaks —
  accepting a break is itself a reviewed change in the same PR.
- **Conformance tests** (schemathesis in-process under pytest — the "app lies about its spec"
  catcher) are wanted but do not block the ratchet; they are their own ticket in the execution
  program.

Clients consume **the committed file, never a live server**. The UI branch's dev-server curl
script (`generate-api.sh`) is replaced by offline generation from `openapi/v1.json`; a live
`/openapi.json` endpoint cannot be diffed, gated, or reviewed.

### 5. Truth covers webhook events

The document's OpenAPI 3.1 **`webhooks`** section is generated from the existing event catalog +
frozen payload dataclasses (injected via `openapi_extra`). The 31 deliverable event types and
their payload schemas live in the same gated artifact, so catalog/`schemas.py` misalignment — the
drift class that already produced a silently undeliverable event — becomes a CI failure, and
tenants get their first machine-readable webhook payload contract. Known caveat: client codegen
does not consume the `webhooks` section yet; near-term value is documentation + gating.

## Consequences

- Every API-shape change is visible and reviewable as a spec diff; breaking changes cannot land
  without an explicit, committed suppression.
- The SDK (`ubb-sdk`) and UI types get a fixed artifact to be generated from or pinned against
  (the SDK endgame is [#65](https://github.com/ashcochrane/ubb/issues/65)'s decision, not this
  one).
- The seven duplicate-Schema renames and the `reverse()` sweep are hard prerequisites of the
  restructure PR.
- One docs UI and one `/openapi.json` replace twelve — a deliberate product outcome, not a side
  effect.
- Until the restructure lands, nothing is enforced; the ratchet's switch-on is tied to that PR by
  decision 3.
- The merge-script alternative (and Redocly `join`, openapi-merge-cli) is rejected — if the
  restructure stalls, the fallback is to reopen this ADR, not to quietly add glue.
