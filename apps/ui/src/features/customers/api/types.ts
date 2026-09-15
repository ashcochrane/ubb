// Type aliases from the generated contract, plus local interfaces for the
// handful of responses the schema leaves untyped (additionalProperties: true).

import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
  PlatformSchemas,
  SubscriptionSchemas,
} from "@/api/types";

// ---------------------------------------------------------------------------
// Margin (list + detail workbench overview)

export type CustomerMarginListRow = MarginSchemas["CustomerMarginListRow"];
export type MarginListOut = MarginSchemas["MarginListOut"];
export type CustomerMarginOut = MarginSchemas["CustomerMarginOut"];
export type MarginTrendOut = MarginSchemas["MarginTrendOut"];
export type MarginTrendPointOut = MarginSchemas["MarginTrendPointOut"];
export type BusinessMarginOut = MarginSchemas["BusinessMarginOut"];
export type SeatMarginOut = MarginSchemas["SeatMarginOut"];
export type BusinessMarginTotals = MarginSchemas["BusinessMarginTotals"];
export type PeriodWindow = MarginSchemas["PeriodWindow"];

// ---------------------------------------------------------------------------
// Platform (create customer)

export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type CustomerResponse = PlatformSchemas["CustomerResponse"];

// ---------------------------------------------------------------------------
// Billing (wallet, grants, customer spend pool, wallet policy)

export type BalanceResponse = BillingSchemas["BalanceResponse"];
export type WalletTransactionOut = BillingSchemas["WalletTransactionOut"];
export type GrantOut = BillingSchemas["GrantOut"];
export type CreateGrantRequest = BillingSchemas["CreateGrantRequest"];
export type CreateTopUpRequest = BillingSchemas["CreateTopUpRequest"];
export type TopUpCheckoutResponse = BillingSchemas["TopUpCheckoutResponse"];
export type WithdrawRequest = BillingSchemas["WithdrawRequest"];
export type WithdrawResponse = BillingSchemas["WithdrawResponse"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];
export type AffordabilityResponse = BillingSchemas["AffordabilityResponse"];
export type CustomerSpendPoolIn = BillingSchemas["CustomerSpendPoolIn"];
export type CustomerSpendPoolOut = BillingSchemas["CustomerSpendPoolOut"];
export type CustomerSpendPoolStatusOut = BillingSchemas["CustomerSpendPoolStatusOut"];
export type CustomerBillingProfileIn = BillingSchemas["CustomerBillingProfileIn"];
export type CustomerBillingProfileOut = BillingSchemas["CustomerBillingProfileOut"];
export type ConfigureAutoTopUpRequest = BillingSchemas["ConfigureAutoTopUpRequest"];
export type StatusResponse = BillingSchemas["StatusResponse"];
export type UsageInvoiceOut = BillingSchemas["UsageInvoiceOut"];

// ---------------------------------------------------------------------------
// Metering (usage analytics + pricing)

export type UsageAnalyticsResponse = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseriesResponse = MeteringSchemas["UsageTimeseriesResponse"];

// ---------------------------------------------------------------------------
// Subscriptions

export type StripeSubscriptionOut = SubscriptionSchemas["StripeSubscriptionOut"];
export type SubscriptionInvoiceOut = SubscriptionSchemas["SubscriptionInvoiceOut"];
export type SubscribeIn = SubscriptionSchemas["SubscribeIn"];

// ---------------------------------------------------------------------------
// Local interfaces for the contract's UNTYPED bodies.
// [backend-verified shape — see discovery spec]

/**
 * One bucket of GET /metering/analytics/usage/timeseries `series[]`.
 *
 * No grouped-value field: this feature never sends `group_by` (see
 * `usage-tab.tsx`), so the backend never emits one, and the chart plots only
 * bucket and the two costs. The optional field this carried was narrowed but
 * read by nothing.
 */
export interface TimeseriesPoint {
  bucket: string;
  provider_cost_micros: number;
  billed_cost_micros: number;
  markup_micros: number;
  event_count: number;
  /** This bucket's own uncosted events — the server answers it per bucket. */
  unresolved_event_count: number;
}

// ---------------------------------------------------------------------------
// Narrowing — field-by-field coercion of the untyped bodies above. This is
// the ONLY place a cast-like assertion may live for these shapes; everything
// is rebuilt with typeof guards (unknown fields default safely).

function num(value: unknown): number {
  return typeof value === "number" ? value : 0;
}
function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

export function narrowTimeseriesPoints(
  rows: Record<string, unknown>[],
): TimeseriesPoint[] {
  return rows.map((row) => ({
    bucket: str(row.bucket),
    provider_cost_micros: num(row.provider_cost_micros),
    billed_cost_micros: num(row.billed_cost_micros),
    markup_micros: num(row.markup_micros),
    event_count: num(row.event_count),
    unresolved_event_count: num(row.unresolved_event_count),
  }));
}

// ⚠ `narrowPastLimitReport` AND THE FOUR SHAPES IT NARROWED ARE DELETED (#466).
// They narrowed the untyped body of the per-customer report of what was spent
// past a stop; that route, its module and its schema are gone, and the
// customer's Usage tab hosts Stops and breaches — typed rows, injected by the
// route from the spend-controls feature — in the section's place.

// ⚠ `narrowAssignResult` AND `AssignRateCardResult` ARE DELETED (#368).
// They narrowed the untyped body of the route that assigned a book to a
// customer; that record and its route are gone, and a customer's book
// comes from their plan.
