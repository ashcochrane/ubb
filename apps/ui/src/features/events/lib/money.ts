// Per-event money display. Individual events are routinely priced below a
// cent (rates accept 6 decimals), where 2-decimal rounding shows a genuinely
// non-zero charge as "$0.00" — so sub-unit amounts route through
// formatCostMicros's 4-decimal small-value branch instead. Amounts of one
// currency unit and up keep formatMicros's standard 2 decimals.

import { formatCostMicros, formatMicros } from "@/lib/format";

/** Per-event amount: non-zero values under 1 unit keep 4-decimal precision. */
export function formatEventMicros(micros: number, currency: string): string {
  if (micros !== 0 && Math.abs(micros) < 1_000_000) {
    return formatCostMicros(micros, currency);
  }
  return formatMicros(micros, currency);
}

/** Signed per-event amount for margins: "+$0.0452" / "-$1.25". */
export function formatSignedEventMicros(
  micros: number,
  currency: string,
): string {
  const formatted = formatEventMicros(Math.abs(micros), currency);
  if (micros === 0) return formatted;
  return `${micros > 0 ? "+" : "-"}${formatted}`;
}
