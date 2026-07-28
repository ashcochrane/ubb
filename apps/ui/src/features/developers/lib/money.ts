// Per-event money display for the test console — the point of a test event
// is to verify the resolved price, and events are routinely priced below a
// cent, where 2-decimal rounding shows a non-zero charge as "$0.00". Sub-unit
// amounts route through formatCostMicros's 4-decimal small-value branch.
// (Duplicated from features/events/lib/money.ts — no cross-feature imports.)

import { formatCostMicros, formatMicros } from "@/lib/format";

/** Per-event amount: non-zero values under 1 unit keep 4-decimal precision. */
export function formatEventMicros(micros: number, currency: string): string {
  if (micros !== 0 && Math.abs(micros) < 1_000_000) {
    return formatCostMicros(micros, currency);
  }
  return formatMicros(micros, currency);
}
