import { describe, expect, it } from "vitest";

import {
  CUSTOMER_REVENUE,
  drawableMeasure,
  GROSS_MARGIN,
  statedValue,
  SUPPLIER_COGS,
  type MeasureFigure,
} from "@/lib/economic-query";
import type { AnalyticsMeasure } from "@/lib/vocabulary";

import {
  mockCustomerEconomics,
  mockGroupedEconomics,
  mockTenantEconomics,
} from "../api/mock-data";
import {
  toBreakdown,
  toCustomerRows,
  toTenantEconomics,
  type BreakdownRow,
  type CustomerEconomicsRow,
} from "../api/types";
import { shortId, sortCustomers, topWithOther } from "./economics";

const WINDOW = { start_date: "2026-07-01", end_date: "2026-07-23" };

/** One figure, known unless the case says otherwise. */
function fig(
  measure: AnalyticsMeasure,
  value: number | null,
  status = "known",
): MeasureFigure {
  return {
    measure,
    status,
    value,
    unresolved_event_count: 0,
    unpriced_event_count: 0,
    available_from: null,
  };
}

function customer(
  id: string,
  revenue: number,
  margin: number | null,
  marginStatus = "known",
): CustomerEconomicsRow {
  return {
    customer_id: id,
    revenue: fig(CUSTOMER_REVENUE, revenue),
    cost: fig(SUPPLIER_COGS, revenue - (margin ?? 0)),
    margin: fig(GROSS_MARGIN, margin, marginStatus),
    events: null,
  };
}

describe("sortCustomers", () => {
  const rows = [customer("a", 100_000_000, 50_000_000), customer("b", 900_000_000, 20_000_000)];

  it("sorts descending by the requested key", () => {
    expect(sortCustomers(rows, "revenue").map((r) => r.customer_id)).toEqual(["b", "a"]);
    expect(sortCustomers(rows, "margin").map((r) => r.customer_id)).toEqual(["a", "b"]);
    expect(sortCustomers(rows, "margin_pct").map((r) => r.customer_id)).toEqual(["a", "b"]);
  });

  // ⚠ A ROW STATING NO MARGIN MUST NOT SORT AS IF IT STATED ZERO, which is
  // where it would land if the comparator coerced — in the middle of the table,
  // between the profitable and the unprofitable, reading as a claim about a
  // customer UBB cannot report on.
  it("files a customer with no margin last rather than as a zero", () => {
    const withAGap = [
      ...rows,
      customer("gap", 400_000_000, null, "unavailable_at_requested_grain"),
      // A figure under a state that states none is a gap too, whatever number
      // the wire carries beside it.
      customer("placed", 400_000_000, 99_000_000_000, "unavailable_at_requested_grain"),
    ];
    expect(sortCustomers(withAGap, "margin").map((r) => r.customer_id)).toEqual(
      ["a", "b", "gap", "placed"],
    );
    expect(sortCustomers(withAGap, "margin_pct").map((r) => r.customer_id)).toEqual(
      ["a", "b", "gap", "placed"],
    );
  });
});

describe("topWithOther", () => {
  const rows: BreakdownRow[] = Array.from({ length: 10 }, (_, i) => ({
    group_value: `group-${i}`,
    cost: fig(SUPPLIER_COGS, 5_000_000),
    revenue: fig(CUSTOMER_REVENUE, (10 - i) * 1_000_000),
  }));

  it("keeps the top 8 by revenue and folds the rest into Other", () => {
    const bars = topWithOther(rows, 8);
    expect(bars).toHaveLength(9);
    expect(bars[0]?.name).toBe("group-0");
    const other = bars[8];
    expect(other?.isOther).toBe(true);
    expect(other?.name).toBe("Other (2)");
    // group-8 (2) + group-9 (1) revenue, folded with its state.
    expect(other?.plotted).toMatchObject({ status: "known", value: 3_000_000 });
    expect(other?.cost).toMatchObject({ status: "known", value: 10_000_000 });
  });

  // ⚠ The fold used to sum numbers, so a folded row with no figure made the
  // "Other" bar smaller rather than unstateable.
  it("folds a row stating no figure into an Other that states none", () => {
    const gapped = rows.map((row, i) =>
      i === 9 ? { ...row, cost: fig(SUPPLIER_COGS, null, "unavailable_outside_retention_horizon") } : row,
    );
    const other = topWithOther(gapped, 8)[8];
    expect(other?.cost?.status).toBe("unavailable_outside_retention_horizon");
    expect(statedValue(other?.cost ?? null)).toBeNull();
  });

  // ⚠ The grain case (#510): a revenue that cannot be placed is not drawn —
  // the part that could be placed is a floor, and a bar is a total.
  it("draws the cost where the revenue cannot be placed at this grain", () => {
    const grain = rows.map((row) => ({
      ...row,
      revenue: fig(CUSTOMER_REVENUE, 7_000_000, "unavailable_at_requested_grain"),
    }));
    expect(drawableMeasure(grain)).toBe(SUPPLIER_COGS);
    expect(topWithOther(grain, 8)[0]?.plotted?.measure).toBe(SUPPLIER_COGS);
    expect(drawableMeasure(rows)).toBe(CUSTOMER_REVENUE);
  });

  it("labels an absent group value as unattributed", () => {
    const bars = topWithOther([
      { group_value: null, cost: fig(SUPPLIER_COGS, 0), revenue: fig(CUSTOMER_REVENUE, 1) },
    ]);
    expect(bars[0]?.name).toBe("(unattributed)");
  });
});

// ⚠ THE LEGACY-FALLBACK SUITE IS GONE WITH THE SHAPE IT NARROWED (#501). The
// one economic query DECLARES its row, so what is left to assert is the
// narrowing itself — and since #510, that the narrowing keeps each measure's
// STATE and the answer's context rather than a number coalesced to zero.
describe("toBreakdown", () => {
  it("reads the grouped value and both figures off a declared row", () => {
    const breakdown = toBreakdown(mockGroupedEconomics(WINDOW, "provider"));
    expect(breakdown.rows[0]?.group_value).toBe("openai");
    expect(breakdown.rows[0]?.cost).toMatchObject({ status: "known", value: 245_000_000 });
  });

  // ⚠ Grouped by a supplier, the subscription cannot be placed: the revenue
  // reads as the state on every row and the money is in the context. The rows
  // sum to the usage alone, and the subscription is the rest — never dropped.
  it("carries the revenue's state and the context that holds the rest", () => {
    const breakdown = toBreakdown(mockGroupedEconomics(WINDOW, "provider"));
    expect(breakdown.rows.every((row) => row.revenue?.status === "unavailable_at_requested_grain")).toBe(true);
    const placed = breakdown.rows.reduce((sum, row) => sum + (row.revenue?.value ?? 0), 0);
    const context = breakdown.context.reduce((sum, row) => sum + row.amount_micros, 0);
    expect(placed + context).toBe(852_900_000);
  });

  it("places the subscription grouped by the customer, and states no context", () => {
    const breakdown = toBreakdown(mockGroupedEconomics(WINDOW, "customer"));
    expect(breakdown.context).toEqual([]);
    expect(breakdown.rows.every((row) => row.revenue?.status === "known")).toBe(true);
  });

  // ⚠ THE ROW WHOSE AXIS VALUE IS ABSENT IS A ROW, and dropping it would make
  // the bars stop summing to the total above them.
  it("keeps a row whose axis value was never recorded", () => {
    const breakdown = toBreakdown(mockGroupedEconomics(WINDOW, "task_type"));
    const absent = breakdown.rows.filter((row) => row.group_value === null);
    expect(absent).toHaveLength(1);
    expect(absent[0]?.cost?.value).toBe(42_000_000);
  });
});

describe("toCustomerRows", () => {
  it("reads one row per customer, keyed by the identity the axis groups", () => {
    const rows = toCustomerRows(mockCustomerEconomics(WINDOW));
    expect(rows).toHaveLength(5);
    expect(rows[0]?.revenue).toMatchObject({ status: "known", value: 541_500_000 });
    expect(rows[0]?.customer_id).toMatch(/^[0-9a-f-]{36}$/);
  });

  // ⚠ EACH ROW'S OWN COMPLETENESS, NOT THE WINDOW'S.
  it("carries each row's own completeness", () => {
    const rows = toCustomerRows(mockCustomerEconomics(WINDOW));
    const partial = rows.filter((row) => row.cost?.status === "incomplete");
    expect(partial).toHaveLength(1);
    expect(partial[0]?.cost?.unresolved_event_count).toBe(4);
  });
});

describe("toTenantEconomics", () => {
  it("narrows the single row an ungrouped answer always has", () => {
    const totals = toTenantEconomics(mockTenantEconomics(WINDOW));
    expect(totals.revenue).toMatchObject({ status: "known", value: 852_900_000 });
    // The count is answerable here precisely BECAUSE the question is
    // ungrouped: one row compares with nothing.
    expect(totals.events).toMatchObject({ status: "known", value: 93_558 });
  });

  // ⚠ §15: the window's cost is a floor by nova-ai's four uncosted events,
  // so the margin is INCOMPLETE — while the revenue beside it reads known.
  it("reads the margin incomplete where the cost is, whatever the revenue says", () => {
    const totals = toTenantEconomics(mockTenantEconomics(WINDOW));
    expect(totals.revenue?.status).toBe("known");
    expect(totals.margin).toMatchObject({
      status: "incomplete",
      value: 289_300_000,
      unresolved_event_count: 4,
    });
  });
});

describe("shortId", () => {
  it("shortens UUIDs to an 8-char prefix", () => {
    expect(shortId("3e7f0a41-5c2d-4b8e-9f10-8a64c1d2e301")).toBe("3e7f0a41…");
    expect(shortId("short")).toBe("short");
  });
});
