import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
  WebhookSchemas,
} from "@/api/types";

// Derived backend shapes — never redeclared.
export type MarginSummary = MarginSchemas["MarginSummaryOut"];
export type RevenueAnalytics = BillingSchemas["RevenueAnalyticsResponse"];
export type UsageAnalytics = MeteringSchemas["UsageAnalyticsResponse"];
export type BudgetConfig = BillingSchemas["BudgetConfigOut"];
export type UnprofitableCustomerRow = MarginSchemas["UnprofitableCustomerRow"];
export type UnprofitableResult = MarginSchemas["UnprofitableOut"];
export type WebhookConfig = WebhookSchemas["WebhookConfigResponse"];

/** UI-only: an ISO date window (YYYY-MM-DD) for the analytics endpoints. */
export interface DateRange {
  start_date: string;
  end_date: string;
}
