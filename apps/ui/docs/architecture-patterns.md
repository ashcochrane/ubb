# Architecture: Patterns

## Routing

TanStack Router with file-based route generation. The `@tanstack/router-plugin/vite` plugin watches `src/routes/` and generates `src/routeTree.gen.ts` automatically.

### Route Structure

```
__root.tsx                          → Root layout, 404 handler
├── sign-in.tsx                     → /sign-in (public)
├── _authenticated.tsx              → Auth guard + app shell
│   ├── index.tsx                   → / (dashboard)
│   ├── customers/index.tsx         → /customers
│   ├── customers/$customerId.tsx   → /customers/:customerId
│   ├── metering/pricing.tsx        → /metering/pricing
│   ├── metering/pricing.new.tsx    → /metering/pricing/new
│   ├── metering/dashboard.tsx      → /metering/dashboard
│   ├── billing/wallets.tsx         → /billing/wallets
│   ├── billing/transactions.tsx    → /billing/transactions
│   ├── billing/invoices.tsx        → /billing/invoices
│   ├── billing/top-ups.tsx         → /billing/top-ups
│   ├── settings/general.tsx        → /settings/general
│   ├── settings/team.tsx           → /settings/team
│   ├── settings/webhooks.tsx       → /settings/webhooks
│   └── settings/stripe.tsx         → /settings/stripe
```

### Route Pattern

Routes are thin — they define the route and delegate to feature components:

```typescript
import { createFileRoute } from "@tanstack/react-router";
import { PricingCardsPage } from "@/components/metering/pricing/pricing-cards-page";

export const Route = createFileRoute("/_authenticated/metering/pricing")({
  component: PricingCardsPage,
});
```

For stub pages (not yet implemented), the route file contains its own simple placeholder component.

### Auth Guard

`_authenticated.tsx` uses `beforeLoad` to check Clerk auth and redirect unauthenticated users:

```typescript
beforeLoad: ({ context }) => {
  if (!context.auth?.isSignedIn) {
    throw redirect({ to: "/sign-in" });
  }
},
```

The authenticated layout wraps all child routes with the sidebar + top bar shell.

## Authentication

**Provider:** Clerk (`@clerk/react`)

**Flow:**
1. `ClerkProvider` wraps the app in `main.tsx`
2. `InnerApp` registers the token getter with `setAuthTokenGetter()`
3. Router waits for `isLoaded` before rendering
4. Auth context (`isSignedIn`, `isLoaded`, `getToken`) is passed to the router
5. `_authenticated` route guard checks context and redirects if needed
6. Every API request gets a fresh JWT via middleware

**Rules:**
- Tokens are in memory only — never stored in localStorage
- Token getter is called per-request for freshness
- Sign-in page is the only public route

## State Management

### Server State: TanStack Query

All data from the API is managed through TanStack Query hooks in `src/api/hooks/`.

```typescript
// src/api/hooks/use-pricing.ts
export function usePricingCards() {
  return useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => meteringApi.GET("/rate-cards"),
    // or mock data via initialData during development
  });
}
```

**Defaults (configured in main.tsx):**
- `staleTime: 30_000` (30 seconds)
- `retry: 1`

**Rules:**
- All server data goes through TanStack Query — never `useEffect` + `useState` for fetching
- Query keys are descriptive arrays: `["pricing-cards"]`, `["customers", customerId]`
- Mutations use `useMutation` with `onSuccess` invalidation

### Client State: Zustand

For UI-only state that doesn't come from the API (theme, sidebar state, wizard form state).

```typescript
import { create } from "zustand";

interface ThemeStore {
  theme: "light" | "dark";
  toggle: () => void;
}

export const useTheme = create<ThemeStore>((set) => ({
  theme: "light",
  toggle: () => set((s) => ({ theme: s.theme === "light" ? "dark" : "light" })),
}));
```

**Rules:**
- One store per concern, keep small
- Never put server data in Zustand — that's TanStack Query's job
- Component-local state (modal open, input focus) stays in React `useState`

## Data Fetching Pattern

### Current Approach (Mock Data Phase)

During development, hooks return mock data via `initialData` or inline data. When the backend is ready, swap to real `queryFn` calls.

```typescript
// Development — mock data
export function usePricingCards() {
  return useQuery({
    queryKey: ["pricing-cards"],
    queryFn: async () => mockPricingCards, // from lib/mock-data/metering.ts
    initialData: mockPricingCards,
  });
}

// Production — real API
export function usePricingCards() {
  return useQuery({
    queryKey: ["pricing-cards"],
    queryFn: () => meteringApi.GET("/rate-cards").then(r => r.data),
  });
}
```

### Mock Data Location

All mock data lives in `src/lib/mock-data/`. Currently:
- `metering.ts` — Rate cards, cost data, usage events, templates

**Mock data rules:**
- Realistic but obviously fake values (e.g., "Acme Corp", model names from real LLMs)
- Cover all UI states: populated, empty, loading, error
- Same shape as real API responses
- Never imported directly by components — only through hooks

## Forms

**Stack:** React Hook Form + Zod + `@hookform/resolvers`

```typescript
const schema = z.object({
  name: z.string().min(1, "Required"),
  provider: z.string().min(1, "Select a provider"),
});

type FormValues = z.infer<typeof schema>;

function MyForm() {
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: { name: "", provider: "" },
  });

  const onSubmit = (values: FormValues) => { /* mutation */ };

  return <form onSubmit={form.handleSubmit(onSubmit)}>...</form>;
}
```

**Rules:**
- Every form uses Zod schema for validation
- Default values always provided
- Submit handlers call TanStack Query mutations
- Multi-step wizards use a single `useForm` instance shared across steps

## Error Handling

- **Route-level:** TanStack Router error boundaries
- **Component-level:** `<ErrorBoundary>` component in `src/components/error-boundary.tsx`
- **API errors:** TanStack Query's built-in error states
- **Toast notifications:** Sonner for transient error/success messages

## Tables

Built with TanStack Table v8 for headless functionality + shadcn `<Table>` for presentation.

```typescript
const columns: ColumnDef<Customer>[] = [
  { accessorKey: "name", header: "Name" },
  { accessorKey: "email", header: "Email" },
];

function CustomersTable({ data }: { data: Customer[] }) {
  const table = useReactTable({ data, columns, getCoreRowModel: getCoreRowModel() });
  return <Table>...</Table>;
}
```

## Formatting Utilities

`src/lib/format.ts` provides consistent formatting across the app:

| Function | Purpose | Example |
|----------|---------|---------|
| `formatMicros()` | Micros to currency | `1500000` -> `"$1.50"` |
| `formatCostMicros()` | Cost display | `1247000000` -> `"$1,247"` |
| `formatPrice()` | Rate card pricing | `100, 1000000` -> `"$0.10 / 1M"` |
| `formatDate()` | ISO to readable | -> `"Apr 9, 2026, 02:30 PM"` |
| `formatRelativeDate()` | Time ago | -> `"3h ago"` |
| `formatEventCount()` | Abbreviate numbers | `84219` -> `"84.2k"` |
| `formatPercentChange()` | Trend display | -> `"+12.3%"` |

All monetary values in the backend use **micros** (1 dollar = 1,000,000 micros). Always use the format utilities — never divide by 1M inline.
