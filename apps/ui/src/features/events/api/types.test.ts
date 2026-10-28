// The events page's two views of the one query keep the revenue view their
// answer was stated under (#548). Both values, so a narrowing that wrote either
// word in place of the answer's would fail the other.

import { describe, expect, it } from "vitest";

import { knownMeasures } from "@/lib/economic-scenarios";
import { REVENUE_BASIS_VALUES, type RevenueBasis } from "@/lib/vocabulary";

import { asTimeseries, toWindowTotals, type Economics } from "./types";

function answer(basis: RevenueBasis, bucket: string | null): Economics {
  return {
    period_start: "2026-07-01",
    period_end: "2026-07-31",
    group_by: [],
    bucket,
    basis,
    economic_data_available_from: "2020-07-01",
    measurement_data_available_from: "2026-01-01",
    foreign_currency_subscription_count: 0,
    rows: [{
      bucket_start: bucket === null ? null : "2026-07-01T00:00:00Z",
      grouping_field_value: [],
      grouping_field_value_status: [],
      measures: knownMeasures({ cost_micros: 3_000_000, revenue_micros: 8_000_000, events: 2 }),
    }],
    context: [],
  };
}

describe("the events narrowings keep the answer's basis", () => {
  it.each(REVENUE_BASIS_VALUES)("keeps %s on the strip's totals and the chart's series", (basis) => {
    expect(toWindowTotals(answer(basis, null)).basis).toBe(basis);
    expect(asTimeseries(answer(basis, "day")).basis).toBe(basis);
  });
});
