// Type aliases over the generated schema map, plus local interfaces for the
// contract's UNTYPED response shapes (additionalProperties: true). The
// narrowing helpers below are the ONLY place a cast-like assertion lives for
// this feature — every consumer of an untyped shape goes through them, and
// they are defensive: unknown/misshapen entries degrade instead of throwing.

import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
} from "@/api/types";

export type UsageEventRow = MeteringSchemas["UsageEventOut"];
export type UsageEventDetail = MeteringSchemas["UsageEventDetailOut"];
export type UsagePage = MeteringSchemas["PaginatedUsageResponse"];
export type UsageAnalytics = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseries = MeteringSchemas["UsageTimeseriesResponse"];
export type PastLimitReport = MeteringSchemas["PastLimitReportResponse"];
export type CloseTaskResult = MeteringSchemas["CloseTaskResponse"];
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
  /** Present only when group_by was requested; "(unattributed)" for empties. */
  dimension?: string;
}

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
    };
    const dimension = str(row.dimension);
    if (dimension !== null) point.dimension = dimension;
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
  provider_cost_micros: number;
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
          provider_cost_micros: num(record.provider_cost_micros),
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
    });
  }
  return out;
}

export interface LimitTotalsRow {
  limit: string;
  billed_cost_micros: number;
  provider_cost_micros: number;
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
      event_count: num(record.event_count),
    });
  }
  return rows;
}
