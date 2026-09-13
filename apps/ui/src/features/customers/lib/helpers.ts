// Pure helpers for the customers feature (no React, no IO).

import type { CustomerMarginListRow } from "../api/types";

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

/** The list rows lack total_revenue_micros — derive it the way the detail does. */
export function listRowRevenueMicros(row: CustomerMarginListRow): number {
  return row.subscription_revenue_micros + row.usage_revenue_micros;
}

export type CustomerSort = "revenue" | "margin" | "margin_pct";

export const CUSTOMER_SORT_OPTIONS: { value: CustomerSort; label: string }[] = [
  { value: "revenue", label: "Revenue" },
  { value: "margin", label: "Gross margin" },
  { value: "margin_pct", label: "Margin %" },
];

/** Sort a copy of the rows descending by the chosen measure. */
export function sortMarginRows(
  rows: CustomerMarginListRow[],
  sort: CustomerSort,
): CustomerMarginListRow[] {
  const measure = (row: CustomerMarginListRow): number =>
    sort === "revenue"
      ? listRowRevenueMicros(row)
      : sort === "margin"
        ? row.gross_margin_micros
        : row.margin_percentage;
  return [...rows].sort((a, b) => measure(b) - measure(a));
}

/** Client-side search: match on customer_id (the list rows carry no external_id). */
export function filterMarginRows(
  rows: CustomerMarginListRow[],
  query: string,
): CustomerMarginListRow[] {
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
