# Progress Tracker — UBB UI

## Current Status

**Phase:** 3 — Dashboard (not started)  
**Last completed:** Phase 2 — Pricing Card Wizard  
**Next up:** Build dashboard from `dashboard.html` mockup

## Phase Summary

| Phase | Name | Status | Mockup files |
|-------|------|--------|-------------|
| 1 | Foundation | Complete | — (infrastructure only) |
| 2 | Pricing Card Wizard | Complete | 4 mockups |
| 3 | Dashboard | Not started | `dashboard.html` |
| 4 | Onboarding | Not started | 7 mockups |
| 5 | Customer Mapping | Not started | `customer_mapping_management.html` |
| 6 | Reconciliation | Not started | `unified_reconciliation_v3.html` |
| 7 | Margin Management | Not started | `margin-management-dashboard.html` |
| 8 | Data Export | Not started | `data_export_page.html` |

## Phase 1: Foundation (Complete)

- [x] Vite + React 19 + TypeScript scaffold
- [x] Tailwind CSS v4 with design tokens (migrated from previous index.css)
- [x] shadcn/ui component library
- [x] TanStack Router with route structure (routes in src/app/routes/)
- [x] Clerk auth (with no-auth dev mode)
- [x] Provider pattern (selectProvider, api-provider.ts)
- [x] API client (openapi-fetch + auth middleware)
- [x] Nav shell (sidebar with section labels matching screenshot)
- [x] Top bar (collapse toggle, theme toggle, user slot)
- [x] Zustand auth store (tenant context, mode, permissions)
- [x] QueryProvider in root route
- [x] TooltipProvider in root route
- [x] Sonner toaster at root
- [x] Vitest + RTL setup
- [x] Migrate format.ts + tests
- [x] Stub pages for all 7 nav sections
- [x] Error boundaries (route-error, not-found)
- [x] ESLint config updated for route files + shadcn

## Phase 2: Pricing Card Wizard (Complete)

- [x] Pricing cards list page with search
- [x] 4-step creation wizard (source, details, dimensions, review)
- [x] Template selection + custom creation
- [x] Live card preview (updates as user types)
- [x] Dimension configuration with collapse/duplicate/remove
- [x] Live cost tester (real-time calculations)
- [x] Dry-run simulator with breakdown + distribution bar
- [x] Sanity warnings (dominated dimension, high prices)
- [x] Product assignment with toggle pills
- [x] SDK integration snippet (auto-updates)
- [x] Activation flow with confirmation dialog
- [x] Feature API layer (types, mock, api, queries, provider)
- [x] Pure calculation functions with tests (6 tests)
- [x] Slugify utility with tests (7 tests)
- [x] Zod schema validation
- [x] Quick-add dimension chips

## Session Log

| Date | What |
|------|------|
| 2026-04-08 | Initial commit (old architecture) |
| 2026-04-09 | Full rebuild decision. Design spec written. Phase 1 + Phase 2 complete. |
