// The past-limit report is UNTYPED in the contract, so its narrowing is the
// only thing that says what its rows carry — and the only place a fact can be
// dropped without a type error anywhere.
//
// #328 put `unresolved_event_count` on every episode and per-limit total, and
// made the itemized rows carry `costing_status` beside a supplier cost that has
// been nullable since #317. None of that is visible to a scan of the contract's
// typed schemas, which is exactly how this surface was first read as one with
// no completeness at all (#330). These tests are what makes the omission
// impossible to repeat silently.

import { describe, expect, it } from "vitest";

import { asPastLimitEpisodes, asTotalsPerLimit } from "./types";

describe("asPastLimitEpisodes", () => {
  it("carries each episode's own uncosted-event count through", () => {
    const [episode] = asPastLimitEpisodes([
      {
        family: "floor_stop",
        limit: "customer_floor",
        stop_scope: "customer",
        events: [],
        event_count: 3,
        total_billed_cost_micros: 2_980_000,
        total_provider_cost_micros: 1_872_000,
        unresolved_event_count: 1,
      },
    ]);

    expect(episode?.unresolved_event_count).toBe(1);
  });

  // A cost UBB never learned must stay ABSENT all the way to the cell that
  // renders it. Coalescing to zero here would tell a tenant their supplier
  // charged nothing for the very events that overran their spend stop.
  it("keeps an itemized event's missing supplier cost absent, not zero", () => {
    const [episode] = asPastLimitEpisodes([
      {
        family: "floor_stop",
        limit: "customer_floor",
        stop_scope: "customer",
        events: [
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000301",
            effective_at: "2026-07-02T09:14:00Z",
            billed_cost_micros: 640_000,
            provider_cost_micros: null,
            costing_status: "unresolved",
            arrived_after: true,
          },
        ],
        event_count: 1,
        total_billed_cost_micros: 640_000,
        total_provider_cost_micros: 0,
        unresolved_event_count: 1,
      },
    ]);

    expect(episode?.events[0]?.provider_cost_micros).toBeNull();
    expect(episode?.events[0]?.costing_status).toBe("unresolved");
  });

  // A status the registry has never declared is not one of the three, and
  // guessing which it meant would be inventing a state. The row said nothing
  // this console can act on, and `null` is how it says so.
  it("reports an undeclared status as no status rather than defaulting one", () => {
    const [episode] = asPastLimitEpisodes([
      {
        family: "floor_stop",
        limit: "customer_floor",
        stop_scope: "customer",
        events: [
          {
            event_id: "9c32c7a4-0000-4000-8000-000000000302",
            effective_at: "2026-07-02T09:15:00Z",
            billed_cost_micros: 1,
            provider_cost_micros: null,
            costing_status: "something_nobody_declared",
            arrived_after: false,
          },
        ],
        event_count: 1,
        total_billed_cost_micros: 1,
        total_provider_cost_micros: 0,
        unresolved_event_count: 0,
      },
    ]);

    expect(episode?.events[0]?.costing_status).toBeNull();
  });

  // The absence of the key is not the claim "this episode left nothing out" —
  // but a zero is the only answer a number can give, and the server writes the
  // key on every row it emits. Pinned so the coalesce is a deliberate reading
  // of a guaranteed field rather than an accident.
  it("reads a row with no count at all as zero", () => {
    const [episode] = asPastLimitEpisodes([
      { family: "soft_floor", stop_scope: "customer", events: [] },
    ]);

    expect(episode?.unresolved_event_count).toBe(0);
  });
});

describe("asTotalsPerLimit", () => {
  it("carries each limit's own uncosted-event count through", () => {
    const [row] = asTotalsPerLimit({
      customer_floor: {
        billed_cost_micros: 2_980_000,
        provider_cost_micros: 1_872_000,
        unresolved_event_count: 1,
        event_count: 3,
      },
    });

    expect(row?.unresolved_event_count).toBe(1);
  });
});
