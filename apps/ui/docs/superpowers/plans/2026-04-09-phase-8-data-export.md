# Phase 8: Data Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the Data Export page at `/export` — live-updating filters, row estimate, 5-row preview table with granularity switching, and download with format/granularity toggles.

**Architecture:** Feature-co-located module under `src/features/export/` following the same pattern as `src/features/customers/`. All filter state in ExportPage as useState, TanStack Query for preview data + download mutation, debounced filter-to-query bridge. CustomerMultiSelect uses shadcn Popover for searchable dropdown. TogglePillGroup is a reusable component for product/card pill filters.

**Tech Stack:** React 19, TanStack Query v5, shadcn/ui (Popover, Badge, Input, Button, ScrollArea, Skeleton), Lucide icons, Tailwind CSS v4.

**Spec:** `docs/superpowers/specs/2026-04-09-phase-8-data-export.md`
**Mockup:** `docs/design/files/data_export_page.html`

---

## File Map

```
Files to CREATE:
  src/components/ui/popover.tsx                    — shadcn Popover (installed via CLI)
  src/features/export/api/types.ts                 — TypeScript interfaces
  src/features/export/api/mock-data.ts             — Filter options + preview rows + estimate logic
  src/features/export/api/mock.ts                  — Mock API functions
  src/features/export/api/api.ts                   — Real API stubs
  src/features/export/api/provider.ts              — selectProvider({ mock, api })
  src/features/export/api/queries.ts               — TanStack Query hooks
  src/features/export/api/mutations.ts             — Download mutation
  src/features/export/components/toggle-pill-group.tsx      — Reusable pill filter (products & cards)
  src/features/export/components/customer-multi-select.tsx  — Searchable multi-select with Popover
  src/features/export/components/export-filters.tsx         — Filters card composing sub-components
  src/features/export/components/export-estimate.tsx        — Summary + row count + file size
  src/features/export/components/data-preview-table.tsx     — 5-row preview, columns swap by granularity
  src/features/export/components/download-bar.tsx           — Format/granularity toggles + download button
  src/features/export/components/export-page.tsx            — Orchestrator

Files to MODIFY:
  src/app/routes/_app/export/index.tsx             — Replace stub with feature import
```

---

### Task 1: Install Popover + Create API Types

**Files:**
- Install: `src/components/ui/popover.tsx` (via shadcn CLI)
- Create: `src/features/export/api/types.ts`

- [ ] **Step 1: Install shadcn Popover component**

Run: `pnpm dlx shadcn@latest add popover`
Expected: Creates `src/components/ui/popover.tsx` using `@base-ui/react/popover`.

- [ ] **Step 2: Verify Popover installed**

Run: `ls src/components/ui/popover.tsx`
Expected: File exists.

- [ ] **Step 3: Create types file**

```typescript
// src/features/export/api/types.ts

export type ExportGranularity = "dimension" | "event";
export type ExportFormat = "csv" | "json";
export type DatePreset = "7d" | "30d" | "90d" | "all";

export interface ExportFilters {
  dateFrom: string; // "YYYY-MM-DD"
  dateTo: string; // "YYYY-MM-DD"
  customerIds: string[]; // empty = all
  productKeys: string[]; // empty = all
  cardKeys: string[]; // empty = all
  granularity: ExportGranularity;
}

export interface ExportEstimate {
  rowCount: number;
  fileSizeBytes: number;
}

export interface PreviewColumn {
  key: string;
  label: string;
  align?: "left" | "right";
}

export interface ExportPreviewData {
  estimate: ExportEstimate;
  columns: PreviewColumn[];
  rows: Record<string, string | number | null>[];
}

export interface FilterOptionCustomer {
  id: string;
  name: string;
  eventCount: number;
}

export interface FilterOptionProduct {
  key: string;
  label: string;
  percentage: number;
}

export interface FilterOptionCard {
  key: string;
  label: string;
  percentage: number;
}

export interface ExportFilterOptions {
  customers: FilterOptionCustomer[];
  products: FilterOptionProduct[];
  cards: FilterOptionCard[];
}
```

- [ ] **Step 4: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 5: Ready to commit**

Suggested: `feat(export): install Popover component and add API types`

---

### Task 2: Mock Data + Mock Implementation

**Files:**
- Create: `src/features/export/api/mock-data.ts`
- Create: `src/features/export/api/mock.ts`

**Context:** The mock estimate uses the mockup's formula: ~8,260 rows/day, scaled by filters. Preview rows are hardcoded from the mockup for both granularity modes. Filter options reuse customer names from the customer mapping mockup.

- [ ] **Step 1: Create mock-data.ts**

```typescript
// src/features/export/api/mock-data.ts
import type {
  ExportFilterOptions,
  PreviewColumn,
} from "./types";

export const mockFilterOptions: ExportFilterOptions = {
  customers: [
    { id: "1", name: "Acme Corp", eventCount: 14_219 },
    { id: "2", name: "BrightPath Ltd", eventCount: 11_402 },
    { id: "3", name: "NovaTech Inc", eventCount: 6_841 },
    { id: "4", name: "Helios Digital", eventCount: 9_403 },
    { id: "5", name: "Zenith Labs", eventCount: 5_120 },
    { id: "6", name: "ClearView Analytics", eventCount: 8_210 },
    { id: "7", name: "Eko Systems", eventCount: 7_891 },
    { id: "8", name: "Pinnacle AI", eventCount: 2_104 },
    { id: "9", name: "Meridian Group", eventCount: 3_812 },
    { id: "10", name: "Atlas Robotics", eventCount: 2_310 },
    { id: "11", name: "Quantum Logic", eventCount: 1_891 },
    { id: "12", name: "BlueSky Data", eventCount: 1_402 },
    { id: "13", name: "Vertex Labs", eventCount: 980 },
    { id: "14", name: "Forge AI", eventCount: 820 },
    { id: "15", name: "Echo Systems", eventCount: 650 },
    { id: "16", name: "Ridgeline", eventCount: 410 },
    { id: "17", name: "Prism Health", eventCount: 220 },
    { id: "18", name: "Aether Inc", eventCount: 102 },
  ],
  products: [
    { key: "property_search", label: "Property search", percentage: 68 },
    { key: "doc_summariser", label: "Doc summariser", percentage: 22 },
    { key: "content_gen", label: "Content gen", percentage: 10 },
  ],
  cards: [
    { key: "gemini_2_flash", label: "Gemini 2.0 Flash", percentage: 55 },
    { key: "claude_sonnet", label: "Claude Sonnet", percentage: 25 },
    { key: "gpt_4o", label: "GPT-4o", percentage: 12 },
    { key: "google_places", label: "Google Places", percentage: 5 },
    { key: "serper", label: "Serper", percentage: 3 },
  ],
};

export const dimensionColumns: PreviewColumn[] = [
  { key: "eventTime", label: "event_time" },
  { key: "customer", label: "customer" },
  { key: "product", label: "product" },
  { key: "pricingCard", label: "pricing_card" },
  { key: "cardVersion", label: "card_version" },
  { key: "dimension", label: "dimension" },
  { key: "quantity", label: "quantity", align: "right" },
  { key: "unitPrice", label: "unit_price", align: "right" },
  { key: "cost", label: "cost", align: "right" },
  { key: "eventTotal", label: "event_total", align: "right" },
];

export const dimensionRows: Record<string, string | number | null>[] = [
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "input_tokens", quantity: "1,842", unitPrice: "0.0000001500", cost: "0.000276", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "output_tokens", quantity: "623", unitPrice: "0.0000004000", cost: "0.000249", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", dimension: "grounding_requests", quantity: "1", unitPrice: "0.0350000000", cost: "0.035000", eventTotal: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "google_places", cardVersion: "v1", dimension: "requests", quantity: "1", unitPrice: "0.0320000000", cost: "0.032000", eventTotal: "0.032000" },
  { eventTime: "2026-03-20 14:22:58", customer: "brightpath", product: "doc_summariser", pricingCard: "claude_35_sonnet", cardVersion: "v2", dimension: "input_tokens", quantity: "4,210", unitPrice: "0.0000030000", cost: "0.012630", eventTotal: "0.040335" },
];

export const eventColumns: PreviewColumn[] = [
  { key: "eventTime", label: "event_time" },
  { key: "customer", label: "customer" },
  { key: "product", label: "product" },
  { key: "pricingCard", label: "pricing_card" },
  { key: "cardVersion", label: "card_version" },
  { key: "inputTokens", label: "input_tokens", align: "right" },
  { key: "outputTokens", label: "output_tokens", align: "right" },
  { key: "groundingReqs", label: "grounding_reqs", align: "right" },
  { key: "requests", label: "requests", align: "right" },
  { key: "totalCost", label: "total_cost", align: "right" },
];

export const eventRows: Record<string, string | number | null>[] = [
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", inputTokens: "1,842", outputTokens: "623", groundingReqs: "1", requests: null, totalCost: "0.035847" },
  { eventTime: "2026-03-20 14:23:01", customer: "acme_corp", product: "property_search", pricingCard: "google_places", cardVersion: "v1", inputTokens: null, outputTokens: null, groundingReqs: null, requests: "1", totalCost: "0.032000" },
  { eventTime: "2026-03-20 14:22:58", customer: "brightpath", product: "doc_summariser", pricingCard: "claude_35_sonnet", cardVersion: "v2", inputTokens: "4,210", outputTokens: "1,847", groundingReqs: null, requests: null, totalCost: "0.040335" },
  { eventTime: "2026-03-20 14:22:55", customer: "novatech", product: "property_search", pricingCard: "gemini_2_flash", cardVersion: "v3", inputTokens: "986", outputTokens: "412", groundingReqs: "1", requests: null, totalCost: "0.035321" },
  { eventTime: "2026-03-20 14:22:51", customer: "helios", product: "content_gen", pricingCard: "gpt_4o", cardVersion: "v1", inputTokens: "2,105", outputTokens: "3,241", groundingReqs: null, requests: null, totalCost: "0.037685" },
];

/** Product key → fraction of total events */
export const productPcts: Record<string, number> = {
  property_search: 0.68,
  doc_summariser: 0.22,
  content_gen: 0.10,
};

/** Card key → fraction of total events */
export const cardPcts: Record<string, number> = {
  gemini_2_flash: 0.55,
  claude_sonnet: 0.25,
  gpt_4o: 0.12,
  google_places: 0.05,
  serper: 0.03,
};
```

- [ ] **Step 2: Create mock.ts**

```typescript
// src/features/export/api/mock.ts
import type {
  ExportFilterOptions,
  ExportFilters,
  ExportPreviewData,
} from "./types";
import {
  mockFilterOptions,
  dimensionColumns,
  dimensionRows,
  eventColumns,
  eventRows,
  productPcts,
  cardPcts,
} from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

export async function getFilterOptions(): Promise<ExportFilterOptions> {
  await delay();
  return structuredClone(mockFilterOptions);
}

function computeEstimate(filters: ExportFilters) {
  const from = new Date(filters.dateFrom);
  const to = new Date(filters.dateTo);
  const days = Math.max(1, Math.round((to.getTime() - from.getTime()) / 86_400_000));

  let rows = 8_260 * days;

  if (filters.customerIds.length > 0) {
    rows = Math.round(rows * (filters.customerIds.length / mockFilterOptions.customers.length));
  }
  if (filters.productKeys.length > 0) {
    const frac = filters.productKeys.reduce((s, k) => s + (productPcts[k] ?? 0), 0);
    rows = Math.round(rows * frac);
  }
  if (filters.cardKeys.length > 0) {
    const frac = filters.cardKeys.reduce((s, k) => s + (cardPcts[k] ?? 0), 0);
    rows = Math.round(rows * frac);
  }
  if (filters.granularity === "event") {
    rows = Math.round(rows / 2.8);
  }

  rows = Math.max(0, rows);
  const fileSizeBytes = Math.round(Math.max(100, rows * 75));

  return { rowCount: rows, fileSizeBytes };
}

export async function getPreview(
  filters: ExportFilters,
): Promise<ExportPreviewData> {
  await delay();
  const estimate = computeEstimate(filters);
  const columns = filters.granularity === "event" ? eventColumns : dimensionColumns;
  const rows = filters.granularity === "event" ? eventRows : dimensionRows;
  return {
    estimate,
    columns: structuredClone(columns),
    rows: structuredClone(rows),
  };
}

export async function generateExport(
  _filters: ExportFilters,
): Promise<{ downloadUrl: string }> {
  await delay(1500);
  return { downloadUrl: "#mock-download" };
}
```

- [ ] **Step 3: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 4: Ready to commit**

Suggested: `feat(export): add mock data and mock API implementation`

---

### Task 3: API Stubs + Provider + Queries + Mutations

**Files:**
- Create: `src/features/export/api/api.ts`
- Create: `src/features/export/api/provider.ts`
- Create: `src/features/export/api/queries.ts`
- Create: `src/features/export/api/mutations.ts`

- [ ] **Step 1: Create api.ts**

```typescript
// src/features/export/api/api.ts
import type {
  ExportFilterOptions,
  ExportFilters,
  ExportPreviewData,
} from "./types";
import { platformApi } from "@/api/client";

export async function getFilterOptions(): Promise<ExportFilterOptions> {
  const { data } = await platformApi.GET("/export/filter-options", {});
  return data as ExportFilterOptions;
}

export async function getPreview(
  filters: ExportFilters,
): Promise<ExportPreviewData> {
  const { data } = await platformApi.POST("/export/preview", {
    body: filters,
  });
  return data as ExportPreviewData;
}

export async function generateExport(
  filters: ExportFilters,
): Promise<{ downloadUrl: string }> {
  const { data } = await platformApi.POST("/export/generate", {
    body: filters,
  });
  return data as { downloadUrl: string };
}
```

- [ ] **Step 2: Create provider.ts**

```typescript
// src/features/export/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const exportApi = selectProvider({ mock, api });
```

- [ ] **Step 3: Create queries.ts**

```typescript
// src/features/export/api/queries.ts
import { useQuery } from "@tanstack/react-query";
import { exportApi } from "./provider";
import type { ExportFilters } from "./types";

export function useExportFilterOptions() {
  return useQuery({
    queryKey: ["export-filter-options"],
    queryFn: () => exportApi.getFilterOptions(),
    staleTime: 5 * 60 * 1000, // 5 minutes
  });
}

export function useExportPreview(filters: ExportFilters | null) {
  return useQuery({
    queryKey: ["export-preview", filters],
    queryFn: () => exportApi.getPreview(filters!),
    enabled: filters !== null,
    placeholderData: (prev) => prev, // keep previous data while refetching
  });
}
```

- [ ] **Step 4: Create mutations.ts**

```typescript
// src/features/export/api/mutations.ts
import { useMutation } from "@tanstack/react-query";
import { exportApi } from "./provider";
import type { ExportFilters } from "./types";

export function useGenerateExport() {
  return useMutation({
    mutationFn: (filters: ExportFilters) => exportApi.generateExport(filters),
  });
}
```

- [ ] **Step 5: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 6: Ready to commit**

Suggested: `feat(export): add API stubs, provider, queries, and mutations`

---

### Task 4: TogglePillGroup Component

**Files:**
- Create: `src/features/export/components/toggle-pill-group.tsx`

**Context:** Reusable component for product and pricing card pill filters. "All" pill + individual pills with percentage labels. Used twice in ExportFilters.

- [ ] **Step 1: Create toggle-pill-group.tsx**

```typescript
// src/features/export/components/toggle-pill-group.tsx
import { cn } from "@/lib/utils";

interface PillOption {
  key: string;
  label: string;
  percentage: number;
}

interface TogglePillGroupProps {
  label: string;
  allLabel: string; // "All products" or "All cards"
  options: PillOption[];
  selectedKeys: string[];
  onSelectionChange: (keys: string[]) => void;
}

export function TogglePillGroup({
  label,
  allLabel,
  options,
  selectedKeys,
  onSelectionChange,
}: TogglePillGroupProps) {
  const isAll = selectedKeys.length === 0;

  function toggleKey(key: string) {
    if (selectedKeys.includes(key)) {
      const next = selectedKeys.filter((k) => k !== key);
      onSelectionChange(next); // empty = all
    } else {
      onSelectionChange([...selectedKeys, key]);
    }
  }

  return (
    <div>
      <div className="mb-1.5 text-xs font-medium">{label}</div>
      <div className="flex flex-wrap gap-1">
        <button
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[11px]",
            isAll
              ? "border-foreground bg-foreground text-background"
              : "border-border text-muted-foreground hover:bg-accent",
          )}
          onClick={() => onSelectionChange([])}
        >
          {allLabel}
        </button>
        {options.map((opt) => {
          const active = selectedKeys.includes(opt.key);
          return (
            <button
              key={opt.key}
              className={cn(
                "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[11px]",
                active
                  ? "border-foreground bg-foreground text-background"
                  : "border-border text-muted-foreground hover:bg-accent",
              )}
              onClick={() => toggleKey(opt.key)}
            >
              {opt.label}
              <span className="text-[9px] opacity-60">{opt.percentage}%</span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 3: Ready to commit**

Suggested: `feat(export): add TogglePillGroup component`

---

### Task 5: CustomerMultiSelect Component

**Files:**
- Create: `src/features/export/components/customer-multi-select.tsx`

**Context:** Searchable multi-select using shadcn Popover + ScrollArea. "All customers" pill, search input, checkbox dropdown, chip tags. IMPORTANT: Read `src/components/ui/popover.tsx` before implementing to understand the Base UI Popover API.

- [ ] **Step 1: Read the Popover component to understand the API**

Read `src/components/ui/popover.tsx` — check what's exported and how the Base UI Popover works (it uses `@base-ui/react/popover`, not Radix).

- [ ] **Step 2: Create customer-multi-select.tsx**

```typescript
// src/features/export/components/customer-multi-select.tsx
import { useState } from "react";
import { cn } from "@/lib/utils";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  Popover,
  PopoverTrigger,
  PopoverContent,
} from "@/components/ui/popover";
import { X } from "lucide-react";
import type { FilterOptionCustomer } from "../api/types";

interface CustomerMultiSelectProps {
  customers: FilterOptionCustomer[];
  selectedIds: string[];
  onSelectionChange: (ids: string[]) => void;
}

export function CustomerMultiSelect({
  customers,
  selectedIds,
  onSelectionChange,
}: CustomerMultiSelectProps) {
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const isAll = selectedIds.length === 0;

  const filtered = customers.filter((c) =>
    c.name.toLowerCase().includes(search.toLowerCase()),
  );

  function toggleCustomer(id: string) {
    if (selectedIds.includes(id)) {
      onSelectionChange(selectedIds.filter((i) => i !== id));
    } else {
      onSelectionChange([...selectedIds, id]);
    }
  }

  function removeCustomer(id: string) {
    onSelectionChange(selectedIds.filter((i) => i !== id));
  }

  return (
    <div>
      <div className="mb-1.5 text-xs font-medium">Customers</div>
      <div className="mb-1 flex items-center gap-1.5">
        <button
          className={cn(
            "inline-flex items-center gap-1 rounded-full border px-3 py-1 text-[11px]",
            isAll
              ? "border-foreground bg-foreground text-background"
              : "border-border text-muted-foreground hover:bg-accent",
          )}
          onClick={() => onSelectionChange([])}
        >
          All customers
          <span className="text-[9px] opacity-60">({customers.length})</span>
        </button>
        <span className="text-[10px] text-muted-foreground">
          or select specific:
        </span>
      </div>

      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger
          className="w-full rounded-lg border border-border bg-transparent px-2.5 py-1.5 text-left text-[11px] text-muted-foreground hover:border-ring focus:border-ring focus:outline-none"
          onClick={() => setOpen(true)}
        >
          Search customers...
        </PopoverTrigger>
        <PopoverContent
          className="w-[var(--anchor-width)] p-0"
          align="start"
          sideOffset={4}
        >
          <div className="p-2">
            <input
              type="text"
              placeholder="Search customers..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full rounded-md border border-border bg-transparent px-2.5 py-1.5 text-[11px] focus:border-ring focus:outline-none"
              autoFocus
            />
          </div>
          <ScrollArea className="max-h-[160px]">
            {filtered.map((c) => {
              const checked = selectedIds.includes(c.id);
              return (
                <button
                  key={c.id}
                  className="flex w-full items-center justify-between px-3 py-1.5 text-[11px] hover:bg-accent"
                  onClick={() => toggleCustomer(c.id)}
                >
                  <div className="flex items-center gap-1.5">
                    <div
                      className={cn(
                        "flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-[3px] border-[1.5px]",
                        checked
                          ? "border-blue-600 bg-blue-600"
                          : "border-border",
                      )}
                    >
                      {checked && (
                        <svg
                          width="8"
                          height="8"
                          viewBox="0 0 8 8"
                          fill="none"
                        >
                          <path
                            d="M1.5 4L3 5.5L6.5 2"
                            stroke="white"
                            strokeWidth="1.5"
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                        </svg>
                      )}
                    </div>
                    <span className="font-medium">{c.name}</span>
                  </div>
                  <span className="font-mono text-[9px] text-muted-foreground">
                    {c.eventCount.toLocaleString()} evts
                  </span>
                </button>
              );
            })}
            {filtered.length === 0 && (
              <div className="px-3 py-2 text-[11px] text-muted-foreground">
                No customers match your search.
              </div>
            )}
          </ScrollArea>
        </PopoverContent>
      </Popover>

      {selectedIds.length > 0 && (
        <div className="mt-1.5 flex flex-wrap gap-1">
          {selectedIds.map((id) => {
            const customer = customers.find((c) => c.id === id);
            if (!customer) return null;
            return (
              <Badge
                key={id}
                variant="secondary"
                className="gap-1 bg-blue-50 text-[10px] text-blue-700 dark:bg-blue-950 dark:text-blue-300"
              >
                {customer.name}
                <button
                  onClick={() => removeCustomer(id)}
                  className="opacity-50 hover:opacity-100"
                >
                  <X className="h-3 w-3" />
                </button>
              </Badge>
            );
          })}
        </div>
      )}
    </div>
  );
}
```

**IMPORTANT:** After reading the Popover component file, adapt the props if the Base UI API differs from the code above. The key props needed are `open`, `onOpenChange`, and `PopoverContent` with `align` and `sideOffset`. If the shadcn Popover wraps these differently, adjust accordingly.

- [ ] **Step 3: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 4: Ready to commit**

Suggested: `feat(export): add CustomerMultiSelect component`

---

### Task 6: ExportFilters Component

**Files:**
- Create: `src/features/export/components/export-filters.tsx`

**Context:** Composes date range, presets, CustomerMultiSelect, and two TogglePillGroup instances into a single filters card.

- [ ] **Step 1: Create export-filters.tsx**

```typescript
// src/features/export/components/export-filters.tsx
import { cn } from "@/lib/utils";
import type {
  DatePreset,
  ExportFilterOptions,
} from "../api/types";
import { CustomerMultiSelect } from "./customer-multi-select";
import { TogglePillGroup } from "./toggle-pill-group";

interface ExportFiltersProps {
  filterOptions: ExportFilterOptions;
  dateFrom: string;
  dateTo: string;
  datePreset: DatePreset | null;
  onDateFromChange: (v: string) => void;
  onDateToChange: (v: string) => void;
  onDatePreset: (preset: DatePreset) => void;
  selectedCustomerIds: string[];
  onCustomerSelectionChange: (ids: string[]) => void;
  selectedProductKeys: string[];
  onProductSelectionChange: (keys: string[]) => void;
  selectedCardKeys: string[];
  onCardSelectionChange: (keys: string[]) => void;
}

const presets: { key: DatePreset; label: string }[] = [
  { key: "7d", label: "Last 7 days" },
  { key: "30d", label: "Last 30 days" },
  { key: "90d", label: "Last 90 days" },
  { key: "all", label: "All time" },
];

export function ExportFilters({
  filterOptions,
  dateFrom,
  dateTo,
  datePreset,
  onDateFromChange,
  onDateToChange,
  onDatePreset,
  selectedCustomerIds,
  onCustomerSelectionChange,
  selectedProductKeys,
  onProductSelectionChange,
  selectedCardKeys,
  onCardSelectionChange,
}: ExportFiltersProps) {
  return (
    <div className="rounded-xl border border-border p-4">
      <h2 className="mb-3 text-sm font-medium">Filters</h2>

      <div className="mb-2.5 grid grid-cols-2 gap-2.5">
        <div>
          <label className="mb-1 block text-xs font-medium">From</label>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => onDateFromChange(e.target.value)}
            className="w-full rounded-lg border border-border bg-transparent px-2.5 py-1.5 text-xs focus:border-ring focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">To</label>
          <input
            type="date"
            value={dateTo}
            onChange={(e) => onDateToChange(e.target.value)}
            className="w-full rounded-lg border border-border bg-transparent px-2.5 py-1.5 text-xs focus:border-ring focus:outline-none"
          />
        </div>
      </div>

      <div className="mb-3.5 flex flex-wrap gap-1">
        {presets.map((p) => (
          <button
            key={p.key}
            className={cn(
              "rounded-full border px-2.5 py-0.5 text-[10px]",
              datePreset === p.key
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
            onClick={() => onDatePreset(p.key)}
          >
            {p.label}
          </button>
        ))}
      </div>

      <div className="mb-3">
        <CustomerMultiSelect
          customers={filterOptions.customers}
          selectedIds={selectedCustomerIds}
          onSelectionChange={onCustomerSelectionChange}
        />
      </div>

      <div className="mb-3">
        <TogglePillGroup
          label="Products"
          allLabel="All products"
          options={filterOptions.products}
          selectedKeys={selectedProductKeys}
          onSelectionChange={onProductSelectionChange}
        />
      </div>

      <TogglePillGroup
        label="Pricing cards"
        allLabel="All cards"
        options={filterOptions.cards}
        selectedKeys={selectedCardKeys}
        onSelectionChange={onCardSelectionChange}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 3: Ready to commit**

Suggested: `feat(export): add ExportFilters component`

---

### Task 7: ExportEstimate Component

**Files:**
- Create: `src/features/export/components/export-estimate.tsx`

**Context:** Displays the natural language summary, row count, file size, and optional large export warning. The summary is built client-side from the filters and filter options.

- [ ] **Step 1: Create export-estimate.tsx**

```typescript
// src/features/export/components/export-estimate.tsx
import { AlertCircle } from "lucide-react";
import { formatShortDate } from "@/lib/format";
import type { ExportEstimate as EstimateData, ExportFilterOptions } from "../api/types";

interface ExportEstimateProps {
  estimate: EstimateData;
  filterOptions: ExportFilterOptions;
  selectedCustomerIds: string[];
  selectedProductKeys: string[];
  selectedCardKeys: string[];
  dateFrom: string;
  dateTo: string;
}

function formatFileSize(bytes: number): string {
  if (bytes >= 1_000_000) return `~${Math.round(bytes / 1_000_000)} MB`;
  if (bytes >= 1_000) return `~${Math.round(bytes / 1_000)} KB`;
  return `${bytes} B`;
}

export function ExportEstimate({
  estimate,
  filterOptions,
  selectedCustomerIds,
  selectedProductKeys,
  selectedCardKeys,
  dateFrom,
  dateTo,
}: ExportEstimateProps) {
  const customerText =
    selectedCustomerIds.length === 0
      ? `all ${filterOptions.customers.length} customers`
      : selectedCustomerIds.length === 1
        ? (filterOptions.customers.find((c) => c.id === selectedCustomerIds[0])?.name ?? "1 customer")
        : `${selectedCustomerIds.length} customers`;

  const productText =
    selectedProductKeys.length === 0
      ? "all products"
      : selectedProductKeys
          .map((k) => filterOptions.products.find((p) => p.key === k)?.label)
          .filter(Boolean)
          .join(", ");

  const cardText =
    selectedCardKeys.length === 0
      ? "all pricing cards"
      : selectedCardKeys
          .map((k) => filterOptions.cards.find((c) => c.key === k)?.label)
          .filter(Boolean)
          .join(", ");

  const days = Math.max(
    1,
    Math.round(
      (new Date(dateTo).getTime() - new Date(dateFrom).getTime()) / 86_400_000,
    ),
  );

  const dateRange = `${formatShortDate(dateFrom + "T00:00:00Z")} \u2014 ${formatShortDate(dateTo + "T00:00:00Z")}`;

  return (
    <div className="rounded-xl bg-accent/50 px-4 py-3.5">
      <div className="flex items-start justify-between gap-3">
        <p className="flex-1 text-xs leading-relaxed text-muted-foreground">
          Exporting <strong className="text-foreground">all events</strong>{" "}
          across{" "}
          <strong className="text-foreground">{customerText}</strong>,{" "}
          <strong className="text-foreground">{productText}</strong>, and{" "}
          <strong className="text-foreground">{cardText}</strong> from{" "}
          <strong className="text-foreground">{dateRange}</strong> ({days}{" "}
          day{days !== 1 && "s"}).
        </p>
        <div className="flex gap-4">
          <div className="text-center">
            <div className="text-lg font-medium">
              {estimate.rowCount.toLocaleString()}
            </div>
            <div className="text-[10px] text-muted-foreground">rows</div>
          </div>
          <div className="text-center">
            <div className="text-lg font-medium">
              {formatFileSize(estimate.fileSizeBytes)}
            </div>
            <div className="text-[10px] text-muted-foreground">file size</div>
          </div>
        </div>
      </div>
      {estimate.rowCount > 500_000 && (
        <div className="mt-2 flex items-center gap-2 rounded-lg bg-amber-50 px-2.5 py-1.5 text-[11px] text-amber-700 dark:bg-amber-950/40 dark:text-amber-400">
          <AlertCircle className="h-3.5 w-3.5 shrink-0" />
          Large export — consider adding filters to reduce the file size.
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 3: Ready to commit**

Suggested: `feat(export): add ExportEstimate component`

---

### Task 8: DataPreviewTable Component

**Files:**
- Create: `src/features/export/components/data-preview-table.tsx`

**Context:** Renders 5 preview rows. Columns come from the preview data (swap between dimension and event schemas based on granularity). Monospace font for data, muted for null/dash values, bold for cost columns.

- [ ] **Step 1: Create data-preview-table.tsx**

```typescript
// src/features/export/components/data-preview-table.tsx
import { cn } from "@/lib/utils";
import type { PreviewColumn } from "../api/types";

interface DataPreviewTableProps {
  columns: PreviewColumn[];
  rows: Record<string, string | number | null>[];
  totalRowCount: number;
}

const BOLD_KEYS = new Set(["cost", "eventTotal", "totalCost"]);

export function DataPreviewTable({
  columns,
  rows,
  totalRowCount,
}: DataPreviewTableProps) {
  return (
    <div className="overflow-hidden rounded-xl border border-border">
      <div className="flex items-center justify-between border-b border-border px-3.5 py-2.5">
        <span className="text-[13px] font-medium">Data preview</span>
        <span className="text-[10px] text-muted-foreground">
          First {rows.length} of {totalRowCount.toLocaleString()} rows
        </span>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse whitespace-nowrap text-[10px]">
          <thead>
            <tr>
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "border-b border-border bg-accent/50 px-2 py-1.5 font-medium text-muted-foreground",
                    col.align === "right" ? "text-right" : "text-left",
                  )}
                >
                  {col.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row, i) => (
              <tr key={i} className="border-b border-border last:border-0">
                {columns.map((col) => {
                  const val = row[col.key];
                  const isNull = val === null || val === "\u2014";
                  const isBold = BOLD_KEYS.has(col.key);
                  return (
                    <td
                      key={col.key}
                      className={cn(
                        "px-2 py-1.5 font-mono",
                        col.align === "right" && "text-right",
                        isNull && "text-muted-foreground",
                        isBold && !isNull && "font-medium",
                      )}
                    >
                      {isNull ? "\u2014" : val}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="bg-accent/50 px-3.5 py-2 text-center text-[10px] text-muted-foreground">
        {Math.max(0, totalRowCount - rows.length).toLocaleString()} more rows
        match your filters
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 3: Ready to commit**

Suggested: `feat(export): add DataPreviewTable component`

---

### Task 9: DownloadBar Component

**Files:**
- Create: `src/features/export/components/download-bar.tsx`

**Context:** Format toggle (CSV/JSON), granularity toggle (dimension/event), and download button with three states. Granularity changes are lifted to the parent page.

- [ ] **Step 1: Create download-bar.tsx**

```typescript
// src/features/export/components/download-bar.tsx
import { useState, useEffect } from "react";
import { cn } from "@/lib/utils";
import type { ExportFormat, ExportGranularity } from "../api/types";

interface DownloadBarProps {
  format: ExportFormat;
  onFormatChange: (f: ExportFormat) => void;
  granularity: ExportGranularity;
  onGranularityChange: (g: ExportGranularity) => void;
  onDownload: () => void;
  isGenerating: boolean;
  isSuccess: boolean;
}

function SegmentedToggle<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: { key: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
}) {
  return (
    <div>
      <div className="mb-1 text-xs font-medium">{label}</div>
      <div className="flex">
        {options.map((opt, i) => (
          <button
            key={opt.key}
            className={cn(
              "border px-3 py-1.5 text-[11px]",
              i === 0 && "rounded-l-lg",
              i === options.length - 1 && "rounded-r-lg border-l-0",
              i > 0 && i < options.length - 1 && "border-l-0",
              value === opt.key
                ? "border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
            onClick={() => onChange(opt.key)}
          >
            {opt.label}
          </button>
        ))}
      </div>
    </div>
  );
}

export function DownloadBar({
  format,
  onFormatChange,
  granularity,
  onGranularityChange,
  onDownload,
  isGenerating,
  isSuccess,
}: DownloadBarProps) {
  const [showReady, setShowReady] = useState(false);

  useEffect(() => {
    if (isSuccess) {
      setShowReady(true);
      const timer = setTimeout(() => setShowReady(false), 2500);
      return () => clearTimeout(timer);
    }
  }, [isSuccess]);

  return (
    <div>
      <div className="flex items-center justify-between gap-3 rounded-xl border border-border px-4 py-3.5">
        <div className="flex gap-3">
          <SegmentedToggle
            label="Format"
            options={[
              { key: "csv" as ExportFormat, label: "CSV" },
              { key: "json" as ExportFormat, label: "JSON" },
            ]}
            value={format}
            onChange={onFormatChange}
          />
          <SegmentedToggle
            label="Granularity"
            options={[
              { key: "dimension" as ExportGranularity, label: "By dimension" },
              { key: "event" as ExportGranularity, label: "By event" },
            ]}
            value={granularity}
            onChange={onGranularityChange}
          />
        </div>
        <button
          className={cn(
            "rounded-lg px-6 py-2.5 text-[13px] font-medium text-background",
            showReady
              ? "bg-green-600"
              : "bg-foreground hover:opacity-90",
            isGenerating && "opacity-60",
          )}
          onClick={onDownload}
          disabled={isGenerating}
        >
          {isGenerating
            ? "Generating..."
            : showReady
              ? "Download ready"
              : "Download export"}
        </button>
      </div>
      <p className="mt-2 text-center text-[10px] text-muted-foreground">
        Export generates server-side. Large files may take up to 30 seconds.
      </p>
    </div>
  );
}
```

- [ ] **Step 2: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 3: Ready to commit**

Suggested: `feat(export): add DownloadBar component`

---

### Task 10: ExportPage + Route Update

**Files:**
- Create: `src/features/export/components/export-page.tsx`
- Modify: `src/app/routes/_app/export/index.tsx`

**Context:** The orchestrator component. Manages all filter state, debounces filter changes, composes all child components. The route file is a thin delegate.

- [ ] **Step 1: Create export-page.tsx**

```typescript
// src/features/export/components/export-page.tsx
import { useState, useMemo, useEffect } from "react";
import { Link } from "@tanstack/react-router";
import { ArrowLeft } from "lucide-react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useExportFilterOptions, useExportPreview } from "../api/queries";
import { useGenerateExport } from "../api/mutations";
import type { DatePreset, ExportFilters, ExportFormat, ExportGranularity } from "../api/types";
import { ExportFilters as ExportFiltersPanel } from "./export-filters";
import { ExportEstimate } from "./export-estimate";
import { DataPreviewTable } from "./data-preview-table";
import { DownloadBar } from "./download-bar";

function getPresetDates(preset: DatePreset): { from: string; to: string } {
  const to = new Date();
  const toStr = to.toISOString().split("T")[0];
  if (preset === "all") return { from: "2026-01-12", to: toStr };
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const from = new Date(to);
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().split("T")[0], to: toStr };
}

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  const serialized = JSON.stringify(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [serialized, delayMs]);
  return debounced;
}

export function ExportPage() {
  const { data: filterOptions, isLoading: optionsLoading } =
    useExportFilterOptions();

  const defaultDates = getPresetDates("30d");
  const [dateFrom, setDateFrom] = useState(defaultDates.from);
  const [dateTo, setDateTo] = useState(defaultDates.to);
  const [datePreset, setDatePreset] = useState<DatePreset | null>("30d");
  const [selectedCustomerIds, setSelectedCustomerIds] = useState<string[]>([]);
  const [selectedProductKeys, setSelectedProductKeys] = useState<string[]>([]);
  const [selectedCardKeys, setSelectedCardKeys] = useState<string[]>([]);
  const [granularity, setGranularity] = useState<ExportGranularity>("dimension");
  const [format, setFormat] = useState<ExportFormat>("csv");

  const filters = useMemo<ExportFilters>(
    () => ({
      dateFrom,
      dateTo,
      customerIds: selectedCustomerIds,
      productKeys: selectedProductKeys,
      cardKeys: selectedCardKeys,
      granularity,
    }),
    [dateFrom, dateTo, selectedCustomerIds, selectedProductKeys, selectedCardKeys, granularity],
  );

  const debouncedFilters = useDebouncedValue(filters, 300);
  const { data: preview } = useExportPreview(
    filterOptions ? debouncedFilters : null,
  );
  const exportMutation = useGenerateExport();

  function handleDatePreset(preset: DatePreset) {
    const dates = getPresetDates(preset);
    setDateFrom(dates.from);
    setDateTo(dates.to);
    setDatePreset(preset);
  }

  function handleDateFromChange(value: string) {
    setDateFrom(value);
    setDatePreset(null);
  }

  function handleDateToChange(value: string) {
    setDateTo(value);
    setDatePreset(null);
  }

  function handleDownload() {
    exportMutation.mutate({ ...filters, format } as ExportFilters & { format: ExportFormat });
  }

  if (optionsLoading || !filterOptions) {
    return (
      <div className="space-y-4">
        <PageHeader title="Export raw data" />
        <Skeleton className="h-64 rounded-xl" />
        <Skeleton className="h-20 rounded-xl" />
        <Skeleton className="h-48 rounded-xl" />
        <Skeleton className="h-16 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      <Link
        to="/"
        className="inline-flex items-center gap-1 text-xs text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" />
        Back to dashboard
      </Link>

      <PageHeader
        title="Export raw data"
        description="Download event-level data as a file. Filters narrow your export — the preview and estimate update live as you go."
      />

      <ExportFiltersPanel
        filterOptions={filterOptions}
        dateFrom={dateFrom}
        dateTo={dateTo}
        datePreset={datePreset}
        onDateFromChange={handleDateFromChange}
        onDateToChange={handleDateToChange}
        onDatePreset={handleDatePreset}
        selectedCustomerIds={selectedCustomerIds}
        onCustomerSelectionChange={setSelectedCustomerIds}
        selectedProductKeys={selectedProductKeys}
        onProductSelectionChange={setSelectedProductKeys}
        selectedCardKeys={selectedCardKeys}
        onCardSelectionChange={setSelectedCardKeys}
      />

      {preview && (
        <>
          <ExportEstimate
            estimate={preview.estimate}
            filterOptions={filterOptions}
            selectedCustomerIds={selectedCustomerIds}
            selectedProductKeys={selectedProductKeys}
            selectedCardKeys={selectedCardKeys}
            dateFrom={dateFrom}
            dateTo={dateTo}
          />

          <DataPreviewTable
            columns={preview.columns}
            rows={preview.rows}
            totalRowCount={preview.estimate.rowCount}
          />
        </>
      )}

      <DownloadBar
        format={format}
        onFormatChange={setFormat}
        granularity={granularity}
        onGranularityChange={setGranularity}
        onDownload={handleDownload}
        isGenerating={exportMutation.isPending}
        isSuccess={exportMutation.isSuccess}
      />
    </div>
  );
}
```

- [ ] **Step 2: Update route file**

Replace the contents of `src/app/routes/_app/export/index.tsx`:

```typescript
import { createFileRoute } from "@tanstack/react-router";
import { ExportPage } from "@/features/export/components/export-page";

export const Route = createFileRoute("/_app/export/")({
  component: ExportPage,
});
```

- [ ] **Step 3: Verify no type errors**

Run: `pnpm tsc --noEmit`

- [ ] **Step 4: Verify in browser**

Run: `pnpm dev`

1. Navigate to `/export` — should see full page with filters, estimate, preview, download bar
2. Click date presets — estimate + preview should update
3. Open customer dropdown — search and select customers, verify chips appear
4. Click product/card pills — verify estimate updates
5. Toggle granularity — preview table columns should swap between dimension and event modes
6. Toggle format — CSV/JSON segmented toggle should highlight
7. Click "Download export" — should show "Generating..." then "Download ready" (green)
8. Verify "Back to dashboard" link works
9. Verify large export warning appears when selecting "All time" (should exceed 500k rows)

- [ ] **Step 5: Ready to commit**

Suggested: `feat(export): add ExportPage orchestrator and wire route`

---

## Post-Implementation

After all tasks are complete:

- [ ] Update `PROGRESS.md`:
  - Change Phase 8 status from "Not started" to "Complete"
  - Add Phase 8 checklist items (all checked)
  - Update "Current Status" to point to next phase
  - Add session log entry

- [ ] Suggested commit for PROGRESS.md: `docs: mark phase 8 data export complete`
