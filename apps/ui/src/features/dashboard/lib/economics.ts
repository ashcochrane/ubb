// Pure derivations for the CFO overview.
//
// ⚠ **THE METERED VIEW IS GONE, AND #501 IS WHY IT COULD GO.** This module used
// to branch on whether the workspace bills through UBB: a meter-only one
// substituted its billed usage for the server's revenue total and drew a margin
// from it. The premise expired in #497 — the customer-level revenue switch was
// deleted and billed usage counts as revenue for every workspace — and #497
// wrote the branch down as a RESIDUAL rather than removing it, because the
// field it keyed on was not the field being deleted and nothing forced the
// issue.
//
// What forced the issue is the collapse. The branch read `usage_billed_micros`,
// a field of a response that no longer exists: the one economic query answers
// `customer_revenue` from one definition, with no per-source split to
// substitute. So the residual is PAID here rather than deferred again, and the
// consequence is the one #497 predicted — a metered workspace now reads the
// same revenue on this page as on the customer page, over the same window,
// because there is one definition of it.
//
// ⚠ **EVERY FIGURE HERE CARRIES ITS STATE, AND NOTHING HERE READS A NUMBER
// PAST IT (#510).** The views are the measures themselves (`MeasureFigure`);
// what a sort or a bar may use of one is `statedValue`, which is a GAP wherever
// the state states no figure — never a zero, and never the part of a revenue
// that could be placed at a grain where the rest could not.
//
// Money stays in integer micros end-to-end; only percentages (display-only)
// use floats.

import {
  combineFigures,
  CUSTOMER_REVENUE,
  descendingWithAbsencesLast,
  statedShare,
  statedValue,
  SUPPLIER_COGS,
  type MeasureFigure,
} from "@/lib/economic-query";

import type { BreakdownRow, CustomerEconomicsRow } from "../api/types";

// ---------------------------------------------------------------------------
// The customer table's order

export type CustomerSortKey = "revenue" | "margin" | "margin_pct";

/**
 * Sort customer rows descending by the displayed figure.
 *
 * ⚠ **A ROW STATING NO FIGURE SORTS LAST RATHER THAN AS ZERO.** Treating an
 * absent margin as `0` would file a customer UBB cannot report on among the
 * ones it can, in the middle of the table, which reads as a claim.
 */
export function sortCustomers(
  rows: CustomerEconomicsRow[],
  key: CustomerSortKey,
): CustomerEconomicsRow[] {
  const value = (row: CustomerEconomicsRow): number | null =>
    key === "revenue"
      ? statedValue(row.revenue)
      : key === "margin"
        ? statedValue(row.margin)
        : statedShare(row.margin, row.revenue);
  return [...rows].sort(descendingWithAbsencesLast(value));
}

// ---------------------------------------------------------------------------
// Cost breakdown bars

export interface BreakdownBar {
  name: string;
  /** The measure the bar's length is drawn from — see `plottedMeasureOf`. */
  plotted: MeasureFigure | null;
  revenue: MeasureFigure | null;
  cost: MeasureFigure | null;
  isOther: boolean;
}

/**
 * Which measure the breakdown's bars are drawn from: revenue where every row
 * states one, and the supplier cost where they do not.
 *
 * ⚠ **GROUPED BY A SUPPLIER, AN EVENT TYPE OR A KIND OF WORK, A WORKSPACE WITH
 * A SUBSCRIPTION HAS NO REVENUE TO DRAW.** Neither a subscription nor a figure
 * the tenant supplied names one, so the query reads every row's revenue as
 * `unavailable_at_requested_grain` and states the money as context instead.
 * The bars used to plot the PART that could be placed — billed usage alone —
 * as "Revenue by provider", which drew a floor as a total and dropped the
 * subscription without a word. The cost is known at every grain, so it is what
 * the card can still draw truthfully; the revenue beside each bar renders as
 * its state and the card states the context.
 */
export function plottedMeasureOf(
  rows: readonly BreakdownRow[],
): typeof CUSTOMER_REVENUE | typeof SUPPLIER_COGS {
  return rows.every((row) => statedValue(row.revenue) !== null)
    ? CUSTOMER_REVENUE
    : SUPPLIER_COGS;
}

/**
 * Top N rows by the plotted measure, remainder folded into a single "Other"
 * bar.
 *
 * The fold is `combineFigures`, never a sum of numbers: a folded row that
 * states no figure makes the "Other" bar state none either, rather than a
 * smaller one.
 *
 * ⚠ **A NULL AXIS VALUE IS A REAL ROW.** The report this replaced bucketed
 * every absence under one `(unattributed)` string; the answer now carries
 * `null` with a status beside it saying which absence it is. The bar keeps the
 * familiar heading; telling the two absences apart on the page is unowned — the
 * status is an open string with no registry concept to word it, and coining one
 * is a registry act rather than a rendering one.
 */
export function topWithOther(rows: BreakdownRow[], limit = 8): BreakdownBar[] {
  const measure = plottedMeasureOf(rows);
  const plottedOf = (row: BreakdownRow): MeasureFigure | null =>
    measure === CUSTOMER_REVENUE ? row.revenue : row.cost;
  const sorted = [...rows].sort(
    descendingWithAbsencesLast((row: BreakdownRow) => statedValue(plottedOf(row))),
  );
  const top = sorted.slice(0, limit).map((row) => ({
    name: row.group_value || "(unattributed)",
    plotted: plottedOf(row),
    revenue: row.revenue,
    cost: row.cost,
    isOther: false,
  }));
  const rest = sorted.slice(limit);
  if (rest.length === 0) return top;
  return [
    ...top,
    {
      name: `Other (${rest.length})`,
      plotted: combineFigures(measure, rest.map(plottedOf)),
      revenue: combineFigures(CUSTOMER_REVENUE, rest.map((row) => row.revenue)),
      cost: combineFigures(SUPPLIER_COGS, rest.map((row) => row.cost)),
      isOther: true,
    },
  ];
}

/** "3e7f0a41-…" — shortened UUID for table cells (full id via copy/title). */
export function shortId(id: string): string {
  return id.length <= 8 ? id : `${id.slice(0, 8)}…`;
}
