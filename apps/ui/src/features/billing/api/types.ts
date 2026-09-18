// Type aliases from the generated schema map, plus the narrowed shapes this
// feature reads the one economic query through.
//
// ⚠ **THE REVENUE SECTION READ A ROUTE OF ITS OWN UNTIL #501**, and that route
// was a DUPLICATE: a tenant-wide day series of billed total versus supplier
// cost, which is exactly what the metering timeseries beside it already served,
// under a second definition and a different name for the difference between
// them. One question answers it now, bucketed by day.

import type { BillingSchemas } from "@/api/types";
import {
  caveatsOf,
  combineFigures,
  CUSTOMER_REVENUE,
  FIGURES_KEY,
  figureOn,
  GROSS_MARGIN,
  RECORDED_EVENTS,
  statedValue,
  SUPPLIER_COGS,
  type AnswerCaveats,
  type EconomicsAnswer,
  type MeasureFigure,
  type PlottedFigures,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

export type Economics = EconomicsAnswer;
export type CustomerSpendPool = BillingSchemas["CustomerSpendPoolOut"];
export type CustomerSpendPoolIn = BillingSchemas["CustomerSpendPoolIn"];
export type TenantUsageInvoice = BillingSchemas["TenantUsageInvoiceOut"];
export type TenantUsageInvoicePage = BillingSchemas["TenantUsageInvoiceListResponse"];
export type PostpaidConfig = BillingSchemas["PostpaidConfigOut"];
export type PostpaidConfigIn = BillingSchemas["PostpaidConfigIn"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];

/**
 * One day of the revenue chart.
 *
 * The plotted numbers are `statedValue` of their figures — a GAP where the
 * state states none — and the figures ride under `FIGURES_KEY`, each carrying
 * its own day's counts: an unresolved cost or an unresolved price belongs to
 * the day it fell in, and a reader hovering one point is told about that point.
 */
export interface RevenueDailyRow {
  /** Calendar day, YYYY-MM-DD. */
  day: string;
  provider_cost_micros: number | null;
  revenue_micros: number | null;
  /**
   * The day's margin AS THE QUERY STATES IT. The chart used to compute it
   * itself, revenue minus cost, which is a second copy of the server's rule —
   * and one that drew a margin through a day the server said had none.
   */
  margin_micros: number | null;
  event_count: number | null;
  [FIGURES_KEY]: PlottedFigures;
}

/**
 * The window's series and its totals.
 *
 * ⚠ **THE TOTALS ARE FOLDED FROM THE DAYS, AND A FOLD IS NOT A SUM.** Each
 * bucket is a real total over the postings that fell in it, and the window is
 * the buckets — which is how the server builds its own ungrouped answer. What
 * must NOT happen is a day's STATE vanishing into the total: until #510 the
 * cost and revenue were summed as numbers, so a day past the horizon counted as
 * a zero and the window read as a smaller whole. `combineFigures` lets the worst
 * day's state win, exactly as the query ranks a margin's two sides, and states
 * no figure under a state that states none.
 */
export interface RevenueWindow extends AnswerCaveats {
  /**
   * The revenue view the server drew these figures under (#508; slice 7 §5).
   *
   * ⚠ **A CHART SUMMING SUPPLIED AMOUNTS OWES THIS AND CAN OWE NOTHING ELSE.**
   * The per-record panels on a customer's page show a source reference and a
   * recognition method per row; a window adding three revenue sources together
   * has neither to show, so the one honest thing it can say is which of the two
   * views it was drawn under — and the answer states it rather than the console
   * assuming.
   */
  basis: string;
  daily: RevenueDailyRow[];
  revenue: MeasureFigure;
  cost: MeasureFigure;
  margin: MeasureFigure;
  events: MeasureFigure;
}

export function toRevenueWindow(answer: Economics): RevenueWindow {
  const daily: RevenueDailyRow[] = answer.rows.map((row) => {
    const figures = {
      provider_cost_micros: figureOn(row, SUPPLIER_COGS),
      revenue_micros: figureOn(row, CUSTOMER_REVENUE),
      margin_micros: figureOn(row, GROSS_MARGIN),
    };
    return {
      day: (row.bucket_start ?? "").slice(0, 10),
      provider_cost_micros: statedValue(figures.provider_cost_micros),
      revenue_micros: statedValue(figures.revenue_micros),
      margin_micros: statedValue(figures.margin_micros),
      event_count: statedValue(figureOn(row, RECORDED_EVENTS)),
      [FIGURES_KEY]: figures,
    };
  });
  const across = (measure: AnalyticsMeasure) =>
    combineFigures(measure, answer.rows.map((row) => figureOn(row, measure)));
  return {
    ...caveatsOf(answer),
    basis: answer.basis,
    daily,
    revenue: across(CUSTOMER_REVENUE),
    cost: across(SUPPLIER_COGS),
    margin: across(GROSS_MARGIN),
    events: across(RECORDED_EVENTS),
  };
}
