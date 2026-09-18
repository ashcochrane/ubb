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
  subscriptionsApi,
} from "@/api/client";
import type { CursorPage } from "@/api/pagination";
import { unwrap } from "@/api/problem";
import {
  EVERY_MEASURE,
  FIELD_AXIS,
  MONEY_MEASURES,
} from "@/lib/economic-query";
import type { DateRange } from "@/lib/date-range";
import type { RevenueBasis } from "@/lib/vocabulary";

import {
  type BalanceResponse,
  type CustomerSpendPoolIn,
  type CustomerSpendPoolOut,
  type CustomerSpendPoolStatusOut,
  type ConfigureAutoTopUpRequest,
  type CreateCustomerRequest,
  type CustomerIdentity,
  type CreateGrantRequest,
  type CreateTopUpRequest,
  type CreditRequest,
  type CustomerBillingProfileIn,
  type CustomerBillingProfileOut,
  type Economics,
  type CustomerResponse,
  type DebitCreditResponse,
  type DebitRequest,
  type GrantOut,
  type AffordabilityResponse,
  type StatusResponse,
  type StripeSubscriptionOut,
  type SubscribeIn,
  type SubscriptionInvoiceOut,
  type TopUpCheckoutResponse,
  type UsageInvoiceOut,
  type WalletTransactionOut,
  type WithdrawRequest,
  type WithdrawResponse,
  type BusinessMarginOut,
  type SuppliedRevenueIn,
  type SuppliedRevenueRecord,
  type SuppliedRevenueWindow,
} from "./types";

// ---------------------------------------------------------------------------
// Margin

export async function listCustomerMargins(range: DateRange): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          ...range,
          measures: [...MONEY_MEASURES],
          group_by: [FIELD_AXIS("customer")],
        },
      },
    }),
  );
}

export async function getCustomerMargin(
  customerId: string,
  range: DateRange,
): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          ...range,
          customer_id: customerId,
          measures: [...EVERY_MEASURE],
        },
      },
    }),
  );
}

/**
 * The customer's margin month by month.
 *
 * ⚠ **A WINDOW THIS CONSOLE COMPUTES, WHERE IT USED TO BE A COUNT THE SERVER
 * TOOK.** The trend route read N stored monthly snapshots; the one query
 * derives each month from the facts as they stand, so what it takes is a
 * window and a bucket. Twelve months is the most it can answer in one request,
 * because a computed report is bounded at 366 days — and that is a real
 * narrowing from the thirty-six the snapshot route would serve.
 */
export async function getMarginTrend(
  customerId: string,
  periods: number,
): Promise<Economics> {
  const months = Math.max(1, Math.min(periods, 12));
  const today = new Date();
  const start = new Date(
    Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - (months - 1), 1),
  );
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          start_date: start.toISOString().slice(0, 10),
          end_date: today.toISOString().slice(0, 10),
          customer_id: customerId,
          measures: [...MONEY_MEASURES],
          bucket: "month",
        },
      },
    }),
  );
}

// THE RECURRING REVENUE PAIR WAS HERE AND IS GONE (#496, slice 7 section 9).
// It read and wrote one recurring amount per customer - no period, no source,
// and an amount the backend added into the same field as a Stripe
// subscription. Its replacement is the pair directly below.

// ---------------------------------------------------------------------------
// Tenant-supplied revenue (#508, slice 7 section 9)

/**
 * The window's supplied revenue, under a basis the answer NAMES.
 *
 * ⚠ **THE BASIS IS ASKED FOR, NEVER ASSUMED.** `recorded` places each supplied
 * amount whole on the day its period opens and distributes nothing;
 * `recognised` spreads it by the record's own method across the span the record
 * declares. The route will choose for a caller that does not, and then says
 * which it chose — but a surface offering the tenant both views has to send the
 * one it is showing, or the label over the figure is a guess.
 */
export async function getSuppliedRevenue(
  customerId: string,
  range: DateRange,
  basis: RevenueBasis,
): Promise<SuppliedRevenueWindow> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}/supplied-revenue", {
      params: { path: { customer_id: customerId }, query: { ...range, basis } },
    }),
  );
}

/**
 * State what this customer earned over one period. **ADMIN floor.**
 *
 * ⚠ **A RE-STATEMENT IS THE SAME ACT PERFORMED AGAIN, AND A SECOND SOURCE IS A
 * SECOND FACT.** The record's identity is customer + period start + source
 * reference, so sending the same source for the same period corrects the figure
 * and sending a different one records another figure beside it. Two invoices
 * covering one month are two facts rather than a contradiction, which is why
 * the surface never asks the tenant to pick one.
 */
export async function recordSuppliedRevenue(
  customerId: string,
  body: SuppliedRevenueIn,
): Promise<SuppliedRevenueRecord> {
  return unwrap(
    await marginApi.POST("/customers/{customer_id}/supplied-revenue", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

// AND THE REVENUE-SWITCH PAIR WAS HERE AND IS GONE TOO (#497, slice 7 section
// 9) - one path, two operations, which with the pair above completes what
// phase A takes off this module. It read and wrote a per-customer override of
// whether that customer's billed usage was revenue, resolved from the
// workspace's billing mode wherever it was unset. Who raises a customer's
// invoices is not who earned the money: each posting's own price status says
// whether it carried revenue, and nothing above it has to guess.

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

/** One customer's identity — the id you gave them, from the id UBB did. */
export async function getCustomerIdentity(
  customerId: string,
): Promise<CustomerIdentity> {
  return unwrap(
    await platformApi.GET("/customers/{customer_id}", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

export async function createCustomer(
  body: CreateCustomerRequest,
): Promise<CustomerResponse> {
  return unwrap(await platformApi.POST("/customers", { body }));
}

// ---------------------------------------------------------------------------
// Metering — usage analytics
//
// ⚠ **THERE IS NO SEPARATE CALL HERE ANY MORE, AND THAT IS THE TICKET'S OWN
// POINT TURNED INWARD (#501).** The Usage tab and the Overview tab ask the same
// question of the same customer over the same window — every measure, no
// grouping — so a second function would issue a byte-identical request and
// cache it under a second key. Two cache entries for one answer is how two tabs
// start disagreeing about a period, which is the defect this whole slice
// exists to remove. Both tabs call `getCustomerMargin` through
// `useCustomerMargin`, and each narrows the one answer its own way.

export async function getUsageTimeseries(
  customerId: string,
  range: DateRange,
): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          ...range,
          customer_id: customerId,
          measures: [...EVERY_MEASURE],
          bucket: "day",
        },
      },
    }),
  );
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

/**
 * The affordability question (#463): a READ that registers nothing and moves
 * no admission window. A denial is still HTTP 200 — branch on `allowed` and
 * `reason` in the body; `reason` is a value of an OPEN vocabulary, rendered
 * through the shared open-set helper.
 */
export async function affordability(customerId: string): Promise<AffordabilityResponse> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/affordability", {
      params: { path: { customer_id: customerId } },
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
// Billing — customer spend pool, wallet policy, auto top-up

export async function getCustomerSpendPool(customerId: string): Promise<CustomerSpendPoolOut> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/customer-spend-pool", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

/** PUT is a FULL upsert — always send every field (defaults apply to omissions). */
export async function putCustomerSpendPool(
  customerId: string,
  body: CustomerSpendPoolIn,
): Promise<CustomerSpendPoolOut> {
  return unwrap(
    await billingApi.PUT("/customers/{customer_id}/customer-spend-pool", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

export async function getCustomerSpendPoolStatus(customerId: string): Promise<CustomerSpendPoolStatusOut> {
  return unwrap(
    await billingApi.GET("/customers/{customer_id}/customer-spend-pool/status", {
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
