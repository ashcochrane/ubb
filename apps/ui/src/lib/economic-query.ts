// Reading the one economic query, in one place.
//
// Nine published routes collapsed into `GET /metering/analytics/economics`
// (#501), and five console features read what those routes used to serve. The
// shape they now read is the same for all five — a row per bucket per group,
// each carrying one entry per requested measure — so the narrowing lives here
// rather than five times over.
//
// ⚠ **THE MEASURE NAMES ARE LITERALS AND THAT IS DELIBERATE.** The generated
// vocabulary module carries them as constants, and importing those constants
// would make this console a declared consumer of the measure concept — an act
// with a ledger entry behind it and a rendering ticket that owns it. Until that
// ticket, these are request values spelled the way every other request value on
// this console is spelled.
//
// ⚠ **AND A MEASURE'S AMOUNT IS `number | null`, NEVER COERCED HERE.** A null
// means UBB has no figure to state — the stretch is past a retention horizon,
// or a margin could not be attributed at the grain asked for — and a helper
// that answered `0` would turn "we cannot say" into "it was nothing", which is
// the defect this whole surface exists to end. Each caller decides what to
// render; the state is on the row for it to read.

import type { MeteringSchemas } from "@/api/types";

export type EconomicsAnswer = MeteringSchemas["EconomicsOut"];
export type EconomicRow = MeteringSchemas["EconomicRowOut"];
export type EconomicMeasure = MeteringSchemas["EconomicMeasureOut"];

/** The measures, as the request spells them. */
export const SUPPLIER_COGS = "supplier_cogs";
export const CUSTOMER_REVENUE = "customer_revenue";
export const GROSS_MARGIN = "gross_margin";
export const RECORDED_EVENTS = "recorded_events";

/** The three money measures, which every economic panel on this console asks
 *  for together: a cost with no revenue beside it is half a page. */
export const MONEY_MEASURES = [
  SUPPLIER_COGS,
  CUSTOMER_REVENUE,
  GROSS_MARGIN,
] as const;

/** All four — the money plus the count of recorded work. */
export const EVERY_MEASURE = [...MONEY_MEASURES, RECORDED_EVENTS] as const;

/** The grouping axes this console offers, in the request's own vocabulary.
 *
 *  Each is `<kind>:<name>`: the kind is what tells a column on the event apart
 *  from a join to a rollup UBB owns, and the server refuses a word that is on
 *  neither list. This builds the `field:` half — the reserved words every
 *  tenant has (`customer`, `provider`, `event_type`, `task_type`,
 *  `subtask_type`) take it as readily as a tenant's own declared key, because
 *  the server tells them apart and the caller does not have to. The picker that
 *  reads a tenant's declared axes off the discovery contract is a later
 *  ticket's; this console names the axis it wants at each call site. */
export const FIELD_AXIS = (name: string) => `field:${name}`;

/**
 * A measure's figure where it states one, and zero where it does not.
 *
 * ⚠ **CALL THIS ONLY WHERE ZERO IS THE HONEST READING, WHICH IS NOT
 * EVERYWHERE.** A cost or a revenue UBB could not attribute at the grain asked
 * for is genuinely nothing on that row — the money is in the answer's
 * `context`, not in this bucket — so summing it as zero is correct. A
 * MARGIN is different: `null` there means UBB will not state one at all, and
 * zero would be a claim about the customer. `amountOn` keeps the null so a
 * caller has to choose; this is the choice spelled once instead of four times.
 */
export function orZero(value: number | null | undefined): number {
  return typeof value === "number" && Number.isFinite(value) ? value : 0;
}

/**
 * The share a margin is of the revenue it was drawn from, as a percentage.
 *
 * Zero where there is no margin to state and where there is no revenue to
 * divide by — the second because a percentage of nothing is not a number,
 * and the callers all render the figure beside the amounts it came from.
 */
export function marginPercentOf(revenue: number, margin: number | null): number {
  if (margin === null || revenue === 0) return 0;
  return (margin / revenue) * 100;
}

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

export function measureOn(
  row: EconomicRow | undefined,
  measure: string,
): EconomicMeasure | undefined {
  return row?.measures.find((entry) => entry.measure === measure);
}

/** A measure's money figure, or null where it states none. */
export function amountOn(
  row: EconomicRow | undefined,
  measure: string,
): number | null {
  return measureOn(row, measure)?.amount_micros ?? null;
}

/** The count measure's figure, or null where it states none. */
export function eventsOn(row: EconomicRow | undefined): number | null {
  return measureOn(row, RECORDED_EVENTS)?.event_count ?? null;
}

/**
 * What each side of the margin left out, as the pair every cost helper on this
 * console already takes.
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
 * `amountOn` does not.
 */
export function completenessOn(row: EconomicRow | undefined): {
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
