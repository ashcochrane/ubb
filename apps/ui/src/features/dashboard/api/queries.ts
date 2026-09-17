// TanStack Query hooks for the CFO overview. All query keys live here; the
// first key segment is the BACKEND namespace (metering / margin / tenant /
// connect), not the feature name. The dashboard is read-only — no mutations, so
// no invalidation lives here either.
//
// ⚠ **FIVE KEYS BECAME ONE NAMESPACE (#501).** Four of these hooks read one
// route each and a fifth chose between two by product; they all read
// `metering/analytics/economics` now, and what distinguishes their cache
// entries is the SHAPE of the question — grouped, bucketed or neither — rather
// than which route was asked.

import {
  keepPreviousData,
  useQuery,
  type UseQueryResult,
} from "@tanstack/react-query";

import { dashboardApi } from "./provider";
import {
  toBreakdownRows,
  toCustomerRows,
  toRevenueCostPoints,
  toTenantEconomics,
  type ApiKeyList,
  type BreakdownAxis,
  type BreakdownRow,
  type ConnectStatus,
  type CustomerEconomicsRow,
  type Economics,
  type PricingBookList,
  type RevenueCostPoint,
  type TenantEconomics,
  type Unprofitable,
  type Window,
} from "./types";

export function useTenantEconomics(
  window: Window,
): UseQueryResult<TenantEconomics> {
  return useQuery({
    queryKey: ["metering", "analytics", "economics", "totals", window] as const,
    queryFn: () => dashboardApi.getTenantEconomics(window),
    select: toTenantEconomics,
    // Date-range changes refresh in the background instead of blanking.
    placeholderData: keepPreviousData,
  });
}

/**
 * The same window grouped by one axis. The totals do not depend on the axis, so
 * `placeholderData` keeps the bars stable while an axis switch refetches.
 */
export function useGroupedEconomics(
  window: Window,
  groupBy: BreakdownAxis,
): UseQueryResult<BreakdownRow[]> {
  return useQuery({
    queryKey: [
      "metering", "analytics", "economics", "grouped",
      { ...window, groupBy },
    ] as const,
    queryFn: () => dashboardApi.getGroupedEconomics(window, groupBy),
    select: toBreakdownRows,
    placeholderData: keepPreviousData,
  });
}

/** All-time totals — decides whether the getting-started card renders. */
export function useLifetimeEconomics(): UseQueryResult<Economics> {
  return useQuery({
    queryKey: ["metering", "analytics", "economics", "lifetime"] as const,
    queryFn: () => dashboardApi.getLifetimeEconomics(),
  });
}

/**
 * Chart source: one question for every workspace.
 *
 * ⚠ **THE PRODUCT FORK IS GONE AND THAT IS THE COLLAPSE WORKING.** This hook
 * used to pick between the billing revenue report and the metering timeseries
 * on whether the workspace had the billing product, and hold both queries so
 * neither fired before the product list resolved. The two reports were the same
 * two numbers over the same postings under two definitions; one query answers
 * both, so there is nothing left to choose and nothing to wait for.
 */
export function useRevenueVsCost(
  window: Window,
): UseQueryResult<RevenueCostPoint[]> {
  return useQuery({
    queryKey: [
      "metering", "analytics", "economics", "daily", window,
    ] as const,
    queryFn: () => dashboardApi.getDailyEconomics(window),
    select: toRevenueCostPoints,
    placeholderData: keepPreviousData,
  });
}

export function useCustomerEconomics(
  window: Window,
): UseQueryResult<CustomerEconomicsRow[]> {
  return useQuery({
    queryKey: [
      "metering", "analytics", "economics", "by-customer", window,
    ] as const,
    queryFn: () => dashboardApi.getCustomerEconomics(window),
    select: toCustomerRows,
    placeholderData: keepPreviousData,
  });
}

/** Unprofitable customers in the current (server-defaulted) period.
 *
 *  Still the MARGIN namespace, because it still reads the alerting record —
 *  which is why it kept its route when the reports lost theirs. */
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
