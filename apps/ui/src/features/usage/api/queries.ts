import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { toastOnError } from "@/lib/mutations";
import { useCursorList } from "@/lib/use-cursor-list";
import * as api from "./api";
import type {
  CustomerUsageParams,
  RecordUsageRequest,
  UsageAnalyticsParams,
} from "./types";

const ROOT = ["metering", "usage"] as const;

export const analyticsKey = (params: UsageAnalyticsParams) =>
  [...ROOT, "analytics", params] as const;
export const timeseriesKey = (params: Record<string, unknown>) =>
  [...ROOT, "timeseries", params] as const;
export const eventKey = (eventId: string) => [...ROOT, "event", eventId] as const;

export function useUsageAnalytics(params: UsageAnalyticsParams) {
  return useQuery({
    queryKey: analyticsKey(params),
    queryFn: () => api.getUsageAnalytics(params),
  });
}

export function useUsageTimeseries(params: {
  granularity?: string;
  start_date?: string;
  end_date?: string;
  customer_id?: string;
  group_by?: string;
}) {
  return useQuery({
    queryKey: timeseriesKey(params),
    queryFn: () => api.getUsageTimeseries(params),
  });
}

export function useCustomerUsage(
  customerId: string,
  filters?: CustomerUsageParams,
) {
  return useCursorList({
    queryKeyBase: [...ROOT, "customer", customerId, filters ?? {}],
    fetchPage: (cursor) =>
      api.listCustomerUsage(customerId, { ...filters, cursor, limit: 50 }),
    enabled: !!customerId,
  });
}

export function useUsageEvent(eventId: string) {
  return useQuery({
    queryKey: eventKey(eventId),
    queryFn: () => api.getUsageEvent(eventId),
    enabled: !!eventId,
  });
}

export function useRecordUsage() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: RecordUsageRequest) => api.recordUsage(body),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ROOT });
      toast.success("Usage recorded");
    },
    onError: toastOnError("Couldn't record usage"),
  });
}

export function useCloseTask() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (taskId: string) => api.closeTask(taskId),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ROOT });
      toast.success("Task closed");
    },
    onError: toastOnError("Couldn't close task"),
  });
}
