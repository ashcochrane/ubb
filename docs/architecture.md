# Architecture

## Overview

UBB UI is the admin dashboard for the Usage-Based Billing platform. It provides tenant administrators with tools to manage metering (rate cards, cost analytics), billing (wallets, invoices, transactions), customers, and platform settings.

The backend is a .NET API with multiple service namespaces. The UI connects via OpenAPI-generated type-safe clients with Clerk JWT authentication.

## Tech Stack

| Layer | Choice |
|-------|--------|
| Framework | React 19 + Vite 8 + TypeScript 5.9 |
| Server state | TanStack Query v5 |
| Client state | Zustand 5 |
| Components | shadcn/ui (Base UI / Radix primitives) |
| Styling | Tailwind CSS v4 |
| Routing | TanStack Router (file-based, type-safe) |
| Forms | React Hook Form + Zod |
| Charts | Recharts |
| HTTP | openapi-fetch (type-safe OpenAPI client) |
| Auth | Clerk (@clerk/react) |
| Icons | Lucide |
| Font | Geist Variable |
| Testing | Vitest + React Testing Library |
| API mocking | MSW (Mock Service Worker) |
| Linting | ESLint + TypeScript ESLint |

## Project Structure

```
src/
├── api/                        — API infrastructure
│   ├── client.ts               — OpenAPI fetch clients (platform, metering, billing, tenant)
│   └── hooks/                  — TanStack Query hooks per domain
│       ├── use-pricing.ts
│       ├── use-metering-analytics.ts
│       ├── use-customers.ts
│       └── use-dashboard.ts
├── components/                 — UI components
│   ├── ui/                     — shadcn base components (button, card, table, etc.)
│   ├── layout/                 — App shell (sidebar, top bar, nav config)
│   ├── shared/                 — Reusable composites (stat-card, stepper)
│   ├── metering/               — Metering feature components
│   │   ├── pricing/            — Pricing cards list page
│   │   ├── wizard/             — New card creation wizard
│   │   └── dashboard/          — Cost analytics dashboard
│   ├── customers/              — Customer management components
│   ├── dashboard/              — Home dashboard components
│   └── error-boundary.tsx
├── hooks/                      — Shared hooks
│   ├── use-mobile.ts
│   └── use-theme.ts
├── lib/                        — Pure utilities
│   ├── format.ts               — Currency, date, number formatting
│   ├── format.test.ts          — Format utility tests
│   ├── mock-data/              — Mock data for development
│   │   └── metering.ts
│   └── utils.ts                — General helpers (cn, etc.)
├── routes/                     — TanStack Router file-based routes
│   ├── __root.tsx              — Root layout + 404
│   ├── sign-in.tsx             — Clerk sign-in page
│   ├── _authenticated.tsx      — Auth guard + app shell layout
│   └── _authenticated/         — Protected routes
│       ├── index.tsx           — Dashboard home
│       ├── customers/          — Customer list + detail
│       ├── metering/           — Pricing, wizard, cost dashboard
│       ├── billing/            — Wallets, transactions, invoices, top-ups
│       └── settings/           — General, team, webhooks, stripe
└── routeTree.gen.ts            — Auto-generated route tree (do not edit)
```

## API Architecture

### Four API Namespaces

Each namespace maps to a microservice boundary on the backend:

```typescript
export const platformApi = createApiClient("/api/v1/platform");   // Tenants, users, API keys
export const meteringApi = createApiClient("/api/v1/metering");   // Rate cards, usage events, costs
export const billingApi  = createApiClient("/api/v1/billing");    // Wallets, invoices, transactions
export const tenantApi   = createApiClient("/api/v1/tenant");     // Tenant-specific config
```

### Auth Flow

1. Clerk initialises and provides `getToken()`
2. `setAuthTokenGetter()` registers the getter with the API client module
3. An OpenAPI fetch middleware injects `Authorization: Bearer <jwt>` on every request
4. Tokens are always fresh (getter is called per-request, not cached)

### Type Generation

```bash
pnpm api:generate    # runs scripts/generate-api.sh
```

This generates TypeScript types from the backend's OpenAPI spec. Until codegen runs, API clients use `any` — after codegen, replace with generated path types for full type safety.

### Dev Proxy

Vite proxies `/api/*` to `http://localhost:8000` in development, so the UI and API share the same origin.

## Dependency Rules

Imports flow DOWN only:

```
Layer 1: Routes (src/routes/)              — can import from everything below
Layer 2: Components (src/components/)      — can import from api/hooks, hooks, lib
Layer 3: API hooks (src/api/hooks/)        — can import from api/client, lib
Layer 4: Shared (hooks, lib)               — can import between each other
Layer 5: API client (src/api/client.ts)    — standalone
```

**NEVER:**
- Import from one feature's components into another (e.g., `metering/` <- `customers/`)
- Import API client directly in components — go through `api/hooks/`
- Put business logic in route files — routes are thin wrappers
- Edit `routeTree.gen.ts` — it's auto-generated

## Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `VITE_API_URL` | Backend base URL | `http://localhost:8000` |
| `VITE_CLERK_PUBLISHABLE_KEY` | Clerk auth key | `pk_test_...` |

## Build & Development

```bash
pnpm dev              # Vite dev server with HMR
pnpm build            # TypeScript + Vite production build
pnpm lint             # ESLint checks
pnpm preview          # Preview production build
pnpm test             # Vitest unit tests (single run)
pnpm test:watch       # Vitest watch mode
pnpm api:generate     # OpenAPI codegen
```
