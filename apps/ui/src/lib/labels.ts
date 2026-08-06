// THE LEGACY LABEL ADAPTER — every export below is a migration debt (#210).
//
// This module used to be the console's whole labelling layer, and ADR-0008 §4
// retired the idea it rests on. It hand-writes thirty-two value maps and falls
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
// This file survives only because it is imported by fifty-one others, and #210
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

export const PRODUCTS = [
  "metering",
  "billing",
  "subscriptions",
  "referrals",
  "metering_async",
] as const;
export type Product = (typeof PRODUCTS)[number];

export const productLabel = legacyLabelMap({
  metering: "Metering",
  billing: "Billing",
  subscriptions: "Subscriptions",
  referrals: "Referrals",
  metering_async: "Async ingestion",
});

export const productDescription = legacyLabelMap({
  metering: "Usage events, pricing, analytics, and the audit trail.",
  billing: "Wallets, credit grants, budgets, invoices, and spend control.",
  subscriptions: "Stripe subscription mirror, plans, and seat management.",
  referrals: "Referral programs, attribution, rewards, and payouts.",
  metering_async: "High-throughput asynchronous event ingestion lane.",
});

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

export const cardTypeLabel = legacyLabelMap({ cost: "Cost card", price: "Price card" });
export const pricingModelLabel = legacyLabelMap({ per_unit: "Per unit", flat: "Flat" });

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
  pricing_error: "Pricing failed",
  validation_error: "Validation failed",
});

export const ingestModeLabel = legacyLabelMap({
  async: "Async",
  sync_fallback: "Sync fallback",
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
