# Metering UI Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the metering section of the UBB tenant dashboard — pricing card management with a 4-step creation wizard, and a cost analytics dashboard with charts and tables.

**Architecture:** Two page routes within the existing authenticated layout, plus a wizard route. All data is mocked via a centralized mock data layer. Components follow existing patterns (shadcn Card, TanStack Table, Recharts). Hooks use TanStack Query with mock data via `initialData`, ready to swap for real API calls later.

**Tech Stack:** React 19, TypeScript, Tailwind CSS v4, shadcn/ui (base-nova), TanStack Router/Query/Table, Recharts, React Hook Form, Zod, Lucide icons, Sonner (toasts)

**Spec:** `docs/superpowers/specs/2026-03-14-metering-ui-design.md`

---

## Chunk 1: Infrastructure

### Task 1: Nav Config Update & Route Cleanup

**Files:**
- Modify: `src/components/layout/nav-config.ts`
- Delete: `src/routes/_authenticated/metering/usage.tsx`
- Delete: `src/routes/_authenticated/metering/analytics.tsx`

- [ ] **Step 1: Update nav-config.ts metering section**

Replace the METERING section in `navSections` with:

```typescript
{
  label: "METERING",
  items: [
    { title: "Pricing", url: "/metering/pricing", icon: DollarSign },
    { title: "Cost Dashboard", url: "/metering/dashboard", icon: BarChart3 },
  ],
},
```

Remove the `Search` and `Gauge` imports if they become unused.

- [ ] **Step 2: Delete old placeholder route files**

```bash
rm src/routes/_authenticated/metering/usage.tsx
rm src/routes/_authenticated/metering/analytics.tsx
```

- [ ] **Step 3: Verify the app builds**

```bash
pnpm dev
```

Open browser, confirm sidebar shows "Pricing" and "Cost Dashboard" under METERING. The "Cost Dashboard" link will 404 until we create the route — that's expected.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "chore: update metering nav config, remove placeholder routes"
```

---

### Task 2: Mock Data Layer

**Files:**
- Create: `src/lib/mock-data/metering.ts`

- [ ] **Step 1: Create the mock data file**

This file provides all mock data for the metering UI. It should export:

```typescript
// src/lib/mock-data/metering.ts

// --- Types ---

export type MockRateCard = {
  id: string;
  name: string;
  provider: string;
  eventType: string; // maps to event_type / cardId
  status: "active" | "draft";
  productTag?: string;
  updatedAt: string; // ISO date
  dimensions: MockDimension[];
};

export type MockDimension = {
  metricKey: string;
  pricingType: "per_unit" | "flat";
  costPerUnitMicros: number;
  unitQuantity: number;
  displayLabel: string;
  displayUnit: string;
  displayPrice: string;
};

export type MockDailyCost = {
  date: string; // YYYY-MM-DD
  products: Record<string, number>; // product name → cost in micros
  totalMicros: number;
};

export type MockRecentEvent = {
  id: string;
  time: string; // ISO date
  cardName: string;
  productTag: string;
  dimensions: string; // summary like "1,842 in · 623 out · 1 ground"
  costMicros: number;
};

export type MockCostBreakdown = {
  name: string;
  costMicros: number;
  percentage: number;
};

export type MockDimensionCost = {
  dimension: string;
  card: string;
  volume: string;
  costMicros: number;
  sharePercent: number;
};

export type WizardTemplate = {
  id: string;
  name: string;
  provider: string;
  dimensionCount: number;
  eventType: string;
  pricingPattern: "token" | "per_request" | "mixed";
  dimensions: Omit<MockDimension, "displayPrice">[];
};

// --- Mock Rate Cards ---

export const mockRateCards: MockRateCard[] = [
  {
    id: "1",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    eventType: "gemini_2_flash",
    status: "active",
    productTag: "Property search",
    updatedAt: new Date(Date.now() - 2 * 86400000).toISOString(),
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 100, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens", displayPrice: "$0.10" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 400, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens", displayPrice: "$0.40" },
      { metricKey: "grounding_requests", pricingType: "flat", costPerUnitMicros: 35_000, unitQuantity: 1, displayLabel: "Grounding requests", displayUnit: "per request", displayPrice: "$0.035" },
    ],
  },
  {
    id: "2",
    name: "Google Places text search",
    provider: "Google",
    eventType: "google_places_text",
    status: "active",
    productTag: "Property search",
    updatedAt: new Date(Date.now() - 5 * 86400000).toISOString(),
    dimensions: [
      { metricKey: "requests", pricingType: "flat", costPerUnitMicros: 32_000, unitQuantity: 1, displayLabel: "Requests", displayUnit: "per call", displayPrice: "$0.032" },
    ],
  },
  {
    id: "3",
    name: "Claude 3.5 Sonnet",
    provider: "Anthropic",
    eventType: "claude_35_sonnet",
    status: "active",
    productTag: "Doc summariser",
    updatedAt: new Date(Date.now() - 7 * 86400000).toISOString(),
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 3_000, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens", displayPrice: "$3.00" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 15_000, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens", displayPrice: "$15.00" },
    ],
  },
  {
    id: "4",
    name: "GPT-4o",
    provider: "OpenAI",
    eventType: "gpt_4o",
    status: "active",
    productTag: "Content gen",
    updatedAt: new Date(Date.now() - 3 * 86400000).toISOString(),
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 2_500, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens", displayPrice: "$2.50" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 10_000, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens", displayPrice: "$10.00" },
    ],
  },
  {
    id: "5",
    name: "Whisper large-v3",
    provider: "OpenAI",
    eventType: "whisper_large_v3",
    status: "draft",
    updatedAt: new Date().toISOString(),
    dimensions: [
      { metricKey: "audio_minutes", pricingType: "flat", costPerUnitMicros: 6_000, unitQuantity: 1, displayLabel: "Audio minutes", displayUnit: "per min", displayPrice: "$0.006" },
    ],
  },
  {
    id: "6",
    name: "Serper web search",
    provider: "Serper",
    eventType: "serper_web",
    status: "active",
    productTag: "Property search",
    updatedAt: new Date(Date.now() - 14 * 86400000).toISOString(),
    dimensions: [
      { metricKey: "search_queries", pricingType: "flat", costPerUnitMicros: 1_000, unitQuantity: 1, displayLabel: "Search queries", displayUnit: "per query", displayPrice: "$0.001" },
    ],
  },
];

// --- Mock Analytics ---

function generateDailyCosts(days: number): MockDailyCost[] {
  const result: MockDailyCost[] = [];
  const now = new Date();
  for (let i = days - 1; i >= 0; i--) {
    const date = new Date(now);
    date.setDate(date.getDate() - i);
    const dateStr = date.toISOString().split("T")[0];
    const base = 25_000_000 + Math.random() * 20_000_000;
    const spike = i === Math.floor(days * 0.6) ? 45_000_000 : 0;
    const propSearch = (base + spike) * 0.55;
    const docSumm = base * 0.25;
    const contentGen = base * 0.20;
    result.push({
      date: dateStr,
      products: {
        "Property search": Math.round(propSearch),
        "Doc summariser": Math.round(docSumm),
        "Content gen": Math.round(contentGen),
      },
      totalMicros: Math.round(propSearch + docSumm + contentGen),
    });
  }
  return result;
}

export const mockDailyCosts = generateDailyCosts(30);

export const mockAnalyticsStats = {
  totalCostMicros: 1_247_000_000,
  totalEvents: 84_219,
  avgCostPerEventMicros: 14_800,
  avgDailyCostMicros: 41_570_000,
  prevPeriodTotalCostMicros: 1_110_000_000,
  prevPeriodTotalEvents: 77_980,
  prevPeriodAvgCostMicros: 13_200,
  typicalDailyRange: "$35-48",
};

export const mockCostByProduct: MockCostBreakdown[] = [
  { name: "Property search", costMicros: 848_000_000, percentage: 68 },
  { name: "Doc summariser", costMicros: 274_000_000, percentage: 22 },
  { name: "Content gen", costMicros: 125_000_000, percentage: 10 },
];

export const mockCostByCard: MockCostBreakdown[] = [
  { name: "Gemini 2.0 Flash", costMicros: 686_000_000, percentage: 55 },
  { name: "Claude 3.5 Sonnet", costMicros: 312_000_000, percentage: 25 },
  { name: "GPT-4o", costMicros: 150_000_000, percentage: 12 },
  { name: "Google Places", costMicros: 62_000_000, percentage: 5 },
  { name: "Serper", costMicros: 37_000_000, percentage: 3 },
];

export const mockDimensionCosts: MockDimensionCost[] = [
  { dimension: "grounding_requests", card: "Gemini 2.0 Flash", volume: "18,412 requests", costMicros: 644_420_000, sharePercent: 51.7 },
  { dimension: "output_tokens", card: "Claude 3.5 Sonnet", volume: "18.6M tokens", costMicros: 279_000_000, sharePercent: 22.4 },
  { dimension: "output_tokens", card: "GPT-4o", volume: "12.1M tokens", costMicros: 121_000_000, sharePercent: 9.7 },
  { dimension: "requests", card: "Google Places", volume: "1,938 calls", costMicros: 62_020_000, sharePercent: 5.0 },
  { dimension: "output_tokens", card: "Gemini 2.0 Flash", volume: "65.4M tokens", costMicros: 26_160_000, sharePercent: 2.1 },
  { dimension: "search_queries", card: "Serper", volume: "37,100 queries", costMicros: 37_100_000, sharePercent: 3.0 },
];

export const mockRecentEvents: MockRecentEvent[] = [
  { id: "e1", time: new Date(Date.now() - 2 * 60000).toISOString(), cardName: "Gemini 2.0 Flash", productTag: "Property search", dimensions: "1,842 in · 623 out · 1 ground", costMicros: 35_400 },
  { id: "e2", time: new Date(Date.now() - 2 * 60000).toISOString(), cardName: "Google Places", productTag: "Property search", dimensions: "1 request", costMicros: 32_000 },
  { id: "e3", time: new Date(Date.now() - 3 * 60000).toISOString(), cardName: "Claude 3.5 Sonnet", productTag: "Doc summariser", dimensions: "4,210 in · 1,847 out", costMicros: 40_200 },
  { id: "e4", time: new Date(Date.now() - 5 * 60000).toISOString(), cardName: "Gemini 2.0 Flash", productTag: "Property search", dimensions: "986 in · 412 out · 1 ground", costMicros: 35_300 },
  { id: "e5", time: new Date(Date.now() - 5 * 60000).toISOString(), cardName: "Serper", productTag: "Property search", dimensions: "1 query", costMicros: 1_000 },
  { id: "e6", time: new Date(Date.now() - 7 * 60000).toISOString(), cardName: "GPT-4o", productTag: "Content gen", dimensions: "2,105 in · 3,241 out", costMicros: 37_700 },
];

// --- Wizard Templates ---

export const wizardTemplates: WizardTemplate[] = [
  {
    id: "gemini-flash",
    name: "Gemini 2.0 Flash",
    provider: "Google",
    dimensionCount: 3,
    eventType: "gemini_2_flash",
    pricingPattern: "token",
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 100, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 400, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens" },
      { metricKey: "grounding_requests", pricingType: "flat", costPerUnitMicros: 35_000, unitQuantity: 1, displayLabel: "Grounding requests", displayUnit: "per request" },
    ],
  },
  {
    id: "gpt-4o",
    name: "GPT-4o",
    provider: "OpenAI",
    dimensionCount: 2,
    eventType: "gpt_4o",
    pricingPattern: "token",
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 2_500, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 10_000, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens" },
    ],
  },
  {
    id: "claude-sonnet",
    name: "Claude Sonnet",
    provider: "Anthropic",
    dimensionCount: 2,
    eventType: "claude_sonnet",
    pricingPattern: "token",
    dimensions: [
      { metricKey: "input_tokens", pricingType: "per_unit", costPerUnitMicros: 3_000, unitQuantity: 1_000_000, displayLabel: "Input tokens", displayUnit: "per 1M tokens" },
      { metricKey: "output_tokens", pricingType: "per_unit", costPerUnitMicros: 15_000, unitQuantity: 1_000_000, displayLabel: "Output tokens", displayUnit: "per 1M tokens" },
    ],
  },
];

// --- Provider List (for select dropdown) ---

export const providerOptions = [
  "Google",
  "OpenAI",
  "Anthropic",
  "Serper",
  "Cohere",
  "Mistral",
  "Meta",
  "Custom",
];

// --- Product Tags (for assignment) ---

export const productTags = [
  "Property search",
  "Doc summariser",
  "Content gen",
];
```

- [ ] **Step 2: Verify TypeScript compiles**

```bash
pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add -A && git commit -m "feat: add metering mock data layer"
```

---

### Task 3: Format Utilities

**Files:**
- Modify: `src/lib/format.ts`

- [ ] **Step 1: Add new formatting functions**

Add these to the existing `format.ts` file (after the existing functions):

```typescript
/**
 * Format a rate card price for display.
 * e.g. costPerUnitMicros=100, unitQuantity=1_000_000 → "$0.10 / 1M"
 * e.g. costPerUnitMicros=35_000, unitQuantity=1 → "$0.035 / req"
 */
export function formatPrice(
  costPerUnitMicros: number,
  unitQuantity: number,
  displayUnit?: string,
): string {
  const price = costPerUnitMicros / 1_000_000;
  const formatted = price < 0.01
    ? `$${price.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")}`
    : `$${price.toFixed(price < 1 ? 3 : 2).replace(/0+$/, "").replace(/\.$/, "")}`;

  if (displayUnit) return `${formatted} / ${displayUnit.replace(/^per\s+/i, "")}`;
  if (unitQuantity === 1) return formatted;
  if (unitQuantity === 1_000_000) return `${formatted} / 1M`;
  if (unitQuantity === 1_000) return `${formatted} / 1K`;
  return `${formatted} / ${unitQuantity.toLocaleString()}`;
}

/**
 * Format cost in micros for dashboard display.
 * Large values: "$1,247"  Small values: "$0.0148"
 */
export function formatCostMicros(micros: number): string {
  const dollars = micros / 1_000_000;
  if (dollars === 0) return "$0";
  if (dollars >= 1) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(dollars);
  }
  // Small values — show precision
  return `$${dollars.toFixed(4)}`;
}

/**
 * Format large numbers with abbreviations.
 * 84219 → "84.2k"   1247000 → "1.25M"
 */
export function formatEventCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(2)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return count.toLocaleString();
}

/**
 * Format percent change between two values.
 * Returns "+12.3%" or "-5.1%"
 */
export function formatPercentChange(current: number, previous: number): string {
  if (previous === 0) return current > 0 ? "+∞%" : "0%";
  const change = ((current - previous) / previous) * 100;
  const sign = change >= 0 ? "+" : "";
  return `${sign}${change.toFixed(1)}%`;
}
```

- [ ] **Step 2: Verify build**

```bash
pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/format.ts && git commit -m "feat: add metering format utilities"
```

---

### Task 4: Shared StatCard Component

**Files:**
- Create: `src/components/shared/stat-card.tsx`

- [ ] **Step 1: Create the StatCard component**

```typescript
// src/components/shared/stat-card.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

interface StatCardProps {
  label: string;
  value: string;
  subtitle?: string;
  subtitleColor?: "green" | "red" | "muted";
}

export function StatCard({ label, value, subtitle, subtitleColor = "muted" }: StatCardProps) {
  const colorClass =
    subtitleColor === "green"
      ? "text-green-600"
      : subtitleColor === "red"
        ? "text-red-600"
        : "text-muted-foreground";

  return (
    <Card>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <div className="text-2xl font-bold">{value}</div>
        {subtitle && (
          <p className={`text-xs ${colorClass} mt-1`}>{subtitle}</p>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add src/components/shared/stat-card.tsx && git commit -m "feat: add shared StatCard component"
```

---

### Task 5: Stepper Component

**Files:**
- Create: `src/components/shared/stepper.tsx`

- [ ] **Step 1: Create the Stepper component**

Build from scratch using shadcn primitives. The stepper shows 4 numbered circles with connecting lines. Completed steps show a checkmark, current step is highlighted.

```typescript
// src/components/shared/stepper.tsx
import { Check } from "lucide-react";
import { cn } from "@/lib/utils";

export interface StepperStep {
  label: string;
}

interface StepperProps {
  steps: StepperStep[];
  currentStep: number; // 0-indexed
}

export function Stepper({ steps, currentStep }: StepperProps) {
  return (
    <div className="flex items-center justify-center gap-0">
      {steps.map((step, index) => {
        const isCompleted = index < currentStep;
        const isCurrent = index === currentStep;
        const isLast = index === steps.length - 1;

        return (
          <div key={step.label} className="flex items-center">
            <div className="flex flex-col items-center gap-1.5">
              <div
                className={cn(
                  "flex size-9 items-center justify-center rounded-full border-2 text-sm font-medium transition-colors",
                  isCompleted && "border-primary bg-primary text-primary-foreground",
                  isCurrent && "border-primary text-primary",
                  !isCompleted && !isCurrent && "border-muted-foreground/30 text-muted-foreground/50",
                )}
              >
                {isCompleted ? <Check className="size-4" /> : index + 1}
              </div>
              <span
                className={cn(
                  "text-xs font-medium",
                  isCurrent && "text-foreground",
                  isCompleted && "text-foreground",
                  !isCompleted && !isCurrent && "text-muted-foreground/50",
                )}
              >
                {step.label}
              </span>
            </div>
            {!isLast && (
              <div
                className={cn(
                  "mx-2 h-0.5 w-16 -translate-y-3",
                  isCompleted ? "bg-primary" : "bg-muted-foreground/20",
                )}
              />
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

```bash
pnpm tsc --noEmit
```

- [ ] **Step 3: Commit**

```bash
git add src/components/shared/stepper.tsx && git commit -m "feat: add shared Stepper component"
```

---

### Task 6: Pricing & Analytics Hooks (Mock)

**Files:**
- Create: `src/api/hooks/use-pricing.ts`
- Create: `src/api/hooks/use-metering-analytics.ts`

- [ ] **Step 1: Create pricing hook**

```typescript
// src/api/hooks/use-pricing.ts
import { useQuery } from "@tanstack/react-query";
import { mockRateCards, type MockRateCard } from "@/lib/mock-data/metering";

export function usePricingCards() {
  return useQuery<MockRateCard[]>({
    queryKey: ["pricing", "cards"],
    queryFn: async () => mockRateCards,
    initialData: mockRateCards,
  });
}
```

- [ ] **Step 2: Create analytics hook**

```typescript
// src/api/hooks/use-metering-analytics.ts
import { useQuery } from "@tanstack/react-query";
import {
  mockAnalyticsStats,
  mockDailyCosts,
  mockCostByProduct,
  mockCostByCard,
  mockDimensionCosts,
  mockRecentEvents,
} from "@/lib/mock-data/metering";

export function useMeteringAnalytics() {
  return useQuery({
    queryKey: ["metering", "analytics"],
    queryFn: async () => ({
      stats: mockAnalyticsStats,
      dailyCosts: mockDailyCosts,
      costByProduct: mockCostByProduct,
      costByCard: mockCostByCard,
      dimensionCosts: mockDimensionCosts,
      recentEvents: mockRecentEvents,
    }),
    initialData: {
      stats: mockAnalyticsStats,
      dailyCosts: mockDailyCosts,
      costByProduct: mockCostByProduct,
      costByCard: mockCostByCard,
      dimensionCosts: mockDimensionCosts,
      recentEvents: mockRecentEvents,
    },
  });
}
```

- [ ] **Step 3: Verify build**

```bash
pnpm tsc --noEmit
```

- [ ] **Step 4: Commit**

```bash
git add src/api/hooks/use-pricing.ts src/api/hooks/use-metering-analytics.ts && git commit -m "feat: add metering query hooks with mock data"
```

---

## Chunk 2: Pricing Cards Page

### Task 7: Pricing Cards Page

**Files:**
- Modify: `src/routes/_authenticated/metering/pricing.tsx`
- Create: `src/components/metering/pricing/pricing-cards-page.tsx`
- Create: `src/components/metering/pricing/pricing-card.tsx`
- Create: `src/components/metering/pricing/pricing-stats.tsx`
- Create: `src/components/metering/pricing/pricing-empty-state.tsx`

- [ ] **Step 1: Create PricingCard component**

Individual card in the grid. Displays a `MockRateCard` matching the design screenshot.

```typescript
// src/components/metering/pricing/pricing-card.tsx
import { Card, CardContent, CardFooter, CardHeader } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Separator } from "@/components/ui/separator";
import { formatRelativeDate } from "@/lib/format";
import type { MockRateCard } from "@/lib/mock-data/metering";

interface PricingCardProps {
  card: MockRateCard;
}

export function PricingCard({ card }: PricingCardProps) {
  return (
    <Card className="cursor-pointer transition-shadow hover:shadow-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between">
          <div>
            <div className="flex items-center gap-2">
              <span
                className={`size-2 rounded-full ${card.status === "active" ? "bg-blue-500" : "bg-amber-500"}`}
              />
              <h3 className="font-semibold">{card.name}</h3>
            </div>
            <p className="mt-0.5 text-sm text-muted-foreground">{card.provider}</p>
          </div>
          <Badge variant={card.status === "active" ? "outline" : "secondary"}>
            {card.status === "active" ? "Active" : "Draft"}
          </Badge>
        </div>
      </CardHeader>
      <Separator />
      <CardContent className="py-3">
        <div className="space-y-1.5">
          {card.dimensions.map((dim) => (
            <div key={dim.metricKey} className="flex items-center justify-between text-sm">
              <span className="font-mono text-muted-foreground">{dim.metricKey}</span>
              <span>{dim.displayPrice} / {dim.displayUnit.replace(/^per\s+/i, "")}</span>
            </div>
          ))}
        </div>
      </CardContent>
      <Separator />
      <CardFooter className="pt-3 text-sm text-muted-foreground">
        <div className="flex w-full items-center justify-between">
          <div>
            {card.productTag && (
              <Badge variant="outline" className="text-xs">
                {card.productTag}
              </Badge>
            )}
          </div>
          <span>Updated {formatRelativeDate(card.updatedAt)}</span>
        </div>
      </CardFooter>
    </Card>
  );
}
```

- [ ] **Step 2: Create PricingStats component**

```typescript
// src/components/metering/pricing/pricing-stats.tsx
import { StatCard } from "@/components/shared/stat-card";
import { formatCostMicros, formatEventCount } from "@/lib/format";
import type { MockRateCard } from "@/lib/mock-data/metering";
import { mockAnalyticsStats } from "@/lib/mock-data/metering";

interface PricingStatsProps {
  cards: MockRateCard[];
}

export function PricingStats({ cards }: PricingStatsProps) {
  const activeCount = cards.filter((c) => c.status === "active").length;
  const products = new Set(cards.map((c) => c.productTag).filter(Boolean));

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard label="Active cards" value={activeCount.toString()} />
      <StatCard
        label="Tracked this month"
        value={formatCostMicros(mockAnalyticsStats.totalCostMicros)}
      />
      <StatCard
        label="Total API calls"
        value={formatEventCount(mockAnalyticsStats.totalEvents)}
      />
      <StatCard label="Products using cards" value={products.size.toString()} />
    </div>
  );
}
```

- [ ] **Step 3: Create PricingEmptyState component**

```typescript
// src/components/metering/pricing/pricing-empty-state.tsx
import { CreditCard } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link } from "@tanstack/react-router";

export function PricingEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
      <CreditCard className="size-12 text-muted-foreground/50" />
      <h3 className="mt-4 text-lg font-semibold">Set up your first pricing card</h3>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Pricing cards define how your API usage gets costed. Create one to start tracking.
      </p>
      <Button className="mt-6" render={<Link to="/metering/pricing/new" />}>
        + Create pricing card
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Create PricingCardsPage component**

```typescript
// src/components/metering/pricing/pricing-cards-page.tsx
import { useState, useMemo } from "react";
import { Link } from "@tanstack/react-router";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { usePricingCards } from "@/api/hooks/use-pricing";
import { PricingCard } from "./pricing-card";
import { PricingStats } from "./pricing-stats";
import { PricingEmptyState } from "./pricing-empty-state";

export function PricingCardsPage() {
  const { data: cards = [] } = usePricingCards();
  const [search, setSearch] = useState("");

  const filteredCards = useMemo(() => {
    if (!search) return cards;
    const q = search.toLowerCase();
    return cards.filter(
      (c) =>
        c.name.toLowerCase().includes(q) ||
        c.provider.toLowerCase().includes(q),
    );
  }, [cards, search]);

  if (cards.length === 0) {
    return (
      <div className="space-y-6">
        <h1 className="text-2xl font-bold tracking-tight">Pricing cards</h1>
        <PricingEmptyState />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Pricing cards</h1>
        <div className="flex items-center gap-3">
          <Input
            placeholder="Search cards..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="w-64"
          />
          <Button render={<Link to="/metering/pricing/new" />}>
            + New card
          </Button>
        </div>
      </div>

      <PricingStats cards={cards} />

      <div className="grid gap-4 md:grid-cols-2">
        {filteredCards.map((card) => (
          <PricingCard key={card.id} card={card} />
        ))}
      </div>

      {filteredCards.length === 0 && search && (
        <p className="py-8 text-center text-muted-foreground">
          No cards matching "{search}"
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 5: Update pricing route**

Replace the placeholder in `src/routes/_authenticated/metering/pricing.tsx`:

```typescript
import { createFileRoute } from "@tanstack/react-router";
import { PricingCardsPage } from "@/components/metering/pricing/pricing-cards-page";

export const Route = createFileRoute("/_authenticated/metering/pricing")({
  component: PricingCardsPage,
});
```

- [ ] **Step 6: Verify in browser**

```bash
pnpm dev
```

Navigate to `/metering/pricing`. Should see stats row, search bar, "+ New card" button, and 6 pricing cards in a 2-column grid.

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "feat: add pricing cards page with stats, search, and card grid"
```

---

## Chunk 3: Card Creation Wizard

### Task 8: Wizard Container + Step 1 (Source)

**Files:**
- Create: `src/routes/_authenticated/metering/pricing.new.tsx`
- Create: `src/components/metering/wizard/new-card-wizard.tsx`
- Create: `src/components/metering/wizard/step-source.tsx`

- [ ] **Step 1: Create the wizard route**

```typescript
// src/routes/_authenticated/metering/pricing.new.tsx
import { createFileRoute } from "@tanstack/react-router";
import { NewCardWizard } from "@/components/metering/wizard/new-card-wizard";

export const Route = createFileRoute("/_authenticated/metering/pricing/new")({
  component: NewCardWizard,
});
```

- [ ] **Step 2: Create the wizard container**

This component manages step state and wraps everything in a React Hook Form provider.

```typescript
// src/components/metering/wizard/new-card-wizard.tsx
import { useState } from "react";
import { useForm, FormProvider } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { Stepper } from "@/components/shared/stepper";
import { StepSource } from "./step-source";
import { StepDetails } from "./step-details";
import { StepDimensions } from "./step-dimensions";
import { StepReview } from "./step-review";

const dimensionSchema = z.object({
  metricKey: z.string().regex(/^[a-z][a-z0-9_]{0,63}$/, "Lowercase letters, numbers, underscores. Must start with a letter."),
  pricingType: z.enum(["per_unit", "flat"]),
  unitPriceMicros: z.coerce.number().int().min(0),
  unitQuantity: z.coerce.number().int().min(1).default(1_000_000),
  displayLabel: z.string().optional().default(""),
  displayUnit: z.string().optional().default(""),
  displayPrice: z.string().optional().default(""),
});

const wizardSchema = z.object({
  source: z.enum(["template", "custom"]),
  templateId: z.string().optional().default(""),
  name: z.string().min(1, "Card name is required").max(100),
  provider: z.string().min(1, "Provider is required").max(100),
  cardId: z.string().regex(/^[a-z0-9_-]+$/, "Lowercase letters, numbers, hyphens, underscores only"),
  pricingPattern: z.enum(["token", "per_request", "mixed"]),
  description: z.string().max(250).optional().default(""),
  pricingSourceUrl: z.string().url().optional().or(z.literal("")).default(""),
  dimensions: z.array(dimensionSchema).min(1, "At least one dimension required"),
  productTag: z.string().optional().default(""),
});

export type WizardFormData = z.infer<typeof wizardSchema>;

const STEPS = [
  { label: "Source" },
  { label: "Details" },
  { label: "Dimensions" },
  { label: "Review & test" },
];

export function NewCardWizard() {
  const [currentStep, setCurrentStep] = useState(0);

  const methods = useForm<WizardFormData>({
    resolver: zodResolver(wizardSchema),
    defaultValues: {
      source: "custom",
      templateId: "",
      name: "",
      provider: "",
      cardId: "",
      pricingPattern: "token",
      description: "",
      pricingSourceUrl: "",
      dimensions: [],
      productTag: "",
    },
    mode: "onChange",
  });

  const goNext = () => setCurrentStep((s) => Math.min(s + 1, STEPS.length - 1));
  const goBack = () => setCurrentStep((s) => Math.max(s - 1, 0));

  return (
    <FormProvider {...methods}>
      <div className="mx-auto max-w-3xl space-y-8 py-4">
        <Stepper steps={STEPS} currentStep={currentStep} />
        {currentStep === 0 && <StepSource onNext={goNext} />}
        {currentStep === 1 && <StepDetails onNext={goNext} onBack={goBack} />}
        {currentStep === 2 && <StepDimensions onNext={goNext} onBack={goBack} />}
        {currentStep === 3 && <StepReview onBack={goBack} goToStep={setCurrentStep} />}
      </div>
    </FormProvider>
  );
}
```

- [ ] **Step 3: Create Step 1 — Source**

```typescript
// src/components/metering/wizard/step-source.tsx
import { useFormContext } from "react-hook-form";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import { wizardTemplates } from "@/lib/mock-data/metering";
import type { WizardFormData } from "./new-card-wizard";

interface StepSourceProps {
  onNext: () => void;
}

export function StepSource({ onNext }: StepSourceProps) {
  const { watch, setValue } = useFormContext<WizardFormData>();
  const source = watch("source");
  const templateId = watch("templateId");

  const handleSourceSelect = (value: "template" | "custom") => {
    setValue("source", value);
    if (value === "custom") {
      setValue("templateId", "");
    }
  };

  const handleTemplateSelect = (id: string) => {
    setValue("templateId", id);
    const template = wizardTemplates.find((t) => t.id === id);
    if (template) {
      setValue("name", template.name);
      setValue("provider", template.provider);
      setValue("cardId", template.eventType);
      setValue("pricingPattern", template.pricingPattern);
      setValue(
        "dimensions",
        template.dimensions.map((d) => ({
          ...d,
          unitPriceMicros: d.costPerUnitMicros,
          displayPrice: "",
        })),
      );
    }
  };

  const canContinue = source === "custom" || (source === "template" && templateId);

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">How do you want to start?</h2>
        <p className="mt-2 text-muted-foreground">
          Pick a pre-built template or configure from scratch. Templates use current public pricing — you just verify.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card
          className={cn(
            "cursor-pointer transition-all",
            source === "template" && "border-2 border-foreground",
          )}
          onClick={() => handleSourceSelect("template")}
        >
          <CardContent className="p-6">
            <h3 className="font-semibold">From template</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Pre-filled with current API pricing. Fastest path — just verify and go.
            </p>
          </CardContent>
        </Card>
        <Card
          className={cn(
            "cursor-pointer transition-all",
            source === "custom" && "border-2 border-foreground",
          )}
          onClick={() => handleSourceSelect("custom")}
        >
          <CardContent className="p-6">
            <h3 className="font-semibold">Custom card</h3>
            <p className="mt-1 text-sm text-muted-foreground">
              Configure from scratch for any API or service not in our catalog.
            </p>
          </CardContent>
        </Card>
      </div>

      {source === "template" && (
        <div className="space-y-3">
          <h3 className="font-semibold">Choose a template</h3>
          <div className="grid gap-4 md:grid-cols-3">
            {wizardTemplates.map((t) => (
              <Card
                key={t.id}
                className={cn(
                  "cursor-pointer transition-all",
                  templateId === t.id && "border-2 border-foreground",
                )}
                onClick={() => handleTemplateSelect(t.id)}
              >
                <CardContent className="p-4">
                  <h4 className="font-semibold">{t.name}</h4>
                  <p className="text-sm text-muted-foreground">
                    {t.dimensionCount} dimensions
                  </p>
                </CardContent>
              </Card>
            ))}
          </div>
        </div>
      )}

      <div className="flex justify-end border-t pt-6">
        <Button onClick={onNext} disabled={!canContinue}>
          Continue
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Create placeholder files for Steps 2-4**

Create minimal placeholder components so the wizard container compiles:

```typescript
// src/components/metering/wizard/step-details.tsx
export function StepDetails({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  return <div>Step 2: Details (coming next)</div>;
}

// src/components/metering/wizard/step-dimensions.tsx
export function StepDimensions({ onNext, onBack }: { onNext: () => void; onBack: () => void }) {
  return <div>Step 3: Dimensions (coming next)</div>;
}

// src/components/metering/wizard/step-review.tsx
export function StepReview({ onBack, goToStep }: { onBack: () => void; goToStep: (step: number) => void }) {
  return <div>Step 4: Review (coming next)</div>;
}
```

- [ ] **Step 5: Verify in browser**

```bash
pnpm dev
```

Navigate to `/metering/pricing`, click "+ New card". Should see the stepper at the top and the Source step with template/custom selection.

- [ ] **Step 6: Commit**

```bash
git add -A && git commit -m "feat: add new card wizard with stepper and Step 1 (Source)"
```

---

### Task 9: Wizard Step 2 (Details)

**Files:**
- Modify: `src/components/metering/wizard/step-details.tsx`
- Create: `src/components/metering/wizard/card-preview.tsx`

- [ ] **Step 1: Create CardPreview widget**

```typescript
// src/components/metering/wizard/card-preview.tsx
import { useFormContext } from "react-hook-form";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import type { WizardFormData } from "./new-card-wizard";

export function CardPreview() {
  const { watch } = useFormContext<WizardFormData>();
  const name = watch("name");
  const provider = watch("provider");
  const cardId = watch("cardId");
  const pricingPattern = watch("pricingPattern");

  return (
    <Card className="bg-muted/50">
      <CardContent className="p-4">
        <p className="text-xs text-muted-foreground">Card preview</p>
        <div className="mt-2 flex items-center gap-2">
          <span className="size-2 rounded-full bg-muted-foreground" />
          <span className="font-semibold">{name || "Untitled card"}</span>
          <Badge variant="secondary" className="text-xs">Draft</Badge>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          {provider || "No provider selected"}
        </p>
        <p className="mt-1 text-xs text-muted-foreground font-mono">
          card_id: {cardId || "—"}
        </p>
        {pricingPattern && (
          <p className="mt-1 text-xs text-muted-foreground">
            No pricing pattern selected
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Implement Step 2 — Details**

Replace the placeholder in `step-details.tsx`:

```typescript
// src/components/metering/wizard/step-details.tsx
import { useFormContext } from "react-hook-form";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { cn } from "@/lib/utils";
import { providerOptions } from "@/lib/mock-data/metering";
import { CardPreview } from "./card-preview";
import type { WizardFormData } from "./new-card-wizard";

interface StepDetailsProps {
  onNext: () => void;
  onBack: () => void;
}

function slugify(str: string): string {
  return str
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_|_$/g, "");
}

export function StepDetails({ onNext, onBack }: StepDetailsProps) {
  const { register, watch, setValue, formState: { errors } } = useFormContext<WizardFormData>();
  const source = watch("source");
  const templateId = watch("templateId");
  const pricingPattern = watch("pricingPattern");
  const name = watch("name");
  const descriptionLength = (watch("description") || "").length;

  const handleNameChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setValue("name", val);
    setValue("cardId", slugify(val));
  };

  const breadcrumb = source === "template" ? `From template: ${templateId}` : "Custom card";

  const canContinue = name && watch("provider") && watch("cardId") && pricingPattern;

  const pricingPatterns = [
    { value: "token", label: "Token-based", desc: "Charges per input and/or output token. Most LLM APIs." },
    { value: "per_request", label: "Per-request", desc: "Flat fee per API call regardless of payload size." },
    { value: "mixed", label: "Mixed / other", desc: "Combination of unit-based and flat charges, or something unique." },
  ] as const;

  return (
    <div className="space-y-8">
      <div>
        <Badge variant="outline" className="mb-3">{breadcrumb}</Badge>
        <h2 className="text-2xl font-bold">Describe this API</h2>
        <p className="mt-2 text-muted-foreground">
          Tell us what you're tracking. This helps us suggest the right dimension structure in the next step and organises your dashboard.
        </p>
      </div>

      {/* Identity */}
      <div className="space-y-4">
        <h3 className="font-semibold">Identity</h3>
        <p className="text-sm text-muted-foreground">How this card appears across your account.</p>

        <div className="space-y-2">
          <Label htmlFor="name">Card name</Label>
          <Input
            id="name"
            placeholder="e.g. Mapbox Geocoding API, Internal OCR Service, Twilio SMS"
            value={name}
            onChange={handleNameChange}
          />
          <p className="text-xs text-muted-foreground">
            Use the API or model name your team would recognise. Be specific — include the model variant or tier if relevant.
          </p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="provider">Provider</Label>
          <Select value={watch("provider")} onValueChange={(v) => setValue("provider", v)}>
            <SelectTrigger>
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {providerOptions.map((p) => (
                <SelectItem key={p} value={p}>{p}</SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label htmlFor="cardId">Card ID</Label>
          <div className="flex gap-2">
            <Input
              id="cardId"
              {...register("cardId")}
              className="font-mono"
            />
            <Button
              variant="outline"
              type="button"
              onClick={() => setValue("cardId", slugify(name || "card"))}
            >
              Regenerate
            </Button>
          </div>
          <p className="text-xs text-muted-foreground">
            Referenced in SDK calls. Auto-derived from name. Locked after activation.
          </p>
          {errors.cardId && (
            <p className="text-xs text-destructive">{errors.cardId.message}</p>
          )}
        </div>
      </div>

      {/* Pricing pattern */}
      <div className="space-y-4">
        <h3 className="font-semibold">Pricing pattern</h3>
        <p className="text-sm text-muted-foreground">
          How does this API charge? This helps us pre-configure the right dimensions on the next step.
        </p>
        <div className="grid gap-3 md:grid-cols-3">
          {pricingPatterns.map((pp) => (
            <Card
              key={pp.value}
              className={cn(
                "cursor-pointer transition-all",
                pricingPattern === pp.value && "border-2 border-foreground",
              )}
              onClick={() => setValue("pricingPattern", pp.value)}
            >
              <CardContent className="p-4">
                <h4 className="text-sm font-semibold">{pp.label}</h4>
                <p className="mt-1 text-xs text-muted-foreground">{pp.desc}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </div>

      {/* Optional context */}
      <div className="space-y-4">
        <h3 className="font-semibold">Optional context</h3>
        <p className="text-sm text-muted-foreground">Notes for your team. Not used in cost calculations.</p>

        <div className="space-y-2">
          <Label htmlFor="description">Description</Label>
          <Textarea
            id="description"
            {...register("description")}
            placeholder="e.g. Used for geocoding property addresses in the search pipeline. Rate-limited to 100 req/s on our current plan."
            rows={3}
          />
          <p className="text-xs text-muted-foreground text-right">{descriptionLength} / 250</p>
        </div>

        <div className="space-y-2">
          <Label htmlFor="pricingSourceUrl">Pricing source URL (optional)</Label>
          <Input
            id="pricingSourceUrl"
            {...register("pricingSourceUrl")}
            placeholder="e.g. https://cloud.google.com/maps-platform/pricing"
          />
          <p className="text-xs text-muted-foreground">
            Link to the provider's pricing page. Helpful when verifying or updating prices later.
          </p>
        </div>
      </div>

      <CardPreview />

      <div className="flex justify-between border-t pt-6">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <Button onClick={onNext} disabled={!canContinue}>
          Continue to dimensions
        </Button>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

Navigate to wizard, proceed to Step 2. Fill in fields and verify the card preview updates live, the slug auto-generates, pricing patterns are selectable.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: add wizard Step 2 (Details) with card preview"
```

---

### Task 10: Wizard Step 3 (Dimensions) + Cost Tester

**Files:**
- Modify: `src/components/metering/wizard/step-dimensions.tsx`
- Create: `src/components/metering/wizard/cost-tester.tsx`

- [ ] **Step 1: Create the CostTester component**

Shared between Step 3 and Step 4. Takes dimensions from form state, lets user enter sample quantities, shows live cost calculations.

```typescript
// src/components/metering/wizard/cost-tester.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { formatCostMicros } from "@/lib/format";
import type { WizardFormData } from "./new-card-wizard";

interface CostTesterProps {
  showProjections?: boolean;
}

export function CostTester({ showProjections = false }: CostTesterProps) {
  const { watch } = useFormContext<WizardFormData>();
  const dimensions = watch("dimensions") || [];
  const [quantities, setQuantities] = useState<Record<string, number>>({});

  const calculations = dimensions.map((dim) => {
    const qty = quantities[dim.metricKey] || 1000;
    const costMicros =
      dim.pricingType === "flat"
        ? qty * dim.unitPriceMicros
        : Math.round((qty * dim.unitPriceMicros) / (dim.unitQuantity || 1_000_000));
    return {
      metricKey: dim.metricKey,
      displayLabel: dim.displayLabel || dim.metricKey,
      quantity: qty,
      unitPrice: dim.unitPriceMicros / 1_000_000,
      unitQuantity: dim.unitQuantity || 1_000_000,
      costMicros,
      pricingType: dim.pricingType,
    };
  });

  const totalCostMicros = calculations.reduce((sum, c) => sum + c.costMicros, 0);

  return (
    <Card className="bg-muted/50">
      <CardContent className="p-6 space-y-4">
        <div className="flex items-center justify-between">
          <h4 className="font-semibold">
            {showProjections ? "Dry-run simulator" : "Live cost tester"}
          </h4>
          <Badge variant="outline" className="text-xs">
            {showProjections ? "Looks correct" : "Updates as you type"}
          </Badge>
        </div>
        {showProjections && (
          <p className="text-sm text-muted-foreground">
            Enter realistic sample quantities for a single API call. The simulator shows exactly how costs would be calculated.
          </p>
        )}

        <div className="space-y-3">
          {calculations.map((calc) => (
            <div key={calc.metricKey} className="flex items-center gap-4">
              <span className="w-36 text-sm font-mono shrink-0">{calc.metricKey}</span>
              <Input
                type="number"
                className="w-24"
                value={quantities[calc.metricKey] ?? 1000}
                onChange={(e) =>
                  setQuantities((prev) => ({
                    ...prev,
                    [calc.metricKey]: parseInt(e.target.value) || 0,
                  }))
                }
              />
              <span className="text-sm text-muted-foreground">
                {calc.quantity.toLocaleString()}
                {calc.pricingType === "flat" ? " event" : ""} x ${calc.unitPrice.toFixed(
                  calc.unitPrice < 0.001 ? 7 : 6,
                )}{" "}
                = ${(calc.costMicros / 1_000_000).toFixed(6)}
              </span>
            </div>
          ))}
        </div>

        <div className="border-t pt-3 flex justify-between items-center font-semibold">
          <span>{showProjections ? "Total per event" : "Total event cost"}</span>
          <span className="font-mono">${(totalCostMicros / 1_000_000).toFixed(6)}</span>
        </div>

        {showProjections && totalCostMicros > 0 && (
          <p className="text-sm text-muted-foreground text-right">
            At 1,000 events/day: ~{formatCostMicros(totalCostMicros * 1000)}/day · ~{formatCostMicros(totalCostMicros * 30000)}/month
          </p>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Implement Step 3 — Dimensions**

Replace the placeholder in `step-dimensions.tsx`:

```typescript
// src/components/metering/wizard/step-dimensions.tsx
import { useFormContext, useFieldArray } from "react-hook-form";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import { CostTester } from "./cost-tester";
import type { WizardFormData } from "./new-card-wizard";

interface StepDimensionsProps {
  onNext: () => void;
  onBack: () => void;
}

const QUICK_ADD_SUGGESTIONS = [
  { metricKey: "grounding_requests", displayLabel: "Grounding", displayUnit: "per request", pricingType: "flat" as const, unitQuantity: 1 },
  { metricKey: "cached_tokens", displayLabel: "Cached tokens", displayUnit: "per 1M tokens", pricingType: "per_unit" as const, unitQuantity: 1_000_000 },
  { metricKey: "image_tokens", displayLabel: "Image tokens", displayUnit: "per 1M tokens", pricingType: "per_unit" as const, unitQuantity: 1_000_000 },
  { metricKey: "requests", displayLabel: "Requests", displayUnit: "per request", pricingType: "flat" as const, unitQuantity: 1 },
  { metricKey: "search_queries", displayLabel: "Search queries", displayUnit: "per query", pricingType: "flat" as const, unitQuantity: 1 },
];

export function StepDimensions({ onNext, onBack }: StepDimensionsProps) {
  const { register, watch, setValue, formState: { errors } } = useFormContext<WizardFormData>();
  const { fields, append, remove } = useFieldArray<WizardFormData>({ name: "dimensions" });
  const source = watch("source");
  const pricingPattern = watch("pricingPattern");
  const dimensions = watch("dimensions");

  const existingKeys = new Set(dimensions?.map((d) => d.metricKey) || []);

  const addDimension = (preset?: typeof QUICK_ADD_SUGGESTIONS[0]) => {
    append({
      metricKey: preset?.metricKey || "",
      pricingType: preset?.pricingType || "per_unit",
      unitPriceMicros: 0,
      unitQuantity: preset?.unitQuantity || 1_000_000,
      displayLabel: preset?.displayLabel || "",
      displayUnit: preset?.displayUnit || "",
      displayPrice: "",
    });
  };

  const duplicateDimension = (index: number) => {
    const dim = dimensions[index];
    append({ ...dim, metricKey: `${dim.metricKey}_copy` });
  };

  const breadcrumbSource = source === "template" ? "From template" : "Custom card";
  const breadcrumbPattern = pricingPattern === "token" ? "Pre-seeded: token-based" : pricingPattern === "per_request" ? "Pre-seeded: per-request" : "";

  return (
    <div className="space-y-8">
      <div>
        <div className="flex gap-2 mb-3">
          <Badge variant="outline">{breadcrumbSource}</Badge>
          {breadcrumbPattern && <Badge variant="secondary">{breadcrumbPattern}</Badge>}
        </div>
        <h2 className="text-2xl font-bold">Define cost dimensions</h2>
        <p className="mt-2 text-muted-foreground">
          Each dimension is one line item on your cost breakdown.
          {dimensions.length > 0 && " Adjust the prices and add more as needed."}
        </p>
      </div>

      <div className="space-y-4">
        {fields.map((field, index) => (
          <Card key={field.id}>
            <CardContent className="p-6 space-y-4">
              <div className="flex items-center justify-between">
                <h4 className="font-semibold">Dimension {index + 1}</h4>
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={() => duplicateDimension(index)}>
                    Duplicate
                  </Button>
                  <Button variant="outline" size="sm" onClick={() => remove(index)} disabled={fields.length === 1}>
                    Remove
                  </Button>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Metric key</Label>
                  <Input
                    {...register(`dimensions.${index}.metricKey`)}
                    className="font-mono"
                    placeholder="e.g. input_tokens"
                  />
                  <p className="text-xs text-muted-foreground">Must match the key your SDK sends</p>
                </div>

                <div className="space-y-2">
                  <Label>Pricing type</Label>
                  <div className="flex rounded-md border">
                    {(["per_unit", "flat"] as const).map((type) => (
                      <button
                        key={type}
                        type="button"
                        className={cn(
                          "flex-1 px-3 py-2 text-sm font-medium transition-colors",
                          watch(`dimensions.${index}.pricingType`) === type
                            ? "bg-foreground text-background"
                            : "hover:bg-muted",
                        )}
                        onClick={() => {
                          setValue(`dimensions.${index}.pricingType`, type);
                          setValue(`dimensions.${index}.unitQuantity`, type === "flat" ? 1 : 1_000_000);
                        }}
                      >
                        {type === "per_unit" ? "Per unit" : "Flat"}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="space-y-2">
                  <Label>Unit price ($)</Label>
                  <Input
                    type="number"
                    step="any"
                    {...register(`dimensions.${index}.unitPriceMicros`, { valueAsNumber: true })}
                    placeholder="0.00000010"
                    className="font-mono"
                  />
                  <p className="text-xs text-muted-foreground">
                    {watch(`dimensions.${index}.pricingType`) === "flat"
                      ? "Price per event"
                      : "Price per single token"}
                  </p>
                </div>
              </div>

              <div className="grid gap-4 md:grid-cols-3">
                <div className="space-y-2">
                  <Label>Display label</Label>
                  <Input
                    {...register(`dimensions.${index}.displayLabel`)}
                    placeholder="e.g. Input tokens"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Display unit</Label>
                  <Input
                    {...register(`dimensions.${index}.displayUnit`)}
                    placeholder="e.g. per 1M tokens"
                  />
                </div>
                <div className="space-y-2">
                  <Label>Display price</Label>
                  <Input
                    {...register(`dimensions.${index}.displayPrice`)}
                    placeholder="e.g. $0.10"
                  />
                  <p className="text-xs text-muted-foreground">Shown on dashboard. Auto-calculated if blank.</p>
                </div>
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      <Card className="border-dashed">
        <CardContent className="p-6 text-center space-y-3">
          <Button variant="outline" onClick={() => addDimension()}>
            + Add dimension
          </Button>
          <div className="flex flex-wrap justify-center gap-2">
            {QUICK_ADD_SUGGESTIONS.filter((s) => !existingKeys.has(s.metricKey)).map((s) => (
              <Badge
                key={s.metricKey}
                variant="outline"
                className="cursor-pointer hover:bg-muted"
                onClick={() => addDimension(s)}
              >
                + {s.displayLabel.toLowerCase()}
              </Badge>
            ))}
          </div>
        </CardContent>
      </Card>

      {dimensions.length > 0 && <CostTester />}

      <div className="flex justify-between border-t pt-6">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <div className="flex gap-2">
          <Button variant="outline" onClick={onBack}>Save draft</Button>
          <Button onClick={onNext} disabled={dimensions.length === 0}>
            Review & test
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify in browser**

Navigate through wizard to Step 3. Add/remove dimensions, use quick-add suggestions, verify cost tester updates live.

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: add wizard Step 3 (Dimensions) with live cost tester"
```

---

### Task 11: Wizard Step 4 (Review & Test) + Sanity Checks

**Files:**
- Modify: `src/components/metering/wizard/step-review.tsx`
- Create: `src/components/metering/wizard/sanity-checks.tsx`

- [ ] **Step 1: Create SanityChecks component**

```typescript
// src/components/metering/wizard/sanity-checks.tsx
import { useFormContext } from "react-hook-form";
import { Check, AlertTriangle } from "lucide-react";
import type { WizardFormData } from "./new-card-wizard";

export function SanityChecks() {
  const { watch } = useFormContext<WizardFormData>();
  const dimensions = watch("dimensions") || [];
  const cardId = watch("cardId");

  const checks = [
    {
      label: "All dimensions have non-zero prices",
      pass: dimensions.every((d) => d.unitPriceMicros > 0),
    },
    {
      label: "No duplicate metric keys",
      pass: new Set(dimensions.map((d) => d.metricKey)).size === dimensions.length,
    },
    {
      label: "Unit prices are within expected ranges",
      pass: dimensions.every((d) => d.unitPriceMicros <= 100_000_000),
    },
    {
      label: "Card ID is valid and unique",
      pass: /^[a-z0-9_-]+$/.test(cardId),
    },
  ];

  // Check if one dimension dominates cost (>90%)
  const totalCost = dimensions.reduce((sum, d) => sum + d.unitPriceMicros, 0);
  const maxCost = Math.max(...dimensions.map((d) => d.unitPriceMicros));
  const dominated = totalCost > 0 && maxCost / totalCost > 0.9 && dimensions.length > 1;

  return (
    <div className="space-y-2">
      {checks.map((check) => (
        <div key={check.label} className="flex items-center gap-2">
          {check.pass ? (
            <Check className="size-4 text-green-600" />
          ) : (
            <AlertTriangle className="size-4 text-amber-500" />
          )}
          <span className="text-sm">{check.label}</span>
        </div>
      ))}
      {dominated && (
        <div className="flex items-center gap-2">
          <AlertTriangle className="size-4 text-amber-500" />
          <span className="text-sm">Cost dominated by one dimension (see sanity check above)</span>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 2: Implement Step 4 — Review & Test**

Replace the placeholder in `step-review.tsx`:

```typescript
// src/components/metering/wizard/step-review.tsx
import { useState } from "react";
import { useFormContext } from "react-hook-form";
import { useNavigate } from "@tanstack/react-router";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { toast } from "sonner";
import { CostTester } from "./cost-tester";
import { SanityChecks } from "./sanity-checks";
import { productTags } from "@/lib/mock-data/metering";
import { cn } from "@/lib/utils";
import type { WizardFormData } from "./new-card-wizard";

interface StepReviewProps {
  onBack: () => void;
  goToStep: (step: number) => void;
}

export function StepReview({ onBack, goToStep }: StepReviewProps) {
  const { watch, setValue } = useFormContext<WizardFormData>();
  const navigate = useNavigate();
  const [isActivating, setIsActivating] = useState(false);

  const name = watch("name");
  const provider = watch("provider");
  const cardId = watch("cardId");
  const dimensions = watch("dimensions") || [];
  const productTag = watch("productTag");

  const handleActivate = async () => {
    setIsActivating(true);
    // Simulate API call delay
    await new Promise((resolve) => setTimeout(resolve, 1000));
    setIsActivating(false);
    toast.success(`Pricing card "${name}" activated successfully`);
    navigate({ to: "/metering/pricing" });
  };

  return (
    <div className="space-y-8">
      <div>
        <h2 className="text-2xl font-bold">Review and test</h2>
        <p className="mt-2 text-muted-foreground">
          Verify your configuration, run a test event to confirm costs calculate correctly, then activate when ready.
        </p>
      </div>

      {/* Card Summary */}
      <Card>
        <CardContent className="p-6 space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <h3 className="text-lg font-semibold">{name}</h3>
              <Badge variant="secondary">Draft v1</Badge>
            </div>
            <Button variant="outline" size="sm" onClick={() => goToStep(1)}>
              Edit details
            </Button>
          </div>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <span>{provider}</span>
            <span className="font-mono bg-muted px-1.5 py-0.5 rounded text-xs">{cardId}</span>
          </div>
          <Separator />
          <div className="flex items-center justify-between">
            <h4 className="font-medium">Cost dimensions ({dimensions.length})</h4>
            <Button variant="outline" size="sm" onClick={() => goToStep(2)}>
              Edit dimensions
            </Button>
          </div>
          <div className="space-y-2">
            {dimensions.map((dim) => (
              <div key={dim.metricKey} className="flex items-center justify-between text-sm">
                <span className="font-mono">{dim.metricKey}</span>
                <div className="flex items-center gap-4 text-muted-foreground">
                  <span>{dim.pricingType === "flat" ? "flat" : "per unit"}</span>
                  <span>{dim.displayUnit || (dim.unitQuantity === 1 ? "per event" : `per ${(dim.unitQuantity / 1_000_000).toFixed(0)}M`)}</span>
                  <span className="font-semibold text-foreground">
                    {dim.displayPrice || `$${(dim.unitPriceMicros / 1_000_000).toFixed(dim.unitPriceMicros < 1000 ? 6 : 2)}`}
                  </span>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>

      {/* Dry-run simulator */}
      <CostTester showProjections />

      {/* Sanity checks */}
      <Card>
        <CardContent className="p-6">
          <SanityChecks />
        </CardContent>
      </Card>

      {/* Assign to product */}
      <Card>
        <CardContent className="p-6 space-y-3">
          <h4 className="font-semibold">Assign to product</h4>
          <p className="text-sm text-muted-foreground">
            Group this card under a product for dashboard cost aggregation. You can change this anytime.
          </p>
          <div className="flex flex-wrap gap-2">
            {productTags.map((tag) => (
              <Badge
                key={tag}
                variant={productTag === tag ? "default" : "outline"}
                className="cursor-pointer"
                onClick={() => setValue("productTag", productTag === tag ? "" : tag)}
              >
                {tag}
              </Badge>
            ))}
            <Badge variant="outline" className="cursor-pointer">
              + Create new product
            </Badge>
          </div>
        </CardContent>
      </Card>

      {/* Footer */}
      <div className="flex justify-between border-t pt-6">
        <Button variant="outline" onClick={onBack}>Back</Button>
        <div className="flex gap-2">
          <Button
            variant="outline"
            onClick={() => {
              toast.info("Draft saved (not persisted in this prototype)");
              navigate({ to: "/metering/pricing" });
            }}
          >
            Save draft
          </Button>
          <Button onClick={handleActivate} disabled={isActivating}>
            {isActivating ? "Activating..." : "Activate"}
          </Button>
        </div>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Verify full wizard flow in browser**

Navigate through all 4 steps: Source → Details → Dimensions → Review & Test. Verify:
- Template selection pre-fills fields
- Card preview updates
- Dimensions can be added/removed/duplicated
- Cost tester shows live calculations
- Sanity checks show pass/fail
- "Activate" shows loading state and redirects with toast

- [ ] **Step 4: Commit**

```bash
git add -A && git commit -m "feat: add wizard Step 4 (Review & test) with sanity checks"
```

---

## Chunk 4: Cost Dashboard

### Task 12: Cost Dashboard — Route, Stats, Chart

**Files:**
- Create: `src/routes/_authenticated/metering/dashboard.tsx`
- Create: `src/components/metering/dashboard/cost-dashboard-page.tsx`
- Create: `src/components/metering/dashboard/cost-stats.tsx`
- Create: `src/components/metering/dashboard/cost-chart.tsx`
- Create: `src/components/metering/dashboard/dashboard-empty-state.tsx`

- [ ] **Step 1: Create CostStats component**

```typescript
// src/components/metering/dashboard/cost-stats.tsx
import { StatCard } from "@/components/shared/stat-card";
import { formatCostMicros, formatEventCount, formatPercentChange } from "@/lib/format";
import { mockAnalyticsStats } from "@/lib/mock-data/metering";

export function CostStats() {
  const s = mockAnalyticsStats;

  return (
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
      <StatCard
        label="Total cost (30d)"
        value={formatCostMicros(s.totalCostMicros)}
        subtitle={`${formatPercentChange(s.totalCostMicros, s.prevPeriodTotalCostMicros)} vs prev 30d`}
        subtitleColor="green"
      />
      <StatCard
        label="Total events"
        value={formatEventCount(s.totalEvents)}
        subtitle={`${formatPercentChange(s.totalEvents, s.prevPeriodTotalEvents)} vs prev 30d`}
        subtitleColor="green"
      />
      <StatCard
        label="Avg cost / event"
        value={formatCostMicros(s.avgCostPerEventMicros)}
        subtitle={`${formatPercentChange(s.avgCostPerEventMicros, s.prevPeriodAvgCostMicros)} vs prev 30d`}
        subtitleColor="green"
      />
      <StatCard
        label="Avg daily cost"
        value={formatCostMicros(s.avgDailyCostMicros)}
        subtitle={`Typical range: ${s.typicalDailyRange}`}
      />
    </div>
  );
}
```

- [ ] **Step 2: Create CostChart component**

```typescript
// src/components/metering/dashboard/cost-chart.tsx
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  Legend,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { mockDailyCosts } from "@/lib/mock-data/metering";

const COLORS = {
  "Property search": "oklch(0.62 0.17 250)",
  "Doc summariser": "oklch(0.60 0.12 300)",
  "Content gen": "oklch(0.55 0.12 170)",
};

export function CostChart() {
  const chartData = mockDailyCosts.map((day) => ({
    date: day.date.slice(5), // "MM-DD"
    ...Object.fromEntries(
      Object.entries(day.products).map(([k, v]) => [k, v / 1_000_000]),
    ),
  }));

  const productKeys = Object.keys(mockDailyCosts[0]?.products || {});

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle>Cost over time</CardTitle>
        <Button variant="outline" size="sm">View details</Button>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={300}>
          <AreaChart data={chartData}>
            <CartesianGrid strokeDasharray="3 3" stroke="oklch(0.90 0.01 85)" />
            <XAxis
              dataKey="date"
              tick={{ fontSize: 12 }}
              tickFormatter={(v) => {
                const [m, d] = v.split("-");
                const months = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
                return `${parseInt(d)} ${months[parseInt(m)]}`;
              }}
            />
            <YAxis
              tick={{ fontSize: 12 }}
              tickFormatter={(v) => `$${v}`}
            />
            <Tooltip
              formatter={(value: number) => [`$${value.toFixed(2)}`, undefined]}
              labelFormatter={(label) => `Date: ${label}`}
            />
            <Legend />
            {productKeys.map((key) => (
              <Area
                key={key}
                type="monotone"
                dataKey={key}
                stackId="1"
                stroke={COLORS[key as keyof typeof COLORS] || "#888"}
                fill={COLORS[key as keyof typeof COLORS] || "#888"}
                fillOpacity={0.3}
              />
            ))}
          </AreaChart>
        </ResponsiveContainer>
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 3: Create DashboardEmptyState component**

```typescript
// src/components/metering/dashboard/dashboard-empty-state.tsx
import { BarChart3 } from "lucide-react";

export function DashboardEmptyState() {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border border-dashed p-12 text-center">
      <BarChart3 className="size-12 text-muted-foreground/50" />
      <h3 className="mt-4 text-lg font-semibold">No usage data yet</h3>
      <p className="mt-2 max-w-sm text-sm text-muted-foreground">
        Start sending usage events via the SDK to see cost analytics here.
      </p>
    </div>
  );
}
```

- [ ] **Step 4: Create CostDashboardPage**

```typescript
// src/components/metering/dashboard/cost-dashboard-page.tsx
import { useState } from "react";
import { Button } from "@/components/ui/button";
import { CostStats } from "./cost-stats";
import { CostChart } from "./cost-chart";
import { CostBreakdowns } from "./cost-breakdowns";
import { CostByDimension } from "./cost-by-dimension";
import { RecentEvents } from "./recent-events";
import { cn } from "@/lib/utils";

const PERIODS = ["7d", "30d", "90d", "YTD"] as const;

export function CostDashboardPage() {
  const [period, setPeriod] = useState<string>("30d");

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">Cost dashboard</h1>
        <div className="flex items-center gap-2">
          <div className="flex rounded-md border">
            {PERIODS.map((p) => (
              <button
                key={p}
                className={cn(
                  "px-3 py-1.5 text-sm font-medium transition-colors",
                  period === p ? "bg-foreground text-background" : "hover:bg-muted",
                )}
                onClick={() => setPeriod(p)}
              >
                {p}
              </button>
            ))}
          </div>
          <Button variant="outline">All products</Button>
          <Button variant="outline">Export</Button>
        </div>
      </div>

      <CostStats />
      <CostChart />
      <CostBreakdowns />
      <CostByDimension />
      <RecentEvents />
    </div>
  );
}
```

- [ ] **Step 5: Create placeholder files for breakdowns and tables**

Create minimal placeholders so the dashboard compiles:

```typescript
// src/components/metering/dashboard/cost-breakdowns.tsx
export function CostBreakdowns() {
  return <div>Cost breakdowns (coming next)</div>;
}

// src/components/metering/dashboard/cost-by-dimension.tsx
export function CostByDimension() {
  return <div>Cost by dimension (coming next)</div>;
}

// src/components/metering/dashboard/recent-events.tsx
export function RecentEvents() {
  return <div>Recent events (coming next)</div>;
}
```

- [ ] **Step 6: Create dashboard route**

```typescript
// src/routes/_authenticated/metering/dashboard.tsx
import { createFileRoute } from "@tanstack/react-router";
import { CostDashboardPage } from "@/components/metering/dashboard/cost-dashboard-page";

export const Route = createFileRoute("/_authenticated/metering/dashboard")({
  component: CostDashboardPage,
});
```

- [ ] **Step 7: Verify in browser**

Navigate to `/metering/dashboard`. Should see stats row, area chart with mock data, period toggles, and placeholder sections.

- [ ] **Step 8: Commit**

```bash
git add -A && git commit -m "feat: add cost dashboard with stats and area chart"
```

---

### Task 13: Cost Dashboard — Breakdowns, Tables

**Files:**
- Modify: `src/components/metering/dashboard/cost-breakdowns.tsx`
- Modify: `src/components/metering/dashboard/cost-by-dimension.tsx`
- Modify: `src/components/metering/dashboard/recent-events.tsx`

- [ ] **Step 1: Implement CostBreakdowns**

Side-by-side cards showing cost by product and cost by pricing card.

```typescript
// src/components/metering/dashboard/cost-breakdowns.tsx
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatCostMicros } from "@/lib/format";
import { mockCostByProduct, mockCostByCard, type MockCostBreakdown } from "@/lib/mock-data/metering";

const COLORS = ["oklch(0.62 0.17 250)", "oklch(0.60 0.12 300)", "oklch(0.55 0.12 170)", "oklch(0.70 0.16 55)", "oklch(0.65 0.02 75)"];

function BreakdownList({ items }: { items: MockCostBreakdown[] }) {
  const maxCost = Math.max(...items.map((i) => i.costMicros));
  return (
    <div className="space-y-3">
      {items.map((item, i) => (
        <div key={item.name} className="flex items-center gap-3">
          <span
            className="size-2.5 shrink-0 rounded-sm"
            style={{ background: COLORS[i % COLORS.length] }}
          />
          <span className="flex-1 text-sm">{item.name}</span>
          <div className="w-24 h-2 rounded-full bg-muted overflow-hidden">
            <div
              className="h-full rounded-full"
              style={{
                width: `${(item.costMicros / maxCost) * 100}%`,
                background: COLORS[i % COLORS.length],
              }}
            />
          </div>
          <span className="w-16 text-right text-sm font-medium">
            {formatCostMicros(item.costMicros)}
          </span>
          <span className="w-10 text-right text-sm text-muted-foreground">
            {item.percentage}%
          </span>
        </div>
      ))}
    </div>
  );
}

export function CostBreakdowns() {
  return (
    <div className="grid gap-4 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cost by product</CardTitle>
        </CardHeader>
        <CardContent>
          <BreakdownList items={mockCostByProduct} />
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Cost by pricing card</CardTitle>
        </CardHeader>
        <CardContent>
          <BreakdownList items={mockCostByCard} />
        </CardContent>
      </Card>
    </div>
  );
}
```

- [ ] **Step 2: Implement CostByDimension**

```typescript
// src/components/metering/dashboard/cost-by-dimension.tsx
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Button } from "@/components/ui/button";
import { formatCostMicros } from "@/lib/format";
import { mockDimensionCosts, type MockDimensionCost } from "@/lib/mock-data/metering";

const columns: ColumnDef<MockDimensionCost>[] = [
  {
    accessorKey: "dimension",
    header: "Dimension",
    cell: ({ row }) => (
      <span className="font-mono text-sm">{row.getValue("dimension")}</span>
    ),
  },
  { accessorKey: "card", header: "Card" },
  { accessorKey: "volume", header: "Volume (30d)" },
  {
    accessorKey: "costMicros",
    header: () => <span className="text-right block">Cost</span>,
    cell: ({ row }) => (
      <span className="text-right block font-medium">
        {formatCostMicros(row.getValue("costMicros"))}
      </span>
    ),
  },
  {
    accessorKey: "sharePercent",
    header: () => <span className="text-right block">Share</span>,
    cell: ({ row }) => (
      <span className="text-right block text-muted-foreground">
        {row.getValue<number>("sharePercent")}%
      </span>
    ),
  },
];

export function CostByDimension() {
  const table = useReactTable({
    data: mockDimensionCosts,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Cost by dimension</h2>
        <Button variant="outline" size="sm">View all</Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id}>
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
```

- [ ] **Step 3: Implement RecentEvents**

```typescript
// src/components/metering/dashboard/recent-events.tsx
import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  type ColumnDef,
} from "@tanstack/react-table";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatRelativeDate } from "@/lib/format";
import { mockRecentEvents, type MockRecentEvent } from "@/lib/mock-data/metering";

const columns: ColumnDef<MockRecentEvent>[] = [
  {
    accessorKey: "time",
    header: "Time",
    cell: ({ row }) => (
      <span className="text-muted-foreground">{formatRelativeDate(row.getValue("time"))}</span>
    ),
  },
  { accessorKey: "cardName", header: "Card" },
  {
    accessorKey: "productTag",
    header: "Product",
    cell: ({ row }) => (
      <Badge variant="outline" className="text-xs">
        {row.getValue("productTag")}
      </Badge>
    ),
  },
  {
    accessorKey: "dimensions",
    header: "Dimensions",
    cell: ({ row }) => (
      <span className="font-mono text-xs text-muted-foreground">
        {row.getValue("dimensions")}
      </span>
    ),
  },
  {
    accessorKey: "costMicros",
    header: () => <span className="text-right block">Cost</span>,
    cell: ({ row }) => (
      <span className="text-right block font-semibold font-mono">
        ${(row.getValue<number>("costMicros") / 1_000_000).toFixed(4)}
      </span>
    ),
  },
];

export function RecentEvents() {
  const table = useReactTable({
    data: mockRecentEvents,
    columns,
    getCoreRowModel: getCoreRowModel(),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <h2 className="text-lg font-semibold">Recent events</h2>
        <Button variant="outline" size="sm">View all events</Button>
      </div>
      <div className="rounded-md border">
        <Table>
          <TableHeader>
            {table.getHeaderGroups().map((hg) => (
              <TableRow key={hg.id}>
                {hg.headers.map((h) => (
                  <TableHead key={h.id}>
                    {h.isPlaceholder ? null : flexRender(h.column.columnDef.header, h.getContext())}
                  </TableHead>
                ))}
              </TableRow>
            ))}
          </TableHeader>
          <TableBody>
            {table.getRowModel().rows.map((row) => (
              <TableRow key={row.id}>
                {row.getVisibleCells().map((cell) => (
                  <TableCell key={cell.id}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Verify full dashboard in browser**

Navigate to `/metering/dashboard`. Should see all sections: stats, chart, breakdowns, dimension table, recent events.

- [ ] **Step 5: Commit**

```bash
git add -A && git commit -m "feat: add cost dashboard breakdowns, dimension table, and recent events"
```

---

## Summary

| Task | What it builds | Files |
|------|---------------|-------|
| 1 | Nav config + route cleanup | 3 files |
| 2 | Mock data layer | 1 file |
| 3 | Format utilities | 1 file (modify) |
| 4 | Shared StatCard | 1 file |
| 5 | Shared Stepper | 1 file |
| 6 | Pricing + analytics hooks | 2 files |
| 7 | Pricing cards page | 5 files |
| 8 | Wizard container + Step 1 | 6 files |
| 9 | Wizard Step 2 + card preview | 2 files |
| 10 | Wizard Step 3 + cost tester | 2 files |
| 11 | Wizard Step 4 + sanity checks | 2 files |
| 12 | Dashboard: stats, chart, route | 6 files |
| 13 | Dashboard: breakdowns, tables | 3 files |

**Total: 13 tasks, ~35 files created/modified**
