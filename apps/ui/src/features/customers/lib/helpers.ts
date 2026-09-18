// Pure helpers for the customers feature (no React, no IO).

import { wholeDaysBetween } from "@/lib/supplied-revenue";

import type { CustomerEconomics } from "../api/types";
import {
  descendingWithAbsencesLast,
  statedShare,
  statedValue,
} from "@/lib/economic-query";

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
  // table: a row stating no figure sorts LAST rather than as zero. Only the
  // extractor is this table's, and it asks each figure the one question a
  // number-shaped caller may ask of one — `statedValue` (#510).
  const measure = (row: CustomerEconomics): number | null =>
    sort === "revenue"
      ? statedValue(row.revenue)
      : sort === "margin"
        ? statedValue(row.margin)
        : statedShare(row.margin, row.revenue);
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
  /** How many whole calendar months it runs to, from the month it opens in. */
  months: number;
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
  months = 1,
): SuppliedPeriod | null {
  const parsed = MONTH_RE.exec(month);
  if (!parsed) return null;
  const year = Number(parsed[1]);
  const monthNumber = Number(parsed[2]);
  if (monthNumber < 1 || monthNumber > 12) return null;
  if (!Number.isInteger(months) || months < 1) return null;
  const firstOfMonth = Date.UTC(year, monthNumber - 1, 1);
  // The first of the month AFTER the span, which `Date.UTC` rolls into the
  // next year on its own — an increment that touched the month alone would run
  // December's span backwards.
  //
  // ⚠ **A SPAN MAY RUN PAST ONE MONTH, because a supplied figure may.** §9
  // says the record carries the period it actually covers, and a tenant that
  // invoices quarterly earned that money across three months; a form that
  // could only say "one month" would make them state three rows for one
  // invoice, which is the data-entry burden this affordance exists to remove
  // rather than relocate.
  const firstAfter = Date.UTC(year, monthNumber - 1 + months, 1);

  let opens = firstOfMonth;
  if (beganOn !== "") {
    opens = Date.parse(`${beganOn}T00:00:00Z`);
    // The day must fall inside the month the span OPENS in — a start part-way
    // through month two of a quarter is a different period, stated as one.
    const firstOfNext = Date.UTC(year, monthNumber, 1);
    if (Number.isNaN(opens) || opens < firstOfMonth || opens >= firstOfNext) {
      return null;
    }
  }
  const period_start = new Date(opens).toISOString().slice(0, 10);
  const period_end = new Date(firstAfter).toISOString().slice(0, 10);
  return {
    period_start,
    period_end,
    // The one counter, shared with the mock's attribution and the panel's own
    // span — a supplied amount is DIVIDED by this under a spreading method.
    days: wholeDaysBetween(period_start, period_end),
    // The first of the month is a WHOLE period however it was entered: a
    // figure covering all of June is not partial because the tenant reached
    // for the day picker to say so.
    partial: opens > firstOfMonth,
    months,
  };
}
