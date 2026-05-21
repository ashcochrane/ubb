# UBB UI — Tenant Dashboard Design Spec

**Date:** 2026-03-13
**Status:** Approved
**Scope:** Tenant-facing dashboard for managing usage-based billing

---

## Overview

A single-page application where UBB tenants log in to manage their customers, rate cards, usage analytics, billing, and settings. Deployed as a static site to Cloudflare Pages, consuming the existing django-ninja REST API.

## Tech Stack

| Layer | Tool |
|---|---|
| Build | Vite |
| Framework | React 19 + TypeScript |
| Package manager | pnpm |
| Routing | TanStack Router (file-based, type-safe) |
| Server state | TanStack Query |
| Styling | Tailwind CSS v4 + shadcn/ui |
| Auth | Clerk (@clerk/clerk-react) |
| API client | openapi-typescript + openapi-fetch (auto-generated from django-ninja OpenAPI schemas) |
| Charts | Recharts |
| Forms | React Hook Form + Zod |
| Tables | TanStack Table (via shadcn DataTable) |
| Toasts | Sonner (via shadcn) |
| Testing | Vitest + React Testing Library + MSW |
| Deploy | Cloudflare Pages (static dist/) |

**Starting point:** Fork/reference [satnaing/shadcn-admin](https://github.com/satnaing/shadcn-admin) for the layout shell, sidebar, theming, and command palette.

## Monorepo Structure

```
ubb/
├── ubb-platform/      # Django API (existing)
├── ubb-sdk/           # Python SDK (existing)
└── ubb-ui/            # Vite + React SPA (new)
    ├── src/
    │   ├── components/    # shadcn/ui + custom components
    │   ├── routes/        # TanStack Router file-based routes
    │   ├── api/           # Auto-generated client + query hooks
    │   │   ├── generated/ # Output of openapi-typescript (gitignored)
    │   │   ├── client.ts  # openapi-fetch client with Clerk auth middleware
    │   │   └── hooks/     # TanStack Query hooks per domain
    │   ├── hooks/         # Shared React hooks
    │   ├── lib/           # Utilities (micros formatting, dates, etc.)
    │   └── stores/        # Minimal client state (Zustand if needed)
    ├── scripts/
    │   └── generate-api.sh  # Merges OpenAPI schemas + runs codegen
    ├── public/
    ├── index.html
    ├── vite.config.ts
    ├── tsconfig.json
    └── package.json
```

Note: Tailwind CSS v4 uses CSS-based configuration (`@theme` directives in `src/index.css`) rather than `tailwind.config.ts`.

## Authentication Flow

### Problem
The existing API uses API key auth (machine-to-machine). Dashboard users need interactive session auth.

### Solution
1. Tenant user visits `app.ubb.com` → Clerk handles login (email/password, Google, SSO)
2. Clerk issues a session JWT
3. Dashboard attaches JWT to every API request via `Authorization: Bearer <token>`
4. Django verifies the Clerk JWT using Clerk's JWKS endpoint

### Backend Changes Required

**New auth class: `ClerkJWTAuth`**
- Verifies Clerk JWTs via Clerk's JWKS endpoint (cached)
- Resolves the Clerk user ID → TenantUser → Tenant
- Sets `request.auth` with the same shape as `ApiKeyAuth` so existing endpoint code works unchanged

**New model: `TenantUser`**
```
TenantUser (apps/platform/tenants/)
├── id: UUID (BaseModel)
├── tenant: FK → Tenant
├── clerk_user_id: str (unique, indexed)
├── email: str
├── role: enum (owner, admin, member)  # for future RBAC
├── created_at, updated_at (BaseModel)
```

- Initial TenantUser is created during tenant signup (Clerk webhook or manual provisioning)
- Additional users invited via Clerk org invitations, synced via webhook

**Dual-auth on existing endpoints (not a new namespace)**

Rather than duplicating endpoints under `/api/v1/dashboard/`, we add `ClerkJWTAuth` as an alternative authenticator on the existing NinjaAPI instances. django-ninja supports multiple auth classes per API — a request succeeds if *any* auth class passes:

```python
metering_api = NinjaAPI(auth=[ApiKeyAuth(), ClerkJWTAuth()], ...)
```

Both auth classes set `request.auth` to the same `AuthContext(tenant=...)` shape, so endpoint code requires zero changes. This avoids duplicating endpoints and keeps a single source of truth.

### Signup Flow (v1)
1. New tenant signs up via Clerk hosted sign-up page
2. Clerk webhook fires `user.created` → Django creates Tenant + TenantUser
3. User is redirected to dashboard, fully authenticated

## API Client Strategy

### OpenAPI Schema Merging

The backend has 9 separate NinjaAPI instances, each generating its own OpenAPI schema:
- `/api/v1/docs/openapi.json` (health/ready)
- `/api/v1/metering/docs/openapi.json`
- `/api/v1/billing/docs/openapi.json`
- `/api/v1/platform/docs/openapi.json`
- `/api/v1/subscriptions/docs/openapi.json`
- `/api/v1/tenant/docs/openapi.json`
- etc.

A build script merges these into a single OpenAPI spec for codegen:

```bash
# scripts/generate-api.sh
#!/bin/bash
set -e

SCHEMAS=(
  "http://localhost:8000/api/v1/platform/openapi.json"
  "http://localhost:8000/api/v1/metering/openapi.json"
  "http://localhost:8000/api/v1/billing/openapi.json"
  "http://localhost:8000/api/v1/tenant/openapi.json"
)

# Fetch and merge schemas using openapi-merge-cli
for url in "${SCHEMAS[@]}"; do
  name=$(echo "$url" | grep -oP '/v1/\K[^/]+')
  curl -s "$url" -o "src/api/generated/${name}.json"
done

# Generate TypeScript types from each schema
for schema in src/api/generated/*.json; do
  name=$(basename "$schema" .json)
  npx openapi-typescript "$schema" -o "src/api/generated/${name}.ts"
done
```

### Client Setup

```ts
import createClient from 'openapi-fetch'
import type { paths as MeteringPaths } from './generated/metering'
import type { paths as BillingPaths } from './generated/billing'
import type { paths as PlatformPaths } from './generated/platform'

function createApiClient<T extends {}>(baseUrl: string) {
  const client = createClient<T>({ baseUrl })
  // Add Clerk auth token via middleware
  client.use({
    async onRequest({ request }) {
      const token = await clerk.session?.getToken()
      if (token) request.headers.set('Authorization', `Bearer ${token}`)
      return request
    }
  })
  return client
}

export const meteringApi = createApiClient<MeteringPaths>(
  import.meta.env.VITE_API_URL + '/api/v1/metering'
)
export const billingApi = createApiClient<BillingPaths>(
  import.meta.env.VITE_API_URL + '/api/v1/billing'
)
export const platformApi = createApiClient<PlatformPaths>(
  import.meta.env.VITE_API_URL + '/api/v1/platform'
)
```

### TanStack Query Hooks

```ts
// api/hooks/useCustomers.ts
export function useCustomers() {
  return useQuery({
    queryKey: ['customers'],
    queryFn: async () => {
      const { data, error } = await platformApi.GET('/customers/')
      if (error) throw error
      return data
    },
  })
}
```

### Dev Script
```json
"api:generate": "bash scripts/generate-api.sh"
```

## Backend Endpoints — Gaps to Fill

The dashboard requires several endpoints that don't exist yet:

### Platform (`/api/v1/platform/`)
- `GET /customers/` — list customers for tenant (paginated, filterable)
- `GET /customers/{id}/` — customer detail
- `PUT /customers/{id}/` — update customer
- `DELETE /customers/{id}/` — soft delete customer

### Billing (`/api/v1/billing/`)
- `GET /wallets/` — list all wallets for tenant (for dashboard overview + low-balance alerts)

### Metering (`/api/v1/metering/`)
- `GET /analytics/overview/` — aggregated dashboard metrics (total usage, revenue, active customers)

These will be built as part of the implementation plan.

## Pages & Views

### Overview
- **Dashboard Home** — key metrics (total usage, revenue, active customers, wallet balances), usage trend charts

### Customers
- **Customer List** — searchable/filterable DataTable with balance, status, created date
- **Customer Detail** — usage history, wallet balance, transactions, invoices, runs

### Metering
- **Pricing** — CRUD for provider rates and markups (the backend's two pricing primitives)
- **Usage Explorer** — query and visualize usage events by customer, event type, time range
- **Analytics** — revenue breakdowns, usage trends, top customers

### Billing
- **Wallets** — customer wallet balances overview, low-balance alerts
- **Transactions** — filterable transaction log
- **Invoices** — list with status, download/view detail
- **Top-Ups** — auto top-up configs, top-up attempt history

### Settings
- **General** — tenant name, API keys (view/rotate), webhook URLs
- **Team** — manage tenant users (Clerk-powered)
- **Webhooks** — configure endpoints, view delivery logs
- **Stripe** — connection status, account linking

### Deferred (v2+)
- Referrals management
- Subscription management
- Run monitoring (real-time)
- Widget configuration (managing `/api/v1/me/` widget settings)

## Layout

```
┌─────────────────────────────────────────────────┐
│  Sidebar (collapsible)  │  Top Bar              │
│                         │  Cmd+K search bar     │
│  Logo                   │  Clerk <UserButton/>  │
│  ─────────              ├───────────────────────│
│  Dashboard              │                       │
│  Customers              │   Page Content        │
│  Metering ▸             │                       │
│    Pricing              │   (tables, charts,    │
│    Usage Explorer       │    forms, details)    │
│    Analytics            │                       │
│  Billing ▸              │                       │
│    Wallets              │                       │
│    Transactions         │                       │
│    Invoices             │                       │
│    Top-Ups              │                       │
│  Settings ▸             │                       │
└─────────────────────────┴───────────────────────┘
```

## Component Patterns

| Pattern | Approach |
|---|---|
| Data tables | shadcn DataTable on TanStack Table — sortable, filterable, paginated |
| Charts | Recharts wrapped in shadcn chart components |
| Forms | React Hook Form + Zod validation + shadcn form components |
| Modals/Sheets | shadcn Dialog for confirmations, Sheet for side panels |
| Currency display | Utility to format micros → `$12.34` |
| Loading states | TanStack Query isPending → shadcn Skeleton |
| Error states | Query isError → error card with retry button |
| Error boundary | Global React error boundary + TanStack Router 404 fallback |
| Toast notifications | Sonner for mutation feedback |

## Deployment

### Local Development
```bash
cd ubb-ui
pnpm install
pnpm dev          # Vite dev server on localhost:5173
                  # Proxies /api to localhost:8000 (Django)
```

Vite config proxies `/api` to Django in dev — no CORS issues locally.

### Production
- **Dashboard:** `app.ubb.com` — Cloudflare Pages, static dist/ folder
- **API:** `api.ubb.com` — Django backend
- **CORS:** Add `app.ubb.com` to `CORS_ALLOWED_ORIGINS` env var on Django. `CORS_ALLOW_CREDENTIALS` is already enabled.
- Build command: `pnpm build` (runs `tsc && vite build`)

### Environment Variables
```
VITE_API_URL=https://api.ubb.com
VITE_CLERK_PUBLISHABLE_KEY=pk_live_...
```

### Dev Scripts
```json
{
  "dev": "vite",
  "build": "tsc && vite build",
  "preview": "vite preview",
  "api:generate": "bash scripts/generate-api.sh",
  "lint": "eslint src/",
  "test": "vitest"
}
```

### Testing
- **Unit/Integration:** Vitest + React Testing Library
- **API mocking:** MSW (Mock Service Worker) for tests without hitting Django
- **E2E:** Playwright (deferred to v2, but structure supports it)
