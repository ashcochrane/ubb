// TanStack Query hooks for the CFO overview. All query keys live here; the
// first key segment is the BACKEND namespace (margin / metering / billing /
// tenant / connect), not the feature name. The dashboard is read-only — no
// mutations, so no invalidation lives here either.

import {
  keepPreviousData,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { hasProduct, useTenantConfig } from "@/hooks/use-tenant-config";

import { revenuePoints, timeseriesPoints, type RevenueCostPoint } from "../lib/economics";
import { dashboardApi } from "./provider";
import type {
  ApiKeyList,
  BreakdownDimension,
  ConnectStatus,
  MarginCustomerList,
  MarginSummary,
  PricingBookList,
  UsageAnalytics,
  Unprofitable,
  Window,
} from "./types";

export function useMarginSummary(window: Window): UseQueryResult<MarginSummary> {
  return useQuery({
    queryKey: ["margin", "summary", window] as const,
    queryFn: () => dashboardApi.getMarginSummary(window),
    // Date-range changes refresh in the background instead of blanking.
    placeholderData: keepPreviousData,
  });
}

/**
 * Windowed usage analytics with one breakdown axis. The totals do not depend on
 * the axis, so `placeholderData` keeps the stat row and bars stable while an
 * axis switch refetches.
 */
export function useWindowAnalytics(
  window: Window,
  groupBy: BreakdownDimension,
): UseQueryResult<UsageAnalytics> {
  return useQuery({
    queryKey: ["metering", "analytics", "usage", { ...window, groupBy }] as const,
    queryFn: () => dashboardApi.getWindowAnalytics(window, groupBy),
    placeholderData: keepPreviousData,
  });
}

/** All-time totals — decides whether the getting-started card renders. */
export function useLifetimeAnalytics(): UseQueryResult<UsageAnalytics> {
  return useQuery({
    queryKey: ["metering", "analytics", "usage", "lifetime"] as const,
    queryFn: () => dashboardApi.getLifetimeAnalytics(),
  });
}

export interface RevenueCostChartQuery {
  points: RevenueCostPoint[] | undefined;
  isPending: boolean;
  isError: boolean;
  error: unknown;
  refetch: () => void;
}

/**
 * Chart source selection: tenants with the billing product read
 * GET /billing/analytics/revenue; everyone else reads the metering daily
 * timeseries. Neither query fires until tenant config resolves, so the wrong
 * endpoint is never hit while the product list is unknown.
 */
export function useRevenueVsCost(window: Window): RevenueCostChartQuery {
  const { data: config } = useTenantConfig();
  const billing = config ? hasProduct(config, "billing") : undefined;

  const revenueQuery = useQuery({
    queryKey: ["billing", "analytics", "revenue", window] as const,
    queryFn: () => dashboardApi.getRevenueAnalytics(window),
    enabled: billing === true,
    select: revenuePoints,
    placeholderData: keepPreviousData,
  });
  const timeseriesQuery = useQuery({
    queryKey: [
      "metering",
      "analytics",
      "timeseries",
      { ...window, granularity: "day" },
    ] as const,
    queryFn: () => dashboardApi.getUsageTimeseries(window),
    enabled: billing === false,
    select: timeseriesPoints,
    placeholderData: keepPreviousData,
  });

  const active = billing === false ? timeseriesQuery : revenueQuery;
  return {
    points: active.data,
    // While config is still loading neither query runs — report pending.
    isPending: billing === undefined || active.isPending,
    isError: active.isError,
    error: active.error,
    refetch: active.refetch,
  };
}

export function useMarginCustomers(
  window: Window,
): UseQueryResult<MarginCustomerList> {
  return useQuery({
    queryKey: ["margin", "customers", window] as const,
    queryFn: () => dashboardApi.getMarginCustomers(window),
    placeholderData: keepPreviousData,
  });
}

/** Unprofitable customers in the current (server-defaulted) period. */
export function useUnprofitable(): UseQueryResult<Unprofitable> {
  return useQuery({
    queryKey: ["margin", "unprofitable"] as const,
    queryFn: () => dashboardApi.getUnprofitable(),
  });
}

// ---------------------------------------------------------------------------
// Getting-started checks (only mounted when the workspace looks new)

export function useApiKeysCheck(): UseQueryResult<ApiKeyList> {
  return useQuery({
    // Distinct tail from the developers feature's paginated list to avoid
    // colliding with an infinite-query cache entry of a different shape.
    queryKey: ["tenant", "api-keys", "first-page"] as const,
    queryFn: () => dashboardApi.getApiKeysFirstPage(),
  });
}

export function usePricingBooksCheck(): UseQueryResult<PricingBookList> {
  return useQuery({
    queryKey: ["metering", "pricing", "pricing-books", "first-page"] as const,
    queryFn: () => dashboardApi.getPricingBooksFirstPage(),
  });
}

export function useConnectStatus(enabled: boolean): UseQueryResult<ConnectStatus> {
  return useQuery({
    queryKey: ["connect", "status"] as const,
    queryFn: () => dashboardApi.getConnectStatus(),
    enabled,
  });
}
