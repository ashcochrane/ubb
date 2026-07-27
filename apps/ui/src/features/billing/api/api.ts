// src/features/billing/api/api.ts
//
// Thin calls to the generated namespaced clients, unwrapped via requireData.
// Paths are RELATIVE to each namespace prefix (billingApi → /api/v1/billing,
// tenantApi → /api/v1/tenant).
import { billingApi, tenantApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  BudgetConfig,
  BudgetConfigIn,
  CreditRequest,
  DateRange,
  DebitCreditResponse,
  DebitRequest,
  PostpaidConfig,
  PostpaidConfigIn,
  PreCheckRequest,
  PreCheckResponse,
  RevenueAnalytics,
  TenantBillingPeriod,
  TenantInvoice,
  TenantUsageInvoice,
} from "./types";

// --- Tenant budget ---
export function getBudget(): Promise<BudgetConfig> {
  return billingApi
    .GET("/budget", {})
    .then((r) => requireData(r, "Failed to load tenant budget"));
}

export function putBudget(body: BudgetConfigIn): Promise<BudgetConfig> {
  return billingApi
    .PUT("/budget", { body })
    .then((r) => requireData(r, "Couldn't save budget"));
}

// --- Postpaid config ---
export function getPostpaidConfig(): Promise<PostpaidConfig> {
  return billingApi
    .GET("/postpaid-config", {})
    .then((r) => requireData(r, "Failed to load postpaid config"));
}

export function putPostpaidConfig(
  body: PostpaidConfigIn,
): Promise<PostpaidConfig> {
  return billingApi
    .PUT("/postpaid-config", { body })
    .then((r) => requireData(r, "Couldn't save postpaid config"));
}

// --- Revenue analytics ---
export function getRevenueAnalytics(
  range?: DateRange,
): Promise<RevenueAnalytics> {
  return billingApi
    .GET("/analytics/revenue", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load revenue analytics"));
}

// --- Manual adjustments ---
export function credit(body: CreditRequest): Promise<DebitCreditResponse> {
  return billingApi
    .POST("/credit", { body })
    .then((r) => requireData(r, "Couldn't issue credit"));
}

export function debit(body: DebitRequest): Promise<DebitCreditResponse> {
  return billingApi
    .POST("/debit", { body })
    .then((r) => requireData(r, "Couldn't record debit"));
}

// --- Spend pre-check ---
export function preCheck(body: PreCheckRequest): Promise<PreCheckResponse> {
  return billingApi
    .POST("/pre-check", { body })
    .then((r) => requireData(r, "Pre-check failed"));
}

// --- Invoices & periods ---
export function listTenantUsageInvoices(params?: {
  period?: string;
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<TenantUsageInvoice>> {
  return billingApi
    .GET("/tenant/usage-invoices", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load usage invoices"));
}

export function listTenantInvoices(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<TenantInvoice>> {
  return tenantApi
    .GET("/invoices", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load tenant invoices"));
}

export function listBillingPeriods(params?: {
  cursor?: string;
  limit?: number;
}): Promise<CursorPage<TenantBillingPeriod>> {
  return tenantApi
    .GET("/billing-periods", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load billing periods"));
}
