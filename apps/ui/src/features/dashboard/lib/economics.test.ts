import { describe, expect, it } from "vitest";

import { mockWindowAnalytics } from "../api/mock-data";
import { toBreakdownRows, type BreakdownRow, type MarginCustomerRow, type MarginSummary } from "../api/types";
import {
  customerEconomics,
  shortId,
  sortCustomers,
  summaryEconomics,
  topWithOther,
} from "./economics";

const SUMMARY: MarginSummary = {
  period: { start: "2026-07-01", end: "2026-07-23" },
  subscription_revenue_micros: 1_000_000_000,
  supplied_revenue_micros: 0,
  // THE TWO USAGE FIGURES ARE ONE FIGURE SINCE #497, so a fixture where
  // they differ describes a response no server can produce. This one read
  // 4,000,000,000 against 5,000,000,000 billed.
  usage_billed_micros: 5_000_000_000,
  usage_revenue_micros: 5_000_000_000,
  provider_cost_micros: 2_500_000_000,
  unresolved_event_count: 0,
  unpriced_event_count: 0,
  // 1,000,000,000 subscription + 5,000,000,000 usage.
  total_revenue_micros: 6_000_000_000,
  gross_margin_micros: 3_500_000_000,
  margin_percentage: 58.33,
  customer_count: 3,
};

describe("summaryEconomics", () => {
  it("passes server figures through for billing tenants", () => {
    const view = summaryEconomics(SUMMARY, false);
    expect(view.revenue_micros).toBe(6_000_000_000);
    expect(view.margin_micros).toBe(3_500_000_000);
    expect(view.margin_pct).toBe(58.33);
  });

  // ⚠ THIS CASE NOW SHOWS THE METERED VIEW LOSING A BILLION, WHICH IS WHY
  // IT IS RENAMED RATHER THAN QUIETLY RE-NUMBERED. The two branches agreed
  // on this fixture while a metered workspace really did have ~zero
  // recognised revenue; #497 deleted the switch that made that true, so the
  // substitution now DROPS the subscription revenue the server counted.
  // `economics.ts`'s header records it as a residual owned by the
  // dashboard's own ticket (#507). What this case does is stop it being
  // invisible, by asserting the gap rather than the substituted figure
  // alone.
  it("drops non-usage revenue for meter-only tenants — a residual, not a rule", () => {
    const view = summaryEconomics(SUMMARY, true);
    expect(view.revenue_micros).toBe(5_000_000_000); // usage billed alone
    expect(SUMMARY.total_revenue_micros).toBe(6_000_000_000); // what the server said
    expect(view.margin_micros).toBe(2_500_000_000);
    expect(view.margin_pct).toBe(50);
  });
});

const ROW: MarginCustomerRow = {
  customer_id: "3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301",
  subscription_revenue_micros: 200_000_000,
  supplied_revenue_micros: 0,
  usage_billed_micros: 1_000_000_000,
  // Equal to the billed figure, as it is on every row the server serves
  // since #497. It read 0, commented "metered-only customer", which was
  // the deleted switch's whole effect.
  usage_revenue_micros: 1_000_000_000,
  provider_cost_micros: 600_000_000,
  unresolved_event_count: 0,
  unpriced_event_count: 0,
  // 200,000,000 subscription + 1,000,000,000 usage − 600,000,000 cost.
  gross_margin_micros: 600_000_000,
  margin_percentage: 50,
};

describe("customerEconomics", () => {
  it("sums subscription + usage revenue for billing tenants (rows lack a total)", () => {
    const view = customerEconomics(ROW, false);
    expect(view.revenue_micros).toBe(1_200_000_000);
    expect(view.margin_micros).toBe(600_000_000);
  });

  it("uses usage billed for meter-only tenants", () => {
    const view = customerEconomics(ROW, true);
    expect(view.revenue_micros).toBe(1_000_000_000);
    expect(view.margin_micros).toBe(400_000_000);
    expect(view.margin_pct).toBe(40);
  });

  // ⚠ A ROW WITH NOTHING SUPPLIED CANNOT TELL A THREE-WAY SUM FROM A TWO-WAY
  // ONE, which is why this case carries a figure and the one above does not
  // (#496). The tenant it describes bills its customers outside UBB: dropping
  // its supplied figure here would under-report its revenue everywhere on the
  // dashboard, and every assertion above would still pass.
  it("counts what the tenant supplied as revenue too", () => {
    const supplied: MarginCustomerRow = {
      ...ROW,
      subscription_revenue_micros: 0,
      supplied_revenue_micros: 500_000_000,
      // Both, together: the two are one figure on the wire, and a row that
      // moved only one of them could not be served.
      usage_billed_micros: 100_000_000,
      usage_revenue_micros: 100_000_000,
    };
    expect(customerEconomics(supplied, false).revenue_micros).toBe(600_000_000);
  });
});

describe("sortCustomers", () => {
  const rows: MarginCustomerRow[] = [
    { ...ROW, customer_id: "a", usage_billed_micros: 100_000_000, usage_revenue_micros: 100_000_000, gross_margin_micros: 50_000_000, margin_percentage: 10 },
    { ...ROW, customer_id: "b", usage_billed_micros: 900_000_000, usage_revenue_micros: 900_000_000, gross_margin_micros: 20_000_000, margin_percentage: 90 },
  ];

  it("sorts descending by the requested key", () => {
    expect(sortCustomers(rows, false, "revenue").map((r) => r.customer_id)).toEqual(["b", "a"]);
    expect(sortCustomers(rows, false, "margin").map((r) => r.customer_id)).toEqual(["a", "b"]);
    expect(sortCustomers(rows, false, "margin_pct").map((r) => r.customer_id)).toEqual(["b", "a"]);
  });
});

describe("topWithOther", () => {
  const rows: BreakdownRow[] = Array.from({ length: 10 }, (_, i) => ({
    group_value: `group-${i}`,
    event_count: 10,
    total_provider_cost_micros: 5_000_000,
    total_billed_cost_micros: (10 - i) * 1_000_000,
  }));

  it("keeps the top 8 by billed cost and folds the rest into Other", () => {
    const bars = topWithOther(rows, 8);
    expect(bars).toHaveLength(9);
    expect(bars[0]?.name).toBe("group-0");
    const other = bars[8];
    expect(other?.isOther).toBe(true);
    expect(other?.name).toBe("Other (2)");
    // group-8 (2) + group-9 (1) billed
    expect(other?.billed_micros).toBe(3_000_000);
    expect(other?.event_count).toBe(20);
  });

  it("labels empty group values as unattributed", () => {
    const bars = topWithOther([
      { group_value: null, event_count: 1, total_provider_cost_micros: 0, total_billed_cost_micros: 1 },
    ]);
    expect(bars[0]?.name).toBe("(unattributed)");
  });
});

describe("toBreakdownRows legacy fallback", () => {
  it("reads by_customer's quirky keys when breakdowns lacks the axis", () => {
    // Analytics answered with only the `provider` breakdown — asking for
    // `customer` must fall back to the legacy by_customer rows, which key the
    // value as `customer__external_id` and billed cost as `total_cost_micros`.
    const analytics = mockWindowAnalytics("provider");
    const rows = toBreakdownRows(analytics, "customer");
    expect(rows.length).toBeGreaterThan(0);
    expect(rows[0]?.group_value).toBe("acme-corp");
    expect(rows[0]?.total_billed_cost_micros).toBe(342_500_000);
    expect(rows[0]?.total_provider_cost_micros).toBe(274_000_000);
  });

  it("prefers the uniform breakdowns rows when present", () => {
    const analytics = mockWindowAnalytics("provider");
    const rows = toBreakdownRows(analytics, "provider");
    expect(rows[0]?.group_value).toBe("openai");
    expect(rows[0]?.total_billed_cost_micros).toBe(280_000_000);
  });

  // The uniform rows are `additionalProperties: true`, so nothing in the
  // generated types can hold the console's read to the key the backend puts
  // the grouped value under. Both halves of the pairing come from this
  // module's own constant, which means the fixtures above would still pass if
  // the key were renamed on this side alone — and a console reading a key the
  // backend does not emit renders every bar as "(unattributed)" in silence.
  //
  // So this fixture is a literal transcript of a backend response instead. It
  // fails the moment the console's read moves without the backend's emit, and
  // it is what must be updated — deliberately, in the same commit — when the
  // backend's own rename finally lands.
  it("reads the grouped value off a verbatim backend response", () => {
    const fromBackend = {
      total_events: 3,
      total_billed_cost_micros: 900,
      total_provider_cost_micros: 600,
      usage_markup_margin_micros: 300,
      by_provider: [],
      by_event_type: [],
      by_customer: [],
      by_task_type: [],
      by_tag: [],
      breakdowns: {
        provider: [
          {
            grouping_field_value: "openai",
            event_count: 3,
            total_provider_cost_micros: 600,
            total_billed_cost_micros: 900,
          },
        ],
      },
    } as unknown as Parameters<typeof toBreakdownRows>[0];

    const rows = toBreakdownRows(fromBackend, "provider");
    expect(rows).toHaveLength(1);
    expect(rows[0]?.group_value).toBe("openai");
    expect(rows[0]?.total_billed_cost_micros).toBe(900);
  });
});

describe("shortId", () => {
  it("shortens UUIDs to an 8-char prefix", () => {
    expect(shortId("3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301")).toBe("3e7f0a41…");
    expect(shortId("short")).toBe("short");
  });
});
