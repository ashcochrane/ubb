// Mock fixtures for the CFO overview — one coherent story (July 2026).
//
// The margin roster mirrors src/features/customers/api/mock-data.ts
// BYTE-FOR-BYTE (ids + economics) so the Overview → Customers drill-down is
// coherent in mock mode: both features cache the same
// ['margin','customers',{start_date,end_date}] key, so the fixtures must
// agree. Cross-feature imports are forbidden — keep the two files in sync by
// hand when either roster changes.
//
// The story: "Acme AI" resells LLM/API usage to acme-corp (a business with
// two pooled seats), luna-labs, and nova-ai. Month-to-date the workspace has
// $764.90 total revenue ($199 subscriptions + $565.90 usage revenue),
// $653.90 usage billed, $563.60 provider cost, and two unprofitable
// customers (luna-labs runs at a loss; nova-ai is metered-only with real
// COGS and no recognised revenue). Every breakdown below sums exactly to
// those totals so the page reads as one consistent business.

import { WIRE_GROUP_VALUE_KEY } from "./types";
import type {
  ApiKeyList,
  ConnectStatus,
  MarginCustomerRow,
  MarginSummary,
  PricingBookList,
  Unprofitable,
  UsageAnalytics,
  Window,
} from "./types";

// Mirrors CUS_* in src/features/customers/api/mock-data.ts — keep in sync.
export const CUSTOMER_IDS = {
  acme: "1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001",
  luna: "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002",
  nova: "3b2e7c40-6d08-4b3c-9f5d-8c3100000003",
  seatEng: "4c3f6d51-5c97-4a4b-8a6e-9d4200000004",
  seatRes: "5d4a5e62-4b86-495a-9b7f-0e5300000005",
} as const;

// Mirrors MOCK_MARGIN_ROWS in src/features/customers/api/mock-data.ts —
// byte-identical economics, keep in sync.
export const MOCK_MARGIN_CUSTOMERS: MarginCustomerRow[] = [
  {
    // acme-corp — business customer with an active subscription.
    customer_id: CUSTOMER_IDS.acme,
    subscription_revenue_micros: 199_000_000,
    usage_billed_micros: 342_500_000,
    usage_revenue_micros: 342_500_000,
    provider_cost_micros: 274_000_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 267_500_000,
    margin_percentage: 49.4,
  },
  {
    // luna-labs — individual running at a loss this period.
    customer_id: CUSTOMER_IDS.luna,
    subscription_revenue_micros: 0,
    usage_billed_micros: 41_200_000,
    usage_revenue_micros: 41_200_000,
    provider_cost_micros: 55_900_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: -14_700_000,
    margin_percentage: -35.7,
  },
  {
    // nova-ai — metered-only: real COGS, no recognised revenue, and THE ONE
    // CUSTOMER IN THIS STORY WHOSE COGS IS INCOMPLETE (#330). Four of its
    // events carry a supplier cost UBB never learned, so its provider total is
    // a floor and its margin a ceiling — and the console has to say so rather
    // than print both as figures. Kept in sync by hand with the customers
    // feature's roster (`customers/api/mock-data.ts`), which the comment at the
    // head of this file already warns about; the count is a fact about the
    // events behind these figures, so it must not differ between the two.
    customer_id: CUSTOMER_IDS.nova,
    subscription_revenue_micros: 0,
    usage_billed_micros: 88_000_000,
    usage_revenue_micros: 0,
    provider_cost_micros: 88_000_000,
    unresolved_event_count: 4,
    unpriced_event_count: 0,
    gross_margin_micros: -88_000_000,
    margin_percentage: 0,
  },
  {
    // acme-corp:eng — seat under acme-corp.
    customer_id: CUSTOMER_IDS.seatEng,
    subscription_revenue_micros: 0,
    usage_billed_micros: 120_400_000,
    usage_revenue_micros: 120_400_000,
    provider_cost_micros: 96_300_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 24_100_000,
    margin_percentage: 20,
  },
  {
    // acme-corp:research — seat under acme-corp.
    customer_id: CUSTOMER_IDS.seatRes,
    subscription_revenue_micros: 0,
    usage_billed_micros: 61_800_000,
    usage_revenue_micros: 61_800_000,
    provider_cost_micros: 49_400_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 12_400_000,
    margin_percentage: 20.1,
  },
];

export function mockMarginSummary(window: Window): MarginSummary {
  // Every figure is the exact sum over MOCK_MARGIN_CUSTOMERS.
  return {
    period: { start: window.start_date, end: window.end_date },
    subscription_revenue_micros: 199_000_000,
    usage_billed_micros: 653_900_000,
    usage_revenue_micros: 565_900_000,
    provider_cost_micros: 563_600_000,
    // The exact sum over MOCK_MARGIN_CUSTOMERS, this figure included: only
    // nova-ai holds uncosted events, so the window's total is a floor by the
    // same four.
    unresolved_event_count: 4,
    unpriced_event_count: 0,
    total_revenue_micros: 764_900_000,
    gross_margin_micros: 201_300_000,
    margin_percentage: 26.32,
    customer_count: 5,
  };
}

export const MOCK_UNPROFITABLE: Unprofitable = {
  period_start: "2026-07-01",
  customers: [
    {
      customer_id: CUSTOMER_IDS.nova,
      external_id: "nova-ai",
      gross_margin_micros: -88_000_000,
      unresolved_event_count: 4,
      unpriced_event_count: 0,
      margin_percentage: -100,
    },
    {
      customer_id: CUSTOMER_IDS.luna,
      external_id: "luna-labs",
      gross_margin_micros: -14_700_000,
      unresolved_event_count: 0,
      unpriced_event_count: 0,
      margin_percentage: -35.7,
    },
  ],
};

// ---------------------------------------------------------------------------
// Analytics — totals + per-axis rows (uniform `breakdowns` shape).
// Each axis sums exactly to the same window totals.

const WINDOW_TOTALS = {
  total_events: 93_558,
  total_billed_cost_micros: 653_900_000,
  total_provider_cost_micros: 563_600_000,
  // The same four events the margin summary counts — analytics and margin read
  // the same postings over the same window, so a story where they disagreed
  // would be a story no server could produce.
  unresolved_event_count: 4,
  unpriced_event_count: 0,
  usage_markup_margin_micros: 90_300_000,
};

type Row = [name: string, billed: number, provider: number, events: number];

const BY_PROVIDER: Row[] = [
  ["openai", 280_000_000, 245_000_000, 41_000],
  ["anthropic", 180_400_000, 152_600_000, 22_300],
  ["mistral", 96_000_000, 82_000_000, 15_258],
  ["deepgram", 62_500_000, 51_000_000, 9_000],
  ["elevenlabs", 35_000_000, 33_000_000, 6_000],
];

// Ten event types so the breakdown card exercises its top-8 + "Other" fold.
const BY_EVENT_TYPE: Row[] = [
  ["chat.completion", 225_000_000, 196_000_000, 37_000],
  ["embedding", 108_000_000, 92_000_000, 22_000],
  ["transcription", 74_000_000, 63_000_000, 10_500],
  ["image.generation", 64_000_000, 56_000_000, 4_700],
  ["agent.run", 54_000_000, 46_000_000, 6_400],
  ["rerank", 42_000_000, 36_000_000, 5_500],
  ["tool.call", 32_000_000, 27_600_000, 4_050],
  ["tts.synthesize", 26_000_000, 21_000_000, 2_100],
  ["search.query", 19_500_000, 16_000_000, 1_200],
  ["fine_tune.step", 9_400_000, 10_000_000, 108],
];

const BY_TASK_TYPE: Row[] = [
  ["agent-api", 325_000_000, 280_000_000, 48_000],
  ["copilot", 190_900_000, 165_600_000, 26_558],
  ["batch-jobs", 88_000_000, 76_000_000, 13_000],
  ["playground", 50_000_000, 42_000_000, 6_000],
];

// Billed/provider figures match MOCK_MARGIN_CUSTOMERS row-for-row.
const BY_CUSTOMER: Row[] = [
  ["acme-corp", 342_500_000, 274_000_000, 48_213],
  ["acme-corp:eng", 120_400_000, 96_300_000, 17_502],
  ["nova-ai", 88_000_000, 88_000_000, 12_882],
  ["acme-corp:research", 61_800_000, 49_400_000, 8_907],
  ["luna-labs", 41_200_000, 55_900_000, 6_054],
];

const DIMENSION_ROWS = {
  provider: BY_PROVIDER,
  event_type: BY_EVENT_TYPE,
  task_type: BY_TASK_TYPE,
  customer: BY_CUSTOMER,
} as const;

// The uniform rows are emitted under the key the backend still uses, taken by
// reference from the narrowing module rather than re-spelled here.
function breakdownRows(rows: Row[]): Record<string, unknown>[] {
  return rows.map(([name, billed, provider, events]) => ({
    [WIRE_GROUP_VALUE_KEY]: name,
    event_count: events,
    total_provider_cost_micros: provider,
    total_billed_cost_micros: billed,
  }));
}

// Legacy by_* rows carry billed cost as `total_cost_micros` and the customer
// value under the literal key `customer__external_id` — mirrored faithfully.
function legacyRows(rows: Row[], valueKey: string): Record<string, unknown>[] {
  return rows.map(([name, billed, provider, events]) => ({
    [valueKey]: name,
    event_count: events,
    total_cost_micros: billed,
    total_provider_cost_micros: provider,
  }));
}

export function mockWindowAnalytics(
  groupBy: keyof typeof DIMENSION_ROWS,
): UsageAnalytics {
  return {
    ...WINDOW_TOTALS,
    by_provider: legacyRows(BY_PROVIDER, "provider"),
    by_event_type: legacyRows(BY_EVENT_TYPE, "event_type"),
    by_task_type: legacyRows(BY_TASK_TYPE, "task_type"),
    by_customer: legacyRows(BY_CUSTOMER, "customer__external_id"),
    by_tag: [],
    breakdowns: { [groupBy]: breakdownRows(DIMENSION_ROWS[groupBy]) },
  };
}

export const MOCK_LIFETIME_ANALYTICS: UsageAnalytics = {
  total_events: 812_441,
  total_billed_cost_micros: 7_845_300_000,
  total_provider_cost_micros: 6_690_150_000,
  // Lifetime spans the window, so it cannot count FEWER than the window does.
  unresolved_event_count: 4,
  unpriced_event_count: 0,
  usage_markup_margin_micros: 1_155_150_000,
  by_provider: [],
  by_event_type: [],
  by_task_type: [],
  by_customer: [],
  by_tag: [],
  breakdowns: {},
};

// ---------------------------------------------------------------------------
// Daily series — deterministic per-day values over any requested window

/** Inclusive list of YYYY-MM-DD days in the window (clamped to 366). */
export function daysInWindow(window: Window): string[] {
  const days: string[] = [];
  const start = new Date(`${window.start_date}T00:00:00Z`).getTime();
  const end = new Date(`${window.end_date}T00:00:00Z`).getTime();
  if (Number.isNaN(start) || Number.isNaN(end)) return days;
  for (let t = start; t <= end && days.length < 366; t += 86_400_000) {
    days.push(new Date(t).toISOString().slice(0, 10));
  }
  return days;
}

export interface MockDailyPoint {
  day: string;
  billed_cost_micros: number;
  provider_cost_micros: number;
  event_count: number;
}

/**
 * Deterministic pseudo-variation so charts look alive but tests stay stable.
 * Scaled to the monthly story: ~$24–37 billed / ~$20–27 provider per day.
 */
export function mockDailySeries(window: Window): MockDailyPoint[] {
  return daysInWindow(window).map((day, i) => ({
    day,
    billed_cost_micros: (24 + ((i * 37) % 13)) * 1_000_000,
    provider_cost_micros: (20 + ((i * 23) % 8)) * 1_000_000,
    event_count: 3_700 + ((i * 53) % 800),
  }));
}

// ---------------------------------------------------------------------------
// Getting-started checks

export const MOCK_API_KEYS: ApiKeyList = {
  data: [
    {
      id: "ak_01J9ZK3W8Q",
      label: "Production backend",
      key_prefix: "ubb_live_9f2k",
      is_active: true,
      created_at: "2026-07-02T09:14:00Z",
      last_used_at: "2026-07-23T18:40:00Z",
    },
  ],
  has_more: false,
  next_cursor: null,
};

export const MOCK_PRICING_BOOKS: PricingBookList = {
  data: [
    {
      id: "b7c4e1d0-2f8a-4b6c-9d3e-5a7f0c1b8d29",
      key: "default-price-book",
      name: "Default price book",
      is_default: true,
      customer_id: null,
      version: 3,
    },
  ],
  has_more: false,
  next_cursor: null,
};

// Canonical mock account id across all features caching ['connect','status'].
export const MOCK_CONNECT_STATUS: ConnectStatus = {
  account_id: "acct_mock123",
  charges_enabled: true,
  onboarded: true,
};
