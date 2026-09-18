// Dashboard (CFO overview) API shapes.
//
// Typed responses come straight from the generated schema map. The contract
// leaves three surfaces untyped (additionalProperties: true); their concrete
// runtime shapes are backend-verified and hand-typed below, each with a single
// narrowing function — the only place a cast-like assertion may live.
//
// ⚠ **FIVE OF THIS FEATURE'S READS WERE FIVE SEPARATE ROUTES AND ARE NOW ONE
// QUESTION (#501)**: the margin summary, the per-customer margin list, the
// usage report, its timeseries and the billing revenue report. What that
// changed here is the shape of what arrives — a row per bucket per group, each
// carrying one entry per requested MEASURE — so the narrowings below turn one
// answer into the three views this feature has always rendered rather than
// turning four answers into four.
//
// Money stays in integer micros end-to-end; only percentages (display-only)
// use floats.

import type { MeteringSchemas, MarginSchemas, TenantSchemas } from "@/api/types";
import type { UbbAxis } from "@/lib/grouping-axis";
import {
  axisValueOn,
  caveatsOf,
  CUSTOMER_REVENUE,
  FIGURES_KEY,
  figureOn,
  figuresOn,
  GROSS_MARGIN,
  onlyRow,
  RECORDED_EVENTS,
  statedValue,
  SUPPLIER_COGS,
  type AnswerCaveats,
  type EconomicFigures,
  type EconomicsAnswer,
  type MeasureFigure,
  type PlottedFigures,
} from "@/lib/economic-query";
import type { DateRange } from "@/lib/date-range";

/** A fully resolved inclusive date window (YYYY-MM-DD, UTC). */
export type Window = Required<DateRange>;

// ---------------------------------------------------------------------------
// Generated (fully typed) responses

export type Economics = EconomicsAnswer;
export type Unprofitable = MarginSchemas["UnprofitableOut"];
export type UnprofitableRow = MarginSchemas["UnprofitableCustomerRow"];
export type ApiKeyList = TenantSchemas["ApiKeyListResponse"];
export type PricingBookList = MeteringSchemas["PaginatedPricingBooks"];

/**
 * The four breakdown axes the overview picker offers.
 *
 * ⚠ THE IDENTIFIER TOOK ITS SLICE'S WORD IN #506, which is what #372 left for
 * it: that commit paid the SENTENCE early to make room under a spread ceiling
 * and said in terms that the identifier moves with its slice. It has.
 *
 * ⚠ **FOUR NAMED AXES AND NOT THE TENANT'S WHOLE LIST, WHICH IS A CHOICE
 * RATHER THAN THE OLD DEFECT.** The group-by picker on the events page reads
 * every axis this tenant declared off the discovery contract, because exploring
 * is what that page is for. The overview is a summary: it offers four axes
 * every workspace has whatever it declares, so the card says the same thing to
 * a tenant that has declared nothing as to one that has declared ten. What made
 * the old list a defect was not that it was short — it was that three of its
 * entries were PHYSICAL SLOTS, offered as axes nobody had declared. Each of
 * these four is a reserved axis the server always answers for, typed against
 * the five UBB words so a fifth cannot be added here without one.
 */
export const BREAKDOWN_AXES = [
  "provider",
  "event_type",
  "task_type",
  "customer",
] as const satisfies readonly UbbAxis[];
export type BreakdownAxis = (typeof BREAKDOWN_AXES)[number];

// ---------------------------------------------------------------------------
// Narrowed views of the one query

/**
 * The window's economics for the whole workspace — the ungrouped, unbucketed
 * answer, which always has exactly one row.
 *
 * ⚠ **EACH MEASURE IS A FIGURE WITH ITS STATE, NOT AN AMOUNT (#510).** This
 * view used to carry four numbers coalesced to zero and a nullable margin, so a
 * window reaching back past the economic horizon rendered its cost and revenue
 * as `$0.00` — the state was on the wire and the narrowing threw it away.
 * `@/components/shared/measure-value` draws each one as its state allows; the
 * counts that bound an incomplete figure ride inside it.
 */
export type TenantEconomics = EconomicFigures;

/** One customer's row of the same answer, grouped by the customer axis. */
export interface CustomerEconomicsRow extends TenantEconomics {
  /** The customer's identity, which is what that axis groups. */
  customer_id: string;
}

/**
 * One point of the revenue-vs-cost chart, from a day-bucketed answer.
 *
 * The three plotted numbers are `statedValue` of their figures — a GAP where
 * the state states none, never a zero — and the figures themselves ride under
 * `FIGURES_KEY`, keyed by the same data keys, for the tooltip to say each one
 * as its state allows. The counts that bound a day's figures are per point
 * inside them, because an unresolved cost belongs to the day it fell in.
 */
export interface RevenueCostPoint {
  day: string; // YYYY-MM-DD
  revenue_micros: number | null;
  provider_micros: number | null;
  margin_micros: number | null;
  event_count: number | null;
  [FIGURES_KEY]: PlottedFigures;
}

/** The chart's points, and what the answer said beside them. */
export interface RevenueCostSeries extends AnswerCaveats {
  points: RevenueCostPoint[];
}

/** One bar of the cost breakdown, from an answer grouped by one axis.
 *
 *  ⚠ NO EVENT COUNT, and `api.ts` carries the reason: a count compared across
 *  rows that mix Event Types is the comparison the server refuses. */
export interface BreakdownRow {
  /** The value of the axis this row is grouped by, or null when unset. */
  group_value: string | null;
  cost: MeasureFigure | null;
  revenue: MeasureFigure | null;
}

/**
 * The breakdown's rows, and what the answer said beside them.
 *
 * ⚠ **THE CONTEXT IS WHY THIS IS NOT A BARE LIST.** Grouped by a supplier, an
 * event type or a kind of work, a subscription and a figure the tenant supplied
 * cannot be placed — neither names one — so the revenue measure reads
 * `unavailable_at_requested_grain` on every row and the money is in the
 * answer's `context`. A list of rows cannot carry that; the card has to.
 */
export interface Breakdown extends AnswerCaveats {
  rows: BreakdownRow[];
}

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

/** The workspace's totals for the window. */
export function toTenantEconomics(answer: Economics): TenantEconomics {
  return figuresOn(onlyRow(answer));
}

/** One row per customer, from an answer grouped by the customer axis. The
 *  count is null on each, because a grouped question cannot ask for it. */
export function toCustomerRows(answer: Economics): CustomerEconomicsRow[] {
  return answer.rows.map((row) => ({
    customer_id: axisValueOn(row) ?? "",
    ...figuresOn(row),
  }));
}

/**
 * Chart points from a day-bucketed answer.
 *
 * ⚠ The bucket's opening instant is an ISO datetime and the chart's key is a
 * calendar day, so the day is its first ten characters. A bucketed answer
 * always carries one — a posting's own instant is never absent — which is why
 * this narrows without a fallback.
 */
export function toRevenueCostSeries(answer: Economics): RevenueCostSeries {
  return {
    ...caveatsOf(answer),
    points: answer.rows.map((row) => {
      const figures = {
        revenue_micros: figureOn(row, CUSTOMER_REVENUE),
        provider_micros: figureOn(row, SUPPLIER_COGS),
        margin_micros: figureOn(row, GROSS_MARGIN),
      };
      return {
        day: (row.bucket_start ?? "").slice(0, 10),
        revenue_micros: statedValue(figures.revenue_micros),
        provider_micros: statedValue(figures.provider_micros),
        margin_micros: statedValue(figures.margin_micros),
        event_count: statedValue(figureOn(row, RECORDED_EVENTS)),
        [FIGURES_KEY]: figures,
      };
    }),
  };
}

/**
 * Breakdown rows from an answer grouped by one axis, and what it said beside
 * them.
 *
 * ⚠ **A NULL VALUE IS A ROW LIKE ANY OTHER AND MUST NOT BE DROPPED.** The
 * report this replaced bucketed every absence under one `(unattributed)`
 * string; the row now carries `null` with a status saying whether the value was
 * never recorded or whether the question does not apply to those rows. The bar
 * chart renders the absence as a heading either way, and what the two statuses
 * mean is still unrendered — a residual this console carries, not a state of a
 * MEASURE.
 */
export function toBreakdown(answer: Economics): Breakdown {
  return {
    ...caveatsOf(answer),
    rows: answer.rows.map((row) => ({
      group_value: axisValueOn(row),
      cost: figureOn(row, SUPPLIER_COGS),
      revenue: figureOn(row, CUSTOMER_REVENUE),
    })),
  };
}

/** Narrow the untyped connect-status body ("" sentinel = no account). */
export function toConnectStatus(raw: Record<string, unknown>): ConnectStatus {
  return {
    account_id:
      typeof raw["account_id"] === "string" ? raw["account_id"] : "",
    charges_enabled: raw["charges_enabled"] === true,
    onboarded: raw["onboarded"] === true,
  };
}
