# v4 Visual Refresh — Design Spec

**Date:** 2026-04-10
**Status:** Approved
**Scope:** Dashboard page + global design tokens + shell chrome
**Mockups:**
- `ui-mockups/v2/ubb-dashboard-v4.html` — target layout
- `ui-mockups/ubb-design-system.html` — design-system reference (warm stone + terracotta palette)

## 1. Goal

Adopt the new "warm stone + terracotta" design language on the dashboard and in the app shell, replacing the current cool-parchment palette. Other feature pages inherit the new palette automatically through shadcn tokens but are not individually retuned in this pass.

The refresh introduces a richer KPI card (sparkline + delta pill), new chart colors, a single-row scope/filter bar, and a reworked customer-profitability table. Done right, it consolidates several one-off visual patterns into composable primitives that other features can reuse.

## 2. Non-goals

- Individually restyling billing, customers, reconciliation, pricing-cards, or export pages. They inherit the palette through shadcn tokens but are not pixel-matched to their own mockups yet (follow-up work).
- Changing API types, data flow, or feature folder structure.
- Dark mode fidelity against the mockups — the mockups are light-only. Dark mode will still function via the existing `.dark` overrides but is not tuned to the new palette in this pass.
- Touching `routeTree.gen.ts` or any generated file.

## 3. Design tokens

### 3.1 `src/styles/app.css` — rewire shadcn vars

Replace the existing `:root` block. Hex values are sourced from the design-system mockup.

```css
:root {
  /* Shadcn base (drives all shadcn components app-wide) */
  --background:           #f4f2ee; /* bg-page   */
  --foreground:           #2e2520; /* text-primary */
  --card:                 #fcfaf7; /* bg-surface */
  --card-foreground:      #2e2520;
  --popover:              #fcfaf7;
  --popover-foreground:   #2e2520;
  --primary:              #2e2520;
  --primary-foreground:   #fcfaf7;
  --secondary:            #ece8e2; /* bg-subtle */
  --secondary-foreground: #2e2520;
  --muted:                #ece8e2;
  --muted-foreground:     #6d6358; /* text-secondary */
  --accent:               #f8f0e8; /* accent-ghost — hover highlights */
  --accent-foreground:    #5a3520; /* accent-text  */
  --destructive:          #b84848;
  --border:               #e2ddd5;
  --input:                #e2ddd5;
  --ring:                 #a16a4a;
  --radius:               0.625rem;

  /* Sidebar */
  --sidebar:                     #fcfaf7;
  --sidebar-foreground:          #2e2520;
  --sidebar-primary:             #2e2520;
  --sidebar-primary-foreground:  #fcfaf7;
  --sidebar-accent:              #f8f0e8;
  --sidebar-accent-foreground:   #5a3520;
  --sidebar-border:              #e2ddd5;
  --sidebar-ring:                #a16a4a;
}
```

Dark mode (`.dark`): keep existing structure; hand-adjust `--background`, `--foreground`, `--card`, `--border` to neutral dark values. Dark mode is not the focus of this pass — it just must not break.

### 3.2 `@theme inline` — add named design-system palette

Expose the full mockup palette as Tailwind utilities so components can use `bg-bg-surface`, `text-text-muted`, `border-border-mid`, `bg-blue-light`, `text-accent-text`, etc.

```css
@theme inline {
  /* Fonts */
  --font-sans:  'DM Sans Variable', -apple-system, BlinkMacSystemFont, sans-serif;
  --font-serif: 'Cormorant', Georgia, serif;
  --font-mono:  'DM Mono Variable', 'SF Mono', ui-monospace, monospace;

  /* Surface + text */
  --color-bg-page:       #f4f2ee;
  --color-bg-subtle:     #ece8e2;
  --color-bg-surface:    #fcfaf7;
  --color-bg-raised:     #ffffff;
  --color-border-mid:    #d4cdc2;
  --color-border-strong: #b5ad9e;
  --color-text-primary:  #2e2520;
  --color-text-secondary:#6d6358;
  --color-text-muted:    #9a8e80;
  --color-text-inverse:  #fcfaf7;

  /* Accent (terracotta) */
  --color-accent:        #a16a4a;
  --color-accent-hover:  #b07855;
  --color-accent-dark:   #855638;
  --color-accent-light:  #f0e0d2;
  --color-accent-ghost:  #f8f0e8;
  --color-accent-text:   #5a3520;
  --color-accent-border: #d4ad90;

  /* Named data colors (with text + light + border variants) */
  --color-blue:          #4a7fa8;
  --color-blue-light:    #eaf1f7;
  --color-blue-text:     #1e4060;
  --color-blue-border:   #b0cce0;

  --color-red:           #b84848;
  --color-red-light:     #faecec;
  --color-red-text:      #6a1e1e;
  --color-red-border:    #e0a0a0;

  --color-green:         #3a8050;
  --color-green-light:   #eaf5ee;
  --color-green-text:    #1a4a28;
  --color-green-border:  #a0cca8;

  --color-amber:         #a07020;
  --color-amber-light:   #fdf4e4;
  --color-amber-text:    #5a3e10;
  --color-amber-border:  #e0c070;

  --color-purple:        #6a5aaa;
  --color-purple-light:  #f0eefa;
  --color-purple-text:   #3a2a6a;
  --color-purple-border: #c0b0e0;

  --color-stone:         #c2a68e;
  --color-stone-light:   #ede4da;

  /* Keep existing feature tokens that other pages depend on.
     The duplicates below map old names to the new palette so callers
     still work: */
  --color-success-dark: var(--color-green-text);
  --color-danger-dark:  var(--color-red-text);
  --color-purple-bg:    var(--color-purple-light);
  --color-purple-fg:    var(--color-purple-text);
  --color-chart-margin: var(--color-accent);
  --color-chart-loss:   var(--color-red);
  --color-chart-alloc:  var(--color-purple);

  /* Font-size scale (unchanged) */
  --text-label: 0.6875rem; /* 11px */
  --text-muted: 0.625rem;  /* 10px */
  --text-tiny:  0.5625rem; /*  9px */
}
```

The aliasing in the last block is important: existing files reference `text-success-dark`, `bg-purple-bg`, `text-danger-dark`, etc. By aliasing them to the new palette, we avoid a blast-radius refactor of every feature.

### 3.3 Fonts

Install as dev dependencies:
- `@fontsource-variable/dm-sans`
- `@fontsource/cormorant` (weight 700 only — serif is logo-only)
- `@fontsource-variable/dm-mono`

Remove `@fontsource-variable/geist`. Import replacements at the top of `app.css`.

## 4. Shared primitives (new / modified)

All files live under `src/components/shared/` unless noted. Each primitive is its own file and stays focused.

### 4.1 `brand.tsx` (new)

```ts
export interface BrandProps {
  size?: "sm" | "md" | "lg"; // sm=20, md=28, lg=42
  className?: string;
}
```

Renders `ubb.` in Cormorant 700 with the dot colored `--color-accent`. No click handling — wrap in a Link when needed.

### 4.2 `icon-button.tsx` (new)

Circular 30x30 button with `border border-border bg-bg-surface text-text-muted`. Hover → `bg-bg-subtle text-text-secondary border-border-mid`. Props passthrough to `<button>`, accepts `children` (the icon). Used in topbar.

### 4.3 `delta-pill.tsx` (new)

```ts
export interface DeltaPillProps {
  trend: "up" | "down" | "flat";
  children: ReactNode; // the label text
  className?: string;
}
```

10px font, rounded pill, up/down triangle SVG icon matching the mockup. Colors:
- `up`   → `bg-green-light text-green-text`
- `down` → `bg-red-light text-red-text`
- `flat` → `bg-bg-subtle text-text-muted`

### 4.4 `sparkline.tsx` (new)

Thin recharts wrapper:

```ts
export interface SparklineProps {
  data: number[];
  color: string;
  height?: number; // default 32
}
```

No axes, no tooltip, smooth `tension 0.4`, 15% alpha fill, 1.5px stroke. Uses the same recharts instance already in dependencies — no new chart lib.

### 4.5 `chart-card.tsx` (new)

```ts
export interface ChartCardProps {
  title: string;
  legend?: ReactNode;
  actions?: ReactNode;
  children: ReactNode; // the chart
  className?: string;
}
```

`bg-bg-surface border border-border rounded-md p-6` with `hover:border-border-mid`. Header: title left, legend right. Body: chart slot. Replaces the inline markup duplicated across every chart in the current dashboard.

### 4.6 `chart-legend.tsx` (new)

```ts
export interface ChartLegendItem { label: string; color: string; dashed?: boolean; }
export interface ChartLegendProps {
  items: ChartLegendItem[];
  variant: "dot" | "line";
}
```

Dot variant = 7px circle. Line variant = 16×2px bar, with optional dashed border.

### 4.7 `stat-card.tsx` (modify existing)

Extend the existing API without breaking it.

```ts
export interface StatCardProps {
  label: string;
  value: ReactNode;
  change?: { value: string; positive: boolean }; // EXISTING, kept for back-compat
  trend?: "up" | "down" | "flat";                // NEW — if set, renders DeltaPill
  trendLabel?: string;                            // NEW — pill text
  sparkline?: ReactNode;                          // NEW — slot
  subtitle?: string;                              // EXISTING
  variant?: "muted" | "raised" | "purple";       // ADDED "raised"; default stays "muted"
  className?: string;
}
```

**`variant="muted"` (default — current look, no visual regression):**
- `bg-accent/50 rounded-lg px-3 py-2.5` — exactly as today
- Billing `MarginStatsGrid` and customer-mapping `MappingStatsGrid` get no visible change
- `trend`/`sparkline` props still work inside this variant (dashboard is not using this variant anyway, but they render as small pill + slot for consistency if someone does use them)

**`variant="raised"` (new, opt-in — used by dashboard KPI grid):**
- `bg-bg-surface border border-border rounded-md` padding `18px 20px 14px`
- Hover: `border-border-mid shadow-md`
- Label: `text-label font-medium text-text-muted mb-1.5`
- Value: `text-[26px] font-bold leading-[1.15] tracking-tight mb-1`
- Delta row: `<DeltaPill>` if `trend` set, else fallback to existing colored-text behavior for `change` prop
- Sparkline: rendered in a `h-8 -mx-1 mt-2.5` container if provided

**`variant="purple"`** keeps the existing color-swap behavior on the value (unchanged).

Tests: keep all existing tests passing. Add new tests for the `raised` variant, `trend` prop rendering, and `sparkline` slot.

### 4.8 Shell: `top-bar.tsx` + `nav-shell.tsx` (modify)

**`TopBar`:**
- Height `h-[46px]` (instead of `h-11`).
- Layout: left block is 200px wide containing `<Brand size="md" />` aligned to the sidebar rail; right block has mock pill + 2 `<IconButton>`s.
- Remove the panel-left button (mockup has no collapse control).

**`NavShell`:**
- Sidebar width `w-50` (200px) — was `w-56`.
- Remove the internal `UBB` header row (logo now in topbar).
- Icon size `h-3.5 w-3.5`, padding `px-2.5 py-1`, font 12px.
- Pinned user row at bottom with `border-t border-border`, showing avatar + name + role.
- Section labels: `text-[9px] font-semibold uppercase tracking-wider text-text-muted` (tighter than current).
- Active item: `bg-accent-ghost text-accent-text font-semibold`, icon colored `text-accent-dark`.

## 5. Dashboard feature components

All live in `src/features/dashboard/components/`.

### 5.1 `dashboard-page.tsx`

Recomposes into:
```tsx
<div className="px-10 pt-8 pb-20 space-y-7">
  <PageHeader title="Dashboard" description="Profitability overview across all products and customers." />
  <ScopeBar ... />
  <StatsGrid stats={data.stats} sparklines={data.sparklines} />
  <RevenueChart data={data.revenueTimeSeries} />
  <div className="grid grid-cols-2 gap-4">
    <CostBreakdownChart title="Cost by product"      series={data.costByProduct.series} data={data.costByProduct.data} />
    <CostBreakdownChart title="Cost by pricing card" series={data.costByCard.series}    data={data.costByCard.data} />
  </div>
  <div className="grid grid-cols-2 gap-4">
    <BreakdownCard title="Revenue by product" items={data.revenueByProduct} />
    <BreakdownCard title="Margin by product"  items={data.marginByProduct} barColor="#a16a4a" />
  </div>
  <CustomerTable customers={data.customers} />
</div>
```

Route file stays under 50 lines. All business logic stays in feature components. No file renames — all components keep their existing names and locations.

### 5.2 `scope-bar.tsx` (rewrite in place)

Single-row layout (replacing the current 3-row version). Left: `ScopePillTabs` + context text (`Showing: All 18 customers (aggregate)`). Right: `period` label + `DayRangePillGroup` + `Export` button. Both pill groups are small internal subcomponents:

- `ScopePillTabs` — rounded pill container (`bg-bg-surface border rounded-full p-[3px]`), children are buttons. Active = `bg-accent-ghost text-accent-text font-semibold`. Values: "All customers" | "Top 5 by revenue" | "Unprofitable".
- `DayRangePillGroup` — tighter pill group (`bg-bg-subtle rounded-full p-[2px]`). Active = `bg-bg-surface text-text-primary shadow-sm`. Values: `7d | 30d | 90d | YTD`.

These remain feature-local; if a second page uses them they graduate to shared. The file keeps its existing name (`scope-bar.tsx`) to minimize churn.

### 5.3 `stats-grid.tsx` (rewrite in place)

Thin wrapper; 5-col grid of `StatCard` using `variant="raised"`, `trend`, `trendLabel`, and a `sparkline` slot powered by `<Sparkline>`. Pulls per-stat sparkline data from `data.sparklines` (see §6).

Delta-to-trend mapping:
| Stat | Trend rule |
|---|---|
| Revenue        | `revenuePrevChange > 0 ? "up" : "down"` |
| API costs      | `costsPrevChange < 0 ? "up" : "down"` (costs down = good) |
| Gross margin   | `marginPrevChange > 0 ? "up" : "down"` |
| Margin %       | `marginPctPrevChange > 0 ? "up" : "down"` |
| Cost / $1 rev  | `abs(costPerRevPrevChange) < 1 ? "flat" : costPerRevPrevChange < 0 ? "up" : "down"` |

### 5.4 `revenue-chart.tsx` (rewrite in place)

Uses `ChartCard` with `ChartLegend variant="line"`. Chart becomes 240px tall. Recharts colors updated:
- Revenue: stroke `#a16a4a`, fill `rgba(161,106,74,0.07)`, width 2
- API costs: stroke `#b84848`, fill `rgba(184,72,72,0.05)`, width 1.5
- Margin: stroke `#b5ad9e`, `strokeDasharray="5 3"`, no fill, width 1.5, rendered behind costs (`order`)

Export keeps the existing `RevenueChart` component name.

### 5.5 `cost-breakdown-chart.tsx` (rewrite in place)

Switch from `AreaChart` (stacked) to `LineChart`. First series keeps a light fill (area under curve) to match the mockup; remaining series are stroke-only. 180px height. Uses `ChartCard` + `ChartLegend variant="dot"`. Exports the existing `CostBreakdownChart` name.

### 5.6 `breakdown-card.tsx` (rewrite in place)

Uses `ChartCard` (no legend). Each row:
```
[colored dot] [label (flex-1)] [value] [bar (72×5px)] [percentage]
```
- Bar background `bg-bg-subtle`
- Bar fill: `item.color` when not overridden, else `barColor` prop (accent terracotta for the margin view)
- Values mono, percentages 11px text-muted

Exports the existing `BreakdownCard` name.

### 5.7 `customer-table.tsx` (rewrite in place)

Still uses shadcn `Table`. Restyled:
- Container: `bg-bg-surface border border-border rounded-md overflow-hidden`
- Header row: `bg-bg-subtle`, uppercase 10px labels
- Body rows: `hover:bg-bg-page`, 14px vertical padding
- Customer cell: name bold + mono `customer_id` below
- **Type badges:** blue-light/blue-text for `Sub`; amber-light/amber-text for `Usage`
- **Margin cell:** 48×4px bar + colored % text. Color ramp:
  - `>= 50%` → `mgi.g` accent terracotta + `text-green-text`
  - `0–49%`  → `mgi.w` amber + `text-amber-text`
  - `< 0%`   → `mgi.x` red + `text-red-text`
- Negative margin value: `text-red` with `−$` prefix

Table container header (export button above table) remains part of the dashboard-page composition, not inside the table component.

## 6. Mock data updates

`src/features/dashboard/api/mock-data.ts`:

1. Recolor series to mockup values:
   - `productSeries` → blue `#4a7fa8`, purple `#6a5aaa`, red `#b84848`
   - `cardSeries` → `#c0392b`, `#4a7fa8`, `#484240`, `#a16a4a`, `#b5ad9e`
   - `revenueByProduct` / `marginByProduct` colors match `productSeries`
2. Add `sparklines` field to `DashboardData`:
   ```ts
   interface DashboardData {
     ...existing...
     sparklines: {
       revenue: number[];
       apiCosts: number[];
       grossMargin: number[];
       marginPct: number[];
       costPerRev: number[];
     };
   }
   ```
   Populated by mapping existing `revenueTimeSeries` to the respective arrays. No new wave computation needed.
3. Update `types.ts` to include the new field and export `SparklineSeries` helper type if needed.

Monetary values are already in dollars (not micros) in the mock data — the dashboard shows dollars directly. No `format.ts` changes required for this refresh. (The repo-wide `micros` convention remains for real API integration, tracked separately.)

## 7. File size check

| File | Est. lines | Limit |
|------|-----------:|------:|
| `stat-card.tsx`                 | ~130 | 200 |
| `dashboard-page.tsx`            | ~45  | 200 |
| `scope-bar.tsx`                 | ~95  | 200 |
| `stats-grid.tsx`                | ~85  | 200 |
| `revenue-chart.tsx`             | ~95  | 200 |
| `cost-breakdown-chart.tsx`      | ~95  | 200 |
| `breakdown-card.tsx`            | ~55  | 200 |
| `customer-table.tsx`            | ~140 | 200 |
| `chart-card.tsx`                | ~35  | 100 |
| `delta-pill.tsx`                | ~40  | 100 |
| `sparkline.tsx`                 | ~40  | 100 |
| `brand.tsx`                     | ~30  | 100 |
| `icon-button.tsx`               | ~25  | 100 |
| `chart-legend.tsx`              | ~35  | 100 |

All under limits.

## 8. Testing

- **StatCard:** keep existing tests green. Add: renders `DeltaPill` when `trend` set; renders sparkline slot; applies new `raised`/`muted` variant classes.
- **DeltaPill:** renders each trend variant with correct label and a colored icon.
- **Sparkline:** renders an SVG path when given data (snapshot-style shallow assertion).
- **Dashboard components:** no new tests required (behaviour unchanged, only visual). Typecheck + lint must pass.
- **Visual spot-check:** load `/` with `VITE_API_PROVIDER=mock`, compare to mockup side-by-side.

## 9. Verification checklist

- [ ] `pnpm typecheck` passes
- [ ] `pnpm test` passes (all existing tests + new StatCard/DeltaPill/Sparkline tests)
- [ ] `pnpm lint` passes
- [ ] `pnpm build` succeeds
- [ ] Dashboard route renders visually matching mockup at 1440px width
- [ ] Other pages (pricing cards, billing, customers, reconciliation, export) still render without broken styles (palette inherited, no crashes)
- [ ] `PROGRESS.md` updated with Phase 9: Visual refresh entry

## 10. Dependencies (npm)

**Add:**
- `@fontsource-variable/dm-sans`
- `@fontsource/cormorant`
- `@fontsource-variable/dm-mono`

**Remove:**
- `@fontsource-variable/geist`

## 11. Migration notes

- Any file currently referencing the Geist font directly (none expected; font comes in via `app.css`) must be updated.
- `StatCard`'s default `variant="muted"` matches the current look, so billing + customer-mapping stat grids need **no change** to preserve their pixel layout. Only the dashboard opts in to `variant="raised"`.
- Dashboard chart components currently hardcoding `#1D9E75` / `#639922` / `#E24B4A` (cool-palette greens/reds) get those colors replaced inline with the new warm-palette hex values, kept as component-level constants near the chart definitions.
- The font swap from Geist → DM Sans is an app-wide visual change. Since DM Sans has similar metrics and weight coverage, layouts should not shift meaningfully; spot-check the pricing card wizard and reconciliation page after the swap.
