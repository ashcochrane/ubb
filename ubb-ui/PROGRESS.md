# Progress Tracker — UBB UI

## Current Status

**Phase:** All phases complete  
**Last completed:** Phase 10 — v4 palette extended to all feature pages  
**Next up:** Wire real scope/export interactions, or real API integration

## Phase Summary

| Phase | Name | Status | Mockup files |
|-------|------|--------|-------------|
| 1 | Foundation | Complete | — |
| 2 | Pricing Card Wizard | Complete | 4 mockups |
| 3 | Dashboard | Complete | `dashboard.html` |
| 4 | Onboarding | Complete | 7 mockups (consolidated) |
| 5 | Customer Mapping | Complete (other agent) | `customer_mapping_management.html` |
| 6 | Reconciliation | Complete | `unified_reconciliation_v3.html` |
| 7 | Margin Management | Complete | `margin-management-dashboard.html` |
| 8 | Data Export | Complete | `data_export_page.html` |
| 9 | v4 Visual refresh | Complete | ui-mockups/v2/ubb-dashboard-v4.html + ui-mockups/ubb-design-system.html |
| 10 | v4 palette extended | Complete | — |

## Phase 1: Foundation (Complete)

- [x] Vite + React 19 + TypeScript scaffold
- [x] Tailwind CSS v4, shadcn/ui, TanStack Router, Clerk auth, provider pattern
- [x] Nav shell, top bar, Zustand auth store, QueryProvider + Sonner
- [x] Stub pages, error boundaries, ESLint config

## Phase 2: Pricing Card Wizard (Complete)

- [x] Pricing cards list + 4-step wizard + template selection
- [x] Dimension config + cost tester + dry-run + activation
- [x] Feature API layer + 17 tests

## Phase 3: Dashboard (Complete)

- [x] Scope bar, stats, revenue/margin chart, cost charts, breakdowns, customer table

## Phase 4: Onboarding (Complete)

- [x] 3-path onboarding (track/revenue/billing)
- [x] Stripe key validation, customer mapping, margin config, review + activation

## Phase 6: Reconciliation (Complete)

- [x] Dual timeline, version detail, 3 editing panels, adjustments with 4 dist modes
- [x] Reconciliation summary, audit trail, clickable pricing cards

## Phase 7: Margin Management (Complete)

- [x] Margin page at /billing
- [x] 4-metric stats grid (blended margin, costs, billings, earned)
- [x] Margin hierarchy tree (default → product → card)
- [x] Expand/collapse product rows with card children
- [x] Indentation by level + level badges (Default, Card)
- [x] Inherited values grayed out in tree
- [x] Source indicators (Set, Override, From default/product)
- [x] Edit panel with current margin card + slider (0-200%)
- [x] Inherit toggle (revert to parent value)
- [x] Impact preview (was/would-be/delta calculation)
- [x] Immediate vs scheduled effectiveness with datetime picker
- [x] Level-specific description text
- [x] Reason for change field
- [x] Change history in single bordered container with level badges
- [x] Feature API layer with mockup-matching data

## Phase 8: Data Export (Complete)

- [x] Data Export page at /export
- [x] Filters card: date range with presets (7d/30d/90d/All time)
- [x] CustomerMultiSelect with shadcn Popover (searchable dropdown + chips)
- [x] TogglePillGroup reusable component (products and pricing cards with percentages)
- [x] Live row estimate + file size + natural language summary
- [x] Large export warning banner (>500k rows)
- [x] Data preview table (first 5 rows)
- [x] Granularity toggle swaps preview columns (dimension ↔ event)
- [x] Muted/bold styling via PreviewColumn config flags
- [x] Empty state when no rows match filters
- [x] Format toggle (CSV / JSON)
- [x] Download button with three states + actual browser download trigger
- [x] Debounced filter changes (300ms)
- [x] Feature API layer + shadcn Popover install

## Phase 9: v4 Visual refresh (Complete)

- [x] Rewired design tokens to warm stone + terracotta palette (shadcn `:root` + `@theme inline` named palette)
- [x] Swapped fonts: Geist → DM Sans Variable + Cormorant (logo) + DM Mono
- [x] App shell redesigned: 46px TopBar with Cormorant `ubb.` logo + circular icon buttons; 200px sidebar in CSS grid, user row pinned at bottom
- [x] 6 new shared primitives in `src/components/shared/`: Brand, IconButton, DeltaPill, Sparkline, ChartCard, ChartLegend
- [x] StatCard extended with `raised` variant, `trend` pill, and `sparkline` slot (back-compat for billing + customer-mapping preserved via `muted` default)
- [x] Dashboard rebuilt to match `ubb-dashboard-v4.html`: single-row ScopeBar, 5-col KPI grid with sparklines + delta pills, ComposedChart Revenue/Margin, line-chart cost breakdowns, restyled breakdown rows and customer table (blue/amber badges + terracotta margin bars)
- [x] Mock data recolored to the new palette + sparklines derived from revenueTimeSeries
- [x] 7 new tests: 5 DeltaPill (label + 3 data-trend variants + distinct icon shapes), 2 Sparkline (non-empty svg + empty null)
- [x] jsdom stubs for ResizeObserver + getBoundingClientRect hoisted to `src/test-setup.ts` so future chart tests don't need to re-stub
- [x] Shared chart colors extracted to `src/features/dashboard/lib/chart-colors.ts`
- [x] Route file `src/app/routes/_app/index.tsx` wired to mount `DashboardPage` (was a stub)

## Phase 10: v4 Palette Extended (Complete)

- [x] Export page: rounded-md containers, bg-bg-surface cards, v4 semantic tokens for warnings, section heading typography
- [x] Pricing card wizard (11 components): rounded-md containers, bg-bg-surface/bg-bg-subtle backgrounds, v4 semantic colors for all badges/warnings/success states, removed all dark: overrides
- [x] Reconciliation page (15 components): rounded-md containers, bg-bg-surface/bg-bg-subtle backgrounds, v4 semantic colors, consistent input styling, removed all dark: overrides
- [x] All hardcoded Tailwind color scales (green-50, amber-700, blue-600, red-500, etc.) replaced with v4 named tokens (green-light, amber-text, blue, red, etc.) across all three feature areas
- [x] TypeScript clean, all 52 tests pass

## Session Log

| Date | What |
|------|------|
| 2026-04-08 | Initial commit (old architecture) |
| 2026-04-09 | Full rebuild. Phase 1-7 complete (Foundation through Margin Management). |
| 2026-04-10 | Phase 8 Data Export complete. All phases done. |
| 2026-04-10 | Phase 9 v4 visual refresh complete. Tokens, fonts, shell chrome, and all 7 dashboard components rewritten around reusable primitives. |
| 2026-04-13 | Phase 10 v4 palette extended to Export (7 components), Pricing Card wizard (11 components), Reconciliation (15 components). All hardcoded Tailwind colors replaced with v4 named tokens. |
