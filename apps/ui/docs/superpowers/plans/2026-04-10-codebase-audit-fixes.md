# Codebase Audit Fixes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bring the UBB UI codebase from B+ to A+ by fixing every finding from the 2026-04-10 audit — duplication, React perf, inline formatting, hardcoded colors, high-prop components, and the `adjustments-section` monolith.

**Architecture:** Incremental refactor across 8 phases. Each phase groups related work so changes can be verified in isolation. No cross-feature imports are introduced. All existing behavior is preserved — this is cleanup, not new functionality.

**Tech Stack:** React 19 + Vite 8 + TypeScript 5.9 + TanStack Query v5 + TanStack Router + Zustand 5 + Tailwind v4 + shadcn/ui + Vitest + React Testing Library

---

## Process Notes

1. **No git commits.** Per `CLAUDE.md`, the user handles all git operations. Do not run `git commit`, `git push`, or create branches. After completing each phase, STOP and report to the user so they can review and commit.
2. **Verify between phases.** After each phase, run the verification block:
   ```bash
   npx tsc --noEmit && npm run lint && npm test
   ```
   All three must pass before moving on.
3. **Preserve behavior.** These are refactors. The app must look and behave identically after each phase. Spot-check in the browser after Phase 2 (colors), Phase 3 (components), Phase 6 (high-prop refactors), and Phase 7 (adjustments).
4. **TDD discipline.** New shared components (`StatCard`, `StatusBadge`) and new pure functions (format helpers, reducer) get unit tests BEFORE implementation. Replacements of existing UI that preserve behavior do NOT require new tests beyond existing ones still passing.

---

## Phase 1: Foundation & Infrastructure

Foundational helpers that every later phase depends on.

---

### Task 1: Extract shared `delay` helper

Every feature's `mock.ts` redeclares `const delay = (ms = 300) => new Promise(r => setTimeout(r, ms))`. Consolidate into one export.

**Files:**
- Modify: `src/lib/api-provider.ts`
- Modify: `src/features/billing/api/mock.ts`
- Modify: `src/features/customers/api/mock.ts`
- Modify: `src/features/dashboard/api/mock.ts`
- Modify: `src/features/export/api/mock.ts`
- Modify: `src/features/onboarding/api/mock.ts`
- Modify: `src/features/pricing-cards/api/mock.ts`
- Modify: `src/features/reconciliation/api/mock.ts`

- [ ] **Step 1.1: Add `mockDelay` export to `api-provider.ts`**

Append to `src/lib/api-provider.ts`:

```typescript
/** Simulated network delay for mock API providers. */
export function mockDelay(ms = 300): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}
```

- [ ] **Step 1.2: Replace local `delay` in each of the 7 mock files**

In each of the 7 `mock.ts` files:
1. Delete the local `const delay = ...` declaration.
2. Add `import { mockDelay } from "@/lib/api-provider";` at the top (merge with existing imports if any).
3. Replace every `delay(` call with `mockDelay(`.

- [ ] **Step 1.3: Verify**

```bash
npx tsc --noEmit
```
Expected: no errors. Then:
```bash
grep -rn "const delay" src/features/*/api/mock.ts
```
Expected: no matches.

---

### Task 2: Fix `main.tsx` Clerk env-var guard

`src/main.tsx:64` uses `clerkPubKey!` which silently passes `undefined` to `<ClerkProvider>` if the env var is missing in prod. Fail loudly at startup instead.

**Files:**
- Modify: `src/main.tsx`

- [ ] **Step 2.1: Add startup validation and narrow the type**

Replace lines 11–12 in `src/main.tsx`:

```typescript
const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const noAuthMode = !clerkPubKey && API_PROVIDER === "mock";
```

with:

```typescript
const clerkPubKey = import.meta.env.VITE_CLERK_PUBLISHABLE_KEY;
const noAuthMode = !clerkPubKey && API_PROVIDER === "mock";

if (!noAuthMode && !clerkPubKey) {
  throw new Error(
    "VITE_CLERK_PUBLISHABLE_KEY is required when VITE_API_PROVIDER is not 'mock'. " +
      "Set it in .env or run with VITE_API_PROVIDER=mock.",
  );
}
```

- [ ] **Step 2.2: Remove the non-null assertion**

Change line 64 from:

```tsx
<ClerkProvider publishableKey={clerkPubKey!}>
```

to:

```tsx
<ClerkProvider publishableKey={clerkPubKey as string}>
```

(Safe because the throw above guarantees `clerkPubKey` is set in this branch.)

- [ ] **Step 2.3: Verify dev mode still works**

```bash
npx tsc --noEmit
npm run dev
```
Expected: app loads at http://localhost:5173 in no-auth mock mode without errors.

---

### Task 3: Extend `format.ts` with missing helpers

We need helpers for values that are already in dollars (not micros), delta amounts with sign, and file-size formatting. Add them TDD-style.

**Files:**
- Modify: `src/lib/format.ts`
- Modify: `src/lib/format.test.ts`

- [ ] **Step 3.1: Write failing tests**

Append to `src/lib/format.test.ts`:

```typescript
import { formatDollars, formatSignedDollars, formatFileSize, formatRoundedDollars } from "./format";

describe("formatDollars", () => {
  it("formats whole dollars with thousands separators", () => {
    expect(formatDollars(1247)).toBe("$1,247");
    expect(formatDollars(0)).toBe("$0");
    expect(formatDollars(1_234_567)).toBe("$1,234,567");
  });
  it("formats with 2 decimals when fractional", () => {
    expect(formatDollars(12.5)).toBe("$12.50");
    expect(formatDollars(0.07)).toBe("$0.07");
  });
});

describe("formatRoundedDollars", () => {
  it("rounds to whole dollars with thousands separators", () => {
    expect(formatRoundedDollars(1247.89)).toBe("$1,248");
    expect(formatRoundedDollars(0)).toBe("$0");
  });
});

describe("formatSignedDollars", () => {
  it("prefixes positive with +", () => {
    expect(formatSignedDollars(25)).toBe("+$25");
  });
  it("prefixes negative with -", () => {
    expect(formatSignedDollars(-25)).toBe("-$25");
  });
  it("zero has no sign", () => {
    expect(formatSignedDollars(0)).toBe("$0");
  });
});

describe("formatFileSize", () => {
  it("formats bytes as MB", () => {
    expect(formatFileSize(1_500_000)).toBe("2 MB");
    expect(formatFileSize(0)).toBe("0 MB");
  });
  it("formats sub-MB as KB", () => {
    expect(formatFileSize(500)).toBe("1 KB");
  });
});
```

- [ ] **Step 3.2: Run tests to verify they fail**

```bash
npx vitest run src/lib/format.test.ts
```
Expected: FAIL with "formatDollars is not a function" (and similar).

- [ ] **Step 3.3: Add the four helpers to `format.ts`**

Append to `src/lib/format.ts`:

```typescript
/**
 * Format a dollar amount (already in dollars, not micros).
 * Whole numbers: "$1,247"  Fractional: "$12.50"
 */
export function formatDollars(dollars: number): string {
  const hasFraction = dollars % 1 !== 0;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  }).format(dollars);
}

/**
 * Format a dollar amount rounded to whole dollars.
 * e.g. 1247.89 → "$1,248"
 */
export function formatRoundedDollars(dollars: number): string {
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(Math.round(dollars));
}

/**
 * Format a dollar delta with explicit + / - sign.
 * e.g. +25 → "+$25"   -25 → "-$25"   0 → "$0"
 */
export function formatSignedDollars(dollars: number): string {
  if (dollars === 0) return "$0";
  const sign = dollars > 0 ? "+" : "-";
  return `${sign}${formatDollars(Math.abs(dollars))}`;
}

/**
 * Format a byte count for display.
 * >= 1_000_000 bytes → "X MB" (rounded up)
 * Otherwise → "X KB" (rounded up, min 1)
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 MB";
  if (bytes >= 1_000_000) return `${Math.round(bytes / 1_000_000)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}
```

- [ ] **Step 3.4: Run tests to verify they pass**

```bash
npx vitest run src/lib/format.test.ts
```
Expected: PASS all tests.

**Phase 1 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
Expected: all green. STOP and report to user.

---

## Phase 2: Design Tokens

Replace 39 instances of hardcoded hex colors with semantic CSS variables. This is the single biggest styling-quality win.

---

### Task 4: Add semantic color tokens to `app.css`

**Files:**
- Modify: `src/styles/app.css`

- [ ] **Step 4.1: Add color variables to `:root` and `.dark`**

In `src/styles/app.css`, inside the `:root` block (after the existing variables, before the closing `}`), add:

```css
    /* Brand + status tokens */
    --brand-purple: oklch(0.54 0.15 288);             /* #534AB7 */
    --brand-purple-foreground: oklch(0.98 0.008 85);
    --brand-purple-bg: oklch(0.96 0.03 288);          /* #EEEDFE */
    --brand-purple-bg-foreground: oklch(0.35 0.12 285); /* #3C3489 */

    --status-active: oklch(0.78 0.14 160);            /* #5DCAA5 */
    --status-superseded: oklch(0.83 0.01 85);         /* #D3D1C7 */
    --status-retroactive: oklch(0.74 0.10 245);       /* #85B7EB */
    --status-adjustment: oklch(0.78 0.09 288);        /* #AFA9EC */

    --value-positive: oklch(0.48 0.14 128);           /* #3B6D11 */
    --value-positive-strong: oklch(0.58 0.18 136);    /* #639922 */
    --value-negative: oklch(0.48 0.18 24);            /* #A32D2D */
    --value-warning: oklch(0.50 0.13 65);             /* #854F0B */
    --value-success-bg: oklch(0.94 0.07 168);         /* #E1F5EE */
    --value-success-fg: oklch(0.45 0.11 178);         /* #0F6E56 */
```

Inside the `.dark` block, add:

```css
    /* Brand + status tokens (dark) */
    --brand-purple: oklch(0.65 0.16 288);
    --brand-purple-foreground: oklch(0.20 0.015 70);
    --brand-purple-bg: oklch(0.30 0.09 288);
    --brand-purple-bg-foreground: oklch(0.85 0.08 288);

    --status-active: oklch(0.68 0.14 160);
    --status-superseded: oklch(0.60 0.01 85);
    --status-retroactive: oklch(0.62 0.10 245);
    --status-adjustment: oklch(0.62 0.12 288);

    --value-positive: oklch(0.72 0.15 136);
    --value-positive-strong: oklch(0.78 0.18 136);
    --value-negative: oklch(0.70 0.18 24);
    --value-warning: oklch(0.70 0.13 65);
    --value-success-bg: oklch(0.30 0.07 168);
    --value-success-fg: oklch(0.80 0.11 178);
```

- [ ] **Step 4.2: Register the tokens in the `@theme inline` block**

Inside the existing `@theme inline { ... }` block in `app.css`, add:

```css
    --color-brand-purple: var(--brand-purple);
    --color-brand-purple-foreground: var(--brand-purple-foreground);
    --color-brand-purple-bg: var(--brand-purple-bg);
    --color-brand-purple-bg-foreground: var(--brand-purple-bg-foreground);

    --color-status-active: var(--status-active);
    --color-status-superseded: var(--status-superseded);
    --color-status-retroactive: var(--status-retroactive);
    --color-status-adjustment: var(--status-adjustment);

    --color-value-positive: var(--value-positive);
    --color-value-positive-strong: var(--value-positive-strong);
    --color-value-negative: var(--value-negative);
    --color-value-warning: var(--value-warning);
    --color-value-success-bg: var(--value-success-bg);
    --color-value-success-fg: var(--value-success-fg);
```

This makes `bg-brand-purple`, `text-value-negative`, etc. usable as Tailwind utilities.

- [ ] **Step 4.3: Verify the dev server still renders**

```bash
npm run dev
```
Open http://localhost:5173 — existing pages should look identical (no tokens used yet).

---

### Task 5: Replace hardcoded hex in reconciliation components

Seven files need their hex literals swapped for the new tokens. Pattern: `style={{ backgroundColor: "#5DCAA5" }}` → `className="bg-status-active"` where possible, or `style={{ backgroundColor: "var(--status-active)" }}` when inline is required (dynamic width, etc.).

**Files:**
- Modify: `src/features/reconciliation/components/timeline.tsx`
- Modify: `src/features/reconciliation/components/manual-allocation.tsx`
- Modify: `src/features/reconciliation/components/distribution-preview.tsx`
- Modify: `src/features/reconciliation/components/card-header.tsx`
- Modify: `src/features/reconciliation/components/audit-trail.tsx`
- Modify: `src/features/reconciliation/components/reconciliation-summary.tsx`
- Modify: `src/features/reconciliation/components/adjustments-section.tsx`

- [ ] **Step 5.1: `timeline.tsx` — legend swatches**

Replace lines 17–25:

```tsx
<span className="flex items-center gap-1.5">
  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-status-active" /> Active
</span>
<span className="flex items-center gap-1.5">
  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-status-superseded" /> Superseded
</span>
<span className="flex items-center gap-1.5">
  <span className="inline-block h-2.5 w-2.5 rounded-sm bg-status-retroactive" /> Retroactive
</span>
```

Note: lines 98–103 (`style={{ backgroundColor: seg.color, ... }}`) remain inline — `seg.color` is dynamic mock data. Leave as-is for now; the mock-data colors will be replaced in Task 6 by updating the mock-data constants to reference tokens. For now, add a TODO comment: `// TODO: mock-data color values should be token refs`.

- [ ] **Step 5.2: `manual-allocation.tsx`**

Line 36: replace `style={{ width: ..., backgroundColor: "#AFA9EC" }}` with:
```tsx
style={{ width: `${barWidth}%` }}
className="... bg-status-adjustment"
```
(merge with existing className).

Line 54: replace `bg-green-50 px-2.5 ... text-[#3B6D11]` with `bg-green-50 px-2.5 ... text-value-positive`.

Line 62: replace `text-[#A32D2D]` with `text-value-negative`.

- [ ] **Step 5.3: `distribution-preview.tsx`**

Line 77: replace `backgroundColor: "#AFA9EC"` with `backgroundColor: "var(--status-adjustment)"` (still inline because it's within a dynamic style object). Do the same for any other hex literals in lines 67–78.

- [ ] **Step 5.4: `card-header.tsx`**

Line 66: replace `valueColor={stats.netAdjustments > 0 ? "text-[#A32D2D]" : "text-[#3B6D11]"}` with `valueColor={stats.netAdjustments > 0 ? "text-value-negative" : "text-value-positive"}`.

- [ ] **Step 5.5: `audit-trail.tsx`**

Line 13: replace `credit_recorded: "bg-[#EEEDFE] text-[#534AB7]"` with `credit_recorded: "bg-brand-purple-bg text-brand-purple"`.

Line 47: replace `entry.delta > 0 ? "text-[#A32D2D]" : "text-[#3B6D11]"` with `entry.delta > 0 ? "text-value-negative" : "text-value-positive"`.

- [ ] **Step 5.6: `reconciliation-summary.tsx`**

Lines 27–28: replace
```tsx
? "bg-red-50 text-[#A32D2D] dark:bg-red-900/20"
: "bg-green-50 text-[#3B6D11] dark:bg-green-900/20"
```
with:
```tsx
? "bg-red-50 text-value-negative dark:bg-red-900/20"
: "bg-green-50 text-value-positive dark:bg-green-900/20"
```

- [ ] **Step 5.7: `adjustments-section.tsx` — the Record button**

Line 244: replace `className="rounded-md bg-[#534AB7] px-3 py-1.5 text-[11px] font-medium text-white hover:opacity-90 disabled:opacity-50"` with `className="rounded-md bg-brand-purple px-3 py-1.5 text-[11px] font-medium text-brand-purple-foreground hover:opacity-90 disabled:opacity-50"`.

- [ ] **Step 5.8: Verify reconciliation renders identically**

```bash
npm run dev
```
Navigate to a pricing card's reconciliation page. All legends, bars, and badges should look identical.

---

### Task 6: Replace hardcoded hex in dashboard, billing, customers

**Files:**
- Modify: `src/features/dashboard/components/stats-grid.tsx`
- Modify: `src/features/dashboard/components/customer-table.tsx`
- Modify: `src/features/billing/components/margin-stats.tsx`
- Modify: `src/features/billing/components/margin-tree-row.tsx`
- Modify: `src/features/billing/components/change-history.tsx`
- Modify: `src/features/billing/components/impact-preview.tsx`
- Modify: `src/features/customers/components/sync-status-bar.tsx`

- [ ] **Step 6.1: Mechanical sweep — token mapping table**

Apply these replacements to each file above (using Edit tool per replacement):

| Old | New |
|---|---|
| `text-[#3B6D11]` | `text-value-positive` |
| `text-[#639922]` | `text-value-positive-strong` |
| `text-[#A32D2D]` | `text-value-negative` |
| `text-[#854F0B]` | `text-value-warning` |
| `text-[#0F6E56]` | `text-value-success-fg` |
| `bg-[#E1F5EE]` | `bg-value-success-bg` |
| `text-[#534AB7]` | `text-brand-purple` |
| `text-[#3C3489]` | `text-brand-purple-bg-foreground` |
| `bg-[#EEEDFE]` | `bg-brand-purple-bg` |
| `dark:bg-[#2a2757]` | `dark:bg-brand-purple-bg` |
| `dark:text-[#a9a3f0]` | `dark:text-brand-purple-bg-foreground` |
| `dark:bg-[rgba(127,119,221,0.15)]` | `dark:bg-brand-purple-bg` |
| `dark:bg-[rgba(127,119,221,0.3)]` | `dark:bg-brand-purple-bg` |
| `bg-[#F09595]` | `bg-red-300` (use Tailwind; this is a one-off chart color) |
| `bg-[#5DCAA5]` | `bg-status-active` |

Go file-by-file, grep each file to confirm zero hex literals remain:

```bash
grep -n "#" src/features/dashboard/components/stats-grid.tsx | grep -E "\[#|#[0-9a-fA-F]{3}"
```
Expected: no matches per file.

- [ ] **Step 6.2: Verify**

```bash
npx tsc --noEmit && npm run lint
grep -rn "text-\[#\|bg-\[#" src/features --include="*.tsx"
```
Expected: no matches (or only legitimate dynamic color refs like chart-series).

- [ ] **Step 6.3: Spot-check dashboard, billing, customers pages**

```bash
npm run dev
```
Expected: all three pages render identically.

**Phase 2 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
STOP and report to user.

---

## Phase 3: Shared Component Extraction

Four duplicate `StatCard` implementations become one. Status badges get a shared component.

---

### Task 7: Create shared `StatCard` with tests

**Files:**
- Create: `src/components/shared/stat-card.tsx`
- Create: `src/components/shared/stat-card.test.tsx`

- [ ] **Step 7.1: Write failing test**

Create `src/components/shared/stat-card.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatCard } from "./stat-card";

describe("StatCard", () => {
  it("renders label, value, and subtitle", () => {
    render(<StatCard label="Revenue" value="$1,247" subtitle="+12.3%" />);
    expect(screen.getByText("Revenue")).toBeInTheDocument();
    expect(screen.getByText("$1,247")).toBeInTheDocument();
    expect(screen.getByText("+12.3%")).toBeInTheDocument();
  });

  it("accepts a valueClassName override", () => {
    render(
      <StatCard label="Margin" value="$500" valueClassName="text-value-positive" />,
    );
    expect(screen.getByText("$500")).toHaveClass("text-value-positive");
  });

  it("renders without subtitle when omitted", () => {
    render(<StatCard label="Count" value="42" />);
    expect(screen.getByText("42")).toBeInTheDocument();
  });
});
```

- [ ] **Step 7.2: Run to verify it fails**

```bash
npx vitest run src/components/shared/stat-card.test.tsx
```
Expected: FAIL "Cannot find module './stat-card'".

- [ ] **Step 7.3: Implement `StatCard`**

Create `src/components/shared/stat-card.tsx`:

```tsx
import { cn } from "@/lib/utils";

interface StatCardProps {
  label: string;
  value: string;
  subtitle?: string;
  /** Optional class applied to the value (e.g. "text-value-positive" for positive deltas). */
  valueClassName?: string;
  /** Optional class applied to the subtitle. */
  subtitleClassName?: string;
  /** Optional class applied to the outer card. */
  className?: string;
}

export function StatCard({
  label,
  value,
  subtitle,
  valueClassName,
  subtitleClassName,
  className,
}: StatCardProps) {
  return (
    <div className={cn("rounded-lg bg-accent/50 px-3 py-2.5", className)}>
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div
        className={cn(
          "mt-1 text-[17px] font-semibold tracking-tight",
          valueClassName,
        )}
      >
        {value}
      </div>
      {subtitle !== undefined && (
        <div
          className={cn(
            "mt-0.5 text-[10px] text-muted-foreground/60",
            subtitleClassName,
          )}
        >
          {subtitle}
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 7.4: Run tests to verify they pass**

```bash
npx vitest run src/components/shared/stat-card.test.tsx
```
Expected: PASS all tests.

---

### Task 8: Replace the 4 feature `StatCard` implementations

**Files:**
- Modify: `src/features/dashboard/components/stats-grid.tsx`
- Modify: `src/features/billing/components/margin-stats.tsx`
- Modify: `src/features/reconciliation/components/card-header.tsx`
- Modify: `src/features/customers/components/mapping-stats-grid.tsx`

- [ ] **Step 8.1: `stats-grid.tsx` — use shared StatCard**

Replace the entire file contents of `src/features/dashboard/components/stats-grid.tsx` with:

```tsx
import { StatCard } from "@/components/shared/stat-card";
import type { StatsData } from "../api/types";

interface StatsGridProps {
  stats: StatsData;
}

export function StatsGrid({ stats }: StatsGridProps) {
  return (
    <div className="grid grid-cols-5 gap-2">
      <StatCard
        label="Revenue"
        value={`$${stats.revenue.toLocaleString()}`}
        subtitle={`${stats.revenuePrevChange > 0 ? "+" : ""}${stats.revenuePrevChange}% vs prev`}
      />
      <StatCard
        label="API costs"
        value={`$${stats.apiCosts.toLocaleString()}`}
        subtitle={`${stats.costsPrevChange}% vs prev`}
      />
      <StatCard
        label="Gross margin"
        value={`$${stats.grossMargin.toLocaleString()}`}
        subtitle={`${stats.marginPrevChange > 0 ? "+" : ""}${stats.marginPrevChange}% vs prev`}
        valueClassName="text-value-positive"
      />
      <StatCard
        label="Margin %"
        value={`${stats.marginPercentage}%`}
        subtitle={`${stats.marginPctPrevChange > 0 ? "+" : ""}${stats.marginPctPrevChange}pp vs prev`}
        valueClassName="text-value-positive"
      />
      <StatCard
        label="Cost / $1 rev"
        value={`$${stats.costPerDollarRevenue}`}
        subtitle={`${stats.costPerRevPrevChange}% vs prev`}
      />
    </div>
  );
}
```

Note: formatting cleanup (replacing `.toLocaleString()` with `formatDollars`) will happen in Phase 5 — leave as-is for now.

- [ ] **Step 8.2: `margin-stats.tsx`**

Replace entire file with:

```tsx
import { StatCard } from "@/components/shared/stat-card";
import type { MarginStats } from "../api/types";

interface MarginStatsProps {
  stats: MarginStats;
}

export function MarginStatsGrid({ stats }: MarginStatsProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard
        label="Blended margin"
        value={`${stats.blendedMargin}%`}
        subtitle="Weighted by cost volume"
        valueClassName="text-value-positive-strong"
      />
      <StatCard
        label="API costs (30d)"
        value={`$${stats.apiCosts30d.toLocaleString()}`}
        subtitle="Your expense"
      />
      <StatCard
        label="Customer billings (30d)"
        value={`$${stats.customerBillings30d.toLocaleString()}`}
        subtitle="Debited from balances"
      />
      <StatCard
        label="Margin earned (30d)"
        value={`$${stats.marginEarned30d.toLocaleString()}`}
        subtitle="Billings minus costs"
        valueClassName="text-value-positive-strong"
      />
    </div>
  );
}
```

- [ ] **Step 8.3: `card-header.tsx` — replace local `StatCard`**

In `src/features/reconciliation/components/card-header.tsx`:

1. Delete lines 78–91 (the local `StatCard` function).
2. At the top, add `import { StatCard } from "@/components/shared/stat-card";`.
3. Replace the 4 `<StatCard ... sub="..." valueColor="..." />` calls with `<StatCard ... subtitle="..." valueClassName="..." />` (rename `sub`→`subtitle`, `valueColor`→`valueClassName`).

- [ ] **Step 8.4: `mapping-stats-grid.tsx`**

Replace entire file with:

```tsx
import { StatCard } from "@/components/shared/stat-card";
import type { CustomerMappingStats } from "../api/types";

interface MappingStatsGridProps {
  stats: CustomerMappingStats;
}

export function MappingStatsGrid({ stats }: MappingStatsGridProps) {
  return (
    <div className="grid grid-cols-4 gap-2">
      <StatCard
        label="Stripe customers"
        value={String(stats.totalCustomers)}
        subtitle={`${stats.newCustomersSinceLastSync} added since last month`}
      />
      <StatCard
        label="Mapped"
        value={String(stats.mapped)}
        subtitle="Fully connected"
        valueClassName="text-green-600 dark:text-green-400"
      />
      <StatCard
        label="Unmapped"
        value={String(stats.unmapped)}
        subtitle="Need attention"
        valueClassName="text-amber-600 dark:text-amber-400"
      />
      <StatCard
        label="Orphaned events"
        value={String(stats.orphanedEvents)}
        subtitle={`${stats.orphanedIdentifiers} unknown SDK IDs`}
        valueClassName="text-red-600 dark:text-red-400"
      />
    </div>
  );
}
```

- [ ] **Step 8.5: Verify**

```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
Expected: all stat grids render identically on dashboard, billing, reconciliation, customers.

---

### Task 9: Create shared `StatusBadge` with tests

**Files:**
- Create: `src/components/shared/status-badge.tsx`
- Create: `src/components/shared/status-badge.test.tsx`

- [ ] **Step 9.1: Write failing tests**

Create `src/components/shared/status-badge.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StatusBadge } from "./status-badge";

describe("StatusBadge", () => {
  it("renders children", () => {
    render(<StatusBadge tone="active">Active</StatusBadge>);
    expect(screen.getByText("Active")).toBeInTheDocument();
  });

  it("applies the active tone classes", () => {
    render(<StatusBadge tone="active">Active</StatusBadge>);
    expect(screen.getByText("Active")).toHaveClass("bg-green-50");
  });

  it("applies the neutral tone classes for muted status", () => {
    render(<StatusBadge tone="muted">Idle</StatusBadge>);
    expect(screen.getByText("Idle")).toHaveClass("bg-accent");
  });
});
```

- [ ] **Step 9.2: Run to verify they fail**

```bash
npx vitest run src/components/shared/status-badge.test.tsx
```
Expected: FAIL.

- [ ] **Step 9.3: Implement `StatusBadge`**

Create `src/components/shared/status-badge.tsx`:

```tsx
import { cn } from "@/lib/utils";

export type StatusTone =
  | "active"
  | "inactive"
  | "muted"
  | "new"
  | "warning"
  | "danger"
  | "info"
  | "brand";

interface StatusBadgeProps {
  tone: StatusTone;
  children: React.ReactNode;
  className?: string;
}

const TONE_CLASSES: Record<StatusTone, string> = {
  active:
    "bg-green-50 text-green-700 dark:bg-green-900/20 dark:text-green-400",
  inactive: "bg-muted text-muted-foreground",
  muted: "bg-accent text-muted-foreground",
  new: "bg-emerald-50 text-emerald-800 dark:bg-emerald-950 dark:text-emerald-300",
  warning:
    "bg-amber-50 text-amber-700 dark:bg-amber-900/20 dark:text-amber-400",
  danger: "bg-red-50 text-value-negative dark:bg-red-900/20",
  info: "bg-blue-50 text-blue-700 dark:bg-blue-900/20 dark:text-blue-400",
  brand: "bg-brand-purple-bg text-brand-purple",
};

export function StatusBadge({ tone, children, className }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-block rounded-full px-2.5 py-0.5 text-[10px] font-medium",
        TONE_CLASSES[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}
```

- [ ] **Step 9.4: Verify tests pass**

```bash
npx vitest run src/components/shared/status-badge.test.tsx
```
Expected: PASS.

---

### Task 10: Replace hardcoded status pills with `StatusBadge`

Apply the new component wherever we previously inlined `rounded-full px-X.X py-0.5 text-[10px] font-medium ...`.

**Files:**
- Modify: `src/features/reconciliation/components/audit-trail.tsx`
- Modify: `src/features/reconciliation/components/card-header.tsx`
- Modify: `src/features/reconciliation/components/version-detail.tsx`
- Modify: `src/features/customers/components/customer-table.tsx`
- Modify: `src/features/customers/components/sync-status-bar.tsx`
- Modify: `src/features/dashboard/components/customer-table.tsx`
- Modify: `src/features/billing/components/margin-tree-row.tsx`
- Modify: `src/features/pricing-cards/components/pricing-card-item.tsx`

- [ ] **Step 10.1: `audit-trail.tsx`**

In `src/features/reconciliation/components/audit-trail.tsx`:

Replace the `typeStyles` map + the `<span className={cn(...)}` element with a map of tones and a `<StatusBadge>`:

```tsx
import { StatusBadge, type StatusTone } from "@/components/shared/status-badge";

const typeTone: Record<string, StatusTone> = {
  period_insert: "info",
  boundary_shift: "inactive",
  price_edit: "warning",
  credit_recorded: "brand",
};
```

And replace the `<span>` with:
```tsx
<StatusBadge tone={typeTone[entry.type] ?? "inactive"}>
  {typeLabels[entry.type] ?? entry.type}
</StatusBadge>
```

Delete the old `typeStyles` constant.

- [ ] **Step 10.2: `card-header.tsx`**

Replace lines 32–41 (the card status span) with:
```tsx
<StatusBadge tone={card.status === "active" ? "active" : "inactive"}>
  {card.status === "active" ? "Active" : "Inactive"}
</StatusBadge>
```
Add import: `import { StatusBadge } from "@/components/shared/status-badge";`

- [ ] **Step 10.3: `version-detail.tsx`**

Read the file first (it wasn't fully inspected earlier). Find any `rounded-full ... text-[10px]` badge spans and replace each with the appropriate `<StatusBadge tone="...">`. Common tones: version status → `active` | `inactive` | `warning`. Add the import.

- [ ] **Step 10.4: `customers/customer-table.tsx`**

Lines 18–22 define `STATUS_CONFIG`. Replace with tone mapping:

```tsx
const STATUS_TONE: Record<CustomerStatus, { tone: StatusTone; label: string }> = {
  active: { tone: "active", label: "Active" },
  idle: { tone: "muted", label: "Idle" },
  unmapped: { tone: "new", label: "New" },
};
```

Lines 160–162 (the `<span className={...}>`) becomes:
```tsx
<StatusBadge tone={STATUS_TONE[customer.status].tone}>
  {STATUS_TONE[customer.status].label}
</StatusBadge>
```

Add imports. Delete the `StatusPill` type and old `STATUS_CONFIG`.

- [ ] **Step 10.5: `sync-status-bar.tsx`**

Line 36 has `<span className="rounded-full bg-[#EEEDFE] ... text-[#3C3489] ...">`. Replace with `<StatusBadge tone="brand">...</StatusBadge>`.

- [ ] **Step 10.6: `dashboard/customer-table.tsx`**

Find the revenue-type span (Sub/OneTime). Replace with `<StatusBadge tone="brand">Sub</StatusBadge>` / `<StatusBadge tone="info">OneTime</StatusBadge>` (or similar — preserve existing labels).

- [ ] **Step 10.7: `billing/margin-tree-row.tsx`**

Line 49 has the level badge. Replace with `<StatusBadge tone="brand">{level.label}</StatusBadge>`.

- [ ] **Step 10.8: `pricing-cards/components/pricing-card-item.tsx`**

Find any status pills and replace with `<StatusBadge tone={...}>`. Check what tones are needed for pricing card statuses (`draft`, `active`, `archived`).

- [ ] **Step 10.9: Verify**

```bash
npx tsc --noEmit && npm run lint && npm test
grep -rn "rounded-full.*text-\[10px\].*font-medium" src/features --include="*.tsx"
```
Expected: only dynamic/one-off badges remain. Spot-check every affected page in the browser.

**Phase 3 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
STOP and report to user.

---

## Phase 4: React Correctness

Fix the genuine perf and bug hazards from the audit.

---

### Task 11: Add Zustand selectors in reconciliation components

Every `useReconciliationStore()` call in reconciliation/components/ currently destructures the whole store, causing extra re-renders. Replace each with explicit selectors.

**Files:**
- Modify: `src/features/reconciliation/components/reconciliation-page.tsx`
- Modify: `src/features/reconciliation/components/timeline.tsx`
- Modify: `src/features/reconciliation/components/edit-prices-panel.tsx`
- Modify: `src/features/reconciliation/components/adjust-boundary-panel.tsx`
- Modify: `src/features/reconciliation/components/insert-period-panel.tsx`
- Modify: `src/features/reconciliation/components/version-detail.tsx`
- Modify: `src/features/reconciliation/components/adjustments-section.tsx`

- [ ] **Step 11.1: `reconciliation-page.tsx`**

Replace line 22:
```tsx
const { selectedVersionId, openPanel, selectVersion, reset } = useReconciliationStore();
```
with:
```tsx
const selectedVersionId = useReconciliationStore((s) => s.selectedVersionId);
const openPanel = useReconciliationStore((s) => s.openPanel);
const selectVersion = useReconciliationStore((s) => s.selectVersion);
const reset = useReconciliationStore((s) => s.reset);
```

- [ ] **Step 11.2: `timeline.tsx`**

Replace line 11:
```tsx
const { selectedVersionId, selectVersion } = useReconciliationStore();
```
with:
```tsx
const selectedVersionId = useReconciliationStore((s) => s.selectedVersionId);
const selectVersion = useReconciliationStore((s) => s.selectVersion);
```

- [ ] **Step 11.3: `edit-prices-panel.tsx`, `adjust-boundary-panel.tsx`, `insert-period-panel.tsx`**

Each has `const { closePanel } = useReconciliationStore();`. Replace each with:
```tsx
const closePanel = useReconciliationStore((s) => s.closePanel);
```

- [ ] **Step 11.4: `version-detail.tsx`**

Replace `const { openPanelFor } = useReconciliationStore();` with:
```tsx
const openPanelFor = useReconciliationStore((s) => s.openPanelFor);
```

- [ ] **Step 11.5: `adjustments-section.tsx`**

Replace line 51 `const { openPanel, openPanelFor, closePanel } = useReconciliationStore();` with:
```tsx
const openPanel = useReconciliationStore((s) => s.openPanel);
const openPanelFor = useReconciliationStore((s) => s.openPanelFor);
const closePanel = useReconciliationStore((s) => s.closePanel);
```

- [ ] **Step 11.6: Verify**

```bash
npx tsc --noEmit && npm test
grep -rn "= useReconciliationStore()" src/features/reconciliation
```
Expected: no matches (all calls now use selectors).

---

### Task 12: Fix `useDebouncedValue` stale closure

The JSON.stringify-in-deps trick with `// eslint-disable-next-line` is fragile. Depend on `value` directly — React's Object.is equality is fine because the hook is called with an object from `useMemo` upstream.

**Files:**
- Modify: `src/features/export/components/export-page.tsx`

- [ ] **Step 12.1: Replace `useDebouncedValue`**

Replace lines 24–33 in `src/features/export/components/export-page.tsx`:

```typescript
function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);
  return debounced;
}
```

This works because the upstream `filters` object is already memoized via `useMemo` with primitive deps (line 49), so its identity is stable when nothing changed.

- [ ] **Step 12.2: Verify**

```bash
npx tsc --noEmit && npm run lint
```
Expected: no errors, no eslint disable comments needed. Load the export page in dev and confirm filter changes still trigger a 300ms debounced refetch.

---

### Task 13: Fix hardcoded "all time" date in export

`getPresetDates` in `export-page.tsx:17` hardcodes `"2026-01-12"` for the "all" preset. Compute it from filter options instead (the backend already knows the earliest date).

**Files:**
- Modify: `src/features/export/api/types.ts`
- Modify: `src/features/export/api/mock-data.ts`
- Modify: `src/features/export/components/export-page.tsx`

- [ ] **Step 13.1: Add `earliestDataDate` to `ExportFilterOptions`**

Open `src/features/export/api/types.ts` and find the `ExportFilterOptions` interface. Add:
```typescript
earliestDataDate: string; // ISO YYYY-MM-DD
```

- [ ] **Step 13.2: Populate it in mock data**

Open `src/features/export/api/mock-data.ts`. Find where `ExportFilterOptions` is constructed and add `earliestDataDate: "2026-01-12"` to the returned object.

- [ ] **Step 13.3: Use it in `export-page.tsx`**

In `src/features/export/components/export-page.tsx`:

1. Change `getPresetDates` to accept `earliestDate` as a parameter:
```typescript
function getPresetDates(
  preset: DatePreset,
  earliestDate: string,
): { from: string; to: string } {
  const to = new Date();
  const toStr = to.toISOString().split("T")[0];
  if (preset === "all") return { from: earliestDate, to: toStr };
  const days = preset === "7d" ? 7 : preset === "30d" ? 30 : 90;
  const from = new Date(to);
  from.setDate(from.getDate() - days);
  return { from: from.toISOString().split("T")[0], to: toStr };
}
```

2. Move `getPresetDates` usage inside the component, after `filterOptions` is loaded. Since `getPresetDates("30d")` is used to compute `defaultDates` before `filterOptions` is available, change initial state to a lazy initializer and don't use "all" until options load:

Replace lines 39–45 with:
```typescript
const defaultDates = useMemo(() => {
  const to = new Date();
  const toStr = to.toISOString().split("T")[0];
  const from = new Date(to);
  from.setDate(from.getDate() - 30);
  return { from: from.toISOString().split("T")[0], to: toStr };
}, []);

const [dateFrom, setDateFrom] = useState(defaultDates.from);
const [dateTo, setDateTo] = useState(defaultDates.to);
const [datePreset, setDatePreset] = useState<DatePreset | null>("30d");
```

3. Update `handleDatePreset` to thread `filterOptions.earliestDataDate`:
```typescript
function handleDatePreset(preset: DatePreset) {
  if (!filterOptions) return;
  const dates = getPresetDates(preset, filterOptions.earliestDataDate);
  setDateFrom(dates.from);
  setDateTo(dates.to);
  setDatePreset(preset);
}
```

- [ ] **Step 13.4: Verify**

```bash
npx tsc --noEmit && npm test
npm run dev
```
Open the export page, click "All time" — date range should use the mock earliest date.

---

### Task 14: Memoize version date formatting in `version-detail.tsx`

The version timeline formats N dates per render. Cheap but wasteful when many versions.

**Files:**
- Modify: `src/features/reconciliation/components/version-detail.tsx`

- [ ] **Step 14.1: Memoize the derived labels**

Read `version-detail.tsx` first to locate lines 26–29 (the `endLabel` / `startLabel` computations). Wrap them in `useMemo`:

```typescript
const { startLabel, endLabel } = useMemo(() => {
  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  return {
    startLabel: fmt(version.startDate),
    endLabel: version.endDate ? fmt(version.endDate) : "Today",
  };
}, [version.startDate, version.endDate]);
```

Add `useMemo` to the React import at the top of the file if not already imported.

- [ ] **Step 14.2: Verify**

```bash
npx tsc --noEmit && npm test
```

---

### Task 15: Fix `download-bar.tsx` success state on repeat clicks

The 2.5s success toast hides itself via timeout but doesn't reset when the user clicks Download again while `isSuccess` is still true — the effect doesn't re-run on the same value.

**Files:**
- Modify: `src/features/export/components/download-bar.tsx`

- [ ] **Step 15.1: Depend on `downloadUrl` instead of `isSuccess`**

In `src/features/export/components/download-bar.tsx`, replace lines 65–80 with:

```tsx
useEffect(() => {
  if (!downloadUrl) return;
  // Trigger the browser download by programmatically clicking an anchor
  const a = document.createElement("a");
  a.href = downloadUrl;
  a.download = "";
  a.rel = "noopener";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  setShowReady(true);
  const timer = setTimeout(() => setShowReady(false), 2500);
  return () => clearTimeout(timer);
}, [downloadUrl]);
```

Every fresh download produces a new `downloadUrl`, so the effect re-runs each time — no stale-state bug.

- [ ] **Step 15.2: Verify**

```bash
npx tsc --noEmit && npm test
```
In dev, click Download twice in a row — second click should re-show the "Download ready" state.

**Phase 4 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
STOP and report to user.

---

## Phase 5: Inline Formatting Cleanup

63 instances of inline `.toLocaleString()` / `.toFixed(N)` / `/ 1_000_000` need to flow through `format.ts`. This phase does it feature-by-feature.

**Pattern reference** — apply these substitutions throughout:

| Inline pattern | Replacement |
|---|---|
| `` `$${x.toLocaleString()}` `` where `x` is dollars | `formatDollars(x)` |
| `` `$${Math.round(x).toLocaleString()}` `` | `formatRoundedDollars(x)` |
| `` `${x >= 0 ? "+" : ""}$${x}` `` or similar | `formatSignedDollars(x)` |
| `x.toFixed(2)` where `x` is a dollar amount | `formatDollars(x)` — the function already handles decimals |
| `Math.round(bytes / 1_000_000) + " MB"` | `formatFileSize(bytes)` |
| `x.toLocaleString()` where `x` is a count | keep as-is (counts are not dollars) — or use `formatEventCount` if 4+ digits |

---

### Task 16: Replace inline formatting in reconciliation components

**Files:**
- Modify: `src/features/reconciliation/components/reconciliation-summary.tsx`
- Modify: `src/features/reconciliation/components/card-header.tsx`
- Modify: `src/features/reconciliation/components/audit-trail.tsx`
- Modify: `src/features/reconciliation/components/timeline.tsx`
- Modify: `src/features/reconciliation/components/version-detail.tsx`
- Modify: `src/features/reconciliation/components/distribution-preview.tsx`
- Modify: `src/features/reconciliation/components/edit-prices-panel.tsx`
- Modify: `src/features/reconciliation/components/insert-period-panel.tsx`
- Modify: `src/features/reconciliation/components/manual-allocation.tsx`

- [ ] **Step 16.1: `reconciliation-summary.tsx`**

At the top add: `import { formatDollars, formatSignedDollars } from "@/lib/format";`

Replace `` `$${original.toLocaleString()}` `` → `formatDollars(original)`.
Replace `` `$${reconciled.toLocaleString()}` `` → `formatDollars(reconciled)`.
Replace the delta span text computation → `formatSignedDollars(delta)`.

- [ ] **Step 16.2: `card-header.tsx`**

Import: `import { formatRoundedDollars, formatSignedDollars, formatEventCount } from "@/lib/format";`

Line 54: `` `$${Math.round(stats.originalTracked).toLocaleString()}` `` → `formatRoundedDollars(stats.originalTracked)`.
Line 59: same for `reconciledTotal`.
Line 64: `` `${stats.netAdjustments >= 0 ? "+" : ""}$${Math.round(stats.netAdjustments)}` `` → `formatSignedDollars(Math.round(stats.netAdjustments))`.
Line 70: `` `${(stats.eventCount / 1000).toFixed(0)}k / ${stats.currentVersion}` `` → `` `${formatEventCount(stats.eventCount)} / ${stats.currentVersion}` ``.

- [ ] **Step 16.3: `audit-trail.tsx`**

Import `formatSignedDollars`.

Line 50: `` `${entry.delta > 0 ? "+" : ""}$${entry.delta.toFixed(2)}` `` → `formatSignedDollars(entry.delta)`.

- [ ] **Step 16.4: `timeline.tsx`**

Import `formatDollars, formatSignedDollars`.

Line 31: `` `$${timeline.originalTotal.toLocaleString()}` `` → `formatDollars(timeline.originalTotal)`.
Line 45: `` `${timeline.adjustmentTotal >= 0 ? "+" : ""}$${timeline.adjustmentTotal.toFixed(2)} adjustments` `` → `` `${formatSignedDollars(timeline.adjustmentTotal)} adjustments` ``.
Line 53: `` `$${timeline.reconciledTotal.toLocaleString()}` `` → `formatDollars(timeline.reconciledTotal)`.
Line 106: `` `$${seg.cost}` `` → `formatDollars(seg.cost)` (assuming `seg.cost` is numeric; if string, leave).

- [ ] **Step 16.5: `version-detail.tsx`, `distribution-preview.tsx`, `edit-prices-panel.tsx`, `insert-period-panel.tsx`, `manual-allocation.tsx`**

For each file:
1. Read it.
2. Identify every `.toLocaleString()`, `.toFixed(N)`, or `/ 1_000_000` used for displaying dollars.
3. Apply the substitution table above.
4. For `.toFixed(10)` in prices (edit-prices-panel, insert-period-panel), these are per-unit prices — use `formatPrice` from format.ts (already exists).

- [ ] **Step 16.6: Verify**

```bash
npx tsc --noEmit && npm test
grep -rn "\.toLocaleString\|\.toFixed" src/features/reconciliation --include="*.tsx"
```
Expected: no matches (or only in comments).

---

### Task 17: Replace inline formatting in dashboard, billing, customers, export

**Files:**
- Modify: `src/features/dashboard/components/stats-grid.tsx`
- Modify: `src/features/dashboard/components/customer-table.tsx`
- Modify: `src/features/dashboard/components/breakdown-card.tsx`
- Modify: `src/features/dashboard/components/cost-breakdown-chart.tsx`
- Modify: `src/features/dashboard/components/revenue-chart.tsx`
- Modify: `src/features/billing/components/margin-stats.tsx`
- Modify: `src/features/billing/components/margin-tree-row.tsx`
- Modify: `src/features/billing/components/change-history.tsx`
- Modify: `src/features/billing/components/impact-preview.tsx`
- Modify: `src/features/customers/components/orphan-row.tsx`
- Modify: `src/features/export/components/export-estimate.tsx`
- Modify: `src/features/onboarding/components/review-step.tsx`

- [ ] **Step 17.1: Dashboard sweep**

Apply the substitution table per file. Use `formatDollars` for dollar values, `formatEventCount` for large counts. Ensure imports are added.

- [ ] **Step 17.2: Billing sweep**

Same pattern. Replace `` `$${stats.apiCosts30d.toLocaleString()}` `` etc in `margin-stats.tsx` with `formatDollars(stats.apiCosts30d)`.

- [ ] **Step 17.3: Customers sweep**

`orphan-row.tsx` — replace any inline formatting.

- [ ] **Step 17.4: Export sweep — `export-estimate.tsx`**

Replace line 17: `` `${Math.round(bytes / 1_000_000)} MB` `` → `formatFileSize(bytes)`.
Replace line 78 `.toLocaleString()` → `formatDollars` (or `formatEventCount` if a count).

- [ ] **Step 17.5: Onboarding — `review-step.tsx`**

Replace any inline formatting with helpers.

- [ ] **Step 17.6: Final sweep verification**

```bash
grep -rn "\.toLocaleString\|\.toFixed\|/ 1_000_000\|/ 1000000" src/features --include="*.tsx"
```
Expected: zero matches. Any remaining should only be in helpers or non-dollar contexts with a comment explaining why.

**Phase 5 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
Spot-check every page for identical number formatting. STOP and report to user.

---

## Phase 6: Component Refactors

High-prop and monolithic components need structural improvements.

---

### Task 18: Consolidate duplicate `formatVersionLabel`

Two functions with the same name and different signatures exist. Move both into a single shared file with distinct, clear names.

**Files:**
- Create: `src/features/reconciliation/lib/version-label.ts`
- Create: `src/features/reconciliation/lib/version-label.test.ts`
- Modify: `src/features/reconciliation/components/version-detail.tsx`
- Modify: `src/features/reconciliation/components/insert-period-panel.tsx`

- [ ] **Step 18.1: Write failing tests**

Create `src/features/reconciliation/lib/version-label.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import { formatShortVersionLabel, formatVersionWithRange } from "./version-label";
import type { PricingVersion } from "../api/types";

describe("formatShortVersionLabel", () => {
  it("expands 'v1' → 'Version 1'", () => {
    expect(formatShortVersionLabel("v1")).toBe("Version 1");
  });
  it("returns non-matching labels unchanged", () => {
    expect(formatShortVersionLabel("Initial")).toBe("Initial");
  });
});

describe("formatVersionWithRange", () => {
  it("formats a version with start and end dates", () => {
    const v: PricingVersion = {
      id: "v1",
      label: "v1",
      status: "superseded",
      startDate: "2026-03-01",
      endDate: "2026-03-10",
    } as PricingVersion;
    expect(formatVersionWithRange(v)).toContain("Version 1");
    expect(formatVersionWithRange(v)).toContain("Mar");
  });
});
```

- [ ] **Step 18.2: Run to verify fail**

```bash
npx vitest run src/features/reconciliation/lib/version-label.test.ts
```
Expected: FAIL "Cannot find module".

- [ ] **Step 18.3: Implement**

Create `src/features/reconciliation/lib/version-label.ts`:

```typescript
import type { PricingVersion } from "../api/types";

/**
 * Expand a short version label like "v1" to "Version 1".
 * Returns the original label if it doesn't match the pattern.
 */
export function formatShortVersionLabel(label: string): string {
  const match = label.match(/^v(\d+)$/i);
  return match ? `Version ${match[1]}` : label;
}

/**
 * Format a version with its label and date range.
 * e.g. "Version 1 (1 Mar – 10 Mar)"
 */
export function formatVersionWithRange(version: PricingVersion): string {
  const label = formatShortVersionLabel(version.label);
  const fmt = (iso: string) =>
    new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "short" });
  const start = fmt(version.startDate);
  const end = version.endDate ? fmt(version.endDate) : "Today";
  return `${label} (${start} – ${end})`;
}
```

- [ ] **Step 18.4: Verify tests pass**

```bash
npx vitest run src/features/reconciliation/lib/version-label.test.ts
```
Expected: PASS.

- [ ] **Step 18.5: Update the callers**

In `version-detail.tsx`:
1. Delete the local `formatVersionLabel` function.
2. Import: `import { formatShortVersionLabel } from "../lib/version-label";`
3. Replace each call to `formatVersionLabel(...)` with `formatShortVersionLabel(...)`.

In `insert-period-panel.tsx`:
1. Delete the local `formatVersionLabel` function.
2. Import: `import { formatVersionWithRange } from "../lib/version-label";`
3. Replace each call with `formatVersionWithRange(...)`.

- [ ] **Step 18.6: Verify**

```bash
npx tsc --noEmit && npm test
```

---

### Task 19: Refactor `ExportFilters` to single state object

11 props → 2 props (`filters` + `onFiltersChange`).

**Files:**
- Modify: `src/features/export/components/export-filters.tsx`
- Modify: `src/features/export/components/export-page.tsx`

- [ ] **Step 19.1: Redefine `ExportFiltersProps`**

In `src/features/export/components/export-filters.tsx`, replace lines 9–23 (the old `ExportFiltersProps`) with:

```typescript
export interface ExportFiltersState {
  dateFrom: string;
  dateTo: string;
  datePreset: DatePreset | null;
  customerIds: string[];
  productKeys: string[];
  cardKeys: string[];
}

interface ExportFiltersProps {
  filterOptions: ExportFilterOptions;
  state: ExportFiltersState;
  onStateChange: (patch: Partial<ExportFiltersState>) => void;
  onDatePreset: (preset: DatePreset) => void;
}
```

- [ ] **Step 19.2: Update `ExportFilters` function**

Replace the destructure in the function body and inline each onChange:

```tsx
export function ExportFilters({
  filterOptions,
  state,
  onStateChange,
  onDatePreset,
}: ExportFiltersProps) {
  return (
    <div className="rounded-xl border border-border p-4">
      <h2 className="mb-3 text-sm font-medium">Filters</h2>

      <div className="mb-2.5 grid grid-cols-2 gap-2.5">
        <div>
          <label className="mb-1 block text-xs font-medium">From</label>
          <input
            type="date"
            value={state.dateFrom}
            onChange={(e) => onStateChange({ dateFrom: e.target.value, datePreset: null })}
            className="w-full rounded-lg border border-border bg-transparent px-2.5 py-1.5 text-xs focus:border-ring focus:outline-none"
          />
        </div>
        <div>
          <label className="mb-1 block text-xs font-medium">To</label>
          <input
            type="date"
            value={state.dateTo}
            onChange={(e) => onStateChange({ dateTo: e.target.value, datePreset: null })}
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
              state.datePreset === p.key
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
          selectedIds={state.customerIds}
          onSelectionChange={(ids) => onStateChange({ customerIds: ids })}
        />
      </div>

      <div className="mb-3">
        <TogglePillGroup
          label="Products"
          allLabel="All products"
          options={filterOptions.products}
          selectedKeys={state.productKeys}
          onSelectionChange={(keys) => onStateChange({ productKeys: keys })}
        />
      </div>

      <TogglePillGroup
        label="Pricing cards"
        allLabel="All cards"
        options={filterOptions.cards}
        selectedKeys={state.cardKeys}
        onSelectionChange={(keys) => onStateChange({ cardKeys: keys })}
      />
    </div>
  );
}
```

- [ ] **Step 19.3: Update `export-page.tsx` to use the consolidated state**

In `src/features/export/components/export-page.tsx`:

1. Import the new type: add `import type { ExportFiltersState } from "./export-filters";` at the top.
2. Replace lines 40–45 (the individual useState calls) with:
```typescript
const [filtersState, setFiltersState] = useState<ExportFiltersState>(() => ({
  dateFrom: defaultDates.from,
  dateTo: defaultDates.to,
  datePreset: "30d",
  customerIds: [],
  productKeys: [],
  cardKeys: [],
}));

const updateFilters = (patch: Partial<ExportFiltersState>) =>
  setFiltersState((prev) => ({ ...prev, ...patch }));
```

3. Update `filters` useMemo (line 49) to read from `filtersState`:
```typescript
const filters = useMemo<ExportFilters>(
  () => ({
    dateFrom: filtersState.dateFrom,
    dateTo: filtersState.dateTo,
    customerIds: filtersState.customerIds,
    productKeys: filtersState.productKeys,
    cardKeys: filtersState.cardKeys,
    granularity,
  }),
  [filtersState, granularity],
);
```

4. Update `handleDatePreset`:
```typescript
function handleDatePreset(preset: DatePreset) {
  if (!filterOptions) return;
  const dates = getPresetDates(preset, filterOptions.earliestDataDate);
  updateFilters({ dateFrom: dates.from, dateTo: dates.to, datePreset: preset });
}
```

5. Replace the `<ExportFiltersPanel>` usage (lines 115–129):
```tsx
<ExportFiltersPanel
  filterOptions={filterOptions}
  state={filtersState}
  onStateChange={updateFilters}
  onDatePreset={handleDatePreset}
/>
```

6. Delete the now-unused `handleDateFromChange` and `handleDateToChange` functions (lines 74–82).

7. Update `ExportEstimate` call (lines 133–141) — pass `filtersState` fields instead of `selectedCustomerIds` etc. Or just inline the references:
```tsx
<ExportEstimate
  estimate={preview.estimate}
  filterOptions={filterOptions}
  selectedCustomerIds={filtersState.customerIds}
  selectedProductKeys={filtersState.productKeys}
  selectedCardKeys={filtersState.cardKeys}
  dateFrom={filtersState.dateFrom}
  dateTo={filtersState.dateTo}
/>
```

- [ ] **Step 19.4: Verify**

```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
Open the export page, adjust every filter — behavior should be identical.

---

### Task 20: Refactor `CustomerTable` to own its search/filter state

Currently `customer-table.tsx` takes 7 props mixing data + UI state + handlers. Move the UI state (search query, active filter, editing ID) into the table itself; only pass data.

**Files:**
- Modify: `src/features/customers/components/customer-table.tsx`
- Modify: `src/features/customers/components/customer-mapping-page.tsx`

- [ ] **Step 20.1: Read `customer-mapping-page.tsx` to find where state lives**

```bash
```
Read the file to see how `CustomerTable` is used and where the state currently lives.

- [ ] **Step 20.2: Simplify `CustomerTableProps`**

In `src/features/customers/components/customer-table.tsx`, replace `CustomerTableProps` with:

```typescript
interface CustomerTableProps {
  customers: CustomerMapping[];
}
```

Move the state into the component body:
```typescript
export function CustomerTable({ customers }: CustomerTableProps) {
  const [activeFilter, setActiveFilter] = useState<CustomerFilterKey>("all");
  const [searchQuery, setSearchQuery] = useState("");
  const [editingCustomerId, setEditingCustomerId] = useState<string | null>(null);

  // ... rest stays the same, replacing onFilterChange → setActiveFilter, etc.
}
```

Add `import { useState } from "react";` if not already present.

- [ ] **Step 20.3: Update the parent page**

In `customer-mapping-page.tsx`:
1. Delete the useState calls for `activeFilter`, `searchQuery`, `editingCustomerId`.
2. Change the `<CustomerTable>` usage to just pass `customers={...}`.

- [ ] **Step 20.4: Verify**

```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
Navigate to /customers, filter, search, edit — identical behavior.

---

### Task 21: Replace inline button styles with shadcn `Button`

CLAUDE.md mandates using shadcn components. Many places in reconciliation use `className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent"` — that's `<Button variant="outline" size="xs">`.

**Files:**
- Modify: `src/features/reconciliation/components/adjustments-section.tsx`
- Modify: `src/features/reconciliation/components/edit-prices-panel.tsx`
- Modify: `src/features/reconciliation/components/adjust-boundary-panel.tsx`
- Modify: `src/features/reconciliation/components/insert-period-panel.tsx`
- Modify: `src/features/reconciliation/components/card-header.tsx`

- [ ] **Step 21.1: Identify and replace in `edit-prices-panel.tsx`**

Add `import { Button } from "@/components/ui/button";`.

Find `<button ... className="rounded-md border border-border px-3 py-1.5 text-[11px] text-muted-foreground hover:bg-accent">Cancel</button>` and replace with `<Button type="button" variant="outline" size="xs" onClick={...}>Cancel</Button>`.

Do the same for Apply buttons (`variant="default"`).

- [ ] **Step 21.2: `adjust-boundary-panel.tsx`, `insert-period-panel.tsx`**

Same treatment — find inline `<button className="rounded-md border border-border ...">` patterns and replace with the shadcn `Button`.

- [ ] **Step 21.3: `adjustments-section.tsx` — Cancel + Record buttons**

Lines 241–247: replace the two inline buttons with `<Button>`. Note: the Record button uses `bg-brand-purple` — keep it as `<Button variant="default">` and override with `className="bg-brand-purple text-brand-purple-foreground"`, OR add a `brand` variant to `button.tsx`. For now, use `className` override to avoid scope creep.

Also replace lines 107–110 (the "Record an adjustment" button) and the type-selector and distribution-mode selector buttons (lines 124–128, 156–162) — these are card-style selectors, NOT standard buttons. Leave those as-is with a comment: `// Intentional inline style: custom selector card, not a standard button.`

- [ ] **Step 21.4: `card-header.tsx` — Edit card button**

Lines 42–47: replace with `<Button variant="outline" size="xs">Edit card</Button>`.

- [ ] **Step 21.5: Verify**

```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
All buttons should look similar (shadcn outline/default variants are close to the old styles). Minor visual diffs are acceptable — this normalizes styling.

**Phase 6 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
STOP and report to user.

---

## Phase 7: `adjustments-section` Refactor

The 252-line component with 14 `useState` hooks is the single worst file in the codebase. Break it into:
1. A `useReducer` for consolidated state.
2. Four sub-components for each UI section.
3. A main component under 150 lines that composes them.

---

### Task 22: Create the reducer with tests

**Files:**
- Create: `src/features/reconciliation/lib/adjustment-form-reducer.ts`
- Create: `src/features/reconciliation/lib/adjustment-form-reducer.test.ts`

- [ ] **Step 22.1: Write failing tests**

Create `src/features/reconciliation/lib/adjustment-form-reducer.test.ts`:

```typescript
import { describe, expect, it } from "vitest";
import {
  adjustmentFormReducer,
  initialAdjustmentFormState,
  type AdjustmentFormState,
} from "./adjustment-form-reducer";

describe("adjustmentFormReducer", () => {
  const initial = initialAdjustmentFormState;

  it("SET_TYPE updates type and default amount", () => {
    const next = adjustmentFormReducer(initial, {
      type: "SET_TYPE",
      payload: { type: "missing_costs", defaultAmount: 45 },
    });
    expect(next.adjType).toBe("missing_costs");
    expect(next.amount).toBe(45);
  });

  it("SET_AMOUNT updates amount only", () => {
    const next = adjustmentFormReducer(initial, { type: "SET_AMOUNT", payload: 100 });
    expect(next.amount).toBe(100);
    expect(next.adjType).toBe(initial.adjType);
  });

  it("SET_DIST_MODE to manual initializes even allocations", () => {
    const state: AdjustmentFormState = {
      ...initial,
      amount: 100,
      periodStart: "2026-03-01",
      periodEnd: "2026-03-02",
    };
    const next = adjustmentFormReducer(state, {
      type: "SET_DIST_MODE",
      payload: "manual",
    });
    expect(next.distMode).toBe("manual");
    expect(Object.keys(next.manualAllocations).length).toBe(2);
  });

  it("SET_MANUAL_ALLOCATION updates a single day", () => {
    const next = adjustmentFormReducer(
      { ...initial, manualAllocations: { "1 Mar": 10 } },
      { type: "SET_MANUAL_ALLOCATION", payload: { label: "1 Mar", value: 20 } },
    );
    expect(next.manualAllocations["1 Mar"]).toBe(20);
  });

  it("SET_ERROR / CLEAR_ERROR", () => {
    const withError = adjustmentFormReducer(initial, {
      type: "SET_ERROR",
      payload: "boom",
    });
    expect(withError.error).toBe("boom");
    const cleared = adjustmentFormReducer(withError, { type: "CLEAR_ERROR" });
    expect(cleared.error).toBeNull();
  });
});
```

- [ ] **Step 22.2: Run to verify fail**

```bash
npx vitest run src/features/reconciliation/lib/adjustment-form-reducer.test.ts
```
Expected: FAIL "Cannot find module".

- [ ] **Step 22.3: Implement the reducer**

Create `src/features/reconciliation/lib/adjustment-form-reducer.ts`:

```typescript
import type { AdjustmentType, DistributionMode } from "../api/types";

export interface AdjustmentFormState {
  adjType: AdjustmentType;
  amount: number;
  product: string | null;
  distMode: DistributionMode;
  lumpDate: string;
  lumpTime: string;
  periodStart: string;
  periodEnd: string;
  proportionalBasis: "card" | "product";
  manualAllocations: Record<string, number>;
  reason: string;
  evidence: string;
  loading: boolean;
  error: string | null;
}

export const initialAdjustmentFormState: AdjustmentFormState = {
  adjType: "credit_refund",
  amount: -25,
  product: null,
  distMode: "lump_sum",
  lumpDate: "2026-03-10",
  lumpTime: "00:00",
  periodStart: "2026-03-01",
  periodEnd: "2026-03-07",
  proportionalBasis: "card",
  manualAllocations: {},
  reason: "",
  evidence: "",
  loading: false,
  error: null,
};

export type AdjustmentFormAction =
  | { type: "SET_TYPE"; payload: { type: AdjustmentType; defaultAmount: number } }
  | { type: "SET_AMOUNT"; payload: number }
  | { type: "SET_PRODUCT"; payload: string | null }
  | { type: "SET_DIST_MODE"; payload: DistributionMode }
  | { type: "SET_LUMP_DATE"; payload: string }
  | { type: "SET_LUMP_TIME"; payload: string }
  | { type: "SET_PERIOD_START"; payload: string }
  | { type: "SET_PERIOD_END"; payload: string }
  | { type: "SET_PROPORTIONAL_BASIS"; payload: "card" | "product" }
  | { type: "SET_MANUAL_ALLOCATION"; payload: { label: string; value: number } }
  | { type: "RESET_MANUAL_ALLOCATIONS"; payload: Record<string, number> }
  | { type: "SET_REASON"; payload: string }
  | { type: "SET_EVIDENCE"; payload: string }
  | { type: "SET_LOADING"; payload: boolean }
  | { type: "SET_ERROR"; payload: string }
  | { type: "CLEAR_ERROR" };

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

export function getDayLabels(start: string, end: string): string[] {
  const labels: string[] = [];
  const s = new Date(start);
  const e = new Date(end);
  while (s <= e) {
    labels.push(`${s.getDate()} ${MONTHS[s.getMonth()]}`);
    s.setDate(s.getDate() + 1);
  }
  return labels;
}

function buildEvenAllocations(
  start: string,
  end: string,
  amount: number,
): Record<string, number> {
  const labels = getDayLabels(start, end);
  if (labels.length === 0) return {};
  const perDay = Math.round((Math.abs(amount) / labels.length) * 100) / 100;
  const allocs: Record<string, number> = {};
  labels.forEach((l) => {
    allocs[l] = perDay;
  });
  return allocs;
}

export function adjustmentFormReducer(
  state: AdjustmentFormState,
  action: AdjustmentFormAction,
): AdjustmentFormState {
  switch (action.type) {
    case "SET_TYPE":
      return { ...state, adjType: action.payload.type, amount: action.payload.defaultAmount };
    case "SET_AMOUNT":
      return { ...state, amount: action.payload };
    case "SET_PRODUCT":
      return { ...state, product: action.payload };
    case "SET_DIST_MODE": {
      const next = { ...state, distMode: action.payload };
      if (action.payload === "manual") {
        next.manualAllocations = buildEvenAllocations(
          state.periodStart,
          state.periodEnd,
          state.amount,
        );
      }
      return next;
    }
    case "SET_LUMP_DATE":
      return { ...state, lumpDate: action.payload };
    case "SET_LUMP_TIME":
      return { ...state, lumpTime: action.payload };
    case "SET_PERIOD_START": {
      const next = { ...state, periodStart: action.payload };
      if (state.distMode === "manual") {
        next.manualAllocations = buildEvenAllocations(
          action.payload,
          state.periodEnd,
          state.amount,
        );
      }
      return next;
    }
    case "SET_PERIOD_END": {
      const next = { ...state, periodEnd: action.payload };
      if (state.distMode === "manual") {
        next.manualAllocations = buildEvenAllocations(
          state.periodStart,
          action.payload,
          state.amount,
        );
      }
      return next;
    }
    case "SET_PROPORTIONAL_BASIS":
      return { ...state, proportionalBasis: action.payload };
    case "SET_MANUAL_ALLOCATION":
      return {
        ...state,
        manualAllocations: {
          ...state.manualAllocations,
          [action.payload.label]: action.payload.value,
        },
      };
    case "RESET_MANUAL_ALLOCATIONS":
      return { ...state, manualAllocations: action.payload };
    case "SET_REASON":
      return { ...state, reason: action.payload };
    case "SET_EVIDENCE":
      return { ...state, evidence: action.payload };
    case "SET_LOADING":
      return { ...state, loading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload, loading: false };
    case "CLEAR_ERROR":
      return { ...state, error: null };
    default:
      return state;
  }
}
```

- [ ] **Step 22.4: Verify tests pass**

```bash
npx vitest run src/features/reconciliation/lib/adjustment-form-reducer.test.ts
```
Expected: PASS.

---

### Task 23: Split `adjustments-section.tsx` into sub-components

**Files:**
- Create: `src/features/reconciliation/components/adjustment-type-selector.tsx`
- Create: `src/features/reconciliation/components/adjustment-amount-fields.tsx`
- Create: `src/features/reconciliation/components/adjustment-distribution-fields.tsx`
- Create: `src/features/reconciliation/components/adjustment-reason-fields.tsx`
- Modify: `src/features/reconciliation/components/adjustments-section.tsx`

- [ ] **Step 23.1: Create `adjustment-type-selector.tsx`**

```tsx
import { cn } from "@/lib/utils";
import type { AdjustmentType } from "../api/types";

interface TypeOption {
  value: AdjustmentType;
  label: string;
  sub: string;
  defaultAmt: number;
}

const TYPE_OPTIONS: TypeOption[] = [
  {
    value: "credit_refund",
    label: "Credit or refund",
    sub: "Provider refund, billing credit, or cost reversal.",
    defaultAmt: -25,
  },
  {
    value: "missing_costs",
    label: "Missing costs",
    sub: "Costs that were never tracked by the system.",
    defaultAmt: 45,
  },
];

interface Props {
  value: AdjustmentType;
  onChange: (type: AdjustmentType, defaultAmount: number) => void;
}

export function AdjustmentTypeSelector({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-2 gap-2.5">
      {TYPE_OPTIONS.map((t) => (
        <button
          key={t.value}
          type="button"
          onClick={() => onChange(t.value, t.defaultAmt)}
          className={cn(
            "rounded-xl border px-3 py-2.5 text-left transition-colors",
            value === t.value
              ? "border-2 border-foreground"
              : "border-border hover:bg-accent",
          )}
        >
          <div className="text-[12px] font-medium">{t.label}</div>
          <div className="text-[10px] text-muted-foreground">{t.sub}</div>
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 23.2: Create `adjustment-amount-fields.tsx`**

```tsx
interface Props {
  amount: number;
  product: string | null;
  onAmountChange: (amount: number) => void;
  onProductChange: (product: string | null) => void;
}

export function AdjustmentAmountFields({
  amount,
  product,
  onAmountChange,
  onProductChange,
}: Props) {
  return (
    <div className="grid grid-cols-2 gap-3">
      <div>
        <label className="mb-1 block text-[10px] font-medium">Total amount ($)</label>
        <input
          type="number"
          step="any"
          value={amount}
          onChange={(e) => onAmountChange(parseFloat(e.target.value) || 0)}
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 font-mono text-[12px] outline-none focus:border-muted-foreground"
        />
        <p className="mt-0.5 text-[10px] text-muted-foreground">Negative = credit/refund</p>
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-medium">Attribute to product</label>
        <select
          value={product ?? ""}
          onChange={(e) => onProductChange(e.target.value || null)}
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
        >
          <option value="">No product (card-level)</option>
          <option value="property_search">Property search</option>
          <option value="doc_summariser">Doc summariser</option>
          <option value="content_gen">Content gen</option>
        </select>
      </div>
    </div>
  );
}
```

- [ ] **Step 23.3: Create `adjustment-distribution-fields.tsx`**

This is the biggest sub-component — it contains the distribution-mode selector + the conditional fields per mode.

```tsx
import { cn } from "@/lib/utils";
import type { DistributionMode } from "../api/types";
import { DateRangeFields } from "./date-range-fields";
import { ManualAllocation } from "./manual-allocation";

interface Props {
  distMode: DistributionMode;
  amount: number;
  lumpDate: string;
  lumpTime: string;
  periodStart: string;
  periodEnd: string;
  proportionalBasis: "card" | "product";
  manualAllocations: Record<string, number>;
  manualDayLabels: string[];
  onDistModeChange: (mode: DistributionMode) => void;
  onLumpDateChange: (date: string) => void;
  onLumpTimeChange: (time: string) => void;
  onPeriodStartChange: (date: string) => void;
  onPeriodEndChange: (date: string) => void;
  onProportionalBasisChange: (basis: "card" | "product") => void;
  onManualAllocationChange: (label: string, value: number) => void;
}

const DIST_MODES: { value: DistributionMode; label: string; sub: string }[] = [
  { value: "lump_sum", label: "Lump sum", sub: "Single date" },
  { value: "even_daily", label: "Even daily", sub: "Split equally" },
  { value: "proportional", label: "Proportional", sub: "Match existing" },
  { value: "manual", label: "Manual", sub: "Set each day" },
];

export function AdjustmentDistributionFields({
  distMode,
  amount,
  lumpDate,
  lumpTime,
  periodStart,
  periodEnd,
  proportionalBasis,
  manualAllocations,
  manualDayLabels,
  onDistModeChange,
  onLumpDateChange,
  onLumpTimeChange,
  onPeriodStartChange,
  onPeriodEndChange,
  onProportionalBasisChange,
  onManualAllocationChange,
}: Props) {
  return (
    <>
      <div>
        <div className="mb-2 text-[10px] font-medium">Distribution</div>
        <div className="grid grid-cols-4 gap-2">
          {DIST_MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              onClick={() => onDistModeChange(m.value)}
              className={cn(
                "rounded-lg border px-2.5 py-2 text-left transition-colors",
                distMode === m.value
                  ? "border-2 border-foreground"
                  : "border-border hover:bg-accent",
              )}
            >
              <div className="text-[11px] font-medium">{m.label}</div>
              <div className="text-[9px] text-muted-foreground">{m.sub}</div>
            </button>
          ))}
        </div>
      </div>

      {distMode === "lump_sum" && (
        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="mb-1 block text-[10px] font-medium">Date</label>
            <input
              type="date"
              value={lumpDate}
              onChange={(e) => onLumpDateChange(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
            />
          </div>
          <div>
            <label className="mb-1 block text-[10px] font-medium">Time</label>
            <input
              type="time"
              value={lumpTime}
              onChange={(e) => onLumpTimeChange(e.target.value)}
              className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
            />
          </div>
        </div>
      )}

      {distMode === "even_daily" && (
        <DateRangeFields
          startDate={periodStart}
          endDate={periodEnd}
          onStartChange={onPeriodStartChange}
          onEndChange={onPeriodEndChange}
        />
      )}

      {distMode === "proportional" && (
        <>
          <DateRangeFields
            startDate={periodStart}
            endDate={periodEnd}
            onStartChange={onPeriodStartChange}
            onEndChange={onPeriodEndChange}
          />
          <div>
            <label className="mb-1 block text-[10px] font-medium">Proportional to</label>
            <select
              value={proportionalBasis}
              onChange={(e) =>
                onProportionalBasisChange(e.target.value as "card" | "product")
              }
              className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[12px] outline-none focus:border-muted-foreground"
            >
              <option value="card">Total tracked costs for this card</option>
              <option value="product">Costs for selected product only</option>
            </select>
            <p className="mt-0.5 text-[10px] text-muted-foreground">
              Allocates more to days with higher existing costs, less to quieter days.
            </p>
          </div>
        </>
      )}

      {distMode === "manual" && (
        <>
          <DateRangeFields
            startDate={periodStart}
            endDate={periodEnd}
            onStartChange={onPeriodStartChange}
            onEndChange={onPeriodEndChange}
          />
          <ManualAllocation
            dayLabels={manualDayLabels}
            allocations={manualAllocations}
            targetAmount={Math.abs(amount)}
            onChange={onManualAllocationChange}
          />
        </>
      )}
    </>
  );
}
```

- [ ] **Step 23.4: Create `adjustment-reason-fields.tsx`**

```tsx
interface Props {
  reason: string;
  evidence: string;
  onReasonChange: (value: string) => void;
  onEvidenceChange: (value: string) => void;
}

export function AdjustmentReasonFields({
  reason,
  evidence,
  onReasonChange,
  onEvidenceChange,
}: Props) {
  return (
    <>
      <div>
        <label className="mb-1 block text-[10px] font-medium">Reason (required)</label>
        <textarea
          value={reason}
          onChange={(e) => onReasonChange(e.target.value)}
          placeholder="e.g. Google Cloud issued a $25 credit for service disruption on 10 Mar."
          className="min-h-[48px] w-full rounded-lg border border-border bg-background px-3 py-2 text-[11px] outline-none focus:border-muted-foreground"
        />
      </div>
      <div>
        <label className="mb-1 block text-[10px] font-medium">
          Supporting evidence (optional)
        </label>
        <input
          value={evidence}
          onChange={(e) => onEvidenceChange(e.target.value)}
          placeholder="e.g. Invoice link, support ticket URL"
          className="w-full rounded-lg border border-border bg-background px-3 py-1.5 text-[11px] outline-none focus:border-muted-foreground"
        />
      </div>
    </>
  );
}
```

- [ ] **Step 23.5: Rewrite `adjustments-section.tsx`**

Replace the entire contents of `src/features/reconciliation/components/adjustments-section.tsx` with:

```tsx
import { useReducer, useMemo } from "react";
import { Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useReconciliationStore } from "../stores/reconciliation-store";
import {
  adjustmentFormReducer,
  initialAdjustmentFormState,
  getDayLabels,
} from "../lib/adjustment-form-reducer";
import { AdjustmentTypeSelector } from "./adjustment-type-selector";
import { AdjustmentAmountFields } from "./adjustment-amount-fields";
import { AdjustmentDistributionFields } from "./adjustment-distribution-fields";
import { AdjustmentReasonFields } from "./adjustment-reason-fields";
import { DistributionPreview } from "./distribution-preview";
import type { AdjustmentType, DistributionMode } from "../api/types";

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

export function AdjustmentsSection({ onRecord }: AdjustmentsSectionProps) {
  const openPanel = useReconciliationStore((s) => s.openPanel);
  const openPanelFor = useReconciliationStore((s) => s.openPanelFor);
  const closePanel = useReconciliationStore((s) => s.closePanel);
  const isOpen = openPanel === "adjustments";

  const [state, dispatch] = useReducer(adjustmentFormReducer, initialAdjustmentFormState);
  const manualDayLabels = useMemo(
    () => getDayLabels(state.periodStart, state.periodEnd),
    [state.periodStart, state.periodEnd],
  );

  const handleRecord = async () => {
    if (!state.reason.trim()) return;
    dispatch({ type: "SET_LOADING", payload: true });
    dispatch({ type: "CLEAR_ERROR" });
    try {
      await onRecord({
        type: state.adjType,
        amount: state.amount,
        product: state.product,
        distributionMode: state.distMode,
        distributionConfig: {
          lumpDate: state.lumpDate,
          lumpTime: state.lumpTime,
          periodStart: state.periodStart,
          periodEnd: state.periodEnd,
          ...(state.distMode === "proportional"
            ? { proportionalBasis: state.proportionalBasis }
            : {}),
          ...(state.distMode === "manual"
            ? { manualAllocations: state.manualAllocations }
            : {}),
        },
        reason: state.reason,
        evidence: state.evidence || null,
      });
      closePanel();
    } catch (e) {
      dispatch({
        type: "SET_ERROR",
        payload: e instanceof Error ? e.message : "Failed to record adjustment.",
      });
    } finally {
      dispatch({ type: "SET_LOADING", payload: false });
    }
  };

  return (
    <div>
      <div className="flex items-center justify-between">
        <h2 className="text-[14px] font-semibold">Adjustments</h2>
        {!isOpen && (
          <Button
            type="button"
            variant="outline"
            size="xs"
            onClick={() => openPanelFor("adjustments")}
          >
            Record an adjustment
          </Button>
        )}
      </div>
      <p className="mt-0.5 text-[11px] text-muted-foreground">
        For costs outside the event pipeline — refunds, credits, missed data, or invoice
        reconciliation.
      </p>

      {isOpen && (
        <div className="mt-3 space-y-4 rounded-xl border border-border px-4 py-4">
          <AdjustmentTypeSelector
            value={state.adjType}
            onChange={(type, defaultAmount) =>
              dispatch({ type: "SET_TYPE", payload: { type, defaultAmount } })
            }
          />

          <AdjustmentAmountFields
            amount={state.amount}
            product={state.product}
            onAmountChange={(amount) => dispatch({ type: "SET_AMOUNT", payload: amount })}
            onProductChange={(product) => dispatch({ type: "SET_PRODUCT", payload: product })}
          />

          <AdjustmentDistributionFields
            distMode={state.distMode}
            amount={state.amount}
            lumpDate={state.lumpDate}
            lumpTime={state.lumpTime}
            periodStart={state.periodStart}
            periodEnd={state.periodEnd}
            proportionalBasis={state.proportionalBasis}
            manualAllocations={state.manualAllocations}
            manualDayLabels={manualDayLabels}
            onDistModeChange={(mode) => dispatch({ type: "SET_DIST_MODE", payload: mode })}
            onLumpDateChange={(date) => dispatch({ type: "SET_LUMP_DATE", payload: date })}
            onLumpTimeChange={(time) => dispatch({ type: "SET_LUMP_TIME", payload: time })}
            onPeriodStartChange={(date) =>
              dispatch({ type: "SET_PERIOD_START", payload: date })
            }
            onPeriodEndChange={(date) => dispatch({ type: "SET_PERIOD_END", payload: date })}
            onProportionalBasisChange={(basis) =>
              dispatch({ type: "SET_PROPORTIONAL_BASIS", payload: basis })
            }
            onManualAllocationChange={(label, value) =>
              dispatch({ type: "SET_MANUAL_ALLOCATION", payload: { label, value } })
            }
          />

          <DistributionPreview
            mode={state.distMode}
            amount={state.amount}
            startDate={state.distMode === "lump_sum" ? state.lumpDate : state.periodStart}
            endDate={state.distMode === "lump_sum" ? state.lumpDate : state.periodEnd}
            manualAllocations={
              state.distMode === "manual" ? state.manualAllocations : undefined
            }
          />

          <AdjustmentReasonFields
            reason={state.reason}
            evidence={state.evidence}
            onReasonChange={(value) => dispatch({ type: "SET_REASON", payload: value })}
            onEvidenceChange={(value) => dispatch({ type: "SET_EVIDENCE", payload: value })}
          />

          {state.error && <p className="text-[11px] text-value-negative">{state.error}</p>}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="xs" onClick={closePanel}>
              Cancel
            </Button>
            <Button
              type="button"
              size="xs"
              onClick={handleRecord}
              disabled={!state.reason.trim() || state.loading}
              className="bg-brand-purple text-brand-purple-foreground hover:opacity-90"
            >
              {state.loading ? (
                <Loader2 className="h-3 w-3 animate-spin" />
              ) : (
                "Record adjustment"
              )}
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
```

- [ ] **Step 23.6: Verify file size and tests**

```bash
wc -l src/features/reconciliation/components/adjustments-section.tsx
```
Expected: under 200 lines (target ~150).

```bash
npx tsc --noEmit && npm run lint && npm test
npm run dev
```
Navigate to a reconciliation page, click "Record an adjustment", exercise every field — identical behavior.

**Phase 7 verification:**
```bash
npx tsc --noEmit && npm run lint && npm test
```
STOP and report to user.

---

## Phase 8: Final Verification

### Task 24: Full-codebase grep sweep and PROGRESS update

- [ ] **Step 24.1: Zero-hex sweep**

```bash
grep -rn "text-\[#\|bg-\[#" src/features --include="*.tsx"
```
Expected: no matches. Any remaining = open an Edit against that file to remove.

- [ ] **Step 24.2: Zero-inline-formatting sweep**

```bash
grep -rn "\.toLocaleString\|\.toFixed\b" src/features --include="*.tsx"
```
Expected: no matches for dollar/cost formatting. Only counts that can't use `formatEventCount` should remain.

- [ ] **Step 24.3: Zero-destructured-store sweep**

```bash
grep -rn "= useReconciliationStore()" src/features
```
Expected: no matches.

- [ ] **Step 24.4: File size audit**

```bash
find src -name "*.tsx" -not -path "*/routes/*" -exec wc -l {} + | sort -rn | head -20
```
Expected: top files are under 200 lines (components), 150 (hooks), 300 (api adapters), 100 (stores).

- [ ] **Step 24.5: Duplicate `delay` audit**

```bash
grep -rn "const delay = " src/features/*/api/mock.ts
```
Expected: no matches.

- [ ] **Step 24.6: Full verification**

```bash
npx tsc --noEmit
npm run lint
npm test
npm run build
```
Expected: all four commands succeed with zero errors/warnings.

- [ ] **Step 24.7: Manual QA checklist**

Open `npm run dev` and click through each feature:
- Dashboard — stats grid, charts, customer table
- Pricing cards list + one card → reconciliation
- Reconciliation — timeline, version detail, edit panels, adjustments form (all 4 distribution modes)
- Customers — search, filter, edit
- Billing (margin) — stats, tree, edit panel
- Export — all filters, all presets, download
- Onboarding flow

Every screen should look and behave identically to pre-refactor.

- [ ] **Step 24.8: Update `PROGRESS.md`**

Append a new section to `/Users/ashtoncochrane/Git/localscouta/ubb/ubb-ui/PROGRESS.md`:

```markdown
## Codebase Audit Fixes (Complete — 2026-04-10)

- [x] Extracted shared `mockDelay`, removed 7 duplicated copies
- [x] Clerk env guard added, removed non-null assertion in `main.tsx`
- [x] Extended `format.ts` with `formatDollars`, `formatRoundedDollars`, `formatSignedDollars`, `formatFileSize`
- [x] Added semantic design tokens (brand, status, value) to `app.css`
- [x] Removed all 39 hardcoded hex color literals from feature components
- [x] Extracted shared `StatCard` (replaced 4 duplicates) and `StatusBadge` (replaced 8+ inline spans)
- [x] Added Zustand selectors across all reconciliation components
- [x] Fixed `useDebouncedValue` stale closure + eslint-disable in export-page
- [x] Removed hardcoded "2026-01-12" earliest date from export page
- [x] Memoized version date formatting in reconciliation
- [x] Fixed `download-bar` repeat-click success state bug
- [x] Replaced 63 inline `.toLocaleString()` / `.toFixed()` calls with `format.ts` helpers
- [x] Consolidated duplicate `formatVersionLabel` into shared `version-label.ts`
- [x] Refactored `ExportFilters` from 11 props → 2 props (state object pattern)
- [x] Refactored `CustomerTable` — lifted search/filter/editing state inside the component
- [x] Replaced inline `<button>` styles with shadcn `Button` in reconciliation panels
- [x] Rewrote 252-line `adjustments-section.tsx` into reducer + 4 sub-components (all <200 lines)
```

And also add a session log entry:
```markdown
| 2026-04-10 | Codebase audit fixes complete — B+ → A+ |
```

**Phase 8 verification:** The final build must pass cleanly. STOP and report final summary to user.

---

## Summary

**Phases:** 8
**Tasks:** 24
**Steps:** ~90
**Files created:** 10 (4 sub-components, 2 shared components, 2 reducer/lib files, 2 test files)
**Files modified:** ~50 (every feature touched; bulk is mechanical sweeps)

**Execution order is strict.** Each phase depends on the previous one:
- Phase 1 (format helpers) → Phase 5 (inline formatting cleanup)
- Phase 2 (design tokens) → Phases 3, 6, 7 (components use the tokens)
- Phase 3 (shared components) → Phase 7 (adjustments uses `Button`)
- Phase 6 (refactors) → Phase 7 (adjustments also uses refactor patterns)

At every phase boundary: run `npx tsc --noEmit && npm run lint && npm test`, then STOP and hand off to the user for review + commit.
