// Type aliases from the generated contract, plus local interfaces for the
// handful of responses the schema leaves untyped (additionalProperties: true).

import type {
  BillingSchemas,
  MarginSchemas,
  PlatformSchemas,
  SubscriptionSchemas,
} from "@/api/types";
import {
  axisValueOn,
  caveatsOf,
  CUSTOMER_REVENUE,
  FIGURES_KEY,
  figureOn,
  GROSS_MARGIN,
  onlyRow,
  RECORDED_EVENTS,
  statedValue,
  SUPPLIER_COGS,
  type AnswerCaveats,
  type EconomicRow,
  type EconomicsAnswer,
  type MeasureFigure,
  type PlottedFigures,
} from "@/lib/economic-query";

// ---------------------------------------------------------------------------
// Margin (list + detail workbench overview)

// ⚠ **FIVE OF THIS FEATURE'S READS WERE FIVE ROUTES AND ARE ONE (#501)** — the
// per-customer margin list, one customer's margin, that customer's trend, the
// usage rollup and its day series. What arrives is one answer shape; the
// narrowings below turn it into the four views this feature renders.
//
// ⚠ **AND ONE FIGURE IS NOT A THREE-WAY SPLIT ANY MORE.** One customer's margin
// published a subscription share, a supplied share and billed usage beside its
// total. The one economic query answers `customer_revenue` from ONE definition
// — that is the point of it — so the split is not on this surface. The supplied
// share is still readable, from the record that owns it
// (`GET /margin/customers/{id}/supplied-revenue`), and rebuilding the panel on
// that read is the customers feature's own ticket.
export type Economics = EconomicsAnswer;

/**
 * One customer's economics over a window.
 *
 * ⚠ **EACH MEASURE IS A FIGURE WITH ITS STATE (#510).** This view carried four
 * numbers coalesced to zero and a nullable margin; the list then printed that
 * margin's percentage — computed as zero for a margin UBB would not state — as
 * `0.0%` beside the dash for the margin itself, and the Usage tab printed the
 * margin as `$0.00`. `@/components/shared/measure-value` draws each figure as
 * its state allows.
 */
export interface CustomerEconomics {
  customer_id: string;
  revenue: MeasureFigure | null;
  cost: MeasureFigure | null;
  margin: MeasureFigure | null;
  /** Recorded work, where the question could carry it. A GROUPED question
   *  cannot: a count across rows that mix Event Types is the comparison the
   *  server refuses. */
  events: MeasureFigure | null;
}

/**
 * One point of the margin trend — a month of the same answer.
 *
 * The plotted numbers are `statedValue` of their figures, a GAP where the
 * state states none; the figures ride under `FIGURES_KEY` for the tooltip.
 */
export interface TrendPoint {
  period_start: string;
  provider_cost_micros: number | null;
  revenue_micros: number | null;
  gross_margin_micros: number | null;
  [FIGURES_KEY]: PlottedFigures;
}

function economicsOf(row: EconomicRow | undefined, customerId: string): CustomerEconomics {
  return {
    customer_id: customerId,
    revenue: figureOn(row, CUSTOMER_REVENUE),
    cost: figureOn(row, SUPPLIER_COGS),
    margin: figureOn(row, GROSS_MARGIN),
    events: figureOn(row, RECORDED_EVENTS),
  };
}

/** The three money figures of a row, keyed by the data keys a chart plots
 *  them under. */
function moneyFigures(row: EconomicRow): {
  provider_cost_micros: MeasureFigure | null;
  revenue_micros: MeasureFigure | null;
  gross_margin_micros: MeasureFigure | null;
} {
  return {
    provider_cost_micros: figureOn(row, SUPPLIER_COGS),
    revenue_micros: figureOn(row, CUSTOMER_REVENUE),
    gross_margin_micros: figureOn(row, GROSS_MARGIN),
  };
}

/** One row per customer, from an answer grouped by the customer axis. */
export function toCustomerRows(answer: Economics): CustomerEconomics[] {
  return answer.rows.map((row) => economicsOf(row, axisValueOn(row) ?? ""));
}

/** One customer's own figures, from an answer filtered to them. */
export function toOneCustomer(answer: Economics): CustomerEconomics {
  return economicsOf(onlyRow(answer), "");
}

/**
 * A margin trend: the months, and the revenue view they were drawn under.
 *
 * ⚠ **THE BASIS TRAVELS WITH THE POINTS RATHER THAN BESIDE THEM, AND THE TYPE
 * IS WHERE §5 IS ENFORCED.** A supplied revenue figure inside these totals has
 * either been placed whole on the day its period opens or spread across that
 * period by its own method, and the tenant "must be able to see whether they
 * are looking at smoothing they did not ask for". The answer states which; a
 * narrowing that returned bare points would let every caller drop it silently,
 * which is what every caller did until this ticket. Now a surface cannot get
 * the figures without being handed the sentence that qualifies them.
 */
export interface MarginTrend extends AnswerCaveats {
  /** The revenue view the server drew these figures under. */
  basis: string;
  points: TrendPoint[];
}

/** The trend's points, from a month-bucketed answer. */
export function toTrendPoints(answer: Economics): MarginTrend {
  return {
    ...caveatsOf(answer),
    basis: answer.basis,
    points: answer.rows.map((row) => {
      const figures = moneyFigures(row);
      return {
        period_start: (row.bucket_start ?? "").slice(0, 10),
        provider_cost_micros: statedValue(figures.provider_cost_micros),
        revenue_micros: statedValue(figures.revenue_micros),
        gross_margin_micros: statedValue(figures.gross_margin_micros),
        [FIGURES_KEY]: figures,
      };
    }),
  };
}

/** The usage tab's day series, and what the answer said beside it. */
export interface UsageSeries extends AnswerCaveats {
  points: TimeseriesPoint[];
}

/** The usage tab's day series. */
export function toTimeseriesPoints(answer: Economics): UsageSeries {
  return {
    ...caveatsOf(answer),
    points: answer.rows.map((row) => {
      const figures = moneyFigures(row);
      return {
        bucket: row.bucket_start ?? "",
        provider_cost_micros: statedValue(figures.provider_cost_micros),
        revenue_micros: statedValue(figures.revenue_micros),
        event_count: statedValue(figureOn(row, RECORDED_EVENTS)),
        [FIGURES_KEY]: figures,
      };
    }),
  };
}

// ---------------------------------------------------------------------------
// Tenant-supplied revenue (#508; slice 7 §9)
//
// ⚠ **NOT A CHARGE, AND THE TYPES SAY SO BY NAMING THE RECORD RATHER THAN THE
// MONEY.** UBB neither created nor invoiced this figure: a tenant that bills
// its customers somewhere UBB cannot see states what it earned, per customer
// per period, and UBB admits it for analytics. Every surface consuming one has
// to be able to say that — which is why `source_reference` and
// `recognition_method` travel on the row rather than being summed away, and why
// nothing here narrows one to a bare amount.

/** What a tenant states it earned from one customer over one period. */
export type SuppliedRevenueIn = MarginSchemas["TenantSuppliedRevenueIn"];

/** One supplied record, as the tenant stated it. */
export type SuppliedRevenueRecord = MarginSchemas["TenantSuppliedRevenueOut"];

/** One supplied record, and what a window gets of it under one basis. */
export type AttributedSuppliedRevenue = MarginSchemas["AttributedSuppliedRevenueOut"];

/**
 * The window's supplied revenue, under a basis the answer NAMES.
 *
 * ⚠ **`totals` IS A LIST PER CURRENCY AND AN EMPTY ONE IS HOW `unknown` IS
 * SERVED.** It is never a zero: a tenant that has supplied nothing covering
 * this window has revenue UBB does not know, so margin is unavailable there
 * rather than nil. A renderer that coalesces this to `0` states a figure the
 * server deliberately refused to state, which is the defect this record exists
 * to end.
 */
export type SuppliedRevenueWindow = MarginSchemas["SuppliedRevenueWindowOut"];

export type BusinessMarginOut = MarginSchemas["BusinessMarginOut"];
export type SeatMarginOut = MarginSchemas["SeatMarginOut"];
export type BusinessMarginTotals = MarginSchemas["BusinessMarginTotals"];
export type PeriodWindow = MarginSchemas["PeriodWindow"];

// ---------------------------------------------------------------------------
// Platform (create customer)

export type CreateCustomerRequest = PlatformSchemas["CreateCustomerRequest"];
export type CustomerResponse = PlatformSchemas["CustomerResponse"];

/**
 * Who a customer is, by the identity UBB assigned them.
 *
 * ⚠ **READ FROM ITS OWN ROUTE SINCE #501.** One customer's margin used to
 * publish `external_id` beside its figures, and that was the only place a
 * surface holding UBB's id could learn the tenant's own word for a customer.
 * The one economic query groups by identity and publishes no external id —
 * a tenant's vocabulary is not a measure — so the capability moved to
 * `GET /platform/customers/{customer_id}`, which is about identity and says
 * nothing about money.
 *
 * It is load-bearing rather than decorative: the subscription lifecycle is
 * addressed by the EXTERNAL id while every metering and billing read is
 * addressed by the UUID, so this is what bridges them.
 */
export type CustomerIdentity = PlatformSchemas["CustomerIdentityOut"];


// ---------------------------------------------------------------------------
// Billing (wallet, grants, customer spend pool, wallet policy)

export type BalanceResponse = BillingSchemas["BalanceResponse"];
export type WalletTransactionOut = BillingSchemas["WalletTransactionOut"];
export type GrantOut = BillingSchemas["GrantOut"];
export type CreateGrantRequest = BillingSchemas["CreateGrantRequest"];
export type CreateTopUpRequest = BillingSchemas["CreateTopUpRequest"];
export type TopUpCheckoutResponse = BillingSchemas["TopUpCheckoutResponse"];
export type WithdrawRequest = BillingSchemas["WithdrawRequest"];
export type WithdrawResponse = BillingSchemas["WithdrawResponse"];
export type CreditRequest = BillingSchemas["CreditRequest"];
export type DebitRequest = BillingSchemas["DebitRequest"];
export type DebitCreditResponse = BillingSchemas["DebitCreditResponse"];
export type AffordabilityResponse = BillingSchemas["AffordabilityResponse"];
export type CustomerSpendPoolIn = BillingSchemas["CustomerSpendPoolIn"];
export type CustomerSpendPoolOut = BillingSchemas["CustomerSpendPoolOut"];
export type CustomerSpendPoolStatusOut = BillingSchemas["CustomerSpendPoolStatusOut"];
export type CustomerBillingProfileIn = BillingSchemas["CustomerBillingProfileIn"];
export type CustomerBillingProfileOut = BillingSchemas["CustomerBillingProfileOut"];
export type ConfigureAutoTopUpRequest = BillingSchemas["ConfigureAutoTopUpRequest"];
export type StatusResponse = BillingSchemas["StatusResponse"];
export type UsageInvoiceOut = BillingSchemas["UsageInvoiceOut"];

// ---------------------------------------------------------------------------
// Metering (usage analytics + pricing)

// The metering reads are the one query — see the narrowings above.

// ---------------------------------------------------------------------------
// Subscriptions

export type StripeSubscriptionOut = SubscriptionSchemas["StripeSubscriptionOut"];
export type SubscriptionInvoiceOut = SubscriptionSchemas["SubscriptionInvoiceOut"];
export type SubscribeIn = SubscriptionSchemas["SubscribeIn"];

// ---------------------------------------------------------------------------
// Local interfaces for the contract's UNTYPED bodies.
// [backend-verified shape — see discovery spec]

/**
 * One day of the Usage tab's series, narrowed from the one query's rows.
 *
 * ⚠ **THE ROUTE THIS ONCE NAMED IS GONE (#501)** and the sentence outlived it.
 * What the tab reads is `GET /metering/analytics/economics` bucketed by day,
 * filtered to the customer and asked for every measure; the narrowing is
 * `toTimeseriesPoints` above.
 *
 * No grouped-value field, and that is still the tab's own choice rather than
 * the contract's: it sends no `group_by`, so every row is that day's whole
 * window of work and the chart plots bucket, cost, revenue and count.
 */
export interface TimeseriesPoint {
  /** The bucket's opening instant, as the answer states it. */
  bucket: string;
  /** `statedValue` of the figures below — a GAP where the state states none. */
  provider_cost_micros: number | null;
  revenue_micros: number | null;
  event_count: number | null;
  /** The figures behind the numbers, each carrying its own day's counts —
   *  because an unresolved cost belongs to the day it fell in. */
  [FIGURES_KEY]: PlottedFigures;
}

// ---------------------------------------------------------------------------
// Narrowing — field-by-field coercion of the untyped bodies above. This is
// the ONLY place a cast-like assertion may live for these shapes; everything
// is rebuilt with typeof guards (unknown fields default safely).

// ⚠ THE DEFENSIVE TIMESERIES NARROWING IS GONE (#501). It read an untyped
// `series[]` key by key, degrading a missing number to zero, because the route
// left its rows `additionalProperties: true` and nothing in the generated types
// could hold the console's read to them. The one economic query DECLARES its
// row: a key that moves is a contract break the gates see, so there is nothing
// left to defend against and `toTimeseriesPoints` above reads it directly.

// ⚠ `narrowPastLimitReport` AND THE FOUR SHAPES IT NARROWED ARE DELETED (#466).
// They narrowed the untyped body of the per-customer report of what was spent
// past a stop; that route, its module and its schema are gone, and the
// customer's Usage tab hosts Stops and breaches — typed rows, injected by the
// route from the spend-controls feature — in the section's place.

// ⚠ `narrowAssignResult` AND `AssignRateCardResult` ARE DELETED (#368).
// They narrowed the untyped body of the route that assigned a book to a
// customer; that record and its route are gone, and a customer's book
// comes from their plan.
