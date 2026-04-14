# UI flow design rationale

> **Audience:** A developer or agent implementing the frontend. This document explains what each page does, why it exists, what decisions shaped it, and how the pages connect to each other. Read this before looking at the HTML mockups — it gives you the "why" so the UI makes sense.

---

## How this document is structured

The platform has five major UI surfaces. They are explained here in the order a customer encounters them:

1. **Onboarding** — how a new customer gets set up (three different paths depending on what they need)
2. **Creating a pricing card** — the 4-step wizard that defines how API costs are calculated
3. **Editing a pricing card / reconciliation** — what happens after a card is live and prices need correcting
4. **Customer mapping management** — the ongoing dashboard for keeping Stripe-to-SDK links healthy
5. **Exporting raw data** — getting event-level data out of the system

After the individual pages, there is a section on **how everything integrates together** — the navigation model, what links to what, and the overall information architecture.

---

## 1. Onboarding

### The three paths

When a customer first logs in, they choose one of three modes. This choice determines what the platform does with their data and which onboarding steps they see:

| Mode | What it does | Stripe needed? | Steps |
|---|---|---|---|
| **Track costs only** | Monitors API costs per customer, per product. No revenue data. | No | Skip straight to pricing card creation |
| **Revenue + costs** | Pulls revenue from Stripe and pairs it with tracked costs to show profitability. | Yes (read-only) | Stripe key → customer mapping → done |
| **Bill customers** | Everything above, plus debits customer Stripe balances (cost + margin) for each API event. | Yes (read + write) | Stripe key → customer mapping → margin config → review/activate |

The choice screen is in `complete_onboarding_4_screens.html` (the path selection) and `billing_mode_stripe_adaptation.html` (the three-card selector).

**Why three paths instead of one?** Because forcing every customer through Stripe setup when they just want cost tracking would violate the "fast" and "easy" principles. A developer who wants to see "how much am I spending on Gemini" shouldn't need a Stripe account. Conversely, a business that wants to bill customers needs more setup — margin configuration, balance alerts — and shouldn't have those steps hidden in a settings page they might never find.

### Path A: Track costs only

No onboarding steps. The customer goes directly to pricing card creation. The platform only needs SDK events to function — no external integrations.

**Reference mockup:** The "Track costs" card in `complete_onboarding_4_screens.html` leads directly to the pricing card wizard.

### Path B: Revenue + costs (read-only Stripe)

Three steps, shown in `screen_4_stripe_integration.html`:

**Step 1 — Connect Stripe.** The customer creates a restricted API key in their Stripe dashboard with read-only permissions (Customers, Subscriptions, Invoices, Charges — everything else set to "None"). They paste the key, we validate it, and we pull a preview of their Stripe data (customer count, active subscriptions, 30-day revenue).

Why a restricted key instead of OAuth/Connect? Three reasons: it's instant (no approval process), the customer controls exactly what permissions are granted, and it works for any Stripe account regardless of region or plan. The permission table in the UI lists exactly what each permission is used for — transparency builds trust.

Why validate immediately? Because a typo or wrong key type is the most common failure point. The validator catches `sk_` (secret keys — too much access), non-`rk_` prefixes (not a restricted key), and missing permissions (e.g., a key that has Customers but not Invoices). Showing the Stripe data preview after validation ("We found 21 customers, 18 active subs, $8,420 revenue") gives the customer confidence that the right Stripe account is connected.

**Step 2 — Customer mapping.** The customer tells us how their SDK identifies customers — by Stripe customer ID, email, internal slug, or a Stripe metadata field. We auto-match against their Stripe customers and show the results. Unmatched customers get inline input fields so the mapping can be completed right there, not in a separate screen.

Why do this during onboarding instead of later? Because the profitability dashboard is useless without mappings. If a customer connects Stripe and creates pricing cards but doesn't map customers, they see revenue with no costs and costs with no revenue — misleadingly wrong data. Doing it during onboarding means the dashboard works from day one.

The four identifier modes exist because different codebases use different approaches. Some apps already pass `cus_xxxxx` because they use Stripe's SDK. Others look up users by email. Others have their own internal ID scheme. The mode selection tells us how to match, and the auto-matcher runs immediately so the customer sees how many matched and how many need manual input.

**Step 3 — Done.** The Stripe integration is complete. The customer proceeds to create their first pricing card.

**Reference mockups:** `screen_4_stripe_integration.html` (collapsible 3-step version), `step_2_customer_identification.html` (standalone Step 2 with code explanation), `step_2_customer_mapping.html` (earlier version of Step 2).

### Path C: Bill customers (read + write Stripe)

Four steps, shown in `billing_onboarding_fresh_customer_4_steps.html`:

**Step 1 — Connect Stripe (with write permission).** Identical to Path B except the restricted key needs one additional permission: "Customer balance transactions: Write". This allows the platform to create negative balance entries when a customer uses the product. The UI highlights this difference with a purple "billing" tag next to the permission row and an explanation below: "It cannot create charges, modify customer records, or access payment methods."

Why Customer Balance Transactions instead of Stripe Invoices or metered billing? Because balance-based billing is the simplest model for usage-based pricing. The customer's end consumer tops up their balance (via the customer's own payment flow), and our platform debits that balance in real-time as usage events arrive. No subscription management, no invoice generation, no metered billing complexity. One write permission, one simple debit per event.

**Step 2 — Customer mapping.** Identical to Path B. The mapping is the same regardless of whether we're tracking revenue or billing — we need to know which Stripe customer corresponds to which SDK identifier.

**Step 3 — Configure billing (margin setup).** This is the step that's unique to billing mode. The customer sets a default margin percentage that applies to all API costs. A 50% margin means a $2.00 API cost is charged as $3.00 to their end consumer.

Why only a default margin during onboarding? Because the customer has no products or pricing cards yet — those get created after onboarding. Per-product and per-pricing-card margin overrides are available later from the margin management dashboard (`margin-management-dashboard.html`), but during onboarding we can only set the global default.

The billing preview is a key confidence-building element: three boxes showing "API cost + Your margin = Customer charged" with a slider to adjust both the margin percentage and the example cost amount. This makes the abstract concept of "50% margin" concrete: "oh, a $2 API call becomes $3 to my customer, and I keep $1."

The balance alerts section (notify me at $50, email customer at $25, optionally pause at $0) is also set here because it's operationally critical — without alerts, a customer could burn through their balance and the platform would keep debiting into negative territory.

**Step 4 — Review and activate.** A summary of everything configured: Stripe connection details, customer mapping status, margin configuration, and data sync settings. Each section has an "Edit" button that jumps back to the relevant step. The "Per-product overrides" row honestly says "None yet — set up after creating products" because we don't pretend to have information we don't have.

After activation, the next steps are correctly sequenced: create a pricing card first, integrate the SDK, deploy. The pricing card wizard is the natural next action.

**Reference mockups:** `billing_onboarding_fresh_customer_4_steps.html` (fresh customer, 4 steps), `billing_mode_stripe_adaptation.html` (established customer with existing products — shows per-product/per-card margin modes).

### Established customer variant

`billing_mode_stripe_adaptation.html` shows what the billing onboarding looks like for a customer who already has products and pricing cards set up (e.g., they were on "revenue + costs" mode and are upgrading to billing). In this case, Step 3 offers three margin modes: global (same % everywhere), per product (different % per product), and per pricing card (different % per API). The per-product and per-card modes show real product/card names because they already exist. This variant is only shown when the customer has existing data — a fresh customer always sees the simplified 4-step flow.

---

## 2. Creating a pricing card

### What a pricing card is

A pricing card is a versioned bundle of cost dimensions that represents one API or cost source. For example, "Gemini 2.0 Flash" is a pricing card with three dimensions: input tokens, output tokens, and grounding requests. Each dimension has a pricing type (per unit or flat) and a unit price. When the SDK sends a usage event tagged with this card's key, the platform multiplies each dimension's quantity by its unit price and sums them to get the total event cost.

### The 4-step wizard

The wizard is in four files: `pricing_card_creation_flow.html` (Step 1 + overview), `custom_card_details_step.html` (Step 2), `custom_card_dimensions_step.html` (Step 3), and `custom_card_review_test_step.html` (Step 4).

**Step 1 — Source selection.** Choose between creating from a template (pre-configured cards for common APIs like Gemini, GPT-4, Claude) or creating a custom card from scratch.

Why templates? Because the "fast" design goal means a customer tracking Gemini should be able to set up the card in under 60 seconds. A template pre-fills the card name, provider, key, all dimensions, pricing types, and unit prices. The customer reviews and activates — no manual configuration needed. Templates also serve as education: a customer who's never set up a pricing card can see a well-configured example before building their own.

Why custom? Because the platform tracks any API, not just the ones we have templates for. A customer using a niche geocoding API or a custom ML model needs to define their own dimensions.

**Step 2 — Card details.** Name the card, pick the provider, and select a pricing pattern (token-based, per-request, or mixed). The card key (`gemini_2_flash`) is auto-generated from the name using slugification. A live preview card on the right updates as the user types, showing exactly how the card will appear on the dashboard.

Why auto-generate the card key? Because developers will type this key in their SDK calls (`meter.track({ pricing_card: "gemini_2_flash" })`), so it needs to be a valid slug. Auto-generating from the name prevents typos and enforces consistent formatting. The key is editable if the customer wants something different.

Why a pricing pattern selector? Because the pattern pre-seeds Step 3 with the right dimensions. Selecting "token-based" pre-fills input_tokens and output_tokens. Selecting "per-request" pre-fills a single flat-rate requests dimension. Selecting "mixed" pre-fills tokens plus a flat grounding/search fee. This is faster than starting from zero and teaches the customer what dimensions to expect.

**Step 3 — Dimensions.** Configure each cost dimension: metric key, pricing type (per unit or flat), unit price, display label, and display unit. Dimensions can be added, removed, duplicated, and collapsed. A live cost tester at the bottom lets the customer enter sample quantities and see the calculated cost in real-time.

Why per-unit vs flat as the only two types? Because every API cost in existence decomposes into one of these two formulas: `quantity × price_per_unit` (per unit) or `fixed_cost_if_event_fires` (flat). Token pricing is per-unit. Per-request pricing is flat. There is no third type needed — even tiered pricing can be modelled by creating multiple cards for different tiers.

Why a live cost tester? Because unit prices at the scale of `$0.0000001` are impossible for humans to reason about. The tester translates abstract prices into concrete costs: "1,500 input tokens × $0.0000001 = $0.000150." It also shows sanity warnings when one dimension dominates (e.g., "grounding requests account for 98.7% of total cost — is this expected?").

Why quick-add chips? Common dimension names (cached_tokens, search_queries, images) appear as one-click chips below the dimensions list. This is faster than typing and reduces the chance of typos in metric keys, which must match what the SDK sends.

**Step 4 — Review and test.** A read-only summary of the card with a dry-run simulator. The simulator shows line-by-line arithmetic for a sample event: quantity × unit price = line cost for each dimension, then the sum. A cost distribution bar shows what percentage each dimension contributes. A sanity checklist validates: non-zero prices, no duplicate keys, prices within expected ranges, unique card ID.

Below the simulator: product assignment (group this card under a product for dashboard aggregation) and the SDK integration snippet that updates live when a product is assigned (adding the `product: "property_search"` line). The snippet is copy-pasteable — the customer puts it in their app wherever the API call happens.

The activation flow has a confirmation step ("Once active, this card will calculate real costs for every matching usage event") and a success view with next steps (paste the snippet, deploy, check the dashboard). The confirmation exists because activation is a meaningful action — it starts costing real money.

**Reference mockups:** `pricing_card_creation_flow.html`, `custom_card_details_step.html`, `custom_card_dimensions_step.html`, `custom_card_review_test_step.html`.

---

## 3. Editing a pricing card / reconciliation

### Why editing is different from creating

Creating a card is a one-time wizard. Editing a live card is fundamentally different because the card already has historical events priced at the original rates. The platform never retroactively changes historical event costs unless the user explicitly asks for a reconciliation — this is the "risk-free" design principle. Instead, editing a card creates a new version. The old version's events keep their original costs; new events use the new version's prices.

### The reconciliation system

The reconciliation page (`unified_reconciliation_v3.html`) is the most complex UI in the platform. It exists because real-world pricing is messy: providers change prices mid-month, invoices arrive with different amounts than expected, someone configured the wrong unit price and needs to correct historical data.

The page has two main zones:

**Zone 1 — Timeline.** A visual bar showing all versions of a pricing card over time. Two bars are shown: the "originally tracked" timeline (what costs looked like before any corrections) and the "reconciled" timeline (what costs look like after corrections). The difference between these two bars is the net adjustment.

Each version segment is clickable. Clicking one shows a detail card with the version's date range, event count, total cost, and a table of all dimensions with their unit prices.

Three actions are available on each version:

1. **Edit prices** — Change the unit prices for a historical version. All events in that period are recalculated at the corrected prices. Use case: "We configured $0.10/1M input tokens but Google actually charged us $0.15/1M." The UI shows old price → new price for each dimension, requires a reason, and offers a preview before applying.

2. **Adjust boundaries** — Move the dividing line between two adjacent versions. Events that cross the new boundary are repriced under the version they now fall into. Use case: "The price change was effective end of day 5 Feb, not 3 Feb as we originally configured." The UI shows a before/after card for the two affected versions with a date/time picker for the new boundary.

3. **Insert period** — Split an existing version at a date and apply different prices for the second half. This creates a new "retroactive" version (shown in blue on the timeline). Use case: "Google increased input token pricing effective 10 Feb, but we didn't update the card until 18 Mar. We need to retroactively apply the higher price from 10 Feb to 18 Mar." The UI shows the selected version, a split date, and price inputs for the new period — pre-filled with the current prices so only changed dimensions need updating.

**Zone 2 — Adjustments.** For costs that exist outside the event pipeline — refunds, credits, missed data, invoice reconciliation. An adjustment is a dollar amount attributed to a product and distributed across a date range.

Four distribution modes:

1. **Lump sum** — Single date, full amount. Use case: "Google issued a $25 credit on 10 Mar."
2. **Even daily** — Split equally across a date range. Use case: "$180 in untracked costs spread across the month."
3. **Proportional** — Weighted by existing daily costs. Days with higher tracked costs get a larger share. Use case: "Our invoice was $500 more than tracked — allocate proportionally so it matches the usage pattern."
4. **Manual** — Set each day's allocation individually with a bar chart preview. Use case: "I know exactly how much was missing each day from the provider's daily invoice breakdown."

Each adjustment requires a reason (recorded in the audit trail) and optionally a supporting evidence link (invoice URL, support ticket).

**The reconciliation summary bar** at the bottom shows: original tracked cost (struck through), reconciled total (bold), and the net delta (red for increases, green for decreases). This is the single number that answers "how different is reality from what we tracked?"

**The audit trail** records every action chronologically: period inserts, boundary shifts, price edits, and adjustment records. Each entry shows what changed, who did it, when, and the estimated financial impact. This is the compliance and trust layer — any team member can look back and understand why the numbers changed.

**Reference mockup:** `unified_reconciliation_v3.html`.

---

## 4. Customer mapping management

### Why this page exists

Customer mapping is set up during onboarding, but it's not a one-and-done task. Over time: new Stripe customers appear (the customer signs up a new client), internal IDs get refactored (a developer changes how they identify users), and events arrive with unrecognised customer keys (a typo in the SDK call, or a new customer that hasn't been mapped yet).

This page (`customer_mapping_management.html`) is the ongoing home for keeping the Stripe-to-SDK link healthy. It answers: "is everything connected, which specific customers need attention, and are there mystery events floating around?"

### Page structure

**Sync status bar.** Shows Stripe connection health, last sync time, and the current mode (tracking or billing). The "Sync now" button triggers a manual refresh. This gives the customer confidence that the data is current.

**Stats row.** Four numbers: total Stripe customers, mapped count, unmapped count, and orphaned events. If all four are healthy (all mapped, zero orphans), the customer can leave in seconds. If something needs attention, the numbers tell them what and how much.

**Alert banners.** Two conditional banners:
- Amber: "2 new Stripe customers were detected in the last sync." Fires when new customers appear on the Stripe side. Includes a "Map them now" button that filters the table to unmapped rows.
- Red: "142 events arrived with customer IDs that don't match any mapping." Fires when SDK events can't be attributed. In billing mode, this means either unbilled usage (revenue leakage) or inaccurate cost attribution.

**Customer table.** Seven columns: Stripe customer (name + ID + email), SDK identifier, revenue (30d), events (30d), last event time, status, and edit action. The revenue column provides financial context — an unmapped customer with $380/mo revenue is a higher priority fix than one with $15/mo. The "last event" column is the most sensitive health indicator — "2 min ago" means the mapping is working; "—" means either the customer is new or the mapping isn't producing matches.

Filter pills segment the table into actionable populations: All, Active (events flowing), Idle (mapped but no events), Unmapped (new Stripe customers needing identifiers).

Editing is inline — click "Edit" on any row, the SDK identifier cell becomes an input field, change it, click "Save." No modal, no separate page. For unmapped customers, the input field is already visible — type the identifier and click "Map."

**Orphaned events section.** This handles the reverse problem from the main table. The main table is Stripe → SDK ("does this Stripe customer have an SDK identifier?"). The orphan section is SDK → Stripe ("are there SDK identifiers arriving that don't match any known mapping?").

Each orphaned identifier shows: the exact string received, when it first appeared, how many events have accumulated, and the unattributed cost. The resolution mechanism is a dropdown of existing Stripe customers — pick the right one and click "Assign." This does two things: retroactively attributes all existing events to that customer, and creates a new mapping rule so future events with that identifier auto-route. The retroactive attribution is critical — it means fixing a mapping isn't just a go-forward fix, it cleans up historical data too.

### Why this page matters for billing mode specifically

For tracking-only customers, an unmapped customer means incomplete dashboard data — annoying but not financially impactful. For billing customers, an unmapped customer means either: (a) they're using the product without being billed (orphaned events = revenue leakage), or (b) a new customer signed up on Stripe and the system doesn't know whose balance to debit. Both are urgent financial issues. The mode pill at the top ("Billing mode" in purple) visually elevates the importance.

**Reference mockup:** `customer_mapping_management.html`.

---

## 5. Exporting raw data

### What this page does

The data export page (`data_export_page.html`) lets customers download event-level data as CSV or JSON files. It's the "escape hatch" — when the dashboard doesn't answer a specific question, the customer can pull the raw data and analyse it in their own tools (Excel, SQL, Python).

### Page structure

**Filters.** Four filter types that narrow the export:
- Date range with presets (last 7, 30, 90 days, all time)
- Customers (all or select specific, with search and multi-select chips)
- Products (all or select specific, with volume percentages shown)
- Pricing cards (all or select specific, with volume percentages)

Every filter change updates the row estimate and preview table live. The customer never has to "run a query" — the page reacts as they adjust filters.

**Live estimate.** Shows the estimated row count and file size for the current filter selection. A natural-language summary describes what's being exported: "Exporting all events across all 18 customers, all products, and all pricing cards from 18 Feb — 20 Mar 2026 (30 days)." A warning appears for large exports (500k+ rows): "Large export — consider adding filters to reduce the file size."

**Data preview table.** Shows the first 5 rows of what the export will contain. This serves two purposes: it confirms the data shape is what the customer expects (right columns, right granularity), and it lets them verify the filters are working correctly before generating a potentially large file.

**Granularity toggle.** Two modes:
- "By dimension" — one row per dimension per event. A single Gemini API call produces 3 rows (input_tokens, output_tokens, grounding_requests). Columns: event_time, customer, product, pricing_card, card_version, dimension, quantity, unit_price, cost, event_total.
- "By event" — one row per event. Dimensions become columns. The same Gemini call produces 1 row with input_tokens, output_tokens, and grounding_reqs as separate columns. This is a wider but shorter format.

Why two granularity modes? Because "by dimension" is normalised and works well in SQL/databases, while "by event" is denormalised and works better in spreadsheets. Different analysis tools have different preferences.

**Format toggle.** CSV or JSON. CSV for spreadsheets, JSON for programmatic consumption.

**Download button.** Generates the file server-side and provides a download link. Shows "Generating..." state during generation and "Download ready" on completion.

**Reference mockup:** `data_export_page.html`.

---

## 6. How everything integrates together

### The customer journey (chronological)

```
Sign up
  ↓
Choose tracking mode ──→ Costs only: skip to pricing cards
  ↓                  ──→ Revenue+costs: Stripe setup (3 steps) → pricing cards
  ↓                  ──→ Billing: Stripe setup (4 steps) → pricing cards
  ↓
Create first pricing card (4-step wizard)
  ↓
Integrate SDK (copy snippet from Step 4 into their app)
  ↓
Deploy app → events start flowing
  ↓
Dashboard shows live cost data (+ revenue/margin if Stripe connected)
  ↓
Ongoing operations:
  ├── Create more pricing cards as new APIs are added
  ├── Customer mapping management (new customers, orphaned events)
  ├── Margin management (adjust per-product/per-card margins) [billing mode]
  ├── Reconciliation (correct historical prices, record adjustments)
  └── Data export (pull raw data for analysis)
```

### Navigation model

The platform has a persistent sidebar or top nav with these sections:

- **Dashboard** — the profitability overview (`dashboard.html`). This is the home page after onboarding.
- **Pricing cards** — list of all cards, with a "Create card" button leading to the wizard. Clicking a card opens its reconciliation/editing page.
- **Products** — groupings of pricing cards. Products are created either during card creation (Step 4 product assignment) or from a standalone products page.
- **Customers** — the customer mapping management page. Shows mapping health and links to the orphaned events section.
- **Billing** (only if billing mode) — margin management dashboard, balance alerts, billing activity log.
- **Export** — the data export page.
- **Settings** — Stripe connection details, API key management, sync frequency, account settings.

### Cross-page links

These are the key navigation paths between pages:

| From | To | Trigger |
|---|---|---|
| Dashboard | Pricing card reconciliation | Click a pricing card name in the cost breakdown |
| Dashboard | Customer mapping | Click "unmapped" warning or a customer name |
| Dashboard | Data export | "Export" button in the scope bar |
| Pricing card list | Card creation wizard | "Create card" button |
| Pricing card list | Card reconciliation | Click a card row |
| Card creation Step 4 | Dashboard | After activation success |
| Card reconciliation | Card creation wizard | "Edit card" button (creates new version) |
| Customer mapping | Onboarding Step 2 | "Change identifier mode" (rare, resets all mappings) |
| Margin management | Billing onboarding | "Edit" on billing config review card |
| Onboarding completion | Card creation wizard | "Create my first pricing card" button |

### Data flow between pages

The pages share data through the API and database, not through client-side state. However, understanding what data flows where is important for implementation:

**Pricing cards → Dashboard.** The dashboard's cost charts (by product, by pricing card) are aggregations of the `daily_cost_rollups` table, which is populated by the event ingestion pipeline using pricing card configurations. Creating or editing a pricing card affects what appears on the dashboard.

**Stripe integration → Customer mapping → Dashboard.** Stripe sync populates the `customers` table and `customer_revenue` table. Customer mapping links Stripe customer IDs to SDK identifiers. The dashboard's profitability view (revenue vs costs by customer) requires both to be correctly set up — revenue comes from Stripe, costs come from SDK events, and the mapping connects them.

**Margin management → Billing engine → Stripe.** Margin configuration (global, per-product, per-card) is stored in the products and pricing cards tables (margin_override, margin_effective, margin_source fields). When the billing engine processes an event, it reads margin_effective to calculate the charge amount, then creates a Customer Balance Transaction in Stripe for that amount.

**Reconciliation → Dashboard.** Reconciliation actions (price edits, boundary shifts, period inserts) recalculate event costs and update daily_cost_rollups. Adjustments are stored in the adjustments table and added to rollup totals. Both feed into the dashboard's cost figures — so a reconciliation correction is immediately reflected on the dashboard.

**Customer mapping → Orphaned events → Reconciliation.** When an orphaned SDK identifier is assigned to a Stripe customer, the existing events are retroactively attributed. This doesn't change the event costs (those are determined by the pricing card), but it does change the customer attribution — so the dashboard's per-customer view updates.

### The three design principles applied across all pages

Every page should feel consistent with these principles:

1. **Fast.** No page should require more than 3 clicks to complete its primary action. Forms pre-fill where possible. Actions happen inline (no navigating to separate pages for simple edits). Loading states are minimal — use optimistic UI where safe.

2. **Easy.** No jargon without explanation. Every input has a hint or description. Complex concepts (margin, reconciliation, idempotency) are explained through concrete examples and previews, not definitions. The simulator/previewer pattern (used in pricing card dry-run, billing margin preview, export row estimate) is the primary teaching tool — show the result of a configuration, don't just describe it.

3. **Risk-free.** Destructive actions have confirmation steps. Price changes never silently affect historical data. The reconciliation system makes historical corrections explicit and audited. Draft states exist for pricing cards. Anomaly alerts catch unexpected cost spikes. Every mapping change shows what will be retroactively affected.

---

## Reference: HTML mockup inventory

| File | Page | Flow |
|---|---|---|
| `complete_onboarding_4_screens.html` | Trial request, confirmation, login, mode selection | Onboarding entry |
| `billing_mode_stripe_adaptation.html` | Three-path selector + billing Steps 1 & 3 (established customer) | Onboarding (billing, existing data) |
| `billing_onboarding_fresh_customer_4_steps.html` | Full 4-step billing onboarding (fresh customer) | Onboarding (billing, no existing data) |
| `screen_4_stripe_integration.html` | 3-step collapsible Stripe setup | Onboarding (revenue+costs) |
| `step_2_customer_identification.html` | Standalone customer identifier selection + matching | Onboarding Step 2 |
| `step_2_customer_mapping.html` | Earlier version of customer mapping step | Onboarding Step 2 (variant) |
| `step_3_confirm_and_activate.html` | Review and activate for revenue+costs mode | Onboarding Step 3 |
| `pricing_card_creation_flow.html` | 4-step wizard overview with source selection | Pricing card creation |
| `custom_card_details_step.html` | Step 2: card name, provider, pattern, live preview | Pricing card creation |
| `custom_card_dimensions_step.html` | Step 3: dimension config, cost tester | Pricing card creation |
| `custom_card_review_test_step.html` | Step 4: dry-run simulator, product assignment, activation | Pricing card creation |
| `unified_reconciliation_v3.html` | Dual timeline, version editing, adjustments, audit trail | Card editing / reconciliation |
| `customer_mapping_management.html` | Ongoing mapping dashboard with orphaned events | Customer mapping |
| `margin-management-dashboard.html` | Margin hierarchy tree, impact preview, scheduling | Billing margin management |
| `dashboard.html` | Unified profitability dashboard | Main dashboard |
| `data_export_page.html` | Filtered data export with preview | Data export |
| `metering-platform-implementation-guide.md` | Full technical implementation guide (schema, API, SDK) | Technical reference |
