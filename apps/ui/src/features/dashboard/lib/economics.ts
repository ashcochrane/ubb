// Pure derivations for the CFO overview.
//
// ⚠ THE PREMISE OF THE METERED VIEW BELOW EXPIRED IN #497, AND THE VIEW
// ITSELF IS LEFT STANDING. This paragraph used to read: a workspace that
// does not bill through UBB has ~zero `total_revenue_micros` and ~zero
// `gross_margin_micros`, because `usage_revenue_micros` counted billed
// usage as revenue only for billed-mode customers — so the honest figures
// to show were usage billed and the billed-minus-cost margin, labelled
// "(metered)". That is no longer true of any workspace. The customer-level
// revenue switch is deleted, `usage_revenue_micros` equals
// `usage_billed_micros` on every row the server serves, and a workspace
// billing its customers elsewhere gets a real total and a real margin like
// anybody else.
//
// ⚠ **SO THE `meterOnly` BRANCHES NOW UNDER-REPORT, AND IT IS A RESIDUAL
// RATHER THAN A FIX THIS TICKET MAY MAKE.** They substitute `usage_billed`
// for the server's own total, which DROPS subscription revenue and anything
// the tenant supplied (#496's column) — so a metered workspace with either
// would read a smaller revenue figure here than on the customer page, over
// the same window. The branch keys on `/tenant/config`'s billing mode, not
// on the field #497 deletes, so nothing here is contract-forced and `tsc`
// is green either way; removing it is a presentation change across five
// files — the labels, the tooltips, the chart title and the sort — and
// belongs with the dashboard's own ticket in phase B3 (#507), which
// rebuilds this surface on the one economic query. Written down because a
// falsified premise nobody records is how a branch survives six tickets.
//
// Money stays in integer micros end-to-end; only percentages (display-only)
// use floats.

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
      // List rows carry no total_revenue_micros — sum the three revenue parts.
      // The third is what a tenant that bills elsewhere supplied (#496);
      // leaving it out would under-report exactly that tenant's revenue.
      revenue_micros:
        row.subscription_revenue_micros +
        row.supplied_revenue_micros +
        row.usage_revenue_micros,
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
