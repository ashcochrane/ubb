// THE LEGACY LABEL ADAPTER — every export below is a migration debt (#210).
//
// This module used to be the console's whole labelling layer, and ADR-0008 §4
// retired the idea it rests on. It hand-writes twenty-three value maps and falls
// back to `humanize`, which title-cases a raw token into something that reads
// like English — manufacturing user-facing terminology out of an implementation
// token. #154 §9.1 called that a safe soft-landing; ADR-0008 §4.3 REVERSES that
// ruling and calls it a defect. A system that has just spent thirteen documents
// deciding what things are called must not then let a string transformation
// invent a name nobody chose.
//
// The replacement is `@/lib/localisation` reading `@/locales`: keys generated
// from the registry into `@/lib/vocabulary`, wording owned by the console, and
// strict lookup with no fallback at all. Write new code against that.
//
// This file survives only because it is imported by forty-seven others, and #210
// is explicit that slice 0 ends when the mechanism is active and regressions
// are impossible — not when every importer has been rewritten. So:
//
//   * every map below and every file importing `humanize` is an individually
//     identified entry in `gates/migration-ledger.yaml`, owned by the slice
//     that rebuilds that vocabulary;
//   * the ledger only ever shrinks, so a NEW map or a NEW humanising import
//     fails CI (`tools/gates ratchet`) — the old architecture cannot spread;
//   * `tests/contracts/test_label_catalogue.py` holds this file to that ledger
//     in both directions, so paying a debt and deleting its entry are one act.
//
// The contract still has NO closed enums (ADR-003 "open enums") and that has
// not changed. What changed is what an unfamiliar value renders as: a
// deliberate generic form, never a title-cased guess at English.

import {
  AFFORDABILITY_REASON_KNOWN_VALUES,
  CEILING_STATUS_VALUES,
  CONTROL_FAMILY_VALUES,
  COSTING_METHOD_VALUES,
  COSTING_STATUS_VALUES,
  PRICING_METHOD_VALUES,
  PRICING_MODE_VALUES,
  PRICING_STATUS_VALUES,
  RATE_STRUCTURE_VALUES,
  REASON_CODE_KNOWN_VALUES,
  TASK_STATUS_VALUES,
  TENANT_PRODUCT_VALUES,
  TRIGGER_SOURCE_KNOWN_VALUES,
  USAGE_EVENT_KIND_VALUES,
  WEBHOOK_EVENT_TYPE_VALUES,
  type TenantProduct,
} from "@/lib/vocabulary";

/** "failed_permanent" → "Failed permanent", "TOP_UP" → "Top up".
 *
 * The humaniser ADR-0008 §4.3 retires. Reachable only from the sites the
 * migration ledger allowlists; a call from anywhere else fails CI.
 */
export function humanize(value: string): string {
  if (!value) return "—";
  const spaced = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

/** A hand-written value map with a humanising fallback — the shape being retired.
 *
 * Named `legacyLabelMap` rather than `label` so the gate can take the set of
 * maps mechanically: `label` appears in this console as a prop, a variable and
 * a string hundreds of times, so a check keyed on it would be a check keyed on
 * a coincidence. This name appears nowhere else in the tree.
 */
function legacyLabelMap(map: Record<string, string>) {
  return (value: string | null | undefined): string => {
    if (value === null || value === undefined || value === "") return "—";
    return map[value] ?? humanize(value);
  };
}

// ---------------------------------------------------------------------------
// Tenant / workspace

export const BILLING_MODES = ["meter_only", "prepaid", "postpaid"] as const;
export type BillingMode = (typeof BILLING_MODES)[number];

export const billingModeLabel = legacyLabelMap({
  meter_only: "Meter only",
  prepaid: "Prepaid credits",
  postpaid: "Postpaid",
});

export const billingModeDescription = legacyLabelMap({
  meter_only:
    "Track usage, provider cost, and margin. No money movement in UBB.",
  prepaid:
    "Customers hold prepaid credit; usage draws the balance down in real time.",
  postpaid:
    "Usage accrues per period and is pushed to Stripe as invoice line items at period close.",
});

// The registry's three, held BY REFERENCE (#241). `domain-vocabulary/` names
// this file as the console's consumer of `tenant_product`, which is why the
// names stay here rather than moving: the alias is what that declaration
// resolves to, and re-homing it is a registry edit, not a console one.
//
// The words for these values are no longer here at all — `@/lib/products`
// binds them to the label catalogue, and carries the console's own
// per-product description copy (ADR-0008 §4.5).
//
// So NOTHING here needs a console consumer any more, and a file that wants
// only the type takes `TenantProduct` from `@/lib/vocabulary` directly rather
// than reaching this module for it: the tenant-config hook, the nav config and
// the product gate all do. What still imports these two names does so because
// it is already here for a map somebody else owes.
export const PRODUCTS = TENANT_PRODUCT_VALUES;
export type Product = TenantProduct;

export const enforcementModeLabel = legacyLabelMap({
  off: "Off",
  enforcing: "Enforcing",
});

// ---------------------------------------------------------------------------
// Team

export const roleLabel = legacyLabelMap({ admin: "Admin", write: "Write", read: "Read" });
export const ROLES = ["read", "write", "admin"] as const;
export type Role = (typeof ROLES)[number];

/** Rank a role for floor comparisons; unknown roles rank lowest (fail closed). */
export function roleRank(role: string | null | undefined): number {
  return role === "admin" ? 2 : role === "write" ? 1 : role === "read" ? 0 : -1;
}

export const memberStatusLabel = legacyLabelMap({ pending: "Pending", active: "Active" });
export const invitationStatusLabel = legacyLabelMap({
  pending: "Pending",
  accepted: "Accepted",
  revoked: "Revoked",
});

// ---------------------------------------------------------------------------
// Billing / wallet

export const transactionTypeLabel = legacyLabelMap({
  TOP_UP: "Top up",
  USAGE_DEDUCTION: "Usage deduction",
  WITHDRAWAL: "Withdrawal",
  REFUND: "Refund",
  ADJUSTMENT: "Adjustment",
  DISPUTE_DEDUCTION: "Dispute deduction",
  STRIPE_REFUND: "Stripe refund",
  DEBIT: "Debit",
  GRANT: "Credit grant",
  GRANT_EXPIRY: "Grant expiry",
  GRANT_VOID: "Grant void",
});

export const grantKindLabel = legacyLabelMap({ paid: "Paid", promo: "Promo" });
export const grantStatusLabel = legacyLabelMap({
  active: "Active",
  depleted: "Depleted",
  expired: "Expired",
  voided: "Voided",
});
export const grantSourceLabel = legacyLabelMap({
  checkout: "Checkout",
  auto_topup: "Auto top-up",
  api: "API",
  other: "Other",
});

export const usageInvoiceStatusLabel = legacyLabelMap({
  pending: "Pending",
  pushing: "Pushing",
  pushed: "Pushed",
  skipped: "Skipped",
  failed: "Failed",
  failed_permanent: "Failed permanently",
});

export const tenantInvoiceStatusLabel = legacyLabelMap({
  draft: "Draft",
  finalized: "Finalized",
  paid: "Paid",
  void: "Void",
  uncollectible: "Uncollectible",
});

export const billingPeriodStatusLabel = legacyLabelMap({
  open: "Open",
  closed: "Closed",
  invoicing: "Invoicing",
  invoiced: "Invoiced",
});

export const budgetEnforceModeLabel = legacyLabelMap({
  alert_only: "Alert only",
  blocking: "Blocking",
});

// ---------------------------------------------------------------------------
// Metering / events

// The registry's two, held BY REFERENCE (#279) — the same shape and the same
// reason as `PRODUCTS` above: `domain-vocabulary/` names this file as the
// console's consumer of `costing_method`, so re-homing the list is a registry
// edit rather than a console one.
//
// How an Event Type's supplier cost is derived. The WORDS for both are already
// in the catalogue under `costing_method.*`, so a surface that comes to render
// one binds `labelMap(COSTING_METHOD_LABEL_KEYS)` in its own module — the
// `@/lib/products` shape — and never a map here.
export const COSTING_METHODS = COSTING_METHOD_VALUES;

// Whether a supplier cost is settled, and the third of `costing_method`'s
// neighbours to be held by reference here. `domain-vocabulary/` has named this
// file the console's consumer of `costing_status` since #316; until now it held
// none of the three values, which is what `g2-console-costing_status` recorded
// and what this line pays off.
//
// The WORDS are in the catalogue under `costing_status.*` and the rendering
// rule is `@/lib/supplier-cost` — the module that decides what a total may say
// when some of the costs under it were never learned. Nothing here, and no map:
// this file is the legacy adapter, and a concept that has been migrated leaves
// behind its value list and nothing else.
export const COSTING_STATUSES = COSTING_STATUS_VALUES;

// ⚠ `cardTypeLabel` IS DELETED (#368), WHICH IS WHAT ITS LEDGER ENTRY ASKED
// FOR. That entry said the map "is not replaced by a label key at all — it
// goes when slice 4 replaces `RateCard` with the Pricing Book, alongside the
// two G9 table entries that name the same models". Both of those are paid in
// the same commit. A Pricing Book and a cost book are separate entities on
// separate screens now, so nothing needs a word for which of two a book is.

// ⚠ `pricingModelLabel` IS DELETED (#371), WHICH IS WHAT ITS LEDGER ENTRY
// ASKED FOR: *"it becomes `labelMap(RATE_STRUCTURE_LABEL_KEYS)` in the slice
// that rebuilds that vocabulary — the same slice the concept's own value-list
// entry names, because a value list and the words for it cannot honestly move
// apart."* Both halves are paid in this commit — the words moved to
// `features/pricing/lib/rates.ts`, off the locale catalogue, which already
// carried this exact wording; the value list stays here, by reference, on the
// line below.
//
// #366 had already moved the KEYS to the rate's ratified arithmetic shapes
// while leaving the export name alone, because this entry addressed the map by
// export name and a rename would have read to the ratchet as an entry ADDED.
// Deleting it is what that spelling was being preserved for.

// The rate's arithmetic shape, the two methods a pricing rule may declare, and
// whether a customer price is settled — the registry's three, held BY
// REFERENCE (#371), on the same terms and for the same reason as `PRODUCTS`,
// `COSTING_METHODS` and `COSTING_STATUSES` above. `domain-vocabulary/` names
// this file as the console's consumer of all three, so re-homing a list is a
// registry edit rather than a console one.
//
// The WORDS are in the catalogue under `rate_structure.*`, `pricing_method.*`
// and `pricing_status.*`, bound where they are rendered:
// `features/pricing/lib/rules.ts` for the rate's arithmetic shape, and
// `@/lib/customer-price` for the status AND — since #372 — for the method. The
// method's binding sits in `lib/` rather than in the pricing feature because
// TWO features render one: the pricing feature on its rules and in a publish's
// diff, and the events feature on the receipt, where two events of one Event
// Type read differently because their deals differ. `costing_method` above
// still has no binding anywhere, on the same rule: a surface binds the words
// when it comes to show them. Nothing here, and no map: this file is the legacy
// adapter, and a concept that has been migrated leaves behind its value list
// and nothing else.
export const RATE_STRUCTURES = RATE_STRUCTURE_VALUES;
export const PRICING_METHODS = PRICING_METHOD_VALUES;
export const PRICING_STATUSES = PRICING_STATUS_VALUES;

// How a kind of work is sold — the registry's two, held BY REFERENCE (#423),
// on the same terms and for the same reason as the trio above. `domain-
// vocabulary/` names this file as the console's consumer of `pricing_mode`,
// and until now it held neither value, which is what `g2-console-pricing_mode`
// recorded and what this line pays off. There was never a hand-written map to
// delete for this one: the concept was created by slice 5 (#414), so the
// console's first sight of it is already the migrated shape.
//
// The WORDS have been in the catalogue under `pricing_mode.*` since #406. The
// binding was `features/tasks/lib/kinds.ts` — the surface that renders a kind
// of work, per slice 4's rule that a surface binds the words it renders —
// until #425 moved it to `@/lib/pricing-mode`, the day a second feature came
// to render the same word: a charge's receipt carries the regime by value,
// and a concept two features render binds in `lib/`. Nothing here, and no
// map: this file is the legacy adapter, and a concept that has been migrated
// leaves behind its value list and nothing else.
export const PRICING_MODES = PRICING_MODE_VALUES;

export const stopScopeLabel = legacyLabelMap({
  task: "Task",
  subtask: "Subtask",
  customer: "Customer",
});

// ⚠ `stopReasonLabel` IS DELETED (#466), WHICH IS WHAT ITS LEDGER ENTRY ASKED
// FOR: *"it becomes `labelMap(REASON_CODE_LABEL_KEYS)` in the slice that
// rebuilds that vocabulary."* The concept is OPEN, so the binding is not a
// `labelMap` but the console's one open-set rule —
// `components/shared/open-set-value.tsx` over `REASON_CODE_LABEL_KEYS` — at
// each of the surfaces that render a stop word: the stop-context timeline and
// the ledger's stopped indicator (events), the recorded response's stop
// verdict (developers), and Stops and breaches (spend-controls). The
// catalogue has carried all seven words under `reason_code.*` since #457's
// two coinages. The old map also carried five spellings the registry retired
// and two words that are not stop reasons at all; a value outside the seven
// now renders as the token it is, marked unrecognised, never a guess.
//
// Why work was stopped — the registry's seven KNOWN values of an OPEN
// concept, held BY REFERENCE (#466), on `TRIGGER_SOURCES`' terms: the
// generated list is `_KNOWN_VALUES` and a value outside it is legal on the
// wire (ADR-0003). `domain-vocabulary/` names this file as the console's
// consumer of `reason_code`; `g3-console-reason_code` recorded that it held
// none, and this line pays it off.
export const REASON_CODES = REASON_CODE_KNOWN_VALUES;

export const ingestRejectionLabel = legacyLabelMap({
  billing_period_closed: "Billing period closed",
  effective_at_in_future: "Timestamp in the future",
  effective_at_naive: "Timestamp missing timezone",
  effective_at_too_old: "Timestamp too old",
  not_found: "Unknown customer or task",
  validation_error: "Validation failed",
});

// ⚠ `taskStatusLabel` IS DELETED (#424), WHICH IS WHAT ITS LEDGER ENTRY ASKED
// FOR: *"it becomes `labelMap(TASK_STATUS_LABEL_KEYS)` in the slice that
// rebuilds that vocabulary — the same slice the concept's own value-list entry
// names, because a value list and the words for it cannot honestly move
// apart."* Both halves are paid in this commit — the binding is
// `@/lib/task-status`, off the locale catalogue, which has carried all six
// states under `task_status.*` since slice 0; the value list is held by
// reference on the line below. The old map held FOUR of the six: `cancelled`
// and `expired` were never in it, and adding them to it would have been the
// wrong payment twice over (spec §26, §27).

// The durable state a unit of work is in — the registry's six, held BY
// REFERENCE (#424), on the same terms and for the same reason as `PRODUCTS`
// and the pricing lists above. `domain-vocabulary/` names this file as the
// console's consumer of `task_status`, so re-homing the list is a registry
// edit rather than a console one. Nothing here, and no map: this file is the
// legacy adapter, and a concept that has been migrated leaves behind its
// value list and nothing else.
export const TASK_STATUSES = TASK_STATUS_VALUES;

// Which kind of posting a usage row is — the registry's two, held BY
// REFERENCE (#425), on the same terms and for the same reason as the lists
// above. `domain-vocabulary/` names this file as the console's consumer of
// `usage_event_kind`, and until now it held neither value, which is what
// `g2-console-usage_event_kind` recorded and what this line pays off. There
// was never a hand-written map to delete for this one: the concept was
// created by slice 5 (#417), so the console's first sight of it is already
// the migrated shape — spec §27's third shape, as `PRICING_MODES` above.
//
// The WORDS have been in the catalogue under `usage_event_kind.*` since the
// concept was coined, and the binding is `features/events/lib/kind.ts` — the
// surface that renders a posting, per slice 4's rule that a surface binds the
// words it renders. Nothing here, and no map: this file is the legacy
// adapter, and a concept that has been migrated leaves behind its value list
// and nothing else.
export const USAGE_EVENT_KINDS = USAGE_EVENT_KIND_VALUES;

// What a ceiling assessment concluded — the registry's four, held BY
// REFERENCE (#454), on the same terms as the lists above. `domain-vocabulary/`
// names this file as the console's consumer of `ceiling_status`, and until
// now it held none of the four, which is what `g2-console-ceiling_status`
// recorded and what this line pays off. There was never a map to delete: the
// status reached the wire in #452 and the console's first sight of it is the
// migrated shape, as `USAGE_EVENT_KINDS` above. The WORDS have been in the
// catalogue under `ceiling_status.*` since the concept was coined, and the
// binding is `features/tasks/lib/ceiling.ts` — the run page is the surface
// that renders them.
export const CEILING_STATUSES = CEILING_STATUS_VALUES;

// The mechanism that applied a stop — the registry's five KNOWN values of an
// OPEN concept, held BY REFERENCE (#454). `domain-vocabulary/` names this file
// as the console's consumer of `trigger_source`; `g3-console-trigger_source`
// recorded that it held none, and this line pays it off. The concept is open
// (ADR-0003), so the generated list is `_KNOWN_VALUES` and a value outside it
// is legal on the wire — the console's rule for such a value is set in
// `components/shared/open-set-value.tsx` and proved there on these keys. No
// map, no binding beyond that helper: no read this console makes publishes
// the field today (it travels on the terminal webhook payloads only), and
// the words are in the catalogue under `trigger_source.*` for the surface
// that first does.
export const TRIGGER_SOURCES = TRIGGER_SOURCE_KNOWN_VALUES;

// Why an affordability question was answered no — the registry's nine KNOWN
// values of an OPEN concept, held BY REFERENCE (#463), on `TRIGGER_SOURCES`'
// terms: `domain-vocabulary/` names this file as the console's consumer of
// `affordability_reason`, `g3-console-affordability_reason` recorded that it
// held none, and this line pays it off. The hand-written map that stood here
// (`g6-map-pre-check-reason-label`) is deleted with it — it spelled two
// refusal words the registry had retired and humanised the rest. The words
// are in the catalogue under `affordability_reason.*`; the binding is the
// customers feature's affordability dialog, which renders a value through
// `components/shared/open-set-value.tsx` so one the registry has not seen
// renders as the token it is, marked, never guessed at.
export const AFFORDABILITY_REASONS = AFFORDABILITY_REASON_KNOWN_VALUES;

// ⚠ `pastLimitFamilyLabel` IS DELETED (#466), WHICH IS WHAT ITS LEDGER ENTRY
// ASKED FOR: *"it becomes `labelMap(CONTROL_FAMILY_LABEL_KEYS)` in the slice
// that rebuilds that vocabulary — the same slice the concept's own value-list
// entry names, because a value list and the words for it cannot honestly move
// apart."* Both halves are paid in this commit — the binding is
// `features/spend-controls/lib/families.ts`, off the locale catalogue, which
// has carried all four families under `control_family.*` since the concept
// was coined; the value list is held by reference on the line below. The old
// map held THREE words for a family of four, under the report's own spellings
// (`floor_stop`, `soft_floor`, `task`), and none of them was a registry value.
//
// Which of the four spend controls a signal came from — the registry's four,
// held BY REFERENCE (#466), on the same terms and for the same reason as
// `PRODUCTS` above: `domain-vocabulary/` names this file as the console's
// consumer of `control_family`, so re-homing the list is a registry edit
// rather than a console one. Nothing here, and no map.
export const CONTROL_FAMILIES = CONTROL_FAMILY_VALUES;

export const revenueModeLabel = legacyLabelMap({
  billed: "Billed revenue",
  metered_only: "Metered only",
});

// Allowed grouping dimensions for usage analytics + timeseries.
export const ANALYTICS_DIMENSIONS = [
  "provider",
  "event_type",
  "customer",
  "dim1",
  "dim2",
  "dim3",
] as const;
export const TIMESERIES_GROUP_BY = [
  "provider",
  "event_type",
  "dim1",
  "dim2",
  "dim3",
] as const;

export const dimensionLabel = legacyLabelMap({
  provider: "Provider",
  event_type: "Event type",
  customer: "Customer",
  dim1: "Dimension 1",
  dim2: "Dimension 2",
  dim3: "Dimension 3",
});

// ---------------------------------------------------------------------------
// Audit

export const actorKindLabel = legacyLabelMap({
  member: "Team member",
  api_key: "API key",
  operator: "UBB operator",
  end_customer: "End customer",
  system: "System",
});

// ---------------------------------------------------------------------------
// Referrals

export const rewardTypeLabel = legacyLabelMap({
  flat_fee: "Flat fee",
  revenue_share: "Revenue share",
  profit_share: "Profit share",
});

export const referralProgramStatusLabel = legacyLabelMap({
  active: "Active",
  deactivated: "Deactivated",
});

// ---------------------------------------------------------------------------
// Subscriptions (Stripe mirror — Stripe's own vocabulary)

export const subscriptionStatusLabel = legacyLabelMap({
  active: "Active",
  trialing: "Trialing",
  past_due: "Past due",
  canceled: "Canceled",
  unpaid: "Unpaid",
  incomplete: "Incomplete",
  incomplete_expired: "Incomplete (expired)",
  paused: "Paused",
});

export const planIntervalLabel = legacyLabelMap({ month: "Monthly", year: "Yearly" });

// ---------------------------------------------------------------------------
// Webhooks — the event-type catalogue, held BY REFERENCE (#464). The registry
// names this file as the console's consumer of `webhook_event_type`, so the
// list is the generated one under its existing export name (the
// `TASK_STATUSES` shape); the WORDS are bound where they render, in
// `features/webhooks/lib/event-type-label.ts` from the locale catalogue. The
// humaniser that split a name on the dot and title-cased both halves is
// deleted with its ledger entry: a subscriber's picker and the delivery
// table now show the words UBB authored for each of the 37, never a guess.

export const WEBHOOK_EVENT_TYPES = WEBHOOK_EVENT_TYPE_VALUES;
