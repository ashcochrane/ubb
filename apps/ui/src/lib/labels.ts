// THE LEGACY LABEL ADAPTER — every export below is a migration debt (#210).
//
// This module used to be the console's whole labelling layer, and ADR-0008 §4
// retired the idea it rests on. It hand-writes twenty-nine value maps and falls
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
  COSTING_METHOD_VALUES,
  COSTING_STATUS_VALUES,
  TENANT_PRODUCT_VALUES,
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

export const preCheckReasonLabel = legacyLabelMap({
  insufficient_funds: "Insufficient funds",
  account_closed: "Account closed",
  customer_stopped: "Customer is stopped",
  rate_limit_exceeded: "Rate limit exceeded",
  soft_floor_reached: "Soft floor reached",
  budget_exceeded: "Budget exceeded",
  budget_unavailable: "Budget state unavailable",
  parent_task_not_active: "Parent task not active",
  subtask_depth_exceeded: "Subtask depth exceeded",
  concurrency_limit: "Concurrency limit reached",
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
// ⚠ THE VALUES MOVED IN #366 AND THE EXPORT NAME DELIBERATELY DID NOT.
// The keys are the rate's ratified arithmetic shapes now, because this
// feature both renders and SENDS them and a console still saying `flat`
// would post a value the API refuses. The symbol keeps its old spelling
// because `gates/migration-ledger.yaml`'s G6 entry addresses this map BY
// EXPORT NAME, and the ledger's ratchet keys on that address — so renaming
// it here reads as an entry ADDED and costs a seeding authorisation for a
// symbol the ticket that pays the entry deletes outright. That ticket
// replaces the whole thing with `labelMap(RATE_STRUCTURE_LABEL_KEYS)` off
// the locale catalogue, which already carries this exact wording.
export const pricingModelLabel = legacyLabelMap({
  per_unit: "Per unit",
  fixed_component: "Fixed component",
});

export const stopScopeLabel = legacyLabelMap({
  task: "Task",
  subtask: "Subtask",
  customer: "Customer",
});

export const stopReasonLabel = legacyLabelMap({
  task_limit: "Task limit reached",
  subtask_limit: "Subtask limit reached",
  customer_floor: "Customer balance floor",
  task_not_active: "Task not active",
  customer_wide_stop: "Customer-wide stop",
  stale: "Stale task",
  stale_max_age: "Task exceeded max age",
  parent_killed: "Parent task killed",
  suspended: "Customer suspended",
});

export const ingestRejectionLabel = legacyLabelMap({
  billing_period_closed: "Billing period closed",
  effective_at_in_future: "Timestamp in the future",
  effective_at_naive: "Timestamp missing timezone",
  effective_at_too_old: "Timestamp too old",
  not_found: "Unknown customer or task",
  validation_error: "Validation failed",
});

export const taskStatusLabel = legacyLabelMap({
  active: "Active",
  completed: "Completed",
  failed: "Failed",
  killed: "Killed",
});

export const pastLimitFamilyLabel = legacyLabelMap({
  floor_stop: "Balance floor stop",
  soft_floor: "Soft floor",
  task: "Task limit",
});

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
// Webhooks — the event-type catalog (35 types; "*" = all events)

export const WEBHOOK_EVENT_TYPES = [
  "auto_top_up.requires_action",
  "budget.threshold_reached",
  "credit_grant.expired",
  "credit_grant.expiring",
  "customer.deleted",
  "customer.suspended",
  "customer.unprofitable",
  "invitation.created",
  "invitation.revoked",
  "member.activated",
  "provider.cost_spike",
  "referral.created",
  "referral.expired",
  "referral.payout_due",
  "referral.reward_earned",
  "refund.requested",
  "sandbox.reset_completed",
  "soft_floor.cleared",
  "soft_floor.crossed",
  "stop.cleared",
  "stop.fired",
  "subtask.limit_exceeded",
  "task.limit_exceeded",
  "tenant.api_key_created",
  "tenant.api_key_revoked",
  "tenant.api_key_rotated",
  "top_up.requested",
  "usage.recorded",
  "usage.refunded",
  "usage_invoice.push_failed_permanent",
  "usage_invoice.pushed",
  "wallet.balance_critical",
  "wallet.balance_low",
  "wallet.balance_overage",
  "withdrawal.requested",
] as const;

/** "wallet.balance_low" → "Wallet — Balance low". */
export function webhookEventTypeLabel(eventType: string): string {
  if (eventType === "*") return "All events";
  const [group, rest] = eventType.split(".", 2);
  if (!rest) return humanize(eventType);
  return `${humanize(group ?? "")} — ${humanize(rest)}`;
}
