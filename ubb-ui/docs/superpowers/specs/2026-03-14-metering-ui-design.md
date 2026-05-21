# Metering UI Design Spec

> **For agentic workers:** Use superpowers:subagent-driven-development or superpowers:executing-plans to implement the plan generated from this spec.

**Goal:** Build the metering section of the UBB tenant dashboard — pricing card management, a card creation wizard, and a cost analytics dashboard.

**Architecture:** Three client-side views within the existing authenticated layout, using shadcn/ui components, TanStack Router (file-based routes), TanStack Query for data fetching, and Recharts for charts. Data is mocked initially; endpoints will be wired later.

**Tech:** React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui (base-nova) + TanStack Router/Query/Table + Recharts + React Hook Form + Zod

**Out of scope for v1:** Markup management UI, card versioning, product model/CRUD. These are acknowledged backend concepts but intentionally deferred.

---

## Navigation

The metering section has two pages:

```
METERING
  Pricing          → /metering/pricing
  Cost Dashboard   → /metering/dashboard
```

The existing "Usage Explorer" (`usage.tsx`) and "Analytics" (`analytics.tsx`) route files are deleted and replaced by these two. No redirects needed — these pages were placeholders.

---

## Page 1: Pricing Cards (`/metering/pricing`)

### Purpose

The configuration hub where tenants define how API usage gets priced. Lists all rate cards, provides search/filtering, and launches the card creation wizard.

### Layout (top to bottom)

#### Header Row
- Left: Page title "Pricing cards" (text-2xl font-bold)
- Right: Search input ("Search cards...") + "+ New card" button (primary)

Search filters the card grid client-side, matching against card name (event_type) and provider. Debounced at 300ms.

#### Stats Row
Four summary cards in a responsive grid (4 columns on desktop, 2 on mobile):
- **Active cards** — count of distinct provider+event_type groups
- **Tracked this month** — total billed cost formatted as currency
- **Total API calls** — total event count
- **Products using cards** — count of distinct products (placeholder, hardcoded for now)

Each stat card shows a label (text-sm muted) and a value (text-2xl font-bold).

#### Card Grid
Two-column responsive grid (single column on mobile). Each card represents a group of `ProviderRate` records sharing the same `provider + event_type`.

**Card anatomy:**
```
┌─────────────────────────────────────────┐
│ ● Gemini 2.0 Flash           [Active]  │
│   Google                                │
│ ─────────────────────────────────────── │
│   input_tokens          $0.10 / 1M     │
│   output_tokens         $0.40 / 1M     │
│   grounding_requests    $0.035 / req   │
│ ─────────────────────────────────────── │
│   [Property search]      v3 · Updated 2d ago │
└─────────────────────────────────────────┘
```

- Status dot: colored indicator (green = active)
- Name: derived from event_type (humanized)
- Status badge: "Active" in a subtle outlined badge
- Provider: subtitle text in muted color
- Separator line
- Dimensions: each row shows metric_name left-aligned, formatted price right-aligned (e.g. "$0.10 / 1M" calculated from cost_per_unit_micros and unit_quantity)
- Separator line
- Footer: product tag (outlined badge, hardcoded in mock data for now) + relative timestamp from most recent rate's valid_from

**Card interactions:**
- Click card → opens card detail/edit view (future scope, not in v1)
- Hover → subtle elevation/shadow change

### Empty State
When no rate cards exist, show a centered empty state:
- Illustration or icon (CreditCard or similar)
- Heading: "Set up your first pricing card"
- Subtext: "Pricing cards define how your API usage gets costed. Create one to start tracking."
- CTA button: "+ Create pricing card" → opens wizard

### Data
- Mock data initially: 6 sample cards matching the design screenshots (Gemini 2.0 Flash, Google Places, Claude 3.5 Sonnet, GPT-4o, Whisper large-v3, Serper web search)
- Future: `GET /metering/pricing/rates` → group by provider+event_type

---

## Page 2: New Card Wizard

### Purpose

Guided 4-step flow to create a new pricing card (a set of rate definitions). Launched from the Pricing page's "+ New card" button.

### Routing
The wizard lives at `/metering/pricing/new` as a dedicated route (`src/routes/_authenticated/metering/pricing.new.tsx`). This gives the wizard its own URL, supports browser back/forward, and keeps it isolated from the pricing list page. The current step is tracked in component state (not URL params) since losing wizard state on refresh is acceptable — there's no backend draft to recover.

### Stepper
Build a custom stepper component from shadcn primitives (Button, Badge, layout utilities). Four steps displayed horizontally:
1. Source
2. Details
3. Dimensions
4. Review & test

Each step shows a numbered circle with connecting lines. Completed steps show a checkmark. Current step is bold/highlighted.

### Form State
All wizard state lives in a single React Hook Form context with Zod validation. Nothing is persisted to the backend until the user clicks "Activate" on step 4. Navigation between steps validates the current step before advancing.

#### Zod Schema

```typescript
const dimensionSchema = z.object({
  metricKey: z.string().regex(/^[a-z][a-z0-9_]{1,63}$/),
  pricingType: z.enum(["per_unit", "flat"]),
  unitPriceMicros: z.number().int().min(0),
  unitQuantity: z.number().int().min(1).default(1_000_000), // 1 for flat pricing
  displayLabel: z.string().optional(),
  displayUnit: z.string().optional(),
  displayPrice: z.string().optional(), // auto-calculated if blank
});

const wizardSchema = z.object({
  source: z.enum(["template", "custom"]),
  templateId: z.string().optional(),
  name: z.string().min(1).max(100),
  provider: z.string().min(1).max(100),
  cardId: z.string().regex(/^[a-z0-9_-]+$/), // maps to event_type in backend
  pricingPattern: z.enum(["token", "per_request", "mixed"]),
  description: z.string().max(250).optional(),
  pricingSourceUrl: z.string().url().optional().or(z.literal("")),
  dimensions: z.array(dimensionSchema).min(1),
  productTag: z.string().optional(), // display-only grouping, not a backend model
});
```

#### Backend Field Mapping
- `cardId` → `event_type` on `ProviderRate` (the identifier used in SDK calls)
- `name` → humanized display name, stored in mock data only (no backend field yet)
- `provider` → `provider` on `ProviderRate`
- Each dimension → one `ProviderRate` record where `metric_name` = `metricKey`
- "Flat" pricing type → `unit_quantity = 1`, `cost_per_unit_micros` = the flat fee
- "Per unit" pricing type → `unit_quantity` as configured (default 1M), `cost_per_unit_micros` as entered
- Display fields (`displayLabel`, `displayUnit`, `displayPrice`) are derived client-side from `cost_per_unit_micros` and `unit_quantity`. Not stored in backend.

#### Loading & Error States
- "Activate" button shows a loading spinner and is disabled during submission
- On backend error, a toast (Sonner) is shown with the error message and the user stays on Step 4
- On success, redirect to `/metering/pricing` with a success toast
- "Save draft" simply closes the wizard with no backend call (draft state is lost)

---

### Step 1: Source

**Heading:** "How do you want to start?"
**Subtext:** "Pick a pre-built template or configure from scratch. Templates use current public pricing — you just verify."

**Two option cards** (selectable, highlighted border on selection):

| From template | Custom card |
|---|---|
| Pre-filled with current API pricing. Fastest path — just verify and go. | Configure from scratch for any API or service not in our catalog. |

**If "From template" selected**, show a template picker below:

**"Choose a template"** heading, then a row of template cards:
- **Gemini 2.0 Flash** — 3 dimensions
- **GPT-4o** — 2 dimensions
- **Claude Sonnet** — 2 dimensions

Each template card is selectable (highlighted border). Templates are hardcoded data in the frontend containing provider, event_type, and pre-filled dimension configurations with current public pricing.

**Footer:** "Continue" button (right-aligned, disabled until a selection is made)

---

### Step 2: Details

**Breadcrumb tag:** Shows "Custom card" or template name (e.g. "From template: Gemini 2.0 Flash")

**Heading:** "Describe this API"
**Subtext:** "Tell us what you're tracking. This helps us suggest the right dimension structure in the next step and organises your dashboard."

**Identity section:**
- **Card name** — text input, placeholder "e.g. Mapbox Geocoding API, Internal OCR Service, Twilio SMS". Helper: "Use the API or model name your team would recognise. Be specific — include the model variant or tier if relevant."
- **Provider** — select dropdown (with common providers + custom option). Helper: "How this card appears across your account."
- **Card ID** — text input (auto-generated slug from name, editable) + "Regenerate" button. Helper: "Referenced in SDK calls. Auto-derived from name. Locked after activation." Maps to `event_type` in the backend.

**Pricing pattern section:**
**"How does this API charge?"** — helper: "This helps us pre-configure the right dimensions on the next step."

Three option cards (selectable):
- **Token-based** — "Charges per input and/or output token. Most LLM APIs."
- **Per-request** — "Flat fee per API call regardless of payload size."
- **Mixed / other** — "Combination of unit-based and flat charges, or something unique."

**Optional context section:**
- **Description** — textarea (250 char limit), placeholder "e.g. Used for geocoding property addresses in the search pipeline. Rate-limited to 100 req/s on our current plan." Helper: "Notes for your team. Not used in cost calculations."
- **Pricing source URL** — text input, placeholder "e.g. https://cloud.google.com/maps-platform/pricing". Helper: "Link to the provider's pricing page. Helpful when verifying or updating prices later."

**Card preview widget** at the bottom — live-updating mini card showing current state (name, provider, card_id, pricing pattern, status "Draft").

**Footer:** "Back" button (left) + "Continue to dimensions" button (right)

---

### Step 3: Dimensions

**Breadcrumb tags:** Source type + pricing pattern (e.g. "Custom card" + "Pre-seeded: token-based")

**Heading:** "Define cost dimensions"
**Subtext:** "Each dimension is one line item on your cost breakdown. [If from template/pattern]: We've pre-added [X] based on your selection — adjust the prices and add more as needed."

**Dimension cards** — each in a bordered card container:

```
┌─────────────────────────────────────────────────────┐
│ Dimension 1                [Collapse] [Duplicate] [Remove] │
│                                                     │
│ Metric key          Pricing type       Unit price ($)│
│ [input_tokens]      [Per unit|Flat]    [$0.00000010] │
│ "Must match the     toggle button      "Price per    │
│  key your SDK                           single token"│
│  sends"                                              │
│                                                     │
│ Display label       Display unit       Display price │
│ [Input tokens]      [per 1M tokens]    [e.g. $0.10] │
│                                        "Shown on     │
│                                         dashboard.   │
│                                         Auto-calc'd  │
│                                         if blank."   │
└─────────────────────────────────────────────────────┘
```

**Fields per dimension:**
- **Metric key** — text input (must match SDK key). Validated: lowercase, alphanumeric + underscores.
- **Pricing type** — toggle: "Per unit" (default) / "Flat". Per unit = cost_per_unit_micros / unit_quantity. Flat = fixed cost per event.
- **Unit price ($)** — number input showing raw micros price (e.g. $0.00000010). Helper text explains what this means for the pricing type.
- **Display label** — text input for human-readable name (e.g. "Input tokens")
- **Display unit** — text input (e.g. "per 1M tokens")
- **Display price** — text input (e.g. "$0.10"). Auto-calculated from unit price if blank. This is the price shown on the card in the dashboard.

**"+ Add dimension" button** with quick-add suggestions below it as chips/badges (e.g. "+ grounding", "+ cached tokens", "+ image tokens", "+ requests", "+ search queries"). Clicking a suggestion adds a pre-configured dimension.

**Live cost tester widget** at the bottom — bordered card with accent background:
- Heading: "Live cost tester" + "Updates as you type" badge
- For each dimension: metric_key label + number input (quantity) + calculated breakdown (e.g. "1,000 x $0 = $0.000000")
- **Total event cost** row at the bottom (bold)
- All calculations are pure client-side math using the entered prices.

**Footer:** "Back" + "Save draft" + "Review & test"

---

### Step 4: Review & Test

**Heading:** "Review and test"
**Subtext:** "Verify your configuration, run a test event to confirm costs calculate correctly, then activate when ready."

**Card summary** — bordered card:
- Card name + "Draft v1" badge + "Edit details" button
- Provider + card_id (monospace)
- Separator
- "Cost dimensions (N)" heading + "Edit dimensions" button
- Table: metric_name | pricing type | display unit | display price

**Dry-run simulator** — bordered card with accent background:
- Heading: "Dry-run simulator" + "Looks correct" status badge (green when all values are valid)
- Subtext: "Enter realistic sample quantities for a single API call. The simulator shows exactly how costs would be calculated."
- Per-dimension rows: metric_key + number input + breakdown string (e.g. "1,500 x $0.0000001 = $0.000150")
- Separator
- Per-dimension cost summary rows (label + cost right-aligned)
- **Total per event** row (bold, larger text)
- Daily/monthly projections: "At 1,000 events/day: ~$35.47/day · ~$1,064/month"
- **Cost distribution** — stacked bar showing percentage per dimension with legend

**Sanity checks** — list of validation items with check/warning icons:
- All dimensions have non-zero prices (check or warning)
- No duplicate metric keys (check or warning)
- Unit prices are within expected ranges (check or warning)
- Cost dominated by one dimension (informational warning if one dimension is >90%)
- Card ID is valid and unique (check)

**Assign to product** (future scope) — "Group this card under a product for dashboard cost aggregation. You can change this anytime." Shows product chips (e.g. "Property search", "Doc summariser") + "+ Create new product". For v1, this section is present in the UI with hardcoded options from mock data but does not persist to any backend model.

**Footer:** "Back" + "Save draft" + "Activate" (primary button). Activate creates the rates and redirects to the pricing cards page with a success toast.

---

## Page 3: Cost Dashboard (`/metering/dashboard`)

### Purpose

Day-to-day operational view showing cost trends, breakdowns by product/card/dimension, and recent usage events. The primary monitoring page for tenants.

### Layout (top to bottom)

#### Header Row
- Left: "Cost dashboard" (text-2xl font-bold)
- Right: Period toggle group (7d, 30d, 90d, YTD) + "All products" dropdown + "Export" button

#### Alert Banner (optional)
Dismissible banner with warning styling (warm background matching theme):
- Warning icon + message text (e.g. "Cost spike detected: Gemini 2.0 Flash costs were 3.2x above daily average on Mar 11.")
- "Dismiss" button

This is a stretch goal — can be hardcoded/mocked initially or omitted from v1.

#### Stats Row
Four summary cards in a responsive grid:
- **Total cost (period)** — formatted currency + comparison badge (e.g. "+12.3% vs prev 30d" in green)
- **Total events** — formatted number + comparison
- **Avg cost / event** — formatted currency + comparison
- **Avg daily cost** — formatted currency + "Typical range: $35-48" subtitle

#### Cost Over Time Chart
Full-width area chart (Recharts):
- X-axis: dates
- Y-axis: dollar amounts
- Multiple series (one per product) with legend above the chart
- "View details" button top-right
- Stacked or layered area fill with semi-transparent colors

#### Cost Breakdowns Row
Two cards side-by-side (responsive, stacks on mobile):

**Cost by product:**
- List of products with colored dot + name + horizontal bar + dollar amount + percentage
- Sorted by cost descending

**Cost by pricing card:**
- Same layout but grouped by card (provider name)
- Sorted by cost descending

#### Cost by Dimension Table
Full-width data table (TanStack Table):
- Header: "Cost by dimension" + "View all" button
- Columns: Dimension (monospace), Card, Volume (with unit), Cost ($), Share (%)
- Sorted by cost descending
- Shows top ~6 rows with "View all" for expansion

#### Recent Events Table
Full-width data table (TanStack Table):
- Header: "Recent events" + "View all events" button
- Columns: Time (relative), Card, Product (badge), Dimensions (summary like "1,842 in · 623 out · 1 ground"), Cost ($)
- Shows latest ~6 events
- "View all events" links to a future usage explorer page

### Empty State
When no usage data exists:
- Chart area shows flat line at $0
- Stats show $0 / 0
- Tables show "No usage data yet" with guidance: "Start sending usage events via the SDK to see cost analytics here."

### Data
- Mock data initially matching the design screenshots
- Future: extended analytics endpoints

---

## Shared UI Patterns

### Mock Data Layer
Create a `src/lib/mock-data/metering.ts` file with:
- Sample rate cards (6 cards matching screenshots)
- Sample analytics data (30 days of daily costs)
- Sample recent events
- Template definitions for the wizard

This keeps mock data centralized and easy to swap out for real API calls later.

### Formatting Utilities
Extend existing `src/lib/format.ts` with:
- `formatPrice(costPerUnitMicros, unitQuantity)` — returns display string like "$0.10 / 1M"
- `formatCostMicros(micros)` — returns "$1,247" or "$0.0148" depending on magnitude
- `formatEventCount(count)` — returns "84.2k" style abbreviations
- `formatPercentChange(current, previous)` — returns "+12.3%" with sign

### Component Reuse
- Stats cards: extract a generic `StatCard` component (label, value, subtitle/comparison)
- Data tables: use existing TanStack Table setup from customers table as reference
- Cards: shadcn Card component for all card layouts
- Badges: shadcn Badge for status indicators, product tags
- Form inputs: shadcn Input, Select, Textarea with React Hook Form bindings (already available)

---

## File Structure

```
src/
  routes/_authenticated/metering/
    pricing.tsx              — Pricing cards list page route
    pricing.new.tsx          — New card wizard route (full-page)
    dashboard.tsx            — Cost dashboard page route
  components/
    shared/
      stat-card.tsx            — Reusable stat card (label, value, subtitle/comparison)
      stepper.tsx              — Custom stepper component built from shadcn primitives
    metering/
      pricing/
        pricing-cards-page.tsx   — Main pricing page component
        pricing-card.tsx         — Individual card in the grid
        pricing-stats.tsx        — Stats row for pricing page
        pricing-empty-state.tsx  — Empty state for no cards
      wizard/
        new-card-wizard.tsx      — Wizard container with stepper + form provider
        step-source.tsx          — Step 1: Source selection
        step-details.tsx         — Step 2: Card details form
        step-dimensions.tsx      — Step 3: Dimension configuration
        step-review.tsx          — Step 4: Review & test
        card-preview.tsx         — Live card preview widget
        cost-tester.tsx          — Shared cost tester / dry-run simulator (used in steps 3 and 4; step 4 adds projections + cost distribution bar)
        sanity-checks.tsx        — Validation checklist
      dashboard/
        cost-dashboard-page.tsx  — Main dashboard component
        cost-stats.tsx           — Stats row for dashboard (uses shared StatCard)
        cost-chart.tsx           — Cost over time area chart
        cost-breakdowns.tsx      — Cost by product + by card side-by-side
        cost-by-dimension.tsx    — Dimension cost table
        recent-events.tsx        — Recent events table
        dashboard-empty-state.tsx — Empty state for no usage
  lib/
    mock-data/
      metering.ts              — All mock data for metering section
  api/hooks/
    use-pricing.ts             — TanStack Query hooks for pricing (returns mock data via initialData, swap queryFn for real endpoint later)
    use-metering-analytics.ts  — TanStack Query hooks for analytics (same pattern)
```

**Deleted files:** `src/routes/_authenticated/metering/usage.tsx`, `src/routes/_authenticated/metering/analytics.tsx`

---

## Nav Config Update

Update `nav-config.ts` to replace the metering section:

```ts
{
  label: "METERING",
  items: [
    { title: "Pricing", url: "/metering/pricing", icon: DollarSign },
    { title: "Cost Dashboard", url: "/metering/dashboard", icon: BarChart3 },
  ],
}
```

Remove the old "Usage Explorer" and "Analytics" items. Delete the unused route files (`usage.tsx`, `analytics.tsx`).
