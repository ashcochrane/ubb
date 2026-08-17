// What the console may say about a supplier cost it does not fully know.
//
// UBB learns a supplier cost from a Cost Rate or from the caller reporting one.
// Since #317 it may learn NEITHER, and the posting then carries `unresolved`
// with a NULL amount rather than a zero — because zero is a resolved amount and
// means something else entirely (ADR-0007 §2). Every total built over those
// postings sums the ones it resolved and skips the ones it did not, so a total
// beside a non-zero count is a FLOOR rather than a figure, and the margin
// computed from it is a CEILING.
//
// That is the backend's own statement rather than a console inference:
// `get_revenue_analytics` says the markup "is billed MINUS THE RESOLVED
// provider cost, so where the count is non-zero it is an upper bound rather
// than a figure". This module is where the console stops rendering both of them
// as though they were whole.
//
// A MARKER STATES ONLY THAT SOMETHING IS MISSING; "at least $4.20" STATES THE
// ECONOMIC MEANING. A badge reading `incomplete` beside a number leaves the
// reader to work out which way the number is wrong, and the flattering reading —
// a cost that is lower than it really is, a margin that is higher — is the one
// they will reach for. Saying it in the amount itself makes the worst-case
// misreading impossible rather than unlikely.
//
// THE COMPLETENESS QUESTION READS THE COUNT AND NOTHING ELSE, and the case that
// makes this worth writing down is mixed derivation. A Task holding both
// calculated and reported events is COMPLETE when nothing is missing: how a
// cost was derived is not a defect in it, and a footnote on every mixed total is
// a footnote on almost every total. Provenance belongs on the receipt as
// information — the pricing engine's recorded reasons — never as a caveat on a
// number that is whole.
//
// THE SURFACES THIS GOVERNS ARE DERIVED, NOT LISTED FROM MEMORY. They are the
// console's own readers of a supplier cost — or of a margin computed against
// one — intersected with the responses that carry a completeness count:
//
//   dashboard/stat-row              MarginSummaryOut
//   dashboard/customer-economics-table, customers/customers-page
//                                   CustomerMarginListRow
//   dashboard/unprofitable-alert    UnprofitableCustomerRow (margin only)
//   customers/overview-tab          CustomerMarginOut
//   customers/business-rollup       SeatMarginOut + BusinessMarginTotals
//   customers/usage-tab, events/analytics-strip
//                                   UsageAnalyticsResponse
//   billing/revenue-section         RevenueAnalyticsResponse
//   events/task-section             CloseTaskResponse
//   customers/past-limit-section, events/past-limit-panel
//                                   PastLimitReportResponse — episodes, their
//                                   itemized events and the per-limit totals
//   billing/revenue-chart, dashboard/revenue-cost-chart,
//   customers/margin-trend-chart, customers/usage-timeseries-chart,
//   events/usage-timeseries-chart   the per-point rows of the responses above
//
// ⚠ DERIVING THAT LIST FROM THE CONTRACT'S TYPED SCHEMAS MISSES THE UNTYPED
// ONES, AND THAT IS HOW THE PAST-LIMIT REPORT WAS FIRST WRITTEN DOWN HERE AS
// HAVING NO COMPLETENESS AT ALL. `PastLimitReportResponse` is
// `additionalProperties: true`, so its episodes, itemized rows and per-limit
// totals carry `unresolved_event_count` and a nullable supplier cost with no
// schema saying so — #328 put them there and only `api/v1/past_limit.py` shows
// it. A surface whose data is untyped is exactly the surface a schema-derived
// enumeration cannot see, so every untyped response a console reader touches
// has to be read at the server rather than in the spec.
//
// ONE console cost surface is deliberately absent, and it is absent by
// construction rather than by omission: `dashboard/grouping-field-breakdown`
// renders BILLED cost, which is NOT NULL at the column and therefore whole.
// #152's Tasks page, spend-controls nav item and breach episode report are not
// built and not adopted here; the past-limit surfaces above are the ones that
// already exist, not that report.
//
// Per-EVENT surfaces are a different rendering and live below the totals: one
// event has no count, it has the mark itself. Those are the event receipt, the
// event ledger's cost column, the developer console's recorded response and the
// past-limit report's itemized rows.

import { formatMicros, formatPercent } from "@/lib/format";
import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import {
  COSTING_STATUS_LABEL_KEYS,
  COSTING_STATUS_VALUES,
  UNRESOLVED_REASON_LABEL_KEYS,
  type CostingStatus,
} from "@/lib/vocabulary";

/** The wording for a total that can only be higher than it says. */
export const AT_LEAST = "at least";

/** The wording for a figure that can only be lower than it says. */
export const AT_MOST = "at most";

/**
 * Any response row carrying the count of events whose supplier cost UBB never
 * learned.
 *
 * Structural on purpose: every wire row spells it `unresolved_event_count`, so
 * a caller passes the response object it already holds and cannot pass a total
 * without the fact that qualifies it. That is the same pairing rule
 * `@/lib/economic-scenarios` applies to a measurement bag and its status, and
 * for the same reason — the defect these guard against is a fixture, or a call
 * site, that takes half.
 */
export interface CostCompleteness {
  readonly unresolved_event_count: number;
}

/** Whether a total built over supplier costs left any of them out. */
export function isPartial(completeness: CostCompleteness): boolean {
  return completeness.unresolved_event_count > 0;
}

/**
 * A supplier-cost total, said in a way that cannot be read as whole when it is
 * not.
 *
 * Three outcomes, and the third is the one "at least" alone gets wrong:
 *
 *   nothing missing        → `$4.20`, the figure it is
 *   missing, floor above 0 → `at least $4.20`
 *   missing, floor at 0    → the absent marker
 *
 * The last case is a window whose resolved costs sum to nothing while events
 * remain uncosted. Its floor really is zero, and rendering `at least $0.00`
 * would put the exact string this slice exists to delete back on the page with
 * a prefix in front of it — a reader takes it for "this was free". UBB knows no
 * amount here, so it states no amount, and the count beside it says why.
 */
export function supplierCostTotal(
  micros: number,
  completeness: CostCompleteness,
  currency: string,
): string {
  if (!isPartial(completeness)) return formatMicros(micros, currency);
  if (micros === 0) return ABSENT_LABEL;
  return `${AT_LEAST} ${formatMicros(micros, currency)}`;
}

/**
 * A margin or markup computed against a supplier cost that may be partial.
 *
 * Bounded from ABOVE, always, and that stays true when the margin is already
 * negative: the costs UBB has not learned can only take it further down. There
 * is no zero-floor case here — a margin of zero beside missing costs is an
 * honest upper bound, and unlike a cost total it does not read as "free".
 */
export function marginBound(
  micros: number,
  completeness: CostCompleteness,
  currency: string,
  /**
   * How the amount itself is written. Defaulted rather than fixed because one
   * surface — the unprofitable-customer alert — renders margins with an
   * explicit sign, and a bound that quietly dropped the `+` from a thin but
   * positive margin would change what the number says while claiming only to
   * qualify it.
   */
  format: (micros: number, currency: string) => string = formatMicros,
): string {
  const amount = format(micros, currency);
  return isPartial(completeness) ? `${AT_MOST} ${amount}` : amount;
}

/** The same bound on a margin PERCENTAGE, which is derived from the same sum. */
export function marginPercentBound(
  percent: number,
  completeness: CostCompleteness,
): string {
  const formatted = formatPercent(percent);
  return isPartial(completeness) ? `${AT_MOST} ${formatted}` : formatted;
}

/**
 * The sentence beside a partial total, or nothing when the total is whole.
 *
 * Returns `null` rather than an empty string so a caller renders no element at
 * all: a blank line where an explanation used to be is how a caveat starts
 * looking like a layout bug. Console copy, not registry content (ADR-0008 §4),
 * so it carries no label key.
 */
export function partialTotalNote(unresolvedEventCount: number): string | null {
  if (unresolvedEventCount <= 0) return null;
  const events = unresolvedEventCount === 1 ? "event has" : "events have";
  return (
    `${unresolvedEventCount.toLocaleString()} ${events} a supplier cost UBB ` +
    `has not learned. They are left out of this total, so the true figure is ` +
    `higher.`
  );
}

// ---------------------------------------------------------------------------
// One event's own mark
//
// A total has a count; a single posting has the status itself. Identity is the
// registry's (`@/lib/vocabulary`), expression the catalogue's (`@/locales`) —
// the split `@/lib/products` and `events/lib/measurements` both make. This one
// sits in `lib/` because two features read it: the event receipt and the
// developer test console's recorded response.

/** The catalogue's name for a supplier cost's costing status. */
export const costingStatusLabel = labelMap(COSTING_STATUS_LABEL_KEYS);

/**
 * The costing status an UNTYPED response row carries, or `null` if it carries
 * none.
 *
 * The past-limit report is `additionalProperties: true` in the contract, so its
 * itemized rows arrive as `unknown` and something has to decide what a status
 * that is not one of the declared three means. `null` — "the row did not say" —
 * rather than a default, because every available default is a claim: guessing
 * `unresolved` says UBB tried and failed, and guessing `not_applicable` says
 * nothing was owed. A caller renders the absence instead.
 *
 * Membership is tested against the GENERATED value list rather than a literal
 * trio: a second copy of a registry value set in the console is the drift the
 * consumer gates exist to abolish.
 */
export function asCostingStatus(value: unknown): CostingStatus | null {
  return COSTING_STATUS_VALUES.find((declared) => declared === value) ?? null;
}

/** The catalogue's name for WHICH input was missing, when one was. */
export const unresolvedReasonLabel = labelMap(UNRESOLVED_REASON_LABEL_KEYS);

/**
 * What each status means for the person reading a receipt.
 *
 * Total over the generated type and read by indexing rather than through a
 * lookup: a status the registry declares and this constant has no sentence for
 * is a `tsc` failure, which is the difference between console copy and a guess.
 */
export const COSTING_STATUS_EXPLANATIONS = {
  known: "UBB knows what this cost you.",
  unresolved:
    "UBB has not learned what this cost. The amount is missing rather than zero, and it is left out of every total until it arrives.",
  not_applicable:
    "This event's type declares no supplier cost, so there is none to learn and nothing is missing from any total.",
} as const satisfies Record<CostingStatus, string>;
