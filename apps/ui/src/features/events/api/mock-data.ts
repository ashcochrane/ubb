// Mock fixtures for the events feature — one coherent story, July 2026.
//
// Acme AI (the tenant) meters LLM usage for three customers:
//   - acme-prod  (customer A): heavy traffic, one balance-floor stop episode,
//     one killed task, a backfilled event, and a showcase "rich receipt".
//   - globex-dev (customer B): light traffic, nothing past-limit.
//   - initech-ai (customer C): no events yet (empty-ledger state).

import type {
  CustomerMargin,
  MarginCustomerRow,
  PastLimitReport,
  UsageEventDetail,
} from "./types";

export const CUSTOMER_A_ID = "7f3c2a10-9b4e-4c9a-8f21-6d5e8a301b42";
export const CUSTOMER_B_ID = "2b9d4e77-1c3f-4a52-9e08-b4a6c1f92d15";
export const CUSTOMER_C_ID = "c1a8e5f3-6d2b-4b70-a934-08f7d21c65e9";

export const CUSTOMER_A_EXTERNAL = "acme-prod";
export const CUSTOMER_B_EXTERNAL = "globex-dev";
export const CUSTOMER_C_EXTERNAL = "initech-ai";

/** Task killed by its COGS limit on July 21 — closing it keeps `killed`. */
export const TASK_KILLED_ID = "9a7b3c1d-2e4f-46a8-b950-7c3d1e8f2a64";
/** Still-active task — closing it completes it. */
export const TASK_OPEN_ID = "5e2f8a9c-7b1d-4d36-a284-9f6c0b3e7d51";

export const EVENT_RICH_ID = "d41f7a92-5c3e-48b6-9a70-1e8f2c6b3d54";
export const EVENT_TIPPING_ID = "a97c3e51-8d2b-4f60-b813-5c4a9e7f1d20";
export const EVENT_LATE_ID = "b28e4f63-9a1c-4d75-8e02-6d5b0f8a2c31";
export const EVENT_LATE_2_ID = "e50a6b85-1c3e-4097-a124-8f7d2b0c4e63";
export const EVENT_TASK_KILL_ID = "c39f5a74-0b2d-4e86-9f13-7e6c1a9b3d42";
export const EVENT_BACKFILL_ID = "f61b7c96-2d4f-41a8-b235-9a8e3c1d5f74";

export interface MockEvent {
  customer_id: string;
  detail: UsageEventDetail;
}

interface DetailSeed {
  id: string;
  effective_at: string;
  created_at?: string;
  event_type?: string;
  provider?: string;
  dim1?: string;
  dim2?: string;
  dim3?: string;
  billed_cost_micros: number;
  provider_cost_micros: number;
  usage_metrics?: Record<string, number>;
  metadata?: Record<string, unknown>;
  task_id?: string | null;
  stop_context?: Array<Record<string, unknown>> | null;
  pricing_provenance?: Record<string, unknown>;
  request_id?: string;
  idempotency_key?: string;
  /**
   * Whether the measured quantities can still be read (#271). Every seed below
   * is a metered posting whose measurement record is present, so the default
   * says so explicitly rather than being inferred from `usage_metrics` being
   * empty — inferring it is exactly the mistake the field exists to end. The
   * pruned and not-applicable scenarios arrive with the canonical scenario
   * module in #281.
   */
  measurements_status?: UsageEventDetail["measurements_status"];
}

function makeDetail(seed: DetailSeed): UsageEventDetail {
  return {
    id: seed.id,
    request_id: seed.request_id ?? `req_${seed.id.slice(0, 8)}`,
    idempotency_key: seed.idempotency_key ?? `idem_${seed.id.slice(0, 8)}`,
    billed_cost_micros: seed.billed_cost_micros,
    provider_cost_micros: seed.provider_cost_micros,
    effective_at: seed.effective_at,
    created_at: seed.created_at ?? seed.effective_at,
    currency: "usd",
    event_type: seed.event_type ?? "chat.completion",
    provider: seed.provider ?? "openai",
    dim1: seed.dim1 ?? "",
    dim2: seed.dim2 ?? "",
    dim3: seed.dim3 ?? "",
    usage_metrics: seed.usage_metrics ?? {},
    measurements_status: seed.measurements_status ?? "available",
    pricing_provenance: seed.pricing_provenance ?? {},
    metadata: seed.metadata ?? {},
    task_id: seed.task_id ?? null,
    stop_context: seed.stop_context ?? null,
  };
}

function markupProvenance(providerCostMicros: number): Record<string, unknown> {
  return {
    engine_version: "pricing-engine/4.2.1",
    billed_source: "markup",
    cost_source: "caller_reported",
    markup: {
      markup_percentage_micros: 28_000_000,
      fixed_uplift_micros: 0,
      base_provider_cost_micros: providerCostMicros,
    },
  };
}

// ---------------------------------------------------------------------------
// Handcrafted feature events (customer A).

const FEATURE_EVENTS: MockEvent[] = [
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_RICH_ID,
      effective_at: "2026-07-23T09:41:27Z",
      created_at: "2026-07-23T09:41:29Z",
      event_type: "chat.completion",
      provider: "openai",
      dim1: "copilot",
      dim2: "realtime-api",
      dim3: "agent-7",
      billed_cost_micros: 187_500,
      provider_cost_micros: 142_300,
      usage_metrics: { input_tokens: 4200, output_tokens: 1730 },
      metadata: {
        env: "prod",
        team: "search",
        model: "gpt-5",
        request: { model: "gpt-5", region: "us-east-1", stream: true },
        latency_ms: 812,
        client: { sdk: "ubb-node@3.0.0" },
      },
      task_id: TASK_OPEN_ID,
      request_id: "req_search_reindex_0042",
      idempotency_key: "idem_search_reindex_0042",
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "price_card",
        price_card: {
          book_key: "llm-prices-2026",
          book_id: "b7e2d914-3a5c-4f80-9b16-2c7d8e0a1f43",
          version: 7,
        },
        cost_source: "cost_card",
        cost_card: { book_key: "openai-cogs", version: 3 },
        per_metric: {
          input_tokens: {
            rate_per_unit_micros: 30_000,
            unit_quantity: 1000,
            amount_micros: 126_000,
          },
          output_tokens: {
            rate_per_unit_micros: 35_500,
            unit_quantity: 1000,
            amount_micros: 61_500,
          },
        },
      },
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_TIPPING_ID,
      effective_at: "2026-07-18T14:02:11Z",
      created_at: "2026-07-18T14:02:12Z",
      billed_cost_micros: 96_000,
      provider_cost_micros: 75_000,
      usage_metrics: { input_tokens: 2100, output_tokens: 940 },
      metadata: { env: "prod", team: "assist", region: "us-east-1" },
      pricing_provenance: markupProvenance(75_000),
      stop_context: [
        {
          limit: "customer_floor",
          stop_scope: "customer",
          tripped_at: "2026-07-18T14:02:11Z",
          episode_seq: 3,
          task_id: null,
          subtask_id: null,
          arrived_after: false,
        },
      ],
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_LATE_ID,
      effective_at: "2026-07-18T14:03:27Z",
      created_at: "2026-07-18T14:03:28Z",
      billed_cost_micros: 54_000,
      provider_cost_micros: 42_000,
      usage_metrics: { input_tokens: 1200, output_tokens: 480 },
      metadata: { env: "prod", team: "assist" },
      pricing_provenance: markupProvenance(42_000),
      stop_context: [
        {
          limit: "customer_floor",
          stop_scope: "customer",
          tripped_at: "2026-07-18T14:02:11Z",
          episode_seq: 3,
          task_id: null,
          subtask_id: null,
          arrived_after: true,
        },
      ],
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_LATE_2_ID,
      effective_at: "2026-07-18T14:05:44Z",
      created_at: "2026-07-18T14:05:45Z",
      provider: "anthropic",
      event_type: "messages.create",
      billed_cost_micros: 31_000,
      provider_cost_micros: 24_000,
      usage_metrics: { input_tokens: 800, output_tokens: 260 },
      metadata: { env: "prod", team: "assist" },
      pricing_provenance: markupProvenance(24_000),
      stop_context: [
        {
          limit: "customer_floor",
          stop_scope: "customer",
          tripped_at: "2026-07-18T14:02:11Z",
          episode_seq: 3,
          task_id: null,
          subtask_id: null,
          arrived_after: true,
        },
      ],
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_TASK_KILL_ID,
      effective_at: "2026-07-21T09:16:05Z",
      created_at: "2026-07-21T09:16:06Z",
      dim1: "batch",
      dim2: "batch-worker",
      billed_cost_micros: 64_000,
      provider_cost_micros: 50_000,
      usage_metrics: { input_tokens: 1500, output_tokens: 620 },
      metadata: { env: "prod", team: "assist" },
      task_id: TASK_KILLED_ID,
      pricing_provenance: markupProvenance(50_000),
      stop_context: [
        {
          limit: "task_limit",
          stop_scope: "task",
          tripped_at: "2026-07-21T09:15:33Z",
          episode_seq: null,
          task_id: TASK_KILLED_ID,
          subtask_id: null,
          arrived_after: true,
        },
      ],
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_BACKFILL_ID,
      effective_at: "2026-07-06T18:22:40Z",
      created_at: "2026-07-20T10:04:15Z",
      event_type: "embedding.create",
      dim1: "search-api",
      billed_cost_micros: 22_400,
      provider_cost_micros: 17_500,
      usage_metrics: { embedding_tokens: 5200 },
      metadata: {
        env: "prod",
        team: "search",
        backfill_batch: "2026-07-20-recovery",
      },
      pricing_provenance: markupProvenance(17_500),
    }),
  },
];

// ---------------------------------------------------------------------------
// Generated filler traffic.

const PROVIDERS = ["openai", "anthropic", "mistral"] as const;
const PRODUCT_IDS = ["copilot", "search-api", "batch"] as const;

function fillerEvent(index: number, customerId: string, idPrefix: string): MockEvent {
  const day = 5 + (index % 19); // July 5–23
  const hour = (index * 5) % 22;
  const minute = (index * 13) % 60;
  const provider = PROVIDERS[index % PROVIDERS.length] ?? "openai";
  const eventType = index % 3 === 0 ? "embedding.create" : "chat.completion";
  const providerCost = 38_000 + (index % 17) * 9_500;
  const billed = Math.round(providerCost * 1.28);
  const effective = `2026-07-${String(day).padStart(2, "0")}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:12Z`;
  return {
    customer_id: customerId,
    detail: makeDetail({
      id: `${idPrefix}-0000-4000-8000-${String(index).padStart(12, "0")}`,
      effective_at: effective,
      created_at: effective,
      provider,
      event_type: eventType,
      dim1: PRODUCT_IDS[index % PRODUCT_IDS.length] ?? "copilot",
      dim2: index % 4 === 0 ? "batch-worker" : "realtime-api",
      dim3: index % 5 === 0 ? "agent-7" : "",
      billed_cost_micros: billed,
      provider_cost_micros: providerCost,
      usage_metrics: {
        input_tokens: 900 + (index % 23) * 240,
        output_tokens: 260 + (index % 11) * 145,
      },
      metadata: {
        env: index % 4 === 0 ? "staging" : "prod",
        team: index % 2 === 0 ? "search" : "assist",
        region: index % 2 === 0 ? "us-east-1" : "eu-west-1",
        model:
          provider === "openai"
            ? "gpt-5"
            : provider === "anthropic"
              ? "claude-5"
              : "mistral-large",
      },
      pricing_provenance: markupProvenance(providerCost),
      task_id: index % 6 === 0 ? TASK_OPEN_ID : null,
    }),
  };
}

const FILLER_A = Array.from({ length: 58 }, (_, i) =>
  fillerEvent(i, CUSTOMER_A_ID, "f0a1b2c3"),
);
const FILLER_B = Array.from({ length: 5 }, (_, i) =>
  fillerEvent(i * 7 + 2, CUSTOMER_B_ID, "f1b2c3d4"),
);

export const ALL_EVENTS: MockEvent[] = [
  ...FEATURE_EVENTS,
  ...FILLER_A,
  ...FILLER_B,
];

// ---------------------------------------------------------------------------
// Margin surfaces (the customer picker source + external-id resolution).

export const MARGIN_PERIOD = { start: "2026-07-01", end: "2026-07-25" };

export const MARGIN_CUSTOMERS: MarginCustomerRow[] = [
  {
    customer_id: CUSTOMER_A_ID,
    subscription_revenue_micros: 49_000_000,
    usage_billed_micros: 4_620_000,
    usage_revenue_micros: 4_620_000,
    provider_cost_micros: 3_580_000,
    gross_margin_micros: 50_040_000,
    margin_percentage: 93.3,
  },
  {
    customer_id: CUSTOMER_B_ID,
    subscription_revenue_micros: 19_000_000,
    usage_billed_micros: 410_000,
    usage_revenue_micros: 410_000,
    provider_cost_micros: 320_000,
    gross_margin_micros: 19_090_000,
    margin_percentage: 98.4,
  },
  {
    customer_id: CUSTOMER_C_ID,
    subscription_revenue_micros: 9_000_000,
    usage_billed_micros: 0,
    usage_revenue_micros: 0,
    provider_cost_micros: 0,
    gross_margin_micros: 9_000_000,
    margin_percentage: 100,
  },
];

function marginDetail(
  row: MarginCustomerRow,
  externalId: string,
  eventCount: number,
): CustomerMargin {
  return {
    customer_id: row.customer_id,
    external_id: externalId,
    period: MARGIN_PERIOD,
    revenue_mode: "billed",
    event_count: eventCount,
    subscription_revenue_micros: row.subscription_revenue_micros,
    usage_billed_micros: row.usage_billed_micros,
    usage_revenue_micros: row.usage_revenue_micros,
    provider_cost_micros: row.provider_cost_micros,
    total_revenue_micros:
      row.subscription_revenue_micros + row.usage_revenue_micros,
    gross_margin_micros: row.gross_margin_micros,
    margin_percentage: row.margin_percentage,
  };
}

export const CUSTOMER_MARGIN_BY_ID: Record<string, CustomerMargin> = {
  [CUSTOMER_A_ID]: marginDetail(MARGIN_CUSTOMERS[0]!, CUSTOMER_A_EXTERNAL, 64),
  [CUSTOMER_B_ID]: marginDetail(MARGIN_CUSTOMERS[1]!, CUSTOMER_B_EXTERNAL, 5),
  [CUSTOMER_C_ID]: marginDetail(MARGIN_CUSTOMERS[2]!, CUSTOMER_C_EXTERNAL, 0),
};

// ---------------------------------------------------------------------------
// Past-limit report fixtures.

export const PAST_LIMIT_REPORTS: Record<string, PastLimitReport> = {
  [CUSTOMER_A_ID]: {
    customer_id: CUSTOMER_A_ID,
    billing_owner_id: CUSTOMER_A_ID,
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
        tripped_at: "2026-07-17T22:10:04Z",
        resumed_at: "2026-07-18T03:00:41Z",
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
        tripped_at: "2026-07-18T14:02:11Z",
        resumed_at: "2026-07-18T16:40:22Z",
        events: [
          {
            event_id: EVENT_TIPPING_ID,
            effective_at: "2026-07-18T14:02:11Z",
            billed_cost_micros: 96_000,
            provider_cost_micros: 75_000,
            arrived_after: false,
          },
          {
            event_id: EVENT_LATE_ID,
            effective_at: "2026-07-18T14:03:27Z",
            billed_cost_micros: 54_000,
            provider_cost_micros: 42_000,
            arrived_after: true,
          },
          {
            event_id: EVENT_LATE_2_ID,
            effective_at: "2026-07-18T14:05:44Z",
            billed_cost_micros: 31_000,
            provider_cost_micros: 24_000,
            arrived_after: true,
          },
        ],
        event_count: 3,
        total_billed_cost_micros: 181_000,
        total_provider_cost_micros: 141_000,
      },
      {
        family: "task",
        limit: "task_limit",
        stop_scope: "task",
        episode_seq: null,
        task_id: TASK_KILLED_ID,
        subtask_id: null,
        provider_cost_limit_micros: 5_000_000,
        tripped_at: "2026-07-21T09:15:33Z",
        resumed_at: null,
        events: [
          {
            event_id: EVENT_TASK_KILL_ID,
            effective_at: "2026-07-21T09:16:05Z",
            billed_cost_micros: 64_000,
            provider_cost_micros: 50_000,
            arrived_after: true,
          },
        ],
        event_count: 1,
        total_billed_cost_micros: 64_000,
        total_provider_cost_micros: 50_000,
      },
    ],
    totals_per_limit: {
      customer_floor: {
        billed_cost_micros: 181_000,
        provider_cost_micros: 141_000,
        event_count: 3,
      },
      task_limit: {
        billed_cost_micros: 64_000,
        provider_cost_micros: 50_000,
        event_count: 1,
      },
    },
  },
  [CUSTOMER_B_ID]: {
    customer_id: CUSTOMER_B_ID,
    billing_owner_id: CUSTOMER_B_ID,
    since: null,
    until: null,
    episodes: [],
    totals_per_limit: {},
  },
  [CUSTOMER_C_ID]: {
    customer_id: CUSTOMER_C_ID,
    billing_owner_id: CUSTOMER_C_ID,
    since: null,
    until: null,
    episodes: [],
    totals_per_limit: {},
  },
};
