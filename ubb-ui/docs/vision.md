# Product Vision

## What is UBB?

UBB (Usage-Based Billing) is a platform that enables SaaS companies to implement usage-based pricing models. It handles the full lifecycle: defining rate cards, ingesting usage events, computing costs, managing customer wallets, and generating invoices.

## Who is it for?

**Primary persona:** Platform/billing engineers at SaaS companies who need to:
- Define flexible pricing models (per-unit, tiered, volume-based)
- Track real-time usage and costs
- Manage prepaid wallet balances
- Generate and reconcile invoices
- Configure Stripe integration for payment processing

**Secondary persona:** Business stakeholders who need visibility into:
- Cost analytics and trends
- Customer usage patterns
- Revenue metrics

## What does the UI do?

The UBB UI is the admin dashboard for the platform. It provides:

1. **Metering** — Define rate cards with pricing dimensions, monitor costs and usage events
2. **Billing** — Manage customer wallets, view transactions, generate invoices, handle top-ups
3. **Customers** — View and manage tenant customers, their usage, and billing status
4. **Settings** — Configure the tenant: API keys, team members, webhooks, Stripe connection
5. **Dashboard** — High-level overview of platform health and key metrics

## Technical Strategy

- **Frontend-first development:** Build the UI against mock data, then connect to the real backend API
- **Type-safe API integration:** OpenAPI codegen generates TypeScript types from the backend spec
- **Multi-tenant:** Each tenant sees only their own data. Auth and tenant scoping handled by Clerk + backend
- **Modern React:** No SSR needed (SaaS behind auth). Vite + React 19 + TanStack ecosystem

## Success Criteria

- All screens functional with real backend API
- Sub-second page loads with optimistic updates
- Responsive design (desktop-first, functional on tablet)
- Dark mode support
- Accessible (keyboard navigation, screen reader support)
