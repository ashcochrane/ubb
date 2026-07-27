# CLAUDE.md — UBB UI

## MANDATORY: Session Start

1. Read `PROGRESS.md` — know current implementation status
2. Read `docs/superpowers/specs/2026-04-09-full-rebuild-design.md` — the master design spec
3. Read `docs/design/ui-flow-design-rationale.md` — understand the product, page flows, and why decisions were made
4. Read `docs/architecture.md` and companion docs as needed for the task
5. Summarise to user: "Picking up from [last]. Current phase: [X]. Next: [Y]."

---

## Key Reference Documents

| Document | Purpose | When to read |
|----------|---------|-------------|
| `PROGRESS.md` | What's done, what's next | Every session start |
| `docs/superpowers/specs/2026-04-09-full-rebuild-design.md` | Architecture, structure, provider pattern, auth, build phases | Every session start |
| `docs/design/ui-flow-design-rationale.md` | Product vision, page purposes, cross-page links, design principles | Before building any feature |
| `docs/design/files/*.html` | HTML mockups — the source of truth for every screen | Before building a specific page |
| `docs/architecture.md` | Tech stack, project structure, API architecture | When making structural decisions |
| `docs/architecture-components.md` | Design tokens, typography, Tailwind config, component conventions | When building UI |
| `docs/architecture-patterns.md` | Routing, auth, state management, data fetching patterns | When writing hooks/queries/routes |
| `docs/roadmap.md` | Build phases with feature checklists | When planning work |

---

## Architecture Quick Reference

| Layer | Choice |
|-------|--------|
| Framework | React 19 + Vite 8 + TypeScript 5.9 |
| Server state | TanStack Query v5 |
| Client state | Zustand 5 |
| Components | shadcn/ui (Base UI primitives) |
| Styling | Tailwind CSS v4 |
| Routing | TanStack Router (file-based, type-safe) |
| Forms | React Hook Form + Zod |
| Charts | Recharts |
| HTTP | openapi-fetch + openapi-typescript |
| Auth | Clerk (@clerk/react) |
| Icons | Lucide |
| Font | Geist Variable |
| Testing | Vitest + React Testing Library + MSW |
| Toasts | Sonner |

---

## Project Structure (Feature Co-location)

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
│           ├── pricing-cards/      — Card list + wizard
│           ├── products/           — Product groupings
│           ├── customers/          — Customer mapping management
│           ├── billing/            — Margin management
│           ├── export/             — Data export
│           ├── onboarding/         — Mode selection + setup
│           └── settings/           — Stripe, API keys, account
├── features/                       — Feature modules (fully co-located)
│   ├── auth/                       — Auth hooks, stores
│   ├── dashboard/                  — Dashboard components + API
│   ├── pricing-cards/              — Card list, wizard + API
│   ├── onboarding/                 — Mode selection, Stripe setup + API
│   ├── customers/                  — Mapping management + API
│   ├── reconciliation/             — Timeline, edits, adjustments + API
│   ├── billing/                    — Margin management + API
│   └── export/                     — Data export + API
├── components/                     — Shared UI only
│   ├── ui/                         — shadcn base components
│   └── shared/                     — Nav shell, page header, stat card
├── api/                            — API infrastructure ONLY
│   └── client.ts                   — openapi-fetch client + auth middleware
├── hooks/                          — Truly shared hooks
├── lib/                            — Pure utilities
│   ├── api-provider.ts             — Provider selection (mock | api)
│   ├── format.ts                   — Currency, date, number formatting
│   ├── query-client.ts             — QueryClient instance
│   └── utils.ts                    — cn() and helpers
├── stores/                         — App-wide Zustand stores
│   └── auth-store.ts               — Tenant context, permissions
├── types/                          — Shared domain types
└── styles/
    └── app.css                     — Design tokens, Tailwind imports
```

---

## Provider Pattern

Controls whether features use mock data or the real API via `VITE_API_PROVIDER` env var.

### Per-Feature API Structure

Every feature has this identical folder layout:

```
features/{feature}/api/
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

// features/pricing-cards/api/queries.ts
import { pricingCardsApi } from "./provider";
export const usePricingCards = () =>
  useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => pricingCardsApi.getCards(),
  });
```

---

## Dependency Rules (Imports Flow DOWN Only)

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

## File Size Standards

| Type | Limit |
|------|-------|
| Component files | <200 lines |
| Hook files | <150 lines |
| API adapter files | <300 lines |
| Store files | <100 lines |
| Type files | <200 lines |
| Route files | <50 lines |

---

## Code Patterns

### Route Pattern — thin, delegates to feature

```typescript
import { createFileRoute } from "@tanstack/react-router";
import { PricingCardsPage } from "@/features/pricing-cards/components/pricing-cards-page";

export const Route = createFileRoute("/_app/pricing-cards/")({
  component: PricingCardsPage,
});
```

### Component Pattern — focused, uses hooks

```typescript
export function PricingCardsPage() {
  const { data: cards, isLoading } = usePricingCards();
  if (isLoading) return <PricingCardsSkeleton />;
  return <PageHeader title="Pricing Cards" />;
}
```

### Form Pattern — React Hook Form + Zod, always

```typescript
const schema = z.object({ name: z.string().min(1, "Required") });

function CardForm() {
  const form = useForm<z.infer<typeof schema>>({
    resolver: zodResolver(schema),
    defaultValues: { name: "" },
  });
  const mutation = useCreatePricingCard();
  return <form onSubmit={form.handleSubmit((v) => mutation.mutate(v))}>...</form>;
}
```

### Zustand Store — small, one concern

```typescript
export const useAuthStore = create<AuthState>((set) => ({
  activeTenantId: null,
  tenantMode: null,
  setTenant: (id, mode) => set({ activeTenantId: id, tenantMode: mode }),
}));
```

---

## Design Source of Truth

**HTML mockups in `docs/design/files/` are the source of truth for every screen.**

Before building any page:
1. Open the relevant HTML mockup(s) in a browser
2. Read the corresponding section in `docs/design/ui-flow-design-rationale.md`
3. Understand _why_ the page exists and how it connects to other pages
4. Build to match the mockup — pixel-level fidelity is the goal

### Mockup Inventory

| Feature | Mockup files |
|---------|-------------|
| Dashboard | `dashboard.html` |
| Pricing wizard | `pricing_card_creation_flow.html`, `custom_card_details_step.html`, `custom_card_dimensions_step.html`, `custom_card_review_test_step.html` |
| Onboarding | `complete_onboarding_4_screens.html`, `billing_mode_stripe_adaptation.html`, `billing_onboarding_fresh_customer_4_steps.html`, `screen_4_stripe_integration.html`, `step_2_customer_identification.html`, `step_2_customer_mapping.html`, `step_3_confirm_and_activate.html` |
| Customer mapping | `customer_mapping_management.html` |
| Reconciliation | `unified_reconciliation_v3.html` |
| Margin management | `margin-management-dashboard.html` |
| Data export | `data_export_page.html` |

---

## Navigation Model

From `docs/design/ui-flow-design-rationale.md`:

```
Sidebar:
├── Dashboard                    → /
├── Pricing Cards                → /pricing-cards
├── Products                     → /products
├── Customers                    → /customers
├── Billing (if billing mode)    → /billing
├── Export                       → /export
└── Settings                     → /settings
```

Onboarding (`/onboarding`) is a separate flow, not in the sidebar.
Reconciliation is accessed by clicking a pricing card, not a top-level nav item.

---

## Auth

**Clerk** handles identity. **Zustand auth store** holds tenant context and permissions.

- No-auth dev mode: when `VITE_CLERK_PUBLISHABLE_KEY` is blank and `VITE_API_PROVIDER=mock`, skip Clerk entirely and auto-bootstrap mock session
- Tokens in memory only — never localStorage
- Fresh JWT injected per-request via openapi-fetch middleware

---

## Environment Variables

```bash
VITE_API_PROVIDER=mock          # mock | api
VITE_API_URL=http://localhost:8000
VITE_CLERK_PUBLISHABLE_KEY=     # Blank = dev mode (no auth)
```

---

## Formatting

All monetary values use **micros** (1 dollar = 1,000,000 micros). Always use `src/lib/format.ts` utilities. Never divide by 1M inline.

---

## Implementation Checklist (New Feature)

- [ ] Read PROGRESS.md for current status
- [ ] Read design spec + relevant mockup HTML files
- [ ] Read `docs/design/ui-flow-design-rationale.md` for the feature's section
- [ ] Create feature folder: `features/{name}/components/` + `features/{name}/api/`
- [ ] Create API layer: types.ts, mock.ts, mock-data.ts, api.ts, queries.ts, provider.ts
- [ ] Build components matching the HTML mockup
- [ ] Create thin route file in `app/routes/_app/`
- [ ] Update nav config (if new sidebar item)
- [ ] Loading states use skeletons
- [ ] Empty states handled
- [ ] Forms use React Hook Form + Zod
- [ ] File size limits respected
- [ ] No cross-feature imports
- [ ] Route file <50 lines
- [ ] Update PROGRESS.md

---

## Git & Commits

**NEVER commit, push, or create branches.** The user handles all git operations. Do not run `git commit`, `git push`, `git checkout -b`, or any git write commands. You may run read-only git commands (`git status`, `git log`, `git diff`) to understand the repo state.

When work is ready to commit, tell the user what changed and suggest a commit message:

```
{type}({scope}): {description}

Types: feat, fix, refactor, docs, test, chore
Scope: pricing-cards, dashboard, onboarding, customers, reconciliation, billing, export, settings, shared, infra

Examples:
feat(pricing-cards): add 4-step creation wizard
fix(dashboard): correct cost chart date range filtering
```

---

## What NOT to Do

- Don't import from one feature into another
- Don't import API client directly in feature components — use feature's queries.ts
- Don't put business logic in route files
- Don't use `useEffect` for data fetching (use TanStack Query)
- Don't use `useState` for server data
- Don't use spinners for initial loads (use skeletons)
- Don't skip PROGRESS.md updates
- Don't start a feature without reading its mockup and the design rationale
- Don't add features not in the design spec
- Don't modify shadcn components directly
- Don't use inline styles
- Don't store tokens in localStorage (memory only)
- Don't hardcode API URLs
- Don't add `any` types
- Don't edit `routeTree.gen.ts`
- Don't divide by 1M inline — use format utilities

## Three Design Principles (from design rationale)

Every page must embody:
1. **Fast** — No page requires more than 3 clicks for its primary action. Pre-fill where possible. Optimistic UI where safe.
2. **Easy** — No jargon without explanation. Concrete examples and previews over definitions. The simulator/previewer pattern is the primary teaching tool.
3. **Risk-free** — Destructive actions have confirmation steps. Price changes never silently affect historical data. Draft states exist. Anomaly alerts catch surprises.
