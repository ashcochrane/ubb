// Mock fixtures for the events feature — one coherent story, July 2026.
//
// Acme AI (the tenant) meters LLM usage for three customers:
//   - acme-prod  (customer A): heavy traffic, one balance-floor stop episode,
//     one killed task, a backfilled event, and a showcase "rich receipt".
//   - globex-dev (customer B): light traffic, nothing past-limit.
//   - initech-ai (customer C): no events yet (empty-ledger state).

import {
  availableMeasurements,
  knownCost,
  knownPrice,
  measurementsNotApplicable,
  priceNotApplicable,
  prunedMeasurements,
  unknownCost,
  unknownPrice,
  waivedPrice,
  type CustomerPriceScenario,
  type SupplierCostScenario,
} from "@/lib/economic-scenarios";

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
/**
 * The Task sold for one agreed price (#281). Its OWN id rather than a share of
 * one of the two above, because `closeTask` rolls up every event carrying the
 * id it is given: attributing this posting to the killed task would have
 * silently added an event and $2.50 to that task's closing totals, and no test
 * asserts those numbers today, so it would have gone unnoticed.
 */
export const TASK_FIXED_PRICE_ID = "8c1d6f24-9e37-4b05-a6d8-3f2b7c40e195";

export const EVENT_RICH_ID = "d41f7a92-5c3e-48b6-9a70-1e8f2c6b3d54";
export const EVENT_TIPPING_ID = "a97c3e51-8d2b-4f60-b813-5c4a9e7f1d20";
export const EVENT_LATE_ID = "b28e4f63-9a1c-4d75-8e02-6d5b0f8a2c31";
export const EVENT_LATE_2_ID = "e50a6b85-1c3e-4097-a124-8f7d2b0c4e63";
export const EVENT_TASK_KILL_ID = "c39f5a74-0b2d-4e86-9f13-7e6c1a9b3d42";
export const EVENT_BACKFILL_ID = "f61b7c96-2d4f-41a8-b235-9a8e3c1d5f74";
/** May traffic whose measurement detail passed its retention horizon (#281). */
export const EVENT_PRUNED_ID = "3d8c1e47-6f52-4a93-b70e-2c9a5f8d1b06";
/** A Task sold for one agreed price, so never measured at all (#281). */
export const EVENT_TASK_CHARGE_ID = "7a4e9d15-3b60-4c28-8f91-0d6b3e7a2c58";
/** July traffic whose supplier cost matched no Cost Rate, so was never learned
 * (#330). It is the only unresolved posting in this story, and the reason the
 * July totals over it are floors. */
export const EVENT_UNRESOLVED_ID = "6b2f8c30-4d71-4e59-9c18-5a3e7d0f4b92";
/** June traffic whose CUSTOMER PRICE UBB could not resolve, with a settled
 * supplier cost beside it (#351). The crossed case: the two completeness counts
 * are about different postings, and this is the row that proves it. */
export const EVENT_UNPRICED_ID = "1e7d4b09-8a36-4c52-b0f7-9d2c6e5a3f81";
/** A charge somebody decided not to pursue (#351). Same column shape as the
 * row above and a different meaning: reported as a loss, so no total is a floor
 * because of it. */
export const EVENT_WAIVED_ID = "9f3a5c28-7b14-4e60-8d29-4c1e6b0a7d53";
/** An event inside a Task sold for one agreed price, so it generates no
 * customer revenue at this level at all (#351). */
export const EVENT_PRICE_NOT_APPLICABLE_ID =
  "5c8b2e41-0d97-4a36-b1e5-7f3a9d2c6b84";
/** The killed task's other event, costed by CALCULATION where the kill event
 * beside it was REPORTED (#330). Two derivations, one complete task. */
export const EVENT_TASK_RATED_ID = "4f9a2d68-7c05-4b31-8e72-1b6d9a3f5c04";

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
  /**
   * The customer price and its status, as ONE object (#351).
   *
   * A bare `billed_cost_micros: number` sat here until the column went
   * nullable, exactly as a bare `provider_cost_micros` sat here until #330 —
   * and it stops being true the moment one seed does not carry a number. Three
   * of the four statuses null the amount, so composing the pair is what stops a
   * seed writing one half and letting a default invent the other.
   */
  price: CustomerPriceScenario;
  /**
   * The supplier cost, its status and — where there is one — the input that is
   * missing, as ONE object (#330).
   *
   * A bare `provider_cost_micros` used to sit here with the status supplied by
   * a constant in `makeDetail`, which was true while every seed carried a
   * number. It stops being true the moment one does not, and a `null` amount is
   * two different states: a cost UBB could not learn, and a cost there was
   * never going to be. Taking the trio from `@/lib/economic-scenarios` is what
   * stops a seed writing one of them and letting a default invent the rest —
   * the same rule, and the same reason, as `measurements_status` below.
   */
  cost: SupplierCostScenario;
  measurements?: Record<string, number>;
  metadata?: Record<string, unknown>;
  task_id?: string | null;
  stop_context?: Array<Record<string, unknown>> | null;
  pricing_provenance?: Record<string, unknown>;
  request_id?: string;
  idempotency_key?: string;
  /**
   * Whether the measured quantities can still be read (#271). Most seeds below
   * are metered postings whose measurement record is present, so the default
   * says so explicitly rather than being inferred from `measurements` being
   * empty — inferring it is exactly the mistake the field exists to end.
   *
   * THE DEFAULT IS ALSO THE HAZARD, which is why the two scenarios that are not
   * `available` set this pair through `@/lib/economic-scenarios` rather than by
   * hand. `?? "available"` over an empty bag is a confident "no usage" for a
   * payload that expired on schedule (#155 §9.1's `amount ?? 0`, in this
   * feature's clothes). A scenario returns the bag and the status as one
   * object, so a seed cannot take the bag and leave the status to the default.
   */
  measurements_status?: UsageEventDetail["measurements_status"];
}

function makeDetail(seed: DetailSeed): UsageEventDetail {
  // Keyed by the declared key with unset slots omitted, exactly as the API now
  // answers (#277).
  //
  // The keys stay spelled for the slots, and that is FORCED rather than lazy:
  // this mock tenant's declared keys have to match `TIMESERIES_GROUP_BY` in
  // `@/lib/labels`, which the group-by picker offers and which still lists
  // `dim1`/`dim2`/`dim3`. That list and the `dimensionLabel` map beside it are
  // the analytics grouping vocabulary, and both are recorded in the migration
  // ledger as slice 7's. Renaming the keys here without it would leave the
  // picker asking for an axis no posting carries, and every bar would read
  // "(unattributed)".
  const groupingFields: Record<string, string> = {};
  for (const [key, value] of [
    ["dim1", seed.dim1],
    ["dim2", seed.dim2],
    ["dim3", seed.dim3],
  ] as const) {
    if (value !== undefined && value !== "") groupingFields[key] = value;
  }
  return {
    id: seed.id,
    request_id: seed.request_id ?? `req_${seed.id.slice(0, 8)}`,
    idempotency_key: seed.idempotency_key ?? `idem_${seed.id.slice(0, 8)}`,
    // Both from the seed's one PRICE scenario object, for the same reason the
    // cost trio below comes from its own: a constant `"known"` beside a null
    // amount is the row the posting's check constraint refuses (#351).
    billed_cost_micros: seed.price.billed_cost_micros,
    pricing_status: seed.price.pricing_status,
    // All three from the seed's one scenario object. There is no default here
    // any more: the file now HAS an unresolved row to render, and a constant
    // `"known"` beside a null amount would be the exact row the posting's own
    // check constraint refuses.
    provider_cost_micros: seed.cost.provider_cost_micros,
    costing_status: seed.cost.costing_status,
    unresolved_reason: seed.cost.unresolved_reason,
    effective_at: seed.effective_at,
    created_at: seed.created_at ?? seed.effective_at,
    currency: "usd",
    event_type: seed.event_type ?? "chat.completion",
    provider: seed.provider ?? "openai",
    grouping_fields: groupingFields,
    measurements: seed.measurements ?? {},
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
    // ⚠ NO FLAT ADDEND (#369). A per-event uplift used to sit beside the
    // percentage here, because two markup rungs could supply one; both records
    // are deleted and the rung that remains takes ONE term, so a receipt
    // carrying a second would be recording a zero nobody declared.
    markup: {
      markup_percentage_micros: 28_000_000,
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
      price: knownPrice(187_500),
      cost: knownCost(142_300),
      // Composed rather than hand-built, because this is the event the
      // `available` rendering assertion runs against — so all three states the
      // receipt distinguishes come from the same module. The payload is
      // unchanged; what changes is that the status is stated here instead of
      // being supplied by the default below.
      ...availableMeasurements({ input_tokens: 4200, output_tokens: 1730 }),
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
        per_measurement: {
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
      price: knownPrice(96_000),
      cost: knownCost(75_000),
      measurements: { input_tokens: 2100, output_tokens: 940 },
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
      price: knownPrice(54_000),
      cost: knownCost(42_000),
      measurements: { input_tokens: 1200, output_tokens: 480 },
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
      price: knownPrice(31_000),
      cost: knownCost(24_000),
      measurements: { input_tokens: 800, output_tokens: 260 },
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
      price: knownPrice(64_000),
      cost: knownCost(50_000),
      measurements: { input_tokens: 1500, output_tokens: 620 },
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
      // THE KILLED TASK'S OTHER EVENT, AND IT WAS COSTED THE OTHER WAY (#330).
      // Its supplier cost was CALCULATED from Cost Rates; the kill event beside
      // it was REPORTED by the caller. The task therefore holds both derivations
      // and is nonetheless COMPLETE — nothing is missing from it — which is the
      // case the rule has to get right: how a cost was arrived at is not a
      // defect in it, and a footnote on every mixed total is a footnote on
      // almost every total.
      id: EVENT_TASK_RATED_ID,
      effective_at: "2026-07-21T09:02:44Z",
      created_at: "2026-07-21T09:02:45Z",
      event_type: "embedding.create",
      provider: "mistral",
      dim1: "batch",
      dim2: "batch-worker",
      price: knownPrice(38_400),
      cost: knownCost(30_000),
      measurements: { embedding_tokens: 7400 },
      metadata: { env: "prod", team: "assist" },
      task_id: TASK_KILLED_ID,
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "markup",
        cost_source: "cost_rate",
        cost_rate: { book: "llm-prices-2026", quantity: "embedding_tokens" },
      },
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
      price: knownPrice(22_400),
      cost: knownCost(17_500),
      measurements: { embedding_tokens: 5200 },
      metadata: {
        env: "prod",
        team: "search",
        backfill_batch: "2026-07-20-recovery",
      },
      pricing_provenance: markupProvenance(17_500),
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // THE ONE EVENT WHOSE SUPPLIER COST UBB NEVER LEARNED — #155 §9.2's owed
      // fixture for the state slice 3 introduces, and the reason every total
      // over the July window is now a floor rather than a figure.
      //
      // IN the July window on purpose, unlike the two measurement fixtures
      // below. Those had to stay outside it so the story's totals kept their
      // arithmetic; this one has to be inside it, because the thing it exists
      // to exercise IS a total. Its billed amount is real and counted; its
      // supplier cost contributes nothing, and the count beside every total
      // says so.
      //
      // It also belongs to the still-open task, so closing that task shows what
      // a partial Task COGS reads like — the surface the rule was written for.
      id: EVENT_UNRESOLVED_ID,
      effective_at: "2026-07-22T14:08:31Z",
      created_at: "2026-07-22T14:08:32Z",
      event_type: "transcription.create",
      provider: "deepgram",
      dim1: "search-api",
      dim2: "realtime-api",
      price: knownPrice(31_000),
      // No Cost Rate matched this quantity at the moment it happened, so there
      // is nothing to record and the receipt says which input is missing —
      // never a zero, which would state that the supplier charged nothing.
      cost: unknownCost("cost_rate_missing"),
      measurements: { audio_seconds: 412 },
      metadata: { env: "prod", team: "assist" },
      task_id: TASK_OPEN_ID,
      // A billed amount with no supplier cost under it: the engine priced this
      // event directly rather than as a markup over a cost it does not have.
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "price_rule",
        cost_source: "unresolved",
      },
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // ⚠ THE MIRROR OF THE ROW ABOVE, AND #155 §9.2'S OWED FIXTURE FOR THE
      // STATE #351 INTRODUCES: a posting whose SUPPLIER COST is settled and
      // whose CUSTOMER PRICE UBB could not resolve.
      //
      // Deliberately the crossed case rather than a row missing both. The two
      // completeness counts are about different postings, and a fixture that
      // put both absences on one event would pass against a console that read
      // either count for the other — which is the defect the second count
      // exists to make impossible.
      //
      // Dated OUTSIDE the July window, like the two measurement fixtures
      // below, so the coherent July story above keeps its totals and its
      // counts. What it exercises is the detail view and the ledger row, which
      // is where an unresolved price rendered as `$0.00` would say the tenant
      // charged their customer nothing.
      id: EVENT_UNPRICED_ID,
      effective_at: "2026-06-11T11:27:03Z",
      created_at: "2026-06-11T11:27:04Z",
      event_type: "rerank.create",
      provider: "cohere",
      dim1: "search-api",
      price: unknownPrice(),
      cost: knownCost(19_000),
      measurements: { rerank_documents: 240 },
      metadata: { env: "prod", team: "search" },
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "unresolved",
        cost_source: "cost_rate",
      },
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // The OTHER two absent price states, so all three of them have a fixture
      // and a rendering assertion (#155 §9.2). They share a column shape with
      // the row above — a null amount — and differ only by status, which is the
      // whole reason the console cannot read the amount and guess.
      //
      // A charge somebody decided not to pursue. Reported as a loss, so the
      // revenue really is nothing and no total is a floor because of it.
      id: EVENT_WAIVED_ID,
      effective_at: "2026-06-12T09:41:55Z",
      created_at: "2026-06-12T09:41:56Z",
      event_type: "chat.completion",
      provider: "openai",
      dim1: "support-bot",
      price: waivedPrice(),
      cost: knownCost(12_500),
      measurements: { input_tokens: 900, output_tokens: 140 },
      metadata: { env: "prod", team: "support" },
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "waived",
        cost_source: "cost_rate",
      },
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // An event inside a Task sold for one agreed price: the revenue is the
      // Task's and none of it is this event's, so there is no customer price
      // here to resolve or to miss.
      id: EVENT_PRICE_NOT_APPLICABLE_ID,
      effective_at: "2026-06-13T16:08:22Z",
      created_at: "2026-06-13T16:08:23Z",
      event_type: "chat.completion",
      provider: "anthropic",
      dim1: "onboarding",
      price: priceNotApplicable(),
      cost: knownCost(8_400),
      measurements: { input_tokens: 610, output_tokens: 95 },
      metadata: { env: "prod", team: "onboarding" },
      task_id: TASK_FIXED_PRICE_ID,
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "not_applicable",
        cost_source: "cost_rate",
      },
    }),
  },
  // The two events whose measurement record is NOT simply present — #155 §9.2's
  // owed fixtures for the state slice 2 introduces. Both are dated outside the
  // July window the analytics surfaces and the margin period cover, so the
  // coherent July story above keeps its totals and its counts.
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // May traffic. The retention horizon has passed and the measurement
      // detail is gone; the charge it produced is not, and that is the whole
      // reason the receipt must say which of the two happened.
      id: EVENT_PRUNED_ID,
      effective_at: "2026-05-02T11:27:53Z",
      created_at: "2026-05-02T11:27:54Z",
      dim1: "copilot",
      price: knownPrice(94_000),
      cost: knownCost(73_000),
      metadata: { env: "prod", team: "search" },
      pricing_provenance: markupProvenance(73_000),
      ...prunedMeasurements(),
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // A Task sold for one agreed price. Nothing was ever measured, so there
      // is nothing a retention horizon could have removed — the empty bag here
      // and the empty bag above are the same object and different facts.
      id: EVENT_TASK_CHARGE_ID,
      effective_at: "2026-06-11T08:14:02Z",
      created_at: "2026-06-11T08:14:03Z",
      event_type: "task.charge",
      dim1: "batch",
      price: knownPrice(2_500_000),
      cost: knownCost(1_840_000),
      metadata: { env: "prod", team: "assist" },
      task_id: TASK_FIXED_PRICE_ID,
      pricing_provenance: {
        engine_version: "pricing-engine/4.2.1",
        billed_source: "fixed_price",
        cost_source: "caller_reported",
      },
      ...measurementsNotApplicable(),
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
      price: knownPrice(billed),
      cost: knownCost(providerCost),
      measurements: {
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
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 50_040_000,
    margin_percentage: 93.3,
  },
  {
    customer_id: CUSTOMER_B_ID,
    subscription_revenue_micros: 19_000_000,
    usage_billed_micros: 410_000,
    usage_revenue_micros: 410_000,
    provider_cost_micros: 320_000,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    gross_margin_micros: 19_090_000,
    margin_percentage: 98.4,
  },
  {
    customer_id: CUSTOMER_C_ID,
    subscription_revenue_micros: 9_000_000,
    usage_billed_micros: 0,
    usage_revenue_micros: 0,
    provider_cost_micros: 0,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
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
    unresolved_event_count: 0,
    unpriced_event_count: 0,
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
