// TanStack Query hooks for the events feature. ALL query keys and mutation
// invalidation live here. First key segment = backend namespace.

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { useCursorList } from "@/api/pagination";

import { eventsApi } from "./provider";
import type {
  AnalyticsParams,
  RefundBody,
  ReportWindow,
  TaskOutcome,
  TimeseriesParams,
  UsageListFilters,
} from "./types";

/** What closing a unit of work takes: which one, and how it ended. */
export interface CloseTaskVariables {
  taskId: string;
  outcome: TaskOutcome;
}

export function useMarginCustomers() {
  return useQuery({
    queryKey: ["margin", "customers"] as const,
    queryFn: () => eventsApi.listMarginCustomers(),
  });
}

export function useCustomerMargin(customerId: string | undefined) {
  return useQuery({
    queryKey: ["margin", "customer", customerId] as const,
    queryFn: () => eventsApi.getCustomerMargin(customerId ?? ""),
    enabled: customerId !== undefined,
  });
}

export function useUsageAnalytics(params: AnalyticsParams) {
  return useQuery({
    queryKey: ["metering", "analytics", "usage", params] as const,
    queryFn: () => eventsApi.getUsageAnalytics(params),
    // Window/filter changes refresh in the background without blanking.
    placeholderData: (previous) => previous,
  });
}

export function useUsageTimeseries(params: TimeseriesParams) {
  return useQuery({
    queryKey: ["metering", "analytics", "timeseries", params] as const,
    queryFn: () => eventsApi.getUsageTimeseries(params),
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

/** Past-limit report — metering-scoped even though the path is root-level. */
export function usePastLimitReport(
  customerId: string | undefined,
  window: ReportWindow,
) {
  return useQuery({
    queryKey: ["metering", "past-limit-report", customerId, window] as const,
    queryFn: () => eventsApi.getPastLimitReport(customerId ?? "", window),
    enabled: customerId !== undefined,
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
    },
  });
}
