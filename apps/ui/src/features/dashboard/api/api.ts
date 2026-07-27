// Real API calls for the CFO overview. Every call goes through unwrap() so
// callers always reject with a typed ApiProblem.

import {
  billingApi,
  connectApi,
  marginApi,
  meteringApi,
  tenantApi,
} from "@/api/client";
import { unwrap } from "@/api/problem";

import {
  toConnectStatus,
  type ApiKeyList,
  type BreakdownDimension,
  type ConnectStatus,
  type MarginCustomerList,
  type MarginSummary,
  type RateCardBookList,
  type RevenueAnalytics,
  type Unprofitable,
  type UsageAnalytics,
  type UsageTimeseries,
  type Window,
} from "./types";

/** Margin summary for the window (defaults server-side to month-to-date). */
export async function getMarginSummary(window: Window): Promise<MarginSummary> {
  return unwrap(
    await marginApi.GET("/summary", { params: { query: window } }),
  );
}

/**
 * Usage analytics for the window, with one requested breakdown dimension.
 * The totals (events / billed / provider) are dimension-independent, so this
 * single call powers both the stat row and the cost-by-dimension card.
 */
export async function getWindowAnalytics(
  window: Window,
  dimension: BreakdownDimension,
): Promise<UsageAnalytics> {
  return unwrap(
    await meteringApi.GET("/analytics/usage", {
      params: { query: { ...window, dimensions: [dimension] } },
    }),
  );
}

/**
 * All-time usage totals (no date window) — used only to decide whether the
 * workspace looks brand new (total_events === 0) for the getting-started card.
 */
export async function getLifetimeAnalytics(): Promise<UsageAnalytics> {
  return unwrap(await meteringApi.GET("/analytics/usage"));
}

/** Billing revenue analytics (daily billed vs provider) — billing product only. */
export async function getRevenueAnalytics(
  window: Window,
): Promise<RevenueAnalytics> {
  return unwrap(
    await billingApi.GET("/analytics/revenue", { params: { query: window } }),
  );
}

/** Metering daily timeseries — the chart source for tenants without billing. */
export async function getUsageTimeseries(
  window: Window,
): Promise<UsageTimeseries> {
  return unwrap(
    await meteringApi.GET("/analytics/usage/timeseries", {
      params: { query: { granularity: "day", ...window } },
    }),
  );
}

/** Per-customer margin rows for the window (not paginated, unsorted). */
export async function getMarginCustomers(
  window: Window,
): Promise<MarginCustomerList> {
  return unwrap(
    await marginApi.GET("/customers", { params: { query: window } }),
  );
}

/** Unprofitable customers for the current period (server defaults the period). */
export async function getUnprofitable(): Promise<Unprofitable> {
  return unwrap(await marginApi.GET("/unprofitable"));
}

/** First page of API keys — existence check for the getting-started card. */
export async function getApiKeysFirstPage(): Promise<ApiKeyList> {
  return unwrap(
    await tenantApi.GET("/api-keys", { params: { query: { limit: 1 } } }),
  );
}

/** First page of rate-card books — existence check for the getting-started card. */
export async function getRateCardBooksFirstPage(): Promise<RateCardBookList> {
  return unwrap(
    await meteringApi.GET("/pricing/rate-cards", {
      params: { query: { limit: 1 } },
    }),
  );
}

/** Stripe Connect onboarding state (billing tenants). */
export async function getConnectStatus(): Promise<ConnectStatus> {
  return toConnectStatus(unwrap(await connectApi.GET("/status")));
}
