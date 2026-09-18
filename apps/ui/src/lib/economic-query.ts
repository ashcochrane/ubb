// Reading the one economic query, in one place.
//
// Nine published routes collapsed into `GET /metering/analytics/economics`
// (#501), and five console features read what those routes used to serve. The
// shape they now read is the same for all five — a row per bucket per group,
// each carrying one entry per requested measure — so the narrowing lives here
// rather than five times over.
//
// ⚠ **THE MEASURE NAMES ARE THE REGISTRY'S (#510).** They were literals until
// the ticket that renders the measure states, because typing them against the
// generated vocabulary made this console a declared consumer of the measure
// concept — an act with a ledger entry behind it. That ticket is this one: each
// name is checked against `AnalyticsMeasure` at `tsc`, the whole list IS the
// generated one, and `@/lib/labels` holds the set by reference for the census.
//
// ⚠ **AND A MEASURE IS READ WITH ITS STATE, NEVER AS A BARE AMOUNT.** A null
// means UBB has no figure to state — the stretch is past a retention horizon,
// or a margin could not be attributed at the grain asked for — and a number
// beside `unavailable_at_requested_grain` is a PART of the revenue, not the
// revenue. A helper that answered `0` for the first, or the part for the
// second, would turn "we cannot say" into a claim; that was `orZero`, and every
// narrowing on this console used it until #510. `figureOn` carries the state to
// the renderer, `statedValue` is the one question a chart or a sort may ask of
// it, and `@/lib/measure-state` is what a figure is SAID as.

import type { MeteringSchemas } from "@/api/types";
import {
  axisRequestWord,
  FIELD_KIND,
  ROLLUP_KIND,
} from "@/lib/grouping-axis";
import {
  ANALYTICS_MEASURE_VALUES,
  type AnalyticsMeasure,
  type MeasureStatus,
} from "@/lib/vocabulary";

export type EconomicsAnswer = MeteringSchemas["EconomicsOut"];
export type EconomicRow = MeteringSchemas["EconomicRowOut"];
export type EconomicMeasure = MeteringSchemas["EconomicMeasureOut"];

/** The measures, as the registry spells them — a name it does not declare is a
 *  `tsc` failure here rather than a 422 at the server. */
export const SUPPLIER_COGS = "supplier_cogs" satisfies AnalyticsMeasure;
export const CUSTOMER_REVENUE = "customer_revenue" satisfies AnalyticsMeasure;
export const GROSS_MARGIN = "gross_margin" satisfies AnalyticsMeasure;
export const RECORDED_EVENTS = "recorded_events" satisfies AnalyticsMeasure;

/** The three money measures, which every economic panel on this console asks
 *  for together: a cost with no revenue beside it is half a page. */
export const MONEY_MEASURES = [
  SUPPLIER_COGS,
  CUSTOMER_REVENUE,
  GROSS_MARGIN,
] as const satisfies readonly AnalyticsMeasure[];

/** All four — the money plus the count of recorded work — which is the
 *  registry's whole list, in its order. */
export const EVERY_MEASURE = ANALYTICS_MEASURE_VALUES;

/** The request word for a named FIELD axis, where a call site knows which it wants.
 *
 *  Each axis is `<kind>:<name>`: the kind is what tells a column on the event
 *  apart from a join to a rollup UBB owns, and the server refuses a word that
 *  is on neither list. This builds the `field:` half — the reserved words every
 *  tenant has (`customer`, `provider`, `event_type`, `task_type`,
 *  `subtask_type`) take it as readily as a tenant's own declared key, because
 *  the server tells them apart and the caller does not have to.
 *
 *  ⚠ **THIS IS FOR A CALL SITE THAT NAMES ITS OWN AXIS, NEVER FOR A PICKER.**
 *  All but one of its call sites ask for `field:customer`, because grouping by
 *  the customer IS the question they are asking. A surface OFFERING a choice of
 *  axes reads them off the discovery contract, where the request word arrives
 *  already built and may be a rollup (#506) — prefixing one of those again
 *  would name an axis no tenant has. The word is assembled in one place either
 *  way, in `@/lib/grouping-axis`. */
export const FIELD_AXIS = (name: string) =>
  axisRequestWord({ kind: FIELD_KIND, name });

// ⚠ `orZero` AND `marginPercentOf` WERE HERE AND ARE DELETED (#510), with
// `amountOn` and `eventsOn` below them. `orZero` argued that a revenue UBB
// could not attribute at the grain asked for "is genuinely nothing on that
// row", so summing it as zero was correct — and every narrowing on this
// console then coalesced EVERY no-figure state that way, including a stretch
// past the retention horizon, which is not nothing but unknown. §19's
// never-clauses are the ruling that reverses it: a state that states no figure
// is drawn as the state, and the money that could not be placed is drawn as
// the answer's context. `marginPercentOf` answered zero for a margin UBB would
// not state, and the customer list printed that zero as `0.0%`; `statedShare`
// answers null instead.

/**
 * Descending by a stated figure, with every row that states none LAST.
 *
 * ⚠ **A ROW STATING NO MARGIN SORTS LAST RATHER THAN AS ZERO.** Coercing
 * would file a customer UBB cannot report on among the ones it can, in the
 * middle of the table, which reads as a claim about them. Two tables sort the
 * same rows on the same three keys and this is the comparator both use: the
 * extractor is theirs, because their row types differ; the ORDER is one rule.
 */
export function descendingWithAbsencesLast<Row>(
  measure: (row: Row) => number | null,
): (left: Row, right: Row) => number {
  return (a, b) => {
    const left = measure(a);
    const right = measure(b);
    if (left === null && right === null) return 0;
    if (left === null) return 1;
    if (right === null) return -1;
    return right - left;
  };
}

function measureOn(
  row: EconomicRow | undefined,
  measure: string,
): EconomicMeasure | undefined {
  return row?.measures.find((entry) => entry.measure === measure);
}

/**
 * What each side of the margin left out — the two counts `figureOn` hands the
 * margin, which publishes neither on its own entry.
 *
 * ⚠ **THE TWO COUNTS ARE NOT INTERCHANGEABLE AND EACH BELONGS TO ITS OWN
 * MEASURE.** `unresolved_event_count` rides the SUPPLIER COST and says how many
 * postings carry a cost UBB has not learned; `unpriced_event_count` rides the
 * CUSTOMER REVENUE and says how many carry a price it could not resolve. They
 * are different sets of rows, and they bound the margin in opposite directions
 * — so reading one off the other's measure would caveat a figure against the
 * wrong fact.
 *
 * Zero where a measure states none, because these counts have a floor of zero
 * by construction and their absence means what their zero means: nothing was
 * left out. That is NOT true of an AMOUNT, which is why this coerces and
 * `figureOn` keeps an absent amount null.
 */
function completenessOn(row: EconomicRow | undefined): {
  unresolved_event_count: number;
  unpriced_event_count: number;
} {
  const cost = measureOn(row, SUPPLIER_COGS);
  const revenue = measureOn(row, CUSTOMER_REVENUE);
  return {
    unresolved_event_count: cost?.unresolved_event_count ?? 0,
    unpriced_event_count: revenue?.unpriced_event_count ?? 0,
  };
}

// ---------------------------------------------------------------------------
// A measure as a FIGURE: its value, and the state that says what it is worth.

/**
 * One measure off one row, carrying everything a renderer needs to say it
 * honestly and nothing it could say dishonestly.
 *
 * ⚠ **`status` IS A STRING, NOT `MeasureStatus`, ON PURPOSE.** The generated
 * union is the five values this build knows; the console is downstream of a
 * server that may know a sixth (ADR-003), and a narrowing typed on the union
 * would have to decide what to do with it HERE — which is how a state gets
 * mapped onto the nearest familiar one. It reaches the renderer as itself and
 * renders as the marked token (`@/lib/measure-state`).
 *
 * `value` is micros for the three money measures and a count for
 * `recorded_events`: one field, because the measure's own name says which, and
 * the renderer is the one place that turns either into text.
 *
 * ⚠ **THE MARGIN CARRIES BOTH SIDES' COUNTS.** Its own entry publishes none,
 * and it needs both: an uncosted event can only lower it and an unpriced one
 * can only raise it, so which way an incomplete margin is a bound depends on
 * which side is short — and when both are, it is a bound in neither direction.
 */
export interface MeasureFigure {
  readonly measure: AnalyticsMeasure;
  readonly status: string;
  readonly value: number | null;
  readonly unresolved_event_count: number;
  readonly unpriced_event_count: number;
  readonly available_from: string | null;
}

/** The states under which a measure states a figure at all — whole under the
 *  first, a bound under the second. Under every other state the wire's number,
 *  where it carries one, is not the answer. */
export const FIGURE_STATES = [
  "known",
  "incomplete",
] as const satisfies readonly MeasureStatus[];

/** Whether a state states a figure. A state this build has never seen does
 *  not: the console cannot vouch for a number whose meaning it cannot read. */
export function statesAFigure(status: string): boolean {
  return (FIGURE_STATES as readonly string[]).includes(status);
}

/** One measure off a row as a figure, or null where the row does not carry it. */
export function figureOn(
  row: EconomicRow | undefined,
  measure: AnalyticsMeasure,
): MeasureFigure | null {
  const entry = measureOn(row, measure);
  if (entry === undefined) return null;
  const sides = completenessOn(row);
  const value =
    measure === RECORDED_EVENTS ? entry.event_count : entry.amount_micros;
  return {
    measure,
    status: entry.status,
    value: value ?? null,
    unresolved_event_count:
      measure === SUPPLIER_COGS || measure === GROSS_MARGIN
        ? sides.unresolved_event_count
        : 0,
    unpriced_event_count:
      measure === CUSTOMER_REVENUE || measure === GROSS_MARGIN
        ? sides.unpriced_event_count
        : 0,
    available_from: entry.available_from ?? null,
  };
}

/**
 * The figure a chart may plot or a table may sort by — and null wherever the
 * state states none.
 *
 * ⚠ **THE ONE QUESTION A NUMBER-SHAPED CALLER MAY ASK, AND IT REPLACES A
 * COALESCE.** A null here is a GAP: a line breaks at it and a sort files it
 * last (`descendingWithAbsencesLast`). It is never a zero, and it is never the
 * part of a revenue that could be placed at a grain where the rest could not —
 * a line drawn through that part is a floor drawn as a total.
 */
export function statedValue(figure: MeasureFigure | null): number | null {
  if (figure === null || !statesAFigure(figure.status)) return null;
  return figure.value;
}

/**
 * The margin as a percentage of the revenue it was drawn from, where both state
 * a figure and the revenue is not nothing — and null otherwise.
 *
 * ⚠ **IT REPLACES `marginPercentOf`, WHICH ANSWERED ZERO FOR A MARGIN UBB WOULD
 * NOT STATE**, and the customer list printed that zero as `0.0%` beside a dash.
 * A share of a figure that is not there, or of nothing, is not a share.
 */
export function statedShare(
  margin: MeasureFigure | null,
  revenue: MeasureFigure | null,
): number | null {
  const m = statedValue(margin);
  const r = statedValue(revenue);
  if (m === null || r === null || r === 0) return null;
  return (m / r) * 100;
}

/**
 * Which state wins when figures are folded together — the query's own order
 * (`apps/metering/queries.py::MEASURE_STATES_WORST_LAST`), with `not_applicable`
 * first because a measure that does not apply to one row takes nothing from the
 * sum of the rest.
 */
const FOLD_ORDER: readonly string[] = [
  "not_applicable",
  "known",
  "incomplete",
  "unavailable_at_requested_grain",
  "unavailable_outside_retention_horizon",
] satisfies readonly MeasureStatus[];

/** A state's rank in the fold — and a state this build cannot rank ranks
 *  WORST, so it survives the fold as itself rather than being summed away. */
function foldRank(status: string): number {
  const rank = FOLD_ORDER.indexOf(status);
  return rank === -1 ? FOLD_ORDER.length : rank;
}

/**
 * Several rows' figures for one measure, as one.
 *
 * ⚠ **THIS IS THE CONSOLE'S OWN ARITHMETIC AND IT MUST NOT LAUNDER A STATE.**
 * The billing window used to sum its days, so one day UBB could not attribute
 * made the window's revenue a PART presented as the whole, and the dashboard's
 * "Other" bar folded rows the same way. The worst state wins, exactly as the
 * query ranks a margin's two sides; a figure is stated only where that state
 * states one; and a row that carried no figure for the measure at all is a gap
 * in the sum, which makes the sum unstateable rather than smaller.
 *
 * Over no rows at all it is a measured zero — the same answer the query gives an
 * ungrouped question over an empty window.
 */
export function combineFigures(
  measure: AnalyticsMeasure,
  figures: readonly (MeasureFigure | null)[],
): MeasureFigure {
  const present = figures.filter((f): f is MeasureFigure => f !== null);
  const worst = present.reduce<MeasureFigure | null>(
    (held, next) =>
      held === null || foldRank(next.status) > foldRank(held.status) ? next : held,
    null,
  );
  const status = worst?.status ?? "known";
  const whole = present.length === figures.length && statesAFigure(status);
  return {
    measure,
    status,
    value: whole
      ? present.reduce((sum, f) => sum + (statedValue(f) ?? 0), 0)
      : null,
    unresolved_event_count: present.reduce((n, f) => n + f.unresolved_event_count, 0),
    unpriced_event_count: present.reduce((n, f) => n + f.unpriced_event_count, 0),
    available_from:
      present
        .map((f) => f.available_from)
        .filter((day): day is string => day !== null)
        .sort()
        .at(-1) ?? null,
  };
}

/** The request word for the grouping that reads the records the shorter clock
 *  prunes (#500). */
export const MEASUREMENT_CONCEPT_AXIS = axisRequestWord({
  kind: ROLLUP_KIND,
  name: "measurement_concept",
});

/**
 * The first day the records behind this answer are held from.
 *
 * ⚠ **WHICH CLOCK GOVERNS DEPENDS ON THE GROUPING** (#500). Every measure is
 * economic and read from postings, which are held for the economic horizon;
 * only a grouping by what was MEASURED reads the child records the measurement
 * horizon releases. The answer publishes both, whether or not anything was
 * truncated, so this is a choice between two stated days rather than a guess.
 */
export function governingHorizon(answer: EconomicsAnswer): string {
  return answer.group_by.includes(MEASUREMENT_CONCEPT_AXIS)
    ? answer.measurement_data_available_from
    : answer.economic_data_available_from;
}

/**
 * Whether the window asked about starts before that day.
 *
 * ⚠ **THIS IS WHAT AN EMPTY ANSWER MUST ASK BEFORE IT SAYS "NO USAGE".** A
 * grouped question over a stretch whose records were released has no rows to
 * carry the state on (#500's recorded limit), so the empty list is the ONLY
 * shape the answer can take — and "nothing happened" is the one reading of it
 * that is certainly unproven.
 */
export function reachesPastHorizon(answer: EconomicsAnswer): boolean {
  return answer.period_start < governingHorizon(answer);
}

/**
 * What an answer says beside its rows, which a narrowing to points or bars
 * would otherwise drop: the revenue it could not place at the grain asked for,
 * and — where the window reaches back past the records it reads — the day those
 * records are held from.
 *
 * A narrowing that returns bare points lets every caller lose both, which is
 * how a stretch UBB no longer holds becomes a chart reading "no usage" and a
 * subscription becomes a breakdown that never mentions it.
 */
export interface AnswerCaveats {
  readonly context: EconomicsAnswer["context"];
  /** The governing horizon, where the window starts before it; else null. */
  readonly held_from: string | null;
  /** Whether that horizon is the measurement one — the pruned-records clock. */
  readonly measurement_horizon: boolean;
}

export function caveatsOf(answer: EconomicsAnswer): AnswerCaveats {
  return {
    context: answer.context,
    held_from: reachesPastHorizon(answer) ? governingHorizon(answer) : null,
    measurement_horizon: answer.group_by.includes(MEASUREMENT_CONCEPT_AXIS),
  };
}

/** A chart's plotted numbers and the figures they came from, keyed alike. */
export type PlottedFigures = Readonly<Record<string, MeasureFigure | null>>;

/** Where every plotted row keeps the figures behind its numbers, for the
 *  tooltip to say each one as its state allows. */
export const FIGURES_KEY = "figures";

/**
 * One grouped value off a row, by the position of the axis in the request.
 *
 * ⚠ **POSITIONAL, because the row's values are.** The answer echoes `group_by`
 * so the alignment is readable from the response alone; a caller that asked for
 * one axis reads position 0.
 */
export function axisValueOn(
  row: EconomicRow | undefined,
  position = 0,
): string | null {
  return row?.grouping_field_value[position] ?? null;
}

/**
 * The customers the window's work reached, from an answer grouped by the
 * customer axis.
 *
 * ⚠ **IDENTITIES, NOT THE TENANT'S OWN WORD FOR THEM.** That axis groups by the
 * customer's UBB id, which is what a picker submits and what a link navigates
 * by; the external id a tenant chose is its word for the same row and belongs
 * to the surface that renders it. The list route this replaced published the
 * same thing — the id and no external id — so nothing is lost here that was
 * ever there.
 */
export function customerIdsIn(answer: EconomicsAnswer): string[] {
  return answer.rows
    .map((row) => axisValueOn(row))
    .filter((value): value is string => typeof value === "string" && value !== "");
}

/** The single row of an ungrouped, unbucketed answer.
 *
 *  That shape always has exactly one row — over an empty window it is zeros,
 *  which is a measured zero and not an absence — so a caller reading totals
 *  never has to handle an empty list. A grouped or bucketed answer is different
 *  in kind and its rows are whatever groups exist. */
export function onlyRow(answer: EconomicsAnswer): EconomicRow | undefined {
  return answer.rows[0];
}
