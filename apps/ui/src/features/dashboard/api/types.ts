// Dashboard (CFO overview) API shapes.
//
// Typed responses come straight from the generated schema map. The contract
// leaves four surfaces untyped (additionalProperties: true); their concrete
// runtime shapes are backend-verified and hand-typed below, each with a single
// narrowing function — the only place a cast-like assertion may live.

import type {
  BillingSchemas,
  MarginSchemas,
  MeteringSchemas,
  TenantSchemas,
} from "@/api/types";
import type { DateRange } from "@/lib/date-range";

/** A fully resolved inclusive date window (YYYY-MM-DD, UTC). */
export type Window = Required<DateRange>;

// ---------------------------------------------------------------------------
// Generated (fully typed) responses

export type MarginSummary = MarginSchemas["MarginSummaryOut"];
export type MarginCustomerList = MarginSchemas["MarginListOut"];
export type MarginCustomerRow = MarginSchemas["CustomerMarginListRow"];
export type Unprofitable = MarginSchemas["UnprofitableOut"];
export type UnprofitableRow = MarginSchemas["UnprofitableCustomerRow"];
export type UsageAnalytics = MeteringSchemas["UsageAnalyticsResponse"];
export type UsageTimeseries = MeteringSchemas["UsageTimeseriesResponse"];
export type RevenueAnalytics = BillingSchemas["RevenueAnalyticsResponse"];
export type ApiKeyList = TenantSchemas["ApiKeyListResponse"];
export type RateCardBookList = MeteringSchemas["PaginatedBooks"];

/** The four breakdown dimensions the overview picker offers. */
export const BREAKDOWN_DIMENSIONS = [
  "provider",
  "event_type",
  "product_id",
  "customer",
] as const;
export type BreakdownDimension = (typeof BREAKDOWN_DIMENSIONS)[number];

// ---------------------------------------------------------------------------
// Untyped-in-schema responses — hand-typed + narrowed
// [backend-verified shape — see discovery spec]

/** One row of `RevenueAnalyticsResponse.daily` (ordered by day asc). */
export interface RevenueDailyRow {
  day: string; // YYYY-MM-DD
  provider_cost_micros: number;
  billed_cost_micros: number;
  event_count: number;
}

/** One row of `UsageTimeseriesResponse.series` (ordered by bucket asc). */
export interface TimeseriesRow {
  bucket: string; // ISO datetime, day-truncated at granularity=day
  provider_cost_micros: number;
  billed_cost_micros: number;
  markup_micros: number;
  event_count: number;
}

/** One row of `UsageAnalyticsResponse.breakdowns[<dimension>]`. */
export interface BreakdownRow {
  dimension: string | null;
  event_count: number;
  total_provider_cost_micros: number;
  total_billed_cost_micros: number;
}

/** GET /connect/status — untyped `dict` in the schema. */
export interface ConnectStatus {
  account_id: string | null;
  charges_enabled: boolean;
  onboarded: boolean;
}

function num(value: unknown): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

function str(value: unknown): string {
  return typeof value === "string" ? value : "";
}

/** Narrow the untyped `daily` rows of the revenue analytics response. */
export function toRevenueDailyRows(response: RevenueAnalytics): RevenueDailyRow[] {
  return response.daily.map((row) => ({
    day: str(row["day"]),
    provider_cost_micros: num(row["provider_cost_micros"]),
    billed_cost_micros: num(row["billed_cost_micros"]),
    event_count: num(row["event_count"]),
  }));
}

/** Narrow the untyped `series` rows of the usage timeseries response. */
export function toTimeseriesRows(response: UsageTimeseries): TimeseriesRow[] {
  return response.series.map((row) => ({
    bucket: str(row["bucket"]),
    provider_cost_micros: num(row["provider_cost_micros"]),
    billed_cost_micros: num(row["billed_cost_micros"]),
    markup_micros: num(row["markup_micros"]),
    event_count: num(row["event_count"]),
  }));
}

/**
 * Narrow the breakdown rows for one dimension. Prefers the uniform
 * `breakdowns` map (present when the `dimensions` param was sent); falls back
 * to the legacy `by_*` arrays, which have two sharp edges: `by_customer` rows
 * key the value as the literal Django lookup `customer__external_id`, and all
 * `by_*` rows call billed cost `total_cost_micros` (the name drops "billed").
 */
export function toBreakdownRows(
  analytics: UsageAnalytics,
  dimension: BreakdownDimension,
): BreakdownRow[] {
  const fromBreakdowns = analytics.breakdowns[dimension];
  if (Array.isArray(fromBreakdowns)) {
    return fromBreakdowns.map((raw) => {
      const row = (typeof raw === "object" && raw !== null ? raw : {}) as Record<
        string,
        unknown
      >;
      return {
        dimension: typeof row["dimension"] === "string" ? row["dimension"] : null,
        event_count: num(row["event_count"]),
        total_provider_cost_micros: num(row["total_provider_cost_micros"]),
        total_billed_cost_micros: num(row["total_billed_cost_micros"]),
      };
    });
  }

  const legacyRows =
    dimension === "provider"
      ? analytics.by_provider
      : dimension === "event_type"
        ? analytics.by_event_type
        : dimension === "product_id"
          ? analytics.by_product
          : analytics.by_customer;
  const valueKey =
    dimension === "customer" ? "customer__external_id" : dimension;
  return legacyRows.map((row) => {
    const value = row[valueKey];
    return {
      dimension: typeof value === "string" ? value : null,
      event_count: num(row["event_count"]),
      total_provider_cost_micros: num(row["total_provider_cost_micros"]),
      // Legacy rows name billed cost `total_cost_micros`.
      total_billed_cost_micros: num(row["total_cost_micros"]),
    };
  });
}

/** Narrow the untyped connect-status body. */
export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  return {
    account_id:
      typeof raw["account_id"] === "string" ? raw["account_id"] : null,
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}
