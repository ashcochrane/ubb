// Type aliases over the generated schema map, plus local interfaces for the
// contract's UNTYPED response shapes (additionalProperties: true). The
// narrowing helpers below are the ONLY place a cast-like assertion lives for
// this feature — every consumer of an untyped shape goes through them, and
// they are defensive: unknown/misshapen entries degrade instead of throwing.

import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
  RootSchemas,
} from "@/api/types";
import { asCostingStatus } from "@/lib/supplier-cost";
import type { CostingStatus } from "@/lib/vocabulary";

export type UsageEventRow = MeteringSchemas["UsageEventOut"];
export type UsageEventDetail = MeteringSchemas["UsageEventDetailOut"];
export type UsagePage = MeteringSchemas["PaginatedUsageResponse"];
export type UsageAnalytics = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseries = MeteringSchemas["UsageTimeseriesResponse"];
export type PastLimitReport = MeteringSchemas["PastLimitReportResponse"];
// A unit of work is a KERNEL concept and its lifecycle sits at the root prefix
// (#409), so this comes from the root schemas rather than from metering's.
export type CloseTaskResult = RootSchemas["CloseTaskResponse"];

// WHAT A CALLER DECLARES WHEN IT CLOSES A UNIT OF WORK — re-exported from the
// generated vocabulary rather than re-derived from the request schema.
//
// ⚠ THE REGISTRY IS THE SOURCE, NOT THE CONTRACT, and the difference is not
// cosmetic. `src/lib/vocabulary.ts` already generates `TASK_OUTCOME_VALUES` and
// this type from `domain-vocabulary/`, and the console's rule is to import a
// canonical value rather than retype or re-derive one. Reaching for
// `RootSchemas["CloseTaskRequest"]["outcome"]` would produce the same union
// today from a second source, and "there is no console consumer declared for
// this concept" answers the G2 census — a question about which files the
// registry NAMES — rather than this rule, which is about where the console gets
// its canonical values from.
export type { TaskOutcome } from "@/lib/vocabulary";
export type RefundBody = BillingSchemas["RefundRequest"];
export type RefundResult = BillingSchemas["RefundResponse"];
export type MarginCustomers = MarginSchemas["MarginListOut"];
export type MarginCustomerRow = MarginSchemas["CustomerMarginListRow"];
export type CustomerMargin = MarginSchemas["CustomerMarginOut"];

/** Composable filters for the per-customer usage list. */
export interface UsageListFilters {
  tag_key?: string;
  tag_value?: string;
  past_limit?: boolean;
  stop_scope?: string;
  episode_seq?: number;
}

/** Window + filters for GET /metering/analytics/usage. */
export interface AnalyticsParams {
  start_date: string;
  end_date: string;
  customer_id?: string;
  past_limit?: boolean;
  stop_scope?: string;
  episode_seq?: number;
}

/** Window + grouping for GET /metering/analytics/usage/timeseries (day). */
export interface TimeseriesParams {
  start_date: string;
  end_date: string;
  customer_id?: string;
  group_by?: string;
}

/** ISO datetime window for the past-limit report (naive = UTC). */
export interface ReportWindow {
  since?: string;
  until?: string;
}

// ---------------------------------------------------------------------------
// Defensive readers (shared by the narrowing functions below).

function str(value: unknown): string | null {
  return typeof value === "string" ? value : null;
}

function num(value: unknown, fallback = 0): number {
  return typeof value === "number" && Number.isFinite(value) ? value : fallback;
}

function numOrNull(value: unknown): number | null {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function rec(value: unknown): Record<string, unknown> | null {
  return typeof value === "object" && value !== null && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : null;
}

// ---------------------------------------------------------------------------
// stop_context entries — spec types them as bare `items: {}`.
// [backend-verified shape — see discovery spec §1.1]

export interface StopContextEntry {
  limit: string;
  stop_scope: string;
  /** Null only for `suspended` (no durable suspension timestamp exists). */
  tripped_at: string | null;
  episode_seq: number | null;
  task_id: string | null;
  subtask_id: string | null;
  /** false = the tipping event; true = arrived after an existing stop. */
  arrived_after: boolean;
}

export function asStopContextEntries(
  value: unknown[] | null | undefined,
): StopContextEntry[] {
  if (!value) return [];
  const entries: StopContextEntry[] = [];
  for (const item of value) {
    const record = rec(item);
    if (!record) continue;
    const limit = str(record.limit);
    if (!limit) continue;
    entries.push({
      limit,
      stop_scope: str(record.stop_scope) ?? "",
      tripped_at: str(record.tripped_at),
      episode_seq: numOrNull(record.episode_seq),
      task_id: str(record.task_id),
      subtask_id: str(record.subtask_id),
      arrived_after: record.arrived_after === true,
    });
  }
  return entries;
}

// ---------------------------------------------------------------------------
// Timeseries rows — spec-untyped objects.
// [backend-verified shape — see discovery spec §2.2]

export interface TimeseriesPoint {
  bucket: string;
  provider_cost_micros: number;
  billed_cost_micros: number;
  markup_micros: number;
  event_count: number;
  /** This bucket's own uncosted events — the server answers it per bucket. */
  unresolved_event_count: number;
  /** Present only when group_by was requested; "(unattributed)" for empties. */
  group_value?: string;
}

/**
 * The key the backend puts a grouped value under on an untyped timeseries row.
 * It is NOT this console's word for it — `group_value` is — and it is spelled
 * here, once, because the row is untyped: `series` is `additionalProperties:
 * true` in the contract, so no generated type carries the name and no
 * type-checked fixture can.
 *
 * **This constant is what #280 predicted would be the only site that moves,
 * and #312 is the release that moved it.** `apps/metering/queries.py` now
 * writes the property the DECLARED margin rows have always published, so the
 * value below is that one. The two sides moved in the same commit on purpose:
 * renaming this read alone would have rendered every series "(unattributed)"
 * against a live server while every console test still passed.
 *
 * Exported so this feature's mock emits the same key the narrowing reads —
 * which also means the mock cannot contradict a mistake here. For that reason
 * `lib/timeseries.test.ts` pins it against a verbatim backend response, all
 * the way through to a painted series.
 */
export const WIRE_GROUP_VALUE_KEY = "grouping_field_value";

export function asTimeseriesPoints(
  series: Array<Record<string, unknown>>,
): TimeseriesPoint[] {
  const points: TimeseriesPoint[] = [];
  for (const row of series) {
    const bucket = str(row.bucket);
    if (!bucket) continue;
    const point: TimeseriesPoint = {
      bucket,
      provider_cost_micros: num(row.provider_cost_micros),
      billed_cost_micros: num(row.billed_cost_micros),
      markup_micros: num(row.markup_micros),
      event_count: num(row.event_count),
      unresolved_event_count: num(row.unresolved_event_count),
    };
    const groupValue = str(row[WIRE_GROUP_VALUE_KEY]);
    if (groupValue !== null) point.group_value = groupValue;
    points.push(point);
  }
  return points;
}

// ---------------------------------------------------------------------------
// Past-limit report episodes + totals — spec-untyped objects.
// [backend-verified shape — see discovery spec §6]

export interface PastLimitEpisodeEvent {
  event_id: string;
  effective_at: string;
  billed_cost_micros: number;
  /**
   * ⚠ NULLABLE ON THE WIRE, and this report is untyped in the contract, so
   * nothing but this line says so. `api/v1/past_limit.py` emits the posting's
   * own column, nullable since #317, and carries `costing_status` beside it
   * because a `null` there means two different things. Coalescing to zero would
   * tell a tenant their supplier charged nothing for the very events that
   * tripped their spend stop (#330).
   */
  provider_cost_micros: number | null;
  /** `null` where the row carried no status — see `asCostingStatus`. */
  costing_status: CostingStatus | null;
  arrived_after: boolean;
}

export interface PastLimitEpisode {
  /** floor_stop | soft_floor | task (open vocabulary). */
  family: string;
  /** Null for soft-floor marker rows. */
  limit: string | null;
  stop_scope: string;
  episode_seq: number | null;
  task_id: string | null;
  subtask_id: string | null;
  provider_cost_limit_micros: number | null;
  tripped_at: string | null;
  /** Null while stopped; unit kills are terminal (always null there). */
  resumed_at: string | null;
  events: PastLimitEpisodeEvent[];
  event_count: number;
  total_billed_cost_micros: number;
  total_provider_cost_micros: number;
  /**
   * How many of this episode's events carry a cost UBB never learned (#328).
   *
   * On the wire, and invisible to any scan of the contract's typed schemas —
   * this whole report is `additionalProperties: true`, which is how the surface
   * came to be read as one with no completeness at all (#330).
   */
  unresolved_event_count: number;
}

export function asPastLimitEpisodes(
  episodes: Array<Record<string, unknown>>,
): PastLimitEpisode[] {
  const out: PastLimitEpisode[] = [];
  for (const row of episodes) {
    const family = str(row.family);
    if (!family) continue;
    const events: PastLimitEpisodeEvent[] = [];
    if (Array.isArray(row.events)) {
      for (const item of row.events) {
        const record = rec(item);
        if (!record) continue;
        const eventId = str(record.event_id);
        if (!eventId) continue;
        events.push({
          event_id: eventId,
          effective_at: str(record.effective_at) ?? "",
          billed_cost_micros: num(record.billed_cost_micros),
          provider_cost_micros: numOrNull(record.provider_cost_micros),
          costing_status: asCostingStatus(record.costing_status),
          arrived_after: record.arrived_after === true,
        });
      }
    }
    out.push({
      family,
      limit: str(row.limit),
      stop_scope: str(row.stop_scope) ?? "",
      episode_seq: numOrNull(row.episode_seq),
      task_id: str(row.task_id),
      subtask_id: str(row.subtask_id),
      provider_cost_limit_micros: numOrNull(row.provider_cost_limit_micros),
      tripped_at: str(row.tripped_at),
      resumed_at: str(row.resumed_at),
      events,
      event_count: num(row.event_count),
      total_billed_cost_micros: num(row.total_billed_cost_micros),
      total_provider_cost_micros: num(row.total_provider_cost_micros),
      unresolved_event_count: num(row.unresolved_event_count),
    });
  }
  return out;
}

export interface LimitTotalsRow {
  limit: string;
  billed_cost_micros: number;
  provider_cost_micros: number;
  unresolved_event_count: number;
  event_count: number;
}

export function asTotalsPerLimit(
  totals: Record<string, unknown>,
): LimitTotalsRow[] {
  const rows: LimitTotalsRow[] = [];
  for (const [limit, value] of Object.entries(totals)) {
    const record = rec(value);
    if (!record) continue;
    rows.push({
      limit,
      billed_cost_micros: num(record.billed_cost_micros),
      provider_cost_micros: num(record.provider_cost_micros),
      unresolved_event_count: num(record.unresolved_event_count),
      event_count: num(record.event_count),
    });
  }
  return rows;
}
