// src/features/billing/api/types.ts
//
// Tenant-level billing + invoices. Aliases only — never redeclare backend shapes.
import type { BillingSchemas, TenantSchemas } from "@/api/types";

// billing namespace (/api/v1/billing)
export type BudgetConfig = BillingSchemas["BudgetConfigOut"];
export type BudgetConfigIn = BillingSchemas["BudgetConfigIn"];
export type PostpaidConfig = BillingSchemas["PostpaidConfigOut"];
export type PostpaidConfigIn = BillingSchemas["PostpaidConfigIn"];
export type RevenueAnalytics = BillingSchemas["RevenueAnalyticsResponse"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];
export type PreCheckRequest = BillingSchemas["PreCheckRequest"];
export type PreCheckResponse = BillingSchemas["PreCheckResponse"];
export type TenantUsageInvoice = BillingSchemas["TenantUsageInvoiceOut"];

// tenant namespace (/api/v1/tenant)
export type TenantInvoice = TenantSchemas["TenantInvoiceOut"];
export type TenantBillingPeriod = TenantSchemas["TenantBillingPeriodOut"];

/** A start/end date window for the revenue analytics query. */
export interface DateRange {
  start_date?: string;
  end_date?: string;
}
