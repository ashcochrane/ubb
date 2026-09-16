// Type aliases from the generated schema map, plus the narrowed shapes this
// feature reads the one economic query through.
//
// ⚠ **THE REVENUE SECTION READ A ROUTE OF ITS OWN UNTIL #501**, and that route
// was a DUPLICATE: a tenant-wide day series of billed total versus supplier
// cost, which is exactly what the metering timeseries beside it already served,
// under a second definition and a different name for the difference between
// them. One question answers it now, bucketed by day.

import type { BillingSchemas } from "@/api/types";
import {
  amountOn,
  completenessOn,
  CUSTOMER_REVENUE,
  eventsOn,
  GROSS_MARGIN,
  orZero,
  SUPPLIER_COGS,
  type EconomicsAnswer,
} from "@/lib/economic-query";

export type Economics = EconomicsAnswer;
export type CustomerSpendPool = BillingSchemas["CustomerSpendPoolOut"];
export type CustomerSpendPoolIn = BillingSchemas["CustomerSpendPoolIn"];
export type TenantUsageInvoice = BillingSchemas["TenantUsageInvoiceOut"];
export type TenantUsageInvoicePage = BillingSchemas["TenantUsageInvoiceListResponse"];
export type PostpaidConfig = BillingSchemas["PostpaidConfigOut"];
export type PostpaidConfigIn = BillingSchemas["PostpaidConfigIn"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];

/** One day of the revenue chart. */
export interface RevenueDailyRow {
  /** Calendar day, YYYY-MM-DD. */
  day: string;
  provider_cost_micros: number;
  revenue_micros: number;
  event_count: number;
  /**
   * How many of the day's events carry a supplier cost UBB never learned.
   *
   * PER DAY, not per window: an unresolved cost belongs to the day it fell in,
   * and a reader hovering one point has to be told about that point.
   */
  unresolved_event_count: number;
  /**
   * And how many of the day's events carry a customer price UBB could not
   * resolve (#351). Per day for the same reason, and a SECOND field rather
   * than a widened one because the two are about different events: a day can
   * be complete on one side of the margin and a floor on the other.
   */
  unpriced_event_count: number;
}

/**
 * The window's series and its totals.
 *
 * ⚠ **THE TOTALS ARE SUMMED FROM THE DAYS, AND THAT IS ARITHMETIC RATHER THAN
 * A SECOND DEFINITION.** Each bucket is a real total over the postings that
 * fell in it, and the window is the buckets — which is how the server builds
 * its own ungrouped answer. What must NOT be summed is a margin with a day
 * missing from it: a single day UBB cannot state a margin for makes the
 * window's margin unstateable too, so the sum carries the absence rather than
 * skipping the day.
 */
export interface RevenueWindow {
  daily: RevenueDailyRow[];
  revenue_micros: number;
  provider_cost_micros: number;
  margin_micros: number | null;
  unresolved_event_count: number;
  unpriced_event_count: number;
  event_count: number;
}

export function toRevenueWindow(answer: Economics): RevenueWindow {
  const daily: RevenueDailyRow[] = answer.rows.map((row) => ({
    day: (row.bucket_start ?? "").slice(0, 10),
    provider_cost_micros: orZero(amountOn(row, SUPPLIER_COGS)),
    revenue_micros: orZero(amountOn(row, CUSTOMER_REVENUE)),
    event_count: orZero(eventsOn(row)),
    ...completenessOn(row),
  }));
  const stated = answer.rows.map((row) => amountOn(row, GROSS_MARGIN));
  return {
    daily,
    revenue_micros: daily.reduce((sum, row) => sum + row.revenue_micros, 0),
    provider_cost_micros: daily.reduce(
      (sum, row) => sum + row.provider_cost_micros, 0),
    margin_micros: stated.some((amount) => amount === null)
      ? null
      : stated.reduce((sum: number, amount) => sum + (amount ?? 0), 0),
    unresolved_event_count: daily.reduce(
      (sum, row) => sum + row.unresolved_event_count, 0),
    unpriced_event_count: daily.reduce(
      (sum, row) => sum + row.unpriced_event_count, 0),
    event_count: daily.reduce((sum, row) => sum + row.event_count, 0),
  };
}
