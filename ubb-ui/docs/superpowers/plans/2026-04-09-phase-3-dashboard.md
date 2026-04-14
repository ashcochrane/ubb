# Phase 3: Dashboard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **IMPORTANT:** Do NOT commit. The user handles all git operations.
>
> **Design source of truth:** `docs/design/files/dashboard.html`
> **Design rationale:** `docs/design/ui-flow-design-rationale.md` section 6

**Goal:** Build the profitability dashboard matching the HTML mockup, with stats grid, revenue/margin chart, cost breakdown charts, product breakdowns, and customer profitability table — all driven by mock data.

**Architecture:** Feature module at `src/features/dashboard/` with co-located components and API layer. Charts use Recharts (already installed). The dashboard is composed of focused sub-components, each responsible for one visual section. Mock data generates 30-day time series with realistic patterns. The scope bar (customer filtering) is simplified for Phase 3 — full interactivity deferred to Phase 7 when real customer data exists.

**Tech Stack:** React 19, TypeScript, Recharts, TanStack Query, Lucide icons

---

## File Map

### API Layer

| File | Responsibility |
|------|---------------|
| `src/features/dashboard/api/types.ts` | Dashboard data interfaces |
| `src/features/dashboard/api/mock-data.ts` | 30-day synthetic time series, customer data, breakdowns |
| `src/features/dashboard/api/mock.ts` | Mock adapter |
| `src/features/dashboard/api/api.ts` | Real API adapter (placeholder) |
| `src/features/dashboard/api/provider.ts` | selectProvider |
| `src/features/dashboard/api/queries.ts` | TanStack Query hooks |

### Components

| File | Responsibility |
|------|---------------|
| `src/features/dashboard/components/dashboard-page.tsx` | Page container, layout, time range state |
| `src/features/dashboard/components/scope-bar.tsx` | Customer scope filter bar |
| `src/features/dashboard/components/stats-grid.tsx` | 5 metric cards row |
| `src/features/dashboard/components/revenue-chart.tsx` | Revenue & margin line/area chart |
| `src/features/dashboard/components/cost-by-product-chart.tsx` | Cost by product stacked area chart |
| `src/features/dashboard/components/cost-by-card-chart.tsx` | Cost by pricing card stacked area chart |
| `src/features/dashboard/components/breakdown-card.tsx` | Reusable breakdown (revenue/margin by product) |
| `src/features/dashboard/components/customer-table.tsx` | Customer profitability table |

### Route

| File | Change |
|------|--------|
| `src/app/routes/_app/index.tsx` | Replace stub with DashboardPage import |

---

## Task 1: Types + Mock Data + API Layer

**Files:**
- Create: `src/features/dashboard/api/types.ts`
- Create: `src/features/dashboard/api/mock-data.ts`
- Create: `src/features/dashboard/api/mock.ts`
- Create: `src/features/dashboard/api/api.ts`
- Create: `src/features/dashboard/api/provider.ts`
- Create: `src/features/dashboard/api/queries.ts`

- [ ] **Step 1: Create types.ts**

```typescript
// src/features/dashboard/api/types.ts

export type TimeRange = "7d" | "30d" | "90d" | "YTD";

export interface DailyDataPoint {
  date: string; // "YYYY-MM-DD"
  label: string; // "D Mon" for display
}

export interface RevenueTimeSeries extends DailyDataPoint {
  revenue: number;
  apiCosts: number;
  margin: number;
}

export interface CostByProductPoint extends DailyDataPoint {
  [productKey: string]: number | string; // dynamic product keys + date/label
}

export interface StatsData {
  revenue: number;
  apiCosts: number;
  grossMargin: number;
  marginPercentage: number;
  costPerDollarRevenue: number;
  revenuePrevChange: number;
  costsPrevChange: number;
  marginPrevChange: number;
  marginPctPrevChange: number;
  costPerRevPrevChange: number;
}

export interface ProductBreakdown {
  key: string;
  label: string;
  color: string;
  value: number;
  percentage: number;
}

export interface CustomerRow {
  name: string;
  customerId: string;
  revenue: number;
  revenueType: "Sub" | "Usage";
  apiCosts: number;
  margin: number;
  marginPercentage: number;
  events: number;
}

export interface CostSeries {
  key: string;
  label: string;
  color: string;
}

export interface DashboardData {
  stats: StatsData;
  revenueTimeSeries: RevenueTimeSeries[];
  costByProduct: { series: CostSeries[]; data: CostByProductPoint[] };
  costByCard: { series: CostSeries[]; data: CostByProductPoint[] };
  revenueByProduct: ProductBreakdown[];
  marginByProduct: ProductBreakdown[];
  customers: CustomerRow[];
}
```

- [ ] **Step 2: Create mock-data.ts**

Generate 30 days of synthetic data with realistic patterns.

```typescript
// src/features/dashboard/api/mock-data.ts
import type {
  DashboardData,
  RevenueTimeSeries,
  CostByProductPoint,
  CostSeries,
  ProductBreakdown,
  CustomerRow,
  StatsData,
} from "./types";

function generateDays(count: number): { date: string; label: string }[] {
  const days: { date: string; label: string }[] = [];
  const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  const now = new Date();
  for (let i = count - 1; i >= 0; i--) {
    const d = new Date(now);
    d.setDate(d.getDate() - i);
    const date = d.toISOString().split("T")[0];
    const label = `${d.getDate()} ${months[d.getMonth()]}`;
    days.push({ date, label });
  }
  return days;
}

function wave(base: number, amplitude: number, phase: number, day: number): number {
  return Math.max(0, base + amplitude * Math.sin((day + phase) * 0.2) + (Math.random() - 0.5) * amplitude * 0.4);
}

const days30 = generateDays(30);

const revenueTimeSeries: RevenueTimeSeries[] = days30.map((d, i) => {
  const revenue = wave(320, 60, 0, i);
  const apiCosts = wave(145, 30, 2, i);
  return {
    ...d,
    revenue: Math.round(revenue * 100) / 100,
    apiCosts: Math.round(apiCosts * 100) / 100,
    margin: Math.round((revenue - apiCosts) * 100) / 100,
  };
});

const productSeries: CostSeries[] = [
  { key: "property_search", label: "Property search", color: "#378ADD" },
  { key: "doc_summariser", label: "Doc summariser", color: "#7F77DD" },
  { key: "content_gen", label: "Content gen", color: "#D85A30" },
];

const costByProductData: CostByProductPoint[] = days30.map((d, i) => ({
  ...d,
  property_search: Math.round(wave(80, 18, 0, i) * 100) / 100,
  doc_summariser: Math.round(wave(40, 10, 3, i) * 100) / 100,
  content_gen: Math.round(wave(25, 8, 1, i) * 100) / 100,
}));

const cardSeries: CostSeries[] = [
  { key: "gemini_2_flash", label: "Gemini 2.0 Flash", color: "#378ADD" },
  { key: "claude_sonnet", label: "Claude Sonnet", color: "#7F77DD" },
  { key: "gpt_4o", label: "GPT-4o", color: "#D85A30" },
  { key: "google_places", label: "Google Places", color: "#3B6D11" },
  { key: "serper", label: "Serper", color: "#854F0B" },
];

const costByCardData: CostByProductPoint[] = days30.map((d, i) => ({
  ...d,
  gemini_2_flash: Math.round(wave(45, 12, 0, i) * 100) / 100,
  claude_sonnet: Math.round(wave(30, 8, 2, i) * 100) / 100,
  gpt_4o: Math.round(wave(25, 7, 4, i) * 100) / 100,
  google_places: Math.round(wave(28, 6, 1, i) * 100) / 100,
  serper: Math.round(wave(15, 4, 3, i) * 100) / 100,
}));

const revenueByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#378ADD", value: 5210, percentage: 55 },
  { key: "doc_summariser", label: "Doc summariser", color: "#7F77DD", value: 2840, percentage: 30 },
  { key: "content_gen", label: "Content gen", color: "#D85A30", value: 1420, percentage: 15 },
];

const marginByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#5DCAA5", value: 3783, percentage: 81.7 },
  { key: "doc_summariser", label: "Doc summariser", color: "#5DCAA5", value: 2252, percentage: 89.2 },
  { key: "content_gen", label: "Content gen", color: "#5DCAA5", value: 1138, percentage: 90.1 },
];

const customers: CustomerRow[] = [
  { name: "Acme Corp", customerId: "cus_8a2Kd", revenue: 2480, revenueType: "Sub", apiCosts: 412, margin: 2068, marginPercentage: 83.4, events: 84219 },
  { name: "BrightPath Ltd", customerId: "cus_3fR9w", revenue: 1920, revenueType: "Sub", apiCosts: 295, margin: 1625, marginPercentage: 84.6, events: 62340 },
  { name: "NovaTech Inc", customerId: "cus_7mP2x", revenue: 1650, revenueType: "Usage", apiCosts: 380, margin: 1270, marginPercentage: 77.0, events: 71820 },
  { name: "Helios Digital", customerId: "cus_5kL8v", revenue: 1340, revenueType: "Sub", apiCosts: 198, margin: 1142, marginPercentage: 85.2, events: 45600 },
  { name: "ClearView Analytics", customerId: "cus_2nQ4j", revenue: 890, revenueType: "Usage", apiCosts: 920, margin: -30, marginPercentage: -3.4, events: 112500 },
  { name: "Eko Systems", customerId: "cus_9tH6m", revenue: 190, revenueType: "Usage", apiCosts: 245, margin: -55, marginPercentage: -28.9, events: 38200 },
];

const totals = revenueTimeSeries.reduce(
  (acc, d) => ({
    revenue: acc.revenue + d.revenue,
    apiCosts: acc.apiCosts + d.apiCosts,
  }),
  { revenue: 0, apiCosts: 0 },
);

const stats: StatsData = {
  revenue: Math.round(totals.revenue),
  apiCosts: Math.round(totals.apiCosts),
  grossMargin: Math.round(totals.revenue - totals.apiCosts),
  marginPercentage: Math.round(((totals.revenue - totals.apiCosts) / totals.revenue) * 1000) / 10,
  costPerDollarRevenue: Math.round((totals.apiCosts / totals.revenue) * 100) / 100,
  revenuePrevChange: 8.2,
  costsPrevChange: -3.1,
  marginPrevChange: 12.4,
  marginPctPrevChange: 2.1,
  costPerRevPrevChange: -0.03,
};

export const mockDashboardData: DashboardData = {
  stats,
  revenueTimeSeries,
  costByProduct: { series: productSeries, data: costByProductData },
  costByCard: { series: cardSeries, data: costByCardData },
  revenueByProduct,
  marginByProduct,
  customers,
};
```

- [ ] **Step 3: Create mock.ts, api.ts, provider.ts, queries.ts**

```typescript
// src/features/dashboard/api/mock.ts
import type { DashboardData } from "./types";
import { mockDashboardData } from "./mock-data";

const delay = (ms = 300) => new Promise((r) => setTimeout(r, ms));

export async function getDashboard(): Promise<DashboardData> {
  await delay();
  return structuredClone(mockDashboardData);
}
```

```typescript
// src/features/dashboard/api/api.ts
import type { DashboardData } from "./types";
import { platformApi } from "@/api/client";

export async function getDashboard(): Promise<DashboardData> {
  const { data } = await platformApi.GET("/dashboard", {});
  return data as DashboardData;
}
```

```typescript
// src/features/dashboard/api/provider.ts
import { selectProvider } from "@/lib/api-provider";
import * as mock from "./mock";
import * as api from "./api";

export const dashboardApi = selectProvider({ mock, api });
```

```typescript
// src/features/dashboard/api/queries.ts
import { useQuery } from "@tanstack/react-query";
import { dashboardApi } from "./provider";

export function useDashboard() {
  return useQuery({
    queryKey: ["dashboard"],
    queryFn: () => dashboardApi.getDashboard(),
  });
}
```

- [ ] **Step 4: Verify build**

Run: `pnpm build`
Expected: Build succeeds.

---

## Task 2: Stats Grid

**Files:**
- Create: `src/features/dashboard/components/stats-grid.tsx`

- [ ] **Step 1: Create stats-grid.tsx**

5-column stats row: Revenue, API Costs, Gross Margin, Margin %, Cost/$1 Rev.

```typescript
// src/features/dashboard/components/stats-grid.tsx
import { cn } from "@/lib/utils";
import type { StatsData } from "../api/types";

interface StatsGridProps {
  stats: StatsData;
}

interface StatCardProps {
  label: string;
  value: string;
  change: string;
  positive: boolean;
}

function StatCard({ label, value, change, positive }: StatCardProps) {
  return (
    <div className="rounded-xl border border-border px-3.5 py-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-1 text-[17px] font-semibold tracking-tight">{value}</div>
      <div
        className={cn(
          "mt-0.5 text-[10px]",
          positive ? "text-green-600" : "text-red-500",
        )}
      >
        {change}
      </div>
    </div>
  );
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-5 gap-2">
      <StatCard
        label="Revenue"
        value={`$${stats.revenue.toLocaleString()}`}
        change={`${stats.revenuePrevChange > 0 ? "+" : ""}${stats.revenuePrevChange}% vs prev`}
        positive={stats.revenuePrevChange > 0}
      />
      <StatCard
        label="API costs"
        value={`$${stats.apiCosts.toLocaleString()}`}
        change={`${stats.costsPrevChange > 0 ? "+" : ""}${stats.costsPrevChange}% vs prev`}
        positive={stats.costsPrevChange < 0}
      />
      <StatCard
        label="Gross margin"
        value={`$${stats.grossMargin.toLocaleString()}`}
        change={`${stats.marginPrevChange > 0 ? "+" : ""}${stats.marginPrevChange}% vs prev`}
        positive={stats.marginPrevChange > 0}
      />
      <StatCard
        label="Margin %"
        value={`${stats.marginPercentage}%`}
        change={`${stats.marginPctPrevChange > 0 ? "+" : ""}${stats.marginPctPrevChange}pp vs prev`}
        positive={stats.marginPctPrevChange > 0}
      />
      <StatCard
        label="Cost / $1 rev"
        value={`$${stats.costPerDollarRevenue.toFixed(2)}`}
        change={`${stats.costPerRevPrevChange > 0 ? "+" : ""}${stats.costPerRevPrevChange.toFixed(2)} vs prev`}
        positive={stats.costPerRevPrevChange < 0}
      />
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 3: Revenue & Margin Chart

**Files:**
- Create: `src/features/dashboard/components/revenue-chart.tsx`

- [ ] **Step 1: Create revenue-chart.tsx**

Multi-line area chart with Revenue (green), API Costs (red), Margin (olive dashed).

```typescript
// src/features/dashboard/components/revenue-chart.tsx
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { RevenueTimeSeries } from "../api/types";

interface RevenueChartProps {
  data: RevenueTimeSeries[];
}

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="mb-1 text-[13px] font-semibold">Revenue and margin</div>
      <div className="mb-3 flex gap-3">
        <LegendItem color="#1D9E75" label="Revenue" />
        <LegendItem color="#E24B4A" label="API costs" />
        <LegendItem color="#639922" label="Margin" dashed />
      </div>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v}`}
            width={50}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid var(--color-border)",
              background: "var(--color-card)",
            }}
            formatter={(value: number, name: string) => [`$${value.toFixed(2)}`, name]}
          />
          <Area
            type="monotone"
            dataKey="revenue"
            name="Revenue"
            stroke="#1D9E75"
            fill="#1D9E75"
            fillOpacity={0.08}
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="apiCosts"
            name="API costs"
            stroke="#E24B4A"
            fill="#E24B4A"
            fillOpacity={0.06}
            strokeWidth={1.5}
          />
          <Area
            type="monotone"
            dataKey="margin"
            name="Margin"
            stroke="#639922"
            fill="#639922"
            fillOpacity={0.06}
            strokeWidth={1.5}
            strokeDasharray="4 3"
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}

function LegendItem({ color, label, dashed }: { color: string; label: string; dashed?: boolean }) {
  return (
    <div className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
      <div
        className="h-0.5 w-3"
        style={{
          backgroundColor: color,
          borderTop: dashed ? `1.5px dashed ${color}` : undefined,
          height: dashed ? 0 : 2,
        }}
      />
      {label}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 4: Cost Breakdown Charts (Product + Card)

**Files:**
- Create: `src/features/dashboard/components/cost-by-product-chart.tsx`
- Create: `src/features/dashboard/components/cost-by-card-chart.tsx`

- [ ] **Step 1: Create cost-by-product-chart.tsx**

Stacked area chart with legend. The chart uses the `series` array to dynamically render `<Area>` components for each product.

```typescript
// src/features/dashboard/components/cost-by-product-chart.tsx
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from "recharts";
import type { CostByProductPoint, CostSeries } from "../api/types";

interface CostByProductChartProps {
  title: string;
  series: CostSeries[];
  data: CostByProductPoint[];
}

export function CostBreakdownChart({ title, series, data }: CostByProductChartProps) {
  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="mb-1 text-[13px] font-semibold">{title}</div>
      <div className="mb-3 flex flex-wrap gap-3">
        {series.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5 text-[11px] text-muted-foreground">
            <div className="h-2 w-2 rounded-full" style={{ backgroundColor: s.color }} />
            {s.label}
          </div>
        ))}
      </div>
      <ResponsiveContainer width="100%" height={180}>
        <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
          <XAxis
            dataKey="label"
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            interval="preserveStartEnd"
          />
          <YAxis
            tick={{ fontSize: 10, fill: "var(--color-muted-foreground)" }}
            tickLine={false}
            axisLine={false}
            tickFormatter={(v: number) => `$${v}`}
            width={50}
          />
          <Tooltip
            contentStyle={{
              fontSize: 11,
              borderRadius: 8,
              border: "1px solid var(--color-border)",
              background: "var(--color-card)",
            }}
            formatter={(value: number, name: string) => [`$${value.toFixed(2)}`, name]}
          />
          {series.map((s) => (
            <Area
              key={s.key}
              type="monotone"
              dataKey={s.key}
              name={s.label}
              stroke={s.color}
              fill={s.color}
              fillOpacity={0.08}
              strokeWidth={1.5}
              stackId="1"
            />
          ))}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 2: Create cost-by-card-chart.tsx**

This reuses `CostBreakdownChart` — it's the same component with different data. No separate file needed. We'll use the same component in the dashboard page with different props.

Actually, since both charts are identical in structure, we only need one `CostBreakdownChart` component (created above). Skip this file creation.

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 5: Breakdown Cards + Customer Table

**Files:**
- Create: `src/features/dashboard/components/breakdown-card.tsx`
- Create: `src/features/dashboard/components/customer-table.tsx`

- [ ] **Step 1: Create breakdown-card.tsx**

Reusable for both "Revenue by product" and "Margin by product" breakdowns.

```typescript
// src/features/dashboard/components/breakdown-card.tsx
import type { ProductBreakdown } from "../api/types";

interface BreakdownCardProps {
  title: string;
  items: ProductBreakdown[];
  formatValue?: (value: number) => string;
}

export function BreakdownCard({ title, items, formatValue }: BreakdownCardProps) {
  const fmt = formatValue ?? ((v: number) => `$${v.toLocaleString()}`);
  const maxPercentage = Math.max(...items.map((i) => i.percentage));

  return (
    <div className="rounded-xl border border-border px-4 py-3.5">
      <div className="mb-3 text-[13px] font-semibold">{title}</div>
      <div className="space-y-2.5">
        {items.map((item) => (
          <div key={item.key} className="flex items-center gap-3">
            <div
              className="h-2 w-2 shrink-0 rounded-sm"
              style={{ backgroundColor: item.color }}
            />
            <span className="min-w-[100px] text-[12px]">{item.label}</span>
            <div className="flex-1">
              <div className="h-1 rounded-full bg-muted">
                <div
                  className="h-1 rounded-full"
                  style={{
                    width: `${(item.percentage / maxPercentage) * 100}%`,
                    backgroundColor: item.color,
                  }}
                />
              </div>
            </div>
            <span className="w-16 text-right font-mono text-[12px]">{fmt(item.value)}</span>
            <span className="w-12 text-right font-mono text-[11px] text-muted-foreground">
              {item.percentage}%
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Create customer-table.tsx**

```typescript
// src/features/dashboard/components/customer-table.tsx
import { cn } from "@/lib/utils";
import type { CustomerRow } from "../api/types";

interface CustomerTableProps {
  customers: CustomerRow[];
}

export function CustomerTable({ customers }: CustomerTableProps) {
  return (
    <div className="rounded-xl border border-border">
      <table className="w-full text-[12px]">
        <thead>
          <tr className="border-b border-border text-left">
            <th className="px-4 py-2.5 text-[11px] font-semibold text-muted-foreground">Customer</th>
            <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-muted-foreground">Revenue</th>
            <th className="px-3 py-2.5 text-center text-[11px] font-semibold text-muted-foreground">Type</th>
            <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-muted-foreground">API costs</th>
            <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-muted-foreground">Margin</th>
            <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-muted-foreground">Margin %</th>
            <th className="px-3 py-2.5 text-right text-[11px] font-semibold text-muted-foreground">Events</th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr key={c.customerId} className="border-b border-border last:border-0 hover:bg-accent/30">
              <td className="px-4 py-2.5">
                <div className="font-medium">{c.name}</div>
                <div className="text-[10px] text-muted-foreground">{c.customerId}</div>
              </td>
              <td className="px-3 py-2.5 text-right font-mono">${c.revenue.toLocaleString()}</td>
              <td className="px-3 py-2.5 text-center">
                <span className="rounded-full bg-muted px-2 py-0.5 text-[10px]">{c.revenueType}</span>
              </td>
              <td className="px-3 py-2.5 text-right font-mono">${c.apiCosts.toLocaleString()}</td>
              <td className={cn(
                "px-3 py-2.5 text-right font-mono",
                c.margin < 0 && "text-red-500",
              )}>
                ${c.margin.toLocaleString()}
              </td>
              <td className="px-3 py-2.5 text-right">
                <span className={cn(
                  "font-mono",
                  c.marginPercentage >= 0 ? "text-green-600" : "text-red-500",
                )}>
                  {c.marginPercentage}%
                </span>
              </td>
              <td className="px-3 py-2.5 text-right font-mono text-muted-foreground">
                {c.events.toLocaleString()}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 3: Verify build**

Run: `pnpm build`

---

## Task 6: Scope Bar

**Files:**
- Create: `src/features/dashboard/components/scope-bar.tsx`

- [ ] **Step 1: Create scope-bar.tsx**

Simplified for Phase 3 — preset buttons (All customers, Top 5, Unprofitable) + time range toggle. Full customer search/filter deferred to Phase 7.

```typescript
// src/features/dashboard/components/scope-bar.tsx
import { cn } from "@/lib/utils";
import { Download } from "lucide-react";
import type { TimeRange } from "../api/types";

interface ScopeBarProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

const timeRanges: { value: TimeRange; label: string }[] = [
  { value: "7d", label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "YTD", label: "YTD" },
];

export function ScopeBar({ timeRange, onTimeRangeChange }: ScopeBarProps) {
  return (
    <div className="space-y-3">
      {/* Scope presets */}
      <div className="flex items-center gap-1.5 rounded-xl bg-accent/50 px-3.5 py-2.5">
        <ScopeButton label="All customers" selected />
        <div className="mx-1 h-5 w-px bg-border" />
        <ScopeButton label="Top 5 by revenue" query />
        <ScopeButton label="Unprofitable" query />
      </div>

      {/* View label + controls */}
      <div className="flex items-center justify-between">
        <div>
          <span className="text-[12px] font-medium">Showing: All 18 customers</span>
          <span className="ml-1 text-[12px] text-muted-foreground">(aggregate)</span>
        </div>
        <span className="text-[11px] text-muted-foreground">30-day period</span>
      </div>

      {/* Time range + export */}
      <div className="flex items-center justify-between">
        <div className="flex overflow-hidden rounded-lg border border-border">
          {timeRanges.map((tr) => (
            <button
              key={tr.value}
              type="button"
              onClick={() => onTimeRangeChange(tr.value)}
              className={cn(
                "px-3 py-1 text-[11px] transition-colors",
                timeRange === tr.value
                  ? "bg-foreground text-background"
                  : "text-muted-foreground hover:bg-accent",
              )}
            >
              {tr.label}
            </button>
          ))}
        </div>
        <button className="flex items-center gap-1.5 rounded-lg border border-border px-3 py-1 text-[11px] text-muted-foreground hover:bg-accent">
          <Download className="h-3 w-3" /> Export
        </button>
      </div>
    </div>
  );
}

function ScopeButton({ label, selected, query }: { label: string; selected?: boolean; query?: boolean }) {
  return (
    <button
      type="button"
      className={cn(
        "rounded-full px-3.5 py-1 text-[11px] transition-colors",
        selected && "bg-foreground text-background",
        !selected && !query && "border border-border text-muted-foreground hover:border-muted-foreground",
        !selected && query && "border border-dashed border-border text-muted-foreground hover:border-muted-foreground",
      )}
    >
      {label}
    </button>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `pnpm build`

---

## Task 7: Dashboard Page Container + Route

**Files:**
- Create: `src/features/dashboard/components/dashboard-page.tsx`
- Modify: `src/app/routes/_app/index.tsx`

- [ ] **Step 1: Create dashboard-page.tsx**

Composes all sub-components with the dashboard data.

```typescript
// src/features/dashboard/components/dashboard-page.tsx
import { useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "../api/queries";
import type { TimeRange } from "../api/types";
import { ScopeBar } from "./scope-bar";
import { StatsGrid } from "./stats-grid";
import { RevenueChart } from "./revenue-chart";
import { CostBreakdownChart } from "./cost-by-product-chart";
import { BreakdownCard } from "./breakdown-card";
import { CustomerTable } from "./customer-table";

export function DashboardPage() {
  const { data, isLoading } = useDashboard();
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  if (isLoading || !data) {
    return (
      <div className="space-y-5">
        <PageHeader title="Dashboard" />
        <Skeleton className="h-20 rounded-xl" />
        <div className="grid grid-cols-5 gap-2">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-20 rounded-xl" />
          ))}
        </div>
        <Skeleton className="h-60 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />

      <ScopeBar timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      <StatsGrid stats={data.stats} />

      <RevenueChart data={data.revenueTimeSeries} />

      <div className="grid grid-cols-2 gap-4">
        <CostBreakdownChart
          title="Cost by product"
          series={data.costByProduct.series}
          data={data.costByProduct.data}
        />
        <CostBreakdownChart
          title="Cost by pricing card"
          series={data.costByCard.series}
          data={data.costByCard.data}
        />
      </div>

      <div className="grid grid-cols-2 gap-4">
        <BreakdownCard
          title="Revenue by product"
          items={data.revenueByProduct}
        />
        <BreakdownCard
          title="Margin by product"
          items={data.marginByProduct}
        />
      </div>

      <CustomerTable customers={data.customers} />
    </div>
  );
}
```

- [ ] **Step 2: Update route**

```typescript
// src/app/routes/_app/index.tsx
import { createFileRoute } from "@tanstack/react-router";
import { DashboardPage } from "@/features/dashboard/components/dashboard-page";

export const Route = createFileRoute("/_app/")({
  component: DashboardPage,
});
```

- [ ] **Step 3: Verify build, test, lint**

Run: `pnpm build && pnpm test && pnpm lint`
Expected: All pass.

---

## Task 8: Final Verification + PROGRESS.md

- [ ] **Step 1: Full verification**

```bash
pnpm test
pnpm lint
pnpm build
```

All must pass.

- [ ] **Step 2: Manual verification in browser**

Navigate to `/` and verify:
- Scope bar with preset buttons + time range toggle
- 5 stat cards with values and change indicators
- Revenue & margin area chart with 3 series
- Cost by product chart (3 products) + Cost by pricing card (5 cards) side by side
- Revenue by product breakdown + Margin by product breakdown side by side
- Customer profitability table (6 rows) with color-coded margins

- [ ] **Step 3: Update PROGRESS.md**

Mark Phase 3 complete. Update current status to Phase 4.

```markdown
## Phase 3: Dashboard (Complete)

- [x] Dashboard page with all sections
- [x] Scope bar with preset buttons + time range toggle
- [x] 5-metric stats grid
- [x] Revenue & margin area chart (Recharts)
- [x] Cost by product stacked area chart
- [x] Cost by pricing card stacked area chart
- [x] Revenue by product breakdown card
- [x] Margin by product breakdown card
- [x] Customer profitability table
- [x] Feature API layer (types, mock data, queries, provider)
- [x] Loading skeletons
```
