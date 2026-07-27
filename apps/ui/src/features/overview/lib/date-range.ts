import type { DateRange } from "../api/types";

/** ISO calendar date (YYYY-MM-DD) in the browser's local zone. */
function isoDate(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

/** The trailing `days`-day window ending today, as ISO date strings. */
export function lastNDays(days = 30): DateRange {
  const end = new Date();
  const start = new Date();
  start.setDate(start.getDate() - days);
  return { start_date: isoDate(start), end_date: isoDate(end) };
}
