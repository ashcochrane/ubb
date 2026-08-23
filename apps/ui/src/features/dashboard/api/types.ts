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
export type PricingBookList = MeteringSchemas["PaginatedPricingBooks"];

/**
 * The four breakdown axes the overview picker offers.
 *
 * ⚠ THE IDENTIFIER IS STILL SLICE 7's — only the prose is paid here (#372).
 * The plural that named this axis is retired and its console ledger entry
 * counts the files holding it; the constant below keeps the word, because
 * renaming it is part of the one economic query slice 7 builds and is not
 * something a commit about pricing books gets to decide. What this commit
 * needed was room: the pricing feature reads the tenant's own grouping-field
 * registry off the wire, which puts the word in one more file, and the entry's
 * count is a ceiling on spread as well as a floor. Paying a debt early from
 * another slice is allowed and an owner may move earlier and never later, so
 * the sentence moves now and the identifier moves with its slice.
 */
export const BREAKDOWN_DIMENSIONS = [
  "provider",
  "event_type",
  "task_type",
  "customer",
] as const;
export type BreakdownDimension = (typeof BREAKDOWN_DIMENSIONS)[number];

// ---------------------------------------------------------------------------
// Untyped-in-schema responses — hand-typed + narrowed
// [backend-verified shape — see discovery spec]

/**
 * One row of `RevenueAnalyticsResponse.daily` (ordered by day asc).
 *
 * `unresolved_event_count` is that day's OWN completeness — how many of its
 * events carry a supplier cost UBB never learned. Per row rather than per
 * window because a reader hovering one point is asking about that point.
 */
export interface RevenueDailyRow {
  day: string; // YYYY-MM-DD
  provider_cost_micros: number;
  billed_cost_micros: number;
  event_count: number;
  unresolved_event_count: number;
}

/** One row of `UsageTimeseriesResponse.series` (ordered by bucket asc). */
export interface TimeseriesRow {
  bucket: string; // ISO datetime, day-truncated at granularity=day
  provider_cost_micros: number;
  billed_cost_micros: number;
  markup_micros: number;
  event_count: number;
  unresolved_event_count: number;
}

/** One row of a `UsageAnalyticsResponse.breakdowns` entry. */
export interface BreakdownRow {
  /** The value of the axis this row is grouped by, or null when unset. */
  group_value: string | null;
  event_count: number;
  total_provider_cost_micros: number;
  total_billed_cost_micros: number;
}

/**
 * The key the backend puts a grouped value under on an untyped breakdown row.
 * It is NOT this console's word for it — `BreakdownRow.group_value` is — and it
 * is spelled here, once, because the row is untyped.
 *
 * **This constant is what #280 predicted would be the only console site to
 * move, and #312 is the release that moved it.** `api/v1/metering_endpoints.py`
 * now writes the property the DECLARED `/margin/by-grouping-field` rows have
 * always published, so all three rollups agree on one word. Server and console
 * moved in the same commit on purpose: renaming this read alone would have
 * rendered every bar "(unattributed)" against a live server while every console
 * test still passed.
 *
 * The rows are `additionalProperties: true` in the contract, so the generated
 * types cannot carry the name and a fixture cannot be type-checked into
 * matching it. `economics.test.ts` pins the pairing with a representative
 * payload instead.
 *
 * Exported so this feature's mock emits the same key the narrowing reads —
 * a mock that spelled it separately could drift from the backend silently.
 */
export const WIRE_GROUP_VALUE_KEY = "grouping_field_value";

/**
 * GET /connect/status — untyped `dict` in the schema.
 * Canonical shape shared by every feature caching ['connect','status']:
 * `account_id` is always a string — the backend field is a CharField
 * defaulting to "" (never null), so a missing/absent id narrows to "".
 */
export interface ConnectStatus {
  account_id: string;
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
    // `num`'s zero default means "this row left nothing out" — a claim, not a
    // shrug. It stands only because the server writes the count on every row
    // it emits; a row arriving without one is a backend regression rather than
    // a shape this narrowing is entitled to answer for.
    unresolved_event_count: num(row["unresolved_event_count"]),
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
    unresolved_event_count: num(row["unresolved_event_count"]),
  }));
}

/**
 * Narrow the breakdown rows for one axis. Prefers the uniform `breakdowns` map
 * (present when the grouping param was sent); falls back to the legacy `by_*`
 * arrays, which have two sharp edges: `by_customer` rows key the value as the
 * literal Django lookup `customer__external_id`, and all `by_*` rows call
 * billed cost `total_cost_micros` (the name drops "billed").
 */
export function toBreakdownRows(
  analytics: UsageAnalytics,
  groupBy: BreakdownDimension,
): BreakdownRow[] {
  const fromBreakdowns = analytics.breakdowns[groupBy];
  if (Array.isArray(fromBreakdowns)) {
    return fromBreakdowns.map((raw) => {
      const row = (typeof raw === "object" && raw !== null ? raw : {}) as Record<
        string,
        unknown
      >;
      const value = row[WIRE_GROUP_VALUE_KEY];
      return {
        group_value: typeof value === "string" ? value : null,
        event_count: num(row["event_count"]),
        total_provider_cost_micros: num(row["total_provider_cost_micros"]),
        total_billed_cost_micros: num(row["total_billed_cost_micros"]),
      };
    });
  }

  const legacyRows: Array<Record<string, unknown>> =
    groupBy === "provider"
      ? analytics.by_provider
      : groupBy === "event_type"
        ? analytics.by_event_type
        : groupBy === "task_type"
          ? analytics.by_task_type
          : analytics.by_customer;
  const valueKey = groupBy === "customer" ? "customer__external_id" : groupBy;
  return legacyRows.map((row) => {
    const value = row[valueKey];
    return {
      group_value: typeof value === "string" ? value : null,
      event_count: num(row["event_count"]),
      total_provider_cost_micros: num(row["total_provider_cost_micros"]),
      // Legacy rows name billed cost `total_cost_micros`.
      total_billed_cost_micros: num(row["total_cost_micros"]),
    };
  });
}

/** Narrow the untyped connect-status body ("" sentinel = no account). */
export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  return {
    account_id: str(raw["account_id"]),
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}
