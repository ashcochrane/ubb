// Contract timestamps are bare strings with NO declared format (the schema
// deliberately omits format: date-time) — parse defensively and fall back
// to the raw value when it isn't a parseable date.

export function looseDate(value: string | null | undefined, format: (iso: string) => string): string {
  if (!value) return "—";
  return Number.isNaN(new Date(value).getTime()) ? value : format(value);
}

const UTC_MIDNIGHT_RE = /^\d{4}-\d{2}-\d{2}T00:00:00(?:\.0+)?Z$/;

/**
 * Period boundaries arrive as UTC-midnight instants ("2026-07-01T00:00:00Z")
 * but mean calendar days. Reduce them to the bare date so the shared date
 * formatters route through their UTC path — otherwise viewers west of
 * Greenwich see the previous day. Non-midnight values pass through untouched.
 */
export function calendarDay(iso: string): string {
  return UTC_MIDNIGHT_RE.test(iso) ? iso.slice(0, 10) : iso;
}
