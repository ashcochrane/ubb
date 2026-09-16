import { describe, expect, it } from "vitest";

import {
  mockCustomerEconomics,
  mockGroupedEconomics,
  mockTenantEconomics,
} from "../api/mock-data";
import {
  toBreakdownRows,
  toCustomerRows,
  toTenantEconomics,
  type BreakdownRow,
  type CustomerEconomicsRow,
  type TenantEconomics,
} from "../api/types";
import {
  customerEconomics,
  shortId,
  sortCustomers,
  summaryEconomics,
  topWithOther,
} from "./economics";

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

const SUMMARY: TenantEconomics = {
  provider_cost_micros: 2_500_000_000,
  // One figure from one definition (#501). It was three fields — a
  // subscription, a supplied figure and billed usage — which this module
  // summed itself, and a fourth source added later would have gone missing
  // until somebody noticed.
  total_revenue_micros: 6_000_000_000,
  gross_margin_micros: 3_500_000_000,
  margin_percentage: 58.33,
  unresolved_event_count: 0,
  unpriced_event_count: 0,
  event_count: 93_558,
};

describe("summaryEconomics", () => {
  it("passes the server's figures through", () => {
    const view = summaryEconomics(SUMMARY);
    expect(view.revenue_micros).toBe(6_000_000_000);
    expect(view.margin_micros).toBe(3_500_000_000);
    expect(view.margin_pct).toBe(58.33);
  });

  // ⚠ THE METERED VIEW IS GONE AND THIS IS THE CASE THAT REPLACES ITS TWO
  // (#501). It substituted billed usage for the server's revenue total, and
  // #497 — which deleted the switch that had made that substitution true —
  // left it standing as a recorded residual, asserting the GAP rather than the
  // figure so the loss would not be invisible. There is no substitution left to
  // make: the one economic query answers revenue once, so a workspace that
  // bills its customers elsewhere reads the same figure here as anywhere else.
  it("states a margin it has and withholds one it does not", () => {
    expect(summaryEconomics(SUMMARY).margin_micros).toBe(3_500_000_000);
    const unattributable: TenantEconomics = {
      ...SUMMARY,
      gross_margin_micros: null,
    };
    // NOT zero, and not the revenue: a margin UBB cannot state is absent.
    expect(summaryEconomics(unattributable).margin_micros).toBeNull();
  });
});

const ROW: CustomerEconomicsRow = {
  customer_id: "3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301",
  provider_cost_micros: 600_000_000,
  total_revenue_micros: 1_200_000_000,
  gross_margin_micros: 600_000_000,
  margin_percentage: 50,
  unresolved_event_count: 0,
  unpriced_event_count: 0,
  event_count: null,
};

describe("customerEconomics", () => {
  it("reads the row's own total rather than summing revenue sources", () => {
    const view = customerEconomics(ROW);
    expect(view.revenue_micros).toBe(1_200_000_000);
    expect(view.margin_micros).toBe(600_000_000);
  });

  it("carries an absent margin through as an absence", () => {
    const view = customerEconomics({ ...ROW, gross_margin_micros: null });
    expect(view.margin_micros).toBeNull();
  });
});

describe("sortCustomers", () => {
  const rows: CustomerEconomicsRow[] = [
    { ...ROW, customer_id: "a", total_revenue_micros: 100_000_000, gross_margin_micros: 50_000_000, margin_percentage: 10 },
    { ...ROW, customer_id: "b", total_revenue_micros: 900_000_000, gross_margin_micros: 20_000_000, margin_percentage: 90 },
  ];

  it("sorts descending by the requested key", () => {
    expect(sortCustomers(rows, "revenue").map((r) => r.customer_id)).toEqual(["b", "a"]);
    expect(sortCustomers(rows, "margin").map((r) => r.customer_id)).toEqual(["a", "b"]);
    expect(sortCustomers(rows, "margin_pct").map((r) => r.customer_id)).toEqual(["b", "a"]);
  });

  // ⚠ A ROW STATING NO MARGIN MUST NOT SORT AS IF IT STATED ZERO, which is
  // where it would land if the comparator coerced — in the middle of the table,
  // between the profitable and the unprofitable, reading as a claim about a
  // customer UBB cannot report on.
  it("files a customer with no margin last rather than as a zero", () => {
    const withAGap: CustomerEconomicsRow[] = [
      ...rows,
      { ...ROW, customer_id: "gap", gross_margin_micros: null },
    ];
    expect(sortCustomers(withAGap, "margin").map((r) => r.customer_id)).toEqual(
      ["a", "b", "gap"],
    );
    expect(sortCustomers(withAGap, "margin_pct").map((r) => r.customer_id)).toEqual(
      ["b", "a", "gap"],
    );
  });
});

describe("topWithOther", () => {
  const rows: BreakdownRow[] = Array.from({ length: 10 }, (_, i) => ({
    group_value: `group-${i}`,
    total_provider_cost_micros: 5_000_000,
    total_revenue_micros: (10 - i) * 1_000_000,
  }));

  it("keeps the top 8 by revenue and folds the rest into Other", () => {
    const bars = topWithOther(rows, 8);
    expect(bars).toHaveLength(9);
    expect(bars[0]?.name).toBe("group-0");
    const other = bars[8];
    expect(other?.isOther).toBe(true);
    expect(other?.name).toBe("Other (2)");
    // group-8 (2) + group-9 (1) revenue
    expect(other?.revenue_micros).toBe(3_000_000);
    expect(other?.provider_micros).toBe(10_000_000);
  });

  it("labels an absent group value as unattributed", () => {
    const bars = topWithOther([
      { group_value: null, total_provider_cost_micros: 0, total_revenue_micros: 1 },
    ]);
    expect(bars[0]?.name).toBe("(unattributed)");
  });
});

// ⚠ THE LEGACY-FALLBACK SUITE IS GONE WITH THE SHAPE IT NARROWED (#501).
// Three of its cases were about a response that had two ways of saying the same
// thing — a uniform `breakdowns` map and the older `by_*` arrays, which keyed a
// customer as `customer__external_id` and billed cost as `total_cost_micros` —
// and a fourth pinned the key the backend put a grouped value under, because
// the rows were `additionalProperties: true` and nothing in the generated types
// could hold the console's read to it.
//
// The one economic query DECLARES its row. The grouped value's key is on the
// contract, the drift and breaking gates see it, and a rename on one side is a
// break rather than a silent page of "(unattributed)" bars. So what those four
// cases bought is bought by the schema now, and what is left to assert is the
// narrowing itself.
describe("toBreakdownRows", () => {
  it("reads the grouped value and both figures off a declared row", () => {
    const rows = toBreakdownRows(mockGroupedEconomics(WINDOW, "provider"));
    expect(rows[0]?.group_value).toBe("openai");
    expect(rows[0]?.total_revenue_micros).toBe(280_000_000);
    expect(rows[0]?.total_provider_cost_micros).toBe(245_000_000);
  });

  // ⚠ THE ROW WHOSE AXIS VALUE IS ABSENT IS A ROW, and dropping it would make
  // the bars stop summing to the total above them. The report this replaced
  // bucketed it under a sentinel STRING; here it is `null`, and the narrowing
  // has to carry that through rather than filter it out.
  it("keeps a row whose axis value was never recorded", () => {
    const rows = toBreakdownRows(mockGroupedEconomics(WINDOW, "task_type"));
    const absent = rows.filter((row) => row.group_value === null);
    expect(absent).toHaveLength(1);
    expect(absent[0]?.total_revenue_micros).toBe(50_000_000);
  });
});

describe("toCustomerRows", () => {
  it("reads one row per customer, keyed by the identity the axis groups", () => {
    const rows = toCustomerRows(mockCustomerEconomics(WINDOW));
    expect(rows).toHaveLength(5);
    expect(rows[0]?.total_revenue_micros).toBe(541_500_000);
    expect(rows[0]?.customer_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  // ⚠ EACH ROW'S OWN COMPLETENESS, NOT THE WINDOW'S. One customer's unresolved
  // cost says nothing about another's, and a table that bounded every row on
  // the window's total would caveat four rows for one customer's missing
  // invoice.
  it("carries each row's own completeness", () => {
    const rows = toCustomerRows(mockCustomerEconomics(WINDOW));
    const partial = rows.filter((row) => row.unresolved_event_count > 0);
    expect(partial).toHaveLength(1);
    expect(partial[0]?.unresolved_event_count).toBe(4);
  });
});

describe("toTenantEconomics", () => {
  it("narrows the single row an ungrouped answer always has", () => {
    const totals = toTenantEconomics(mockTenantEconomics(WINDOW));
    expect(totals.total_revenue_micros).toBe(852_900_000);
    expect(totals.gross_margin_micros).toBe(289_300_000);
    // The count is answerable here precisely BECAUSE the question is
    // ungrouped: one row compares with nothing.
    expect(totals.event_count).toBe(93_558);
  });
});

describe("shortId", () => {
  it("shortens UUIDs to an 8-char prefix", () => {
    expect(shortId("3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301")).toBe("3e7f0a41…");
    expect(shortId("short")).toBe("short");
  });
});
