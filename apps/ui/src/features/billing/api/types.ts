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
  };
}
