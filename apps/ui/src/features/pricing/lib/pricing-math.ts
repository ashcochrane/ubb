// Pure pricing helpers. All money stays in integer micros; conversion from
// user input happens exactly once via toMicros (Math.round(x * 1e6)).

import type { RateStructure } from "../api/types";

export const UNIT_QUANTITY_CHOICES = [
  { value: "1", quantity: 1, label: "per unit" },
  { value: "1000", quantity: 1_000, label: "per 1K units" },
  { value: "1000000", quantity: 1_000_000, label: "per 1M units" },
  { value: "custom", quantity: null, label: "custom…" },
] as const;

export type UnitChoice = (typeof UNIT_QUANTITY_CHOICES)[number]["value"];

/** Map a stored unit_quantity to the select choice ("custom" when non-standard). */
export function unitChoiceFor(unitQuantity: number): UnitChoice {
  if (unitQuantity === 1) return "1";
  if (unitQuantity === 1_000) return "1000";
  if (unitQuantity === 1_000_000) return "1000000";
  return "custom";
}

/** "per unit" / "per 1K units" / "per 12,345 units". */
export function unitQuantityLabel(unitQuantity: number): string {
  const match = UNIT_QUANTITY_CHOICES.find((choice) => choice.quantity === unitQuantity);
  if (match) return match.label;
  return `per ${unitQuantity.toLocaleString()} units`;
}

/** Currency-unit (or percent) input string → integer micros. */
export function toMicros(value: string | number): number {
  return Math.round(Number(value) * 1e6);
}

/** Integer micros → input-friendly currency-unit string ("2500000" → "2.5"). */
export function microsToUnitString(micros: number): string {
  return (micros / 1_000_000).toString();
}

/**
 * The arithmetic half of a rule's terms — the four fields that decide what a
 * quantity costs.
 *
 * Structural rather than the contract's `RuleTerms`, and deliberately so: a
 * diff row's `before`/`after`, a rule row from the book, and the editor's own
 * unsaved form state are three different shapes that all carry these four, and
 * this function has no business knowing which one it was handed. `RuleTerms`
 * satisfies it, which is what makes the diff's preview free.
 *
 * ⚠ THE METHOD IS NOT ONE OF THEM. `pricing_method` says where a number came
 * from, not how a quantity multiplies out — a margin over cost and a direct
 * price both spend these same four terms once the amount is known. Including
 * it here would invite a call site to believe this function could price a
 * margin, which it cannot: the basis is the supplier's cost and is not on this
 * record at all.
 */
export interface RuleArithmetic {
  rate_structure: RateStructure;
  rate_per_unit_micros: number;
  unit_quantity: number;
  fixed_micros: number;
}

/**
 * What a given number of units would cost under a rule, in integer micros.
 * Integer math only: floor(units * rate / unit_quantity) + fixed.
 * A fixed component charges once per event, regardless of units.
 */
export function exampleChargeMicros(rule: RuleArithmetic, units: number): number {
  if (rule.rate_structure === "fixed_component") return rule.fixed_micros;
  return (
    Math.floor((units * rule.rate_per_unit_micros) / rule.unit_quantity) +
    rule.fixed_micros
  );
}

// ⚠ NO `sameRateValues` (#372). It answered *"do these two rules price
// identically"* for a console that computed its own publish preview, and there
// is no such preview any more: a draft is declared server-side and the RESPONSE
// carries the diff, so what a tenant reads before committing is what the
// service will actually do rather than the console's second opinion about it.
// Keeping a local comparison would be a second implementation of a question
// only one answer to which can be authoritative — and it is the one that runs
// against the book as it will stand at the effective instant, which the console
// cannot see.
