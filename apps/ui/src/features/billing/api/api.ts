// Real API calls for the billing feature. Every call goes through `unwrap`
// so failures always reject with a typed ApiProblem.

import { billingApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import type {
  BudgetConfig,
  BudgetConfigIn,
  CreditRequest,
  DebitCreditResponse,
  DebitRequest,
  PostpaidConfig,
  PostpaidConfigIn,
  RevenueAnalyticsResponse,
  TenantUsageInvoicePage,
} from "./types";

export async function getRevenueAnalytics(range: {
  start_date?: string;
  end_date?: string;
}): Promise<RevenueAnalyticsResponse> {
  return unwrap(
    await billingApi.GET("/analytics/revenue", {
      params: { query: { start_date: range.start_date, end_date: range.end_date } },
    }),
  );
}

export async function getTenantBudget(): Promise<BudgetConfig> {
  return unwrap(await billingApi.GET("/budget"));
}

/** PUT /billing/budget is a FULL upsert — always send every field. */
export async function putTenantBudget(body: BudgetConfigIn): Promise<BudgetConfig> {
  return unwrap(await billingApi.PUT("/budget", { body }));
}

export async function listTenantUsageInvoices(options: {
  period?: string;
  cursor?: string;
}): Promise<TenantUsageInvoicePage> {
  return unwrap(
    await billingApi.GET("/tenant/usage-invoices", {
      params: { query: { period: options.period, cursor: options.cursor } },
    }),
  );
}

export async function getPostpaidConfig(): Promise<PostpaidConfig> {
  return unwrap(await billingApi.GET("/postpaid-config"));
}

/**
 * PUT /billing/postpaid-config is a PARTIAL update: omitted/null fields keep
 * their current value; an explicit "" clears usage_line_item_group_by.
 * Callers build the body via buildPostpaidPayload so only changes are sent.
 */
export async function putPostpaidConfig(body: PostpaidConfigIn): Promise<PostpaidConfig> {
  return unwrap(await billingApi.PUT("/postpaid-config", { body }));
}

/** Body customer_id is the customer's EXTERNAL id, not the UBB UUID. */
export async function creditWallet(body: CreditRequest): Promise<DebitCreditResponse> {
  return unwrap(await billingApi.POST("/credit", { body }));
}

/** Body customer_id is the customer's EXTERNAL id, not the UBB UUID. */
export async function debitWallet(body: DebitRequest): Promise<DebitCreditResponse> {
  return unwrap(await billingApi.POST("/debit", { body }));
}
