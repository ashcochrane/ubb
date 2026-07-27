import {
  platformApi,
  marginApi,
  billingApi,
  meteringApi,
  subscriptionsApi,
  rootApi,
} from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  AssignBook,
  BillingProfile,
  BillingProfileIn,
  BudgetConfig,
  BudgetConfigIn,
  BudgetStatus,
  CreateCustomerRequest,
  CreateGrantRequest,
  CustomerMargin,
  CustomerMarkup,
  CustomerMarkupIn,
  CustomerResponse,
  Grant,
  MarginList,
  MarginTrend,
  PastLimitReport,
  RevenueMode,
  RevenueModeIn,
  RevenueProfile,
  RevenueProfileIn,
  SeatsIn,
  StripeSubscription,
  SubscribeIn,
  SubscriptionCancelIn,
  SubscriptionInvoice,
  UsageEvent,
} from "./types";

const path = (customer_id: string) => ({ params: { path: { customer_id } } });

// ---- Create / roster ----
export function createCustomer(body: CreateCustomerRequest): Promise<CustomerResponse> {
  return platformApi.POST("/customers", { body }).then((r) => requireData(r, "Couldn't create customer"));
}

export function getBusinessAccount(externalId: string) {
  return platformApi
    .GET("/accounts/business/{external_id}", { params: { path: { external_id: externalId } } })
    .then((r) => requireData(r, "Couldn't load business account"));
}

export function listMarginCustomers(query?: {
  start_date?: string;
  end_date?: string;
}): Promise<MarginList> {
  return marginApi
    .GET("/customers", { params: { query } })
    .then((r) => requireData(r, "Couldn't load customer roster"));
}

// ---- Margin (per customer) ----
export function getCustomerMargin(
  id: string,
  query?: { start_date?: string; end_date?: string },
): Promise<CustomerMargin> {
  return marginApi
    .GET("/customers/{customer_id}", { params: { path: { customer_id: id }, query } })
    .then((r) => requireData(r, "Couldn't load margin"));
}

export function getMarginTrend(id: string, periods = 6): Promise<MarginTrend> {
  return marginApi
    .GET("/customers/{customer_id}/trend", { params: { path: { customer_id: id }, query: { periods } } })
    .then((r) => requireData(r, "Couldn't load margin trend"));
}

export function getRevenueProfile(id: string): Promise<RevenueProfile> {
  return marginApi.GET("/customers/{customer_id}/revenue", path(id)).then((r) => requireData(r, "Couldn't load revenue"));
}
export function putRevenueProfile(id: string, body: RevenueProfileIn): Promise<RevenueProfile> {
  return marginApi
    .PUT("/customers/{customer_id}/revenue", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't save revenue"));
}
export function getRevenueMode(id: string): Promise<RevenueMode> {
  return marginApi.GET("/customers/{customer_id}/revenue-mode", path(id)).then((r) => requireData(r, "Couldn't load revenue mode"));
}
export function putRevenueMode(id: string, body: RevenueModeIn): Promise<RevenueMode> {
  return marginApi
    .PUT("/customers/{customer_id}/revenue-mode", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't save revenue mode"));
}

// ---- Billing (per customer): grants / budget / profile ----
export function listGrants(
  id: string,
  query?: { status?: string; cursor?: string; limit?: number },
): Promise<CursorPage<Grant>> {
  return billingApi
    .GET("/customers/{customer_id}/grants", { params: { path: { customer_id: id }, query } })
    .then((r) => requireData(r, "Couldn't load grants"));
}
export function createGrant(id: string, body: CreateGrantRequest): Promise<Grant> {
  return billingApi
    .POST("/customers/{customer_id}/grants", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't create grant"));
}
export function voidGrant(id: string, grantId: string): Promise<Grant> {
  return billingApi
    .POST("/customers/{customer_id}/grants/{grant_id}/void", {
      params: { path: { customer_id: id, grant_id: grantId } },
    })
    .then((r) => requireData(r, "Couldn't void grant"));
}
export function getBudget(id: string): Promise<BudgetConfig> {
  return billingApi.GET("/customers/{customer_id}/budget", path(id)).then((r) => requireData(r, "Couldn't load budget"));
}
export function putBudget(id: string, body: BudgetConfigIn): Promise<BudgetConfig> {
  return billingApi
    .PUT("/customers/{customer_id}/budget", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't save budget"));
}
export function getBudgetStatus(id: string): Promise<BudgetStatus> {
  return billingApi
    .GET("/customers/{customer_id}/budget/status", path(id))
    .then((r) => requireData(r, "Couldn't load budget status"));
}
export function getBillingProfile(id: string): Promise<BillingProfile> {
  return billingApi
    .GET("/customers/{customer_id}/billing-profile", path(id))
    .then((r) => requireData(r, "Couldn't load billing profile"));
}
export function putBillingProfile(id: string, body: BillingProfileIn): Promise<BillingProfile> {
  return billingApi
    .PUT("/customers/{customer_id}/billing-profile", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't save billing profile"));
}
export function getPastLimitReport(
  id: string,
  query?: { since?: string; until?: string },
): Promise<PastLimitReport> {
  return rootApi
    .GET("/customers/{customer_id}/past-limit-report", { params: { path: { customer_id: id }, query } })
    .then((r) => requireData(r, "Couldn't load limit report"));
}

// ---- Metering (per customer): markup / rate-card / usage ----
export function getCustomerMarkup(id: string): Promise<CustomerMarkup> {
  return meteringApi
    .GET("/pricing/customers/{customer_id}/markup", path(id))
    .then((r) => requireData(r, "Couldn't load markup"));
}
export function putCustomerMarkup(id: string, body: CustomerMarkupIn): Promise<CustomerMarkup> {
  return meteringApi
    .PUT("/pricing/customers/{customer_id}/markup", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't save markup"));
}
export function deleteCustomerMarkup(id: string) {
  return meteringApi
    .DELETE("/pricing/customers/{customer_id}/markup", path(id))
    .then((r) => requireData(r, "Couldn't remove markup"));
}
export function assignRateCard(id: string, body: AssignBook) {
  return meteringApi
    .POST("/pricing/customers/{customer_id}/rate-card", { ...path(id), body })
    .then((r) => requireData(r, "Couldn't assign rate card"));
}
export function listCustomerUsage(
  id: string,
  query?: { cursor?: string; limit?: number; tag_key?: string; tag_value?: string; past_limit?: boolean },
): Promise<CursorPage<UsageEvent>> {
  return meteringApi
    .GET("/customers/{customer_id}/usage", { params: { path: { customer_id: id }, query } })
    .then((r) => requireData(r, "Couldn't load usage"));
}

// ---- Subscriptions (per customer) ----
export function getSubscription(id: string): Promise<StripeSubscription> {
  return subscriptionsApi
    .GET("/customers/{customer_id}/subscription", path(id))
    .then((r) => requireData(r, "Couldn't load subscription"));
}
export function listSubscriptionInvoices(
  id: string,
  query?: { cursor?: string; limit?: number },
): Promise<CursorPage<SubscriptionInvoice>> {
  return subscriptionsApi
    .GET("/customers/{customer_id}/invoices", { params: { path: { customer_id: id }, query } })
    .then((r) => requireData(r, "Couldn't load subscription invoices"));
}

// ---- Subscription lifecycle (by EXTERNAL id) ----
export function subscribeCustomer(externalId: string, body: SubscribeIn) {
  return platformApi
    .POST("/customers/{external_id}/subscribe", { params: { path: { external_id: externalId } }, body })
    .then((r) => requireData(r, "Couldn't subscribe customer"));
}
export function setSeats(externalId: string, body: SeatsIn) {
  return platformApi
    .POST("/customers/{external_id}/seats", { params: { path: { external_id: externalId } }, body })
    .then((r) => requireData(r, "Couldn't set seats"));
}
export function cancelSubscription(externalId: string, body?: SubscriptionCancelIn) {
  return platformApi
    .POST("/customers/{external_id}/subscription/cancel", { params: { path: { external_id: externalId } }, body })
    .then((r) => requireData(r, "Couldn't cancel subscription"));
}
export function pauseSubscription(externalId: string) {
  return platformApi
    .POST("/customers/{external_id}/subscription/pause", { params: { path: { external_id: externalId } } })
    .then((r) => requireData(r, "Couldn't pause subscription"));
}
export function resumeSubscription(externalId: string) {
  return platformApi
    .POST("/customers/{external_id}/subscription/resume", { params: { path: { external_id: externalId } } })
    .then((r) => requireData(r, "Couldn't resume subscription"));
}
