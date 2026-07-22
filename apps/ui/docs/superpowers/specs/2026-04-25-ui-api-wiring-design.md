# UI ↔ API Wiring — Replace Mocks with Real API + Inline Placeholders

**Status:** Design
**Branch:** `feat/ubb-ui-dashboard`
**Date:** 2026-04-25

---

## Goal

Connect the `ubb-ui` frontend to real `ubb-platform` endpoints wherever the
backend already supports it, and replace the mock-data scaffolding with
a clear "Backend not yet available" experience for every feature whose
endpoints have not been built yet.

The user wants:
1. To wire up everything that *can* be wired up now.
2. To stop using mock data anywhere.
3. To leave unfinished UI features visible (not deleted) with clear,
   findable markers so the path back to them is obvious.

## Non-goals

- Building any new platform-side endpoints (orphans, reconciliation, margin
  hierarchy, generic export) — those are tracked separately and unblock
  follow-on UI work.
- Restructuring the per-feature `api/` folder layout. The provider/mock
  indirection is removed but the folder shape stays.
- Changing tests beyond what the wiring change requires.

## Decisions (confirmed with user)

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Remove the mock provider system entirely | "Move completely away from mocks" |
| 2 | Inline placeholders for partially-wireable pages (billing, export) | Better visible "what's coming" signal than hiding |
| 3 | Drop `VITE_API_PROVIDER=mock` no-auth dev mode | Devs always run Clerk |
| 4 | Surgical replacement, not folder restructure | Avoid destabilising 7 already-wired features |

## Architecture changes

### Remove

- `src/lib/api-provider.ts` — entire file (`selectProvider`, `mockDelay`,
  `API_PROVIDER`, `ApiProvider` type).
- Per feature: `mock.ts`, `mock-data.ts`, `provider.ts` from `auth`,
  `billing`, `customers`, `dashboard`, `events`, `export`, `onboarding`,
  `pricing-cards`, `reconciliation`.
- `VITE_API_PROVIDER` env var (remove from `.env.example`, README, docs).
- The no-auth dev bootstrap path keyed on `VITE_API_PROVIDER=mock`
  (Clerk becomes mandatory for local dev).

### Add

**`src/lib/api-errors.ts`**

```ts
export class ApiNotImplementedError extends Error {
  readonly endpoint: string;
  readonly docsRef?: string;
  constructor(endpoint: string, docsRef?: string) {
    super(`API not implemented: ${endpoint}`);
    this.name = "ApiNotImplementedError";
    this.endpoint = endpoint;
    this.docsRef = docsRef;
  }
}

export function isApiNotImplementedError(
  e: unknown,
): e is ApiNotImplementedError {
  return e instanceof ApiNotImplementedError;
}
```

**`src/components/shared/not-implemented.tsx`**

Two variants exported from one file:

- `<NotImplementedPage endpoint docsRef? />` — full-page placeholder.
- `<NotImplementedSection endpoint docsRef? compact? />` — inline banner
  sized to fit a card or table column.

Both render: muted-bg card, icon (Lucide `Wrench` or `Construction`),
headline ("Backend coming soon"), supporting line referencing the
endpoint in monospace, and optional doc link.

### Edit

- Each feature's `queries.ts` imports from `./api` (was `./provider`).
- Each feature's `api.ts`:
  - For unfinished endpoints, throws `ApiNotImplementedError` with the
    expected URL string; precede with `// TODO(api):` line referencing
    the spec.
  - For wired endpoints, leaves the existing `openapi-fetch` call in
    place.
- Each consuming component branches on the query error: if
  `isApiNotImplementedError(error)`, render the placeholder; otherwise
  fall through to the normal error state.

## TODO marker convention

All placeholder code is preceded by a single-line comment:

```ts
// TODO(api): <method+path> — see docs/superpowers/specs/2026-04-25-ui-api-wiring-design.md
```

Findable with `rg "TODO\(api\)"`. PROGRESS.md keeps a canonical list of
endpoints still pending. No pre-commit enforcement — convention only.

## Per-feature wiring matrix

| Feature | Outcome | Detail |
|---------|---------|--------|
| `dashboard` | Already wired | Delete mock files. No behavioural change. |
| `pricing-cards` (cards + rates CRUD) | Already wired | Delete mock files. No behavioural change. |
| `pricing-cards` → reconciliation child route | **Page placeholder** | Reconciliation `api.ts` throws on every method. Route renders `<NotImplementedPage endpoint="GET /api/v1/metering/rate-cards/{id}/reconciliation" />`. |
| `customers` basic CRUD | Already wired | Delete mock files. No behavioural change. |
| `customers` → mapping/orphans tabs | **Inline placeholders** | Mapping table + orphan list each render `<NotImplementedSection>` with the expected endpoint. Customer CRUD continues to work. |
| `groups` / `products` | Already wired | Delete mock files. No behavioural change. |
| `events` list/push/audit | Already wired | Delete mock files. No behavioural change. |
| `events` CSV export | **Wired** | Confirm `api.ts` calls `POST /api/v1/platform/events/export`. |
| `billing` margins page | **Partial — inline placeholders** | Stats card "default margin" → `GET /api/v1/platform/tenant/default-margin`. Edit modal → `PATCH /api/v1/platform/tenant/default-margin`. Hierarchy table → `<NotImplementedSection>`. Margin changes log → `<NotImplementedSection>`. Stats fields that need cross-tenant aggregates (`apiCosts30d`, `customerBillings30d`, `marginEarned30d`, `blendedMargin`) → render `<NotImplementedSection compact>` per stat card; do not hide. |
| `export` page | **Partial — inline placeholders** | "Events" filter type → wires to existing `POST /api/v1/platform/events/export`. Other filter types disabled with "Backend coming soon" tag. `getFilterOptions` and `getPreview` throw `ApiNotImplementedError`; preview pane shows `<NotImplementedSection>`. |
| `onboarding` | Audit during implementation | Likely uses platform/tenant endpoints already; wire what works, placeholder anything not backed. |
| `auth` | Remove no-auth bootstrap | Clerk becomes mandatory; update README. |

## Auth changes

- Remove the `VITE_API_PROVIDER === "mock"` branch from auth init.
- `VITE_CLERK_PUBLISHABLE_KEY` becomes required for the app to start;
  show a friendly error if missing.
- Update `.env.example`: drop `VITE_API_PROVIDER`, document required
  Clerk variables.
- Update `ubb-ui/README.md` and `ubb-ui/CLAUDE.md` with the new dev
  setup (no more no-auth shortcut).

## Testing

- Existing Vitest + MSW tests stay; MSW intercepts at the network
  layer and is independent of the deleted `mock.ts` modules.
- New tests:
  - `<NotImplementedPage>` and `<NotImplementedSection>` render the
    endpoint and docs link.
  - For each rewired feature with placeholders (reconciliation,
    customers→mapping, billing margins hierarchy, export filter types),
    a test asserts the placeholder renders when the query throws
    `ApiNotImplementedError`.
  - Billing page test: default-margin path renders real value;
    hierarchy renders placeholder.
  - Export page test: events filter renders preview; non-event filters
    render placeholders.
- Delete any test files that import from a deleted `mock.ts` module
  directly (Vitest module-mock tests are typically network-level and
  unaffected — verify case-by-case).

## Sequencing (single PR, ordered commits)

1. Add `api-errors.ts`, `<NotImplementedPage>` / `<NotImplementedSection>`,
   their unit tests.
2. Remove `VITE_API_PROVIDER` no-auth bootstrap; require Clerk.
3. For each feature: delete `mock.ts` / `mock-data.ts` / `provider.ts`;
   point `queries.ts` at `./api`; in `api.ts` swap any non-existent
   endpoint to `throw new ApiNotImplementedError(...)` with `// TODO(api):`.
4. Update consuming components to branch on `isApiNotImplementedError`
   and render the placeholder.
5. Wire billing default-margin stat + edit modal to the real endpoint.
6. Wire events export inside `/export` page; gate other filter types.
7. Update PROGRESS.md, CLAUDE.md (UI), `.env.example`, README.
8. Run full test suite; manual smoke against a running `ubb-platform`.

## Risks & mitigations

| Risk | Mitigation |
|------|------------|
| Removing no-auth dev mode blocks devs without Clerk dev keys | Document Clerk dev key setup in README; use shared dev tenant if team prefers |
| Already-wired features regress when mock files are deleted | Each feature's removal is its own commit; run tests + smoke per commit |
| MSW test setup may import from deleted `mock-data.ts` for fixtures | Audit `test-setup.ts` and per-feature tests; relocate fixtures into the test files themselves or a `__fixtures__` folder |
| `getFilterOptions` is called on `/export` page mount; throwing breaks the page | The page must catch via TanStack Query `error` and render placeholder rather than crash; covered by sequencing step 6 |
| Hidden mock imports outside the standard `mock.ts` path | Run `rg "from .*mock"` across `src/` before committing the cleanup |
| `features/auth/api/queries.test.ts` may import from `mock.ts` directly | Inspect and either rewrite test against MSW handler or delete if obsolete |

## Out-of-scope follow-ups

These remain backend work and are not addressed by this branch:

- `GET/POST /api/v1/billing/margins` — full margin hierarchy + audit log.
- `GET /api/v1/platform/customers/mapping`, `PUT .../mapping/{id}`,
  `POST/DELETE .../orphans/...`, `POST .../sync` — orphan SDK identifier
  reconciliation.
- `GET /api/v1/metering/rate-cards/{id}/reconciliation` and the four
  related `POST` mutation endpoints.
- `GET /api/v1/platform/export/filter-options`, `POST .../preview`,
  `POST .../generate` — generic data export.
