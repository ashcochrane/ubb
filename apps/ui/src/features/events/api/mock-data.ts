// Mock fixtures for the events feature — one coherent story, July 2026.
//
// Acme AI (the tenant) meters LLM usage for three customers:
//   - acme-prod  (customer A): heavy traffic, one balance-floor stop episode,
//     one killed task, a backfilled event, and a showcase "rich receipt".
//   - globex-dev (customer B): light traffic, nothing past-limit.
//   - initech-ai (customer C): no events yet (empty-ledger state).

import {
  availableMeasurements,
  costNotApplicable,
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
  CostingMethod,
  PricingMethod,
  UsageEventKind,
} from "@/lib/vocabulary";

// The receipt's per-quantity component. Its shape lives one module over
// because the record's key for a measured quantity is a word this file may
// not spell — see `../lib/receipt` for the whole argument.
import { receiptComponent, type ReceiptComponent } from "../lib/receipt";

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
/** An event whose type declares no supplier cost at all, so its empty cost is
 * an absence no recovery will ever fill — the opposite fact to
 * `EVENT_UNRESOLVED_ID`'s, wearing the same null column (#371). */
export const EVENT_COST_NOT_APPLICABLE_ID =
  "2f6a0c93-8d51-4b74-a3e6-1c9f5b28d740";
/** The killed task's other event, costed by CALCULATION where the kill event
 * beside it was REPORTED (#330). Two derivations, one complete task. */
export const EVENT_TASK_RATED_ID = "4f9a2d68-7c05-4b31-8e72-1b6d9a3f5c04";
/**
 * The margin-priced half of spec §21's pair (#372): an `embedding.create`
 * charged as a margin over what the call cost.
 */
export const EVENT_MARGIN_PRICED_ID = "0a3e7c62-4b19-4d85-9f30-6e2b8d1c5a47";
/**
 * The directly-priced half of the SAME Event Type, for a different customer.
 * Same work, same provider, same quantities — a different deal, and the
 * receipts say so.
 */
export const EVENT_DIRECTLY_PRICED_ID = "8d5f1b04-2c76-4e93-a018-3b7e9c4d6e2a";

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
  /**
   * How the price was derived, where one was.
   *
   * ⚠ **REQUIRED EXACTLY WHERE THE PRICE SETTLED, AND THE BUILDER ENFORCES IT
   * RATHER THAN TRUSTING IT.** A receipt's method is how an amount was arrived
   * at, so it is present exactly when the status is `known` — the record's own
   * rule, asked of both sections (`pricing/receipts.py::_validate_section`). A
   * seed that stated a method beside a waived charge would be describing a
   * record the boundary refuses, and the console would then be tested against a
   * receipt it will never be sent.
   */
  pricing_method?: PricingMethod;
  /**
   * The basis a margin was taken over, where the method is one.
   *
   * Stating it turns the method into `margin_over_cost` and writes the terms,
   * because the two are the same fact: the record carries `markup` in the price
   * section's detail exactly when the method is a margin, and a seed that could
   * set one without the other would be able to write a receipt that says a
   * margin was taken and does not say over what.
   */
  markup_micro_percent?: number;
  /** How UBB came by the supplier's figure, where it has one. */
  costing_method?: CostingMethod;
  /** The per-quantity lines that explain each amount, by value. */
  price_components?: ReceiptComponent[];
  cost_components?: ReceiptComponent[];
  /** Cross-reference ids — and never anything a reader could take a figure from. */
  provenance?: Record<string, unknown>;
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
  /**
   * Which kind of posting this is (#417). Defaults to `metered_usage`, which is
   * what every seed but one is: a real event a caller reported.
   *
   * ⚠ **IT IS NOT INDEPENDENT OF `measurements_status` ABOVE**, and the pair is
   * why this field could not simply be defaulted everywhere. `not_applicable`
   * is DERIVED from the kind — the backend reads the kind first and never looks
   * at the record — so a seed composing `measurementsNotApplicable()` while
   * calling itself `metered_usage` describes a posting the derivation cannot
   * produce. The one seed that does compose it says so here.
   */
  kind?: UsageEventKind;
}

/**
 * The id that correlates a posting with the call that produced it.
 *
 * Derived from the posting's own id so a seed states it only when it means
 * something by it.
 *
 * THIS WAS `correlationIds`, PLURAL, AND RETURNED TWO. The second key was a
 * retired term under a console spread ceiling, and hiding it behind this export
 * so that no other file had to spell it was most of why the helper existed
 * (#366, Phase B's second technique). #411 deleted the field, so there is one
 * correlation value left and the plural name would now be a false description
 * of what this returns. What survives is the weaker, real reason: a seed should
 * not have to restate an id it does not care about.
 */
export function correlationId(
  id: string,
  stated: { idempotency_key?: string } = {},
) {
  return {
    idempotency_key: stated.idempotency_key ?? `idem_${id.slice(0, 8)}`,
  };
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
    // WHICH KIND OF POSTING THIS IS (#417), defaulted rather than required:
    // every seed but one is a real event a caller reported, and spelling that
    // on each of them would be noise around the one that is not.
    kind: seed.kind ?? "metered_usage",
    ...correlationId(seed.id, seed),
    // All three from the seed's one PRICE scenario object, for the same reason
    // the cost trio below comes from its own: a constant `"known"` beside a
    // null amount is the row the posting's check constraint refuses (#351).
    //
    // ⚠ THE REASON IS THE THIRD OF THEM NOW (#371), and it is read only under
    // `not_applicable`. Defaulting it here — `?? null`, or omitting it — would
    // put back exactly what the scenario object exists to prevent: a seed that
    // says a price does not apply and lets the file decide, silently, that
    // nobody knows why. The two causes are different answers to the reader.
    billed_cost_micros: seed.price.billed_cost_micros,
    pricing_status: seed.price.pricing_status,
    not_applicable_reason: seed.price.not_applicable_reason,
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
    pricing_receipt: pricingReceipt(seed),
    // DERIVED FROM THE RECEIPT AND NEVER STATED BESIDE IT. The column is what
    // the engine wrote off the record's own price section, so a seed that could
    // set the two apart would be describing a posting whose receipt and whose
    // column disagree about how its price was worked out — and the console
    // would then be tested against a payload the backend cannot produce.
    pricing_method: methodOf(seed),
    metadata: seed.metadata ?? {},
    task_id: seed.task_id ?? null,
    stop_context: seed.stop_context ?? null,
  };
}

/** The shape a receipt written today declares (`receipts.RECEIPT_SCHEMA_VERSION`). */
const RECEIPT_SCHEMA_VERSION = 1;

/** The engine that computed it (`pricing_service.PRICING_ENGINE_VERSION`). */
const PRICING_ENGINE_VERSION = "2.1.0";

/**
 * How this seed's price was derived, or that none was.
 *
 * ⚠ **A METHOD IS PRESENT EXACTLY WHERE THE STATUS IS SETTLED**, which is the
 * receipt's own rule rather than a convenience: a method is how an amount was
 * arrived at, so a waived charge or a price UBB never resolved has none. Stating
 * it in one function means the receipt's section and the posting's column read
 * the same answer and cannot drift.
 */
function methodOf(seed: DetailSeed): PricingMethod | null {
  if (seed.price.pricing_status !== "known") return null;
  if (seed.markup_micro_percent != null) return "margin_over_cost";
  return seed.pricing_method ?? "direct_event_price";
}

/**
 * The Pricing Receipt, in the shape the engine actually writes.
 *
 * ⚠ **THIS IS THE RECORD, NOT A SKETCH OF ONE (#349, #370 forward).** The
 * fixture this replaces was the pre-sectioned shape — `engine_version`,
 * `billed_source`, a `per_measurement` bag — invented by the console before the
 * record existed, and #370 recorded the rebuild as this commit's. The real
 * record is two versions, a typed subject, a costing and a pricing section each
 * holding their method, status and detail BY VALUE, the totals, and a
 * provenance section of cross-reference ids that nothing reads to reconstruct
 * an amount (`pricing/receipts.py`).
 *
 * ⚠ **AND IT IS ASSEMBLED FROM THE SEED'S OWN SCENARIOS RATHER THAN WRITTEN
 * BESIDE THEM.** Every invariant `validate_receipt` enforces is a pairing:
 * a section's method is present exactly when its status is settled, its amount
 * is present on the same condition, and a margin's terms are present exactly
 * when the method is a margin. A hand-written literal can violate all three
 * silently — the console has no validator — so it is derived from the pair the
 * seed already states, which is the same rule `@/lib/economic-scenarios`
 * applies one layer down.
 */
function pricingReceipt(seed: DetailSeed): Record<string, unknown> {
  const method = methodOf(seed);
  const costSettled = seed.cost.costing_status === "known";
  return {
    receipt_schema_version: RECEIPT_SCHEMA_VERSION,
    pricing_engine_version: PRICING_ENGINE_VERSION,
    subject_type: "usage_event",
    subject_id: seed.id,
    effective_at: seed.effective_at,
    currency: "usd",
    costing: {
      method: costSettled ? (seed.costing_method ?? "calculated") : null,
      status: seed.cost.costing_status,
      detail: {
        ...(seed.cost_components ? { components: seed.cost_components } : {}),
        // WHICH INPUT DID NOT ARRIVE, on the record rather than only on the
        // column: the status says a cost is unresolved and this says why.
        unresolved_reason: seed.cost.unresolved_reason,
      },
    },
    pricing: {
      method,
      status: seed.price.pricing_status,
      detail: {
        ...(seed.price_components ? { components: seed.price_components } : {}),
        // THE SUBJECT'S WHOLE-JOB PRICING REGIME, BY VALUE. Every unit of work
        // in this system is event-priced today; the receipt says so out loud
        // rather than leaving the axis out, so a record written now is still
        // explicit about it years from now.
        pricing_mode: "event_priced",
        // ⚠ ONE TERM BESIDE THE PERCENTAGE AND NO ADDEND (#369). A flat
        // per-event uplift used to sit here because two markup records could
        // supply one; both are deleted and the rung that remains takes a
        // percentage and a basis, so a receipt carrying a third term would be
        // recording a zero nobody declared.
        ...(method === "margin_over_cost"
          ? {
              markup: {
                micro_percent: seed.markup_micro_percent,
                // The basis is recorded rather than left to the totals: they
                // coincide for a cost UBB resolved and they do not for one an
                // Event Type declares does not exist, which is still a genuine
                // zero to take a margin over.
                basis_micros: seed.cost.provider_cost_micros ?? 0,
              },
            }
          : {}),
      },
    },
    totals: {
      provider_cost_micros: seed.cost.provider_cost_micros,
      billed_cost_micros: seed.price.billed_cost_micros,
    },
    provenance: seed.provenance ?? {},
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
      idempotency_key: "idem_search_reindex_0042",
      // ⚠ AND THE SHAPE IS THE RECORD'S NOW (#372). #371 took the ratified
      // names for the two containers and said in this very comment that the
      // receipt's SHAPE was still the pre-#349 one and was this commit's to
      // rebuild against `pricing/receipts.py`. It is: the whole record is
      // assembled by `pricingReceipt` below, from each seed's own scenarios.
      // What used to be here — a `billed_source`, a book key, a
      // `per_measurement` bag — was a shape the console invented before the
      // record existed, and none of it survives.
      //
      // THE SHOWCASE RECEIPT, and the one that carries components on both
      // sides. Every term the arithmetic used is written down by value — the
      // quantity, the per-unit rate, the denominator it is divided by and the
      // flat addend — because the receipt has to outlive the measurement rows
      // it explains: those have a retention horizon and this is kept for six
      // years, so a component holding only a quantity and a total would explain
      // nothing the day the detail expires.
      price_components: [
        receiptComponent({
          measurement_key: "input_tokens",
          quantity: 4200,
          rate_per_unit_micros: 30_000,
          unit_quantity: 1000,
          micros: 126_000,
        }),
        receiptComponent({
          measurement_key: "output_tokens",
          quantity: 1730,
          rate_per_unit_micros: 35_500,
          unit_quantity: 1000,
          micros: 61_500,
        }),
      ],
      cost_components: [
        receiptComponent({
          measurement_key: "input_tokens",
          quantity: 4200,
          rate_per_unit_micros: 22_000,
          unit_quantity: 1000,
          micros: 92_400,
        }),
        receiptComponent({
          measurement_key: "output_tokens",
          quantity: 1730,
          rate_per_unit_micros: 28_800,
          unit_quantity: 1000,
          micros: 49_900,
        }),
      ],
      provenance: {
        price_rate_ids: { input_tokens: "ra1e0003-0000-4000-8000-000000000001" },
        cost_rate_ids: { input_tokens: "ra1e0001-0000-4000-8000-000000000001" },
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
      markup_micro_percent: 28_000_000,
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
      markup_micro_percent: 28_000_000,
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
      markup_micro_percent: 28_000_000,
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
      markup_micro_percent: 28_000_000,
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
      markup_micro_percent: 28_000_000,
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
      markup_micro_percent: 28_000_000,
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
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // An event inside a Task sold for one agreed price: the revenue is the
      // Task's and none of it is this event's, so there is no customer price
      // here to resolve or to miss.
      //
      // ⚠ AND IT NAMES WHICH OF THE TWO CAUSES THAT IS (#371). `fixed_task_pricing`
      // is the one that leaves a real charge to go and look at — it sits on the
      // Task. Its sibling, `tenant_not_billing`, says no CUSTOMER charge is
      // raised anywhere (#416 gave such a tenant a Charge RECORD, for margin,
      // which is not a bill),
      // and it CANNOT be seeded here: this workspace has billing enabled, so a
      // posting of its own claiming the tenant does not bill would be a fixture
      // describing a tenant that is not this one. That state is rendered from a
      // fixture the mock does not author — `event-receipt-price.test.tsx`.
      id: EVENT_PRICE_NOT_APPLICABLE_ID,
      effective_at: "2026-06-13T16:08:22Z",
      created_at: "2026-06-13T16:08:23Z",
      event_type: "chat.completion",
      provider: "anthropic",
      dim1: "onboarding",
      price: priceNotApplicable("fixed_task_pricing"),
      cost: knownCost(8_400),
      measurements: { input_tokens: 610, output_tokens: 95 },
      metadata: { env: "prod", team: "onboarding" },
      task_id: TASK_FIXED_PRICE_ID,
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // AN EVENT WHOSE TYPE DECLARES NO SUPPLIER COST AT ALL — slice 3's third
      // canonical cost scenario, which until this commit reached nothing but
      // its own unit test (#371, ruling 10(b)).
      //
      // Its absence is the OPPOSITE fact to `EVENT_UNRESOLVED_ID`'s above.
      // That one is a cost UBB tried to learn and could not, so a total over it
      // is a floor and a recovery run will revisit it. This one was never going
      // to have a supplier cost: nothing is missing, no total is a floor, and
      // there is nothing to recover. The two carry the SAME null column, which
      // is the whole reason a fixture nothing renders cannot catch a reader
      // that guesses between them.
      //
      // A tenant-hosted retrieval call: UBB meters it and bills for it, and
      // there is no third-party supplier behind it to have charged anything.
      // Dated OUTSIDE the July window, like the price fixtures above, so the
      // coherent July story keeps its totals and — this one matters — its
      // unresolved COUNT, which this row must not move.
      id: EVENT_COST_NOT_APPLICABLE_ID,
      effective_at: "2026-06-14T10:33:18Z",
      created_at: "2026-06-14T10:33:19Z",
      event_type: "retrieval.query",
      provider: "",
      dim1: "search-api",
      price: knownPrice(15_000),
      cost: costNotApplicable(),
      measurements: { documents_scanned: 1840 },
      metadata: { env: "prod", team: "search" },
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
      markup_micro_percent: 28_000_000,
      ...prunedMeasurements(),
    }),
  },
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      // A unit of work sold for one agreed price, projected onto its one
      // posting. Nothing was ever measured, so there is nothing a retention
      // horizon could have removed — the empty bag here and the empty bag above
      // are the same object and different facts.
      //
      // ⚠ **IT NAMES NO EVENT TYPE AND COST NOTHING, AND BOTH CHANGED IN
      // #417** — this seed used to invent an `event_type` of `task.charge` and
      // carry a supplier cost of its own. Neither is a posting the backend can
      // produce now that one writes these rows: a projection is marked
      // system-generated by its `kind` precisely so it does not impersonate an
      // Event Type no tenant declared, and its supplier cost is a settled zero
      // because the work a fixed-price unit really burned is on the metered
      // postings beside it. Composing this state from the canonical scenarios,
      // and asserting how it renders on the tasks surface, is #425's.
      id: EVENT_TASK_CHARGE_ID,
      effective_at: "2026-06-11T08:14:02Z",
      created_at: "2026-06-11T08:14:03Z",
      kind: "task_charge",
      dim1: "batch",
      price: knownPrice(2_500_000),
      cost: knownCost(0),
      metadata: { env: "prod", team: "assist" },
      task_id: TASK_FIXED_PRICE_ID,
      costing_method: "reported",
      ...measurementsNotApplicable(),
    }),
  },
  // -------------------------------------------------------------------------
  // TWO EVENTS OF ONE EVENT TYPE THAT READ DIFFERENTLY (spec §21).
  //
  // ⚠ **THIS IS NOT A BUG FOR THE UI TO SMOOTH OVER, AND THE PAIR IS HERE SO
  // THAT IT CANNOT BE.** One customer is on a margin over what their calls
  // cost; another has negotiated a flat price for the same work. Both record
  // `embedding.create`, and their receipts say different things about how the
  // amount was arrived at — because the receipt records the method and the
  // applied value per event, BY VALUE, precisely so it can be shown. A console
  // that took the method from the Event Type would have to pick one of the two
  // and be wrong for the other customer.
  //
  // They are on TWO CUSTOMERS deliberately. The same customer with two methods
  // for one Event Type would need two rules that both matched, which the
  // ladder resolves to one — so it would be a fixture describing something the
  // resolver does not produce.
  {
    customer_id: CUSTOMER_A_ID,
    detail: makeDetail({
      id: EVENT_MARGIN_PRICED_ID,
      effective_at: "2026-07-24T10:05:31Z",
      created_at: "2026-07-24T10:05:32Z",
      event_type: "embedding.create",
      provider: "openai",
      dim1: "copilot",
      price: knownPrice(38_400),
      cost: knownCost(30_000),
      measurements: { embedding_tokens: 7400 },
      metadata: { env: "prod", team: "search" },
      markup_micro_percent: 28_000_000,
    }),
  },
  {
    customer_id: CUSTOMER_B_ID,
    detail: makeDetail({
      id: EVENT_DIRECTLY_PRICED_ID,
      effective_at: "2026-07-24T10:06:44Z",
      created_at: "2026-07-24T10:06:45Z",
      event_type: "embedding.create",
      provider: "openai",
      dim1: "copilot",
      price: knownPrice(74_000),
      cost: knownCost(30_000),
      measurements: { embedding_tokens: 7400 },
      metadata: { env: "prod", team: "search" },
      pricing_method: "direct_event_price",
      price_components: [
        receiptComponent({
          measurement_key: "embedding_tokens",
          quantity: 7400,
          rate_per_unit_micros: 10_000,
          unit_quantity: 1000,
          micros: 74_000,
        }),
      ],
      provenance: {
        price_rate_ids: {
          embedding_tokens: "ra1e0005-0000-4000-8000-000000000001",
        },
      },
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
      markup_micro_percent: 28_000_000,
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
