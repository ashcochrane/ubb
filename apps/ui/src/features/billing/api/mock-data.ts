// Mock fixtures for the billing feature. One coherent story: "Acme AI", a usd
// tenant with a handful of AI-agent customers, told relative to *today*.
// Revenue runs over the trailing 12 weeks, ending today; last month's invoices
// are pushed (one permanently failed), this month's period is still closing.
//
// Every date here is derived from the clock, never written down. An absolute
// span silently stops intersecting the console's month-to-date default the
// moment the calendar leaves it, at which point the billing page renders its
// empty state instead of tiles — see #225, and mock-data.test.ts, which fails
// if this file ever goes back to pinned dates.

import type { BudgetConfig, PostpaidConfig, RevenueDailyRow, TenantUsageInvoice } from "./types";

const DAY_MS = 86_400_000;

/** Length of the generated revenue series. 12 weeks — whole weeks keep the
 *  weekend dip evenly represented however the span lands. */
const REVENUE_SPAN_DAYS = 84;

/** Today at UTC midnight. UTC deliberately: the date-range presets and the API
 *  both work in UTC calendar dates, so the fixture must too. */
function todayUtc(): number {
  const now = new Date();
  return Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
}

function isoDay(epochMs: number): string {
  return new Date(epochMs).toISOString().slice(0, 10);
}

/**
 * How many of today's events are still waiting on a supplier cost.
 *
 * Exported so a test asserting "the window's total renders as a floor" names
 * this rather than a literal, and so the provider that sums the rows and the
 * fixture that seeds them cannot disagree about the number.
 */
export const UNRESOLVED_TODAY = 3;

/** Deterministic pseudo-random in [0, 1) so charts look organic but stable. */
function noise(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/**
 * Daily revenue rows over the trailing {@link REVENUE_SPAN_DAYS} days, ending
 * today: gentle growth + weekend dip.
 *
 * Ending on *today* is what guarantees the default month-to-date window always
 * selects something — including on the 1st, when that window is a single day.
 */
export function buildDailyRows(): RevenueDailyRow[] {
  const rows: RevenueDailyRow[] = [];
  const end = todayUtc();
  const start = end - (REVENUE_SPAN_DAYS - 1) * DAY_MS;
  for (let t = start, i = 0; t <= end; t += DAY_MS, i++) {
    const date = new Date(t);
    const weekday = date.getUTCDay();
    const weekendDip = weekday === 0 || weekday === 6 ? 0.55 : 1;
    const growth = 1 + i / 90;
    const base = 38_000_000 * growth * weekendDip; // provider cost in micros
    const provider = Math.round(base * (0.75 + noise(i) * 0.5));
    // Billed ≈ provider + ~28% markup, varying slightly by day.
    const billed = Math.round(provider * (1.22 + noise(i + 500) * 0.12));
    rows.push({
      day: date.toISOString().slice(0, 10),
      provider_cost_micros: provider,
      billed_cost_micros: billed,
      event_count: Math.round((provider / 1200) * (0.8 + noise(i + 900) * 0.4)),
      // TODAY IS THE ONE INCOMPLETE DAY, and it is today on purpose (#330).
      // A supplier cost that has not arrived is a fact about the day still in
      // progress, so putting it on the last row is both the realistic story and
      // the only placement that survives the window arithmetic this file exists
      // to protect: the narrowest default window there is — the 1st of a month
      // — is a single day, and that day is this one.
      unresolved_event_count: t === end ? UNRESOLVED_TODAY : 0,
    });
  }
  return rows;
}

/**
 * The daily rows a revenue window selects — both bounds inclusive, an absent
 * bound meaning unbounded. Shared with the mock provider so a test asking "does
 * this fixture intersect the default window?" asks it the same way the console
 * does, rather than against a copy that can drift.
 */
export function rowsInRange<T extends { day: string }>(
  rows: readonly T[],
  range: { start_date?: string; end_date?: string },
): T[] {
  return rows.filter(
    (row) =>
      (!range.start_date || row.day >= range.start_date) &&
      (!range.end_date || row.day <= range.end_date),
  );
}

export const INITIAL_BUDGET: BudgetConfig = {
  cap_micros: 2_500_000_000, // $2,500 monthly cap
  enforce_mode: "alert_only",
  hard_stop_pct: 120,
  alert_levels: [50, 80, 100],
  fail_closed: false,
};

export const INITIAL_POSTPAID_CONFIG: PostpaidConfig = {
  usage_line_item_group_by: "product_id",
  consolidate_with_subscription: false,
};

/** First of the month `monthsAgo` months back, as "YYYY-MM-01". */
function periodStart(monthsAgo: number): string {
  const today = new Date(todayUtc());
  return isoDay(Date.UTC(today.getUTCFullYear(), today.getUTCMonth() - monthsAgo, 1));
}

/**
 * One row per customer per billing period: the current period mid-close, and
 * the previous one closed and pushed.
 *
 * Periods track the clock alongside {@link buildDailyRows}. Nothing breaks if
 * they don't — the invoice list is filtered by an explicit period picker, not
 * by the revenue window — but pinned periods would drift ever further from the
 * revenue the same page charts, and this file promises one coherent story.
 */
export function buildUsageInvoices(): TenantUsageInvoice[] {
  const current = periodStart(0);
  const previous = periodStart(1);
  return [
    // Current period — close in progress.
    {
      customer_id: "0d0e3a92-6c1f-4f0a-9a4e-7f2b8c1d4e5f",
      external_id: "acme-support-bot",
      period_start: current,
      total_billed_micros: 1_284_520_000,
      status: "pushing",
      stripe_invoice_id: "",
      skip_reason: "",
      push_attempts: 1,
      last_attempt_error: null,
    },
    {
      customer_id: "3f7c2b10-8a4d-4e6b-b2c9-1d5e8f0a3b6c",
      external_id: "glow-writer",
      period_start: current,
      total_billed_micros: 642_180_000,
      status: "pending",
      stripe_invoice_id: "",
      skip_reason: "",
      push_attempts: 0,
      last_attempt_error: null,
    },
    {
      customer_id: "7a1b9c33-2d4e-4f5a-8b6c-9d0e1f2a3b4c",
      external_id: "nova-agents",
      period_start: current,
      total_billed_micros: 2_918_450_000,
      status: "failed",
      stripe_invoice_id: "",
      skip_reason: "",
      push_attempts: 3,
      last_attempt_error:
        "Stripe: This customer has no attached payment source or default payment method.",
    },
    {
      customer_id: "b4c5d6e7-f8a9-4b0c-8d1e-2f3a4b5c6d7e",
      external_id: "pixel-labs",
      period_start: current,
      total_billed_micros: 0,
      status: "skipped",
      stripe_invoice_id: "",
      skip_reason: "zero_usage_period",
      push_attempts: 0,
      last_attempt_error: null,
    },
    // Previous period — closed and pushed.
    {
      customer_id: "0d0e3a92-6c1f-4f0a-9a4e-7f2b8c1d4e5f",
      external_id: "acme-support-bot",
      period_start: previous,
      total_billed_micros: 1_106_330_000,
      status: "pushed",
      stripe_invoice_id: "in_1Pf8kQ2eZvKYlo2C9yTasMx1",
      skip_reason: "",
      push_attempts: 1,
      last_attempt_error: null,
    },
    {
      customer_id: "3f7c2b10-8a4d-4e6b-b2c9-1d5e8f0a3b6c",
      external_id: "glow-writer",
      period_start: previous,
      total_billed_micros: 587_940_000,
      status: "pushed",
      stripe_invoice_id: "in_1Pf8kR2eZvKYlo2CqW7bNd42",
      skip_reason: "",
      push_attempts: 2,
      last_attempt_error: null,
    },
    {
      customer_id: "7a1b9c33-2d4e-4f5a-8b6c-9d0e1f2a3b4c",
      external_id: "nova-agents",
      period_start: previous,
      total_billed_micros: 2_403_710_000,
      status: "failed_permanent",
      stripe_invoice_id: "",
      skip_reason: "",
      push_attempts: 8,
      last_attempt_error: "Stripe: No such customer: 'cus_QRs7tUvWxYz012'.",
    },
    {
      customer_id: "e8f9a0b1-c2d3-4e5f-9a6b-7c8d9e0f1a2b",
      external_id: "quill-and-ink",
      period_start: previous,
      total_billed_micros: 148_200_000,
      status: "pushed",
      stripe_invoice_id: "in_1Pf8kS2eZvKYlo2CeR3cPq83",
      skip_reason: "",
      push_attempts: 1,
      last_attempt_error: null,
    },
    {
      customer_id: "b4c5d6e7-f8a9-4b0c-8d1e-2f3a4b5c6d7e",
      external_id: "pixel-labs",
      period_start: previous,
      total_billed_micros: 96_750_000,
      status: "pushed",
      stripe_invoice_id: "in_1Pf8kT2eZvKYlo2CxN5dRs29",
      skip_reason: "",
      push_attempts: 1,
      last_attempt_error: null,
    },
  ];
}

export const TENANT_USAGE_INVOICES: TenantUsageInvoice[] = buildUsageInvoices();

/** Wallet balances by EXTERNAL id (credit/debit key on external_id). */
export const INITIAL_WALLETS: Record<string, number> = {
  "acme-support-bot": 182_500_000, // $182.50
  "glow-writer": 47_310_000,
  "nova-agents": 964_020_000,
  "pixel-labs": 12_000_000,
  "quill-and-ink": 0,
};
