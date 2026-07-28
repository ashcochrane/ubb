// Pure pricing helpers. All money stays in integer micros; conversion from
// user input happens exactly once via toMicros (Math.round(x * 1e6)).

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

export interface RateShape {
  pricing_model: string;
  rate_per_unit_micros: number;
  unit_quantity: number;
  fixed_micros: number;
}

/**
 * What a given number of units would cost under a rate, in integer micros.
 * Integer math only: floor(units * rate / unit_quantity) + fixed.
 * A flat rate charges the fixed component per event, regardless of units.
 */
export function exampleChargeMicros(rate: RateShape, units: number): number {
  if (rate.pricing_model === "flat") return rate.fixed_micros;
  return (
    Math.floor((units * rate.rate_per_unit_micros) / rate.unit_quantity) +
    rate.fixed_micros
  );
}

/** True when two rate value-shapes price identically (publish diffing). */
export function sameRateValues(a: RateShape, b: RateShape): boolean {
  return (
    a.pricing_model === b.pricing_model &&
    a.rate_per_unit_micros === b.rate_per_unit_micros &&
    a.unit_quantity === b.unit_quantity &&
    a.fixed_micros === b.fixed_micros
  );
}
