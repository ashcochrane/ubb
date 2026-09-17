// Dashboard (CFO overview) API shapes.
//
// Typed responses come straight from the generated schema map. The contract
// leaves three surfaces untyped (additionalProperties: true); their concrete
// runtime shapes are backend-verified and hand-typed below, each with a single
// narrowing function — the only place a cast-like assertion may live.
//
// ⚠ **FIVE OF THIS FEATURE'S READS WERE FIVE SEPARATE ROUTES AND ARE NOW ONE
// QUESTION (#501)**: the margin summary, the per-customer margin list, the
// usage report, its timeseries and the billing revenue report. What that
// changed here is the shape of what arrives — a row per bucket per group, each
// carrying one entry per requested MEASURE — so the narrowings below turn one
// answer into the three views this feature has always rendered rather than
// turning four answers into four.
//
// Money stays in integer micros end-to-end; only percentages (display-only)
// use floats.

import type { MeteringSchemas, MarginSchemas, TenantSchemas } from "@/api/types";
import type { UbbAxis } from "@/lib/grouping-axis";
import {
  amountOn,
  axisValueOn,
  completenessOn,
  CUSTOMER_REVENUE,
  eventsOn,
  GROSS_MARGIN,
  marginPercentOf,
  measureOn,
  onlyRow,
  orZero,
  SUPPLIER_COGS,
  type EconomicRow,
  type EconomicsAnswer,
} from "@/lib/economic-query";
import type { DateRange } from "@/lib/date-range";

/** A fully resolved inclusive date window (YYYY-MM-DD, UTC). */
export type Window = Required<DateRange>;

// ---------------------------------------------------------------------------
// Generated (fully typed) responses

export type Economics = EconomicsAnswer;
export type Unprofitable = MarginSchemas["UnprofitableOut"];
export type UnprofitableRow = MarginSchemas["UnprofitableCustomerRow"];
export type ApiKeyList = TenantSchemas["ApiKeyListResponse"];
export type PricingBookList = MeteringSchemas["PaginatedPricingBooks"];

/**
 * The four breakdown axes the overview picker offers.
 *
 * ⚠ THE IDENTIFIER TOOK ITS SLICE'S WORD IN #506, which is what #372 left for
 * it: that commit paid the SENTENCE early to make room under a spread ceiling
 * and said in terms that the identifier moves with its slice. It has.
 *
 * ⚠ **FOUR NAMED AXES AND NOT THE TENANT'S WHOLE LIST, WHICH IS A CHOICE
 * RATHER THAN THE OLD DEFECT.** The group-by picker on the events page reads
 * every axis this tenant declared off the discovery contract, because exploring
 * is what that page is for. The overview is a summary: it offers four axes
 * every workspace has whatever it declares, so the card says the same thing to
 * a tenant that has declared nothing as to one that has declared ten. What made
 * the old list a defect was not that it was short — it was that three of its
 * entries were PHYSICAL SLOTS, offered as axes nobody had declared. Each of
 * these four is a reserved axis the server always answers for, typed against
 * the five UBB words so a fifth cannot be added here without one.
 */
export const BREAKDOWN_AXES = [
  "provider",
  "event_type",
  "task_type",
  "customer",
] as const satisfies readonly UbbAxis[];
export type BreakdownAxis = (typeof BREAKDOWN_AXES)[number];

// ---------------------------------------------------------------------------
// Narrowed views of the one query

/**
 * The window's economics for the whole workspace — the ungrouped, unbucketed
 * answer, which always has exactly one row.
 *
 * ⚠ `gross_margin_micros` IS NULLABLE AND ITS NULL IS NOT A ZERO. A margin UBB
 * cannot state is absent rather than small; the two counts beside it say how
 * far the figures that ARE stated can be off, in opposite directions.
 */
export interface TenantEconomics {
  provider_cost_micros: number;
  total_revenue_micros: number;
  gross_margin_micros: number | null;
  margin_percentage: number;
  unresolved_event_count: number;
  unpriced_event_count: number;
  /** Recorded work in the window. Null where the answer did not ask for it —
   *  a grouped question cannot, because a count across rows that mix Event
   *  Types is the comparison the server refuses to answer. */
  event_count: number | null;
}

/** One customer's row of the same answer, grouped by the customer axis. */
export interface CustomerEconomicsRow extends TenantEconomics {
  /** The customer's identity, which is what that axis groups. */
  customer_id: string;
}

/** One point of the revenue-vs-cost chart, from a day-bucketed answer. */
export interface RevenueCostPoint {
  day: string; // YYYY-MM-DD
  revenue_micros: number;
  provider_micros: number;
  margin_micros: number | null;
  event_count: number;
  /**
   * That day's own uncosted events. It rides the point rather than the chart
   * because the answer is per bucket, and because the point is what the
   * tooltip is handed: a count kept beside the series would caveat every day
   * for one day's missing invoice.
   */
  unresolved_event_count: number;
}

/** One bar of the cost breakdown, from an answer grouped by one axis.
 *
 *  ⚠ NO EVENT COUNT, and `api.ts` carries the reason: a count compared across
 *  rows that mix Event Types is the comparison the server refuses. */
export interface BreakdownRow {
  /** The value of the axis this row is grouped by, or null when unset. */
  group_value: string | null;
  total_provider_cost_micros: number;
  total_revenue_micros: number;
}

/**
 * GET /connect/status — untyped `dict` in the schema.
 * Canonical shape shared by every feature caching ['connect','status']:
 * `account_id` is always a string — the backend field is a CharField
 * defaulting to "" (never null), so a missing/absent id narrows to "".
 */
export interface ConnectStatus {
  account_id: string;
  charges_enabled: boolean;
  onboarded: boolean;
}

function economicsOf(row: EconomicRow | undefined): TenantEconomics {
  const revenue = orZero(amountOn(row, CUSTOMER_REVENUE));
  const margin = amountOn(row, GROSS_MARGIN);
  return {
    provider_cost_micros: orZero(amountOn(row, SUPPLIER_COGS)),
    total_revenue_micros: revenue,
    gross_margin_micros: margin,
    margin_percentage: marginPercentOf(revenue, margin),
    event_count: eventsOn(row),
    ...completenessOn(row),
  };
}

/** The workspace's totals for the window. */
export function toTenantEconomics(answer: Economics): TenantEconomics {
  return economicsOf(onlyRow(answer));
}

/** One row per customer, from an answer grouped by the customer axis. */
export function toCustomerRows(answer: Economics): CustomerEconomicsRow[] {
  return answer.rows.map((row) => ({
    customer_id: axisValueOn(row) ?? "",
    ...economicsOf(row),
  }));
}

/**
 * Chart points from a day-bucketed answer.
 *
 * ⚠ The bucket's opening instant is an ISO datetime and the chart's key is a
 * calendar day, so the day is its first ten characters. A bucketed answer
 * always carries one — a posting's own instant is never absent — which is why
 * this narrows without a fallback.
 */
export function toRevenueCostPoints(answer: Economics): RevenueCostPoint[] {
  return answer.rows.map((row) => ({
    day: (row.bucket_start ?? "").slice(0, 10),
    revenue_micros: orZero(amountOn(row, CUSTOMER_REVENUE)),
    provider_micros: orZero(amountOn(row, SUPPLIER_COGS)),
    margin_micros: amountOn(row, GROSS_MARGIN),
    event_count: orZero(eventsOn(row)),
    unresolved_event_count: completenessOn(row).unresolved_event_count,
  }));
}

/**
 * Breakdown rows from an answer grouped by one axis.
 *
 * ⚠ **A NULL VALUE IS A ROW LIKE ANY OTHER AND MUST NOT BE DROPPED.** The
 * report this replaced bucketed every absence under one `(unattributed)`
 * string; the row now carries `null` with a status saying whether the value was
 * never recorded or whether the question does not apply to those rows. The bar
 * chart renders the absence as a heading either way, and what the two statuses
 * mean is the rendering ticket's to show.
 */
export function toBreakdownRows(answer: Economics): BreakdownRow[] {
  return answer.rows.map((row) => ({
    group_value: axisValueOn(row),
    total_provider_cost_micros: orZero(amountOn(row, SUPPLIER_COGS)),
    total_revenue_micros: orZero(amountOn(row, CUSTOMER_REVENUE)),
  }));
}

/** How many customers the window's usage reached — the row count of the answer
 *  grouped by the customer axis, which is what "customers with usage" meant on
 *  the summary route that published it as a field. */
export function customerCount(answer: Economics): number {
  return answer.rows.length;
}

/** Whether a row states a margin at all — the one thing a caller must ask
 *  before rendering one, and the reason `gross_margin_micros` is nullable. */
export function statesAMargin(row: EconomicRow | undefined): boolean {
  return measureOn(row, GROSS_MARGIN)?.amount_micros != null;
}

/** Narrow the untyped connect-status body ("" sentinel = no account). */
export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  return {
    account_id:
      typeof raw["account_id"] === "string" ? raw["account_id"] : "",
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}
