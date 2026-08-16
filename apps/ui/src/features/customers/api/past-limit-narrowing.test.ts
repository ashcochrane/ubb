// The past-limit narrowing, held to what the server actually sends.
//
// This feature's mock returns its fixture OBJECT, so the component tests beside
// it exercise the rendering and never touch `narrowPastLimitReport` — only the
// real API path does. That split is why this file exists: revert the nullable
// read below to the module's `num()` and every component test stays green while
// a live console renders `$0.00` for a cost UBB never learned, on the one report
// a tenant opens because they are worried about money already spent.
//
// The report is `additionalProperties: true` in the contract, so nothing typed
// says its rows carry `unresolved_event_count` or a nullable supplier cost.
// #328 put them there; `api/v1/past_limit.py` is the only thing that shows it.

import { describe, expect, it } from "vitest";

import { narrowPastLimitReport } from "./types";
import type { PastLimitReportResponse } from "./types";

/** The shape the server sends, as the generated (untyped) response type. */
function rawReport(
  episodes: Array<Record<string, unknown>>,
  totalsPerLimit: Record<string, unknown> = {},
): PastLimitReportResponse {
  return {
    customer_id: "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002",
    billing_owner_id: "2a1d8b3f-7e19-4c2d-8e4c-7b2000000002",
    since: null,
    until: null,
    episodes,
    totals_per_limit: totalsPerLimit,
  };
}

describe("narrowPastLimitReport", () => {
  it("carries each episode's own uncosted-event count through", () => {
    const report = narrowPastLimitReport(
      rawReport([
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
      ]),
    );

    expect(report.episodes[0]?.unresolved_event_count).toBe(1);
  });

  // THE ASSERTION THE COMPONENT TESTS CANNOT MAKE. An absent supplier cost has
  // to survive narrowing as an absence; coalescing it to zero here is invisible
  // to every rendering test in this feature, because the mock never runs this
  // code.
  it("keeps an itemized event's missing supplier cost absent, not zero", () => {
    const report = narrowPastLimitReport(
      rawReport([
        {
          family: "floor_stop",
          limit: "customer_floor",
          stop_scope: "customer",
          events: [
            {
              event_id: "9c32c7a4-0000-4000-8000-000000000303",
              effective_at: "2026-07-02T09:16:44Z",
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
      ]),
    );

    const event = report.episodes[0]?.events[0];
    expect(event?.provider_cost_micros).toBeNull();
    expect(event?.provider_cost_micros).not.toBe(0);
    expect(event?.costing_status).toBe("unresolved");
  });

  // A resolved zero is a real amount and must not become an absence either —
  // the read has to distinguish the two, not merely favour one of them.
  it("keeps a resolved zero as a number", () => {
    const report = narrowPastLimitReport(
      rawReport([
        {
          family: "floor_stop",
          limit: "customer_floor",
          stop_scope: "customer",
          events: [
            {
              event_id: "9c32c7a4-0000-4000-8000-000000000304",
              effective_at: "2026-07-02T09:17:00Z",
              billed_cost_micros: 1,
              provider_cost_micros: 0,
              costing_status: "known",
              arrived_after: false,
            },
          ],
          event_count: 1,
          total_billed_cost_micros: 1,
          total_provider_cost_micros: 0,
          unresolved_event_count: 0,
        },
      ]),
    );

    expect(report.episodes[0]?.events[0]?.provider_cost_micros).toBe(0);
  });

  it("reports an undeclared status as no status rather than defaulting one", () => {
    const report = narrowPastLimitReport(
      rawReport([
        {
          family: "floor_stop",
          limit: "customer_floor",
          stop_scope: "customer",
          events: [
            {
              event_id: "9c32c7a4-0000-4000-8000-000000000305",
              effective_at: "2026-07-02T09:18:00Z",
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
      ]),
    );

    expect(report.episodes[0]?.events[0]?.costing_status).toBeNull();
  });

  it("carries each per-limit total's own uncosted-event count through", () => {
    const report = narrowPastLimitReport(
      rawReport([], {
        customer_floor: {
          billed_cost_micros: 2_980_000,
          provider_cost_micros: 1_872_000,
          unresolved_event_count: 1,
          event_count: 3,
        },
      }),
    );

    expect(report.totals_per_limit["customer_floor"]?.unresolved_event_count).toBe(1);
  });
});
