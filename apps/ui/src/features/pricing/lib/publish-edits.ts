// Pure helpers for the publish (atomic reprice) dialog: staging per-row edits
// against a book's active rates and diffing them into the publish payload.

import { formatMicros, formatPrice } from "@/lib/format";
import type { Rate } from "../api/types";
import {
  microsToUnitString,
  toMicros,
  unitChoiceFor,
  type RateShape,
  type UnitChoice,
} from "./pricing-math";

export interface RowEdit {
  pricing_model: "per_unit" | "flat";
  rate: string;
  unit_choice: UnitChoice;
  custom_unit: string;
  fixed: string;
}

/** Seed a row's editable values from its current active rate. */
export function initialEdit(rate: Rate): RowEdit {
  const choice = unitChoiceFor(rate.unit_quantity);
  return {
    pricing_model: rate.pricing_model === "flat" ? "flat" : "per_unit",
    rate: microsToUnitString(rate.rate_per_unit_micros),
    unit_choice: choice,
    custom_unit: choice === "custom" ? String(rate.unit_quantity) : "",
    fixed: microsToUnitString(rate.fixed_micros),
  };
}

/** Parse a row edit into rate values; null while the input is invalid. */
export function editToShape(edit: RowEdit): RateShape | null {
  const fixed = Number(edit.fixed);
  if (edit.fixed.trim() === "" || !Number.isFinite(fixed) || fixed < 0) return null;
  if (edit.pricing_model === "flat") {
    return {
      pricing_model: "flat",
      rate_per_unit_micros: 0,
      unit_quantity: 1,
      fixed_micros: toMicros(edit.fixed),
    };
  }
  const rate = Number(edit.rate);
  if (edit.rate.trim() === "" || !Number.isFinite(rate) || rate < 0) return null;
  const unitQuantity =
    edit.unit_choice === "custom" ? Number(edit.custom_unit) : Number(edit.unit_choice);
  if (!Number.isInteger(unitQuantity) || unitQuantity <= 0) return null;
  return {
    pricing_model: "per_unit",
    rate_per_unit_micros: toMicros(edit.rate),
    unit_quantity: unitQuantity,
    fixed_micros: toMicros(edit.fixed),
  };
}

/** "$2.5 / 1M + $0.01" / "$0.04 flat" — one-line rate summary for old → new. */
export function shapeSummary(shape: RateShape, currency: string): string {
  if (shape.pricing_model === "flat") {
    return `${formatMicros(shape.fixed_micros, currency)} flat`;
  }
  const base = formatPrice(
    shape.rate_per_unit_micros,
    shape.unit_quantity,
    undefined,
    currency,
  );
  return shape.fixed_micros > 0
    ? `${base} + ${formatMicros(shape.fixed_micros, currency)}`
    : base;
}
