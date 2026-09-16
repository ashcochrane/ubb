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
