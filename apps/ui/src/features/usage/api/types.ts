import type { MeteringSchemas } from "@/api/types";

export type UsageAnalytics = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseries = MeteringSchemas["UsageTimeseriesResponse"];
export type UsageEvent = MeteringSchemas["UsageEventOut"];
export type UsageEventDetail = MeteringSchemas["UsageEventDetailOut"];
export type RecordUsageRequest = MeteringSchemas["RecordUsageRequest"];
export type RecordUsageResponse = MeteringSchemas["RecordUsageResponse"];
export type CloseTaskResponse = MeteringSchemas["CloseTaskResponse"];

/** Date-range + optional filters shared by the analytics reads. */
export interface UsageAnalyticsParams {
  start_date?: string;
  end_date?: string;
  customer_id?: string;
  tag_key?: string;
}

/** Query params for the customer-scoped usage-event list. */
export interface CustomerUsageParams {
  cursor?: string;
  limit?: number;
  tag_key?: string;
  tag_value?: string;
  past_limit?: boolean;
}

/**
 * The analytics `by_*` breakdowns and timeseries `series` arrive as untyped
 * objects (`{ [key: string]: unknown }[]`). Render them defensively — never
 * assume a concrete shape.
 */
export type BreakdownRow = Record<string, unknown>;
