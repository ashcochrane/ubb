# UI ↔ API Wire-Up Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace four mocked UI feature surfaces (margins, customers, pricing-card editing, billing customer panel) with real calls to the existing backend, so what ships matches what the platform actually supports.

**Architecture:** Each feature follows the existing `api.ts` → `provider.ts` → `queries.ts` → `components/` layering, with `selectProvider({ mock, api })` letting both layers coexist while we cut over. Generated openapi-typescript types in `src/api/generated/` are the contract source of truth — feature `types.ts` files are derived from them, not invented. Where backend reality is narrower than the existing mock UI (most notably the margin tree), the UI is reshaped down to what the backend exposes rather than padded with synthetic data.

**Tech Stack:** React 19, TanStack Router + Query, openapi-fetch, openapi-typescript, vitest + Testing Library, Tailwind + base-ui, Django-ninja backend.

**Working directory:** all `pnpm`, `pnpm vitest`, `pnpm tsc`, `git add` of `src/...` paths, and references to relative paths like `src/api/...` in this plan run from `ubb-ui/`. Open one shell there and stay in it. The only exceptions are commands explicitly noted as repo-root (e.g. running the Django dev server).

**Key constraints discovered during prep:**

- `GET /platform/tenant/default-margin` returns only `{ defaultMarginPct: number }` — there is no margin hierarchy or change-history endpoint. The current `MarginPage` UI (tree + stats + history) is mostly fiction. This plan reshapes the margin page down to a single editable default-margin form and removes the unsupported pieces.
- `GET /billing/customers/{id}/transactions` has no typed response schema (only a 200 description). We treat it as `unknown[]` at the boundary and define a UI-side `BillingTransaction` shape mirroring what the backend serializer actually returns. A backend schema annotation is captured as a follow-up.
- `me` namespace is fetched and types are generated, but no `meApi` client exists yet. Out of scope for this plan (no /me UI in the agreed scope), but `client.ts` will get a `meApi` export anyway so future work doesn't need to touch the client again.
- Backend `CreateCustomerRequest` requires `externalId` and accepts optional `stripeCustomerId` + `metadata`. There is no `sdkIdentifier` concept on the backend — what the old UI called `sdkIdentifier` is the new `externalId`.

---

## File Structure

### New files

- `src/api/types.ts` — re-export helpers (`PlatformSchemas`, `MeteringSchemas`, `BillingSchemas`) for ergonomic consumption of generated component schemas.
- `src/features/customers/api/api.ts` — **replaced** (delete current contents, see Task 3.1).
- `src/features/customers/api/types.ts` — **replaced**.
- `src/features/customers/api/queries.ts` — **replaced**.
- `src/features/customers/components/customers-page.tsx` — new list page.
- `src/features/customers/components/customer-detail-page.tsx` — new detail page.
- `src/features/customers/components/customer-create-dialog.tsx` — new create modal.
- `src/features/billing/api/api.ts` — **replaced** (margins → default margin only).
- `src/features/billing/api/types.ts` — **trimmed** to what the new page needs.
- `src/features/billing/api/queries.ts` — **trimmed**.
- `src/features/billing/components/default-margin-page.tsx` — new simplified page replacing `margin-page.tsx`.
- `src/features/billing-ops/` — **new feature** for per-customer billing operations (balance, transactions, top-up, refund, withdraw, auto-top-up).
  - `api/api.ts`, `api/mock.ts`, `api/provider.ts`, `api/queries.ts`, `api/types.ts`
  - `components/customer-billing-panel.tsx`
  - `components/top-up-dialog.tsx`
  - `components/withdraw-dialog.tsx`
  - `components/auto-top-up-form.tsx`
  - `components/transactions-table.tsx`
- `src/features/pricing-cards/components/card-edit-form.tsx` — new metadata edit form (used in `$cardId` page).
- `src/features/pricing-cards/components/rate-edit-dialog.tsx` — new add/edit rate dialog.
- `src/app/routes/_app/customers/$customerId.tsx` — new detail route.

### Modified files

- `src/api/client.ts` — add `meApi` export.
- `src/components/shared/nav-config.ts` — rename "Billing" item label/url if needed (kept as-is, but the section comment updated).
- `src/app/routes/_app/billing/index.lazy.tsx` — point at `DefaultMarginPage`.
- `src/app/routes/_app/customers/index.tsx` — point at new `CustomersPage`.
- `src/app/routes/_app/pricing-cards/$cardId.lazy.tsx` — render new `CardEditForm` and rate management UI.
- `src/features/pricing-cards/api/api.ts` — add PATCH/DELETE card + rate CRUD.
- `src/features/pricing-cards/api/mock.ts` — add matching mock implementations.
- `src/features/pricing-cards/api/queries.ts` — add `usePricingCard(cardId)`, update/delete card + rate mutations (all routed through provider).
- `src/app/routes/_app/pricing-cards/$cardId.lazy.tsx` — currently renders `ReconciliationPage` (a feature with no backend). Replaced by a new `CardDetailPage` that combines `CardEditForm` and the rate management UI. Reconciliation is out of scope; see follow-ups doc.

### Deleted files

- `src/features/customers/components/customer-mapping-page.tsx`
- `src/features/customers/components/customer-table.tsx`
- `src/features/customers/components/customer-row-edit.tsx`
- `src/features/customers/components/orphan-row.tsx`
- `src/features/customers/components/orphaned-events-section.tsx`
- `src/features/customers/components/mapping-stats-grid.tsx`
- `src/features/customers/components/alert-banners.tsx`
- `src/features/customers/components/sync-status-bar.tsx`
- `src/features/customers/api/mock.ts` (replaced by new mock)
- `src/features/customers/api/mock-data.ts` (replaced by new mock data)
- `src/features/billing/components/margin-page.tsx`
- `src/features/billing/components/margin-stats.tsx`
- `src/features/billing/components/margin-tree.tsx`
- `src/features/billing/components/margin-tree-row.tsx`
- `src/features/billing/components/margin-edit-panel.tsx`
- `src/features/billing/components/change-history.tsx`
- `src/features/billing/components/impact-preview.tsx`
- `src/features/billing/api/mock.ts` (replaced)
- `src/features/billing/api/mock-data.ts` (replaced)

---

## Phase 1 — Foundations

### Task 1.1: Add `meApi` client export

**Files:**
- Modify: `src/api/client.ts`

- [ ] **Step 1: Add `MePaths` import and `meApi` export**

This is a surgical edit — do NOT rename or restructure anything else in the file. `setAuthTokenGetter` is imported from `src/main.tsx`; leave its name and signature untouched.

In `src/api/client.ts`:

1. Add the import alongside the other generated-path imports:

   ```ts
   import type { paths as MePaths } from "./generated/me";
   ```

2. Add the export after `tenantApi`:

   ```ts
   export const meApi = createApiClient<MePaths>("/api/v1/me");
   ```

That's it. No other changes.

- [ ] **Step 2: Verify typecheck**

Run: `pnpm tsc -b --noEmit 2>&1 | head -50`
Expected: existing errors only (we'll fix those in later tasks). No NEW errors introduced by the `meApi` line.

- [ ] **Step 3: Commit**

```bash
git add src/api/client.ts
git commit -m "feat(ui): add meApi client export"
```

### Task 1.2: Add schema re-export helper

**Files:**
- Create: `src/api/types.ts`

- [ ] **Step 1: Write helper**

```ts
// src/api/types.ts
//
// Shortcut for consuming generated component schemas from each namespace.
// Use like: `type Customer = PlatformSchemas["CustomerDetailResponse"]`.

import type { components as BillingComponents } from "./generated/billing";
import type { components as MeComponents } from "./generated/me";
import type { components as MeteringComponents } from "./generated/metering";
import type { components as PlatformComponents } from "./generated/platform";
import type { components as TenantComponents } from "./generated/tenant";

export type PlatformSchemas = PlatformComponents["schemas"];
export type MeteringSchemas = MeteringComponents["schemas"];
export type BillingSchemas = BillingComponents["schemas"];
export type TenantSchemas = TenantComponents["schemas"];
export type MeSchemas = MeComponents["schemas"];
```

- [ ] **Step 2: Verify typecheck**

Run: `pnpm tsc -b --noEmit 2>&1 | grep "api/types.ts"`
Expected: no output (no errors from this file).

- [ ] **Step 3: Commit**

```bash
git add src/api/types.ts
git commit -m "feat(ui): add schema re-export helper for generated types"
```

### Task 1.3: Wire `pnpm api:check` into CI guidance

**Files:**
- Modify: `src/api/README.md` (or create it if missing)

- [ ] **Step 1: Check whether `src/api/README.md` exists**

Run: `ls src/api/README.md 2>&1`

- [ ] **Step 2: Create or update README**

Create `src/api/README.md` with:

```markdown
# API client + generated types

This directory holds:

- `client.ts` — typed openapi-fetch clients, one per backend namespace.
- `schemas/` — local snapshots of each namespace's `openapi.json` (path prefixes stripped to match `client.ts` `baseUrl`). **Tracked in git.** Snapshots are the reviewable contract — diffs here are how backend changes surface in UI PRs.
- `generated/` — TypeScript types derived from the snapshots. **Gitignored** (`src/api/generated/*.ts`); regenerated locally and in CI.
- `types.ts` — convenience re-exports of generated component schemas.

## Regenerating

With the Django dev server running on `http://localhost:8000`:

```bash
pnpm api:regen      # fetch snapshots + generate types
pnpm api:fetch      # snapshots only (needs server)
pnpm api:generate   # types only (offline)
pnpm api:check      # regen + fail if `src/api/schemas` differs from committed state
```

`api:check` only meaningfully diffs `src/api/schemas` (the tracked snapshots). `src/api/generated` is gitignored, so changes there never trip the check — they're rebuilt from the snapshots.

Feature `types.ts` files should derive from `PlatformSchemas` / `MeteringSchemas` / `BillingSchemas` (see `src/api/types.ts`) rather than redeclare shapes. Anything we add on top (UI-only fields, computed flags) lives next to the derived type.
```

- [ ] **Step 3: Commit**

```bash
git add src/api/README.md
git commit -m "docs(ui): document api client regeneration workflow"
```

---

## Phase 2 — Margins (replace `/margins` with `/tenant/default-margin`)

**Scope reduction:** the existing `MarginPage` renders stats, a margin hierarchy tree, an edit panel, change history, and impact preview — none of which exist on the backend. The backend only exposes `GET/PATCH /platform/tenant/default-margin`, returning `{ defaultMarginPct: number }`. We collapse the page to one editable card. The follow-up "margin hierarchy" backend work is recorded in `docs/plans/` (out of scope here).

### Task 2.1: Replace billing types

**Files:**
- Modify: `src/features/billing/api/types.ts`

- [ ] **Step 1: Replace file contents**

```ts
// src/features/billing/api/types.ts
import type { PlatformSchemas } from "@/api/types";

export type DefaultMargin = PlatformSchemas["TenantDefaultMarginResponse"];
export type UpdateDefaultMarginRequest =
  PlatformSchemas["UpdateTenantDefaultMarginRequest"];
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing/api/types.ts
git commit -m "refactor(ui): collapse billing types to default-margin scope"
```

### Task 2.2: Replace billing API client

**Files:**
- Modify: `src/features/billing/api/api.ts`

- [ ] **Step 1: Replace file**

```ts
// src/features/billing/api/api.ts
import { platformApi } from "@/api/client";
import type { DefaultMargin, UpdateDefaultMarginRequest } from "./types";

export async function getDefaultMargin(): Promise<DefaultMargin> {
  const { data, error } = await platformApi.GET("/tenant/default-margin", {});
  if (error || !data) throw error ?? new Error("Failed to load default margin");
  return data;
}

export async function updateDefaultMargin(
  req: UpdateDefaultMarginRequest,
): Promise<DefaultMargin> {
  const { data, error } = await platformApi.PATCH("/tenant/default-margin", {
    body: req,
  });
  if (error || !data) throw error ?? new Error("Failed to update default margin");
  return data;
}
```

- [ ] **Step 2: Replace mock**

Replace `src/features/billing/api/mock.ts`:

```ts
// src/features/billing/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type { DefaultMargin, UpdateDefaultMarginRequest } from "./types";

let _stub: DefaultMargin = { defaultMarginPct: 20 };

export async function getDefaultMargin(): Promise<DefaultMargin> {
  await mockDelay();
  return _stub;
}

export async function updateDefaultMargin(
  req: UpdateDefaultMarginRequest,
): Promise<DefaultMargin> {
  await mockDelay();
  _stub = { defaultMarginPct: req.defaultMarginPct };
  return _stub;
}
```

- [ ] **Step 3: Delete obsolete mock-data**

```bash
git rm src/features/billing/api/mock-data.ts
```

- [ ] **Step 4: Update provider**

Replace `src/features/billing/api/provider.ts`:

```ts
// src/features/billing/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const billingMarginApi = selectProvider({ mock, api });
```

(The export name is unchanged so we don't have to update the queries file's import path more than necessary — but the contents are now the two new functions.)

- [ ] **Step 5: Commit**

```bash
git add src/features/billing/api/
git commit -m "refactor(ui): point billing margins at /tenant/default-margin"
```

### Task 2.3: Update billing queries

**Files:**
- Modify: `src/features/billing/api/queries.ts`

- [ ] **Step 1: Replace file**

```ts
// src/features/billing/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { billingMarginApi } from "./provider";
import type { UpdateDefaultMarginRequest } from "./types";

const QUERY_KEY = ["default-margin"] as const;

export function useDefaultMargin() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => billingMarginApi.getDefaultMargin(),
  });
}

export function useUpdateDefaultMargin() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateDefaultMarginRequest) =>
      billingMarginApi.updateDefaultMargin(req),
    onSuccess: (data) => qc.setQueryData(QUERY_KEY, data),
    onError: toastOnError("Couldn't update default margin"),
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing/api/queries.ts
git commit -m "refactor(ui): rewrite billing queries for default margin"
```

### Task 2.4: Write failing test for `DefaultMarginPage`

**Files:**
- Create: `src/features/billing/components/default-margin-page.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useDefaultMargin: () => ({ data: { defaultMarginPct: 20 }, isLoading: false }),
  useUpdateDefaultMargin: () => ({ mutateAsync: updateMutate, isPending: false }),
}));

import { DefaultMarginPage } from "./default-margin-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(DefaultMarginPage),
    ),
  );
}

describe("DefaultMarginPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue({ defaultMarginPct: 25 });
  });

  it("renders the current default margin", () => {
    renderPage();
    expect(screen.getByDisplayValue("20")).toBeInTheDocument();
  });

  it("submits a new margin value", async () => {
    renderPage();
    const input = screen.getByLabelText(/default margin/i) as HTMLInputElement;
    fireEvent.change(input, { target: { value: "25" } });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith({ defaultMarginPct: 25 });
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/billing/components/default-margin-page.test.tsx`
Expected: FAIL — "Cannot find module './default-margin-page'".

### Task 2.5: Implement `DefaultMarginPage`

**Files:**
- Create: `src/features/billing/components/default-margin-page.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useDefaultMargin, useUpdateDefaultMargin } from "../api/queries";

export function DefaultMarginPage() {
  const { data, isLoading } = useDefaultMargin();
  const update = useUpdateDefaultMargin();
  const [value, setValue] = useState<string>("");

  useEffect(() => {
    if (data) setValue(String(data.defaultMarginPct));
  }, [data]);

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  const parsed = Number.parseFloat(value);
  const valid = Number.isFinite(parsed) && parsed >= 0 && parsed < 100;
  const dirty = valid && parsed !== data.defaultMarginPct;

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!dirty) return;
    update.mutateAsync({ defaultMarginPct: parsed });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Default margin"
        description="Markup applied to API costs when no product-, card- or customer-level override exists."
      />
      <Card className="max-w-md">
        <CardHeader>
          <CardTitle className="text-base">Default margin</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="default-margin">Default margin (%)</Label>
              <Input
                id="default-margin"
                type="number"
                min={0}
                max={99.99}
                step={0.01}
                value={value}
                onChange={(e) => setValue(e.target.value)}
              />
            </div>
            <Button type="submit" disabled={!dirty || update.isPending}>
              {update.isPending ? "Saving…" : "Save"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm vitest run src/features/billing/components/default-margin-page.test.tsx`
Expected: PASS (both tests).

- [ ] **Step 3: Commit**

```bash
git add src/features/billing/components/default-margin-page.{tsx,test.tsx}
git commit -m "feat(ui): default margin page wired to backend"
```

### Task 2.6: Point billing route at new page and delete legacy margin UI

**Files:**
- Modify: `src/app/routes/_app/billing/index.lazy.tsx`
- Delete: 7 margin-* components

- [ ] **Step 1: Update lazy route**

```tsx
// src/app/routes/_app/billing/index.lazy.tsx
import { createLazyFileRoute } from "@tanstack/react-router";
import { DefaultMarginPage } from "@/features/billing/components/default-margin-page";

export const Route = createLazyFileRoute("/_app/billing/")({
  component: DefaultMarginPage,
});
```

- [ ] **Step 2: Delete legacy components**

```bash
git rm \
  src/features/billing/components/margin-page.tsx \
  src/features/billing/components/margin-stats.tsx \
  src/features/billing/components/margin-tree.tsx \
  src/features/billing/components/margin-tree-row.tsx \
  src/features/billing/components/margin-edit-panel.tsx \
  src/features/billing/components/change-history.tsx \
  src/features/billing/components/impact-preview.tsx
```

- [ ] **Step 3: Typecheck**

Run: `pnpm tsc -b --noEmit 2>&1 | grep -E "features/billing"`
Expected: empty (no errors in billing feature).

- [ ] **Step 4: Smoke test in dev server**

Run: `pnpm dev` in background.
Open `http://localhost:5173/billing`, confirm the default-margin form renders, edit + save, observe network call to `PATCH /api/v1/platform/tenant/default-margin`. Stop dev server.

- [ ] **Step 5: Commit**

```bash
git add -A src/app/routes/_app/billing src/features/billing/components
git commit -m "feat(ui): delete legacy margin tree UI"
```

---

## Phase 3 — Customers (rebuild around real CRUD)

### Task 3.1: Replace customers types

**Files:**
- Modify: `src/features/customers/api/types.ts`

- [ ] **Step 1: Replace file**

```ts
// src/features/customers/api/types.ts
import type { PlatformSchemas } from "@/api/types";

export type Customer = PlatformSchemas["CustomerDetailResponse"];
export type CustomerListResponse = PlatformSchemas["CustomerListResponse"];
// POST /customers returns 201 with CustomerResponse, which is a thinner shape
// than CustomerDetailResponse (no `metadata` etc.). Re-export for clarity.
export type CreatedCustomer = PlatformSchemas["CustomerResponse"];
export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type UpdateCustomerRequest = PlatformSchemas["UpdateCustomerRequest"];

export type CustomerStatus = "active" | "suspended" | "archived";
export const CUSTOMER_STATUSES: CustomerStatus[] = [
  "active",
  "suspended",
  "archived",
];
```

- [ ] **Step 2: Commit**

```bash
git add src/features/customers/api/types.ts
git commit -m "refactor(ui): rewrite customer types from platform schema"
```

### Task 3.2: Replace customers API client

**Files:**
- Modify: `src/features/customers/api/api.ts`
- Modify: `src/features/customers/api/mock.ts`
- Modify: `src/features/customers/api/provider.ts`
- Delete: `src/features/customers/api/mock-data.ts`

- [ ] **Step 1: Rewrite `api.ts`**

```ts
// src/features/customers/api/api.ts
import { platformApi } from "@/api/client";
import type {
  CreateCustomerRequest,
  CreatedCustomer,
  Customer,
  CustomerListResponse,
  UpdateCustomerRequest,
} from "./types";

export async function listCustomers(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CustomerListResponse> {
  const { data, error } = await platformApi.GET("/customers", {
    params: { query: params },
  });
  if (error || !data) throw error ?? new Error("Failed to list customers");
  return data;
}

export async function getCustomer(customerId: string): Promise<Customer> {
  const { data, error } = await platformApi.GET("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
  });
  if (error || !data) throw error ?? new Error("Failed to load customer");
  return data;
}

export async function createCustomer(
  req: CreateCustomerRequest,
): Promise<CreatedCustomer> {
  const { data, error, response } = await platformApi.POST("/customers", {
    body: req,
  });
  if (error || !data) {
    throw error ?? new Error(`Create customer failed (${response.status})`);
  }
  return data;
}

export async function updateCustomer(
  customerId: string,
  req: UpdateCustomerRequest,
): Promise<Customer> {
  const { data, error } = await platformApi.PATCH("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
    body: req,
  });
  if (error || !data) throw error ?? new Error("Failed to update customer");
  return data;
}

export async function deleteCustomer(customerId: string): Promise<void> {
  const { error } = await platformApi.DELETE("/customers/{customer_id}", {
    params: { path: { customer_id: customerId } },
  });
  if (error) throw error;
}
```

- [ ] **Step 2: Rewrite `mock.ts`**

```ts
// src/features/customers/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type {
  CreateCustomerRequest,
  CreatedCustomer,
  Customer,
  CustomerListResponse,
  UpdateCustomerRequest,
} from "./types";

let _store: Customer[] = [
  {
    id: "cus_001",
    externalId: "acme",
    stripeCustomerId: "cus_stripe_001",
    status: "active",
    minBalanceMicros: null,
    metadata: {},
    createdAt: new Date().toISOString(),
  } as Customer,
];

export async function listCustomers(): Promise<CustomerListResponse> {
  await mockDelay();
  return { data: _store, hasMore: false, nextCursor: null };
}

export async function getCustomer(id: string): Promise<Customer> {
  await mockDelay();
  const found = _store.find((c) => c.id === id);
  if (!found) throw new Error("not found");
  return found;
}

export async function createCustomer(
  req: CreateCustomerRequest,
): Promise<CreatedCustomer> {
  await mockDelay();
  const created: Customer = {
    id: `cus_${Math.random().toString(36).slice(2, 8)}`,
    externalId: req.externalId,
    stripeCustomerId: req.stripeCustomerId ?? "",
    status: "active",
    minBalanceMicros: null,
    metadata: req.metadata ?? {},
    createdAt: new Date().toISOString(),
  } as Customer;
  _store.push(created);
  return {
    id: created.id,
    externalId: created.externalId,
    stripeCustomerId: created.stripeCustomerId ?? "",
    status: created.status,
  };
}

export async function updateCustomer(
  id: string,
  req: UpdateCustomerRequest,
): Promise<Customer> {
  await mockDelay();
  const idx = _store.findIndex((c) => c.id === id);
  if (idx < 0) throw new Error("not found");
  _store[idx] = {
    ...(_store[idx] as Customer),
    ...(req.status != null ? { status: req.status } : {}),
    ...(req.stripeCustomerId != null
      ? { stripeCustomerId: req.stripeCustomerId }
      : {}),
    ...(req.minBalanceMicros !== undefined
      ? { minBalanceMicros: req.minBalanceMicros }
      : {}),
    ...(req.metadata != null ? { metadata: req.metadata } : {}),
  } as Customer;
  return _store[idx] as Customer;
}

export async function deleteCustomer(id: string): Promise<void> {
  await mockDelay();
  _store = _store.filter((c) => c.id !== id);
}
```

- [ ] **Step 3: Rewrite `provider.ts`**

```ts
// src/features/customers/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const customersApi = selectProvider({ mock, api });
```

- [ ] **Step 4: Delete old mock-data**

```bash
git rm src/features/customers/api/mock-data.ts
```

- [ ] **Step 5: Commit**

```bash
git add src/features/customers/api/
git commit -m "refactor(ui): point customers feature at real /customers CRUD"
```

### Task 3.3: Replace customers queries

**Files:**
- Modify: `src/features/customers/api/queries.ts`

- [ ] **Step 1: Replace file**

```ts
// src/features/customers/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { customersApi } from "./provider";
import type {
  CreateCustomerRequest,
  UpdateCustomerRequest,
} from "./types";

const LIST_KEY = ["customers", "list"] as const;
const detailKey = (id: string) => ["customers", "detail", id] as const;

export function useCustomers() {
  return useQuery({
    queryKey: LIST_KEY,
    queryFn: () => customersApi.listCustomers(),
  });
}

export function useCustomer(customerId: string) {
  return useQuery({
    queryKey: detailKey(customerId),
    queryFn: () => customersApi.getCustomer(customerId),
    enabled: !!customerId,
  });
}

export function useCreateCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: CreateCustomerRequest) => customersApi.createCustomer(req),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
    onError: toastOnError("Couldn't create customer"),
  });
}

// Note: createCustomer resolves to a CustomerResponse (the thinner shape
// returned by POST /customers). Callers can read .id from the mutation result
// to navigate to the new detail page.

export function useUpdateCustomer(customerId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateCustomerRequest) =>
      customersApi.updateCustomer(customerId, req),
    onSuccess: (data) => {
      qc.setQueryData(detailKey(customerId), data);
      qc.invalidateQueries({ queryKey: LIST_KEY });
    },
    onError: toastOnError("Couldn't update customer"),
  });
}

export function useDeleteCustomer() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (customerId: string) => customersApi.deleteCustomer(customerId),
    onSuccess: () => qc.invalidateQueries({ queryKey: LIST_KEY }),
    onError: toastOnError("Couldn't delete customer"),
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/customers/api/queries.ts
git commit -m "refactor(ui): rewrite customer queries for real CRUD"
```

### Task 3.4: Write failing test for `CustomersPage`

**Files:**
- Create: `src/features/customers/components/customers-page.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const createMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCustomers: () => ({
    data: {
      data: [
        {
          id: "cus_1",
          externalId: "acme",
          stripeCustomerId: "cus_stripe_1",
          status: "active",
          minBalanceMicros: null,
          metadata: {},
          createdAt: "2026-05-01T00:00:00Z",
        },
      ],
      hasMore: false,
      nextCursor: null,
    },
    isLoading: false,
  }),
  useCreateCustomer: () => ({ mutateAsync: createMutate, isPending: false }),
}));

vi.mock("@tanstack/react-router", () => ({
  Link: ({ to, children }: { to: string; children: React.ReactNode }) =>
    React.createElement("a", { href: to }, children),
  useNavigate: () => vi.fn(),
}));

import { CustomersPage } from "./customers-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomersPage),
    ),
  );
}

describe("CustomersPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createMutate.mockResolvedValue({
      id: "cus_new",
      externalId: "wayne",
      stripeCustomerId: "",
      status: "active",
    });
  });

  it("renders customer rows", () => {
    renderPage();
    expect(screen.getByText("acme")).toBeInTheDocument();
    expect(screen.getByText(/active/i)).toBeInTheDocument();
  });

  it("opens the create dialog and submits", async () => {
    renderPage();
    fireEvent.click(screen.getByRole("button", { name: /new customer/i }));
    const externalIdInput = await screen.findByLabelText(/external id/i);
    fireEvent.change(externalIdInput, { target: { value: "wayne" } });
    fireEvent.click(screen.getByRole("button", { name: /^create$/i }));
    await waitFor(() => {
      expect(createMutate).toHaveBeenCalledWith({
        externalId: "wayne",
        stripeCustomerId: "",
        metadata: {},
      });
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/customers/components/customers-page.test.tsx`
Expected: FAIL — module not found for `./customers-page`.

### Task 3.5: Implement `CustomerCreateDialog`

**Files:**
- Create: `src/features/customers/components/customer-create-dialog.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateCustomer } from "../api/queries";

export function CustomerCreateDialog() {
  const [open, setOpen] = useState(false);
  const [externalId, setExternalId] = useState("");
  const [stripeCustomerId, setStripeCustomerId] = useState("");
  const create = useCreateCustomer();
  const navigate = useNavigate();

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!externalId.trim()) return;
    const created = await create.mutateAsync({
      externalId: externalId.trim(),
      stripeCustomerId: stripeCustomerId.trim(),
      metadata: {},
    });
    setOpen(false);
    setExternalId("");
    setStripeCustomerId("");
    navigate({ to: "/customers/$customerId", params: { customerId: created.id } });
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>New customer</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>New customer</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="external-id">External ID</Label>
            <Input
              id="external-id"
              value={externalId}
              onChange={(e) => setExternalId(e.target.value)}
              placeholder="customer identifier you send from your app"
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="stripe-id">Stripe customer ID (optional)</Label>
            <Input
              id="stripe-id"
              value={stripeCustomerId}
              onChange={(e) => setStripeCustomerId(e.target.value)}
              placeholder="cus_…"
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => setOpen(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? "Creating…" : "Create"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Confirm `Dialog` exists**

Run: `ls src/components/ui/dialog.tsx`
Expected: file present. If missing, install via `pnpm dlx shadcn@latest add dialog` and commit.

- [ ] **Step 3: Commit**

```bash
git add src/features/customers/components/customer-create-dialog.tsx
# plus dialog.tsx if newly added
git commit -m "feat(ui): customer create dialog"
```

### Task 3.6: Implement `CustomersPage`

**Files:**
- Create: `src/features/customers/components/customers-page.tsx`

- [ ] **Step 1: Write component**

```tsx
import { Link } from "@tanstack/react-router";
import { Loader2 } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useCustomers } from "../api/queries";
import { CustomerCreateDialog } from "./customer-create-dialog";

export function CustomersPage() {
  const { data, isLoading } = useCustomers();

  return (
    <div className="space-y-6">
      <PageHeader
        title="Customers"
        description="Customers your SDK sends usage for."
        actions={<CustomerCreateDialog />}
      />

      {isLoading || !data ? (
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Loader2 className="h-4 w-4 animate-spin" /> Loading…
        </div>
      ) : data.data.length === 0 ? (
        <div className="rounded-lg border border-dashed p-12 text-center text-sm text-muted-foreground">
          No customers yet. Click <span className="font-medium">New customer</span> to add one.
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>External ID</TableHead>
              <TableHead>Stripe ID</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Created</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {data.data.map((c) => (
              <TableRow key={c.id}>
                <TableCell>
                  <Link
                    to="/customers/$customerId"
                    params={{ customerId: c.id }}
                    className="font-medium hover:underline"
                  >
                    {c.externalId}
                  </Link>
                </TableCell>
                <TableCell className="text-muted-foreground">
                  {c.stripeCustomerId || "—"}
                </TableCell>
                <TableCell>{c.status}</TableCell>
                <TableCell className="text-muted-foreground">
                  {new Date(c.createdAt).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Check `PageHeader` accepts `actions`**

Run: `grep -E "actions" src/components/shared/page-header.tsx`
Expected: an `actions?: ReactNode` prop. If missing, add it before continuing:

```tsx
// in PageHeader's props
actions?: React.ReactNode;
// in JSX, render `{actions && <div>{actions}</div>}` in the header row
```

- [ ] **Step 3: Run tests**

Run: `pnpm vitest run src/features/customers/components/customers-page.test.tsx`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add src/features/customers/components/customers-page.tsx src/components/shared/page-header.tsx
git commit -m "feat(ui): customers list page wired to real API"
```

### Task 3.7: Write failing test for `CustomerDetailPage`

**Files:**
- Create: `src/features/customers/components/customer-detail-page.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();
const deleteMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCustomer: () => ({
    data: {
      id: "cus_1",
      externalId: "acme",
      stripeCustomerId: "cus_stripe_1",
      status: "active",
      minBalanceMicros: null,
      metadata: {},
      createdAt: "2026-05-01T00:00:00Z",
    },
    isLoading: false,
  }),
  useUpdateCustomer: () => ({ mutateAsync: updateMutate, isPending: false }),
  useDeleteCustomer: () => ({ mutateAsync: deleteMutate, isPending: false }),
}));

vi.mock("@tanstack/react-router", () => ({
  useNavigate: () => vi.fn(),
}));

import { CustomerDetailPage } from "./customer-detail-page";

function renderPage() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomerDetailPage, { customerId: "cus_1" }),
    ),
  );
}

describe("CustomerDetailPage", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue(undefined);
    deleteMutate.mockResolvedValue(undefined);
  });

  it("renders the customer's external id and stripe id", () => {
    renderPage();
    expect(screen.getByDisplayValue("acme")).toBeInTheDocument();
    expect(screen.getByDisplayValue("cus_stripe_1")).toBeInTheDocument();
  });

  it("submits a status change", async () => {
    renderPage();
    const select = screen.getByLabelText(/status/i);
    fireEvent.change(select, { target: { value: "suspended" } });
    fireEvent.click(screen.getByRole("button", { name: /save changes/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({ status: "suspended" }),
      );
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/customers/components/customer-detail-page.test.tsx`
Expected: FAIL — module not found.

### Task 3.8: Implement `CustomerDetailPage`

**Files:**
- Create: `src/features/customers/components/customer-detail-page.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  useCustomer,
  useDeleteCustomer,
  useUpdateCustomer,
} from "../api/queries";
import { CUSTOMER_STATUSES, type CustomerStatus } from "../api/types";

export function CustomerDetailPage({ customerId }: { customerId: string }) {
  const { data, isLoading } = useCustomer(customerId);
  const update = useUpdateCustomer(customerId);
  const remove = useDeleteCustomer();
  const navigate = useNavigate();

  const [externalId, setExternalId] = useState("");
  const [stripeCustomerId, setStripeCustomerId] = useState("");
  const [status, setStatus] = useState<CustomerStatus>("active");

  useEffect(() => {
    if (!data) return;
    setExternalId(data.externalId);
    setStripeCustomerId(data.stripeCustomerId ?? "");
    setStatus((data.status as CustomerStatus) ?? "active");
  }, [data]);

  if (isLoading || !data) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    update.mutateAsync({
      stripeCustomerId,
      status,
      minBalanceMicros: data?.minBalanceMicros ?? null,
      metadata: data?.metadata ?? {},
    });
  }

  async function onDelete() {
    if (!confirm(`Delete customer ${data?.externalId}?`)) return;
    await remove.mutateAsync(customerId);
    navigate({ to: "/customers" });
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={data.externalId}
        description={`Created ${new Date(data.createdAt).toLocaleString()}`}
        actions={
          <Button variant="destructive" onClick={onDelete} disabled={remove.isPending}>
            Delete
          </Button>
        }
      />
      <Card className="max-w-xl">
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="external-id">External ID</Label>
              <Input id="external-id" value={externalId} disabled />
              <p className="text-xs text-muted-foreground">
                External ID is immutable.
              </p>
            </div>
            <div className="space-y-2">
              <Label htmlFor="stripe-id">Stripe customer ID</Label>
              <Input
                id="stripe-id"
                value={stripeCustomerId}
                onChange={(e) => setStripeCustomerId(e.target.value)}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="status">Status</Label>
              <select
                id="status"
                className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
                value={status}
                onChange={(e) => setStatus(e.target.value as CustomerStatus)}
              >
                {CUSTOMER_STATUSES.map((s) => (
                  <option key={s} value={s}>
                    {s}
                  </option>
                ))}
              </select>
            </div>
            <Button type="submit" disabled={update.isPending}>
              {update.isPending ? "Saving…" : "Save changes"}
            </Button>
          </form>
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm vitest run src/features/customers/components/customer-detail-page.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/features/customers/components/customer-detail-page.{tsx,test.tsx}
git commit -m "feat(ui): customer detail/edit page"
```

### Task 3.9: Add detail route + repoint list route

**Files:**
- Create: `src/app/routes/_app/customers/$customerId.tsx`
- Modify: `src/app/routes/_app/customers/index.tsx`

- [ ] **Step 1: Repoint list route**

```tsx
// src/app/routes/_app/customers/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { CustomersPage } from "@/features/customers/components/customers-page";

export const Route = createFileRoute("/_app/customers/")({
  component: CustomersPage,
});
```

- [ ] **Step 2: Add detail route**

```tsx
// src/app/routes/_app/customers/$customerId.tsx
import { createFileRoute } from "@tanstack/react-router";
import { CustomerDetailPage } from "@/features/customers/components/customer-detail-page";

export const Route = createFileRoute("/_app/customers/$customerId")({
  component: RouteComponent,
});

function RouteComponent() {
  const { customerId } = Route.useParams();
  return <CustomerDetailPage customerId={customerId} />;
}
```

- [ ] **Step 3: Regenerate router types**

Generated route tree path is `src/app/routeTree.gen.ts` (see `vite.config.ts`: `generatedRouteTree: "./src/app/routeTree.gen.ts"`).

Run `pnpm dev` long enough for the TanStack router plugin to regenerate it (it watches `src/app/routes`). Stop the dev server. Confirm `src/app/routeTree.gen.ts` now contains an entry for `/_app/customers/$customerId`.

- [ ] **Step 4: Commit**

```bash
git add src/app/routes/_app/customers/ src/app/routeTree.gen.ts
git commit -m "feat(ui): customer detail route"
```

### Task 3.10: Delete legacy customers UI

**Files:**
- Delete: 8 mapping/orphan components

- [ ] **Step 1: Delete**

```bash
git rm \
  src/features/customers/components/customer-mapping-page.tsx \
  src/features/customers/components/customer-table.tsx \
  src/features/customers/components/customer-row-edit.tsx \
  src/features/customers/components/orphan-row.tsx \
  src/features/customers/components/orphaned-events-section.tsx \
  src/features/customers/components/mapping-stats-grid.tsx \
  src/features/customers/components/alert-banners.tsx \
  src/features/customers/components/sync-status-bar.tsx
```

- [ ] **Step 2: Typecheck**

Run: `pnpm tsc -b --noEmit 2>&1 | grep -E "features/customers"`
Expected: empty.

- [ ] **Step 3: Smoke test in dev server**

Run dev server, navigate to `/customers`, create a customer (verify network call to `POST /api/v1/platform/customers`), click into detail, edit status, save, delete. Stop server.

- [ ] **Step 4: Commit**

```bash
git add -A src/features/customers/
git commit -m "chore(ui): delete legacy customer mapping/orphans UI"
```

---

## Phase 4 — Pricing card editing (PATCH + rate CRUD)

### Task 4.1: Add card metadata update + rate CRUD to API layer (both real + mock)

The pricing-cards feature already uses a `provider.ts` selector (`mock` vs `api`). Mutations must go through the provider, not call API functions directly — otherwise mock mode is broken for the new surfaces.

**Files:**
- Modify: `src/features/pricing-cards/api/api.ts`
- Modify: `src/features/pricing-cards/api/mock.ts`
- Modify: `src/features/pricing-cards/api/provider.ts` (if needed — see Step 4)

- [ ] **Step 1: Confirm existing provider shape**

Run: `cat src/features/pricing-cards/api/provider.ts`
Note the exported name (e.g. `pricingCardsApi` or similar). All mutation hooks added in Task 4.2 call methods on this exported object, never importing from `./api` directly.

- [ ] **Step 2: Extend `api.ts` (real API)**

Append to `src/features/pricing-cards/api/api.ts`:

```ts
import type { MeteringSchemas } from "@/api/types";

export type UpdateCardRequest = MeteringSchemas["UpdateCardRequest"];
export type DimensionIn = MeteringSchemas["DimensionIn"];

export async function updateCard(
  cardId: string,
  req: UpdateCardRequest,
): Promise<PricingCard> {
  const { data, error } = await meteringApi.PATCH(
    "/pricing/cards/{card_id}",
    {
      params: { path: { card_id: cardId } },
      body: req,
    },
  );
  if (error || !data) throw error ?? new Error("Failed to update card");
  return data as PricingCard;
}

export async function deleteCard(cardId: string): Promise<void> {
  const { error } = await meteringApi.DELETE("/pricing/cards/{card_id}", {
    params: { path: { card_id: cardId } },
  });
  if (error) throw error;
}

export async function createRate(
  cardId: string,
  body: DimensionIn,
): Promise<void> {
  const { error } = await meteringApi.POST("/pricing/cards/{card_id}/rates", {
    params: { path: { card_id: cardId } },
    body,
  });
  if (error) throw error;
}

export async function updateRate(
  cardId: string,
  rateId: string,
  body: DimensionIn,
): Promise<void> {
  const { error } = await meteringApi.PUT(
    "/pricing/cards/{card_id}/rates/{rate_id}",
    {
      params: { path: { card_id: cardId, rate_id: rateId } },
      body,
    },
  );
  if (error) throw error;
}

export async function deleteRate(
  cardId: string,
  rateId: string,
): Promise<void> {
  const { error } = await meteringApi.DELETE(
    "/pricing/cards/{card_id}/rates/{rate_id}",
    { params: { path: { card_id: cardId, rate_id: rateId } } },
  );
  if (error) throw error;
}
```

- [ ] **Step 3: Extend `mock.ts` with matching exports**

Open `src/features/pricing-cards/api/mock.ts`. Add (the local mock store layout will already exist — adapt to it):

```ts
import type { DimensionIn, UpdateCardRequest } from "./api";

export async function updateCard(
  cardId: string,
  req: UpdateCardRequest,
): Promise<PricingCard> {
  await mockDelay();
  const idx = mockCards.findIndex((c) => c.id === cardId);
  if (idx < 0) throw new Error("not found");
  const next = {
    ...mockCards[idx],
    ...(req.name != null ? { name: req.name } : {}),
    ...(req.description != null ? { description: req.description } : {}),
    ...(req.groupId !== undefined ? { groupId: req.groupId } : {}),
    ...(req.pricingSourceUrl != null
      ? { pricingSourceUrl: req.pricingSourceUrl }
      : {}),
    ...(req.status != null ? { status: req.status } : {}),
  };
  mockCards[idx] = next;
  return next;
}

export async function deleteCard(cardId: string): Promise<void> {
  await mockDelay();
  const idx = mockCards.findIndex((c) => c.id === cardId);
  if (idx >= 0) mockCards.splice(idx, 1);
}

export async function createRate(
  cardId: string,
  body: DimensionIn,
): Promise<void> {
  await mockDelay();
  const card = mockCards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = [
    ...card.dimensions,
    {
      id: `rate_${Math.random().toString(36).slice(2, 8)}`,
      ...body,
    },
  ];
}

export async function updateRate(
  cardId: string,
  rateId: string,
  body: DimensionIn,
): Promise<void> {
  await mockDelay();
  const card = mockCards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = card.dimensions.map((d) =>
    d.id === rateId ? { ...d, ...body } : d,
  );
}

export async function deleteRate(
  cardId: string,
  rateId: string,
): Promise<void> {
  await mockDelay();
  const card = mockCards.find((c) => c.id === cardId);
  if (!card) throw new Error("not found");
  card.dimensions = card.dimensions.filter((d) => d.id !== rateId);
}
```

(Naming of `mockCards`/`mockDelay` follows whatever the existing mock module uses. If the mock store is named differently, adapt — but keep the new functions exported from the same module.)

- [ ] **Step 4: Verify provider re-exports**

`src/features/pricing-cards/api/provider.ts` uses `selectProvider({ mock, api })` and exports the chosen module wholesale, so adding matching exports to both `api.ts` and `mock.ts` is enough — no provider edits required. Confirm by reading the file.

- [ ] **Step 5: Commit**

```bash
git add src/features/pricing-cards/api/api.ts src/features/pricing-cards/api/mock.ts
git commit -m "feat(ui): pricing card update/delete + rate CRUD (api + mock)"
```

### Task 4.2: Extend pricing-card queries

**Files:**
- Modify: `src/features/pricing-cards/api/queries.ts`

- [ ] **Step 1: Read current queries.ts**

Run: `cat src/features/pricing-cards/api/queries.ts`
Confirm: `pricingCardsApi` is already imported (line 3), `CreateCardRequest` is already typed-imported from `./types`. The existing list query uses key `["pricing-cards"]`; the **card-detail** query is added in Task 4.2a (next task) with key `["pricing-card", cardId]` — these mutations invalidate that key.

- [ ] **Step 2: Add mutations**

Do NOT duplicate the existing `import { pricingCardsApi } from "./provider";` line. Merge the new type imports with the existing `type { CreateCardRequest }` import so it reads:

```ts
import type { CreateCardRequest } from "./types";
import type { DimensionIn, UpdateCardRequest } from "./api";
```

Then append the new hooks:

```ts
export function useUpdateCard(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateCardRequest) => pricingCardsApi.updateCard(cardId, req),
    onSuccess: (data) => {
      qc.setQueryData(CARD_KEY(cardId), data);
      qc.invalidateQueries({ queryKey: ["pricing-cards"] });
    },
    onError: toastOnError("Couldn't update pricing card"),
  });
}

export function useDeleteCard() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (cardId: string) => pricingCardsApi.deleteCard(cardId),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["pricing-cards"] }),
    onError: toastOnError("Couldn't delete pricing card"),
  });
}

export function useCreateRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (req: DimensionIn) => pricingCardsApi.createRate(cardId, req),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't add rate"),
  });
}

export function useUpdateRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ rateId, body }: { rateId: string; body: DimensionIn }) =>
      pricingCardsApi.updateRate(cardId, rateId, body),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't update rate"),
  });
}

export function useDeleteRate(cardId: string) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (rateId: string) => pricingCardsApi.deleteRate(cardId, rateId),
    onSuccess: () => qc.invalidateQueries({ queryKey: CARD_KEY(cardId) }),
    onError: toastOnError("Couldn't delete rate"),
  });
}
```

If the file uses different existing query keys (e.g. `CARD_KEY(cardId)`), substitute consistently — the existing get-card query key must match what these mutations invalidate.

- [ ] **Step 3: Add `CARD_KEY` and `usePricingCard` query**

Both the mutations above and the new detail page need the per-card query key. Add to the same file (top, near other key constants):

```ts
const CARD_KEY = (cardId: string) => ["pricing-card", cardId] as const;

export function usePricingCard(cardId: string) {
  return useQuery({
    queryKey: CARD_KEY(cardId),
    queryFn: () => pricingCardsApi.getCard(cardId),
    enabled: !!cardId,
  });
}
```

- [ ] **Step 4: Commit**

```bash
git add src/features/pricing-cards/api/queries.ts
git commit -m "feat(ui): pricing card detail query + update/delete + rate mutations"
```

### Task 4.3: Write failing test for `RateEditDialog`

**Files:**
- Create: `src/features/pricing-cards/components/rate-edit-dialog.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const createRateMutate = vi.fn();
const updateRateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useCreateRate: () => ({ mutateAsync: createRateMutate, isPending: false }),
  useUpdateRate: () => ({ mutateAsync: updateRateMutate, isPending: false }),
}));

import { RateEditDialog } from "./rate-edit-dialog";

function renderDialog(props: Partial<React.ComponentProps<typeof RateEditDialog>> = {}) {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(RateEditDialog, {
        cardId: "card_1",
        open: true,
        onOpenChange: vi.fn(),
        ...props,
      }),
    ),
  );
}

describe("RateEditDialog", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    createRateMutate.mockResolvedValue(undefined);
    updateRateMutate.mockResolvedValue(undefined);
  });

  it("creates a new rate", async () => {
    renderDialog();
    fireEvent.change(screen.getByLabelText(/metric name/i), {
      target: { value: "input_tokens" },
    });
    fireEvent.change(screen.getByLabelText(/cost per unit/i), {
      target: { value: "500" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(createRateMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          metricName: "input_tokens",
          costPerUnitMicros: 500,
          unitQuantity: 1_000_000,
        }),
      );
    });
  });

  it("updates an existing rate", async () => {
    renderDialog({
      rate: {
        id: "rate_1",
        metricName: "input_tokens",
        label: "Input tokens",
        unit: "token",
        unitQuantity: 1_000_000,
        currency: "USD",
        pricingType: "per_unit",
        costPerUnitMicros: 500,
        providerCostPerUnitMicros: null,
      },
    });
    fireEvent.change(screen.getByLabelText(/cost per unit/i), {
      target: { value: "750" },
    });
    fireEvent.click(screen.getByRole("button", { name: /save/i }));
    await waitFor(() => {
      expect(updateRateMutate).toHaveBeenCalledWith({
        rateId: "rate_1",
        body: expect.objectContaining({ costPerUnitMicros: 750 }),
      });
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/pricing-cards/components/rate-edit-dialog.test.tsx`
Expected: FAIL — module not found.

### Task 4.4: Implement `RateEditDialog`

**Files:**
- Create: `src/features/pricing-cards/components/rate-edit-dialog.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useEffect, useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateRate, useUpdateRate } from "../api/queries";

export interface RateEditDialogRate {
  id: string;
  metricName: string;
  label: string;
  unit: string;
  unitQuantity: number;
  currency: string;
  pricingType: "per_unit" | "flat";
  costPerUnitMicros: number;
  providerCostPerUnitMicros: number | null;
}

export interface RateEditDialogProps {
  cardId: string;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  rate?: RateEditDialogRate;
}

export function RateEditDialog({
  cardId,
  open,
  onOpenChange,
  rate,
}: RateEditDialogProps) {
  const create = useCreateRate(cardId);
  const update = useUpdateRate(cardId);

  // unitQuantity is how many of `unit` the costPerUnitMicros applies to.
  // Backend default is 1_000_000 (e.g. price per million tokens). Keep that
  // default so simple "per unit" pricing still works without surfacing the
  // field; expose an advanced input for cases like per-1k-token.
  const [metricName, setMetricName] = useState("");
  const [label, setLabel] = useState("");
  const [unit, setUnit] = useState("");
  const [unitQuantity, setUnitQuantity] = useState("1000000");
  const [pricingType, setPricingType] = useState<"per_unit" | "flat">("per_unit");
  const [costPerUnitMicros, setCostPerUnitMicros] = useState("0");
  const [providerCostPerUnitMicros, setProviderCostPerUnitMicros] =
    useState<string>("");

  useEffect(() => {
    setMetricName(rate?.metricName ?? "");
    setLabel(rate?.label ?? "");
    setUnit(rate?.unit ?? "");
    setUnitQuantity(String(rate?.unitQuantity ?? 1_000_000));
    setPricingType(rate?.pricingType ?? "per_unit");
    setCostPerUnitMicros(String(rate?.costPerUnitMicros ?? 0));
    setProviderCostPerUnitMicros(
      rate?.providerCostPerUnitMicros != null
        ? String(rate.providerCostPerUnitMicros)
        : "",
    );
  }, [rate, open]);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const body = {
      metricName: metricName.trim(),
      label,
      unit,
      unitQuantity: Number(unitQuantity) || 1_000_000,
      currency: "USD",
      pricingType,
      costPerUnitMicros: Number(costPerUnitMicros) || 0,
      providerCostPerUnitMicros:
        providerCostPerUnitMicros === ""
          ? null
          : Number(providerCostPerUnitMicros),
    };
    if (rate) {
      await update.mutateAsync({ rateId: rate.id, body });
    } else {
      await create.mutateAsync(body);
    }
    onOpenChange(false);
  }

  const pending = create.isPending || update.isPending;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{rate ? "Edit rate" : "New rate"}</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="metric-name">Metric name</Label>
            <Input
              id="metric-name"
              value={metricName}
              onChange={(e) => setMetricName(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="label">Label</Label>
            <Input
              id="label"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="unit">Unit</Label>
            <Input
              id="unit"
              value={unit}
              onChange={(e) => setUnit(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="pricing-type">Pricing type</Label>
            <select
              id="pricing-type"
              className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
              value={pricingType}
              onChange={(e) =>
                setPricingType(e.target.value as "per_unit" | "flat")
              }
            >
              <option value="per_unit">Per unit</option>
              <option value="flat">Flat</option>
            </select>
          </div>
          <div className="space-y-2">
            <Label htmlFor="cost-per-unit">Cost per unit (micros)</Label>
            <Input
              id="cost-per-unit"
              type="number"
              min={0}
              value={costPerUnitMicros}
              onChange={(e) => setCostPerUnitMicros(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="unit-quantity">
              Unit quantity (how many units the cost applies to)
            </Label>
            <Input
              id="unit-quantity"
              type="number"
              min={1}
              value={unitQuantity}
              onChange={(e) => setUnitQuantity(e.target.value)}
            />
            <p className="text-xs text-muted-foreground">
              Default is 1,000,000 (cost is per million units).
            </p>
          </div>
          <div className="space-y-2">
            <Label htmlFor="provider-cost">
              Provider cost per unit (micros, optional)
            </Label>
            <Input
              id="provider-cost"
              type="number"
              min={0}
              value={providerCostPerUnitMicros}
              onChange={(e) => setProviderCostPerUnitMicros(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button
              type="button"
              variant="ghost"
              onClick={() => onOpenChange(false)}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={pending}>
              {pending ? "Saving…" : "Save"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm vitest run src/features/pricing-cards/components/rate-edit-dialog.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/features/pricing-cards/components/rate-edit-dialog.{tsx,test.tsx}
git commit -m "feat(ui): rate add/edit dialog"
```

### Task 4.5: Write failing test for `CardEditForm`

**Files:**
- Create: `src/features/pricing-cards/components/card-edit-form.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const updateMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useUpdateCard: () => ({ mutateAsync: updateMutate, isPending: false }),
  useGroups: () => ({ data: [], isLoading: false }),
}));

import { CardEditForm } from "./card-edit-form";

const card = {
  id: "card_1",
  name: "OpenAI GPT-4o",
  description: "OpenAI pricing",
  pricingSourceUrl: "https://openai.com/pricing",
  groupId: null,
  groupName: null,
  status: "active",
  dimensions: [],
  createdAt: "2026-05-01T00:00:00Z",
} as const;

function renderForm() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CardEditForm, { card }),
    ),
  );
}

describe("CardEditForm", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    updateMutate.mockResolvedValue(card);
  });

  it("renders the current card metadata", () => {
    renderForm();
    expect(screen.getByDisplayValue("OpenAI GPT-4o")).toBeInTheDocument();
    expect(screen.getByDisplayValue("OpenAI pricing")).toBeInTheDocument();
  });

  it("submits a metadata change", async () => {
    renderForm();
    const name = screen.getByLabelText(/^name$/i);
    fireEvent.change(name, { target: { value: "OpenAI GPT-4o (USD)" } });
    fireEvent.click(screen.getByRole("button", { name: /save card/i }));
    await waitFor(() => {
      expect(updateMutate).toHaveBeenCalledWith(
        expect.objectContaining({ name: "OpenAI GPT-4o (USD)" }),
      );
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/pricing-cards/components/card-edit-form.test.tsx`
Expected: FAIL — module not found.

### Task 4.6: Implement `CardEditForm`

**Files:**
- Create: `src/features/pricing-cards/components/card-edit-form.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import type { PricingCard } from "../api/types";
import { useGroups, useUpdateCard } from "../api/queries";

export function CardEditForm({ card }: { card: PricingCard }) {
  const groups = useGroups();
  const update = useUpdateCard(card.id);

  const [name, setName] = useState(card.name);
  const [description, setDescription] = useState(card.description ?? "");
  const [pricingSourceUrl, setPricingSourceUrl] = useState(
    card.pricingSourceUrl ?? "",
  );
  const [groupId, setGroupId] = useState<string | null>(card.groupId ?? null);

  useEffect(() => {
    setName(card.name);
    setDescription(card.description ?? "");
    setPricingSourceUrl(card.pricingSourceUrl ?? "");
    setGroupId(card.groupId ?? null);
  }, [card]);

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    update.mutateAsync({
      name,
      description,
      pricingSourceUrl,
      groupId,
    });
  }

  return (
    <form onSubmit={onSubmit} className="space-y-4">
      <div className="space-y-2">
        <Label htmlFor="card-name">Name</Label>
        <Input
          id="card-name"
          value={name}
          onChange={(e) => setName(e.target.value)}
          required
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="card-description">Description</Label>
        <Input
          id="card-description"
          value={description}
          onChange={(e) => setDescription(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="card-source-url">Pricing source URL</Label>
        <Input
          id="card-source-url"
          value={pricingSourceUrl}
          onChange={(e) => setPricingSourceUrl(e.target.value)}
        />
      </div>
      <div className="space-y-2">
        <Label htmlFor="card-group">Group</Label>
        <select
          id="card-group"
          className="border-input bg-background h-9 w-full rounded-md border px-3 text-sm"
          value={groupId ?? ""}
          onChange={(e) => setGroupId(e.target.value || null)}
        >
          <option value="">No group</option>
          {(groups.data ?? []).map((g) => (
            <option key={g.id} value={g.id}>
              {g.name}
            </option>
          ))}
        </select>
      </div>
      <Button type="submit" disabled={update.isPending}>
        {update.isPending ? "Saving…" : "Save card"}
      </Button>
    </form>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm vitest run src/features/pricing-cards/components/card-edit-form.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/features/pricing-cards/components/card-edit-form.{tsx,test.tsx}
git commit -m "feat(ui): pricing card metadata edit form"
```

### Task 4.7: Implement `CardDetailPage` and replace reconciliation route

The current `$cardId.lazy.tsx` renders `ReconciliationPage` — a feature with no backend (no `/rate-cards/{id}/reconciliation` endpoint exists). We replace that route with a real card detail surface that combines `CardEditForm` and rate management. The reconciliation feature remains on disk but is detached from any route; it stays parked behind a deferred backend design (see follow-ups doc).

**Files:**
- Create: `src/features/pricing-cards/components/card-detail-page.tsx`
- Modify: `src/app/routes/_app/pricing-cards/$cardId.lazy.tsx`

- [ ] **Step 1: Write `CardDetailPage`**

```tsx
// src/features/pricing-cards/components/card-detail-page.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import { useNavigate } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import {
  useDeleteCard,
  useDeleteRate,
  usePricingCard,
} from "../api/queries";
import { CardEditForm } from "./card-edit-form";
import { RateEditDialog, type RateEditDialogRate } from "./rate-edit-dialog";

export function CardDetailPage({ cardId }: { cardId: string }) {
  const { data: card, isLoading } = usePricingCard(cardId);
  const deleteCard = useDeleteCard();
  const deleteRate = useDeleteRate(cardId);
  const navigate = useNavigate();

  const [rateDialogOpen, setRateDialogOpen] = useState(false);
  const [editingRate, setEditingRate] = useState<RateEditDialogRate | null>(null);

  if (isLoading || !card) {
    return (
      <div className="flex items-center gap-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" /> Loading…
      </div>
    );
  }

  async function onDeleteCard() {
    if (!confirm(`Delete card "${card.name}"?`)) return;
    await deleteCard.mutateAsync(cardId);
    navigate({ to: "/pricing-cards" });
  }

  async function onDeleteRate(rateId: string, metricName: string) {
    if (!confirm(`Delete rate ${metricName}?`)) return;
    await deleteRate.mutateAsync(rateId);
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title={card.name}
        description={card.description ?? ""}
        actions={
          <Button variant="destructive" onClick={onDeleteCard} disabled={deleteCard.isPending}>
            Delete card
          </Button>
        }
      />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Details</CardTitle>
        </CardHeader>
        <CardContent>
          <CardEditForm card={card} />
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Rates</CardTitle>
          <Button
            onClick={() => {
              setEditingRate(null);
              setRateDialogOpen(true);
            }}
          >
            Add rate
          </Button>
        </CardHeader>
        <CardContent>
          {card.dimensions.length === 0 ? (
            <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
              No rates yet.
            </div>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Metric</TableHead>
                  <TableHead>Unit</TableHead>
                  <TableHead className="text-right">Cost (micros)</TableHead>
                  <TableHead className="text-right">Per</TableHead>
                  <TableHead />
                </TableRow>
              </TableHeader>
              <TableBody>
                {card.dimensions.map((d) => (
                  <TableRow key={d.id}>
                    <TableCell className="font-medium">{d.metricName}</TableCell>
                    <TableCell className="text-muted-foreground">{d.unit}</TableCell>
                    <TableCell className="text-right">{d.costPerUnitMicros}</TableCell>
                    <TableCell className="text-right">{d.unitQuantity}</TableCell>
                    <TableCell className="text-right">
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => {
                          setEditingRate(d as RateEditDialogRate);
                          setRateDialogOpen(true);
                        }}
                      >
                        Edit
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        onClick={() => onDeleteRate(d.id, d.metricName)}
                      >
                        Delete
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <RateEditDialog
        cardId={cardId}
        open={rateDialogOpen}
        onOpenChange={setRateDialogOpen}
        rate={editingRate ?? undefined}
      />
    </div>
  );
}
```

Note: `d` from `card.dimensions` will have type `DimensionOut`. Confirm `DimensionOut` includes `unitQuantity` (it does — generated from backend `DimensionOut`). The `as RateEditDialogRate` cast is safe because the local interface is structurally a subset of `DimensionOut`.

- [ ] **Step 2: Update `$cardId` route**

Replace `src/app/routes/_app/pricing-cards/$cardId.lazy.tsx`:

```tsx
import { createLazyFileRoute } from "@tanstack/react-router";
import { CardDetailPage } from "@/features/pricing-cards/components/card-detail-page";

export const Route = createLazyFileRoute("/_app/pricing-cards/$cardId")({
  component: CardDetailRoute,
});

function CardDetailRoute() {
  const { cardId } = Route.useParams();
  return <CardDetailPage cardId={cardId} />;
}
```

- [ ] **Step 3: Typecheck**

Run: `pnpm tsc -b --noEmit 2>&1 | grep -E "features/pricing-cards|routes/_app/pricing-cards"`
Expected: empty.

The `reconciliation` feature is no longer referenced by any route, but its files remain on disk. `tsc` may still typecheck them; that's fine — they live in isolation. The follow-ups doc records the decision to keep them parked.

- [ ] **Step 4: Smoke test in dev server**

Open `/pricing-cards`, click a card, on `/pricing-cards/<id>`:
- edit name, save — observe `PATCH /api/v1/metering/pricing/cards/{id}`
- add rate — observe `POST .../rates`
- edit rate — observe `PUT .../rates/{rate_id}`
- delete rate — observe `DELETE .../rates/{rate_id}`
- delete card — observe `DELETE /api/v1/metering/pricing/cards/{id}` and redirect back to `/pricing-cards`.

- [ ] **Step 5: Commit**

```bash
git add src/features/pricing-cards/components/card-detail-page.tsx src/app/routes/_app/pricing-cards/\$cardId.lazy.tsx
git commit -m "feat(ui): pricing card detail page replaces reconciliation route"
```

---

## Phase 5 — Billing operations (per-customer)

### Task 5.1: Scaffold `billing-ops` feature

**Files:**
- Create: `src/features/billing-ops/api/types.ts`
- Create: `src/features/billing-ops/api/api.ts`
- Create: `src/features/billing-ops/api/mock.ts`
- Create: `src/features/billing-ops/api/provider.ts`

- [ ] **Step 1: Types**

```ts
// src/features/billing-ops/api/types.ts
import type { BillingSchemas } from "@/api/types";

export type Balance = BillingSchemas["BalanceResponse"];
export type CreateTopUpRequest = BillingSchemas["CreateTopUpRequest"];
export type WithdrawRequest = BillingSchemas["WithdrawRequest"];
export type RefundRequest = BillingSchemas["RefundRequest"];
export type ConfigureAutoTopUpRequest =
  BillingSchemas["ConfigureAutoTopUpRequest"];

// /customers/{id}/transactions has no typed response schema in openapi.
// Shape mirrors what the WalletTransaction serializer returns. If the backend
// adds a schema, regenerate and replace this type with the generated one.
export interface BillingTransaction {
  id: string;
  type: string;
  amountMicros: number;
  balanceAfterMicros: number;
  description: string;
  createdAt: string;
}

export interface TransactionsPage {
  data: BillingTransaction[];
  hasMore: boolean;
  nextCursor: string | null;
}
```

- [ ] **Step 2: API**

```ts
// src/features/billing-ops/api/api.ts
import { billingApi } from "@/api/client";
import type {
  Balance,
  BillingTransaction,
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  TransactionsPage,
  WithdrawRequest,
} from "./types";

export async function getBalance(customerId: string): Promise<Balance> {
  const { data, error } = await billingApi.GET(
    "/customers/{customer_id}/balance",
    { params: { path: { customer_id: customerId } } },
  );
  if (error || !data) throw error ?? new Error("Failed to load balance");
  return data;
}

export async function getTransactions(
  customerId: string,
  params?: { cursor?: string; limit?: number },
): Promise<TransactionsPage> {
  const { data, error } = await billingApi.GET(
    "/customers/{customer_id}/transactions",
    {
      params: { path: { customer_id: customerId }, query: params },
    },
  );
  if (error) throw error;
  return normalizeTransactionsPage(data);
}

// The backend endpoint has no typed response schema. To keep this surface
// resilient (and to make the eventual schema-add a no-op), we accept any of:
//   • `{ data, hasMore, nextCursor }` (current/most-likely shape)
//   • a raw array of transaction-ish objects
//   • undefined / null
// and drop rows that fail a minimal sanity check. The moment the backend
// ships a response_model annotation, regenerate types, type
// `BillingTransaction` from `BillingSchemas`, and inline this away.
function normalizeTransactionsPage(input: unknown): TransactionsPage {
  if (input == null) return { data: [], hasMore: false, nextCursor: null };
  const obj = input as Record<string, unknown>;
  const rawRows = Array.isArray(input)
    ? (input as unknown[])
    : Array.isArray(obj.data)
      ? (obj.data as unknown[])
      : [];
  const rows = rawRows
    .map(normalizeTransaction)
    .filter((r): r is BillingTransaction => r !== null);
  return {
    data: rows,
    hasMore: typeof obj.hasMore === "boolean" ? obj.hasMore : false,
    nextCursor:
      typeof obj.nextCursor === "string" || obj.nextCursor === null
        ? (obj.nextCursor as string | null)
        : null,
  };
}

function normalizeTransaction(row: unknown): BillingTransaction | null {
  if (!row || typeof row !== "object") return null;
  const r = row as Record<string, unknown>;
  if (typeof r.id !== "string") return null;
  if (typeof r.amountMicros !== "number") return null;
  return {
    id: r.id,
    type: typeof r.type === "string" ? r.type : "",
    amountMicros: r.amountMicros,
    balanceAfterMicros:
      typeof r.balanceAfterMicros === "number" ? r.balanceAfterMicros : 0,
    description: typeof r.description === "string" ? r.description : "",
    createdAt: typeof r.createdAt === "string" ? r.createdAt : "",
  };
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/top-up",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/withdraw",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function refund(
  customerId: string,
  body: RefundRequest,
): Promise<void> {
  const { error } = await billingApi.POST(
    "/customers/{customer_id}/refund",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}

export async function configureAutoTopUp(
  customerId: string,
  body: ConfigureAutoTopUpRequest,
): Promise<void> {
  const { error } = await billingApi.PUT(
    "/customers/{customer_id}/auto-top-up",
    {
      params: { path: { customer_id: customerId } },
      body,
    },
  );
  if (error) throw error;
}
```

- [ ] **Step 3: Mock**

```ts
// src/features/billing-ops/api/mock.ts
import { mockDelay } from "@/lib/api-provider";
import type {
  Balance,
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  TransactionsPage,
  WithdrawRequest,
} from "./types";

const _balances = new Map<string, Balance>();

export async function getBalance(customerId: string): Promise<Balance> {
  await mockDelay();
  return _balances.get(customerId) ?? { balanceMicros: 0, currency: "USD" };
}

export async function getTransactions(): Promise<TransactionsPage> {
  await mockDelay();
  return { data: [], hasMore: false, nextCursor: null };
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<void> {
  await mockDelay();
  const current =
    _balances.get(customerId)?.balanceMicros ?? 0;
  _balances.set(customerId, {
    balanceMicros: current + body.amountMicros,
    currency: "USD",
  });
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<void> {
  await mockDelay();
  const current =
    _balances.get(customerId)?.balanceMicros ?? 0;
  _balances.set(customerId, {
    balanceMicros: current - body.amountMicros,
    currency: "USD",
  });
}

export async function refund(_id: string, _body: RefundRequest): Promise<void> {
  await mockDelay();
}

export async function configureAutoTopUp(
  _id: string,
  _body: ConfigureAutoTopUpRequest,
): Promise<void> {
  await mockDelay();
}
```

- [ ] **Step 4: Provider**

```ts
// src/features/billing-ops/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const billingOpsApi = selectProvider({ mock, api });
```

- [ ] **Step 5: Commit**

```bash
git add src/features/billing-ops/api/
git commit -m "feat(ui): billing-ops feature scaffold (api + mock + provider)"
```

### Task 5.2: Add billing-ops queries

**Files:**
- Create: `src/features/billing-ops/api/queries.ts`

- [ ] **Step 1: Write file**

```ts
// src/features/billing-ops/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toastOnError } from "@/lib/mutations";
import { billingOpsApi } from "./provider";
import type {
  ConfigureAutoTopUpRequest,
  CreateTopUpRequest,
  RefundRequest,
  WithdrawRequest,
} from "./types";

const balanceKey = (id: string) => ["billing-ops", "balance", id] as const;
const txKey = (id: string) => ["billing-ops", "transactions", id] as const;

export function useBalance(customerId: string) {
  return useQuery({
    queryKey: balanceKey(customerId),
    queryFn: () => billingOpsApi.getBalance(customerId),
    enabled: !!customerId,
  });
}

export function useTransactions(customerId: string) {
  return useQuery({
    queryKey: txKey(customerId),
    queryFn: () => billingOpsApi.getTransactions(customerId),
    enabled: !!customerId,
  });
}

function useBillingMutation<TVars>(
  customerId: string,
  fn: (vars: TVars) => Promise<void>,
  errorMessage: string,
) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: fn,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: balanceKey(customerId) });
      qc.invalidateQueries({ queryKey: txKey(customerId) });
    },
    onError: toastOnError(errorMessage),
  });
}

export function useCreateTopUp(customerId: string) {
  return useBillingMutation<CreateTopUpRequest>(
    customerId,
    (body) => billingOpsApi.createTopUp(customerId, body),
    "Couldn't start top-up",
  );
}

export function useWithdraw(customerId: string) {
  return useBillingMutation<WithdrawRequest>(
    customerId,
    (body) => billingOpsApi.withdraw(customerId, body),
    "Couldn't withdraw",
  );
}

export function useRefund(customerId: string) {
  return useBillingMutation<RefundRequest>(
    customerId,
    (body) => billingOpsApi.refund(customerId, body),
    "Couldn't refund",
  );
}

export function useConfigureAutoTopUp(customerId: string) {
  return useBillingMutation<ConfigureAutoTopUpRequest>(
    customerId,
    (body) => billingOpsApi.configureAutoTopUp(customerId, body),
    "Couldn't configure auto top-up",
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing-ops/api/queries.ts
git commit -m "feat(ui): billing-ops query/mutation hooks"
```

### Task 5.3: Write failing test for `CustomerBillingPanel`

**Files:**
- Create: `src/features/billing-ops/components/customer-billing-panel.test.tsx`

- [ ] **Step 1: Write test**

```tsx
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import React from "react";

const topUpMutate = vi.fn();

vi.mock("../api/queries", () => ({
  useBalance: () => ({
    data: { balanceMicros: 12_500_000, currency: "USD" },
    isLoading: false,
  }),
  useTransactions: () => ({
    data: {
      data: [
        {
          id: "tx_1",
          type: "credit",
          amountMicros: 5_000_000,
          balanceAfterMicros: 12_500_000,
          description: "Stripe top-up",
          createdAt: "2026-05-10T10:00:00Z",
        },
      ],
      hasMore: false,
      nextCursor: null,
    },
    isLoading: false,
  }),
  useCreateTopUp: () => ({ mutateAsync: topUpMutate, isPending: false }),
  useWithdraw: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useConfigureAutoTopUp: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));

import { CustomerBillingPanel } from "./customer-billing-panel";

function renderPanel() {
  const qc = new QueryClient();
  return render(
    React.createElement(QueryClientProvider, { client: qc },
      React.createElement(CustomerBillingPanel, { customerId: "cus_1" }),
    ),
  );
}

describe("CustomerBillingPanel", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    topUpMutate.mockResolvedValue(undefined);
  });

  it("renders the balance in dollars", () => {
    renderPanel();
    expect(screen.getByText(/\$12\.50/)).toBeInTheDocument();
  });

  it("renders a transaction row", () => {
    renderPanel();
    expect(screen.getByText("Stripe top-up")).toBeInTheDocument();
  });

  it("submits a top-up", async () => {
    renderPanel();
    fireEvent.click(screen.getByRole("button", { name: /top up/i }));
    const amount = await screen.findByLabelText(/amount/i);
    fireEvent.change(amount, { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: /start top-up/i }));
    await waitFor(() => {
      expect(topUpMutate).toHaveBeenCalledWith(
        expect.objectContaining({
          amountMicros: 10_000_000,
        }),
      );
    });
  });
});
```

- [ ] **Step 2: Run test (expect fail)**

Run: `pnpm vitest run src/features/billing-ops/components/customer-billing-panel.test.tsx`
Expected: FAIL — module not found.

### Task 5.4: Implement `TopUpDialog`

**Files:**
- Create: `src/features/billing-ops/components/top-up-dialog.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useCreateTopUp } from "../api/queries";

export function TopUpDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const topUp = useCreateTopUp(customerId);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const dollars = Number(amount);
    if (!Number.isFinite(dollars) || dollars <= 0) return;
    // Stripe will redirect back to these URLs after checkout. Anchor on the
    // current page (the customer detail screen) so the user lands where they
    // started, with a query flag we can render a toast for.
    const here = `${window.location.origin}${window.location.pathname}`;
    await topUp.mutateAsync({
      amountMicros: Math.round(dollars * 1_000_000),
      successUrl: `${here}?topup=success`,
      cancelUrl: `${here}?topup=cancel`,
    });
    setOpen(false);
    setAmount("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>Top up</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Top up wallet</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="amount">Amount (USD)</Label>
            <Input
              id="amount"
              type="number"
              min={1}
              step={1}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={topUp.isPending}>
              {topUp.isPending ? "Starting…" : "Start top-up"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing-ops/components/top-up-dialog.tsx
git commit -m "feat(ui): top-up dialog"
```

### Task 5.5: Implement `WithdrawDialog`

**Files:**
- Create: `src/features/billing-ops/components/withdraw-dialog.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState } from "react";
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { useWithdraw } from "../api/queries";

function randomKey() {
  return crypto.randomUUID();
}

export function WithdrawDialog({ customerId }: { customerId: string }) {
  const [open, setOpen] = useState(false);
  const [amount, setAmount] = useState("");
  const [description, setDescription] = useState("");
  const withdraw = useWithdraw(customerId);

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const dollars = Number(amount);
    if (!Number.isFinite(dollars) || dollars <= 0) return;
    await withdraw.mutateAsync({
      amountMicros: Math.round(dollars * 1_000_000),
      description,
      idempotencyKey: randomKey(),
    });
    setOpen(false);
    setAmount("");
    setDescription("");
  }

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button variant="outline">Withdraw</Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Withdraw from wallet</DialogTitle>
        </DialogHeader>
        <form onSubmit={onSubmit} className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="withdraw-amount">Amount (USD)</Label>
            <Input
              id="withdraw-amount"
              type="number"
              min={1}
              step={0.01}
              value={amount}
              onChange={(e) => setAmount(e.target.value)}
              required
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="withdraw-description">Description</Label>
            <Input
              id="withdraw-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button type="button" variant="ghost" onClick={() => setOpen(false)}>
              Cancel
            </Button>
            <Button type="submit" disabled={withdraw.isPending}>
              {withdraw.isPending ? "Withdrawing…" : "Withdraw"}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing-ops/components/withdraw-dialog.tsx
git commit -m "feat(ui): withdraw dialog"
```

### Task 5.6: Implement `AutoTopUpForm`

**Files:**
- Create: `src/features/billing-ops/components/auto-top-up-form.tsx`

- [ ] **Step 1: Write component**

```tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useConfigureAutoTopUp } from "../api/queries";

export function AutoTopUpForm({ customerId }: { customerId: string }) {
  const configure = useConfigureAutoTopUp(customerId);
  const [enabled, setEnabled] = useState(false);
  const [threshold, setThreshold] = useState("5");
  const [topUpAmount, setTopUpAmount] = useState("25");

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    await configure.mutateAsync({
      isEnabled: enabled,
      triggerThresholdMicros: Math.round(Number(threshold) * 1_000_000),
      topUpAmountMicros: Math.round(Number(topUpAmount) * 1_000_000),
    });
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Auto top-up</CardTitle>
      </CardHeader>
      <CardContent>
        <form onSubmit={onSubmit} className="space-y-4">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={enabled}
              onChange={(e) => setEnabled(e.target.checked)}
            />
            Enable auto top-up
          </label>
          <div className="space-y-2">
            <Label htmlFor="threshold">Trigger when balance falls below (USD)</Label>
            <Input
              id="threshold"
              type="number"
              min={0}
              step={0.01}
              value={threshold}
              onChange={(e) => setThreshold(e.target.value)}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="top-up-amount">Top up by (USD)</Label>
            <Input
              id="top-up-amount"
              type="number"
              min={1}
              step={0.01}
              value={topUpAmount}
              onChange={(e) => setTopUpAmount(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={configure.isPending}>
            {configure.isPending ? "Saving…" : "Save"}
          </Button>
        </form>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing-ops/components/auto-top-up-form.tsx
git commit -m "feat(ui): auto top-up configuration form"
```

### Task 5.7: Implement `TransactionsTable`

**Files:**
- Create: `src/features/billing-ops/components/transactions-table.tsx`

- [ ] **Step 1: Write component**

```tsx
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { BillingTransaction } from "../api/types";

function microsToDollars(micros: number): string {
  const sign = micros < 0 ? "-" : "";
  return `${sign}$${(Math.abs(micros) / 1_000_000).toFixed(2)}`;
}

export function TransactionsTable({ rows }: { rows: BillingTransaction[] }) {
  if (rows.length === 0) {
    return (
      <div className="rounded-lg border border-dashed p-8 text-center text-sm text-muted-foreground">
        No transactions yet.
      </div>
    );
  }

  return (
    <Table>
      <TableHeader>
        <TableRow>
          <TableHead>Type</TableHead>
          <TableHead>Description</TableHead>
          <TableHead className="text-right">Amount</TableHead>
          <TableHead className="text-right">Balance after</TableHead>
          <TableHead>When</TableHead>
        </TableRow>
      </TableHeader>
      <TableBody>
        {rows.map((r) => (
          <TableRow key={r.id}>
            <TableCell>{r.type}</TableCell>
            <TableCell className="text-muted-foreground">
              {r.description}
            </TableCell>
            <TableCell className="text-right">
              {microsToDollars(r.amountMicros)}
            </TableCell>
            <TableCell className="text-right">
              {microsToDollars(r.balanceAfterMicros)}
            </TableCell>
            <TableCell className="text-muted-foreground">
              {new Date(r.createdAt).toLocaleString()}
            </TableCell>
          </TableRow>
        ))}
      </TableBody>
    </Table>
  );
}
```

- [ ] **Step 2: Commit**

```bash
git add src/features/billing-ops/components/transactions-table.tsx
git commit -m "feat(ui): billing transactions table"
```

### Task 5.8: Implement `CustomerBillingPanel`

**Files:**
- Create: `src/features/billing-ops/components/customer-billing-panel.tsx`

- [ ] **Step 1: Write component**

```tsx
import { Loader2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { useBalance, useTransactions } from "../api/queries";
import { TopUpDialog } from "./top-up-dialog";
import { WithdrawDialog } from "./withdraw-dialog";
import { AutoTopUpForm } from "./auto-top-up-form";
import { TransactionsTable } from "./transactions-table";

function microsToDollars(micros: number): string {
  return `$${(micros / 1_000_000).toFixed(2)}`;
}

export function CustomerBillingPanel({ customerId }: { customerId: string }) {
  const balance = useBalance(customerId);
  const transactions = useTransactions(customerId);

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader className="flex flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Wallet balance</CardTitle>
          <div className="flex gap-2">
            <TopUpDialog customerId={customerId} />
            <WithdrawDialog customerId={customerId} />
          </div>
        </CardHeader>
        <CardContent>
          {balance.isLoading || !balance.data ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading balance…
            </div>
          ) : (
            <div className="text-3xl font-medium">
              {microsToDollars(balance.data.balanceMicros)}
              <span className="ml-2 text-sm text-muted-foreground">
                {balance.data.currency}
              </span>
            </div>
          )}
        </CardContent>
      </Card>

      <AutoTopUpForm customerId={customerId} />

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Recent transactions</CardTitle>
        </CardHeader>
        <CardContent>
          {transactions.isLoading || !transactions.data ? (
            <div className="flex items-center gap-2 text-sm text-muted-foreground">
              <Loader2 className="h-4 w-4 animate-spin" /> Loading transactions…
            </div>
          ) : (
            <TransactionsTable rows={transactions.data.data} />
          )}
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Run tests**

Run: `pnpm vitest run src/features/billing-ops/components/customer-billing-panel.test.tsx`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add src/features/billing-ops/components/customer-billing-panel.{tsx,test.tsx}
git commit -m "feat(ui): customer billing panel"
```

### Task 5.9: Embed billing panel in customer detail page

**Files:**
- Modify: `src/features/customers/components/customer-detail-page.tsx`

- [ ] **Step 1: Import + render**

In the customer detail page, after the details card, add:

```tsx
import { CustomerBillingPanel } from "@/features/billing-ops/components/customer-billing-panel";

// ...in JSX, after the details Card:
<CustomerBillingPanel customerId={customerId} />
```

- [ ] **Step 2: Re-run customer detail tests**

Run: `pnpm vitest run src/features/customers/components/customer-detail-page.test.tsx`
Expected: PASS (existing test mocks the customers queries, so the billing panel will hit its own queries — which the test environment must also mock, OR we wrap the panel render in a test boundary).

If the test now fails because `useBalance` etc. throw without a mocked queryFn: add to the test file:

```tsx
vi.mock("@/features/billing-ops/api/queries", () => ({
  useBalance: () => ({ data: undefined, isLoading: true }),
  useTransactions: () => ({ data: undefined, isLoading: true }),
  useCreateTopUp: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useWithdraw: () => ({ mutateAsync: vi.fn(), isPending: false }),
  useConfigureAutoTopUp: () => ({ mutateAsync: vi.fn(), isPending: false }),
}));
```

- [ ] **Step 3: Smoke test in dev server**

Open `/customers/<id>`. Verify balance loads, top-up dialog opens (Stripe will reject test cards — that's fine, just confirm the POST fires with the right body), transactions table renders.

- [ ] **Step 4: Commit**

```bash
git add src/features/customers/components/customer-detail-page.tsx src/features/customers/components/customer-detail-page.test.tsx
git commit -m "feat(ui): embed customer billing panel in detail page"
```

---

## Phase 6 — Cleanup + verification

### Task 6.1: Run full typecheck + tests

- [ ] **Step 1: Typecheck**

Run: `pnpm tsc -b --noEmit`
Expected: zero errors.

- [ ] **Step 2: Full test suite**

Run: `pnpm vitest run`
Expected: zero failing tests.

- [ ] **Step 3: Lint**

Run: `pnpm lint`
Expected: zero errors. Warnings tolerated only if unrelated to changed files.

- [ ] **Step 4: API drift check**

Run: `pnpm api:check`
Expected: passes (no diff). If it fails, run `pnpm api:regen` and inspect — the diff means the backend changed during plan execution; reconcile and recommit.

### Task 6.2: Manual smoke pass

- [ ] **Step 1: Start dev server + Django**

Run dev server (`pnpm dev`) and Django (`.venv/bin/python manage.py runserver`).

- [ ] **Step 2: Walk through each new surface**

Tick each as it works end-to-end against the real backend (not mock):

- [ ] Sign in, land on dashboard.
- [ ] `/billing` — load default margin, edit, save, reload.
- [ ] `/customers` — list customers, create one, edit it, change status, save.
- [ ] `/customers/<id>` — billing panel: top-up (POST), withdraw, configure auto-top-up.
- [ ] `/pricing-cards/<id>` — add rate, edit rate, delete rate, delete card.

Set `VITE_API_PROVIDER=api` if not already, to bypass mocks.

- [ ] **Step 3: Final commit (if any docs/cleanups)**

```bash
git status
# only commit if there are uncommitted leftovers
```

### Task 6.3: Document follow-ups

**Files:**
- Create: `docs/plans/2026-05-15-ui-api-wireup-followups.md`

- [ ] **Step 1: Capture what we deliberately deferred**

```markdown
# UI ↔ API Wire-Up — deferred follow-ups

These were intentionally out of scope for the 2026-05-15 plan.

## Backend designs needed
- Margin hierarchy (product / card / customer levels) — the UI used to render a tree; backend only exposes default margin.
- Margin change history.
- Customer mapping / orphans (if we want to bring back the old UI concept).
- Export pipeline (`/export/filter-options`, `/export/preview`, `/export/generate`).
- Rate-card reconciliation (`/rate-cards/{id}/reconciliation` + boundary/edit/insert/record-adjustment). The existing `src/features/reconciliation/` UI is parked (unreachable from any route) until the backend exists.

## Schema annotations needed
- `GET /billing/customers/{id}/transactions` — response is untyped. Add a `response_model` so we can derive the type instead of hand-coding `BillingTransaction`.

## UI work not yet started
- Customer self-service portal using the `/me` namespace (`balance`, `invoices`, `top-up`, `transactions`).
- Tenant billing pages (`/billing/tenant/billing-periods`, `/billing/tenant/invoices`, revenue analytics).
- Usage analytics (`/metering/analytics/usage`, `/metering/customers/{id}/usage`).
- Wallets admin (`/platform/wallets`).
- Refund action (the API call exists in `billing-ops`, but no UI surface invokes it — events page is the natural home for "refund this event").
- Runs management (`/metering/runs/{id}/close`).
```

- [ ] **Step 2: Commit**

```bash
git add docs/plans/2026-05-15-ui-api-wireup-followups.md
git commit -m "docs: capture deferred follow-ups from UI wire-up"
```
