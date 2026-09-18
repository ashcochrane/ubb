// Real API calls for the billing feature. Every call goes through `unwrap`
// so failures always reject with a typed ApiProblem.

import { billingApi, meteringApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import { EVERY_MEASURE } from "@/lib/economic-query";

import type {
  CustomerSpendPool,
  CustomerSpendPoolIn,
  CreditRequest,
  DebitCreditResponse,
  DebitRequest,
  PostpaidConfig,
  PostpaidConfigIn,
  Economics,
  TenantUsageInvoicePage,
} from "./types";

/** The window's revenue and cost, day by day.
 *
 *  ⚠ ON THE METERING PREFIX, because that is where the postings both figures
 *  are read from live. The billing route this replaced was a second definition
 *  of the same two numbers over the same rows (#501). */
export async function getRevenueWindow(range: {
  start_date?: string;
  end_date?: string;
}): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          start_date: range.start_date,
          end_date: range.end_date,
          measures: [...EVERY_MEASURE],
          bucket: "day",
        },
      },
    }),
  );
}

export async function getTenantCustomerSpendPool(): Promise<CustomerSpendPool> {
  return unwrap(await billingApi.GET("/customer-spend-pool"));
}

/** PUT /billing/customer-spend-pool is a FULL upsert — always send every field. */
export async function putTenantCustomerSpendPool(body: CustomerSpendPoolIn): Promise<CustomerSpendPool> {
  return unwrap(await billingApi.PUT("/customer-spend-pool", { body }));
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
 * their current value; an explicit "" clears group_by.
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
