import { billingApi, marginApi, meteringApi, webhooksApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type {
  BudgetConfig,
  DateRange,
  MarginSummary,
  RevenueAnalytics,
  UnprofitableResult,
  UsageAnalytics,
  WebhookConfig,
} from "./types";

export function getMarginSummary(range: DateRange): Promise<MarginSummary> {
  return marginApi
    .GET("/summary", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load margin summary"));
}

export function getUnprofitable(): Promise<UnprofitableResult> {
  return marginApi
    .GET("/unprofitable", {})
    .then((r) => requireData(r, "Failed to load unprofitable customers"));
}

export function getRevenueAnalytics(range: DateRange): Promise<RevenueAnalytics> {
  return billingApi
    .GET("/analytics/revenue", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load revenue analytics"));
}

export function getBudget(): Promise<BudgetConfig> {
  return billingApi
    .GET("/budget", {})
    .then((r) => requireData(r, "Failed to load budget"));
}

export function getUsageAnalytics(range: DateRange): Promise<UsageAnalytics> {
  return meteringApi
    .GET("/analytics/usage", { params: { query: range } })
    .then((r) => requireData(r, "Failed to load usage analytics"));
}

export function listWebhookConfigs(): Promise<WebhookConfig[]> {
  return webhooksApi
    .GET("/configs", { params: { query: { limit: 100 } } })
    .then((r) => requireData(r, "Failed to load webhook endpoints"))
    .then((page) => page.data);
}
