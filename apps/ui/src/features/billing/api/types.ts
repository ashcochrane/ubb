// Type aliases from the generated schema map, plus the one hand-typed shape
// the schema leaves untyped.

import type { BillingSchemas } from "@/api/types";

export type RevenueAnalyticsResponse = BillingSchemas["RevenueAnalyticsResponse"];
export type BudgetConfig = BillingSchemas["BudgetConfigOut"];
export type BudgetConfigIn = BillingSchemas["BudgetConfigIn"];
export type TenantUsageInvoice = BillingSchemas["TenantUsageInvoiceOut"];
export type TenantUsageInvoicePage = BillingSchemas["TenantUsageInvoiceListResponse"];
export type PostpaidConfig = BillingSchemas["PostpaidConfigOut"];
export type PostpaidConfigIn = BillingSchemas["PostpaidConfigIn"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];

// [backend-verified shape — see discovery spec] `RevenueAnalyticsResponse.daily`
// is `array<object additionalProperties: true>` in the schema; the server emits
// one row per day, ordered ascending, with exactly these keys.
export interface RevenueDailyRow {
  /** Calendar day, YYYY-MM-DD. */
  day: string;
  provider_cost_micros: number;
  billed_cost_micros: number;
  event_count: number;
  /**
   * How many of the day's events carry a supplier cost UBB never learned.
   *
   * PER DAY, not per window: an unresolved cost belongs to the day it fell in,
   * and a reader hovering one point has to be told about that point. The server
   * builds it in the same aggregate as the day's cost (`get_revenue_analytics`),
   * so it is present on every row the endpoint emits.
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
 * Narrow one untyped `daily` row to the backend-verified shape. Defensive:
 * missing/mistyped keys degrade to zero values rather than crashing the chart.
 * This is the single place the untyped response is given a shape.
 */
export function toRevenueDailyRow(row: Record<string, unknown>): RevenueDailyRow {
  return {
    day: typeof row.day === "string" ? row.day : "",
    provider_cost_micros:
      typeof row.provider_cost_micros === "number" ? row.provider_cost_micros : 0,
    billed_cost_micros:
      typeof row.billed_cost_micros === "number" ? row.billed_cost_micros : 0,
    event_count: typeof row.event_count === "number" ? row.event_count : 0,
    // Degrading a MISSING count to zero says "this day left nothing out",
    // which is the one claim this field exists to stop the console making by
    // accident. It is safe here only because the server writes it on every row
    // unconditionally and `test_a_cost_total_says_what_it_excluded.py` holds it
    // there; a row without it is a backend regression, not a shape this
    // narrowing should invent an answer for.
    unresolved_event_count:
      typeof row.unresolved_event_count === "number"
        ? row.unresolved_event_count
        : 0,
    // Same degradation and same caveat, one slice on (#351).
    unpriced_event_count:
      typeof row.unpriced_event_count === "number"
        ? row.unpriced_event_count
        : 0,
  };
}
