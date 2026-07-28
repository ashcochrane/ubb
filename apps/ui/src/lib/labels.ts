// Human-readable labels for the API's categorical fields.
//
// The contract deliberately has NO closed enums (ADR-003 "open enums"): every
// status/kind/mode is an open string, and new values may appear without a
// schema change. Every lookup here therefore falls back to a humanised form
// of the raw value — never render a raw snake_case/UPPER_SNAKE token, and
// never assume the value sets below are exhaustive.

/** "failed_permanent" → "Failed permanent", "TOP_UP" → "Top up". */
export function humanize(value: string): string {
  if (!value) return "—";
  const spaced = value.replace(/[_-]+/g, " ").trim().toLowerCase();
  return spaced.charAt(0).toUpperCase() + spaced.slice(1);
}

function label(map: Record<string, string>) {
  return (value: string | null | undefined): string => {
    if (value === null || value === undefined || value === "") return "—";
    return map[value] ?? humanize(value);
  };
}

// ---------------------------------------------------------------------------
// Tenant / workspace

export const BILLING_MODES = ["meter_only", "prepaid", "postpaid"] as const;
export type BillingMode = (typeof BILLING_MODES)[number];

export const billingModeLabel = label({
  meter_only: "Meter only",
  prepaid: "Prepaid credits",
  postpaid: "Postpaid",
});

export const billingModeDescription = label({
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

export const productLabel = label({
  metering: "Metering",
  billing: "Billing",
  subscriptions: "Subscriptions",
  referrals: "Referrals",
  metering_async: "Async ingestion",
});

export const productDescription = label({
  metering: "Usage events, pricing, analytics, and the audit trail.",
  billing: "Wallets, credit grants, budgets, invoices, and spend control.",
  subscriptions: "Stripe subscription mirror, plans, and seat management.",
  referrals: "Referral programs, attribution, rewards, and payouts.",
  metering_async: "High-throughput asynchronous event ingestion lane.",
});

export const enforcementModeLabel = label({
  off: "Off",
  enforcing: "Enforcing",
});

// ---------------------------------------------------------------------------
// Team

export const roleLabel = label({ admin: "Admin", write: "Write", read: "Read" });
export const ROLES = ["read", "write", "admin"] as const;
export type Role = (typeof ROLES)[number];

/** Rank a role for floor comparisons; unknown roles rank lowest (fail closed). */
export function roleRank(role: string | null | undefined): number {
  return role === "admin" ? 2 : role === "write" ? 1 : role === "read" ? 0 : -1;
}

export const memberStatusLabel = label({ pending: "Pending", active: "Active" });
export const invitationStatusLabel = label({
  pending: "Pending",
  accepted: "Accepted",
  revoked: "Revoked",
});

// ---------------------------------------------------------------------------
// Billing / wallet

export const transactionTypeLabel = label({
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

export const grantKindLabel = label({ paid: "Paid", promo: "Promo" });
export const grantStatusLabel = label({
  active: "Active",
  depleted: "Depleted",
  expired: "Expired",
  voided: "Voided",
});
export const grantSourceLabel = label({
  checkout: "Checkout",
  auto_topup: "Auto top-up",
  api: "API",
  other: "Other",
});

export const usageInvoiceStatusLabel = label({
  pending: "Pending",
  pushing: "Pushing",
  pushed: "Pushed",
  skipped: "Skipped",
  failed: "Failed",
  failed_permanent: "Failed permanently",
});

export const tenantInvoiceStatusLabel = label({
  draft: "Draft",
  finalized: "Finalized",
  paid: "Paid",
  void: "Void",
  uncollectible: "Uncollectible",
});

export const billingPeriodStatusLabel = label({
  open: "Open",
  closed: "Closed",
  invoicing: "Invoicing",
  invoiced: "Invoiced",
});

export const budgetEnforceModeLabel = label({
  alert_only: "Alert only",
  blocking: "Blocking",
});

export const preCheckReasonLabel = label({
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

export const cardTypeLabel = label({ cost: "Cost card", price: "Price card" });
export const pricingModelLabel = label({ per_unit: "Per unit", flat: "Flat" });

export const stopScopeLabel = label({
  task: "Task",
  subtask: "Subtask",
  customer: "Customer",
});

export const stopReasonLabel = label({
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

export const ingestRejectionLabel = label({
  billing_period_closed: "Billing period closed",
  effective_at_in_future: "Timestamp in the future",
  effective_at_naive: "Timestamp missing timezone",
  effective_at_too_old: "Timestamp too old",
  not_found: "Unknown customer or task",
  pricing_error: "Pricing failed",
  validation_error: "Validation failed",
});

export const ingestModeLabel = label({
  async: "Async",
  sync_fallback: "Sync fallback",
});

export const taskStatusLabel = label({
  active: "Active",
  completed: "Completed",
  failed: "Failed",
  killed: "Killed",
});

export const pastLimitFamilyLabel = label({
  floor_stop: "Balance floor stop",
  soft_floor: "Soft floor",
  task: "Task limit",
});

export const revenueModeLabel = label({
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

export const dimensionLabel = label({
  provider: "Provider",
  event_type: "Event type",
  customer: "Customer",
  dim1: "Dimension 1",
  dim2: "Dimension 2",
  dim3: "Dimension 3",
});

// ---------------------------------------------------------------------------
// Audit

export const actorKindLabel = label({
  member: "Team member",
  api_key: "API key",
  operator: "UBB operator",
  end_customer: "End customer",
  system: "System",
});

// ---------------------------------------------------------------------------
// Referrals

export const rewardTypeLabel = label({
  flat_fee: "Flat fee",
  revenue_share: "Revenue share",
  profit_share: "Profit share",
});

export const referralProgramStatusLabel = label({
  active: "Active",
  deactivated: "Deactivated",
});

// ---------------------------------------------------------------------------
// Subscriptions (Stripe mirror — Stripe's own vocabulary)

export const subscriptionStatusLabel = label({
  active: "Active",
  trialing: "Trialing",
  past_due: "Past due",
  canceled: "Canceled",
  unpaid: "Unpaid",
  incomplete: "Incomplete",
  incomplete_expired: "Incomplete (expired)",
  paused: "Paused",
});

export const planIntervalLabel = label({ month: "Monthly", year: "Yearly" });

// ---------------------------------------------------------------------------
// Webhooks — the event-type catalog (35 types; "*" = all events)

export const WEBHOOK_EVENT_TYPES = [
  "auto_topup.requires_action",
  "billing.balance_critical",
  "billing.balance_low",
  "billing.balance_overage",
  "billing.credit_grant_expired",
  "billing.credit_grant_expiring",
  "billing.customer_suspended",
  "billing.topup_requested",
  "billing.withdrawal_requested",
  "budget.threshold_reached",
  "customer.deleted",
  "invitation.created",
  "invitation.revoked",
  "margin.customer_unprofitable",
  "margin.provider_cost_spike",
  "member.activated",
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
  "usage.invoice_push_failed_permanent",
  "usage.invoice_pushed",
  "usage.recorded",
  "usage.refunded",
] as const;

/** "billing.balance_low" → "Billing — Balance low". */
export function webhookEventTypeLabel(eventType: string): string {
  if (eventType === "*") return "All events";
  const [group, rest] = eventType.split(".", 2);
  if (!rest) return humanize(eventType);
  return `${humanize(group ?? "")} — ${humanize(rest)}`;
}
