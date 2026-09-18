// Pure helpers for the customers feature (no React, no IO).

import type { CustomerEconomics } from "../api/types";
import { descendingWithAbsencesLast } from "@/lib/economic-query";

/** Shorten a UUID for table display: "1f0c9c4e-8f2a-…" → "1f0c9c4e". */
export function shortId(id: string): string {
  const head = id.split("-")[0];
  return head && head.length < id.length ? `${head}…` : id;
}

/** Currency units (form input string) → integer micros. */
export function toMicros(units: string | number): number {
  return Math.round(Number(units) * 1_000_000);
}

/** Integer micros → currency units string for form prefill. */
export function microsToUnits(micros: number): string {
  const units = micros / 1_000_000;
  return Number.isInteger(units) ? String(units) : units.toFixed(6).replace(/0+$/, "");
}

// ⚠ `listRowRevenueMicros` IS GONE (#501). It summed a row's three revenue
// fields — a subscription share, a supplied share and billed usage — because
// the list route published no total and this console had to add them up, with
// a fourth source added later going missing until somebody noticed. The one
// economic query answers `customer_revenue` from one definition and the row
// carries it, so there is nothing left to sum.

export type CustomerSort = "revenue" | "margin" | "margin_pct";

export const CUSTOMER_SORT_OPTIONS: { value: CustomerSort; label: string }[] = [
  { value: "revenue", label: "Revenue" },
  { value: "margin", label: "Gross margin" },
  { value: "margin_pct", label: "Margin %" },
];

/** Sort a copy of the rows descending by the chosen measure. */
export function sortMarginRows(
  rows: CustomerEconomics[],
  sort: CustomerSort,
): CustomerEconomics[] {
  // The order is `descendingWithAbsencesLast`'s, shared with the dashboard's
  // table: a row stating no margin sorts LAST rather than as zero. Only the
  // extractor is this table's, because only the row type differs.
  const measure = (row: CustomerEconomics): number | null =>
    sort === "revenue"
      ? row.total_revenue_micros
      : sort === "margin"
        ? row.gross_margin_micros
        : row.gross_margin_micros === null
          ? null
          : row.margin_percentage;
  return [...rows].sort(descendingWithAbsencesLast(measure));
}

/** Client-side search: match on customer_id (the list rows carry no external_id). */
export function filterMarginRows(
  rows: CustomerEconomics[],
  query: string,
): CustomerEconomics[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return rows;
  return rows.filter((row) => row.customer_id.toLowerCase().includes(needle));
}

/** "50, 80,100" → [50, 80, 100]; invalid/empty entries dropped. */
export function parseAlertLevels(input: string): number[] {
  return input
    .split(",")
    .map((part) => Number(part.trim()))
    .filter((value) => Number.isInteger(value) && value > 0);
}

export function formatAlertLevels(levels: number[]): string {
  return levels.join(", ");
}

// ---------------------------------------------------------------------------
// The mid-period affordance (#508; slice 7 §9's ruling)

const MONTH_RE = /^(\d{4})-(\d{2})$/;
const MS_PER_DAY = 86_400_000;

/** One supplied period: the span it covers, and whether it is a part month. */
export interface SuppliedPeriod {
  /** ISO date the period opens on. */
  period_start: string;
  /** ISO date it closes on, EXCLUSIVE — the first of the following month. */
  period_end: string;
  /** Whole days between the two, which is what a straight-line method divides by. */
  days: number;
  /** Whether it opens after the first, so the surface can say what it is. */
  partial: boolean;
}

/**
 * The span a supplied figure covers, from the month it belongs to and the day
 * the customer began.
 *
 * ⚠ **THIS IS THE DATA-ENTRY BURDEN THE RECURRING PROFILE USED TO ABSORB.**
 * #153 §19(f) recorded that retiring the profile lost the *began on the
 * fourteenth* semantics: a profile carried one amount and an interval and
 * worked the part month out, while per-period rows can express it **only if
 * the tenant enters the partial period correctly**. So the tenant states which
 * month and which day, and the SPAN is derived here — they never work out that
 * June the fourteenth is seventeen days.
 *
 * The end is EXCLUSIVE, matching the record's own field and the half-open
 * windows every margin surface reads. `null` where the month cannot be read or
 * the day falls outside it, so the form refuses rather than inventing a span.
 */
export function suppliedPeriod(
  month: string,
  beganOn: string,
): SuppliedPeriod | null {
  const parsed = MONTH_RE.exec(month);
  if (!parsed) return null;
  const year = Number(parsed[1]);
  const monthNumber = Number(parsed[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;
  const firstOfMonth = Date.UTC(year, monthNumber - 1, 1);
  // The first of the NEXT month, which `Date.UTC` rolls into the next year on
  // its own — an increment that touched the month alone would run December's
  // span backwards.
  const firstOfNext = Date.UTC(year, monthNumber, 1);

  let opens = firstOfMonth;
  if (beganOn !== "") {
    opens = Date.parse(`${beganOn}T00:00:00Z`);
    if (Number.isNaN(opens) || opens < firstOfMonth || opens >= firstOfNext) {
      return null;
    }
  }
  return {
    period_start: new Date(opens).toISOString().slice(0, 10),
    period_end: new Date(firstOfNext).toISOString().slice(0, 10),
    days: Math.round((firstOfNext - opens) / MS_PER_DAY),
    // The first of the month is a WHOLE month however it was entered: a figure
    // covering all of June is not a partial period because the tenant reached
    // for the day picker to say so.
    partial: opens > firstOfMonth,
  };
}
