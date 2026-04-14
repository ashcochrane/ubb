# Phase 5: Customer Mapping — Design Spec

> **Date:** 2026-04-09
> **Status:** Approved
> **Mockup:** `docs/design/files/customer_mapping_management.html`
> **Rationale:** `docs/design/ui-flow-design-rationale.md` Section 4

---

## 1. Goal

Build the Customer Mapping management page at `/customers`. This is the ongoing dashboard for keeping Stripe-to-SDK customer links healthy — showing sync status, mapping completeness, and orphaned events that need attribution.

The page is accessible when Stripe is connected (`tenantMode` is `"revenue"` or `"billing"`). For `"track"` mode, the page renders a CTA to connect Stripe.

---

## 2. Tenant Mode Strategy

Single component with conditional sections — not separate components per mode.

- `tenantMode` is read from the Zustand auth store
- The mode pill in the sync bar reflects the current mode ("Billing mode" purple, "Revenue + costs" blue)
- Alert urgency wording adapts: orphaned events in billing mode = "revenue leakage", in revenue mode = "incomplete attribution"
- All other UI is identical across revenue and billing modes
- When `tenantMode === "track"`: render a CTA ("Connect Stripe to manage customer mappings") instead of the full page

---

## 3. Data Model

### Types (`features/customers/api/types.ts`)

```typescript
// Data semantics use "unmapped"; display label is "New" (teal pill)
export type CustomerStatus = "active" | "idle" | "unmapped";

export interface CustomerMapping {
  id: string;
  stripeCustomerId: string;
  name: string;
  email: string;
  sdkIdentifier: string | null;
  revenue30d: number;          // micros
  events30d: number;
  lastEventAt: string | null;  // ISO timestamp
  status: CustomerStatus;
}

export interface OrphanedIdentifier {
  id: string;
  sdkIdentifier: string;
  firstSeenAt: string;         // ISO timestamp
  eventCount: number;
  unattributedCost: number;    // micros
}

export interface SyncStatus {
  connected: boolean;
  lastSyncAt: string | null;
  syncing: boolean;
}

export interface CustomerMappingStats {
  totalCustomers: number;
  mapped: number;
  unmapped: number;
  orphanedEvents: number;
  orphanedIdentifiers: number;
  newCustomersSinceLastSync: number;
}

export interface CustomerMappingData {
  syncStatus: SyncStatus;
  stats: CustomerMappingStats;
  customers: CustomerMapping[];
  orphanedIdentifiers: OrphanedIdentifier[];
}
```

### Mutations

| Mutation | Params | Behavior |
|----------|--------|----------|
| `updateMapping` | `customerId: string, sdkIdentifier: string` | Create or update a customer's SDK identifier |
| `assignOrphan` | `orphanId: string, stripeCustomerId: string` | Assign orphaned identifier to a Stripe customer, retroactively attributes events |
| `dismissOrphans` | none | Dismiss all orphaned identifiers |
| `triggerSync` | none | Trigger manual Stripe sync |

---

## 4. Component Architecture

### File Structure

```
src/features/customers/
├── components/
│   ├── customer-mapping-page.tsx    — Orchestrator: fetches data, composes sections
│   ├── sync-status-bar.tsx          — Connection status, last sync, mode pill, sync/settings buttons
│   ├── mapping-stats-grid.tsx       — 4 stat cards (total, mapped, unmapped, orphaned events)
│   ├── alert-banners.tsx            — Conditional amber (new customers) + red (orphaned events)
│   ├── customer-table.tsx           — Filter pills, search, sortable table, inline edit/map
│   └── orphaned-events-section.tsx  — "Unrecognised SDK identifiers" section: header bar, assignment table, dismiss all
└── api/
    ├── types.ts
    ├── mock-data.ts
    ├── mock.ts
    ├── api.ts
    ├── provider.ts
    └── queries.ts
```

### Component Details

**CustomerMappingPage** (~60 lines)
- Page title: "Customer mapping"
- Subtitle: "Manage how your Stripe customers connect to the identifiers your SDK sends. Every mapping must be correct for accurate cost tracking, revenue attribution, and billing."
- Calls `useCustomerMapping()` to fetch all data
- Checks `tenantMode` — if `"track"`, renders Stripe CTA instead of full page
- Renders loading skeleton while fetching
- Composes all child components, passing data as props
- Manages `activeFilter`, `searchQuery`, and `editingCustomerId` via `useState`

**SyncStatusBar** (~50 lines)
- Green dot + "Stripe connected" when `syncStatus.connected`
- "Last synced X ago" using relative time formatting
- Mode pill: reads `tenantMode` from auth store. Purple for billing, blue for revenue
- "Sync now" button: calls `useTriggerSync()` mutation, shows "Syncing..." optimistically
- "Stripe settings" button: links to `/settings`

**MappingStatsGrid** (~40 lines)
- 4-column grid matching mockup
- Cards: Stripe customers (neutral), Mapped (green), Unmapped (amber), Orphaned events (red)
- Subtitles: "X added since last month", "Fully connected", "Need attention", "N unknown SDK IDs"

**AlertBanners** (~50 lines)
- Amber banner: renders when `stats.newCustomersSinceLastSync > 0`. "Map them now" button calls `onFilterChange("unmapped")`
- Red banner: renders when `stats.orphanedEvents > 0`. "Review" button scrolls to orphaned section via `scrollIntoView`
- Alert wording adapts based on `tenantMode` for urgency context
- Either banner can be independently absent

**CustomerTable** (~180 lines, extract `customer-row-edit.tsx` if it exceeds 200)
- Section header with "All customers" title, search input, and "Auto-match" button (disabled, future feature)
- Filter pills: All, Active, Idle, Unmapped — each shows count. Active pill styled with inverted colors
- Client-side filtering by `activeFilter` and `searchQuery` (matches on name, SDK identifier, and Stripe ID — not email, per mockup)
- 7-column table: Stripe customer (name + ID + email), SDK identifier, Revenue (30d), Events (30d), Last event, Status pill, Edit action
- Inline editing via React Hook Form + Zod:
  - Mapped rows: click "Edit" → input + Save/Cancel. Schema: `z.object({ sdkIdentifier: z.string().min(1) })`
  - Unmapped rows: input field always visible with "Map" button. Same schema
  - Save calls `useUpdateMapping()` mutation with optimistic update
- Status pills: Active (green), Idle (gray), New (teal) — "New" is the display label for `status: "unmapped"`
- Revenue formatted via `format.ts` utilities (micros → dollars)

**OrphanedEventsSection** (~80 lines)
- Section title: "Unrecognised SDK identifiers" (matching mockup terminology)
- Description: "These customer IDs appeared in SDK events but don't match any mapping. Either map them to an existing Stripe customer, or check your code for typos."
- Red header bar: "N unknown identifiers (M events)" + "Dismiss all" button
- Table: SDK identifier, First seen, Events count, Unattributed cost, Assign dropdown, Assign button
- Each row has a select dropdown showing all Stripe customers sorted alphabetically. Intelligent fuzzy matching (e.g., suggesting "ClearView Analytics" first for `clearview_v2`) is a future enhancement.
- Assignment uses React Hook Form + Zod: `z.object({ stripeCustomerId: z.string().min(1) })`
- Assign calls `useAssignOrphan()` mutation — row removed optimistically
- "Dismiss all" has a confirmation step before calling `useDismissOrphans()`
- Footer note: "When you assign an orphaned identifier, existing events are retroactively attributed..."

---

## 5. State Management

### Server State (TanStack Query)

```typescript
// Queries
useCustomerMapping()         → queryKey: ["customer-mapping"]

// Mutations (all invalidate ["customer-mapping"] on success)
useUpdateMapping()           → optimistic: update customer's sdkIdentifier in cache
useAssignOrphan()            → optimistic: remove orphan row from cache
useDismissOrphans()          → optimistic: clear orphan list in cache
useTriggerSync()             → optimistic: set syncing = true, revert on settle
```

### Client State (useState in CustomerMappingPage)

| State | Type | Purpose |
|-------|------|---------|
| `activeFilter` | `"all" \| "active" \| "idle" \| "unmapped"` | Which filter pill is selected |
| `searchQuery` | `string` | Search input value |
| `editingCustomerId` | `string \| null` | Which row is in inline edit mode |

### Auth Store (read-only)

- `tenantMode` — drives mode pill and alert wording
- No writes to auth store from this feature

---

## 6. Forms & Validation

All forms use React Hook Form + Zod per project convention.

**Inline mapping edit:**
```typescript
const mappingSchema = z.object({
  sdkIdentifier: z.string().min(1, "SDK identifier is required"),
});
```

**Orphan assignment:**
```typescript
const assignSchema = z.object({
  stripeCustomerId: z.string().min(1, "Select a customer"),
});
```

Each form instance is scoped to its row — `useForm` is called per active edit, not once for the whole table.

---

## 7. Mock Data

Matches the HTML mockup exactly:

- **23 customers total:** 18 active, 3 idle, 2 unmapped (Terraform Solutions, Orbit Analytics)
- **3 orphaned identifiers:** `acme_legacy` (89 events, $12.40), `test_user_001` (41 events, $5.20), `clearview_v2` (12 events, $1.85)
- **Stats:** `totalCustomers: 23`, `mapped: 21`, `unmapped: 2`, `orphanedEvents: 142`, `orphanedIdentifiers: 3`, `newCustomersSinceLastSync: 2`
- **Sync status:** `connected: true`, `lastSyncAt` = 14 minutes ago, `syncing: false`
- All monetary values in micros
- Mock mutations simulate state changes with `delay(300)`

---

## 8. Route & Navigation

**Route file** (`src/app/routes/_app/customers/index.tsx`):
- Replace current stub with thin import of `CustomerMappingPage`
- Under 10 lines

**Nav config:**
- No changes — Customers item already exists in sidebar for all modes
- Page-level gating handles track-only mode (CTA instead of full page)

**Cross-page links:**
- "Stripe settings" → `/settings` (future phase, link is present but page is a stub)
- "Map them now" → sets filter to unmapped (same page)
- "Review" → scrolls to orphaned events section (same page)

---

## 9. Loading & Empty States

- **Loading:** Skeleton matching the page layout (stats grid skeleton, table skeleton)
- **Empty table:** "All customers are mapped and healthy" message when filters produce no results
- **No orphans:** Orphaned events section hidden entirely when `orphanedIdentifiers` is empty
- **No alerts:** Alert banners hidden when conditions not met (new customers = 0, orphaned events = 0)
- **Track mode:** CTA card: "Connect Stripe to manage customer mappings" with description and link to settings

---

## 10. Scope Exclusions

- **Auto-match button:** Rendered but disabled (placeholder for future feature)
- **Table sorting:** Not in mockup — filter pills and search are sufficient for <100 customers
- **Pagination:** Not needed — customer list is small enough for client-side filtering
- **Bulk operations:** Not in mockup — individual row editing only
- **Real API implementation:** Mock only for this phase; `api.ts` has stub signatures
