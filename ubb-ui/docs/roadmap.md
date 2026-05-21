# Roadmap

## Phase Overview

| Phase | Name | Status | Description |
|-------|------|--------|-------------|
| 1 | Foundation | Complete | Project setup, routing, auth, layout, shared components |
| 2 | Metering | Complete | Pricing cards, new card wizard, cost dashboard |
| 3 | Customers | Complete | Customer list, customer detail |
| 4 | Dashboard | Complete | Home dashboard with stats overview |
| 5 | Billing | Planned | Wallets, transactions, invoices, top-ups |
| 6 | Settings | Planned | General, team, webhooks, Stripe integration |
| 7 | API Integration | Planned | Replace mock data with real backend calls |
| 8 | Polish | Planned | Error states, loading optimisation, accessibility audit |

---

## Phase 1: Foundation (Complete)

Setup the project scaffolding and core infrastructure.

- [x] Vite + React 19 + TypeScript project setup
- [x] Tailwind CSS v4 with design tokens
- [x] shadcn/ui component library installation
- [x] TanStack Router with file-based routing
- [x] Clerk authentication integration
- [x] Auth guard (`_authenticated` layout route)
- [x] App shell: sidebar navigation + top bar
- [x] Theme toggle (dark/light mode)
- [x] API client infrastructure (openapi-fetch + auth middleware)
- [x] Testing setup (Vitest + RTL + MSW)
- [x] OpenAPI codegen script

**Exit criteria:** App boots, auth works, navigation between sections, dev proxy to backend.

---

## Phase 2: Metering (Complete)

Build the metering section — the core value of the UBB platform.

### Pricing Cards Page (`/metering/pricing`)
- [x] Grid display of rate cards
- [x] Search and status filtering (All / Active / Drafts)
- [x] Provider filter
- [x] Summary statistics bar
- [x] Empty state

### New Card Wizard (`/metering/pricing/new`)
- [x] 4-step wizard with stepper component
- [x] Step 1: Source selection (template vs custom)
- [x] Step 2: Card details (name, provider, pricing pattern)
- [x] Step 3: Dimension configuration with live cost tester
- [x] Step 4: Review with dry-run simulator and sanity checks
- [x] Form state management across steps (React Hook Form + Zod)

### Cost Dashboard (`/metering/dashboard`)
- [x] Period selector (7d, 30d, 90d, YTD)
- [x] Summary stats row
- [x] Cost-over-time area chart (Recharts)
- [x] Cost breakdowns by product and card
- [x] Cost-by-dimension table
- [x] Recent usage events table

**Exit criteria:** All metering screens functional with mock data. Formatting utilities tested.

---

## Phase 3: Customers (Complete)

- [x] Customer list with TanStack Table
- [x] Column definitions (name, email, status, etc.)
- [x] Customer detail page (`/customers/:customerId`)

**Exit criteria:** Customer list renders, detail page shows customer info.

---

## Phase 4: Dashboard (Complete)

- [x] Stats cards showing key metrics
- [x] Dashboard home page

**Exit criteria:** Dashboard shows overview metrics from mock data.

---

## Phase 5: Billing (Planned)

Build the billing management section.

### Wallets (`/billing/wallets`)
- [ ] Customer wallet list with balances
- [ ] Low-balance alerts/indicators
- [ ] Wallet detail view
- [ ] Manual balance adjustment

### Transactions (`/billing/transactions`)
- [ ] Transaction history table with filters
- [ ] Transaction detail/breakdown
- [ ] Export functionality

### Invoices (`/billing/invoices`)
- [ ] Invoice list with status (draft, sent, paid, overdue)
- [ ] Invoice detail view
- [ ] Invoice generation

### Top-Ups (`/billing/top-ups`)
- [ ] Top-up history
- [ ] Manual top-up form
- [ ] Auto top-up configuration

**Exit criteria:** All billing screens functional with mock data, tables sortable/filterable.

---

## Phase 6: Settings (Planned)

### General (`/settings/general`)
- [ ] Tenant name and configuration
- [ ] API key management (view, rotate, revoke)

### Team (`/settings/team`)
- [ ] Team member list
- [ ] Invite new members
- [ ] Role management

### Webhooks (`/settings/webhooks`)
- [ ] Webhook endpoint configuration
- [ ] Event type subscriptions
- [ ] Delivery history/logs

### Stripe (`/settings/stripe`)
- [ ] Stripe account connection
- [ ] Payment method configuration
- [ ] Sync status

**Exit criteria:** All settings screens functional, forms validate with Zod.

---

## Phase 7: API Integration (Planned)

Replace mock data with real backend API calls.

- [ ] Generate types from OpenAPI spec (`pnpm api:generate`)
- [ ] Replace mock `queryFn` with real API calls in all hooks
- [ ] Add proper error handling for API failures
- [ ] Add optimistic updates for mutations
- [ ] Add loading skeletons to all data-dependent components
- [ ] Test against running backend

**Exit criteria:** All screens work with real API. No mock data in production builds.

---

## Phase 8: Polish (Planned)

- [ ] Comprehensive error boundaries on all routes
- [ ] Accessibility audit (keyboard nav, focus management, aria labels)
- [ ] Responsive design pass (tablet breakpoints)
- [ ] Performance audit (bundle size, lazy loading routes)
- [ ] Toast notifications for all mutations
- [ ] Empty state designs for all list views
- [ ] Loading skeleton coverage

**Exit criteria:** Production-ready quality. No unhandled error states.
