# Phase 7: Margin Management — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit. The user handles all git operations.
>
> **Design source of truth:** `docs/design/files/margin-management-dashboard.html`
> **Design rationale:** `docs/design/ui-flow-design-rationale.md` — margin management is the ongoing billing configuration page, accessible from the Billing nav item. Only visible when tenant mode is "billing".

**Goal:** Build the margin management dashboard with hierarchy tree (default → product → card), inline edit panel with impact preview and scheduling, and change history.

**Architecture:** Feature module at `src/features/billing/`. The page shows a cascading margin hierarchy where cards inherit from products, which inherit from the default. Users can override at any level. The edit panel opens inline with a slider, impact preview, immediate/scheduled toggle, and reason field. Change history tracks all modifications.

**Tech Stack:** React 19, TypeScript, TanStack Query, Lucide icons

---

## File Map

### API Layer

| File | Responsibility |
|------|---------------|
| `src/features/billing/api/types.ts` | Margin hierarchy, change record types |
| `src/features/billing/api/mock-data.ts` | Mock hierarchy tree + change history |
| `src/features/billing/api/mock.ts` | Mock adapter |
| `src/features/billing/api/api.ts` | Real API adapter (placeholder) |
| `src/features/billing/api/provider.ts` | selectProvider |
| `src/features/billing/api/queries.ts` | TanStack Query hooks |

### Components

| File | Responsibility |
|------|---------------|
| `src/features/billing/components/margin-page.tsx` | Page container, data fetching, layout |
| `src/features/billing/components/margin-stats.tsx` | 4-metric cards (blended margin, costs, billings, earned) |
| `src/features/billing/components/margin-tree.tsx` | Hierarchy table with expand/collapse, indentation, edit buttons |
| `src/features/billing/components/margin-tree-row.tsx` | Single row in the hierarchy tree |
| `src/features/billing/components/margin-edit-panel.tsx` | Edit panel: slider, inherit toggle, impact preview, scheduling, reason |
| `src/features/billing/components/impact-preview.tsx` | Was/would-be/delta billing impact calculation |
| `src/features/billing/components/change-history.tsx` | Change history log |

### Route

| File | Change |
|------|--------|
| `src/app/routes/_app/billing/index.tsx` | Replace stub with MarginPage import |

---

## Task 1: Types + Mock Data + API Layer

**Files:**
- Create: `src/features/billing/api/types.ts`
- Create: `src/features/billing/api/mock-data.ts`
- Create: `src/features/billing/api/mock.ts`
- Create: `src/features/billing/api/api.ts`
- Create: `src/features/billing/api/provider.ts`
- Create: `src/features/billing/api/queries.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/billing/api/types.ts

export type MarginLevel = "default" | "product" | "card";
export type MarginSource = "set" | "override" | "inherited";
export type ChangeEffectiveness = "immediately" | "scheduled";

export interface MarginNode {
  id: string;
  level: MarginLevel;
  name: string;
  marginPct: number;
  multiplier: number;
  source: MarginSource;
  parentSource: string;
  billings30d: number;
  children?: MarginNode[];
}

export interface MarginStats {
  blendedMargin: number;
  apiCosts30d: number;
  customerBillings30d: number;
  marginEarned30d: number;
}

export interface MarginChange {
  id: string;
  level: MarginLevel;
  targetName: string;
  fromPct: number;
  toPct: number;
  description: string;
  reason: string;
  effectiveness: ChangeEffectiveness;
  effectiveDate?: string;
  appliedBy: string;
  createdAt: string;
  estimatedImpact: number;
}

export interface MarginDashboardData {
  stats: MarginStats;
  hierarchy: MarginNode[];
  changes: MarginChange[];
}

export interface UpdateMarginRequest {
  nodeId: string;
  level: MarginLevel;
  newMarginPct: number;
  inherit: boolean;
  effectiveness: ChangeEffectiveness;
  effectiveDate?: string;
  reason: string;
}
```

- [ ] **Step 2: Create mock-data.ts**

```typescript
// src/features/billing/api/mock-data.ts
import type { MarginDashboardData } from "./types";

export const mockMarginData: MarginDashboardData = {
  stats: {
    blendedMargin: 54.2,
    apiCosts30d: 1247,
    customerBillings30d: 1923,
    marginEarned30d: 676,
  },
  hierarchy: [
    {
      id: "default",
      level: "default",
      name: "Default margin",
      marginPct: 50,
      multiplier: 1.50,
      source: "set",
      parentSource: "—",
      billings30d: 1923,
      children: [
        {
          id: "prod-ps",
          level: "product",
          name: "Property search",
          marginPct: 60,
          multiplier: 1.60,
          source: "override",
          parentSource: "Default: 50%",
          billings30d: 1357,
          children: [
            { id: "card-gem", level: "card", name: "Gemini 2.0 Flash", marginPct: 60, multiplier: 1.60, source: "inherited", parentSource: "Product: 60%", billings30d: 892 },
            { id: "card-places", level: "card", name: "Google Places", marginPct: 60, multiplier: 1.60, source: "inherited", parentSource: "Product: 60%", billings30d: 298 },
            { id: "card-serper", level: "card", name: "Serper", marginPct: 80, multiplier: 1.80, source: "override", parentSource: "Product: 60%", billings30d: 167 },
          ],
        },
        {
          id: "prod-ds",
          level: "product",
          name: "Doc summariser",
          marginPct: 50,
          multiplier: 1.50,
          source: "inherited",
          parentSource: "Default: 50%",
          billings30d: 411,
          children: [
            { id: "card-claude", level: "card", name: "Claude 3.5 Sonnet", marginPct: 50, multiplier: 1.50, source: "inherited", parentSource: "Product: 50%", billings30d: 411 },
          ],
        },
        {
          id: "prod-cg",
          level: "product",
          name: "Content gen",
          marginPct: 50,
          multiplier: 1.50,
          source: "inherited",
          parentSource: "Default: 50%",
          billings30d: 155,
          children: [
            { id: "card-gpt", level: "card", name: "GPT-4o", marginPct: 50, multiplier: 1.50, source: "inherited", parentSource: "Product: 50%", billings30d: 155 },
          ],
        },
      ],
    },
  ],
  changes: [
    {
      id: "ch-1",
      level: "card",
      targetName: "Serper",
      fromPct: 60,
      toPct: 80,
      description: "Margin changed from 60% to 80%",
      reason: "Higher margin on search — Serper costs are low relative to value delivered.",
      effectiveness: "immediately",
      appliedBy: "j.smith@co",
      createdAt: "2026-03-18T14:30:00Z",
      estimatedImpact: 8,
    },
    {
      id: "ch-2",
      level: "product",
      targetName: "Property search",
      fromPct: 50,
      toPct: 60,
      description: "Margin changed from 50% to 60%",
      reason: "Increasing margin to reflect higher value-add on property search features.",
      effectiveness: "immediately",
      appliedBy: "j.smith@co",
      createdAt: "2026-03-15T10:00:00Z",
      estimatedImpact: 135,
    },
    {
      id: "ch-3",
      level: "default",
      targetName: "Default margin",
      fromPct: 40,
      toPct: 50,
      description: "Default margin changed from 40% to 50%",
      reason: "Initial margin setup during onboarding.",
      effectiveness: "immediately",
      appliedBy: "j.smith@co",
      createdAt: "2026-03-01T09:00:00Z",
      estimatedImpact: 312,
    },
  ],
};
```

- [ ] **Step 3: Create mock.ts, api.ts, provider.ts, queries.ts**

```typescript
// src/features/billing/api/mock.ts
import type { MarginDashboardData, UpdateMarginRequest } from "./types";
import { mockMarginData } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

export async function getMarginDashboard(): Promise<MarginDashboardData> {
  await delay();
  return structuredClone(mockMarginData);
}

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export async function updateMargin(_req: UpdateMarginRequest): Promise<{ success: boolean }> {
  await delay(500);
  return { success: true };
}
```

```typescript
// src/features/billing/api/api.ts
import type { MarginDashboardData, UpdateMarginRequest } from "./types";
import { billingApi } from "@/api/client";

export async function getMarginDashboard(): Promise<MarginDashboardData> {
  const { data } = await billingApi.GET("/margins", {});
  return data as MarginDashboardData;
}

export async function updateMargin(req: UpdateMarginRequest): Promise<{ success: boolean }> {
  const { data } = await billingApi.POST("/margins", { body: req });
  return data as { success: boolean };
}
```

```typescript
// src/features/billing/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const billingMarginApi = selectProvider({ mock, api });
```

```typescript
// src/features/billing/api/queries.ts
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { billingMarginApi } from "./provider";
import type { UpdateMarginRequest } from "./types";

export function useMarginDashboard() {
  return useQuery({
    queryKey: ["margin-dashboard"],
    queryFn: () => billingMarginApi.getMarginDashboard(),
  });
}

export function useUpdateMargin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (req: UpdateMarginRequest) => billingMarginApi.updateMargin(req),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["margin-dashboard"] }),
  });
}
```

- [ ] **Step 4: Verify build**

Run: `pnpm build`

---

## Task 2: Margin Stats + Change History

**Files:**
- Create: `src/features/billing/components/margin-stats.tsx`
- Create: `src/features/billing/components/change-history.tsx`

- [ ] **Step 1: Create margin-stats.tsx**

4-metric cards: blended margin, API costs, customer billings, margin earned.

```typescript
// src/features/billing/components/margin-stats.tsx
import type { MarginStats } from "../api/types";

interface MarginStatsProps {
  stats: MarginStats;
}

export function MarginStatsGrid({ stats }: MarginStatsProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard label="Blended margin" value={`${stats.blendedMargin}%`} sub="Weighted by cost volume" green />
      <StatCard label="API costs (30d)" value={`$${stats.apiCosts30d.toLocaleString()}`} sub="Your expense" />
      <StatCard label="Customer billings (30d)" value={`$${stats.customerBillings30d.toLocaleString()}`} sub="Debited from balances" />
      <StatCard label="Margin earned (30d)" value={`$${stats.marginEarned30d.toLocaleString()}`} sub="Billings minus costs" green />
    </div>
  );
}

function StatCard({ label, value, sub, green }: { label: string; value: string; sub: string; green?: boolean }) {
  return (
    <div className="rounded-lg bg-accent/50 px-3 py-2.5">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className={`mt-1 text-[17px] font-semibold ${green ? "text-[#639922]" : ""}`}>{value}</div>
      <div className="mt-0.5 text-[9px] text-muted-foreground">{sub}</div>
    </div>
  );
}
```

- [ ] **Step 2: Create change-history.tsx**

```typescript
// src/features/billing/components/change-history.tsx
import type { MarginChange } from "../api/types";
import { cn } from "@/lib/utils";

interface ChangeHistoryProps {
  changes: MarginChange[];
}

const levelBadgeStyles = {
  default: "bg-[#EEEDFE] text-[#3C3489]",
  product: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
  card: "bg-muted text-muted-foreground",
};

const levelLabels = {
  default: "Default",
  product: "Product",
  card: "Card",
};

export function ChangeHistory({ changes }: ChangeHistoryProps) {
  if (changes.length === 0) return null;

  return (
    <div>
      <h2 className="mb-3 text-[16px] font-medium">Change history</h2>
      <div className="space-y-3">
        {changes.map((ch) => (
          <div key={ch.id} className="rounded-xl border border-border px-4 py-3">
            <div className="flex items-start justify-between gap-4">
              <div>
                <span className={cn("inline-block rounded-full px-2 py-0.5 text-[10px] font-medium", levelBadgeStyles[ch.level])}>
                  {levelLabels[ch.level]}
                </span>
                <span className="ml-2 text-[12px] font-medium">{ch.targetName}</span>
                <div className="mt-1 text-[11px] text-muted-foreground">{ch.description}</div>
                <div className="mt-0.5 text-[11px] text-muted-foreground italic">"{ch.reason}"</div>
                <div className="mt-1 text-[10px] text-muted-foreground/60">
                  {new Date(ch.createdAt).toLocaleDateString("en-GB", { day: "numeric", month: "short", year: "numeric" })}
                  {" by "}{ch.appliedBy}
                  {ch.effectiveness === "scheduled" && ch.effectiveDate && (
                    <span> · Scheduled for {new Date(ch.effectiveDate).toLocaleDateString("en-GB", { day: "numeric", month: "short" })}</span>
                  )}
                </div>
              </div>
              <div className="text-right">
                <div className={cn(
                  "font-mono text-[12px] font-semibold",
                  ch.estimatedImpact > 0 ? "text-[#A32D2D]" : "text-[#3B6D11]",
                )}>
                  {ch.estimatedImpact >= 0 ? "+" : ""}${ch.estimatedImpact}/mo
                </div>
                <div className="text-[10px] text-muted-foreground">est. impact</div>
              </div>
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

## Task 3: Margin Tree Row + Margin Tree

**Files:**
- Create: `src/features/billing/components/margin-tree-row.tsx`
- Create: `src/features/billing/components/margin-tree.tsx`

- [ ] **Step 1: Create margin-tree-row.tsx**

Single row in the hierarchy tree. Handles indentation (default=0, product=28px, card=48px), expand button for products, and Edit button.

```typescript
// src/features/billing/components/margin-tree-row.tsx
import { ChevronDown, ChevronRight } from "lucide-react";
import type { MarginNode } from "../api/types";
import { cn } from "@/lib/utils";

interface MarginTreeRowProps {
  node: MarginNode;
  expanded?: boolean;
  onToggle?: () => void;
  onEdit: (node: MarginNode) => void;
  hasChildren?: boolean;
}

const levelPadding = { default: "pl-3.5", product: "pl-7", card: "pl-12" };

const sourceBadge = {
  set: { label: "Set", className: "text-[#534AB7] font-medium" },
  override: { label: "Override", className: "text-[#534AB7] font-medium" },
  inherited: { label: "", className: "text-muted-foreground" },
};

export function MarginTreeRow({ node, expanded, onToggle, onEdit, hasChildren }: MarginTreeRowProps) {
  const src = sourceBadge[node.source];
  const sourceLabel = node.source === "inherited"
    ? `From ${node.parentSource.toLowerCase().replace(/:\s*\d+%/, "")}`
    : src.label;

  return (
    <div
      className={cn(
        "grid min-h-[44px] items-center border-b border-border/50 text-[12px] transition-colors hover:bg-accent/30",
        node.level === "default" && "bg-[#EEEDFE] dark:bg-[rgba(127,119,221,0.15)]",
        levelPadding[node.level],
      )}
      style={{ gridTemplateColumns: "minmax(0,1fr) 80px 80px 90px 100px 60px" }}
    >
      {/* Name */}
      <div className="flex items-center gap-1.5 pr-2">
        {node.level === "product" && hasChildren && (
          <button
            type="button"
            onClick={onToggle}
            className="flex h-4 w-4 items-center justify-center rounded-sm border border-border text-[10px] text-muted-foreground hover:bg-accent"
          >
            {expanded ? <ChevronDown className="h-2.5 w-2.5" /> : <ChevronRight className="h-2.5 w-2.5" />}
          </button>
        )}
        {node.level === "default" && (
          <span className="rounded-md bg-[#EEEDFE] px-1.5 py-0.5 text-[9px] font-medium text-[#3C3489] dark:bg-[rgba(127,119,221,0.3)]">
            Default
          </span>
        )}
        {node.level === "card" && (
          <span className="rounded-md bg-muted px-1.5 py-0.5 text-[9px] font-medium text-muted-foreground">
            Card
          </span>
        )}
        <div>
          <span className="font-medium">{node.name}</span>
          {node.level === "default" && (
            <div className="text-[10px] text-muted-foreground">Applies to everything without an override</div>
          )}
        </div>
      </div>

      {/* Margin % */}
      <div className="text-right font-mono font-medium">{node.marginPct}%</div>

      {/* Multiplier */}
      <div className="text-right font-mono text-[11px] text-muted-foreground">{node.multiplier.toFixed(2)}x</div>

      {/* Source */}
      <div className={cn("text-right text-[10px]", src.className)}>
        {sourceLabel}
      </div>

      {/* Billings */}
      <div className="text-right font-mono text-[11px]">${node.billings30d.toLocaleString()}</div>

      {/* Edit */}
      <div className="text-center">
        <button
          type="button"
          onClick={() => onEdit(node)}
          className="text-[10px] text-blue-600 hover:underline dark:text-blue-400"
        >
          Edit
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create margin-tree.tsx**

Renders the header + all rows with expand/collapse state for products.

```typescript
// src/features/billing/components/margin-tree.tsx
import { useState } from "react";
import type { MarginNode } from "../api/types";
import { MarginTreeRow } from "./margin-tree-row";

interface MarginTreeProps {
  hierarchy: MarginNode[];
  onEdit: (node: MarginNode) => void;
}

export function MarginTree({ hierarchy, onEdit }: MarginTreeProps) {
  const [expanded, setExpanded] = useState<Record<string, boolean>>({});

  const toggleExpand = (id: string) => {
    setExpanded((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const defaultNode = hierarchy[0];
  if (!defaultNode) return null;

  return (
    <div>
      <div className="mb-1 flex items-center justify-between">
        <h2 className="text-[16px] font-medium">Margin hierarchy</h2>
      </div>
      <p className="mb-3 text-[11px] text-muted-foreground">
        Margins cascade downward: cards inherit from their product, products inherit from the default. Override at any level.
      </p>

      <div className="overflow-hidden rounded-xl border border-border">
        {/* Header */}
        <div
          className="grid bg-accent/50 px-3.5 py-2 text-[10px] font-medium text-muted-foreground"
          style={{ gridTemplateColumns: "minmax(0,1fr) 80px 80px 90px 100px 60px" }}
        >
          <div>Name</div>
          <div className="text-right">Margin</div>
          <div className="text-right">Multiplier</div>
          <div className="text-right">Source</div>
          <div className="text-right">Billings (30d)</div>
          <div className="text-center">Edit</div>
        </div>

        {/* Default row */}
        <MarginTreeRow node={defaultNode} onEdit={onEdit} />

        {/* Products + cards */}
        {defaultNode.children?.map((product) => (
          <div key={product.id}>
            <MarginTreeRow
              node={product}
              expanded={!!expanded[product.id]}
              onToggle={() => toggleExpand(product.id)}
              onEdit={onEdit}
              hasChildren={!!product.children?.length}
            />
            {expanded[product.id] && product.children?.map((card) => (
              <MarginTreeRow key={card.id} node={card} onEdit={onEdit} />
            ))}
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

## Task 4: Impact Preview + Edit Panel

**Files:**
- Create: `src/features/billing/components/impact-preview.tsx`
- Create: `src/features/billing/components/margin-edit-panel.tsx`

- [ ] **Step 1: Create impact-preview.tsx**

Shows "Was billing" → "Would be billing" = "Difference" with color-coded delta.

```typescript
// src/features/billing/components/impact-preview.tsx
import { cn } from "@/lib/utils";

interface ImpactPreviewProps {
  currentPct: number;
  newPct: number;
  billings30d: number;
}

export function ImpactPreview({ currentPct, newPct, billings30d }: ImpactPreviewProps) {
  const cost30 = Math.round(billings30d / (1 + currentPct / 100));
  const oldBill = billings30d;
  const newBill = Math.round(cost30 * (1 + newPct / 100));
  const delta = newBill - oldBill;

  const deltaSign = delta >= 0 ? "+" : "-";
  const deltaDisplay = `${deltaSign}$${Math.abs(delta).toLocaleString()}`;

  const note = delta === 0
    ? "No change from current margin."
    : delta > 0
      ? `Customers would be billed $${Math.abs(delta).toLocaleString()}/mo more based on recent volume.`
      : `Customers would be billed $${Math.abs(delta).toLocaleString()}/mo less based on recent volume.`;

  return (
    <div className="rounded-lg border border-border px-3.5 py-3">
      <div className="mb-2 text-[12px] font-medium">Impact estimate</div>
      <p className="mb-3 text-[11px] text-muted-foreground">
        Based on the last 30 days of billing volume. Actual results depend on future usage.
      </p>

      <div className="mb-2 grid items-center gap-0" style={{ gridTemplateColumns: "1fr 32px 1fr 32px 1fr" }}>
        <div className="rounded-lg bg-accent/50 px-2.5 py-2 text-center">
          <div className="text-[10px] text-muted-foreground">Was billing (30d)</div>
          <div className="font-mono text-[15px] font-medium text-muted-foreground line-through">
            ${oldBill.toLocaleString()}
          </div>
        </div>
        <div className="text-center text-[14px] text-muted-foreground">→</div>
        <div className="rounded-lg bg-accent/50 px-2.5 py-2 text-center">
          <div className="text-[10px] text-muted-foreground">Would be billing</div>
          <div className="font-mono text-[15px] font-medium">
            ${newBill.toLocaleString()}
          </div>
        </div>
        <div className="text-center text-[14px] text-muted-foreground">=</div>
        <div className="rounded-lg bg-accent/50 px-2.5 py-2 text-center">
          <div className="text-[10px] text-muted-foreground">Difference</div>
          <div className={cn(
            "font-mono text-[15px] font-medium",
            delta > 0 && "text-[#A32D2D]",
            delta < 0 && "text-[#0F6E56]",
          )}>
            {deltaDisplay}
          </div>
        </div>
      </div>

      <p className="text-center text-[10px] text-muted-foreground">{note}</p>
    </div>
  );
}
```

- [ ] **Step 2: Create margin-edit-panel.tsx**

Inline edit panel with slider, inherit toggle, impact preview, immediate/schedule toggle, reason, and apply button.

```typescript
// src/features/billing/components/margin-edit-panel.tsx
import { useState } from "react";
import { Loader2 } from "lucide-react";
import type { MarginNode } from "../api/types";
import { useUpdateMargin } from "../api/queries";
import { ImpactPreview } from "./impact-preview";
import { cn } from "@/lib/utils";

interface MarginEditPanelProps {
  node: MarginNode;
  onClose: () => void;
}

export function MarginEditPanel({ node, onClose }: MarginEditPanelProps) {
  const [newPct, setNewPct] = useState(node.marginPct);
  const [inherit, setInherit] = useState(false);
  const [when, setWhen] = useState<"now" | "sched">("now");
  const [schedDate, setSchedDate] = useState("2026-04-01T00:00");
  const [reason, setReason] = useState("");
  const [error, setError] = useState<string | null>(null);
  const updateMutation = useUpdateMargin();

  const canInherit = node.level !== "default" && node.source === "override";
  const inheritedPct = parseInt(node.parentSource.match(/(\d+)%/)?.[1] ?? "0", 10);
  const effectivePct = inherit ? inheritedPct : newPct;

  const handleApply = async () => {
    setError(null);
    try {
      await updateMutation.mutateAsync({
        nodeId: node.id,
        level: node.level,
        newMarginPct: effectivePct,
        inherit,
        effectiveness: when === "now" ? "immediately" : "scheduled",
        effectiveDate: when === "sched" ? schedDate : undefined,
        reason,
      });
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to update margin.");
    }
  };

  return (
    <div className="rounded-xl border-2 border-blue-400 px-4 py-4 dark:border-blue-600">
      <div className="mb-1 text-[14px] font-medium">
        Edit margin: {node.name}
      </div>
      <div className="mb-4 text-[11px] text-muted-foreground">
        {node.level === "default" ? "Applies to all products and cards without overrides." : `Currently: ${node.marginPct}% (${node.source})`}
      </div>

      {/* Slider */}
      <div className={cn("mb-4", inherit && "opacity-30 pointer-events-none")}>
        <div className="mb-1 flex items-center justify-between">
          <label className="text-[11px] font-medium">New margin</label>
          <span className="min-w-[50px] text-right font-mono text-[16px] font-semibold">{newPct}%</span>
        </div>
        <input
          type="range"
          min={0}
          max={200}
          step={5}
          value={newPct}
          onChange={(e) => setNewPct(Number(e.target.value))}
          className="w-full accent-foreground"
        />
      </div>

      {/* Inherit toggle */}
      {canInherit && (
        <label className="mb-4 flex cursor-pointer items-center gap-2.5">
          <div
            onClick={() => setInherit(!inherit)}
            className={cn(
              "flex h-4 w-4 items-center justify-center rounded-sm border-[1.5px] transition-colors",
              inherit ? "border-blue-600 bg-blue-600" : "border-border",
            )}
          >
            {inherit && <span className="text-[10px] text-white">✓</span>}
          </div>
          <span className="text-[11px] text-muted-foreground">
            Revert to inherited value ({inheritedPct}%)
          </span>
        </label>
      )}

      {/* Impact preview */}
      <div className="mb-4">
        <ImpactPreview
          currentPct={node.marginPct}
          newPct={effectivePct}
          billings30d={node.billings30d}
        />
      </div>

      {/* When */}
      <div className="mb-4">
        <div className="mb-2 text-[12px] font-medium">When should this take effect?</div>
        <div className="flex gap-1.5">
          <button
            type="button"
            onClick={() => setWhen("now")}
            className={cn(
              "rounded-lg border px-3.5 py-1.5 text-[11px] transition-colors",
              when === "now"
                ? "border-2 border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
          >
            Immediately
          </button>
          <button
            type="button"
            onClick={() => setWhen("sched")}
            className={cn(
              "rounded-lg border px-3.5 py-1.5 text-[11px] transition-colors",
              when === "sched"
                ? "border-2 border-foreground bg-foreground text-background"
                : "border-border text-muted-foreground hover:bg-accent",
            )}
          >
            Schedule for later
          </button>
        </div>
        {when === "sched" && (
          <div className="mt-2">
            <label className="mb-1 block text-[11px] font-medium">Effective date and time</label>
            <input
              type="datetime-local"
              value={schedDate}
              onChange={(e) => setSchedDate(e.target.value)}
              className="rounded-lg border border-border bg-background px-2.5 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
            />
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              Current margin applies until this time. New margin applies to all events after.
            </p>
          </div>
        )}
      </div>

      {/* Reason */}
      <div className="mb-4">
        <label className="mb-1 block text-[11px] font-medium">Reason</label>
        <textarea
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="e.g. Increasing margin to reflect higher value-add..."
          className="min-h-[50px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[12px] outline-none focus:border-muted-foreground"
        />
        <p className="mt-0.5 text-[10px] text-muted-foreground">
          Recorded in change history. Visible to your team.
        </p>
      </div>

      {error && <p className="mb-3 text-[11px] text-red-500">{error}</p>}

      {/* Actions */}
      <div className="flex justify-end gap-2">
        <button
          type="button"
          onClick={onClose}
          className="rounded-lg border border-border px-4 py-1.5 text-[12px] text-muted-foreground hover:bg-accent"
        >
          Cancel
        </button>
        <button
          type="button"
          onClick={handleApply}
          disabled={updateMutation.isPending || (effectivePct === node.marginPct && !inherit)}
          className="rounded-lg bg-foreground px-5 py-1.5 text-[12px] font-medium text-background hover:opacity-90 disabled:opacity-50"
        >
          {updateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : "Apply margin change"}
        </button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 5: Margin Page + Route

**Files:**
- Create: `src/features/billing/components/margin-page.tsx`
- Modify: `src/app/routes/_app/billing/index.tsx` (replace stub)

- [ ] **Step 1: Create margin-page.tsx**

Composes all sub-components. Manages which node is being edited.

```typescript
// src/features/billing/components/margin-page.tsx
import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useMarginDashboard } from "../api/queries";
import type { MarginNode } from "../api/types";
import { MarginStatsGrid } from "./margin-stats";
import { MarginTree } from "./margin-tree";
import { MarginEditPanel } from "./margin-edit-panel";
import { ChangeHistory } from "./change-history";

export function MarginPage() {
  const { data, isLoading } = useMarginDashboard();
  const [editingNode, setEditingNode] = useState<MarginNode | null>(null);

  if (isLoading || !data) {
    return (
      <div className="space-y-5">
        <PageHeader title="Billing margins" />
        <div className="grid grid-cols-4 gap-2">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-lg" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Billing margins"
        description="Control how much margin is applied on top of API costs when billing your customers. Changes apply to future events only."
      />

      <MarginStatsGrid stats={data.stats} />

      <MarginTree
        hierarchy={data.hierarchy}
        onEdit={(node) => setEditingNode(node)}
      />

      {editingNode && (
        <MarginEditPanel
          node={editingNode}
          onClose={() => setEditingNode(null)}
        />
      )}

      <ChangeHistory changes={data.changes} />
    </div>
  );
}
```

- [ ] **Step 2: Update billing route**

```typescript
// src/app/routes/_app/billing/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { MarginPage } from "@/features/billing/components/margin-page";

export const Route = createFileRoute("/_app/billing/")({
  component: MarginPage,
});
```

- [ ] **Step 3: Verify build, test, lint**

Run: `pnpm build && pnpm test && pnpm lint`

---

## Task 6: Final Verification + PROGRESS.md

- [ ] **Step 1: Full verification**

```bash
pnpm test
pnpm lint
pnpm build
```

All must pass.

- [ ] **Step 2: Manual verification in browser**

Navigate to `/billing` and verify:
- 4 stat cards (blended margin, costs, billings, earned)
- Margin hierarchy tree with default → products → cards
- Expand/collapse product rows to see child cards
- Click "Edit" on any row → edit panel opens
- Slider updates impact preview in real-time
- Inherit toggle (on overridden nodes) reverts to parent value
- Immediate/schedule toggle shows datetime picker
- Reason field with helper text
- Apply button (disabled when no change)
- Change history with 3 entries

- [ ] **Step 3: Update PROGRESS.md**

Mark Phase 7 complete.

```markdown
## Phase 7: Margin Management (Complete)

- [x] Margin page at /billing
- [x] 4-metric stats grid (blended margin, costs, billings, earned)
- [x] Margin hierarchy tree (default → product → card)
- [x] Expand/collapse product rows
- [x] Indentation by level (default, product +28px, card +48px)
- [x] Source indicators (Set, Override, From default/product)
- [x] Edit panel with margin slider (0-200%)
- [x] Inherit toggle (revert to parent value)
- [x] Impact preview (was/would-be/delta calculation)
- [x] Immediate vs scheduled effectiveness
- [x] Reason field for audit trail
- [x] Change history with level badges and impact
- [x] Feature API layer with mock data
```
