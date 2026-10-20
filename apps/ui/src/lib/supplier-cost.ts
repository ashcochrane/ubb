// What the console may say about a supplier cost it does not fully know.
//
// UBB learns a supplier cost from a Cost Rate or from the caller reporting one.
// Since #317 it may learn NEITHER, and the posting then carries `unresolved`
// with a NULL amount rather than a zero — because zero is a resolved amount and
// means something else entirely (ADR-0007 §2). Every total built over those
// postings sums the ones it resolved and skips the ones it did not, so a total
// beside a non-zero count is the SUM OF WHAT RESOLVED rather than the total,
// and so is the margin computed from it.
//
// ⚠ IT IS NO BOUND, IN EITHER DIRECTION (#603, ADR-0020 §6). This module used
// to say "at least" on such a total and "at most" on the margin, because a
// cost left out could only add. A quantity may now be negative, so an amount
// left out may move the total either way: the retired words promised a
// direction nothing guarantees. The published contract says it the same way —
// `EconomicMeasureOut.status` reads `incomplete` when the figure is the sum of
// the inputs that resolved, and the count beside it says how many are not
// included. This module is where the console stops rendering either as though
// it were whole.
//
// ⚠ IT USED TO CITE `get_revenue_analytics`, one of five backend definitions
// of revenue and margin that each said this in their own words. All five are
// deleted and the one query says it once, per MEASURE rather than per
// response — which is why the roster below now names one schema where it used
// to name six.
//
// THE MARK RIDES IN THE AMOUNT ITSELF — "$4.20 (Incomplete)" — so no reader
// takes a partial figure for a whole one: a badge somewhere else on the row is
// a badge somebody skims past. It names the STATE, the catalogue's word for
// `measure_status.incomplete`, and no direction, because there is none to
// name; the sentence beside it says how many amounts are not included.
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
//   dashboard/unprofitable-alert    UnprofitableCustomerRow (margin only)
//   customers/business-rollup       SeatMarginOut + BusinessMarginTotals
//   events/task-section             CloseTaskResponse
//   spend-controls/stops-and-breaches (its own tab and the customer's
//   Usage tab)                      StopsAndBreachesResponse — episodes, their
//                                   itemised events and the per-family totals
//
// ⚠ **THE ONE ECONOMIC QUERY'S SURFACES LEFT THIS LIST IN #510.** Its stat
// cards, its tables, its breakdown and its charts read `EconomicsOut`, which carries
// a STATE per measure per row rather than a bare count — and a count can only
// say "incomplete", while that state also says "unavailable at this grain",
// "outside the retention horizon" and "not applicable". They read
// `@/lib/measure-state` now, which applies this module's rule
// (`partialTotalNote`, the zero-sum absence) to an incomplete cost and adds
// the readings a count could never carry. This module keeps the surfaces
// whose responses still publish a count and no state.
//
// ⚠ DERIVING THAT LIST FROM THE CONTRACT'S TYPED SCHEMAS MISSES THE UNTYPED
// ONES, AND THAT IS HOW THE REPORT STOPS AND BREACHES REPLACED WAS FIRST
// WRITTEN DOWN HERE AS HAVING NO COMPLETENESS AT ALL. That report's response
// was `additionalProperties: true`, so its episodes, itemised rows and
// per-stop totals carried `unresolved_event_count` and a nullable supplier
// cost with no schema saying so (#328, #330); it retired in #466 and its
// successor publishes the same facts as typed rows. The rule survives it: a
// surface whose data is untyped is exactly the surface a schema-derived
// enumeration cannot see, so every untyped response a console reader touches
// has to be read at the server rather than in the spec.
//
// Per-EVENT surfaces are a different rendering and live below the totals: one
// event has no count, it has the mark itself. Those are the event receipt, the
// event ledger's cost column, the developer console's recorded response and
// Stops and breaches' itemised rows.

import { formatMicros, formatPercent } from "@/lib/format";
import { ABSENT_LABEL, labelMap } from "@/lib/localisation";
import {
  COSTING_STATUS_LABEL_KEYS,
  MEASURE_STATUS_LABEL_KEYS,
  UNRESOLVED_REASON_LABEL_KEYS,
  type CostingStatus,
} from "@/lib/vocabulary";

const stateWord = labelMap(MEASURE_STATUS_LABEL_KEYS);

/**
 * A figure, marked where it is computed over a total that leaves amounts out:
 * "$4.20 (Incomplete)" or "$4.20". The caller states WHEN it is incomplete —
 * that is the per-surface rule — and this is the one spelling of it, for an
 * amount, a share and a margin alike. The mark is the catalogue's word for
 * `measure_status.incomplete` and names no direction (#603, ADR-0020 §6).
 */
export function incompleteFigure(text: string, incomplete: boolean): string {
  return incomplete ? `${text} (${stateWord("incomplete")})` : text;
}

/** A whole-number share, marked where it is over an incomplete total. */
export function shareOver(percentage: number, incomplete: boolean): string {
  return incompleteFigure(`${percentage}%`, incomplete);
}

/** An amount, marked where it is over an incomplete total. */
export function amountOver(micros: number, currency: string, incomplete: boolean): string {
  return incompleteFigure(formatMicros(micros, currency), incomplete);
}

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
 * Three outcomes, and the third is the one a mark alone gets wrong:
 *
 *   nothing missing           → `$4.20`, the figure it is
 *   missing, resolved sum ≠ 0 → `$4.20 (Incomplete)`
 *   missing, resolved sum = 0 → the absent marker
 *
 * The last case is a window whose resolved costs sum to nothing while events
 * remain uncosted. Rendering `$0.00` there, marked or not, would put the exact
 * string this slice exists to delete back on the page — a reader takes it for
 * "this was free". UBB knows no total here, so it states no amount, and the
 * count beside it says why.
 */
export function supplierCostTotal(
  micros: number,
  completeness: CostCompleteness,
  currency: string,
): string {
  if (!isPartial(completeness)) return formatMicros(micros, currency);
  if (micros === 0) return ABSENT_LABEL;
  return incompleteFigure(formatMicros(micros, currency), true);
}

/**
 * A margin or markup computed against a supplier cost that may be partial,
 * marked incomplete wherever the cost is. There is no zero-sum case here — a
 * margin of zero beside missing costs does not read as "free" the way a cost
 * total does, so it states its figure, marked.
 */
export function marginOver(
  micros: number,
  completeness: CostCompleteness,
  currency: string,
  /**
   * How the amount itself is written. Defaulted rather than fixed because one
   * surface — the unprofitable-customer alert — renders margins with an
   * explicit sign, and a mark that quietly dropped the `+` from a thin but
   * positive margin would change what the number says while claiming only to
   * qualify it.
   */
  format: (micros: number, currency: string) => string = formatMicros,
): string {
  return incompleteFigure(format(micros, currency), isPartial(completeness));
}

/** The same mark on a margin PERCENTAGE, which is derived from the same sum. */
export function marginPercentOver(
  percent: number,
  completeness: CostCompleteness,
): string {
  return incompleteFigure(formatPercent(percent), isPartial(completeness));
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
    `has not learned. They are not included in this total, which is the sum of ` +
    `the costs UBB has.`
  );
}

// ---------------------------------------------------------------------------
// One event's own mark
//
// A total has a count; a single posting has the status itself. Identity is the
// registry's (`@/lib/vocabulary`), expression the catalogue's (`@/locales`) —
// the split `@/lib/products` and `events/lib/measurements` both make. This one
// sits in `lib/` because two features read it: the event receipt and the
// Code Builder's Verify acknowledgements (`developers/components/
// acknowledgement-card.tsx`, which was the test console's response card until
// #581 deleted the console).

/** The catalogue's name for a supplier cost's costing status. */
export const costingStatusLabel = labelMap(COSTING_STATUS_LABEL_KEYS);

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
