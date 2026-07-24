// Mock implementation — same exported signatures as ./api.ts, computed from
// the fixture event set so the strip, chart, ledger, and report stay
// coherent with each other. Mutations keep session state (module-level) so
// replays behave like the real idempotent endpoints.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";

import {
  ALL_EVENTS,
  CUSTOMER_A_ID,
  CUSTOMER_B_ID,
  CUSTOMER_C_ID,
  CUSTOMER_MARGIN_BY_ID,
  MARGIN_CUSTOMERS,
  MARGIN_PERIOD,
  PAST_LIMIT_REPORTS,
  TASK_KILLED_ID,
  type MockEvent,
} from "./mock-data";
import {
  asStopContextEntries,
  type AnalyticsParams,
  type CloseTaskResult,
  type CustomerMargin,
  type MarginCustomers,
  type PastLimitReport,
  type RefundBody,
  type RefundResult,
  type ReportWindow,
  type TimeseriesParams,
  type UsageAnalytics,
  type UsageEventDetail,
  type UsageEventRow,
  type UsageListFilters,
  type UsagePage,
  type UsageTimeseries,
} from "./types";

const KNOWN_CUSTOMERS = new Set([CUSTOMER_A_ID, CUSTOMER_B_ID, CUSTOMER_C_ID]);
const MOCK_PAGE_SIZE = 25;

function notFound(detail: string): ApiProblem {
  return new ApiProblem({
    status: 404,
    code: "not_found",
    title: "Not Found",
    detail,
  });
}

function toRow(detail: UsageEventDetail): UsageEventRow {
  return {
    id: detail.id,
    request_id: detail.request_id,
    effective_at: detail.effective_at,
    metadata: detail.metadata,
    event_type: detail.event_type,
    provider: detail.provider,
    billed_cost_micros: detail.billed_cost_micros,
    provider_cost_micros: detail.provider_cost_micros,
    units: detail.units ?? null,
    stop_context: detail.stop_context ?? null,
  };
}

function matchesFilters(
  detail: UsageEventDetail,
  filters: UsageListFilters,
): boolean {
  const entries = asStopContextEntries(detail.stop_context);
  if (filters.past_limit === true && entries.length === 0) return false;
  if (filters.past_limit === false && entries.length > 0) return false;
  if (
    filters.stop_scope !== undefined &&
    !entries.some((entry) => entry.stop_scope === filters.stop_scope)
  ) {
    return false;
  }
  if (
    filters.episode_seq !== undefined &&
    !entries.some((entry) => entry.episode_seq === filters.episode_seq)
  ) {
    return false;
  }
  if (filters.tag_key !== undefined && filters.tag_value !== undefined) {
    const tags = detail.tags ?? {};
    if (tags[filters.tag_key] !== filters.tag_value) return false;
  }
  return true;
}

function inWindow(detail: UsageEventDetail, start: string, end: string): boolean {
  const day = detail.effective_at.slice(0, 10);
  return day >= start && day <= end;
}

function byEffectiveDesc(a: MockEvent, b: MockEvent): number {
  return b.detail.effective_at.localeCompare(a.detail.effective_at);
}

export async function listUsage(
  customerId: string,
  filters: UsageListFilters,
  cursor?: string,
): Promise<UsagePage> {
  await mockDelay();
  if (!KNOWN_CUSTOMERS.has(customerId)) {
    throw notFound("No customer with that id.");
  }
  const filtered = ALL_EVENTS.filter(
    (event) =>
      event.customer_id === customerId && matchesFilters(event.detail, filters),
  ).sort(byEffectiveDesc);
  const offset = cursor ? Number.parseInt(cursor, 10) || 0 : 0;
  const page = filtered.slice(offset, offset + MOCK_PAGE_SIZE);
  const nextOffset = offset + MOCK_PAGE_SIZE;
  const hasMore = nextOffset < filtered.length;
  return {
    data: page.map((event) => toRow(event.detail)),
    has_more: hasMore,
    next_cursor: hasMore ? String(nextOffset) : null,
  };
}

export async function getUsageEvent(eventId: string): Promise<UsageEventDetail> {
  await mockDelay();
  const match = ALL_EVENTS.find((event) => event.detail.id === eventId);
  if (!match) throw notFound("No usage event with that id.");
  return match.detail;
}

interface GroupTotals {
  event_count: number;
  billed: number;
  provider: number;
}

function groupBy(
  events: MockEvent[],
  keyOf: (detail: UsageEventDetail) => string,
): Map<string, GroupTotals> {
  const groups = new Map<string, GroupTotals>();
  for (const event of events) {
    const key = keyOf(event.detail);
    if (key === "") continue;
    const totals = groups.get(key) ?? { event_count: 0, billed: 0, provider: 0 };
    totals.event_count += 1;
    totals.billed += event.detail.billed_cost_micros;
    totals.provider += event.detail.provider_cost_micros;
    groups.set(key, totals);
  }
  return groups;
}

function legacyRows(
  groups: Map<string, GroupTotals>,
  keyName: string,
): Array<Record<string, unknown>> {
  return [...groups.entries()]
    .sort((a, b) => b[1].billed - a[1].billed)
    .map(([key, totals]) => ({
      [keyName]: key,
      event_count: totals.event_count,
      total_cost_micros: totals.billed,
      total_provider_cost_micros: totals.provider,
    }));
}

export async function getUsageAnalytics(
  params: AnalyticsParams,
): Promise<UsageAnalytics> {
  await mockDelay();
  const filters: UsageListFilters = {
    past_limit: params.past_limit,
    stop_scope: params.stop_scope,
    episode_seq: params.episode_seq,
  };
  const events = ALL_EVENTS.filter(
    (event) =>
      (params.customer_id === undefined ||
        event.customer_id === params.customer_id) &&
      inWindow(event.detail, params.start_date, params.end_date) &&
      matchesFilters(event.detail, filters),
  );
  let billed = 0;
  let provider = 0;
  for (const event of events) {
    billed += event.detail.billed_cost_micros;
    provider += event.detail.provider_cost_micros;
  }
  return {
    total_events: events.length,
    total_billed_cost_micros: billed,
    total_provider_cost_micros: provider,
    usage_markup_margin_micros: billed - provider,
    by_provider: legacyRows(groupBy(events, (d) => d.provider), "provider"),
    by_event_type: legacyRows(groupBy(events, (d) => d.event_type), "event_type"),
    by_customer: [],
    by_product: legacyRows(groupBy(events, (d) => d.product_id), "product_id"),
    by_tag: [],
    breakdowns: {},
  };
}

function dimensionValue(detail: UsageEventDetail, groupKey: string): string {
  const value =
    groupKey === "provider"
      ? detail.provider
      : groupKey === "event_type"
        ? detail.event_type
        : groupKey === "product_id"
          ? detail.product_id
          : groupKey === "service_id"
            ? detail.service_id
            : groupKey === "agent_id"
              ? detail.agent_id
              : "";
  return value === "" ? "(unattributed)" : value;
}

export async function getUsageTimeseries(
  params: TimeseriesParams,
): Promise<UsageTimeseries> {
  await mockDelay();
  const events = ALL_EVENTS.filter(
    (event) =>
      (params.customer_id === undefined ||
        event.customer_id === params.customer_id) &&
      inWindow(event.detail, params.start_date, params.end_date),
  );
  const buckets = new Map<
    string,
    { billed: number; provider: number; count: number }
  >();
  for (const event of events) {
    const day = `${event.detail.effective_at.slice(0, 10)}T00:00:00Z`;
    const key = params.group_by
      ? `${day}|${dimensionValue(event.detail, params.group_by)}`
      : day;
    const bucket = buckets.get(key) ?? { billed: 0, provider: 0, count: 0 };
    bucket.billed += event.detail.billed_cost_micros;
    bucket.provider += event.detail.provider_cost_micros;
    bucket.count += 1;
    buckets.set(key, bucket);
  }
  const series = [...buckets.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, totals]) => {
      const [bucket = "", dimension] = key.split("|");
      const row: Record<string, unknown> = {
        bucket,
        provider_cost_micros: totals.provider,
        billed_cost_micros: totals.billed,
        markup_micros: totals.billed - totals.provider,
        event_count: totals.count,
      };
      if (dimension !== undefined) row.dimension = dimension;
      return row;
    });
  return {
    granularity: "day",
    group_by: params.group_by ?? "",
    series,
  };
}

export async function listMarginCustomers(): Promise<MarginCustomers> {
  await mockDelay();
  return { customers: MARGIN_CUSTOMERS, period: MARGIN_PERIOD };
}

export async function getCustomerMargin(
  customerId: string,
): Promise<CustomerMargin> {
  await mockDelay();
  const margin = CUSTOMER_MARGIN_BY_ID[customerId];
  if (!margin) throw notFound("No customer with that id.");
  return margin;
}

export async function getPastLimitReport(
  customerId: string,
  window: ReportWindow,
): Promise<PastLimitReport> {
  await mockDelay();
  const report = PAST_LIMIT_REPORTS[customerId];
  if (!report) throw notFound("No customer with that id.");
  return {
    ...report,
    since: window.since ?? null,
    until: window.until ?? null,
  };
}

// --- Mutations (session-coherent state) ------------------------------------

let mockBalanceMicros = 42_180_000;
const refundsByKey = new Map<string, RefundResult>();

export async function refundUsage(
  customerId: string,
  body: RefundBody,
): Promise<RefundResult> {
  await mockDelay(500);
  const replay = refundsByKey.get(body.idempotency_key);
  if (replay) return replay;
  const match = ALL_EVENTS.find(
    (event) =>
      event.detail.id === body.usage_event_id &&
      event.customer_id === customerId,
  );
  if (!match) throw notFound("No usage event with that id for this customer.");
  mockBalanceMicros += match.detail.billed_cost_micros;
  const result: RefundResult = {
    refund_id: `re_${body.idempotency_key.slice(0, 12)}`,
    balance_micros: mockBalanceMicros,
  };
  refundsByKey.set(body.idempotency_key, result);
  return result;
}

const closedTasks = new Map<string, CloseTaskResult>();

export async function closeTask(taskId: string): Promise<CloseTaskResult> {
  await mockDelay(500);
  const replay = closedTasks.get(taskId);
  if (replay) return replay;
  const taskEvents = ALL_EVENTS.filter(
    (event) => event.detail.task_id === taskId,
  );
  if (taskEvents.length === 0) throw notFound("No task with that id.");
  let billed = 0;
  let provider = 0;
  for (const event of taskEvents) {
    billed += event.detail.billed_cost_micros;
    provider += event.detail.provider_cost_micros;
  }
  const result: CloseTaskResult = {
    task_id: taskId,
    parent_task_id: null,
    // A killed unit keeps its state when closed (#38 semantics).
    status: taskId === TASK_KILLED_ID ? "killed" : "completed",
    event_count: taskEvents.length,
    total_billed_cost_micros: billed,
    total_provider_cost_micros: provider,
  };
  closedTasks.set(taskId, result);
  return result;
}
