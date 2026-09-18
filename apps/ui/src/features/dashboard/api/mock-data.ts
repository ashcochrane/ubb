// Mock fixtures for the CFO overview — one coherent story (July 2026).
//
// The customer roster mirrors src/features/customers/api/mock-data.ts
// BYTE-FOR-BYTE (ids + economics) so the Overview → Customers drill-down is
// coherent in mock mode: both features cache the same
// ['metering','analytics','economics','by-customer',{start_date,end_date}] key,
// so the fixtures must agree. Cross-feature imports are forbidden — keep the
// two files in sync by hand when either roster changes.
//
// The story: "Acme AI" resells LLM/API usage to acme-corp (a business with
// two pooled seats), luna-labs, and nova-ai. Month-to-date the workspace has
// $852.90 total revenue ($199 subscriptions + $653.90 usage revenue),
// $563.60 provider cost, and two unprofitable customers (luna-labs runs at a
// loss; nova-ai sits at break-even against an INCOMPLETE supplier cost, so even
// that figure is a ceiling). Every breakdown below sums exactly to those totals
// so the page reads as one consistent business — ⚠ with ONE exception the
// server imposes, below: grouped by a supplier, an event type or a kind of
// work, the $199 subscription cannot be placed on any row, so those answers
// state it as context and read their revenue as unavailable at that grain
// (#510). Their rows sum to the $653.90 of usage; the subscription is the rest.
//
// ⚠ THOSE FIGURES MOVED IN #497 AND THIS PARAGRAPH IS WHY THEY ARE WRITTEN
// DOWN. It read $764.90 total and $565.90 usage revenue — the same totals
// less nova-ai's $88.00, which a customer-level revenue switch struck out of
// its revenue — and described that customer as having no recognised revenue
// at all. The switch is deleted, every customer's billed usage is its
// revenue, and the promise in the last sentence is the thing that would have
// quietly become false.
//
// ⚠ AND THE SHAPE MOVED IN #501, WHILE THE STORY DID NOT. Five routes served
// these figures and one question serves them now, so a fixture is an ANSWER —
// rows carrying one entry per measure — rather than five response bodies that
// had to be kept agreeing with each other by hand. The three revenue fields a
// customer row used to publish are one `customer_revenue` measure: the split
// between a subscription, a supplied figure and billed usage is not something
// the one query states, and the totals below are the sums they always were.

import {
  completePriceTotal,
  completeTotal,
  incompleteTotal,
  knownMeasures,
  measuresFor,
  revenueUnavailableAtThisGrain,
  type CostTotalScenario,
  type EconomicMeasureScenario,
  type RevenueContextScenario,
} from "@/lib/economic-scenarios";
import {
  EVERY_MEASURE,
  MONEY_MEASURES,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import type {
  ApiKeyList,
  ConnectStatus,
  Economics,
  PricingBookList,
  Unprofitable,
  Window,
} from "./types";

/**
 * A row's four measures, COMPOSED from `@/lib/economic-scenarios` (#510).
 *
 * The margin and every state are the composers' to derive, never this file's to
 * state: this builder used to write each measure by hand and pick the margin's
 * state from whether a margin was passed at all, which let a fixture describe a
 * margin `unavailable_at_requested_grain` beside a revenue reading `known` — a
 * row no server can write.
 */
function measuresOf(
  cost: CostTotalScenario,
  revenueMicros: number,
  events: number,
): EconomicMeasureScenario[] {
  return measuresFor({
    cost_micros: cost.micros,
    unresolved_event_count: cost.unresolved_event_count,
    revenue_micros: revenueMicros,
    events,
  });
}

/** One row of an answer, carrying exactly the measures its question asked for.
 *
 *  ⚠ A GROUPED ANSWER CARRIES NO COUNT, because the server refuses one: a count
 *  compared across rows that mix Event Types is not comparable, and three of
 *  the four breakdown axes mix them. A fixture that carried it would describe
 *  a response no server produces — which is why the measures are filtered to
 *  the question rather than taken whole from the composer. */
function economicRow({
  values = [],
  statuses = [],
  bucket = null,
  measures,
  asked = EVERY_MEASURE,
}: {
  values?: (string | null)[];
  statuses?: string[];
  bucket?: string | null;
  measures: EconomicMeasureScenario[];
  asked?: readonly AnalyticsMeasure[];
}): Economics["rows"][number] {
  return {
    bucket_start: bucket,
    grouping_field_value: values,
    grouping_field_value_status:
      statuses.length ? statuses : values.map((v) => (v === null ? "not_recorded" : "recorded")),
    measures: measures.filter((entry) => asked.includes(entry.measure)),
  };
}

/** A whole answer, echoing the request it answers. */
function economicAnswer({
  window,
  rows,
  groupBy = [],
  bucket = null,
  context = [],
}: {
  window?: Window;
  rows: Economics["rows"];
  groupBy?: string[];
  bucket?: string | null;
  context?: RevenueContextScenario[];
}): Economics {
  return {
    period_start: window?.start_date ?? "2020-07-01",
    period_end: window?.end_date ?? "2026-07-31",
    group_by: groupBy,
    bucket,
    basis: "recorded",
    // The two horizons every answer publishes, truncated or not.
    economic_data_available_from: "2020-07-01",
    measurement_data_available_from: "2026-01-01",
    rows,
    context,
  };
}

// Mirrors CUS_* in src/features/customers/api/mock-data.ts — keep in sync.
export const CUSTOMER_IDS = {
  acme: "1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001",
  luna: "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002",
  nova: "3b2e7c40-6d08-4b3c-9f5d-8c3100000003",
  seatEng: "4c3f6d51-5c97-4a4b-8a6e-9d4200000004",
  seatRes: "5d4a5e62-4b86-495a-9b7f-0e5300000005",
} as const;

// Each customer's supplier cost for the period, and how much of it UBB knows.
//
// COMPOSED, NEVER STATED FIELD BY FIELD (#371), for the reason the customers
// feature's identical block gives: a total and the count of events it had to
// skip are ONE fact, and `@/lib/economic-scenarios` returns them as one object
// so a fixture cannot take half. Both rosters compose them from the SAME
// module, which is as close as the layering lets these two files get to sharing
// the number — a cross-feature import is forbidden, and `lib/` is the seam that
// is not.
//
// nova-ai is the one incomplete customer in this story: its provider total
// renders as "at least $88.00" and its margin as a bound.
const ACME_PROVIDER_COST = completeTotal(274_000_000);
const LUNA_PROVIDER_COST = completeTotal(55_900_000);
const NOVA_PROVIDER_COST = incompleteTotal(88_000_000, 4);
const SEAT_ENG_PROVIDER_COST = completeTotal(96_300_000);
const SEAT_RES_PROVIDER_COST = completeTotal(49_400_000);

/**
 * The whole workspace's supplier cost for the window.
 *
 * SUMMED FROM THE ROSTER rather than typed out, which is what the comments on
 * the totals below already promised and nothing enforced. It is a floor by
 * nova-ai's four events and by no others, so the count comes from that row
 * rather than from a second literal — the overview's "at least $563.60" is
 * this object rendered.
 */
const WINDOW_PROVIDER_COST = incompleteTotal(
  ACME_PROVIDER_COST.micros +
    LUNA_PROVIDER_COST.micros +
    NOVA_PROVIDER_COST.micros +
    SEAT_ENG_PROVIDER_COST.micros +
    SEAT_RES_PROVIDER_COST.micros,
  NOVA_PROVIDER_COST.unresolved_event_count,
);

/** Every window this workspace has ever had, rolled up. */
const LIFETIME_PROVIDER_COST = incompleteTotal(
  6_690_150_000,
  WINDOW_PROVIDER_COST.unresolved_event_count,
);

/**
 * The five customers, as the one query answers them grouped by the customer
 * axis: `[customer_id, revenue, cost, margin, events]`.
 *
 * Mirrors the customers feature's roster — byte-identical economics, keep in
 * sync. The revenue is the whole of it: acme-corp's includes its $199
 * subscription, and every other row is its billed usage.
 */
const CUSTOMER_ROWS: [string, number, number, number, number][] = [
  [CUSTOMER_IDS.acme, 541_500_000, ACME_PROVIDER_COST.micros, 267_500_000, 48_213],
  [CUSTOMER_IDS.luna, 41_200_000, LUNA_PROVIDER_COST.micros, -14_700_000, 6_054],
  // nova-ai — THE ONE CUSTOMER IN THIS STORY WHOSE COGS IS INCOMPLETE (#330).
  // Four of its events carry a supplier cost UBB never learned, so its provider
  // total is a floor and its margin a ceiling, and the console has to say so
  // rather than print both as figures. At break-even that is the sharpest form
  // of it: the displayed margin is the best case.
  [CUSTOMER_IDS.nova, 88_000_000, NOVA_PROVIDER_COST.micros, 0, 12_882],
  [CUSTOMER_IDS.seatEng, 120_400_000, SEAT_ENG_PROVIDER_COST.micros, 24_100_000, 17_502],
  [CUSTOMER_IDS.seatRes, 61_800_000, SEAT_RES_PROVIDER_COST.micros, 12_400_000, 8_907],
];

export function mockCustomerEconomics(window: Window): Economics {
  return economicAnswer({
    window,
    groupBy: ["field:customer"],
    // Grouped by the customer, every revenue source CAN be placed — a
    // subscription names its customer — so these rows state their revenue
    // whole, the subscription inside acme-corp's. The margin column of the
    // tuple is the subtraction the composer performs, written down.
    rows: CUSTOMER_ROWS.map(([id, revenue, cost, , events]) =>
      economicRow({
        values: [id],
        measures: measuresOf(
          id === CUSTOMER_IDS.nova
            ? NOVA_PROVIDER_COST
            : completeTotal(cost),
          revenue,
          events,
        ),
        asked: MONEY_MEASURES,
      }),
    ),
  });
}

/** The workspace's totals — the exact sums over the roster above. */
export function mockTenantEconomics(window: Window): Economics {
  return economicAnswer({
    window,
    rows: [
      economicRow({
        // Revenue: 199,000,000 subscription + 653,900,000 billed usage. The
        // margin the composer derives is 852,900,000 - 563,600,000, the exact
        // sum of the five rows' margins above (267.5 - 14.7 + 0 + 24.1 +
        // 12.4, in millions). The events are the window's recorded work —
        // ungrouped, so the count compares with nothing and the server
        // answers it. The cost is the exact sum over the roster: only nova-ai
        // holds uncosted events, so the window's total is a floor by the same
        // four, and the margin is INCOMPLETE with it whatever the revenue
        // reads (§15).
        measures: measuresOf(WINDOW_PROVIDER_COST, 852_900_000, 93_558),
      }),
    ],
  });
}

export const MOCK_UNPROFITABLE: Unprofitable = {
  period_start: "2026-07-01",
  customers: [
    {
      customer_id: CUSTOMER_IDS.nova,
      external_id: "nova-ai",
      // BREAK-EVEN, NOT MINUS THE WHOLE COST (#497) — the roster row above
      // carries the reason. Still on this list, and the list is why the change
      // is worth reading twice: unprofitable is a THRESHOLD verdict the
      // alerting record holds, not "the margin is negative", so a customer
      // sitting at 0% against a minimum of 15% belongs here exactly as before.
      gross_margin_micros: 0,
      // The count is the ROSTER ROW's, not a second literal: this is the same
      // customer over the same window, and a margin beside a non-zero count is
      // a CEILING for exactly those events (#371).
      unresolved_event_count: NOVA_PROVIDER_COST.unresolved_event_count,
      unpriced_event_count: 0,
      margin_percentage: 0,
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
// The same window, grouped one axis at a time. Each axis sums exactly to the
// workspace totals above — analytics and margin read the same postings over the
// same window, so a story where they disagreed would be a story no server could
// produce.

type Row = [name: string | null, revenue: number, provider: number, events: number];

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

// ⚠ THE LAST ROW HAS NO VALUE, AND IT IS THE POINT OF THIS AXIS. Work recorded
// with no kind of work against it is a row like any other, carrying `null` with
// a status saying the value was never recorded — where the report this replaced
// bucketed it under an `(unattributed)` string that could not say whether the
// value was missing or the question did not apply.
const BY_TASK_TYPE: Row[] = [
  ["agent-api", 325_000_000, 280_000_000, 48_000],
  ["copilot", 190_900_000, 165_600_000, 26_558],
  ["batch-jobs", 88_000_000, 76_000_000, 13_000],
  [null, 50_000_000, 42_000_000, 6_000],
];

// Revenue/provider figures match the customer roster row-for-row.
const BY_CUSTOMER: Row[] = CUSTOMER_ROWS.map(
  ([id, revenue, cost, , events]) => [id, revenue, cost, events],
);

const AXIS_ROWS = {
  provider: BY_PROVIDER,
  event_type: BY_EVENT_TYPE,
  task_type: BY_TASK_TYPE,
  customer: BY_CUSTOMER,
} as const;

/**
 * acme-corp's subscription for the window, as an answer states money it could
 * not place.
 *
 * It names its customer and no supplier, event type or kind of work — the
 * server's `REVENUE_ATTRIBUTABLE_AXES` is the customer alone — and it can be
 * placed as finely as a day, because its accrual divides by days.
 */
function acmeSubscription(window: Window): RevenueContextScenario {
  return {
    source: "subscription",
    customer_id: CUSTOMER_IDS.acme,
    amount_micros: 199_000_000,
    window_start: window.start_date,
    window_end: window.end_date,
    attributable_axes: ["customer"],
    attributable_bucket: "day",
  };
}

export function mockGroupedEconomics(
  window: Window,
  groupBy: keyof typeof AXIS_ROWS,
): Economics {
  // ⚠ ONLY THE CUSTOMER AXIS CAN PLACE THE SUBSCRIPTION (#510). This fixture
  // used to answer every axis with `known` revenue, and the operational axes'
  // rows summed to $653.90 against a $852.90 workspace — the subscription
  // silently gone, on rows claiming to be whole. The server cannot produce that
  // answer: it reads each row's revenue as unavailable at that grain, draws no
  // margin, and states the subscription in `context`.
  if (groupBy === "customer") return mockCustomerEconomics(window);
  const subscription = acmeSubscription(window);
  return economicAnswer({
    window,
    groupBy: [`field:${groupBy}`],
    context: [subscription],
    rows: AXIS_ROWS[groupBy].map(([name, revenue, provider, events]) =>
      economicRow({
        values: [name],
        measures: revenueUnavailableAtThisGrain({
          cost: completeTotal(provider),
          revenue: completePriceTotal(revenue),
          events,
          context: [subscription],
        }).measures,
        asked: MONEY_MEASURES,
      }),
    ),
  });
}

export const MOCK_LIFETIME_ECONOMICS: Economics = economicAnswer({
  rows: [
    economicRow({
      // Lifetime spans the window, so it cannot count FEWER uncosted events
      // than the window does.
      measures: measuresOf(LIFETIME_PROVIDER_COST, 7_845_300_000, 812_441),
    }),
  ],
});

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
  revenue_micros: number;
  provider_cost_micros: number;
  event_count: number;
}

/**
 * Deterministic pseudo-variation so charts look alive but tests stay stable.
 * Scaled to the monthly story: ~$24–37 revenue / ~$20–27 provider per day.
 */
export function mockDailySeries(window: Window): MockDailyPoint[] {
  return daysInWindow(window).map((day, i) => ({
    day,
    revenue_micros: (24 + ((i * 37) % 13)) * 1_000_000,
    provider_cost_micros: (20 + ((i * 23) % 8)) * 1_000_000,
    event_count: 3_700 + ((i * 53) % 800),
  }));
}

/** The same series, as a day-bucketed answer. */
export function mockDailyEconomics(window: Window): Economics {
  return economicAnswer({
    window,
    bucket: "day",
    rows: mockDailySeries(window).map((point) =>
      economicRow({
        bucket: `${point.day}T00:00:00+00:00`,
        measures: knownMeasures({
          cost_micros: point.provider_cost_micros,
          revenue_micros: point.revenue_micros,
          events: point.event_count,
        }),
      }),
    ),
  });
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
