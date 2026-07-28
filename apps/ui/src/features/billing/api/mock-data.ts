// Mock fixtures for the billing feature. One coherent story: "Acme AI", a
// usd tenant with a handful of AI-agent customers, mid-July 2026. Revenue
// runs May 1 – July 23; June's invoices are pushed (one permanently failed),
// July's period is still closing.

import type { BudgetConfig, PostpaidConfig, RevenueDailyRow, TenantUsageInvoice } from "./types";

/** Deterministic pseudo-random in [0, 1) so charts look organic but stable. */
function noise(seed: number): number {
  const x = Math.sin(seed * 12.9898) * 43758.5453;
  return x - Math.floor(x);
}

/** Daily revenue rows, 2026-05-01 → 2026-07-23, gentle growth + weekly dip. */
export function buildDailyRows(): RevenueDailyRow[] {
  const rows: RevenueDailyRow[] = [];
  const start = Date.UTC(2026, 4, 1); // 2026-05-01
  const end = Date.UTC(2026, 6, 23); // 2026-07-23
  for (let t = start, i = 0; t <= end; t += 86_400_000, i++) {
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
    });
  }
  return rows;
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

export const TENANT_USAGE_INVOICES: TenantUsageInvoice[] = [
  // July period — close in progress.
  {
    customer_id: "0d0e3a92-6c1f-4f0a-9a4e-7f2b8c1d4e5f",
    external_id: "acme-support-bot",
    period_start: "2026-07-01",
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
    period_start: "2026-07-01",
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
    period_start: "2026-07-01",
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
    period_start: "2026-07-01",
    total_billed_micros: 0,
    status: "skipped",
    stripe_invoice_id: "",
    skip_reason: "zero_usage_period",
    push_attempts: 0,
    last_attempt_error: null,
  },
  // June period — closed and pushed.
  {
    customer_id: "0d0e3a92-6c1f-4f0a-9a4e-7f2b8c1d4e5f",
    external_id: "acme-support-bot",
    period_start: "2026-06-01",
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
    period_start: "2026-06-01",
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
    period_start: "2026-06-01",
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
    period_start: "2026-06-01",
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
    period_start: "2026-06-01",
    total_billed_micros: 96_750_000,
    status: "pushed",
    stripe_invoice_id: "in_1Pf8kT2eZvKYlo2CxN5dRs29",
    skip_reason: "",
    push_attempts: 1,
    last_attempt_error: null,
  },
];

/** Wallet balances by EXTERNAL id (credit/debit key on external_id). */
export const INITIAL_WALLETS: Record<string, number> = {
  "acme-support-bot": 182_500_000, // $182.50
  "glow-writer": 47_310_000,
  "nova-agents": 964_020_000,
  "pixel-labs": 12_000_000,
  "quill-and-ink": 0,
};
