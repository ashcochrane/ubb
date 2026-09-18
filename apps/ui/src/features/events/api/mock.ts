// Mock implementation — same exported signatures as ./api.ts, computed from
// the fixture event set so the strip, chart and ledger stay coherent with
// each other. Mutations keep session state (module-level) so
// replays behave like the real idempotent endpoints.

import { ApiProblem } from "@/api/problem";
import { mockDelay } from "@/lib/api-provider";
import {
  EVERY_MEASURE,
  MEASUREMENT_CONCEPT_AXIS,
  MONEY_MEASURES,
} from "@/lib/economic-query";
import {
  completePriceTotal,
  completeTotal,
  incompleteMeasures,
  incompletePriceTotal,
  incompleteTotal,
  knownMeasures,
  type EconomicMeasureScenario,
} from "@/lib/economic-scenarios";
import { axisNameOf } from "@/lib/grouping-axis";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import {
  ALL_EVENTS,
  CUSTOMER_A_ID,
  CUSTOMER_B_ID,
  CUSTOMER_C_ID,
  CUSTOMER_CHOICES,
  ECONOMIC_HORIZON,
  MEASUREMENT_CONCEPT_OF,
  MEASUREMENT_HORIZON,
  TASK_KILLED_ID,
  type MockEvent,
} from "./mock-data";
import {
  asStopContextEntries,
  type AnalyticsParams,
  type CloseTaskResult,
  type CustomerChoice,
  type RefundBody,
  type RefundResult,
  type TaskOutcome,
  type TimeseriesParams,
  type Economics,
  type UsageEventDetail,
  type UsageEventRow,
  type UsageListFilters,
  type UsagePage,
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
  if (
    filters.metadata_key !== undefined &&
    filters.metadata_value !== undefined
  ) {
    // Filtering is what the open bag is for, and what survived the fold — and
    // the pair is named for the bag it reads rather than for a grouping axis,
    // on this side exactly as on the wire (#504, #507).
    const bag = detail.metadata ?? {};
    if (bag[filters.metadata_key] !== filters.metadata_value) return false;
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

// ⚠ THE TWO HELPERS THAT BUILT THE REPORT'S BREAKDOWN BLOCKS WERE HERE AND
// ARE GONE (#501). One grouped events by an axis and the other emitted the
// older `by_*` row shape, with its own key for a customer and its own name for
// billed cost. The one economic query answers a grouping when it is asked for
// one, in a row the contract declares — so a mock has one row shape to build
// rather than two that had to agree.


export async function getUsageAnalytics(
  params: AnalyticsParams,
): Promise<Economics> {
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
    period_start: params.start_date,
    period_end: params.end_date,
    group_by: [],
    bucket: null,
    basis: "recorded",
    economic_data_available_from: ECONOMIC_HORIZON,
    measurement_data_available_from: MEASUREMENT_HORIZON,
    // ⚠ ONE ROW, ALWAYS. An ungrouped, unbucketed question has exactly one —
    // zeros over an empty window, which is a measured zero rather than an
    // absence — so the page never has to handle an empty list here.
    rows: [{
      bucket_start: null,
      grouping_field_value: [],
      grouping_field_value_status: [],
      measures: measuresOver(events, billed, provider),
    }],
    context: [],
  };
}

/**
 * The four measures over a set of seeds, as the query would state them —
 * COMPOSED rather than written (#510). This file wrote each state by hand, and
 * its day series hardcoded both counts to zero, so a bucket holding an uncosted
 * event read as a whole figure in the chart while the strip above it called
 * the window's total a floor.
 */
function measuresOver(
  events: MockEvent[],
  billed: number,
  provider: number,
): EconomicMeasureScenario[] {
  const unresolved = countUnresolved(events);
  const unpriced = countUnpriced(events);
  if (unresolved === 0 && unpriced === 0) {
    return knownMeasures({ cost_micros: provider, revenue_micros: billed, events: events.length });
  }
  return incompleteMeasures({
    cost: unresolved > 0 ? incompleteTotal(provider, unresolved) : completeTotal(provider),
    revenue: unpriced > 0 ? incompletePriceTotal(billed, unpriced) : completePriceTotal(billed),
    events: events.length,
  });
}

/**
 * The measurement concepts one seed was measured under — nothing where its
 * measurement record is not there to read.
 *
 * ⚠ **THIS IS WHERE THE PRUNED SEED MEETS ANALYTICS.** Its bag is
 * `prunedMeasurements()`'s empty object because the record was REMOVED at the
 * measurement horizon, so a grouping by what was measured has nothing of it to
 * group — and the server answers the same stretch with no rows at all (#500).
 * Reading the bag rather than the status is deliberate: it is what the server's
 * join reads, and it is why the console, handed that empty answer, must say
 * the stretch was pruned rather than that nothing happened.
 */
function conceptsOf(detail: UsageEventDetail): (string | null)[] {
  const keys = Object.keys(detail.measurements ?? {});
  return [...new Set(keys.map((key) => MEASUREMENT_CONCEPT_OF[key] ?? null))];
}

function axisValue(detail: UsageEventDetail, requestWord: string): string {
  // The two always-present axes are their own properties; everything else is a
  // declared grouping field, looked up by the tenant's own key (#277). The
  // chain of slot comparisons this replaces could only ever reach three of the
  // ten slots that exist, and had to be extended by hand for each one.
  //
  // ⚠ THE AXIS ARRIVES AS THE REQUEST WORD NOW, KIND AND ALL (#506), because
  // the picker reads it off the discovery contract, and the kind comes off
  // before the lookup.
  //
  // ⚠ **THE EVENT-CATEGORY ROLLUP THEREFORE FALLS THROUGH TO
  // "(unattributed)", AND THAT IS A LIMIT OF THIS FIXTURE RATHER THAN OF THE
  // ANSWER.** A rollup is a JOIN — a controlled mapping from an event type to a
  // broader classification — and these seeds carry no such mapping to join to,
  // so in mock mode picking it draws a single series under the unattributed
  // name. The measurement-concept rollup is no longer here: since #510 the
  // mock tenant declares which concept each of its measurement keys belongs to
  // (`MEASUREMENT_CONCEPT_OF`) and `getUsageTimeseries` groups by it directly,
  // because that grouping is where a pruned measurement record shows.
  const axis = axisNameOf(requestWord);
  const value =
    axis === "provider"
      ? detail.provider
      : axis === "event_type"
        ? detail.event_type
        : (detail.grouping_fields[axis] ?? "");
  return value === "" ? "(unattributed)" : value;
}

export async function getUsageTimeseries(
  params: TimeseriesParams,
): Promise<Economics> {
  await mockDelay();
  const events = ALL_EVENTS.filter(
    (event) =>
      (params.customer_id === undefined ||
        event.customer_id === params.customer_id) &&
      inWindow(event.detail, params.start_date, params.end_date),
  );
  // A grouped question carries exactly the measures it asked for; an
  // ungrouped one carries all four.
  const asked: readonly AnalyticsMeasure[] = params.group_by
    ? (params.measures ?? MONEY_MEASURES)
    : EVERY_MEASURE;
  const byMeasurement = params.group_by === MEASUREMENT_CONCEPT_AXIS;

  // Each (day, group) bucket keeps the seeds that fell in it. A seed measured
  // under two concepts is one event in each of their rows — which is what
  // grouping by a many-valued join means, and why those rows do not add up to
  // the ungrouped total.
  const buckets = new Map<string, MockEvent[]>();
  for (const event of events) {
    const day = `${event.detail.effective_at.slice(0, 10)}T00:00:00Z`;
    const groups: (string | null)[] | [undefined] = !params.group_by
      ? [undefined]
      : byMeasurement
        ? conceptsOf(event.detail)
        : [axisValue(event.detail, params.group_by)];
    for (const group of groups) {
      const key = `${day}|${group === undefined ? "" : JSON.stringify(group)}`;
      buckets.set(key, [...(buckets.get(key) ?? []), event]);
    }
  }
  const rows = [...buckets.entries()]
    .sort((a, b) => a[0].localeCompare(b[0]))
    .map(([key, bucketed]) => {
      const [bucket = "", encoded = ""] = key.split("|");
      const group = encoded === "" ? undefined : (JSON.parse(encoded) as string | null);
      let billed = 0;
      let provider = 0;
      for (const event of bucketed) {
        billed = addKnownCost(billed, event.detail.billed_cost_micros);
        provider = addKnownCost(provider, event.detail.provider_cost_micros);
      }
      return {
        bucket_start: bucket,
        // ⚠ POSITIONAL, aligned with the `group_by` the answer echoes: a
        // grouped question carries one value, an ungrouped one carries none.
        grouping_field_value: group === undefined ? [] : [group],
        grouping_field_value_status:
          group === undefined ? [] : [group === null ? "not_recorded" : "recorded"],
        measures: measuresOver(bucketed, billed, provider).filter((entry) =>
          asked.includes(entry.measure),
        ),
      };
    });
  return {
    period_start: params.start_date,
    period_end: params.end_date,
    // Echoed exactly as asked, which is what the real answer does — the
    // request word already carries its kind.
    group_by: params.group_by ? [params.group_by] : [],
    bucket: "day",
    basis: "recorded",
    economic_data_available_from: ECONOMIC_HORIZON,
    measurement_data_available_from: MEASUREMENT_HORIZON,
    rows,
    context: [],
  };
}


export async function listCustomerChoices(): Promise<CustomerChoice[]> {
  await mockDelay();
  return CUSTOMER_CHOICES.map((row) => ({ ...row }));
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
