// Mock fixtures — one coherent story, July 2026.
//
// acme-corp     — business customer with two pooled seats, active subscription,
//                 grants, budget, recurring revenue profile; healthy margin.
// luna-labs     — individual on a negative balance (floor stop episodes),
//                 negative margin, no subscription, no revenue profile.
// nova-ai       — individual pinned to metered_only; usage tracked at cost.
// acme-corp:eng / acme-corp:research — seats under acme-corp.

import type {
  BalanceResponse,
  BookOut,
  BudgetConfigOut,
  BudgetStatusOut,
  BusinessMarginOut,
  CustomerBillingProfileOut,
  CustomerMarginListRow,
  CustomerMarginOut,
  GrantOut,
  MarginTrendPointOut,
  PastLimitReport,
  RevenueModeOut,
  RevenueProfileOut,
  StripeSubscriptionOut,
  SubscriptionInvoiceOut,
  TenantMarkupOut,
  UsageInvoiceOut,
  UsageAnalyticsResponse,
  UsageTimeseriesResponse,
  WalletTransactionOut,
} from "./types";

export const CUS_ACME = "1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001";
export const CUS_LUNA = "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002";
export const CUS_NOVA = "3b2e7c40-6d08-4b3c-9f5d-8c3100000003";
export const CUS_SEAT_ENG = "4c3f6d51-5c97-4a4b-8a6e-9d4200000004";
export const CUS_SEAT_RES = "5d4a5e62-4b86-495a-9b7f-0e5300000005";

export interface MockCustomer {
  id: string;
  external_id: string;
  account_type: string;
  parent_external_id: string;
  stripe_customer_id: string;
}

export const MOCK_DIRECTORY: MockCustomer[] = [
  {
    id: CUS_ACME,
    external_id: "acme-corp",
    account_type: "business",
    parent_external_id: "",
    stripe_customer_id: "cus_mock_acme",
  },
  {
    id: CUS_LUNA,
    external_id: "luna-labs",
    account_type: "individual",
    parent_external_id: "",
    stripe_customer_id: "",
  },
  {
    id: CUS_NOVA,
    external_id: "nova-ai",
    account_type: "individual",
    parent_external_id: "",
    stripe_customer_id: "",
  },
  {
    id: CUS_SEAT_ENG,
    external_id: "acme-corp:eng",
    account_type: "seat",
    parent_external_id: "acme-corp",
    stripe_customer_id: "",
  },
  {
    id: CUS_SEAT_RES,
    external_id: "acme-corp:research",
    account_type: "seat",
    parent_external_id: "acme-corp",
    stripe_customer_id: "",
  },
];

export const MOCK_MARGIN_ROWS: CustomerMarginListRow[] = [
  {
    customer_id: CUS_ACME,
    subscription_revenue_micros: 199_000_000,
    usage_billed_micros: 342_500_000,
    usage_revenue_micros: 342_500_000,
    provider_cost_micros: 274_000_000,
    gross_margin_micros: 267_500_000,
    margin_percentage: 49.4,
  },
  {
    customer_id: CUS_LUNA,
    subscription_revenue_micros: 0,
    usage_billed_micros: 41_200_000,
    usage_revenue_micros: 41_200_000,
    provider_cost_micros: 55_900_000,
    gross_margin_micros: -14_700_000,
    margin_percentage: -35.7,
  },
  {
    customer_id: CUS_NOVA,
    subscription_revenue_micros: 0,
    usage_billed_micros: 88_000_000,
    usage_revenue_micros: 0,
    provider_cost_micros: 88_000_000,
    gross_margin_micros: -88_000_000,
    margin_percentage: 0,
  },
  {
    customer_id: CUS_SEAT_ENG,
    subscription_revenue_micros: 0,
    usage_billed_micros: 120_400_000,
    usage_revenue_micros: 120_400_000,
    provider_cost_micros: 96_300_000,
    gross_margin_micros: 24_100_000,
    margin_percentage: 20,
  },
  {
    customer_id: CUS_SEAT_RES,
    subscription_revenue_micros: 0,
    usage_billed_micros: 61_800_000,
    usage_revenue_micros: 61_800_000,
    provider_cost_micros: 49_400_000,
    gross_margin_micros: 12_400_000,
    margin_percentage: 20.1,
  },
];

export const MOCK_PERIOD = { start: "2026-07-01", end: "2026-07-24" };

export const MOCK_MARGIN_DETAILS: Record<string, CustomerMarginOut> = {
  [CUS_ACME]: {
    customer_id: CUS_ACME,
    external_id: "acme-corp",
    period: MOCK_PERIOD,
    revenue_mode: "billed",
    event_count: 48_213,
    subscription_revenue_micros: 199_000_000,
    usage_billed_micros: 342_500_000,
    usage_revenue_micros: 342_500_000,
    provider_cost_micros: 274_000_000,
    total_revenue_micros: 541_500_000,
    gross_margin_micros: 267_500_000,
    margin_percentage: 49.4,
  },
  [CUS_LUNA]: {
    customer_id: CUS_LUNA,
    external_id: "luna-labs",
    period: MOCK_PERIOD,
    revenue_mode: "billed",
    event_count: 6_054,
    subscription_revenue_micros: 0,
    usage_billed_micros: 41_200_000,
    usage_revenue_micros: 41_200_000,
    provider_cost_micros: 55_900_000,
    total_revenue_micros: 41_200_000,
    gross_margin_micros: -14_700_000,
    margin_percentage: -35.7,
  },
  [CUS_NOVA]: {
    customer_id: CUS_NOVA,
    external_id: "nova-ai",
    period: MOCK_PERIOD,
    revenue_mode: "metered_only",
    event_count: 12_882,
    subscription_revenue_micros: 0,
    usage_billed_micros: 88_000_000,
    usage_revenue_micros: 0,
    provider_cost_micros: 88_000_000,
    total_revenue_micros: 0,
    gross_margin_micros: -88_000_000,
    margin_percentage: 0,
  },
  [CUS_SEAT_ENG]: {
    customer_id: CUS_SEAT_ENG,
    external_id: "acme-corp:eng",
    period: MOCK_PERIOD,
    revenue_mode: "billed",
    event_count: 17_502,
    subscription_revenue_micros: 0,
    usage_billed_micros: 120_400_000,
    usage_revenue_micros: 120_400_000,
    provider_cost_micros: 96_300_000,
    total_revenue_micros: 120_400_000,
    gross_margin_micros: 24_100_000,
    margin_percentage: 20,
  },
  [CUS_SEAT_RES]: {
    customer_id: CUS_SEAT_RES,
    external_id: "acme-corp:research",
    period: MOCK_PERIOD,
    revenue_mode: "billed",
    event_count: 8_907,
    subscription_revenue_micros: 0,
    usage_billed_micros: 61_800_000,
    usage_revenue_micros: 61_800_000,
    provider_cost_micros: 49_400_000,
    total_revenue_micros: 61_800_000,
    gross_margin_micros: 12_400_000,
    margin_percentage: 20.1,
  },
};

/** 12 closed monthly periods, chronological ascending (Aug 2025 → Jul 2026). */
export const MOCK_TREND_POINTS: MarginTrendPointOut[] = [
  "2025-08-01",
  "2025-09-01",
  "2025-10-01",
  "2025-11-01",
  "2025-12-01",
  "2026-01-01",
  "2026-02-01",
  "2026-03-01",
  "2026-04-01",
  "2026-05-01",
  "2026-06-01",
  "2026-07-01",
].map((period_start, index) => {
  const billed = 180_000_000 + index * 16_000_000;
  const provider = 150_000_000 + index * 11_000_000;
  const subscription = index >= 5 ? 199_000_000 : 0;
  const margin = billed + subscription - provider;
  return {
    period_start,
    provider_cost_micros: provider,
    usage_billed_micros: billed,
    subscription_revenue_micros: subscription,
    gross_margin_micros: margin,
    margin_percentage:
      billed + subscription === 0
        ? 0
        : Math.round((margin / (billed + subscription)) * 1000) / 10,
  };
});

export const MOCK_REVENUE_PROFILES: Record<string, RevenueProfileOut> = {
  [CUS_ACME]: {
    recurring_amount_micros: 199_000_000,
    currency: "usd",
    interval: "month",
    effective_from: "2026-01-01T00:00:00Z",
    effective_to: null,
  },
};

export const MOCK_REVENUE_MODES: Record<string, RevenueModeOut> = {
  [CUS_ACME]: { revenue_mode: "", resolved: "billed" },
  [CUS_LUNA]: { revenue_mode: "", resolved: "billed" },
  [CUS_NOVA]: { revenue_mode: "metered_only", resolved: "metered_only" },
  [CUS_SEAT_ENG]: { revenue_mode: "", resolved: "billed" },
  [CUS_SEAT_RES]: { revenue_mode: "", resolved: "billed" },
};

export const MOCK_BUSINESS_MARGIN: BusinessMarginOut = {
  business_id: CUS_ACME,
  external_id: "acme-corp",
  seats: [
    {
      customer_id: CUS_SEAT_ENG,
      revenue_mode: "billed",
      event_count: 17_502,
      subscription_revenue_micros: 0,
      usage_billed_micros: 120_400_000,
      usage_revenue_micros: 120_400_000,
      provider_cost_micros: 96_300_000,
      total_revenue_micros: 120_400_000,
      gross_margin_micros: 24_100_000,
      margin_percentage: 20,
    },
    {
      customer_id: CUS_SEAT_RES,
      revenue_mode: "billed",
      event_count: 8_907,
      subscription_revenue_micros: 0,
      usage_billed_micros: 61_800_000,
      usage_revenue_micros: 61_800_000,
      provider_cost_micros: 49_400_000,
      total_revenue_micros: 61_800_000,
      gross_margin_micros: 12_400_000,
      margin_percentage: 20.1,
    },
  ],
  totals: {
    event_count: 26_409,
    subscription_revenue_micros: 0,
    usage_revenue_micros: 182_200_000,
    provider_cost_micros: 145_700_000,
    total_revenue_micros: 182_200_000,
    gross_margin_micros: 36_500_000,
  },
};

// ---------------------------------------------------------------------------
// Billing

export const MOCK_BALANCES: Record<string, BalanceResponse> = {
  [CUS_ACME]: {
    balance_micros: 258_400_000,
    currency: "usd",
    billing_owner_id: CUS_ACME,
    billing_owner_external_id: "acme-corp",
    is_pooled_seat: false,
    promo_micros: 25_000_000,
    expiring_micros: 25_000_000,
    next_expiry_at: "2026-08-15T00:00:00Z",
    negative_since: null,
  },
  [CUS_LUNA]: {
    balance_micros: -12_500_000,
    currency: "usd",
    billing_owner_id: CUS_LUNA,
    billing_owner_external_id: "luna-labs",
    is_pooled_seat: false,
    promo_micros: 0,
    expiring_micros: 0,
    next_expiry_at: null,
    negative_since: "2026-07-02T09:14:00Z",
  },
  [CUS_NOVA]: {
    balance_micros: 0,
    currency: "usd",
    billing_owner_id: CUS_NOVA,
    billing_owner_external_id: "nova-ai",
    is_pooled_seat: false,
    promo_micros: null,
    expiring_micros: null,
    next_expiry_at: null,
    negative_since: null,
  },
};

export const MOCK_TRANSACTIONS: Record<string, WalletTransactionOut[]> = {
  [CUS_ACME]: [
    {
      id: "7a10a5e2-0000-4000-8000-000000000010",
      transaction_type: "USAGE_DEDUCTION",
      amount_micros: -8_420_000,
      balance_after_micros: 258_400_000,
      description: "Usage — claude-sonnet batch",
      reference_id: "evt_01hz3v",
      created_at: "2026-07-23T18:22:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000009",
      transaction_type: "GRANT",
      amount_micros: 25_000_000,
      balance_after_micros: 266_820_000,
      description: "Promo credit — launch offer",
      reference_id: "grant_promo_launch",
      created_at: "2026-07-20T10:00:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000008",
      transaction_type: "TOP_UP",
      amount_micros: 200_000_000,
      balance_after_micros: 241_820_000,
      description: "Stripe Checkout top-up",
      reference_id: "cs_live_a1b2",
      created_at: "2026-07-18T14:03:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000007",
      transaction_type: "USAGE_DEDUCTION",
      amount_micros: -31_180_000,
      balance_after_micros: 41_820_000,
      description: "Usage — embeddings backfill",
      reference_id: "evt_01hy9k",
      created_at: "2026-07-15T02:47:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000006",
      transaction_type: "REFUND",
      amount_micros: 2_150_000,
      balance_after_micros: 73_000_000,
      description: "Refund — duplicate charge",
      reference_id: "evt_01hx2p",
      created_at: "2026-07-12T16:30:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000005",
      transaction_type: "DEBIT",
      amount_micros: -5_000_000,
      balance_after_micros: 70_850_000,
      description: "Manual debit — SLA credit clawback",
      reference_id: "ops-2026-114",
      created_at: "2026-07-10T09:12:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000004",
      transaction_type: "ADJUSTMENT",
      amount_micros: 10_000_000,
      balance_after_micros: 75_850_000,
      description: "Manual credit — onboarding goodwill",
      reference_id: "ops-2026-102",
      created_at: "2026-07-06T11:45:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000003",
      transaction_type: "WITHDRAWAL",
      amount_micros: -40_000_000,
      balance_after_micros: 65_850_000,
      description: "Withdrawal to Stripe balance",
      reference_id: "wd_2026_07",
      created_at: "2026-07-03T08:00:00Z",
    },
  ],
  [CUS_LUNA]: [
    {
      id: "7a10a5e2-0000-4000-8000-000000000102",
      transaction_type: "USAGE_DEDUCTION",
      amount_micros: -14_500_000,
      balance_after_micros: -12_500_000,
      description: "Usage — overnight crawl",
      reference_id: "evt_01hw8d",
      created_at: "2026-07-02T09:14:00Z",
    },
    {
      id: "7a10a5e2-0000-4000-8000-000000000101",
      transaction_type: "TOP_UP",
      amount_micros: 20_000_000,
      balance_after_micros: 2_000_000,
      description: "Stripe Checkout top-up",
      reference_id: "cs_live_x9y8",
      created_at: "2026-06-28T12:00:00Z",
    },
  ],
};

export const MOCK_GRANTS: Record<string, GrantOut[]> = {
  [CUS_ACME]: [
    {
      id: "5b21b6f3-0000-4000-8000-000000000021",
      kind: "promo",
      granted_micros: 25_000_000,
      remaining_micros: 25_000_000,
      expired_micros: 0,
      voided_micros: 0,
      currency: "usd",
      status: "active",
      source: "api",
      expires_at: "2026-08-15T00:00:00Z",
      warning_sent_at: null,
      created_at: "2026-07-20T10:00:00Z",
      balance_micros: null,
      transaction_id: null,
    },
    {
      id: "5b21b6f3-0000-4000-8000-000000000022",
      kind: "paid",
      granted_micros: 50_000_000,
      remaining_micros: 12_300_000,
      expired_micros: 0,
      voided_micros: 0,
      currency: "usd",
      status: "active",
      source: "checkout",
      expires_at: "2026-10-01T00:00:00Z",
      warning_sent_at: null,
      created_at: "2026-07-01T08:30:00Z",
      balance_micros: null,
      transaction_id: null,
    },
    {
      id: "5b21b6f3-0000-4000-8000-000000000023",
      kind: "promo",
      granted_micros: 10_000_000,
      remaining_micros: 0,
      expired_micros: 0,
      voided_micros: 10_000_000,
      currency: "usd",
      status: "voided",
      source: "api",
      expires_at: null,
      warning_sent_at: null,
      created_at: "2026-06-05T15:00:00Z",
      balance_micros: null,
      transaction_id: null,
    },
  ],
};

export const MOCK_BUDGETS: Record<string, BudgetConfigOut> = {
  [CUS_ACME]: {
    cap_micros: 500_000_000,
    enforce_mode: "alert_only",
    hard_stop_pct: 100,
    alert_levels: [50, 80, 100],
    fail_closed: false,
  },
};

export const MOCK_BUDGET_STATUS: Record<string, BudgetStatusOut> = {
  [CUS_ACME]: {
    period: "2026-07",
    spend_micros: 231_400_000,
    cap_micros: 500_000_000,
    pct: 46.3,
    enforce_mode: "alert_only",
  },
  [CUS_LUNA]: {
    period: "2026-07",
    spend_micros: 55_900_000,
    cap_micros: 0,
    pct: 0,
    enforce_mode: "alert_only",
  },
};

// Floor wire semantics: min_balance_micros = allowed overdraft MAGNITUDE
// (stop line at −value, must be ≥ 0); soft_min_balance_micros is negated the
// same way and must be ≤ the hard value (acme: stop at −$25, wind-down once
// $20 into the overdraft — a state the real PUT accepts).
export const MOCK_BILLING_PROFILES: Record<string, CustomerBillingProfileOut> = {
  [CUS_ACME]: {
    billing_owner_id: CUS_ACME,
    billing_owner_external_id: "acme-corp",
    is_pooled_seat: false,
    min_balance_micros: 25_000_000,
    soft_min_balance_micros: 20_000_000,
    topup_grant_expiry_days: 90,
  },
  [CUS_LUNA]: {
    billing_owner_id: CUS_LUNA,
    billing_owner_external_id: "luna-labs",
    is_pooled_seat: false,
    min_balance_micros: null,
    soft_min_balance_micros: null,
    topup_grant_expiry_days: null,
  },
};

// Per-customer usage-invoice (Stripe push) history — newest first. Acme's
// pushes succeed; luna exercises the failed_permanent + skipped states.
export const MOCK_USAGE_INVOICES: Record<string, UsageInvoiceOut[]> = {
  [CUS_ACME]: [
    {
      period_start: "2026-06-01",
      period_end: "2026-07-01",
      total_billed_micros: 356_000_000,
      currency: "usd",
      status: "pushed",
      stripe_invoice_id: "in_mock_usage_2026_06",
      skip_reason: "",
      push_attempts: 1,
      last_attempt_error: null,
    },
    {
      period_start: "2026-05-01",
      period_end: "2026-06-01",
      total_billed_micros: 301_200_000,
      currency: "usd",
      status: "pushed",
      stripe_invoice_id: "in_mock_usage_2026_05",
      skip_reason: "",
      push_attempts: 2,
      last_attempt_error: null,
    },
  ],
  [CUS_LUNA]: [
    {
      period_start: "2026-06-01",
      period_end: "2026-07-01",
      total_billed_micros: 38_600_000,
      currency: "usd",
      status: "failed_permanent",
      stripe_invoice_id: "",
      skip_reason: "",
      push_attempts: 5,
      last_attempt_error:
        "Stripe: no such customer — the customer has no Stripe customer on file.",
    },
    {
      period_start: "2026-05-01",
      period_end: "2026-06-01",
      total_billed_micros: 0,
      currency: "usd",
      status: "skipped",
      skip_reason: "zero_usage",
      stripe_invoice_id: "",
      push_attempts: 0,
      last_attempt_error: null,
    },
  ],
};

// ---------------------------------------------------------------------------
// Usage tab

export const MOCK_USAGE_ANALYTICS: Record<string, UsageAnalyticsResponse> = {
  [CUS_ACME]: {
    total_events: 48_213,
    total_billed_cost_micros: 342_500_000,
    total_provider_cost_micros: 274_000_000,
    usage_markup_margin_micros: 68_500_000,
    by_provider: [
      {
        provider: "anthropic",
        event_count: 31_204,
        total_cost_micros: 228_000_000,
        total_provider_cost_micros: 182_400_000,
      },
      {
        provider: "openai",
        event_count: 17_009,
        total_cost_micros: 114_500_000,
        total_provider_cost_micros: 91_600_000,
      },
    ],
    by_event_type: [],
    by_customer: [],
    by_task_type: [],
    by_tag: [],
    breakdowns: {},
  },
  [CUS_LUNA]: {
    total_events: 6_054,
    total_billed_cost_micros: 41_200_000,
    total_provider_cost_micros: 55_900_000,
    usage_markup_margin_micros: -14_700_000,
    by_provider: [],
    by_event_type: [],
    by_customer: [],
    by_task_type: [],
    by_tag: [],
    breakdowns: {},
  },
};

export function buildMockTimeseries(customerId: string): UsageTimeseriesResponse {
  const scale = customerId === CUS_ACME ? 1 : 0.15;
  const series = Array.from({ length: 14 }, (_, index) => {
    const day = index + 10;
    const provider = Math.round((9_000_000 + (index % 5) * 2_400_000) * scale);
    const billed = Math.round(provider * 1.25);
    return {
      bucket: `2026-07-${String(day).padStart(2, "0")}T00:00:00Z`,
      provider_cost_micros: provider,
      billed_cost_micros: billed,
      markup_micros: billed - provider,
      event_count: Math.round((1_800 + index * 120) * scale),
    };
  });
  return { granularity: "day", group_by: "", series };
}

export const MOCK_PAST_LIMIT_REPORTS: Record<string, PastLimitReport> = {
  [CUS_LUNA]: {
    customer_id: CUS_LUNA,
    billing_owner_id: CUS_LUNA,
    since: null,
    until: null,
    episodes: [
      {
        family: "soft_floor",
        limit: null,
        stop_scope: "customer",
        episode_seq: null,
        task_id: null,
        subtask_id: null,
        provider_cost_limit_micros: null,
        tripped_at: "2026-07-01T22:40:00Z",
        resumed_at: "2026-07-01T23:55:00Z",
        events: [],
        event_count: 0,
        total_billed_cost_micros: 0,
        total_provider_cost_micros: 0,
      },
      {
        family: "floor_stop",
        limit: "customer_floor",
        stop_scope: "customer",
        episode_seq: 3,
        task_id: null,
        subtask_id: null,
        provider_cost_limit_micros: null,
        tripped_at: "2026-07-02T09:14:00Z",
        resumed_at: "2026-07-04T08:02:00Z",
        events: [
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000301",
            effective_at: "2026-07-02T09:14:00Z",
            billed_cost_micros: 1_450_000,
            provider_cost_micros: 1_160_000,
            arrived_after: false,
          },
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000302",
            effective_at: "2026-07-02T09:15:12Z",
            billed_cost_micros: 890_000,
            provider_cost_micros: 712_000,
            arrived_after: true,
          },
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000303",
            effective_at: "2026-07-02T09:16:44Z",
            billed_cost_micros: 640_000,
            provider_cost_micros: 512_000,
            arrived_after: true,
          },
        ],
        event_count: 3,
        total_billed_cost_micros: 2_980_000,
        total_provider_cost_micros: 2_384_000,
      },
      {
        family: "task",
        limit: "task_limit",
        stop_scope: "task",
        episode_seq: null,
        task_id: "4d43d8b5-0000-4000-8000-000000000401",
        subtask_id: null,
        provider_cost_limit_micros: 5_000_000,
        tripped_at: "2026-07-11T17:20:00Z",
        resumed_at: null,
        events: [
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000304",
            effective_at: "2026-07-11T17:20:00Z",
            billed_cost_micros: 1_120_000,
            provider_cost_micros: 896_000,
            arrived_after: false,
          },
        ],
        event_count: 1,
        total_billed_cost_micros: 1_120_000,
        total_provider_cost_micros: 896_000,
      },
    ],
    totals_per_limit: {
      customer_floor: {
        billed_cost_micros: 2_980_000,
        provider_cost_micros: 2_384_000,
        event_count: 3,
      },
      task_limit: {
        billed_cost_micros: 1_120_000,
        provider_cost_micros: 896_000,
        event_count: 1,
      },
    },
  },
};

export function emptyPastLimitReport(customerId: string): PastLimitReport {
  return {
    customer_id: customerId,
    billing_owner_id: customerId,
    since: null,
    until: null,
    episodes: [],
    totals_per_limit: {},
  };
}

// ---------------------------------------------------------------------------
// Pricing

export const MOCK_MARKUPS: Record<string, TenantMarkupOut> = {
  [CUS_ACME]: { markup_percentage_micros: 25_000_000, fixed_uplift_micros: 0 },
  [CUS_LUNA]: { markup_percentage_micros: 20_000_000, fixed_uplift_micros: 50_000 },
  [CUS_NOVA]: { markup_percentage_micros: 0, fixed_uplift_micros: 0 },
};

export const MOCK_PRICE_BOOKS: BookOut[] = [
  {
    id: "6e54e9c6-0000-4000-8000-000000000501",
    key: "standard-price",
    name: "Standard price book",
    card_type: "price",
    provider_key: "",
    currency: "usd",
    is_default: true,
    version: 3,
  },
  {
    id: "6e54e9c6-0000-4000-8000-000000000502",
    key: "enterprise-price",
    name: "Enterprise price book",
    card_type: "price",
    provider_key: "",
    currency: "usd",
    is_default: false,
    version: 1,
  },
];

// ---------------------------------------------------------------------------
// Subscriptions

export const MOCK_SUBSCRIPTIONS: Record<string, StripeSubscriptionOut> = {
  [CUS_ACME]: {
    id: "8f65f0d7-0000-4000-8000-000000000601",
    stripe_subscription_id: "sub_mock_acme",
    stripe_product_name: "UBB Platform — Pro",
    status: "active",
    amount_micros: 199_000_000,
    currency: "usd",
    interval: "month",
    current_period_start: "2026-07-01T00:00:00Z",
    current_period_end: "2026-08-01T00:00:00Z",
    last_synced_at: "2026-07-24T06:10:00Z",
  },
};

export const MOCK_SUB_INVOICES: Record<string, SubscriptionInvoiceOut[]> = {
  [CUS_ACME]: [
    {
      id: "af76a1e8-0000-4000-8000-000000000701",
      stripe_invoice_id: "in_mock_2026_07",
      amount_paid_micros: 199_000_000,
      currency: "usd",
      period_start: "2026-07-01T00:00:00Z",
      period_end: "2026-08-01T00:00:00Z",
      paid_at: "2026-07-01T04:12:00Z",
    },
    {
      id: "af76a1e8-0000-4000-8000-000000000702",
      stripe_invoice_id: "in_mock_2026_06",
      amount_paid_micros: 199_000_000,
      currency: "usd",
      period_start: "2026-06-01T00:00:00Z",
      period_end: "2026-07-01T00:00:00Z",
      paid_at: "2026-06-01T04:02:00Z",
    },
    {
      id: "af76a1e8-0000-4000-8000-000000000703",
      stripe_invoice_id: "in_mock_2026_05",
      amount_paid_micros: 149_000_000,
      currency: "usd",
      period_start: "2026-05-01T00:00:00Z",
      period_end: "2026-06-01T00:00:00Z",
      paid_at: "2026-05-01T04:33:00Z",
    },
  ],
};
