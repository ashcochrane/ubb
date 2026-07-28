// Live example line for the add-rate dialog: "1,000 units → $X", computed
// with integer math only.

import { formatMicros } from "@/lib/format";
import { exampleChargeMicros, toMicros } from "./pricing-math";
import { resolveUnitQuantity, type RateFormValues } from "./schemas";

/** Null while the form's numeric inputs are incomplete or invalid. */
export function buildRatePreview(values: RateFormValues, currency: string): string | null {
  const fixed = Number(values.fixed);
  if (values.fixed.trim() === "" || !Number.isFinite(fixed) || fixed < 0) return null;
  if (values.pricing_model === "flat") {
    return `Each event → ${formatMicros(toMicros(values.fixed), currency)}`;
  }
  const rate = Number(values.rate);
  if (values.rate.trim() === "" || !Number.isFinite(rate) || rate < 0) return null;
  const unitQuantity = resolveUnitQuantity(values);
  if (!Number.isInteger(unitQuantity) || unitQuantity <= 0) return null;
  const example = exampleChargeMicros(
    {
      pricing_model: "per_unit",
      rate_per_unit_micros: toMicros(values.rate),
      unit_quantity: unitQuantity,
      fixed_micros: toMicros(values.fixed),
    },
    1_000,
  );
  return `1,000 units → ${formatMicros(example, currency)}`;
}
