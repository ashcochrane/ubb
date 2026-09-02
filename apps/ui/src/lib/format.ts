// All API money is integer MICROS of the tenant currency (1,000,000 micros =
// 1 currency unit; 1 cent = 10,000 micros). Currency codes arrive lowercase
// ("usd"). Formatting divides only for display — never compute in floats.

export function formatMicros(micros: number, currency = "USD"): string {
  const dollars = micros / 1_000_000;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(dollars);
}

/** Signed micros with explicit +/- for ledger deltas: "+$25.00" / "-$0.35". */
export function formatSignedMicros(micros: number, currency = "USD"): string {
  const formatted = formatMicros(Math.abs(micros), currency);
  if (micros === 0) return formatted;
  return `${micros > 0 ? "+" : "-"}${formatted}`;
}

/**
 * `markup_percentage_micros` is a percentage expressed in micros:
 * 1,000,000 = 1%. Not a currency amount.
 */
export function formatPercentMicros(percentMicros: number): string {
  const pct = percentMicros / 1_000_000;
  return `${Number.isInteger(pct) ? pct : pct.toFixed(2).replace(/0+$/, "").replace(/\.$/, "")}%`;
}

/** Float percent (0–100) as the API's margin_percentage/pct fields carry it. */
export function formatPercent(value: number, digits = 1): string {
  return `${value.toFixed(digits).replace(/\.0+$/, "")}%`;
}

/** Bare calendar date: "2026-07-01" (length 10, no time component). */
const BARE_DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Format a calendar date — a bare "YYYY-MM-DD" string (or a UTC-midnight
 * timestamp such as a day-truncated chart bucket) — as "Jul 1, 2026".
 * Always renders in UTC: `new Date("2026-07-01")` parses as UTC midnight,
 * so local-zone formatting would show Jun 30 for any viewer west of
 * Greenwich. Use this for billing periods, invoice periods, day buckets —
 * anything the contract declares as a date rather than an instant.
 */
export function formatCalendarDate(isoDate: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    timeZone: "UTC",
  }).format(new Date(isoDate));
}

/**
 * Timestamps render in the viewer's local zone with time; bare calendar
 * dates ("YYYY-MM-DD") route through the UTC path so the day never shifts.
 */
export function formatDate(isoString: string): string {
  if (BARE_DATE_RE.test(isoString)) return formatCalendarDate(isoString);
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(isoString));
}

/**
 * Date-only rendering ("Jul 14, 2026" — same en-US order as formatDate).
 * Bare calendar dates route through the UTC path (no local-tz day shift);
 * timestamps render the viewer's local calendar day.
 */
export function formatShortDate(isoString: string): string {
  if (BARE_DATE_RE.test(isoString)) return formatCalendarDate(isoString);
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
  }).format(new Date(isoString));
}

export function formatRelativeDate(isoString: string): string {
  const now = Date.now();
  const then = new Date(isoString).getTime();
  const diffMs = now - then;
  const diffMins = Math.floor(diffMs / 60_000);
  if (diffMins < 1) return "just now";
  if (diffMins < 60) return `${diffMins}m ago`;
  const diffHours = Math.floor(diffMins / 60);
  if (diffHours < 24) return `${diffHours}h ago`;
  const diffDays = Math.floor(diffHours / 24);
  if (diffDays < 30) return `${diffDays}d ago`;
  return formatDate(isoString);
}

/**
 * Format a pricing rule's price for display, in the given currency (accepts the
 * API's lowercase codes; defaults to USD for legacy call sites).
 * e.g. costPerUnitMicros=100, unitQuantity=1_000_000 → "$0.0001 / 1M"
 * e.g. costPerUnitMicros=35_000, unitQuantity=1 → "$0.035"
 */
export function formatPrice(
  costPerUnitMicros: number,
  unitQuantity: number,
  displayUnit?: string,
  currency = "USD",
): string {
  const price = costPerUnitMicros / 1_000_000;
  const maxDigits = price !== 0 && Math.abs(price) < 0.01 ? 6 : Math.abs(price) < 1 ? 3 : 2;
  const formatted = new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 0,
    maximumFractionDigits: maxDigits,
  }).format(price);

  if (displayUnit) return `${formatted} / ${displayUnit.replace(/^per\s+/i, "")}`;
  if (unitQuantity === 1) return formatted;
  if (unitQuantity === 1_000_000) return `${formatted} / 1M`;
  if (unitQuantity === 1_000) return `${formatted} / 1K`;
  return `${formatted} / ${unitQuantity.toLocaleString()}`;
}

/**
 * Format cost in micros for dashboard display, in the given currency
 * (accepts the API's lowercase codes; defaults to USD for legacy call sites).
 * Large values: "$1,247"  Small values (<1 unit): 4-decimal precision, "$0.0148"
 */
export function formatCostMicros(micros: number, currency = "USD"): string {
  const dollars = micros / 1_000_000;
  if (dollars === 0 || Math.abs(dollars) >= 1) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: currency.toUpperCase(),
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(dollars);
  }
  // Small values — keep sub-cent precision
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: currency.toUpperCase(),
    minimumFractionDigits: 4,
    maximumFractionDigits: 4,
  }).format(dollars);
}

/**
 * Format large numbers with abbreviations.
 * 84219 → "84.2k"   1247000 → "1.25M"
 */
export function formatEventCount(count: number): string {
  if (count >= 1_000_000) return `${(count / 1_000_000).toFixed(2)}M`;
  if (count >= 1_000) return `${(count / 1_000).toFixed(1)}k`;
  return count.toLocaleString();
}

/**
 * Format percent change between two values.
 * Returns "+12.3%" or "-5.1%"
 */
export function formatPercentChange(current: number, previous: number): string {
  if (previous === 0) return current > 0 ? "+∞%" : "0%";
  const change = ((current - previous) / previous) * 100;
  const sign = change >= 0 ? "+" : "";
  return `${sign}${change.toFixed(1)}%`;
}

/**
 * Format a dollar amount (already in dollars, not micros).
 * Whole numbers: "$1,247"  Fractional: "$12.50"
 */
export function formatDollars(dollars: number): string {
  const hasFraction = dollars % 1 !== 0;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    minimumFractionDigits: hasFraction ? 2 : 0,
    maximumFractionDigits: hasFraction ? 2 : 0,
  }).format(dollars);
}

/**
 * Format a dollar amount rounded to whole dollars.
 * e.g. 1247.89 → "$1,248"
 */
export function formatRoundedDollars(dollars: number): string {
  return formatDollars(Math.round(dollars));
}

/**
 * Format a dollar delta with explicit + / - sign.
 * e.g. +25 → "+$25"   -25 → "-$25"   0 → "$0"
 */
export function formatSignedDollars(dollars: number): string {
  if (dollars === 0) return "$0";
  const sign = dollars > 0 ? "+" : "-";
  return `${sign}${formatDollars(Math.abs(dollars))}`;
}

/**
 * Format a byte count for display.
 * >= 1_000_000 bytes → "X MB" (rounded)
 * Otherwise → "X KB" (rounded, min 1)
 */
export function formatFileSize(bytes: number): string {
  if (bytes === 0) return "0 MB";
  if (bytes >= 1_000_000) return `${Math.round(bytes / 1_000_000)} MB`;
  return `${Math.max(1, Math.round(bytes / 1000))} KB`;
}

/**
 * The first eight characters of an id, for a cell that cannot hold a UUID:
 * "7f3c2a10…". Show the whole id beside it — a copy affordance, a title —
 * rather than only the truncation.
 */
export function shortId(id: string): string {
  return id.length > 8 ? `${id.slice(0, 8)}…` : id;
}
