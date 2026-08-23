// Real API implementation — every call goes through unwrap so failures reject
// with a typed ApiProblem.
//
// Identifier discipline (the contract's sharpest edge):
// - Path {customer_id} params are always the internal Customer UUID.
// - POST /billing/credit and /billing/debit take the EXTERNAL id in the body.
// - Platform routes (/customers/{external_id}/...) key on the external id.
// - GET /margin/business/{external_id} keys on a business customer's external id.

import {
  billingApi,
  marginApi,
  meteringApi,
  platformApi,
  rootApi,
  subscriptionsApi,
} from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";
import type { DateRange } from "@/lib/date-range";

import {
  narrowPastLimitReport,
  type BalanceResponse,
  type BudgetConfigIn,
  type BudgetConfigOut,
  type BudgetStatusOut,
  type ConfigureAutoTopUpRequest,
  type CreateCustomerRequest,
  type CreateGrantRequest,
  type CreateTopUpRequest,
  type CreditRequest,
  type CustomerBillingProfileIn,
  type CustomerBillingProfileOut,
  type CustomerMarginOut,
  type CustomerResponse,
  type DebitCreditResponse,
  type DebitRequest,
  type GrantOut,
  type MarginListOut,
  type MarginTrendOut,
  type PastLimitReport,
  type PreCheckResponse,
  type RevenueModeOut,
  type RevenueProfileIn,
  type RevenueProfileOut,
  type StatusResponse,
  type StripeSubscriptionOut,
  type SubscribeIn,
  type SubscriptionInvoiceOut,
  type TopUpCheckoutResponse,
  type UsageAnalyticsResponse,
  type UsageInvoiceOut,
  type UsageTimeseriesResponse,
  type WalletTransactionOut,
  type WithdrawRequest,
  type WithdrawResponse,
  type BusinessMarginOut,
} from "./types";

// ---------------------------------------------------------------------------
// Margin

export async function listCustomerMargins(range: DateRange): Promise<MarginListOut> {
  return unwrap(await marginApi.GET("/customers", { params: { query: range } }));
}

export async function getCustomerMargin(
  customerId: string,
  range: DateRange,
): Promise<CustomerMarginOut> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}", {
      params: { path: { customer_id: customerId }, query: range },
    }),
  );
}

export async function getMarginTrend(
  customerId: string,
  periods: number,
): Promise<MarginTrendOut> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}/trend", {
      params: { path: { customer_id: customerId }, query: { periods } },
    }),
  );
}

export async function getRevenueProfile(customerId: string): Promise<RevenueProfileOut> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}/revenue", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function putRevenueProfile(
  customerId: string,
  body: RevenueProfileIn,
): Promise<RevenueProfileOut> {
  return unwrap(
    await marginApi.PUT("/customers/{customer_id}/revenue", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

export async function getRevenueMode(customerId: string): Promise<RevenueModeOut> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}/revenue-mode", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function putRevenueMode(
  customerId: string,
  revenueMode: string,
): Promise<RevenueModeOut> {
  return unwrap(
    await marginApi.PUT("/customers/{customer_id}/revenue-mode", {
      params: { path: { customer_id: customerId } },
      body: { revenue_mode: revenueMode },
    }),
  );
}

export async function getBusinessMargin(
  externalId: string,
  range: DateRange,
): Promise<BusinessMarginOut> {
  return unwrap(
    await marginApi.GET("/business/{external_id}", {
      params: { path: { external_id: externalId }, query: range },
    }),
  );
}

// ---------------------------------------------------------------------------
// Platform — create customer

export async function createCustomer(
  body: CreateCustomerRequest,
): Promise<CustomerResponse> {
  return unwrap(await platformApi.POST("/customers", { body }));
}

// ---------------------------------------------------------------------------
// Metering — usage analytics + past-limit report

export async function getUsageAnalytics(
  customerId: string,
  range: DateRange,
): Promise<UsageAnalyticsResponse> {
  return unwrap(
    await meteringApi.GET("/analytics/usage", {
      params: { query: { ...range, customer_id: customerId } },
    }),
  );
}

export async function getUsageTimeseries(
  customerId: string,
  range: DateRange,
): Promise<UsageTimeseriesResponse> {
  return unwrap(
    await meteringApi.GET("/analytics/usage/timeseries", {
      params: { query: { ...range, customer_id: customerId, granularity: "day" } },
    }),
  );
}

export async function getPastLimitReport(customerId: string): Promise<PastLimitReport> {
  const raw = unwrap(
    await rootApi.GET("/customers/{customer_id}/past-limit-report", {
      params: { path: { customer_id: customerId } },
    }),
  );
  return narrowPastLimitReport(raw);
}

// ---------------------------------------------------------------------------
// Billing — wallet + money movement

export async function getBalance(customerId: string): Promise<BalanceResponse> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/balance", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function createTopUp(
  customerId: string,
  body: CreateTopUpRequest,
): Promise<TopUpCheckoutResponse> {
  return unwrap(
    await billingApi.POST("/customers/{customer_id}/top-up", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

export async function withdraw(
  customerId: string,
  body: WithdrawRequest,
): Promise<WithdrawResponse> {
  return unwrap(
    await billingApi.POST("/customers/{customer_id}/withdraw", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

/** NOTE: body.customer_id is the customer's EXTERNAL id, not the UUID. */
export async function creditWallet(body: CreditRequest): Promise<DebitCreditResponse> {
  return unwrap(await billingApi.POST("/credit", { body }));
}

/** NOTE: body.customer_id is the customer's EXTERNAL id, not the UUID. */
export async function debitWallet(body: DebitRequest): Promise<DebitCreditResponse> {
  return unwrap(await billingApi.POST("/debit", { body }));
}

/** A denial is still HTTP 200 — branch on `allowed`/`reason` in the body. */
export async function preCheck(customerId: string): Promise<PreCheckResponse> {
  return unwrap(
    await billingApi.POST("/pre-check", {
      body: { customer_id: customerId, start_task: false, external_task_id: "" },
    }),
  );
}

export async function listTransactions(
  customerId: string,
  cursor?: string,
): Promise<CursorPage<WalletTransactionOut>> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/transactions", {
      params: { path: { customer_id: customerId }, query: { cursor } },
    }),
  );
}

export async function listGrants(
  customerId: string,
  options: { status?: string; cursor?: string },
): Promise<CursorPage<GrantOut>> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/grants", {
      params: {
        path: { customer_id: customerId },
        query: { status: options.status, cursor: options.cursor },
      },
    }),
  );
}

export async function createGrant(
  customerId: string,
  body: CreateGrantRequest,
): Promise<GrantOut> {
  return unwrap(
    await billingApi.POST("/customers/{customer_id}/grants", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

export async function voidGrant(customerId: string, grantId: string): Promise<GrantOut> {
  return unwrap(
    await billingApi.POST("/customers/{customer_id}/grants/{grant_id}/void", {
      params: { path: { customer_id: customerId, grant_id: grantId } },
    }),
  );
}

// ---------------------------------------------------------------------------
// Billing — budget, profile, auto top-up

export async function getCustomerBudget(customerId: string): Promise<BudgetConfigOut> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/budget", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

/** PUT is a FULL upsert — always send every field (defaults apply to omissions). */
export async function putCustomerBudget(
  customerId: string,
  body: BudgetConfigIn,
): Promise<BudgetConfigOut> {
  return unwrap(
    await billingApi.PUT("/customers/{customer_id}/budget", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

export async function getBudgetStatus(customerId: string): Promise<BudgetStatusOut> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/budget/status", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function getBillingProfile(
  customerId: string,
): Promise<CustomerBillingProfileOut> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/billing-profile", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function putBillingProfile(
  customerId: string,
  body: CustomerBillingProfileIn,
): Promise<CustomerBillingProfileOut> {
  return unwrap(
    await billingApi.PUT("/customers/{customer_id}/billing-profile", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

/** Per-customer usage-invoice (Stripe push) history — one row per period. */
export async function listCustomerUsageInvoices(
  customerId: string,
  cursor?: string,
): Promise<CursorPage<UsageInvoiceOut>> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/usage-invoices", {
      params: { path: { customer_id: customerId }, query: { cursor } },
    }),
  );
}

/** There is NO GET for auto top-up — settings cannot be read back. */
export async function configureAutoTopUp(
  customerId: string,
  body: ConfigureAutoTopUpRequest,
): Promise<StatusResponse> {
  return unwrap(
    await billingApi.PUT("/customers/{customer_id}/auto-top-up", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

// ---------------------------------------------------------------------------
// Metering — pricing
//
// ⚠ THERE IS NOTHING HERE, AND TWO SEPARATE DELETIONS EMPTIED IT.
//
// #368 took the book-assignment read and write: the record that assigned a
// book to a customer is deleted outright, with its route. A customer reaches a
// book through their PLAN, which is where their pricing already resolved from,
// or through a book that carries them, so there is nothing to pick from a list.
//
// #369 took the markup override — a resolved read, a write and a delete over a
// percentage and a per-event flat amount on a configuration row. That record is
// deleted too. What one named customer is charged is now a RULE in their own
// pricing book, which says which quantity it prices — and the surface that
// reads and writes one is the PRICING feature's, not this one's (#372). It is
// composed onto the customer page at the route, because the console's imports
// flow down and one feature never reaches into another's components.

// ---------------------------------------------------------------------------
// Subscriptions (reads key on the UUID; lifecycle verbs key on external_id)

export async function getSubscription(customerId: string): Promise<StripeSubscriptionOut> {
  return unwrap(
    await subscriptionsApi.GET("/customers/{customer_id}/subscription", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function listSubscriptionInvoices(
  customerId: string,
  cursor?: string,
): Promise<CursorPage<SubscriptionInvoiceOut>> {
  return unwrap(
    await subscriptionsApi.GET("/customers/{customer_id}/invoices", {
      params: { path: { customer_id: customerId }, query: { cursor } },
    }),
  );
}

export async function subscribeCustomer(
  externalId: string,
  body: SubscribeIn,
): Promise<Record<string, unknown>> {
  return unwrap(
    await subscriptionsApi.POST("/customers/{external_id}/subscribe", {
      params: { path: { external_id: externalId } },
      body,
    }),
  );
}

export async function cancelSubscription(
  externalId: string,
  atPeriodEnd: boolean,
): Promise<Record<string, unknown>> {
  return unwrap(
    await subscriptionsApi.POST("/customers/{external_id}/subscription/cancel", {
      params: { path: { external_id: externalId } },
      body: { at_period_end: atPeriodEnd },
    }),
  );
}

export async function pauseSubscription(
  externalId: string,
): Promise<Record<string, unknown>> {
  return unwrap(
    await subscriptionsApi.POST("/customers/{external_id}/subscription/pause", {
      params: { path: { external_id: externalId } },
    }),
  );
}

export async function resumeSubscription(
  externalId: string,
): Promise<Record<string, unknown>> {
  return unwrap(
    await subscriptionsApi.POST("/customers/{external_id}/subscription/resume", {
      params: { path: { external_id: externalId } },
    }),
  );
}

export async function setSeats(
  externalId: string,
  seats: number,
): Promise<Record<string, unknown>> {
  return unwrap(
    await subscriptionsApi.POST("/customers/{external_id}/seats", {
      params: { path: { external_id: externalId } },
      body: { seats },
    }),
  );
}
