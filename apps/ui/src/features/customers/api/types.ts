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
export type RevenueProfileOut = MarginSchemas["RevenueProfileOut"];
export type RevenueProfileIn = MarginSchemas["RevenueProfileIn"];
export type RevenueModeOut = MarginSchemas["RevenueModeOut"];
export type BusinessMarginOut = MarginSchemas["BusinessMarginOut"];
export type SeatMarginOut = MarginSchemas["SeatMarginOut"];
export type BusinessMarginTotals = MarginSchemas["BusinessMarginTotals"];
export type PeriodWindow = MarginSchemas["PeriodWindow"];

// ---------------------------------------------------------------------------
// Platform (create customer)

export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type CustomerResponse = PlatformSchemas["CustomerResponse"];

// ---------------------------------------------------------------------------
// Billing (wallet, grants, budget, profile)

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
export type PreCheckResponse = BillingSchemas["PreCheckResponse"];
export type BudgetConfigIn = BillingSchemas["BudgetConfigIn"];
export type BudgetConfigOut = BillingSchemas["BudgetConfigOut"];
export type BudgetStatusOut = BillingSchemas["BudgetStatusOut"];
export type CustomerBillingProfileIn = BillingSchemas["CustomerBillingProfileIn"];
export type CustomerBillingProfileOut = BillingSchemas["CustomerBillingProfileOut"];
export type ConfigureAutoTopUpRequest = BillingSchemas["ConfigureAutoTopUpRequest"];
export type StatusResponse = BillingSchemas["StatusResponse"];
export type UsageInvoiceOut = BillingSchemas["UsageInvoiceOut"];

// ---------------------------------------------------------------------------
// Metering (usage analytics + pricing)

export type UsageAnalyticsResponse = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseriesResponse = MeteringSchemas["UsageTimeseriesResponse"];
export type TenantMarkupIn = MeteringSchemas["TenantMarkupIn"];
export type TenantMarkupOut = MeteringSchemas["TenantMarkupOut"];
export type BookOut = MeteringSchemas["BookOut"];
export type PastLimitReportResponse = MeteringSchemas["PastLimitReportResponse"];

// ---------------------------------------------------------------------------
// Subscriptions

export type StripeSubscriptionOut = SubscriptionSchemas["StripeSubscriptionOut"];
export type SubscriptionInvoiceOut = SubscriptionSchemas["SubscriptionInvoiceOut"];
export type SubscribeIn = SubscriptionSchemas["SubscribeIn"];

// ---------------------------------------------------------------------------
// Local interfaces for the contract's UNTYPED bodies.
// [backend-verified shape — see discovery spec]

/** One bucket of GET /metering/analytics/usage/timeseries `series[]`. */
export interface TimeseriesPoint {
  bucket: string;
  provider_cost_micros: number;
  billed_cost_micros: number;
  markup_micros: number;
  event_count: number;
  dimension?: string;
}

/** One itemized event inside a past-limit episode. */
export interface PastLimitEpisodeEvent {
  event_id: string;
  effective_at: string;
  billed_cost_micros: number;
  provider_cost_micros: number;
  arrived_after: boolean;
}

/** One episode row of the past-limit report (soft-floor rows carry no events). */
export interface PastLimitEpisode {
  family: string;
  limit: string | null;
  stop_scope: string;
  episode_seq: number | null;
  task_id: string | null;
  subtask_id: string | null;
  provider_cost_limit_micros: number | null;
  tripped_at: string | null;
  resumed_at: string | null;
  events: PastLimitEpisodeEvent[];
  event_count: number;
  total_billed_cost_micros: number;
  total_provider_cost_micros: number;
}

export interface PastLimitLimitTotals {
  billed_cost_micros: number;
  provider_cost_micros: number;
  event_count: number;
}

/** The whole past-limit report, with episodes/totals narrowed. */
export interface PastLimitReport {
  customer_id: string;
  billing_owner_id: string;
  since: string | null;
  until: string | null;
  episodes: PastLimitEpisode[];
  totals_per_limit: Record<string, PastLimitLimitTotals>;
}

/** POST /metering/pricing/customers/{id}/rate-card answers `{assigned}`. */
export interface AssignRateCardResult {
  assigned: string;
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
function strOrNull(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}
function numOrNull(value: unknown): number | null {
  return typeof value === "number" ? value : null;
}
function asRecord(value: unknown): Record<string, unknown> {
  return typeof value === "object" && value !== null
    ? (value as Record<string, unknown>)
    : {};
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
    ...(typeof row.dimension === "string" ? { dimension: row.dimension } : {}),
  }));
}

function narrowEpisode(raw: Record<string, unknown>): PastLimitEpisode {
  const events = Array.isArray(raw.events) ? raw.events : [];
  return {
    family: str(raw.family),
    limit: strOrNull(raw.limit),
    stop_scope: str(raw.stop_scope),
    episode_seq: numOrNull(raw.episode_seq),
    task_id: strOrNull(raw.task_id),
    subtask_id: strOrNull(raw.subtask_id),
    provider_cost_limit_micros: numOrNull(raw.provider_cost_limit_micros),
    tripped_at: strOrNull(raw.tripped_at),
    resumed_at: strOrNull(raw.resumed_at),
    events: events.map((entry) => {
      const record = asRecord(entry);
      return {
        event_id: str(record.event_id),
        effective_at: str(record.effective_at),
        billed_cost_micros: num(record.billed_cost_micros),
        provider_cost_micros: num(record.provider_cost_micros),
        arrived_after: record.arrived_after === true,
      };
    }),
    event_count: num(raw.event_count),
    total_billed_cost_micros: num(raw.total_billed_cost_micros),
    total_provider_cost_micros: num(raw.total_provider_cost_micros),
  };
}

export function narrowPastLimitReport(
  raw: PastLimitReportResponse,
): PastLimitReport {
  const totals: Record<string, PastLimitLimitTotals> = {};
  for (const [limit, value] of Object.entries(raw.totals_per_limit)) {
    const record = asRecord(value);
    totals[limit] = {
      billed_cost_micros: num(record.billed_cost_micros),
      provider_cost_micros: num(record.provider_cost_micros),
      event_count: num(record.event_count),
    };
  }
  return {
    customer_id: raw.customer_id,
    billing_owner_id: raw.billing_owner_id,
    since: raw.since ?? null,
    until: raw.until ?? null,
    episodes: raw.episodes.map(narrowEpisode),
    totals_per_limit: totals,
  };
}

export function narrowAssignResult(
  raw: Record<string, unknown>,
): AssignRateCardResult {
  return { assigned: str(raw.assigned) };
}
