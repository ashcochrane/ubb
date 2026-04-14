# Phase 6: Reconciliation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit. The user handles all git operations.
>
> **Design source of truth:** `docs/design/files/unified_reconciliation_v3.html`
> **Design rationale:** `docs/design/ui-flow-design-rationale.md` section 3

**Goal:** Build the pricing card reconciliation page — dual timeline, version editing (edit prices, adjust boundaries, insert period), adjustments with 4 distribution modes, reconciliation summary, and audit trail.

**Architecture:** Feature module at `src/features/reconciliation/`. The page is accessed via `/pricing-cards/:cardId` — clicking a card from the list opens its reconciliation view. The page is composed of distinct zones (timeline, version detail, editing panels, adjustments, summary, audit trail) that share state via a Zustand store for the currently selected version and open panels. Mock data includes 3 versions (v1, v2, v3) with a retroactive insert (v2b) for demonstration.

**Tech Stack:** React 19, TypeScript, Zustand (page-level store for selection state), TanStack Query, TanStack Router (dynamic route param), Lucide icons

---

## File Map

### API Layer

| File | Responsibility |
|------|---------------|
| `src/features/reconciliation/api/types.ts` | Version, timeline, adjustment, audit types |
| `src/features/reconciliation/api/mock-data.ts` | Mock card with 4 versions, adjustments, audit entries |
| `src/features/reconciliation/api/mock.ts` | Mock adapter with mutation handlers |
| `src/features/reconciliation/api/api.ts` | Real API adapter (placeholder) |
| `src/features/reconciliation/api/provider.ts` | selectProvider |
| `src/features/reconciliation/api/queries.ts` | TanStack Query hooks |

### Components

| File | Responsibility |
|------|---------------|
| `src/features/reconciliation/components/reconciliation-page.tsx` | Page container, data fetching, layout |
| `src/features/reconciliation/components/card-header.tsx` | Back link, card name, provider, status, stats grid |
| `src/features/reconciliation/components/timeline.tsx` | Dual-track timeline (original vs reconciled) with clickable segments |
| `src/features/reconciliation/components/version-detail.tsx` | Selected version info: date range, events, cost, dimension pricing table |
| `src/features/reconciliation/components/edit-prices-panel.tsx` | Panel: current → new price inputs per dimension, reason, apply |
| `src/features/reconciliation/components/adjust-boundary-panel.tsx` | Panel: boundary date/time picker, before/after card, reason, apply |
| `src/features/reconciliation/components/insert-period-panel.tsx` | Panel: split version, date, new prices, reason, apply |
| `src/features/reconciliation/components/adjustments-section.tsx` | Adjustment form: type selector, amount, product, distribution mode |
| `src/features/reconciliation/components/distribution-preview.tsx` | Bar chart preview for all 4 distribution modes |
| `src/features/reconciliation/components/reconciliation-summary.tsx` | Summary bar: original (strikethrough), reconciled, net delta |
| `src/features/reconciliation/components/audit-trail.tsx` | Chronological action log with type tags and deltas |

### Store

| File | Responsibility |
|------|---------------|
| `src/features/reconciliation/stores/reconciliation-store.ts` | Zustand: selected version, open panel, adjustment form state |

### Route

| File | Responsibility |
|------|---------------|
| `src/app/routes/_app/pricing-cards/$cardId.tsx` | Dynamic route for reconciliation |

### Existing File Modifications

| File | Change |
|------|--------|
| `src/features/pricing-cards/components/pricing-card-item.tsx` | Make card clickable (Link to `/pricing-cards/:cardId`) |

---

## Task 1: Types + Mock Data + API Layer

**Files:**
- Create: `src/features/reconciliation/api/types.ts`
- Create: `src/features/reconciliation/api/mock-data.ts`
- Create: `src/features/reconciliation/api/mock.ts`
- Create: `src/features/reconciliation/api/api.ts`
- Create: `src/features/reconciliation/api/provider.ts`
- Create: `src/features/reconciliation/api/queries.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/reconciliation/api/types.ts

export type VersionStatus = "active" | "superseded" | "retroactive";
export type AdjustmentType = "credit_refund" | "missing_costs";
export type DistributionMode = "lump_sum" | "even_daily" | "proportional" | "manual";
export type AuditEntryType = "period_insert" | "boundary_shift" | "price_edit" | "credit_recorded";

export interface DimensionPrice {
  key: string;
  type: "per_unit" | "flat";
  unitPrice: number;
  displayPrice: string;
}

export interface PricingVersion {
  id: string;
  label: string;
  status: VersionStatus;
  startDate: string;
  endDate: string | null;
  durationDays: number;
  eventCount: number;
  cost: number;
  dimensions: DimensionPrice[];
}

export interface TimelineSegment {
  id: string;
  versionId: string;
  label: string;
  cost: number;
  flex: number;
  color: string;
}

export interface TimelineData {
  originalTrack: TimelineSegment[];
  reconciledTrack: TimelineSegment[];
  originalTotal: number;
  reconciledTotal: number;
  adjustmentTotal: number;
  dateMarkers: string[];
}

export interface AuditEntry {
  id: string;
  type: AuditEntryType;
  title: string;
  description: string;
  metadata: string;
  delta: number;
  deltaLabel: string;
}

export interface Adjustment {
  id: string;
  type: AdjustmentType;
  amount: number;
  product: string | null;
  distributionMode: DistributionMode;
  reason: string;
  evidence: string | null;
  date: string;
}

export interface ReconciliationData {
  card: {
    id: string;
    name: string;
    provider: string;
    cardId: string;
    status: "active" | "inactive";
  };
  stats: {
    originalTracked: number;
    reconciledTotal: number;
    netAdjustments: number;
    adjustmentCount: number;
    eventCount: number;
    currentVersion: string;
    since: string;
  };
  versions: PricingVersion[];
  timeline: TimelineData;
  adjustments: Adjustment[];
  auditTrail: AuditEntry[];
}

export interface EditPricesRequest {
  versionId: string;
  newPrices: Record<string, number>;
  reason: string;
}

export interface AdjustBoundaryRequest {
  fromVersionId: string;
  toVersionId: string;
  newBoundaryDate: string;
  newBoundaryTime: string;
  reason: string;
}

export interface InsertPeriodRequest {
  versionId: string;
  splitDate: string;
  splitTime: string;
  newPrices: Record<string, number>;
  reason: string;
}

export interface RecordAdjustmentRequest {
  type: AdjustmentType;
  amount: number;
  product: string | null;
  distributionMode: DistributionMode;
  distributionConfig: Record<string, unknown>;
  reason: string;
  evidence: string | null;
}
```

- [ ] **Step 2: Create mock-data.ts**

```typescript
// src/features/reconciliation/api/mock-data.ts
import type { ReconciliationData } from "./types";

export const mockReconciliationData: ReconciliationData = {
  card: {
    id: "pc-001",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    cardId: "gemini_2_flash",
    status: "active",
  },
  stats: {
    originalTracked: 2386,
    reconciledTotal: 2418,
    netAdjustments: 32,
    adjustmentCount: 3,
    eventCount: 186000,
    currentVersion: "v3",
    since: "12 Jan 2026",
  },
  versions: [
    {
      id: "v1",
      label: "v1",
      status: "superseded",
      startDate: "2026-01-12",
      endDate: "2026-02-03",
      durationDays: 22,
      eventCount: 42150,
      cost: 387,
      dimensions: [
        { key: "input_tokens", type: "per_unit", unitPrice: 0.0000001, displayPrice: "$0.10 / 1M" },
        { key: "output_tokens", type: "per_unit", unitPrice: 0.0000004, displayPrice: "$0.40 / 1M" },
        { key: "grounding_requests", type: "flat", unitPrice: 0.035, displayPrice: "$0.035 / req" },
      ],
    },
    {
      id: "v2",
      label: "v2",
      status: "superseded",
      startDate: "2026-02-03",
      endDate: "2026-02-20",
      durationDays: 17,
      eventCount: 38200,
      cost: 449,
      dimensions: [
        { key: "input_tokens", type: "per_unit", unitPrice: 0.00000015, displayPrice: "$0.15 / 1M" },
        { key: "output_tokens", type: "per_unit", unitPrice: 0.0000006, displayPrice: "$0.60 / 1M" },
        { key: "grounding_requests", type: "flat", unitPrice: 0.035, displayPrice: "$0.035 / req" },
      ],
    },
    {
      id: "v2b",
      label: "v2b",
      status: "retroactive",
      startDate: "2026-02-20",
      endDate: "2026-03-18",
      durationDays: 26,
      eventCount: 61294,
      cost: 781,
      dimensions: [
        { key: "input_tokens", type: "per_unit", unitPrice: 0.0000002, displayPrice: "$0.20 / 1M" },
        { key: "output_tokens", type: "per_unit", unitPrice: 0.0000008, displayPrice: "$0.80 / 1M" },
        { key: "grounding_requests", type: "flat", unitPrice: 0.035, displayPrice: "$0.035 / req" },
      ],
    },
    {
      id: "v3",
      label: "v3",
      status: "active",
      startDate: "2026-03-18",
      endDate: null,
      durationDays: 2,
      eventCount: 44356,
      cost: 835,
      dimensions: [
        { key: "input_tokens", type: "per_unit", unitPrice: 0.0000002, displayPrice: "$0.20 / 1M" },
        { key: "output_tokens", type: "per_unit", unitPrice: 0.0000008, displayPrice: "$0.80 / 1M" },
        { key: "grounding_requests", type: "flat", unitPrice: 0.04, displayPrice: "$0.04 / req" },
      ],
    },
  ],
  timeline: {
    originalTrack: [
      { id: "orig-v1", versionId: "v1", label: "v1", cost: 387, flex: 3, color: "#F1EFE8" },
      { id: "orig-v2", versionId: "v2", label: "v2", cost: 1166, flex: 4, color: "#F1EFE8" },
      { id: "orig-v3", versionId: "v3", label: "v3", cost: 835, flex: 1.5, color: "#F1EFE8" },
    ],
    reconciledTrack: [
      { id: "rec-v1", versionId: "v1", label: "v1", cost: 387, flex: 3, color: "#D3D1C7" },
      { id: "rec-v2", versionId: "v2", label: "v2", cost: 449, flex: 2.5, color: "#D3D1C7" },
      { id: "rec-v2b", versionId: "v2b", label: "v2b", cost: 781, flex: 1.5, color: "#85B7EB" },
      { id: "rec-v3", versionId: "v3", label: "v3", cost: 835, flex: 1.5, color: "#5DCAA5" },
    ],
    originalTotal: 2386,
    reconciledTotal: 2418,
    adjustmentTotal: 32.40,
    dateMarkers: ["12 Jan 2026", "3 Feb", "20 Feb", "18 Mar", "Today"],
  },
  adjustments: [
    {
      id: "adj-1",
      type: "credit_refund",
      amount: -12.80,
      product: "property_search",
      distributionMode: "lump_sum",
      reason: "Google Cloud service disruption credit.",
      evidence: "https://support.google.com/ticket/12345",
      date: "2026-03-10",
    },
  ],
  auditTrail: [
    {
      id: "log-1",
      type: "period_insert",
      title: "Inserted v2b: 20 Feb — 18 Mar",
      description: "input_tokens $0.15→$0.20/1M. Google price increase.",
      metadata: "61,294 events recalculated. 20 Mar by j.smith@co",
      delta: 38.39,
      deltaLabel: "net delta",
    },
    {
      id: "log-2",
      type: "boundary_shift",
      title: "v1/v2 boundary: 3 Feb → 5 Feb",
      description: "Corrected to actual pricing effective date.",
      metadata: "4,102 events reassigned. 19 Mar by j.smith@co",
      delta: 6.81,
      deltaLabel: "net delta",
    },
    {
      id: "log-3",
      type: "credit_recorded",
      title: "Provider credit — 10 Mar (lump sum)",
      description: "Google Cloud service disruption credit.",
      metadata: "15 Mar by j.smith@co",
      delta: -12.80,
      deltaLabel: "credit",
    },
  ],
};
```

- [ ] **Step 3: Create mock.ts, api.ts, provider.ts, queries.ts**

```typescript
// src/features/reconciliation/api/mock.ts
import type {
  ReconciliationData,
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";
import { mockReconciliationData } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

export async function getReconciliation(_cardId: string): Promise<ReconciliationData> {
  await delay();
  return structuredClone(mockReconciliationData);
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function editPrices(_req: EditPricesRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function adjustBoundary(_req: AdjustBoundaryRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function insertPeriod(_req: InsertPeriodRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function recordAdjustment(_req: RecordAdjustmentRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}
```

```typescript
// src/features/reconciliation/api/api.ts
import type {
  ReconciliationData,
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";
import { meteringApi } from "@/api/client";

export async function getReconciliation(cardId: string): Promise<ReconciliationData> {
  const { data } = await meteringApi.GET("/rate-cards/{cardId}/reconciliation", { params: { path: { cardId } } });
  return data as ReconciliationData;
}

export async function editPrices(req: EditPricesRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/edit-prices", { body: req });
  return data as { success: boolean };
}

export async function adjustBoundary(req: AdjustBoundaryRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/adjust-boundary", { body: req });
  return data as { success: boolean };
}

export async function insertPeriod(req: InsertPeriodRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/insert-period", { body: req });
  return data as { success: boolean };
}

export async function recordAdjustment(req: RecordAdjustmentRequest): Promise<{ success: boolean }> {
  const { data } = await meteringApi.POST("/rate-cards/reconciliation/record-adjustment", { body: req });
  return data as { success: boolean };
}
```

```typescript
// src/features/reconciliation/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const reconciliationApi = selectProvider({ mock, api });
```

```typescript
// src/features/reconciliation/api/queries.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { reconciliationApi } from "./provider";
import type {
  EditPricesRequest,
  AdjustBoundaryRequest,
  InsertPeriodRequest,
  RecordAdjustmentRequest,
} from "./types";

export function useReconciliation(cardId: string) {
  return useQuery({
    queryKey: ["reconciliation", cardId],
    queryFn: () => reconciliationApi.getReconciliation(cardId),
    enabled: !!cardId,
  });
}

function useInvalidateReconciliation(cardId: string) {
  const queryClient = useQueryClient();
  return () => queryClient.invalidateQueries({ queryKey: ["reconciliation", cardId] });
}

export function useEditPrices(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({ mutationFn: (req: EditPricesRequest) => reconciliationApi.editPrices(req), onSuccess: invalidate });
}

export function useAdjustBoundary(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({ mutationFn: (req: AdjustBoundaryRequest) => reconciliationApi.adjustBoundary(req), onSuccess: invalidate });
}

export function useInsertPeriod(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({ mutationFn: (req: InsertPeriodRequest) => reconciliationApi.insertPeriod(req), onSuccess: invalidate });
}

export function useRecordAdjustment(cardId: string) {
  const invalidate = useInvalidateReconciliation(cardId);
  return useMutation({ mutationFn: (req: RecordAdjustmentRequest) => reconciliationApi.recordAdjustment(req), onSuccess: invalidate });
}
```

- [ ] **Step 4: Verify build**

Run: `pnpm build`

---

## Task 2: Store + Card Header + Stats

**Files:**
- Create: `src/features/reconciliation/stores/reconciliation-store.ts`
- Create: `src/features/reconciliation/components/card-header.tsx`

- [ ] **Step 1: Create reconciliation-store.ts**

Page-level state: which version is selected, which panel is open.

```typescript
// src/features/reconciliation/stores/reconciliation-store.ts
import { create } from "zustand";

type PanelType = "edit-prices" | "adjust-boundary" | "insert-period" | "adjustments" | null;

interface ReconciliationStore {
  selectedVersionId: string | null;
  openPanel: PanelType;
  selectVersion: (id: string) => void;
  openPanelFor: (panel: PanelType) => void;
  closePanel: () => void;
}

export const useReconciliationStore = create<ReconciliationStore>((set) => ({
  selectedVersionId: null,
  openPanel: null,
  selectVersion: (id) => set({ selectedVersionId: id, openPanel: null }),
  openPanelFor: (panel) => set({ openPanel: panel }),
  closePanel: () => set({ openPanel: null }),
}));
```

- [ ] **Step 2: Create card-header.tsx**

Back link, card name/provider/status, 4-stat grid.

```typescript
// src/features/reconciliation/components/card-header.tsx
import { ArrowLeft } from "lucide-react";
import { Link } from "@tanstack/react-router";
import type { ReconciliationData } from "../api/types";
import { cn } from "@/lib/utils";

interface CardHeaderProps {
  data: ReconciliationData;
}

export function CardHeader({ data }: CardHeaderProps) {
  const { card, stats } = data;

  return (
    <div className="space-y-4">
      <Link
        to="/pricing-cards"
        className="inline-flex items-center gap-1 text-[12px] text-muted-foreground hover:text-foreground"
      >
        <ArrowLeft className="h-3 w-3" /> Back to all cards
      </Link>

      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-[22px] font-bold">{card.name}</h1>
          <div className="text-[13px] text-muted-foreground">
            {card.provider}{" "}
            <code className="rounded bg-muted px-1.5 py-0.5 font-mono text-[11px]">{card.cardId}</code>
          </div>
        </div>
        <span
          className={cn(
            "rounded-full px-2.5 py-0.5 text-[10px] font-semibold",
            card.status === "active"
              ? "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400"
              : "bg-muted text-muted-foreground",
          )}
        >
          {card.status === "active" ? "Active" : "Inactive"}
        </span>
      </div>

      <div className="grid grid-cols-4 gap-2.5">
        <StatCard label="Originally tracked" value={`$${stats.originalTracked.toLocaleString()}`} sub="Raw event costs" />
        <StatCard label="Reconciled total" value={`$${stats.reconciledTotal.toLocaleString()}`} sub="After adjustments" />
        <StatCard
          label="Net adjustments"
          value={`${stats.netAdjustments >= 0 ? "+" : ""}$${stats.netAdjustments}`}
          sub={`${stats.adjustmentCount} adjustments applied`}
          valueColor={stats.netAdjustments > 0 ? "text-[#A32D2D]" : "text-[#3B6D11]"}
        />
        <StatCard
          label="Events / versions"
          value={`${(stats.eventCount / 1000).toFixed(0)}k / ${stats.currentVersion}`}
          sub={`Since ${stats.since}`}
        />
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, valueColor }: {
  label: string;
  value: string;
  sub: string;
  valueColor?: string;
}) {
  return (
    <div className="rounded-lg bg-accent/50 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={cn("mt-1 text-[17px] font-semibold", valueColor)}>{value}</div>
      <div className="mt-0.5 text-[10px] text-muted-foreground">{sub}</div>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 3: Timeline Visualization

**Files:**
- Create: `src/features/reconciliation/components/timeline.tsx`

- [ ] **Step 1: Create timeline.tsx**

Dual-track timeline: "As originally tracked" and "Reconciled timeline" with clickable segments, date markers, and adjustment connector.

```typescript
// src/features/reconciliation/components/timeline.tsx
import type { TimelineData, TimelineSegment } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { cn } from "@/lib/utils";

interface TimelineProps {
  timeline: TimelineData;
}

export function Timeline({ timeline }: TimelineProps) {
  const { selectedVersionId, selectVersion } = useReconciliationStore();

  return (
    <div className="space-y-2">
      {/* Legend */}
      <div className="flex gap-4 text-[10px] text-muted-foreground">
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#5DCAA5" }} /> Active
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#D3D1C7" }} /> Superseded
        </span>
        <span className="flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm" style={{ backgroundColor: "#85B7EB" }} /> Retroactive
        </span>
      </div>

      {/* Original track */}
      <div>
        <div className="mb-1 text-[11px] text-muted-foreground">
          As originally tracked: <span className="font-mono font-medium">${timeline.originalTotal.toLocaleString()}</span>
        </div>
        <TrackBar
          segments={timeline.originalTrack}
          selectedVersionId={selectedVersionId}
          onSelect={selectVersion}
          dashed
        />
      </div>

      {/* Connector */}
      <div className="flex items-center gap-2 px-2">
        <div className="h-px flex-1 border-t border-dashed border-border" />
        <span className="text-[10px] text-muted-foreground">
          {timeline.adjustmentTotal >= 0 ? "+" : ""}${timeline.adjustmentTotal.toFixed(2)} adjustments
        </span>
        <div className="h-px flex-1 border-t border-dashed border-border" />
      </div>

      {/* Reconciled track */}
      <div>
        <div className="mb-1 text-[11px] text-muted-foreground">
          Reconciled timeline: <span className="font-mono font-medium">${timeline.reconciledTotal.toLocaleString()}</span>
        </div>
        <TrackBar
          segments={timeline.reconciledTrack}
          selectedVersionId={selectedVersionId}
          onSelect={selectVersion}
        />
      </div>

      {/* Date markers */}
      <div className="flex justify-between px-1 text-[9px] text-muted-foreground">
        {timeline.dateMarkers.map((d) => (
          <span key={d}>{d}</span>
        ))}
      </div>
    </div>
  );
}

function TrackBar({
  segments,
  selectedVersionId,
  onSelect,
  dashed,
}: {
  segments: TimelineSegment[];
  selectedVersionId: string | null;
  onSelect: (id: string) => void;
  dashed?: boolean;
}) {
  return (
    <div className="flex gap-0.5">
      {segments.map((seg) => {
        const isSelected = selectedVersionId === seg.versionId;
        return (
          <button
            key={seg.id}
            type="button"
            onClick={() => onSelect(seg.versionId)}
            className={cn(
              "flex h-9 items-center justify-center rounded-md px-2 text-[11px] font-medium transition-all",
              dashed && "border border-dashed",
              !dashed && "border",
              isSelected && "outline outline-2 outline-offset-1 outline-foreground",
            )}
            style={{
              flex: seg.flex,
              backgroundColor: seg.color,
              borderColor: dashed ? "rgba(0,0,0,0.15)" : "transparent",
              color: seg.color === "#F1EFE8" ? "#888780" : "#1a1a1a",
            }}
          >
            <span className="mr-1 text-[10px] opacity-70">{seg.label}</span>
            <span className="font-mono text-[10px]">${seg.cost}</span>
          </button>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 4: Version Detail Card

**Files:**
- Create: `src/features/reconciliation/components/version-detail.tsx`

- [ ] **Step 1: Create version-detail.tsx**

Shows selected version info: status pill, date range, event count, cost, dimension pricing table, and action buttons.

```typescript
// src/features/reconciliation/components/version-detail.tsx
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { cn } from "@/lib/utils";

interface VersionDetailProps {
  version: PricingVersion;
}

const statusColors: Record<string, string> = {
  active: "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
  superseded: "bg-muted text-muted-foreground",
  retroactive: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
};

export function VersionDetail({ version }: VersionDetailProps) {
  const { openPanelFor } = useReconciliationStore();

  const endLabel = version.endDate
    ? new Date(version.endDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" })
    : "Today";
  const startLabel = new Date(version.startDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" });

  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="text-[14px] font-semibold">{version.label}</span>
          <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-medium", statusColors[version.status])}>
            {version.status}
          </span>
        </div>
      </div>

      <div className="mt-1 text-[11px] text-muted-foreground">
        {startLabel} — {endLabel} ({version.durationDays} days)
      </div>

      <div className="mt-1 flex gap-4 text-[11px]">
        <span>Events: <span className="font-mono font-medium">{version.eventCount.toLocaleString()}</span></span>
        <span>Cost: <span className="font-mono font-medium">${version.cost.toLocaleString()}</span></span>
      </div>

      {/* Dimension pricing table */}
      <div className="mt-3 rounded-lg border border-border">
        <table className="w-full text-[11px]">
          <thead>
            <tr className="border-b border-border">
              <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Dimension</th>
              <th className="px-3 py-1.5 text-left font-medium text-muted-foreground">Type</th>
              <th className="px-3 py-1.5 text-right font-medium text-muted-foreground">Unit price</th>
              <th className="px-3 py-1.5 text-right font-medium text-muted-foreground">Display</th>
            </tr>
          </thead>
          <tbody>
            {version.dimensions.map((d) => (
              <tr key={d.key} className="border-b border-border/50 last:border-0">
                <td className="px-3 py-1.5 font-mono">{d.key}</td>
                <td className="px-3 py-1.5">
                  <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">{d.type === "per_unit" ? "per unit" : "flat"}</span>
                </td>
                <td className="px-3 py-1.5 text-right font-mono">${d.unitPrice.toFixed(10)}</td>
                <td className="px-3 py-1.5 text-right font-mono">{d.displayPrice}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Action buttons */}
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          onClick={() => openPanelFor("edit-prices")}
          className="rounded-md bg-amber-50 px-3 py-1.5 text-[11px] font-medium text-amber-700 hover:opacity-90 dark:bg-amber-900/20 dark:text-amber-400"
        >
          Edit prices
        </button>
        <button
          type="button"
          onClick={() => openPanelFor("adjust-boundary")}
          className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent"
        >
          Adjust boundaries
        </button>
        {version.status !== "active" && (
          <button
            type="button"
            onClick={() => openPanelFor("insert-period")}
            className="rounded-md bg-blue-50 px-3 py-1.5 text-[11px] font-medium text-blue-700 hover:opacity-90 dark:bg-blue-900/20 dark:text-blue-400"
          >
            Split this period
          </button>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 5: Version Editing Panels (Edit Prices, Adjust Boundary, Insert Period)

**Files:**
- Create: `src/features/reconciliation/components/edit-prices-panel.tsx`
- Create: `src/features/reconciliation/components/adjust-boundary-panel.tsx`
- Create: `src/features/reconciliation/components/insert-period-panel.tsx`

- [ ] **Step 1: Create edit-prices-panel.tsx**

Panel showing current → new price inputs for each dimension, reason textarea, apply button.

```typescript
// src/features/reconciliation/components/edit-prices-panel.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface EditPricesPanelProps {
  version: PricingVersion;
  onApply: (newPrices: Record<string, number>, reason: string) => Promise<void>;
}

export function EditPricesPanel({ version, onApply }: EditPricesPanelProps) {
  const { closePanel } = useReconciliationStore();
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of version.dimensions) {
      init[d.key] = "";
    }
    return init;
  });
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApply = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const newPrices: Record<string, number> = {};
      for (const d of version.dimensions) {
        const val = prices[d.key];
        newPrices[d.key] = val ? parseFloat(val) : d.unitPrice;
      }
      await onApply(newPrices, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to apply correction.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50/50 px-4 py-4 dark:border-amber-800 dark:bg-amber-900/10">
      <h3 className="text-[13px] font-semibold">Edit prices for {version.label}</h3>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        All events in this period will be recalculated at the corrected prices.
      </p>

      <div className="mt-3 space-y-2">
        {version.dimensions.map((d) => (
          <div key={d.key} className="grid grid-cols-[110px_1fr_16px_1fr] items-center gap-2">
            <span className="font-mono text-[11px]">{d.key}</span>
            <span className="text-right font-mono text-[11px] text-muted-foreground">${d.unitPrice.toFixed(10)}</span>
            <span className="text-center text-[11px] text-muted-foreground">→</span>
            <div className="relative">
              <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">$</span>
              <input
                type="number"
                step="any"
                value={prices[d.key]}
                onChange={(e) => setPrices((p) => ({ ...p, [d.key]: e.target.value }))}
                placeholder={d.unitPrice.toFixed(10)}
                className="w-full rounded border border-border bg-background py-1 pl-5 pr-2 font-mono text-[11px] outline-none focus:border-muted-foreground"
              />
            </div>
          </div>
        ))}
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-[10px] font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Google increased input token pricing effective 10 Feb."
          className="min-h-[48px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[11px] outline-none focus:border-muted-foreground"
        />
      </div>

      {error && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!reason.trim() || loading}
          className="rounded-md bg-amber-600 px-3 py-1.5 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply correction"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create adjust-boundary-panel.tsx**

```typescript
// src/features/reconciliation/components/adjust-boundary-panel.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface AdjustBoundaryPanelProps {
  version: PricingVersion;
  nextVersion?: PricingVersion;
  onApply: (newDate: string, newTime: string, reason: string) => Promise<void>;
}

export function AdjustBoundaryPanel({ version, nextVersion, onApply }: AdjustBoundaryPanelProps) {
  const { closePanel } = useReconciliationStore();
  const [date, setDate] = useState(version.endDate ?? "");
  const [time, setTime] = useState("00:00");
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApply = async () => {
    if (!reason.trim() || !date) return;
    setLoading(true);
    setError(null);
    try {
      await onApply(date, time, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to adjust boundary.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-border px-4 py-4">
      <h3 className="text-[13px] font-semibold">Adjust version boundary</h3>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Move the boundary between two adjacent versions. Events crossing the new boundary will be repriced.
      </p>

      {/* Before/after visual */}
      <div className="mt-3 grid grid-cols-[1fr_auto_1fr] items-center gap-3">
        <div className="rounded-lg bg-accent/50 px-3 py-2 text-center">
          <div className="text-[11px] font-medium">{version.label}</div>
          <div className="text-[10px] text-muted-foreground">ends</div>
        </div>
        <div className="h-8 w-px bg-border" />
        <div className="rounded-lg bg-accent/50 px-3 py-2 text-center">
          <div className="text-[11px] font-medium">{nextVersion?.label ?? "—"}</div>
          <div className="text-[10px] text-muted-foreground">starts</div>
        </div>
      </div>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-[10px] font-medium">Move boundary to</label>
          <input
            type="date"
            value={date}
            onChange={(e) => setDate(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-medium">Time (optional)</label>
          <input
            type="time"
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-[10px] font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Corrected to actual pricing effective date."
          className="min-h-[48px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[11px] outline-none focus:border-muted-foreground"
        />
      </div>

      {error && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!reason.trim() || !date || loading}
          className="rounded-md bg-foreground px-3 py-1.5 text-[11px] font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply boundary change"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Create insert-period-panel.tsx**

```typescript
// src/features/reconciliation/components/insert-period-panel.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { PricingVersion } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";

interface InsertPeriodPanelProps {
  version: PricingVersion;
  onApply: (splitDate: string, splitTime: string, newPrices: Record<string, number>, reason: string) => Promise<void>;
}

export function InsertPeriodPanel({ version, onApply }: InsertPeriodPanelProps) {
  const { closePanel } = useReconciliationStore();
  const [splitDate, setSplitDate] = useState("");
  const [splitTime, setSplitTime] = useState("00:00");
  const [prices, setPrices] = useState<Record<string, string>>(() => {
    const init: Record<string, string> = {};
    for (const d of version.dimensions) {
      init[d.key] = d.unitPrice.toString();
    }
    return init;
  });
  const [reason, setReason] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleApply = async () => {
    if (!reason.trim() || !splitDate) return;
    setLoading(true);
    setError(null);
    try {
      const newPrices: Record<string, number> = {};
      for (const d of version.dimensions) {
        newPrices[d.key] = parseFloat(prices[d.key]) || d.unitPrice;
      }
      await onApply(splitDate, splitTime, newPrices, reason);
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to insert period.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="rounded-xl border border-blue-200 bg-blue-50/50 px-4 py-4 dark:border-blue-800 dark:bg-blue-900/10">
      <h3 className="text-[13px] font-semibold">Insert a pricing period</h3>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        Split {version.label} at a date to apply different prices for part of its period.
      </p>

      <div className="mt-3 grid grid-cols-2 gap-3">
        <div>
          <label className="mb-1 block text-[10px] font-medium">Split at date</label>
          <input
            type="date"
            value={splitDate}
            onChange={(e) => setSplitDate(e.target.value)}
            min={version.startDate}
            max={version.endDate ?? undefined}
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
        <div>
          <label className="mb-1 block text-[10px] font-medium">Time</label>
          <input
            type="time"
            value={splitTime}
            onChange={(e) => setSplitTime(e.target.value)}
            className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
          />
        </div>
      </div>

      <div className="mt-3">
        <div className="mb-2 text-[11px] font-medium">New period prices</div>
        <div className="space-y-2">
          {version.dimensions.map((d) => (
            <div key={d.key} className="grid grid-cols-[110px_1fr_16px_1fr] items-center gap-2">
              <span className="font-mono text-[11px]">{d.key}</span>
              <span className="text-right font-mono text-[11px] text-muted-foreground">${d.unitPrice.toFixed(10)}</span>
              <span className="text-center text-[11px] text-muted-foreground">→</span>
              <div className="relative">
                <span className="absolute left-2 top-1/2 -translate-y-1/2 text-[11px] text-muted-foreground">$</span>
                <input
                  type="number"
                  step="any"
                  value={prices[d.key]}
                  onChange={(e) => setPrices((p) => ({ ...p, [d.key]: e.target.value }))}
                  className="w-full rounded border border-amber-300 bg-background py-1 pl-5 pr-2 font-mono text-[11px] outline-none focus:border-muted-foreground dark:border-amber-700"
                />
              </div>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-3">
        <label className="mb-1 block text-[10px] font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Google increased input token pricing effective 10 Feb."
          className="min-h-[48px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[11px] outline-none focus:border-muted-foreground"
        />
      </div>

      {error && <p className="mt-2 text-[11px] text-red-500">{error}</p>}

      <div className="mt-3 flex justify-end gap-2">
        <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent">
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={!reason.trim() || !splitDate || loading}
          className="rounded-md bg-blue-600 px-3 py-1.5 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
        >
          {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Apply and recalculate"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify build**

Run: `pnpm build`

---

## Task 6: Adjustments Section + Distribution Preview

**Files:**
- Create: `src/features/reconciliation/components/distribution-preview.tsx`
- Create: `src/features/reconciliation/components/adjustments-section.tsx`

- [ ] **Step 1: Create distribution-preview.tsx**

Bar chart preview for all 4 modes. The component receives the distribution mode, amount, and date range, and renders the appropriate bar visualization.

```typescript
// src/features/reconciliation/components/distribution-preview.tsx
import { useMemo } from "react";

interface DistributionPreviewProps {
  mode: "lump_sum" | "even_daily" | "proportional" | "manual";
  amount: number;
  startDate: string;
  endDate: string;
  manualAllocations?: Record<string, number>;
}

function getDayLabels(start: string, end: string): string[] {
  const labels: string[] = [];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const s = new Date(start);
  const e = new Date(end);
  while (s <= e) {
    labels.push(`${s.getDate()} ${months[s.getMonth()]}`);
    s.setDate(s.getDate() + 1);
  }
  return labels;
}

// Deterministic mock weights for proportional mode
const PROPORTIONAL_WEIGHTS = [18, 12, 22, 15, 28, 20, 14];

export function DistributionPreview({ mode, amount, startDate, endDate, manualAllocations }: DistributionPreviewProps) {
  const dayLabels = useMemo(() => getDayLabels(startDate, endDate), [startDate, endDate]);
  const dayCount = dayLabels.length;
  const absAmount = Math.abs(amount);

  if (dayCount === 0 || absAmount === 0) return null;

  const bars = useMemo(() => {
    switch (mode) {
      case "lump_sum":
        return [{ label: dayLabels[0], value: absAmount }];

      case "even_daily": {
        const daily = absAmount / dayCount;
        return dayLabels.map((l) => ({ label: l, value: Math.round(daily * 100) / 100 }));
      }

      case "proportional": {
        const weights = dayLabels.map((_, i) => PROPORTIONAL_WEIGHTS[i % PROPORTIONAL_WEIGHTS.length]);
        const weightTotal = weights.reduce((a, b) => a + b, 0);
        return dayLabels.map((l, i) => ({
          label: l,
          value: Math.round((weights[i] / weightTotal) * absAmount * 100) / 100,
        }));
      }

      case "manual":
        return dayLabels.map((l) => ({
          label: l,
          value: manualAllocations?.[l] ?? 0,
        }));
    }
  }, [mode, absAmount, dayLabels, dayCount, manualAllocations]);

  const maxValue = Math.max(...bars.map((b) => b.value), 0.01);

  return (
    <div className="rounded-lg bg-accent/30 px-3 py-3">
      <div className="mb-2 text-[10px] font-medium text-muted-foreground">Preview</div>
      <div className="flex items-end gap-px" style={{ height: 60 }}>
        {bars.map((bar) => (
          <div key={bar.label} className="flex flex-1 flex-col items-center justify-end" style={{ height: "100%" }}>
            <span className="mb-0.5 font-mono text-[8px] text-muted-foreground">
              ${bar.value.toFixed(2)}
            </span>
            <div
              className="w-full rounded-t-sm"
              style={{
                height: `${(bar.value / maxValue) * 100}%`,
                backgroundColor: "#AFA9EC",
                minHeight: bar.value > 0 ? 2 : 0,
              }}
            />
            <span className="mt-0.5 text-[7px] text-muted-foreground">{bar.label.split(" ")[0]}</span>
          </div>
        ))}
      </div>
      <div className="mt-1 text-right font-mono text-[10px] text-muted-foreground">
        Total: ${absAmount.toFixed(2)}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create adjustments-section.tsx**

Adjustment type selector, amount/product fields, 4 distribution modes, reason/evidence, record button.

```typescript
// src/features/reconciliation/components/adjustments-section.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { AdjustmentType, DistributionMode } from "../api/types";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { DistributionPreview } from "./distribution-preview";
import { cn } from "@/lib/utils";

interface AdjustmentsSectionProps {
  onRecord: (data: {
    type: AdjustmentType;
    amount: number;
    product: string | null;
    distributionMode: DistributionMode;
    distributionConfig: Record<string, unknown>;
    reason: string;
    evidence: string | null;
  }) => Promise<void>;
}

const distModes: { value: DistributionMode; label: string; sub: string }[] = [
  { value: "lump_sum", label: "Lump sum", sub: "Single date" },
  { value: "even_daily", label: "Even daily", sub: "Split equally" },
  { value: "proportional", label: "Proportional", sub: "Match existing" },
  { value: "manual", label: "Manual", sub: "Set each day" },
];

export function AdjustmentsSection({ onRecord }: AdjustmentsSectionProps) {
  const { openPanel, openPanelFor, closePanel } = useReconciliationStore();
  const isOpen = openPanel === "adjustments";

  const [adjType, setAdjType] = useState<AdjustmentType>("credit_refund");
  const [amount, setAmount] = useState(-25);
  const [product, setProduct] = useState<string | null>(null);
  const [distMode, setDistMode] = useState<DistributionMode>("lump_sum");
  const [lumpDate, setLumpDate] = useState("2026-03-10");
  const [periodStart, setPeriodStart] = useState("2026-03-01");
  const [periodEnd, setPeriodEnd] = useState("2026-03-07");
  const [reason, setReason] = useState("");
  const [evidence, setEvidence] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleRecord = async () => {
    if (!reason.trim()) return;
    setLoading(true);
    setError(null);
    try {
      await onRecord({
        type: adjType,
        amount,
        product,
        distributionMode: distMode,
        distributionConfig: {
          lumpDate,
          periodStart,
          periodEnd,
        },
        reason,
        evidence: evidence || null,
      });
      closePanel();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to record adjustment.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold">Adjustments</h2>
        {!isOpen && (
          <button
            type="button"
            onClick={() => openPanelFor("adjustments")}
            className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent"
          >
            Record an adjustment
          </button>
        )}
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        For costs outside the event pipeline — refunds, credits, missed data, or invoice reconciliation.
      </p>

      {isOpen && (
        <div className="mt-3 space-y-4 rounded-xl border border-border px-4 py-4">
          {/* Type selector */}
          <div className="grid grid-cols-2 gap-2.5">
            <button
              type="button"
              onClick={() => { setAdjType("credit_refund"); setAmount(-25); }}
              className={cn(
                "rounded-xl border px-3 py-2.5 text-left transition-colors",
                adjType === "credit_refund" ? "border-2 border-foreground" : "border-border hover:bg-accent",
              )}
            >
              <div className="text-[12px] font-medium">Credit or refund</div>
              <div className="text-[10px] text-muted-foreground">Provider refund, billing credit, or cost reversal.</div>
            </button>
            <button
              type="button"
              onClick={() => { setAdjType("missing_costs"); setAmount(45); }}
              className={cn(
                "rounded-xl border px-3 py-2.5 text-left transition-colors",
                adjType === "missing_costs" ? "border-2 border-foreground" : "border-border hover:bg-accent",
              )}
            >
              <div className="text-[12px] font-medium">Missing costs</div>
              <div className="text-[10px] text-muted-foreground">Costs that were never tracked by the system.</div>
            </button>
          </div>

          {/* Amount + product */}
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="mb-1 block text-[10px] font-medium">Total amount ($)</label>
              <input
                type="number"
                step="any"
                value={amount}
                onChange={(e) => setAmount(parseFloat(e.target.value) || 0)}
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground"
              />
              <p className="mt-0.5 text-[10px] text-muted-foreground">Negative = credit/refund</p>
            </div>
            <div>
              <label className="mb-1 block text-[10px] font-medium">Attribute to product</label>
              <select
                value={product ?? ""}
                onChange={(e) => setProduct(e.target.value || null)}
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              >
                <option value="">No product (card-level)</option>
                <option value="property_search">Property search</option>
                <option value="doc_summariser">Doc summariser</option>
                <option value="content_gen">Content gen</option>
              </select>
            </div>
          </div>

          {/* Distribution mode */}
          <div>
            <div className="mb-2 text-[10px] font-medium">Distribution</div>
            <div className="grid grid-cols-4 gap-2">
              {distModes.map((m) => (
                <button
                  key={m.value}
                  type="button"
                  onClick={() => setDistMode(m.value)}
                  className={cn(
                    "rounded-lg border px-2.5 py-2 text-left transition-colors",
                    distMode === m.value ? "border-2 border-foreground" : "border-border hover:bg-accent",
                  )}
                >
                  <div className="text-[11px] font-medium">{m.label}</div>
                  <div className="text-[9px] text-muted-foreground">{m.sub}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Mode-specific fields */}
          {distMode === "lump_sum" && (
            <div>
              <label className="mb-1 block text-[10px] font-medium">Date</label>
              <input
                type="date"
                value={lumpDate}
                onChange={(e) => setLumpDate(e.target.value)}
                className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
              />
            </div>
          )}

          {(distMode === "even_daily" || distMode === "proportional" || distMode === "manual") && (
            <div className="grid grid-cols-2 gap-3">
              <div>
                <label className="mb-1 block text-[10px] font-medium">Period start</label>
                <input type="date" value={periodStart} onChange={(e) => setPeriodStart(e.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground" />
              </div>
              <div>
                <label className="mb-1 block text-[10px] font-medium">Period end</label>
                <input type="date" value={periodEnd} onChange={(e) => setPeriodEnd(e.target.value)} className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground" />
              </div>
            </div>
          )}

          {/* Distribution preview */}
          <DistributionPreview
            mode={distMode}
            amount={amount}
            startDate={distMode === "lump_sum" ? lumpDate : periodStart}
            endDate={distMode === "lump_sum" ? lumpDate : periodEnd}
          />

          {/* Reason + evidence */}
          <div>
            <label className="mb-1 block text-[10px] font-medium">Reason (required)</label>
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="e.g. Google Cloud issued a $25 credit for service disruption on 10 Mar."
              className="min-h-[48px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[11px] outline-none focus:border-muted-foreground"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-medium">Supporting evidence (optional)</label>
            <input
              value={evidence}
              onChange={(e) => setEvidence(e.target.value)}
              placeholder="e.g. Invoice link, support ticket URL"
              className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[11px] outline-none focus:border-muted-foreground"
            />
          </div>

          {error && <p className="text-[11px] text-red-500">{error}</p>}

          <div className="flex justify-end gap-2">
            <button type="button" onClick={closePanel} className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent">
              Cancel
            </button>
            <button
              type="button"
              onClick={handleRecord}
              disabled={!reason.trim() || loading}
              className="rounded-md bg-[#534AB7] px-3 py-1.5 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"
            >
              {loading ? <Loader2 className="h-3 w-3 animate-spin" /> : "Record adjustment"}
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 7: Reconciliation Summary + Audit Trail

**Files:**
- Create: `src/features/reconciliation/components/reconciliation-summary.tsx`
- Create: `src/features/reconciliation/components/audit-trail.tsx`

- [ ] **Step 1: Create reconciliation-summary.tsx**

```typescript
// src/features/reconciliation/components/reconciliation-summary.tsx
import { cn } from "@/lib/utils";

interface ReconciliationSummaryProps {
  original: number;
  reconciled: number;
  delta: number;
}

export function ReconciliationSummary({ original, reconciled, delta }: ReconciliationSummaryProps) {
  const isPositive = delta > 0;

  return (
    <div className="flex items-center justify-between rounded-lg bg-accent/50 px-3.5 py-2.5">
      <span className="text-[12px] text-muted-foreground">All-time reconciled cost</span>
      <div className="flex items-baseline gap-2.5">
        <span className="font-mono text-[13px] text-muted-foreground line-through">
          ${original.toLocaleString()}
        </span>
        <span className="font-mono text-[15px] font-bold">
          ${reconciled.toLocaleString()}
        </span>
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-mono text-[11px] font-medium",
            isPositive
              ? "bg-red-50 text-[#A32D2D] dark:bg-red-900/20"
              : "bg-green-50 text-[#3B6D11] dark:bg-green-900/20",
          )}
        >
          {isPositive ? "+" : ""}${delta.toFixed(2)}
        </span>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create audit-trail.tsx**

```typescript
// src/features/reconciliation/components/audit-trail.tsx
import type { AuditEntry } from "../api/types";
import { cn } from "@/lib/utils";

interface AuditTrailProps {
  entries: AuditEntry[];
}

const typeStyles: Record<string, string> = {
  period_insert: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
  boundary_shift: "bg-muted text-muted-foreground",
  price_edit: "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
  credit_recorded: "bg-[#EEEDFE] text-[#534AB7]",
};

const typeLabels: Record<string, string> = {
  period_insert: "Period insert",
  boundary_shift: "Boundary shift",
  price_edit: "Price edit",
  credit_recorded: "Credit recorded",
};

export function AuditTrail({ entries }: AuditTrailProps) {
  if (entries.length === 0) return null;

  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <h3 className="mb-3 text-[13px] font-semibold text-muted-foreground">Audit trail</h3>
      <div className="space-y-3">
        {entries.map((entry) => (
          <div key={entry.id} className="flex items-start justify-between gap-4">
            <div>
              <span className={cn(
                "inline-block rounded-full px-2 py-0.5 text-[10px] font-medium",
                typeStyles[entry.type] ?? "bg-muted text-muted-foreground",
              )}>
                {typeLabels[entry.type] ?? entry.type}
              </span>
              <div className="mt-1 text-[11px]">{entry.title}</div>
              <div className="text-[11px] text-muted-foreground">{entry.description}</div>
              <div className="mt-0.5 text-[10px] text-muted-foreground/60">{entry.metadata}</div>
            </div>
            <div className="text-right">
              <div
                className={cn(
                  "font-mono text-[12px] font-semibold",
                  entry.delta > 0 ? "text-[#A32D2D]" : "text-[#3B6D11]",
                )}
              >
                {entry.delta > 0 ? "+" : ""}${entry.delta.toFixed(2)}
              </div>
              <div className="text-[10px] text-muted-foreground">{entry.deltaLabel}</div>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 8: Reconciliation Page + Route + Clickable Cards

**Files:**
- Create: `src/features/reconciliation/components/reconciliation-page.tsx`
- Create: `src/app/routes/_app/pricing-cards/$cardId.tsx`
- Modify: `src/features/pricing-cards/components/pricing-card-item.tsx` (make clickable)

- [ ] **Step 1: Create reconciliation-page.tsx**

Composes all sub-components. Fetches data via `useReconciliation(cardId)`.

```typescript
// src/features/reconciliation/components/reconciliation-page.tsx
import { useEffect } from "react";
import { Skeleton } from "@/components/ui/skeleton";
import { useReconciliation, useEditPrices, useAdjustBoundary, useInsertPeriod, useRecordAdjustment } from "../api/queries";
import { useReconciliationStore } from "../stores/reconciliation-store";
import { CardHeader } from "./card-header";
import { Timeline } from "./timeline";
import { VersionDetail } from "./version-detail";
import { EditPricesPanel } from "./edit-prices-panel";
import { AdjustBoundaryPanel } from "./adjust-boundary-panel";
import { InsertPeriodPanel } from "./insert-period-panel";
import { AdjustmentsSection } from "./adjustments-section";
import { ReconciliationSummary } from "./reconciliation-summary";
import { AuditTrail } from "./audit-trail";

interface ReconciliationPageProps {
  cardId: string;
}

export function ReconciliationPage({ cardId }: ReconciliationPageProps) {
  const { data, isLoading } = useReconciliation(cardId);
  const { selectedVersionId, openPanel, selectVersion } = useReconciliationStore();
  const editPrices = useEditPrices(cardId);
  const adjustBoundary = useAdjustBoundary(cardId);
  const insertPeriod = useInsertPeriod(cardId);
  const recordAdjustment = useRecordAdjustment(cardId);

  // Auto-select the active version on load
  useEffect(() => {
    if (data && !selectedVersionId) {
      const active = data.versions.find((v) => v.status === "active");
      if (active) selectVersion(active.id);
    }
  }, [data, selectedVersionId, selectVersion]);

  if (isLoading || !data) {
    return (
      <div className="space-y-4">
        <Skeleton className="h-8 w-48" />
        <Skeleton className="h-24 rounded-xl" />
        <div className="grid grid-cols-4 gap-2.5">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-40 rounded-xl" />
      </div>
    );
  }

  const selectedVersion = data.versions.find((v) => v.id === selectedVersionId);
  const selectedIdx = data.versions.findIndex((v) => v.id === selectedVersionId);
  const nextVersion = selectedIdx >= 0 ? data.versions[selectedIdx + 1] : undefined;

  return (
    <div className="space-y-5">
      <CardHeader data={data} />

      <Timeline timeline={data.timeline} />

      {selectedVersion && (
        <>
          <VersionDetail version={selectedVersion} />

          {openPanel === "edit-prices" && (
            <EditPricesPanel
              version={selectedVersion}
              onApply={async (newPrices, reason) => {
                await editPrices.mutateAsync({ versionId: selectedVersion.id, newPrices, reason });
              }}
            />
          )}

          {openPanel === "adjust-boundary" && (
            <AdjustBoundaryPanel
              version={selectedVersion}
              nextVersion={nextVersion}
              onApply={async (newDate, newTime, reason) => {
                await adjustBoundary.mutateAsync({
                  fromVersionId: selectedVersion.id,
                  toVersionId: nextVersion?.id ?? "",
                  newBoundaryDate: newDate,
                  newBoundaryTime: newTime,
                  reason,
                });
              }}
            />
          )}

          {openPanel === "insert-period" && (
            <InsertPeriodPanel
              version={selectedVersion}
              onApply={async (splitDate, splitTime, newPrices, reason) => {
                await insertPeriod.mutateAsync({
                  versionId: selectedVersion.id,
                  splitDate,
                  splitTime,
                  newPrices,
                  reason,
                });
              }}
            />
          )}
        </>
      )}

      <AdjustmentsSection
        onRecord={async (adjData) => {
          await recordAdjustment.mutateAsync(adjData);
        }}
      />

      <ReconciliationSummary
        original={data.stats.originalTracked}
        reconciled={data.stats.reconciledTotal}
        delta={data.stats.netAdjustments}
      />

      <AuditTrail entries={data.auditTrail} />
    </div>
  );
}
```

- [ ] **Step 2: Create the dynamic route**

```typescript
// src/app/routes/_app/pricing-cards/$cardId.tsx
import { createFileRoute } from "@tanstack/react-router";
import { ReconciliationPage } from "@/features/reconciliation/components/reconciliation-page";

export const Route = createFileRoute("/_app/pricing-cards/$cardId")({
  component: CardReconciliationRoute,
});

function CardReconciliationRoute() {
  const { cardId } = Route.useParams();
  return <ReconciliationPage cardId={cardId} />;
}
```

- [ ] **Step 3: Make pricing card items clickable**

Read the current `pricing-card-item.tsx` and wrap the card content in a Link to `/pricing-cards/:cardId`.

In `src/features/pricing-cards/components/pricing-card-item.tsx`, add `Link` from `@tanstack/react-router` and wrap the outer div in a Link:

```typescript
// Change the outer div to a Link:
import { Link } from "@tanstack/react-router";

// Replace:
//   <div className="rounded-xl border ...">
// With:
//   <Link to="/pricing-cards/$cardId" params={{ cardId: card.id }} className="block rounded-xl border ...">
// And close with </Link> instead of </div>
```

- [ ] **Step 4: Verify build, test, lint**

Run: `pnpm build && pnpm test && pnpm lint`

---

## Task 9: Final Verification + PROGRESS.md

- [ ] **Step 1: Full verification**

```bash
pnpm test
pnpm lint
pnpm build
```

All must pass.

- [ ] **Step 2: Manual verification in browser**

Navigate to `/pricing-cards` → click a card → reconciliation page:
- Card header with back link, stats grid
- Dual timeline (original vs reconciled) with clickable segments
- Version detail card with dimension pricing table
- Edit prices panel (click "Edit prices")
- Adjust boundary panel (click "Adjust boundaries")
- Insert period panel (click "Split this period")
- Adjustments section with type selector, 4 distribution modes, preview bars
- Reconciliation summary bar
- Audit trail with typed entries

- [ ] **Step 3: Update PROGRESS.md**

Mark Phase 6 complete.

```markdown
## Phase 6: Reconciliation (Complete)

- [x] Reconciliation page at /pricing-cards/:cardId
- [x] Card header with back link, stats grid
- [x] Dual timeline visualization (original vs reconciled tracks)
- [x] Clickable timeline segments with version selection
- [x] Version detail card with dimension pricing table
- [x] Edit prices panel (current → new, reason, apply)
- [x] Adjust boundary panel (date/time picker, before/after visual)
- [x] Insert period panel (split date, new prices, apply)
- [x] Adjustments section with type selector
- [x] 4 distribution modes (lump sum, even daily, proportional, manual)
- [x] Distribution preview bar charts
- [x] Reconciliation summary bar (original strikethrough, reconciled, delta)
- [x] Audit trail with typed entries and deltas
- [x] Pricing card items now clickable (link to reconciliation)
- [x] Feature API layer + Zustand store
- [x] Mock data with 4 versions + adjustments + audit entries
```
