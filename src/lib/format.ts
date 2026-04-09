export function formatMicros(micros: number, currency = "USD"): string {
  const dollars = micros / 1_000_000;
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(dollars);
}

export function formatDate(isoString: string): string {
  return new Intl.DateTimeFormat("en-US", {
    year: "numeric",
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
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
 * Format a rate card price for display.
 * e.g. costPerUnitMicros=100, unitQuantity=1_000_000 → "$0.10 / 1M"
 * e.g. costPerUnitMicros=35_000, unitQuantity=1 → "$0.035 / req"
 */
export function formatPrice(
  costPerUnitMicros: number,
  unitQuantity: number,
  displayUnit?: string,
): string {
  const price = costPerUnitMicros / 1_000_000;
  const formatted = price < 0.01
    ? `$${price.toFixed(6).replace(/0+$/, "").replace(/\.$/, "")}`
    : `$${price.toFixed(price < 1 ? 3 : 2).replace(/0+$/, "").replace(/\.$/, "")}`;

  if (displayUnit) return `${formatted} / ${displayUnit.replace(/^per\s+/i, "")}`;
  if (unitQuantity === 1) return formatted;
  if (unitQuantity === 1_000_000) return `${formatted} / 1M`;
  if (unitQuantity === 1_000) return `${formatted} / 1K`;
  return `${formatted} / ${unitQuantity.toLocaleString()}`;
}

/**
 * Format cost in micros for dashboard display.
 * Large values: "$1,247"  Small values: "$0.0148"
 */
export function formatCostMicros(micros: number): string {
  const dollars = micros / 1_000_000;
  if (dollars === 0) return "$0";
  if (dollars >= 1) {
    return new Intl.NumberFormat("en-US", {
      style: "currency",
      currency: "USD",
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(dollars);
  }
  // Small values — show precision
  return `$${dollars.toFixed(4)}`;
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
