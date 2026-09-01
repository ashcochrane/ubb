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
  WIRE_GROUP_VALUE_KEY,
  type AnalyticsParams,
  type CloseTaskResult,
  type CustomerMargin,
  type MarginCustomers,
  type PastLimitReport,
  type RefundBody,
  type RefundResult,
  type ReportWindow,
  type TaskOutcome,
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

/**
 * Add the KNOWN part of a supplier cost to a running total (#320).
 *
 * An unresolved cost is ABSENT, not zero, so it contributes nothing — which is
 * what SQL's own aggregates do to a NULL, and what the real read contract does
 * behind these mocks. It is written as a skip rather than as `?? 0` because the
 * two differ exactly where it matters: a coalesce produces a number that cannot
 * be told apart from a complete one.
 *
 * The totals below are therefore floors, and every one of them now says how
 * many rows it left out: `countUnresolved` is the other half of the pair, and
 * the two are computed over the same event list in the same pass so a total and
 * its completeness cannot come from different sets of rows.
 */
function addKnownCost(total: number, micros: number | null | undefined): number {
  return micros == null ? total : total + micros;
}

/**
 * How many of these events carry a supplier cost UBB never learned.
 *
 * DERIVED, never stated. A mock that wrote its own number would go on saying
 * "nothing was excluded" whatever its fixtures held — which is the shape of a
 * fixture that agrees with the code it is meant to check. Reads the STATUS
 * rather than testing the amount for null: `not_applicable` also has no amount,
 * and nothing is missing from a total that never had one to include.
 */
function countUnresolved(events: MockEvent[]): number {
  return events.filter(
    (event) => event.detail.costing_status === "unresolved",
  ).length;
}

/**
 * How many of these events carry a customer price UBB could not resolve (#351).
 *
 * The price half of the pair above, and `addKnownCost` serves both amounts —
 * one rule, not two. Reads the STATUS and only `unknown`: `waived` and
 * `not_applicable` have no amount either, and neither is missing information.
 */
function countUnpriced(events: MockEvent[]): number {
  return events.filter(
    (event) => event.detail.pricing_status === "unknown",
  ).length;
}

function notFound(detail: string): ApiProblem {
  return new ApiProblem({
    status: 404,
    code: "not_found",
    title: "Not Found",
    detail,
  });
}

/** A close that contradicts a state the server already recorded (#409). It
 *  names the unit's REAL state, which is the half that matters: a caller told
 *  only "conflict" cannot tell a delivery refused on a killed unit from a
 *  double-submitted button. */
function alreadyEnded(status: CloseTaskResult["status"]): ApiProblem {
  return new ApiProblem({
    status: 409,
    code: "task_already_terminal",
    title: "This unit of work has already ended, and differently",
    detail: `this unit is already ${status} and cannot be closed that way`,
  });
}

/** The outcome-to-state map, mirroring the server's. Three declarations, three
 *  states, and nothing maps onto `killed` or `expired` — which is why a close
 *  against either is refused by construction rather than by a special case.
 *
 *  ⚠ `satisfies Record<TaskOutcome, …>` IS WHAT HOLDS THIS BY REFERENCE, and it
 *  is the idiom the generated vocabulary uses for its own maps. The console
 *  generator emits a VALUES array and a union type per concept, not a constant
 *  per value, so there is no `TASK_OUTCOME_DELIVERED` to import in TypeScript —
 *  the binding that can fail is the one on the whole map. A fourth declared
 *  outcome, a mistyped key, or a state that is not a real one is a `tsc` error
 *  here rather than a silently unmapped state at runtime. */
const STATUS_FOR_OUTCOME = {
  delivered: "completed",
  failed: "failed",
  cancelled: "cancelled",
} as const satisfies Record<TaskOutcome, CloseTaskResult["status"]>;

function toRow(detail: UsageEventDetail): UsageEventRow {
  return {
    id: detail.id,
    // Carried from the detail on the same argument as the two statuses below
    // it (#417): one posting, two shapes, and a row that decided its own kind
    // could say a thing the detail it came from contradicts.
    kind: detail.kind,
    // Carried from the detail rather than restated: the list row and the
    // detail describe one posting, and a projection that decided this for
    // itself could disagree with the row it came from (#317).
    costing_status: detail.costing_status,
    // And the price half, carried from the detail on the same argument (#351).
    pricing_status: detail.pricing_status,
    effective_at: detail.effective_at,
    metadata: detail.metadata,
    event_type: detail.event_type,
    provider: detail.provider,
    billed_cost_micros: detail.billed_cost_micros,
    provider_cost_micros: detail.provider_cost_micros,
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
    // Filtering is what the open bag is for, and what survived the fold.
    // The parameter names keep the analytics spelling they are published
    // under; that vocabulary is slice 7's to migrate.
    const bag = detail.metadata ?? {};
    if (bag[filters.tag_key] !== filters.tag_value) return false;
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
    totals.billed = addKnownCost(totals.billed, event.detail.billed_cost_micros);
    totals.provider = addKnownCost(
      totals.provider, event.detail.provider_cost_micros);
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
    billed = addKnownCost(billed, event.detail.billed_cost_micros);
    provider = addKnownCost(provider, event.detail.provider_cost_micros);
  }
  return {
    total_events: events.length,
    total_billed_cost_micros: billed,
    total_provider_cost_micros: provider,
    unresolved_event_count: countUnresolved(events),
    unpriced_event_count: countUnpriced(events),
    usage_markup_margin_micros: billed - provider,
    by_provider: legacyRows(groupBy(events, (d) => d.provider), "provider"),
    by_event_type: legacyRows(groupBy(events, (d) => d.event_type), "event_type"),
    by_customer: [],
    by_task_type: legacyRows(
      groupBy(events, (d) => d.grouping_fields["dim1"] ?? ""),
      "task_type",
    ),
    by_tag: [],
    breakdowns: {},
  };
}

function dimensionValue(detail: UsageEventDetail, groupKey: string): string {
  // The two always-present axes are their own properties; everything else is a
  // declared grouping field, looked up by the tenant's own key (#277). The
  // chain of slot comparisons this replaces could only ever reach three of the
  // ten slots that exist, and had to be extended by hand for each one.
  const value =
    groupKey === "provider"
      ? detail.provider
      : groupKey === "event_type"
        ? detail.event_type
        : (detail.grouping_fields[groupKey] ?? "");
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
    bucket.billed = addKnownCost(bucket.billed, event.detail.billed_cost_micros);
    bucket.provider = addKnownCost(
      bucket.provider, event.detail.provider_cost_micros);
    bucket.count += 1;
    buckets.set(key, bucket);
  }
  const series = [...buckets.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, totals]) => {
      const [bucket = "", groupValue] = key.split("|");
      const row: Record<string, unknown> = {
        bucket,
        provider_cost_micros: totals.provider,
        billed_cost_micros: totals.billed,
        markup_micros: totals.billed - totals.provider,
        event_count: totals.count,
      };
      // Emitted under the key the backend still uses, taken by reference from
      // the narrowing module rather than re-spelled here.
      if (groupValue !== undefined) row[WIRE_GROUP_VALUE_KEY] = groupValue;
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
  // There is nothing to refund where UBB never resolved a price (#351); the
  // real endpoint refuses such a refund with its own code, and this mock has no
  // amount to move either.
  mockBalanceMicros = addKnownCost(
    mockBalanceMicros, match.detail.billed_cost_micros);
  const result: RefundResult = {
    refund_id: `re_${body.idempotency_key.slice(0, 12)}`,
    balance_micros: mockBalanceMicros,
  };
  refundsByKey.set(body.idempotency_key, result);
  return result;
}

const closedTasks = new Map<string, CloseTaskResult>();

export async function closeTask(
  taskId: string,
  outcome: TaskOutcome,
): Promise<CloseTaskResult> {
  await mockDelay(500);
  // A REPEATED IDENTICAL CLOSE REPLAYS AND WRITES NOTHING (#409). The stored
  // answer comes back with `replayed` flipped, which is the one field that
  // tells a retry after a lost response apart from a second close.
  const replay = closedTasks.get(taskId);
  if (replay) {
    if (replay.outcome !== outcome) throw alreadyEnded(replay.status);
    return { ...replay, replayed: true };
  }
  const taskEvents = ALL_EVENTS.filter(
    (event) => event.detail.task_id === taskId,
  );
  if (taskEvents.length === 0) throw notFound("No task with that id.");
  // ⚠ AND A UNIT UBB ALREADY KILLED REFUSES EVERY CLOSE (#409), where this
  // mock used to answer 200 carrying the killed status. That silent success is
  // exactly what becomes silent revenue loss once a delivery creates a charge:
  // the caller would be told the close succeeded and never told that no charge
  // fired. Letting a late delivery override a kill was rejected outright — it
  // makes ignoring the stop signal free, so the ceiling stops being a ceiling.
  if (taskId === TASK_KILLED_ID) throw alreadyEnded("killed");
  let billed = 0;
  let provider = 0;
  for (const event of taskEvents) {
    billed = addKnownCost(billed, event.detail.billed_cost_micros);
    provider = addKnownCost(provider, event.detail.provider_cost_micros);
  }
  const result: CloseTaskResult = {
    task_id: taskId,
    parent_task_id: null,
    status: STATUS_FOR_OUTCOME[outcome],
    outcome,
    replayed: false,
    // False because nothing this fixture authors is sold at one agreed price —
    // its one unit of work is `event_priced` — and only a delivered close on
    // work sold that way earns a charge (#416). Not a stub: it is what the
    // route answers for this workspace.
    charge_created: false,
    event_count: taskEvents.length,
    total_billed_cost_micros: billed,
    total_provider_cost_micros: provider,
    unresolved_event_count: countUnresolved(taskEvents),
    unpriced_event_count: countUnpriced(taskEvents),
  };
  closedTasks.set(taskId, result);
  return result;
}
