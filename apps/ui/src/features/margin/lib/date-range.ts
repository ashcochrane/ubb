import type { DateRange } from "../api/types";

/** ISO yyyy-mm-dd for a Date (date-only, matches the API's date query params). */
function toISODate(d: Date): string {
  return d.toISOString().slice(0, 10);
}

/** Default analytical window: the trailing 30 days ending today. */
export function defaultDateRange(): DateRange {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - 30);
  return { start_date: toISODate(start), end_date: toISODate(end) };
}

/** First day of the current calendar month — the default period_start. */
export function currentPeriodStart(): string {
  const now = new Date();
  return toISODate(new Date(now.getFullYear(), now.getMonth(), 1));
}
