// Pure derivations for the CFO overview.
//
// Meter-only semantics (margin spec): `usage_billed_micros` is what usage
// billed at the tenant's prices regardless of mode; `usage_revenue_micros`
// counts it as revenue only for billed-mode customers. A meter-only tenant
// therefore has ~zero `total_revenue_micros`/`gross_margin_micros`, so the
// honest figures to show are usage billed and the markup margin
// (billed − provider cost) — clearly labelled "(metered)". Money stays in
// integer micros end-to-end; only percentages (display-only) use floats.

import type {
  BreakdownRow,
  MarginCustomerRow,
  MarginSummary,
  RevenueAnalytics,
  UsageTimeseries,
} from "../api/types";
import { toRevenueDailyRows, toTimeseriesRows } from "../api/types";

// ---------------------------------------------------------------------------
// Revenue / margin views

export interface EconomicsView {
  revenue_micros: number;
  margin_micros: number;
  margin_pct: number;
}

function pct(marginMicros: number, revenueMicros: number): number {
  if (revenueMicros === 0) return 0;
  return (marginMicros / revenueMicros) * 100;
}

/** Headline figures for the stat row, honest about meter-only mode. */
export function summaryEconomics(
  summary: MarginSummary,
  meterOnly: boolean,
): EconomicsView {
  if (!meterOnly) {
    return {
      revenue_micros: summary.total_revenue_micros,
      margin_micros: summary.gross_margin_micros,
      margin_pct: summary.margin_percentage,
    };
  }
  const margin = summary.usage_billed_micros - summary.provider_cost_micros;
  return {
    revenue_micros: summary.usage_billed_micros,
    margin_micros: margin,
    margin_pct: pct(margin, summary.usage_billed_micros),
  };
}

/** Per-customer figures for the economics table, meter-only aware. */
export function customerEconomics(
  row: MarginCustomerRow,
  meterOnly: boolean,
): EconomicsView {
  if (!meterOnly) {
    return {
      // List rows carry no total_revenue_micros — sum the two revenue parts.
      revenue_micros:
        row.subscription_revenue_micros + row.usage_revenue_micros,
      margin_micros: row.gross_margin_micros,
      margin_pct: row.margin_percentage,
    };
  }
  const margin = row.usage_billed_micros - row.provider_cost_micros;
  return {
    revenue_micros: row.usage_billed_micros,
    margin_micros: margin,
    margin_pct: pct(margin, row.usage_billed_micros),
  };
}

export type CustomerSortKey = "revenue" | "margin" | "margin_pct";

/** Sort margin rows descending by the displayed (mode-aware) figure. */
export function sortCustomers(
  rows: MarginCustomerRow[],
  meterOnly: boolean,
  key: CustomerSortKey,
): MarginCustomerRow[] {
  const value = (row: MarginCustomerRow): number => {
    const view = customerEconomics(row, meterOnly);
    return key === "revenue"
      ? view.revenue_micros
      : key === "margin"
        ? view.margin_micros
        : view.margin_pct;
  };
  return [...rows].sort((a, b) => value(b) - value(a));
}

// ---------------------------------------------------------------------------
// Revenue-vs-cost chart points (one shape from either source)

export interface RevenueCostPoint {
  day: string; // YYYY-MM-DD
  billed_micros: number;
  provider_micros: number;
  margin_micros: number;
  event_count: number;
  /**
   * That day's own uncosted events. It rides the point rather than the chart
   * because the two sources below both answer per bucket, and because the
   * point is what the tooltip is handed: a count kept beside the series would
   * caveat every day for one day's missing invoice.
   */
  unresolved_event_count: number;
}

/** Chart points from the billing revenue analytics (billing tenants). */
export function revenuePoints(response: RevenueAnalytics): RevenueCostPoint[] {
  return toRevenueDailyRows(response).map((row) => ({
    day: row.day,
    billed_micros: row.billed_cost_micros,
    provider_micros: row.provider_cost_micros,
    margin_micros: row.billed_cost_micros - row.provider_cost_micros,
    event_count: row.event_count,
    unresolved_event_count: row.unresolved_event_count,
  }));
}

/** Chart points from the metering daily timeseries (no billing product). */
export function timeseriesPoints(response: UsageTimeseries): RevenueCostPoint[] {
  return toTimeseriesRows(response).map((row) => ({
    day: row.bucket.slice(0, 10),
    billed_micros: row.billed_cost_micros,
    provider_micros: row.provider_cost_micros,
    margin_micros: row.markup_micros,
    event_count: row.event_count,
    unresolved_event_count: row.unresolved_event_count,
  }));
}

// ---------------------------------------------------------------------------
// Cost breakdown bars

export interface BreakdownBar {
  name: string;
  billed_micros: number;
  provider_micros: number;
  event_count: number;
  isOther: boolean;
}

/**
 * Top N rows by billed cost, remainder folded into a single "Other" bar.
 * Null/empty group values render as "(unattributed)".
 */
export function topWithOther(rows: BreakdownRow[], limit = 8): BreakdownBar[] {
  const sorted = [...rows].sort(
    (a, b) => b.total_billed_cost_micros - a.total_billed_cost_micros,
  );
  const top = sorted.slice(0, limit).map((row) => ({
    name: row.group_value || "(unattributed)",
    billed_micros: row.total_billed_cost_micros,
    provider_micros: row.total_provider_cost_micros,
    event_count: row.event_count,
    isOther: false,
  }));
  const rest = sorted.slice(limit);
  if (rest.length === 0) return top;
  return [
    ...top,
    {
      name: `Other (${rest.length})`,
      billed_micros: rest.reduce((s, r) => s + r.total_billed_cost_micros, 0),
      provider_micros: rest.reduce(
        (s, r) => s + r.total_provider_cost_micros,
        0,
      ),
      event_count: rest.reduce((s, r) => s + r.event_count, 0),
      isOther: true,
    },
  ];
}

/** "3e7f0a41-…" — shortened UUID for table cells (full id via copy/title). */
export function shortId(id: string): string {
  return id.length <= 8 ? id : `${id.slice(0, 8)}…`;
}
