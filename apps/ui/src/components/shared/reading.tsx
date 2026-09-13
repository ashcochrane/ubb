// A total's reading as one rendered value (#466; lifted out of the episode
// card in #467, and out of the spend-controls feature in #468, the day the
// customer's Billing tab became the second feature to render one — the
// console's imports only flow down, so a cell two features share sits here).
//
// `data-reading` is the reading's kind, so a test asserts WHICH reading a
// cell holds — a figure, a floor, or unknown — rather than matching prose
// that the wrong one could satisfy.

import { describeTotal, UNKNOWN_TOTAL, type TotalReading } from "@/lib/total-reading";

/** A reading as one value, with its kind on the node. */
export function Reading({ reading, currency }: { reading: TotalReading; currency: string }) {
  return (
    <span data-reading={reading.kind} className={reading.kind === "unknown" ? "text-text-muted" : undefined}>
      {describeTotal(reading, currency)}
    </span>
  );
}

/** A reading the wire left null: unknown, said so, never zero. */
export function Unknown({ because }: { because: string }) {
  return (
    <span data-reading="unknown" className="text-text-muted" title={because}>
      {UNKNOWN_TOTAL}
    </span>
  );
}
