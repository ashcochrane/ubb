// Real API calls for the events feature. Every call goes through `unwrap`
// so failures always reject with a typed ApiProblem.

import { billingApi, marginApi, meteringApi, rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";

import type {
  AnalyticsParams,
  CloseTaskResult,
  CustomerMargin,
  MarginCustomers,
  PastLimitReport,
  RefundBody,
  RefundResult,
  ReportWindow,
  TaskOutcome,
  TimeseriesParams,
  UsageAnalytics,
  UsageEventDetail,
  UsageListFilters,
  UsagePage,
  UsageTimeseries,
} from "./types";

/** Cursor page of a customer's usage ledger (newest first). */
export async function listUsage(
  customerId: string,
  filters: UsageListFilters,
  cursor?: string,
): Promise<UsagePage> {
  return unwrap(
    await meteringApi.GET("/customers/{customer_id}/usage", {
      params: {
        path: { customer_id: customerId },
        query: {
          cursor,
          limit: 50,
          tag_key: filters.tag_key,
          tag_value: filters.tag_value,
          past_limit: filters.past_limit,
          stop_scope: filters.stop_scope,
          episode_seq: filters.episode_seq,
        },
      },
    }),
  );
}

/** One event's full pricing receipt (404 for unknown/foreign ids). */
export async function getUsageEvent(eventId: string): Promise<UsageEventDetail> {
  return unwrap(
    await meteringApi.GET("/usage/{event_id}", {
      params: { path: { event_id: eventId } },
    }),
  );
}

/** Window rollup: totals in both denominations + markup margin. */
export async function getUsageAnalytics(
  params: AnalyticsParams,
): Promise<UsageAnalytics> {
  return unwrap(
    await meteringApi.GET("/analytics/usage", {
      params: { query: { ...params } },
    }),
  );
}

/** Daily spend timeseries, optionally grouped by one axis. */
export async function getUsageTimeseries(
  params: TimeseriesParams,
): Promise<UsageTimeseries> {
  return unwrap(
    await meteringApi.GET("/analytics/usage/timeseries", {
      params: { query: { granularity: "day", ...params } },
    }),
  );
}

/** All customers with margin rows — the ledger's customer picker source. */
export async function listMarginCustomers(): Promise<MarginCustomers> {
  return unwrap(await marginApi.GET("/customers"));
}

/** One customer's margin detail — resolves the UUID to its external_id. */
export async function getCustomerMargin(
  customerId: string,
): Promise<CustomerMargin> {
  return unwrap(
    await marginApi.GET("/customers/{customer_id}", {
      params: { path: { customer_id: customerId } },
    }),
  );
}

/** Per-customer past-limit episodes + totals per limit. */
export async function getPastLimitReport(
  customerId: string,
  window: ReportWindow,
): Promise<PastLimitReport> {
  return unwrap(
    await rootApi.GET("/customers/{customer_id}/past-limit-report", {
      params: {
        path: { customer_id: customerId },
        query: { since: window.since, until: window.until },
      },
    }),
  );
}

/** Refund a usage charge back into the wallet (lot-aware; admin floor). */
export async function refundUsage(
  customerId: string,
  body: RefundBody,
): Promise<RefundResult> {
  return unwrap(
    await billingApi.POST("/customers/{customer_id}/refund", {
      params: { path: { customer_id: customerId } },
      body,
    }),
  );
}

/**
 * Close a unit of work, DECLARING HOW IT ENDED; returns the state that
 * declaration produced plus the rolled-up totals.
 *
 * On `rootApi` rather than `meteringApi` (#409): a unit of work is a kernel
 * concept neither metering nor billing owns, so the lifecycle is mounted at
 * the root prefix and is ungated.
 *
 * `outcome` is required and has NO default here, deliberately, because it has
 * none on the server either — the forgiving path must never be the
 * money-moving one, and a default would put one back a layer below the call
 * that refuses it.
 */
export async function closeTask(
  taskId: string,
  outcome: TaskOutcome,
): Promise<CloseTaskResult> {
  return unwrap(
    await rootApi.POST("/tasks/{task_id}/close", {
      params: { path: { task_id: taskId } },
      body: { outcome },
    }),
  );
}
