# UBB UI — Audit Cleanup Design Spec

> **Date:** 2026-04-10
> **Status:** Approved for planning
> **Scope:** Implement the 18 items from the 2026-04-10 codebase audit in a single coordinated effort. Production-hardening, design-system extraction, quick wins, and architectural decisions bundled into one spec with six sequential phases.

---

## 1. Goal

Take the audit findings from `2026-04-10` and turn them into a shippable cleanup. The codebase is structurally sound (feature co-location, provider pattern, strict types, no forbidden patterns). The risks are concentrated in production readiness (bundle bloat, silent mutation failures, broken auth fallback) and compounding duplication (stat cards, steppers, tables, hex colors). This spec addresses all of them.

## 2. Success Criteria

- Main bundle no longer ships Recharts on every page load.
- Heavy routes (dashboard, reconciliation, billing, export, onboarding) are code-split via TanStack Router lazy files.
- No mutation can fail silently. Every mutation surfaces an error toast via Sonner.
- Any query error renders a real error UI via a route-level `errorComponent`, never a broken/empty screen.
- `StatCard`, `Stepper`, `EmptyState`, `FormField` each exist exactly once in `components/shared/`.
- All 6 hand-rolled tables are migrated to shadcn `Table` + shared `EmptyState`.
- Custom alert banners are migrated to shadcn `Alert`.
- Zero hardcoded hex colors in feature components — all colors go through OKLCH tokens in `styles/app.css`.
- Zero magic font sizes (`text-[11px]`, etc.) in feature components — all sizes go through Tailwind `@theme` scale.
- `@tanstack/react-table` is uninstalled.
- Dedicated `mutations.ts` files are deleted; all query/mutation hooks live in each feature's `queries.ts`.
- Misconfigured prod env (`VITE_API_PROVIDER=api` without `VITE_CLERK_PUBLISHABLE_KEY`) fails at boot with a clear message.
- All feature component files are ≤200 lines (fixes `adjustments-section.tsx` at 252). `src/components/ui/*` shadcn primitives are exempt per `CLAUDE.md` ("shadcn components restyled via Tailwind — never edit the component files").
- `noUncheckedIndexedAccess` is enabled in `tsconfig.app.json` with all resulting errors resolved.

## 3. Non-Goals

- No new features.
- No rewrite of pages that work today.
- No React Compiler experiment — deferred until the compiler leaves RC.
- No switch to `@tanstack/react-table` — the package is removed.
- No `mutations.ts`-file pattern — inline-in-`queries.ts` everywhere.
- No new tests for existing behavior — existing tests (pricing-cards calculations, format, slugify) are the safety net. New unit tests are added only for the new shared components.

## 4. Key Decisions (recorded from brainstorming)

| Decision | Chosen | Alternatives rejected |
|---|---|---|
| `@tanstack/react-table` | Remove | Adopt, or keep installed but unused |
| Memoization strategy | Manual `React.memo` on 6 hot spots | React Compiler, hybrid |
| Mutation file pattern | Inline in `queries.ts` | Dedicated `mutations.ts` file per feature |
| Query error handling | Route-level `errorComponent` + `throwOnError: true` | Inline `isError` blocks, hybrid |
| Auth fallback (`api` provider + no Clerk key) | Throw at boot | Allow as valid dev mode, opt-in env var |

## 5. Architecture

### 5.1 Shared components added in Phase 1

```tsx
// src/components/shared/stat-card.tsx
export interface StatCardProps {
  label: string;
  value: React.ReactNode;           // ReactNode so callers pass pre-formatted micros
  change?: { value: string; positive: boolean };
  subtitle?: string;
  variant?: "default" | "purple";
  className?: string;
}

// src/components/shared/stepper.tsx
export interface StepperProps {
  steps: Array<{ label: string }>;
  currentIndex: number;
  className?: string;
}

// src/components/shared/empty-state.tsx
export interface EmptyStateProps {
  title: string;
  description?: string;
  icon?: LucideIcon;
  action?: { label: string; onClick: () => void };
  className?: string;
}

// src/components/shared/form-field.tsx
// Wraps Label + input + error text. Uses React.useId() to wire htmlFor automatically.
export interface FormFieldProps {
  label: string;
  error?: string;
  hint?: string;
  className?: string;
  children: (id: string) => React.ReactNode;
}
```

Usage for `FormField`:

```tsx
<FormField label="Stripe key" error={errors.key?.message}>
  {(id) => <Input id={id} {...register("key")} />}
</FormField>
```

Each component has one Vitest unit test covering the happy path + empty/error props.

### 5.2 Design tokens in `styles/app.css`

Append to the existing `@theme` block:

```css
--color-success-dark: <oklch(…)>;   /* replaces #3B6D11 */
--color-danger-dark:  <oklch(…)>;   /* replaces #A32D2D */
--color-purple-bg:    <oklch(…)>;   /* replaces #EEEDFE */
--color-purple-fg:    <oklch(…)>;   /* replaces #534AB7 */
--color-chart-margin: <oklch(…)>;   /* replaces #5DCAA5 */
--color-chart-loss:   <oklch(…)>;   /* replaces #F09595 */
--color-chart-alloc:  <oklch(…)>;   /* replaces #AFA9EC */

--text-label: 0.6875rem;  /* 11px */
--text-muted: 0.625rem;   /* 10px */
--text-tiny:  0.5625rem;  /*  9px */
```

Hex-to-OKLCH conversion uses https://oklch.com during implementation. Once defined, Tailwind v4 auto-generates `text-success-dark`, `bg-purple-bg`, `text-label`, etc., which are then grepped-and-replaced across feature components.

### 5.3 Bundle splitting (`vite.config.ts`)

```ts
build: {
  rollupOptions: {
    output: {
      manualChunks: {
        "vendor-react":   ["react", "react-dom"],
        "vendor-router":  ["@tanstack/react-router"],
        "vendor-query":   ["@tanstack/react-query"],
        "vendor-clerk":   ["@clerk/react"],
        "vendor-charts":  ["recharts"],
      },
    },
  },
},
```

Plus:

1. **Lazy chart components.** `revenue-chart.tsx` and `cost-breakdown-chart.tsx` become lazy exports; call sites wrap in `<Suspense fallback={<Skeleton className="h-64 w-full" />}>`.
2. **Route code-splitting.** Convert these routes to TanStack Router lazy files:
   - `src/app/routes/_app/index.tsx` (dashboard — hosts Recharts)
   - `src/app/routes/_app/pricing-cards/$cardId.tsx` (reconciliation)
   - `src/app/routes/_app/billing/index.tsx`
   - `src/app/routes/_app/export/index.tsx`
   - `src/app/routes/onboarding.tsx`

   Approach: split each into `route.tsx` (route definition only) + `route.lazy.tsx` (component). TanStack Router picks up `.lazy.tsx` automatically via the file-based plugin.

### 5.4 Route-level error handling

```ts
// src/lib/query-client.ts
new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      gcTime: 5 * 60_000,
      throwOnError: true,
    },
    mutations: {
      throwOnError: false, // mutations handle errors via per-call onError
    },
  },
});
```

```tsx
// src/components/shared/route-error.tsx  (already exists — needs modification)
// CURRENT: accepts { error: Error }, uses window.location.reload() for recovery
// REQUIRED: accept { error, reset } from TanStack Router's errorComponent contract;
// call reset() on the "Try again" button instead of full page reload.
// Also switch the hand-rolled button to use <Button> from components/ui/button.tsx.
interface RouteErrorProps {
  error: Error;
  reset: () => void;
}
```

```tsx
// src/app/routes/_app.tsx
createFileRoute("/_app")({
  component: AppLayout,
  errorComponent: RouteError,
});
```

With `throwOnError: true`, the five pages currently ignoring `isError` (dashboard, pricing-cards list, margin, reconciliation, customer-mapping) automatically gain error UI via the route. Their existing `isLoading || !data` guards can remain — they're still needed for the loading state.

### 5.5 Mutation error handler pattern

A shared helper so every mutation looks identical:

```ts
// src/lib/mutations.ts  (new file)
import { toast } from "sonner";

export const toastOnError = (defaultMessage: string) => (error: unknown) => {
  const message = error instanceof Error ? error.message : defaultMessage;
  toast.error(defaultMessage, { description: message });
};
```

Every mutation adopts this pattern:

```ts
useMutation({
  mutationFn: ...,
  onError: toastOnError("Couldn't save margin changes"),
  onSuccess: () => queryClient.invalidateQueries(...),
});
```

Mutations with optimistic updates (`customers` — after its `mutations.ts` is inlined into `queries.ts`) keep their rollback logic in `onError` and call `toastOnError(...)` at the end of that handler.

`reconciliation-page.tsx` currently uses `mutateAsync` without try/catch. Switch to `mutate` unless the call site genuinely needs to await the result — in which case wrap in try/catch.

### 5.6 Auth boot assertion

```ts
// src/main.tsx
if (import.meta.env.VITE_API_PROVIDER === "api" && !import.meta.env.VITE_CLERK_PUBLISHABLE_KEY) {
  throw new Error(
    "VITE_CLERK_PUBLISHABLE_KEY is required when VITE_API_PROVIDER=api. " +
    "Set it in .env.local, or use VITE_API_PROVIDER=mock for no-auth dev mode."
  );
}
```

No UI change — this fails before React mounts, Vite will surface the error in the browser overlay in dev and a blank page + console error in prod (which is correct; the deploy is broken).

### 5.7 Table migration waves

**Wave 1** (simplest, validates the pattern):
- `src/features/onboarding/components/permissions-table.tsx`
- `src/features/onboarding/components/match-results-table.tsx`
- `src/features/export/components/data-preview-table.tsx`

**Wave 2** (most complex):
- `src/features/dashboard/components/customer-table.tsx`
- `src/features/customers/components/customer-table.tsx`
- `src/features/reconciliation/components/audit-trail.tsx` (if table-shaped; verify during implementation)

Each migration:
1. Replace hand-rolled `<table>` with shadcn `<Table>`/`<TableHeader>`/`<TableRow>`/`<TableCell>`.
2. Replace inline empty-state JSX with `<EmptyState />`.
3. Replace hex colors with tokens from §5.2.

After Wave 2: `pnpm remove @tanstack/react-table`, then `pnpm build`.

### 5.8 Manual memoization targets

| Component | Change | Why |
|---|---|---|
| `src/features/billing/components/margin-tree-row.tsx` | Wrap in `React.memo` | Whole tree re-renders on every expand toggle |
| `src/features/reconciliation/components/edit-prices-panel.tsx` | Wrap in `React.memo` | All 6 panels re-render on any parent state change |
| `src/features/reconciliation/components/adjust-boundary-panel.tsx` | Wrap in `React.memo` | Same |
| `src/features/reconciliation/components/insert-period-panel.tsx` | Wrap in `React.memo` | Same |
| `src/features/reconciliation/components/timeline.tsx` | `useMemo` for `dateMarkers`; `React.memo` on marker items | Computed in render body |
| `src/features/export/components/export-page.tsx` | `useMemo` on `debouncedFilters`; `React.memo` on `ExportFiltersPanel`, `ExportEstimate`, `DataPreviewTable` | Filter changes ripple to all siblings |

### 5.9 Onboarding auto-redirect

`ActivationSuccess` component: add `useEffect` on mount with `useNavigate({ to: "/" })` after a short delay (~1500ms) so the success message is visible before redirect. The existing manual "Go to dashboard" link stays as a fallback.

### 5.10 Zustand selector fix

`src/features/reconciliation/components/reconciliation-page.tsx` currently has:

```ts
const { selectedVersionId, openPanel, selectVersion, reset } = useReconciliationStore();
```

Change to individual selector calls:

```ts
const selectedVersionId = useReconciliationStore((s) => s.selectedVersionId);
const openPanel = useReconciliationStore((s) => s.openPanel);
const selectVersion = useReconciliationStore((s) => s.selectVersion);
const reset = useReconciliationStore((s) => s.reset);
```

### 5.11 `adjustments-section.tsx` split

Current: `src/features/reconciliation/components/adjustments-section.tsx` is 252 lines. Target: ≤200.

Extract two sub-components into the same folder:
- `distribution-mode-selector.tsx` — the 4-mode segmented control
- `allocation-display.tsx` — the per-day allocation rendering (lump/even/proportional/manual variants)

`adjustments-section.tsx` keeps the form state, validation, and submission; children are pure presentation.

## 6. Execution Order

### Phase 1 — Foundation
Blocks Phase 3.

1. Create `src/components/shared/stat-card.tsx` + unit test
2. Create `src/components/shared/stepper.tsx` + unit test
3. Create `src/components/shared/empty-state.tsx` + unit test
4. Create `src/components/shared/form-field.tsx` + unit test
5. Add OKLCH color tokens + font-size tokens to `src/styles/app.css`

### Phase 2 — Production hardening
Runs in parallel with Phase 3 (different files).

6. Create `src/lib/mutations.ts` with `toastOnError` helper
7. Update `src/lib/query-client.ts` with `throwOnError: true` + `gcTime`
8. Update `src/components/shared/route-error.tsx` to accept `{ error, reset }` (per §5.4), use `reset()` on the recovery button, and use `<Button>` from `components/ui/button.tsx` instead of the hand-rolled button
9. Wire `errorComponent: RouteError` into `_app.tsx`
10. Add `onError: toastOnError(...)` to all 11 mutations:
    - `export/api/mutations.ts::useGenerateExport` (then inline into `queries.ts` per Phase 2 item below)
    - `reconciliation/api/queries.ts` — 4 mutations
    - `pricing-cards/api/queries.ts::useCreateCard`
    - `onboarding/api/queries.ts` — 3 mutations
    - `billing/api/queries.ts::useUpdateMargin`
11. Switch `reconciliation-page.tsx` from `mutateAsync` to `mutate` (or wrap existing calls in try/catch)
12. Inline `customers/api/mutations.ts` contents into `customers/api/queries.ts`; delete the `mutations.ts` file
13. Inline `export/api/mutations.ts` contents into `export/api/queries.ts`; delete the `mutations.ts` file
14. Add auth boot assertion to `src/main.tsx`
15. Update `vite.config.ts` with `manualChunks`
16. Convert `revenue-chart.tsx` and `cost-breakdown-chart.tsx` to lazy exports; wrap usage in `<Suspense>`
17. Convert 5 heavy routes to `.lazy.tsx` pattern:
    - `_app/index.tsx` (dashboard)
    - `_app/pricing-cards/$cardId.tsx`
    - `_app/billing/index.tsx`
    - `_app/export/index.tsx`
    - `onboarding.tsx`

### Phase 3 — Design system migration
Depends on Phase 1. Does NOT block Phase 2.

18. Install shadcn `Table` primitive
19. Install shadcn `Alert` primitive
20. **Wave 1** — migrate `onboarding/permissions-table`, `onboarding/match-results-table`, `export/data-preview-table` to shadcn `Table` + `<EmptyState />`
21. **Wave 2** — migrate `dashboard/customer-table`, `customers/customer-table`, `reconciliation/audit-trail` (if table-shaped)
22. `pnpm remove @tanstack/react-table` + `pnpm build`
23. Migrate custom alert banners to shadcn `Alert`:
    - `features/customers/components/alert-banners.tsx`
    - Any banner in `stripe-key-step.tsx`
    - Any banner in `reconciliation-summary.tsx`
24. Grep-replace hex colors in feature components with tokens from §5.2
25. Grep-replace magic font sizes (`text-[11px]`, `text-[10px]`, `text-[9px]`) with `text-label`/`text-muted`/`text-tiny`
26. Replace the template-literal `className` in `billing/margin-stats.tsx:23` with `cn()`
27. Refactor feature pages to use `<PageHeader />` instead of hand-rolled `<h1>`
28. Extract duplicate `StatCard` usages in `dashboard/stats-grid.tsx`, `billing/margin-stats.tsx`, `customers/mapping-stats-grid.tsx` to use the new shared component
29. Extract duplicate `Stepper` usages in `onboarding/onboarding-progress.tsx` and `pricing-cards/wizard-stepper.tsx` to use the shared component

### Phase 4 — Quick wins
Batch into one small PR. Independent from everything else.

30. Convert Zustand destructuring in `reconciliation-page.tsx` to per-selector calls (§5.10)
31. Delete local `formatFileSize()` in `export/components/export-estimate.tsx`; import from `src/lib/format.ts`
32. Split `reconciliation/components/adjustments-section.tsx` into 3 files (§5.11)
33. Add `aria-label` to the two icon-only buttons in `components/shared/top-bar.tsx:14,26`

### Phase 5 — Memoization + onboarding redirect
After everything above has settled.

34. Add `React.memo` wrappers per §5.8 table
35. Add `useMemo` to timeline date markers and export-page debouncedFilters
36. Add auto-redirect in `ActivationSuccess` via `useEffect` + `useNavigate` (§5.9)

### Phase 6 — `noUncheckedIndexedAccess`
Standalone, last. May expand scope.

37. Add `"noUncheckedIndexedAccess": true` to `tsconfig.app.json`
38. Run `pnpm build`; fix every resulting TS error (expected to cascade across dozens of files)
39. Run `pnpm test`; fix any runtime failures

## 7. Verification Strategy

### Phase 1
- `pnpm test` — new shared component unit tests must pass
- Manual visual pass on dashboard, billing, reconciliation after token changes

### Phase 2
- `pnpm build` — confirm under `dist/assets/`:
  - A `vendor-charts-*.js` chunk exists (~300kb)
  - No "recharts" string in `dist/assets/index-*.js` (the main entry chunk)
  - Separate chunks for `dashboard-*.js`, `reconciliation-*.js`, `billing-*.js`, `export-*.js`, `onboarding-*.js`
- **Route error component test:** temporarily throw in a feature query (`throw new Error("test")` in one `mock.ts` function), reload, confirm `<RouteError />` renders, revert
- **Mutation error handling test:** temporarily make one mutation reject in `mock.ts`, trigger it in the UI, confirm Sonner error toast appears, revert. Spot check one mutation per feature
- **Auth boot assertion test:** run `VITE_API_PROVIDER=api pnpm dev` without a Clerk key, confirm the app throws at boot with a clear message. Then with the key, confirm normal startup
- `pnpm build && pnpm test` — build passes, existing tests stay green

### Phase 3
- Visual parity: open each migrated table/banner/page side-by-side with its `docs/design/files/*.html` mockup, confirm no regression
- `pnpm build` — catches removed imports, missing tokens, dead code
- `pnpm test` — stays green
- Final: confirm `@tanstack/react-table` no longer in `package.json` and `pnpm build` still succeeds

### Phase 4
- `pnpm test` — covers `formatFileSize` deduplication
- `pnpm build` — catches aria-label syntax or split-file import issues
- Manual: open `/reconciliation`, confirm panels still open/close correctly after store selector change

### Phase 5
- React DevTools Profiler on: margin tree expand, reconciliation panel open, export filter change. Confirm fewer "wasted" renders than before
- Manual: complete onboarding, confirm auto-redirect to dashboard after activation

### Phase 6
- `pnpm build` must pass with zero errors
- `pnpm test` stays green

### Final cross-cutting checks (before merge)
- `pnpm lint` — zero errors
- `pnpm build` — zero warnings about unused imports
- `pnpm test` — all tests pass
- Manual smoke test: click through every sidebar item, create a pricing card end-to-end, open reconciliation for an existing card, trigger one mutation, trigger one deliberate error, complete onboarding end-to-end

## 8. Risks & Mitigations

| Risk | Mitigation |
|---|---|
| Phase 6 (`noUncheckedIndexedAccess`) cascades into dozens of type errors and delays shipping | Isolated in its own phase at the end. If the scope balloons, it can be deferred without blocking Phases 1–5 |
| TanStack Router `.lazy.tsx` split breaks an existing route | Migrate one route first (dashboard), verify, then proceed to the rest |
| Hex-to-OKLCH conversion shifts colors perceptibly | Use the first conversion on a low-stakes element (stat card positive-change text) and visually confirm before batch replacement |
| Shadcn Table migration loses some hand-rolled styling | Wave 1 validates the pattern on simple tables before Wave 2 touches complex ones |
| Mutation `mutateAsync → mutate` change breaks reconciliation flow if a call site genuinely awaited the result | Audit each `mutateAsync` call site during Phase 2 item 11; wrap in try/catch where awaiting is necessary |
| Lazy Recharts adds a flash of skeleton on dashboard first load | Acceptable — the dashboard already uses skeletons on first load. Chart-specific skeleton matches existing pattern |

## 9. Out of Scope (explicit)

- React Compiler — deferred until it leaves RC
- `@tanstack/react-table` adoption — package is removed
- `mutations.ts` file pattern — deleted, merged into `queries.ts`
- New features or UI additions
- Backend changes
- CI/CD changes
- Adding new tests for existing behavior
