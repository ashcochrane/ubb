// A total beside the count of what it left out, and what it may be SAID to be
// (#424; lifted out of the tasks feature in #466).
//
// NO NUMBER NOBODY KNOWS RENDERS AS A ZERO AMOUNT (#155 §9.2). A total arrives
// as a figure beside a COUNT of what the figure could not include —
// `incompleteTotal` and `incompletePriceTotal` in `@/lib/economic-scenarios`
// — and the count is what says whether the figure is a figure, a floor, or
// nothing at all. That is the reading `@/lib/supplier-cost` gives every other
// total in the console; what is different here is the THIRD outcome.
// Elsewhere a total whose resolved part sums to nothing renders as an
// absence; a surface that puts totals in a column beside real zeros — a run
// that ran nothing, an episode that itemised nothing — and beside amounts
// that do not apply cannot use a dash for it, because a column of dashes
// could not tell a reader which of the three they were looking at. So it
// renders as UNKNOWN, in a word. All three are distinct, and none is `$0.00`.
//
// IT SITS IN `lib/` because two features read a total this way: the runs
// surface (`features/tasks/lib/runs.ts`, where the reading was written) and
// Stops and breaches (`features/spend-controls`), whose itemised events carry
// the same pair on every row and on every family's total. The console's
// imports only flow down, so the reading moved here the day the second feature
// rendered it — the rule `@/lib/pricing-mode` states for the pricing method
// (#425). Each feature keeps the readers that are its own: what a RUN's price
// total means depends on how the run was sold, and that decision stays with
// the runs surface.

import { formatMicros } from "@/lib/format";
import { AT_LEAST } from "@/lib/supplier-cost";

/**
 * The wording for a total none of whose parts UBB has learned.
 *
 * Console copy, and NOT the catalogue's `pricing_status.unknown` or
 * `costing_status.unresolved`, though the catalogue words both. Those are the
 * states of ONE posting; a total is not in a state. It is an amount beside a
 * COUNT of what it left out, with no registry value of its own for the
 * catalogue to word — `incompleteTotal` in `@/lib/economic-scenarios` makes
 * the same point, and `at least` beside it is copy of the same kind.
 */
export const UNKNOWN_TOTAL = "Unknown";

/**
 * A total and what it is worth as a statement.
 *
 * A union rather than a string, so a renderer branches on WHICH reading it
 * holds and cannot coalesce one into a number: `figure` is the amount, `floor`
 * is an amount that was spent — or will be charged — AT LEAST, and `unknown`
 * is no amount at all. `eventsLeftOut` is the count the total could not
 * include, whichever side's count that is.
 */
export type TotalReading =
  | { readonly kind: "figure"; readonly micros: number }
  | { readonly kind: "floor"; readonly micros: number; readonly eventsLeftOut: number }
  | { readonly kind: "unknown"; readonly eventsLeftOut: number };

/**
 * The decision every total makes, once.
 *
 *   nothing left out          → the figure
 *   left out, amount above 0  → a floor
 *   left out, amount at 0     → unknown: UBB knows no amount here
 *
 * A total whose parts all resolved to nothing, with nothing left out, is a
 * FIGURE of zero — a real zero, and it renders as one.
 */
export function readTotal(micros: number, eventsLeftOut: number): TotalReading {
  if (eventsLeftOut <= 0) return { kind: "figure", micros };
  if (micros === 0) return { kind: "unknown", eventsLeftOut };
  return { kind: "floor", micros, eventsLeftOut };
}

export function describeTotal(reading: TotalReading, currency: string): string {
  switch (reading.kind) {
    case "figure":
      return formatMicros(reading.micros, currency);
    case "floor":
      return `${AT_LEAST} ${formatMicros(reading.micros, currency)}`;
    case "unknown":
      return UNKNOWN_TOTAL;
  }
}

/** "2 events have" / "1 event has" — the subject of every sentence about what a total left out. */
export function eventsHave(count: number): string {
  return `${count.toLocaleString()} ${count === 1 ? "event has" : "events have"}`;
}
