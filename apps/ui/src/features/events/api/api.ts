// Real API calls for the events feature. Every call goes through `unwrap`
// so failures always reject with a typed ApiProblem.

import { billingApi, meteringApi, rootApi } from "@/api/client";
import { unwrap } from "@/api/problem";
import {
  customerIdsIn,
  EVERY_MEASURE,
  FIELD_AXIS,
  MONEY_MEASURES,
  SUPPLIER_COGS,
} from "@/lib/economic-query";

import type {
  AnalyticsParams,
  CloseTaskResult,
  RefundBody,
  RefundResult,
  TaskOutcome,
  TimeseriesParams,
  CustomerChoice,
  Economics,
  UsageEventDetail,
  UsageListFilters,
  UsagePage,
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
          metadata_key: filters.metadata_key,
          metadata_value: filters.metadata_value,
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

/** Window rollup: what the window cost, earned and the difference. */
export async function getUsageAnalytics(
  params: AnalyticsParams,
): Promise<Economics> {
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: { query: { ...params, measures: [...EVERY_MEASURE] } },
    }),
  );
}

/** Daily spend timeseries, optionally grouped by one axis.
 *
 *  ⚠ MONEY ONLY WHERE IT GROUPS. `recorded_events` counts records at the
 *  granularity each Event Type declares, so the server refuses it across rows
 *  that mix Event Types — which a provider or declared-field grouping does. */
export async function getUsageTimeseries(
  params: TimeseriesParams,
): Promise<Economics> {
  const { group_by, ...window } = params;
  return unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: {
          ...window,
          bucket: "day",
          measures: group_by ? [...MONEY_MEASURES] : [...EVERY_MEASURE],
          // ⚠ NOT PREFIXED HERE ANY MORE (#506). The picker's value IS the
          // request word, kind and all, because it came off the discovery
          // contract — and it has to be, since a rollup is as offerable as a
          // field and this call site cannot know which it was handed.
          ...(group_by ? { group_by: [group_by] } : {}),
        },
      },
    }),
  );
}

/** Every customer the window's work reached — the picker's choices. */
export async function listCustomerChoices(): Promise<CustomerChoice[]> {
  const answer = unwrap(
    await meteringApi.GET("/analytics/economics", {
      params: {
        query: { measures: [SUPPLIER_COGS], group_by: [FIELD_AXIS("customer")] },
      },
    }),
  );
  return customerIdsIn(answer).map((customer_id) => ({ customer_id }));
}

// ⚠ THIS PICKER SHOWS IDS RATHER THAN THE TENANT'S OWN WORDS, AND THE REASON IS
// THE SHAPE OF THE READ RATHER THAN THE ABSENCE OF ONE. One customer's margin
// published the tenant's word for the row beside its figures, and that route is
// gone (#501); the one economic query groups by IDENTITY and publishes no
// external id, because a tenant's own vocabulary belongs to the surface that
// renders it rather than to a measure.
//
// `GET /platform/customers/{customer_id}` — added by the same commit — does map
// one id to one external id, and `customers/api/api.ts: getCustomerIdentity`
// calls it where a page holds ONE customer. It is not called here: this builds a
// picker over every customer in the answer, so resolving the list would be one
// request per row. Turning that into a read the picker can afford — a batch, or
// the axis publishing the word beside the id — is the events page's own ticket.
// The picker shows the shortened id with a copy affordance meanwhile, which is
// what it shows in its own list.

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
