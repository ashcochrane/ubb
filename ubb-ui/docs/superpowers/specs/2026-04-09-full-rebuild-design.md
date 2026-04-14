# UBB UI — Full Rebuild Design Spec

> **Date:** 2026-04-09  
> **Status:** Draft  
> **Scope:** Wipe current codebase. Rebuild from scratch following engage-online-ui architecture patterns, driven by HTML mockups in `docs/design/files/`.

---

## 1. Goal

Replace the current layer-based UI with a feature-co-located architecture modeled after `engage-online-ui`. Every screen is driven by the HTML mockups in `docs/design/files/` and the flow described in `docs/design/ui-flow-design-rationale.md`.

### What We're Keeping

- `docs/design/` — all mockups and rationale (untouched, these drive everything)
- `docs/superpowers/` — existing specs/plans (reference only)
- `src/lib/format.ts` + `src/lib/format.test.ts` — formatting utilities (migrate into new structure)
- `src/index.css` — OKLCH design tokens, light/dark mode (migrate into new structure)
- Git history

### What We're Deleting

Everything else in `src/`. Fresh scaffold.

---

## 2. Architecture

### Tech Stack

| Layer | Choice | Rationale |
|-------|--------|-----------|
| Framework | React 19 + Vite 8 + TypeScript 5.9 | Same as current, proven |
| Server state | TanStack Query v5 | Caching, mutations, optimistic updates |
| Client state | Zustand 5 | Auth store, UI state |
| Components | shadcn/ui (Base UI / Radix primitives) | Same as current |
| Styling | Tailwind CSS v4 | Same as current, `@theme inline` |
| Routing | TanStack Router (file-based) | Type-safe, same as current |
| Forms | React Hook Form + Zod | Same as current |
| Charts | Recharts | Dashboard cost charts |
| HTTP | openapi-fetch + openapi-typescript | Type-safe from Python backend's OpenAPI spec |
| Auth | Clerk (@clerk/react) | Long-term auth provider |
| Icons | Lucide | Same as current |
| Font | Geist Variable | Same as current |
| Testing | Vitest + React Testing Library + MSW | Same as current |
| Toasts | Sonner | Transient notifications |

### Project Structure (engage-online-ui pattern)

```
src/
├── app/                            — App shell & providers
│   ├── providers/
│   │   └── query-provider.tsx      — QueryClientProvider wrapper
│   └── routes/                     — TanStack Router file-based routes
│       ├── __root.tsx              — Root layout (providers, toaster)
│       ├── sign-in.tsx             — Clerk sign-in (public)
│       ├── _app.tsx                — Auth guard + nav shell layout
│       └── _app/                   — Protected routes
│           ├── index.tsx           — Dashboard
│           ├── pricing-cards/
│           │   ├── index.tsx       — Card list
│           │   └── new.tsx         — Creation wizard
│           ├── products/
│           │   └── index.tsx       — Product groupings
│           ├── customers/
│           │   └── index.tsx       — Customer mapping management
│           ├── billing/
│           │   └── index.tsx       — Margin management
│           ├── export/
│           │   └── index.tsx       — Data export
│           ├── onboarding/
│           │   └── index.tsx       — Mode selection + setup flows
│           └── settings/
│               └── index.tsx       — Stripe, API keys, account
├── features/                       — Feature modules (co-located)
│   ├── auth/
│   │   ├── components/             — Sign-in related UI (if needed beyond Clerk)
│   │   ├── hooks/                  — useAuth, usePermissions
│   │   └── stores/                 — auth-store.ts (tenant context, permissions)
│   ├── dashboard/
│   │   ├── components/             — Scope bar, cost chart, profitability, anomalies
│   │   └── api/                    — types, mock, api, queries, provider
│   ├── pricing-cards/
│   │   ├── components/             — Card list, wizard steps, card preview
│   │   └── api/                    — types, mock, api, queries, provider
│   ├── onboarding/
│   │   ├── components/             — Mode selector, Stripe setup, customer mapping steps
│   │   └── api/                    — types, mock, api, queries, provider
│   ├── customers/
│   │   ├── components/             — Mapping table, orphaned events, inline edit
│   │   └── api/                    — types, mock, api, queries, provider
│   ├── reconciliation/
│   │   ├── components/             — Timeline, version editor, adjustments, audit trail
│   │   └── api/                    — types, mock, api, queries, provider
│   ├── billing/
│   │   ├── components/             — Margin tree, impact preview, balance alerts
│   │   └── api/                    — types, mock, api, queries, provider
│   └── export/
│       ├── components/             — Filters, preview table, download
│       └── api/                    — types, mock, api, queries, provider
├── components/                     — Shared UI
│   ├── ui/                         — shadcn base components
│   └── shared/                     — Nav shell, page header, stat card, etc.
├── api/                            — API infrastructure ONLY
│   ├── client.ts                   — openapi-fetch client + auth middleware
│   └── types.ts                    — Shared API types (if any)
├── hooks/                          — Truly shared hooks
├── lib/                            — Pure utilities
│   ├── api-provider.ts             — Provider selection (mock | api)
│   ├── format.ts                   — Currency, date, number formatting (migrated)
│   ├── format.test.ts              — Format tests (migrated)
│   ├── query-client.ts             — QueryClient instance
│   └── utils.ts                    — cn() and helpers
├── stores/                         — App-wide Zustand stores
│   └── auth-store.ts               — Token, user, tenant, permissions
├── types/                          — Shared domain types
└── styles/
    └── app.css                     — Design tokens, Tailwind imports (migrated from index.css)
```

### Key Structural Differences from Current

| Current (layer-based) | New (feature co-located) |
|----------------------|--------------------------|
| `src/components/metering/` | `src/features/pricing-cards/components/` |
| `src/api/hooks/use-pricing.ts` | `src/features/pricing-cards/api/queries.ts` |
| `src/lib/mock-data/metering.ts` | `src/features/pricing-cards/api/mock.ts` |
| Routes in `src/routes/` | Routes in `src/app/routes/` |
| Providers in `main.tsx` | Providers in `__root.tsx` |
| No provider pattern | `selectProvider()` per feature |

---

## 3. Provider Pattern

Adopted from engage-online-ui. Controls whether features use mock data or the real API.

### Provider Selection

```typescript
// src/lib/api-provider.ts
const VALID_PROVIDERS = ["mock", "api"] as const;
export type ApiProvider = (typeof VALID_PROVIDERS)[number];

function getApiProvider(): ApiProvider {
  const value = import.meta.env.VITE_API_PROVIDER;
  if (!value || !VALID_PROVIDERS.includes(value as ApiProvider)) {
    return "mock"; // Default to mock in development
  }
  return value as ApiProvider;
}

export const API_PROVIDER = getApiProvider();

export function selectProvider<T>(providers: Record<ApiProvider, T>): T {
  return providers[API_PROVIDER];
}
```

### Per-Feature API Structure

Each feature has identical API folder structure:

```
features/pricing-cards/api/
├── types.ts        — Backend-agnostic TypeScript interfaces
├── mock.ts         — Mock implementation (returns fake data with delay)
├── mock-data.ts    — Mock data constants
├── api.ts          — Real API calls via openapi-fetch client
├── queries.ts      — TanStack Query hooks (imports from provider)
└── provider.ts     — selectProvider({ mock, api })
```

```typescript
// features/pricing-cards/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const pricingCardsApi = selectProvider({ mock, api });
```

```typescript
// features/pricing-cards/api/queries.ts
import { useQuery } from "@tanstack/react-query";
import { pricingCardsApi } from "./provider";

export const usePricingCards = () =>
  useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => pricingCardsApi.getCards(),
  });
```

### Two Providers (not three)

engage-online-ui has three providers (mock, legacy, engage-online) because it's migrating between backends. UBB has one backend (Python), so we only need:

- **`mock`** — Development without backend
- **`api`** — Real Python backend via openapi-fetch

---

## 4. Auth Architecture

### Clerk + Zustand Hybrid

Clerk handles identity (sign-in, sign-up, JWT). Zustand stores tenant context and permissions that Clerk doesn't know about.

```typescript
// src/stores/auth-store.ts
interface AuthState {
  activeTenantId: string | null;
  tenantMode: "track" | "revenue" | "billing" | null;
  permissions: string[];
  setTenant: (tenantId: string, mode: TenantMode) => void;
  hasPermission: (permission: string) => boolean;
  reset: () => void;
}
```

### Auth Flow

1. `ClerkProvider` wraps app in `main.tsx`
2. `__root.tsx` registers token getter with API client
3. `_app.tsx` checks `isSignedIn` via Clerk context, redirects to `/sign-in` if not
4. After sign-in, fetch tenant context from backend, populate Zustand store
5. API middleware injects fresh Clerk JWT on every request

### No-Auth Dev Mode

When `VITE_CLERK_PUBLISHABLE_KEY` is not set AND `VITE_API_PROVIDER=mock`:
- Skip ClerkProvider entirely
- Fake `isSignedIn: true` in router context
- Auto-bootstrap mock tenant context in auth store
- Render a placeholder avatar instead of Clerk's UserButton

This is cleaner than the current `clerkEnabled` checks scattered across components.

---

## 5. Navigation Model

From `docs/design/ui-flow-design-rationale.md` (lines 276-284):

```
Sidebar:
├── Dashboard                    → /              (dashboard.html)
├── Pricing Cards                → /pricing-cards  (card list + wizard)
├── Products                     → /products       (product groupings)
├── Customers                    → /customers      (customer-mapping-management.html)
├── Billing (if billing mode)    → /billing        (margin-management-dashboard.html)
├── Export                       → /export         (data_export_page.html)
└── Settings                     → /settings       (Stripe, API keys, account)
```

**Onboarding** (`/onboarding`) is a separate flow — shown after first sign-in when no tenant mode is configured. Not in the sidebar.

**Reconciliation** is accessed by clicking a pricing card from the list or dashboard, not a top-level nav item.

### Sidebar Behaviour

- Collapsible (icon-only mode)
- Active item highlighted
- Billing section conditionally visible based on `tenantMode === "billing"`
- Bottom: theme toggle + Clerk UserButton (or placeholder in dev mode)

---

## 6. Environment Variables

```bash
# API
VITE_API_PROVIDER=mock          # mock | api
VITE_API_URL=http://localhost:8000

# Auth
VITE_CLERK_PUBLISHABLE_KEY=     # Blank = dev mode (no auth)
```

---

## 7. Build Phases

Each phase delivers a working increment. Mock data first, real API later.

### Phase 1: Foundation
- Vite + React 19 + TypeScript scaffold
- Tailwind CSS v4 with migrated design tokens
- shadcn/ui component library
- TanStack Router with route structure
- Clerk auth (with no-auth dev mode)
- Provider pattern (`selectProvider`)
- API client (openapi-fetch + auth middleware)
- Nav shell (sidebar from mockup nav model)
- Zustand auth store (tenant context)
- QueryProvider in root route
- Sonner toaster
- Vitest + RTL + MSW setup
- Migrated `format.ts` + tests

### Phase 2: Pricing Card Wizard
Mockups: `pricing_card_creation_flow.html`, `custom_card_details_step.html`, `custom_card_dimensions_step.html`, `custom_card_review_test_step.html`

- Pricing cards list page
- 4-step creation wizard (source, details, dimensions, review)
- Template selection + custom creation
- Live card preview
- Dimension configuration with cost tester
- Dry-run simulator + sanity checks
- Product assignment + SDK snippet
- Feature API layer (types, mock, api, queries, provider)

### Phase 3: Dashboard
Mockup: `dashboard.html`

- Scope bar (date range, customer filter, product filter)
- Cost overview chart
- Profitability breakdown (revenue vs costs)
- Per-customer table
- Per-product breakdown
- Anomaly alerts
- Feature API layer

### Phase 4: Onboarding
Mockups: `complete_onboarding_4_screens.html`, `billing_mode_stripe_adaptation.html`, `billing_onboarding_fresh_customer_4_steps.html`, `screen_4_stripe_integration.html`, `step_2_customer_identification.html`, `step_2_customer_mapping.html`, `step_3_confirm_and_activate.html`

- Mode selection (track / revenue+costs / billing)
- Path A: Skip to pricing cards
- Path B: Stripe setup (3 steps) → customer mapping → done
- Path C: Stripe setup (4 steps) → customer mapping → margin config → review
- Established customer variant (per-product/per-card margins)
- Feature API layer

### Phase 5: Customer Mapping
Mockup: `customer_mapping_management.html`

- Sync status bar
- Stats row (total, mapped, unmapped, orphaned)
- Alert banners (new customers, orphaned events)
- Customer table with inline editing
- Filter pills (All, Active, Idle, Unmapped)
- Orphaned events section with assignment
- Feature API layer

### Phase 6: Reconciliation
Mockup: `unified_reconciliation_v3.html`

- Dual timeline (original vs reconciled)
- Version detail cards
- Edit prices action
- Adjust boundaries action
- Insert period action
- Adjustments section (lump sum, even daily, proportional, manual)
- Reconciliation summary bar
- Audit trail
- Feature API layer

### Phase 7: Margin Management
Mockup: `margin-management-dashboard.html`

- Margin hierarchy tree (global → product → card)
- Impact preview
- Scheduling (future margin changes)
- Feature API layer

### Phase 8: Data Export
Mockup: `data_export_page.html`

- Date range + entity filters
- Live row estimate + summary
- Data preview table (first 5 rows)
- Granularity toggle (by dimension / by event)
- Format toggle (CSV / JSON)
- Download generation
- Feature API layer

---

## 8. Dependency Rules

Same as engage-online-ui. Imports flow DOWN only.

```
Layer 1: Routes (src/app/routes/)           — can import from features, components, hooks, lib
Layer 2: Features (src/features/)           — can import from components, api, hooks, lib, stores, types
Layer 3: Components (src/components/)       — can import from hooks, lib, types
Layer 4: API (src/api/)                     — can import from lib, stores, types
Layer 5: Shared (hooks, lib, stores, types) — can import between each other
```

**NEVER:**
- Import from one feature into another
- Import API client directly in feature components — go through feature's `queries.ts`
- Put business logic in route files
- Edit `routeTree.gen.ts`

---

## 9. File Size Standards

| Type | Limit |
|------|-------|
| Component files | <200 lines |
| Hook files | <150 lines |
| API adapter files | <300 lines |
| Store files | <100 lines |
| Type files | <200 lines |
| Route files | <50 lines |

---

## 10. Conventions

### Commit Messages

```
{type}({scope}): {description}

Types: feat, fix, refactor, docs, test, chore
Scope: feature name or "shared"/"infra"
```

### Component Rules

- Loading states use `<Skeleton />`, not spinners
- Empty states use descriptive placeholders
- Forms use React Hook Form + Zod (always)
- Icons from `lucide-react` only
- `cn()` for conditional classes
- shadcn components restyled via Tailwind — never edit the component files

### Mock Data Rules

- Realistic but obviously fake values
- Cover all UI states (populated, empty, error)
- Same shape as real API responses
- Include `delay()` for realistic timing
- Never imported directly by components — only through `queries.ts`
