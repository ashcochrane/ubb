// TanStack Query hooks for the events feature. ALL query keys and mutation
// invalidation live here. First key segment = backend namespace.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { eventsApi } from "./provider";
import {
  asTimeseriesPoints,
  toWindowTotals,
  type AnalyticsParams,
  type RefundBody,
  type TaskOutcome,
  type TimeseriesParams,
  type UsageListFilters,
} from "./types";

/** What closing a unit of work takes: which one, and how it ended. */
export interface CloseTaskVariables {
  taskId: string;
  outcome: TaskOutcome;
}

export function useCustomerChoices() {
  return useQuery({
    queryKey: ["metering", "analytics", "economics", "by-customer"] as const,
    queryFn: () => eventsApi.listCustomerChoices(),
  });
}

// ⚠ THE HOOK THAT RESOLVED A CUSTOMER'S UUID TO ITS EXTERNAL ID IS GONE (#501)
// with the route behind it, and nothing on the contract replaces it —
// `api.ts` carries the whole reason beside the call that used to make it.

export function useUsageAnalytics(params: AnalyticsParams) {
  return useQuery({
    queryKey: ["metering", "analytics", "economics", "totals", params] as const,
    queryFn: () => eventsApi.getUsageAnalytics(params),
    select: toWindowTotals,
    // Window/filter changes refresh in the background without blanking.
    placeholderData: (previous) => previous,
  });
}

export function useUsageTimeseries(params: TimeseriesParams) {
  return useQuery({
    queryKey: ["metering", "analytics", "economics", "daily", params] as const,
    queryFn: () => eventsApi.getUsageTimeseries(params),
    select: asTimeseriesPoints,
    placeholderData: (previous) => previous,
  });
}

export function useUsageLedger(
  customerId: string | undefined,
  filters: UsageListFilters,
) {
  return useCursorList(
    ["metering", "usage", customerId ?? "none", filters],
    (cursor) => eventsApi.listUsage(customerId ?? "", filters, cursor),
    { enabled: customerId !== undefined },
  );
}

export function useUsageEvent(eventId: string) {
  return useQuery({
    queryKey: ["metering", "usage-event", eventId] as const,
    queryFn: () => eventsApi.getUsageEvent(eventId),
  });
}

/** Refund moves wallet money and shifts margin — over-invalidate all three. */
export function useRefundUsage(customerId: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: RefundBody) => eventsApi.refundUsage(customerId, body),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["billing"] });
      void queryClient.invalidateQueries({ queryKey: ["margin"] });
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
    },
  });
}

/** Close a unit of work, declaring how it ended.
 *
 * The mutation takes a PAIR rather than a task id (#409), so the outcome has
 * to be named at the call site. A hook that defaulted it would be the
 * forgiving path becoming the money-moving one, two layers above the server
 * that refuses exactly that. */
export function useCloseTask() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ taskId, outcome }: CloseTaskVariables) =>
      eventsApi.closeTask(taskId, outcome),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["metering"] });
      // The tasks feature reads the same runs under its own root-mounted
      // namespace (#423); a close changes what they say, so over-invalidate
      // rather than miss.
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
    },
  });
}
