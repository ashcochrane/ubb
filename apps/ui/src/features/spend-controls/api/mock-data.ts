// Mock fixtures for the spend-controls feature — the July 2026 story the
// customers feature tells, seen from the controls that fired:
//
//   luna-labs  — an individual on a negative balance: one hard-floor episode
//                (cleared two days later), one soft-floor marker before it.
//   acme-corp  — a business: one unit of work stopped on its own ceiling with
//                events still landing after the stop, one older ceiling stop
//                whose kill announcement has aged out, and one customer spend
//                pool crossing found by replaying the period's charges.
//
// COMPOSED, NEVER STATED FIELD BY FIELD (#155 §9.4; apps/ui/CLAUDE.md). Every
// amount on these rows is an economic STATE — a price or cost that may be
// unresolved, a total that may be a floor, a ceiling assessment concluded
// from its terms — so each is composed from `@/lib/economic-scenarios` and the
// itemised totals are ADDED UP from the composed events by the backend's own
// rule (add what is resolved, count what is not), never typed beside them.
// The report this feature replaced kept two fixtures of the same episodes by
// hand, in two features, and they disagreed on which fields existed.
//
// The ids below are the customers feature's story ids and the tasks feature's
// killed run, restated as literals: a feature may not import another feature's
// mock (the console's imports only flow down), and a mock-mode console that
// could not follow its own links from this tab to a customer or a run would
// be telling a story nobody can walk through.
//
// THE MOCK IGNORES THE WINDOW, as the customers feature's mock does for the
// same page: the story is July 2026 and a month-to-date default would select
// none of it whatever month the console is opened in. The window is echoed
// back as asked; the customer and family filters are honoured.

import {
  ceilingAssessment,
  completeTotal,
  incompletePriceTotal,
  incompleteTotal,
  knownCost,
  knownPrice,
  unknownCost,
  unknownPrice,
  type CustomerPriceScenario,
  type SupplierCostScenario,
} from "@/lib/economic-scenarios";
import type { ReasonCodeKnown } from "@/lib/vocabulary";

import type {
  CeilingEpisodeRow,
  CustomerSpendPoolEpisodeRow,
  EpisodeRow,
  FamilyTotalsRow,
  ItemisedEventRow,
  ItemisedEvents,
  MarginCustomers,
  WalletPolicyEpisodeRow,
} from "./types";

/** luna-labs — the customers feature's `CUS_LUNA`. */
export const CUSTOMER_LUNA = "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002";
/** acme-corp — the customers feature's `CUS_ACME`. */
export const CUSTOMER_ACME = "1f0c9c4e-8f2a-4a1e-9d3b-6a1f00000001";
/** The tasks feature's `RUN_KILLED_ID` — the run its story stopped on its ceiling. */
export const UNIT_KILLED = "4d7b1e9f-2c58-4a06-b371-9e5f0d8c2a17";
/** A second unit, stopped earlier, whose kill announcement has since aged out. */
export const UNIT_KILLED_EARLIER = "a91c4e7d-5b02-4f38-8c6e-2d7f0a1b9c53";
/** The Charge that crossed acme-corp's pool, and the posting that projects it. */
export const CROSSING_CHARGE_ID = "3c7e9a1b-4d26-4f80-9b5a-6e1d2c8f0a47";
export const CROSSING_POSTING_ID = "8f2b6d04-1e93-4a57-b0c8-5d7a3e9f1c26";

/** The stop words the story's controls fired with, typed against the registry's known values. */
const CEILING_STOP: ReasonCodeKnown = "task_cogs_ceiling";
const POOL_STOP: ReasonCodeKnown = "customer_spend_pool";
const FLOOR_STOP: ReasonCodeKnown = "hard_floor";

// ---------------------------------------------------------------------------
// One itemised event, composed.

interface EventSeed {
  readonly id: string;
  readonly customer: string;
  readonly at: string;
  readonly price: CustomerPriceScenario;
  readonly cost: SupplierCostScenario;
  readonly arrivedAfter: boolean;
  readonly chargeId?: string;
}

/**
 * One event as the report itemises it. The two amount/status pairs are taken
 * from their scenarios by name, never spread: a scenario carries the cause
 * beside a not-applicable status, and the wire row does not.
 */
function event(seed: EventSeed): ItemisedEventRow {
  return {
    event_id: seed.id,
    customer_id: seed.customer,
    effective_at: seed.at,
    billed_cost_micros: seed.price.billed_cost_micros,
    pricing_status: seed.price.pricing_status,
    provider_cost_micros: seed.cost.provider_cost_micros,
    costing_status: seed.cost.costing_status,
    charge_id: seed.chargeId ?? null,
    arrived_after: seed.arrivedAfter,
  };
}

/**
 * The itemised block over its events — the backend's own rule, applied to the
 * composed rows: add what is resolved, count what is not, in both
 * denominations (`core.cost_totals`). Typing the totals beside the events is
 * how a fixture comes to say a total is whole while its own events say it is
 * not.
 */
export function itemised(events: readonly ItemisedEventRow[]): ItemisedEvents {
  let billed = 0;
  let unpriced = 0;
  let provider = 0;
  let unresolved = 0;
  for (const row of events) {
    if (row.billed_cost_micros != null) billed += row.billed_cost_micros;
    else if (row.pricing_status === "unknown") unpriced += 1;
    if (row.provider_cost_micros != null) provider += row.provider_cost_micros;
    else if (row.costing_status === "unresolved") unresolved += 1;
  }
  return {
    events: [...events],
    event_count: events.length,
    billed_cost_micros: billed,
    unpriced_event_count: unpriced,
    provider_cost_micros: provider,
    unresolved_event_count: unresolved,
  };
}

/**
 * Per family, the totals over exactly the itemised events of the rows shown,
 * each event once per family — the backend's `_totals`, so the mock's totals
 * can never disagree with its rows.
 */
export function totalsOf(rows: readonly EpisodeRow[]): FamilyTotalsRow[] {
  const byFamily = new Map<EpisodeRow["control_family"], Map<string, ItemisedEventRow>>();
  for (const row of rows) {
    const seen = byFamily.get(row.control_family) ?? new Map<string, ItemisedEventRow>();
    for (const item of row.itemised.events) {
      if (!seen.has(item.event_id)) seen.set(item.event_id, item);
    }
    byFamily.set(row.control_family, seen);
  }
  return [...byFamily.entries()]
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([control_family, seen]) => {
      const block = itemised([...seen.values()]);
      return {
        control_family,
        event_count: block.event_count,
        billed_cost_micros: block.billed_cost_micros,
        unpriced_event_count: block.unpriced_event_count,
        provider_cost_micros: block.provider_cost_micros,
        unresolved_event_count: block.unresolved_event_count,
      };
    });
}

// ---------------------------------------------------------------------------
// The rows

/**
 * acme-corp's video render stopped on its own ceiling on 21 July, with two
 * events landing after the stop — one of them at a cost UBB never learned,
 * which is exactly the row a zeroed absence would misreport as a free overrun
 * (#330). The pair the unit ended on is composed as a ceiling assessment so
 * the fixture cannot state a "reached" row the registry's rule would not
 * conclude; the pair it fired on is a floor beside the one event it could not
 * include.
 */
/** The ceiling the story's video renders pin at start — the tasks feature's `VIDEO_RENDER_CEILING_MICROS`. */
const VIDEO_RENDER_CEILING = 3_000_000;

const CEILING_VIDEO_RENDER: CeilingEpisodeRow = (() => {
  const ended = ceilingAssessment("ceiling_reached", {
    ceiling_micros: VIDEO_RENDER_CEILING,
    cost: incompleteTotal(3_420_000, 1),
  });
  const fired = incompleteTotal(3_050_000, 1);
  return {
    control_family: "ceiling",
    control_id: "video-render",
    reason_code: CEILING_STOP,
    ceiling_basis: "cost",
    trigger_source: "usage_ingest",
    task_id: UNIT_KILLED,
    parent_task_id: null,
    customer_id: CUSTOMER_ACME,
    task_type: "video-render",
    stop_scope: "task",
    task_cogs_ceiling_micros: VIDEO_RENDER_CEILING,
    opened_at: "2026-07-21T09:15:33Z",
    crossed_provider_cost_micros: fired.micros,
    crossed_unresolved_event_count: fired.unresolved_event_count,
    final_provider_cost_micros: ended.total_provider_cost_micros,
    final_unresolved_event_count: ended.unresolved_event_count,
    itemised: itemised([
      event({
        id: "9c32c7a4-0000-4000-8000-000000000304",
        customer: CUSTOMER_ACME,
        at: "2026-07-21T09:16:05Z",
        price: knownPrice(64_000),
        cost: knownCost(50_000),
        arrivedAfter: true,
      }),
      event({
        id: "9c32c7a4-0000-4000-8000-000000000305",
        customer: CUSTOMER_ACME,
        at: "2026-07-21T09:17:40Z",
        // THE ONE ITEMISED EVENT WHOSE SUPPLIER COST UBB NEVER LEARNED (#330).
        // It landed past the stop and it is still billed, so its row must not
        // read as a free overrun: the amount is absent and the block's total
        // says "at least".
        price: knownPrice(41_000),
        cost: unknownCost("cost_rate_missing"),
        arrivedAfter: true,
      }),
    ]),
  };
})();

/**
 * An earlier ceiling stop on the same kind of work whose kill announcement
 * has aged out of the outbox: the pair the ceiling fired on is NULL — unknown,
 * never zero — and the mechanism that applied it was not recorded either.
 * Nothing landed after the stop.
 */
const CEILING_ANNOUNCEMENT_GONE: CeilingEpisodeRow = (() => {
  const ended = ceilingAssessment("ceiling_reached", {
    ceiling_micros: VIDEO_RENDER_CEILING,
    cost: completeTotal(3_000_000),
  });
  return {
    control_family: "ceiling",
    control_id: "video-render",
    reason_code: CEILING_STOP,
    ceiling_basis: "cost",
    trigger_source: null,
    task_id: UNIT_KILLED_EARLIER,
    parent_task_id: null,
    customer_id: CUSTOMER_ACME,
    task_type: "video-render",
    stop_scope: "task",
    task_cogs_ceiling_micros: VIDEO_RENDER_CEILING,
    opened_at: "2026-07-03T16:40:12Z",
    crossed_provider_cost_micros: null,
    crossed_unresolved_event_count: null,
    final_provider_cost_micros: ended.total_provider_cost_micros,
    final_unresolved_event_count: ended.unresolved_event_count,
    itemised: itemised([]),
  };
})();

/**
 * acme-corp's pool crossed its stop line on 12 July on a delivered unit's
 * Charge — found by REPLAYING the period's charges, because a Charge reaches
 * the pool through its projection and the durable drawdown rather than the
 * live lane, so the recording route marked no tipping event (#465, ruling 2).
 * Three events landed after it, one at a price UBB could not resolve, so the
 * spend after the crossing is a floor.
 */
const POOL_ACME: CustomerSpendPoolEpisodeRow = (() => {
  const events = [
    event({
      id: CROSSING_POSTING_ID,
      customer: CUSTOMER_ACME,
      at: "2026-07-12T10:05:00Z",
      price: knownPrice(5_000_000),
      cost: knownCost(0),
      arrivedAfter: false,
      chargeId: CROSSING_CHARGE_ID,
    }),
    event({
      id: "e4a1c8d2-7b39-4f60-9c15-3d8e6a2f0b74",
      customer: CUSTOMER_ACME,
      at: "2026-07-12T10:06:12Z",
      price: knownPrice(8_500_000),
      cost: knownCost(6_100_000),
      arrivedAfter: true,
    }),
    event({
      id: "f7b2d9e3-8c40-4a71-8d26-4e9f7b3a1c85",
      customer: CUSTOMER_ACME,
      at: "2026-07-12T10:09:48Z",
      price: knownPrice(4_000_000),
      cost: knownCost(2_950_000),
      arrivedAfter: true,
    }),
    event({
      id: "a8c3e0f4-9d51-4b82-9e37-5f0a8c4b2d96",
      customer: CUSTOMER_ACME,
      at: "2026-07-12T10:11:03Z",
      price: unknownPrice(),
      cost: knownCost(1_200_000),
      arrivedAfter: true,
    }),
  ];
  const after = incompletePriceTotal(12_500_000, 1);
  return {
    control_family: "customer_spend_pool",
    control_id: "pool-acme-2026-07",
    reason_code: POOL_STOP,
    customer_id: CUSTOMER_ACME,
    episode_seq: 1,
    period: "2026-07",
    cap_micros: 500_000_000,
    opened_at: "2026-07-12T10:05:01Z",
    closed_at: "2026-08-01T00:00:00Z",
    crossing_charge_id: CROSSING_CHARGE_ID,
    crossing_posting_id: CROSSING_POSTING_ID,
    crossing_marked: false,
    spent_after_micros: after.micros,
    unpriced_after_count: after.unpriced_event_count,
    work_stopped_count: 3,
    itemised: itemised(events),
  };
})();

/**
 * luna-labs crossed its hard floor on 2 July and recovered on the 4th: three
 * events past the stop, two costs known and one never learned, so the
 * episode's supplier total is a floor — the customers feature's story, and the
 * numbers its old report showed (`$1.87` at least).
 */
const FLOOR_LUNA: WalletPolicyEpisodeRow = {
  control_family: "wallet_policy",
  control_id: "floor-luna",
  reason_code: FLOOR_STOP,
  soft_floor: false,
  customer_id: CUSTOMER_LUNA,
  episode_seq: 3,
  floor_micros: -5_000_000,
  balance_at_crossing_micros: -6_000_000,
  opened_at: "2026-07-02T09:14:00Z",
  closed_at: "2026-07-04T08:02:00Z",
  itemised: itemised([
    event({
      id: "9c32c7a4-0000-4000-8000-000000000301",
      customer: CUSTOMER_LUNA,
      at: "2026-07-02T09:14:00Z",
      price: knownPrice(1_450_000),
      cost: knownCost(1_160_000),
      arrivedAfter: false,
    }),
    event({
      id: "9c32c7a4-0000-4000-8000-000000000302",
      customer: CUSTOMER_LUNA,
      at: "2026-07-02T09:15:12Z",
      price: knownPrice(890_000),
      cost: knownCost(712_000),
      arrivedAfter: true,
    }),
    event({
      id: "9c32c7a4-0000-4000-8000-000000000303",
      customer: CUSTOMER_LUNA,
      at: "2026-07-02T09:16:44Z",
      price: knownPrice(640_000),
      cost: unknownCost("cost_rate_missing"),
      arrivedAfter: true,
    }),
  ]),
};

/** luna-labs crossed its soft floor the evening before — a marker, nothing stopped, nothing itemised. */
const SOFT_FLOOR_LUNA: WalletPolicyEpisodeRow = {
  control_family: "wallet_policy",
  control_id: null,
  reason_code: null,
  soft_floor: true,
  customer_id: CUSTOMER_LUNA,
  episode_seq: 3,
  floor_micros: -2_000_000,
  balance_at_crossing_micros: -2_150_000,
  opened_at: "2026-07-01T22:40:00Z",
  closed_at: "2026-07-01T23:55:00Z",
  itemised: itemised([]),
};

/** Every episode of the story, in the order the report answers them: by opening instant. */
export const MOCK_EPISODES: readonly EpisodeRow[] = [
  SOFT_FLOOR_LUNA,
  FLOOR_LUNA,
  CEILING_ANNOUNCEMENT_GONE,
  POOL_ACME,
  CEILING_VIDEO_RENDER,
];

/**
 * The customer filter's choices — the two customers of the story with a
 * margin row, as the margin list carries them. The margin figures are the
 * customers feature's July story restated for the same two ids.
 */
export const MOCK_MARGIN_CUSTOMERS: MarginCustomers = {
  period: { start: "2026-07-01", end: "2026-07-31" },
  customers: [
    {
      customer_id: CUSTOMER_ACME,
      usage_billed_micros: 1_247_000_000,
      usage_revenue_micros: 1_247_000_000,
      subscription_revenue_micros: 240_000_000,
      provider_cost_micros: 945_500_000,
      gross_margin_micros: 541_500_000,
      margin_percentage: 36.4,
      unresolved_event_count: 0,
      unpriced_event_count: 0,
    },
    {
      customer_id: CUSTOMER_LUNA,
      usage_billed_micros: 61_000_000,
      usage_revenue_micros: 61_000_000,
      subscription_revenue_micros: 0,
      provider_cost_micros: 72_400_000,
      gross_margin_micros: -11_400_000,
      margin_percentage: -18.7,
      unresolved_event_count: 1,
      unpriced_event_count: 0,
    },
  ],
};
