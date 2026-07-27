import { meteringApi } from "@/api/client";
import { requireData } from "@/api/errors";
import type { CursorPage } from "@/lib/use-cursor-list";
import type {
  CloseTaskResponse,
  CustomerUsageParams,
  RecordUsageRequest,
  RecordUsageResponse,
  UsageAnalytics,
  UsageAnalyticsParams,
  UsageEvent,
  UsageEventDetail,
  UsageTimeseries,
} from "./types";

export function getUsageAnalytics(
  params: UsageAnalyticsParams,
): Promise<UsageAnalytics> {
  return meteringApi
    .GET("/analytics/usage", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load usage analytics"));
}

export function getUsageTimeseries(params: {
  granularity?: string;
  start_date?: string;
  end_date?: string;
  customer_id?: string;
  group_by?: string;
}): Promise<UsageTimeseries> {
  return meteringApi
    .GET("/analytics/usage/timeseries", { params: { query: params } })
    .then((r) => requireData(r, "Failed to load usage timeseries"));
}

export function listCustomerUsage(
  customerId: string,
  params?: CustomerUsageParams,
): Promise<CursorPage<UsageEvent>> {
  return meteringApi
    .GET("/customers/{customer_id}/usage", {
      params: { path: { customer_id: customerId }, query: params },
    })
    .then((r) => requireData(r, "Failed to load usage events"));
}

export function getUsageEvent(eventId: string): Promise<UsageEventDetail> {
  return meteringApi
    .GET("/usage/{event_id}", {
      params: { path: { event_id: eventId } },
    })
    .then((r) => requireData(r, "Failed to load usage event"));
}

export function recordUsage(
  body: RecordUsageRequest,
): Promise<RecordUsageResponse> {
  return meteringApi
    .POST("/usage", { body })
    .then((r) => requireData(r, "Failed to record usage"));
}

export function closeTask(taskId: string): Promise<CloseTaskResponse> {
  return meteringApi
    .POST("/tasks/{task_id}/close", {
      params: { path: { task_id: taskId } },
    })
    .then((r) => requireData(r, "Failed to close task"));
}
