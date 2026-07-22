# Phase 8: Data Export — Design Spec

> **Date:** 2026-04-09
> **Status:** Approved
> **Mockup:** `docs/design/files/data_export_page.html`
> **Rationale:** `docs/design/ui-flow-design-rationale.md` Section 5

---

## 1. Goal

Build the Data Export page at `/export`. This is the "escape hatch" — when the dashboard doesn't answer a specific question, customers download event-level data as CSV or JSON and analyse it in their own tools.

The page has live-updating filters, a row estimate with natural language summary, a 5-row preview table that changes shape based on granularity, and a download bar with format/granularity toggles.

---

## 2. Data Model

### Types (`features/export/api/types.ts`)

```typescript
export type ExportGranularity = "dimension" | "event";
export type ExportFormat = "csv" | "json";
export type DatePreset = "7d" | "30d" | "90d" | "all";

// ExportFilters does NOT include format — format only affects download,
// not preview/estimate. Changing CSV/JSON should not re-fetch preview data.
export interface ExportFilters {
  dateFrom: string;          // "YYYY-MM-DD"
  dateTo: string;            // "YYYY-MM-DD"
  customerIds: string[];     // empty = all customers
  productKeys: string[];     // empty = all products
  cardKeys: string[];        // empty = all cards
  granularity: ExportGranularity;
}

export interface ExportEstimate {
  rowCount: number;
  fileSizeBytes: number;
  // Summary text is built client-side from filters + filter options,
  // not returned by the server.
}

// Generic column-based approach for preview data.
// Avoids index signature anti-pattern on EventPreviewRow.
// The server returns different column sets for each granularity mode.
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

### API Functions

| Function | Params | Returns | Behavior |
|----------|--------|---------|----------|
| `getFilterOptions` | none | `ExportFilterOptions` | Fetches available customers, products, cards for filter UI |
| `getPreview` | `ExportFilters` | `ExportPreviewData` | Returns estimate + 5 preview rows for current filters |
| `generateExport` | `ExportFilters & { format: ExportFormat }` | `{ downloadUrl: string }` | Triggers server-side file generation, returns download URL. Format is only needed here, not for preview. |

---

## 3. Component Architecture

### File Structure

```
src/features/export/
├── components/
│   ├── export-page.tsx              — Orchestrator: manages filter state, composes sections
│   ├── export-filters.tsx           — Filters card: date range, presets, customer/product/card filters
│   ├── customer-multi-select.tsx    — Searchable dropdown with checkboxes + chips (uses shadcn Popover)
│   ├── toggle-pill-group.tsx        — Reusable "All" + individual toggle pills with percentages
│   ├── export-estimate.tsx          — Summary text, row count, file size, large export warning
│   ├── data-preview-table.tsx       — First 5 rows, columns change with granularity
│   └── download-bar.tsx             — Format toggle, granularity toggle, download button
└── api/
    ├── types.ts
    ├── mock-data.ts
    ├── mock.ts
    ├── api.ts
    ├── provider.ts
    ├── queries.ts
    └── mutations.ts
```

### Component Details

**ExportPage** (~80 lines)
- Page title: "Export raw data"
- Subtitle: "Download event-level data as a file. Filters narrow your export — the preview and estimate update live as you go."
- "Back to dashboard" link at top, navigates to `/`
- Holds all filter state in `useState` (no forms — these are filters, not submissions)
- Debounces filter changes (300ms) before passing to `useExportPreview`
- Composes all child components, passes filter state + callbacks down
- Loading skeleton while filter options load

**ExportFilters** (~120 lines)
- Wrapped in a bordered card matching mockup's `.fz` section
- Section title: "Filters"
- Date range: two date inputs (From/To) in a 2-column grid
- Date presets: "Last 7 days", "Last 30 days" (default selected), "Last 90 days", "All time" — clicking a preset sets both date inputs and highlights the pill. Manual date change deselects the preset.
- Customer filter: renders `CustomerMultiSelect` with label "Customers"
- Product filter: renders `TogglePillGroup` with label "Products"
- Pricing card filter: renders `TogglePillGroup` with label "Pricing cards"

**CustomerMultiSelect** (~140 lines)
- Default state: "All customers" pill (selected) + hint text "or select specific:"
- Search input: filters the dropdown list as user types
- Dropdown: shadcn `Popover` + `ScrollArea` containing a scrollable list of customers. Each row shows checkbox indicator, customer name, and event count in mono font. Clicking toggles selection.
- Chips: selected customers shown as `Badge` components below the search input, each with "x" to remove
- Selecting any specific customer deselects "All customers". Removing all specific selections re-selects "All customers".
- Dropdown closes on click outside (Popover default behavior)

**TogglePillGroup** (~60 lines)
- Generic component reused for products and pricing cards
- Props: `label`, `options` (key, label, percentage), `selectedKeys`, `onSelectionChange`
- "All [label]" pill + individual pills with percentage labels (e.g., "Property search 68%")
- Selecting specific pills deselects "All". Deselecting all specific pills re-selects "All".
- Active pill: inverted colors (dark bg, light text). Inactive: border, muted text.

**ExportEstimate** (~50 lines)
- Background card matching mockup's `.est` section
- Left side: natural language summary with bold segments (e.g., "Exporting **all events** across **all 18 customers**, **all products**, and **all pricing cards** from **18 Feb — 20 Mar 2026** (30 days).")
- Right side: two metrics — row count and file size (e.g., "247,614 rows", "~18 MB")
- Amber warning banner when `rowCount > 500,000`: "Large export — consider adding filters to reduce the file size."

**DataPreviewTable** (~100 lines)
- Header bar: "Data preview" title + "First 5 of N rows" count
- Table columns depend on granularity:
  - **By dimension** (10 cols): event_time, customer, product, pricing_card, card_version, dimension, quantity, unit_price, cost, event_total
  - **By event** (dynamic cols): event_time, customer, product, pricing_card, card_version, [dimension columns], total_cost
- Monospace font for all data cells. Dimension names and em-dashes styled as muted.
- Footer: "N more rows match your filters"
- Horizontal scroll for overflow on narrow screens

**DownloadBar** (~70 lines)
- Bordered card with flex layout: toggles on left, button on right
- Format toggle: segmented button group — CSV (default) | JSON
- Granularity toggle: segmented button group — By dimension (default) | By event
- Granularity change is lifted to page (affects preview table + estimate)
- Download button states:
  - Default: "Download export" (dark bg)
  - Pending: "Generating..." (dimmed, disabled)
  - Success: "Download ready" (green bg, auto-triggers browser download)
  - Resets to default after download completes
- Footer text: "Export generates server-side. Large files may take up to 30 seconds."

---

## 4. State Management

### Client State (useState in ExportPage)

| State | Type | Default |
|-------|------|---------|
| `dateFrom` | `string` | 30 days before today, "YYYY-MM-DD" |
| `dateTo` | `string` | today, "YYYY-MM-DD" |
| `datePreset` | `DatePreset \| null` | `"30d"` |
| `selectedCustomerIds` | `string[]` | `[]` (empty = all) |
| `selectedProductKeys` | `string[]` | `[]` (empty = all) |
| `selectedCardKeys` | `string[]` | `[]` (empty = all) |
| `granularity` | `ExportGranularity` | `"dimension"` |
| `format` | `ExportFormat` | `"csv"` |

### Server State (TanStack Query)

```typescript
// Query — called once on mount, long stale time
useExportFilterOptions()     → queryKey: ["export-filter-options"]

// Query — called on every filter change (debounced 300ms)
useExportPreview(filters)    → queryKey: ["export-preview", filters]

// Mutation — triggered by download button
useGenerateExport()          → returns { downloadUrl: string }
```

### Data Flow

1. Page mounts → `useExportFilterOptions()` fetches customer/product/card lists for filter UI
2. User changes any filter → `useState` updates → 300ms debounce → `useExportPreview(filters)` fires
3. Estimate + preview table update live from query result
4. User clicks "Download export" → `useGenerateExport()` mutation fires with current filters
5. On success, browser initiates download from returned URL

No Zustand, no forms (React Hook Form not needed — these are filters, not validated submissions), no cross-feature imports.

---

## 5. shadcn Components

**Already installed:** Button, Input, Badge, Skeleton, Card, ScrollArea

**Need to install:** Popover

The Popover wraps the CustomerMultiSelect dropdown:
```
Popover
├── PopoverTrigger — search input area
└── PopoverContent — ScrollArea with customer checkbox list
```

Checkboxes inside the dropdown are custom-styled divs matching the mockup's checkbox pattern (border box with checkmark on selection), not a standalone Checkbox component.

Segmented toggles in the download bar are custom button groups matching the mockup's `.dl-g` pattern.

---

## 6. Mock Data

Matches the mockup exactly:

**Filter options:**
- 18 customers (reusing names from customer mapping mock data): Acme Corp (14,219 evts), BrightPath Ltd (11,402 evts), etc.
- 3 products: Property search (68%), Doc summariser (22%), Content gen (10%)
- 5 pricing cards: Gemini 2.0 Flash (55%), Claude Sonnet (25%), GPT-4o (12%), Google Places (5%), Serper (3%)

**Preview (by dimension mode):** 5 hardcoded rows from mockup:
1. acme_corp / property_search / gemini_2_flash / v3 / input_tokens / 1,842 / 0.0000001500 / 0.000276 / 0.035847
2. acme_corp / property_search / gemini_2_flash / v3 / output_tokens / 623 / 0.0000004000 / 0.000249 / 0.035847
3. acme_corp / property_search / gemini_2_flash / v3 / grounding_requests / 1 / 0.0350000000 / 0.035000 / 0.035847
4. acme_corp / property_search / google_places / v1 / requests / 1 / 0.0320000000 / 0.032000 / 0.032000
5. brightpath / doc_summariser / claude_35_sonnet / v2 / input_tokens / 4,210 / 0.0000030000 / 0.012630 / 0.040335

**Preview (by event mode):** 5 hardcoded rows from mockup. Note: column header is `grounding_reqs` (abbreviated), distinct from the dimension-mode value `grounding_requests` (full name) — this matches the mockup intentionally.

1. acme_corp / property_search / gemini_2_flash / v3 / input_tokens=1,842 / output_tokens=623 / grounding_reqs=1 / requests=— / total_cost=0.035847
2. acme_corp / property_search / google_places / v1 / input_tokens=— / output_tokens=— / grounding_reqs=— / requests=1 / total_cost=0.032000
3. brightpath / doc_summariser / claude_35_sonnet / v2 / input_tokens=4,210 / output_tokens=1,847 / grounding_reqs=— / requests=— / total_cost=0.040335
4. novatech / property_search / gemini_2_flash / v3 / input_tokens=986 / output_tokens=412 / grounding_reqs=1 / requests=— / total_cost=0.035321
5. helios / content_gen / gpt_4o / v1 / input_tokens=2,105 / output_tokens=3,241 / grounding_reqs=— / requests=— / total_cost=0.037685

**Preview value formatting:** Mock data stores all values as pre-formatted strings. The table renders them as-is.

| Column | Format | Example |
|--------|--------|---------|
| quantity | Comma-separated integer | `1,842` |
| unit_price | 10 decimal places | `0.0000001500` |
| cost | 6 decimal places | `0.000276` |
| event_total | 6 decimal places | `0.035847` |
| total_cost | 6 decimal places | `0.035847` |
| Null/missing | Em dash | `—` |

**Estimate:** computed from filters in mock — base rate ~8,260 rows/day, scaled by date range, customer selection (proportional), product percentages, card percentages. Event granularity divides by ~2.8. File size at ~75 bytes/row.

**Download:** mock returns a fake blob URL after 1.5s delay.

**Name discrepancy note:** In dimension mode, the dimension value `grounding_requests` uses the full name. In event mode, the column header `grounding_reqs` is abbreviated. This matches the mockup exactly and should not be normalized.

---

## 7. Route & Navigation

**Route file** (`src/app/routes/_app/export/index.tsx`):
- Replace current stub with thin import of `ExportPage`
- Under 10 lines

**Nav config:**
- No changes — Export already exists in sidebar

**Cross-page links:**
- "Back to dashboard" at top → `/` (Link component)
- Dashboard "Export table" button → `/export` (already a stub link)

---

## 8. Loading & Empty States

- **Loading:** Skeleton matching the page layout (filters card skeleton, estimate skeleton, preview table skeleton)
- **No results:** Estimate shows "0 rows", preview table shows "No events match your current filters" empty state
- **Large export warning:** Amber banner when `rowCount > 500,000`: "Large export — consider adding filters to reduce the file size."
- **Download states:** "Download export" → "Generating..." (disabled, dimmed) → "Download ready" (green bg, triggers download) → resets to default

---

## 9. Scope Exclusions

- **Saved/scheduled exports:** Not in mockup — future feature
- **Export history:** Not in mockup — future feature
- **Server-sent events for progress:** Download uses simple mutation with loading state, no streaming progress
- **Real API implementation:** Mock only for this phase; `api.ts` has stub signatures
- **Tenant mode gating:** Export page is available in all modes (track, revenue, billing)
