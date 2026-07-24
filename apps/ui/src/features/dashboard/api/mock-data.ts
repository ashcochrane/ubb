// Mock fixtures for the CFO overview — one coherent story (July 2026).
//
// "Acme AI" resells LLM/API usage to six customers. Month-to-date the
// workspace has $9,370.40 total revenue ($1,250 subscriptions + $8,120.40
// usage revenue), $8,432.55 usage billed, $5,330.42 provider cost, and one
// unprofitable customer (atlas-fintech, a metered-only account with real
// COGS and no recognised revenue). Every breakdown below sums exactly to
// those totals so the page reads as one consistent business.

import type {
  ApiKeyList,
  ConnectStatus,
  MarginCustomerRow,
  MarginSummary,
  RateCardBookList,
  Unprofitable,
  UsageAnalytics,
  Window,
} from "./types";

export const CUSTOMER_IDS = {
  orbit: "3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301",
  quill: "9c2d5b18-7e4f-4a6b-b3c8-1f5e9d0a7b42",
  helios: "5fd0c7a2-1b9e-4c3d-8a57-6e2f4b8d9c13",
  nimbus: "b48e1f63-9a0d-4e7c-a2b5-3c8f7d1e6a94",
  vector: "7a91d2c5-3e8b-4f6a-9d04-5b2c8e1f7a35",
  atlas: "d62a9e37-4c1f-4b8d-a6e9-0f3b5d7c2e86",
} as const;

export const MOCK_MARGIN_CUSTOMERS: MarginCustomerRow[] = [
  {
    customer_id: CUSTOMER_IDS.orbit,
    subscription_revenue_micros: 500_000_000,
    usage_billed_micros: 3_200_100_000,
    usage_revenue_micros: 3_200_100_000,
    provider_cost_micros: 1_900_550_000,
    gross_margin_micros: 1_799_550_000,
    margin_percentage: 48.64,
  },
  {
    customer_id: CUSTOMER_IDS.quill,
    subscription_revenue_micros: 250_000_000,
    usage_billed_micros: 2_100_000_000,
    usage_revenue_micros: 2_100_000_000,
    provider_cost_micros: 1_450_000_000,
    gross_margin_micros: 900_000_000,
    margin_percentage: 38.3,
  },
  {
    customer_id: CUSTOMER_IDS.helios,
    subscription_revenue_micros: 0,
    usage_billed_micros: 1_500_000_000,
    usage_revenue_micros: 1_500_000_000,
    provider_cost_micros: 700_000_000,
    gross_margin_micros: 800_000_000,
    margin_percentage: 53.33,
  },
  {
    customer_id: CUSTOMER_IDS.nimbus,
    subscription_revenue_micros: 300_000_000,
    usage_billed_micros: 820_000_000,
    usage_revenue_micros: 820_000_000,
    provider_cost_micros: 610_000_000,
    gross_margin_micros: 510_000_000,
    margin_percentage: 45.54,
  },
  {
    customer_id: CUSTOMER_IDS.vector,
    subscription_revenue_micros: 200_000_000,
    usage_billed_micros: 512_450_000,
    usage_revenue_micros: 500_300_000,
    provider_cost_micros: 420_000_000,
    gross_margin_micros: 280_300_000,
    margin_percentage: 40.03,
  },
  {
    // Metered-only account: real COGS, no recognised revenue → unprofitable.
    customer_id: CUSTOMER_IDS.atlas,
    subscription_revenue_micros: 0,
    usage_billed_micros: 300_000_000,
    usage_revenue_micros: 0,
    provider_cost_micros: 249_870_000,
    gross_margin_micros: -249_870_000,
    margin_percentage: 0,
  },
];

export function mockMarginSummary(window: Window): MarginSummary {
  return {
    period: { start: window.start_date, end: window.end_date },
    subscription_revenue_micros: 1_250_000_000,
    usage_billed_micros: 8_432_550_000,
    usage_revenue_micros: 8_120_400_000,
    provider_cost_micros: 5_330_420_000,
    total_revenue_micros: 9_370_400_000,
    gross_margin_micros: 4_039_980_000,
    margin_percentage: 43.11,
    customer_count: 6,
  };
}

export const MOCK_UNPROFITABLE: Unprofitable = {
  period_start: "2026-07-01",
  customers: [
    {
      customer_id: CUSTOMER_IDS.atlas,
      external_id: "atlas-fintech",
      gross_margin_micros: -249_870_000,
      margin_percentage: -83.29,
    },
  ],
};

// ---------------------------------------------------------------------------
// Analytics — totals + per-dimension rows (uniform `breakdowns` shape)

const WINDOW_TOTALS = {
  total_events: 184_230,
  total_billed_cost_micros: 8_432_550_000,
  total_provider_cost_micros: 5_330_420_000,
  usage_markup_margin_micros: 3_102_130_000,
};

type Row = [name: string, billed: number, provider: number, events: number];

const BY_PROVIDER: Row[] = [
  ["openai", 3_600_300_000, 2_450_100_000, 92_410],
  ["anthropic", 2_602_250_000, 1_690_320_000, 41_205],
  ["mistral", 1_100_000_000, 640_000_000, 28_114],
  ["deepgram", 730_000_000, 380_000_000, 14_501],
  ["elevenlabs", 400_000_000, 170_000_000, 8_000],
];

// Ten event types so the breakdown card exercises its top-8 + "Other" fold.
const BY_EVENT_TYPE: Row[] = [
  ["chat.completion", 2_900_000_000, 1_950_000_000, 70_000],
  ["embedding", 1_400_000_000, 820_000_000, 45_000],
  ["transcription", 950_000_000, 560_000_000, 21_000],
  ["image.generation", 830_000_000, 540_000_000, 9_400],
  ["agent.run", 700_000_000, 430_000_000, 12_800],
  ["rerank", 540_000_000, 310_000_000, 11_030],
  ["tool.call", 420_000_000, 260_000_000, 8_100],
  ["tts.synthesize", 330_000_000, 210_000_000, 4_200],
  ["search.query", 250_000_000, 160_000_000, 2_400],
  ["fine_tune.step", 112_550_000, 90_420_000, 300],
];

const BY_PRODUCT: Row[] = [
  ["agent-api", 4_200_000_000, 2_700_000_000, 98_000],
  ["copilot", 2_432_550_000, 1_530_420_000, 50_230],
  ["batch-jobs", 1_100_000_000, 700_000_000, 26_000],
  ["playground", 700_000_000, 400_000_000, 10_000],
];

const BY_CUSTOMER: Row[] = [
  ["orbit-labs", 3_200_100_000, 1_900_550_000, 71_400],
  ["quill-ai", 2_100_000_000, 1_450_000_000, 45_800],
  ["helios-devtools", 1_500_000_000, 700_000_000, 33_200],
  ["nimbus-crm", 820_000_000, 610_000_000, 19_230],
  ["vector-shop", 512_450_000, 420_000_000, 9_800],
  ["atlas-fintech", 300_000_000, 249_870_000, 4_800],
];

const DIMENSION_ROWS = {
  provider: BY_PROVIDER,
  event_type: BY_EVENT_TYPE,
  product_id: BY_PRODUCT,
  customer: BY_CUSTOMER,
} as const;

function breakdownRows(rows: Row[]): Record<string, unknown>[] {
  return rows.map(([name, billed, provider, events]) => ({
    dimension: name,
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
  dimension: keyof typeof DIMENSION_ROWS,
): UsageAnalytics {
  return {
    ...WINDOW_TOTALS,
    by_provider: legacyRows(BY_PROVIDER, "provider"),
    by_event_type: legacyRows(BY_EVENT_TYPE, "event_type"),
    by_product: legacyRows(BY_PRODUCT, "product_id"),
    by_customer: legacyRows(BY_CUSTOMER, "customer__external_id"),
    by_tag: [],
    breakdowns: { [dimension]: breakdownRows(DIMENSION_ROWS[dimension]) },
  };
}

export const MOCK_LIFETIME_ANALYTICS: UsageAnalytics = {
  total_events: 1_204_552,
  total_billed_cost_micros: 55_310_220_000,
  total_provider_cost_micros: 34_880_140_000,
  usage_markup_margin_micros: 20_430_080_000,
  by_provider: [],
  by_event_type: [],
  by_product: [],
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

/** Deterministic pseudo-variation so charts look alive but tests stay stable. */
export function mockDailySeries(window: Window): MockDailyPoint[] {
  return daysInWindow(window).map((day, i) => ({
    day,
    billed_cost_micros: (300 + ((i * 37) % 130)) * 1_000_000,
    provider_cost_micros: (190 + ((i * 23) % 80)) * 1_000_000,
    event_count: 5_200 + ((i * 53) % 1_900),
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

export const MOCK_RATE_CARD_BOOKS: RateCardBookList = {
  data: [
    {
      id: "b7c4e1d0-2f8a-4b6c-9d3e-5a7f0c1b8d29",
      key: "default-price-book",
      name: "Default price book",
      card_type: "price",
      provider_key: "",
      currency: "usd",
      is_default: true,
      version: 3,
    },
  ],
  has_more: false,
  next_cursor: null,
};

export const MOCK_CONNECT_STATUS: ConnectStatus = {
  account_id: "acct_mock123",
  charges_enabled: true,
  onboarded: true,
};
