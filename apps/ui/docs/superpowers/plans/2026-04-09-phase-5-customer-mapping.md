# Phase 5: Customer Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Customer Mapping management page at `/customers` — sync status, stats, alerts, customer table with inline editing, and orphaned events section.

**Architecture:** Feature-co-located module under `src/features/customers/` following the identical pattern as `src/features/dashboard/`. Provider pattern for mock/api switching. Single page component composing 5 child components. TanStack Query for server state, useState for UI state, React Hook Form + Zod for inline editing.

**Tech Stack:** React 19, TanStack Query v5, React Hook Form + Zod, Zustand (auth store read-only), shadcn/ui (Select, Input, Button, Badge, Dialog, Skeleton), Lucide icons, Tailwind CSS v4.

**Spec:** `docs/superpowers/specs/2026-04-09-phase-5-customer-mapping.md`
**Mockup:** `docs/design/files/customer_mapping_management.html`

---

## File Map

```
Files to CREATE:
  src/features/customers/api/types.ts          — TypeScript interfaces
  src/features/customers/api/mock-data.ts      — 23 customers + 3 orphans + stats
  src/features/customers/api/mock.ts           — Mock functions with delay
  src/features/customers/api/api.ts            — Real API stubs via platformApi
  src/features/customers/api/provider.ts       — selectProvider({ mock, api })
  src/features/customers/api/queries.ts        — TanStack Query hooks + mutations
  src/features/customers/components/sync-status-bar.tsx
  src/features/customers/components/mapping-stats-grid.tsx
  src/features/customers/components/alert-banners.tsx
  src/features/customers/components/customer-table.tsx
  src/features/customers/components/orphaned-events-section.tsx
  src/features/customers/components/customer-mapping-page.tsx

Files to MODIFY:
  src/app/routes/_app/customers/index.tsx      — Replace stub with feature import
```

---

### Task 1: API Types

**Files:**
- Create: `src/features/customers/api/types.ts`

- [ ] **Step 1: Create types file**

```typescript
// src/features/customers/api/types.ts

// Data semantics use "unmapped"; display label is "New" (teal pill)
export type CustomerStatus = "active" | "idle" | "unmapped";

export interface CustomerMapping {
  id: string;
  stripeCustomerId: string;
  name: string;
  email: string;
  sdkIdentifier: string | null;
  revenue30d: number; // micros
  events30d: number;
  lastEventAt: string | null; // ISO timestamp
  status: CustomerStatus;
}

export interface OrphanedIdentifier {
  id: string;
  sdkIdentifier: string;
  firstSeenAt: string; // ISO timestamp
  eventCount: number;
  unattributedCost: number; // micros
}

export interface SyncStatus {
  connected: boolean;
  lastSyncAt: string | null; // ISO timestamp
  syncing: boolean;
}

export interface CustomerMappingStats {
  totalCustomers: number;
  mapped: number;
  unmapped: number;
  orphanedEvents: number;
  orphanedIdentifiers: number;
  newCustomersSinceLastSync: number;
}

export interface CustomerMappingData {
  syncStatus: SyncStatus;
  stats: CustomerMappingStats;
  customers: CustomerMapping[];
  orphanedIdentifiers: OrphanedIdentifier[];
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors related to the new types file.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add API types for customer mapping`

---

### Task 2: Mock Data + Mock Implementation

**Files:**
- Create: `src/features/customers/api/mock-data.ts`
- Create: `src/features/customers/api/mock.ts`

**Context:** All monetary values are in micros (1 dollar = 1,000,000 micros). The 23 customers and 3 orphans match the HTML mockup exactly. `lastEventAt` timestamps are computed relative to import time so `formatRelativeDate` shows realistic values.

- [ ] **Step 1: Create mock-data.ts**

```typescript
// src/features/customers/api/mock-data.ts
import type {
  CustomerMapping,
  CustomerMappingData,
  OrphanedIdentifier,
} from "./types";

/** Compute an ISO timestamp N minutes before now. */
function minutesAgo(mins: number): string {
  return new Date(Date.now() - mins * 60_000).toISOString();
}

const customers: CustomerMapping[] = [
  { id: "1", stripeCustomerId: "cus_R4kB9xPm2nQ", name: "Acme Corp", email: "admin@acmecorp.com", sdkIdentifier: "cus_R4kB9xPm2nQ", revenue30d: 2_400_000_000, events30d: 14_219, lastEventAt: minutesAgo(2), status: "active" },
  { id: "2", stripeCustomerId: "cus_Q7mN3vHj8wL", name: "BrightPath Ltd", email: "team@brightpath.io", sdkIdentifier: "cus_Q7mN3vHj8wL", revenue30d: 1_800_000_000, events30d: 11_402, lastEventAt: minutesAgo(5), status: "active" },
  { id: "3", stripeCustomerId: "cus_S2pK5tRn7xY", name: "NovaTech Inc", email: "ops@novatech.co", sdkIdentifier: "cus_S2pK5tRn7xY", revenue30d: 950_000_000, events30d: 6_841, lastEventAt: minutesAgo(12), status: "active" },
  { id: "4", stripeCustomerId: "cus_U6nR2wKm9xQ", name: "Helios Digital", email: "hello@helios.dev", sdkIdentifier: "cus_U6nR2wKm9xQ", revenue30d: 720_000_000, events30d: 9_403, lastEventAt: minutesAgo(8), status: "active" },
  { id: "5", stripeCustomerId: "cus_T9wM1kJp4qB", name: "Zenith Labs", email: "info@zenithlabs.com", sdkIdentifier: "cus_T9wM1kJp4qB", revenue30d: 680_000_000, events30d: 5_120, lastEventAt: minutesAgo(60), status: "active" },
  { id: "6", stripeCustomerId: "cus_V3bP8sHn5mJ", name: "ClearView Analytics", email: "support@clearview.ai", sdkIdentifier: "cus_V3bP8sHn5mJ", revenue30d: 150_000_000, events30d: 8_210, lastEventAt: minutesAgo(22), status: "active" },
  { id: "7", stripeCustomerId: "cus_W1cT4rFk7pN", name: "Eko Systems", email: "dev@ekosystems.io", sdkIdentifier: "cus_W1cT4rFk7pN", revenue30d: 90_000_000, events30d: 7_891, lastEventAt: minutesAgo(3), status: "active" },
  { id: "8", stripeCustomerId: "cus_X5rW8nKp3mQ", name: "Pinnacle AI", email: "cto@pinnacle.ai", sdkIdentifier: "cus_X5rW8nKp3mQ", revenue30d: 340_000_000, events30d: 2_104, lastEventAt: minutesAgo(45), status: "active" },
  { id: "9", stripeCustomerId: "cus_Y2dF6hTn8qR", name: "Meridian Group", email: "ops@meridian.co", sdkIdentifier: "cus_Y2dF6hTn8qR", revenue30d: 480_000_000, events30d: 3_812, lastEventAt: minutesAgo(60), status: "active" },
  { id: "10", stripeCustomerId: "cus_Z3eG7jUo9sS", name: "Atlas Robotics", email: "api@atlas-robotics.com", sdkIdentifier: "cus_Z3eG7jUo9sS", revenue30d: 320_000_000, events30d: 2_310, lastEventAt: minutesAgo(120), status: "active" },
  { id: "11", stripeCustomerId: "cus_A4fH8kVp0tT", name: "Quantum Logic", email: "dev@quantumlogic.io", sdkIdentifier: "cus_A4fH8kVp0tT", revenue30d: 275_000_000, events30d: 1_891, lastEventAt: minutesAgo(180), status: "active" },
  { id: "12", stripeCustomerId: "cus_B5gI9lWq1uU", name: "BlueSky Data", email: "team@blueskydata.com", sdkIdentifier: "cus_B5gI9lWq1uU", revenue30d: 210_000_000, events30d: 1_402, lastEventAt: minutesAgo(240), status: "active" },
  { id: "13", stripeCustomerId: "cus_C6hJ0mXr2vV", name: "Vertex Labs", email: "eng@vertex.dev", sdkIdentifier: "cus_C6hJ0mXr2vV", revenue30d: 190_000_000, events30d: 980, lastEventAt: minutesAgo(360), status: "active" },
  { id: "14", stripeCustomerId: "cus_D7iK1nYs3wW", name: "Forge AI", email: "hello@forge-ai.com", sdkIdentifier: "cus_D7iK1nYs3wW", revenue30d: 165_000_000, events30d: 820, lastEventAt: minutesAgo(300), status: "active" },
  { id: "15", stripeCustomerId: "cus_E8jL2oZt4xX", name: "Echo Systems", email: "api@echo-sys.io", sdkIdentifier: "cus_E8jL2oZt4xX", revenue30d: 140_000_000, events30d: 650, lastEventAt: minutesAgo(480), status: "active" },
  { id: "16", stripeCustomerId: "cus_F9kM3pAu5yY", name: "Ridgeline", email: "tech@ridgeline.co", sdkIdentifier: "cus_F9kM3pAu5yY", revenue30d: 120_000_000, events30d: 410, lastEventAt: minutesAgo(720), status: "active" },
  { id: "17", stripeCustomerId: "cus_G0lN4qBv6zZ", name: "Prism Health", email: "dev@prismhealth.com", sdkIdentifier: "cus_G0lN4qBv6zZ", revenue30d: 95_000_000, events30d: 220, lastEventAt: minutesAgo(1440), status: "active" },
  { id: "18", stripeCustomerId: "cus_H1mO5rCw7aA", name: "Aether Inc", email: "eng@aether.inc", sdkIdentifier: "cus_H1mO5rCw7aA", revenue30d: 60_000_000, events30d: 102, lastEventAt: minutesAgo(2880), status: "active" },
  { id: "19", stripeCustomerId: "cus_I2nP6sDx8bB", name: "Nomad Digital", email: "api@nomad.digital", sdkIdentifier: "cus_I2nP6sDx8bB", revenue30d: 45_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "20", stripeCustomerId: "cus_J3oQ7tEy9cC", name: "Strata Corp", email: "tech@strata.io", sdkIdentifier: "cus_J3oQ7tEy9cC", revenue30d: 30_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "21", stripeCustomerId: "cus_K4pR8uFz0dD", name: "Cobalt Labs", email: "dev@cobalt-labs.com", sdkIdentifier: "cus_K4pR8uFz0dD", revenue30d: 15_000_000, events30d: 0, lastEventAt: null, status: "idle" },
  { id: "22", stripeCustomerId: "cus_L5qS9vGa1eE", name: "Terraform Solutions", email: "hello@terraform-sol.com", sdkIdentifier: null, revenue30d: 380_000_000, events30d: 0, lastEventAt: null, status: "unmapped" },
  { id: "23", stripeCustomerId: "cus_M6rT0wHb2fF", name: "Orbit Analytics", email: "team@orbit-analytics.io", sdkIdentifier: null, revenue30d: 125_000_000, events30d: 0, lastEventAt: null, status: "unmapped" },
];

const orphanedIdentifiers: OrphanedIdentifier[] = [
  { id: "o1", sdkIdentifier: "acme_legacy", firstSeenAt: "2026-03-18T10:00:00Z", eventCount: 89, unattributedCost: 12_400_000 },
  { id: "o2", sdkIdentifier: "test_user_001", firstSeenAt: "2026-03-20T14:30:00Z", eventCount: 41, unattributedCost: 5_200_000 },
  { id: "o3", sdkIdentifier: "clearview_v2", firstSeenAt: "2026-03-22T09:15:00Z", eventCount: 12, unattributedCost: 1_850_000 },
];

export const mockCustomerMappingData: CustomerMappingData = {
  syncStatus: {
    connected: true,
    lastSyncAt: minutesAgo(14),
    syncing: false,
  },
  stats: {
    totalCustomers: 23,
    mapped: 21,
    unmapped: 2,
    orphanedEvents: 142,
    orphanedIdentifiers: 3,
    newCustomersSinceLastSync: 2,
  },
  customers,
  orphanedIdentifiers,
};
```

- [ ] **Step 2: Create mock.ts**

This file provides the mock API functions. Mutations operate on a cloned copy of the data so changes persist within a session.

```typescript
// src/features/customers/api/mock.ts
import type { CustomerMappingData } from "./types";
import { mockCustomerMappingData } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

// Session-local mutable copy so mock mutations persist across calls
let sessionData: CustomerMappingData = structuredClone(mockCustomerMappingData);

export async function getCustomerMapping(): Promise<CustomerMappingData> {
  await delay();
  return structuredClone(sessionData);
}

export async function updateMapping(
  customerId: string,
  sdkIdentifier: string,
): Promise<void> {
  await delay();
  const customer = sessionData.customers.find((c) => c.id === customerId);
  if (!customer) throw new Error(`Customer ${customerId} not found`);
  const wasUnmapped = !customer.sdkIdentifier;
  customer.sdkIdentifier = sdkIdentifier;
  if (wasUnmapped) {
    customer.status = "idle";
    customer.events30d = 0;
    sessionData.stats.mapped += 1;
    sessionData.stats.unmapped -= 1;
  }
}

export async function assignOrphan(
  orphanId: string,
  _stripeCustomerId: string,
): Promise<void> {
  await delay();
  const idx = sessionData.orphanedIdentifiers.findIndex(
    (o) => o.id === orphanId,
  );
  if (idx === -1) throw new Error(`Orphan ${orphanId} not found`);
  const orphan = sessionData.orphanedIdentifiers[idx];
  sessionData.stats.orphanedEvents -= orphan.eventCount;
  sessionData.stats.orphanedIdentifiers -= 1;
  sessionData.orphanedIdentifiers.splice(idx, 1);
}

export async function dismissOrphans(): Promise<void> {
  await delay();
  sessionData.stats.orphanedEvents = 0;
  sessionData.stats.orphanedIdentifiers = 0;
  sessionData.orphanedIdentifiers = [];
}

export async function triggerSync(): Promise<void> {
  await delay(1200);
  sessionData.syncStatus.lastSyncAt = new Date().toISOString();
}
```

- [ ] **Step 3: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors.

- [ ] **Step 4: Ready to commit**

Suggested: `feat(customers): add mock data and mock API implementation`

---

### Task 3: API Stubs + Provider + Queries

**Files:**
- Create: `src/features/customers/api/api.ts`
- Create: `src/features/customers/api/provider.ts`
- Create: `src/features/customers/api/queries.ts`

**Context:** Follow the exact pattern from `src/features/dashboard/api/`. The `api.ts` file has placeholder stubs that will be implemented when the real backend is connected. The `queries.ts` file has 1 query + 4 mutations with optimistic updates.

- [ ] **Step 1: Create api.ts (real API stubs)**

```typescript
// src/features/customers/api/api.ts
import type { CustomerMappingData } from "./types";
import { platformApi } from "@/api/client";

export async function getCustomerMapping(): Promise<CustomerMappingData> {
  const { data } = await platformApi.GET("/customers/mapping", {});
  return data as CustomerMappingData;
}

export async function updateMapping(
  customerId: string,
  sdkIdentifier: string,
): Promise<void> {
  await platformApi.PUT("/customers/mapping/{customerId}", {
    params: { path: { customerId } },
    body: { sdkIdentifier },
  });
}

export async function assignOrphan(
  orphanId: string,
  stripeCustomerId: string,
): Promise<void> {
  await platformApi.POST("/customers/orphans/{orphanId}/assign", {
    params: { path: { orphanId } },
    body: { stripeCustomerId },
  });
}

export async function dismissOrphans(): Promise<void> {
  await platformApi.DELETE("/customers/orphans", {});
}

export async function triggerSync(): Promise<void> {
  await platformApi.POST("/customers/sync", {});
}
```

- [ ] **Step 2: Create provider.ts**

```typescript
// src/features/customers/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const customersApi = selectProvider({ mock, api });
```

- [ ] **Step 3: Create queries.ts**

```typescript
// src/features/customers/api/queries.ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { customersApi } from "./provider";
import type { CustomerMappingData } from "./types";

const QUERY_KEY = ["customer-mapping"] as const;

export function useCustomerMapping() {
  return useQuery({
    queryKey: QUERY_KEY,
    queryFn: () => customersApi.getCustomerMapping(),
  });
}

export function useUpdateMapping() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      customerId,
      sdkIdentifier,
    }: {
      customerId: string;
      sdkIdentifier: string;
    }) => customersApi.updateMapping(customerId, sdkIdentifier),
    onMutate: async ({ customerId, sdkIdentifier }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        const customer = previous.customers.find((c) => c.id === customerId);
        const wasUnmapped = customer && !customer.sdkIdentifier;
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          customers: previous.customers.map((c) =>
            c.id === customerId
              ? {
                  ...c,
                  sdkIdentifier,
                  status: wasUnmapped ? ("idle" as const) : c.status,
                  events30d: wasUnmapped ? 0 : c.events30d,
                }
              : c,
          ),
          stats: wasUnmapped
            ? {
                ...previous.stats,
                mapped: previous.stats.mapped + 1,
                unmapped: previous.stats.unmapped - 1,
              }
            : previous.stats,
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useAssignOrphan() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({
      orphanId,
      stripeCustomerId,
    }: {
      orphanId: string;
      stripeCustomerId: string;
    }) => customersApi.assignOrphan(orphanId, stripeCustomerId),
    onMutate: async ({ orphanId }) => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        const orphan = previous.orphanedIdentifiers.find(
          (o) => o.id === orphanId,
        );
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          orphanedIdentifiers: previous.orphanedIdentifiers.filter(
            (o) => o.id !== orphanId,
          ),
          stats: {
            ...previous.stats,
            orphanedEvents:
              previous.stats.orphanedEvents - (orphan?.eventCount ?? 0),
            orphanedIdentifiers: previous.stats.orphanedIdentifiers - 1,
          },
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useDismissOrphans() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customersApi.dismissOrphans(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          orphanedIdentifiers: [],
          stats: {
            ...previous.stats,
            orphanedEvents: 0,
            orphanedIdentifiers: 0,
          },
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}

export function useTriggerSync() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => customersApi.triggerSync(),
    onMutate: async () => {
      await queryClient.cancelQueries({ queryKey: QUERY_KEY });
      const previous =
        queryClient.getQueryData<CustomerMappingData>(QUERY_KEY);
      if (previous) {
        queryClient.setQueryData<CustomerMappingData>(QUERY_KEY, {
          ...previous,
          syncStatus: { ...previous.syncStatus, syncing: true },
        });
      }
      return { previous };
    },
    onError: (_err, _vars, context) => {
      if (context?.previous) {
        queryClient.setQueryData(QUERY_KEY, context.previous);
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: QUERY_KEY });
    },
  });
}
```

- [ ] **Step 4: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors. The query hooks and provider should compile cleanly.

- [ ] **Step 5: Ready to commit**

Suggested: `feat(customers): add API stubs, provider, and TanStack Query hooks`

---

### Task 4: SyncStatusBar Component

**Files:**
- Create: `src/features/customers/components/sync-status-bar.tsx`

**Context:** Displays Stripe connection status, last sync time, tenant mode pill, and sync/settings buttons. Reads `tenantMode` from auth store (`src/stores/auth-store.ts`). Uses `formatRelativeDate` from `src/lib/format.ts`. The "Sync now" button calls the `useTriggerSync` mutation.

- [ ] **Step 1: Create sync-status-bar.tsx**

```typescript
// src/features/customers/components/sync-status-bar.tsx
import { Link } from "@tanstack/react-router";
import { cn } from "@/lib/utils";
import { formatRelativeDate } from "@/lib/format";
import { useAuthStore } from "@/stores/auth-store";
import { useTriggerSync } from "../api/queries";
import type { SyncStatus } from "../api/types";

interface SyncStatusBarProps {
  syncStatus: SyncStatus;
}

export function SyncStatusBar({ syncStatus }: SyncStatusBarProps) {
  const tenantMode = useAuthStore((s) => s.tenantMode);
  const syncMutation = useTriggerSync();
  const isSyncing = syncStatus.syncing || syncMutation.isPending;

  return (
    <div className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-accent/50 px-3.5 py-2.5">
      <div className="flex items-center gap-2 text-xs text-muted-foreground">
        <div
          className={cn(
            "h-2 w-2 rounded-full",
            syncStatus.connected ? "bg-green-500" : "bg-red-500",
          )}
        />
        <span>{syncStatus.connected ? "Stripe connected" : "Stripe disconnected"}</span>
        {syncStatus.lastSyncAt && (
          <span className="text-muted-foreground/60">
            Last synced {formatRelativeDate(syncStatus.lastSyncAt)}
          </span>
        )}
      </div>
      <div className="flex items-center gap-1.5">
        {tenantMode === "billing" && (
          <span className="rounded-full bg-[#EEEDFE] px-2.5 py-0.5 text-[10px] font-medium text-[#3C3489] dark:bg-[#2a2757] dark:text-[#a9a3f0]">
            Billing mode
          </span>
        )}
        {tenantMode === "revenue" && (
          <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-[10px] font-medium text-blue-700 dark:bg-blue-950 dark:text-blue-300">
            Revenue + costs
          </span>
        )}
        <button
          className="rounded-lg border border-border px-2.5 py-1 text-[11px] text-foreground hover:bg-accent disabled:opacity-50"
          onClick={() => syncMutation.mutate()}
          disabled={isSyncing}
        >
          {isSyncing ? "Syncing..." : "Sync now"}
        </button>
        <Link
          to="/settings"
          className="rounded-lg border border-border px-2.5 py-1 text-[11px] text-foreground hover:bg-accent"
        >
          Stripe settings
        </Link>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add SyncStatusBar component`

---

### Task 5: MappingStatsGrid Component

**Files:**
- Create: `src/features/customers/components/mapping-stats-grid.tsx`

**Context:** 4-column grid of stat cards. Values are color-coded: green for mapped, amber for unmapped, red for orphaned events. Matches the `.stats` section of the mockup.

- [ ] **Step 1: Create mapping-stats-grid.tsx**

```typescript
// src/features/customers/components/mapping-stats-grid.tsx
import { cn } from "@/lib/utils";
import type { CustomerMappingStats } from "../api/types";

interface MappingStatsGridProps {
  stats: CustomerMappingStats;
}

interface StatCardProps {
  label: string;
  value: number;
  subtitle: string;
  colorClass?: string;
}

function StatCard({ label, value, subtitle, colorClass }: StatCardProps) {
  return (
    <div className="rounded-lg bg-accent/50 px-3 py-2.5">
      <div className="text-[10px] text-muted-foreground">{label}</div>
      <div className={cn("mt-0.5 text-[17px] font-semibold", colorClass)}>
        {value}
      </div>
      <div className="mt-0.5 text-[9px] text-muted-foreground/60">
        {subtitle}
      </div>
    </div>
  );
}

export function MappingStatsGrid({ stats }: MappingStatsGridProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard
        label="Stripe customers"
        value={stats.totalCustomers}
        subtitle={`${stats.newCustomersSinceLastSync} added since last month`}
      />
      <StatCard
        label="Mapped"
        value={stats.mapped}
        subtitle="Fully connected"
        colorClass="text-green-600 dark:text-green-400"
      />
      <StatCard
        label="Unmapped"
        value={stats.unmapped}
        subtitle="Need attention"
        colorClass="text-amber-600 dark:text-amber-400"
      />
      <StatCard
        label="Orphaned events"
        value={stats.orphanedEvents}
        subtitle={`${stats.orphanedIdentifiers} unknown SDK IDs`}
        colorClass="text-red-600 dark:text-red-400"
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add MappingStatsGrid component`

---

### Task 6: AlertBanners Component

**Files:**
- Create: `src/features/customers/components/alert-banners.tsx`

**Context:** Two conditional banners — amber for new customers, red for orphaned events. "Map them now" sets the filter to unmapped (via callback). "Review" scrolls to orphaned section (via callback). Alert wording adapts based on tenant mode.

- [ ] **Step 1: Create alert-banners.tsx**

```typescript
// src/features/customers/components/alert-banners.tsx
import { AlertCircle } from "lucide-react";
import { useAuthStore } from "@/stores/auth-store";
import type { CustomerMappingStats } from "../api/types";

interface AlertBannersProps {
  stats: CustomerMappingStats;
  onFilterUnmapped: () => void;
  onScrollToOrphans: () => void;
}

export function AlertBanners({
  stats,
  onFilterUnmapped,
  onScrollToOrphans,
}: AlertBannersProps) {
  const tenantMode = useAuthStore((s) => s.tenantMode);

  return (
    <div className="space-y-2.5">
      {stats.newCustomersSinceLastSync > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-amber-200 bg-amber-50 px-3.5 py-2.5 dark:border-amber-900 dark:bg-amber-950/40">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-amber-100 dark:bg-amber-900">
              <AlertCircle className="h-3 w-3 text-amber-600 dark:text-amber-400" />
            </div>
            <p className="text-xs">
              <span className="font-medium">
                {stats.newCustomersSinceLastSync} new Stripe customer
                {stats.newCustomersSinceLastSync !== 1 && "s"}
              </span>{" "}
              were detected in the last sync and need to be mapped to an SDK
              identifier before their revenue and costs can be tracked.
            </p>
          </div>
          <button
            className="shrink-0 rounded-lg border border-border bg-background px-2.5 py-1 text-[11px] hover:bg-accent"
            onClick={onFilterUnmapped}
          >
            Map them now
          </button>
        </div>
      )}

      {stats.orphanedEvents > 0 && (
        <div className="flex items-center justify-between rounded-lg border border-red-200 bg-red-50 px-3.5 py-2.5 dark:border-red-900 dark:bg-red-950/40">
          <div className="flex items-center gap-2">
            <div className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-red-100 dark:bg-red-900">
              <AlertCircle className="h-3 w-3 text-red-600 dark:text-red-400" />
            </div>
            <p className="text-xs">
              <span className="font-medium">{stats.orphanedEvents} events</span>{" "}
              arrived with customer IDs that don&apos;t match any mapping.
              {tenantMode === "billing"
                ? " These events represent potential revenue leakage."
                : " These events are tracked but can\u2019t be attributed to a Stripe customer."}
            </p>
          </div>
          <button
            className="shrink-0 rounded-lg border border-border bg-background px-2.5 py-1 text-[11px] hover:bg-accent"
            onClick={onScrollToOrphans}
          >
            Review
          </button>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add AlertBanners component`

---

### Task 7: CustomerTable Component

**Files:**
- Create: `src/features/customers/components/customer-table.tsx`

**Context:** The most complex component. Includes filter pills (All/Active/Idle/Unmapped with counts), search input, sortable 7-column table, inline editing for mapped rows (Edit -> input + Save/Cancel), and always-visible input for unmapped rows (Map button). Uses React Hook Form + Zod for inline editing per project convention. Search matches on name, SDK identifier, and Stripe ID.

**Important:** If this file exceeds 200 lines during implementation, extract the inline edit cell into `customer-row-edit.tsx`.

- [ ] **Step 1: Create customer-table.tsx**

```typescript
// src/features/customers/components/customer-table.tsx
import { useState } from "react";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { cn } from "@/lib/utils";
import { formatCostMicros, formatRelativeDate } from "@/lib/format";
import { useUpdateMapping } from "../api/queries";
import type { CustomerMapping, CustomerStatus } from "../api/types";

type FilterKey = "all" | "active" | "idle" | "unmapped";

interface CustomerTableProps {
  customers: CustomerMapping[];
  activeFilter: FilterKey;
  onFilterChange: (filter: FilterKey) => void;
  searchQuery: string;
  onSearchChange: (query: string) => void;
  editingCustomerId: string | null;
  onEditingChange: (id: string | null) => void;
}

const mappingSchema = z.object({
  sdkIdentifier: z.string().min(1, "SDK identifier is required"),
});

type MappingFormValues = z.infer<typeof mappingSchema>;

function InlineEditCell({
  customerId,
  defaultValue,
  isNew,
  onDone,
}: {
  customerId: string;
  defaultValue: string;
  isNew: boolean;
  onDone: () => void;
}) {
  const { register, handleSubmit } = useForm<MappingFormValues>({
    resolver: zodResolver(mappingSchema),
    defaultValues: { sdkIdentifier: defaultValue },
  });
  const mutation = useUpdateMapping();

  const onSubmit = (values: MappingFormValues) => {
    mutation.mutate(
      { customerId, sdkIdentifier: values.sdkIdentifier },
      { onSuccess: onDone },
    );
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="flex items-center gap-1">
      <input
        {...register("sdkIdentifier")}
        className="rounded border border-blue-300 bg-background px-1.5 py-1 font-mono text-[10px] focus:border-blue-500 focus:outline-none dark:border-blue-700"
        placeholder="Enter identifier..."
        autoFocus={!isNew}
      />
      <button
        type="submit"
        className="text-[10px] font-medium text-blue-600 hover:underline dark:text-blue-400"
        disabled={mutation.isPending}
      >
        {isNew ? "Map" : "Save"}
      </button>
      {!isNew && (
        <button
          type="button"
          className="text-[10px] text-muted-foreground hover:underline"
          onClick={onDone}
        >
          Cancel
        </button>
      )}
    </form>
  );
}

const statusConfig: Record<
  CustomerStatus,
  { label: string; className: string }
> = {
  active: {
    label: "Active",
    className: "bg-green-50 text-green-700 dark:bg-green-950 dark:text-green-300",
  },
  idle: {
    label: "Idle",
    className: "bg-accent text-muted-foreground",
  },
  unmapped: {
    label: "New",
    className: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  },
};

function filterMatches(filter: FilterKey, status: CustomerStatus): boolean {
  if (filter === "all") return true;
  if (filter === "unmapped") return status === "unmapped";
  return status === filter;
}

function searchMatches(query: string, customer: CustomerMapping): boolean {
  if (!query) return true;
  const q = query.toLowerCase();
  return (
    customer.name.toLowerCase().includes(q) ||
    (customer.sdkIdentifier?.toLowerCase().includes(q) ?? false) ||
    customer.stripeCustomerId.toLowerCase().includes(q)
  );
}

export function CustomerTable({
  customers,
  activeFilter,
  onFilterChange,
  searchQuery,
  onSearchChange,
  editingCustomerId,
  onEditingChange,
}: CustomerTableProps) {
  const filtered = customers.filter(
    (c) => filterMatches(activeFilter, c.status) && searchMatches(searchQuery, c),
  );

  const counts: Record<FilterKey, number> = {
    all: customers.length,
    active: customers.filter((c) => c.status === "active").length,
    idle: customers.filter((c) => c.status === "idle").length,
    unmapped: customers.filter((c) => c.status === "unmapped").length,
  };

  const filters: { key: FilterKey; label: string }[] = [
    { key: "all", label: "All" },
    { key: "active", label: "Active" },
    { key: "idle", label: "Idle" },
    { key: "unmapped", label: "Unmapped" },
  ];

  return (
    <div>
      <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-base font-medium">All customers</h2>
        <div className="flex items-center gap-1.5">
          <input
            type="text"
            placeholder="Search customers..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="rounded-full border border-border bg-transparent px-2.5 py-1 text-[11px] text-foreground placeholder:text-muted-foreground focus:border-ring focus:outline-none"
          />
          <button
            className="rounded-lg border border-border px-2.5 py-1 text-[11px] text-foreground opacity-50"
            disabled
          >
            Auto-match
          </button>
        </div>
      </div>

      <div className="mb-2 flex flex-wrap gap-1">
        {filters.map((f) => (
          <button
            key={f.key}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[10px]",
              activeFilter === f.key
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
            onClick={() => onFilterChange(f.key)}
          >
            {f.label} ({counts[f.key]})
          </button>
        ))}
      </div>

      <div className="overflow-hidden rounded-xl border border-border">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-border bg-accent/50">
              <th className="px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">Stripe customer</th>
              <th className="px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">SDK identifier</th>
              <th className="px-2.5 py-2 text-right text-[10px] font-medium text-muted-foreground">Revenue (30d)</th>
              <th className="px-2.5 py-2 text-right text-[10px] font-medium text-muted-foreground">Events (30d)</th>
              <th className="px-2.5 py-2 text-right text-[10px] font-medium text-muted-foreground">Last event</th>
              <th className="w-[70px] px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">Status</th>
              <th className="w-[40px] px-2.5 py-2" />
            </tr>
          </thead>
          <tbody>
            {filtered.map((customer) => {
              const isEditing = editingCustomerId === customer.id;
              const isUnmapped = customer.status === "unmapped";
              const pill = statusConfig[customer.status];

              return (
                <tr
                  key={customer.id}
                  className={cn(
                    "border-b border-border last:border-0 hover:bg-accent/30",
                    isUnmapped && "bg-emerald-50/20 dark:bg-emerald-950/10",
                  )}
                >
                  <td className="px-2.5 py-2">
                    <div className="font-medium text-[11px]">{customer.name}</div>
                    <div className="font-mono text-[9px] text-muted-foreground/60">{customer.stripeCustomerId}</div>
                    <div className="text-[10px] text-muted-foreground/60">{customer.email}</div>
                  </td>
                  <td className="px-2.5 py-2">
                    {isEditing || isUnmapped ? (
                      <InlineEditCell
                        customerId={customer.id}
                        defaultValue={customer.sdkIdentifier ?? ""}
                        isNew={isUnmapped}
                        onDone={() => onEditingChange(null)}
                      />
                    ) : (
                      <span className="font-mono text-[10px] text-blue-600 dark:text-blue-400">
                        {customer.sdkIdentifier}
                      </span>
                    )}
                  </td>
                  <td className="px-2.5 py-2 text-right font-mono text-[10px]">
                    {formatCostMicros(customer.revenue30d)}
                  </td>
                  <td className={cn(
                    "px-2.5 py-2 text-right font-mono text-[10px]",
                    (customer.events30d === 0 || isUnmapped) && "text-muted-foreground/60",
                  )}>
                    {isUnmapped ? "\u2014" : customer.events30d.toLocaleString()}
                  </td>
                  <td className="px-2.5 py-2 text-right text-[10px] text-muted-foreground/60">
                    {customer.lastEventAt
                      ? formatRelativeDate(customer.lastEventAt)
                      : "\u2014"}
                  </td>
                  <td className="px-2.5 py-2">
                    <span className={cn("rounded-full px-2 py-0.5 text-[9px] font-medium", pill.className)}>
                      {pill.label}
                    </span>
                  </td>
                  <td className="px-2.5 py-2 text-center">
                    {customer.sdkIdentifier && !isEditing && (
                      <button
                        className="text-[10px] text-blue-600 hover:underline dark:text-blue-400"
                        onClick={() => onEditingChange(customer.id)}
                      >
                        Edit
                      </button>
                    )}
                  </td>
                </tr>
              );
            })}
            {filtered.length === 0 && (
              <tr>
                <td colSpan={7} className="px-2.5 py-8 text-center text-xs text-muted-foreground">
                  All customers are mapped and healthy.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors. Check that the file is under 200 lines. If it exceeds 200, extract `InlineEditCell` to `customer-row-edit.tsx`.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add CustomerTable component with inline editing`

---

### Task 8: OrphanedEventsSection Component

**Files:**
- Create: `src/features/customers/components/orphaned-events-section.tsx`

**Context:** The "Unrecognised SDK identifiers" section at the bottom of the page. Red header bar, table with select dropdowns for assignment, dismiss all with confirmation dialog. Uses React Hook Form + Zod for the assignment dropdown. Uses shadcn Select and Dialog components.

- [ ] **Step 1: Create orphaned-events-section.tsx**

```typescript
// src/features/customers/components/orphaned-events-section.tsx
import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { formatDate, formatMicros } from "@/lib/format";
import {
  Dialog,
  DialogTrigger,
  DialogPortal,
  DialogOverlay,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
  DialogFooter,
  DialogClose,
} from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { useAssignOrphan, useDismissOrphans } from "../api/queries";
import type { CustomerMapping, OrphanedIdentifier } from "../api/types";

interface OrphanedEventsSectionProps {
  orphans: OrphanedIdentifier[];
  customers: CustomerMapping[];
}

const assignSchema = z.object({
  stripeCustomerId: z.string().min(1, "Select a customer"),
});

type AssignFormValues = z.infer<typeof assignSchema>;

function OrphanRow({
  orphan,
  customers,
}: {
  orphan: OrphanedIdentifier;
  customers: CustomerMapping[];
}) {
  const assignMutation = useAssignOrphan();
  const { control, handleSubmit } = useForm<AssignFormValues>({
    resolver: zodResolver(assignSchema),
    defaultValues: { stripeCustomerId: "" },
  });

  const onSubmit = (values: AssignFormValues) => {
    assignMutation.mutate({
      orphanId: orphan.id,
      stripeCustomerId: values.stripeCustomerId,
    });
  };

  const sortedCustomers = [...customers]
    .filter((c) => c.sdkIdentifier)
    .sort((a, b) => a.name.localeCompare(b.name));

  return (
    <tr className="border-b border-border last:border-0 hover:bg-accent/30">
      <td className="px-2.5 py-2">
        <span className="font-mono text-[11px] font-medium text-red-600 dark:text-red-400">
          {orphan.sdkIdentifier}
        </span>
      </td>
      <td className="px-2.5 py-2 text-[10px] text-muted-foreground/60">
        {formatDate(orphan.firstSeenAt)}
      </td>
      <td className="px-2.5 py-2 text-right font-mono text-[10px]">
        {orphan.eventCount}
      </td>
      <td className="px-2.5 py-2 text-right font-mono text-[10px] font-medium">
        {formatMicros(orphan.unattributedCost)}
      </td>
      <td className="px-2.5 py-2">
        <form
          onSubmit={handleSubmit(onSubmit)}
          className="flex items-center gap-1"
        >
          <Controller
            name="stripeCustomerId"
            control={control}
            render={({ field }) => (
              <Select value={field.value} onValueChange={field.onChange}>
                <SelectTrigger size="sm" className="min-w-[130px] text-[10px]">
                  <SelectValue placeholder="Select customer..." />
                </SelectTrigger>
                <SelectContent>
                  {sortedCustomers.map((c) => (
                    <SelectItem key={c.id} value={c.id}>
                      {c.name} ({c.stripeCustomerId.slice(0, 7)})
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            )}
          />
          <button
            type="submit"
            className="text-[10px] font-medium text-blue-600 hover:underline dark:text-blue-400"
            disabled={assignMutation.isPending}
          >
            {assignMutation.isPending ? "Assigning..." : "Assign"}
          </button>
        </form>
      </td>
    </tr>
  );
}

export function OrphanedEventsSection({
  orphans,
  customers,
}: OrphanedEventsSectionProps) {
  const dismissMutation = useDismissOrphans();
  const [dismissOpen, setDismissOpen] = useState(false);
  const totalEvents = orphans.reduce((sum, o) => sum + o.eventCount, 0);

  if (orphans.length === 0) return null;

  return (
    <div>
      <div className="mb-2">
        <h2 className="text-base font-medium">
          Unrecognised SDK identifiers
        </h2>
        <p className="mt-0.5 text-xs text-muted-foreground">
          These customer IDs appeared in SDK events but don&apos;t match any
          mapping. Either map them to an existing Stripe customer, or check
          your code for typos.
        </p>
      </div>

      <div className="flex items-center justify-between rounded-t-xl bg-red-50 px-3.5 py-2.5 dark:bg-red-950/40">
        <span className="text-xs font-medium text-red-600 dark:text-red-400">
          {orphans.length} unknown identifier{orphans.length !== 1 && "s"} ({totalEvents} events)
        </span>
        <Dialog open={dismissOpen} onOpenChange={setDismissOpen}>
          <DialogTrigger
            className="rounded-lg border border-red-200 bg-background px-2.5 py-1 text-[11px] text-red-600 hover:bg-red-50 dark:border-red-800 dark:text-red-400 dark:hover:bg-red-950"
          >
            Dismiss all
          </DialogTrigger>
          <DialogPortal>
            <DialogOverlay />
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Dismiss all orphaned identifiers?</DialogTitle>
                <DialogDescription>
                  This will dismiss {orphans.length} unrecognised SDK identifiers
                  and {totalEvents} unattributed events. This action cannot be
                  undone.
                </DialogDescription>
              </DialogHeader>
              <DialogFooter>
                <DialogClose render={<Button variant="outline" />}>
                  Cancel
                </DialogClose>
                <Button
                  variant="destructive"
                  onClick={() => {
                    dismissMutation.mutate(undefined, {
                      onSuccess: () => setDismissOpen(false),
                    });
                  }}
                  disabled={dismissMutation.isPending}
                >
                  {dismissMutation.isPending ? "Dismissing..." : "Dismiss all"}
                </Button>
              </DialogFooter>
            </DialogContent>
          </DialogPortal>
        </Dialog>
      </div>

      <div className="overflow-hidden rounded-b-xl border border-t-0 border-red-200 dark:border-red-900">
        <table className="w-full border-collapse text-[11px]">
          <thead>
            <tr className="border-b border-border bg-accent/50">
              <th className="px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">SDK identifier received</th>
              <th className="px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">First seen</th>
              <th className="px-2.5 py-2 text-right text-[10px] font-medium text-muted-foreground">Events</th>
              <th className="px-2.5 py-2 text-right text-[10px] font-medium text-muted-foreground">Unattributed cost</th>
              <th className="px-2.5 py-2 text-left text-[10px] font-medium text-muted-foreground">Assign to Stripe customer</th>
            </tr>
          </thead>
          <tbody>
            {orphans.map((orphan) => (
              <OrphanRow
                key={orphan.id}
                orphan={orphan}
                customers={customers}
              />
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-1.5 px-1 text-[10px] text-muted-foreground/60">
        When you assign an orphaned identifier, the existing events are
        retroactively attributed to that Stripe customer. Future events with
        this identifier will also be mapped automatically.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors. The Dialog and Select component imports should resolve to the existing shadcn components.

- [ ] **Step 3: Ready to commit**

Suggested: `feat(customers): add OrphanedEventsSection component`

---

### Task 9: CustomerMappingPage + Route Update

**Files:**
- Create: `src/features/customers/components/customer-mapping-page.tsx`
- Modify: `src/app/routes/_app/customers/index.tsx`

**Context:** The orchestrator component. Fetches data, manages client state, composes all child components. Checks `tenantMode` for track-only gating. The route file is a thin delegate.

- [ ] **Step 1: Create customer-mapping-page.tsx**

```typescript
// src/features/customers/components/customer-mapping-page.tsx
import { useRef, useState } from "react";
import { Link } from "@tanstack/react-router";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useAuthStore } from "@/stores/auth-store";
import { useCustomerMapping } from "../api/queries";
import { SyncStatusBar } from "./sync-status-bar";
import { MappingStatsGrid } from "./mapping-stats-grid";
import { AlertBanners } from "./alert-banners";
import { CustomerTable } from "./customer-table";
import { OrphanedEventsSection } from "./orphaned-events-section";

type FilterKey = "all" | "active" | "idle" | "unmapped";

export function CustomerMappingPage() {
  const tenantMode = useAuthStore((s) => s.tenantMode);
  const { data, isLoading } = useCustomerMapping();
  const [activeFilter, setActiveFilter] = useState<FilterKey>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingCustomerId, setEditingCustomerId] = useState<string | null>(
    null,
  );
  const orphanRef = useRef<HTMLDivElement>(null);

  if (tenantMode === "track") {
    return (
      <div className="space-y-6">
        <PageHeader
          title="Customer mapping"
          description="Manage how your Stripe customers connect to the identifiers your SDK sends."
        />
        <div className="rounded-lg border border-dashed p-12 text-center">
          <h3 className="text-sm font-medium">Connect Stripe to get started</h3>
          <p className="mt-1 text-xs text-muted-foreground">
            Customer mapping requires a Stripe connection. Connect your Stripe
            account to map customers to SDK identifiers.
          </p>
          <Link
            to="/settings"
            className="mt-3 inline-block rounded-lg bg-primary px-4 py-2 text-xs text-primary-foreground hover:bg-primary/90"
          >
            Go to Settings
          </Link>
        </div>
      </div>
    );
  }

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <PageHeader title="Customer mapping" />
        <Skeleton className="h-12 rounded-lg" />
        <div className="grid grid-cols-4 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-[68px] rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-10 rounded-lg" />
        <Skeleton className="h-64 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <PageHeader
        title="Customer mapping"
        description="Manage how your Stripe customers connect to the identifiers your SDK sends. Every mapping must be correct for accurate cost tracking, revenue attribution, and billing."
      />

      <SyncStatusBar syncStatus={data.syncStatus} />

      <MappingStatsGrid stats={data.stats} />

      <AlertBanners
        stats={data.stats}
        onFilterUnmapped={() => setActiveFilter("unmapped")}
        onScrollToOrphans={() =>
          orphanRef.current?.scrollIntoView({ behavior: "smooth" })
        }
      />

      <CustomerTable
        customers={data.customers}
        activeFilter={activeFilter}
        onFilterChange={setActiveFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        editingCustomerId={editingCustomerId}
        onEditingChange={setEditingCustomerId}
      />

      <div ref={orphanRef}>
        <OrphanedEventsSection
          orphans={data.orphanedIdentifiers}
          customers={data.customers}
        />
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Update route file**

Replace the contents of `src/app/routes/_app/customers/index.tsx`:

```typescript
import { createFileRoute } from "@tanstack/react-router";
import { CustomerMappingPage } from "@/features/customers/components/customer-mapping-page";

export const Route = createFileRoute("/_app/customers/")({
  component: CustomerMappingPage,
});
```

- [ ] **Step 3: Verify no type errors**

Run: `pnpm tsc --noEmit`
Expected: No errors.

- [ ] **Step 4: Verify in browser**

Run: `pnpm dev`

1. Navigate to `/customers` — should see the full page with sync bar, stats, alerts, table, and orphaned section
2. Click filter pills — table should filter correctly
3. Type in search — table should filter by name/SDK ID/Stripe ID
4. Click "Edit" on a mapped row — should show inline input with Save/Cancel
5. Click "Map" on an unmapped row — should save and change status to Idle
6. Click "Sync now" — should show "Syncing..." then revert
7. Verify the "Map them now" alert button sets filter to Unmapped
8. Verify the "Review" alert button scrolls to orphaned section
9. Test assigning an orphan — select a customer, click Assign, row should disappear
10. Test "Dismiss all" — should show confirmation dialog

- [ ] **Step 5: Ready to commit**

Suggested: `feat(customers): add CustomerMappingPage orchestrator and route`

---

## Post-Implementation

After all tasks are complete:

- [ ] Update `PROGRESS.md`:
  - Change Phase 5 status from "Not started" to "Complete"
  - Add Phase 5 checklist items (all checked)
  - Update "Current Status" to point to Phase 6
  - Add session log entry

- [ ] Suggested commit for PROGRESS.md: `docs: mark phase 5 customer mapping complete`
