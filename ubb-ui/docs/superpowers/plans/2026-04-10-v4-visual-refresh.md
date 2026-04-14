# v4 Visual Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **GIT POLICY:** Per `CLAUDE.md`, the user handles all git operations. Never run `git commit`, `git push`, or `git checkout`. At each "Checkpoint" step, report progress to the user and suggest a commit message — do not create the commit.

**Goal:** Adopt the warm-stone + terracotta design language on the dashboard page and across the app shell by rewiring design tokens, swapping fonts, and rebuilding the dashboard components around reusable primitives (`DeltaPill`, `Sparkline`, `ChartCard`, etc.).

**Architecture:** Two layers of tokens (shadcn vars in `:root` drive the shell; named palette tokens in `@theme inline` expose Tailwind utilities). Dashboard-specific visuals are built as composable primitives in `src/components/shared/` so other features can reuse them later. Existing file names are preserved — only internals are rewritten — to minimize import churn.

**Tech Stack:** React 19, TypeScript 5.9, Tailwind v4, shadcn/ui, recharts 3, Vitest + React Testing Library.

**Spec reference:** `docs/superpowers/specs/2026-04-10-v4-visual-refresh-design.md`

**Target mockups:**
- `ui-mockups/v2/ubb-dashboard-v4.html` — dashboard layout to match
- `ui-mockups/ubb-design-system.html` — palette + typography reference

---

## Task 1: Install font packages, drop Geist

**Files:**
- Modify: `package.json`
- Modify: `pnpm-lock.yaml` (via install)

- [ ] **Step 1: Remove Geist, add DM Sans + Cormorant + DM Mono**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && \
pnpm remove @fontsource-variable/geist && \
pnpm add @fontsource-variable/dm-sans @fontsource/cormorant @fontsource/dm-mono
```

Expected: `package.json` no longer contains `@fontsource-variable/geist`; now lists the three new packages in `dependencies`.

- [ ] **Step 2: Sanity check**

Run:
```bash
grep -E "dm-sans|cormorant|dm-mono|geist" /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui/package.json
```
Expected: three matches for the new fonts, zero for `geist`.

- [ ] **Step 3: Checkpoint**

Stop and report: **Task 1 complete — font packages swapped.** Suggest commit message: `chore(deps): replace geist with dm-sans + cormorant + dm-mono`.

---

## Task 2: Rewrite design tokens in `app.css`

**Files:**
- Modify: `src/styles/app.css`

This task rewires both layers — shadcn vars at `:root` and the named palette inside `@theme inline`. It is the only task that touches this file.

- [ ] **Step 1: Replace the file contents**

Overwrite `src/styles/app.css` with:

```css
@import "tailwindcss";
@import "tw-animate-css";
@import "shadcn/tailwind.css";
@import "@fontsource-variable/dm-sans";
@import "@fontsource/cormorant/700.css";
@import "@fontsource/dm-mono/400.css";
@import "@fontsource/dm-mono/500.css";

@custom-variant dark (&:is(.dark *));

:root {
  /* Shadcn base (drives all shadcn components app-wide).
     Hex values sourced from docs/superpowers/specs/2026-04-10-v4-visual-refresh-design.md §3.1. */
  --background:           #f4f2ee;
  --foreground:           #2e2520;
  --card:                 #fcfaf7;
  --card-foreground:      #2e2520;
  --popover:              #fcfaf7;
  --popover-foreground:   #2e2520;
  --primary:              #2e2520;
  --primary-foreground:   #fcfaf7;
  --secondary:            #ece8e2;
  --secondary-foreground: #2e2520;
  --muted:                #ece8e2;
  --muted-foreground:     #6d6358;
  --accent:               #f8f0e8;
  --accent-foreground:    #5a3520;
  --destructive:          #b84848;
  --border:               #e2ddd5;
  --input:                #e2ddd5;
  --ring:                 #a16a4a;
  --radius:               0.625rem;

  --sidebar:                     #fcfaf7;
  --sidebar-foreground:          #2e2520;
  --sidebar-primary:             #2e2520;
  --sidebar-primary-foreground:  #fcfaf7;
  --sidebar-accent:              #f8f0e8;
  --sidebar-accent-foreground:   #5a3520;
  --sidebar-border:              #e2ddd5;
  --sidebar-ring:                #a16a4a;
}

.dark {
  --background:           #1c1814;
  --foreground:           #f4f2ee;
  --card:                 #24201b;
  --card-foreground:      #f4f2ee;
  --popover:              #24201b;
  --popover-foreground:   #f4f2ee;
  --primary:              #f4f2ee;
  --primary-foreground:   #1c1814;
  --secondary:            #2a2520;
  --secondary-foreground: #f4f2ee;
  --muted:                #2a2520;
  --muted-foreground:     #a9a095;
  --accent:               #3a2a20;
  --accent-foreground:    #f4e0cc;
  --destructive:          #cf6060;
  --border:               rgba(255,255,255,0.08);
  --input:                rgba(255,255,255,0.12);
  --ring:                 #c08060;

  --sidebar:                     #1c1814;
  --sidebar-foreground:          #f4f2ee;
  --sidebar-primary:             #f4f2ee;
  --sidebar-primary-foreground:  #1c1814;
  --sidebar-accent:              #3a2a20;
  --sidebar-accent-foreground:   #f4e0cc;
  --sidebar-border:              rgba(255,255,255,0.08);
  --sidebar-ring:                #c08060;
}

@theme inline {
  /* Fonts */
  --font-sans:  'DM Sans Variable', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-serif: 'Cormorant', Georgia, serif;
  --font-mono:  'DM Mono', 'SF Mono', ui-monospace, monospace;

  /* Shadcn color aliases (pipe-through) */
  --color-sidebar-ring: var(--sidebar-ring);
  --color-sidebar-border: var(--sidebar-border);
  --color-sidebar-accent-foreground: var(--sidebar-accent-foreground);
  --color-sidebar-accent: var(--sidebar-accent);
  --color-sidebar-primary-foreground: var(--sidebar-primary-foreground);
  --color-sidebar-primary: var(--sidebar-primary);
  --color-sidebar-foreground: var(--sidebar-foreground);
  --color-sidebar: var(--sidebar);
  --color-ring: var(--ring);
  --color-input: var(--input);
  --color-border: var(--border);
  --color-destructive: var(--destructive);
  --color-accent-foreground: var(--accent-foreground);
  --color-accent: var(--accent);
  --color-muted-foreground: var(--muted-foreground);
  --color-muted: var(--muted);
  --color-secondary-foreground: var(--secondary-foreground);
  --color-secondary: var(--secondary);
  --color-primary-foreground: var(--primary-foreground);
  --color-primary: var(--primary);
  --color-popover-foreground: var(--popover-foreground);
  --color-popover: var(--popover);
  --color-card-foreground: var(--card-foreground);
  --color-card: var(--card);
  --color-foreground: var(--foreground);
  --color-background: var(--background);

  /* Named design-system palette (v4). All hex taken from
     ui-mockups/ubb-design-system.html and ui-mockups/v2/ubb-dashboard-v4.html. */
  --color-bg-page:        #f4f2ee;
  --color-bg-subtle:      #ece8e2;
  --color-bg-surface:     #fcfaf7;
  --color-bg-raised:      #ffffff;
  --color-border-mid:     #d4cdc2;
  --color-border-strong:  #b5ad9e;
  --color-text-primary:   #2e2520;
  --color-text-secondary: #6d6358;
  --color-text-muted:     #9a8e80;
  --color-text-inverse:   #fcfaf7;

  --color-accent-base:    #a16a4a;
  --color-accent-hover:   #b07855;
  --color-accent-dark:    #855638;
  --color-accent-light:   #f0e0d2;
  --color-accent-ghost:   #f8f0e8;
  --color-accent-text:    #5a3520;
  --color-accent-border:  #d4ad90;

  --color-blue:           #4a7fa8;
  --color-blue-light:     #eaf1f7;
  --color-blue-text:      #1e4060;
  --color-blue-border:    #b0cce0;

  --color-red:            #b84848;
  --color-red-light:      #faecec;
  --color-red-text:       #6a1e1e;
  --color-red-border:     #e0a0a0;

  --color-green:          #3a8050;
  --color-green-light:    #eaf5ee;
  --color-green-text:     #1a4a28;
  --color-green-border:   #a0cca8;

  --color-amber:          #a07020;
  --color-amber-light:    #fdf4e4;
  --color-amber-text:     #5a3e10;
  --color-amber-border:   #e0c070;

  --color-purple:         #6a5aaa;
  --color-purple-light:   #f0eefa;
  --color-purple-text:    #3a2a6a;
  --color-purple-border:  #c0b0e0;

  --color-stone:          #c2a68e;
  --color-stone-light:    #ede4da;

  /* Legacy feature tokens aliased onto new palette so existing callers
     (billing, customers, reconciliation, etc.) keep compiling without
     touching every file. See spec §3.2. */
  --color-success-dark:   var(--color-green-text);
  --color-danger-dark:    var(--color-red-text);
  --color-purple-bg:      var(--color-purple-light);
  --color-purple-fg:      var(--color-purple-text);
  --color-chart-margin:   var(--color-accent-base);
  --color-chart-loss:     var(--color-red);
  --color-chart-alloc:    var(--color-purple);

  /* Tailwind radii */
  --radius-sm: calc(var(--radius) * 0.6);
  --radius-md: calc(var(--radius) * 0.8);
  --radius-lg: var(--radius);
  --radius-xl: calc(var(--radius) * 1.4);
  --radius-2xl: calc(var(--radius) * 1.8);
  --radius-3xl: calc(var(--radius) * 2.2);
  --radius-4xl: calc(var(--radius) * 2.6);

  /* Tight font-size scale for dense stat/table layouts. */
  --text-label: 0.6875rem;  /* 11px */
  --text-muted: 0.625rem;   /* 10px */
  --text-tiny:  0.5625rem;  /*  9px */
}

@layer base {
  * {
    @apply border-border outline-ring/50;
  }
  body {
    @apply bg-background text-foreground text-[13px] leading-snug;
    font-family: var(--font-sans);
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
  }
  html {
    @apply font-sans;
  }
}
```

- [ ] **Step 2: Verify Vite picks up the new imports**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm typecheck 2>&1 | head -30
```
Expected: no errors related to missing CSS. If `typecheck` script doesn't exist, run `pnpm exec tsc -b --noEmit` instead.

- [ ] **Step 3: Visual smoke test (optional)**

Run `pnpm dev` and open the app. The base colors should shift to warm cream/terracotta even though components haven't been updated yet. Kill the dev server before continuing.

- [ ] **Step 4: Checkpoint**

Stop and report: **Task 2 complete — design tokens rewired.** Suggest commit message: `refactor(styles): adopt warm stone + terracotta design tokens`.

---

## Task 3: Extend dashboard types with `sparklines`

**Files:**
- Modify: `src/features/dashboard/api/types.ts`

- [ ] **Step 1: Add `SparklineSet` type + field**

Edit `src/features/dashboard/api/types.ts`. Add above `DashboardData`:

```ts
export interface SparklineSet {
  revenue: number[];
  apiCosts: number[];
  grossMargin: number[];
  marginPct: number[];
  costPerRev: number[];
}
```

And extend `DashboardData`:

```ts
export interface DashboardData {
  stats: StatsData;
  revenueTimeSeries: RevenueTimeSeries[];
  costByProduct: { series: CostSeries[]; data: CostByProductPoint[] };
  costByCard: { series: CostSeries[]; data: CostByProductPoint[] };
  revenueByProduct: ProductBreakdown[];
  marginByProduct: ProductBreakdown[];
  customers: CustomerRow[];
  sparklines: SparklineSet;
}
```

- [ ] **Step 2: Verify type compiles**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: TypeScript errors ONLY inside `mock-data.ts` (missing `sparklines` field). No other feature should complain.

---

## Task 4: Recolor mock data + populate `sparklines`

**Files:**
- Modify: `src/features/dashboard/api/mock-data.ts`

- [ ] **Step 1: Update `productSeries` colors**

Replace the `productSeries` constant with:

```ts
const productSeries: CostSeries[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8" },
  { key: "doc_summariser", label: "Doc summariser", color: "#6a5aaa" },
  { key: "content_gen", label: "Content gen", color: "#b84848" },
];
```

- [ ] **Step 2: Update `cardSeries` colors**

Replace:

```ts
const cardSeries: CostSeries[] = [
  { key: "gemini_2_flash", label: "Gemini 2.0 Flash", color: "#c0392b" },
  { key: "claude_sonnet",  label: "Claude Sonnet",    color: "#4a7fa8" },
  { key: "gpt_4o",         label: "GPT-4o",           color: "#484240" },
  { key: "google_places",  label: "Google Places",    color: "#a16a4a" },
  { key: "serper",         label: "Serper",           color: "#b5ad9e" },
];
```

- [ ] **Step 3: Update `revenueByProduct` + `marginByProduct` colors**

Replace both constants (keep values unchanged — only colors shift):

```ts
const revenueByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8", value: 4631, percentage: 55 },
  { key: "doc_summariser",  label: "Doc summariser",  color: "#6a5aaa", value: 2526, percentage: 38 },
  { key: "content_gen",     label: "Content gen",     color: "#b84848", value: 1263, percentage: 15 },
];

const marginByProduct: ProductBreakdown[] = [
  { key: "property_search", label: "Property search", color: "#4a7fa8", value: 3783, percentage: 81.7 },
  { key: "doc_summariser",  label: "Doc summariser",  color: "#6a5aaa", value: 2252, percentage: 89.2 },
  { key: "content_gen",     label: "Content gen",     color: "#b84848", value: 1138, percentage: 90.1 },
];
```

Note: `revenueByProduct[1].percentage` changes from `30` to `38` to match the mockup.

- [ ] **Step 4: Derive `sparklines` from `revenueTimeSeries`**

Add just above the `export const mockDashboardData = ...` line:

```ts
const sparklines = {
  revenue:     revenueTimeSeries.map((d) => d.revenue),
  apiCosts:    revenueTimeSeries.map((d) => d.apiCosts),
  grossMargin: revenueTimeSeries.map((d) => d.margin),
  marginPct:   revenueTimeSeries.map((d) =>
    Math.round(((d.revenue - d.apiCosts) / d.revenue) * 1000) / 10,
  ),
  costPerRev:  revenueTimeSeries.map((d) =>
    Math.round((d.apiCosts / d.revenue) * 1000) / 1000,
  ),
};
```

- [ ] **Step 5: Add field to `mockDashboardData` export**

Update the export object to include `sparklines`:

```ts
export const mockDashboardData: DashboardData = {
  stats,
  revenueTimeSeries,
  costByProduct: { series: productSeries, data: costByProductData },
  costByCard: { series: cardSeries, data: costByCardData },
  revenueByProduct,
  marginByProduct,
  customers,
  sparklines,
};
```

- [ ] **Step 6: Verify types**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 7: Checkpoint**

Stop and report: **Task 3+4 complete — dashboard data extended with sparklines and recolored.** Suggest commit message: `feat(dashboard): add sparklines data + v4 palette colors to mock data`.

---

## Task 5: Create `DeltaPill` primitive (TDD)

**Files:**
- Create: `src/components/shared/delta-pill.tsx`
- Create: `src/components/shared/delta-pill.test.tsx`

- [ ] **Step 1: Write the failing tests**

Create `src/components/shared/delta-pill.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { DeltaPill } from "./delta-pill";

describe("DeltaPill", () => {
  it("renders the label", () => {
    render(<DeltaPill trend="up">+14.2% vs prev</DeltaPill>);
    expect(screen.getByText("+14.2% vs prev")).toBeInTheDocument();
  });

  it("applies up trend classes", () => {
    render(<DeltaPill trend="up">x</DeltaPill>);
    const pill = screen.getByText("x").closest("span");
    expect(pill?.className).toMatch(/bg-green-light/);
    expect(pill?.className).toMatch(/text-green-text/);
  });

  it("applies down trend classes", () => {
    render(<DeltaPill trend="down">x</DeltaPill>);
    const pill = screen.getByText("x").closest("span");
    expect(pill?.className).toMatch(/bg-red-light/);
    expect(pill?.className).toMatch(/text-red-text/);
  });

  it("applies flat trend classes", () => {
    render(<DeltaPill trend="flat">x</DeltaPill>);
    const pill = screen.getByText("x").closest("span");
    expect(pill?.className).toMatch(/bg-bg-subtle/);
    expect(pill?.className).toMatch(/text-text-muted/);
  });
});
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- delta-pill 2>&1 | tail -20
```
Expected: FAIL — `Cannot find module './delta-pill'`.

- [ ] **Step 3: Implement `DeltaPill`**

Create `src/components/shared/delta-pill.tsx`:

```tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface DeltaPillProps {
  trend: "up" | "down" | "flat";
  children: ReactNode;
  className?: string;
}

const TREND_STYLES: Record<DeltaPillProps["trend"], string> = {
  up:   "bg-green-light text-green-text",
  down: "bg-red-light text-red-text",
  flat: "bg-bg-subtle text-text-muted",
};

export function DeltaPill({ trend, children, className }: DeltaPillProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] font-medium",
        TREND_STYLES[trend],
        className,
      )}
    >
      <TrendIcon trend={trend} />
      {children}
    </span>
  );
}

function TrendIcon({ trend }: { trend: DeltaPillProps["trend"] }) {
  if (trend === "flat") {
    return (
      <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
        <rect x="1" y="3.5" width="6" height="1" fill="currentColor" />
      </svg>
    );
  }
  return (
    <svg width="8" height="8" viewBox="0 0 8 8" aria-hidden="true">
      {trend === "up" ? (
        <path d="M4 1L7 5H1z" fill="currentColor" />
      ) : (
        <path d="M4 7L7 3H1z" fill="currentColor" />
      )}
    </svg>
  );
}
```

- [ ] **Step 4: Run tests and verify they pass**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- delta-pill 2>&1 | tail -20
```
Expected: PASS — all 4 tests green.

---

## Task 6: Create `Sparkline` primitive

**Files:**
- Create: `src/components/shared/sparkline.tsx`
- Create: `src/components/shared/sparkline.test.tsx`

- [ ] **Step 1: Write the failing test**

Create `src/components/shared/sparkline.test.tsx`:

```tsx
import { render } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Sparkline } from "./sparkline";

describe("Sparkline", () => {
  it("renders an svg with a path for non-empty data", () => {
    const { container } = render(
      <Sparkline data={[1, 2, 3, 2, 4]} color="#a16a4a" />,
    );
    // ResponsiveContainer + recharts line renders an SVG path element.
    const svg = container.querySelector("svg");
    expect(svg).not.toBeNull();
  });

  it("returns null for empty data", () => {
    const { container } = render(<Sparkline data={[]} color="#a16a4a" />);
    expect(container.firstChild).toBeNull();
  });
});
```

- [ ] **Step 2: Run the test and verify it fails**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- sparkline 2>&1 | tail -20
```
Expected: FAIL — cannot find module.

- [ ] **Step 3: Implement `Sparkline`**

Create `src/components/shared/sparkline.tsx`:

```tsx
import { Area, AreaChart, ResponsiveContainer } from "recharts";

export interface SparklineProps {
  data: number[];
  color: string;
  height?: number;
  className?: string;
}

export function Sparkline({ data, color, height = 32, className }: SparklineProps) {
  if (data.length === 0) return null;

  const chartData = data.map((value, index) => ({ index, value }));

  return (
    <div className={className} style={{ height, width: "100%" }}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 0, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id={`spark-${color.replace("#", "")}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={color} stopOpacity={0.18} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey="value"
            stroke={color}
            strokeWidth={1.5}
            fill={`url(#spark-${color.replace("#", "")})`}
            isAnimationActive={false}
            dot={false}
            activeDot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  );
}
```

- [ ] **Step 4: Run tests and verify they pass**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- sparkline 2>&1 | tail -20
```
Expected: PASS.

---

## Task 7: Create `Brand` primitive

**Files:**
- Create: `src/components/shared/brand.tsx`

- [ ] **Step 1: Implement `Brand`**

Create `src/components/shared/brand.tsx`:

```tsx
import { cn } from "@/lib/utils";

export interface BrandProps {
  size?: "sm" | "md" | "lg";
  className?: string;
}

const SIZES: Record<NonNullable<BrandProps["size"]>, string> = {
  sm: "text-[16px]",
  md: "text-[21px]",
  lg: "text-[42px]",
};

export function Brand({ size = "md", className }: BrandProps) {
  return (
    <span
      className={cn(
        "font-serif font-bold leading-none tracking-[-0.5px] text-text-primary",
        SIZES[size],
        className,
      )}
      aria-label="ubb"
    >
      ubb<span className="text-accent-base">.</span>
    </span>
  );
}
```

No tests — this is a trivial renderer. Verify it renders in the topbar during Task 11.

---

## Task 8: Create `IconButton` primitive

**Files:**
- Create: `src/components/shared/icon-button.tsx`

- [ ] **Step 1: Implement `IconButton`**

Create `src/components/shared/icon-button.tsx`:

```tsx
import { forwardRef, type ButtonHTMLAttributes } from "react";
import { cn } from "@/lib/utils";

export interface IconButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {}

export const IconButton = forwardRef<HTMLButtonElement, IconButtonProps>(
  function IconButton({ className, children, ...props }, ref) {
    return (
      <button
        ref={ref}
        type="button"
        className={cn(
          "flex h-[30px] w-[30px] items-center justify-center rounded-full",
          "border border-border bg-bg-surface text-text-muted",
          "transition-colors hover:bg-bg-subtle hover:text-text-secondary hover:border-border-mid",
          "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring/40",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
```

No tests — thin wrapper. Usage verified in Task 11.

---

## Task 9: Create `ChartLegend` primitive

**Files:**
- Create: `src/components/shared/chart-legend.tsx`

- [ ] **Step 1: Implement `ChartLegend`**

Create `src/components/shared/chart-legend.tsx`:

```tsx
import { cn } from "@/lib/utils";

export interface ChartLegendItem {
  label: string;
  color: string;
  dashed?: boolean;
}

export interface ChartLegendProps {
  items: ChartLegendItem[];
  variant: "dot" | "line";
  className?: string;
}

export function ChartLegend({ items, variant, className }: ChartLegendProps) {
  return (
    <div className={cn("flex flex-wrap items-center gap-3.5", className)}>
      {items.map((item) => (
        <div key={item.label} className="flex items-center gap-1.5 text-[11px] text-text-muted">
          <Swatch color={item.color} dashed={item.dashed} variant={variant} />
          {item.label}
        </div>
      ))}
    </div>
  );
}

function Swatch({
  color,
  dashed,
  variant,
}: {
  color: string;
  dashed?: boolean;
  variant: "dot" | "line";
}) {
  if (variant === "dot") {
    return (
      <span
        className="block h-[7px] w-[7px] shrink-0 rounded-full"
        style={{ backgroundColor: color }}
      />
    );
  }
  return (
    <span
      className="block h-[2px] w-4 shrink-0 rounded-[1px]"
      style={{
        backgroundColor: dashed ? "transparent" : color,
        borderTop: dashed ? `1.5px dashed ${color}` : undefined,
      }}
    />
  );
}
```

No tests — pure presentational.

---

## Task 10: Create `ChartCard` primitive

**Files:**
- Create: `src/components/shared/chart-card.tsx`

- [ ] **Step 1: Implement `ChartCard`**

Create `src/components/shared/chart-card.tsx`:

```tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface ChartCardProps {
  title: string;
  legend?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
}

export function ChartCard({ title, legend, actions, children, className }: ChartCardProps) {
  return (
    <div
      className={cn(
        "rounded-md border border-border bg-bg-surface p-6 transition-colors",
        "hover:border-border-mid",
        className,
      )}
    >
      <div className="mb-5 flex items-center justify-between gap-4">
        <div className="text-[14px] font-semibold tracking-[-0.15px]">{title}</div>
        {legend ?? null}
        {actions ?? null}
      </div>
      {children}
    </div>
  );
}
```

No tests — pure presentational.

- [ ] **Step 2: Checkpoint**

Stop and report: **Tasks 5–10 complete — 6 shared primitives built (DeltaPill, Sparkline, Brand, IconButton, ChartLegend, ChartCard).** Suggest commit message: `feat(shared): add v4 visual primitives (delta pill, sparkline, brand, icon button, chart card/legend)`.

---

## Task 11: Extend `StatCard` with `raised` variant + trend + sparkline slot

**Files:**
- Modify: `src/components/shared/stat-card.tsx`
- Modify: `src/components/shared/stat-card.test.tsx`

- [ ] **Step 1: Write the new failing tests**

Append to `src/components/shared/stat-card.test.tsx` (inside the existing `describe` block):

```tsx
  it("renders a DeltaPill when trend is set", () => {
    render(
      <StatCard label="Revenue" value="$8,420" trend="up" trendLabel="+14.2% vs prev" />,
    );
    expect(screen.getByText("+14.2% vs prev")).toBeInTheDocument();
  });

  it("renders a sparkline slot when provided", () => {
    render(
      <StatCard
        label="Revenue"
        value="$8,420"
        variant="raised"
        sparkline={<div data-testid="spark" />}
      />,
    );
    expect(screen.getByTestId("spark")).toBeInTheDocument();
  });

  it("applies the raised variant via data attribute", () => {
    render(<StatCard label="Revenue" value="$8,420" variant="raised" />);
    const card = screen.getByText("Revenue").parentElement;
    expect(card).toHaveAttribute("data-variant", "raised");
  });
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- stat-card 2>&1 | tail -30
```
Expected: 3 new tests FAIL (the props don't exist yet); the 4 original tests still PASS.

- [ ] **Step 3: Rewrite `StatCard`**

Replace the contents of `src/components/shared/stat-card.tsx`:

```tsx
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";
import { DeltaPill } from "./delta-pill";

export type StatCardVariant = "muted" | "raised" | "purple";

export interface StatCardProps {
  label: string;
  value: ReactNode;
  /** Legacy prop — colored text delta. Preserved for back-compat. */
  change?: { value: string; positive: boolean };
  /** New: renders a <DeltaPill> with up/down/flat styling. */
  trend?: "up" | "down" | "flat";
  /** Label text inside the delta pill (required when `trend` is set). */
  trendLabel?: string;
  /** New: optional slot rendered below the delta row (sparkline). */
  sparkline?: ReactNode;
  subtitle?: string;
  variant?: StatCardVariant;
  className?: string;
}

/**
 * Shared stat card used across dashboard, billing, and customer mapping.
 *
 * Variants:
 * - `muted`  (default) — quiet bg-accent/50 card used by billing + mapping pages
 * - `raised`            — bordered bg-bg-surface card used by the v4 dashboard KPI grid
 * - `purple`            — muted layout with a purple-tinted value (billing mode)
 */
export function StatCard({
  label,
  value,
  change,
  trend,
  trendLabel,
  sparkline,
  subtitle,
  variant = "muted",
  className,
}: StatCardProps) {
  const isRaised = variant === "raised";

  return (
    <div
      data-variant={variant}
      className={cn(
        isRaised
          ? "rounded-md border border-border bg-bg-surface px-5 pt-[18px] pb-[14px] transition-colors hover:border-border-mid hover:shadow-md"
          : "rounded-lg bg-accent/50 px-3 py-2.5",
        className,
      )}
    >
      <div
        className={cn(
          "text-label text-text-muted",
          isRaised && "mb-1.5 font-medium",
        )}
      >
        {label}
      </div>
      <div
        className={cn(
          isRaised
            ? "mb-1 text-[26px] font-bold leading-[1.15] tracking-[-0.6px]"
            : "mt-1 text-[17px] font-semibold tracking-tight",
          variant === "purple" && "text-purple-fg",
        )}
      >
        {value}
      </div>

      {trend && (
        <DeltaPill trend={trend}>{trendLabel ?? ""}</DeltaPill>
      )}

      {!trend && change && (
        <div
          className={cn(
            "mt-0.5 text-muted",
            change.positive ? "text-success-dark" : "text-danger-dark",
          )}
        >
          {change.positive ? "+" : ""}
          {change.value}
        </div>
      )}

      {subtitle && !change && !trend && (
        <div className="mt-0.5 text-tiny text-text-muted/60">
          {subtitle}
        </div>
      )}

      {sparkline && <div className="-mx-1 mt-2.5 h-8">{sparkline}</div>}
    </div>
  );
}
```

- [ ] **Step 4: Run tests and verify all pass**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test -- stat-card 2>&1 | tail -30
```
Expected: all 7 tests PASS (4 existing + 3 new).

- [ ] **Step 5: Checkpoint**

Stop and report: **Task 11 complete — StatCard extended with raised variant, trend pill, and sparkline slot; back-compat preserved.** Suggest commit message: `feat(shared): extend StatCard with raised variant + trend pill + sparkline slot`.

---

## Task 12: Rewrite `TopBar`

**Files:**
- Modify: `src/components/shared/top-bar.tsx`

- [ ] **Step 1: Rewrite the file**

Replace contents of `src/components/shared/top-bar.tsx`:

```tsx
import type { ReactNode } from "react";
import { API_PROVIDER } from "@/lib/api-provider";
import { Brand } from "./brand";
import { IconButton } from "./icon-button";

interface TopBarProps {
  userSlot?: ReactNode;
}

export function TopBar({ userSlot }: TopBarProps) {
  const isMock = API_PROVIDER === "mock";

  return (
    <header className="flex h-[46px] shrink-0 items-center justify-between border-b border-border bg-bg-surface px-6">
      <div className="flex w-[200px] items-center">
        <Brand size="md" />
      </div>

      <div className="flex items-center gap-2">
        {isMock && (
          <span className="rounded-full border border-accent-border bg-accent-ghost px-2 py-[3px] text-[10px] font-bold uppercase tracking-[0.04em] text-accent-text">
            Mock
          </span>
        )}
        <IconButton aria-label="Appearance">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="8" r="4" />
            <path d="M8 1v2M8 13v2M1 8h2M13 8h2" />
          </svg>
        </IconButton>
        <IconButton aria-label="Account">
          <svg width="13" height="13" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
            <circle cx="8" cy="6" r="3" />
            <path d="M3 14c0-2.5 2-4.5 5-4.5s5 2 5 4.5" />
          </svg>
        </IconButton>
        {userSlot}
      </div>
    </header>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no errors.

---

## Task 13: Rewrite `NavShell` sidebar

**Files:**
- Modify: `src/components/shared/nav-shell.tsx`

- [ ] **Step 1: Replace the file**

Replace contents of `src/components/shared/nav-shell.tsx`:

```tsx
import { Link } from "@tanstack/react-router";
import type { ReactNode } from "react";
import { navSections } from "./nav-config";
import { TopBar } from "./top-bar";
import { useAuth } from "@/features/auth/hooks/use-auth";
import { cn } from "@/lib/utils";

interface NavShellProps {
  children: ReactNode;
  userSlot?: ReactNode;
}

export function NavShell({ children, userSlot }: NavShellProps) {
  const { isBillingMode } = useAuth();

  const visibleSections = navSections.filter(
    (section) =>
      !section.visibleWhen ||
      (section.visibleWhen === "billing" && isBillingMode),
  );

  return (
    <div className="grid h-screen grid-cols-[200px_1fr] grid-rows-[46px_1fr] bg-bg-page">
      {/* Topbar spans full width */}
      <div className="col-span-2 row-start-1">
        <TopBar userSlot={userSlot} />
      </div>

      {/* Sidebar (below topbar, fixed 200px) */}
      <aside className="col-start-1 row-start-2 flex flex-col border-r border-border bg-bg-surface py-4">
        <div className="flex-1 overflow-auto">
          {visibleSections.map((section, sectionIdx) => (
            <div key={section.label ?? sectionIdx} className={cn(sectionIdx > 0 && "mt-1")}>
              {section.label && (
                <div className="px-4 pt-[14px] pb-[5px] text-[9px] font-bold uppercase tracking-[0.08em] text-text-muted">
                  {section.label}
                </div>
              )}
              <div className="flex flex-col px-[6px]">
                {section.items.map((item) => (
                  <Link
                    key={item.url}
                    to={item.url}
                    className="flex items-center gap-2 rounded-[6px] px-2.5 py-[5px] text-[12px] text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
                    activeProps={{
                      className:
                        "flex items-center gap-2 rounded-[6px] px-2.5 py-[5px] text-[12px] bg-accent-ghost text-accent-text font-semibold",
                    }}
                    activeOptions={{ exact: item.url === "/" }}
                  >
                    <item.icon className="h-3.5 w-3.5 shrink-0 opacity-50" />
                    <span>{item.title}</span>
                  </Link>
                ))}
              </div>
            </div>
          ))}
        </div>

        <div className="mt-auto border-t border-border px-4 py-[14px]">
          <div className="flex items-center gap-2">
            <div className="flex h-[26px] w-[26px] items-center justify-center rounded-full bg-accent-light text-[10px] font-bold text-accent-text">
              A
            </div>
            <div>
              <div className="text-[12px] font-semibold">Ash</div>
              <div className="text-[10px] text-text-muted">admin</div>
            </div>
          </div>
        </div>
      </aside>

      {/* Main content */}
      <main className="col-start-2 row-start-2 overflow-auto">{children}</main>
    </div>
  );
}
```

- [ ] **Step 2: Typecheck + smoke test**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no errors.

- [ ] **Step 3: Checkpoint**

Stop and report: **Tasks 12+13 complete — app shell (topbar + sidebar) updated to v4 chrome.** Suggest commit message: `feat(shell): update topbar + sidebar to v4 warm-stone chrome`.

---

## Task 14: Rewrite `scope-bar.tsx` as `DashboardFilterBar` (in-place)

**Files:**
- Modify: `src/features/dashboard/components/scope-bar.tsx`

- [ ] **Step 1: Replace the file**

Replace contents of `src/features/dashboard/components/scope-bar.tsx`:

```tsx
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import type { TimeRange } from "../api/types";

interface ScopeBarProps {
  timeRange: TimeRange;
  onTimeRangeChange: (range: TimeRange) => void;
}

type ScopeKey = "all" | "top5" | "unprofitable";

const SCOPE_TABS: { key: ScopeKey; label: string }[] = [
  { key: "all",           label: "All customers" },
  { key: "top5",          label: "Top 5 by revenue" },
  { key: "unprofitable",  label: "Unprofitable" },
];

const RANGE_OPTIONS: { value: TimeRange; label: string }[] = [
  { value: "7d",  label: "7d" },
  { value: "30d", label: "30d" },
  { value: "90d", label: "90d" },
  { value: "YTD", label: "YTD" },
];

const RANGE_CONTEXT: Record<TimeRange, string> = {
  "7d":  "7-day period",
  "30d": "30-day period",
  "90d": "90-day period",
  "YTD": "Year-to-date",
};

export function ScopeBar({ timeRange, onTimeRangeChange }: ScopeBarProps) {
  return (
    <div className="flex flex-wrap items-center justify-between gap-2.5">
      <div className="flex items-center gap-3.5">
        <ScopePillTabs activeKey="all" />
        <span className="text-[11px] text-text-muted">
          Showing: <b className="font-semibold text-text-secondary">All 18 customers</b> (aggregate)
        </span>
      </div>

      <div className="flex items-center gap-2.5">
        <span className="text-[11px] text-text-muted">{RANGE_CONTEXT[timeRange]}</span>
        <DayRangePillGroup value={timeRange} onChange={onTimeRangeChange} />
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-full border border-border-mid bg-bg-surface px-3 py-[5px] text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
        >
          <Download className="h-[11px] w-[11px]" />
          Export
        </button>
      </div>
    </div>
  );
}

function ScopePillTabs({ activeKey }: { activeKey: ScopeKey }) {
  return (
    <div className="flex gap-px rounded-full border border-border bg-bg-surface p-[3px]">
      {SCOPE_TABS.map((tab) => (
        <button
          key={tab.key}
          type="button"
          className={cn(
            "rounded-full px-3 py-1 text-[11px] transition-colors",
            tab.key === activeKey
              ? "bg-accent-ghost font-semibold text-accent-text"
              : "text-text-secondary hover:text-text-primary",
          )}
        >
          {tab.label}
        </button>
      ))}
    </div>
  );
}

function DayRangePillGroup({
  value,
  onChange,
}: {
  value: TimeRange;
  onChange: (range: TimeRange) => void;
}) {
  return (
    <div className="flex gap-px rounded-full bg-bg-subtle p-[2px]">
      {RANGE_OPTIONS.map((opt) => (
        <button
          key={opt.value}
          type="button"
          onClick={() => onChange(opt.value)}
          className={cn(
            "rounded-full px-2.5 py-[3px] text-[10px] font-medium transition-colors",
            value === opt.value
              ? "bg-bg-surface text-text-primary shadow-sm"
              : "text-text-muted hover:text-text-secondary",
          )}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no errors.

---

## Task 15: Rewrite `stats-grid.tsx` to use raised variant + sparklines

**Files:**
- Modify: `src/features/dashboard/components/stats-grid.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import { StatCard } from "@/components/shared/stat-card";
import { Sparkline } from "@/components/shared/sparkline";
import type { SparklineSet, StatsData } from "../api/types";

interface StatsGridProps {
  stats: StatsData;
  sparklines: SparklineSet;
}

const TERRACOTTA = "#a16a4a";
const RED        = "#b84848";
const GREEN      = "#3a8050";
const STONE      = "#9a8e80";

export function StatsGrid({ stats, sparklines }: StatsGridProps) {
  return (
    <div className="grid grid-cols-5 gap-3.5">
      <StatCard
        variant="raised"
        label="Revenue"
        value={`$${stats.revenue.toLocaleString()}`}
        trend={stats.revenuePrevChange > 0 ? "up" : "down"}
        trendLabel={formatSignedPercent(stats.revenuePrevChange) + " vs prev"}
        sparkline={<Sparkline data={sparklines.revenue} color={TERRACOTTA} />}
      />
      <StatCard
        variant="raised"
        label="API costs"
        value={`$${stats.apiCosts.toLocaleString()}`}
        trend={stats.costsPrevChange < 0 ? "up" : "down"}
        trendLabel={formatSignedPercent(stats.costsPrevChange) + " vs prev"}
        sparkline={<Sparkline data={sparklines.apiCosts} color={RED} />}
      />
      <StatCard
        variant="raised"
        label="Gross margin"
        value={`$${stats.grossMargin.toLocaleString()}`}
        trend={stats.marginPrevChange > 0 ? "up" : "down"}
        trendLabel={formatSignedPercent(stats.marginPrevChange) + " vs prev"}
        sparkline={<Sparkline data={sparklines.grossMargin} color={GREEN} />}
      />
      <StatCard
        variant="raised"
        label="Margin %"
        value={`${stats.marginPercentage}%`}
        trend={stats.marginPctPrevChange > 0 ? "up" : "down"}
        trendLabel={formatSignedPoint(stats.marginPctPrevChange) + " vs prev"}
        sparkline={<Sparkline data={sparklines.marginPct} color={TERRACOTTA} />}
      />
      <StatCard
        variant="raised"
        label="Cost / $1 rev"
        value={`$${stats.costPerDollarRevenue.toFixed(3)}`}
        trend={Math.abs(stats.costPerRevPrevChange) < 1 ? "flat" : stats.costPerRevPrevChange < 0 ? "up" : "down"}
        trendLabel={`±${Math.abs(stats.costPerRevPrevChange)}% vs prev`}
        sparkline={<Sparkline data={sparklines.costPerRev} color={STONE} />}
      />
    </div>
  );
}

function formatSignedPercent(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "" : "";
  return `${sign}${value}%`;
}

function formatSignedPoint(value: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "" : "";
  return `${sign}${value}pp`;
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: errors in `dashboard-page.tsx` because `StatsGrid` now requires `sparklines` prop — expected, will fix in Task 20.

---

## Task 16: Rewrite `revenue-chart.tsx` to use `ChartCard` + v4 palette

**Files:**
- Modify: `src/features/dashboard/components/revenue-chart.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import {
  Area,
  AreaChart,
  CartesianGrid,
  Line,
  ComposedChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import type { RevenueTimeSeries } from "../api/types";

interface RevenueChartProps {
  data: RevenueTimeSeries[];
}

const COLOR_REVENUE = "#a16a4a";
const COLOR_COSTS   = "#b84848";
const COLOR_MARGIN  = "#b5ad9e";

export function RevenueChart({ data }: RevenueChartProps) {
  return (
    <ChartCard
      title="Revenue and margin"
      legend={
        <ChartLegend
          variant="line"
          items={[
            { label: "Revenue",   color: COLOR_REVENUE },
            { label: "API costs", color: COLOR_COSTS },
            { label: "Margin",    color: COLOR_MARGIN, dashed: true },
          ]}
        />
      }
    >
      <div className="h-[240px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `$${v}`}
              width={48}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                borderRadius: 8,
                border: "1px solid var(--color-border)",
                background: "var(--color-card)",
              }}
              formatter={(value, name) => [`$${Number(value).toFixed(2)}`, name]}
            />
            <Area
              type="monotone"
              dataKey="revenue"
              name="Revenue"
              stroke={COLOR_REVENUE}
              fill={COLOR_REVENUE}
              fillOpacity={0.07}
              strokeWidth={2}
            />
            <Area
              type="monotone"
              dataKey="apiCosts"
              name="API costs"
              stroke={COLOR_COSTS}
              fill={COLOR_COSTS}
              fillOpacity={0.05}
              strokeWidth={1.5}
            />
            <Line
              type="monotone"
              dataKey="margin"
              name="Margin"
              stroke={COLOR_MARGIN}
              strokeWidth={1.5}
              strokeDasharray="5 3"
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no new errors from this file.

---

## Task 17: Rewrite `cost-breakdown-chart.tsx` as line chart

**Files:**
- Modify: `src/features/dashboard/components/cost-breakdown-chart.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ChartCard } from "@/components/shared/chart-card";
import { ChartLegend } from "@/components/shared/chart-legend";
import type { CostByProductPoint, CostSeries } from "../api/types";

interface CostBreakdownChartProps {
  title: string;
  series: CostSeries[];
  data: CostByProductPoint[];
}

export function CostBreakdownChart({ title, series, data }: CostBreakdownChartProps) {
  const [primary, ...rest] = series;

  return (
    <ChartCard
      title={title}
      legend={
        <ChartLegend
          variant="dot"
          items={series.map((s) => ({ label: s.label, color: s.color }))}
        />
      }
    >
      <div className="h-[180px] w-full">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: 0 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
            <XAxis
              dataKey="label"
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              interval="preserveStartEnd"
            />
            <YAxis
              tick={{ fontSize: 10, fill: "var(--color-text-muted)" }}
              tickLine={false}
              axisLine={false}
              tickFormatter={(v: number) => `$${v}`}
              width={40}
            />
            <Tooltip
              contentStyle={{
                fontSize: 11,
                borderRadius: 8,
                border: "1px solid var(--color-border)",
                background: "var(--color-card)",
              }}
              formatter={(value, name) => [`$${Number(value).toFixed(2)}`, name]}
            />
            {primary && (
              <Area
                type="monotone"
                dataKey={primary.key}
                name={primary.label}
                stroke={primary.color}
                fill={primary.color}
                fillOpacity={0.07}
                strokeWidth={1.8}
                isAnimationActive={false}
              />
            )}
            {rest.map((s) => (
              <Line
                key={s.key}
                type="monotone"
                dataKey={s.key}
                name={s.label}
                stroke={s.color}
                strokeWidth={1.5}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </ChartCard>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no new errors from this file.

---

## Task 18: Rewrite `breakdown-card.tsx` with v4 row layout

**Files:**
- Modify: `src/features/dashboard/components/breakdown-card.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import { ChartCard } from "@/components/shared/chart-card";
import type { ProductBreakdown } from "../api/types";

interface BreakdownCardProps {
  title: string;
  items: ProductBreakdown[];
  /** Optional override for the bar fill color (e.g. accent terracotta for margin view). */
  barColor?: string;
  formatValue?: (value: number) => string;
}

export function BreakdownCard({ title, items, barColor, formatValue }: BreakdownCardProps) {
  const fmt = formatValue ?? ((v: number) => `$${v.toLocaleString()}`);
  const maxPercentage = Math.max(...items.map((i) => i.percentage));

  return (
    <ChartCard title={title}>
      <div>
        {items.map((item, i) => (
          <div
            key={item.key}
            className="flex items-center gap-3 py-2.5"
            style={{
              borderBottom: i < items.length - 1 ? "1px solid var(--color-bg-subtle)" : undefined,
            }}
          >
            <span
              className="h-2 w-2 shrink-0 rounded-full"
              style={{ backgroundColor: item.color }}
            />
            <span className="flex-1 text-[13px]">{item.label}</span>
            <span className="min-w-[65px] text-right font-mono text-[13px] font-semibold">
              {fmt(item.value)}
            </span>
            <div className="h-[5px] w-[72px] overflow-hidden rounded-full bg-bg-subtle">
              <div
                className="h-full rounded-full"
                style={{
                  width: `${(item.percentage / maxPercentage) * 100}%`,
                  backgroundColor: barColor ?? item.color,
                }}
              />
            </div>
            <span className="min-w-[34px] text-right text-[11px] font-medium text-text-muted">
              {item.percentage}%
            </span>
          </div>
        ))}
      </div>
    </ChartCard>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no new errors from this file.

---

## Task 19: Rewrite `customer-table.tsx` with v4 styling

**Files:**
- Modify: `src/features/dashboard/components/customer-table.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import { Download } from "lucide-react";
import { cn } from "@/lib/utils";
import type { CustomerRow } from "../api/types";

interface CustomerTableProps {
  customers: CustomerRow[];
}

export function CustomerTable({ customers }: CustomerTableProps) {
  return (
    <div className="overflow-hidden rounded-md border border-border bg-bg-surface">
      <div className="flex items-center justify-between px-6 py-[18px]">
        <div className="text-[14px] font-semibold tracking-[-0.15px]">Customer profitability</div>
        <button
          type="button"
          className="inline-flex items-center gap-1.5 rounded-full border border-border-mid bg-bg-surface px-3 py-[5px] text-[11px] font-medium text-text-secondary transition-colors hover:bg-bg-subtle hover:text-text-primary"
        >
          <Download className="h-[11px] w-[11px]" />
          Export table
        </button>
      </div>

      <table className="w-full border-collapse">
        <thead>
          <tr>
            <Th>Customer</Th>
            <Th align="right">Revenue</Th>
            <Th align="center">Type</Th>
            <Th align="right">API costs</Th>
            <Th align="right">Margin</Th>
            <Th>Margin %</Th>
            <Th align="right">Events</Th>
          </tr>
        </thead>
        <tbody>
          {customers.map((c) => (
            <tr
              key={c.customerId}
              className="border-b border-bg-subtle last:border-0 transition-colors hover:bg-bg-page"
            >
              <Td>
                <div className="font-semibold">{c.name}</div>
                <div className="mt-0.5 font-mono text-[10px] text-text-muted">{c.customerId}</div>
              </Td>
              <Td align="right" mono>
                ${c.revenue.toLocaleString()}
              </Td>
              <Td align="center">
                <TypeBadge type={c.revenueType} />
              </Td>
              <Td align="right" mono>
                ${c.apiCosts.toLocaleString()}
              </Td>
              <Td align="right" mono>
                <span className={cn(c.margin < 0 && "text-red")}>
                  {c.margin < 0
                    ? `−$${Math.abs(c.margin).toLocaleString()}`
                    : `$${c.margin.toLocaleString()}`}
                </span>
              </Td>
              <Td>
                <MarginCell percentage={c.marginPercentage} />
              </Td>
              <Td align="right" mono className="text-text-muted">
                {formatEvents(c.events)}
              </Td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Th({
  children,
  align = "left",
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
}) {
  return (
    <th
      className={cn(
        "border-t border-b border-border bg-bg-subtle px-6 py-2.5 text-[10px] font-bold uppercase tracking-[0.06em] text-text-muted",
        align === "right" && "text-right",
        align === "center" && "text-center",
        align === "left" && "text-left",
      )}
    >
      {children}
    </th>
  );
}

function Td({
  children,
  align = "left",
  mono,
  className,
}: {
  children: React.ReactNode;
  align?: "left" | "right" | "center";
  mono?: boolean;
  className?: string;
}) {
  return (
    <td
      className={cn(
        "px-6 py-3.5 align-middle text-[13px]",
        align === "right" && "text-right",
        align === "center" && "text-center",
        mono && "font-mono text-[12px]",
        className,
      )}
    >
      {children}
    </td>
  );
}

function TypeBadge({ type }: { type: "Sub" | "Usage" }) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-[3px] text-[10px] font-semibold",
        type === "Sub"
          ? "bg-blue-light text-blue-text"
          : "bg-amber-light text-amber-text",
      )}
    >
      {type}
    </span>
  );
}

function MarginCell({ percentage }: { percentage: number }) {
  const clamped = Math.max(-100, Math.min(100, percentage));
  const barColor =
    percentage < 0
      ? "bg-red"
      : percentage < 50
        ? "bg-amber"
        : "bg-accent-base";
  const textColor =
    percentage < 0
      ? "text-red-text"
      : percentage < 50
        ? "text-amber-text"
        : "text-green-text";

  const width = percentage < 0 ? Math.abs(clamped) : clamped;

  return (
    <div className="flex items-center gap-1.5">
      <div className="h-1 w-12 overflow-hidden rounded-full bg-bg-subtle">
        <div className={cn("h-full rounded-full", barColor)} style={{ width: `${width}%` }} />
      </div>
      <span className={cn("font-mono text-[12px] font-semibold", textColor)}>
        {percentage < 0 ? "−" : ""}
        {Math.abs(percentage)}%
      </span>
    </div>
  );
}

function formatEvents(count: number): string {
  if (count >= 1000) return `${(count / 1000).toFixed(1)}k`;
  return count.toLocaleString();
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: no errors from this file; the only remaining error should be `dashboard-page.tsx` still passing the old `StatsGrid` props.

---

## Task 20: Recompose `dashboard-page.tsx`

**Files:**
- Modify: `src/features/dashboard/components/dashboard-page.tsx`

- [ ] **Step 1: Replace the file**

Replace contents:

```tsx
import { lazy, Suspense, useState } from "react";
import { PageHeader } from "@/components/shared/page-header";
import { Skeleton } from "@/components/ui/skeleton";
import { useDashboard } from "../api/queries";
import type { TimeRange } from "../api/types";
import { BreakdownCard } from "./breakdown-card";
import { CustomerTable } from "./customer-table";
import { ScopeBar } from "./scope-bar";
import { StatsGrid } from "./stats-grid";

const RevenueChart = lazy(() =>
  import("./revenue-chart").then((m) => ({ default: m.RevenueChart })),
);
const CostBreakdownChart = lazy(() =>
  import("./cost-breakdown-chart").then((m) => ({ default: m.CostBreakdownChart })),
);

const ACCENT = "#a16a4a";

export function DashboardPage() {
  const { data, isLoading } = useDashboard();
  const [timeRange, setTimeRange] = useState<TimeRange>("30d");

  if (isLoading || !data) {
    return (
      <div className="px-10 pt-8 pb-20 space-y-7">
        <PageHeader title="Dashboard" />
        <Skeleton className="h-12 rounded-md" />
        <div className="grid grid-cols-5 gap-3.5">
          {Array.from({ length: 5 }).map((_, i) => (
            <Skeleton key={i} className="h-[120px] rounded-md" />
          ))}
        </div>
        <Skeleton className="h-[280px] rounded-md" />
      </div>
    );
  }

  return (
    <div className="px-10 pt-8 pb-20 space-y-7">
      <PageHeader
        title="Dashboard"
        description="Profitability overview across all products and customers."
      />

      <ScopeBar timeRange={timeRange} onTimeRangeChange={setTimeRange} />

      <StatsGrid stats={data.stats} sparklines={data.sparklines} />

      <Suspense fallback={<Skeleton className="h-[280px] w-full rounded-md" />}>
        <RevenueChart data={data.revenueTimeSeries} />
      </Suspense>

      <div className="grid grid-cols-2 gap-4">
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          <CostBreakdownChart
            title="Cost by product"
            series={data.costByProduct.series}
            data={data.costByProduct.data}
          />
        </Suspense>
        <Suspense fallback={<Skeleton className="h-[220px] w-full rounded-md" />}>
          <CostBreakdownChart
            title="Cost by pricing card"
            series={data.costByCard.series}
            data={data.costByCard.data}
          />
        </Suspense>
      </div>

      <div className="grid grid-cols-2 gap-4">
        <BreakdownCard title="Revenue by product" items={data.revenueByProduct} />
        <BreakdownCard title="Margin by product" items={data.marginByProduct} barColor={ACCENT} />
      </div>

      <CustomerTable customers={data.customers} />
    </div>
  );
}
```

- [ ] **Step 2: Typecheck**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm exec tsc -b --noEmit
```
Expected: zero errors across the whole project.

- [ ] **Step 3: Checkpoint**

Stop and report: **Tasks 14–20 complete — dashboard page rewritten to match v4 mockup.** Suggest commit message: `feat(dashboard): rewrite page to match v4 mockup (filter bar, KPI sparklines, chart cards, table styling)`.

---

## Task 21: Full verification pass

**Files:** (none modified)

- [ ] **Step 1: Run the test suite**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm test 2>&1 | tail -40
```
Expected: all tests pass. New tests: `delta-pill` (4), `sparkline` (2), `stat-card` (7 total = 4 existing + 3 new).

If anything fails, stop and fix. Do not proceed.

- [ ] **Step 2: Run the linter**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm lint 2>&1 | tail -30
```
Expected: no errors. Warnings from unrelated files are acceptable but flag them in the checkpoint report.

- [ ] **Step 3: Run the production build**

Run:
```bash
cd /Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui && pnpm build 2>&1 | tail -20
```
Expected: clean build, no errors.

- [ ] **Step 4: Visual spot-check (manual)**

Run `pnpm dev`, open `http://localhost:5173/`, verify against `ui-mockups/v2/ubb-dashboard-v4.html`:

1. Topbar: 46px tall, "ubb." serif logo on left, mock pill + 2 circular buttons on right.
2. Sidebar: 200px wide, no logo inside, section labels "METERING"/"BILLING"/"SETTINGS", user row pinned at the bottom with top border.
3. Scope bar: single row — scope tabs + context text left, period label + day range pill + Export right.
4. 5-column KPI grid with sparklines, delta pills (green/red/flat), bordered cards that lift on hover.
5. Revenue chart: 240px tall, terracotta/red area + dashed grey margin line.
6. Cost charts: 2 columns, 180px line charts (first series filled).
7. Breakdown cards: 2 columns, dot + name + value + 72px bar + percentage rows.
8. Customer table: bordered container, blue "Sub" / amber "Usage" badges, colored margin bars.
9. Other pages (pricing cards, billing, customers, reconciliation, export) still render without crashing — they inherit the new palette automatically.

Kill the dev server.

- [ ] **Step 5: Update `PROGRESS.md`**

Append a new row to the Session Log and a new "Phase 9: Visual refresh" section. Edit `PROGRESS.md`:

Add under `## Phase Summary` table:

```
| 9 | v4 Visual refresh | Complete | ubb-dashboard-v4.html |
```

Add a new section after Phase 8:

```
## Phase 9: v4 Visual refresh (Complete)

- [x] Rewired design tokens to warm stone + terracotta palette
- [x] Swapped Geist → DM Sans + Cormorant + DM Mono fonts
- [x] Rebuilt app shell (topbar + sidebar) to 46px/200px chrome
- [x] Added shared primitives: DeltaPill, Sparkline, Brand, IconButton, ChartCard, ChartLegend
- [x] Extended StatCard with `raised` variant + `trend` + `sparkline` slot (back-compat preserved)
- [x] Rewrote dashboard page to match ubb-dashboard-v4.html (filter bar, KPI sparklines, line-chart cost breakdowns, v4 customer table)
- [x] Recolored dashboard mock data to new palette
- [x] 6 new tests (DeltaPill, Sparkline, StatCard raised variant)
```

Add to the Session Log table:

```
| 2026-04-10 | Phase 9 v4 visual refresh complete (dashboard + tokens + shell). |
```

- [ ] **Step 6: Final checkpoint**

Stop and report: **Task 21 complete — all verification passes, PROGRESS.md updated.** Suggest final commit message: `docs: log phase 9 v4 visual refresh in PROGRESS.md`.

Summarize to the user:
- What changed (tokens, fonts, shell, dashboard, 6 new shared primitives)
- What inherits automatically (other pages now warm-toned via shadcn vars)
- What does NOT change (billing/customers/reconciliation/pricing-cards/export layouts, which were not individually retuned)
- Next suggested steps if user wants a full rebrand follow-up

---

## Spec coverage check

| Spec section | Task(s) |
|---|---|
| §3.1 Shadcn token rewire | Task 2 |
| §3.2 Named palette `@theme inline` | Task 2 |
| §3.3 Font swap | Tasks 1, 2 |
| §4.1 Brand | Task 7 |
| §4.2 IconButton | Task 8 |
| §4.3 DeltaPill | Task 5 |
| §4.4 Sparkline | Task 6 |
| §4.5 ChartCard | Task 10 |
| §4.6 ChartLegend | Task 9 |
| §4.7 StatCard extension | Task 11 |
| §4.8 TopBar + NavShell shell | Tasks 12, 13 |
| §5.1 DashboardPage recomposition | Task 20 |
| §5.2 ScopeBar rewrite | Task 14 |
| §5.3 StatsGrid rewrite | Task 15 |
| §5.4 RevenueChart rewrite | Task 16 |
| §5.5 CostBreakdownChart rewrite | Task 17 |
| §5.6 BreakdownCard rewrite | Task 18 |
| §5.7 CustomerTable rewrite | Task 19 |
| §6 Mock data recolor + sparklines | Tasks 3, 4 |
| §8 Testing (DeltaPill, Sparkline, StatCard new tests) | Tasks 5, 6, 11 |
| §9 Verification checklist | Task 21 |
| §10 Dependencies | Task 1 |
| §11 Migration notes | Covered across tasks 2, 11 |
