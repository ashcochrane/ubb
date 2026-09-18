// What a measure of the one economic query is SAID as (#510; slice 7 §19).
//
// `measure_status` is the fact the one query publishes beside every figure, and
// this is the console's one reading of it. Five values the registry declares,
// and they are five different facts — not five decorations on one number:
//
//   known                                 the amount
//   incomplete                            a BOUND, with the count that bounds it
//   unavailable_at_requested_grain        the state, never an amount: the money
//                                         exists and is stated as context, at the
//                                         grain it can be placed
//   unavailable_outside_retention_horizon the state, with the day the series can
//                                         start — never zero, never "no usage"
//   not_applicable                        the state — never known, never within
//                                         anything
//
// and a sixth the server may one day send renders as the token it is, marked,
// through `components/shared/open-set-value.tsx` (slice 6 §18). ⚠ **UNKNOWN IS
// NEVER A ZERO, ANYWHERE.** A chart that drops what it cannot resolve does not
// draw a lower bound; it draws a number wrong in an unknown direction, and that
// number gets used to set a price.
//
// Identity is the registry's (`@/lib/vocabulary`), the words the catalogue's
// (`@/locales`), and the rules below console copy — the split `@/lib/products`,
// `@/lib/customer-price` and `@/lib/supplier-cost` all make. It sits in `lib/`
// because four features render a measure: the dashboard, the customers page,
// billing and the events page.
//
// ⚠ **THE MARGIN IS THE MEASURE THIS MODULE EXISTS TO GET RIGHT.** The query
// derives its state from BOTH sides (§15, `queries.py::_margin`), and a revenue
// side reading `known` over a cost nobody resolved is the honest rendering of a
// dishonest input that #473 owns — so nothing here reads the revenue side's
// state as evidence about the margin. What decides which way an incomplete
// margin is a bound is which side is short, and the figure carries both counts
// for exactly that reason (`MeasureFigure` in `@/lib/economic-query`).

import {
  CUSTOMER_REVENUE,
  GROSS_MARGIN,
  isNoFigureState,
  RECORDED_EVENTS,
  statedShare,
  statedValue,
  type EconomicsAnswer,
  type MeasureFigure,
  type NoFigureState,
} from "@/lib/economic-query";
import {
  formatCalendarDate,
  formatEventCount,
  formatMicros,
  formatPercent,
} from "@/lib/format";
import { UBB_AXIS_TITLES, type UbbAxis } from "@/lib/grouping-axis";
import { ABSENT_LABEL, labelMap, tenantDefinedLabel } from "@/lib/localisation";
import { AT_LEAST, AT_MOST, partialTotalNote } from "@/lib/supplier-cost";
import { eventsHave } from "@/lib/total-reading";
import {
  ANALYTICS_MEASURE_LABEL_KEYS,
  MEASURE_STATUS_LABEL_KEYS,
  type MeasureStatus,
} from "@/lib/vocabulary";

/** The catalogue's name for what a measure's figure is worth. */
export const measureStatusLabel = labelMap(MEASURE_STATUS_LABEL_KEYS);

/**
 * The catalogue's name for a measure — for where a surface names a measure BY
 * VALUE, chosen at run time (which one a chart could draw), rather than titling
 * a fixed slot. A card or a column whose measure is fixed keeps the console's
 * own copy for that slot ("Provider cost (COGS)"); a sentence saying which
 * measure the lines turned out to be says the registry's word for it.
 */
export const measureLabel = labelMap(ANALYTICS_MEASURE_LABEL_KEYS);

/**
 * What each state means for the person reading the figure.
 *
 * Total over the generated type and read by indexing, the
 * `PRICING_STATUS_EXPLANATIONS` shape: a state the registry declares and this
 * has no sentence for is a `tsc` failure rather than a guess.
 */
export const MEASURE_STATUS_EXPLANATIONS = {
  known: "Every input to this figure is resolved, and this is the amount.",
  incomplete:
    "Some inputs to this figure are still unresolved, so it is a bound rather than a total.",
  unavailable_at_requested_grain:
    "UBB has this money and cannot place it this finely — a subscription or a figure you supplied names no supplier, event type or day. Ask a coarser question to see it.",
  unavailable_outside_retention_horizon:
    "This stretch reaches back past the horizon UBB holds these records for, so there is no figure for it — not a zero.",
  not_applicable:
    "This measure does not apply here, so there is no figure to state.",
} as const satisfies Record<MeasureStatus, string>;

/**
 * One measure, as it may be said.
 *
 * The kinds are what a renderer branches on, and they are the five facts in
 * the header less the two the text alone can carry: a known figure and a bound
 * are both TEXT (the bound says so in its own words), a state that states no
 * figure is its NAME plus the sentence that explains it, and a state the build
 * cannot read is its TOKEN, which a component marks. `absent` is the row not
 * carrying the measure at all — nobody asked, so nobody is told anything.
 */
export type MeasureReading =
  | { readonly kind: "absent" }
  | { readonly kind: "figure"; readonly text: string }
  | { readonly kind: "bound"; readonly text: string; readonly note: string | null }
  | {
      readonly kind: "state";
      readonly status: MeasureStatus;
      readonly text: string;
      readonly note: string;
    }
  | { readonly kind: "unfamiliar"; readonly status: string };

/**
 * Which way an incomplete figure can be wrong — or `null` where it can be wrong
 * either way.
 *
 * A cost, a revenue and a count are FLOORS: what they left out can only add.
 * A margin is bounded by whichever side is short — from above by an uncosted
 * event, from below by an unpriced one — and by neither when both are.
 */
function boundOf(figure: MeasureFigure): typeof AT_LEAST | typeof AT_MOST | null {
  if (figure.measure !== GROSS_MARGIN) return AT_LEAST;
  const costShort = figure.unresolved_event_count > 0;
  const priceShort = figure.unpriced_event_count > 0;
  if (costShort && !priceShort) return AT_MOST;
  if (priceShort && !costShort) return AT_LEAST;
  return null;
}

/** The sentence beside a bound, naming the count that makes it one. */
function boundNote(figure: MeasureFigure): string | null {
  const uncosted = figure.unresolved_event_count;
  const unpriced = figure.unpriced_event_count;
  if (figure.measure === CUSTOMER_REVENUE) return unpricedTotalNote(unpriced);
  if (figure.measure !== GROSS_MARGIN) return partialTotalNote(uncosted);
  if (uncosted > 0 && unpriced > 0) {
    return (
      `${eventsHave(uncosted)} a supplier cost UBB has not learned and ` +
      `${eventsHave(unpriced)} a customer price it could not resolve, so the ` +
      `true margin could be higher or lower.`
    );
  }
  if (uncosted > 0) {
    return `${eventsHave(uncosted)} a supplier cost UBB has not learned, so the true margin is lower.`;
  }
  if (unpriced > 0) {
    return `${eventsHave(unpriced)} a customer price UBB could not resolve, so the true margin is higher.`;
  }
  return null;
}

/**
 * The sentence beside a revenue total that left unpriced events out — the
 * price-side twin of `partialTotalNote` in `@/lib/supplier-cost`.
 *
 * `null` where nothing was left out, so a caller renders no element at all.
 */
export function unpricedTotalNote(unpricedEventCount: number): string | null {
  if (unpricedEventCount <= 0) return null;
  return (
    `${eventsHave(unpricedEventCount)} a customer price UBB could not resolve. ` +
    `They are left out of this total, so the true figure is higher.`
  );
}

/** A figure's amount in its own unit — a count for the count measure, money
 *  for the other three. */
function amountText(figure: MeasureFigure, value: number, currency: string): string {
  return figure.measure === RECORDED_EVENTS
    ? formatEventCount(value)
    : formatMicros(value, currency);
}

/**
 * How one measure may be said.
 *
 * ⚠ **THE STATE IS READ FIRST AND THE NUMBER ONLY WHERE THE STATE ALLOWS.** A
 * number arrives beside `unavailable_at_requested_grain` (the part of a revenue
 * that could be placed) and a zero could arrive beside `not_applicable`; under
 * neither is it the figure, and under a state this build cannot read no number
 * is vouched for at all.
 *
 * A floor of ZERO states no amount — the `supplierCostTotal` rule, for the
 * reason it gives: "at least $0.00" is the string this surface exists to
 * delete, with a prefix in front of it.
 */
export function readMeasure(
  figure: MeasureFigure | null,
  currency: string,
): MeasureReading {
  if (figure === null) return { kind: "absent" };
  if (isNoFigureState(figure.status)) {
    return {
      kind: "state",
      status: figure.status,
      text: measureStatusLabel(figure.status),
      note: stateNote(figure.status, figure.available_from),
    };
  }
  const value = statedValue(figure);
  if (figure.status === "known") {
    return value === null
      ? { kind: "absent" }
      : { kind: "figure", text: amountText(figure, value, currency) };
  }
  if (figure.status === "incomplete") {
    const bound = boundOf(figure);
    const note = boundNote(figure);
    if (value === null || (value === 0 && bound === AT_LEAST)) {
      return { kind: "bound", text: ABSENT_LABEL, note };
    }
    const amount = amountText(figure, value, currency);
    return {
      kind: "bound",
      text: bound === null ? `${amount} (${measureStatusLabel("incomplete")})` : `${bound} ${amount}`,
      note,
    };
  }
  return { kind: "unfamiliar", status: figure.status };
}

function stateNote(status: NoFigureState, availableFrom: string | null): string {
  if (status === "unavailable_outside_retention_horizon" && availableFrom !== null) {
    return (
      `UBB holds these records from ${formatCalendarDate(availableFrom)}. The ` +
      `stretch before that is no longer held, so there is no figure for it — not a zero.`
    );
  }
  return MEASURE_STATUS_EXPLANATIONS[status];
}

/**
 * A reading as plain text, for a place that holds text only — a card's
 * subtitle, a tooltip row, a `title`.
 *
 * An unfamiliar state is its token VERBATIM, never humanised (ADR-0008 §4.3);
 * a surface able to render an element marks it with `MeasureValue` instead.
 */
export function readingText(reading: MeasureReading): string {
  switch (reading.kind) {
    case "absent":
      return ABSENT_LABEL;
    case "unfamiliar":
      return reading.status;
    default:
      return reading.text;
  }
}

/** The sentence that goes beside a reading, where it has one. */
export function readingNote(reading: MeasureReading): string | null {
  return reading.kind === "bound" || reading.kind === "state" ? reading.note : null;
}

/**
 * The sentence beside a figure, for a place that holds text only — or
 * `undefined` where it has none, so a card renders no subtitle at all rather
 * than a blank line that reads as a layout bug.
 */
export function figureNote(
  figure: MeasureFigure | null,
  currency: string,
): string | undefined {
  return readingNote(readMeasure(figure, currency)) ?? undefined;
}

/**
 * The sentence a figure owes where it states NO figure — and `undefined` where
 * it states one, bound or whole.
 *
 * For a card whose bound is already explained beside it: a margin's bound comes
 * from the same uncosted events the cost card's note counts, and saying it on
 * both would make a caveat out of one fact. The bound's own reason still rides
 * on the value's hover (`MeasureValue`); what a card cannot leave unsaid is
 * why there is no figure at all.
 */
export function noFigureNote(
  figure: MeasureFigure | null,
  currency: string,
): string | undefined {
  const reading = readMeasure(figure, currency);
  return reading.kind === "state" ? reading.note : undefined;
}

/**
 * A margin card's subtitle: the share of revenue where the margin states a
 * figure and there is revenue to take a share of, and otherwise the sentence the
 * margin's own state owes.
 */
export function shareNote(
  margin: MeasureFigure | null,
  revenue: MeasureFigure | null,
  currency: string,
): string | undefined {
  if (statedValue(margin) === null) return figureNote(margin, currency);
  const share = readShare(margin, revenue);
  return share.kind === "absent" ? undefined : `${readingText(share)} margin`;
}

/** Whether a figure states a loss — the one fact a renderer styles in red. A
 *  figure it does not state is neither a loss nor a gain. */
export function isNegative(figure: MeasureFigure | null): boolean {
  const value = statedValue(figure);
  return value !== null && value < 0;
}

/**
 * The margin as a share of the revenue it was drawn from.
 *
 * ⚠ **IT REPLACES A PERCENTAGE THAT ANSWERED ZERO FOR A MARGIN UBB WOULD NOT
 * STATE**, which the customer list then printed as `0.0%` beside the dash for
 * the margin itself. Where the margin states no figure, the share is the
 * margin's own state; where the revenue states none or states nothing, there is
 * no share of it to state.
 *
 * The bound follows the MARGIN's: an uncosted event lowers the numerator alone,
 * and an unpriced one raises numerator and denominator by the same amount,
 * which can only move a share of at most 100% upward.
 */
export function readShare(
  margin: MeasureFigure | null,
  revenue: MeasureFigure | null,
): MeasureReading {
  if (margin === null) return { kind: "absent" };
  if (statedValue(margin) === null) return readMeasure(margin, "");
  const stated = statedShare(margin, revenue);
  if (stated === null) return { kind: "absent" };
  const share = formatPercent(stated);
  if (margin.status === "known" && revenue?.status === "known") {
    return { kind: "figure", text: share };
  }
  const bound = boundOf(margin);
  return {
    kind: "bound",
    text: bound === null ? `${share} (${measureStatusLabel("incomplete")})` : `${bound} ${share}`,
    note: boundNote(margin),
  };
}

// ---------------------------------------------------------------------------
// The coarser figure, where a finer question could not place it (§5).

type RevenueContextRow = EconomicsAnswer["context"][number];

/** Where a context figure came from, in words — and a source this build has
 *  never met as its token, never a guess. */
function sourceWords(source: string): string {
  if (source === "subscription") return "subscriptions";
  if (source === "tenant_supplied") return "figures you supplied";
  return source;
}

const BUCKET_WORDS: Readonly<Record<string, string>> = {
  hour: "per hour",
  day: "per day",
  month: "per month",
};

const BUCKETS_FINEST_FIRST = ["hour", "day", "month"];

/**
 * The sentence stating revenue the answer could not place, or null where it
 * placed everything.
 *
 * ⚠ **"NEVER SILENTLY DROP" IS THIS SENTENCE.** A revenue measure unavailable
 * at the grain asked for states no figure, and a chart over it draws no margin
 * — so without this the tenant sees neither the money nor the reason. The
 * answer's `context` carries the money and the axes and bucket at which asking
 * again WOULD place it; this says both, in the terms a tenant can act on.
 *
 * The axes are the ones EVERY row admits and the bucket the coarsest any row
 * needs, which is the query's own rule for whether a question can place them
 * all (`queries.py::_contributions_are_attributable`).
 */
export function revenueContextNote(
  context: readonly RevenueContextRow[],
  currency: string,
): string | null {
  if (context.length === 0) return null;
  const total = context.reduce((sum, row) => sum + row.amount_micros, 0);
  const sources = [...new Set(context.map((row) => sourceWords(row.source)))];
  const axes = context
    .map((row) => row.attributable_axes)
    .reduce((kept, next) => kept.filter((axis) => next.includes(axis)));
  const bucket = context
    .map((row) => row.attributable_bucket)
    .reduce((coarsest, next) =>
      BUCKETS_FINEST_FIRST.indexOf(next) > BUCKETS_FINEST_FIRST.indexOf(coarsest)
        ? next
        : coarsest,
    );
  const where =
    axes.length === 0
      ? "on the whole window"
      : `by ${axes.map(axisWords).join(" or ")}`;
  return (
    `${formatMicros(total, currency)} of revenue from ${sources.join(" and ")} ` +
    `can only be placed ${where}, ${BUCKET_WORDS[bucket] ?? bucket} — so no ` +
    `margin is drawn at this grain.`
  );
}

/**
 * The sentence an answer owes where its window reaches back past the records
 * it reads — or null where it does not.
 *
 * ⚠ **THIS IS WHAT STANDS WHERE "NO USAGE" WOULD OTHERWISE BE.** A grouped
 * question over a stretch whose records were released has no rows to carry a
 * state on (#500), so the only thing the page receives is an empty list — and
 * the one reading of it that is certainly unproven is that nothing happened.
 *
 * ⚠ **THE MEASUREMENT CASE IS THE PRUNED ONE**, and it is worded as such: the
 * records a grouping by what was measured reads are the measurement records
 * `prunedMeasurements()` describes one posting at a time, removed on schedule
 * at their horizon. The economic case is the longer clock, and says so.
 */
export function horizonNote(caveats: {
  readonly held_from: string | null;
  readonly measurement_horizon: boolean;
}): string | null {
  if (caveats.held_from === null) return null;
  const from = formatCalendarDate(caveats.held_from);
  return caveats.measurement_horizon
    ? `Measurements before ${from} have been pruned at their retention horizon, ` +
        `so a grouping by what was measured has nothing to read before then. That ` +
        `stretch is pruned — it is not a stretch with no usage.`
    : `UBB holds economic records from ${from}. Before that this window has no ` +
        `figure — not a zero, and not a stretch with no usage.`;
}

/** An axis the context names, in words: UBB's own axes by UBB's word, any other
 *  as the tenant declared it. */
function axisWords(name: string): string {
  return name in UBB_AXIS_TITLES
    ? UBB_AXIS_TITLES[name as UbbAxis].toLowerCase()
    : tenantDefinedLabel(name);
}
