// Type aliases from the generated contract, plus local interfaces for the
// handful of responses the schema leaves untyped (additionalProperties: true).

import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
  PlatformSchemas,
  SubscriptionSchemas,
} from "@/api/types";
import { asCostingStatus } from "@/lib/supplier-cost";
import type { CostingStatus } from "@/lib/vocabulary";

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

/**
 * One itemized event inside a past-limit episode.
 *
 * ⚠ `provider_cost_micros` IS NULLABLE ON THE WIRE and this report is UNTYPED
 * in the contract, so nothing but this interface says so. `api/v1/past_limit.py`
 * emits the posting's own column, which has been nullable since #317, and it
 * carries `costing_status` beside it precisely because a `null` there means two
 * different things. Narrowing the amount with the module's `num()` would turn
 * both into `$0.00` — a report about money already spent, telling a tenant their
 * supplier charged nothing for the events that tripped their own spend stop.
 */
export interface PastLimitEpisodeEvent {
  event_id: string;
  effective_at: string;
  /**
   * ⚠ NULLABLE SINCE #351, on exactly the argument above: the column went
   * nullable with a `pricing_status` beside it, so `num()` here would render a
   * price UBB could not resolve as `$0.00` — telling a tenant they charged
   * their customer nothing for an event that tripped their own spend stop.
   *
   * The absence is not yet NAMED on this surface, and that is the split #317
   * and #330 already made once for the supplier half: this ticket stops the
   * zero, and the console consumer that says WHICH of the three absences it is
   * (`unknown`, `waived`, `not_applicable`) is the pricing feature's.
   */
  billed_cost_micros: number | null;
  provider_cost_micros: number | null;
  /** `null` where the row carried no status — see `asCostingStatus`. */
  costing_status: CostingStatus | null;
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
  /**
   * How many of this episode's events carry a cost UBB never learned (#328).
   *
   * Present on the wire since #328 and invisible to any schema-derived scan,
   * because the whole report is `additionalProperties: true` — which is how
   * this surface came to be read as one with no completeness at all.
   */
  unresolved_event_count: number;
  /**
   * And how many carry a customer price UBB could not resolve (#351).
   *
   * The same invisibility applies: the report is `additionalProperties: true`,
   * so nothing schema-derived can see this field arrive or leave.
   */
  unpriced_event_count: number;
}

export interface PastLimitLimitTotals {
  billed_cost_micros: number;
  unpriced_event_count: number;
  provider_cost_micros: number;
  unresolved_event_count: number;
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
    unresolved_event_count: num(row.unresolved_event_count),
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
        // `numOrNull`, NOT `num`, on BOTH amounts: an absent amount stays
        // absent all the way to the cell that renders it (#330, #351). See the
        // interface above.
        billed_cost_micros: numOrNull(record.billed_cost_micros),
        provider_cost_micros: numOrNull(record.provider_cost_micros),
        costing_status: asCostingStatus(record.costing_status),
        arrived_after: record.arrived_after === true,
      };
    }),
    event_count: num(raw.event_count),
    total_billed_cost_micros: num(raw.total_billed_cost_micros),
    total_provider_cost_micros: num(raw.total_provider_cost_micros),
    unresolved_event_count: num(raw.unresolved_event_count),
    unpriced_event_count: num(raw.unpriced_event_count),
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
      unpriced_event_count: num(record.unpriced_event_count),
      provider_cost_micros: num(record.provider_cost_micros),
      unresolved_event_count: num(record.unresolved_event_count),
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
