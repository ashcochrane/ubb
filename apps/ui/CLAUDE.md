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
- **A migrated concept gets its own small `src/lib/` module** — `src/lib/products.ts` is the first:
  the label bound once (`labelMap(TENANT_PRODUCT_LABEL_KEYS)`), plus any console-owned explanatory
  copy beside it as a constant total over the generated type, so a value with no sentence is a `tsc`
  failure. Explanatory prose is NOT catalogue content (ADR-0008 §4.5) and has no label key: keys must
  decompose into a declared concept prefix and a declared value of it, both ways.
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

**Query keys**: first segment = backend namespace (`['margin', 'customers', …]`), so mutations can
invalidate every affected prefix (over-invalidate rather than miss). **Same key ⇒ same cached
shape**: shared keys cache the RAW response; projections add a tail (`['margin','customers','picker']`).

**Layering (imports flow down)**: routes → features → components → api/hooks/lib. No cross-feature
imports; no client calls from components (go through the feature's queries.ts); never edit
`routeTree.gen.ts`.

## Navigation model

```
Overview /  ·  Events /events  ·  Customers /customers
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
