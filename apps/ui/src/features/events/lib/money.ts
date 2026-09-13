// Signed per-event money for the receipt's margin line. The per-event amount
// itself is `@/lib/format`'s `formatEventMicros` since #466 — three surfaces
// render one event's money, and this feature's copy was the first of them.

import { formatEventMicros } from "@/lib/format";

/** Signed per-event amount for margins: "+$0.0452" / "-$1.25". */
export function formatSignedEventMicros(
  micros: number,
  currency: string,
): string {
  const formatted = formatEventMicros(Math.abs(micros), currency);
  if (micros === 0) return formatted;
  return `${micros > 0 ? "+" : "-"}${formatted}`;
}
