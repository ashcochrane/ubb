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
// ⚠ **A MARGIN MAY BE ABSENT AND ABSENT IS NOT ZERO.** Every view below carries
// `margin_micros: number | null`; a null means UBB has no figure to state, and
// a caller that rendered it as a currency zero would be publishing exactly the
// silent zero this programme exists to delete.
//
// Money stays in integer micros end-to-end; only percentages (display-only)
// use floats.

import { descendingWithAbsencesLast } from "@/lib/economic-query";

import type {
  BreakdownRow,
  CustomerEconomicsRow,
  TenantEconomics,
} from "../api/types";

// ---------------------------------------------------------------------------
// Revenue / margin views

export interface EconomicsView {
  revenue_micros: number;
  margin_micros: number | null;
  margin_pct: number;
}

/** Headline figures for the stat row. */
export function summaryEconomics(summary: TenantEconomics): EconomicsView {
  return {
    revenue_micros: summary.total_revenue_micros,
    margin_micros: summary.gross_margin_micros,
    margin_pct: summary.margin_percentage,
  };
}

/** Per-customer figures for the economics table.
 *
 *  ⚠ THE ROWS CARRY A TOTAL NOW. The list route this replaced published three
 *  revenue fields per row and no total, so this console summed them itself and
 *  a source added later would have been missed until somebody noticed. One
 *  definition means one figure, and the summing is gone with the three fields.
 */
export function customerEconomics(row: CustomerEconomicsRow): EconomicsView {
  return {
    revenue_micros: row.total_revenue_micros,
    margin_micros: row.gross_margin_micros,
    margin_pct: row.margin_percentage,
  };
}

export type CustomerSortKey = "revenue" | "margin" | "margin_pct";

/**
 * Sort customer rows descending by the displayed figure.
 *
 * ⚠ **A ROW STATING NO MARGIN SORTS LAST RATHER THAN AS ZERO.** Treating an
 * absent margin as `0` would file a customer UBB cannot report on among the
 * ones it can, in the middle of the table, which reads as a claim.
 */
export function sortCustomers(
  rows: CustomerEconomicsRow[],
  key: CustomerSortKey,
): CustomerEconomicsRow[] {
  const value = (row: CustomerEconomicsRow): number | null => {
    const view = customerEconomics(row);
    return key === "revenue"
      ? view.revenue_micros
      : key === "margin"
        ? view.margin_micros
        : view.margin_micros === null
          ? null
          : view.margin_pct;
  };
  return [...rows].sort(descendingWithAbsencesLast(value));
}

// ---------------------------------------------------------------------------
// Cost breakdown bars

export interface BreakdownBar {
  name: string;
  revenue_micros: number;
  provider_micros: number;
  isOther: boolean;
}

/**
 * Top N rows by revenue, remainder folded into a single "Other" bar.
 *
 * ⚠ **A NULL AXIS VALUE IS A REAL ROW.** The report this replaced bucketed
 * every absence under one `(unattributed)` string; the answer now carries
 * `null` with a status beside it saying which absence it is. The bar keeps the
 * familiar heading, and telling the two absences apart on the page is the
 * rendering ticket's.
 */
export function topWithOther(rows: BreakdownRow[], limit = 8): BreakdownBar[] {
  const sorted = [...rows].sort(
    (a, b) => b.total_revenue_micros - a.total_revenue_micros,
  );
  const top = sorted.slice(0, limit).map((row) => ({
    name: row.group_value || "(unattributed)",
    revenue_micros: row.total_revenue_micros,
    provider_micros: row.total_provider_cost_micros,
    isOther: false,
  }));
  const rest = sorted.slice(limit);
  if (rest.length === 0) return top;
  return [
    ...top,
    {
      name: `Other (${rest.length})`,
      revenue_micros: rest.reduce((s, r) => s + r.total_revenue_micros, 0),
      provider_micros: rest.reduce(
        (s, r) => s + r.total_provider_cost_micros,
        0,
      ),
      isOther: true,
    },
  ];
}

/** "3e7f0a41-…" — shortened UUID for table cells (full id via copy/title). */
export function shortId(id: string): string {
  return id.length <= 8 ? id : `${id.slice(0, 8)}…`;
}
