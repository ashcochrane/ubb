# Pricing Cards v4 Visual Refresh — Design Spec

**Date:** 2026-04-10
**Status:** Approved
**Scope:** `/pricing-cards` list + 4-step wizard + shared primitives
**Mockup:** `ui-mockups/v2/ubb-pricing-cards.html`
**Related:**
- `ui-mockups/ubb-design-system.html` (v4 palette reference)
- `docs/superpowers/specs/2026-04-10-v4-visual-refresh-design.md` (dashboard refresh, already shipped)

## 1. Goal

Adopt the v4 warm stone + terracotta design language on the pricing-cards list page and the 4-step creation wizard, matching `ui-mockups/v2/ubb-pricing-cards.html` pixel-for-pixel while leaning on **shadcn primitives wherever they fit**. Extract three reusable components (`CodeBlock`, `CheckList`, `OptionCard`) that onboarding and other features can pick up later.

Unlike the dashboard refresh — which was purely visual — this pass also adds a small set of behaviors the mockup implies but the current implementation lacks: dimension collapse/duplicate, quick-dim chips, dominant-dimension warning alert, cost bar + legend in the review step, per-day/month projection, and a Save-as-draft action.

## 2. Non-goals

- Changing the wizard's form-state flow (React Hook Form + Zod + `wizardSchema` stay intact).
- Changing the backend API shape. Save-as-draft maps to the existing save mutation.
- Restyling onboarding, billing, customers, reconciliation, or export pages — they already inherit the v4 palette via the shadcn tokens from the dashboard refresh.
- Touching `routeTree.gen.ts` or generated files.
- Dark mode fidelity — the mockup is light-only; dark mode continues to work but isn't tuned.

## 3. shadcn usage — what to reach for first

The mockup uses a handful of primitives repeatedly. For each, map to a shadcn component and extend only when necessary:

| Mockup element | shadcn primitive | Action |
|---|---|---|
| `.btn.btn-primary` | `Button` variant="default" | Use as-is; add `className="rounded-full"` for pill shape |
| `.btn.btn-outline` | `Button` variant="outline" | Use as-is |
| `.btn.btn-ghost` | `Button` variant="ghost" with border override OR variant="outline" | Fine to use `outline` for now |
| `.btn.btn-accent` | `Button` **new variant `accent`** | Add to `buttonVariants` cva |
| `.btn.btn-sm` | `Button` size="sm" | Use as-is |
| `.fi` (text input) | `Input` | Use as-is |
| `textarea.fi` | `Textarea` | Use as-is |
| `select.fi` | `Select` | Use as-is |
| `.field-label` | `Label` | Use as-is |
| `hr.sep` | `Separator` | Use as-is |
| `.pc-card`, `.dim-card`, `.review-card`, `.code-block` | `Card` + `CardContent` | Override padding/border via className |
| `.alert.alert-amber` | `Alert` **extend variants** | Add `amber \| blue \| green` to `alertVariants` cva |
| `.badge.badge-green`, `.badge.badge-amber` | `Badge` **extend variants if needed** | Verify current variants; add as needed |
| `.dim-actions button` (with `title="..."`) | `Button` size="icon-xs" variant="ghost" + `Tooltip` | Replace title attributes with accessible tooltips |
| `.toggle-row` (per-unit / flat) | `ToggleGroup` — **new shadcn install** | `pnpm dlx shadcn@latest add toggle-group` |
| `.search-wrap input` | `Input` + absolute-positioned icon | Hand-rolled wrapper (existing pattern in dashboard export) |

### 3.1 Button — add `accent` variant

In `src/components/ui/button.tsx`, extend the `variants.variant` object with:

```ts
accent:
  "bg-accent-base text-text-inverse hover:bg-accent-hover aria-expanded:bg-accent-hover",
```

Everything else in `buttonVariants` stays as-is.

### 3.2 Alert — add `amber`, `blue`, `green` variants

In `src/components/ui/alert.tsx`, extend the `alertVariants` cva with:

```ts
amber:
  "border-amber-border bg-amber-light text-amber-text [&_[data-slot=alert-description]]:text-amber-text/80",
blue:
  "border-blue-border bg-blue-light text-blue-text [&_[data-slot=alert-description]]:text-blue-text/80",
green:
  "border-green-border bg-green-light text-green-text [&_[data-slot=alert-description]]:text-green-text/80",
```

Existing `default` and `destructive` stay unchanged.

### 3.3 Badge — verify / extend variants

Read `src/components/ui/badge.tsx` first. If it doesn't already have `amber` / `green` / `blue` variants mapped to the v4 palette (`bg-amber-light text-amber-text`, etc.), add them. Likely needed since the dashboard customer table previously used inline hex for amber.

### 3.4 New shadcn install — ToggleGroup

Run `pnpm dlx shadcn@latest add toggle-group` (non-interactive via `--yes` if available). This adds `src/components/ui/toggle-group.tsx` using `@base-ui/react`'s `ToggleGroup` primitive (consistent with the rest of the ui/ components built on base-ui).

Wrap-style: for the v4 "segmented toggle" look (border around the group, text-primary-filled selected state), the wrapper in `dimension-card.tsx` will pass `className` overrides. No further shadcn extension needed.

## 4. New shared primitives

All live in `src/components/shared/` and each has one clear responsibility.

### 4.1 `code-block.tsx`

```ts
export interface CodeBlockProps {
  title?: string;
  code: string;
  hint?: string;
  language?: string;       // for future syntax highlighting; stored but not used yet
  onCopy?: () => void;     // optional override; default uses navigator.clipboard
  copyLabel?: string;      // defaults to "Copy to clipboard"
  className?: string;
}
```

Renders a `Card` with `bg-bg-subtle border border-border rounded-md p-4`. Optional header row: title left + "Copy to clipboard" `Button variant="ghost" size="sm"` right. Body is `<pre>` in `font-mono text-[12px]` with horizontal scroll. Optional hint in `text-[11px] text-text-muted mt-2`.

Copy behavior: uses `navigator.clipboard.writeText(code)` and shows a transient "Copied" state (local `useState`, 2-second timeout) unless `onCopy` overrides.

### 4.2 `check-list.tsx`

```ts
export type CheckStatus = "pass" | "warn" | "fail";

export interface CheckItem {
  status: CheckStatus;
  label: string;
}

export interface CheckListProps {
  items: CheckItem[];
  className?: string;
}
```

Renders a `<ul>` of `CheckItem`s. Each row has a colored 18×18 circle icon on the left (green check / amber warning / red x) and the label text. Icons are lucide: `<Check>` / `<AlertTriangle>` / `<X>` inside a rounded-full colored background matching the palette: `bg-green-light text-green` / `bg-amber-light text-amber` / `bg-red-light text-red`.

### 4.3 `option-card.tsx`

```ts
export interface OptionCardProps {
  selected?: boolean;
  onClick?: () => void;
  title: string;
  description?: string;
  children?: ReactNode;    // slot — if provided, replaces title/description layout
  className?: string;
}
```

Renders a shadcn `Card` with `cursor-pointer transition-colors`. Idle state: `border-[1.5px] border-border hover:border-border-mid`. Selected state: `border-[1.5px] border-text-primary shadow-[0_0_0_1px_var(--color-text-primary)_inset]`. Exposes `data-selected={selected}` for styling + testing.

Used in two places in the step-source wizard screen: as the Template-vs-Custom options (with title + description) and as the template grid items (with a `children` slot for custom dense layout).

## 5. Existing shared — restyled

### 5.1 `stepper.tsx` (keep API, restyle internals)

Visual updates:
- Circle size: 28×28 (unchanged)
- Pending: `bg-bg-surface border-[1.5px] border-border-mid text-text-muted`
- Active: `border-[1.5px] border-text-primary text-text-primary shadow-[0_0_0_3px_var(--color-bg-subtle)]`
- Completed: `bg-green border-green text-text-inverse` (was `bg-foreground`)
- Connector line: `w-12 h-[1.5px] bg-border` (active span: `bg-green`)
- Label: `text-[10px] text-text-muted mt-1.5 font-medium` (pending); `text-text-primary font-semibold` (active); `text-green-text` (completed)
- Check icon: `h-3 w-3` (uses existing lucide `Check`)

API unchanged — existing tests stay green. Existing consumers (`new-card-wizard.tsx` and the onboarding wizard if any) inherit the new look automatically.

## 6. Feature-local components — `src/features/pricing-cards/components/`

All files keep their current names and exports. Internals are rewritten to match v4.

### 6.1 `pricing-cards-page.tsx`

- Wrapper: `px-10 pt-8 pb-20 space-y-6` (to match dashboard-page rhythm)
- `PageHeader` with title "Pricing Cards", description "Define how API costs are calculated.", and a pill `<Button variant="default" className="rounded-full">+ Create card</Button>` linking to `/pricing-cards/new`
- Search: `max-w-[320px] relative` wrapper + `<Search />` lucide icon absolute-positioned left + shadcn `<Input className="pl-9 rounded-md">`
- Grid: `grid grid-cols-3 gap-4`
- Loading: 6 `<Skeleton className="h-28 rounded-md">` in a 3-col grid
- Empty state: dashed border card ("No cards yet — create your first card")

### 6.2 `pricing-card-item.tsx`

- `<Link>` wrapping a shadcn `Card` with `p-5 cursor-pointer hover:border-border-mid hover:shadow-md transition-all`
- Top row: `<div className="flex items-start justify-between mb-1"><div className="text-[14px] font-semibold tracking-[-0.15px]">{name}</div><Badge>{status}</Badge></div>`
- Provider: `text-[12px] text-text-secondary mb-2.5`
- Slug: `font-mono text-[11px] text-text-muted mb-1`
- Meta: `text-[11px] text-text-muted` showing `{n} dimension{s} · v{version}`

### 6.3 `new-card-wizard.tsx`

- Wrapper: `mx-auto max-w-[580px] pt-8 pb-20` (was 640px)
- Stepper at top with `mb-10`
- `FormProvider` + conditional step components (no change)
- Step error `<Alert variant="destructive">` (instead of red text)
- Footer: 
  - Step < 3: `<div className="flex items-center justify-between mt-8">` with Back/Cancel on left, Next on right
  - Step === 3: left = Back, right = flex row of `<Button variant="outline">Save as draft</Button>` + `<Button variant="accent">Activate card</Button>`

Save-as-draft action: call the existing save mutation with `{ status: "draft" }`. Activate: existing flow. Both navigate to `/pricing-cards` on success.

### 6.4 `step-source.tsx`

- Wiz title (17px bold) + sub (13px muted)
- Option grid: 2-col, uses new shared `<OptionCard>` for Template vs Custom
- Conditional template section (only when `sourceType === "template"`): uppercase section label + 3-col grid of `<OptionCard>` (templates) with dense children slot
- Pricing pattern is NOT asked here in the v4 mockup — it's derived from the template. Confirm current schema behavior and align.

### 6.5 `step-details.tsx`

- `Card name` field: `<Label> + <Input>` + hint
- `field-row`: `<Label>+<Input>` for Provider + `<Label>+<Input with group button>` for cardId + Regenerate
- `<Separator>`
- Description field with shadcn `<Textarea>` + char count (`{length} / 250`) right-aligned below
- Pricing source URL field
- Card preview footer: inline block with `bg-bg-subtle rounded-md p-3.5` showing a dot + current form `name` value + "Draft" badge. (Inlines the deleted `card-preview.tsx`.)

### 6.6 `step-dimensions.tsx`

- Wiz title "Define cost dimensions" + sub
- `useFieldArray` over `dimensions`
- For each dimension, render `<DimensionCard>` (feature-local)
- `<AddDimensionCard />` dashed-border button: "+ Add dimension"
- `<QuickDimChips />` — horizontal flex of chips. Each chip is a small pill (`font-mono text-[11px] px-2.5 py-1 rounded-full border`) showing `+ {key}`. Click → appends to `dimensions` with default values. Disabled (opacity + cursor) if the key already exists.
- `<LiveCostTester>` — pass current dimensions, outputs live calculation

State:
- `collapsedIds: Set<string>` — local `useState`
- Quick dims list — local const:

```ts
const QUICK_DIMS = [
  { key: "grounding",      label: "Grounding",      defaultUnit: "per unit" },
  { key: "cached_tokens",  label: "Cached tokens",  defaultUnit: "per 1M tokens" },
  { key: "image_tokens",   label: "Image tokens",   defaultUnit: "per 1M tokens" },
  { key: "requests",       label: "Requests",       defaultUnit: "per request" },
  { key: "search_queries", label: "Search queries", defaultUnit: "per query" },
];
```

### 6.7 `dimension-card.tsx`

Rewrite with:
- `<Card>` wrapper, collapsible body
- Header: title "Dimension {index + 1}" on left, action buttons on right (shadcn `Button size="icon-xs" variant="ghost"` + `Tooltip`: collapse/expand, duplicate, delete)
- Body (when expanded):
  - Row: Metric key input (flex-2) + pricing type `ToggleGroup` per-unit/flat (flex-1)
  - Unit price: `<Label>` + input-group (prefix `$` inside `<div>` + `<Input>`)
  - Row: display label + display unit + display price
- Body (when collapsed): 1-line summary `{key} — {unit price} per {unit}`

Duplicate action: `append({ ...currentValue, key: `${currentValue.key}_copy` })` on the parent's `useFieldArray`.
Delete action: `remove(index)` — but guard if it's the only dimension (disable with tooltip "At least one dimension required").

### 6.8 `cost-tester.tsx` (live tester in step 3)

- Wrapper: `bg-accent-ghost border border-accent-border rounded-md p-5`
- Header row: title + "Updates as you type" in `text-[10px] text-green-text font-semibold`
- Sub: "Enter sample quantities to see calculated costs in real time."
- Row for each dimension: `<Label>{dimKey}</Label>` + `<Input className="w-20 text-right font-mono">` + calc text `text-[11px] text-text-muted font-mono` showing `{qty} × ${price} = ${product}`
- Total row: top-bordered `flex justify-between pt-2.5 mt-2.5`

### 6.9 `dry-run-simulator.tsx` (step 4)

Similar to cost-tester but with additions:
- Header subtitle: "Enter realistic sample quantities for a single API call."
- Per-day/month projection under the total: `At 1000 events/day: ~$X/day · ~$Y/month`
- Cost bar: horizontal `h-[6px] rounded-full overflow-hidden flex` of colored segments, one per dimension, width = `(dimCost / total) * 100%`. Use hardcoded `#4a7fa8`, `#6a5aaa`, `#a16a4a`, `#b84848`, `#3a8050` as the color cycle.
- Cost bar legend: `flex gap-3 mt-1.5` of `<span>` with 6px dot + `{pct}% {label}`

### 6.10 `step-review.tsx`

- Review card: shadcn `<Card>` with provider name, mono slug, amber/green status badge, sections labeled in `text-[11px] uppercase tracking-wider text-text-muted`, each dimension rendered as a row with: name left, type pill + price right
- Dry-run simulator (see §6.9)
- Dominant-dimension alert: computed via `features/pricing-cards/lib/cost-analysis.ts` — if `max(dimCost) / total > 0.80`, render `<Alert variant="amber">` with title "Dominated by one dimension" and description `"{key} accounts for {pct}% of total cost. Is this expected?"`
- `<CheckList items={...}>` for the 4 validation checks:
  - "All dimensions have non-zero prices" (pass if every dim has `unitPrice > 0`)
  - "No duplicate metric keys" (pass if `Set(keys).size === keys.length`)
  - "Unit prices within expected ranges" (pass if every `unitPrice < 1000`; warn otherwise)
  - "Card ID is valid" (pass if `cardId` matches `/^[a-z0-9_]+$/`; warn otherwise)
- `<CodeBlock title="Integration snippet" code={snippet} hint="...">` replacing the old `integration-snippet.tsx`

Computed in a local selector function from the form state; no async work. Extract the pure analysis helpers into `src/features/pricing-cards/lib/cost-analysis.ts` so they're unit-testable.

### 6.11 Deleted files

- `src/features/pricing-cards/components/integration-snippet.tsx` — folded into `step-review.tsx` using shared `CodeBlock`
- `src/features/pricing-cards/components/card-preview.tsx` — inlined into `step-details.tsx`

## 7. Library extraction

New file: `src/features/pricing-cards/lib/cost-analysis.ts`

```ts
import type { WizardDimension } from "./schema";

export interface DimensionCost {
  key: string;
  cost: number;
  pct: number; // 0..100, rounded to 1 decimal
}

export interface CostAnalysis {
  total: number;
  perDim: DimensionCost[];
  dominantDim: DimensionCost | null; // present if any dim.pct > 80
}

export function analyzeCost(
  dimensions: WizardDimension[],
  quantities: Record<string, number>,
): CostAnalysis { ... }

export function validateCard(values: WizardFormValues): CheckItem[] { ... }
```

Rationale: pure functions, unit-testable, and keeps `step-review.tsx` under the 200-line limit.

## 8. Testing

### New tests

- `src/components/shared/code-block.test.tsx`
  - Renders title + code + hint
  - Clicking Copy calls `onCopy` if provided, otherwise `navigator.clipboard.writeText`
- `src/components/shared/check-list.test.tsx`
  - Renders one row per item
  - Each row has the correct data-status attribute
- `src/components/shared/option-card.test.tsx`
  - Idle state: no `data-selected` (or `data-selected="false"`)
  - Selected state: `data-selected="true"`
  - Clicking calls `onClick`
- `src/features/pricing-cards/lib/cost-analysis.test.ts`
  - Empty dimensions → `total: 0`, `perDim: []`, `dominantDim: null`
  - Two dims with 50/50 split → no dominant
  - Two dims 90/10 → dominantDim is the 90% one
  - Duplicate keys → `validateCard` returns warn on duplicate-key check
  - Invalid cardId → warn on card-id check

### Existing tests that must stay green

- `stepper.test.tsx` — `Stepper` API unchanged, all assertions on Check icon presence + current state remain valid
- `form-field.test.tsx` — not touched
- `stat-card.test.tsx` — not touched
- Pricing-cards lib unit tests (`calculations.test.ts`) — not touched
- Dashboard tests — not touched

### No new tests needed for

- Feature-local components (pure presentational, covered by typecheck + visual pass)
- Button/Alert/Badge variant extensions (static cva additions)

## 9. File size check

| File | Est. lines | Limit |
|---|---:|---:|
| `pricing-cards-page.tsx`    | ~70  | 200 |
| `pricing-card-item.tsx`     | ~50  | 200 |
| `new-card-wizard.tsx`       | ~160 | 200 |
| `step-source.tsx`           | ~90  | 200 |
| `step-details.tsx`          | ~110 | 200 |
| `step-dimensions.tsx`       | ~130 | 200 |
| `dimension-card.tsx`        | ~170 | 200 |
| `cost-tester.tsx`           | ~75  | 200 |
| `dry-run-simulator.tsx`     | ~140 | 200 |
| `step-review.tsx`           | ~160 | 200 |
| `cost-analysis.ts` (lib)    | ~80  | 200 |
| `code-block.tsx` (shared)   | ~55  | 100 |
| `check-list.tsx` (shared)   | ~45  | 100 |
| `option-card.tsx` (shared)  | ~40  | 100 |
| `stepper.tsx` (shared)      | ~65  | 100 |

All under limits. `dimension-card.tsx` is the largest feature file; if it pushes past 200 lines, extract the collapsed-summary row into a small sub-component.

## 10. Verification checklist

- [ ] `pnpm exec tsc -b --noEmit` passes
- [ ] `pnpm test` passes (existing + new CodeBlock/CheckList/OptionCard/cost-analysis tests)
- [ ] `pnpm lint` passes (0 errors; existing unrelated warnings OK)
- [ ] `pnpm build` succeeds
- [ ] `/pricing-cards` list renders matching the mockup
- [ ] Wizard step 1-4 render matching the mockup
- [ ] Dimension collapse/duplicate/delete work
- [ ] Quick-dim chips append dimensions and grey out when already added
- [ ] Dominant-dimension alert appears when any dimension > 80% of total
- [ ] Cost bar + legend reflect current simulator quantities
- [ ] Per-day/month projection calculates correctly
- [ ] Save-as-draft and Activate-card buttons both navigate back to list
- [ ] `PROGRESS.md` updated

## 11. Dependencies

**New shadcn install:**
- `toggle-group` (via `pnpm dlx shadcn@latest add toggle-group`)

**No new npm dependencies.**

## 12. Migration notes

- No backwards-compat breaks. Existing callers of `Stepper`, `StatCard`, `Button`, `Alert` continue to work — only additive changes (new variants).
- `integration-snippet.tsx` and `card-preview.tsx` are deleted; if any other file imports them (unlikely — they're feature-local), update imports to the new inlined/shared locations.
- The wizard's `step-source.tsx` currently asks for `pricingPattern` (token vs request vs mixed). The v4 mockup derives this from the selected template and doesn't expose it as a wizard choice. **Resolution:** keep `pricingPattern` in `wizardSchema`, populate it from the template when a template is chosen, default to `"token"` for custom cards, and don't render it in the UI.
- Save-as-draft behavior: confirmed via `src/features/pricing-cards/api/types.ts:50` — `CreateCardRequest` already has a `status: CardStatus` field. The wizard just needs to pass `"draft"` or `"active"` to `useCreateCard().mutate()` based on which footer button was clicked. No backend or mutation signature changes required.
