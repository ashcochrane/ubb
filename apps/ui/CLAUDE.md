# CLAUDE.md — UBB Tenant Console (apps/ui)

The tenant-facing console for UBB (usage metering, spend control, margin, billing in front of
Stripe). Lives inside the ubb monorepo; the backend contract is the committed OpenAPI snapshot —
**`src/api/schema.json` is the source of truth for everything this UI does.**

## Architecture

| Layer | Choice |
|-------|--------|
| Framework | React 19 + Vite + TypeScript (strict, `noUncheckedIndexedAccess`) |
| Server state | TanStack Query v5 |
| Routing | TanStack Router (file-based, `src/app/routes`, generated `routeTree.gen.ts`) |
| Components | shadcn-style on **Base UI** primitives (NOT Radix) + Tailwind v4 |
| Forms | React Hook Form + zod v4 |
| Charts | Recharts (monochrome tokens `--chart-1/2/3`, `--chart-grid`) |
| HTTP | openapi-fetch + openapi-typescript (generated types, gitignored `src/api/generated/`) |
| Auth | Clerk member JWT (or no-auth dev mode); same bearer seam as tenant API keys |
| Testing | Vitest + RTL + jsdom; per-feature tests + `src/app/router-smoke.test.tsx` |

## The contract, in one box

- **Bootstrap**: `GET /tenant/config` → `billing_mode` (`meter_only|prepaid|postpaid`) +
  `products[]` (`metering|billing|referrals` — the set the contract declares, held by reference
  from `src/lib/vocabulary.ts`) gate nav and pages (`useTenantConfig`, `useHasProduct`,
  `ProductGate`). There is no console `/me` endpoint.
- **`/api/v1/me/**` is the END-CUSTOMER widget portal** (different auth) — never call it here.
- **Money**: integer micros everywhere (1e6 = 1 unit); `markup_percentage_micros` is micros of a
  PERCENT. Use `src/lib/format.ts`; convert inputs with `Math.round(x * 1e6)`; no float math.
- **Pagination**: one cursor envelope `{data, has_more, next_cursor}` (limit ≤ 100, newest first,
  no totals) → `useCursorList` + `LoadMore`.
- **Errors**: RFC 9457 problem+json on ANY non-2xx (declared or not) → wrap every call in
  `unwrap()` (`src/api/problem.ts`), branch on `code`.
- **Open enums (ADR-003)**: every categorical field is an open string, and new values may appear
  without a schema change. That has not changed; what an unrecognised value *renders as* has.
- **Labels**: `resolveLabel`/`labelMap` from `src/lib/localisation.ts`, over the generated
  `*_LABEL_KEYS` maps in `src/lib/vocabulary.ts`, reading the per-locale catalogue in `src/locales`.
  **Strict — there is no fallback.** A registry value with no wording fails CI (G6) and renders an
  explicit development error; a value the registry has never seen renders **verbatim**, never
  title-cased into English UBB did not author (ADR-0008 §4.3, reversing #154 §9.1). Add wording by
  editing `src/locales/en.json`, never by writing a map. **This reverses the old "never render a
  raw snake_case token" rule** — that rule was right when the alternative was humanising it; now
  the alternative is a placeholder that discards what the server sent. Branch on `kind` to style it.
- **A value the TENANT authored** — an Event Type key, a metadata key — takes `tenantDefinedLabel`
  from the same module. The registry declares such a concept `tenant_defined` and generates no label
  keys for it (UBB must never ship a catalogue of its tenants' vocabulary), so every value resolves
  `unfamiliar` and renders exactly as they declared it. ADR-0008 §4 settles this for a value UBB has
  not *yet* met; #279 extends the same reasoning to one it was never going to meet. Not `{value}` —
  the lookup is also what renders an empty key as an absence rather than as a blank name. It returns
  text, so a surface wanting to mark the token visually calls `resolveLabel(NO_DECLARED_VALUES, …)`
  and branches on `kind` as above.
- **`src/lib/labels.ts` is the LEGACY adapter** — every value map in it is a migration debt recorded
  in `gates/migration-ledger.yaml` with an owner slice. Do not add a map to it, and do not import its
  `humanize` into a new file: both fail CI, because the ledger is the allowlist and it only shrinks.
  A concept that has been migrated leaves nothing behind but its value list, held BY REFERENCE from
  the generated module because `domain-vocabulary/` names this file as the console's consumer of it
  (`PRODUCTS` / `Product` are the worked example, #241). Don't reach here for a canonical type —
  import `TenantProduct` and friends from `src/lib/vocabulary.ts` directly.
- **A migrated concept gets its own small module** — `src/lib/products.ts` is the first: the label
  bound once (`labelMap(TENANT_PRODUCT_LABEL_KEYS)`), plus any console-owned explanatory copy beside
  it as a constant total over the generated type, so a value with no sentence is a `tsc` failure.
  Explanatory prose is NOT catalogue content (ADR-0008 §4.5) and has no label key: keys must
  decompose into a declared concept prefix and a declared value of it, both ways. **A surface binds
  the words it renders**: the module sits in that feature's `lib/` while one feature is the only
  reader (`features/events/lib/measurements.ts`) and moves to `src/lib/` the day a second feature
  renders the word (`src/lib/pricing-mode.ts`, moved in #425), because imports only flow down.
- **Canonical values**: `src/lib/vocabulary.ts` is **generated** from the repo's vocabulary registry
  (`domain-vocabulary/`) — value lists, union types and stable label *keys*, never the English.
  Import from it rather than retyping a status/kind/mode literal. Never hand-edit it: CI regenerates
  and fails on any diff (`python -m tools.vocabulary --write` at the git root). An `open` concept's
  type admits any string on purpose, so don't write an exhaustive `switch` over one.
- **Verdict bodies**: HTTP 200 ≠ success for pre-check (`allowed:false`) or usage recording (`stop`
  on `POST /metering/usage`, per-item `accepted` on its batch sibling) — branch on the body.
- **Identity**: path `customer_id` = UBB UUID; `credit`/`debit` bodies + platform routes use
  `external_id`.
- Regen after backend changes: `pnpm api:sync` (copies `../../openapi/v1.json` + regenerates types).

## Feature modules (src/features/*)

Every feature has the api sextet: `types.ts` (aliases from `@/api/types` + local interfaces for the
contract's untyped responses only), `api.ts` (real calls via the namespace clients in
`src/api/client.ts`, all `unwrap`ed), `mock.ts`/`mock-data.ts` (same signatures, realistic typed
fixtures, module-level state for coherent mutations), `provider.ts` (`selectProvider`),
`queries.ts` (ALL query keys + invalidation). `VITE_API_PROVIDER=mock|api` switches.

**An ECONOMIC STATE is composed from `src/lib/economic-scenarios.ts`** (#155 §9.4). Money and
measurement have states beyond "a number": unknown, waived, not applicable, incomplete,
indeterminate, pruned — and the types prove only that the console can *receive* one. Each scenario
returns the ambiguous fact together with the fact that disambiguates it, so a fixture cannot take
half and let a default supply the rest; `prunedMeasurements()` is the worked example. §9.2 is the
obligation with teeth: a slice that introduces or changes an economic state owes a scenario here
**and** a rendering assertion that the state renders as itself. A slice that renames a table owes
nothing.

**A fixture is not complete until a mock or a component test consumes it**, and
`economic-scenarios.reachability.test.ts` is what says so rather than a reviewer (#371). A scenario
reaching only `economic-scenarios.test.ts` proves the scenario is well-formed and nothing about the
console — the `?? 0` defect lives in a RENDERER — so a new scenario with no consumer fails on the
commit that adds it. Slice 3 left three orphaned that way and nobody noticed for two slices.

**Where a change NARROWS a type, the rendering assertion has to be on a fixture the mock does not
author.** A mock returns its own fixture object, so it narrows along with the module and the page
goes on receiving exactly what it always received: the mutation stays green across every component
test. `features/events/components/event-receipt-price.test.tsx` is the shape — provider stubbed,
detail assembled in the test, one composed scenario inside it — and it carries the mutation that
proves it.

**Two concepts can share a word.** `costing_status.known` and `pricing_status.known` are both
"Known", so a page-wide `getByText` finds two nodes and cannot say which side it found. Scope the
query to its section.

This does **not** yet reach the fixtures that were already correct. `events/api/mock-data.ts` still
hand-builds most of its measurement bags and lets `?? "available"` complete them — true for every
one of those seeds, and the reason #281 could seed the module without rewriting them. Composing
them and deleting the default would design the hazard out rather than guard it; until some slice
does, **a NON-`available` state that skips this module is a defect**, because that default is
silently wrong for exactly the two states whose bag is empty.

**Query keys**: first segment = backend namespace (`['margin', 'customers', …]`), so mutations can
invalidate every affected prefix (over-invalidate rather than miss). **Same key ⇒ same cached
shape**: shared keys cache the RAW response; projections add a tail (`['margin','customers','picker']`).

**Layering (imports flow down)**: routes → features → components → api/hooks/lib. No cross-feature
imports; no client calls from components (go through the feature's queries.ts); never edit
`routeTree.gen.ts`.

## Navigation model

```
Overview /  ·  Events /events  ·  Tasks /tasks (+ /kinds/$key · /runs · /runs/$taskId)  ·  Customers /customers
REVENUE: Pricing /pricing · Billing /billing [billing] · Plans /plans [billing] · Referrals /referrals [referrals]
PLATFORM: Webhooks /webhooks · Developers /developers · Settings /settings (+ /team /products /billing /audit)
```
Bracketed = product-gated (hidden from nav; direct URL renders `ProductGate` explanation).

## UX ground rules

Skeletons (never spinners) for initial loads; `ErrorCard` + retry for failures; `EmptyState` with a
real CTA; mutations disable while pending with visible success; destructive actions use
`ConfirmDialog` with consequence copy; secrets follow the contract exactly (API keys return-once;
webhook secrets caller-supplied write-only — no reveal affordances); long ids truncate + `CopyButton`;
plain language over backend jargon; monochrome palette with red reserved for destructive/failure.

## Verification

```bash
pnpm test          # vitest (includes the route-tree smoke suite)
npx tsc -b         # strict typecheck
pnpm lint          # eslint
pnpm build         # tsc + vite production build
```
All four must pass before handing work back.

## Git

Standard monorepo flow: feature branch → draft PR → review. (The old standalone-repo "never
commit" rule is retired.)

## History

The pre-rebuild design docs (`docs/design/*`, `docs/architecture*.md`, `docs/roadmap.md`,
`PROGRESS.md` phases 1–10) describe the mock-first standalone app and its HTML mockups. They are
frozen history — useful for UX archaeology (wizard/simulator patterns), not current truth.
